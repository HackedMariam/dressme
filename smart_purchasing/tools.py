"""All 5 specialized tools for the Purchase Agent in a single, clean module.

Tools:
1. analyze_item           -> Vision analysis & attribute extraction
2. find_similar_items      -> Wardrobe retrieval & redundancy check
3. generate_outfits        -> Outfit generation & compatibility ranking
4. analyze_wardrobe_gaps   -> Closet gap & coverage analysis
5. calculate_purchase_value -> Deterministic purchase scoring formula
"""

import os
import re
import hashlib
from typing import List, Dict, Any, Optional
from PIL import Image

from schemas import (
    Garment,
    CandidateItem,
    SimilarItemMatch,
    OutfitRecommendation,
    GapAnalysisResult,
    PurchaseScoreResult,
    PurchaseScoreBreakdown,
    DecisionType,
)

try:
    from color_similarity import ColorSimilarityService, compare_colors, compute_color_similarity as ciede_color_similarity
except ImportError:
    from smart_purchasing.color_similarity import ColorSimilarityService, compare_colors, compute_color_similarity as ciede_color_similarity



# =====================================================================
# HELPER: Vision & Embedding Utilities
# =====================================================================

def extract_dominant_color(image_path: str) -> str:
    """Extracts dominant garment color by filtering out background pixels and focusing on garment center."""
    if not image_path or not os.path.exists(image_path):
        return "neutral"
    try:
        with Image.open(image_path) as img:
            img = img.convert("RGB")
            w, h = img.size
            # Crop to center 60% of image where the garment is located
            center_crop = img.crop((int(w * 0.2), int(h * 0.15), int(w * 0.8), int(h * 0.85)))
            center_crop = center_crop.resize((60, 60))
            pixels = list(center_crop.getdata())

            # Filter out white/off-white background pixels (R, G, B > 210)
            garment_pixels = [
                p for p in pixels
                if not (p[0] > 205 and p[1] > 205 and p[2] > 205)
            ]

            # If almost all pixels were background, fall back to center pixels
            if len(garment_pixels) < 50:
                garment_pixels = pixels

            r_avg = sum(p[0] for p in garment_pixels) / len(garment_pixels)
            g_avg = sum(p[1] for p in garment_pixels) / len(garment_pixels)
            b_avg = sum(p[2] for p in garment_pixels) / len(garment_pixels)

            # Color classification
            if r_avg < 80 and g_avg < 80 and b_avg < 80:
                return "black"
            elif r_avg > 200 and g_avg > 200 and b_avg > 200:
                return "white"
            elif b_avg > r_avg + 10 and b_avg > g_avg and b_avg > 140 and r_avg > 115:
                return "light_blue"
            elif b_avg > r_avg + 15 and b_avg > g_avg:
                return "navy" if b_avg < 110 else "blue"
            elif abs(r_avg - g_avg) < 18 and abs(g_avg - b_avg) < 18:
                return "grey"
            elif r_avg > g_avg and g_avg > b_avg:
                return "camel" if r_avg > 130 else "brown"
            elif r_avg > g_avg + 40 and r_avg > b_avg + 40:
                return "red"
            elif g_avg > r_avg + 20 and g_avg > b_avg + 20:
                return "green"
            else:
                return "neutral"
    except Exception:
        return "neutral"


def normalize_color(c: Optional[str]) -> str:
    """Normalizes color string into canonical representation to eliminate spacing/underscore discrepancies."""
    if not c:
        return "neutral"
    return ColorSimilarityService.get_instance().normalize_color_name(c)


def compute_color_similarity(color1: str, color2: str) -> float:
    """Computes perceptual color similarity between two colors using CIEDE2000 in [0.0, 1.0]."""
    return ColorSimilarityService.get_instance().get_color_similarity(color1, color2)



def generate_embedding(text_or_path: str, dim: int = 64) -> List[float]:
    """Generates a fast normalized pseudo-embedding (extensible with FashionCLIP)."""
    digest = hashlib.sha256(text_or_path.encode("utf-8")).digest()
    raw = [float(b) / 255.0 for b in digest[:dim]]
    while len(raw) < dim:
        raw.extend(raw[:dim - len(raw)])
    norm = sum(x * x for x in raw) ** 0.5
    return [x / norm for x in raw] if norm > 0 else raw


def cosine_sim(v1: List[float], v2: List[float]) -> float:
    """Cosine similarity between two vectors."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    norm_a = sum(a * a for a in v1) ** 0.5
    norm_b = sum(b * b for b in v2) ** 0.5
    return max(0.0, min(1.0, dot / (norm_a * norm_b))) if norm_a * norm_b > 0 else 0.0


# =====================================================================
# TOOL 1: analyze_item (Vision / Attribute Extraction)
# =====================================================================

def analyze_item(candidate: CandidateItem) -> Dict[str, Any]:
    """Tool 1: Analyzes garment image & metadata to verify color, category, and features."""
    detected_color = candidate.color
    
    # If color is missing or unknown, extract from image
    if (not detected_color or detected_color.lower() in ["unknown", "neutral", "auto-detect", ""]) and candidate.image_path:
        detected_color = extract_dominant_color(candidate.image_path)
    elif not detected_color:
        detected_color = "neutral"

    # Also check if candidate name has explicit color
    candidate_name = (candidate.name or "").lower()
    for c in ["light blue", "dark blue", "black", "white", "navy", "grey", "charcoal", "camel", "brown", "beige", "red", "green", "blue"]:
        if re.search(r'\b' + c + r'\b', candidate_name):
            detected_color = c
            break

    desc = f"{detected_color}_{candidate.category}_" + "_".join(candidate.style)
    embedding = generate_embedding(candidate.image_path or desc)

    return {
        "id": candidate.id,
        "category": candidate.category.lower(),
        "color": detected_color.lower(),
        "style": [s.lower() for s in candidate.style],
        "seasons": candidate.seasons or ["spring", "autumn"],
        "occasions": candidate.occasions or ["work"],
        "embedding": embedding,
        "price": candidate.price,
        "image_path": candidate.image_path,
        "is_analyzed": True,
    }


# =====================================================================
# TOOL 2: find_similar_items (Wardrobe Retrieval & Redundancy)
# =====================================================================

CATEGORY_EQUIVALENCE = {
    "blazer": {"blazer", "jacket", "suit_jacket", "outerwear"},
    "jacket": {"blazer", "jacket", "suit_jacket", "outerwear"},
    "outerwear": {"blazer", "jacket", "coat", "raincoat", "cardigan", "outerwear"},
    "coat": {"coat", "overcoat", "trench", "raincoat", "outerwear"},
    "raincoat": {"raincoat", "coat", "outerwear"},
    "cardigan": {"cardigan", "sweater", "knitwear", "outerwear"},
    "sweater": {"sweater", "knitwear", "cardigan", "hoodie", "top"},
    "knitwear": {"sweater", "knitwear", "cardigan"},
    "hoodie": {"hoodie", "sweater", "top"},
    "shirt": {"shirt", "blouse", "button_down", "top"},
    "blouse": {"shirt", "blouse", "top"},
    "t-shirt": {"t-shirt", "t_shirt", "tee", "top"},
    "t_shirt": {"t-shirt", "t_shirt", "tee", "top"},
    "skirt": {"skirt", "bottom"},
    "shorts": {"shorts", "bottom"},
    "trousers": {"trousers", "pants", "chinos", "slacks", "jeans", "bottom"},
    "jeans": {"jeans", "denim", "trousers", "bottom"},
    "shoes": {"shoes", "sandals", "sneakers", "boots", "loafers"},
    "sandals": {"shoes", "sandals"},
    "sneakers": {"shoes", "sneakers"},
    "boots": {"shoes", "boots"},
    "dress": {"dress", "formal_dress", "casual_dress", "formal-dress", "casual-dress"},
    "formal_dress": {"dress", "formal_dress", "formal-dress"},
    "casual_dress": {"dress", "casual_dress", "casual-dress"},
    "belt": {"belt", "accessory"},
    "scarf": {"scarf", "accessory"},
    "hat": {"hat", "accessory"},
    "bag": {"bag", "accessory"}
}

def are_equivalent_categories(cat1: str, cat2: str) -> bool:
    """Checks whether two fashion categories share functional purpose or type."""
    c1 = cat1.lower().strip().replace("-", "_")
    c2 = cat2.lower().strip().replace("-", "_")
    if c1 == c2:
        return True
    eq1 = CATEGORY_EQUIVALENCE.get(c1, {c1})
    eq2 = CATEGORY_EQUIVALENCE.get(c2, {c2})
    return bool(eq1.intersection(eq2) or (c1 in eq2) or (c2 in eq1))


def find_similar_items(
    candidate: CandidateItem,
    wardrobe: List[Garment],
    top_k: int = 5
) -> List[SimilarItemMatch]:
    """Tool 2: Finds visually and functionally similar clothes in owned wardrobe.
    
    Strictly detects duplicates when category, normalized color, and subtype/style overlap.
    """
    cand_cat = candidate.category.lower().strip().replace("-", "_")
    cand_col_norm = normalize_color(candidate.color)

    # Extract key fashion subtype tokens from candidate
    cand_text = f"{candidate.name or ''} {candidate.category} {' '.join(candidate.style)}".lower()
    fashion_subtypes = [
        "oxford", "cotton", "linen", "flannel", "chinos", "trench", "overcoat", 
        "bomber", "loafers", "sneakers", "boots", "chelsea", "cashmere", "sweater", 
        "silk", "wool", "suit", "blazer", "jacket", "denim", "t-shirt", "sandals", "skirt", "coat"
    ]
    cand_subtypes = {w for w in fashion_subtypes if w in cand_text}

    matches: List[SimilarItemMatch] = []
    for g in wardrobe:
        g_cat = g.category.lower().strip().replace("-", "_")
        g_col_norm = normalize_color(g.color)
        g_text = f"{g.name} {g.category} {' '.join(g.style)} {' '.join(g.tags)} {g.description or ''}".lower()

        is_both_sneakers = ({cand_cat, g_cat} == {"sneakers", "shoes"} and ("sneaker" in g_text or "sneaker" in cand_text))
        same_category = are_equivalent_categories(cand_cat, g_cat) or is_both_sneakers
        same_color = (g_col_norm == cand_col_norm)
        col_comp = compare_colors(candidate.color, g.color)
        col_sim = 1.0 if same_color else col_comp.similarity_score

        g_subtypes = {w for w in fashion_subtypes if w in g_text}
        shared_subtypes = cand_subtypes.intersection(g_subtypes)

        cand_styles = set(s.lower().replace("-", "_") for s in candidate.style)
        g_styles = set(s.lower().replace("-", "_") for s in g.style)
        style_overlap = len(cand_styles.intersection(g_styles)) / max(1, len(cand_styles)) if cand_styles else 0.5

        # Subtype overlap strength (e.g. both are Oxford shirts, Blazers/Jackets, or Minimalist Sandals!)
        has_strong_subtype_match = bool(shared_subtypes)

        if same_category and (same_color or (col_sim >= 0.85 and has_strong_subtype_match)):
            # DIRECT DUPLICATE: Same category and same color
            if same_color and has_strong_subtype_match:
                score = 0.95 + 0.05 * style_overlap
            elif same_color:
                score = 0.88 + 0.12 * style_overlap
            else:
                score = 0.80 + 0.15 * col_sim
        elif same_category:
            # Same category, different color (functional overlap)
            score = 0.50 + 0.15 * col_sim + 0.15 * style_overlap
        else:
            related_cat = {
                ("blazer", "outerwear"): 0.45,
                ("jacket", "outerwear"): 0.45,
                ("trousers", "jeans"): 0.45,
                ("trousers", "skirt"): 0.35,
                ("jeans", "skirt"): 0.35,
                ("shorts", "skirt"): 0.35,
                ("shoes", "sneakers"): 0.65,
                ("shoes", "sandals"): 0.65,
                ("t-shirt", "shirt"): 0.40,
                ("knitwear", "outerwear"): 0.35,
            }
            base = related_cat.get((cand_cat, g_cat), related_cat.get((g_cat, cand_cat), 0.10))
            score = base + 0.15 * col_sim

        if score > 0.4:
            is_redundant = same_category and (same_color or score >= 0.75)
            warning = None
            if same_category and (same_color or score >= 0.85):
                warning = f"DIRECT DUPLICATE: You already own a {g.color.replace('_', ' ')} {g.category} ('{g.name}'). Buying another serves the exact same role."
            elif is_redundant:
                warning = f"Redundancy risk: You already own a {g.color.replace('_', ' ')} {g.category} ('{g.name}')."

            matches.append(SimilarItemMatch(
                garment=g,
                similarity_score=round(score, 2),
                functional_overlap=same_category,
                redundancy_warning=warning,
                color_similarity=round(col_sim, 4),
                color_delta_e=round(col_comp.delta_e, 2)
            ))

    matches.sort(key=lambda x: x.similarity_score, reverse=True)
    return matches[:top_k]


# =====================================================================
# TOOL 3: check_outfit_compatibility (Outfit Compatibility Check)
# =====================================================================

def evaluate_outfit_compatibility(candidate: CandidateItem, items: List[Garment]) -> float:
    """Calculates compatibility score (0-100) between candidate and paired items."""
    if not items:
        return 50.0
    score = 75.0
    neutrals = {"black", "white", "navy", "beige", "grey", "charcoal", "camel", "cream", "brown", "ivory", "off_white", "khaki", "taupe"}
    if normalize_color(candidate.color) in neutrals:
        score += 10.0
    cand_seasons = set(s.lower() for s in candidate.seasons)
    for it in items:
        if cand_seasons.intersection(set(s.lower() for s in it.seasons)):
            score += 5.0
            break
    return min(100.0, score)


def check_outfit_compatibility(
    candidate: CandidateItem,
    wardrobe: List[Garment],
    target_occasion: Optional[str] = None
) -> Dict[str, Any]:
    """Tool 3: Checks compatibility of the candidate item with existing wardrobe pieces.
    
    Returns how many outfits this item is compatible with and details the combinations.
    """
    valid_combinations: List[OutfitRecommendation] = []
    occasion = target_occasion or (candidate.occasions[0] if candidate.occasions else "work")
    cat = candidate.category.lower().strip().replace("-", "_")

    is_top_or_outerwear = cat in [
        "blazer", "jacket", "outerwear", "coat", "raincoat", "cardigan",
        "sweater", "knitwear", "shirt", "t_shirt", "t-shirt", "blouse", "hoodie"
    ]
    is_bottom = cat in ["trousers", "jeans", "skirt", "shorts", "pants"]
    is_shoes = cat in ["shoes", "sandals", "sneakers", "boots", "loafers"]
    is_dress = cat in ["dress", "formal_dress", "casual_dress"]

    if is_top_or_outerwear:
        bottoms = [
            g for g in wardrobe
            if g.category in ["trousers", "jeans", "skirt", "shorts"] or "bottom" in g.tags
        ]
        shoes = [
            g for g in wardrobe
            if g.category in ["shoes", "sandals", "sneakers", "boots", "loafers"] or "shoes" in g.tags
        ]
        inner_tops = [
            g for g in wardrobe
            if g.category in ["shirt", "t_shirt", "t-shirt", "blouse", "sweater"] or "top" in g.tags
        ]

        for i, b in enumerate(bottoms[:2]):
            paired = [b]
            if shoes:
                paired.append(shoes[i % len(shoes)])
            if cat in ["blazer", "jacket", "coat", "outerwear", "raincoat"] and inner_tops and i < len(inner_tops):
                paired.insert(0, inner_tops[i])

            score = evaluate_outfit_compatibility(candidate, paired)
            desc_items = " + ".join([g.name for g in paired])
            valid_combinations.append(OutfitRecommendation(
                outfit_id=f"outfit_00{i+1}",
                candidate_item_category=candidate.category,
                paired_garments=paired,
                compatibility_score=score,
                occasion=occasion,
                description=f"Pair with: {desc_items}"
            ))
    elif is_bottom:
        tops = [
            g for g in wardrobe
            if g.category in ["shirt", "t_shirt", "t-shirt", "blouse", "sweater", "jacket", "coat", "blazer"] or "top" in g.tags or "outerwear" in g.tags
        ]
        shoes = [
            g for g in wardrobe
            if g.category in ["shoes", "sandals", "sneakers"] or "shoes" in g.tags
        ]
        for i, t in enumerate(tops[:2]):
            paired = [t]
            if shoes:
                paired.append(shoes[i % len(shoes)])
            score = evaluate_outfit_compatibility(candidate, paired)
            desc_items = " + ".join([g.name for g in paired])
            valid_combinations.append(OutfitRecommendation(
                outfit_id=f"outfit_00{i+1}",
                candidate_item_category=candidate.category,
                paired_garments=paired,
                compatibility_score=score,
                occasion=occasion,
                description=f"Pair with: {desc_items}"
            ))
    elif is_shoes:
        bottoms = [
            g for g in wardrobe
            if g.category in ["trousers", "jeans", "skirt", "shorts"] or "bottom" in g.tags
        ]
        tops = [
            g for g in wardrobe
            if g.category in ["shirt", "t_shirt", "blouse", "sweater", "blazer", "jacket", "coat"] or "top" in g.tags
        ]
        for i in range(min(2, len(bottoms))):
            paired = [bottoms[i]]
            if tops and i < len(tops):
                paired.append(tops[i])
            score = evaluate_outfit_compatibility(candidate, paired)
            desc_items = " + ".join([g.name for g in paired])
            valid_combinations.append(OutfitRecommendation(
                outfit_id=f"outfit_00{i+1}",
                candidate_item_category=candidate.category,
                paired_garments=paired,
                compatibility_score=score,
                occasion=occasion,
                description=f"Pair with: {desc_items}"
            ))
    elif is_dress:
        layers = [
            g for g in wardrobe
            if g.category in ["jacket", "coat", "cardigan", "raincoat", "blazer"] or "outerwear" in g.tags
        ]
        shoes = [
            g for g in wardrobe
            if g.category in ["shoes", "sandals", "sneakers"] or "shoes" in g.tags
        ]
        accessories = [
            g for g in wardrobe
            if g.category in ["bag", "scarf", "belt", "hat"] or "accessory" in g.tags
        ]
        paired = []
        if layers:
            paired.append(layers[0])
        if shoes:
            paired.append(shoes[0])
        if accessories and len(paired) < 3:
            paired.append(accessories[0])
        score = evaluate_outfit_compatibility(candidate, paired)
        desc_items = " + ".join([g.name for g in paired])
        valid_combinations.append(OutfitRecommendation(
            outfit_id="outfit_001",
            candidate_item_category=candidate.category,
            paired_garments=paired,
            compatibility_score=score,
            occasion=occasion,
            description=f"Pair with: {desc_items}"
        ))
    else:
        sample_paired = wardrobe[:2]
        score = evaluate_outfit_compatibility(candidate, sample_paired)
        valid_combinations.append(OutfitRecommendation(
            outfit_id="outfit_001",
            candidate_item_category=candidate.category,
            paired_garments=sample_paired,
            compatibility_score=score,
            occasion=occasion,
            description=f"Pair with: " + ", ".join([g.name for g in sample_paired])
        ))

    compatible_count = len(valid_combinations)
    avg_score = (
        sum(o.compatibility_score for o in valid_combinations) / max(1, compatible_count)
        if valid_combinations else 50.0
    )
    summary_text = f"This item is compatible with {compatible_count} outfit(s) in your wardrobe (Average compatibility: {avg_score:.2f}%)."

    return {
        "compatible_count": compatible_count,
        "average_score": avg_score,
        "summary": summary_text,
        "combinations": valid_combinations
    }


# =====================================================================
# TOOL 4: analyze_wardrobe_gaps (Wardrobe Gap & Coverage)
# =====================================================================

def analyze_wardrobe_gaps(candidate: CandidateItem, wardrobe: List[Garment]) -> GapAnalysisResult:
    """Tool 4: Identifies whether the item fills an underrepresented wardrobe gap."""
    cat = candidate.category.lower().strip().replace("-", "_")
    cand_norm_color = normalize_color(candidate.color)

    owned_in_cat = [
        g for g in wardrobe
        if are_equivalent_categories(cat, g.category) or (cat in g.tags)
    ]
    owned_norm_colors = {normalize_color(g.color) for g in owned_in_cat}

    if len(owned_in_cat) == 0:
        gap_score = 90.0
        reasoning = f"Essential gap: You currently own zero items in the '{cat}' category."
    elif cand_norm_color in owned_norm_colors:
        # Same category and same color already owned -> NO gap filled!
        gap_score = 10.0
        reasoning = f"No gap filled (Duplicate): You already own {len([g for g in owned_in_cat if normalize_color(g.color) == cand_norm_color])} {cand_norm_color.replace('_', ' ')} {cat}(s)."
    else:
        gap_score = 75.0
        display_owned = list({g.color.replace('_', ' ') for g in owned_in_cat})[:4]
        reasoning = f"Color gap: Adds a new {candidate.color.replace('_', ' ')} option to your {cat} collection (currently own: {', '.join(display_owned)})."

    return GapAnalysisResult(
        category=candidate.category,
        underrepresented_occasions=candidate.occasions or ["work"],
        underrepresented_seasons=candidate.seasons or ["autumn"],
        gap_fill_score=gap_score,
        reasoning=reasoning,
    )


# =====================================================================
# TOOL 5: calculate_purchase_value (Deterministic Scoring Formula)
# =====================================================================

def calculate_purchase_value(
    outfit_compatibility_score: float,
    wardrobe_gap_score: float,
    versatility_score: float,
    personal_style_score: float,
    redundancy_score: float,
    price: Optional[float] = None,
    budget: Optional[float] = None,
    is_direct_duplicate: bool = False,
    color_similarity_score: Optional[float] = None
) -> PurchaseScoreResult:
    """Tool 5: Deterministic purchase score calculation with hard constraint validation.

    Formula:
      S = 0.30*O + 0.20*G + 0.20*V + 0.15*P + 0.15*(100 - R) - BudgetPenalty
      
    Hard Constraint:
      If the user already owns an item with the same category, color, and style (is_direct_duplicate=True
      or redundancy_score >= 85), the score is capped and the decision is strictly SKIP.
    """
    O = max(0.0, min(100.0, float(outfit_compatibility_score)))
    G = max(0.0, min(100.0, float(wardrobe_gap_score)))
    V = max(0.0, min(100.0, float(versatility_score)))
    P = max(0.0, min(100.0, float(personal_style_score)))
    R = max(0.0, min(100.0, float(redundancy_score)))

    low_redundancy_val = 100.0 - R

    outfit_contrib = 0.30 * O
    gap_contrib = 0.20 * G
    versatility_contrib = 0.20 * V
    style_contrib = 0.15 * P
    low_redundancy_contrib = 0.15 * low_redundancy_val

    base_score = outfit_contrib + gap_contrib + versatility_contrib + style_contrib + low_redundancy_contrib

    # Affordability adjustment (if budget is known)
    budget_penalty = 0.0
    if price is not None and budget is not None and budget > 0:
        if price > budget:
            overage_ratio = (price - budget) / budget
            budget_penalty = min(25.0, round(overage_ratio * 20.0, 2))

    overall_score = round(max(0.0, min(100.0, base_score - budget_penalty)), 2)

    # HARD CONSTRAINT: Direct duplicate in category + color + style
    if is_direct_duplicate or R >= 85.0:
        # Direct duplicate strictly forces SKIP decision, and budget penalty dynamically applies
        overall_score = round(max(0.0, min(40.0, base_score) - budget_penalty), 2)
        decision = DecisionType.SKIP
    elif overall_score >= 70.0:
        decision = DecisionType.BUY
    elif overall_score >= 45.0:
        decision = DecisionType.CONSIDER
    else:
        decision = DecisionType.SKIP


    breakdown = PurchaseScoreBreakdown(
        outfit_compatibility=round(O, 2),
        outfit_contribution=round(outfit_contrib, 2),
        gap_contribution_score=round(G, 2),
        gap_contribution=round(gap_contrib, 2),
        versatility_score=round(V, 2),
        versatility_contribution=round(versatility_contrib, 2),
        style_match_score=round(P, 2),
        style_contribution=round(style_contrib, 2),
        redundancy_raw_score=round(R, 2),
        low_redundancy_contribution=round(low_redundancy_contrib, 2),
        budget_penalty=budget_penalty,
        color_similarity_score=round(color_similarity_score, 4) if color_similarity_score is not None else None
    )

    penalty_text = f", Budget Penalty: -{budget_penalty:.2f}" if budget_penalty > 0 else ""
    summary = (
        f"Overall Purchase Score: {overall_score:.2f}/100 [{decision.value}]. "
        f"(Outfits: {O:.2f}%, Wardrobe Gap: {G:.2f}%, Versatility: {V:.2f}%, "
        f"Style: {P:.2f}%, Uniqueness: {low_redundancy_val:.2f}%{penalty_text})."
    )

    return PurchaseScoreResult(
        overall_score=overall_score,
        decision=decision,
        breakdown=breakdown,
        summary=summary
    )



# =====================================================================
# Tool Call Schemas for Qwen3-4B
# =====================================================================

PURCHASE_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "analyze_item",
            "description": "Extract attributes and visual embedding from candidate product image.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string"},
                    "color": {"type": "string"},
                    "image_path": {"type": "string"}
                },
                "required": ["category"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "find_similar_items",
            "description": "Find items in owned wardrobe that are functionally or visually similar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string"},
                    "color": {"type": "string"}
                },
                "required": ["category"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_outfit_compatibility",
            "description": "Checks how many existing wardrobe outfits this item is compatible with.",
            "parameters": {
                "type": "object",
                "properties": {
                    "occasion": {"type": "string", "description": "Target occasion, e.g. work, casual, formal"}
                }
            }
        }
    },

    {
        "type": "function",
        "function": {
            "name": "analyze_wardrobe_gaps",
            "description": "Check whether the item fulfills an underrepresented wardrobe gap.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string"}
                },
                "required": ["category"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_purchase_value",
            "description": "Calculates deterministic score S based on outfit, gap, versatility, style, and redundancy.",
            "parameters": {
                "type": "object",
                "properties": {
                    "outfit_compatibility_score": {"type": "number"},
                    "wardrobe_gap_score": {"type": "number"},
                    "versatility_score": {"type": "number"},
                    "personal_style_score": {"type": "number"},
                    "redundancy_score": {"type": "number"}
                },
                "required": ["outfit_compatibility_score", "wardrobe_gap_score", "versatility_score", "personal_style_score", "redundancy_score"]
            }
        }
    }
]
