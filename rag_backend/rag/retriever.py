"""Hybrid retrieval over the fashion knowledge base.

Vector search is combined with Postgres full-text search using Reciprocal
Rank Fusion (RRF). Weak vector matches are filtered by ``RAG_MIN_SIMILARITY``
so the service can say "not enough information" instead of hallucinating.
"""

from __future__ import annotations

import logging
import math
from functools import lru_cache

from config import get_settings
from rag.supabase_client import (
    SupabaseUnavailable,
    execute_with_retries,
    get_supabase,
)

logger = logging.getLogger(__name__)

# Capability flags avoid retrying a missing RPC on every query. They reset when
# the process restarts (for example after a migration is applied).
_VECTOR_RPC_HAS_THRESHOLD: bool | None = None
_KEYWORD_RPC_AVAILABLE: bool | None = None


class RetrievalUnavailable(RuntimeError):
    """Raised when the knowledge index cannot be queried."""


@lru_cache(maxsize=1)
def get_embedding_model():
    settings = get_settings()

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as error:  # pragma: no cover - install issue
        raise RetrievalUnavailable(
            "sentence-transformers is not installed"
        ) from error

    logger.info("Loading embedding model %s", settings.embedding_model)
    return SentenceTransformer(settings.embedding_model)


def embed_query(query: str) -> list[float]:
    model = get_embedding_model()
    vector = model.encode(
        query,
        normalize_embeddings=True,
    )
    return vector.tolist()


def _as_float(value) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if math.isnan(number) or math.isinf(number):
        return 0.0
    return number


def _normalize_row(row: dict, retrieval: str) -> dict:
    return {
        "chunk_id": row.get("chunk_id"),
        "content": row.get("content") or "",
        "source": row.get("source"),
        "page": row.get("page"),
        "title": row.get("title"),
        "section": row.get("section"),
        "category": row.get("category"),
        "topics": row.get("topics") or [],
        "document_id": row.get("document_id"),
        "similarity": _as_float(row.get("similarity")),
        "retrieval": retrieval,
    }


def _vector_search(
    query_vector: list[float],
    *,
    match_count: int,
    min_similarity: float,
) -> list[dict]:
    global _VECTOR_RPC_HAS_THRESHOLD

    supabase = get_supabase()
    params = {
        "query_embedding": query_vector,
        "match_count": match_count,
        "min_similarity": min_similarity,
    }

    response = None
    if _VECTOR_RPC_HAS_THRESHOLD is not False:
        try:
            response = execute_with_retries(
                lambda: supabase.rpc("match_knowledge_chunks", params)
            )
            _VECTOR_RPC_HAS_THRESHOLD = True
        except Exception as error:
            _VECTOR_RPC_HAS_THRESHOLD = False
            logger.warning(
                "Vector RPC with min_similarity unavailable (%s); "
                "falling back to the legacy two-argument RPC. Apply the "
                "latest Supabase migration to enable the similarity floor.",
                error,
            )

    if response is None:
        try:
            response = execute_with_retries(
                lambda: supabase.rpc(
                    "match_knowledge_chunks",
                    {
                        "query_embedding": query_vector,
                        "match_count": match_count,
                    },
                )
            )
        except Exception as legacy_error:
            raise RetrievalUnavailable(
                f"Vector search failed: {legacy_error}"
            ) from legacy_error

    rows = [
        _normalize_row(row, "vector")
        for row in (response.data or [])
    ]
    return [
        row
        for row in rows
        if row["similarity"] >= min_similarity
    ]


def _keyword_search(query: str, *, match_count: int) -> list[dict]:
    global _KEYWORD_RPC_AVAILABLE

    if _KEYWORD_RPC_AVAILABLE is False:
        return []

    supabase = get_supabase()

    try:
        response = execute_with_retries(
            lambda: supabase.rpc(
                "search_knowledge_chunks",
                {
                    "query_text": query,
                    "match_count": match_count,
                },
            )
        )
        _KEYWORD_RPC_AVAILABLE = True
    except Exception as error:
        _KEYWORD_RPC_AVAILABLE = False
        logger.info(
            "Keyword RPC unavailable (%s); using vector search only. "
            "Apply the latest Supabase migration to enable hybrid search.",
            error,
        )
        return []

    return [
        _normalize_row(row, "keyword")
        for row in (response.data or [])
    ]


def _reciprocal_rank_fusion(
    ranked_lists: list[list[dict]],
    *,
    rrf_constant: int,
) -> list[dict]:
    scores: dict[str, float] = {}
    rows: dict[str, dict] = {}
    retrieval_kinds: dict[str, set[str]] = {}

    for ranked in ranked_lists:
        for rank, row in enumerate(ranked, start=1):
            chunk_id = row.get("chunk_id")
            if not chunk_id:
                continue

            kind = row.get("retrieval") or "vector"
            retrieval_kinds.setdefault(chunk_id, set()).add(kind)
            scores[chunk_id] = scores.get(chunk_id, 0.0) + (
                1.0 / (rrf_constant + rank)
            )

            existing = rows.get(chunk_id)
            if existing is None or row["similarity"] > existing["similarity"]:
                rows[chunk_id] = {**row, "retrieval": kind}

    ordered = sorted(
        rows.values(),
        key=lambda row: scores.get(row["chunk_id"], 0.0),
        reverse=True,
    )
    for row in ordered:
        row["score"] = scores.get(row["chunk_id"], 0.0)
        kinds = retrieval_kinds.get(row["chunk_id"], set())
        row["retrieval"] = "hybrid" if len(kinds) > 1 else next(
            iter(kinds), "vector"
        )

    return ordered


def retrieve(
    query: str,
    top_k: int | None = None,
    *,
    min_similarity: float | None = None,
    candidate_k: int | None = None,
) -> list[dict]:
    """Retrieve relevant fashion knowledge from Supabase.

    Raises:
        RetrievalUnavailable: when the index cannot be reached.
    """
    settings = get_settings()
    top_k = top_k or settings.default_top_k
    candidate_k = candidate_k or max(settings.candidate_k, top_k)
    threshold = (
        settings.min_similarity
        if min_similarity is None
        else min_similarity
    )

    if not query.strip():
        return []

    query_vector = embed_query(query)
    vector_rows = [
        row
        for row in _vector_search(
            query_vector,
            match_count=candidate_k,
            min_similarity=threshold,
        )
        if row.get("similarity", 0.0) >= threshold
    ]

    if not settings.hybrid_enabled:
        return vector_rows[:top_k]

    keyword_rows = _keyword_search(query, match_count=candidate_k)
    if not keyword_rows:
        return vector_rows[:top_k]

    # Keyword-only rows have no cosine score. Keep them only when the vector
    # search also produced at least one credible match, otherwise the answer
    # would silently lose the similarity guard.
    if not vector_rows:
        logger.info(
            "No vector matches above %.3f; dropping keyword-only results",
            threshold,
        )
        return []

    fused = _reciprocal_rank_fusion(
        [vector_rows, keyword_rows],
        rrf_constant=settings.rrf_constant,
    )

    results = []
    seen: set[str] = set()
    for row in fused:
        chunk_id = row.get("chunk_id")
        if not chunk_id or chunk_id in seen:
            continue
        seen.add(chunk_id)
        results.append(row)
        if len(results) >= top_k:
            break

    return results


def get_index_embedding_versions() -> set[str]:
    """Return embedding versions present in the index (best effort)."""
    try:
        response = execute_with_retries(
            lambda: get_supabase()
            .table("knowledge_chunks")
            .select("embedding_version")
            .limit(1000)
        )
    except (SupabaseUnavailable, Exception):
        return set()

    return {
        row["embedding_version"]
        for row in (response.data or [])
        if row.get("embedding_version")
    }
