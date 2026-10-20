from __future__ import annotations

from ingestion.chunker import chunk_pages, clean_text, split_text
from ingestion.quality import classify_topics, slugify, text_sha256


def test_clean_text_normalizes_whitespace():
    assert clean_text("a\t b\n\n\n\nc") == "a b\n\nc"


def test_split_text_overlaps_and_respects_boundaries():
    text = " ".join(f"word{i}" for i in range(400))
    chunks = split_text(text, chunk_size=200, chunk_overlap=40)

    assert len(chunks) > 1
    assert all(len(chunk) <= 220 for chunk in chunks)
    assert "word0" in chunks[0]


def test_split_text_rejects_invalid_overlap():
    try:
        split_text("hello", chunk_size=100, chunk_overlap=100)
    except ValueError as error:
        assert "greater" in str(error)
    else:
        raise AssertionError("expected ValueError")


def test_chunk_pages_enriches_metadata():
    pages = [
        {
            "source": "Color Harmony Workbook.pdf",
            "page": 3,
            "text": (
                "This chapter explains colour theory, complementary colours, "
                "neutrals and how to build a palette for an outfit. " * 10
            ),
            "document_id": "doc-1",
            "title": "Color Harmony",
            "author": "Test",
            "page_count": 10,
            "section": "Chapter 1",
        }
    ]

    chunks = chunk_pages(
        pages,
        chunk_size=300,
        chunk_overlap=50,
        embedding_model="test-model",
        embedding_version="test-model-v1",
    )

    assert chunks
    first = chunks[0]
    assert first["chunk_id"].startswith("color-harmony-workbook-pdf-p3-c0")
    assert first["document_id"] == "doc-1"
    assert first["category"] == "color"
    assert "color" in first["topics"]
    assert first["content_hash"] == text_sha256(first["text"])
    assert first["embedding_version"] == "test-model-v1"


def test_slugify_is_filesystem_safe():
    assert slugify("Color Harmony Workbook.pdf") == "color-harmony-workbook-pdf"
    assert slugify("!!!") == "unknown"


def test_classify_topics_finds_fashion_topics():
    category, topics = classify_topics(
        "Capsule wardrobe with wool fabrics, neutral colours and travel packing"
    )
    assert category in topics
    assert {"wardrobe", "fabrics", "color", "travel"} & set(topics)
