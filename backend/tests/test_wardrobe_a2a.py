"""The agents of BO1 reach the Wardrobe Agent over A2A (with the user's token) and fall back on the in-process agent."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from a2a_protocol import A2AError  # noqa: E402
from app import agent, config, similar_agent, wardrobe_a2a, wardrobe_agent  # noqa: E402

ITEMS = [{"id": "a", "name": "Navy Blazer", "category": "jacket", "category_group": "Outerwear", "color_name": "navy"}]


class FakeClient:
    calls = []
    reply = None
    error = None

    def __init__(self, url, token=None, timeout=0):
        FakeClient.calls.append(("init", url, token))

    def send(self, text="", data=None, context_id=None):
        FakeClient.calls.append(("send", data))
        if FakeClient.error:
            raise FakeClient.error
        return {"status": {"state": "completed"}, "artifacts": [{"parts": [{"kind": "data", "data": FakeClient.reply}]}]}

    state_of = staticmethod(lambda task: task["status"]["state"])
    data_of = staticmethod(lambda task: task["artifacts"][0]["parts"][0]["data"])


@pytest.fixture(autouse=True)
def env(monkeypatch):
    FakeClient.calls, FakeClient.error, FakeClient.reply = [], None, {"items": ITEMS}
    monkeypatch.setattr(wardrobe_a2a, "A2AClient", FakeClient)
    monkeypatch.setattr(wardrobe_agent, "list_items", lambda user_id: [{"id": "local"}])
    monkeypatch.setattr(wardrobe_agent, "ask", lambda items, request: {"reply": "in-process", "items": [], "filters": []})


def test_the_wardrobe_is_read_over_a2a_with_the_users_token():
    assert wardrobe_a2a.list_items("u1", "Bearer tok") == ITEMS
    assert ("init", "http://127.0.0.1:8000/a2a/wardrobe", "Bearer tok") in FakeClient.calls
    assert ("send", {"action": "list"}) in FakeClient.calls


def test_without_a_token_or_when_a2a_fails_the_in_process_agent_answers():
    assert wardrobe_a2a.list_items("u1", None) == [{"id": "local"}] and FakeClient.calls == []      # local mode: no network hop
    FakeClient.error = A2AError("unreachable")
    assert wardrobe_a2a.list_items("u1", "Bearer tok") == [{"id": "local"}]
    assert wardrobe_a2a.ask(ITEMS, "jackets", "Bearer tok")["reply"] == "in-process"


def test_asking_in_plain_words_goes_over_a2a_and_returns_the_pieces_found():
    FakeClient.reply = {"reply": "One blazer.", "items": ITEMS, "filters": [{"category": "jacket"}]}
    answer = wardrobe_a2a.ask([], "my jackets", "Bearer tok")
    assert answer == {"reply": "One blazer.", "items": ITEMS, "filters": [{"category": "jacket"}]}
    assert ("send", {"action": "ask", "request": "my jackets"}) in FakeClient.calls


def test_the_stylist_asks_the_wardrobe_agent_over_a2a_when_it_has_the_users_token(monkeypatch):
    FakeClient.reply = {"reply": "One blazer.", "items": ITEMS, "filters": []}
    script = [SimpleNamespace(content=None, tool_calls=[_call("1", "ask_wardrobe_agent", request="my jackets")]),
              SimpleNamespace(content=json.dumps({"answer": "Wear the Navy Blazer."}), tool_calls=None)]
    llm = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: SimpleNamespace(
        choices=[SimpleNamespace(message=script.pop(0))]))))
    monkeypatch.setattr("openai.OpenAI", lambda **kwargs: llm)
    monkeypatch.setattr(config, "OPENAI_API_KEY", "test")
    reply = agent.chat(ITEMS, "what jackets do I have?", {"city": "Tunis"}, "Bearer tok")
    assert ("send", {"action": "ask", "request": "my jackets"}) in FakeClient.calls
    assert [i["id"] for i in reply["items"]] == ["a"]


def test_the_similar_agent_passes_the_token_to_its_wardrobe_questions(monkeypatch):
    FakeClient.reply = {"reply": "Found.", "items": ITEMS, "filters": []}
    script = [SimpleNamespace(content=None, tool_calls=[_call("1", "ask_wardrobe_agent", request="navy jackets")]),
              SimpleNamespace(content=json.dumps({"pieces": [{"index": 0, "status": "owned", "closest_item_id": "a", "reason": "You own it."}]}), tool_calls=None)]
    llm = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: SimpleNamespace(
        choices=[SimpleNamespace(message=script.pop(0))]))))
    monkeypatch.setattr("openai.OpenAI", lambda **kwargs: llm)
    monkeypatch.setattr(config, "OPENAI_API_KEY", "test")
    monkeypatch.setattr(similar_agent, "_GRAPH", None)
    result = similar_agent.compare(ITEMS, [{"category": "jacket", "color_name": "navy"}], "Bearer tok")
    assert ("send", {"action": "ask", "request": "navy jackets"}) in FakeClient.calls
    assert result["pieces"][0]["status"] == "owned"


def _call(call_id, name, **arguments):
    function = SimpleNamespace(name=name, arguments=json.dumps(arguments))
    call = SimpleNamespace(id=call_id, function=function)
    call.model_dump = lambda: {"id": call_id, "type": "function", "function": {"name": name, "arguments": function.arguments}}
    return call


def test_the_wardrobe_agent_answers_the_ask_action_over_its_a2a_endpoint(monkeypatch):
    from fastapi.testclient import TestClient

    from app import main

    monkeypatch.setattr(config, "AUTH_ENABLED", False)
    monkeypatch.setattr(wardrobe_agent, "list_items", lambda user_id: ITEMS)
    monkeypatch.setattr(wardrobe_agent, "ask", lambda items, request: {"reply": "One blazer.", "items": ITEMS, "filters": [{"text": request}]})
    body = {"jsonrpc": "2.0", "id": 1, "method": "message/send", "params": {"message": {
        "role": "user", "parts": [{"kind": "data", "data": {"action": "ask", "request": "my jackets"}}]}}}
    reply = TestClient(main.app).post("/a2a/wardrobe", json=body).json()["result"]
    data = reply["artifacts"][0]["parts"][0]["data"]
    assert reply["status"]["state"] == "completed" and data["reply"] == "One blazer." and data["items"][0]["id"] == "a"
    assert data["filters"] == [{"text": "my jackets"}]
