"""Tools the gap agent can call; each is a plain function usable without the LLM."""

import json
import math
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Any

from xgboost_ranker import FEATURES, rank_gap_candidates

from .coverage import GOALS, compute_coverage, get_requirement
from .learning import DEMO_MODEL_PATH, active_model_path, model_metadata, shap_contributions
from .memory import AgentMemory
from .wardrobe_source import load_wardrobe as _load_wardrobe

BACKEND_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BACKEND_DIR / "data"

CATEGORY_LABELS = {
    "top": "a top or shirt",
    "bottom": "trousers, jeans or a skirt",
    "dress": "a dress",
    "outerwear": "a coat or jacket",
    "shoes": "a pair of shoes",
    "accessory": "a bag, hat or accessory",
}
COLOR_LABELS = ["white", "black", "grey", "navy", "blue", "beige", "camel", "brown", "green", "red", "pink", "yellow"]


def load_wardrobe() -> list[dict[str, Any]]:
    return _load_wardrobe()


def load_profile() -> dict[str, Any]:
    return json.loads((DATA_DIR / "sample_profile.json").read_text(encoding="utf-8"))


def item_description(item: dict[str, Any]) -> str:
    color = item["colors"][0] if item.get("colors") else ""
    material = item["materials"][0] if item.get("materials") else ""
    kind = (item.get("subcategory") or item["category"]).replace("_", " ")
    return " ".join(part for part in ("a", color, material, kind) if part)


@lru_cache(maxsize=1)
def _encoder():
    from fashionclip import FashionCLIPEncoder

    return FashionCLIPEncoder(device="cpu")


def fashionclip_available() -> bool:
    try:
        _encoder()
        return True
    except Exception:
        return False


def _lexical_similarity(a: str, b: str) -> float:
    words_a, words_b = set(a.lower().split()) - {"a"}, set(b.lower().split()) - {"a"}
    return len(words_a & words_b) / len(words_a | words_b) if words_a | words_b else 0.0


def redundancy_scores(descriptions: list[str], wardrobe: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Closest owned item per candidate. FashionCLIP cosine is rescaled from [0.5, 0.95] to [0, 1]."""
    owned = [item_description(item) for item in wardrobe]
    if fashionclip_available():
        encoder = _encoder()
        similarities = (encoder.encode_text(descriptions) @ encoder.encode_text(owned).T).tolist()
        method = "fashionclip"
    else:
        similarities = [[_lexical_similarity(d, o) for o in owned] for d in descriptions]
        method = "lexical_fallback"

    results = []
    for row in similarities:
        best = max(range(len(row)), key=row.__getitem__)
        raw = row[best]
        score = min(1.0, max(0.0, (raw - 0.5) / 0.45)) if method == "fashionclip" else raw
        results.append(
            {
                "redundancy_score": round(score, 4),
                "closest_owned_item": wardrobe[best]["name"],
                "raw_similarity": round(raw, 4),
                "method": method,
            }
        )
    return results


def score_candidates(
    goal_id: str, candidates: list[dict[str, Any]], wardrobe: list[dict[str, Any]], profile: dict[str, Any]
) -> list[dict[str, Any]]:
    """Fill the six ranker features for each uncovered requirement."""
    season = GOALS[goal_id]["season"]
    in_season = [item for item in wardrobe if season in item.get("seasons", [])]
    requirements = [get_requirement(goal_id, c["candidate_id"]) for c in candidates]
    redundancy = redundancy_scores([r["description"] for r in requirements], wardrobe)
    preferred_styles = set(profile.get("preferred_styles", []))
    frequencies = profile.get("occasion_frequency", {})

    scored = []
    for candidate, requirement, closest in zip(candidates, requirements, redundancy):
        pairable = sum(1 for item in in_season if item["category"] in requirement["pairs_with"])
        style_tags = set(requirement.get("style_tags", []))
        style_overlap = len(style_tags & preferred_styles) / len(style_tags) if style_tags else 0.5
        scored.append(
            {
                **candidate,
                "suggested_item": requirement["description"],
                "coverage_deficit": candidate["coverage_deficit"],
                "use_frequency": float(frequencies.get(requirement["occasion"], 0.5)),
                "season_relevance": requirement["season_relevance"],
                "outfit_gain": round(min(1.0, pairable / 8), 4),
                "preference_match": round(0.4 + 0.6 * style_overlap, 4),
                "redundancy_score": closest["redundancy_score"],
                "closest_owned_item": closest["closest_owned_item"],
                "redundancy_method": closest["method"],
                "pairable_owned_items": pairable,
            }
        )
    return scored


def _priority(rank: int, total: int) -> str:
    third = math.ceil(total / 3)
    return "high" if rank <= third else "medium" if rank <= 2 * third else "low"


class GapAgentTools:
    """Binds the tools to one user, conversation and optional uploaded image."""

    def __init__(self, memory: AgentMemory, user_id: str, conversation_id: str | None = None) -> None:
        self.memory = memory
        self.user_id = user_id
        self.conversation_id = conversation_id
        self.uploaded_image: Path | None = None
        self.last_ranking: dict[str, Any] | None = None

    def get_wardrobe(self) -> dict[str, Any]:
        wardrobe, profile = load_wardrobe(), load_profile()
        return {
            "profile": profile,
            "item_count": len(wardrobe),
            "items_by_category": dict(Counter(item["category"] for item in wardrobe)),
            "items": [
                {"name": item["name"], "category": item["category"], "seasons": item["seasons"]}
                for item in wardrobe
            ],
        }

    def compute_coverage(self, goal: str) -> dict[str, Any]:
        return compute_coverage(load_wardrobe(), goal)

    def rank_gaps(self, goal: str) -> dict[str, Any]:
        wardrobe, profile = load_wardrobe(), load_profile()
        coverage = compute_coverage(wardrobe, goal)
        if not coverage["candidates"]:
            return {"goal": goal, "ranked_gaps": [], "covered": coverage["covered"],
                    "note": "Every requirement for this goal is covered."}

        scored = score_candidates(goal, coverage["candidates"], wardrobe, profile)
        model_path = active_model_path()
        ranked = rank_gap_candidates(scored, model_path=model_path)
        explanations = shap_contributions([[gap[name] for name in FEATURES] for gap in ranked], model_path)
        for gap, explanation in zip(ranked, explanations):
            gap["priority"] = _priority(gap["rank"], len(ranked))
            gap["ranking_score"] = round(gap["ranking_score"], 4)
            gap["shap"] = explanation

        metadata = model_metadata()
        result = {
            "goal": goal,
            "goal_label": coverage["goal_label"],
            "season": coverage["season"],
            "ranker_model": model_path.name,
            "ranker_trained_on": (
                "synthetic data" if model_path == DEMO_MODEL_PATH
                else f"synthetic data + {metadata['explicit_labels'] if metadata else 'your'} feedback labels"
            ),
            "ranked_gaps": ranked,
            "covered": coverage["covered"],
        }
        self.memory.save_gap_analysis(self.user_id, self.conversation_id, goal, result)
        self.last_ranking = result
        return result

    def analyze_uploaded_garment(self) -> dict[str, Any]:
        if self.uploaded_image is None:
            return {"error": "No image has been uploaded. Ask the user to upload one."}
        if not fashionclip_available():
            return {"error": "FashionCLIP weights are missing. Run python backend/download_fashionclip.py."}

        encoder = _encoder()
        image = encoder.encode_images([self.uploaded_image])
        categories = list(CATEGORY_LABELS)
        category_sims = (image @ encoder.encode_text([f"a photo of {CATEGORY_LABELS[c]}" for c in categories]).T)[0]
        color_sims = (image @ encoder.encode_text([f"a photo of a {c} garment" for c in COLOR_LABELS]).T)[0]

        wardrobe = load_wardrobe()
        owned_sims = (image @ encoder.encode_text([item_description(i) for i in wardrobe]).T)[0]
        closest = owned_sims.argsort(descending=True)[:3].tolist()
        return {
            "predicted_category": categories[int(category_sims.argmax())],
            "predicted_color": COLOR_LABELS[int(color_sims.argmax())],
            "closest_owned_items": [
                {"name": wardrobe[i]["name"], "similarity": round(owned_sims[i].item(), 4)} for i in closest
            ],
            "note": "Zero-shot FashionCLIP predictions; similarities are not probabilities.",
        }

    def get_past_analyses(self) -> dict[str, Any]:
        return {"past_analyses": self.memory.past_gap_analyses(self.user_id)}

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        handlers = {
            "get_wardrobe": self.get_wardrobe,
            "compute_coverage": self.compute_coverage,
            "rank_gaps": self.rank_gaps,
            "analyze_uploaded_garment": self.analyze_uploaded_garment,
            "get_past_analyses": self.get_past_analyses,
        }
        if name not in handlers:
            return {"error": f"Unknown tool {name!r}."}
        try:
            return handlers[name](**arguments)
        except Exception as error:
            return {"error": f"{type(error).__name__}: {error}"}


GOAL_ENUM = list(GOALS)

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_wardrobe",
            "description": "Return the user's style profile and a summary of every owned wardrobe item.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compute_coverage",
            "description": "Check which requirements of a wardrobe goal are covered or missing. Rules decide whether a gap exists.",
            "parameters": {
                "type": "object",
                "properties": {"goal": {"type": "string", "enum": GOAL_ENUM}},
                "required": ["goal"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rank_gaps",
            "description": (
                "Compute coverage for a goal, score each missing requirement (coverage deficit, use frequency, "
                "season relevance, outfit gain, preference match, FashionCLIP redundancy) and order them with the "
                "XGBoost learning-to-rank model. Saves the analysis to memory."
            ),
            "parameters": {
                "type": "object",
                "properties": {"goal": {"type": "string", "enum": GOAL_ENUM}},
                "required": ["goal"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_uploaded_garment",
            "description": "Analyse the garment photo the user uploaded with FashionCLIP: category, colour and closest owned items.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_past_analyses",
            "description": "Recall this user's previous gap analyses from long-term memory.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]
