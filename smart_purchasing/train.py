"""Fine-tuning and evaluation script for Qwen3-4B on Cloud GPU."""

import json
import argparse
from pathlib import Path
from schemas import CandidateItem, EvaluatePurchaseRequest
from agent import PurchaseAgent


def evaluate_dataset(eval_file_path: str = "data/evaluation.jsonl"):
    """Runs evaluation benchmark against test dataset."""
    agent = PurchaseAgent()
    path = Path(__file__).resolve().parent / eval_file_path
    if not path.exists():
        print(f"Error: {path} not found.")
        return

    print("=== Running Purchase Agent Evaluation Benchmark ===")
    total, correct = 0, 0
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            total += 1
            cand = CandidateItem(**row["candidate_item"])
            rec = agent.evaluate(EvaluatePurchaseRequest(candidate=cand))
            expected = row.get("expected_decision")
            actual = rec.decision.value
            passed = (expected == actual)
            if passed:
                correct += 1
            print(f"[{row.get('eval_id')}]: Expected={expected}, Actual={actual}, Score={rec.overall_score:.1f} | {'PASS' if passed else 'FAIL'}")

    acc = (correct / max(1, total)) * 100
    print(f"\nAccuracy: {acc:.1f}% ({correct}/{total})")


def train_lora_cloud(
    model_name: str = "Qwen/Qwen3-4B",
    dataset_path: str = "data/training.jsonl",
    output_dir: str = "models/purchase_agent_lora",
    epochs: int = 3
):
    """Skeleton for QLoRA fine-tuning on a Cloud GPU (Colab/Modal/RunPod)."""
    print(f"=== Qwen3-4B LoRA Fine-Tuning Setup ===")
    print(f"Model: {model_name}")
    print(f"Dataset: {dataset_path}")
    print(f"Output: {output_dir}")
    print("\nTo train on Cloud GPU:")
    print("1. pip install trl peft transformers datasets bitsandbytes accelerate")
    print("2. python train.py --train")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--eval", action="store_true", help="Run evaluation benchmark")
    parser.add_argument("--train", action="store_true", help="Run LoRA training")
    args = parser.parse_args()

    if args.train:
        train_lora_cloud()
    else:
        evaluate_dataset()
