"""Train the BO3 XGBoost ranker from grouped, labeled candidate feedback."""

import argparse
import csv
from collections import defaultdict
from pathlib import Path

from xgboost import XGBRanker

from xgboost_ranker import FEATURES, MODEL_PATH

REQUIRED_COLUMNS = ("query_id", "candidate_id", *FEATURES, "relevance")


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

    ranker = XGBRanker(
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
