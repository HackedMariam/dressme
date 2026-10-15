import json
import os
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

INPUT_FILE = Path("data/embedded_chunks.jsonl")
TABLE = "knowledge_chunks"

BATCH_SIZE = 250
PAGE_SIZE = 1000


def get_client():
    load_dotenv()

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get(
        "SUPABASE_KEY"
    )

    if not url or not key:
        raise RuntimeError(
            "Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env"
        )

    return create_client(url, key)


def load_records() -> list[dict]:
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"{INPUT_FILE} not found. Run chunker.py and embedder.py first."
        )

    records = []

    with INPUT_FILE.open("r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue

            record = json.loads(line)

            records.append(
                {
                    "chunk_id": record["chunk_id"],
                    "source": record.get("source"),
                    "page": record.get("page"),
                    "content": record["text"],
                    "embedding": record["embedding"],
                }
            )

    return records


def existing_chunk_ids(client) -> set[str]:
    """Collect already-indexed chunk ids so re-runs never duplicate rows."""
    chunk_ids = set()
    offset = 0

    while True:
        response = (
            client.table(TABLE)
            .select("chunk_id")
            .range(offset, offset + PAGE_SIZE - 1)
            .execute()
        )

        batch = response.data or []
        chunk_ids.update(row["chunk_id"] for row in batch)

        if len(batch) < PAGE_SIZE:
            break

        offset += PAGE_SIZE

    return chunk_ids


def main():
    client = get_client()
    records = load_records()
    seen = existing_chunk_ids(client)

    new_records = [
        record for record in records if record["chunk_id"] not in seen
    ]
    skipped = len(records) - len(new_records)
    inserted = 0

    print(f"Chunks to index: {len(records)}")
    print(f"Already in Supabase (skipped): {skipped}")

    for start in range(0, len(new_records), BATCH_SIZE):
        batch = new_records[start : start + BATCH_SIZE]
        client.table(TABLE).insert(batch).execute()
        inserted += len(batch)
        print(f"Inserted {inserted}/{len(new_records)}...")

    print(f"Inserted total: {inserted}")


if __name__ == "__main__":
    main()
