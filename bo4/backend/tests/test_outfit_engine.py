"""Tests de caractérisation de outfit_engine.py.

Ils figent le comportement ACTUEL, défauts compris. Quand une correction
modifie un de ces résultats, le test doit être mis à jour délibérément, en
même temps que le test correspondant de test_known_issues.py.
"""

import copy
import random

import pytest

from bo4_fixtures import AMERICAN, DENISE, HUFFEL, LEGOLAS, SKINNY, outfit_key
from outfit_engine import (
    base_color,
    color_family,
    color_score,
    garment_role,
    is_neutral,
    item_warmth,
    normalize,
    occasion_score,
    recommend_outfits,
    season_score,
    style_score,
    WARMTH_LEVELS,
)

pytestmark = pytest.mark.characterization

ALL = 100  # top_k suffisant pour obtenir toutes les combinaisons
OCCASIONS = ["university", "work", "evening", "casual"]
SEASONS = ["spring", "summer", "autumn", "winter"]
SCORE_KEYS = ["score", "color_score", "style_score", "occasion_score", "season_score"]


def scores(results):
    return [r["score"] for r in results]


# ---------------------------------------------------------------------------
# A. Classement de référence (university / autumn)
# ---------------------------------------------------------------------------

def test_reference_total_combinations_is_6(reference_wardrobe):
    # 3 hauts x 1 bas x (1 + 1 veste)
    assert len(recommend_outfits(reference_wardrobe, top_k=ALL)) == 6


def test_reference_score_sequence(reference_wardrobe):
    results = recommend_outfits(reference_wardrobe, "university", "autumn", top_k=ALL)
    # ISSUE-04b : DENISE + Skinny + Huffel 75.0 -> 74.5 (couleur plafonnée), ordre inchangé
    assert scores(results) == [76.5, 76.07, 76.0, 75.2, 74.5, 73.7]


def test_reference_top_outfit(reference_wardrobe):
    best = recommend_outfits(reference_wardrobe, "university", "autumn", top_k=1)[0]
    assert outfit_key(best) == (AMERICAN, SKINNY)


def test_reference_inner_layer_breaks_former_tie(reference_wardrobe):
    """Ex aequo avant la couche intérieure (76.07) : le pull sous la veste
    passe désormais devant la chemise sous la veste."""
    results = recommend_outfits(reference_wardrobe, "university", "autumn", top_k=ALL)
    by_key = {outfit_key(r): r["score"] for r in results}
    assert by_key[(AMERICAN, SKINNY, HUFFEL)] == 76.07
    assert by_key[(LEGOLAS, SKINNY, HUFFEL)] == 76.0


# Valeurs depuis ISSUE-04a (saisons par chaleur plausible ; aucun attribut
# `warmth` dans la garde-robe de référence : estimation par catégorie).
EXPECTED_AUTUMN = {
    # tenue: (score, couleur, style, occasion, saison)
    (AMERICAN, SKINNY): (76.5, 95.0, 60.0, 60.0, 90.0),
    (AMERICAN, SKINNY, HUFFEL): (76.07, 95.0, 60.0, 60.0, 87.83),
    (LEGOLAS, SKINNY, HUFFEL): (76.0, 95.0, 60.0, 60.0, 87.51),
    (LEGOLAS, SKINNY): (75.2, 95.0, 60.0, 60.0, 83.5),
    (DENISE, SKINNY, HUFFEL): (74.5, 90.0, 60.0, 60.0, 87.51),  # ISSUE-04b : couleur plafonnée à la base haut/bas (était 75.0 / 91.67)
    (DENISE, SKINNY): (73.7, 90.0, 60.0, 60.0, 83.5),
}


def test_reference_component_scores(reference_wardrobe):
    results = recommend_outfits(reference_wardrobe, "university", "autumn", top_k=ALL)
    actual = {outfit_key(r): tuple(r[k] for k in SCORE_KEYS) for r in results}
    assert actual.keys() == EXPECTED_AUTUMN.keys()
    for key, expected in EXPECTED_AUTUMN.items():
        assert actual[key] == pytest.approx(expected), key


def test_reference_top_explanations(reference_wardrobe):
    best = recommend_outfits(reference_wardrobe, "university", "autumn", top_k=1)[0]
    assert best["explanations"] == [
        "Association de couleurs neutres",
        "Styles non renseignés",
        "Adéquation à l'occasion incertaine",
        "Tenue globalement adaptée à la saison : autumn",
    ]


@pytest.mark.parametrize("occasion", OCCASIONS)
@pytest.mark.parametrize("season", SEASONS)
def test_score_is_weighted_sum(reference_wardrobe, occasion, season):
    for r in recommend_outfits(reference_wardrobe, occasion, season, top_k=ALL):
        expected = (
            0.30 * r["color_score"]
            + 0.20 * r["style_score"]
            + 0.30 * r["occasion_score"]
            + 0.20 * r["season_score"]
        )
        # Les composantes sont arrondies à 2 décimales avant d'être renvoyées.
        assert r["score"] == pytest.approx(expected, abs=0.01)


@pytest.mark.parametrize("top_k, expected_len", [(1, 1), (3, 3), (5, 5), (6, 6), (100, 6)])
def test_top_k_truncates(reference_wardrobe, top_k, expected_len):
    assert len(recommend_outfits(reference_wardrobe, top_k=top_k)) == expected_len


def test_result_structure(reference_wardrobe):
    result = recommend_outfits(reference_wardrobe, "work", "winter", top_k=1)[0]
    assert set(result) == {"items", "occasion", "season", "explanations", *SCORE_KEYS}
    assert result["occasion"] == "work"
    assert result["season"] == "winter"
    assert isinstance(result["explanations"], list)
    # Les vêtements sont renvoyés tels quels (mêmes dicts, champs conservés).
    for item in result["items"]:
        assert any(item is original for original in reference_wardrobe)


def test_results_sorted_descending(reference_wardrobe):
    for season in SEASONS:
        s = scores(recommend_outfits(reference_wardrobe, "university", season, top_k=ALL))
        assert s == sorted(s, reverse=True)


# ---------------------------------------------------------------------------
# B. Occasions et saisons
# ---------------------------------------------------------------------------

EXPECTED_SEASON_RANKING = {
    "spring": [
        ((LEGOLAS, SKINNY), 76.85),
        ((LEGOLAS, SKINNY, HUFFEL), 75.55),
        ((DENISE, SKINNY), 75.35),
        ((AMERICAN, SKINNY), 74.9),
        ((DENISE, SKINNY, HUFFEL), 74.05),  # ISSUE-04b : couleur plafonnée à la base haut/bas (était 74.55)
        ((AMERICAN, SKINNY, HUFFEL), 73.82),
    ],
    "summer": [
        ((LEGOLAS, SKINNY), 75.2),
        ((DENISE, SKINNY), 73.7),
        ((LEGOLAS, SKINNY, HUFFEL), 71.3),
        ((DENISE, SKINNY, HUFFEL), 69.8),  # ISSUE-04b : couleur plafonnée à la base haut/bas (était 70.3)
        ((AMERICAN, SKINNY), 69.35),
        ((AMERICAN, SKINNY, HUFFEL), 68.27),
    ],
    "autumn": [
        ((AMERICAN, SKINNY), 76.5),
        ((AMERICAN, SKINNY, HUFFEL), 76.07),
        ((LEGOLAS, SKINNY, HUFFEL), 76.0),
        ((LEGOLAS, SKINNY), 75.2),
        ((DENISE, SKINNY, HUFFEL), 74.5),  # ISSUE-04b : couleur plafonnée à la base haut/bas (était 75.0)
        ((DENISE, SKINNY), 73.7),
    ],
    "winter": [
        ((AMERICAN, SKINNY, HUFFEL), 75.1),
        ((AMERICAN, SKINNY), 74.45),
        ((LEGOLAS, SKINNY, HUFFEL), 72.72),
        ((DENISE, SKINNY, HUFFEL), 71.22),  # ISSUE-04b : couleur plafonnée à la base haut/bas (était 71.72)
        ((LEGOLAS, SKINNY), 69.25),
        ((DENISE, SKINNY), 67.75),
    ],
}


@pytest.mark.parametrize("season", SEASONS)
def test_ranking_per_season(reference_wardrobe, season):
    results = recommend_outfits(reference_wardrobe, "university", season, top_k=ALL)
    assert [(outfit_key(r), r["score"]) for r in results] == EXPECTED_SEASON_RANKING[season]


def test_winter_best_is_sweater_with_jacket(reference_wardrobe):
    best = recommend_outfits(reference_wardrobe, "university", "winter", top_k=1)[0]
    assert outfit_key(best) == (AMERICAN, SKINNY, HUFFEL)


def test_summer_penalizes_sweater(reference_wardrobe):
    results = recommend_outfits(reference_wardrobe, "university", "summer", top_k=ALL)
    sweater = [r for r in results if r["items"][0]["name"] == AMERICAN]
    assert [r["season_score"] for r in sweater] == [54.25, 48.83]
    assert all(
        "American Beauty intarsia trop chaud pour l'été (estimation par catégorie)" in r["explanations"]
        for r in sweater
    )


def test_issue01_occasion_inert_when_styles_unknown(reference_wardrobe):
    """ISSUE-01 (limite actuelle) : sans style connu, l'occasion ne change rien."""
    def ranking(occasion):
        return [
            (outfit_key(r), r["score"])
            for r in recommend_outfits(reference_wardrobe, occasion, "autumn", top_k=ALL)
        ]

    baseline = ranking("university")
    for occasion in OCCASIONS[1:]:
        assert ranking(occasion) == baseline


def _styled_wardrobe(make_item):
    # Couleurs toutes neutres et distinctes : la couleur ne départage pas.
    return [
        make_item("shirt", "white", "formal", name="formal shirt"),
        make_item("trousers", "black", "formal", name="formal trousers"),
        make_item("tshirt", "grey", "casual", name="casual tshirt"),
        make_item("jeans", "navy_blue", "casual", name="casual jeans"),
    ]


def test_issue01_occasion_changes_ranking_with_known_styles(make_item):
    """ISSUE-01 : avec des styles connus, l'occasion influence bien le classement."""
    wardrobe = _styled_wardrobe(make_item)
    work = recommend_outfits(wardrobe, "work", "autumn", top_k=1)[0]
    casual = recommend_outfits(wardrobe, "casual", "autumn", top_k=1)[0]
    assert outfit_key(work) == ("formal shirt", "formal trousers")
    assert outfit_key(casual) == ("casual tshirt", "casual jeans")
    assert work["occasion_score"] == 100.0
    assert casual["occasion_score"] == 100.0


def test_issue01_mismatched_occasion_scores_low(make_item):
    wardrobe = _styled_wardrobe(make_item)
    results = recommend_outfits(wardrobe, "casual", "autumn", top_k=ALL)
    formal = next(r for r in results if outfit_key(r) == ("formal shirt", "formal trousers"))
    assert formal["occasion_score"] == 20.0  # plancher max(0.20, ...)
    assert formal["style_score"] == 100.0    # styles cohérents entre eux


@pytest.mark.parametrize("bad", ["party", "", "University"])
def test_invalid_occasion_raises(reference_wardrobe, bad):
    with pytest.raises(ValueError):
        recommend_outfits(reference_wardrobe, occasion=bad)


@pytest.mark.parametrize("bad", ["fall", "", "Winter"])
def test_invalid_season_raises(reference_wardrobe, bad):
    with pytest.raises(ValueError):
        recommend_outfits(reference_wardrobe, season=bad)


# ---------------------------------------------------------------------------
# C. Garde-robes vides ou incomplètes
# ---------------------------------------------------------------------------

def test_empty_wardrobe_returns_empty():
    assert recommend_outfits([]) == []


def test_no_top_returns_empty(make_item):
    assert recommend_outfits([make_item("trousers"), make_item("jacket")]) == []


def test_no_bottom_returns_empty(make_item):
    assert recommend_outfits([make_item("shirt"), make_item("coat")]) == []


def test_only_outerwear_returns_empty(make_item):
    assert recommend_outfits([make_item("jacket"), make_item("blazer")]) == []


def test_without_outerwear_only_two_piece_outfits(make_item):
    results = recommend_outfits([make_item("shirt"), make_item("jeans")], top_k=ALL)
    assert len(results) == 1
    assert len(results[0]["items"]) == 2


@pytest.mark.parametrize("category", [None, "", "dungarees", "jumpsuit/playsuit", "shoes", "unknown"])
def test_unsupported_category_is_ignored(make_item, category):
    wardrobe = [make_item("shirt"), make_item("jeans"), make_item(category)]
    results = recommend_outfits(wardrobe, top_k=ALL)
    assert len(results) == 1


def test_missing_color_uses_unknown_branch(make_item):
    top = make_item("shirt")
    del top["color"]
    result = recommend_outfits([top, make_item("jeans")], top_k=1)[0]
    assert result["color_score"] == 60.0
    assert "Couleur non renseignée" in result["explanations"]


# ---------------------------------------------------------------------------
# D. Combinaisons et doublons
# ---------------------------------------------------------------------------

def _wardrobe_3x2x2(make_item):
    return (
        [make_item("shirt", c) for c in ("white", "light_blue", "red")]
        + [make_item("jeans", c) for c in ("navy_blue", "black")]
        + [make_item("jacket", c) for c in ("black", "beige")]
    )


def test_combination_count_formula(make_item):
    # T x B x (J + 1) = 3 x 2 x 3
    assert len(recommend_outfits(_wardrobe_3x2x2(make_item), top_k=ALL)) == 18


def test_same_id_is_never_used_twice(make_item):
    shared = make_item("shirt")
    # Même id réutilisé pour un bas : la combinaison doit être écartée.
    duplicate_bottom = make_item("jeans", id=shared["id"])
    other_bottom = make_item("trousers")
    results = recommend_outfits([shared, duplicate_bottom, other_bottom], top_k=ALL)
    assert len(results) == 1
    for r in results:
        ids = [i["id"] for i in r["items"]]
        assert len(ids) == len(set(ids))


def test_no_duplicate_outfits_in_results(make_item):
    results = recommend_outfits(_wardrobe_3x2x2(make_item), top_k=ALL)
    keys = [tuple(i["id"] for i in r["items"]) for r in results]
    assert len(keys) == len(set(keys))


def test_items_ordered_top_bottom_outerwear(make_item):
    for r in recommend_outfits(_wardrobe_3x2x2(make_item), top_k=ALL):
        roles = [garment_role(i) for i in r["items"]]
        assert roles in (["top", "bottom"], ["top", "bottom", "outerwear"])


def test_issue06_tie_order_follows_item_ids(make_item):
    """ISSUE-06 (corrigé) : les ex aequo sont ordonnés par identifiant, quel que
    soit l'ordre d'entrée (départage technique, pas de pertinence)."""
    # Deux hauts strictement équivalents : vraie égalité.
    wardrobe = [
        make_item("shirt", "white", name="shirt A"),
        make_item("shirt", "white", name="shirt B"),
        make_item("trousers", "black", name="trousers"),
    ]
    forward = recommend_outfits(wardrobe, top_k=ALL)
    backward = recommend_outfits(list(reversed(wardrobe)), top_k=ALL)
    assert forward[0]["score"] == forward[1]["score"]
    assert [outfit_key(r) for r in forward] == [("shirt A", "trousers"), ("shirt B", "trousers")]
    assert [outfit_key(r) for r in backward] == [("shirt A", "trousers"), ("shirt B", "trousers")]


def test_scores_independent_of_input_order(reference_wardrobe):
    shuffled = list(reference_wardrobe)
    random.Random(42).shuffle(shuffled)
    a = {outfit_key(r): r["score"] for r in recommend_outfits(reference_wardrobe, top_k=ALL)}
    b = {outfit_key(r): r["score"] for r in recommend_outfits(shuffled, top_k=ALL)}
    assert a == b


# ---------------------------------------------------------------------------
# E. Fonctions unitaires
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw, expected", [
    ("Light Blue", "light_blue"),
    ("  T-Shirt ", "t_shirt"),
    ("DARK-GREY", "dark_grey"),
    (None, "unknown"),
    ("", "unknown"),
    (42, "42"),
])
def test_normalize(raw, expected):
    assert normalize(raw) == expected


@pytest.mark.parametrize("category, role", [
    *[(c, "top") for c in ("shirt", "tshirt", "t_shirt", "blouse", "sweater", "hoodie", "top")],
    *[(c, "bottom") for c in ("trousers", "pants", "jeans", "shorts", "skirt")],
    *[(c, "outerwear") for c in ("blazer", "jacket", "coat", "cardigan")],
    ("T-Shirt", "top"),
    ("dress", "dress"),
    ("Dress", "dress"),
    ("dungarees", None),
    ("underdress", None),
    ("jumpsuit/playsuit", None),
    ("polo_shirt", None),
    (None, None),
])
def test_garment_role(category, role):
    assert garment_role({"category": category}) == role


@pytest.mark.parametrize("a, b, expected, reason", [
    ("unknown", "black", 0.60, "Couleur non renseignée"),
    (None, "black", 0.60, "Couleur non renseignée"),
    ("red", "red", 0.75, "Ensemble monochrome"),
    ("white", "black", 0.95, "Association de couleurs neutres"),
    ("grey", "grey", 0.95, "Ensemble monochrome neutre"),
    ("dark_grey", "black", 0.95, "Association de couleurs neutres"),
    ("light_blue", "dark_grey", 0.90, "Une couleur neutre équilibre la tenue"),
    ("light_blue", "navy_blue", 0.90, "Une couleur neutre équilibre la tenue"),
    ("light_blue", "blue", 0.85, "Couleurs de la même famille"),
    ("red", "green", 0.55, "Association de couleurs à vérifier"),
])
def test_color_score_branches(a, b, expected, reason):
    assert color_score(a, b) == (expected, reason)


def test_color_score_is_symmetric():
    colors = ["black", "white", "dark_grey", "light_blue", "red", "unknown", "green"]
    for a in colors:
        for b in colors:
            assert color_score(a, b) == color_score(b, a)


def test_dark_grey_is_neutral():
    """Comportement correct à conserver lors des corrections de couleurs."""
    assert color_score("dark_grey", "white")[0] == 0.95
    assert color_score("dark_grey", "red")[0] == 0.90


def test_issue03_neutral_monochrome_scored_as_neutral_pair():
    """ISSUE-03 (corrigé) : un monochrome neutre vaut une paire de neutres."""
    assert color_score("grey", "grey") == (0.95, "Ensemble monochrome neutre")
    assert color_score("black", "black") == (0.95, "Ensemble monochrome neutre")
    assert color_score("grey", "dark_grey") == (0.95, "Association de couleurs neutres")


def test_issue03_non_neutral_monochrome_unchanged():
    """Hors périmètre d'ISSUE-03 : le monochrome coloré reste à 0.75."""
    assert color_score("red", "red") == (0.75, "Ensemble monochrome")
    assert color_score("light_blue", "light_blue") == (0.75, "Ensemble monochrome")


def test_issue02_hm_colors_recognised():
    """ISSUE-02 (corrigé) : variantes H&M interprétées par le moteur."""
    assert color_score("off_white", "light_pink")[0] == 0.90
    assert color_score("light_beige", "light_pink")[0] == 0.90
    assert color_score("dark_red", "red")[0] == 0.85
    assert color_score("light_purple", "purple")[0] == 0.85


@pytest.mark.parametrize("raw, expected", [
    ("light_beige", "beige"),
    ("dark_beige", "beige"),
    ("off_white", "white"),
    ("other_pink", "pink"),
    ("yellowish_brown", "brown"),
    ("greenish_khaki", "khaki"),
    ("light_turquoise", "turquoise"),
    ("navy_blue", "navy_blue"),    # "navy" n'est pas un modificateur
    ("denim_blue", "denim_blue"),
    ("light", "light"),            # jamais vidé
    ("unknown", "unknown"),
    (None, "unknown"),
])
def test_base_color(raw, expected):
    assert base_color(raw) == expected


@pytest.mark.parametrize("color, neutral", [
    ("black", True), ("white", True), ("grey", True), ("gray", True),
    ("dark_grey", True), ("light_grey", True), ("beige", True), ("cream", True),
    ("navy_blue", True), ("navy", True),
    ("off_white", True), ("light_beige", True), ("dark_beige", True),
    ("light_blue", False), ("dark_blue", False), ("blue", False),
    ("light_pink", False), ("gold", False), ("silver", False), ("unknown", False),
])
def test_is_neutral(color, neutral):
    assert is_neutral(color) is neutral


@pytest.mark.parametrize("color, family", [
    ("light_blue", "blue"), ("dark_blue", "blue"), ("navy_blue", "blue"),
    ("dark_red", "red"), ("light_red", "red"), ("other_red", "red"),
    ("dark_pink", "pink"), ("other_pink", "pink"),
    ("light_purple", "purple"), ("lilac", "purple"),
    ("dark_green", "green"), ("greenish_khaki", "green"),
    ("yellowish_brown", "brown"),
    ("dark_orange", "orange"), ("light_turquoise", "turquoise"),
])
def test_color_family(color, family):
    assert color_family(color) == family


@pytest.mark.parametrize("styles, expected", [
    (["unknown", "unknown"], (0.60, "Styles non renseignés")),
    (["formal", "formal"], (1.0, "Styles cohérents")),
    (["formal", "unknown"], (1.0, "Styles cohérents")),
    (["formal", "casual"], (0.75, "Mélange de styles potentiellement compatible")),
    (["formal", "sporty"], (0.50, "Mélange de styles à vérifier")),
])
def test_style_score(styles, expected):
    assert style_score([{"style": s} for s in styles]) == expected


@pytest.mark.parametrize("styles, occasion, expected", [
    (["unknown", "unknown"], "work", 0.60),
    (["formal", "smart_casual"], "work", 1.0),
    (["formal", "casual"], "work", 0.5),
    (["casual", "casual"], "work", 0.20),
    (["formal", "formal"], "casual", 0.20),
])
def test_occasion_score(styles, occasion, expected):
    score, _ = occasion_score([{"style": s} for s in styles], occasion)
    assert score == pytest.approx(expected)


@pytest.mark.parametrize("categories, season, expected", [
    # torse = espérance de la couche la plus chaude ; bas pondéré à 0.35
    (["shirt", "trousers"], "autumn", 0.835),             # 0.65*0.8 + 0.35*0.9
    (["shirt", "trousers", "jacket"], "autumn", 0.875083),  # couche intérieure : 0.878333 -> 0.875083
    (["tshirt", "jeans"], "autumn", 0.705),               # 0.65*0.6 + 0.35*0.9
    (["sweater", "shorts"], "summer", 0.5775),            # 0.65*0.35 + 0.35*1.0
    (["sweater", "hoodie", "coat"], "winter", 0.95125),     # couche intérieure : 0.9625 -> 0.95125
    (["tshirt", "shorts"], "winter", 0.2),
    (["tshirt", "shorts"], "summer", 1.0),
])
def test_season_score(categories, season, expected):
    score, _ = season_score([{"category": c} for c in categories], season)
    assert score == pytest.approx(expected, abs=1e-6)


def test_season_score_without_roles():
    assert season_score([], "summer") == (0.60, ["Adéquation saisonnière non évaluable"])
    assert season_score([{"category": "dungarees"}], "winter")[0] == 0.60


def test_issue04_summer_outerwear_ranked_below_two_piece(reference_wardrobe):
    """ISSUE-04 (corrigé) : en été, ajouter la veste fait baisser la tenue.

    Sans attribut `warmth`, la veste garde ses trois niveaux plausibles : c'est
    l'incertitude (elle PEUT être chaude), pas l'identification de la doudoune,
    qui la pénalise ici. L'identification viendra avec ISSUE-04b-data.
    """
    results = recommend_outfits(reference_wardrobe, "university", "summer", top_k=ALL)
    by_key = {outfit_key(r): r["season_score"] for r in results}
    assert by_key[(LEGOLAS, SKINNY, HUFFEL)] == 64.0
    assert by_key[(LEGOLAS, SKINNY)] == 83.5


# ---------------------------------------------------------------------------
# F. Chaleur des vêtements et scénarios saisonniers (ISSUE-04a)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("item, expected", [
    ({"category": "jacket", "warmth": "heavy"}, (("heavy",), "attribute")),
    ({"category": "jacket", "warmth": "Light"}, (("light",), "attribute")),
    ({"category": "tshirt", "warmth": "heavy"}, (("heavy",), "attribute")),  # l'attribut prime
    ({"category": "shirt"}, (("light", "medium"), "category")),
    ({"category": "shirt", "warmth": "unknown"}, (("light", "medium"), "category")),
    ({"category": "shirt", "warmth": "hot"}, (("light", "medium"), "category")),  # valeur invalide ignorée
    ({"category": "sweater"}, (("medium", "heavy"), "category")),
    ({"category": "tshirt"}, (("light",), "category")),
    ({"category": "jacket"}, (WARMTH_LEVELS, "unknown")),
    ({"category": "cardigan"}, (WARMTH_LEVELS, "unknown")),
    ({"category": "dress"}, (("light", "medium"), "category")),
    ({"category": "dungarees"}, (WARMTH_LEVELS, "unknown")),
    ({}, (WARMTH_LEVELS, "unknown")),
])
def test_item_warmth(item, expected):
    assert item_warmth(item) == expected


def test_no_category_defaults_to_medium():
    """Une catégorie peu informative n'est jamais ramenée à "medium"."""
    for category in ("jacket", "cardigan", "dungarees", None):
        levels, source = item_warmth({"category": category})
        assert levels == WARMTH_LEVELS
        assert source == "unknown"


def _season(items, season):
    return season_score(items, season)[0]


def test_puffer_in_summer_is_penalised(make_item):
    top = make_item("tshirt", "white", name="tee")
    bottom = make_item("shorts", "black", name="shorts")
    puffer = make_item("jacket", "black", warmth="heavy", name="puffer")
    with_puffer, reasons = season_score([top, bottom, puffer], "summer")
    assert with_puffer < _season([top, bottom], "summer")
    assert "puffer trop chaud pour l'été (attribut)" in reasons


@pytest.mark.parametrize("season", ["summer", "spring"])
def test_light_jacket_not_penalised(make_item, season):
    top = make_item("tshirt", "white")
    bottom = make_item("trousers", "black")
    light_jacket = make_item("jacket", "beige", warmth="light")
    assert _season([top, bottom, light_jacket], season) == _season([top, bottom], season)


def test_medium_jacket_helps_in_spring(make_item):
    top = make_item("tshirt", "white")
    bottom = make_item("trousers", "black")
    jacket = make_item("jacket", "beige", warmth="medium")
    assert _season([top, bottom, jacket], "spring") > _season([top, bottom], "spring")


@pytest.mark.parametrize("season", SEASONS)
def test_third_piece_without_thermal_change_gives_no_bonus(make_item, season):
    """Une pièce qui ne change pas la chaleur de la tenue ne change pas le score."""
    top = make_item("sweater", "grey", warmth="medium")
    bottom = make_item("trousers", "black", warmth="medium")
    jacket = make_item("jacket", "black", warmth="medium")
    assert _season([top, bottom, jacket], season) == _season([top, bottom], season)


def test_sweater_is_best_top_in_winter(make_item):
    wardrobe = [
        make_item("tshirt", "white", name="tee"),
        make_item("shirt", "white", name="shirt"),
        make_item("sweater", "white", name="sweater"),
        make_item("trousers", "black", name="trousers"),
    ]
    best = recommend_outfits(wardrobe, "university", "winter", top_k=1)[0]
    assert outfit_key(best) == ("sweater", "trousers")


def test_shorts_preferred_in_summer(make_item):
    top = make_item("tshirt", "white")
    assert _season([top, make_item("shorts")], "summer") > _season([top, make_item("trousers")], "summer")


def test_shorts_penalised_in_winter(make_item):
    top = make_item("sweater", "white", warmth="heavy")
    with_shorts, reasons = season_score([top, make_item("shorts")], "winter")
    assert with_shorts < _season([top, make_item("trousers")], "winter")
    assert "shorts peu adapté à la saison winter" in reasons


def test_winter_without_warm_layer_is_penalised(make_item):
    top = make_item("tshirt", "white", name="tee")
    bottom = make_item("trousers", "black")
    coat = make_item("coat", "black", warmth="heavy", name="coat")
    bare, reasons = season_score([top, bottom], "winter")
    assert bare < _season([top, bottom, coat], "winter")
    assert "Couches insuffisamment chaudes pour la saison : winter" in reasons


def test_light_top_under_heavy_coat_is_fine_in_winter(make_item):
    """La tenue complète compte : un haut léger sous un manteau chaud reste une
    bonne tenue d'hiver, simplement moins bien classée qu'un pull."""
    bottom = make_item("trousers", "black")
    coat = make_item("coat", "black", warmth="heavy")
    light_top = make_item("tshirt", "white", warmth="light")
    warm_top = make_item("sweater", "white", warmth="medium")
    score, reasons = season_score([light_top, bottom, coat], "winter")
    assert score >= 0.8
    assert score < _season([warm_top, bottom, coat], "winter")
    assert score > _season([light_top, bottom], "winter")
    assert not any("insuffisamment" in r or "trop chaud" in r or "peu adapté" in r for r in reasons)


def test_unknown_warmth_is_reported_not_invented(make_item):
    jacket = make_item("jacket", "black", name="mystery jacket")
    _, reasons = season_score([make_item("shirt"), make_item("trousers"), jacket], "autumn")
    assert "Chaleur de mystery jacket non renseignée : estimation incertaine" in reasons


def test_explicit_unknown_equals_missing_attribute(make_item):
    a = [make_item("shirt"), make_item("trousers"), make_item("jacket")]
    b = [dict(i, warmth="unknown") for i in a]
    for season in SEASONS:
        assert season_score(a, season) == season_score(b, season)


def test_category_estimate_not_reported_as_unknown(make_item):
    _, reasons = season_score([make_item("shirt", name="shirt"), make_item("trousers")], "autumn")
    assert not any("non renseignée" in r for r in reasons)


def test_bo1_shaped_items_still_supported():
    """Non-régression : les vêtements BO1 (sans nom, sans warmth) restent utilisables."""
    wardrobe = [
        {"id": "1", "category": "shirt", "color": "light_blue", "style": "unknown",
         "image_path": "crop1.jpg", "review_status": "provisional"},
        {"id": "2", "category": "trousers", "color": "black", "style": "unknown",
         "image_path": "crop2.jpg", "review_status": "provisional"},
        {"id": "3", "category": "jacket", "color": "beige", "style": "unknown",
         "image_path": "crop3.jpg", "review_status": "provisional"},
    ]
    results = recommend_outfits(wardrobe, "university", "winter", top_k=ALL)
    assert len(results) == 2
    assert any("Chaleur de jacket non renseignée" in e for r in results for e in r["explanations"])


def test_recommend_does_not_mutate_items(reference_wardrobe):
    snapshot = copy.deepcopy(reference_wardrobe)
    for season in SEASONS:
        recommend_outfits(reference_wardrobe, "university", season, top_k=ALL)
    assert reference_wardrobe == snapshot
