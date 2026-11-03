"""Wardrobe Gaps for a women's, men's or mixed wardrobe.

The base rules in coverage.py are the original ones and stay untouched. This file only says how they change
for a man (or add to them for a "both" wardrobe), so nothing changes for a user whose department is unknown.

Which department?  `resolve_department(shopping_for, gender)`:
    1. style_profiles.shopping_for  (women | men | both) when the user chose it
    2. otherwise profiles.gender    (female -> women, male -> men, non_binary -> both)
    3. otherwise None: the base rules, as before.  "prefer_not_to_say" also gives None.

What each department gets (`adapt`):
    None / women   the base rules.
    men            the base rules, with the variants below: a variant changes a need in place (same id, for
                   example "swimwear" asks for swim shorts), replaces it by another need (a suit instead of an
                   evening dress, new id) or drops it (a clutch has no equivalent).
    both           the base rules plus the NEW needs of the men's variants (a suit AND an evening dress).
                   In-place changes are not applied, so a swimsuit stays a swimsuit.

A new need gets a new id on purpose: "I need this" / "Not relevant" answers are stored per id, and the answer to
"an evening dress" must not become the answer to "a suit".
"""

from typing import Any, Mapping, Sequence

DEPARTMENTS = ("women", "men", "both")
_GENDER_TO_DEPARTMENT = {"female": "women", "male": "men", "non_binary": "both"}


def resolve_department(shopping_for: str | None, gender: str | None) -> tuple[str | None, str | None]:
    """(department, where it came from) from the two profile fields. (None, None) when the user said nothing."""
    if shopping_for in DEPARTMENTS:
        return shopping_for, "shopping_for"
    mapped = _GENDER_TO_DEPARTMENT.get(gender or "")
    return (mapped, "gender") if mapped else (None, None)


# goal -> base requirement id -> changes for men.  None drops the need.  A dict is merged over the base need.
MEN_VARIANTS: dict[str, dict[str, dict[str, Any] | None]] = {
    "summer_casual": {
        "breathable_tops": {
            "description": "a breathable linen shirt",
            "match": [{"category": "top", "subcategories": ["t-shirt", "linen_shirt", "tank_top", "polo"]}],
        },
        "light_bottoms": {
            "match": [{"category": "bottom", "subcategories": ["shorts", "linen_trousers", "chinos"]}],
        },
        "swimwear": {"description": "swim shorts"},
    },
    "formal_event": {
        "formal_outfit": {
            "id": "formal_suit",
            "name": "Formal outfit (suit)",
            "description": "a dark formal suit",
            "match": [{"category": "outerwear", "subcategories": ["suit_jacket"]}],
        },
        "formal_shoes": {
            "description": "black leather oxford shoes",
            "match": [{"category": "shoes", "subcategories": ["oxfords", "derbies", "loafers"]}],
        },
        "evening_accessory": {
            "id": "formal_tie",
            "name": "Tie or pocket square",
            "description": "a silk tie",
            "match": [{"category": "accessory", "subcategories": ["tie"]}],
            "pairs_with": ["top", "outerwear"],
        },
    },
    "sport_gym": {
        "training_bottoms": {"description": "breathable running shorts"},
    },
    "beach_pool": {
        "swimwear": {"description": "swim shorts"},
        "cover_up": {
            "description": "a light linen shirt",
            "match": [{"category": "top", "subcategories": ["linen_shirt", "tank_top", "shirt"]}],
        },
        "beach_bag": {"description": "a canvas beach bag"},
    },
    "dinner_date": {
        "date_outfit": None,
        "dressy_tops": {
            "description": "a fitted dress shirt",
            "match": [{"category": "top", "subcategories": ["shirt", "polo", "turtleneck"], "tags": ["date_night", "elegant"]}],
        },
        "date_shoes": {
            "description": "leather chelsea boots",
            "match": [{"category": "shoes", "subcategories": ["ankle_boots", "boots", "loafers", "derbies"]}],
        },
        "evening_bag_date": None,
    },
}


def adapt(requirements: Sequence[Mapping[str, Any]], goal_id: str, department: str | None) -> list[dict[str, Any]]:
    """The requirements of a goal for a department. Never modifies the base rules it is given."""
    if department not in ("men", "both"):
        return [dict(r) for r in requirements]

    variants = MEN_VARIANTS.get(goal_id, {})
    adapted: list[dict[str, Any]] = []
    for requirement in requirements:
        if requirement["id"] not in variants:
            adapted.append(dict(requirement))
            continue
        change = variants[requirement["id"]]
        if change is None:                                   # no men's equivalent
            if department == "both":
                adapted.append(dict(requirement))
            continue
        changed = {**requirement, **change}
        if changed["id"] != requirement["id"]:               # a different need: kept next to the base one for "both"
            if department == "both":
                adapted.append(dict(requirement))
            adapted.append(changed)
        else:                                                # the same need, worded and matched for men
            adapted.append(changed if department == "men" else dict(requirement))
    return adapted


def all_variants(goal_id: str, requirements: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Every need a goal can have in any department (used to look a need up by id)."""
    return adapt(requirements, goal_id, "both") + adapt(requirements, goal_id, "men")
