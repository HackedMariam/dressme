"""Verify the Supabase index and the hardened RAG migration.

Run after ``supabase db push`` and again after re-indexing:

    python verify_setup.py
"""

from __future__ import annotations

import sys

from config import get_settings
from rag.supabase_client import execute_with_retries, get_supabase

TABLE = "knowledge_chunks"


def _has_column(client, column: str) -> bool:
    try:
        client.table(TABLE).select(column).limit(1).execute()
        return True
    except Exception:
        return False


def _has_vector_threshold(client) -> bool:
    try:
        client.rpc(
            "match_knowledge_chunks",
            {
                "query_embedding": [0.0] * 384,
                "match_count": 0,
                "min_similarity": 0.0,
            },
        ).execute()
        return True
    except Exception:
        return False


def _has_keyword_rpc(client) -> bool:
    try:
        client.rpc(
            "search_knowledge_chunks",
            {"query_text": "capsule wardrobe", "match_count": 0},
        ).execute()
        return True
    except Exception:
        return False


def main() -> int:
    settings = get_settings()
    client = get_supabase()

    count_response = execute_with_retries(
        lambda: client.table(TABLE)
        .select("chunk_id", count="exact")
        .limit(1),
        attempts=1,
    )
    count = count_response.count

    checks = {
        "table": count is not None,
        "metadata.document_id": _has_column(client, "document_id"),
        "metadata.category": _has_column(client, "category"),
        "metadata.topics": _has_column(client, "topics"),
        "metadata.content_hash": _has_column(client, "content_hash"),
        "metadata.embedding_version": _has_column(
            client, "embedding_version"
        ),
        "rpc.match_knowledge_chunks(min_similarity)": _has_vector_threshold(
            client
        ),
        "rpc.search_knowledge_chunks": _has_keyword_rpc(client),
    }

    versions: set[str] = set()
    if checks["metadata.embedding_version"]:
        response = execute_with_retries(
            lambda: client.table(TABLE)
            .select("embedding_version")
            .limit(1000),
            attempts=1,
        )
        versions = {
            row["embedding_version"]
            for row in (response.data or [])
            if row.get("embedding_version")
        }

    print(f"Supabase URL: {settings.supabase_url}")
    print(f"Rows in {TABLE}: {count}")
    print(f"Expected embedding version: {settings.embedding_version}")
    print(f"Versions in index: {sorted(versions) or '(none)'}")

    failed = False
    for name, ok in checks.items():
        print(f"[{'ok' if ok else 'MISSING'}] {name}")
        failed = failed or not ok

    if versions and settings.embedding_version not in versions:
        print(
            "WARNING: index embedding version differs from the configured "
            "model; re-run embedder.py and indexer.py."
        )

    print(
        "\nApply the migration with: "
        "npx supabase db push (from the repo root, after supabase link)"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
