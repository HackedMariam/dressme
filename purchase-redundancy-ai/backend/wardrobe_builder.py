"""
Starter wardrobes - a realistic set of 40+ real catalog pieces adapted to a profile
(gender, preferred styles and colors, sizes). Used at sign-up, by "+ Exemples" and by the demo accounts.

Each plan lists pieces per category AND subcategory, so a wardrobe looks like a real one (several
t-shirts, a few jeans, shoes for different occasions, bags, watches, belts...) instead of random picks.
"""

import random
from collections import Counter
from typing import Dict, Iterable, List, Optional

MIN_PIECES = 40

# (category, subcategory, pieces) - subcategories missing from the catalog are filled from the same category
PLANS: Dict[str, List[tuple]] = {
    "Women": [
        ("shirts", "t-shirt", 5), ("shirts", "top", 5), ("shirts", "casual shirt", 2), ("shirts", "sweatshirt", 1),
        ("pants", "jeans", 3), ("pants", "trousers", 3), ("pants", "skirt", 2), ("pants", "shorts", 1), ("pants", "leggings", 1),
        ("dresses", "dress", 6),
        ("outerwear", "jacket", 4),
        ("shoes", "sneakers", 2), ("shoes", "heels", 2), ("shoes", "flats", 2), ("shoes", "sandals", 2),
        ("accessories", "bag", 3), ("accessories", "watch", 2), ("accessories", "jewelry", 2),
        ("accessories", "sunglasses", 1), ("accessories", "hat", 1),
    ],
    "Men": [
        ("shirts", "t-shirt", 9), ("shirts", "casual shirt", 6), ("shirts", "sweatshirt", 1),
        ("pants", "jeans", 4), ("pants", "trousers", 4), ("pants", "joggers", 2), ("pants", "shorts", 2),
        ("outerwear", "jacket", 3),
        ("shoes", "sneakers", 3), ("shoes", "dress shoes", 2), ("shoes", "athletic shoes", 2), ("shoes", "sandals", 1),
        ("accessories", "watch", 3), ("accessories", "belt", 2), ("accessories", "sunglasses", 2),
        ("accessories", "bag", 1), ("accessories", "hat", 1),
    ],
}
UNISEX_SUBCATEGORIES = {"sunglasses", "bag", "hat", "cap", "backpack"}
GENDERS = ("Women", "Men", "Unspecified")


def plan_for(gender: str) -> List[tuple]:
    """Women / Men plans; 'Unspecified' mixes both (half of each, at least 40 pieces)"""
    if gender in PLANS:
        return PLANS[gender]
    mixed: Dict[tuple, int] = Counter()
    for plan in PLANS.values():
        for category, subcategory, count in plan:
            mixed[(category, subcategory)] += max(1, round(count / 2))
    return [(c, s, n) for (c, s), n in mixed.items()]


def plan_summary(gender: str) -> Dict[str, int]:
    """Pieces per category, for the sign-up preview"""
    summary: Dict[str, int] = Counter()
    for category, _, count in plan_for(gender):
        summary[category] += count
    return dict(summary)


def fits(product: Dict, gender: str, catalog_has_gender: bool = True) -> bool:
    """Same gender or unisex; unlabeled products only when genuinely unisex (sunglasses, bags...).
    Catalogs without any gender information (the illustrated one) accept every product."""
    product_gender = product.get("gender")
    if not catalog_has_gender or gender not in PLANS:
        return product_gender not in ("Boys", "Girls", "Kids")
    if product_gender in (gender, "Unisex"):
        return True
    return product_gender is None and product.get("subcategory") in UNISEX_SUBCATEGORIES


def _preference(product: Dict, styles: Iterable[str], colors: Iterable[str], rng: random.Random) -> float:
    return ((product.get("primary_color") in colors) * 2.0 + (product.get("style") in styles) * 1.5
            + rng.random() * 2.0)  # taste + variety


def build_starter_wardrobe(catalog: List[Dict], gender: str = "Unspecified", styles: Iterable[str] = (),
                           colors: Iterable[str] = (), exclude: Iterable[str] = (), seed: Optional[int] = None,
                           minimum: int = MIN_PIECES, near_duplicates: int = 0) -> List[Dict]:
    """Pick catalog products following the plan; returns at least `minimum` products when the catalog allows it.
    near_duplicates > 0 adds that many look-alike pieces (same subcategory + color) - used by the demo accounts."""
    rng = random.Random(seed)
    styles, colors = set(styles or ()), set(colors or ())
    taken = set(exclude or ())
    has_gender = any(p.get("gender") for p in catalog)
    eligible = [p for p in catalog if fits(p, gender, has_gender) and p["id"] not in taken]
    ranked = sorted(eligible, key=lambda p: _preference(p, styles, colors, rng), reverse=True)

    chosen: List[Dict] = []
    shortfall: Counter = Counter()

    looks = Counter()  # (subcategory, color) already in the wardrobe

    def take(pool: List[Dict], count: int) -> int:
        """Prefer new looks: a second black t-shirt only when no other color is left in the pool
        (a starter wardrobe should not be full of duplicates)"""
        added = 0
        while added < count:
            free = [p for p in pool if p["id"] not in taken]
            if not free:
                break
            # least represented look first; the preference ranking breaks ties
            product = min(free, key=lambda p: looks[(p.get("subcategory"), p.get("primary_color"))])
            chosen.append(product)
            taken.add(product["id"])
            looks[(product.get("subcategory"), product.get("primary_color"))] += 1
            added += 1
        return added

    for category, subcategory, count in plan_for(gender):
        pool = [p for p in ranked if p["category"] == category and p.get("subcategory") == subcategory]
        missing = count - take(pool, count)
        if missing:
            shortfall[category] += missing

    for category, missing in shortfall.items():  # e.g. few men's jackets: other pieces of the same category
        take([p for p in ranked if p["category"] == category], missing)
    if len(chosen) < minimum:  # still short (small catalog): top up with the best remaining matches
        take(ranked, minimum - len(chosen))

    for base in rng.sample(chosen, k=min(len(chosen), near_duplicates * 4)):
        if near_duplicates <= 0:
            break
        twins = [p for p in eligible if p["id"] not in taken and p.get("subcategory") == base.get("subcategory")
                 and p.get("primary_color") == base.get("primary_color")]
        if twins:
            take([rng.choice(twins)], 1)
            near_duplicates -= 1
    return chosen
