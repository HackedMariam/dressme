"""DressMe Shopping Assistant — Autonomous Inference Pipeline.

Integrates:
- Supabase Live Wardrobe (with automatic local dataset fallback)
- YOLO11 Segmentation & CIEDE2000 Dominant Color Vision
- Teammate Redundancy Engine (purchase-redundancy-ai FeatureSet)
- Teammate Outfit Recommendation Engine (bo4 outfit_engine)
- Teammate Wardrobe Gap Analysis (bo3 coverage & XGBoost ranker)
- XGBoost Decision Classifier
- Fine-tuned Qwen decision agent (Hugging Face, tool-calling) - see decision_agent.py
- OpenAI GPT-4 Stylist Interpretation (it only rewrites Qwen's JSON verdict)
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
from types import SimpleNamespace
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
    PURCHASE_TOOLS_SCHEMA,
)
from ml_model import predict_purchase_ml
from decision_agent import PurchaseToolbox, QwenBackend, run_decision_agent

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
        use_qwen: Optional[bool] = None,
    ):
        self.skip_llm = skip_llm          # skips the GPT stylist interpretation only
        self.openai_key = openai_key or os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY")
        self.model_id = model_id or DEFAULT_LLM_MODEL
        self.user_id = user_id or os.getenv("WARDROBE_USER_ID")
        self.wardrobe: List[Garment] = wardrobe if wardrobe is not None else []
        self.openai_client = None
        # The decision agent: fine-tuned Qwen on Hugging Face. Unavailable (no HF_TOKEN, no model) -> deterministic evaluation.
        self.qwen = None if use_qwen is False else QwenBackend()

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

    # The sections of the stylist's answer, in the order the UI shows them. The UI draws each one in its own zone and
    # writes the label itself (in bold), so the model returns plain text per section, with no markdown and no labels.
    SECTION_KEYS = ("verdict", "why_it_works", "final_advice")
    SECTION_TITLES = {"verdict": "Our Answer", "why_it_works": "Why", "final_advice": "Tip"}

    @classmethod
    def _clean_section(cls, value: Any) -> List[str]:
        """A section as a list of short plain-text lines (the model may answer with a string or a list)."""
        if isinstance(value, str):
            value = [part for part in re.split(r"\n+", value)]
        if not isinstance(value, list):
            return []
        lines = []
        for entry in value:
            text = re.sub(r"[*_`#]+", "", str(entry))
            text = re.sub(r"^\s*(?:[-\u2022]|\d+[.)])\s*", "", text).strip()
            if text:
                lines.append(text)
        return lines

    def _interpret_sections(self, summary_payload: Dict[str, Any]) -> Optional[Dict[str, List[str]]]:
        """Asks the LLM for the styling recommendation as four separate sections (JSON), or None if unavailable."""
        if not self.openai_client:
            return None

        system_prompt = (
            "You are DressMe Shopping Assistant, a personal stylist who helps a shopper decide in seconds. "
            "Write simply, like a trusted friend with great taste: short sentences, no jargon (never mention "
            "XGBoost, scores or model names; never write the words redundancy, risk or score: say \"you already own...\" instead), no emojis, no markdown, no asterisks, no section titles inside the "
            "text (the app adds the titles). Be convincing and honest: take a clear position, back every claim "
            "with a concrete fact from the data (a number, or the name of a piece the shopper owns), and never "
            "invent facts that are not in the data. Write prices as plain numbers, without currency symbols. The decision in agent_verdict was made by the purchase "
            "decision agent: explain it and never change or contradict it."
        )
        user_content = (
            f"The shopper asks: \"{summary_payload['user_query']}\"\n\n"
            f"What the tools found (the item is shown in 'candidate_item', its closet matches in "
            f"'tool_evidence'):\n{json.dumps(summary_payload, indent=2)}\n\n"
            "Answer with ONLY a JSON object with exactly these keys, each a list of short plain-text strings:\n"
            '- "verdict": ONE string, 20 words at most. Start with "Yes, buy it:", "Think twice:" or "Skip it:" '
            "(matching agent_verdict.decision BUY, CONSIDER or SKIP), then the single strongest reason.\n"
            '- "why_it_works": exactly 3 strings, one short sentence each, each with a concrete fact: how many '
            'outfits it makes with what they already own and the names of one or two of those pieces, whether it '
            "fills a gap or duplicates something they own (name the closest piece), and the price "
            "(cost_per_outfit, within_budget when a price is given).\n"
            '- "final_advice": 1 or 2 strings: one practical tip on how to wear it, and, if the decision is not '
            "BUY, what to check before paying."
        )
        try:
            response = self.openai_client.chat.completions.create(
                model=self.model_id,
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_content}],
                temperature=0.5,
                max_tokens=600,
                response_format={"type": "json_object"},
            )
            data = json.loads(response.choices[0].message.content or "{}")
        except Exception as e:
            print(f"[LLM Warning] OpenAI interpretation failed: {e}")
            return None
        sections = {key: self._clean_section(data.get(key)) for key in self.SECTION_KEYS}
        return sections if any(sections.values()) else None

    @classmethod
    def _sections_to_text(cls, sections: Dict[str, List[str]]) -> str:
        """Plain-text version of the sections (command line output, older clients)."""
        blocks = []
        for key in cls.SECTION_KEYS:
            if sections.get(key):
                blocks.append(cls.SECTION_TITLES[key] + "\n" + "\n".join(f"- {line}" for line in sections[key]))
        return "\n\n".join(blocks)

    def _interpret_with_gpt(self, summary_payload: Dict[str, Any]) -> Optional[str]:
        """The styling recommendation as plain text (kept for the command line and older callers)."""
        sections = self._interpret_sections(summary_payload)
        return self._sections_to_text(sections) if sections else None

    def evaluate(
        self,
        image_path: str,
        price: float,
        budget: float,
        user_prompt: str = "Should I buy this?",
        wardrobe: Optional[List[Garment]] = None,
        detected: Optional[Garment] = None,
        interpret: bool = True,
    ) -> Dict[str, Any]:
        """Runs end-to-end evaluation pipeline.

        `detected` is the candidate as recognised by the app's main pipeline (detector + LLM, the one that classifies
        the closet): when given, its category, colour, style, seasons and occasions are used as they are instead of
        this engine's own, less accurate, vision step.
        """
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
        if detected is not None:
            category, color = detected.category, detected.color
            occasion, styles = self.infer_occasion_and_style(user_prompt, category)
            if not any(re.search(r"\b" + kw + r"\b", user_prompt.lower()) for kw in OCCASION_KEYWORDS):
                occasion = detected.occasions[0] if detected.occasions else occasion   # the prompt names no occasion
                styles = list(detected.style) or styles
            cand.name = detected.name or user_prompt
            cand.seasons = list(detected.seasons) or (["all"] if occasion == "work" else ["autumn"])
        else:
            vision_data = analyze_item(cand)
            category = vision_data["category"]
            color = vision_data["color"]
            occasion, styles = self.infer_occasion_and_style(user_prompt, category)
            cand.seasons = ["all"] if occasion == "work" else ["autumn"]

        cand.category = category
        cand.color = color
        cand.occasions = [occasion]
        cand.style = styles

        # 3. The decision agent (fine-tuned Qwen) drives the purchase tools; the tools are Python functions on the real
        #    wardrobe, so their results are authoritative. If Qwen cannot run, the same tools are run in a fixed order.
        box = PurchaseToolbox(
            candidate=cand, wardrobe=active_wardrobe, price=price, budget=budget, occasion=occasion,
            tools=SimpleNamespace(
                find_similar_items=find_similar_items, check_outfit_compatibility=check_outfit_compatibility,
                analyze_wardrobe_gaps=analyze_wardrobe_gaps, calculate_purchase_value=calculate_purchase_value,
                predict_purchase_ml=predict_purchase_ml))
        qwen_verdict = None
        if self.qwen is not None and self.qwen.available:
            qwen_verdict = run_decision_agent(box, self.qwen, user_prompt, PURCHASE_TOOLS_SCHEMA)
        box.complete()                       # the page shows every piece of evidence, whatever Qwen asked for

        sims = box.sims
        redundancy_pct = box.redundancy_pct
        compat_data = box.compat()
        comp_count = compat_data["compatible_count"]
        avg_score = compat_data["average_score"]

        matching_outfits = []
        paired_item_ids = box.paired_item_ids
        for combo in compat_data.get("combinations", [])[:3]:
            paired_summary = [
                {"item_id": g.id, "name": g.name, "category": g.category, "color": g.color}
                for g in combo.paired_garments
            ]
            matching_outfits.append({
                "outfit_id": combo.outfit_id,
                "description": combo.description,
                "compatibility_score": round(combo.compatibility_score, 1),
                "paired_items": paired_summary,
            })

        gap_res = box.gap
        gap_score = gap_res.gap_fill_score

        # 4. XGBoost model and deterministic value (computed by the tools above)
        penalty = box.penalty
        ml_res = box.ml
        val_res = box.value

        # 5. Build structured payload
        payload = {
            "status": "success",
            "user_query": user_prompt,
            "candidate_item": {
                "name": detected.name if detected is not None else None,
                "image_source": str(image_path),
                "detected_category": category,
                "detected_color": color,
                "inferred_occasion": occasion,
                "inferred_style": styles,
                "price": price,
                "budget": budget,
                "within_budget": (price <= budget) if (price > 0 and budget > 0) else None,
                "cost_per_outfit": round(price / comp_count, 2) if (price > 0 and comp_count > 0) else None,
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
                "decision_source": "deterministic",
            },
        }
        payload["tool_evidence"]["deterministic_decision"] = val_res.decision.value
        payload["decision_agent"] = {"source": "deterministic", "model": None, "tools_called": []}
        if qwen_verdict:
            verdict = payload["agent_verdict"]
            verdict.update({"decision": qwen_verdict["decision"], "score": qwen_verdict["score"],
                            "matching_item_ids": qwen_verdict["matching_item_ids"] or paired_item_ids,
                            "reasons": qwen_verdict["reasons"] or verdict["reasons"], "decision_source": "qwen-agent"})
            payload["decision_agent"] = {"source": "qwen-agent", "model": self.qwen.label, "tools_called": list(box.called)}

        # 6. Generate GPT-4 styling interpretation if enabled
        # GPT only rewrites the JSON verdict of the decision agent as stylist advice: it decides nothing.
        if interpret and not self.skip_llm and self.openai_client:
            sections = self._interpret_sections(payload)
            if sections:
                payload["stylist_sections"] = sections
                payload["stylist_interpretation"] = self._sections_to_text(sections)

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
