"""Tools the gap agent can call; each is a plain function usable without the LLM."""

import math
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Any

from xgboost_ranker import rank_gap_candidates

from .coverage import ALL_YEAR, GOALS, compute_coverage, get_requirement
from .learning import DEMO_MODEL_PATH, active_model_path, model_metadata
from .memory import AgentMemory
from .profile_source import load_profile   # re-exported: api.py and the Streamlit pages import it from here
from .wardrobe_source import load_wardrobe, source_info

BACKEND_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BACKEND_DIR / "data"


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
                "closest_owned_item_id": wardrobe[best]["id"],
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
    in_season = list(wardrobe) if season == ALL_YEAR else [item for item in wardrobe if season in item.get("seasons", [])]
    department = profile.get("department")
    requirements = [get_requirement(goal_id, c["candidate_id"], department) for c in candidates]
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
                "closest_owned_item_id": closest["closest_owned_item_id"],
                "redundancy_method": closest["method"],
                "pairable_owned_items": pairable,
            }
        )
    return scored


def _priority(rank: int, total: int) -> str:
    third = math.ceil(total / 3)
    return "high" if rank <= third else "medium" if rank <= 2 * third else "low"


class GapAgentTools:
    """Binds the tools to one user and conversation."""

    def __init__(self, memory: AgentMemory, user_id: str, conversation_id: str | None = None) -> None:
        self.memory = memory
        self.user_id = user_id
        self.conversation_id = conversation_id
        self.last_ranking: dict[str, Any] | None = None
        self.shown_items: list[dict[str, Any]] = []   # owned items the agent chose to show as photo cards

    def get_wardrobe(self) -> dict[str, Any]:
        wardrobe, profile = load_wardrobe(self.user_id), load_profile(self.user_id)
        return {
            "profile": profile,
            "wardrobe_source": source_info(self.user_id),
            "item_count": len(wardrobe),
            "items_by_category": dict(Counter(item["category"] for item in wardrobe)),
            "items": [
                {"id": item["id"], "name": item["name"], "category": item["category"],
                 "subcategory": item.get("subcategory"), "colors": item.get("colors", []), "seasons": item["seasons"]}
                for item in wardrobe
            ],
        }

    def compute_coverage(self, goal: str) -> dict[str, Any]:
        department = load_profile(self.user_id).get("department")
        return {**compute_coverage(load_wardrobe(self.user_id), goal, department), "department": department,
                "wardrobe_source": source_info(self.user_id)}

    def rank_gaps(self, goal: str) -> dict[str, Any]:
        wardrobe, profile = load_wardrobe(self.user_id), load_profile(self.user_id)
        source = source_info(self.user_id)
        if source["source"] in ("empty", "error"):
            # No pieces to analyse: say so instead of reporting every requirement as a gap.
            return {"goal": goal, "ranked_gaps": [], "covered": [], "wardrobe_source": source,
                    "profile_source": profile.get("profile_source"), "department": profile.get("department"),
                    "note": source["message"]}
        coverage = compute_coverage(wardrobe, goal, profile.get("department"))
        if not coverage["candidates"]:
            return {"goal": goal, "ranked_gaps": [], "covered": coverage["covered"],
                    "wardrobe_source": source, "profile_source": profile.get("profile_source"),
                    "department": profile.get("department"), "not_analysed": coverage["not_analysed"],
                    "note": "Every requirement for this goal is covered."}

        scored = score_candidates(goal, coverage["candidates"], wardrobe, profile)
        model_path = active_model_path(self.user_id)
        ranked = rank_gap_candidates(scored, model_path=model_path)
        for gap in ranked:
            gap["priority"] = _priority(gap["rank"], len(ranked))
            gap["ranking_score"] = round(gap["ranking_score"], 4)

        metadata = model_metadata(self.user_id)
        result = {
            "goal": goal,
            "wardrobe_source": source,
            "profile_source": profile.get("profile_source"),
            "department": profile.get("department"),   # who the suggestions are for: women | men | both | None
            "goal_label": coverage["goal_label"],
            "season": coverage["season"],
            "ranker_model": model_path.name,
            "ranker_trained_on": (
                "synthetic data" if model_path == DEMO_MODEL_PATH
                else f"synthetic data + {metadata['explicit_labels'] if metadata else 'your'} feedback labels"
            ),
            "ranked_gaps": ranked,
            "covered": coverage["covered"],
            "not_analysed": coverage["not_analysed"],   # pieces the scanner cannot see: never reported as gaps
        }
        self.memory.save_gap_analysis(self.user_id, self.conversation_id, goal, result)
        self.last_ranking = result
        return result

    def show_items(self, item_ids: list[str]) -> dict[str, Any]:
        """Queue owned items to be displayed to the user, with their photo, next to the answer."""
        by_id = {item["id"]: item for item in load_wardrobe(self.user_id)}
        shown, unknown = [], []
        for item_id in item_ids:
            item = by_id.get(item_id)
            if item is None:
                unknown.append(item_id)
            elif all(entry["id"] != item_id for entry in self.shown_items) and len(self.shown_items) < MAX_SHOWN_ITEMS:
                self.shown_items.append(
                    {key: item.get(key) for key in ("id", "name", "category", "subcategory", "colors", "image_url")}
                )
                shown.append(item["name"])
        return {"shown": shown, "unknown_ids": unknown}

    def get_past_analyses(self) -> dict[str, Any]:
        return {"past_analyses": self.memory.past_gap_analyses(self.user_id)}

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        handlers = {
            "get_wardrobe": self.get_wardrobe,
            "compute_coverage": self.compute_coverage,
            "rank_gaps": self.rank_gaps,
            "get_past_analyses": self.get_past_analyses,
            "show_items": self.show_items,
        }
        if name not in handlers:
            return {"error": f"Unknown tool {name!r}."}
        try:
            return handlers[name](**arguments)
        except Exception as error:
            return {"error": f"{type(error).__name__}: {error}"}


GOAL_ENUM = list(GOALS)
MAX_SHOWN_ITEMS = 8

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
            "name": "get_past_analyses",
            "description": "Recall this user's previous gap analyses from long-term memory.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "show_items",
            "description": (
                "Display owned wardrobe items to the user as photo cards next to your answer. Call it whenever you "
                "name owned items. Ids come from get_wardrobe, matched_item_ids or closest_owned_item_id. At most 8."
            ),
            "parameters": {
                "type": "object",
                "properties": {"item_ids": {"type": "array", "items": {"type": "string"}}},
                "required": ["item_ids"],
            },
        },
    },
]
