from __future__ import annotations

import dataclasses

import pytest
from fastapi.testclient import TestClient

import app as app_module
from config import get_settings
from rag.llm_client import LLMUnavailable
from rag.retriever import RetrievalUnavailable


@pytest.fixture
def client():
    with TestClient(app_module.app) as test_client:
        yield test_client


def _fake_answer(question: str, **kwargs):
    return {
        "answer": "Wear a neutral blazer [S1].",
        "sources": [
            {
                "chunk_id": "work-clothes-pdf-p1-c0",
                "source": "Work clothes.pdf",
                "page": 1,
                "title": "Work clothes",
                "similarity": 0.81,
                "topics": ["occasions"],
            }
        ],
        "citations": [
            {
                "marker": "[S1]",
                "chunk_id": "work-clothes-pdf-p1-c0",
                "source": "Work clothes.pdf",
                "page": 1,
            }
        ],
        "rewritten_query": question,
        "grounded": True,
        "usage": None,
    }


def test_ask_success_and_history(client, monkeypatch):
    monkeypatch.setattr(
        app_module.rag_service, "answer_question", _fake_answer
    )

    response = client.post(
        "/ask", json={"question": "What should I wear to work?"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["conversation_id"]
    assert body["sources"][0]["chunk_id"] == "work-clothes-pdf-p1-c0"

    history = client.get(
        f"/conversations/{body['conversation_id']}"
    )
    assert history.status_code == 200
    messages = history.json()["messages"]
    assert [message["role"] for message in messages] == [
        "user",
        "assistant",
    ]


def test_ask_rejects_blank_question(client, monkeypatch):
    monkeypatch.setattr(
        app_module.rag_service, "answer_question", _fake_answer
    )
    response = client.post("/ask", json={"question": "   "})
    assert response.status_code == 400


def test_ask_maps_retrieval_failure_to_503(client, monkeypatch):
    def fail(*args, **kwargs):
        raise RetrievalUnavailable("down")

    monkeypatch.setattr(app_module.rag_service, "answer_question", fail)
    response = client.post("/ask", json={"question": "What to wear?"})
    assert response.status_code == 503


def test_ask_maps_llm_failure_to_502(client, monkeypatch):
    def fail(*args, **kwargs):
        raise LLMUnavailable("down")

    monkeypatch.setattr(app_module.rag_service, "answer_question", fail)
    response = client.post("/ask", json={"question": "What to wear?"})
    assert response.status_code == 502


def test_health_reports_component_failures(client, monkeypatch):
    monkeypatch.setattr(
        app_module,
        "_check_supabase",
        lambda: {"ok": False, "error": "db down"},
    )
    monkeypatch.setattr(
        app_module, "_check_llm", lambda: {"ok": True, "model": "test"}
    )
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json()["status"] == "degraded"


def test_health_ok(client, monkeypatch):
    monkeypatch.setattr(
        app_module,
        "_check_supabase",
        lambda: {
            "ok": True,
            "chunks": 10,
            "embedding_versions": ["test-model-v1"],
        },
    )
    monkeypatch.setattr(
        app_module, "_check_llm", lambda: {"ok": True, "model": "test"}
    )
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_streaming_sse(client, monkeypatch):
    def fake_stream(*args, **kwargs):
        yield {
            "type": "sources",
            "sources": [{"source": "a.pdf", "page": 1}],
        }
        yield {"type": "token", "text": "Hello"}
        yield {"type": "token", "text": " world"}
        yield {"type": "done", "citations": [], "grounded": False}

    monkeypatch.setattr(
        app_module.rag_service, "stream_answer", fake_stream
    )

    response = client.post(
        "/ask/stream", json={"question": "What should I wear?"}
    )
    assert response.status_code == 200
    assert "event: sources" in response.text
    assert "event: token" in response.text
    assert "Hello" in response.text

    conversation_id = response.text.split('"conversation_id": "')[1].split(
        '"'
    )[0]
    history = client.get(f"/conversations/{conversation_id}").json()
    assert history["messages"][-1]["content"] == "Hello world"


def test_api_key_required_when_configured(client, monkeypatch):
    monkeypatch.setattr(
        app_module.rag_service, "answer_question", _fake_answer
    )
    client.app.state.settings = dataclasses.replace(
        get_settings(), api_key="secret"
    )

    unauthorized = client.post(
        "/ask", json={"question": "What should I wear?"}
    )
    assert unauthorized.status_code == 401

    authorized = client.post(
        "/ask",
        json={"question": "What should I wear?"},
        headers={get_settings().api_key_header: "secret"},
    )
    assert authorized.status_code == 200


def test_rate_limit_returns_429(client, monkeypatch):
    monkeypatch.setattr(
        app_module.rag_service, "answer_question", _fake_answer
    )
    client.app.state.rate_limiter.limit = 1

    first = client.post("/ask", json={"question": "one"})
    second = client.post("/ask", json={"question": "two"})

    assert first.status_code == 200
    assert second.status_code == 429
    assert "Retry-After" in second.headers
