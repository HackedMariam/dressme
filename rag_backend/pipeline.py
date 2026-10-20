"""Run the full DressMe ingestion pipeline end to end."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from config import RAG_ROOT, get_settings


def run_step(module: str, *args: str) -> None:
    command = [sys.executable, "-m", module, *args]
    print(f"\n$ {' '.join(command)}")
    subprocess.run(command, cwd=RAG_ROOT, check=True)


def main() -> None:
    settings = get_settings()

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-extract", action="store_true")
    parser.add_argument("--skip-embed", action="store_true")
    parser.add_argument("--skip-index", action="store_true")
    parser.add_argument("--prune", action="store_true")
    parser.add_argument("--no-ocr", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    steps = []
    if not args.skip_extract:
        steps.append(
            (
                "ingestion.pdf_extractor",
                (["--no-ocr"] if args.no_ocr else []),
            )
        )
    steps.append(("ingestion.chunker", []))
    if not args.skip_embed:
        embed_args = ["--limit", str(args.limit)] if args.limit else []
        steps.append(("ingestion.embedder", embed_args))
    if not args.skip_index:
        index_args = ["--prune"] if args.prune else []
        steps.append(("ingestion.indexer", index_args))

    for module, extra in steps:
        run_step(module, *extra)

    chunks_file = Path(settings.chunks_file)
    if chunks_file.exists():
        count = sum(
            1
            for line in chunks_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
        print(f"\nChunk file check: {count} chunks in {chunks_file}")

    print(f"Quality report: {settings.quality_report_file}")
    print("Pipeline complete.")


if __name__ == "__main__":
    main()
