"""Hypothèses de conception (ISSUE-04b, ISSUE-07).

Ces tests décrivaient un comportement qui POURRAIT être préférable et étaient
en xfail strict. Les deux hypothèses ont été validées puis implémentées : ce
sont désormais des tests ordinaires. Une nouvelle hypothèse non validée doit
être ajoutée ici en xfail strict ; si elle est rejetée, on supprime le test.
"""

import pytest

from bo4_fixtures import outfit_key
from outfit_engine import recommend_outfits

pytestmark = pytest.mark.design_hypothesis

ALL = 100


# ISSUE-04b : hypothèse validée et implémentée (couleur haut+bas+veste plafonnée à la base).
def test_issue04b_season_neutral_third_piece_not_rewarded(make_item):
    """Une pièce qui ne change pas la chaleur de la tenue ne devrait pas, à elle
    seule, augmenter le score via la moyenne des paires de couleurs.

    Depuis ISSUE-04a, la partie saisonnière de ce biais a disparu (chaleur
    identique : score saisonnier identique) ; seule la partie couleur subsiste.
    """
    top = make_item("shirt", "light_blue", warmth="medium", name="top")
    bottom = make_item("trousers", "dark_grey", warmth="medium", name="bottom")
    blazer = make_item("blazer", "black", warmth="medium", name="blazer")
    results = recommend_outfits([top, bottom, blazer], "university", "spring", top_k=ALL)
    by_key = {outfit_key(r): r for r in results}
    two, three = by_key[("top", "bottom")], by_key[("top", "bottom", "blazer")]
    assert three["season_score"] == two["season_score"]
    assert three["score"] <= two["score"]


# ISSUE-07 : hypothèse validée et implémentée (select_diverse, contrainte de couverture).
def test_issue07_top_k_is_diverse(make_item):
    """Quand une alternative existe, le top 3 ne devrait pas réutiliser le même haut partout."""
    wardrobe = [
        make_item("shirt", "white", name="white shirt"),
        make_item("shirt", "red", name="red shirt"),
        make_item("trousers", "black", name="black trousers"),
        make_item("trousers", "grey", name="grey trousers"),
        make_item("jeans", "navy_blue", name="navy jeans"),
    ]
    top3 = recommend_outfits(wardrobe, "university", "autumn", top_k=3)
    assert len({r["items"][0]["name"] for r in top3}) > 1
