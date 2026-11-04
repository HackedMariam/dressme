"""Turn extracted pages into metadata-rich, overlapping chunks."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from config import get_settings
from ingestion.quality import classify_topics, slugify, text_sha256

MIN_CHUNK_CHARS = 40


def clean_text(text: str) -> str:
    """Normalize whitespace without removing meaningful punctuation."""
    text = (text or "").replace("\x00", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_text(
    text: str,
    *,
    chunk_size: int = 1000,
    chunk_overlap: int = 150,
) -> list[str]:
    """Split text into overlapping character-based chunks."""
    if chunk_size <= chunk_overlap:
        raise ValueError("chunk_size must be greater than chunk_overlap")

    chunks = []
    start = 0

    while start < len(text):
        end = min(start + chunk_size, len(text))

        if end < len(text):
            boundary = text.rfind(" ", start, end)
            if boundary > start + chunk_size // 2:
                end = boundary

        chunk = text[start:end].strip()
        if len(chunk) >= MIN_CHUNK_CHARS:
            chunks.append(chunk)

        if end >= len(text):
            break

        start = max(end - chunk_overlap, start + 1)

    return chunks


def chunk_pages(
    pages: list[dict],
    *,
    chunk_size: int,
    chunk_overlap: int,
    embedding_model: str,
    embedding_version: str,
) -> list[dict]:
    records: list[dict] = []
    seen: set[str] = set()

    for page_data in pages:
        page_number = page_data.get("page")
        source = page_data.get("source") or "unknown"
        text = clean_text(page_data.get("text", ""))

        if not text:
            continue

        section = page_data.get("section")
        for index, chunk_text in enumerate(
            split_text(
                text,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )
        ):
            chunk_id = (
                f"{slugify(source)}-p{page_number}-c{index}"
            )
            if chunk_id in seen:
                continue
            seen.add(chunk_id)

            page_category, page_topics = classify_topics(
                f"{section or ''}\n{chunk_text}"
            )

            record = {
                "chunk_id": chunk_id,
                "document_id": page_data.get("document_id"),
                "source": source,
                "title": page_data.get("title"),
                "author": page_data.get("author"),
                "page": page_number,
                "page_count": page_data.get("page_count"),
                "section": section,
                "category": page_category,
                "topics": page_topics,
                "chunk_index": index,
                "content_hash": text_sha256(chunk_text),
                "embedding_model": embedding_model,
                "embedding_version": embedding_version,
                "ocr": bool(page_data.get("ocr")),
                "text": chunk_text,
            }
            records.append(record)

    return records


def main() -> None:
    settings = get_settings()

    parser = argparse.ArgumentParser(
        description="Create chunks with document and fashion metadata."
    )
    parser.add_argument(
        "input",
        nargs="?",
        default=str(settings.extracted_file),
        help=f"Extracted pages JSON (default: {settings.extracted_file})",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=str(settings.chunks_file),
        help=f"Output JSONL (default: {settings.chunks_file})",
    )
    parser.add_argument("--chunk-size", type=int, default=settings.chunk_size)
    parser.add_argument(
        "--chunk-overlap", type=int, default=settings.chunk_overlap
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    with input_path.open("r", encoding="utf-8") as file:
        pages = json.load(file)

    records = chunk_pages(
        pages,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
        embedding_model=settings.embedding_model,
        embedding_version=settings.embedding_version,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as output:
        for record in records:
            output.write(json.dumps(record, ensure_ascii=False) + "\n")

    by_source = Counter(record["source"] for record in records)
    by_category = Counter(record["category"] for record in records)
    by_topic: Counter[str] = Counter()
    for record in records:
        by_topic.update(record.get("topics") or [])

    print(f"Pages processed: {len(pages)}")
    print(f"Chunks created: {len(records)}")
    print(f"Documents: {len(by_source)}")
    print(f"Saved to: {output_path}")
    print("Chunks by category:")
    for category, count in by_category.most_common():
        print(f"  - {category}: {count}")
    print("Top topics:")
    for topic, count in by_topic.most_common(8):
        print(f"  - {topic}: {count}")


if __name__ == "__main__":
    main()
