"""Rank candidate BO3 wardrobe gaps with a trained XGBoost ranker."""

import math
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
    """Load the model produced by train_bo3_ranker.py."""
    path = Path(model_path)
    if not path.is_file():
        raise FileNotFoundError(
            f"No trained BO3 ranker at {path}. Collect labeled feedback and "
            "run backend/train_bo3_ranker.py first."
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
