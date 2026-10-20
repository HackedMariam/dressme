from __future__ import annotations

import dataclasses

import rag.retriever as retriever
from config import get_settings


def _row(chunk_id: str, source: str, similarity: float = 0.5):
    return {
        "chunk_id": chunk_id,
        "content": f"content {chunk_id}",
        "source": source,
        "page": 1,
        "similarity": similarity,
    }


def test_retrieve_filters_weak_vector_matches(monkeypatch):
    settings = dataclasses.replace(
        get_settings(), hybrid_enabled=False, min_similarity=0.4
    )
    monkeypatch.setattr(retriever, "get_settings", lambda: settings)
    monkeypatch.setattr(retriever, "embed_query", lambda query: [0.1] * 3)

    def fake_vector(query_vector, *, match_count, min_similarity):
        return [
            _row("a", "a.pdf", 0.9),
            _row("b", "b.pdf", 0.1),
        ]

    monkeypatch.setattr(retriever, "_vector_search", fake_vector)

    rows = retriever.retrieve("question", top_k=5)
    assert [row["chunk_id"] for row in rows] == ["a"]


def test_hybrid_rrf_dedupes_chunks(monkeypatch):
    settings = dataclasses.replace(
        get_settings(), hybrid_enabled=True, min_similarity=0.2
    )
    monkeypatch.setattr(retriever, "get_settings", lambda: settings)
    monkeypatch.setattr(retriever, "embed_query", lambda query: [0.1] * 3)

    monkeypatch.setattr(
        retriever,
        "_vector_search",
        lambda *args, **kwargs: [
            _row("a", "a.pdf", 0.8),
            _row("b", "b.pdf", 0.7),
        ],
    )
    monkeypatch.setattr(
        retriever,
        "_keyword_search",
        lambda *args, **kwargs: [
            _row("b", "b.pdf", 0.3),
            _row("c", "c.pdf", 0.2),
        ],
    )

    rows = retriever.retrieve("question", top_k=3)
    ids = [row["chunk_id"] for row in rows]

    assert len(ids) == len(set(ids))
    assert "b" in ids
    assert "a" in ids


def test_keyword_only_results_are_dropped_without_vector_matches(monkeypatch):
    settings = dataclasses.replace(
        get_settings(), hybrid_enabled=True, min_similarity=0.3
    )
    monkeypatch.setattr(retriever, "get_settings", lambda: settings)
    monkeypatch.setattr(retriever, "embed_query", lambda query: [0.1] * 3)
    monkeypatch.setattr(retriever, "_vector_search", lambda *a, **k: [])
    monkeypatch.setattr(
        retriever,
        "_keyword_search",
        lambda *a, **k: [_row("c", "c.pdf", 0.2)],
    )

    assert retriever.retrieve("question") == []
