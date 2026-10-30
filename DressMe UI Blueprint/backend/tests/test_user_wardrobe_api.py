"""The BO3 API must use BO1's authenticated wardrobe, not a demo or another user."""

import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient

# These integration tests replace ranking with a deterministic fake when XGBoost
# is not installed; the real service still requires the package to start.
if importlib.util.find_spec("xgboost") is None:
    fake_xgboost = types.ModuleType("xgboost")
    fake_xgboost.XGBRanker = type("XGBRanker", (), {})
    sys.modules["xgboost"] = fake_xgboost

import api
import xgboost_ranker
from agent import bo1_client, learning, tools
from agent.memory import AgentMemory


class Response:
    def __init__(self, status, data):
        self.status_code = status
        self.data = data

    def json(self):
        return self.data


@pytest.fixture
def app_client(monkeypatch, tmp_path):
    memory = AgentMemory(tmp_path / "memory.sqlite3")
    monkeypatch.setattr(api, "memory", memory)
    monkeypatch.setattr(learning, "USER_MODELS_DIR", tmp_path / "models")
    requests = []
    wardrobes = {
        "alice": [{"id": "a", "name": "Alice evening dress", "category": "dress", "seasons": ["summer"]}],
        "bob": [{"id": "b", "name": "Bob heels", "category": "shoe", "seasons": ["summer"]}],
        "empty": [],
    }

    def fake_get(url, headers, timeout):
        token = headers["Authorization"].removeprefix("Bearer ")
        requests.append((url, token))
        if token == "bad":
            return Response(401, {})
        if token == "local":
            return Response(200, {"id": "local"})
        if token == "unavailable" and url.endswith("/api/items"):
            return Response(503, {})
        if url.endswith("/api/me"):
            return Response(200, {"id": "alice" if token == "unavailable" else token})
        return Response(200, wardrobes[token])

    monkeypatch.setattr(bo1_client.httpx, "get", fake_get)
    monkeypatch.setattr(tools, "rank_gap_candidates", lambda scored, model_path: [
        {**candidate, "rank": i + 1, "ranking_score": float(len(scored) - i)}
        for i, candidate in enumerate(scored)
    ])
    monkeypatch.setattr(tools, "fashionclip_available", lambda: False)
    yield TestClient(api.app), requests, memory
    memory.connection.close()


def auth(user):
    return {"Authorization": f"Bearer {user}"}


def test_each_user_sees_only_their_own_wardrobe_and_empty_is_empty(app_client):
    client, requests, _ = app_client
    alice = client.get("/api/bo3/gaps?goal=formal_event&interpret=false", headers=auth("alice"))
    bob = client.get("/api/bo3/gaps?goal=formal_event&interpret=false", headers=auth("bob"))
    empty = client.get("/api/bo3/gaps?goal=formal_event&interpret=false", headers=auth("empty"))
    assert alice.status_code == bob.status_code == empty.status_code == 200
    assert [x["name"] for x in alice.json()["covered"]] == ["Formal outfit (evening dress or suit)"]
    assert [x["name"] for x in bob.json()["covered"]] == ["Formal shoes"]
    assert empty.json()["covered"] == []
    assert all(gap["owned_count"] == 0 and gap["redundancy_score"] == 0 for gap in empty.json()["ranked_gaps"])
    assert ("http://127.0.0.1:8000/api/items", "alice") in requests
    assert client.get("/api/bo3/context", headers=auth("empty")).json()["wardrobe_source"]["source"] == "bo1"


def test_auth_and_bo1_failures_never_fall_back_to_sample(app_client):
    client, _, _ = app_client
    assert client.get("/api/bo3/gaps").status_code == 401
    assert client.get("/api/bo3/gaps", headers=auth("bad")).status_code == 401
    assert client.get("/api/bo3/gaps", headers=auth("local")).status_code == 503
    assert client.get("/api/bo3/gaps", headers=auth("unavailable")).status_code == 503


def test_feedback_conversations_and_models_are_user_scoped(app_client, monkeypatch):
    client, _, memory = app_client
    body = {"goal": "formal_event", "candidate_id": "formal_shoes", "relevance": 3}
    assert client.post("/api/bo3/feedback", json=body, headers=auth("alice")).status_code == 200
    assert client.get("/api/bo3/learning", headers=auth("alice")).json()["feedback_labels"] == 1
    assert client.get("/api/bo3/learning", headers=auth("bob")).json()["feedback_labels"] == 0

    class FakeAgent:
        def __init__(self, user_tools):
            self.tools = user_tools
        def run(self, _message, _history):
            return SimpleNamespace(answer=self.tools.get_wardrobe()["items"][0]["name"], ranking=None, trace=[])

    monkeypatch.setattr(api, "GapAgent", FakeAgent)
    alice = client.post("/api/bo3/chat", json={"message": "Hi"}, headers=auth("alice"))
    assert alice.status_code == 200
    assert alice.json()["answer"] == "Alice evening dress"
    conversation = alice.json()["conversation_id"]
    assert memory.owns_conversation(conversation, "alice")
    assert client.post("/api/bo3/chat", json={"message": "Hi", "conversation_id": conversation}, headers=auth("bob")).status_code == 404

    alice_model = learning.user_model_path("alice")
    bob_model = learning.user_model_path("bob")
    for path in (alice_model, bob_model):
        path.parent.mkdir(parents=True)
        path.write_text("model")
    assert client.post("/api/bo3/reset-model", headers=auth("alice")).status_code == 200
    assert not alice_model.exists() and bob_model.exists()


def test_ranker_receives_numeric_array(monkeypatch):
    class Ranker:
        def predict(self, data):
            assert isinstance(data, np.ndarray)
            assert data.shape == (1, len(xgboost_ranker.FEATURES))
            return np.array([0.75])
    monkeypatch.setattr(xgboost_ranker, "load_ranker", lambda _path: Ranker())
    candidate = {name: 0.5 for name in xgboost_ranker.FEATURES}
    assert xgboost_ranker.rank_gap_candidates([candidate], Path("unused"))[0]["ranking_score"] == 0.75
