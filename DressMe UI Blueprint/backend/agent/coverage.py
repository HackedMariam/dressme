"""BO3 coverage rules: decide which gaps exist before any ranking happens."""

from typing import Any, Mapping, Sequence

# Each requirement lists the owned items that satisfy it (`match`), how many are
# needed, and priors used later as ranker features. `season_relevance` is a
# domain prior for the goal's season in a Tunisian climate.
#
# A match condition names a `category` and narrows it with `subcategories` and/or `tags`:
# an item satisfies it if its subcategory is listed OR one of its occasion/style tags is
# (e.g. the "sport" occasion or "sporty" style that BO1 attaches to a piece).
# Goals whose season is ALL_YEAR (activities, not weather) never filter pieces by season.
ALL_YEAR = "all-year"

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
    "sport_gym": {
        "label": "Gym and sport",
        "season": ALL_YEAR,
        "requirements": [
            {
                "id": "training_tops",
                "name": "Training tops",
                "description": "a breathable sports t-shirt",
                "match": [{"category": "top", "subcategories": ["sports_top", "tank_top"], "tags": ["sport", "sporty"]}],
                "min_count": 3,
                "occasion": "sport",
                "season_relevance": 0.9,
                "style_tags": ["sporty", "practical"],
                "pairs_with": ["bottom", "shoes"],
            },
            {
                "id": "training_bottoms",
                "name": "Training bottoms",
                "description": "stretch running leggings",
                "match": [{"category": "bottom", "subcategories": ["leggings", "joggers", "shorts"], "tags": ["sport", "sporty"]}],
                "min_count": 2,
                "occasion": "sport",
                "season_relevance": 0.9,
                "style_tags": ["sporty", "practical"],
                "pairs_with": ["top", "shoes"],
            },
            {
                "id": "training_shoes",
                "name": "Training shoes",
                "description": "running sneakers",
                "match": [{"category": "shoes", "subcategories": ["sneakers"], "tags": ["sport", "sporty"]}],
                "min_count": 1,
                "occasion": "sport",
                "season_relevance": 0.95,
                "style_tags": ["sporty", "practical"],
                "pairs_with": ["bottom"],
            },
            {
                "id": "warm_up_layer",
                "name": "Warm-up layer",
                "description": "a lightweight track jacket",
                "match": [
                    {"category": "outerwear", "subcategories": ["track_jacket", "windbreaker", "hoodie", "fleece"], "tags": ["sport", "sporty"]},
                    {"category": "top", "subcategories": ["hoodie"]},
                ],
                "min_count": 1,
                "occasion": "sport",
                "season_relevance": 0.7,
                "style_tags": ["sporty", "relaxed"],
                "pairs_with": ["top", "bottom"],
            },
            {
                "id": "gym_bag",
                "name": "Gym bag",
                "description": "a gym backpack",
                "match": [{"category": "accessory", "subcategories": ["gym_bag", "backpack"]}],
                "min_count": 1,
                "occasion": "sport",
                "season_relevance": 0.6,
                "style_tags": ["practical"],
                "pairs_with": ["top", "bottom"],
            },
            {
                "id": "sport_accessories",
                "name": "Sport accessories",
                "description": "a sports headband",
                "match": [{"category": "accessory", "subcategories": ["headband", "socks", "cap"]}],
                "min_count": 1,
                "occasion": "sport",
                "season_relevance": 0.5,
                "style_tags": ["sporty"],
                "pairs_with": ["top", "bottom"],
            },
        ],
    },
    "hiking_outdoor": {
        "label": "Hiking and outdoors",
        "season": ALL_YEAR,
        "requirements": [
            {
                "id": "hiking_footwear",
                "name": "Hiking footwear",
                "description": "waterproof hiking boots",
                "match": [{"category": "shoes", "subcategories": ["hiking_boots", "boots", "ankle_boots"]}],
                "min_count": 1,
                "occasion": "outdoor",
                "season_relevance": 0.9,
                "style_tags": ["practical"],
                "pairs_with": ["bottom"],
            },
            {
                "id": "weather_shell",
                "name": "Wind and rain shell",
                "description": "a waterproof windbreaker",
                "match": [{"category": "outerwear", "subcategories": ["rain_jacket", "windbreaker", "parka"]}],
                "min_count": 1,
                "occasion": "outdoor",
                "season_relevance": 0.85,
                "style_tags": ["practical"],
                "pairs_with": ["top", "bottom"],
            },
            {
                "id": "trail_bottoms",
                "name": "Trail trousers or leggings",
                "description": "technical hiking trousers",
                "match": [{"category": "bottom", "subcategories": ["trousers", "leggings", "joggers"], "tags": ["outdoor"]}],
                "min_count": 2,
                "occasion": "outdoor",
                "season_relevance": 0.8,
                "style_tags": ["practical", "relaxed"],
                "pairs_with": ["top", "shoes"],
            },
            {
                "id": "mid_layer",
                "name": "Warm mid-layer",
                "description": "a fleece pullover",
                "match": [
                    {"category": "outerwear", "subcategories": ["fleece", "hoodie"]},
                    {"category": "top", "subcategories": ["sweater", "hoodie"]},
                ],
                "min_count": 1,
                "occasion": "outdoor",
                "season_relevance": 0.75,
                "style_tags": ["practical", "relaxed"],
                "pairs_with": ["bottom", "outerwear"],
            },
            {
                "id": "sun_cap",
                "name": "Cap or hat",
                "description": "a breathable cap",
                "match": [{"category": "accessory", "subcategories": ["cap", "hat"]}],
                "min_count": 1,
                "occasion": "outdoor",
                "season_relevance": 0.6,
                "style_tags": ["practical"],
                "pairs_with": ["top"],
            },
            {
                "id": "daypack",
                "name": "Daypack",
                "description": "a hiking backpack",
                "match": [{"category": "accessory", "subcategories": ["backpack"]}],
                "min_count": 1,
                "occasion": "outdoor",
                "season_relevance": 0.7,
                "style_tags": ["practical"],
                "pairs_with": ["top", "bottom"],
            },
        ],
    },
    "beach_pool": {
        "label": "Beach and pool",
        "season": "summer",
        "requirements": [
            {
                "id": "swimwear",
                "name": "Swimwear",
                "description": "a swimsuit",
                "match": [{"category": "other", "subcategories": ["swimwear"]}],
                "min_count": 2,
                "occasion": "beach",
                "season_relevance": 0.95,
                "style_tags": ["minimal"],
                "pairs_with": ["accessory"],
                "check_season": False,
            },
            {
                "id": "cover_up",
                "name": "Beach cover-up",
                "description": "a light linen shirt or beach dress",
                "match": [
                    {"category": "top", "subcategories": ["linen_shirt", "tank_top"]},
                    {"category": "dress", "tags": ["beach", "outdoor"]},
                ],
                "min_count": 1,
                "occasion": "beach",
                "season_relevance": 0.85,
                "style_tags": ["relaxed", "minimal"],
                "pairs_with": ["accessory", "shoes"],
            },
            {
                "id": "beach_sandals",
                "name": "Sandals or slides",
                "description": "flat leather sandals",
                "match": [{"category": "shoes", "subcategories": ["sandals", "slides", "espadrilles"]}],
                "min_count": 1,
                "occasion": "beach",
                "season_relevance": 0.9,
                "style_tags": ["relaxed"],
                "pairs_with": ["top", "dress"],
            },
            {
                "id": "beach_hat",
                "name": "Sun hat",
                "description": "a wide straw sun hat",
                "match": [{"category": "accessory", "subcategories": ["hat", "cap"]}],
                "min_count": 1,
                "occasion": "beach",
                "season_relevance": 0.8,
                "style_tags": ["classic", "practical"],
                "pairs_with": ["top", "dress"],
                "check_season": False,
            },
            {
                "id": "sunglasses",
                "name": "Sunglasses",
                "description": "classic black sunglasses",
                "match": [{"category": "accessory", "subcategories": ["sunglasses"]}],
                "min_count": 1,
                "occasion": "beach",
                "season_relevance": 0.8,
                "style_tags": ["classic"],
                "pairs_with": ["top", "dress"],
                "check_season": False,
            },
            {
                "id": "beach_bag",
                "name": "Beach bag",
                "description": "a large straw tote bag",
                "match": [{"category": "accessory", "subcategories": ["tote", "beach_bag"]}],
                "min_count": 1,
                "occasion": "beach",
                "season_relevance": 0.7,
                "style_tags": ["relaxed"],
                "pairs_with": ["top", "dress"],
                "check_season": False,
            },
        ],
    },
    "dinner_date": {
        "label": "Dinner or date night",
        "season": ALL_YEAR,
        "requirements": [
            {
                "id": "date_outfit",
                "name": "Dress or dressy outfit",
                "description": "an elegant midi dress",
                "match": [{"category": "dress"}],
                "min_count": 1,
                "occasion": "date_night",
                "season_relevance": 0.8,
                "style_tags": ["elegant", "classic"],
                "pairs_with": ["shoes", "accessory"],
            },
            {
                "id": "dressy_tops",
                "name": "Dressy tops",
                "description": "a silk blouse",
                "match": [{"category": "top", "subcategories": ["blouse", "shirt", "turtleneck"], "tags": ["date_night", "elegant"]}],
                "min_count": 2,
                "occasion": "date_night",
                "season_relevance": 0.7,
                "style_tags": ["elegant", "minimal"],
                "pairs_with": ["bottom", "outerwear"],
            },
            {
                "id": "date_shoes",
                "name": "Evening shoes",
                "description": "heeled ankle boots",
                "match": [{"category": "shoes", "subcategories": ["heels", "pumps", "ankle_boots", "boots", "loafers"]}],
                "min_count": 1,
                "occasion": "date_night",
                "season_relevance": 0.75,
                "style_tags": ["elegant", "classic"],
                "pairs_with": ["dress", "bottom"],
            },
            {
                "id": "smart_layer",
                "name": "Smart layer",
                "description": "a tailored blazer",
                "match": [{"category": "outerwear", "subcategories": ["blazer", "suit_jacket", "coat", "trench"]}],
                "min_count": 1,
                "occasion": "date_night",
                "season_relevance": 0.65,
                "style_tags": ["classic", "elegant"],
                "pairs_with": ["dress", "top", "bottom"],
            },
            {
                "id": "evening_bag_date",
                "name": "Evening bag",
                "description": "a small evening clutch",
                "match": [{"category": "accessory", "subcategories": ["clutch", "evening_bag"]}],
                "min_count": 1,
                "occasion": "date_night",
                "season_relevance": 0.5,
                "style_tags": ["elegant"],
                "pairs_with": ["dress", "outerwear"],
            },
        ],
    },
}


def _condition_met(item: Mapping[str, Any], condition: Mapping[str, Any]) -> bool:
    if item.get("category") != condition["category"]:
        return False
    subcategories, tags = condition.get("subcategories"), condition.get("tags")
    if not subcategories and not tags:
        return True
    if subcategories and item.get("subcategory") in subcategories:
        return True
    item_tags = {*item.get("occasion_tags", []), *item.get("style_tags", [])}
    return bool(tags and item_tags & set(tags))


def _matches(item: Mapping[str, Any], requirement: Mapping[str, Any], season: str) -> bool:
    if season != ALL_YEAR and requirement.get("check_season", True) and season not in item.get("seasons", []):
        return False
    return any(_condition_met(item, condition) for condition in requirement["match"])


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
            "matched_item_ids": [item["id"] for item in matched],
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
