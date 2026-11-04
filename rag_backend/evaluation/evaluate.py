"""Evaluate retrieval and groundedness on a golden fashion Q&A set.

Usage (from ``rag_backend``):
    python -m evaluation.evaluate --top-k 5 --judge

Retrieval metrics run without an LLM. ``--judge`` adds LLM-as-judge scores
for faithfulness and answer relevance. ``--ragas`` is optional and requires
``pip install -r requirements-eval.txt``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from config import get_settings
from evaluation.metrics import (
    citation_accuracy,
    context_precision,
    groundedness,
    hit_at_k,
    reciprocal_rank_at_k,
    summarize,
)
from rag.llm_client import LLMUnavailable, chat_completion
from rag.rag_service import answer_question
from rag.retriever import retrieve

GOLDEN_PATH = Path(__file__).with_name("golden_qa.jsonl")

JUDGE_PROMPT = """You are evaluating a fashion RAG answer.

Return strict JSON with three numbers between 0 and 1:
- faithfulness: are the factual claims supported by the retrieved context?
- answer_relevance: does the answer actually address the question?
- citation_accuracy: do the citations support the claims they are attached to?

Do not add any prose or markdown fences."""


def load_golden(path: Path = GOLDEN_PATH) -> list[dict]:
    with path.open("r", encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def _parse_scores(text: str) -> dict:
    match = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not match:
        return {}
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}
    return {
        key: float(data[key])
        for key in (
            "faithfulness",
            "answer_relevance",
            "citation_accuracy",
        )
        if key in data
    }


def judge_answer(
    question: str,
    answer: str,
    rows: list[dict],
) -> dict:
    context = "\n\n".join(
        f"[S{index}] {row.get('source')}, page {row.get('page')}\n"
        f"{(row.get('content') or '')[:1200]}"
        for index, row in enumerate(rows, start=1)
    )
    try:
        response = chat_completion(
            model=get_settings().llm_model,
            messages=[
                {"role": "system", "content": JUDGE_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Question:\n{question}\n\n"
                        f"Answer:\n{answer}\n\n"
                        f"Retrieved context:\n{context}"
                    ),
                },
            ],
            temperature=0.0,
            max_tokens=160,
        )
        return _parse_scores(response.choices[0].message.content or "")
    except LLMUnavailable as error:
        print(f"  judge unavailable: {error}", file=sys.stderr)
        return {}


def try_ragas(samples: list[dict]) -> dict:
    try:
        from datasets import Dataset  # type: ignore
        from ragas import evaluate  # type: ignore
        from ragas.metrics import (  # type: ignore
            answer_relevancy,
            context_precision,
            faithfulness,
        )
    except ImportError:
        return {
            "error": (
                "RAGAS is not installed. Run: pip install -r "
                "requirements-eval.txt"
            )
        }

    dataset = Dataset.from_list(samples)
    result = evaluate(
        dataset,
        metrics=[faithfulness, answer_relevancy, context_precision],
    )
    return dict(result)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--min-similarity", type=float, default=None)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--judge",
        action="store_true",
        help="Use an LLM judge for faithfulness/relevance",
    )
    parser.add_argument(
        "--ragas",
        action="store_true",
        help="Also run optional RAGAS metrics",
    )
    parser.add_argument(
        "--output",
        default=str(
            get_settings().data_dir / "evaluation_results.json"
        ),
    )
    args = parser.parse_args()

    golden = load_golden()
    if args.limit:
        golden = golden[: args.limit]

    results = []
    samples = []

    for item in golden:
        rows = retrieve(
            item["question"],
            top_k=args.top_k,
            min_similarity=args.min_similarity,
        )
        result = {
            "id": item["id"],
            "question": item["question"],
            "hit_at_k": hit_at_k(rows, item["expected_sources"]),
            "mrr_at_k": reciprocal_rank_at_k(
                rows, item["expected_sources"]
            ),
            "context_precision": context_precision(
                rows, item["expected_sources"]
            ),
            "retrieved_sources": [
                {
                    "chunk_id": row.get("chunk_id"),
                    "source": row.get("source"),
                    "page": row.get("page"),
                    "similarity": row.get("similarity"),
                    "retrieval": row.get("retrieval"),
                }
                for row in rows
            ],
        }

        answer = ""
        citations: list[dict] = []
        if args.judge:
            generated = answer_question(
                item["question"],
                top_k=args.top_k,
                min_similarity=args.min_similarity,
            )
            answer = generated["answer"]
            citations = generated.get("citations") or []
            result["answer"] = answer
            result["citation_accuracy"] = citation_accuracy(
                answer, citations, rows
            )
            result["groundedness"] = groundedness(answer, citations)
            result.update(judge_answer(item["question"], answer, rows))

            samples.append(
                {
                    "user_input": item["question"],
                    "retrieved_contexts": [
                        row.get("content") or "" for row in rows
                    ],
                    "response": answer,
                    "reference": item.get("reference_answer", ""),
                }
            )

        results.append(result)
        print(
            f"{item['id']}: hit@k={result['hit_at_k']:.2f} "
            f"mrr={result['mrr_at_k']:.2f} "
            f"precision={result['context_precision']:.2f}"
        )

    summary = summarize(results)
    if args.ragas and samples:
        summary["ragas"] = try_ragas(samples)

    output = {
        "config": {
            "top_k": args.top_k,
            "min_similarity": args.min_similarity,
            "embedding_version": get_settings().embedding_version,
        },
        "summary": summary,
        "results": results,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(output, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("\nSummary:")
    for key, value in summary.items():
        print(f"  {key}: {value}")
    print(f"\nSaved to: {output_path}")


if __name__ == "__main__":
    main()
