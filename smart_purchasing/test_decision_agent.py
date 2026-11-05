"""The Qwen decision agent of "Should I buy this?": the tool loop, the verdict checks, the backends and the fallbacks.

Run from smart_purchasing/:  python -m unittest test_decision_agent -v
"""
import json
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import decision_agent
from decision_agent import QwenBackend, parse_generation, validate_verdict
from inference import DressMeInferenceEngine
from schemas import Garment

WARDROBE = [
    Garment(id="g1", name="Cream Knit Sweater", category="sweater", color="cream", style=["casual"], seasons=["autumn"], occasions=["work"]),
    Garment(id="g2", name="Navy A-Line Skirt", category="skirt", color="navy", style=["classic"], seasons=["autumn"], occasions=["work"]),
    Garment(id="g3", name="Black Leather Boots", category="shoe", color="black", style=["classic"], seasons=["autumn"], occasions=["work"]),
]
SKIRT = Garment(id="c", name="Navy Pleated Skirt", category="skirt", color="navy", style=["classic"], seasons=["autumn"], occasions=["work"])


class FakeBackend:
    """Plays the fine-tuned Qwen: each call answers with the next scripted reply."""
    available = True
    label = "fake-qwen (test)"

    def __init__(self, script):
        self.script, self.seen = list(script), []

    def chat(self, messages, tools):
        self.seen.append((len(messages), [t["function"]["name"] for t in tools]))
        return self.script.pop(0)


def engine_with(backend):
    engine = DressMeInferenceEngine(skip_llm=True, wardrobe=WARDROBE, use_qwen=False)
    engine.qwen = backend
    return engine


def evaluate(engine):
    return engine.evaluate("missing-candidate.jpg", 35.0, 50.0, "Should I buy this?", detected=SKIRT)


class QwenAgentTest(unittest.TestCase):
    def test_qwen_drives_the_tools_and_its_verdict_becomes_the_agents_verdict(self):
        backend = FakeBackend([
            {"content": "", "tool_calls": [{"name": "analyze_item", "arguments": {"category": "skirt"}},
                                           {"name": "find_similar_items", "arguments": {"category": "skirt"}}]},
            {"content": "", "tool_calls": [{"name": "check_outfit_compatibility", "arguments": {"occasion": "work"}}]},
            {"content": json.dumps({"decision": "SKIP", "score": 31, "matching_item_ids": ["g1", "ghost"],
                                    "reasons": ["You already own a navy skirt.", "Only two outfits."]}), "tool_calls": []},
        ])
        result = evaluate(engine_with(backend))
        verdict = result["agent_verdict"]
        self.assertEqual((verdict["decision"], verdict["score"], verdict["decision_source"]), ("SKIP", 31.0, "qwen-agent"))
        self.assertEqual(verdict["matching_item_ids"], ["g1"])                       # the invented id is dropped
        self.assertEqual(verdict["reasons"][0], "You already own a navy skirt.")
        self.assertEqual(result["decision_agent"]["source"], "qwen-agent")
        self.assertEqual(result["decision_agent"]["tools_called"], ["analyze_item", "find_similar_items", "check_outfit_compatibility"])
        # the evidence of the page is computed by the tools, whatever Qwen asked for
        self.assertIn("redundancy_score", result["tool_evidence"])
        self.assertIn("deterministic_decision", result["tool_evidence"])
        self.assertIn("analyze_wardrobe_gaps", [name for _, names in backend.seen for name in names])   # all tools are offered

    def test_gpt_receives_the_qwen_verdict_and_only_interprets_it(self):
        backend = FakeBackend([{"content": json.dumps({"decision": "BUY", "score": 88, "matching_item_ids": [], "reasons": ["Fills a gap."]}), "tool_calls": []}])
        engine = DressMeInferenceEngine(skip_llm=False, wardrobe=WARDROBE, use_qwen=False)
        engine.qwen = backend
        seen = {}

        def create(**kwargs):
            seen["payload"] = kwargs["messages"][1]["content"]
            seen["system"] = kwargs["messages"][0]["content"]
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({"verdict": ["Yes, buy it: fills a gap."]})))])

        engine.openai_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        result = evaluate(engine)
        self.assertIn('"decision_source": "qwen-agent"', seen["payload"])
        self.assertIn('"decision": "BUY"', seen["payload"])
        self.assertIn("never change or contradict", seen["system"])
        self.assertEqual(result["agent_verdict"]["decision"], "BUY")
        self.assertEqual(result["stylist_sections"]["verdict"], ["Yes, buy it: fills a gap."])

    def test_a_missing_model_or_a_bad_answer_falls_back_on_the_deterministic_evaluation(self):
        unavailable = FakeBackend([])
        unavailable.available = False
        for backend in (unavailable, FakeBackend([{"content": "I think you should buy it!", "tool_calls": []}]),
                        FakeBackend([{"content": json.dumps({"decision": "MAYBE", "score": 10}), "tool_calls": []}])):
            result = evaluate(engine_with(backend))
            self.assertEqual(result["agent_verdict"]["decision_source"], "deterministic")
            self.assertEqual(result["decision_agent"]["source"], "deterministic")
            self.assertIn(result["agent_verdict"]["decision"], ("BUY", "CONSIDER", "SKIP"))
        broken = FakeBackend([])           # chat() raises on the first call
        self.assertEqual(evaluate(engine_with(broken))["agent_verdict"]["decision_source"], "deterministic")


class VerdictAndGenerationTest(unittest.TestCase):
    def test_the_verdict_is_checked(self):
        ok = validate_verdict('{"decision": "don\'t buy", "score": 140, "matching_item_ids": ["a", 3], "reasons": ["x", ""]}', {"a"})
        self.assertEqual(ok, {"decision": "SKIP", "score": 100.0, "matching_item_ids": ["a"], "reasons": ["x"]})
        self.assertEqual(validate_verdict('text {"decision": "BUY", "score": "72"} text', set())["score"], 72.0)
        for bad in ("not json", '{"decision": "BUY"}', '{"decision": "LATER", "score": 3}', "[]", ""):
            self.assertIsNone(validate_verdict(bad, set()))

    def test_qwens_tool_call_text_is_parsed(self):
        text = 'Let me check.\n<tool_call>\n{"name": "find_similar_items", "arguments": {"category": "skirt"}}\n</tool_call>\n<tool_call>{bad}</tool_call>'
        parsed = parse_generation(text)
        self.assertEqual(parsed["tool_calls"], [{"name": "find_similar_items", "arguments": {"category": "skirt"}}])
        self.assertTrue(parsed["content"].startswith("Let me check."))


class BackendChoiceTest(unittest.TestCase):
    def test_no_token_or_off_means_no_qwen(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("HF_TOKEN", None)
            self.assertFalse(QwenBackend().available)
        self.assertFalse(QwenBackend(mode="off", token="hf_x").available)

    def test_the_backend_follows_the_configuration(self):
        self.assertEqual(QwenBackend(mode="local", token="hf_x").mode, "local")
        self.assertEqual(QwenBackend(mode="hf_api", token="hf_x").mode, "hf_api")
        with mock.patch.dict(os.environ, {"HF_ENDPOINT_URL": "https://endpoint.example"}):
            self.assertEqual(QwenBackend(mode="auto", token="hf_x").mode, "hf_api")

    def test_the_hugging_face_api_reply_becomes_a_tool_loop_message(self):
        function = SimpleNamespace(name="analyze_item", arguments={"category": "skirt"})
        reply = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=None, tool_calls=[SimpleNamespace(function=function)]))])
        fake_client = SimpleNamespace(chat_completion=lambda **kwargs: reply)
        backend = QwenBackend(mode="hf_api", token="hf_x")
        backend._client = fake_client
        self.assertEqual(backend.chat([{"role": "user", "content": "hi"}], []),
                         {"content": "", "tool_calls": [{"name": "analyze_item", "arguments": {"category": "skirt"}}]})

    def test_tool_call_history_is_converted_for_qwens_chat_template(self):
        messages = [{"role": "assistant", "content": "", "tool_calls": [{"id": "1", "type": "function",
                     "function": {"name": "analyze_item", "arguments": "{\"category\": \"skirt\"}"}}]},
                    {"role": "tool", "tool_call_id": "1", "content": "{}"}]
        converted = decision_agent._for_template(messages)
        self.assertEqual(converted[0]["tool_calls"][0]["function"]["arguments"], {"category": "skirt"})
        self.assertEqual(converted[1], {"role": "tool", "content": "{}"})


if __name__ == "__main__":
    unittest.main()
