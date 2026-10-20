"""Extract page text from PDFs, with OCR fallback and quality checks."""

from __future__ import annotations

import argparse
import io
import json
import logging
from pathlib import Path

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

_OCR_UNAVAILABLE_WARNED = False


def _ocr_page(page, dpi: int, language: str) -> str:
    """Render a page and OCR it. Returns "" when OCR is unavailable."""
    global _OCR_UNAVAILABLE_WARNED

    try:
        import pytesseract
        from PIL import Image
    except ImportError:
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
) -> tuple[list[dict], list[str]]:
    """Extract every page, keeping 1-based page numbers.

    Pages with little or no text are sent through OCR when available.
    """
    pages: list[dict] = []
    warnings: list[str] = []

    with fitz.open(pdf_path) as document:
        metadata = document.metadata or {}
        title = (metadata.get("title") or "").strip() or pdf_path.stem
        author = (metadata.get("author") or "").strip() or None
        document_id = file_sha256(pdf_path)
        page_count = document.page_count

        for index, page in enumerate(document):
            text = page.get_text("text") or ""
            used_ocr = False
            page_error = None

            if ocr_enabled and len(text.strip()) < ocr_min_chars:
                ocr_text = _ocr_page(page, ocr_dpi, ocr_language)
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
        "--no-ocr",
        action="store_true",
        help="Disable OCR fallback for scanned pages",
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

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    pages: list[dict] = []
    warnings: list[str] = []
    seen_hashes: dict[str, str] = {}
    skipped_duplicates: list[dict] = []
    failed_documents: list[dict] = []

    for pdf_path in pdf_paths:
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

            document_pages, document_warnings = extract_pages(
                pdf_path,
                ocr_enabled=not args.no_ocr and settings.ocr_enabled,
                ocr_min_chars=args.ocr_min_chars,
                ocr_dpi=args.dpi,
                ocr_language=settings.ocr_language,
            )
            pages.extend(document_pages)
            warnings.extend(document_warnings)
        except Exception as error:  # pragma: no cover - host dependent
            logger.exception("Failed to extract %s", pdf_path)
            failed_documents.append(
                {"source": pdf_path.name, "error": str(error)}
            )

    report = build_quality_report(pages)
    report["warnings"] = warnings
    report["skipped_duplicates"] = skipped_duplicates
    report["failed_documents"] = failed_documents

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(pages, file, ensure_ascii=False, indent=2)

    with report_path.open("w", encoding="utf-8") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)

    totals = report["totals"]
    print(f"PDFs processed: {len(pdf_paths) - len(skipped_duplicates)}")
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
