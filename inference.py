"""DressMe Shopping Assistant — Autonomous Inference Pipeline.

Integrates:
- Supabase Live Wardrobe (with automatic local dataset fallback)
- YOLO11 Segmentation & CIEDE2000 Dominant Color Vision
- Teammate Redundancy Engine (purchase-redundancy-ai FeatureSet)
- Teammate Outfit Recommendation Engine (bo4 outfit_engine)
- Teammate Wardrobe Gap Analysis (bo3 coverage & XGBoost ranker)
- XGBoost Decision Classifier
- OpenAI GPT-4 Stylist Interpretation
"""

import os
import sys
import json
import re
import time
import argparse
import tempfile
import urllib.request
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

# Set UTF-8 encoding for standard output if running in Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = CURRENT_DIR / "smart_purchasing" if (CURRENT_DIR / "smart_purchasing").exists() else CURRENT_DIR
for p in [CURRENT_DIR, PROJECT_DIR, CURRENT_DIR.parent]:
    if p.exists() and str(p) not in sys.path:
        sys.path.insert(0, str(p))


def load_dotenv(env_path: Optional[Path] = None):
    """Loads environment variables from .env files."""
    candidates = [
        Path(".env"),
        CURRENT_DIR / ".env",
        PROJECT_DIR / ".env",
        CURRENT_DIR.parent / ".env",
    ]
    for c in candidates:
        if c.exists():
            try:
                with open(c, "r", encoding="utf-8") as f:
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


# Automatically load environment variables
load_dotenv()

# Domain schemas and tools
from schemas import CandidateItem, Garment
from wardrobe_loader import load_user_wardrobe, load_wardrobe_from_csv
from tools import (
    find_similar_items,
    check_outfit_compatibility,
    analyze_wardrobe_gaps,
    calculate_purchase_value,
    analyze_item,
)
from ml_model import predict_purchase_ml

DEFAULT_LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o")

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


class DressMeInferenceEngine:
    """Manages model loading, Supabase wardrobe synchronization, and end-to-end evaluation."""

    def __init__(
        self,
        skip_llm: bool = False,
        openai_key: Optional[str] = None,
        model_id: Optional[str] = None,
        user_id: Optional[str] = None,
        wardrobe: Optional[List[Garment]] = None,
    ):
        self.skip_llm = skip_llm
        self.openai_key = openai_key or os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY")
        self.model_id = model_id or DEFAULT_LLM_MODEL
        self.user_id = user_id or os.getenv("WARDROBE_USER_ID")
        self.wardrobe: List[Garment] = wardrobe if wardrobe is not None else []
        self.openai_client = None

        if wardrobe is None:
            self._load_wardrobe()
        if not self.skip_llm:
            self._init_llm_client()

    def _load_wardrobe(self):
        """Loads wardrobe from Supabase with graceful fallback."""
        self.wardrobe = load_user_wardrobe(user_id=self.user_id)

    def _init_llm_client(self):
        """Initializes OpenAI client for personal styling and decision explanation."""
        if not self.openai_key:
            print("[LLM Notice] No OPENAI_API_KEY found in .env; running in deterministic evaluation mode.")
            return

        try:
            from openai import OpenAI
            self.openai_client = OpenAI(api_key=self.openai_key)
        except Exception as e:
            self.openai_client = None

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

    def _interpret_with_gpt(self, summary_payload: Dict[str, Any]) -> Optional[str]:
        """Interprets raw agent JSON using GPT-4 into a styled, user-friendly recommendation."""
        if not self.openai_client:
            return None

        system_prompt = (
            "You are DressMe Shopping Assistant, an expert personal stylist and wardrobe consultant. "
            "Your role is to interpret raw technical decision data (vision analysis, redundancy scores, "
            "outfit combinations, wardrobe gaps, and budget math) into an elegant, clear, and actionable advice "
            "for the shopper. Do NOT use emojis. Maintain a chic, professional, and clear tone."
        )

        user_content = (
            f"User Question: \"{summary_payload['user_query']}\"\n\n"
            f"Here is the technical evaluation data from the agent tools:\n"
            f"{json.dumps(summary_payload, indent=2)}\n\n"
            f"Please write a structured styling recommendation with:\n"
            f"1. **The Verdict**: Clear BUY / CONSIDER / DON'T BUY with confidence rating.\n"
            f"2. **Why It Works (or Doesn't)**: Plain-language summary of redundancy, wardrobe gap, and budget.\n"
            f"3. **Ready-to-Wear Outfits**: Explicit combinations using existing pieces in their closet.\n"
            f"4. **Stylist's Final Advice**: Practical tips on wearing and versatility.\n\n"
            f"Remember: Do not include emojis."
        )

        try:
            response = self.openai_client.chat.completions.create(
                model=self.model_id,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.7,
                max_tokens=450,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"[LLM Warning] OpenAI interpretation failed: {e}")
            return None

    def evaluate(
        self,
        image_path: str,
        price: float,
        budget: float,
        user_prompt: str = "Should I buy this?",
        wardrobe: Optional[List[Garment]] = None,
    ) -> Dict[str, Any]:
        """Runs end-to-end evaluation pipeline."""
        active_wardrobe = wardrobe if wardrobe is not None else self.wardrobe
        # 1. Download image if URL
        local_image = str(image_path)
        if local_image.startswith("http://") or local_image.startswith("https://"):
            local_image = os.path.join(tempfile.gettempdir(), "downloaded_garment.jpg")
            req = urllib.request.Request(image_path, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req) as resp, open(local_image, "wb") as f:
                f.write(resp.read())

        # 2. Computer Vision Analysis (YOLO segmentation + CIEDE2000)
        cand = CandidateItem(name=user_prompt, category="unknown", image_path=local_image, price=price, budget=budget)
        vision_data = analyze_item(cand)

        category = vision_data["category"]
        color = vision_data["color"]
        occasion, styles = self.infer_occasion_and_style(user_prompt, category)

        cand.category = category
        cand.color = color
        cand.occasions = [occasion]
        cand.style = styles
        cand.seasons = ["all"] if occasion == "work" else ["autumn"]

        # 3. Tool Analysis
        sims = find_similar_items(cand, active_wardrobe, top_k=3)
        top_sim = sims[0].similarity_score if sims else 0.0
        redundancy_pct = round(top_sim * 100.0, 1)

        compat_data = check_outfit_compatibility(cand, active_wardrobe, target_occasion=occasion)
        comp_count = compat_data["compatible_count"]
        avg_score = compat_data["average_score"]

        matching_outfits = []
        paired_item_ids = []
        for combo in compat_data.get("combinations", [])[:3]:
            paired_summary = [
                {"item_id": g.id, "name": g.name, "category": g.category, "color": g.color}
                for g in combo.paired_garments
            ]
            for g in combo.paired_garments:
                if g.id not in paired_item_ids:
                    paired_item_ids.append(g.id)
            matching_outfits.append({
                "outfit_id": combo.outfit_id,
                "description": combo.description,
                "compatibility_score": round(combo.compatibility_score, 1),
                "paired_items": paired_summary,
            })

        gap_res = analyze_wardrobe_gaps(cand, active_wardrobe)
        gap_score = gap_res.gap_fill_score

        # 4. XGBoost Model & Deterministic Evaluation
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

        # 5. Build structured payload
        payload = {
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
                "xgboost_confidence": round(ml_res["confidence"], 3),
                "deterministic_score": round(val_res.overall_score, 1),
                "budget_penalty": penalty,
            },
            "agent_verdict": {
                "decision": val_res.decision.value,
                "score": round(val_res.overall_score, 1),
                "matching_item_ids": paired_item_ids,
                "reasons": [
                    f"Compatible with {comp_count} outfits in existing wardrobe.",
                    f"XGBoost classification: {ml_res['ml_decision']} (confidence {ml_res['confidence']*100:.1f}%).",
                    f"Wardrobe gap score: {gap_score:.1f}/100.",
                    f"Redundancy risk: {redundancy_pct}%.",
                ],
                "uncertainties": [],
            },
        }

        # 6. Generate GPT-4 styling interpretation if enabled
        if not self.skip_llm and self.openai_client:
            interpretation = self._interpret_with_gpt(payload)
            if interpretation:
                payload["stylist_interpretation"] = interpretation

        return payload


def main():
    parser = argparse.ArgumentParser(description="DressMe Autonomous Shopping Assistant")
    parser.add_argument("--image", type=str, default=None, help="URL or path to candidate clothing image")
    parser.add_argument("--price", type=float, default=35.0, help="Item price in USD")
    parser.add_argument("--budget", type=float, default=50.0, help="User budget in USD")
    parser.add_argument("--prompt", type=str, default="Should I buy this for casual weekend wear?", help="User's natural language question")
    parser.add_argument("--user-id", type=str, default=None, help="Supabase user ID")
    parser.add_argument("--openai-key", type=str, default=None, help="OpenAI API key")
    parser.add_argument("--model", type=str, default=DEFAULT_LLM_MODEL, help="LLM model ID")
    parser.add_argument("--skip-llm", action="store_true", help="Skip LLM interpretation and return pure deterministic tool output")
    parser.add_argument("--json", action="store_true", help="Print raw machine-readable JSON evaluation")
    args = parser.parse_args()

    img = args.image
    if not img:
        sample_local = PROJECT_DIR / "data" / "sample_camel_blazer.jpg"
        if sample_local.exists():
            img = str(sample_local)
        else:
            img = "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQuFucmwpSu49mBKKfTp4NJHMMZsKI9YuuM16xSn2Fmt15lRUCez5qvMy0&s=10"

    engine = DressMeInferenceEngine(
        skip_llm=args.skip_llm,
        openai_key=args.openai_key,
        model_id=args.model,
        user_id=args.user_id,
    )
    result = engine.evaluate(
        image_path=img,
        price=args.price,
        budget=args.budget,
        user_prompt=args.prompt,
    )

    if args.json:
        print(json.dumps(result, indent=2))
    elif "stylist_interpretation" in result:
        print("================================================================")
        print("          PERSONAL STYLIST RECOMMENDATION")
        print("================================================================")
        print(result["stylist_interpretation"])
    else:
        print("================================================================")
        print("          EVALUATION SUMMARY")
        print("================================================================")
        print(f"Decision: {result['agent_verdict']['decision']} (Score: {result['agent_verdict']['score']}/100)")
        print(f"XGBoost Prediction: {result['tool_evidence']['xgboost_prediction']} (Confidence: {result['tool_evidence']['xgboost_confidence']*100:.1f}%)")
        print("Reasons:")
        for r in result['agent_verdict']['reasons']:
            print(f"- {r}")


if __name__ == "__main__":
    main()
