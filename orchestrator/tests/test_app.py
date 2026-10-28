"""Tests de l'API FastAPI de l'orchestrateur (services simulés)."""
import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi import testclient  # noqa: E402

import app as orch_app  # noqa: E402
from services import Gateway  # noqa: E402
from test_orchestrator import SERVICES, TOKEN, FakeServices  # noqa: E402


@pytest.fixture
def client():
    fake = FakeServices()
    orch_app.configure(gateway=Gateway(SERVICES, transport=fake), llm=None)
    yield testclient.TestClient(orch_app.app), fake
    orch_app._settings.clear()


@pytest.fixture
def strict():
    fake = FakeServices()
    orch_app.configure(gateway=Gateway(SERVICES, transport=fake), llm=None, require_auth=True)
    yield testclient.TestClient(orch_app.app), fake
    orch_app._settings.clear()


def test_local_chat_without_token(client):
    http, fake = client
    data = http.post("/api/chat", json={"message": "Est-ce que j'ai une jupe noire ?"}).json()
    assert data["route"] == "wardrobe" and data["thread_id"]
    assert data["visited"] == ["route_intent", "wardrobe", "respond"]
    assert 'class="n v"' in data["svg"] and "#556B2F" in data["svg"]
    assert fake.to("bo1")[0]["auth"] is None


def test_token_is_checked_by_bo1_and_forwarded(client):
    http, fake = client
    data = http.post("/api/chat", json={"message": "J'ai un entretien demain, que porter ?", "thread_id": "abc"},
                     headers={"Authorization": f"Bearer {TOKEN}"}).json()
    assert data["route"] == "stylist" and data["thread_id"] == "abc"
    assert fake.to("bo1")[0]["path"] == "/api/me"
    assert fake.to("stylist")[0]["auth"] == f"Bearer {TOKEN}"
    assert TOKEN not in str(data)


def test_require_auth(strict):
    http, _ = strict
    assert http.post("/api/chat", json={"message": "Bonjour"}).status_code == 401
    bad = http.post("/api/chat", json={"message": "Bonjour"}, headers={"Authorization": "Bearer faux"})
    assert bad.status_code == 401
    malformed = http.post("/api/chat", json={"message": "Bonjour"}, headers={"Authorization": "Token x"})
    assert malformed.status_code == 401
    ok = http.post("/api/chat", json={"message": "Bonjour"}, headers={"Authorization": f"Bearer {TOKEN}"})
    assert ok.status_code == 200 and ok.json()["route"] == "clarify"


def test_bo1_down_gives_503_when_a_token_is_sent(client):
    http, fake = client
    fake.down.add("bo1")
    response = http.post("/api/chat", json={"message": "Bonjour"}, headers={"Authorization": f"Bearer {TOKEN}"})
    assert response.status_code == 503 and "ne répond pas" in response.json()["detail"]


def test_graph_endpoint_and_page(client):
    http, _ = client
    data = http.get("/api/graph", params={"visited": "route_intent,knowledge,respond,bidon"}).json()
    assert data["visited"] == ["route_intent", "knowledge", "respond"]
    assert data["svg"].count('class="n v"') == 3
    page = http.get("/").text
    assert "<svg" in page and "Coulisses" in page and "__GRAPH__" not in page


def test_thread_id_with_colon_is_refused(client):
    http, _ = client
    assert http.post("/api/chat", json={"message": "Bonjour", "thread_id": "a:b"}).status_code == 422
