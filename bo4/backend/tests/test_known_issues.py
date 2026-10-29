"""Comportement souhaité pour les défauts confirmés par l'audit.

Chaque test est en xfail strict : il est rapporté "xfailed" tant que le défaut
existe. Quand une correction le fait passer, pytest signale XPASS(strict) :
retirer alors le marker xfail ici et mettre à jour le test de caractérisation
correspondant (même identifiant ISSUE-xx).

Les tests décrivent un résultat observable, pas une implémentation.
"""

import pytest

from bo4_fixtures import outfit_key
from outfit_engine import color_score, garment_role, recommend_outfits
from wardrobe_db_adapter import normalize_category, normalize_color

pytestmark = pytest.mark.desired

ALL = 100


# ISSUE-02 et ISSUE-03 : corrigés (outfit_engine.base_color / is_neutral).

@pytest.mark.parametrize("raw", ["Off White", "Light Beige", "Dark Beige"])
def test_issue02_hm_neutral_colors_are_neutral(raw):
    # Un neutre associé à une couleur vive doit "équilibrer la tenue" (>= 0.90).
    assert color_score(normalize_color(raw), normalize_color("Light Pink"))[0] >= 0.90


@pytest.mark.parametrize("variant, base", [
    ("Dark Red", "Red"),
    ("Light Purple", "Purple"),
    ("Dark Pink", "Pink"),
])
def test_issue02_hm_color_variants_belong_to_family(variant, base):
    assert color_score(normalize_color(variant), normalize_color(base))[0] >= 0.85


@pytest.mark.parametrize("neutral", ["grey", "black", "white", "beige"])
def test_issue03_neutral_monochrome_not_penalized(neutral):
    assert color_score(neutral, neutral)[0] >= color_score("grey", "dark_grey")[0]


# ISSUE-04 : corrigé par ISSUE-04a (season_score par chaleur plausible).
def test_issue04_summer_outerwear_does_not_increase_score(reference_wardrobe):
    """En été, ajouter une veste/doudoune ne doit pas augmenter le score d'une tenue."""
    results = recommend_outfits(reference_wardrobe, "university", "summer", top_k=ALL)
    by_key = {outfit_key(r): r["score"] for r in results}
    for key, score in by_key.items():
        if len(key) == 3:
            assert score <= by_key[key[:2]], key


# ISSUE-05 : corrigé (rôle "dress" dans outfit_engine).
def test_issue05_dress_is_supported_by_adapter():
    assert garment_role({"category": normalize_category("Dress")}) is not None


def test_issue05_dress_forms_an_outfit(make_item):
    # Forme exacte provisoire : une robe seule ou avec une veste doit être proposée.
    wardrobe = [make_item("dress", "black", name="dress"), make_item("jacket", "white", name="jacket")]
    keys = {outfit_key(r) for r in recommend_outfits(wardrobe, top_k=ALL)}
    assert any("dress" in key for key in keys)


# ISSUE-06 : corrigé (départage technique par identifiant, outfit_sort_key).
def test_issue06_ties_are_broken_deterministically(make_item):
    # Vraie égalité : deux hauts strictement équivalents.
    wardrobe = [
        make_item("shirt", "white", name="shirt A"),
        make_item("shirt", "white", name="shirt B"),
        make_item("trousers", "black", name="trousers"),
    ]
    forward = [outfit_key(r) for r in recommend_outfits(wardrobe, top_k=ALL)]
    backward = [outfit_key(r) for r in recommend_outfits(list(reversed(wardrobe)), top_k=ALL)]
    assert forward == backward
