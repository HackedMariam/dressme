"""ISSUE-04b : la veste ne peut pas compenser l'harmonie haut/bas.

Haut + bas + veste : couleur = min(couleur(haut, bas), moyenne des 3 paires).
Haut + bas, robe seule, robe + veste : inchangés.
"""

import itertools

import pytest

from bo4_fixtures import REFERENCE_WARDROBE
from outfit_engine import (
    JACKET_COLOR_CAP_REASON,
    SINGLE_PIECE_COLOR_SCORE,
    color_score,
    evaluate_outfit,
    recommend_outfits,
)

PALETTE = [
    "black", "white", "grey", "dark_grey", "navy_blue", "beige", "off_white", "light_beige",
    "red", "green", "light_blue", "dark_red", "light_pink", "yellow", "gold", "other", "unknown",
]


def top(color):
    return {"id": "t", "category": "shirt", "color": color}


def bottom(color):
    return {"id": "b", "category": "trousers", "color": color}


def jacket(color):
    return {"id": "j", "category": "jacket", "color": color}


def dress(color):
    return {"id": "d", "category": "dress", "color": color}


def colour_of(items):
    result = evaluate_outfit(items, "university", "autumn")
    return result["color_score"], result["explanations"]


def mean_of_pairs(colors):
    pairs = [color_score(a, b)[0] for a, b in itertools.combinations(colors, 2)]
    return sum(pairs) / len(pairs)


# ---------------------------------------------------------------------------
# Règle et explication
# ---------------------------------------------------------------------------

def test_three_piece_rule_on_full_palette():
    for t, b, j in itertools.product(PALETTE, repeat=3):
        base = color_score(t, b)[0]
        expected = min(base, mean_of_pairs([t, b, j]))
        score, reasons = colour_of([top(t), bottom(b), jacket(j)])
        assert score == round(expected * 100, 2), (t, b, j)
        assert score <= round(base * 100, 2), (t, b, j)               # jamais de compensation
        capped = mean_of_pairs([t, b, j]) > base
        assert (JACKET_COLOR_CAP_REASON in reasons) == capped, (t, b, j)


def test_clash_is_not_diluted_by_neutral_jacket():
    score, reasons = colour_of([top("red"), bottom("green"), jacket("black")])
    assert score == 55.0                                              # était 78.33
    assert JACKET_COLOR_CAP_REASON in reasons
    assert "Association de couleurs à vérifier" in reasons            # explications existantes conservées


def test_neutral_jacket_on_one_neutral_base():
    score, reasons = colour_of([top("light_blue"), bottom("dark_grey"), jacket("black")])
    assert score == 90.0                                              # était 91.67
    assert JACKET_COLOR_CAP_REASON in reasons


def test_all_neutral_outfit_unchanged_and_not_flagged():
    score, reasons = colour_of([top("white"), bottom("black"), jacket("grey")])
    assert score == 95.0
    assert JACKET_COLOR_CAP_REASON not in reasons


@pytest.mark.parametrize("colors, expected", [
    (("white", "black", "red"), 91.67),    # veste colorée : baisse conservée
    (("red", "black", "green"), 78.33),    # veste qui crée un conflit : baisse conservée
])
def test_jacket_can_still_lower_the_score(colors, expected):
    score, reasons = colour_of([top(colors[0]), bottom(colors[1]), jacket(colors[2])])
    assert score == expected
    assert JACKET_COLOR_CAP_REASON not in reasons


def test_unknown_colors():
    # Base inconnue (0.60) : la veste neutre ne la relève pas
    score, reasons = colour_of([top("unknown"), bottom("black"), jacket("black")])
    assert score == 60.0 and JACKET_COLOR_CAP_REASON in reasons
    # Veste inconnue : elle fait baisser la moyenne, pas de plafonnement
    score, reasons = colour_of([top("white"), bottom("black"), jacket("unknown")])
    assert score == round(mean_of_pairs(["white", "black", "unknown"]) * 100, 2)
    assert JACKET_COLOR_CAP_REASON not in reasons


# ---------------------------------------------------------------------------
# Structures non concernées
# ---------------------------------------------------------------------------

def test_two_piece_outfits_unchanged():
    for t, b in itertools.product(PALETTE, repeat=2):
        score, reasons = colour_of([top(t), bottom(b)])
        assert score == round(color_score(t, b)[0] * 100, 2)
        assert JACKET_COLOR_CAP_REASON not in reasons


def test_dresses_unchanged():
    for d in PALETTE:
        score, reasons = colour_of([dress(d)])
        assert score == SINGLE_PIECE_COLOR_SCORE * 100
        assert JACKET_COLOR_CAP_REASON not in reasons
        for j in PALETTE:
            score, reasons = colour_of([dress(d), jacket(j)])
            assert score == round(color_score(d, j)[0] * 100, 2)      # paire réelle, non plafonnée
            assert JACKET_COLOR_CAP_REASON not in reasons


# ---------------------------------------------------------------------------
# Effet sur la garde-robe de référence
# ---------------------------------------------------------------------------

def test_reference_only_denise_with_jacket_is_capped():
    """Seule DENISE (bleu clair) + Skinny (gris foncé) + Huffel (noir) est concernée."""
    for season in ("spring", "summer", "autumn", "winter"):
        for r in recommend_outfits(REFERENCE_WARDROBE, "university", season, top_k=100):
            names = [i["name"] for i in r["items"]]
            capped = JACKET_COLOR_CAP_REASON in r["explanations"]
            assert capped == (names == ["DENISE S.8", "Shaping Skinny H.W", "Huffel puffer jacket"])
