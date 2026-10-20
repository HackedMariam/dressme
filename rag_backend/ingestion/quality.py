"""Document quality checks and fashion metadata helpers.

These helpers are deliberately deterministic (no model calls) so the
ingestion pipeline can run cheaply and reproducibly.
"""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

WHITESPACE_RE = re.compile(r"\s+")
PAGE_NUMBER_RE = re.compile(
    r"^(?:page\s*)?[\divxlcdm]+(?:\s*(?:/|of)\s*[\divxlcdm]+)?$",
    re.IGNORECASE,
)

TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "color": (
        "color",
        "colour",
        "palette",
        "hue",
        "tint",
        "shade",
        "contrast",
        "neutral",
        "undertone",
        "chromatic",
    ),
    "styling": (
        "style",
        "styling",
        "outfit",
        "silhouette",
        "proportion",
        "layering",
        "accessor",
        "look",
        "aesthetic",
    ),
    "body": (
        "body shape",
        "body type",
        "proportion",
        "petite",
        "tall",
        "curvy",
        "plus size",
        "fit",
        "measurement",
    ),
    "seasons": (
        "spring",
        "summer",
        "autumn",
        "fall",
        "winter",
        "season",
        "weather",
        "temperature",
    ),
    "fabrics": (
        "fabric",
        "textile",
        "wool",
        "cotton",
        "silk",
        "linen",
        "leather",
        "denim",
        "cashmere",
        "polyester",
        "viscose",
        "suede",
        "knit",
    ),
    "occasions": (
        "formal",
        "business",
        "casual",
        "wedding",
        "interview",
        "dinner",
        "occasion",
        "evening",
        "cocktail",
        "work",
        "office",
    ),
    "wardrobe": (
        "capsule",
        "wardrobe",
        "closet",
        "essential",
        "minimal",
        "versatile",
        "cost per wear",
        "cost-per-wear",
    ),
    "footwear": (
        "shoe",
        "shoes",
        "boot",
        "boots",
        "sneaker",
        "heel",
        "footwear",
        "sandal",
        "loafer",
    ),
    "menswear": (
        "men's",
        "mens",
        "menswear",
        "suit",
        "shirt",
        "tie",
        "tuxedo",
        "blazer",
    ),
    "travel": (
        "pack",
        "packing",
        "travel",
        "trip",
        "luggage",
        "carry-on",
        "carry on",
        "destination",
    ),
    "sustainability": (
        "sustainab",
        "circular",
        "ethical",
        "recycl",
        "environment",
        "upcycl",
    ),
    "construction": (
        "pattern",
        "sewing",
        "sew",
        "stitch",
        "garment construction",
        "dart",
        "seam",
        "tailor",
    ),
    "care": (
        "care",
        "washing",
        "laundry",
        "clean",
        "maintenance",
        "repair",
        "iron",
    ),
}

TOPIC_PATTERNS = {
    topic: re.compile(
        r"\b(?:" + "|".join(re.escape(word) for word in words) + r")\w*",
        re.IGNORECASE,
    )
    for topic, words in TOPIC_KEYWORDS.items()
}


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = text.replace("\x00", " ")
    return WHITESPACE_RE.sub(" ", text).strip().lower()


def text_sha256(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def file_sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    return slug or "unknown"


def classify_topics(text: str, *, max_topics: int = 5) -> tuple[str, list[str]]:
    """Return a primary category and up to ``max_topics`` topic tags."""
    scores: Counter[str] = Counter()

    for topic, pattern in TOPIC_PATTERNS.items():
        matches = pattern.findall(text or "")
        if matches:
            scores[topic] = len(matches)

    if not scores:
        return "general", []

    ordered = [topic for topic, _ in scores.most_common(max_topics)]
    return ordered[0], ordered


def detect_section(text: str) -> str | None:
    """Best-effort section heading from the first lines of a page."""
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]

    for line in lines[:8]:
        if len(line) > 120:
            continue
        if re.match(
            r"^(chapter|part|section|unit|lesson)\s+[\divxlcdm]+",
            line,
            re.IGNORECASE,
        ):
            return line
        if line.isupper() and 4 <= len(line) <= 80:
            return line.title()

    return None


def _candidate_lines(text: str) -> list[str]:
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    candidates: list[str] = []

    for line in lines[:3] + lines[-3:]:
        normalized = normalize_text(line)
        if not normalized or len(normalized) > 120:
            continue
        if PAGE_NUMBER_RE.match(normalized):
            continue
        candidates.append(normalized)

    return candidates


def detect_repeated_lines(
    pages: list[dict],
    *,
    min_ratio: float = 0.3,
    min_pages: int = 3,
) -> set[str]:
    """Find running headers/footers repeated across a document."""
    counts: Counter[str] = Counter()
    non_empty_pages = 0

    for page in pages:
        text = page.get("text") or ""
        if not text.strip():
            continue
        non_empty_pages += 1
        counts.update(set(_candidate_lines(text)))

    threshold = max(min_pages, math.ceil(non_empty_pages * min_ratio))
    return {line for line, count in counts.items() if count >= threshold}


def remove_repeated_lines(text: str, repeated: set[str]) -> str:
    if not repeated:
        return text

    kept = []
    for line in (text or "").splitlines():
        if normalize_text(line) in repeated:
            continue
        kept.append(line)

    return "\n".join(kept).strip()


def page_has_meaningful_text(text: str, min_chars: int = 24) -> bool:
    return len(normalize_text(text)) >= min_chars


def detect_duplicate_documents(pages: list[dict]) -> list[dict]:
    """Group documents whose normalized full text is identical.

    This catches re-downloads that are byte-different but content-identical.
    """
    by_source: dict[str, list[str]] = defaultdict(list)

    for page in pages:
        source = page.get("source") or "unknown"
        by_source[source].append(page.get("text") or "")

    by_hash: dict[str, list[str]] = defaultdict(list)
    for source, texts in by_source.items():
        combined = "\n".join(texts)
        if len(normalize_text(combined)) < 200:
            continue
        by_hash[text_sha256(combined)].append(source)

    return [
        {"text_sha256": digest, "sources": sorted(sources)}
        for digest, sources in by_hash.items()
        if len(sources) > 1
    ]


def build_quality_report(pages: list[dict]) -> dict:
    by_source: dict[str, list[dict]] = defaultdict(list)
    for page in pages:
        by_source[page.get("source") or "unknown"].append(page)

    documents = []
    for source, document_pages in sorted(by_source.items()):
        chars = sum(len(page.get("text") or "") for page in document_pages)
        empty_pages = [
            page.get("page")
            for page in document_pages
            if not page_has_meaningful_text(page.get("text") or "")
        ]
        ocr_pages = [
            page.get("page")
            for page in document_pages
            if page.get("ocr")
        ]
        errors = [
            {"page": page.get("page"), "error": page["error"]}
            for page in document_pages
            if page.get("error")
        ]

        documents.append(
            {
                "source": source,
                "document_id": document_pages[0].get("document_id"),
                "title": document_pages[0].get("title"),
                "author": document_pages[0].get("author"),
                "pages": len(document_pages),
                "characters": chars,
                "empty_pages": empty_pages,
                "ocr_pages": ocr_pages,
                "errors": errors,
            }
        )

    return {
        "documents": documents,
        "duplicate_documents": detect_duplicate_documents(pages),
        "totals": {
            "documents": len(documents),
            "pages": len(pages),
            "characters": sum(item["characters"] for item in documents),
            "empty_pages": sum(len(item["empty_pages"]) for item in documents),
            "ocr_pages": sum(len(item["ocr_pages"]) for item in documents),
            "errors": sum(len(item["errors"]) for item in documents),
        },
    }
