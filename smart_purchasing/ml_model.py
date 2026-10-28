"""XGBoost Machine Learning Classifier for Smart Purchasing Decisions.

Predicts purchase decisions (BUY, CONSIDER, SKIP) and class probability distributions
based on wardrobe feature vectors:
1. outfit_compatibility (0-100)
2. wardrobe_gap (0-100)
3. redundancy (0-100)
4. versatility (0-100)
5. style_match (0-100)
6. budget_penalty (0-25)
"""

import os
import json
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
import numpy as np

try:
    import xgboost as xgb
    XGB_AVAILABLE = True
except ImportError:
    XGB_AVAILABLE = False


MODEL_FILENAME = "xgb_purchase_model.json"
FEATURE_NAMES = [
    "outfit_compatibility",
    "wardrobe_gap",
    "redundancy",
    "versatility",
    "style_match",
    "budget_penalty"
]
CLASS_MAP = {0: "SKIP", 1: "CONSIDER", 2: "BUY"}
REV_CLASS_MAP = {"SKIP": 0, "CONSIDER": 1, "BUY": 2}


class PurchaseMLClassifier:
    """Trained XGBoost model to provide statistical decision predictions & confidence."""

    def __init__(self, model_dir: Optional[str] = None):
        self.model_dir = Path(model_dir) if model_dir else Path(__file__).resolve().parent / "data"
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.model_path = self.model_dir / MODEL_FILENAME
        self.model = None
        self._initialize_model()

    def _generate_synthetic_training_data(self, n_samples: int = 500) -> Tuple[np.ndarray, np.ndarray]:
        """Generates representative purchase evaluation feature vectors."""
        np.random.seed(42)

        outfit = np.random.uniform(30.0, 100.0, n_samples)
        gap = np.random.uniform(20.0, 95.0, n_samples)
        redundancy = np.random.uniform(0.0, 100.0, n_samples)
        versatility = np.random.uniform(50.0, 90.0, n_samples)
        style = np.random.uniform(50.0, 90.0, n_samples)
        penalty = np.random.choice([0.0, 5.0, 15.0, 25.0], p=[0.70, 0.10, 0.10, 0.10], size=n_samples)

        X = np.column_stack([outfit, gap, redundancy, versatility, style, penalty])
        y = []

        for o, g, r, v, s, p in X:
            low_r = max(0.0, 100.0 - r)
            score = 0.30 * o + 0.25 * g + 0.20 * v + 0.15 * s + 0.10 * low_r - p

            # Ground-truth constraints
            if r >= 85.0 or score < 45.0 or p >= 20.0:
                y.append(0)  # SKIP
            elif score >= 70.0:
                y.append(2)  # BUY
            else:
                y.append(1)  # CONSIDER

        return X, np.array(y, dtype=int)

    def _train_and_save_model(self):
        """Trains XGBoost multi-class classifier and serializes to JSON."""
        if not XGB_AVAILABLE:
            return

        X_train, y_train = self._generate_synthetic_training_data(n_samples=500)
        clf = xgb.XGBClassifier(
            n_estimators=75,
            max_depth=3,
            learning_rate=0.1,
            objective="multi:softprob",
            num_class=3,
            random_state=42
        )
        clf.fit(X_train, y_train)
        clf.save_model(str(self.model_path))
        self.model = clf

    def _initialize_model(self):
        """Loads cached model or trains a new one."""
        if not XGB_AVAILABLE:
            return

        if self.model_path.exists():
            try:
                clf = xgb.XGBClassifier()
                clf.load_model(str(self.model_path))
                self.model = clf
            except Exception:
                self._train_and_save_model()
        else:
            self._train_and_save_model()

    def predict(
        self,
        outfit_compatibility: float,
        wardrobe_gap: float,
        redundancy: float,
        versatility: float = 75.0,
        style_match: float = 80.0,
        budget_penalty: float = 0.0
    ) -> Dict[str, Any]:
        """Predicts decision probabilities and confidence using XGBoost."""
        if self.model is None or not XGB_AVAILABLE:
            # Deterministic heuristic fallback if XGBoost is unavailable
            return self._heuristic_fallback(
                outfit_compatibility, wardrobe_gap, redundancy, versatility, style_match, budget_penalty
            )

        features = np.array([[
            float(outfit_compatibility),
            float(wardrobe_gap),
            float(redundancy),
            float(versatility),
            float(style_match),
            float(budget_penalty)
        ]])

        probs = self.model.predict_proba(features)[0]
        pred_idx = int(np.argmax(probs))
        pred_label = CLASS_MAP[pred_idx]
        confidence = float(probs[pred_idx])

        # Top feature driver identification
        if redundancy >= 85.0:
            top_driver = "Direct Duplicate / Severe Redundancy"
        elif budget_penalty >= 15.0:
            top_driver = "Severe Budget Overrun"
        elif wardrobe_gap >= 70.0 and outfit_compatibility >= 70.0:
            top_driver = "High Wardrobe Gap & Outfit Pairing"
        elif outfit_compatibility >= 75.0:
            top_driver = "High Outfit Versatility"
        else:
            top_driver = "Moderate Wardrobe Overlap"

        return {
            "status": "success",
            "ml_decision": pred_label,
            "confidence": round(confidence, 3),
            "class_probabilities": {
                "BUY": round(float(probs[2]), 3),
                "CONSIDER": round(float(probs[1]), 3),
                "SKIP": round(float(probs[0]), 3)
            },
            "top_driver": top_driver
        }

    def _heuristic_fallback(
        self,
        outfit_compatibility: float,
        wardrobe_gap: float,
        redundancy: float,
        versatility: float,
        style_match: float,
        budget_penalty: float
    ) -> Dict[str, Any]:
        low_r = max(0.0, 100.0 - redundancy)
        score = 0.30 * outfit_compatibility + 0.25 * wardrobe_gap + 0.20 * versatility + 0.15 * style_match + 0.10 * low_r - budget_penalty

        if redundancy >= 85.0 or score < 45.0:
            label = "SKIP"
            probs = {"BUY": 0.05, "CONSIDER": 0.15, "SKIP": 0.80}
            conf = 0.80
        elif score >= 70.0:
            label = "BUY"
            probs = {"BUY": 0.85, "CONSIDER": 0.10, "SKIP": 0.05}
            conf = 0.85
        else:
            label = "CONSIDER"
            probs = {"BUY": 0.15, "CONSIDER": 0.70, "SKIP": 0.15}
            conf = 0.70

        return {
            "status": "fallback",
            "ml_decision": label,
            "confidence": conf,
            "class_probabilities": probs,
            "top_driver": "Heuristic Rule Fallback"
        }

    def get_feature_importances(self) -> Dict[str, float]:
        """Returns relative feature importances."""
        if self.model is None or not hasattr(self.model, "feature_importances_"):
            return {f: 0.166 for f in FEATURE_NAMES}
        return {
            name: round(float(imp), 4)
            for name, imp in zip(FEATURE_NAMES, self.model.feature_importances_)
        }


# Global singleton instance
_instance = None

def get_ml_classifier() -> PurchaseMLClassifier:
    """Returns cached instance of the PurchaseMLClassifier."""
    global _instance
    if _instance is None:
        _instance = PurchaseMLClassifier()
    return _instance


def predict_purchase_ml(
    outfit_compatibility: float,
    wardrobe_gap: float,
    redundancy: float,
    versatility: float = 75.0,
    style_match: float = 80.0,
    budget_penalty: float = 0.0
) -> Dict[str, Any]:
    """Convenience function calling the singleton XGBoost classifier."""
    return get_ml_classifier().predict(
        outfit_compatibility=outfit_compatibility,
        wardrobe_gap=wardrobe_gap,
        redundancy=redundancy,
        versatility=versatility,
        style_match=style_match,
        budget_penalty=budget_penalty
    )
