"""RAG_TABLE: the knowledge table and its RPCs are configurable (default: knowledge_chunks)."""

from __future__ import annotations

import pytest

from config import reload_settings


class FakeQuery:
    def __init__(self, data):
        self.data = data
        self.count = len(data)

    def execute(self):
        return self


class FakeSupabase:
    """Records every RPC name and table name used by the retriever."""

    def __init__(self):
        self.rpcs, self.tables = [], []

    def rpc(self, name, params):
        self.rpcs.append(name)
        return FakeQuery([{"chunk_id": "c1", "content": "x", "source": "s", "page": 1, "title": "t",
                           "section": "s", "category": "c", "topics": [], "document_id": "d",
                           "similarity": 0.9}])

    def table(self, name):
        self.tables.append(name)
        return self

    def select(self, *args, **kwargs):
        return self

    def limit(self, *args):
        return FakeQuery([{"embedding_version": "v1"}])


@pytest.fixture
def fake(monkeypatch):
    from rag import retriever
    client = FakeSupabase()
    monkeypatch.setattr(retriever, "get_supabase", lambda: client)
    monkeypatch.setattr(retriever, "_VECTOR_RPC_HAS_THRESHOLD", None)
    monkeypatch.setattr(retriever, "_KEYWORD_RPC_AVAILABLE", None)
    return client


def test_default_table_is_unchanged(monkeypatch):
    monkeypatch.delenv("RAG_TABLE", raising=False)
    settings = reload_settings()
    assert settings.rag_table == "knowledge_chunks"
    assert (settings.match_rpc, settings.search_rpc) == ("match_knowledge_chunks", "search_knowledge_chunks")


def test_v2_table_uses_v2_rpcs(monkeypatch):
    monkeypatch.setenv("RAG_TABLE", "knowledge_chunks_v2")
    settings = reload_settings()
    assert (settings.match_rpc, settings.search_rpc) == ("match_knowledge_chunks_v2", "search_knowledge_chunks_v2")


@pytest.mark.parametrize("name", ["knowledge chunks", "Knowledge", "chunks;drop", "1table", ""])
def test_invalid_table_name_is_rejected(monkeypatch, name):
    monkeypatch.setenv("RAG_TABLE", name)
    settings = reload_settings()
    errors = settings.validate(strict=False)
    if name:
        assert any("RAG_TABLE" in e for e in errors)
    else:                                                   # empty -> default table
        assert settings.rag_table == "knowledge_chunks"


@pytest.mark.parametrize("table, match, search", [
    (None, "match_knowledge_chunks", "search_knowledge_chunks"),
    ("knowledge_chunks_v2", "match_knowledge_chunks_v2", "search_knowledge_chunks_v2"),
])
def test_retriever_calls_the_configured_rpcs(monkeypatch, fake, table, match, search):
    from rag import retriever
    if table:
        monkeypatch.setenv("RAG_TABLE", table)
    else:
        monkeypatch.delenv("RAG_TABLE", raising=False)
    monkeypatch.setenv("RAG_HYBRID_ENABLED", "true")
    reload_settings()
    retriever._vector_search([0.0] * 384, match_count=5, min_similarity=0.0)
    retriever._keyword_search("wool sweater", match_count=5)
    assert fake.rpcs == [match, search]
    retriever.get_index_embedding_versions()
    assert fake.tables == [table or "knowledge_chunks"]
