"""The Gap Agent over A2A: Agent Card, structured goal (no LLM) and plain-words request (the agent picks its tools).

Run from "DressMe UI Blueprint/backend":  python -m unittest discover -s tests -v
"""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import httpx
from fastapi import FastAPI, Header
from fastapi.testclient import TestClient

import a2a_gap
from a2a_protocol import A2AClient


def principal(authorization: str | None = Header(None)) -> str:
    return "user-1"


class FakeMemory:
    def __init__(self):
        self.messages = []

    def start_conversation(self, user_id):
        return "conv-1"

    def add_message(self, conversation_id, role, text):
        self.messages.append((role, text))


class GapOverA2ATest(unittest.TestCase):
    def setUp(self):
        self.memory = FakeMemory()
        app = FastAPI()
        app.include_router(a2a_gap.make_router(self.memory, principal))
        test_client = TestClient(app)

        def handler(request):
            reply = test_client.request(request.method, request.url.path, content=request.content,
                                        headers={k: v for k, v in request.headers.items() if k != "host"})
            return httpx.Response(reply.status_code, content=reply.content, headers={"content-type": "application/json"})

        self.a2a = A2AClient("http://testserver/a2a/gap", transport=httpx.MockTransport(handler))

    def test_the_card_names_the_skill(self):
        card = self.a2a.card()
        self.assertEqual(card["name"], "DressMe Gap Agent")
        self.assertEqual(card["skills"][0]["id"], "wardrobe-gaps")

    def test_a_structured_goal_ranks_the_gaps_without_any_llm(self):
        ranking = {"goal_label": "Winter work days", "ranked_gaps": [
            {"name": "Warm coat", "priority": "high", "description": "a wool coat"}, {"name": "Boots", "priority": "medium"}]}
        with mock.patch.object(a2a_gap, "GapAgentTools", return_value=SimpleNamespace(rank_gaps=lambda goal: ranking)):
            task = self.a2a.send(data={"goal": "winter_work"})
        self.assertEqual(self.a2a.state_of(task), "completed")
        self.assertIn("1. Warm coat (high): a wool coat", self.a2a.text_of(task))
        self.assertEqual(self.a2a.data_of(task)["ranking"], ranking)

    def test_an_unknown_goal_fails_clearly(self):
        task = self.a2a.send(data={"goal": "moon_walk"})
        self.assertEqual(self.a2a.state_of(task), "failed")
        self.assertIn("Unknown goal", self.a2a.text_of(task))

    def test_plain_words_go_to_the_gap_agent_with_the_context_of_the_trip_agent(self):
        seen = {}

        class FakeAgent:
            def __init__(self, tools):
                pass

            def run(self, message, history):
                seen["message"] = message
                return SimpleNamespace(answer="You lack a rain jacket.", ranking={"ranked_gaps": []}, items=[])

        capsule = {"trip": {"destination": "Paris", "activities": ["sightseeing"]}, "days": [1, 2, 3]}
        with mock.patch.object(a2a_gap, "GapAgent", FakeAgent), mock.patch.object(a2a_gap, "GapAgentTools"):
            task = self.a2a.send("Which pieces am I missing for this trip?", data={"capsule": capsule})
        self.assertEqual(self.a2a.text_of(task), "You lack a rain jacket.")
        self.assertIn("trip to Paris", seen["message"])
        self.assertIn("3 day(s)", seen["message"])
        self.assertEqual(self.memory.messages[-1], ("assistant", "You lack a rain jacket."))

    def test_an_empty_request_asks_what_the_user_wants(self):
        task = self.a2a.send(data={"capsule": {}})
        self.assertEqual(self.a2a.state_of(task), "input-required")


if __name__ == "__main__":
    unittest.main()
