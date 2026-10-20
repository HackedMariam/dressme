"""Idempotently index embedded chunks into Supabase.

The indexer upserts by ``chunk_id`` and deletes chunks that are no longer
produced by the current extraction (changed/removed pages). ``--prune`` also
removes chunks belonging to documents that are no longer in the input set.
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from config import get_settings
from ingestion.quality import text_sha256
from rag.supabase_client import execute_with_retries, get_supabase

logger = logging.getLogger(__name__)

TABLE = "knowledge_chunks"
BATCH_SIZE = 250
PAGE_SIZE = 1000

METADATA_COLUMNS = (
    "document_id",
    "title",
    "author",
    "section",
    "category",
    "topics",
    "content_hash",
    "chunk_index",
    "embedding_model",
    "embedding_version",
    "ocr",
    "updated_at",
)


class SchemaCapabilities:
    def __init__(self, *, metadata: bool, content_hash: bool, topics: bool):
        self.metadata = metadata
        self.content_hash = content_hash
        self.topics = topics


def detect_schema(client) -> SchemaCapabilities:
    def can_select(column: str) -> bool:
        try:
            client.table(TABLE).select(column).limit(1).execute()
            return True
        except Exception:
            return False

    metadata = can_select("document_id") and can_select("category")
    return SchemaCapabilities(
        metadata=metadata,
        content_hash=can_select("content_hash"),
        topics=can_select("topics") and metadata,
    )


def load_records(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run chunker.py and embedder.py first."
        )

    records: dict[str, dict] = {}

    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            if not record.get("chunk_id"):
                raise ValueError(
                    f"Missing chunk_id on line {line_number} of {path}"
                )
            if not record.get("embedding"):
                raise ValueError(
                    f"Missing embedding on line {line_number} of {path}"
                )
            record.setdefault(
                "content_hash", text_sha256(record.get("text", ""))
            )
            records[record["chunk_id"]] = record

    return list(records.values())


def fetch_existing(
    client, capabilities: SchemaCapabilities
) -> dict[str, dict]:
    columns = "chunk_id,source"
    if capabilities.content_hash:
        columns += ",content_hash"

    rows: dict[str, dict] = {}
    offset = 0

    while True:
        response = execute_with_retries(
            lambda offset=offset: client.table(TABLE)
            .select(columns)
            .range(offset, offset + PAGE_SIZE - 1)
        )

        batch = response.data or []
        for row in batch:
            rows[row["chunk_id"]] = row

        if len(batch) < PAGE_SIZE:
            break
        offset += PAGE_SIZE

    return rows


def build_payload(record: dict, capabilities: SchemaCapabilities) -> dict:
    payload = {
        "chunk_id": record["chunk_id"],
        "source": record.get("source"),
        "page": record.get("page"),
        "content": record["text"],
        "embedding": record["embedding"],
    }

    if capabilities.content_hash:
        payload["content_hash"] = record.get("content_hash") or text_sha256(
            record["text"]
        )

    if capabilities.metadata:
        payload.update(
            {
                "document_id": record.get("document_id"),
                "title": record.get("title"),
                "author": record.get("author"),
                "section": record.get("section"),
                "category": record.get("category"),
                "chunk_index": record.get("chunk_index"),
                "embedding_model": record.get("embedding_model"),
                "embedding_version": record.get("embedding_version"),
                "ocr": bool(record.get("ocr")),
                "updated_at": datetime.now(UTC).isoformat(),
            }
        )
        if capabilities.topics:
            payload["topics"] = record.get("topics") or []

    return payload


def write_batch(client, payload: list[dict]) -> None:
    """Upsert a batch, falling back to delete+insert on legacy schemas."""
    try:
        execute_with_retries(
            lambda: client.table(TABLE).upsert(
                payload, on_conflict="chunk_id"
            )
        )
        return
    except Exception as error:
        logger.warning(
            "Upsert failed (%s); falling back to delete+insert for %s rows",
            error,
            len(payload),
        )

    chunk_ids = [row["chunk_id"] for row in payload]
    for start in range(0, len(chunk_ids), BATCH_SIZE):
        batch_ids = chunk_ids[start : start + BATCH_SIZE]
        execute_with_retries(
            lambda batch_ids=batch_ids: client.table(TABLE)
            .delete()
            .in_("chunk_id", batch_ids)
        )

    execute_with_retries(lambda: client.table(TABLE).insert(payload))


def delete_chunk_ids(client, chunk_ids: list[str]) -> int:
    deleted = 0
    for start in range(0, len(chunk_ids), BATCH_SIZE):
        batch = chunk_ids[start : start + BATCH_SIZE]
        if not batch:
            continue
        execute_with_retries(
            lambda batch=batch: client.table(TABLE)
            .delete()
            .in_("chunk_id", batch)
        )
        deleted += len(batch)
    return deleted


def compute_stale(
    existing: dict[str, dict],
    records: list[dict],
    *,
    prune: bool,
) -> list[str]:
    current_ids = {record["chunk_id"] for record in records}
    current_sources = {record.get("source") for record in records}

    stale = []
    for chunk_id, row in existing.items():
        if chunk_id in current_ids:
            continue
        if prune or row.get("source") in current_sources:
            stale.append(chunk_id)

    return sorted(stale)


def main() -> None:
    settings = get_settings()

    parser = argparse.ArgumentParser(
        description="Upsert embedded chunks into Supabase."
    )
    parser.add_argument(
        "input",
        nargs="?",
        default=str(settings.embedded_file),
        help=f"Embedded JSONL (default: {settings.embedded_file})",
    )
    parser.add_argument(
        "--prune",
        action="store_true",
        help="Delete chunks whose document is no longer in the input",
    )
    parser.add_argument(
        "--batch-size", type=int, default=BATCH_SIZE
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned changes without writing to Supabase",
    )
    args = parser.parse_args()

    records = load_records(Path(args.input))
    client = get_supabase()
    capabilities = detect_schema(client)
    existing = fetch_existing(client, capabilities)

    stale = compute_stale(existing, records, prune=args.prune)
    unchanged = sum(
        1
        for record in records
        if (
            existing.get(record["chunk_id"], {}).get("content_hash")
            == record.get("content_hash")
        )
    )

    print(f"Chunks to index: {len(records)}")
    print(f"Already in Supabase: {len(existing)}")
    print(f"Unchanged content hashes: {unchanged}")
    print(f"Stale chunks to delete: {len(stale)}")
    print(
        "Schema metadata: "
        f"{'enabled' if capabilities.metadata else 'legacy (run migration)'}"
    )

    if args.dry_run:
        print("Dry run: no changes written.")
        return

    inserted = 0
    for start in range(0, len(records), args.batch_size):
        batch_records = records[start : start + args.batch_size]
        payload = [
            build_payload(record, capabilities)
            for record in batch_records
        ]
        write_batch(client, payload)
        inserted += len(payload)
        print(f"Upserted {inserted}/{len(records)}...")

    deleted = delete_chunk_ids(client, stale)

    total_response = execute_with_retries(
        lambda: client.table(TABLE)
        .select("chunk_id", count="exact")
        .limit(1)
    )

    print(f"Upserted total: {inserted}")
    print(f"Deleted stale total: {deleted}")
    print(
        "Rows now in Supabase: "
        f"{total_response.count if total_response.count is not None else '?'}"
    )


if __name__ == "__main__":
    main()
