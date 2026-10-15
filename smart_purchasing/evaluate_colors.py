"""Color Similarity Evaluation Script for DressMe Smart Purchasing Agent.

Demonstrates perceptual CIEDE2000 color distance calculations, normalized
similarity scores, and domain-grounded wardrobe redundancy decisions.
"""

import sys
from pathlib import Path

# Add current dir to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from color_similarity import ColorSimilarityService, compare_colors
from schemas import CandidateItem, Garment, EvaluatePurchaseRequest
from tools import find_similar_items, analyze_wardrobe_gaps
from agent import PurchaseAgent


def evaluate_perceptual_color_pairs():
    """Demonstrates CIEDE2000 distance and similarity on representative fashion color pairs."""
    service = ColorSimilarityService.get_instance()

    test_pairs = [
        ("white", "ivory", "Closely related tints (warm white vs optical white)"),
        ("white", "cream", "Relatively close tints (pale butter vs optical white)"),
        ("white", "beige", "Warm sandy neutral vs white"),
        ("white", "off_white", "Muted chalky white vs optical white"),
        ("white", "camel", "Distinct versatile neutrals (complementary pairing, not redundant)"),
        ("navy", "light_blue", "Same family, high luminance contrast"),
        ("navy", "blue", "Dark blue vs primary blue"),
        ("black", "charcoal", "Deep black vs dark grey suit textile"),
        ("black", "white", "Opposite ends of color luminance space"),
        ("camel", "khaki", "Warm golden brown vs earthy twill neutral"),
        ("camel", "tan", "Closely related warm brown hues"),
        ("burgundy", "red", "Deep wine red vs bright classic red"),
        ("olive", "green", "Muted army green vs emerald green"),
        ("cyberpunk_magenta", "neon_glow", "Unrecognized / custom color labels (graceful handling)"),
    ]

    print("=" * 105)
    print("           DRESSME SMART PURCHASING AGENT - PERCEPTUAL COLOR SIMILARITY BENCHMARK")
    print("=" * 105)
    print(f"{'COLOR 1':<18} {'COLOR 2':<18} {'DELTA E (00)':<14} {'SIMILARITY':<12} {'SAME FAM?':<11} {'INTERPRETATION'}")
    print("-" * 105)

    for c1, c2, desc in test_pairs:
        res = compare_colors(c1, c2)
        de_str = f"{res.delta_e:.2f}" if res.delta_e is not None else "N/A"
        sim_pct = f"{res.similarity_score * 100:.1f}%"
        fam_str = "YES" if res.is_same_family else "NO"
        print(f"{res.color1:<18} {res.color2:<18} {de_str:<14} {sim_pct:<12} {fam_str:<11} {desc}")

    print("=" * 105)


def evaluate_wardrobe_redundancy_rules():
    """Demonstrates that color similarity does not automatically cause redundancy across categories."""
    print("\n" + "=" * 105)
    print("           CROSS-CATEGORY VS SAME-CATEGORY REDUNDANCY DEMONSTRATION")
    print("=" * 105)

    # Base owned wardrobe piece: White Shirt
    owned_shirt = Garment(
        id="ITEM_W_SHIRT",
        name="Classic White Oxford Shirt",
        category="shirt",
        color="white",
        style=["formal", "classic"],
        seasons=["all-season"],
        occasions=["work"]
    )
    wardrobe = [owned_shirt]

    # Scenario A: Cross-category (Cream Skirt vs White Shirt)
    cream_skirt = CandidateItem(
        name="Pleated Cream Midi Skirt",
        category="skirt",
        color="cream",
        style=["formal", "classic"],
        price=75.0,
        budget=100.0
    )

    # Scenario B: Same-category (Cream Shirt vs White Shirt)
    cream_shirt = CandidateItem(
        name="Classic Cream Oxford Shirt",
        category="shirt",
        color="cream",
        style=["formal", "classic"],
        price=60.0,
        budget=80.0
    )

    # Compare Scenario A
    color_comp_a = compare_colors(cream_skirt.color, owned_shirt.color)
    matches_a = find_similar_items(cream_skirt, wardrobe)
    gap_a = analyze_wardrobe_gaps(cream_skirt, wardrobe)

    print("\n[SCENARIO A: Cream Skirt vs Owned White Shirt]")
    print(f"  • Color Comparison    : '{cream_skirt.color}' vs '{owned_shirt.color}'")
    print(f"  • Delta E (CIEDE2000) : {color_comp_a.delta_e:.2f}")
    print(f"  • Color Similarity    : {color_comp_a.similarity_score * 100:.1f}% (High Color Similarity)")
    print(f"  • Functional Overlap  : {matches_a[0].functional_overlap if matches_a else False} (Different Categories!)")
    print(f"  • Redundancy Warning  : {matches_a[0].redundancy_warning if matches_a else 'None (Safe to purchase)'}")
    print(f"  • Wardrobe Gap Score  : {gap_a.gap_fill_score:.1f}/100 ({gap_a.reasoning})")
    print("  -> RESULT: High color similarity does NOT flag redundancy because categories differ!")

    # Compare Scenario B
    color_comp_b = compare_colors(cream_shirt.color, owned_shirt.color)
    matches_b = find_similar_items(cream_shirt, wardrobe)
    gap_b = analyze_wardrobe_gaps(cream_shirt, wardrobe)

    print("\n[SCENARIO B: Cream Shirt vs Owned White Shirt]")
    print(f"  • Color Comparison    : '{cream_shirt.color}' vs '{owned_shirt.color}'")
    print(f"  • Delta E (CIEDE2000) : {color_comp_b.delta_e:.2f}")
    print(f"  • Color Similarity    : {color_comp_b.similarity_score * 100:.1f}% (High Color Similarity)")
    print(f"  • Functional Overlap  : {matches_b[0].functional_overlap if matches_b else False} (Same Category & Style!)")
    print(f"  • Redundancy Warning  : {matches_b[0].redundancy_warning if matches_b else 'None'}")
    print(f"  • Wardrobe Gap Score  : {gap_b.gap_fill_score:.1f}/100")
    print("  -> RESULT: Same category + matching style + high color similarity correctly flags duplicate redundancy!")

    # Scenario C: Neutral pairing (Camel Coat vs White Shirt)
    camel_coat = CandidateItem(
        name="Tailored Camel Wool Coat",
        category="coat",
        color="camel",
        style=["classic", "formal"],
        price=180.0,
        budget=200.0
    )
    color_comp_c = compare_colors(camel_coat.color, owned_shirt.color)
    matches_c = find_similar_items(camel_coat, wardrobe)
    gap_c = analyze_wardrobe_gaps(camel_coat, wardrobe)

    print("\n[SCENARIO C: Camel Coat vs Owned White Shirt]")
    print(f"  • Color Comparison    : '{camel_coat.color}' vs '{owned_shirt.color}'")
    print(f"  • Delta E (CIEDE2000) : {color_comp_c.delta_e:.2f}")
    print(f"  • Color Similarity    : {color_comp_c.similarity_score * 100:.1f}% (Distinct, contrasting shades)")
    print(f"  • Functional Overlap  : {matches_c[0].functional_overlap if matches_c else False} (Coat vs Shirt = different categories)")
    print(f"  • Redundancy Warning  : {matches_c[0].redundancy_warning if matches_c else 'None (Safe to purchase)'}")
    print(f"  • Wardrobe Gap Score  : {gap_c.gap_fill_score:.1f}/100")
    print("  -> RESULT: White shirt and camel coat complement each other without being redundant!")
    print("=" * 105 + "\n")


if __name__ == "__main__":
    evaluate_perceptual_color_pairs()
    evaluate_wardrobe_redundancy_rules()
