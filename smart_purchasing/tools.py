"""All 5 specialized tools for the Purchase Agent in a single, clean module.

Tools:
1. analyze_item           -> Vision analysis & attribute extraction
2. find_similar_items      -> Wardrobe retrieval & redundancy check
3. generate_outfits        -> Outfit generation & compatibility ranking
4. analyze_wardrobe_gaps   -> Closet gap & coverage analysis
5. calculate_purchase_value -> Deterministic purchase scoring formula
"""

import os
import sys
import re
import hashlib
from pathlib import Path
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

try:
    from ml_model import predict_purchase_ml, get_ml_classifier
except ImportError:
    from smart_purchasing.ml_model import predict_purchase_ml, get_ml_classifier

try:
    from vision_model import get_vision_model, DressMeVisionModel
except ImportError:
    from smart_purchasing.vision_model import get_vision_model, DressMeVisionModel

# Teammates' Integration Paths (Redundancy, Recommendation BO4, Gap Analysis BO3)
ROOT_DIR = Path(__file__).resolve().parent.parent
for subpath in [
    ROOT_DIR / "bo4" / "backend",
    ROOT_DIR / "purchase-redundancy-ai" / "backend",
    ROOT_DIR / "DressMe UI Blueprint" / "backend",
]:
    if subpath.exists() and str(subpath) not in sys.path:
        sys.path.insert(0, str(subpath))

try:
    import outfit_engine
except Exception:
    outfit_engine = None

try:
    from features import FeatureSet
except Exception:
    FeatureSet = None

try:
    from agent import coverage
    import xgboost_ranker
except Exception:
    coverage = None
    xgboost_ranker = None



# =====================================================================
# HELPER: Vision & Embedding Utilities (Powered by dressme_best.pt)
# =====================================================================

def extract_dominant_color(image_path: str) -> str:
    """Extracts dominant garment color using dressme_best.pt pixel segmentation."""
    res = get_vision_model().analyze_garment_image(image_path)
    return res["color"]


def normalize_color(c: Optional[str]) -> str:
    """Normalizes color string into canonical representation to eliminate spacing/underscore discrepancies."""
    if not c:
        return "neutral"
    return ColorSimilarityService.get_instance().normalize_color_name(c)


def compute_color_similarity(color1: str, color2: str) -> float:
    """Computes perceptual color similarity between two colors using CIEDE2000 in [0.0, 1.0]."""
    return ColorSimilarityService.get_instance().get_color_similarity(color1, color2)


def generate_embedding(text_or_path: str, dim: int = 64) -> List[float]:
    """Generates visual feature embedding using dressme_best.pt segmentation."""
    vm = get_vision_model()
    if text_or_path and os.path.exists(text_or_path):
        res = vm.analyze_garment_image(text_or_path)
        return res["embedding"]
    return vm.compute_fallback_embedding(text_or_path or "garment", dim=dim)


def cosine_sim(v1: List[float], v2: List[float]) -> float:
    """Cosine similarity between two vectors."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    norm_a = sum(a * a for a in v1) ** 0.5
    norm_b = sum(b * b for b in v2) ** 0.5
    return max(0.0, min(1.0, dot / (norm_a * norm_b))) if norm_a * norm_b > 0 else 0.0


# =====================================================================
# TOOL 1: analyze_item (Vision / Attribute Extraction via dressme_best.pt)
# =====================================================================

def analyze_item(candidate: CandidateItem) -> Dict[str, Any]:
    """Tool 1: Analyzes garment image using the trained YOLO segmentation model (dressme_best.pt).
    Extracts category, pixel-segmented color, style, seasons, occasions, and visual embeddings.
    """
    vision_model = get_vision_model()
    analysis = vision_model.analyze_garment_image(
        image_path=candidate.image_path,
        hint_name=candidate.name,
        preferred_category=candidate.category if candidate.category not in ["unknown", "auto-detect", ""] else None,
        preferred_color=candidate.color if candidate.color not in ["unknown", "auto-detect", "neutral", ""] else None,
        preferred_style=candidate.style if candidate.style and candidate.style != ["formal"] else None,
        preferred_occasion=candidate.target_occasion or (candidate.occasions[0] if candidate.occasions else None),
    )

    detected_category = analysis["category"]
    detected_color = analysis["color"]
    detected_style = analysis["style"]
    detected_seasons = analysis["seasons"]
    detected_occasions = analysis["occasions"]
    embedding = analysis["embedding"]

    return {
        "id": candidate.id,
        "category": detected_category.lower(),
        "color": detected_color.lower(),
        "detected_rgb": analysis.get("detected_rgb"),
        "color_delta_e": analysis.get("color_delta_e"),
        "style": [s.lower() for s in detected_style],
        "seasons": detected_seasons,
        "occasions": detected_occasions,
        "embedding": embedding,
        "confidence": analysis.get("confidence", 0.0),
        "has_mask": analysis.get("has_mask", False),
        "bbox": analysis.get("bbox"),
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
    
    Integrated with teammate's purchase-redundancy-ai FeatureSet for authoritative
    redundancy scoring, duplicate detection, and explanations.
    """
    cand_cat = candidate.category.lower().strip().replace("-", "_")
    cand_col_norm = normalize_color(candidate.color)

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
        has_strong_subtype_match = bool(shared_subtypes)

        # Teammate's purchase-redundancy-ai FeatureSet scoring
        if FeatureSet is not None:
            raw_sim = FeatureSet.feature_2_similarity_score(
                visual_sim=col_sim if same_category else col_sim * 0.4,
                color_match=same_color,
                style_match=style_overlap > 0.4 or has_strong_subtype_match,
                material_match=False,
                color_known=True,
                material_known=False
            )
            score = raw_sim / 100.0
            if same_category and same_color and has_strong_subtype_match:
                score = max(score, 0.95 + 0.05 * style_overlap)
            elif same_category and same_color:
                score = max(score, 0.88 + 0.12 * style_overlap)
        else:
            if same_category and (same_color or (col_sim >= 0.85 and has_strong_subtype_match)):
                score = (0.95 + 0.05 * style_overlap) if same_color and has_strong_subtype_match else (0.88 + 0.12 * style_overlap) if same_color else (0.80 + 0.15 * col_sim)
            elif same_category:
                score = 0.50 + 0.15 * col_sim + 0.15 * style_overlap
            else:
                related_cat = {
                    ("blazer", "outerwear"): 0.45, ("jacket", "outerwear"): 0.45,
                    ("trousers", "jeans"): 0.45, ("shoes", "sneakers"): 0.65,
                    ("shoes", "sandals"): 0.65, ("t-shirt", "shirt"): 0.40,
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

def _to_bo4_item(g: Any) -> dict:
    color = (getattr(g, "color", None) or "neutral").lower().replace("-", "_").replace(" ", "_")
    cat = (getattr(g, "category", None) or "top").lower().replace("-", "_").replace(" ", "_")
    styles = getattr(g, "style", []) or []
    style = styles[0] if len(styles) > 0 else "casual"
    seasons = getattr(g, "seasons", []) or []
    season = seasons[0] if len(seasons) > 0 else "autumn"
    warmth_val = getattr(g, "warmth_level", None)
    warmth = "medium" if warmth_val is None else ("light" if warmth_val <= 2 else "heavy" if warmth_val >= 4 else "medium")
    return {
        "id": getattr(g, "id", "item"),
        "name": getattr(g, "name", "Garment"),
        "category": cat,
        "color": color,
        "style": style,
        "season": season,
        "warmth": warmth,
    }


def evaluate_outfit_compatibility(
    candidate: CandidateItem,
    items: List[Garment],
    occasion: str = "work",
    season: str = "autumn"
) -> float:
    """Calculates compatibility score (0-100) using teammate's bo4 recommendation outfit engine."""
    if not items:
        return 50.0

    if outfit_engine is not None:
        try:
            cand_dict = _to_bo4_item(candidate)
            paired_dicts = [_to_bo4_item(it) for it in items]
            outfit = [cand_dict] + paired_dicts
            res = outfit_engine.evaluate_outfit(outfit, occasion=occasion, season=season)
            return round(float(res["score"]), 1)
        except Exception:
            pass

    # Fallback heuristic
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
            if g.category in ["trousers", "jeans", "skirt", "shorts", "bottom", "pants"] or "bottom" in g.tags
        ]
        shoes = [
            g for g in wardrobe
            if g.category in ["shoes", "shoe", "sandals", "sneakers", "boots", "loafers"] or "shoes" in g.tags
        ]
        inner_tops = [
            g for g in wardrobe
            if g.category in ["shirt", "t_shirt", "t-shirt", "blouse", "sweater", "top"] or "top" in g.tags
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
            if g.category in ["top", "shirt", "t_shirt", "t-shirt", "blouse", "sweater", "jacket", "coat", "blazer", "outerwear"] or "top" in g.tags or "outerwear" in g.tags
        ]
        shoes = [
            g for g in wardrobe
            if g.category in ["shoes", "shoe", "sandals", "sneakers"] or "shoes" in g.tags
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
    """Tool 4: Identifies whether the item fills an underrepresented wardrobe gap.
    
    Integrated with teammate's BO3 coverage analyzer and XGBoost ranker to identify
    genuine wardrobe deficits for work, casual, or formal goals.
    """
    cat = candidate.category.lower().strip().replace("-", "_")
    cand_norm_color = normalize_color(candidate.color)

    owned_in_cat = [
        g for g in wardrobe
        if are_equivalent_categories(cat, g.category) or (cat in g.tags)
    ]
    owned_norm_colors = {normalize_color(g.color) for g in owned_in_cat}

    gap_score = 75.0
    reasoning = None

    # Check teammate's BO3 coverage and XGBoost ranker
    if coverage is not None:
        try:
            bo3_wardrobe = [
                {
                    "id": g.id,
                    "category": "top" if g.category in ["top", "shirt", "blouse", "sweater", "t_shirt", "t-shirt"]
                               else "bottom" if g.category in ["pants", "trousers", "jeans", "shorts", "skirt"]
                               else "outerwear" if g.category in ["jacket", "coat", "blazer", "raincoat"]
                               else "shoes" if g.category in ["shoes", "sneakers", "sandals", "boots"]
                               else "dress" if g.category == "dress" else "accessory",
                    "subcategory": g.category,
                    "colors": [g.color],
                    "seasons": g.seasons or ["all"],
                }
                for g in wardrobe
            ]
            goal_id = "winter_work" if "work" in (candidate.occasions or []) else "summer_casual" if "summer" in (candidate.seasons or []) else "formal_event" if "formal" in (candidate.occasions or []) else "winter_work"
            cov = coverage.compute_coverage(bo3_wardrobe, goal_id)
            gaps = cov.get("gaps", [])
            if xgboost_ranker is not None and gaps:
                try:
                    ranked = xgboost_ranker.rank_gap_candidates(gaps)
                    for r in ranked:
                        if cat in r.get("id", "").lower() or r.get("name", "").lower() in cat or cat in r.get("name", "").lower():
                            gap_score = 90.0 if r.get("priority") == "high" else 80.0
                            reasoning = f"Fills high-priority gap ({r['name']}) identified by BO3 XGBoost ranker for {goal_id}."
                            break
                except Exception:
                    pass
        except Exception:
            pass

    if reasoning is None:
        if len(owned_in_cat) == 0:
            gap_score = 90.0
            reasoning = f"Essential gap: You currently own zero items in the '{cat}' category."
        elif cand_norm_color in owned_norm_colors:
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
    color_similarity_score: Optional[float] = None,
    ml_decision: Optional[str] = None,
    ml_confidence: Optional[float] = None,
    ml_probabilities: Optional[Dict[str, float]] = None
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
        color_similarity_score=round(color_similarity_score, 4) if color_similarity_score is not None else None,
        ml_decision=ml_decision,
        ml_confidence=round(ml_confidence, 3) if ml_confidence is not None else None,
        ml_probabilities=ml_probabilities
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
            "name": "predict_purchase_ml",
            "description": "Uses trained XGBoost classification model to predict BUY/CONSIDER/SKIP decision probabilities and confidence based on wardrobe feature signals.",
            "parameters": {
                "type": "object",
                "properties": {
                    "outfit_compatibility": {"type": "number"},
                    "wardrobe_gap": {"type": "number"},
                    "redundancy": {"type": "number"},
                    "budget_penalty": {"type": "number"}
                },
                "required": ["outfit_compatibility", "wardrobe_gap", "redundancy"]
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
