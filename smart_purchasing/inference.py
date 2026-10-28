"""Standalone Universal Inference Pipeline for DressMe Fashion Agent.

Powered by:
- YOLO segmentation model ('dressme_best.pt') for garment detection & CIEDE2000 color extraction.
- Wardrobe combinatorics & XGBoost ML tool ('xgb_purchase_model.json').
- Hugging Face Serverless Inference API for Qwen reasoning (0 GB downloaded, 0 MB RAM, fast).
  Reads 'HF_TOKEN' automatically from your .env file.
"""

import os
import sys
import re
import csv
import json
import time
import argparse
import tempfile
import urllib.request
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

# Add smart_purchasing to sys.path
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = CURRENT_DIR / "smart_purchasing" if (CURRENT_DIR / "smart_purchasing").exists() else CURRENT_DIR
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))


def load_dotenv(env_path: Optional[Path] = None):
    """Loads environment variables from .env without requiring external libraries."""
    if env_path is None:
        candidates = [
            Path(".env"),
            CURRENT_DIR / ".env",
            PROJECT_DIR / ".env",
            CURRENT_DIR.parent / ".env",
        ]
        for c in candidates:
            if c.exists():
                env_path = c
                break

    if env_path and env_path.exists():
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        if k and k not in os.environ and v:
                            os.environ[k] = v
        except Exception:
            pass


# Automatically load .env on startup
load_dotenv()

# Domain tools & schemas
from schemas import CandidateItem, Garment
from tools import (
    find_similar_items,
    check_outfit_compatibility,
    analyze_wardrobe_gaps,
    calculate_purchase_value,
    analyze_item,
)
from ml_model import predict_purchase_ml

# Default models on Hugging Face Serverless API
DEFAULT_HF_MODEL = os.environ.get("HF_MODEL_ID", "Qwen/Qwen2.5-72B-Instruct")

SYSTEM_PROMPT = (
    "You are DressMe Shopping Assistant, an expert AI fashion and wardrobe consultant. "
    "Evaluate whether the user should buy the proposed clothing item based on their wardrobe, "
    "preferences, tool results, and budget. Return ONLY a valid JSON object with fields: "
    "decision (BUY, DON'T BUY, CONSIDER), score (0-100), reasons (list), and uncertainties (list)."
)

OCCASION_KEYWORDS = {
    "work": ("work", ["formal", "smart_casual"]),
    "office": ("work", ["formal", "smart_casual"]),
    "meeting": ("work", ["formal", "smart_casual"]),
    "business": ("work", ["formal", "smart_casual"]),
    "formal": ("formal_event", ["formal"]),
    "wedding": ("formal_event", ["formal", "evening"]),
    "dinner": ("dinner", ["smart_casual", "formal"]),
    "date": ("dinner", ["smart_casual"]),
    "party": ("party", ["party", "evening"]),
    "casual": ("casual_outing", ["casual"]),
    "weekend": ("casual_outing", ["casual"]),
    "everyday": ("casual_outing", ["casual"]),
    "gym": ("gym", ["sporty"]),
}


def load_wardrobe_from_csv(file_path: Path) -> List[Garment]:
    """Loads and adapts wardrobe.csv into typed Garment domain objects without depending on agent.py."""
    garments: List[Garment] = []
    with open(file_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            item_id = row.get("item_id", "").strip()
            name = row.get("name", "").strip()
            macro_cat = row.get("category", "").strip().lower()
            item_type = row.get("item_type", "").strip().lower().replace("-", "_")
            primary_cat = item_type if item_type else macro_cat
            color = row.get("color", "unknown").strip().lower()

            style_raw = row.get("style", "casual").strip().lower().replace("-", "_")
            style_list = [style_raw]
            if style_raw == "smart_casual":
                style_list = ["smart_casual", "formal"]

            season_raw = row.get("season", "all-season").strip().lower()
            if season_raw in ["all-season", "all_season"]:
                seasons = ["spring", "summer", "autumn", "winter"]
            else:
                seasons = [season_raw]

            formality = int(row.get("formality_level", 3)) if row.get("formality_level") else 3
            if formality >= 4 or style_raw == "formal":
                occasions = ["work", "formal_event", "meeting", "dinner"]
            elif formality == 3 or style_raw == "smart_casual":
                occasions = ["work", "dinner", "casual_outing", "meeting"]
            else:
                occasions = ["casual_outing", "weekend", "travel"]

            tags = [macro_cat, item_type]
            desc = row.get("description", "").strip()
            if desc:
                tags.extend([w.lower() for w in desc.split() if len(w) > 3])

            versatility_val = None
            if row.get("versatility"):
                try:
                    versatility_val = float(row["versatility"])
                except ValueError:
                    pass

            garments.append(Garment(
                id=item_id,
                name=name,
                category=primary_cat,
                color=color,
                style=style_list,
                seasons=seasons,
                occasions=occasions,
                tags=tags,
                item_type=item_type,
                warmth_level=int(row["warmth_level"]) if row.get("warmth_level") else None,
                water_resistance=int(row["water_resistance"]) if row.get("water_resistance") else None,
                weight_g=int(row["weight_g"]) if row.get("weight_g") else None,
                versatility=versatility_val,
                formality_level=formality,
                clean_items_available=row.get("clean_items_available", "True").lower() == "true",
                description=desc,
            ))
    return garments


class DressMeInferenceEngine:
    """Manages model loading and end-to-end evaluation using Hugging Face Inference API."""

    def __init__(self, skip_llm: bool = False, hf_token: Optional[str] = None, model_id: Optional[str] = None):
        self.skip_llm = skip_llm
        self.hf_token = hf_token or os.environ.get("HF_TOKEN")
        self.model_id = model_id or DEFAULT_HF_MODEL
        self.wardrobe: List[Garment] = []
        self.client = None

        self._load_wardrobe()
        if not self.skip_llm:
            self._init_hf_client()

    def _load_wardrobe(self):
        """Loads wardrobe from wardrobe.csv."""
        wardrobe_candidates = [
            PROJECT_DIR / "wardrobe.csv",
            CURRENT_DIR / "wardrobe.csv",
            PROJECT_DIR / "data" / "sample_wardrobe.json",
        ]
        chosen = None
        for p in wardrobe_candidates:
            if p.exists():
                chosen = p
                break
        if chosen and chosen.suffix.lower() == ".csv":
            self.wardrobe = load_wardrobe_from_csv(chosen)
            print(f"[Wardrobe] Loaded {len(self.wardrobe)} garments from {chosen.name}")
        elif chosen:
            with open(chosen, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.wardrobe = [Garment(**it) for it in data]
            print(f"[Wardrobe] Loaded {len(self.wardrobe)} garments from {chosen.name}")
        else:
            print("[Wardrobe Warning] wardrobe.csv not found; wardrobe list is empty.")

    def _init_hf_client(self):
        """Initializes Hugging Face InferenceClient using HF_TOKEN from .env."""
        if not self.hf_token:
            print("[Model Notice] No HF_TOKEN found in .env or environment.")
            print("               To enable cloud Qwen reasoning, paste your free token in .env:")
            print("               HF_TOKEN=hf_your_token_here")
            print("               Running in deterministic evaluation mode...")
            return

        try:
            from huggingface_hub import InferenceClient
            self.client = InferenceClient(token=self.hf_token)
            print(f"[Model Loader] Connected to Hugging Face Serverless API ({self.model_id})")
        except Exception as e:
            print(f"[Model Notice] Could not initialize Hugging Face client: {e}")
            self.client = None

    @staticmethod
    def infer_occasion_and_style(user_prompt: str, detected_category: str) -> Tuple[str, List[str]]:
        prompt_lower = user_prompt.lower()
        for kw, (occ, styles) in OCCASION_KEYWORDS.items():
            if re.search(r"\b" + kw + r"\b", prompt_lower):
                return occ, styles

        cat = detected_category.lower().replace("-", "_")
        if cat in ["jacket", "blazer", "coat"]:
            return "work", ["formal", "smart_casual"]
        if cat in ["dress"]:
            return "dinner", ["formal", "evening"]
        return "casual_outing", ["casual"]

    def evaluate(
        self,
        image_path: str,
        price: float,
        budget: float,
        user_prompt: str = "Should I buy this?"
    ) -> Dict[str, Any]:
        """Runs end-to-end evaluation pipeline."""
        # 1. Download image if URL
        local_image = str(image_path)
        if local_image.startswith("http://") or local_image.startswith("https://"):
            local_image = os.path.join(tempfile.gettempdir(), "downloaded_garment.jpg")
            req = urllib.request.Request(image_path, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req) as resp, open(local_image, "wb") as f:
                f.write(resp.read())

        # 2. Computer Vision Analysis (YOLO segmentation + CIEDE2000)
        cand = CandidateItem(category="unknown", image_path=local_image, price=price, budget=budget)
        vision_data = analyze_item(cand)
        category = vision_data.get("category", "top")
        color = vision_data.get("color", "black")

        # 3. Infer occasion & style
        occasion, styles = self.infer_occasion_and_style(user_prompt, category)
        cand.category = category
        cand.color = color
        cand.target_occasion = occasion
        cand.style = styles

        # 4. Execute domain tools
        sims = find_similar_items(cand, self.wardrobe, top_k=3)
        top_sim = sims[0].similarity_score if sims else 0.0
        redundancy_pct = round(top_sim * 100.0, 1)

        outfits = check_outfit_compatibility(cand, self.wardrobe, target_occasion=occasion)
        comp_count = outfits.get("compatible_count", 0)
        avg_score = outfits.get("average_score", 70.0)

        matching_outfits = []
        paired_item_ids = []
        outfit_desc_lines = []
        for combo in outfits.get("combinations", []):
            combo_items = []
            item_labels = []
            for g in combo.paired_garments:
                combo_items.append({
                    "item_id": g.id,
                    "name": g.name,
                    "category": g.category,
                    "color": g.color,
                })
                if g.id not in paired_item_ids:
                    paired_item_ids.append(g.id)
                item_labels.append(f"{g.id} ({g.name})")
            matching_outfits.append({
                "outfit_id": combo.outfit_id,
                "description": combo.description,
                "compatibility_score": combo.compatibility_score,
                "paired_items": combo_items,
            })
            outfit_desc_lines.append(f"{combo.outfit_id}: " + " + ".join(item_labels))

        paired_ids_str = ", ".join(paired_item_ids) if paired_item_ids else "None"
        outfit_summary = "; ".join(outfit_desc_lines) if outfit_desc_lines else "None"

        gap_res = analyze_wardrobe_gaps(cand, self.wardrobe)
        gap_score = gap_res.gap_fill_score

        penalty = min(25.0, round(((price - budget) / budget) * 20.0, 2)) if budget > 0 and price > budget else 0.0

        ml_res = predict_purchase_ml(
            outfit_compatibility=avg_score,
            wardrobe_gap=gap_score,
            redundancy=redundancy_pct,
            versatility=min(100.0, 50.0 + comp_count * 15.0),
            style_match=80.0,
            budget_penalty=penalty,
        )

        val_res = calculate_purchase_value(
            outfit_compatibility_score=avg_score,
            wardrobe_gap_score=gap_score,
            versatility_score=min(100.0, 50.0 + comp_count * 15.0),
            personal_style_score=80.0,
            redundancy_score=redundancy_pct,
            price=price,
            budget=budget,
            ml_decision=ml_res["ml_decision"],
            ml_confidence=ml_res["confidence"],
        )

        # 5. Qwen Reasoning via Hugging Face Serverless API
        agent_output = None
        if not self.skip_llm and self.client is not None:
            scenario_prompt = (
                f"Scenario ID: IMG-{int(time.time())%10000}\n"
                f"Proposed Item: {color.title()} {category.title()} (Image Analysis), Price: ${price:.0f}, Style: {', '.join(styles)}\n"
                f"User Budget: ${budget:.0f}, Preferred Style: {', '.join(styles)}\n"
                f"User Question: \"{user_prompt}\"\n"
                f"Category Evaluation Focus: autonomous_full_loop\n"
                f"Wardrobe Context: User has {len(self.wardrobe)} items in wardrobe.\n"
                f"Tool analysis: Redundancy={redundancy_pct}%, Outfits={comp_count}.\n"
                f"Matching Outfits in Wardrobe: {outfit_summary}\n"
                f"Compatible Garment IDs: [{paired_ids_str}]\n"
                f"GapScore={gap_score:.1f}, CalculatedScore={val_res.overall_score:.1f}, ML_Decision={ml_res['ml_decision']}.\n"
                f"Instruction: In your reasons, cite the exact item IDs (e.g. {paired_ids_str}) of the clothes that pair into complete outfits."
            )
            try:
                print(f"[API] Querying {self.model_id} on Hugging Face Serverless API...")
                response = self.client.chat.completions.create(
                    model=self.model_id,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": scenario_prompt},
                    ],
                    max_tokens=220,
                    temperature=0.1,
                )
                raw_response = response.choices[0].message.content.strip()

                cleaned = raw_response
                if "```" in cleaned:
                    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
                    if m:
                        cleaned = m.group(1).strip()
                m = re.search(r"(\{[\s\S]*\})", cleaned)
                if m:
                    cleaned = m.group(1).strip()

                try:
                    agent_output = json.loads(cleaned)
                except Exception:
                    agent_output = {
                        "decision": val_res.decision.value,
                        "score": val_res.overall_score,
                        "reasons": [raw_response],
                        "uncertainties": [],
                    }
            except Exception as e:
                print(f"[API Warning] Hugging Face API query failed: {e}")
                print("[API Warning] Falling back to deterministic output.")
                agent_output = None

        if agent_output is None:
            # Deterministic output
            agent_output = {
                "decision": val_res.decision.value,
                "score": val_res.overall_score,
                "reasons": [
                    f"Deterministic evaluation: compatible with {comp_count} outfits in closet.",
                    f"XGBoost classification: {ml_res['ml_decision']} (confidence {ml_res['confidence']*100:.1f}%).",
                ],
                "uncertainties": [],
            }

        return {
            "status": "success",
            "user_query": user_prompt,
            "candidate_item": {
                "image_source": str(image_path),
                "detected_category": category,
                "detected_color": color,
                "inferred_occasion": occasion,
                "inferred_style": styles,
                "price": price,
                "budget": budget,
            },
            "tool_evidence": {
                "redundancy_score": redundancy_pct,
                "closest_wardrobe_match": sims[0].garment.name if sims else None,
                "compatible_outfits_count": comp_count,
                "matching_wardrobe_item_ids": paired_item_ids,
                "matching_outfits": matching_outfits,
                "wardrobe_gap_score": gap_score,
                "xgboost_prediction": ml_res["ml_decision"],
                "xgboost_confidence": ml_res["confidence"],
                "deterministic_score": val_res.overall_score,
                "budget_penalty": penalty,
            },
            "agent_verdict": {
                "decision": agent_output.get("decision", val_res.decision.value),
                "score": agent_output.get("score", val_res.overall_score),
                "matching_item_ids": paired_item_ids,
                "reasons": agent_output.get("reasons", []),
                "uncertainties": agent_output.get("uncertainties", []),
            },
        }


def main():
    parser = argparse.ArgumentParser(description="DressMe Autonomous Inference Pipeline (Hugging Face API)")
    parser.add_argument("--image", type=str, default=None, help="Path to local image or image URL")
    parser.add_argument("--price", type=float, default=35.0, help="Item price (default: 35.0)")
    parser.add_argument("--budget", type=float, default=50.0, help="User budget (default: 50.0)")
    parser.add_argument("--prompt", type=str, default="Should I buy this black t-shirt for casual weekend wear?", help="User query")
    parser.add_argument("--hf-token", type=str, default=None, help="Hugging Face API token (or set in .env)")
    parser.add_argument("--model", type=str, default=None, help="HF model ID (default: Qwen/Qwen2.5-72B-Instruct)")
    parser.add_argument("--skip-llm", action="store_true", help="Run only vision + deterministic ML tools without querying LLM")
    args = parser.parse_args()

    # Default sample image if none provided
    img = args.image
    if not img:
        sample_local = PROJECT_DIR / "data" / "sample_camel_blazer.jpg"
        if sample_local.exists():
            img = str(sample_local)
        else:
            img = "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQuFucmwpSu49mBKKfTp4NJHMMZsKI9YuuM16xSn2Fmt15lRUCez5qvMy0&s=10"

    print("================================================================")
    print("      👗 DRESSME SHOPPER AGENT — AUTONOMOUS INFERENCE")
    print("================================================================")
    print(f"Image:  {img}")
    print(f"Price:  ${args.price:.2f}")
    print(f"Budget: ${args.budget:.2f}")
    print(f"Prompt: \"{args.prompt}\"")
    print("----------------------------------------------------------------")

    engine = DressMeInferenceEngine(
        skip_llm=args.skip_llm,
        hf_token=args.hf_token,
        model_id=args.model,
    )
    result = engine.evaluate(
        image_path=img,
        price=args.price,
        budget=args.budget,
        user_prompt=args.prompt,
    )

    print("\n[RESULT JSON]:")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
