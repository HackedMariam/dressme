import argparse
import json
from pathlib import Path

try:
    import pymupdf as fitz  # PyMuPDF >= 1.24
except ImportError:
    import fitz  # PyMuPDF < 1.24

INPUT_PATH = Path("ingestion/pdfs")
OUTPUT_FILE = Path("data/extracted_pages.json")


def extract_pages(pdf_path: Path) -> list[dict]:
    """Extract the text of every page, keeping 1-based page numbers."""
    pages = []

    with fitz.open(pdf_path) as document:
        for index, page in enumerate(document):
            pages.append(
                {
                    "source": pdf_path.name,
                    "page": index + 1,
                    "text": page.get_text("text"),
                }
            )

    return pages


def collect_pdfs(input_path: Path) -> list[Path]:
    """Accept a single PDF or a folder of PDFs."""
    if input_path.is_file():
        return [input_path]

    if input_path.is_dir():
        return sorted(
            path
            for path in input_path.iterdir()
            if path.is_file() and path.suffix.lower() == ".pdf"
        )

    raise FileNotFoundError(f"No such file or folder: {input_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Extract text and page numbers from PDFs into JSON."
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=str(INPUT_PATH),
        help=f"A PDF file or a folder of PDFs (default: {INPUT_PATH})",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=str(OUTPUT_FILE),
        help=f"Path to the output JSON (default: {OUTPUT_FILE})",
    )
    args = parser.parse_args()

    pdf_paths = collect_pdfs(Path(args.path))

    if not pdf_paths:
        raise SystemExit("No PDF files found.")

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    pages = []
    empty_documents = []

    for pdf_path in pdf_paths:
        document_pages = extract_pages(pdf_path)

        if not sum(len(page["text"].strip()) for page in document_pages):
            empty_documents.append(pdf_path.name)

        pages.extend(document_pages)

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(pages, file, ensure_ascii=False, indent=2)

    total_chars = sum(len(page["text"]) for page in pages)

    print(f"PDFs processed: {len(pdf_paths)}")
    print(f"Pages extracted: {len(pages)}")
    print(f"Characters extracted: {total_chars}")
    print(f"Saved to: {output_path}")

    if empty_documents:
        print("WARNING - no extractable text (scanned/image PDFs?):")
        for name in empty_documents:
            print(f"  - {name}")


if __name__ == "__main__":
    main()
