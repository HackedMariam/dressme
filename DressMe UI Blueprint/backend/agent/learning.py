"""Human-in-the-loop learning for the BO3 ranker: feedback -> retraining -> SHAP explanations.

Feedback labels: "I need this" = 3, "Not relevant" = 0. Candidates shown for the same goal
but left unrated are treated as neutral (1), so a single click already forms a usable
ranking group. Real feedback groups are weighted above the synthetic groups so a handful
of real labels can move a model trained on 140 synthetic scenarios.
"""

import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.metrics import ndcg_score
from xgboost import DMatrix, XGBRanker

from xgboost_ranker import FEATURES, MODEL_PATH, load_ranker

from .coverage import compute_coverage
from .memory import AgentMemory

BACKEND_DIR = Path(__file__).resolve().parents[1]
SYNTHETIC_DATA = BACKEND_DIR / "data" / "bo3_synthetic_training_demo.csv"
DEMO_MODEL_PATH = BACKEND_DIR / "models" / "bo3_gap_ranker_synthetic_demo.json"
META_PATH = MODEL_PATH.with_suffix(".meta.json")

NEUTRAL_RELEVANCE = 1
# Chosen empirically: 8 fully learns one feedback group while disturbing other goals less than 25.
REAL_GROUP_WEIGHT = 8.0


def active_model_path() -> Path:
    """Prefer the model retrained from feedback; fall back to the synthetic demo."""
    return MODEL_PATH if MODEL_PATH.is_file() else DEMO_MODEL_PATH


def model_metadata() -> dict[str, Any] | None:
    if MODEL_PATH.is_file() and META_PATH.is_file():
        return json.loads(META_PATH.read_text(encoding="utf-8"))
    return None


def shap_contributions(feature_rows: list[list[float]], model_path: Path | None = None) -> list[dict[str, Any]]:
    """Exact TreeSHAP values from XGBoost: per-feature contribution to each ranking score."""
    booster = load_ranker(model_path or active_model_path()).get_booster()
    contributions = booster.predict(DMatrix(np.array(feature_rows, dtype=float)), pred_contribs=True)
    return [
        {
            "contributions": {name: round(float(value), 4) for name, value in zip(FEATURES, row[:-1])},
            "base_value": round(float(row[-1]), 4),
        }
        for row in contributions
    ]


def _synthetic_groups() -> list[tuple[list[list[float]], list[int]]]:
    grouped: dict[str, tuple[list[list[float]], list[int]]] = defaultdict(lambda: ([], []))
    with SYNTHETIC_DATA.open(encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            features, labels = grouped[row["query_id"]]
            features.append([float(row[name]) for name in FEATURES])
            labels.append(int(row["relevance"]))
    return list(grouped.values())


def feedback_groups(memory: AgentMemory, user_id: str) -> list[dict[str, Any]]:
    """One ranking group per goal the user rated, completed with neutral unrated candidates."""
    # Imported here to avoid a circular import: tools uses this module for SHAP.
    from .tools import load_profile, load_wardrobe, score_candidates

    by_goal: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for entry in memory.list_feedback(user_id):
        by_goal[entry["goal"]][entry["candidate_id"]] = entry

    wardrobe, profile = load_wardrobe(), load_profile()
    groups = []
    for goal, rated in by_goal.items():
        candidates = compute_coverage(wardrobe, goal)["candidates"]
        current = {c["candidate_id"]: c for c in score_candidates(goal, candidates, wardrobe, profile)} if candidates else {}
        ids, features, labels = [], [], []
        for candidate_id in sorted(set(rated) | set(current)):
            if candidate_id in rated:
                feature_values = rated[candidate_id]["features"]
                label = rated[candidate_id]["relevance"]
            else:
                feature_values = current[candidate_id]
                label = NEUTRAL_RELEVANCE
            ids.append(candidate_id)
            features.append([float(feature_values[name]) for name in FEATURES])
            labels.append(label)
        if len(ids) >= 2 and len(set(labels)) >= 2:
            groups.append({"goal": goal, "candidate_ids": ids, "features": features, "labels": labels,
                           "explicit_labels": len(rated)})
    return groups


def _ndcg_at_3(model_path: Path, groups: list[dict[str, Any]]) -> float | None:
    if not groups:
        return None
    ranker = load_ranker(model_path)
    scores = [
        ndcg_score([group["labels"]], [ranker.predict(np.array(group["features"])).tolist()], k=3)
        for group in groups
    ]
    return round(float(np.mean(scores)), 4)


def retrain(memory: AgentMemory, user_id: str) -> dict[str, Any]:
    groups = feedback_groups(memory, user_id)
    if not groups:
        raise ValueError(
            "Not enough feedback yet. Mark at least one suggestion as 'I need this' or 'Not relevant'."
        )

    previous_model = active_model_path()
    ndcg_before = _ndcg_at_3(previous_model, groups)

    features: list[list[float]] = []
    labels: list[int] = []
    query_ids: list[int] = []
    group_weights: list[float] = []
    all_groups = [(g, 1.0) for g in _synthetic_groups()] + [
        ((group["features"], group["labels"]), REAL_GROUP_WEIGHT) for group in groups
    ]
    for query_id, ((group_features, group_labels), weight) in enumerate(all_groups):
        features += group_features
        labels += group_labels
        query_ids += [query_id] * len(group_labels)
        group_weights.append(weight)

    # Same hyperparameters as train_bo3_ranker.py, plus per-group weights.
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
    ranker.fit(np.array(features), labels, qid=query_ids, sample_weight=group_weights, verbose=False)
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    ranker.save_model(str(MODEL_PATH))

    metadata = {
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "previous_model": previous_model.name,
        "synthetic_groups": len(all_groups) - len(groups),
        "feedback_groups": len(groups),
        "explicit_labels": sum(group["explicit_labels"] for group in groups),
        "real_group_weight": REAL_GROUP_WEIGHT,
        "ndcg_at_3_before": ndcg_before,
        "ndcg_at_3_after": _ndcg_at_3(MODEL_PATH, groups),
        "evaluation": "in-sample on the user's feedback groups",
    }
    META_PATH.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def reset_model() -> None:
    """Return to the synthetic demo model."""
    MODEL_PATH.unlink(missing_ok=True)
    META_PATH.unlink(missing_ok=True)


def learning_status(memory: AgentMemory, user_id: str) -> dict[str, Any]:
    feedback = memory.list_feedback(user_id)
    return {
        "active_model": active_model_path().name,
        "personalised": MODEL_PATH.is_file(),
        "feedback_labels": len(feedback),
        "need_labels": sum(1 for f in feedback if f["relevance"] == 3),
        "not_relevant_labels": sum(1 for f in feedback if f["relevance"] == 0),
        "goals_with_feedback": sorted({f["goal"] for f in feedback}),
        "last_training": model_metadata(),
    }
