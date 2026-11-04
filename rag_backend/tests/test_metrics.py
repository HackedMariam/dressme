from __future__ import annotations

from evaluation.metrics import (
    citation_accuracy,
    context_precision,
    hit_at_k,
    reciprocal_rank_at_k,
    summarize,
)

ROWS = [
    {"source": "Color Harmony Workbook.pdf", "title": "Color Harmony"},
    {"source": "Work clothes.pdf", "title": "Work clothes"},
]


def test_hit_and_mrr():
    expected = ["color harmony"]
    assert hit_at_k(ROWS, expected) == 1.0
    assert reciprocal_rank_at_k(ROWS, expected) == 1.0
    assert reciprocal_rank_at_k(ROWS[::-1], expected) == 0.5


def test_context_precision():
    assert context_precision(ROWS, ["work clothes"]) == 0.5
    assert context_precision([], ["work clothes"]) == 0.0


def test_citation_accuracy():
    answer = "Wear neutrals [S1]. Avoid logos [S2]."
    citations = [
        {
            "marker": "[S1]",
            "source": "Color Harmony Workbook.pdf",
        },
        {
            "marker": "[S2]",
            "source": "Work clothes.pdf",
        },
    ]
    assert citation_accuracy(answer, citations, ROWS) == 1.0


def test_summarize_averages_present_fields():
    summary = summarize(
        [
            {"hit_at_k": 1.0, "mrr_at_k": 1.0},
            {"hit_at_k": 0.0, "mrr_at_k": 0.5},
        ]
    )
    assert summary["questions"] == 2
    assert summary["hit_at_k"] == 0.5
    assert summary["mrr_at_k"] == 0.75
