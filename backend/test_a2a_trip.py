"""The Trip Agent over A2A, and its call to the Gap Agent (agent to agent)."""
from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from a2a_protocol import A2AClient
from backend import main
from backend.main import create_app
from packing_backend.trip_agent.wardrobe import SyntheticWardrobeProvider


class Reply:
    status_code = 200
    ok = True

    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


def bridge(test_client: TestClient) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        reply = test_client.request(request.method, request.url.path, content=request.content,
                                    headers={k: v for k, v in request.headers.items() if k != "host"})
        return httpx.Response(reply.status_code, content=reply.content, headers={"content-type": "application/json"})
    return httpx.MockTransport(handler)


@pytest.fixture()
def trip(monkeypatch):
    monkeypatch.setattr("backend.main.requests.get", lambda url, **kwargs: Reply(
        {"id": "user-1"} if url.endswith("/api/me") else [{"id": "example"}]))
    app = create_app(use_llm=False, allow_weather_network=False,
                     wardrobe_provider_factory=lambda _: SyntheticWardrobeProvider())
    with TestClient(app) as test_client:
        yield test_client, A2AClient("http://testserver/a2a/trip", token="t", transport=bridge(test_client))


def test_the_trip_agent_publishes_its_card_and_plans_a_trip_over_a2a(trip):
    _, a2a = trip
    card = a2a.card()
    assert card["name"] == "DressMe Trip Agent" and card["skills"][0]["id"] == "plan-trip-packing"
    assert card["security"] == [{"bearer": []}]

    task = a2a.send(data={"trip": {"destination": "Paris", "start_date": "2027-06-03", "end_date": "2027-06-07",
                                   "activities": ["sightseeing", "formal-dinner"], "max_luggage_weight_kg": 8}})
    data = a2a.data_of(task)
    assert a2a.state_of(task) == "completed" and task["contextId"] == data["session_id"]
    assert data["optimization_status"] in {"OPTIMAL", "FEASIBLE"} and data["capsule"]["selected_items"]
    assert data["checklist"]["items"]


def test_a_missing_detail_makes_the_task_input_required_and_the_same_context_continues_it(trip):
    _, a2a = trip
    task = a2a.send("I want to travel to Paris")
    assert a2a.state_of(task) == "input-required" and a2a.text_of(task)
    session_id = task["contextId"]
    followed = a2a.send("Paris from 2027-06-03 to 2027-06-07, sightseeing, 8 kg luggage", context_id=session_id)
    assert followed["contextId"] == session_id            # same trip session, not a new one


def test_the_trip_agent_asks_the_gap_agent_over_a2a_with_the_users_token(trip, monkeypatch):
    test_client, a2a = trip
    calls = []

    class FakeGapClient:
        def __init__(self, url, token=None, timeout=0):
            calls.append((url, token))

        def send(self, text="", data=None, context_id=None):
            calls.append((text, data))
            return {"id": "task-9", "status": {"state": "completed", "message": {"parts": [
                {"kind": "text", "text": "Missing: a light rain jacket."}]}},
                "artifacts": [{"parts": [{"kind": "data", "data": {"ranking": {"ranked_gaps": [{"name": "Rain jacket"}]}}}]}]}

        state_of = staticmethod(A2AClient.state_of)
        text_of = staticmethod(A2AClient.text_of)
        data_of = staticmethod(A2AClient.data_of)

    monkeypatch.setattr(main, "A2AClient", FakeGapClient)
    task = a2a.send(data={"trip": {"destination": "Paris", "start_date": "2027-06-03", "end_date": "2027-06-07",
                                   "activities": ["sightseeing"], "max_luggage_weight_kg": 8}})
    session_id = task["contextId"]
    result = test_client.post(f"/api/trips/{session_id}/gap-analysis", headers={"Authorization": "Bearer t"})
    assert result.status_code == 200, result.text
    findings = result.json()["gap_analysis"]["findings"]
    assert findings["provider"] == "a2a:gap-agent" and findings["answer"] == "Missing: a light rain jacket."
    assert findings["ranked_gaps"] == [{"name": "Rain jacket"}]
    assert ("http://127.0.0.1:8001/a2a/gap", "Bearer t") in calls                            # the user's token travels
    sent = [data for _, data in calls if isinstance(data, dict)]
    assert len(sent) == 1 and sent[0]["capsule"]["trip"]["destination"] == "Paris"           # and the trip, as data
