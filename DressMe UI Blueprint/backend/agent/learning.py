"""Human-in-the-loop learning for the BO3 ranker: feedback -> retraining.

Feedback labels: "I need this" = 3, "Not relevant" = 0. Candidates shown for the same goal
but left unrated are treated as neutral (1), so a single click already forms a usable
ranking group. Real feedback groups are weighted above the synthetic groups so a handful
of real labels can move a model trained on 140 synthetic scenarios.

Each user has their own retrained model (models/users/<user id>.json), trained on the synthetic
scenarios plus only that user's feedback. Retraining or resetting therefore never touches anyone
else's model; users without a retrained model rank with the shared synthetic demo model.
"""

import csv
import json
import os
import re
import threading
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.metrics import ndcg_score

from xgboost_ranker import FEATURES, load_ranker, make_ranker

from .coverage import compute_coverage
from .memory import AgentMemory

BACKEND_DIR = Path(__file__).resolve().parents[1]
SYNTHETIC_DATA = BACKEND_DIR / "data" / "bo3_synthetic_training_demo.csv"
DEMO_MODEL_PATH = BACKEND_DIR / "models" / "bo3_gap_ranker_synthetic_demo.json"
USER_MODELS_DIR = BACKEND_DIR / "models" / "users"

NEUTRAL_RELEVANCE = 1
# Chosen empirically: 8 fully learns one feedback group while disturbing other goals less than 25.
REAL_GROUP_WEIGHT = 8.0

_train_lock = threading.Lock()   # XGBoost training is CPU-heavy: one retraining at a time per process


def user_model_path(user_id: str | None) -> Path:
    """models/users/<user id>.json; anything but letters, digits, '-' and '_' is replaced (no path tricks)."""
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", user_id or "demo_user")[:80]
    return USER_MODELS_DIR / f"{safe}.json"


def _meta_path(user_id: str | None) -> Path:
    return user_model_path(user_id).with_suffix(".meta.json")


def active_model_path(user_id: str | None = None) -> Path:
    """The user's own retrained model if they have one; otherwise the synthetic demo model."""
    own = user_model_path(user_id)
    return own if own.is_file() else DEMO_MODEL_PATH


def model_metadata(user_id: str | None = None) -> dict[str, Any] | None:
    meta = _meta_path(user_id)
    if user_model_path(user_id).is_file() and meta.is_file():
        return json.loads(meta.read_text(encoding="utf-8"))
    return None


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
    # Imported here to avoid a circular import: tools uses this module for the active model.
    from .tools import load_profile, load_wardrobe, score_candidates

    by_goal: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for entry in memory.list_feedback(user_id):
        by_goal[entry["goal"]][entry["candidate_id"]] = entry

    wardrobe, profile = load_wardrobe(user_id), load_profile(user_id)

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

    previous_model = active_model_path(user_id)
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

    ranker = make_ranker()   # same hyperparameters as CSV training; here with per-group weights
    with _train_lock:
        ranker.fit(np.array(features), labels, qid=query_ids, sample_weight=group_weights, verbose=False)
    model_path = user_model_path(user_id)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = model_path.with_name(model_path.stem + ".tmp.json")
    ranker.save_model(str(temporary))
    os.replace(temporary, model_path)      # a request ranking at the same moment never reads a half-written file

    metadata = {
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "previous_model": previous_model.name,
        "synthetic_groups": len(all_groups) - len(groups),
        "feedback_groups": len(groups),
        "explicit_labels": sum(group["explicit_labels"] for group in groups),
        "real_group_weight": REAL_GROUP_WEIGHT,
        "ndcg_at_3_before": ndcg_before,
        "ndcg_at_3_after": _ndcg_at_3(model_path, groups),
        "evaluation": "in-sample on the user's feedback groups",
    }
    _meta_path(user_id).write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def reset_model(user_id: str | None = None) -> None:
    """Return THIS user to the synthetic demo model. Other users' models are untouched."""
    user_model_path(user_id).unlink(missing_ok=True)
    _meta_path(user_id).unlink(missing_ok=True)


def learning_status(memory: AgentMemory, user_id: str) -> dict[str, Any]:
    feedback = memory.list_feedback(user_id)
    return {
        "active_model": active_model_path(user_id).name,
        "personalised": user_model_path(user_id).is_file(),
        "feedback_labels": len(feedback),
        "need_labels": sum(1 for f in feedback if f["relevance"] == 3),
        "not_relevant_labels": sum(1 for f in feedback if f["relevance"] == 0),
        "goals_with_feedback": sorted({f["goal"] for f in feedback}),
        "last_training": model_metadata(user_id),
    }
