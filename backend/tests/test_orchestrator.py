"""The Orchestrator (LangGraph): routing, memory of the conversation, delegation over A2A. The agents are replaced by fakes."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from a2a_protocol import A2AError  # noqa: E402
from app import agent, config, orchestrator_agent as orch, wardrobe_agent  # noqa: E402


class FakeA2A:
    """Stands for the Trip Agent and the Gap Agent: one scripted task per message, the calls are recorded."""
    calls = []
    script = []

    def __init__(self, url, token=None, timeout=0):
        self.url, self.token = url, token

    def send(self, text="", data=None, context_id=None):
        FakeA2A.calls.append((self.url, self.token, text, context_id))
        result = FakeA2A.script.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    state_of = staticmethod(lambda task: task["status"]["state"])
    text_of = staticmethod(lambda task: task["status"]["message"]["parts"][0]["text"])
    data_of = staticmethod(lambda task: {})


def task(state, text, context="ctx-1"):
    return {"id": "t", "contextId": context, "status": {"state": state, "message": {"parts": [{"kind": "text", "text": text}]}}}


@pytest.fixture
def env(monkeypatch):
    FakeA2A.calls, FakeA2A.script = [], []
    monkeypatch.setattr(orch, "A2AClient", FakeA2A)
    monkeypatch.setattr(orch, "_GRAPH", None)
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")                    # no LLM: the rules route
    monkeypatch.setattr(wardrobe_agent, "list_items", lambda user_id: [{"id": "a", "name": "Navy Blazer"}])
    return monkeypatch


def test_the_rules_point_each_request_to_its_agent():
    assert orch.rule_candidates("Prepare ma valise pour Paris") == ["trip"]
    assert orch.rule_candidates("What should I wear tomorrow?") == ["stylist"]
    assert orch.rule_candidates("How many tops do I own?") == ["wardrobe"]
    assert orch.rule_candidates("What is my wardrobe missing for work?") == ["gap"]
    assert orch.rule_candidates("Should I buy this jacket?") == ["redirect"]
    assert orch.rule_candidates("Build me three outfits for work") == ["outfit"]


def test_the_llm_chooses_but_only_among_the_known_agents():
    llm = lambda messages: json.dumps({"agent": "trip", "why": "packing"})
    assert orch.decide_route("anything", [], llm) == ("trip", "packing")
    assert orch.decide_route("what should I wear", [], lambda m: json.dumps({"agent": "evil", "why": "x"})) == ("stylist", "rules")
    assert orch.decide_route("what should I wear", [], lambda m: "not json") == ("stylist", "rules")
    assert orch.decide_route("hello there", [], None) == ("clarify", "no rule matched")


def test_a_follow_up_is_routed_with_the_recent_conversation():
    seen = {}

    def llm(messages):
        seen["messages"] = messages
        return json.dumps({"agent": "stylist", "why": "follow-up"})

    history = [{"role": "user", "text": "what should I wear?"}, {"role": "assistant", "text": "The blazer.", "agent": "stylist"}]
    orch.decide_route("and for Friday?", history, llm)
    assert [m["content"] for m in seen["messages"][1:]] == ["what should I wear?", "The blazer.", "and for Friday?"]


def test_the_stylist_answers_style_questions_in_this_service(env):
    env.setattr(agent, "chat", lambda items, message, place, authorization=None: {"reply": "Wear the blazer.", "items": items, "sections": {"why": ["x"]},
                                                              "weather": None, "sources": [], "filters": []})
    result = orch.chat("u1", "What should I wear tomorrow?", place={"city": "Tunis"})
    assert (result["agent"], result["agent_label"], result["reply"]) == ("stylist", "AI Stylist", "Wear the blazer.")
    assert result["agents_called"] == ["AI Stylist"] and result["data"]["sections"] == {"why": ["x"]}


def test_the_trip_agent_is_called_over_a2a_with_the_users_token_and_its_question_is_continued(env):
    FakeA2A.script = [task("input-required", "Which dates?", "trip-7"), task("completed", "Packing list ready.", "trip-7")]
    first = orch.chat("u1", "Prepare ma valise pour Paris", authorization="Bearer tok", thread_id="th1")
    assert first["agent"] == "trip" and first["state"] == "input-required" and first["reply"] == "Which dates?"
    assert FakeA2A.calls[0] == (orch.TRIP_URL, "Bearer tok", "Prepare ma valise pour Paris", None)
    # the answer has no keyword at all: the open question decides who gets it, with the same A2A context
    second = orch.chat("u1", "from 3 to 7 June, 8 kg", authorization="Bearer tok", thread_id="th1")
    assert second["agent"] == "trip" and second["reply"] == "Packing list ready." and second["agents_called"] == ["Trip Agent (A2A)"]
    assert second["action"] == {"page": "help-me-pack", "label": "Open Help Me Pack", "session_id": "trip-7"}   # opens this very trip
    assert first["action"]["session_id"] == "trip-7"
    assert FakeA2A.calls[1][3] == "trip-7"
    third = orch.chat("u1", "how many tops do I own?", thread_id="th1")                 # the question is closed: back to routing
    assert third["agent"] == "wardrobe"


def test_a_change_waiting_for_confirmation_continues_on_yes_only(env):
    answers = iter([{"reply": "Change the colour to navy? Confirm.", "state": "input-required", "context_id": "th2", "items": [],
                     "filters": [], "pending": {"item_id": "a"}, "updated": None},
                    {"reply": "Done.", "state": "completed", "context_id": "th2", "items": [], "filters": [], "pending": None, "updated": {}}])
    seen = []
    env.setattr(wardrobe_agent, "converse", lambda user_id, text, confirm=None, context_id=None: seen.append((text, context_id)) or next(answers))
    first = orch.chat("u1", "fix my grey skirt, it is navy", thread_id="th2")
    assert first["agent"] == "wardrobe" and first["state"] == "input-required"
    second = orch.chat("u1", "yes", thread_id="th2")
    assert second["reply"] == "Done." and seen[1] == ("yes", "th2")


def test_an_unreachable_service_is_reported_not_raised(env):
    FakeA2A.script = [A2AError("unreachable")]
    result = orch.chat("u1", "What is my wardrobe missing for work?")
    assert result["agent"] == "gap" and result["state"] == "failed" and "not reachable" in result["reply"]


def test_shopping_questions_point_to_the_page_that_has_the_photo_upload(env):
    result = orch.chat("u1", "Should I buy this jacket?")
    assert result["agent"] == "redirect" and result["action"] == {"page": "should-i-buy", "label": "Open Should I buy this?"}
    vague = orch.chat("u1", "hello")
    assert vague["agent"] == "clarify" and "What would you like" in vague["reply"]


def test_the_conversations_of_two_users_do_not_mix(env):
    env.setattr(agent, "chat", lambda items, message, place, authorization=None: {"reply": "ok", "items": [], "sections": None, "weather": None, "sources": [], "filters": []})
    FakeA2A.script = [task("input-required", "Which dates?", "trip-1")]
    orch.chat("u1", "Prepare ma valise", thread_id="shared")
    other = orch.chat("u2", "what should I wear", thread_id="shared")             # same thread id, another user
    assert other["agent"] == "stylist"


def test_the_route_returns_the_orchestrators_answer(env):
    from fastapi.testclient import TestClient

    from app import main

    env.setattr(config, "AUTH_ENABLED", False)
    env.setattr(agent, "chat", lambda items, message, place, authorization=None: {"reply": "Wear it.", "items": [], "sections": None, "weather": None, "sources": [], "filters": []})
    reply = TestClient(main.app).post("/api/assistant/chat", json={"message": "what should I wear", "city": "Tunis"})
    assert reply.status_code == 200 and reply.json()["agent"] == "stylist" and reply.json()["thread_id"]
