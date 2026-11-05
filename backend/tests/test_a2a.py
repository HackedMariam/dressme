"""A2A (Agent2Agent): the protocol server and client, and the AI Stylist and Outfit Builder served over it."""
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from a2a_protocol import A2AClient, A2AError, AgentCall, AgentResult, Skill, build_router  # noqa: E402
from app import a2a_agents, config  # noqa: E402


def bridge(test_client: TestClient) -> httpx.MockTransport:
    """Lets the A2AClient talk to an in-process FastAPI app."""
    def handler(request: httpx.Request) -> httpx.Response:
        reply = test_client.request(request.method, request.url.path, content=request.content,
                                    headers={k: v for k, v in request.headers.items() if k != "host"})
        return httpx.Response(reply.status_code, content=reply.content, headers={"content-type": "application/json"})
    return httpx.MockTransport(handler)


def echo(call: AgentCall) -> AgentResult:
    if call.text == "boom":
        raise RuntimeError("secret internal detail")
    if call.text == "which city?":
        return AgentResult(text="Which city?", state="input-required", context_id="conversation-42")
    return AgentResult(text=f"echo: {call.text}", data={"data": call.data, "context": call.context_id,
                                                         "who": str(call.principal)})


def bearer(authorization: str | None = Header(None)) -> str:
    if authorization != "Bearer good":
        raise HTTPException(401, "Not signed in")
    return "user-1"


def make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(build_router(prefix="/a2a/echo", name="Echo", version="9", description="Repeats", handler=echo,
                                    principal=bearer, skills=[Skill("echo", "Echo", "Repeats", ["test"], ["hi"])]))
    return app


@pytest.fixture
def client():
    test_client = TestClient(make_app())
    return A2AClient("http://testserver/a2a/echo", token="good", transport=bridge(test_client)), test_client


def rpc(test_client, body, auth="Bearer good"):
    return test_client.post("/a2a/echo", json=body, headers={"Authorization": auth} if auth else {})


def send_body(parts, **extra):
    return {"jsonrpc": "2.0", "id": 7, "method": "message/send",
            "params": {"message": {"kind": "message", "role": "user", "messageId": "m1", "parts": parts, **extra}}}


# ------------------------------------------------------------------------------------------------- Agent Card
def test_the_agent_card_is_public_and_describes_the_agent_and_its_security(client):
    a2a, _ = client
    card = a2a.card()
    assert card["protocolVersion"] == "0.3.0" and card["name"] == "Echo" and card["preferredTransport"] == "JSONRPC"
    assert card["url"] == "http://testserver/a2a/echo"
    assert card["skills"][0]["id"] == "echo" and card["skills"][0]["examples"] == ["hi"]
    assert card["capabilities"]["streaming"] is False
    assert card["security"] == [{"bearer": []}] and card["securitySchemes"]["bearer"]["scheme"] == "bearer"


# ------------------------------------------------------------------------------------------------- message/send
def test_a_message_returns_a_completed_task_with_text_and_a_data_artifact(client):
    a2a, _ = client
    task = a2a.send("hello", data={"goal": "x"})
    assert task["kind"] == "task" and a2a.state_of(task) == "completed"
    assert a2a.text_of(task) == "echo: hello"
    assert a2a.data_of(task) == {"data": {"goal": "x"}, "context": task["contextId"], "who": "user-1"}
    assert task["history"][0]["role"] == "user" and a2a.get_task(task["id"])["id"] == task["id"]


def test_the_agent_can_ask_for_more_and_name_the_conversation(client):
    a2a, _ = client
    task = a2a.send("which city?")
    assert a2a.state_of(task) == "input-required" and task["contextId"] == "conversation-42"
    followed = a2a.send("Paris", context_id=task["contextId"])
    assert followed["contextId"] == "conversation-42"


def test_a_crashing_agent_gives_a_failed_task_without_leaking_the_error(client):
    a2a, _ = client
    task = a2a.send("boom")
    assert a2a.state_of(task) == "failed" and "secret" not in a2a.text_of(task)


# ------------------------------------------------------------------------------------------------- errors
@pytest.mark.parametrize("body,code", [
    ({"jsonrpc": "2.0", "id": 1, "method": "nope"}, -32601),
    ({"jsonrpc": "1.0", "id": 1, "method": "message/send"}, -32600),
    ({"jsonrpc": "2.0", "id": 1, "method": "message/send", "params": {}}, -32602),
    (send_body([]), -32602),
    (send_body([{"kind": "file", "file": {}}]), -32602),
    ({**send_body([{"kind": "text", "text": "x"}]), "method": "message/stream"}, -32004),
    ({"jsonrpc": "2.0", "id": 1, "method": "tasks/get", "params": {"id": "missing"}}, -32001),
])
def test_protocol_errors_use_json_rpc_codes(client, body, code):
    _, test_client = client
    reply = rpc(test_client, body)
    assert reply.status_code == 200 and reply.json()["error"]["code"] == code and reply.json()["id"] == body["id"]


def test_invalid_json_is_a_parse_error(client):
    _, test_client = client
    reply = test_client.post("/a2a/echo", content=b"{nope", headers={"Authorization": "Bearer good", "content-type": "application/json"})
    assert reply.json()["error"]["code"] == -32700


def test_without_valid_credentials_nothing_runs(client):
    _, test_client = client
    assert rpc(test_client, send_body([{"kind": "text", "text": "x"}]), auth=None).status_code == 401
    refused = A2AClient("http://testserver/a2a/echo", token="bad", transport=bridge(test_client))
    with pytest.raises(A2AError, match="refused"):
        refused.send("hello")


def test_a_task_belongs_to_the_caller_who_created_it(client):
    a2a, test_client = client
    task = a2a.send("hello")
    # same endpoint, other user: the task must look unknown
    other = FastAPI()
    other.include_router(build_router(prefix="/a2a/echo", name="Echo", version="9", description="", handler=echo,
                                      principal=lambda authorization=Header(None): "user-2", skills=[]))
    assert TestClient(other).post("/a2a/echo", json={"jsonrpc": "2.0", "id": 1, "method": "tasks/get", "params": {"id": task["id"]}}
                                  ).json()["error"]["code"] == -32001
    cancel = rpc(test_client, {"jsonrpc": "2.0", "id": 2, "method": "tasks/cancel", "params": {"id": task["id"]}})
    assert cancel.json()["error"]["code"] == -32002          # already completed


def test_an_unreachable_agent_is_an_a2a_error():
    def down(request):
        raise httpx.ConnectError("refused", request=request)
    with pytest.raises(A2AError, match="unreachable"):
        A2AClient("http://nowhere.test/a2a/x", transport=httpx.MockTransport(down)).send("hi")
    with pytest.raises(A2AError, match="No Agent Card"):
        A2AClient("http://nowhere.test/a2a/x", transport=httpx.MockTransport(down)).card()


# ------------------------------------------------------------------------------------------------- DressMe agents
ITEMS = [{"id": "a", "name": "Navy blazer", "category": "jacket"}, {"id": "b", "name": "Grey trousers", "category": "pants"}]


@pytest.fixture
def dressme(monkeypatch):
    from app import main
    monkeypatch.setattr(config, "AUTH_ENABLED", False)           # the local user, no Supabase
    monkeypatch.setattr(a2a_agents, "get_store", lambda: SimpleNamespace(list_items=lambda user_id: ITEMS))
    test_client = TestClient(main.app)
    return test_client, A2AClient("http://testserver/a2a/stylist", transport=bridge(test_client))


def test_the_ai_stylist_is_discoverable_and_answers_over_a2a(dressme, monkeypatch):
    test_client, _ = dressme
    seen = {}

    def chat(items, message, place):
        seen.update(items=items, message=message, place=place)
        return {"reply": "My pick: the Navy blazer.", "items": [ITEMS[0]], "sources": [], "weather": None,
                "sections": {"outfit": ["Navy blazer"]}}

    monkeypatch.setattr(a2a_agents.agent, "chat", chat)
    a2a = A2AClient("http://testserver/a2a/stylist", transport=bridge(test_client))
    assert [s["id"] for s in a2a.card()["skills"]] == ["style-advice", "wardrobe-search"]
    task = a2a.send("What should I wear?", data={"city": "Tunis", "country": "Tunisia", "unit": "Celsius"})
    assert a2a.text_of(task) == "My pick: the Navy blazer." and a2a.data_of(task)["items"][0]["name"] == "Navy blazer"
    assert seen["message"] == "What should I wear?" and seen["place"]["city"] == "Tunis" and seen["items"] == ITEMS


def test_the_outfit_builder_serves_outfits_over_a2a(dressme, monkeypatch):
    test_client, _ = dressme
    seen = {}

    def build(items, occasion, season, place, avoid):
        seen.update(occasion=occasion, season=season, avoid=avoid)
        return {"outfits": [{"title": "Smart", "items": ["a", "b"], "weather_note": "17 C", "why": ["Navy suits work"]}],
                "weather": {"city": "Tunis"}, "sources": [], "missing": []}

    monkeypatch.setattr(a2a_agents.outfit_agent, "build", build)
    a2a = A2AClient("http://testserver/a2a/outfit", transport=bridge(test_client))
    task = a2a.send("Outfits for work this winter", data={"avoid": [["a", "b"]]})
    assert (seen["occasion"], seen["season"], seen["avoid"]) == ("work", "winter", [["a", "b"]])
    assert a2a.text_of(task) == "1. Smart: Navy blazer + Grey trousers"
    assert a2a.data_of(task)["outfits"][0]["items"] == [{"id": "a", "name": "Navy blazer", "category": "jacket"},
                                                        {"id": "b", "name": "Grey trousers", "category": "pants"}]


def test_an_empty_stylist_request_asks_for_more_and_an_empty_wardrobe_fails_the_outfit_builder(dressme, monkeypatch):
    test_client, _ = dressme
    a2a = A2AClient("http://testserver/a2a/stylist", transport=bridge(test_client))
    assert a2a.state_of(a2a.send(data={"city": "Tunis"})) == "input-required"
    monkeypatch.setattr(a2a_agents, "get_store", lambda: SimpleNamespace(list_items=lambda user_id: []))
    outfit = A2AClient("http://testserver/a2a/outfit", transport=bridge(test_client))
    assert outfit.state_of(outfit.send("outfits")) == "failed"
