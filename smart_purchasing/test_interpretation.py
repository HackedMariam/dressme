"""The stylist's answer in "Should I buy this?" comes as separate sections the UI draws in their own zones."""

import json
import unittest
from types import SimpleNamespace

from inference import DressMeInferenceEngine

PAYLOAD = {"user_query": "Should I buy this?", "tool_evidence": {"matching_outfits": []}}


def engine_answering(content):
    """An engine whose LLM replies with `content` (a JSON string) and records what it was asked."""
    engine = DressMeInferenceEngine(skip_llm=True, wardrobe=[])
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        if isinstance(content, Exception):
            raise content
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

    engine.openai_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return engine, calls


class TestStylistSections(unittest.TestCase):
    def test_the_answer_is_split_into_the_four_sections_without_markdown(self):
        engine, calls = engine_answering(json.dumps({
            "verdict": "**CONSIDER** - confidence 83%.",
            "why_it_works": ["- Moderate overlap with your wardrobe.", "2. A real gap in footwear."],
            "ready_to_wear": ["Charcoal top + Blue jeans + these boots"],
            "final_advice": "Wear them with slim trousers.\nKeep the heel clean.",
        }))
        sections = engine._interpret_sections(PAYLOAD)
        self.assertEqual(list(sections), ["verdict", "why_it_works", "ready_to_wear", "final_advice"])
        self.assertEqual(sections["verdict"], ["CONSIDER - confidence 83%."])
        self.assertEqual(sections["why_it_works"], ["Moderate overlap with your wardrobe.", "A real gap in footwear."])
        self.assertEqual(sections["final_advice"], ["Wear them with slim trousers.", "Keep the heel clean."])
        self.assertEqual(calls[0]["response_format"], {"type": "json_object"})
        self.assertNotIn("**", json.dumps(sections))

    def test_the_prompt_asks_for_plain_text_because_the_app_writes_the_titles(self):
        engine, calls = engine_answering(json.dumps({"verdict": ["BUY"]}))
        engine._interpret_sections(PAYLOAD)
        prompt = calls[0]["messages"][0]["content"] + calls[0]["messages"][1]["content"]
        for key in DressMeInferenceEngine.SECTION_KEYS:
            self.assertIn(f'"{key}"', prompt)
        self.assertIn("Never use emojis, markdown", prompt)

    def test_nothing_is_returned_when_the_llm_fails_or_answers_with_nothing_usable(self):
        for content in (RuntimeError("boom"), "not json", "{}", json.dumps({"verdict": [], "final_advice": "  "})):
            engine, _ = engine_answering(content)
            self.assertIsNone(engine._interpret_sections(PAYLOAD), content)
        self.assertIsNone(DressMeInferenceEngine(skip_llm=True, wardrobe=[])._interpret_sections(PAYLOAD))

    def test_the_plain_text_version_keeps_the_titles_for_the_command_line(self):
        engine, _ = engine_answering(json.dumps({"verdict": ["BUY"], "final_advice": ["Wear it often."]}))
        text = engine._interpret_with_gpt(PAYLOAD)
        self.assertEqual(text, "The Verdict\n- BUY\n\nStylist's Final Advice\n- Wear it often.")


if __name__ == "__main__":
    unittest.main()
