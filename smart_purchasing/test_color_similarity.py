"""Unit test suite for Perceptual Color Similarity and Redundancy Integration.

Covers all required user specifications:
1. White vs Ivory: High perceptual color similarity.
2. White vs Cream: Relatively high perceptual color similarity (with White-Ivory > White-Cream).
3. Black vs White: Very low color similarity (high perceptual distance).
4. Navy vs Light Blue: Partial similarity reflecting same hue family with high luminance delta.
5. Cross-category color similarity: Garments with similar colors but different categories
   (e.g., Cream Skirt vs White Shirt) must NOT be classified as redundant.
6. Same-category color similarity: Garments with similar colors and same category/style
   (e.g., Cream Formal Shirt vs White Formal Shirt) correctly trigger redundancy warning.
7. Unknown / Missing color labels: Graceful handling without throwing exceptions.
8. Mathematical correctness: CIELAB conversion and CIEDE2000 symmetry & identity.
"""

import sys
import unittest
from pathlib import Path

# Ensure module path is accessible
current_dir = Path(__file__).resolve().parent
pkg_root = current_dir.parent if current_dir.name == "tests" else current_dir
if str(pkg_root) not in sys.path:
    sys.path.insert(0, str(pkg_root))

from color_similarity import (
    ColorSimilarityService,
    compare_colors,
    compute_color_similarity,
    rgb_to_lab,
    ciede2000,
)
from schemas import CandidateItem, Garment, EvaluatePurchaseRequest
from tools import find_similar_items, analyze_wardrobe_gaps
from agent import PurchaseAgent


class TestPerceptualColorSimilarity(unittest.TestCase):
    """Test suite verifying CIEDE2000 color distance, normalization, and redundancy logic."""

    @classmethod
    def setUpClass(cls):
        cls.service = ColorSimilarityService.get_instance()

    # -----------------------------------------------------------------
    # Requirement 4.1: White versus Ivory (High similarity)
    # -----------------------------------------------------------------
    def test_white_vs_ivory_high_similarity(self):
        res = compare_colors("white", "ivory")
        # Perceptually, ivory is a very subtle off-white tint (Delta E ~ 5.96)
        self.assertLess(res.delta_e, 10.0, f"Delta E too large: {res.delta_e}")
        self.assertGreaterEqual(res.similarity_score, 0.85, f"Similarity too low: {res.similarity_score}")
        self.assertTrue(res.is_same_family)
        self.assertEqual(res.family1, "white")
        self.assertEqual(res.family2, "white")

    # -----------------------------------------------------------------
    # Requirement 4.2: White versus Cream (Relatively high similarity)
    # -----------------------------------------------------------------
    def test_white_vs_cream_relatively_high_similarity(self):
        res_cream = compare_colors("white", "cream")
        res_ivory = compare_colors("white", "ivory")

        # Cream is a warmer tint than ivory, but still in the white family (Delta E ~ 7.94)
        self.assertLess(res_cream.delta_e, 15.0, f"Delta E too large: {res_cream.delta_e}")
        self.assertGreaterEqual(res_cream.similarity_score, 0.80, f"Similarity too low: {res_cream.similarity_score}")
        self.assertTrue(res_cream.is_same_family)

        # Ivory should be closer to pure white than cream is
        self.assertGreater(
            res_ivory.similarity_score,
            res_cream.similarity_score,
            "Ivory should have higher similarity to White than Cream does."
        )

    # -----------------------------------------------------------------
    # Requirement 4.3: Black versus White (Low similarity)
    # -----------------------------------------------------------------
    def test_black_vs_white_low_similarity(self):
        res = compare_colors("black", "white")
        # Opposite ends of the L* luminance channel (Delta E ~ 94.36)
        self.assertGreater(res.delta_e, 80.0, f"Delta E too small: {res.delta_e}")
        self.assertLessEqual(res.similarity_score, 0.15, f"Similarity too high: {res.similarity_score}")
        self.assertFalse(res.is_same_family)

    # -----------------------------------------------------------------
    # Requirement 4.4: Navy versus Light Blue (Partial similarity)
    # -----------------------------------------------------------------
    def test_navy_vs_light_blue_partial_similarity(self):
        res = compare_colors("navy", "light_blue")
        # Both are blues, but with heavy luminance contrast (Delta E ~ 74.28)
        self.assertTrue(res.is_same_family, "Both should share the 'blue' family")
        self.assertTrue(
            20.0 <= res.similarity_score * 100.0 <= 45.0,
            f"Expected partial similarity between 20% and 45%, got {res.similarity_score*100:.1f}%"
        )
        self.assertGreater(res.delta_e, 50.0)

    # -----------------------------------------------------------------
    # Requirement 4.5: Cross-category non-redundancy
    # Cream Skirt vs White Shirt: High color similarity, but different categories -> NOT redundant!
    # -----------------------------------------------------------------
    def test_cross_category_similar_colors_not_redundant(self):
        candidate_skirt = CandidateItem(
            name="Pleated Cream Midi Skirt",
            category="skirt",
            color="cream",
            style=["minimalist", "casual"],
            seasons=["spring", "summer"],
            occasions=["work", "casual"]
        )

        owned_wardrobe = [
            Garment(
                id="G_SHIRT_01",
                name="Crisp White Button Shirt",
                category="shirt",
                color="white",
                style=["formal", "workwear"],
                seasons=["all-season"],
                occasions=["work"],
                tags=["top", "shirt"]
            )
        ]

        # 1. Check find_similar_items
        matches = find_similar_items(candidate_skirt, owned_wardrobe)
        for m in matches:
            self.assertFalse(
                m.functional_overlap,
                "A skirt and a shirt must not have functional overlap despite similar colors!"
            )
            self.assertIsNone(
                m.redundancy_warning,
                "A skirt must not trigger a redundancy warning against a shirt!"
            )

        # 2. Check analyze_wardrobe_gaps
        gap = analyze_wardrobe_gaps(candidate_skirt, owned_wardrobe)
        # The user owns zero skirts, so gap_fill_score must be high (90.0) regardless of white shirt
        self.assertEqual(gap.gap_fill_score, 90.0)
        self.assertIn("zero items in the 'skirt' category", gap.reasoning.lower())

    # -----------------------------------------------------------------
    # Requirement 4.5 (Counterpart): Same-category & same-style redundancy
    # Cream Shirt vs White Shirt with matching formal style -> Redundancy detected!
    # -----------------------------------------------------------------
    def test_same_category_similar_colors_triggers_redundancy(self):
        candidate_shirt = CandidateItem(
            name="Classic Cream Oxford Shirt",
            category="shirt",
            color="cream",
            style=["formal", "classic"],
            seasons=["all-season"],
            occasions=["work"]
        )

        owned_wardrobe = [
            Garment(
                id="G_SHIRT_02",
                name="White Oxford Cotton Shirt",
                category="shirt",
                color="white",
                style=["formal", "classic"],
                seasons=["all-season"],
                occasions=["work"],
                tags=["top", "shirt", "oxford", "cotton"]
            )
        ]

        matches = find_similar_items(candidate_shirt, owned_wardrobe)
        self.assertTrue(len(matches) > 0, "Should match the existing shirt")
        top_match = matches[0]

        self.assertTrue(top_match.functional_overlap, "Both are shirts, so functional overlap is True")
        self.assertIsNotNone(top_match.color_similarity)
        self.assertGreaterEqual(top_match.color_similarity, 0.85)
        self.assertIsNotNone(
            top_match.redundancy_warning,
            "Matching category, subtype, and close color shade should trigger a redundancy warning."
        )

    # -----------------------------------------------------------------
    # Requirement 4.6: Graceful handling of unknown / missing colors
    # -----------------------------------------------------------------
    def test_unknown_and_missing_color_labels(self):
        # 1. Unknown custom colors
        res_unknown = compare_colors("cyberpunk_neon_chartreuse", "space_cadet_purple")
        self.assertIsNotNone(res_unknown)
        self.assertFalse(res_unknown.is_same_family)
        self.assertEqual(res_unknown.similarity_score, 0.20)
        self.assertIn("Unrecognized color label", res_unknown.explanation)

        # 2. None / Empty inputs handled gracefully without crashing
        res_empty = compare_colors("", "")
        self.assertIsNotNone(res_empty)
        self.assertIsInstance(res_empty.similarity_score, float)
        self.assertTrue(0.0 <= res_empty.similarity_score <= 1.0)

        sim_none = compute_color_similarity(None, "black")
        self.assertIsInstance(sim_none, float)
        self.assertTrue(0.0 <= sim_none <= 1.0)

    # -----------------------------------------------------------------
    # Color Math & CIEDE2000 Verification
    # -----------------------------------------------------------------
    def test_cielab_conversion_and_ciede2000_properties(self):
        # Pure White: L* should be ~100.0, a* ~ 0.0, b* ~ 0.0
        lab_white = rgb_to_lab((255, 255, 255))
        self.assertAlmostEqual(lab_white[0], 100.0, delta=0.5)
        self.assertAlmostEqual(lab_white[1], 0.0, delta=0.5)
        self.assertAlmostEqual(lab_white[2], 0.0, delta=0.5)

        # Pure Black: L* should be 0.0
        lab_black = rgb_to_lab((0, 0, 0))
        self.assertAlmostEqual(lab_black[0], 0.0, delta=0.5)

        # CIEDE2000 identity: Delta E with itself must be 0.0
        lab_blue = rgb_to_lab((30, 90, 180))
        self.assertEqual(ciede2000(lab_blue, lab_blue), 0.0)

        # CIEDE2000 symmetry: d(A, B) == d(B, A)
        lab_red = rgb_to_lab((200, 30, 30))
        de_ab = ciede2000(lab_blue, lab_red)
        de_ba = ciede2000(lab_red, lab_blue)
        self.assertAlmostEqual(de_ab, de_ba, places=5)

    # -----------------------------------------------------------------
    # Requirement 5: Evaluation evidence surfaces color similarity
    # -----------------------------------------------------------------
    def test_agent_surfaces_color_similarity_in_evidence(self):
        agent = PurchaseAgent()
        cand = CandidateItem(
            name="Cream Tailored Blazer",
            category="jacket",
            color="cream",
            style=["formal", "classic"],
            price=120.0,
            budget=150.0
        )
        req = EvaluatePurchaseRequest(
            candidate=cand,
            user_query="Should I buy this cream blazer?"
        )
        rec = agent.evaluate(req, skip_llm=True)

        self.assertIsNotNone(rec.similar_items)
        if rec.similar_items:
            first_match = rec.similar_items[0]
            self.assertIsNotNone(first_match.color_similarity)
            self.assertIsNotNone(first_match.color_delta_e)

        # Check evidence contains color analysis
        has_color_ev = any("color analysis" in ev.lower() for ev in rec.evidence)
        if rec.similar_items:
            self.assertTrue(has_color_ev, "Evidence must include color similarity details")

    def test_white_and_camel_complementary_not_redundant(self):
        """White and camel are versatile neutrals, but have distinct perceptual color contrast and are not redundant."""
        res = compare_colors("white", "camel")
        self.assertFalse(res.is_same_family, "White and camel belong to distinct color families.")
        self.assertLessEqual(res.similarity_score, 0.35, "White and camel must not be treated as highly similar colors.")

        # A white shirt and a camel coat complement each other without redundancy
        candidate_coat = CandidateItem(category="coat", color="camel", style=["classic", "formal"])
        owned_wardrobe = [Garment(id="W_SHIRT", name="White Oxford Shirt", category="shirt", color="white", style=["formal"])]
        matches = find_similar_items(candidate_coat, owned_wardrobe)
        for m in matches:
            self.assertFalse(m.functional_overlap)
            self.assertIsNone(m.redundancy_warning)


if __name__ == "__main__":
    unittest.main()
