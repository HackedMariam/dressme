"""Data Science Benchmark & Evaluation Metrics Runner for DressMe Shopper Agent.

Computes standard ML & Engineering metrics:
1. Classification Accuracy
2. Confusion Matrix (BUY, CONSIDER, SKIP)
3. Precision, Recall, and F1-Score (Per-Class, Macro, and Weighted)
4. Score Regression Metrics: Mean Absolute Error (MAE) and Root Mean Squared Error (RMSE)
5. Actionable Error Analysis for model and weight tuning
"""

import json
import time
from pathlib import Path
from collections import defaultdict
from typing import Dict, Any, List, Tuple

from schemas import CandidateItem, EvaluatePurchaseRequest, DecisionType
from agent import PurchaseAgent


def compute_classification_metrics(y_true: List[str], y_pred: List[str]) -> Dict[str, Any]:
    """Calculates Accuracy, Confusion Matrix, Precision, Recall, and F1 per class."""
    classes = ["BUY", "CONSIDER", "SKIP"]
    total = len(y_true)

    # Confusion Matrix: cm[actual][predicted]
    cm = {act: {pred: 0 for pred in classes} for act in classes}
    for t, p in zip(y_true, y_pred):
        if t in cm and p in cm[t]:
            cm[t][p] += 1

    # Accuracy
    correct = sum(cm[c][c] for c in classes)
    accuracy = correct / max(1, total)

    # Per-class metrics
    metrics_per_class = {}
    macro_p, macro_r, macro_f1 = 0.0, 0.0, 0.0
    weighted_p, weighted_r, weighted_f1 = 0.0, 0.0, 0.0

    for c in classes:
        tp = cm[c][c]
        fp = sum(cm[other][c] for other in classes if other != c)
        fn = sum(cm[c][other] for other in classes if other != c)
        support = sum(cm[c].values())

        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0

        metrics_per_class[c] = {
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "f1_score": round(f1, 4),
            "support": support
        }

        macro_p += prec
        macro_r += rec
        macro_f1 += f1

        weighted_p += prec * support
        weighted_r += rec * support
        weighted_f1 += f1 * support

    macro_p /= len(classes)
    macro_r /= len(classes)
    macro_f1 /= len(classes)

    weighted_p /= max(1, total)
    weighted_r /= max(1, total)
    weighted_f1 /= max(1, total)

    return {
        "accuracy": round(accuracy, 4),
        "confusion_matrix": cm,
        "per_class": metrics_per_class,
        "macro_avg": {
            "precision": round(macro_p, 4),
            "recall": round(macro_r, 4),
            "f1_score": round(macro_f1, 4)
        },
        "weighted_avg": {
            "precision": round(weighted_p, 4),
            "recall": round(weighted_r, 4),
            "f1_score": round(weighted_f1, 4)
        }
    }


def compute_regression_metrics(y_true_scores: List[float], y_pred_scores: List[float]) -> Dict[str, float]:
    """Calculates MAE and RMSE between predicted purchase score and ground-truth target score."""
    n = len(y_true_scores)
    if n == 0:
        return {"mae": 0.0, "rmse": 0.0}

    mae = sum(abs(t - p) for t, p in zip(y_true_scores, y_pred_scores)) / n
    mse = sum((t - p) ** 2 for t, p in zip(y_true_scores, y_pred_scores)) / n
    rmse = mse ** 0.5

    return {
        "mae": round(mae, 2),
        "rmse": round(rmse, 2)
    }


def run_benchmark(dataset_file: str = "data/test_benchmark.json"):
    data_path = Path(__file__).resolve().parent / dataset_file
    if not data_path.exists():
        print(f"Error: Dataset {data_path} not found.")
        return

    with open(data_path, "r", encoding="utf-8") as f:
        benchmark_cases = json.load(f)

    print("==========================================================================================")
    print(f"       DRESSME SHOPPER AGENT — DATA SCIENCE EVALUATION BENCHMARK ({len(benchmark_cases)} SAMPLES)")
    print("==========================================================================================")

    agent = PurchaseAgent()

    y_true_labels = []
    y_pred_labels = []
    y_true_scores = []
    y_pred_scores = []
    error_cases = []

    start_time = time.time()

    for idx, case in enumerate(benchmark_cases):
        cand = CandidateItem(**case["candidate"])
        req = EvaluatePurchaseRequest(
            candidate=cand,
            budget=case["candidate"].get("budget"),
            user_query=f"Should I buy this {cand.color} {cand.category}?"
        )
        rec = agent.evaluate(req, skip_llm=True)

        pred_label = rec.decision.value if rec.decision else "UNKNOWN"
        true_label = case["ground_truth_decision"]
        pred_score = rec.overall_score if rec.overall_score is not None else 50.0
        true_score = case.get("target_score", 50.0)

        y_true_labels.append(true_label)
        y_pred_labels.append(pred_label)
        y_true_scores.append(true_score)
        y_pred_scores.append(pred_score)

        is_correct = (pred_label == true_label)
        status_tag = "PASS" if is_correct else "MISMATCH"
        print(
            f"[{idx+1:02d}/{len(benchmark_cases):02d}] {status_tag} | {case['name'][:42]:<42} "
            f"| Target: {true_label:<8} | Pred: {pred_label:<8} (Score: {pred_score:4.1f} vs {true_score:4.1f})",
            flush=True
        )


        if not is_correct:
            error_cases.append({
                "id": case["id"],
                "name": case["name"],
                "true_label": true_label,
                "pred_label": pred_label,
                "true_score": true_score,
                "pred_score": pred_score,
                "scenario": case.get("scenario_type")
            })

    total_time = time.time() - start_time

    # Compute Metrics
    clf_metrics = compute_classification_metrics(y_true_labels, y_pred_labels)
    reg_metrics = compute_regression_metrics(y_true_scores, y_pred_scores)

    # -------------------------------------------------------------------------
    # PRINT FORMAL DATA SCIENCE REPORT
    # -------------------------------------------------------------------------
    print("\n" + "=" * 90)
    print("                              CLASSIFICATION REPORT")
    print("=" * 90)
    print(f"{'CLASS':<12} {'PRECISION':<12} {'RECALL':<12} {'F1-SCORE':<12} {'SUPPORT':<10}")
    print("-" * 58)
    for c in ["BUY", "CONSIDER", "SKIP"]:
        m = clf_metrics["per_class"][c]
        print(f"{c:<12} {m['precision']:<12.4f} {m['recall']:<12.4f} {m['f1_score']:<12.4f} {m['support']:<10}")
    print("-" * 58)
    ma = clf_metrics["macro_avg"]
    wa = clf_metrics["weighted_avg"]
    print(f"{'Macro Avg':<12} {ma['precision']:<12.4f} {ma['recall']:<12.4f} {ma['f1_score']:<12.4f} {len(y_true_labels):<10}")
    print(f"{'Weighted Avg':<12} {wa['precision']:<12.4f} {wa['recall']:<12.4f} {wa['f1_score']:<12.4f} {len(y_true_labels):<10}")
    print("=" * 90)
    print(f"OVERALL MODEL ACCURACY : {clf_metrics['accuracy'] * 100:.2f}% ({sum(1 for t, p in zip(y_true_labels, y_pred_labels) if t == p)} / {len(y_true_labels)} samples correct)")
    print(f"SCORE REGRESSION MAE   : {reg_metrics['mae']:.2f} points (Mean Absolute Error against target)")
    print(f"SCORE REGRESSION RMSE  : {reg_metrics['rmse']:.2f} points")
    print(f"TOTAL BENCHMARK TIME   : {total_time:.2f}s (Average: {total_time/len(benchmark_cases):.2f}s per item)")

    # -------------------------------------------------------------------------
    # CONFUSION MATRIX
    # -------------------------------------------------------------------------
    print("\n" + "=" * 65)
    print("                       CONFUSION MATRIX")
    print("=" * 65)
    print(f"{'Actual \\ Predicted':<18} {'Pred BUY':<12} {'Pred CONSIDER':<15} {'Pred SKIP':<10}")
    print("-" * 55)
    cm = clf_metrics["confusion_matrix"]
    for act in ["BUY", "CONSIDER", "SKIP"]:
        print(f"{act:<18} {cm[act]['BUY']:<12} {cm[act]['CONSIDER']:<15} {cm[act]['SKIP']:<10}")
    print("=" * 65)

    # -------------------------------------------------------------------------
    # ERROR ANALYSIS & ACTIONABLE MODEL IMPROVEMENTS
    # -------------------------------------------------------------------------
    if error_cases:
        print("\n" + "=" * 90)
        print("                 ERROR ANALYSIS & MODEL IMPROVEMENT GUIDANCE")
        print("=" * 90)
        for err in error_cases:
            print(f" * Case [{err['id']}]: {err['name']}")
            print(f"   Target: {err['true_label']} (Score {err['true_score']}) -> Model Predicted: {err['pred_label']} (Score {err['pred_score']})")
            if err["true_label"] == "SKIP" and err["pred_label"] != "SKIP":
                print("   [Remediation Tip]: Under-penalizing redundancy. Increase weight W_R in formula or tighten direct duplicate threshold.")
            elif err["true_label"] == "BUY" and err["pred_label"] != "BUY":
                print("   [Remediation Tip]: Over-penalizing gap or compatibility. Lower decision threshold from 70 to 68 or boost outfit weight W_O.")
    else:
        print("\nPerfect 100% Score across all 15 diverse benchmark scenarios!")
    print("=" * 90)


if __name__ == "__main__":
    run_benchmark()
