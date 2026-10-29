"""Tests du client BO5 (RAG), avec urlopen simulé : aucun appel réseau."""

import io
import json
import urllib.error

import pytest

import bo5_client


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def captured(monkeypatch):
    calls = {}

    def install(payload=None, raw=None, error=None):
        def fake_urlopen(request, timeout=None):
            calls.update(url=request.full_url, method=request.get_method(), timeout=timeout,
                         body=json.loads(request.data.decode("utf-8")),
                         headers={k.lower(): v for k, v in request.header_items()})
            if error:
                raise error
            return FakeResponse(raw if raw is not None else json.dumps(payload).encode("utf-8"))
        monkeypatch.setattr(bo5_client.urllib.request, "urlopen", fake_urlopen)
        return calls
    monkeypatch.delenv("BO5_API_URL", raising=False)
    monkeypatch.delenv("BO5_API_KEY", raising=False)
    return install


ASK_RESPONSE = {   # forme d'AskResponse (rag_backend/app.py)
    "answer": "  Pour un entretien, privilégie des pièces sobres.  ",
    "sources": [{"chunk_id": "c1", "source": "Dress to Impress Guide 2020.pdf", "page": 3, "title": None},
                {"chunk_id": "c2", "source": "career.pdf", "title": "Career Closet"},
                {"chunk_id": "c3", "source": "Dress to Impress Guide 2020.pdf", "page": 7}],
    "citations": [], "conversation_id": "x", "grounded": True,
}


def test_success_returns_answer_and_source_titles(captured):
    calls = captured(payload=ASK_RESPONSE)
    result = bo5_client.ask_bo5("Quels conseils pour un entretien ?")
    assert result == {"answer": "Pour un entretien, privilégie des pièces sobres.",
                      "sources": ["Dress to Impress Guide 2020.pdf", "Career Closet"]}
    assert calls["url"] == "http://localhost:8001/ask" and calls["method"] == "POST"
    assert calls["body"] == {"question": "Quels conseils pour un entretien ?", "top_k": 3}
    assert calls["timeout"] == 20
    assert "x-api-key" not in calls["headers"]          # pas de clé : pas de header


def test_api_key_header_and_base_url(captured):
    calls = captured(payload=ASK_RESPONSE)
    bo5_client.ask_bo5("q", base_url="http://127.0.0.1:9000/", api_key="secret-test", top_k=5)
    assert calls["url"] == "http://127.0.0.1:9000/ask"
    assert calls["headers"]["x-api-key"] == "secret-test"
    assert calls["body"]["top_k"] == 5


def test_env_variables_are_used(captured, monkeypatch):
    calls = captured(payload=ASK_RESPONSE)
    monkeypatch.setenv("BO5_API_URL", "http://bo5.local:8001")
    monkeypatch.setenv("BO5_API_KEY", "cle-env")
    bo5_client.ask_bo5("q")
    assert calls["url"] == "http://bo5.local:8001/ask" and calls["headers"]["x-api-key"] == "cle-env"


def test_network_error(captured):
    captured(error=urllib.error.URLError("connexion refusée"))
    with pytest.raises(bo5_client.BO5UnavailableError, match="injoignable"):
        bo5_client.ask_bo5("q")


def test_http_error(captured):
    captured(error=urllib.error.HTTPError("http://localhost:8001/ask", 503, "down", {}, None))
    with pytest.raises(bo5_client.BO5UnavailableError, match="HTTP 503"):
        bo5_client.ask_bo5("q")


@pytest.mark.parametrize("raw", [b"<html>pas du json</html>", b'{"sources": []}', b'["answer"]',
                                 b'{"answer": "ok", "sources": "pas une liste"}'])
def test_invalid_or_unexpected_json(captured, raw):
    captured(raw=raw)
    with pytest.raises(bo5_client.BO5UnavailableError):
        bo5_client.ask_bo5("q")
