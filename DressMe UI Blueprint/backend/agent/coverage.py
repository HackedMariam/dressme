"""BO3 coverage rules: decide which gaps exist before any ranking happens."""

from typing import Any, Mapping, Sequence

# Each requirement lists the owned items that satisfy it (`match`), how many are
# needed, and priors used later as ranker features. `season_relevance` is a
# domain prior for the goal's season in a Tunisian climate.
GOALS: dict[str, dict[str, Any]] = {
    "winter_work": {
        "label": "Winter work days",
        "season": "winter",
        "requirements": [
            {
                "id": "warm_coat",
                "name": "Warm outerwear coat",
                "description": "a warm wool coat",
                "match": [{"category": "outerwear", "subcategories": ["coat", "wool_coat", "parka", "puffer"]}],
                "min_count": 1,
                "occasion": "work",
                "season_relevance": 0.95,
                "style_tags": ["classic", "minimal"],
                "pairs_with": ["top", "bottom", "dress"],
            },
            {
                "id": "rain_protection",
                "name": "Rain-protective layer",
                "description": "a waterproof rain jacket",
                "match": [{"category": "outerwear", "subcategories": ["rain_jacket", "trench"]}],
                "min_count": 1,
                "occasion": "work",
                "season_relevance": 0.85,
                "style_tags": ["classic", "practical"],
                "pairs_with": ["top", "bottom"],
            },
            {
                "id": "closed_work_shoes",
                "name": "Closed work shoes",
                "description": "black leather loafers",
                "match": [{"category": "shoes", "subcategories": ["boots", "loafers", "derbies", "oxfords", "ankle_boots"]}],
                "min_count": 1,
                "occasion": "work",
                "season_relevance": 0.9,
                "style_tags": ["classic"],
                "pairs_with": ["bottom", "dress"],
            },
            {
                "id": "work_trousers",
                "name": "Work trousers",
                "description": "tailored wool trousers",
                "match": [{"category": "bottom", "subcategories": ["trousers", "chinos"]}],
                "min_count": 2,
                "occasion": "work",
                "season_relevance": 0.75,
                "style_tags": ["classic"],
                "pairs_with": ["top", "outerwear", "shoes"],
            },
            {
                "id": "layering_knit",
                "name": "Layering knit",
                "description": "a wool knit sweater",
                "match": [{"category": "top", "subcategories": ["sweater", "cardigan", "turtleneck"]}],
                "min_count": 2,
                "occasion": "work",
                "season_relevance": 0.8,
                "style_tags": ["minimal", "classic"],
                "pairs_with": ["bottom", "outerwear"],
            },
            {
                "id": "work_shirts",
                "name": "Work shirts",
                "description": "a white button-down shirt",
                "match": [{"category": "top", "subcategories": ["shirt", "blouse"]}],
                "min_count": 3,
                "occasion": "work",
                "season_relevance": 0.6,
                "style_tags": ["classic"],
                "pairs_with": ["bottom", "outerwear"],
            },
        ],
    },
    "summer_casual": {
        "label": "Hot summer days",
        "season": "summer",
        "requirements": [
            {
                "id": "breathable_tops",
                "name": "Breathable tops",
                "description": "a breathable linen top",
                "match": [{"category": "top", "subcategories": ["t-shirt", "linen_shirt", "tank_top", "blouse"]}],
                "min_count": 4,
                "occasion": "casual",
                "season_relevance": 0.95,
                "style_tags": ["minimal", "relaxed"],
                "pairs_with": ["bottom"],
            },
            {
                "id": "light_bottoms",
                "name": "Light bottoms",
                "description": "light linen trousers",
                "match": [{"category": "bottom", "subcategories": ["shorts", "linen_trousers", "skirt"]}],
                "min_count": 3,
                "occasion": "casual",
                "season_relevance": 0.9,
                "style_tags": ["relaxed", "classic"],
                "pairs_with": ["top", "shoes"],
            },
            {
                "id": "summer_shoes",
                "name": "Open summer shoes",
                "description": "leather sandals",
                "match": [{"category": "shoes", "subcategories": ["sandals", "espadrilles", "slides"]}],
                "min_count": 1,
                "occasion": "casual",
                "season_relevance": 0.85,
                "style_tags": ["classic"],
                "pairs_with": ["bottom", "dress"],
            },
            {
                "id": "sun_hat",
                "name": "Sun protection hat",
                "description": "a straw sun hat",
                "match": [{"category": "accessory", "subcategories": ["hat", "cap"]}],
                "min_count": 1,
                "occasion": "outdoor",
                "season_relevance": 0.8,
                "style_tags": ["classic", "practical"],
                "pairs_with": ["top", "dress"],
            },
            {
                "id": "swimwear",
                "name": "Swimwear",
                "description": "a swimsuit",
                "match": [{"category": "other", "subcategories": ["swimwear"]}],
                "min_count": 1,
                "occasion": "outdoor",
                "season_relevance": 0.75,
                "style_tags": ["minimal"],
                "pairs_with": ["accessory"],
                "check_season": False,
            },
        ],
    },
    "formal_event": {
        "label": "Wedding or formal celebration",
        "season": "summer",
        "requirements": [
            {
                "id": "formal_outfit",
                "name": "Formal outfit (evening dress or suit)",
                "description": "an elegant evening dress",
                "match": [
                    {"category": "dress", "subcategories": ["evening_dress", "cocktail_dress"]},
                    {"category": "outerwear", "subcategories": ["suit_jacket"]},
                ],
                "min_count": 1,
                "occasion": "formal",
                "season_relevance": 0.8,
                "style_tags": ["classic", "elegant"],
                "pairs_with": ["shoes", "accessory"],
                "check_season": False,
            },
            {
                "id": "formal_shoes",
                "name": "Formal shoes",
                "description": "elegant heeled shoes",
                "match": [{"category": "shoes", "subcategories": ["heels", "pumps", "oxfords", "derbies"]}],
                "min_count": 1,
                "occasion": "formal",
                "season_relevance": 0.7,
                "style_tags": ["classic", "elegant"],
                "pairs_with": ["dress", "bottom"],
                "check_season": False,
            },
            {
                "id": "evening_accessory",
                "name": "Evening bag or accessory",
                "description": "a small evening clutch bag",
                "match": [{"category": "accessory", "subcategories": ["clutch", "evening_bag", "tie", "jewelry"]}],
                "min_count": 1,
                "occasion": "formal",
                "season_relevance": 0.5,
                "style_tags": ["elegant"],
                "pairs_with": ["dress", "outerwear"],
                "check_season": False,
            },
            {
                "id": "evening_layer",
                "name": "Light evening layer",
                "description": "a tailored blazer",
                "match": [{"category": "outerwear", "subcategories": ["blazer", "shawl", "suit_jacket"]}],
                "min_count": 1,
                "occasion": "smart_casual",
                "season_relevance": 0.55,
                "style_tags": ["classic"],
                "pairs_with": ["dress", "top", "bottom"],
                "check_season": False,
            },
        ],
    },
}


def _matches(item: Mapping[str, Any], requirement: Mapping[str, Any], season: str) -> bool:
    if requirement.get("check_season", True) and season not in item.get("seasons", []):
        return False
    return any(
        item.get("category") == condition["category"]
        and (
            not condition.get("subcategories")
            or item.get("subcategory") in condition["subcategories"]
        )
        for condition in requirement["match"]
    )


def compute_coverage(wardrobe: Sequence[Mapping[str, Any]], goal_id: str) -> dict[str, Any]:
    """Compare the wardrobe with a goal's requirements and return uncovered needs."""
    if goal_id not in GOALS:
        raise ValueError(f"Unknown goal {goal_id!r}. Choose one of: {', '.join(GOALS)}.")
    goal = GOALS[goal_id]
    season = goal["season"]

    covered, candidates = [], []
    for requirement in goal["requirements"]:
        matched = [item for item in wardrobe if _matches(item, requirement, season)]
        required = requirement["min_count"]
        deficit = max(0, required - len(matched)) / required
        entry = {
            "candidate_id": requirement["id"],
            "name": requirement["name"],
            "owned_count": len(matched),
            "required_count": required,
            "coverage_deficit": round(deficit, 4),
            "matched_items": [item["name"] for item in matched],
        }
        (candidates if deficit > 0 else covered).append(entry)

    return {
        "goal": goal_id,
        "goal_label": goal["label"],
        "season": season,
        "covered": covered,
        "candidates": candidates,
    }


def get_requirement(goal_id: str, requirement_id: str) -> dict[str, Any]:
    for requirement in GOALS[goal_id]["requirements"]:
        if requirement["id"] == requirement_id:
            return requirement
    raise KeyError(requirement_id)
