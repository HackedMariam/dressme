"""Extract page text from PDFs, with OCR fallback and quality checks.

Extraction is cached per document (keyed by the file hash and the OCR
settings). This makes long OCR runs resumable: stopping the process loses at
most the PDF that was being processed, and re-running reuses every completed
document.
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import os
import shutil
from collections.abc import Callable
from pathlib import Path

from tqdm import tqdm

try:
    import pymupdf as fitz  # PyMuPDF >= 1.24
except ImportError:  # pragma: no cover - compatibility with older PyMuPDF
    import fitz  # type: ignore[no-redef]

from config import get_settings
from ingestion.quality import (
    build_quality_report,
    detect_repeated_lines,
    detect_section,
    file_sha256,
    remove_repeated_lines,
)

logger = logging.getLogger(__name__)

CACHE_VERSION = 1
CHECKPOINT_EVERY = 25
_OCR_UNAVAILABLE_WARNED = False
_TESSERACT_PATH: str | None = None

WINDOWS_TESSERACT_PATHS = (
    Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
    Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
)


def _find_tesseract(tesseract_cmd: str | None = None) -> str | None:
    """Return the Tesseract executable path, checking PATH and common dirs."""
    candidates: list[Path] = []
    if tesseract_cmd:
        candidates.append(Path(tesseract_cmd).expanduser())

    which = shutil.which("tesseract")
    if which:
        candidates.append(Path(which))

    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            candidates.extend(
                [
                    Path(local_app_data)
                    / "Programs"
                    / "Tesseract-OCR"
                    / "tesseract.exe",
                    Path(local_app_data)
                    / "Tesseract-OCR"
                    / "tesseract.exe",
                ]
            )
        candidates.extend(WINDOWS_TESSERACT_PATHS)

    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return None


def _ensure_tesseract(tesseract_cmd: str | None = None) -> str:
    """Locate and configure Tesseract, raising a clear error when missing."""
    global _TESSERACT_PATH

    if _TESSERACT_PATH:
        return _TESSERACT_PATH

    try:
        import pytesseract
    except ImportError as error:  # pragma: no cover - install issue
        raise RuntimeError(
            "OCR requires pytesseract and Pillow. Install them with "
            "`pip install -r requirements.txt`."
        ) from error

    binary = _find_tesseract(tesseract_cmd)
    if not binary:
        raise RuntimeError(
            "Tesseract OCR binary not found. Install it (for example "
            "`winget install --id UB-Mannheim.TesseractOCR`) or set "
            "TESSERACT_CMD to the full path of tesseract.exe."
        )

    pytesseract.pytesseract.tesseract_cmd = binary
    _TESSERACT_PATH = binary
    logger.info("Using Tesseract at %s", binary)
    return binary


def _ocr_page(
    page,
    dpi: int,
    language: str,
    *,
    tesseract_cmd: str | None = None,
) -> str:
    """Render a page and OCR it. Returns "" when OCR fails for this page."""
    global _OCR_UNAVAILABLE_WARNED

    _ensure_tesseract(tesseract_cmd)

    try:
        import pytesseract
        from PIL import Image
    except ImportError:  # pragma: no cover - install issue
        if not _OCR_UNAVAILABLE_WARNED:
            logger.warning(
                "OCR fallback disabled: install pytesseract + Pillow and the "
                "Tesseract binary to read scanned pages."
            )
            _OCR_UNAVAILABLE_WARNED = True
        return ""

    try:
        scale = dpi / 72
        pixmap = page.get_pixmap(
            matrix=fitz.Matrix(scale, scale),
            alpha=False,
        )
        image = Image.open(io.BytesIO(pixmap.tobytes("png")))
        return pytesseract.image_to_string(image, lang=language)
    except Exception as error:  # pragma: no cover - depends on host install
        if not _OCR_UNAVAILABLE_WARNED:
            logger.warning("OCR fallback failed: %s", error)
            _OCR_UNAVAILABLE_WARNED = True
        return ""


def extract_pages(
    pdf_path: Path,
    *,
    ocr_enabled: bool = True,
    ocr_min_chars: int = 24,
    ocr_dpi: int = 200,
    ocr_language: str = "eng",
    tesseract_cmd: str | None = None,
    show_progress: bool = False,
    initial_pages: list[dict] | None = None,
    checkpoint: Callable[[list[dict]], None] | None = None,
    checkpoint_every: int = CHECKPOINT_EVERY,
) -> tuple[list[dict], list[str]]:
    """Extract every page, keeping 1-based page numbers.

    Pages with little or no text are sent through OCR when available.
    ``initial_pages`` resumes an interrupted extraction; ``checkpoint`` is
    called periodically with the raw pages extracted so far.
    """
    pages: list[dict] = list(initial_pages or [])
    warnings: list[str] = []
    start_page = len(pages)

    if ocr_enabled:
        _ensure_tesseract(tesseract_cmd)

    with fitz.open(pdf_path) as document:
        metadata = document.metadata or {}
        title = (metadata.get("title") or "").strip() or pdf_path.stem
        author = (metadata.get("author") or "").strip() or None
        document_id = file_sha256(pdf_path)
        page_count = document.page_count

        progress = (
            tqdm(
                total=page_count,
                initial=start_page,
                desc=f"  {pdf_path.name[:38]}",
                unit="page",
                leave=False,
                dynamic_ncols=True,
            )
            if show_progress
            else None
        )

        try:
            for index, page in enumerate(document):
                if index < start_page:
                    continue

                text = page.get_text("text") or ""
                used_ocr = False
                page_error = None

                if ocr_enabled and len(text.strip()) < ocr_min_chars:
                    ocr_text = _ocr_page(
                        page,
                        ocr_dpi,
                        ocr_language,
                        tesseract_cmd=tesseract_cmd,
                    )
                    if ocr_text.strip():
                        text = ocr_text
                        used_ocr = True

                pages.append(
                    {
                        "source": pdf_path.name,
                        "page": index + 1,
                        "text": text,
                        "document_id": document_id,
                        "title": title,
                        "author": author,
                        "page_count": page_count,
                        "ocr": used_ocr,
                    }
                )

                if page_error:
                    pages[-1]["error"] = page_error

                if progress is not None:
                    progress.update(1)

                if (
                    checkpoint is not None
                    and checkpoint_every > 0
                    and len(pages) % checkpoint_every == 0
                ):
                    checkpoint(pages)
        finally:
            if progress is not None:
                progress.close()

        if not any(page["text"].strip() for page in pages):
            warnings.append(
                f"{pdf_path.name}: no extractable text; scanned/image-only PDF "
                "needs OCR (install Tesseract or provide a text layer)."
            )

        repeated = detect_repeated_lines(pages)
        for page in pages:
            page["text"] = remove_repeated_lines(page["text"], repeated)
            page["section"] = detect_section(page["text"])

            is_empty = len(page["text"].strip()) < ocr_min_chars
            if is_empty and not page.get("ocr"):
                page["empty"] = True

    return pages, warnings


def collect_pdfs(input_path: Path) -> list[Path]:
    """Accept a single PDF or a folder of PDFs."""
    if input_path.is_file():
        if input_path.suffix.lower() != ".pdf":
            raise ValueError(f"Not a PDF file: {input_path}")
        return [input_path]

    if input_path.is_dir():
        return sorted(
            path
            for path in input_path.iterdir()
            if path.is_file() and path.suffix.lower() == ".pdf"
        )

    raise FileNotFoundError(f"No such file or folder: {input_path}")


def _parse_patterns(value: str | None) -> list[str]:
    return [
        item.strip().lower()
        for item in (value or "").split(",")
        if item.strip()
    ]


def _matches_patterns(pdf_path: Path, patterns: list[str]) -> bool:
    if not patterns:
        return True
    name = pdf_path.name.lower()
    return any(pattern in name for pattern in patterns)


def _cache_options(
    *,
    ocr_enabled: bool,
    ocr_min_chars: int,
    ocr_dpi: int,
    ocr_language: str,
) -> dict:
    return {
        "version": CACHE_VERSION,
        "ocr_enabled": ocr_enabled,
        "ocr_min_chars": ocr_min_chars,
        "ocr_dpi": ocr_dpi,
        "ocr_language": ocr_language,
    }


def _load_cached(
    cache_path: Path, options: dict
) -> dict | None:
    if not cache_path.exists():
        return None

    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Ignoring unreadable extraction cache %s", cache_path)
        return None

    if payload.get("version") != CACHE_VERSION:
        return None
    if payload.get("options") != options:
        return None
    if not isinstance(payload.get("pages"), list):
        return None
    return payload


def _write_cached(
    cache_path: Path,
    options: dict,
    pages: list[dict],
    warnings: list[str],
    *,
    complete: bool,
) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": CACHE_VERSION,
        "options": options,
        "complete": complete,
        "pages": pages,
        "warnings": warnings,
    }
    temporary = cache_path.with_suffix(cache_path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )
    temporary.replace(cache_path)


def main() -> None:
    settings = get_settings()

    parser = argparse.ArgumentParser(
        description="Extract text and page numbers from PDFs into JSON."
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=str(settings.pdf_dir),
        help=f"A PDF file or a folder of PDFs (default: {settings.pdf_dir})",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=str(settings.extracted_file),
        help=f"Path to the output JSON (default: {settings.extracted_file})",
    )
    parser.add_argument(
        "--report",
        default=str(settings.quality_report_file),
        help="Path to the document quality report JSON",
    )
    parser.add_argument(
        "--cache-dir",
        default=str(settings.extraction_cache_dir),
        help=(
            "Per-document extraction cache directory "
            f"(default: {settings.extraction_cache_dir})"
        ),
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Do not read or write the per-document extraction cache",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Re-extract every PDF and overwrite its cache entry",
    )
    parser.add_argument(
        "--no-ocr",
        action="store_true",
        help="Disable OCR fallback for scanned pages",
    )
    parser.add_argument(
        "--ocr-only",
        default="",
        help=(
            "Comma-separated filename substrings to OCR (for example "
            "'Color Harmony,Textilepedia,Fabric Science'). Other PDFs are "
            "extracted without OCR."
        ),
    )
    parser.add_argument(
        "--ocr-min-chars",
        type=int,
        default=settings.ocr_min_chars,
        help="Pages with fewer characters are OCR'd",
    )
    parser.add_argument(
        "--dpi", type=int, default=settings.ocr_dpi, help="OCR render DPI"
    )
    args = parser.parse_args()

    pdf_paths = collect_pdfs(Path(args.path))
    if not pdf_paths:
        raise SystemExit("No PDF files found.")

    patterns = _parse_patterns(args.ocr_only)
    base_ocr = not args.no_ocr and settings.ocr_enabled
    ocr_targets = [
        path
        for path in pdf_paths
        if base_ocr and _matches_patterns(path, patterns)
    ]

    if patterns and not ocr_targets:
        raise SystemExit(
            "No PDF filenames matched --ocr-only: "
            + ", ".join(patterns)
        )

    if ocr_targets:
        try:
            _ensure_tesseract(settings.tesseract_cmd)
        except RuntimeError as error:
            raise SystemExit(str(error)) from error
        print(
            f"OCR enabled for {len(ocr_targets)}/"
            f"{len(pdf_paths)} PDF(s):"
        )
        for path in ocr_targets:
            print(f"  - {path.name}")
    elif base_ocr:
        print(
            f"OCR enabled for all {len(pdf_paths)} PDF(s). Use --ocr-only "
            "to limit OCR to scanned books."
        )
    else:
        print(f"OCR disabled for all {len(pdf_paths)} PDF(s).")

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    cache_dir = Path(args.cache_dir)

    pages: list[dict] = []
    warnings: list[str] = []
    seen_hashes: dict[str, str] = {}
    skipped_duplicates: list[dict] = []
    failed_documents: list[dict] = []
    cache_hits = 0

    progress = tqdm(
        pdf_paths,
        desc="PDFs",
        unit="pdf",
        dynamic_ncols=True,
    )

    for pdf_path in progress:
        try:
            digest = file_sha256(pdf_path)
            if digest in seen_hashes:
                skipped_duplicates.append(
                    {
                        "source": pdf_path.name,
                        "duplicate_of": seen_hashes[digest],
                    }
                )
                logger.warning(
                    "Skipping byte-identical duplicate %s (already read as %s)",
                    pdf_path.name,
                    seen_hashes[digest],
                )
                continue
            seen_hashes[digest] = pdf_path.name

            use_ocr = base_ocr and _matches_patterns(pdf_path, patterns)
            options = _cache_options(
                ocr_enabled=use_ocr,
                ocr_min_chars=args.ocr_min_chars,
                ocr_dpi=args.dpi,
                ocr_language=settings.ocr_language,
            )
            cache_path = cache_dir / f"{digest}.json"

            cached = None
            if not args.no_cache and not args.refresh:
                cached = _load_cached(cache_path, options)

            initial_pages: list[dict] = []
            if cached is not None:
                cached_pages = cached.get("pages") or []
                if cached.get("complete"):
                    pages.extend(cached_pages)
                    warnings.extend(cached.get("warnings") or [])
                    cache_hits += 1
                    progress.set_postfix_str(
                        f"cache={cache_hits}", refresh=True
                    )
                    continue

                initial_pages = cached_pages
                print(
                    f"Resuming {pdf_path.name} at page "
                    f"{len(initial_pages) + 1} from cache."
                )

            def checkpoint(
                current_pages: list[dict],
                cache_path: Path = cache_path,
                options: dict = options,
            ) -> None:
                _write_cached(
                    cache_path,
                    options,
                    current_pages,
                    [],
                    complete=False,
                )

            document_pages, document_warnings = extract_pages(
                pdf_path,
                ocr_enabled=use_ocr,
                ocr_min_chars=args.ocr_min_chars,
                ocr_dpi=args.dpi,
                ocr_language=settings.ocr_language,
                tesseract_cmd=settings.tesseract_cmd,
                show_progress=use_ocr,
                initial_pages=initial_pages,
                checkpoint=None if args.no_cache else checkpoint,
            )
            pages.extend(document_pages)
            warnings.extend(document_warnings)

            if not args.no_cache:
                _write_cached(
                    cache_path,
                    options,
                    document_pages,
                    document_warnings,
                    complete=True,
                )
        except Exception as error:  # pragma: no cover - host dependent
            logger.exception("Failed to extract %s", pdf_path)
            failed_documents.append(
                {"source": pdf_path.name, "error": str(error)}
            )

    progress.close()

    report = build_quality_report(pages)
    report["warnings"] = warnings
    report["skipped_duplicates"] = skipped_duplicates
    report["failed_documents"] = failed_documents
    report["cache_hits"] = cache_hits

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(pages, file, ensure_ascii=False, indent=2)

    with report_path.open("w", encoding="utf-8") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)

    totals = report["totals"]
    print(f"PDFs processed: {len(pdf_paths) - len(skipped_duplicates)}")
    print(f"Cache hits: {cache_hits}")
    print(f"Pages extracted: {totals['pages']}")
    print(f"Characters extracted: {totals['characters']}")
    print(f"OCR pages: {totals['ocr_pages']}")
    print(f"Empty pages: {totals['empty_pages']}")
    print(f"Extraction errors: {totals['errors']}")
    print(f"Saved pages to: {output_path}")
    print(f"Saved quality report to: {report_path}")

    if skipped_duplicates:
        print("Skipped byte-identical duplicates:")
        for item in skipped_duplicates:
            print(f"  - {item['source']} == {item['duplicate_of']}")

    content_duplicates = report.get("duplicate_documents") or []
    if content_duplicates:
        print("WARNING - documents with identical extracted text:")
        for item in content_duplicates:
            print(f"  - {', '.join(item['sources'])}")

    if warnings:
        print("WARNING - extraction notes:")
        for warning in warnings:
            print(f"  - {warning}")

    if failed_documents:
        print("ERROR - documents that failed to extract:")
        for item in failed_documents:
            print(f"  - {item['source']}: {item['error']}")


if __name__ == "__main__":
    main()
