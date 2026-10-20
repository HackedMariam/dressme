"""Retrieval and grounding metrics used by the golden-set evaluation."""

from __future__ import annotations

import re
from statistics import mean


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip().lower()


def _source_text(row: dict) -> str:
    return _normalize(
        " ".join(
            str(row.get(field) or "")
            for field in ("source", "title", "document_id")
        )
    )


def is_relevant(row: dict, expected_sources: list[str]) -> bool:
    text = _source_text(row)
    return any(term.lower() in text for term in expected_sources)


def hit_at_k(rows: list[dict], expected_sources: list[str]) -> float:
    return 1.0 if any(
        is_relevant(row, expected_sources) for row in rows
    ) else 0.0


def reciprocal_rank_at_k(
    rows: list[dict], expected_sources: list[str]
) -> float:
    for rank, row in enumerate(rows, start=1):
        if is_relevant(row, expected_sources):
            return 1.0 / rank
    return 0.0


def context_precision(
    rows: list[dict], expected_sources: list[str]
) -> float:
    if not rows:
        return 0.0
    relevant = sum(
        1 for row in rows if is_relevant(row, expected_sources)
    )
    return relevant / len(rows)


def citation_accuracy(
    answer: str,
    citations: list[dict],
    rows: list[dict],
) -> float:
    """Fraction of cited markers that are valid and map to retrieved rows."""
    markers = re.findall(r"\[S(\d+)\]", answer or "")
    if not markers:
        return 0.0

    valid_markers = {item.get("marker") for item in citations}
    retrieved_sources = {_source_text(row) for row in rows}

    correct = 0
    for marker in set(markers):
        citation = next(
            (
                item
                for item in citations
                if item.get("marker") == f"[S{marker}]"
            ),
            None,
        )
        if not citation or citation.get("marker") not in valid_markers:
            continue
        source_text = _source_text(citation)
        if any(
            source_text
            and (
                source_text in source
                or source in source_text
            )
            for source in retrieved_sources
        ):
            correct += 1

    return correct / len(set(markers))


def groundedness(answer: str, citations: list[dict]) -> float:
    """Cheap proxy: does the answer cite at least one retrieved source?"""
    if not (answer or "").strip():
        return 0.0
    return 1.0 if citations else 0.0


def summarize(rows: list[dict]) -> dict:
    if not rows:
        return {}

    numeric_fields = [
        "hit_at_k",
        "mrr_at_k",
        "context_precision",
        "citation_accuracy",
        "groundedness",
        "faithfulness",
        "answer_relevance",
    ]
    summary = {"questions": len(rows)}
    for field in numeric_fields:
        values = [
            row[field]
            for row in rows
            if isinstance(row.get(field), (int, float))
        ]
        if values:
            summary[field] = round(mean(values), 4)
    return summary
