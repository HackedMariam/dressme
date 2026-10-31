"""Rank candidate BO3 wardrobe gaps with an XGBoost ranker, and train that ranker from labeled feedback.

Train from a CSV (see data/bo3_ranker_feedback_template.csv):
    python backend/xgboost_ranker.py --data backend/data/bo3_ranker_feedback.csv
"""

import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from xgboost import XGBRanker

FEATURES = (
    "coverage_deficit",
    "use_frequency",
    "season_relevance",
    "outfit_gain",
    "preference_match",
    "redundancy_score",
)
MODEL_PATH = Path(__file__).resolve().parent / "models" / "bo3_gap_ranker.json"
REQUIRED_COLUMNS = ("query_id", "candidate_id", *FEATURES, "relevance")


def make_ranker() -> XGBRanker:
    """The one set of hyperparameters, shared by CSV training and the feedback retraining (agent/learning.py)."""
    return XGBRanker(
        objective="rank:ndcg",
        eval_metric="ndcg@3",
        n_estimators=150,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        tree_method="hist",
        random_state=42,
        n_jobs=4,
    )


def _feature_matrix(candidates: Sequence[Mapping[str, Any]]) -> list[list[float]]:
    matrix = []
    for index, candidate in enumerate(candidates):
        missing = [name for name in FEATURES if name not in candidate]
        if missing:
            raise ValueError(f"Candidate {index} is missing features: {', '.join(missing)}")

        row = []
        for name in FEATURES:
            try:
                value = float(candidate[name])
            except (TypeError, ValueError) as error:
                raise ValueError(f"Candidate {index} has an invalid {name} value.") from error
            if not math.isfinite(value) or not 0.0 <= value <= 1.0:
                raise ValueError(f"Candidate {index} feature {name} must be between 0 and 1.")
            row.append(value)
        matrix.append(row)
    return matrix


def load_ranker(model_path: str | Path = MODEL_PATH) -> XGBRanker:
    """Load the model produced by train() (or by the feedback retraining)."""
    path = Path(model_path)
    if not path.is_file():
        raise FileNotFoundError(
            f"No trained BO3 ranker at {path}. Collect labeled feedback and "
            "run `python backend/xgboost_ranker.py --data <labeled csv>` first."
        )
    ranker = XGBRanker()
    ranker.load_model(str(path))
    return ranker


def rank_gap_candidates(
    candidates: Sequence[Mapping[str, Any]],
    model_path: str | Path = MODEL_PATH,
) -> list[dict[str, Any]]:
    """Order already-generated gap candidates; scores are ranking values, not probabilities."""
    if not candidates:
        return []

    feature_matrix = _feature_matrix(candidates)
    scores = load_ranker(model_path).predict(feature_matrix).tolist()
    ranked = sorted(enumerate(scores), key=lambda pair: pair[1], reverse=True)
    return [
        {
            **dict(candidates[index]),
            "rank": rank,
            "ranking_score": float(score),
        }
        for rank, (index, score) in enumerate(ranked, start=1)
    ]


# --- Training from a labeled CSV ------------------------------------------------------------

def read_feedback(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        missing = [name for name in REQUIRED_COLUMNS if name not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"Feedback CSV is missing columns: {', '.join(missing)}")
        rows = list(reader)

    if not rows:
        raise ValueError("Feedback CSV has no candidate rows.")
    return rows


def train(feedback_path: Path, model_path: Path) -> None:
    rows = read_feedback(feedback_path)
    grouped_rows: dict[str, list[dict[str, str]]] = defaultdict(list)

    for line_number, row in enumerate(rows, start=2):
        query_id = row["query_id"].strip()
        candidate_id = row["candidate_id"].strip()
        if not query_id or not candidate_id:
            raise ValueError(f"CSV line {line_number} needs query_id and candidate_id.")

        for feature in FEATURES:
            try:
                value = float(row[feature])
            except (TypeError, ValueError) as error:
                raise ValueError(f"CSV line {line_number} has invalid {feature}.") from error
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"CSV line {line_number}: {feature} must be between 0 and 1.")

        try:
            relevance = int(row["relevance"])
        except (TypeError, ValueError) as error:
            raise ValueError(f"CSV line {line_number} has invalid relevance.") from error
        if relevance not in (0, 1, 2, 3):
            raise ValueError(f"CSV line {line_number}: relevance must be 0, 1, 2, or 3.")
        grouped_rows[query_id].append(row)

    if len(grouped_rows) < 2:
        raise ValueError("Add feedback from at least two different user-context queries.")
    for query_id, query_rows in grouped_rows.items():
        if len(query_rows) < 2:
            raise ValueError(f"Query {query_id!r} needs at least two candidate gaps to rank.")
        labels = {int(row["relevance"]) for row in query_rows}
        if len(labels) < 2:
            raise ValueError(f"Query {query_id!r} needs candidates with different relevance labels.")

    features: list[list[float]] = []
    labels: list[int] = []
    query_ids: list[int] = []
    for numeric_query_id, query_id in enumerate(sorted(grouped_rows)):
        for row in grouped_rows[query_id]:
            features.append([float(row[name]) for name in FEATURES])
            labels.append(int(row["relevance"]))
            query_ids.append(numeric_query_id)

    ranker = make_ranker()
    ranker.fit(features, labels, qid=query_ids, verbose=False)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    ranker.save_model(str(model_path))
    print(f"Trained on {len(rows)} candidates across {len(grouped_rows)} queries.")
    print(f"Saved BO3 ranker to {model_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, type=Path, help="Labeled BO3 feedback CSV")
    parser.add_argument("--output", type=Path, default=MODEL_PATH, help="Model output JSON path")
    arguments = parser.parse_args()
    train(arguments.data, arguments.output)


if __name__ == "__main__":
    main()
