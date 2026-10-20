from __future__ import annotations

from ingestion.quality import (
    build_quality_report,
    detect_duplicate_documents,
    detect_repeated_lines,
    remove_repeated_lines,
)


def test_repeated_headers_are_detected_and_removed():
    pages = [
        {
            "source": "book.pdf",
            "page": index,
            "text": f"FASHION BASICS\nBody text {index}\nPage footer",
        }
        for index in range(1, 7)
    ]

    repeated = detect_repeated_lines(pages)
    assert "fashion basics" in repeated
    assert "page footer" in repeated

    cleaned = remove_repeated_lines(pages[0]["text"], repeated)
    assert "Body text 1" in cleaned
    assert "FASHION BASICS" not in cleaned


def test_duplicate_documents_are_grouped_by_text():
    pages = [
        {"source": "a.pdf", "page": 1, "text": "same content " * 40},
        {"source": "b.pdf", "page": 1, "text": "same content " * 40},
        {"source": "c.pdf", "page": 1, "text": "different content " * 40},
    ]

    duplicates = detect_duplicate_documents(pages)
    assert len(duplicates) == 1
    assert duplicates[0]["sources"] == ["a.pdf", "b.pdf"]


def test_quality_report_counts_empty_pages():
    pages = [
        {
            "source": "a.pdf",
            "page": 1,
            "text": "real text " * 40,
            "document_id": "a",
        },
        {
            "source": "a.pdf",
            "page": 2,
            "text": "",
            "document_id": "a",
        },
    ]

    report = build_quality_report(pages)
    assert report["totals"]["pages"] == 2
    assert report["totals"]["empty_pages"] == 1
