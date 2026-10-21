"""
All 31 Features Implementation
13 BUILD + 18 BACKUP features
All fully executable, deterministic and JSON-serializable
"""

import math
import re
from collections import Counter
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np
import logging

logger = logging.getLogger(__name__)

# ============================================================================
# DOMAIN KNOWLEDGE
# ============================================================================

NEUTRAL_COLORS = {"black", "white", "gray", "grey", "navy", "beige", "cream", "khaki", "tan", "brown", "denim", "charcoal"}

# Approximate hue (degrees) for color-wheel harmony checks
COLOR_HUES = {
    "red": 0, "burgundy": 345, "maroon": 350, "coral": 16, "salmon": 10, "peach": 25,
    "orange": 30, "gold": 45, "yellow": 55, "lime": 90, "olive": 70, "green": 120,
    "forest green": 130, "emerald": 140, "mint": 150, "teal": 180, "turquoise": 175,
    "blue": 220, "cobalt": 215, "royal blue": 225, "purple": 280, "lavender": 270, "pink": 330,
}

MATERIAL_QUALITY = {
    "silk": 90, "wool": 88, "leather": 90, "linen": 82, "suede": 80, "cotton": 75, "denim": 78,
    "hemp": 74, "bamboo": 72, "jersey": 65, "viscose": 60, "rayon": 58, "blend": 60,
    "fleece": 62, "nylon": 60, "spandex": 55, "polyester": 55, "acrylic": 50,
}

MATERIAL_SUSTAINABILITY = {
    "hemp": 92, "linen": 88, "bamboo": 75, "wool": 72, "cotton": 60, "silk": 62, "denim": 55,
    "leather": 45, "suede": 45, "viscose": 50, "rayon": 48, "blend": 45, "jersey": 50,
    "fleece": 35, "nylon": 30, "spandex": 30, "polyester": 28, "acrylic": 25,
}

LUXURY_BRANDS = {"gucci", "prada", "chanel", "louis vuitton", "dior", "versace", "dolce & gabbana", "armani",
                 "burberry", "ferragamo", "louboutin", "manolo blahnik", "jimmy choo", "arc'teryx"}
PREMIUM_BRANDS = {"ralph lauren", "tommy hilfiger", "calvin klein", "patagonia", "north face", "levi's",
                  "lululemon", "allsaints", "rag & bone", "michael kors", "coach", "brooks brothers",
                  "j.crew", "reformation", "madewell", "timberland", "dr. martens", "birkenstock"}

TIMELESS_STYLES = {"classic", "minimalist", "business", "preppy", "casual"}
TREND_STYLES = {"trendy", "streetwear", "edgy", "bohemian"}

SEASON_COMPAT = {
    "spring": {"spring", "all-season"},
    "summer": {"summer", "all-season", "spring"},
    "fall": {"fall", "all-season", "winter"},
    "winter": {"winter", "all-season", "fall"},
}

EVENT_PROFILES = {
    "wedding": {"styles": {"formal", "classic", "romantic", "luxury"}, "use_cases": {"party", "dinner", "date night"}},
    "interview": {"styles": {"business", "formal", "classic", "minimalist"}, "use_cases": {"office"}},
    "office": {"styles": {"business", "classic", "minimalist", "preppy"}, "use_cases": {"office", "work from home"}},
    "party": {"styles": {"trendy", "edgy", "luxury", "romantic"}, "use_cases": {"party", "date night", "dinner"}},
    "date": {"styles": {"romantic", "trendy", "classic"}, "use_cases": {"date night", "dinner"}},
    "gym": {"styles": {"sporty", "athletic"}, "use_cases": {"gym", "workout", "running", "yoga"}},
    "hiking": {"styles": {"sporty", "athletic"}, "use_cases": {"hiking", "travel"}},
    "beach": {"styles": {"casual", "bohemian"}, "use_cases": {"beach", "travel", "weekend"}},
    "casual": {"styles": {"casual", "streetwear", "minimalist"}, "use_cases": {"casual", "weekend", "everyday"}},
}

SIZE_ORDER = ["XXS", "XS", "S", "M", "L", "XL", "XXL", "XXXL"]

TOPS = {"shirts", "dresses"}
BOTTOMS = {"pants"}


def _s(value) -> str:
    """Safe lowercase string"""
    return str(value).strip().lower() if value is not None else ""


def _color(item: Dict) -> str:
    return _s(item.get("color") or item.get("primary_color"))


def _price(item: Dict) -> float:
    try:
        return float(item.get("price") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _hue_distance(c1: str, c2: str) -> Optional[float]:
    if c1 not in COLOR_HUES or c2 not in COLOR_HUES:
        return None
    d = abs(COLOR_HUES[c1] - COLOR_HUES[c2]) % 360
    return min(d, 360 - d)

# ============================================================================
# BUILD FEATURES (1-13)
# ============================================================================

class FeatureSet:
    """All 31 features implementation"""

    # Injected at startup by main.py (needed by image & market features)
    image_processor = None
    catalog: List[Dict] = []

    # --------
    # FEATURE 1: Visual Similarity Detection
    # --------

    @staticmethod
    def feature_1_visual_similarity(embedding1: List[float], embedding2: List[float]) -> float:
        """
        Feature 1: Visual Similarity Detection
        Cosine similarity of CLIP embeddings (0-1)
        """
        try:
            emb1 = np.asarray(embedding1, dtype=np.float32)
            emb2 = np.asarray(embedding2, dtype=np.float32)
            if emb1.shape != emb2.shape or emb1.size == 0:
                return 0.0
            cosine = float(np.dot(emb1, emb2) / ((np.linalg.norm(emb1) * np.linalg.norm(emb2)) + 1e-8))
            return float(np.clip(cosine, 0, 1))
        except Exception as e:
            logger.error(f"Feature 1 error: {e}")
            return 0.0

    # --------
    # FEATURE 2: Similarity Score (0-100)
    # --------

    @staticmethod
    def feature_2_similarity_score(
        visual_sim: float,
        color_match: bool,
        style_match: bool,
        material_match: bool,
        color_known: bool = True,
        material_known: bool = True,
    ) -> int:
        """
        Feature 2: Similarity Score (0-100)
        Converts visual similarity + attribute matches into a 0-100 score.
        An attribute missing on either item (frequent for real products) is neutral: its points
        follow the visual evidence instead of counting as a mismatch.
        """
        visual = float(visual_sim)
        score = visual * 65
        score += (12 if color_match else 0) if color_known else 12 * visual
        score += 13 if style_match else 0
        score += (10 if material_match else 0) if material_known else 10 * visual
        return int(np.clip(round(score), 0, 100))

    # --------
    # FEATURE 3: Attribute Comparison
    # --------

    @staticmethod
    def feature_3_attribute_comparison(item1: Dict, item2: Dict) -> Dict:
        """
        Feature 3: Attribute-based Comparison
        Compare color, style, material, use_case, category
        """
        result = {
            "color_match": _color(item1) == _color(item2) != "",
            "style_match": _s(item1.get("style")) == _s(item2.get("style")) != "",
            "material_match": _s(item1.get("material")) == _s(item2.get("material")) != "",
            "use_case_match": _s(item1.get("use_case")) == _s(item2.get("use_case")) != "",
            "category_match": _s(item1.get("category")) == _s(item2.get("category")) != "",
        }
        result["match_ratio"] = round(sum(result.values()) / len(result), 2)
        result["color_known"] = _color(item1) not in ("", "unknown") and _color(item2) not in ("", "unknown")
        result["material_known"] = _s(item1.get("material")) not in ("", "unknown") and _s(item2.get("material")) not in ("", "unknown")
        return result

    # --------
    # FEATURE 4: Similar Items Retrieval
    # --------

    @staticmethod
    def feature_4_similar_items_retrieval(
        new_item_embedding: List[float],
        wardrobe_items: List[Dict],
        threshold: float = 0.6,
        top_k: int = 5
    ) -> List[Dict]:
        """
        Feature 4: Similar Items Retrieval
        Vector search over wardrobe items that carry an 'embedding'
        """
        similar = []
        for item in wardrobe_items:
            if item.get("embedding"):
                similarity = FeatureSet.feature_1_visual_similarity(new_item_embedding, item["embedding"])
                if similarity >= threshold:
                    similar.append({"item_id": item.get("id"), "name": item.get("name"), "similarity": round(similarity, 4)})

        similar.sort(key=lambda x: x["similarity"], reverse=True)
        return similar[:top_k]

    # --------
    # FEATURE 5: Redundancy Score
    # --------

    @staticmethod
    def feature_5_redundancy_score(
        visual_redundancy: float,
        functional_redundancy: float,
        category_saturation: float,
        outfit_contribution: float
    ) -> int:
        """
        Feature 5: Redundancy Score (0-100)
        4-factor weighted formula: visual 40%, functional 30%, saturation 20%, (100 - outfit contribution) 10%
        """
        score = (
            float(visual_redundancy) * 0.4 +
            float(functional_redundancy) * 0.3 +
            float(category_saturation) * 0.2 +
            (100 - float(outfit_contribution)) * 0.1
        )
        return int(np.clip(round(score), 0, 100))

    # --------
    # FEATURE 6: Camera / In-Store Scan
    # --------

    @staticmethod
    def feature_6_camera_scan(image_base64: str) -> Dict:
        """
        Feature 6: Camera / In-Store Scan
        Analyze a camera frame (base64 / data URL) with CLIP
        """
        if FeatureSet.image_processor is None:
            return {"status": "error", "error": "Image processor not initialized"}
        result = FeatureSet.image_processor.process_image(image_base64)
        result.pop("embedding_full", None)
        return {"capture_method": "camera", "timestamp": datetime.now().isoformat(), **result}

    # --------
    # FEATURE 7: Screenshot Analysis
    # --------

    @staticmethod
    def feature_7_screenshot_analysis(screenshot_data: str, page_text: str = "") -> Dict:
        """
        Feature 7: Screenshot Analysis
        Visual attributes from a shopping screenshot + price/brand/material parsed from page text
        """
        visual = {}
        if screenshot_data and FeatureSet.image_processor is not None:
            visual = FeatureSet.image_processor.process_image(screenshot_data)
            visual.pop("embedding_full", None)

        text = page_text or ""
        price_match = re.search(r"(?:[$€£]\s?(\d+(?:[.,]\d{2})?))|(?:(\d+(?:[.,]\d{2})?)\s?(?:€|eur|usd|\$))", text, re.I)
        price = None
        if price_match:
            price = float((price_match.group(1) or price_match.group(2)).replace(",", "."))

        lower = text.lower()
        brands = {p.get("brand") for p in FeatureSet.catalog if p.get("brand")}
        brand = next((b for b in sorted(brands, key=len, reverse=True) if b.lower() in lower), None)
        material = next((m for m in MATERIAL_QUALITY if re.search(rf"\b{re.escape(m)}\b", lower)), None)
        color = next((c for c in list(COLOR_HUES) + sorted(NEUTRAL_COLORS) if re.search(rf"\b{re.escape(c)}\b", lower)), None)

        attributes = visual.get("attributes", {}) if visual else {}
        return {
            "status": "extracted" if (visual.get("status") == "success" or text) else "no_input",
            "visual_analysis": visual or None,
            "text_recognized": bool(text),
            "attributes_extracted": {
                "brand": brand,
                "price": price,
                "color": color or attributes.get("primary_color"),
                "material": material or attributes.get("material_appearance"),
                "category": attributes.get("category"),
            },
        }

    # --------
    # FEATURE 8: Outfit Contribution
    # --------

    @staticmethod
    def feature_8_outfit_contribution(
        wardrobe_items: List[Dict],
        new_item: Dict,
        similar_items: List[Dict]
    ) -> float:
        """
        Feature 8: Outfit Contribution Check
        How much new outfit potential the item adds (0-100)
        """
        contribution = 100.0

        # Each strongly similar owned item removes value
        for item in similar_items:
            contribution -= 25 * float(item.get("similarity", 0.5))

        if wardrobe_items:
            colors = [_color(i) for i in wardrobe_items if _color(i)]
            if colors:
                most_common_color = Counter(colors).most_common(1)[0][0]
                if _color(new_item) == most_common_color:
                    contribution -= 15

            # Bonus if it pairs with categories already owned (e.g. a top when you own bottoms)
            categories = {_s(i.get("category")) for i in wardrobe_items}
            category = _s(new_item.get("category"))
            if category in TOPS and categories & BOTTOMS:
                contribution += 10
            elif category in BOTTOMS and categories & TOPS:
                contribution += 10

            if category not in categories:
                contribution += 10  # fills a gap

        return float(np.clip(contribution, 0, 100))

    # --------
    # FEATURE 9: Category Saturation
    # --------

    @staticmethod
    def feature_9_category_saturation(
        wardrobe_items: List[Dict],
        new_item_category: str,
        saturation_limit: int = 5
    ) -> float:
        """
        Feature 9: Category Saturation
        Owned items in this category relative to a healthy limit (default 5) - 0-100
        """
        if not wardrobe_items:
            return 0.0
        count = sum(1 for item in wardrobe_items if _s(item.get("category")) == _s(new_item_category))
        return float(min(count / max(saturation_limit, 1) * 100, 100.0))

    # --------
    # FEATURE 10: User Override / Feedback
    # --------

    @staticmethod
    def feature_10_user_feedback(
        item_id: str,
        feedback_type: str,
        rating: int,
        comment: str = ""
    ) -> Dict:
        """
        Feature 10: User Feedback Recording
        Validate and normalize user feedback (persisted by the API)
        """
        return {
            "item_id": item_id,
            "feedback_type": feedback_type,
            "rating": max(0, min(5, int(rating))),  # 0-5 stars
            "comment": comment,
            "recorded_at": datetime.now().isoformat(),
            "status": "recorded"
        }

    # --------
    # FEATURE 11: Duplicate Purchase Warning
    # --------

    @staticmethod
    def feature_11_duplicate_warning(
        redundancy_score: int,
        similar_items: List[Dict],
        recommendation: str,
        lang: str = "en"
    ) -> Dict:
        """
        Feature 11: Duplicate Purchase Warning
        Explicit alert for redundant items
        """
        fr = lang == "fr"
        closest = similar_items[0]['name'] if similar_items else ("vos pièces" if fr else "existing items")
        warning_level = "none"
        message = "Aucun doublon détecté" if fr else "No duplicate detected"

        if redundancy_score >= 80:
            warning_level = "critical"
            message = (f"⚠️ Quasi identique à « {closest} »" if fr
                       else f"⚠️ CRITICAL: This item is nearly identical to {closest}")
        elif redundancy_score >= 60:
            warning_level = "high"
            message = "⚠️ Forte redondance avec votre garde-robe" if fr else "⚠️ HIGH REDUNDANCY: Similar to existing items"
        elif redundancy_score >= 40:
            warning_level = "moderate"
            message = "Des pièces similaires existent déjà" if fr else "Consider: Similar items exist in your wardrobe"

        return {
            "warning_level": warning_level,
            "message": message,
            "redundancy_score": redundancy_score,
            "recommendation": recommendation
        }

    # --------
    # FEATURE 12: Explain Redundancy
    # --------

    @staticmethod
    def feature_12_explain_redundancy(
        item_name: str,
        redundancy_score: int,
        similar_items: List[Dict],
        recommendation: str,
        lang: str = "en"
    ) -> str:
        """
        Feature 12: Explain the Redundancy
        Rule-based explanation (Claude can rewrite it, see llm_client.py)
        """
        if lang == "fr":
            verdicts = {"buy": "un bon achat", "consider": "à réfléchir", "skip": "probablement inutile"}
            verdict = verdicts.get(_s(recommendation), _s(recommendation))
            if not similar_items:
                return (f"{item_name} : {verdict}. Rien de similaire dans votre garde-robe "
                        f"(score de redondance {redundancy_score}/100) — il apporte de la nouveauté.")
            text = f"{item_name} : {verdict}.\n\nVous possédez déjà {len(similar_items)} pièce(s) proche(s) :\n"
            for item in similar_items[:3]:
                text += f"  • {item['name']} (similarité {item['similarity']:.0%})\n"
            text += f"\nScore de redondance {redundancy_score}/100 : "
            text += ("quasi identique à ce que vous avez." if redundancy_score >= 80 else
                     "chevauchement important avec votre garde-robe." if redundancy_score >= 60 else
                     "un peu de chevauchement — vérifiez qu'il apporte un nouvel usage." if redundancy_score >= 35 else
                     "peu de chevauchement — il ajoute de la variété.")
            return text

        verdicts = {"buy": "a good purchase", "consider": "worth thinking twice about", "skip": "probably one to skip"}
        verdict = verdicts.get(_s(recommendation), _s(recommendation))

        if not similar_items:
            return (f"{item_name} looks {verdict}: nothing similar was found in your wardrobe "
                    f"(redundancy score {redundancy_score}/100).")

        explanation = f"{item_name} is {verdict}.\n\nWhy: you already own {len(similar_items)} similar item(s):\n"
        for item in similar_items[:3]:
            explanation += f"  • {item['name']} (similarity: {item['similarity']:.0%})\n"

        explanation += f"\nThe redundancy score of {redundancy_score}/100 indicates "
        if redundancy_score >= 80:
            explanation += "this is nearly identical to items you already have."
        elif redundancy_score >= 60:
            explanation += "it overlaps significantly with your current wardrobe."
        elif redundancy_score >= 35:
            explanation += "some overlap - consider whether it adds a new use."
        else:
            explanation += "low overlap - it adds variety."

        return explanation

    # --------
    # FEATURE 13: Alternative From Wardrobe
    # --------

    @staticmethod
    def feature_13_alternatives(
        new_item: Dict,
        similar_items: List[Dict],
        lang: str = "en"
    ) -> List[Dict]:
        """
        Feature 13: Suggest Existing Alternatives
        Recommend owned items that already cover the need
        """
        if lang == "fr":
            tips_fr = {
                "shirts": "Portez-le sous une veste ou un pull pour changer le look",
                "pants": "Associez-le à un haut contrasté et d'autres chaussures",
                "dresses": "Ajoutez une ceinture ou une veste pour une nouvelle silhouette",
                "shoes": "Alternez-les avec d'autres tenues pour varier",
                "outerwear": "Changez la pièce du dessous pour une tenue neuve",
                "accessories": "Associez-le à une nouvelle couleur d'accent",
            }
            tip = tips_fr.get(_s(new_item.get("category")), "Essayez de le porter autrement")
            return [{"item": item, "reason": f"Remplit déjà ce rôle ({item.get('similarity', 0):.0%} similaire)",
                     "styling_tip": tip} for item in similar_items[:3]]

        tips = {
            "shirts": "Layer it under a blazer or knit to change the look",
            "pants": "Pair it with a contrasting top and different shoes",
            "dresses": "Add a belt or a jacket for a new silhouette",
            "shoes": "Rotate it with different socks/outfits to extend its use",
            "outerwear": "Wear it over a different base layer for a fresh outfit",
            "accessories": "Combine it with a new color accent",
        }
        tip = tips.get(_s(new_item.get("category")), "Try styling it differently for variety")

        alternatives = []
        for item in similar_items[:3]:
            alternatives.append({
                "item": item,
                "reason": f"Already serves the same purpose ({item.get('similarity', 0):.0%} similar)",
                "styling_tip": tip
            })
        return alternatives

    # ============================================================================
    # BACKUP FEATURES (14-31)
    # ============================================================================

    @staticmethod
    def feature_14_advanced_recommendations(wardrobe: List[Dict]) -> List[Dict]:
        """Feature 14: Advanced Recommendations - wardrobe gap analysis"""
        # dresses are optional (not every wardrobe needs one) -> never reported as a gap
        targets = {"shirts": 5, "pants": 4, "shoes": 3, "outerwear": 2, "accessories": 3, "dresses": 0}
        counts = Counter(_s(i.get("category")) for i in wardrobe)
        recs = []
        for category, target in targets.items():
            have = counts.get(category, 0)
            if target == 0:
                continue
            if have < target:
                recs.append({"type": "gap", "category": category, "have": have, "target": target,
                             "priority": round((target - have) / target, 2),
                             "advice": f"Add {target - have} {category} item(s)"})
            elif have > target * 2:
                recs.append({"type": "excess", "category": category, "have": have, "target": target,
                             "priority": 0.0, "advice": f"Avoid buying more {category}"})

        neutrals = sum(1 for i in wardrobe if _color(i) in NEUTRAL_COLORS)
        if wardrobe and neutrals / len(wardrobe) < 0.4:
            recs.append({"type": "color", "advice": "Add neutral basics (black, white, navy, beige) to increase outfit combinations",
                         "priority": 0.6})
        return sorted(recs, key=lambda r: r["priority"], reverse=True)

    @staticmethod
    def feature_15_multi_wardrobe_analysis(wardrobes: List[List[Dict]]) -> Dict:
        """Feature 15: Multi-Wardrobe Analysis - overlap between several wardrobes (e.g. a household)"""
        signatures = [{(_s(i.get("category")), _color(i)) for i in w} for w in wardrobes]
        shared = set.intersection(*signatures) if signatures else set()
        return {
            "wardrobes_analyzed": len(wardrobes),
            "total_items": sum(len(w) for w in wardrobes),
            "shared_item_types": [{"category": c, "color": col} for c, col in sorted(shared)],
            "overlap_ratio": round(len(shared) / max(len(set.union(*signatures)), 1), 2) if signatures else 0.0,
        }

    @staticmethod
    def feature_16_seasonal_rotation(wardrobe: List[Dict], season: str) -> Dict:
        """Feature 16: Seasonal Rotation - what to wear vs store"""
        season = _s(season)
        compatible = SEASON_COMPAT.get(season, {season, "all-season"})
        wear = [i.get("name") for i in wardrobe if _s(i.get("season") or "all-season") in compatible]
        store = [i.get("name") for i in wardrobe if _s(i.get("season") or "all-season") not in compatible]
        return {"season": season, "items_for_season": len(wear), "wear": wear, "store": store}

    @staticmethod
    def feature_17_color_harmony(colors: List[str]) -> Dict:
        """Feature 17: Color Harmony Detection (neutrals, analogous, complementary)"""
        colors = [_s(c) for c in colors if c]
        accents = [c for c in colors if c not in NEUTRAL_COLORS]
        pairs = []
        score_total, n = 0.0, 0
        for i in range(len(accents)):
            for j in range(i + 1, len(accents)):
                d = _hue_distance(accents[i], accents[j])
                if d is None:
                    continue
                if d <= 40:
                    relation, score = "analogous", 0.9
                elif 150 <= d <= 210:
                    relation, score = "complementary", 0.8
                elif 100 <= d <= 140:
                    relation, score = "triadic", 0.7
                else:
                    relation, score = "clashing", 0.35
                pairs.append({"colors": [accents[i], accents[j]], "relation": relation})
                score_total += score
                n += 1
        harmony = score_total / n if n else 1.0  # only neutrals / single accent = always harmonious
        if len(accents) > 3:
            harmony -= 0.1 * (len(accents) - 3)
        harmony = float(np.clip(harmony, 0, 1))
        return {"colors": colors, "neutrals": [c for c in colors if c in NEUTRAL_COLORS], "pairs": pairs,
                "harmony_score": round(harmony, 2),
                "verdict": "good" if harmony >= 0.7 else "needs_care" if harmony >= 0.5 else "problematic"}

    @staticmethod
    def feature_18_style_consistency(wardrobe: List[Dict]) -> Dict:
        """Feature 18: Style Consistency (1 = one coherent style, 0 = every item a different style)"""
        styles = [_s(i.get("style")) for i in wardrobe if i.get("style")]
        if len(styles) < 2:
            return {"consistency": 1.0, "dominant_style": styles[0] if styles else None, "distribution": dict(Counter(styles))}
        counts = Counter(styles)
        probs = np.array(list(counts.values()), dtype=float) / len(styles)
        entropy = -float((probs * np.log(probs)).sum())
        max_entropy = math.log(min(len(styles), len(counts))) if len(counts) > 1 else 1.0
        consistency = 1.0 - (entropy / max_entropy if max_entropy else 0.0)
        return {"consistency": round(consistency, 2), "dominant_style": counts.most_common(1)[0][0],
                "distribution": dict(counts)}

    @staticmethod
    def feature_19_budget_optimization(budget: float, wardrobe: List[Dict]) -> Dict:
        """Feature 19: Budget Optimization - allocate budget to wardrobe gaps"""
        gaps = [r for r in FeatureSet.feature_14_advanced_recommendations(wardrobe) if r.get("type") == "gap"]
        weights = {r["category"]: r["priority"] for r in gaps} or {"shirts": 0.3, "pants": 0.3, "shoes": 0.2, "outerwear": 0.2}
        total = sum(weights.values()) or 1.0
        allocation = {c: round(float(budget) * w / total, 2) for c, w in weights.items()}
        excess = [r["category"] for r in FeatureSet.feature_14_advanced_recommendations(wardrobe) if r.get("type") == "excess"]
        return {"budget": float(budget), "recommended_allocation": allocation, "avoid_categories": excess,
                "current_wardrobe_value": round(sum(_price(i) for i in wardrobe), 2)}

    @staticmethod
    def feature_20_trend_analysis(item: Dict) -> Dict:
        """Feature 20: Trend Analysis - trendy vs timeless"""
        style, color = _s(item.get("style")), _color(item)
        timeless = 0.5
        timeless += 0.25 if style in TIMELESS_STYLES else -0.2 if style in TREND_STYLES else 0
        timeless += 0.2 if color in NEUTRAL_COLORS else -0.1
        timeless = float(np.clip(timeless, 0, 1))
        return {"item": item.get("name"), "timeless_score": round(timeless, 2), "trend_score": round(1 - timeless, 2),
                "timeless": timeless >= 0.6, "wearable_in_2_years": timeless >= 0.5}

    @staticmethod
    def feature_21_event_planning(wardrobe: List[Dict], event_type: str) -> Dict:
        """Feature 21: Event Planning - pick owned items suitable for an event"""
        profile = EVENT_PROFILES.get(_s(event_type), EVENT_PROFILES["casual"])
        scored = []
        for item in wardrobe:
            score = (2 if _s(item.get("style")) in profile["styles"] else 0) + (1 if _s(item.get("use_case")) in profile["use_cases"] else 0)
            if score:
                scored.append({"item": item.get("name"), "category": item.get("category"), "suitability": score})
        scored.sort(key=lambda x: x["suitability"], reverse=True)
        return {"event_type": event_type, "suitable_items": scored[:6],
                "missing": [] if scored else [f"Nothing suitable - consider a {sorted(profile['styles'])[0]} piece"]}

    @staticmethod
    def feature_22_personal_brand(wardrobe: List[Dict]) -> Dict:
        """Feature 22: Personal Brand Development - signature style & palette"""
        styles = Counter(_s(i.get("style")) for i in wardrobe if i.get("style"))
        colors = Counter(_color(i) for i in wardrobe if _color(i))
        consistency = FeatureSet.feature_18_style_consistency(wardrobe)["consistency"]
        recs = []
        if consistency < 0.5:
            recs.append("Your wardrobe mixes many styles - choose 1-2 signature styles")
        if colors and len(colors) > 6:
            recs.append("Narrow your palette to 3 base colors + 2 accents")
        return {"brand_style": styles.most_common(1)[0][0] if styles else None,
                "signature_colors": [c for c, _ in colors.most_common(3)],
                "consistency": consistency, "recommendations": recs}

    @staticmethod
    def feature_23_quality_assessment(item: Dict) -> Dict:
        """Feature 23: Quality Assessment (0-100) from material, durability and price point"""
        material_score = MATERIAL_QUALITY.get(_s(item.get("material")), 60)
        durability = item.get("durability_score")
        price = _price(item)
        score = material_score * 0.6
        score += (float(durability) * 100 if durability is not None else 65) * 0.3
        score += min(price / 200, 1.0) * 100 * 0.1 if price else 5
        score = int(round(np.clip(score, 0, 100)))
        return {"item": item.get("name"), "quality_score": score, "material_score": material_score,
                "value_for_money": round(score / max(price, 1) * 10, 2) if price else None}

    @staticmethod
    def feature_24_sustainability_tracking(item: Dict) -> Dict:
        """Feature 24: Sustainability Tracking (0-100)"""
        material_score = MATERIAL_SUSTAINABILITY.get(_s(item.get("material")), 45)
        rating = item.get("sustainability_rating")
        durability = item.get("durability_score")
        score = material_score * 0.5
        score += (float(rating) * 100 if rating is not None else 50) * 0.3
        score += (float(durability) * 100 if durability is not None else 60) * 0.2
        score = int(round(np.clip(score, 0, 100)))
        tips = []
        if material_score < 40:
            tips.append("Synthetic material - look for recycled or natural fibers")
        tips.append("Buying second-hand avoids most of the footprint")
        return {"item": item.get("name"), "sustainability_score": score, "material_score": material_score, "tips": tips}

    @staticmethod
    def feature_25_resale_value(item: Dict) -> Dict:
        """Feature 25: Resale Value Estimation"""
        price = _price(item)
        brand = _s(item.get("brand"))
        ratio = 0.6 if brand in LUXURY_BRANDS else 0.4 if brand in PREMIUM_BRANDS else 0.25
        condition = _s(item.get("condition") or "good")
        ratio *= {"new": 1.1, "good": 1.0, "fair": 0.7, "worn": 0.4}.get(condition, 1.0)
        return {"original_price": price, "estimated_resale": round(price * ratio, 2), "resale_ratio": round(ratio, 2),
                "brand_tier": "luxury" if brand in LUXURY_BRANDS else "premium" if brand in PREMIUM_BRANDS else "mass-market"}

    @staticmethod
    def feature_26_capsule_builder(wardrobe: List[Dict], size: int = 10) -> Dict:
        """Feature 26: Capsule Wardrobe Builder - most versatile items per category"""
        quotas = {"shirts": 3, "pants": 2, "shoes": 2, "outerwear": 1, "accessories": 1, "dresses": 1}

        def versatility(i: Dict) -> int:
            return (2 if _color(i) in NEUTRAL_COLORS else 0) + (1 if _s(i.get("style")) in TIMELESS_STYLES else 0) + \
                   (1 if _s(i.get("season") or "all-season") == "all-season" else 0)

        capsule = []
        for category, quota in quotas.items():
            items = sorted([i for i in wardrobe if _s(i.get("category")) == category], key=versatility, reverse=True)
            capsule.extend({"name": i.get("name"), "category": category, "versatility": versatility(i)} for i in items[:quota])
        return {"capsule": capsule[:size], "size": len(capsule[:size]),
                "missing_categories": [c for c in quotas if not any(_s(i.get("category")) == c for i in wardrobe)]}

    @staticmethod
    def feature_27_outfit_matching(items: List[Dict], max_outfits: int = 5) -> List[Dict]:
        """Feature 27: Outfit Matching - top + bottom (+ shoes) combos ranked by color harmony"""
        by_cat = {c: [i for i in items if _s(i.get("category")) == c] for c in ("shirts", "pants", "shoes", "dresses")}
        outfits = []
        bases = [[t, b] for t in by_cat["shirts"] for b in by_cat["pants"]] + [[d] for d in by_cat["dresses"]]
        for base in bases:
            for shoe in (by_cat["shoes"] or [None]):
                pieces = base + ([shoe] if shoe else [])
                harmony = FeatureSet.feature_17_color_harmony([_color(p) for p in pieces])["harmony_score"]
                outfits.append({"pieces": [p.get("name") for p in pieces], "harmony_score": harmony})
        outfits.sort(key=lambda o: o["harmony_score"], reverse=True)
        return outfits[:max_outfits]

    @staticmethod
    def feature_28_size_optimization(item: Dict, user_size: str, fit_preference: str = "regular") -> Dict:
        """Feature 28: Size Optimization - adjust size for fit preference & availability"""
        size = _s(user_size).upper()
        available = [str(s).upper() for s in (item.get("size_range") or [])]
        recommended = size
        if size in SIZE_ORDER:
            idx = SIZE_ORDER.index(size)
            if _s(fit_preference) == "oversized" and idx + 1 < len(SIZE_ORDER):
                recommended = SIZE_ORDER[idx + 1]
            elif _s(fit_preference) == "slim" and _s(item.get("material")) in {"spandex", "jersey"} and idx > 0:
                recommended = SIZE_ORDER[idx - 1]
        in_stock = (recommended in available) if available else None
        return {"item": item.get("name"), "user_size": size, "recommended_size": recommended,
                "fit_preference": fit_preference, "available": in_stock,
                "fit_score": 0.9 if in_stock in (True, None) else 0.4}

    @staticmethod
    def feature_29_care_recommendations(item: Dict) -> List[str]:
        """Feature 29: Care Recommendations"""
        material = _s(item.get("material"))
        care = {
            "silk": ["Hand wash with silk detergent", "Air dry flat", "Iron on low heat"],
            "wool": ["Dry clean or hand wash cold", "Never use hot water", "Lay flat to dry"],
            "leather": ["Wipe with a damp cloth", "Condition every 3-6 months", "Keep away from heat"],
            "suede": ["Brush regularly", "Spot clean only", "Use a waterproofing spray"],
            "linen": ["Gentle wash", "Hang dry", "Iron while slightly damp"],
            "denim": ["Wash inside out in cold water", "Wash rarely", "Hang dry to keep color"],
        }.get(material, ["Machine wash cold", "Tumble dry low", "Iron as needed"])
        if item.get("care_instructions"):
            care = [item["care_instructions"]] + care
        return care

    @staticmethod
    def feature_30_fashion_score(wardrobe: List[Dict]) -> Dict:
        """Feature 30: Fashion Score (0-100) - variety, color harmony, style coherence"""
        if not wardrobe:
            return {"fashion_score": 0, "variety": 0, "harmony": 0, "consistency": 0}
        variety = len({_s(i.get("category")) for i in wardrobe}) / 6
        harmony = FeatureSet.feature_17_color_harmony(list({_color(i) for i in wardrobe if _color(i)}))["harmony_score"]
        consistency = FeatureSet.feature_18_style_consistency(wardrobe)["consistency"]
        score = int(round((variety * 0.4 + harmony * 0.3 + consistency * 0.3) * 100))
        return {"fashion_score": score, "variety": round(variety, 2), "harmony": harmony, "consistency": consistency}

    @staticmethod
    def feature_31_market_intelligence(item: Dict) -> Dict:
        """Feature 31: Market Intelligence - price position vs the priced products of the catalog"""
        category = _s(item.get("category"))
        peers = [p for p in FeatureSet.catalog if _s(p.get("category")) == category and p.get("price")]
        if not peers:
            return {"item": item.get("name"), "status": "no_market_data"}
        prices = np.array([float(p["price"]) for p in peers])
        price = _price(item)
        percentile = float((prices < price).mean() * 100) if price else None
        same_color = sum(1 for p in peers if _color(p) == _color(item))
        return {
            "item": item.get("name"),
            "category": category,
            "market_items": len(peers),
            "price_stats": {"min": float(prices.min()), "median": float(np.median(prices)),
                            "mean": round(float(prices.mean()), 2), "max": float(prices.max())},
            "price_percentile": round(percentile, 1) if percentile is not None else None,
            "price_position": None if percentile is None else "budget" if percentile < 33 else "mid-range" if percentile < 66 else "premium",
            "same_color_offers": same_color,
            "demand_level": "high" if same_color > len(peers) * 0.05 else "moderate",
        }

    # ============================================================================
    # FEATURE REGISTRY
    # ============================================================================

    @staticmethod
    def get_feature(feature_id: int):
        """Get feature by ID"""
        return getattr(FeatureSet, FEATURE_METHODS.get(feature_id, ""), None)

    @staticmethod
    def get_all_features() -> Dict:
        """Get all feature metadata"""
        features = {}
        for i in range(1, 32):
            func = FeatureSet.get_feature(i)
            doc = (func.__doc__ or f"Feature {i}").strip().splitlines()
            features[f"Feature {i}"] = {
                "id": i,
                "type": "build" if i <= 13 else "backup",
                "function": FEATURE_METHODS[i],
                "title": doc[0].strip().split(": ", 1)[-1],
                "description": " ".join(line.strip() for line in doc),
            }
        return features


FEATURE_METHODS = {
    int(name.split("_")[1]): name
    for name in dir(FeatureSet)
    if name.startswith("feature_") and name.split("_")[1].isdigit()
}
assert sorted(FEATURE_METHODS) == list(range(1, 32)), "All 31 features must be registered"
