"""The Gap Agent's tool loop is the shared LangGraph loop: it calls tools, shows items and ends cleanly.

Run from "DressMe UI Blueprint/backend":  python -m unittest discover -s tests -v
"""

import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent import gap_agent


def call(call_id, name, **arguments):
    function = SimpleNamespace(name=name, arguments=json.dumps(arguments))
    result = SimpleNamespace(id=call_id, function=function)
    result.model_dump = lambda: {"id": call_id, "type": "function", "function": {"name": name, "arguments": function.arguments}}
    return result


class FakeClient:
    def __init__(self, script):
        self.script = list(script)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: SimpleNamespace(
            choices=[SimpleNamespace(message=self.script.pop(0))])))


class FakeTools:
    last_ranking = None
    shown_items = []

    def call(self, name, arguments):
        if name == "rank_gaps":
            self.last_ranking = {"goal": arguments["goal"], "ranked_gaps": [{"name": "Warm coat"}]}
            return self.last_ranking
        return {"ok": True}


def make_agent(script):
    with mock.patch.object(gap_agent, "llm_settings", return_value=("key", "http://x", "model")), \
            mock.patch.object(gap_agent, "OpenAI", return_value=FakeClient(script)):
        return gap_agent.GapAgent(FakeTools())


class GapGraphTest(unittest.TestCase):
    def test_the_agent_calls_its_tools_then_answers_with_the_ranking_and_a_trace(self):
        agent = make_agent([SimpleNamespace(content=None, tool_calls=[call("1", "rank_gaps", goal="winter_work")]),
                            SimpleNamespace(content="You lack a warm coat.", tool_calls=None)])
        result = agent.run("What am I missing for winter work?", [])
        self.assertEqual(result.answer, "You lack a warm coat.")
        self.assertEqual(result.ranking["goal"], "winter_work")
        self.assertEqual([(t["step"], t["tool"]) for t in result.trace], [(1, "rank_gaps")])

    def test_a_model_that_never_stops_calling_tools_ends_with_the_step_limit_message(self):
        looping = [SimpleNamespace(content=None, tool_calls=[call(str(n), "get_wardrobe")]) for n in range(gap_agent.MAX_STEPS + 1)]
        result = make_agent(looping).run("loop", [])
        self.assertIn("step limit", result.answer)

    def test_an_unreachable_model_is_a_runtime_error_for_the_route(self):
        agent = make_agent([])          # the fake raises IndexError on the first call
        with self.assertRaises(RuntimeError):
            agent.run("hello", [])


if __name__ == "__main__":
    unittest.main()
