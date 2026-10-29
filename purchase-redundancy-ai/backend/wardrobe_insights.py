"""
Wardrobe insights - the analysis behind the dashboard and the agent's audit.

From the owned pieces (and the profile) it measures:
  composition    pieces per category vs the ideal mix for this gender (from the starter-wardrobe plans)
  duplicates     groups of near-identical pieces (CLIP image + text), with which one to keep
  colors         palette, share of neutrals, color harmony
  versatility    how many harmonious outfits the wardrobe makes; "star" pieces and "orphans"
  styles/seasons dominant style, consistency, winter / summer coverage
  scores         balance, uniqueness, versatility, harmony -> overall health 0-100
  tips           prioritized, actionable advice (French), each with an action the UI can run
  suggestions    real catalog products that fill the gaps, adapted to gender, colors and budget
"""

from collections import Counter
from itertools import product as cartesian
from typing import Dict, List, Optional

from features import NEUTRAL_COLORS, SEASON_COMPAT, FeatureSet
from wardrobe_builder import fits, plan_summary

CATEGORY_FR = {"shirts": "hauts", "pants": "bas", "dresses": "robes", "shoes": "chaussures",
               "outerwear": "vestes & manteaux", "accessories": "accessoires"}
COLOR_FR = {"black": "noir", "white": "blanc", "gray": "gris", "navy": "bleu marine", "blue": "bleu", "beige": "beige",
            "brown": "marron", "khaki": "kaki", "green": "vert", "olive": "olive", "red": "rouge", "burgundy": "bordeaux",
            "pink": "rose", "orange": "orange", "yellow": "jaune", "purple": "violet", "teal": "bleu canard",
            "silver": "argent", "gold": "doré", "multi": "multicolore", "cream": "crème", "tan": "camel"}
GOOD_HARMONY = 0.7
MAX_COMBOS = 4000  # outfit combinations evaluated (tops x bottoms x shoes), plenty for 100+ pieces


def _color(item: Dict) -> str:
    return (item.get("color") or item.get("primary_color") or "").lower()


def _slim(item: Dict) -> Dict:
    return {k: item.get(k) for k in ("id", "name", "category", "color", "image_url", "brand", "price")}


# ----------------------------------------------------------------------------
# Pieces of the analysis
# ----------------------------------------------------------------------------

def composition(wardrobe: List[Dict], gender: str) -> List[Dict]:
    """Have vs ideal per category. Ideal = share of the starter plan for this gender x wardrobe size
    (at least the essentials for small wardrobes)."""
    plan = plan_summary(gender if gender in ("Women", "Men") else "Unspecified")
    plan_total = sum(plan.values())
    counts = Counter(i.get("category") for i in wardrobe)
    size = max(len(wardrobe), 20)  # below 20 pieces, compare with a small but complete wardrobe
    rows = []
    for category in ("shirts", "pants", "dresses", "outerwear", "shoes", "accessories"):
        ideal = round(plan.get(category, 0) / plan_total * size)
        have = counts.get(category, 0)
        if ideal == 0 and have == 0:
            continue
        if have < ideal * 0.6 and ideal - have >= 1:
            status = "low"
        elif ideal and have > ideal * 1.6 and have - ideal >= 3:
            status = "high"
        else:
            status = "ok"
        rows.append({"category": category, "label": CATEGORY_FR[category], "have": have, "ideal": ideal, "status": status})
    return rows


def duplicate_groups(wardrobe: List[Dict], engine, versatility_by_id: Dict[str, int]) -> List[Dict]:
    """Duplicate pairs -> groups: 3 identical black tees = 1 group, not 3 pairs.
    Complete linkage: a piece joins a group only if it duplicates EVERY piece already in it - a plain
    transitive closure chained "blue jeans ~ navy trousers ~ black trousers" into one meaningless group."""
    pairs = engine.find_internal_duplicates(wardrobe) if len(wardrobe) >= 2 else []
    best: Dict[frozenset, float] = {frozenset((p["item_a_id"], p["item_b_id"])): p["similarity"] for p in pairs}
    group_of: Dict[str, int] = {}
    group_list: List[List[str]] = []

    def linked(item_id: str, members: List[str]) -> bool:
        return all(frozenset((item_id, m)) in best for m in members)

    for pair in sorted(best, key=best.get, reverse=True):  # strongest pairs first
        a, b = tuple(pair)
        ga, gb = group_of.get(a), group_of.get(b)
        if ga is None and gb is None:
            group_of[a] = group_of[b] = len(group_list)
            group_list.append([a, b])
        elif ga is None and linked(a, group_list[gb]):
            group_of[a] = gb
            group_list[gb].append(a)
        elif gb is None and linked(b, group_list[ga]):
            group_of[b] = ga
            group_list[ga].append(b)

    by_id = {i["id"]: i for i in wardrobe}
    result = []
    for ids in group_list:
        if len(ids) < 2:
            continue
        # keep the most versatile piece (then the most recent), the others are candidates to sell / donate
        items = sorted((by_id[i] for i in ids if i in by_id),
                       key=lambda i: (versatility_by_id.get(i["id"], 0), i.get("added_at") or ""), reverse=True)
        sims = [s for pair, s in best.items() if pair <= set(ids)]
        result.append({"items": [_slim(i) for i in items], "keep": items[0]["id"],
                       "extra": [i["id"] for i in items[1:]], "similarity": round(max(sims), 2),
                       "category": items[0].get("category")})
    return sorted(result, key=lambda g: (len(g["items"]), g["similarity"]), reverse=True)


def outfits(wardrobe: List[Dict]) -> Dict:
    """Harmonious outfits: top + bottom (+ shoes), or dress (+ shoes)"""
    by_cat = {c: [i for i in wardrobe if i.get("category") == c] for c in ("shirts", "pants", "dresses", "shoes")}
    shoes = by_cat["shoes"] or [None]
    bases = [[t, b] for t, b in cartesian(by_cat["shirts"], by_cat["pants"])] + [[d] for d in by_cat["dresses"]]
    counts: Counter = Counter()
    good, best = 0, []
    evaluated = 0
    for base in bases:
        for shoe in shoes:
            if evaluated >= MAX_COMBOS:
                break
            evaluated += 1
            pieces = base + ([shoe] if shoe else [])
            harmony = FeatureSet.feature_17_color_harmony([_color(p) for p in pieces])["harmony_score"]
            if harmony >= GOOD_HARMONY:
                good += 1
                for p in pieces:
                    counts[p["id"]] += 1
                if len(best) < 60:
                    best.append({"pieces": [_slim(p) for p in pieces], "harmony": harmony})
    best.sort(key=lambda o: o["harmony"], reverse=True)
    combinable = [i for i in wardrobe if i.get("category") in ("shirts", "pants", "dresses", "shoes")]
    orphans = [_slim(i) for i in combinable if counts.get(i["id"], 0) == 0]
    clothes = [i for i in combinable if i.get("category") != "shoes"]  # shoes join almost every outfit
    stars = [dict(_slim(by), outfits=counts[by["id"]]) for by in
             sorted(clothes, key=lambda i: counts.get(i["id"], 0), reverse=True)[:4] if counts.get(by["id"], 0)]
    return {"good_outfits": good, "evaluated": evaluated, "examples": best[:6], "stars": stars,
            "orphans": orphans[:8], "orphan_count": len(orphans), "by_item": dict(counts)}


def palette(wardrobe: List[Dict]) -> Dict:
    colors = Counter(_color(i) for i in wardrobe if _color(i) and _color(i) != "unknown")
    total = sum(colors.values()) or 1
    neutral = sum(n for c, n in colors.items() if c in NEUTRAL_COLORS)
    # A wardrobe naturally holds several accent colors (feature 17 penalizes each accent beyond 3, which suits
    # one outfit, not a closet): half the score is the neutral base (50 % neutrals = full marks), half is how
    # well the 3 main accents go together.
    main_accents = [c for c, _ in colors.most_common() if c not in NEUTRAL_COLORS][:3]
    accent_harmony = FeatureSet.feature_17_color_harmony(main_accents)["harmony_score"]
    harmony = round(0.5 * min(1.0, (neutral / total) / 0.5) + 0.5 * accent_harmony, 2)
    return {"colors": [{"color": c, "label": COLOR_FR.get(c, c), "count": n, "share": round(n / total, 3)}
                       for c, n in colors.most_common()],
            "neutral_share": round(neutral / total, 2), "harmony": harmony,
            "accents": len([c for c in colors if c not in NEUTRAL_COLORS])}


def seasons(wardrobe: List[Dict]) -> Dict:
    coverage = {}
    for season in ("winter", "summer"):
        compatible = SEASON_COMPAT[season]
        wearable = [i for i in wardrobe if (i.get("season") or "all-season") in compatible]
        coverage[season] = {"pieces": len(wearable),
                            "outerwear": sum(i.get("category") == "outerwear" for i in wearable)}
    return coverage


# ----------------------------------------------------------------------------
# Full analysis
# ----------------------------------------------------------------------------

def analyze_wardrobe(wardrobe: List[Dict], engine, catalog: List[Dict], profile: Optional[Dict] = None,
                     budget: Optional[float] = None) -> Dict:
    profile = profile or {}
    gender = profile.get("gender") or "Unspecified"
    if not wardrobe:
        return {"empty": True, "pieces": 0, "scores": None, "health": None, "gender": gender,
                "tips": [{"id": "start", "severity": "high", "title": "Votre garde-robe est vide",
                          "detail": "Ajoutez vos pièces en photo, depuis le catalogue, ou une garde-robe de départ adaptée.",
                          "action": {"type": "starter"}}],
                "composition": [], "duplicates": [], "outfits": None, "palette": None, "suggestions": []}

    comp = composition(wardrobe, gender)
    outfit_data = outfits(wardrobe)
    dups = duplicate_groups(wardrobe, engine, outfit_data["by_item"])
    pal = palette(wardrobe)
    style = FeatureSet.feature_18_style_consistency(wardrobe)
    season = seasons(wardrobe)
    extra_pieces = sum(len(g["extra"]) for g in dups)

    # ---- scores (0-100)
    deviations = [abs(r["have"] - r["ideal"]) / max(r["ideal"], 1) for r in comp]
    balance = round(100 * max(0.0, 1 - sum(min(d, 1.5) for d in deviations) / max(len(comp), 1) / 1.0))
    uniqueness = round(100 * max(0.0, 1 - 2.5 * extra_pieces / len(wardrobe)))
    bases = sum(1 for i in wardrobe if i.get("category") in ("shirts", "dresses"))
    versatility = round(min(100, 100 * outfit_data["good_outfits"] / max(bases * 3, 1)))
    harmony = round(100 * pal["harmony"])
    health = round(0.3 * balance + 0.25 * uniqueness + 0.25 * versatility + 0.2 * harmony)

    # ---- tips (most useful first)
    tips: List[Dict] = []
    if dups:
        tips.append({"id": "duplicates", "severity": "high" if extra_pieces >= 3 else "medium",
                     "title": f"{extra_pieces} pièce{'s' if extra_pieces > 1 else ''} en double",
                     "detail": f"{len(dups)} groupe{'s' if len(dups) > 1 else ''} de pièces quasi identiques. Gardez la plus "
                               "polyvalente de chaque groupe ; revendez ou donnez les autres, et n'en rachetez pas.",
                     "action": {"type": "duplicates"}})
    for row in sorted((r for r in comp if r["status"] == "low"), key=lambda r: r["have"] - r["ideal"]):
        tips.append({"id": f"gap-{row['category']}", "severity": "medium",
                     "title": f"Peu de {row['label']} ({row['have']} / {row['ideal']} conseillés)",
                     "detail": f"Ajouter {row['ideal'] - row['have']} {row['label']} multiplierait vos tenues.",
                     "action": {"type": "catalog", "category": row["category"]}})
    for row in (r for r in comp if r["status"] == "high"):
        tips.append({"id": f"excess-{row['category']}", "severity": "medium",
                     "title": f"Beaucoup de {row['label']} ({row['have']}, ~{row['ideal']} suffisent)",
                     "detail": f"N'achetez plus de {row['label']} pour l'instant : c'est là que les doublons naissent.",
                     "action": None})
    if outfit_data["orphan_count"]:
        tips.append({"id": "orphans", "severity": "low",
                     "title": f"{outfit_data['orphan_count']} pièce{'s' if outfit_data['orphan_count'] > 1 else ''} difficile{'s' if outfit_data['orphan_count'] > 1 else ''} à associer",
                     "detail": "Elles ne forment aucune tenue harmonieuse avec le reste. Un basique neutre (noir, blanc, "
                               "marine, beige) les rendrait portables.",
                     "action": {"type": "orphans"}})
    if pal["neutral_share"] < 0.4:
        tips.append({"id": "neutrals", "severity": "medium",
                     "title": f"Seulement {round(pal['neutral_share'] * 100)} % de couleurs neutres",
                     "detail": "Visez environ la moitié de basiques neutres : ils s'accordent avec toutes vos couleurs.",
                     "action": {"type": "catalog", "color": "black"}})
    if season["winter"]["outerwear"] == 0:
        tips.append({"id": "winter", "severity": "medium", "title": "Rien de chaud pour l'hiver",
                     "detail": "Aucune veste ni manteau d'hiver dans votre garde-robe.",
                     "action": {"type": "catalog", "category": "outerwear"}})
    if style["consistency"] < 0.35 and len(wardrobe) >= 10:
        tips.append({"id": "style", "severity": "low", "title": "Style dispersé",
                     "detail": "Vos pièces mélangent beaucoup de styles. Choisir 1 ou 2 styles signature facilite les tenues.",
                     "action": None})
    if len(wardrobe) < 40:
        tips.append({"id": "starter", "severity": "low", "title": f"Garde-robe incomplète ({len(wardrobe)} pièces)",
                     "detail": "Ajoutez une garde-robe de départ adaptée (40+ pièces) pour des analyses plus justes.",
                     "action": {"type": "starter"}})
    if not tips:
        tips.append({"id": "great", "severity": "low", "title": "Garde-robe équilibrée",
                     "detail": "Pas de doublon, bon équilibre et couleurs harmonieuses : achetez seulement pour remplacer.",
                     "action": None})
    severity_rank = {"high": 0, "medium": 1, "low": 2}
    tips.sort(key=lambda t: severity_rank[t["severity"]])

    # ---- catalog suggestions for the gaps (gender, favorite colors / neutrals, budget, not owned)
    suggestions = shopping_suggestions(wardrobe, catalog, comp, profile, budget)

    return {
        "empty": False, "pieces": len(wardrobe), "gender": gender,
        "value": round(sum(float(i.get("price") or 0) for i in wardrobe), 2),
        "health": health,
        "scores": {"balance": balance, "uniqueness": uniqueness, "versatility": versatility, "harmony": harmony},
        "composition": comp, "duplicates": dups, "extra_pieces": extra_pieces,
        "outfits": {k: v for k, v in outfit_data.items() if k != "by_item"},
        "palette": pal,
        "style": {"dominant": style.get("dominant_style"), "consistency": style["consistency"],
                  "distribution": style.get("distribution", {})},
        "seasons": season, "tips": tips, "suggestions": suggestions,
    }


def shopping_suggestions(wardrobe: List[Dict], catalog: List[Dict], comp: List[Dict], profile: Dict,
                         budget: Optional[float] = None, per_gap: int = 2) -> List[Dict]:
    gender = profile.get("gender") or "Unspecified"
    owned = {i.get("product_id") for i in wardrobe}
    favorite = set(profile.get("favorite_colors") or ()) | NEUTRAL_COLORS
    has_gender = any(p.get("gender") for p in catalog)
    out = []
    for row in sorted((r for r in comp if r["status"] == "low"), key=lambda r: r["have"] - r["ideal"]):
        pool = [p for p in catalog if p["category"] == row["category"] and p["id"] not in owned
                and fits(p, gender, has_gender) and (not budget or (p.get("price") and p["price"] <= budget))]
        pool.sort(key=lambda p: ((p.get("primary_color") in favorite), bool(p.get("price"))), reverse=True)
        for p in pool[:per_gap]:
            out.append(dict(_slim(p), color=p.get("primary_color"),
                            reason=f"Comble un manque : {row['label']} ({row['have']}/{row['ideal']})"))
    return out[:6]


# Dress codes: pieces that do not belong to an occasion, whatever their catalog "style" says
DRESS_CODE = {"wedding": "formal", "interview": "formal", "office": "smart", "party": "smart", "date": "smart",
              "gym": "sport", "hiking": "sport", "beach": "casual", "casual": "casual"}
TOO_CASUAL = {"shorts", "joggers", "leggings", "sweatshirt", "athletic shoes", "sandals", "cap", "hat"}
EXCLUDED = {
    "formal": TOO_CASUAL | {"t-shirt", "sneakers", "jeans"},
    "smart": TOO_CASUAL,
    "sport": {"dress", "heels", "dress shoes", "flats", "jewelry", "skirt"},
    "casual": set(),
}
CASUAL_NAME_WORDS = ("cargo", "track", "jogger", "hoodie", "flip flop", "sweat", "tee")
OPPOSITE_SEASON = {"summer": "winter", "winter": "summer"}


def wearable_in(item: Dict, season: str) -> bool:
    """Catalog seasons are coarse labels (heels tagged "fall"): only the opposite season excludes a piece,
    and shoes / accessories are worn all year"""
    if item.get("category") in ("shoes", "accessories"):
        return True
    return (item.get("season") or "all-season") != OPPOSITE_SEASON.get(season)


def fits_dress_code(item: Dict, dress_code: str) -> bool:
    if item.get("subcategory") in EXCLUDED.get(dress_code, set()):
        return False
    if dress_code in ("formal", "smart"):
        name = (item.get("name") or "").lower()
        return not any(word in name for word in CASUAL_NAME_WORDS)
    return True


def compose_outfits(wardrobe: List[Dict], styles: set, avoid: set, season: str, count: int = 3,
                    dress_code: str = "casual") -> Dict:
    """Up to `count` different outfits for an occasion (preferred styles, styles to avoid) and a season:
    top + bottom (+ shoes) or dress (+ shoes), plus a jacket in fall / winter and one accessory"""
    usable = [w for w in wardrobe if wearable_in(w, season) and w.get("style") not in avoid and fits_dress_code(w, dress_code)]
    preferred = [w for w in usable if w.get("style") in styles]
    has_top = any(w.get("category") in ("shirts", "dresses") for w in preferred)
    has_bottom = any(w.get("category") in ("pants", "dresses") for w in preferred)
    pool = preferred + [w for w in usable if w not in preferred and w.get("category") in ("shoes", "outerwear", "accessories")] \
        if has_top and has_bottom else usable
    matrix = outfits(pool)
    chosen, used = [], set()
    for outfit in matrix["examples"]:
        ids = {p["id"] for p in outfit["pieces"]}
        if not ids & used:  # different outfits rather than the same shirt three times
            chosen.append({"pieces": list(outfit["pieces"]), "harmony": outfit["harmony"]})
            used |= ids
        if len(chosen) == count:
            break
    jackets = [w for w in pool if w.get("category") == "outerwear"]
    accessories = [w for w in pool if w.get("category") == "accessories"]
    for n, outfit in enumerate(chosen):
        if season in ("winter", "fall") and jackets:
            outfit["pieces"].append(_slim(jackets[n % len(jackets)]))
        free = [a for a in accessories if a["id"] not in used]
        if free:
            outfit["pieces"].append(_slim(free[0]))
            used.add(free[0]["id"])
    categories = {w.get("category") for w in pool}
    missing = [c for c, ok in (("shirts", categories & {"shirts", "dresses"}), ("pants", categories & {"pants", "dresses"}),
                               ("shoes", "shoes" in categories),
                               ("outerwear", season not in ("winter", "fall") or "outerwear" in categories)) if not ok]
    return {"outfits": chosen, "possible": matrix["good_outfits"], "pool": len(pool), "missing": missing}


# ----------------------------------------------------------------------------
# Outfit synergy & pairwise similarity (Outfit Studio, agent tools)
# ----------------------------------------------------------------------------

def score_outfit(pieces: List[Dict], wardrobe: Optional[List[Dict]] = None) -> Dict:
    """Synergy score 0-100 of a set of owned pieces, with its breakdown, feedback and pieces to add.
    completeness 30 %, then harmony 35 % (color rules), style coherence 20 % and season coherence 15 %
    scaled by completeness, minus 15 points per piece that doubles a role (two pairs of trousers, two pairs of shoes)."""
    if not pieces:
        return {"score": 0, "verdict": "empty", "breakdown": {}, "feedback": ["Choisissez au moins deux pièces."], "add": []}
    categories = Counter(p.get("category") for p in pieces)
    has_base = categories["dresses"] >= 1 or (categories["shirts"] >= 1 and categories["pants"] >= 1)

    harmony = FeatureSet.feature_17_color_harmony([_color(p) for p in pieces if _color(p)])["harmony_score"]
    completeness = (60 if has_base else 25 if (categories["shirts"] or categories["pants"]) else 0) \
        + (25 if categories["shoes"] else 0) + (15 if categories["outerwear"] or categories["accessories"] else 0)
    styles = Counter(p.get("style") for p in pieces if p.get("style"))
    coherence = (styles.most_common(1)[0][1] / sum(styles.values())) if styles else 1.0
    seasons_used = {p.get("season") for p in pieces if p.get("season") and p.get("category") not in ("shoes", "accessories")}
    season_ok = 0.0 if {"summer", "winter"} <= seasons_used else 1.0
    doubled = sum(max(0, n - 1) for c, n in categories.items() if c in ("pants", "dresses", "shoes", "outerwear")) \
        + max(0, categories["shirts"] - 2)  # a shirt under a sweater is fine, three tops are not

    # Harmony, coherence and season only mean something for a complete look: they are weighted by completeness
    score = round(0.3 * completeness + (35 * harmony + 20 * coherence + 15 * season_ok) * completeness / 100 - 15 * doubled)
    score = max(0, min(100, score))

    feedback = []
    if not has_base:
        feedback.append("Il manque la base : un haut et un bas, ou une robe.")
    if not categories["shoes"]:
        feedback.append("Ajoutez des chaussures pour terminer la tenue.")
    if harmony < 0.6:
        clashing = [p for p in FeatureSet.feature_17_color_harmony([_color(p) for p in pieces])["pairs"]
                    if p["relation"] == "clashing"]
        if clashing:
            a, b = clashing[0]["colors"]
            feedback.append(f"Le {COLOR_FR.get(a, a)} et le {COLOR_FR.get(b, b)} se heurtent : remplacez l'un par un neutre.")
    if coherence < 0.6 and len(styles) > 1:
        feedback.append("Les styles se mélangent : gardez un style dominant.")
    if not season_ok:
        feedback.append("Des pièces d'été et d'hiver dans la même tenue.")
    if doubled:
        feedback.append("Deux pièces jouent le même rôle : gardez-en une seule.")
    if not feedback:
        feedback.append("Tenue cohérente : couleurs, style et saison s'accordent.")

    # Pieces from the wardrobe that would complete the look with the best harmony
    add = []
    if wardrobe:
        chosen_ids = {p.get("id") for p in pieces}
        wanted = ["shoes"] if not categories["shoes"] else []
        if not has_base:
            wanted += ["pants"] if categories["shirts"] else ["shirts"] if categories["pants"] else ["shirts", "pants"]
        if not (categories["outerwear"] or categories["accessories"]):
            wanted.append("accessories")
        base_colors = [_color(p) for p in pieces if _color(p)]
        for category in wanted:
            options = [w for w in wardrobe if w.get("category") == category and w.get("id") not in chosen_ids]
            options.sort(key=lambda w: FeatureSet.feature_17_color_harmony(base_colors + [_color(w)])["harmony_score"],
                         reverse=True)
            add += [_slim(w) for w in options[:2]]

    verdict = "excellent" if score >= 85 else "good" if score >= 65 else "weak"
    return {"score": score, "verdict": verdict,
            "breakdown": {"harmony": round(harmony * 100), "completeness": completeness,
                          "coherence": round(coherence * 100), "season": round(season_ok * 100), "doubled_roles": doubled},
            "feedback": feedback, "add": add[:4]}


def compare_pieces(a: Dict, b: Dict, engine) -> Dict:
    """Similarity of two pieces with its breakdown - the same computation as the duplicate detection"""
    match = engine.compare_wardrobe(a, [b], image_embedding=engine.image_embedding_for(a))
    if match:
        m = match[0]
        similarity, visual, image = m["similarity"], m["visual_similarity"], m.get("image_similarity")
        attrs = m["attribute_match"]
    else:  # below the "similar" threshold: compute the attributes anyway
        attrs = FeatureSet.feature_3_attribute_comparison(a, b)
        text_sim = engine._rescale(float(engine.embed(a) @ engine.embed(b)))
        similarity, visual, image = None, text_sim, None
    same_color = attrs["color_match"] or not attrs.get("color_known", True)
    duplicate = bool(similarity is not None and attrs["category_match"]
                     and similarity >= (0.75 if same_color else 0.9))
    return {"similarity": round(similarity, 2) if similarity is not None else None,
            "visual_similarity": round(visual, 2), "image_similarity": round(image, 2) if image is not None else None,
            "same_category": attrs["category_match"], "same_color": attrs["color_match"],
            "same_style": attrs["style_match"], "same_material": attrs["material_match"], "duplicate": duplicate,
            "a": _slim(a), "b": _slim(b)}
