"""Embed chunks and stamp every vector with its model/version."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from config import get_settings


def main() -> None:
    settings = get_settings()

    parser = argparse.ArgumentParser(description="Embed chunked documents.")
    parser.add_argument(
        "input",
        nargs="?",
        default=str(settings.chunks_file),
        help=f"Chunks JSONL (default: {settings.chunks_file})",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=str(settings.embedded_file),
        help=f"Embedded JSONL (default: {settings.embedded_file})",
    )
    parser.add_argument(
        "--batch-size", type=int, default=settings.embedding_batch_size
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Only embed the first N chunks (debugging)",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        raise FileNotFoundError(
            f"{input_path} not found. Run chunker.py first."
        )

    with input_path.open("r", encoding="utf-8") as file:
        records = [
            json.loads(line) for line in file if line.strip()
        ]

    if args.limit:
        records = records[: args.limit]

    if not records:
        raise ValueError("No chunks found to embed.")

    from sentence_transformers import SentenceTransformer

    print(f"Loading embedding model: {settings.embedding_model}")
    model = SentenceTransformer(settings.embedding_model)

    texts = [record["text"] for record in records]

    print(
        f"Generating embeddings for {len(texts)} chunks "
        f"({settings.embedding_version})..."
    )
    embeddings = model.encode(
        texts,
        batch_size=args.batch_size,
        normalize_embeddings=True,
        show_progress_bar=True,
        convert_to_numpy=True,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as output:
        for record, embedding in zip(records, embeddings, strict=True):
            result = {
                **record,
                "embedding_model": settings.embedding_model,
                "embedding_version": settings.embedding_version,
                "embedding": embedding.tolist(),
            }
            output.write(json.dumps(result, ensure_ascii=False) + "\n")

    print(f"Chunks embedded: {len(embeddings)}")
    print(f"Vector dimensions: {embeddings.shape[1]}")
    print(f"Embedding version: {settings.embedding_version}")
    print(f"Saved to: {output_path}")


if __name__ == "__main__":
    main()
