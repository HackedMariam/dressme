"""Run the full DressMe ingestion pipeline end to end."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from tqdm import tqdm

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
    parser.add_argument(
        "--ocr-only",
        default="",
        help=(
            "Comma-separated PDF filename substrings to OCR. Other PDFs are "
            "extracted without OCR."
        ),
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Ignore the per-document extraction cache",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Re-extract every PDF instead of reusing cached pages",
    )
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    if not args.skip_extract and not args.no_ocr and not args.ocr_only:
        print(
            "WARNING: OCR is enabled for every PDF. Use --ocr-only with "
            "filename substrings to OCR only the scanned books."
        )

    steps = []
    if not args.skip_extract:
        extract_args = []
        if args.no_ocr:
            extract_args.append("--no-ocr")
        if args.ocr_only:
            extract_args.extend(["--ocr-only", args.ocr_only])
        if args.no_cache:
            extract_args.append("--no-cache")
        if args.refresh:
            extract_args.append("--refresh")
        steps.append(("ingestion.pdf_extractor", extract_args))
    steps.append(("ingestion.chunker", []))
    if not args.skip_embed:
        embed_args = ["--limit", str(args.limit)] if args.limit else []
        steps.append(("ingestion.embedder", embed_args))
    if not args.skip_index:
        index_args = ["--prune"] if args.prune else []
        steps.append(("ingestion.indexer", index_args))

    with tqdm(
        total=len(steps),
        desc="Pipeline",
        unit="step",
        dynamic_ncols=True,
    ) as progress:
        for module, extra in steps:
            progress.set_description(
                f"Pipeline: {module.rsplit('.', 1)[-1]}"
            )
            run_step(module, *extra)
            progress.update(1)

    chunks_file = Path(settings.chunks_file)
    if chunks_file.exists():
        with chunks_file.open("r", encoding="utf-8") as file:
            count = sum(1 for line in file if line.strip())
        print(f"\nChunk file check: {count} chunks in {chunks_file}")

    print(f"Quality report: {settings.quality_report_file}")
    print("Pipeline complete.")


if __name__ == "__main__":
    main()
