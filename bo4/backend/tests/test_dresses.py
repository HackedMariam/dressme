"""Support des robes (ISSUE-05) : génération, scores, saisons, non-régression,
déterminisme et diversification.
"""

import itertools
import random

import pytest

import outfit_engine
from bo4_fixtures import DRESS_DB_ROWS, REFERENCE_DB_ROWS, REFERENCE_WARDROBE, FakeConnection
from outfit_engine import (
    DIVERSITY_ITEM_CAP,
    DIVERSITY_SCORE_WINDOW,
    SEASONS,
    SINGLE_PIECE_COLOR_SCORE,
    garment_role,
    item_warmth,
    outfit_sort_key,
    recommend_outfits,
    season_score,
)
from wardrobe_db_adapter import load_user_wardrobe

ALL = 10_000
VALID_STRUCTURES = (
    ["top", "bottom"], ["top", "bottom", "outerwear"], ["dress"], ["dress", "outerwear"],
)
SINGLE_PIECE_REASON = "Pièce unique : aucune association de couleurs entre pièces n'est évaluée"


def roles(result):
    return [garment_role(i) for i in result["items"]]


def key(result):
    return tuple(str(i.get("id")) for i in result["items"])


def visible(result):
    return (key(result), result["score"], result["color_score"], result["style_score"],
            result["occasion_score"], result["season_score"], tuple(result["explanations"]))


def _season(items, season):
    return season_score(items, season)[0]


def mixed_wardrobe(make_item):
    return [
        make_item("shirt", "white", id="1", name="shirt"),
        make_item("tshirt", "grey", id="2", name="tee"),
        make_item("trousers", "black", id="3", name="trousers"),
        make_item("skirt", "beige", id="4", name="skirt"),
        make_item("jacket", "black", id="5", name="jacket"),
        make_item("dress", "black", id="6", name="black dress"),
        make_item("dress", "red", id="7", name="red dress"),
        make_item("dress", "black", id="8", name="black dress"),  # homonyme, autre identifiant
    ]


# ---------------------------------------------------------------------------
# Génération
# ---------------------------------------------------------------------------

def test_dress_alone(make_item):
    results = recommend_outfits([make_item("dress", "red", name="dress")], top_k=ALL)
    assert [roles(r) for r in results] == [["dress"]]
    assert results[0]["color_score"] == SINGLE_PIECE_COLOR_SCORE * 100
    assert results[0]["explanations"][0] == SINGLE_PIECE_REASON


def test_dress_with_jacket(make_item):
    wardrobe = [make_item("dress", "red", name="dress"), make_item("jacket", "black", name="jacket")]
    assert sorted(roles(r) for r in recommend_outfits(wardrobe, top_k=ALL)) == [["dress"], ["dress", "outerwear"]]


def test_several_dresses_and_jackets(make_item):
    wardrobe = ([make_item("dress", c) for c in ("black", "red", "white")]
                + [make_item("coat", c) for c in ("black", "beige")])
    assert len(recommend_outfits(wardrobe, top_k=ALL)) == 3 * (2 + 1)


@pytest.mark.parametrize("season", SEASONS)
def test_mixed_wardrobe_combination_count_and_structures(make_item, season):
    results = recommend_outfits(mixed_wardrobe(make_item), "university", season, top_k=ALL, diversify=False)
    # haut x bas x (veste + 1) + robes x (veste + 1)
    assert len(results) == 2 * 2 * 2 + 3 * 2
    for r in results:
        assert roles(r) in VALID_STRUCTURES


def test_dress_never_combined_with_top_or_bottom(make_item):
    for r in recommend_outfits(mixed_wardrobe(make_item), top_k=ALL, diversify=False):
        if "dress" in roles(r):
            assert not {"top", "bottom"} & set(roles(r))


@pytest.mark.parametrize("wardrobe_spec, expected", [
    ([("dress", "1")], 1),
    ([("dress", "1"), ("dress", "2")], 2),
    ([("dress", "1"), ("jacket", "2")], 2),
    ([("dress", "1"), ("trousers", "2")], 1),   # le pantalon seul ne forme rien
    ([("dress", "1"), ("shirt", "2")], 1),
    ([("jacket", "1")], 0),
])
def test_small_wardrobes_with_dresses(make_item, wardrobe_spec, expected):
    wardrobe = [make_item(category, id=item_id, name=category) for category, item_id in wardrobe_spec]
    for season in SEASONS:
        assert len(recommend_outfits(wardrobe, "university", season, top_k=5)) == expected


# ---------------------------------------------------------------------------
# Couleur
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("color", ["black", "red", "light_pink", "unknown"])
def test_single_piece_color_is_conventional(make_item, color):
    result = recommend_outfits([make_item("dress", color)], top_k=1)[0]
    assert result["color_score"] == 90.0
    assert SINGLE_PIECE_REASON in result["explanations"]


def test_dress_with_jacket_uses_pair_color_rules(make_item):
    wardrobe = [make_item("dress", "red", name="dress"), make_item("jacket", "black", name="jacket")]
    with_jacket = next(r for r in recommend_outfits(wardrobe, top_k=ALL) if len(r["items"]) == 2)
    assert with_jacket["color_score"] == 90.0
    assert "Une couleur neutre équilibre la tenue" in with_jacket["explanations"]
    assert SINGLE_PIECE_REASON not in with_jacket["explanations"]


# ---------------------------------------------------------------------------
# Saisons
# ---------------------------------------------------------------------------

def test_dress_covers_torso_and_legs_with_existing_weights(make_item):
    dress = make_item("dress", "black")  # catégorie : {light, medium}
    for season in SEASONS:
        torso = outfit_engine._expected_suitability([("light", "medium")], outfit_engine.TORSO_SUITABILITY[season])
        legs = outfit_engine._expected_suitability([("light", "medium")], outfit_engine.BOTTOM_SUITABILITY[season])
        expected = outfit_engine.TORSO_WEIGHT * torso + (1 - outfit_engine.TORSO_WEIGHT) * legs
        assert _season([dress], season) == pytest.approx(expected)


def test_dress_category_warmth_is_light_or_medium():
    assert item_warmth({"category": "dress"}) == (("light", "medium"), "category")
    # Le texte reste prioritaire (règles existantes)
    assert item_warmth({"category": "dress", "warmth": "heavy"}) == (("heavy",), "attribute")
    assert item_warmth({"category": "dress", "warmth_source": "text_conflict",
                        "text_warmth_levels": ["heavy"]}) == (("light", "medium", "heavy"), "conflict")


def test_light_and_warm_dresses_across_seasons(make_item):
    light = make_item("dress", "white", warmth="light", sleeve_length="sleeveless", name="light dress")
    warm = make_item("dress", "white", warmth="heavy", sleeve_length="long", name="warm dress")
    assert _season([light], "summer") > _season([warm], "summer")
    assert _season([warm], "winter") > _season([light], "winter")
    _, reasons = season_score([warm], "summer")
    assert "warm dress trop chaud pour l'été (attribut)" in reasons
    _, reasons = season_score([light], "winter")
    assert "Bras peu couverts (sans manches) pour la saison : winter" in reasons


def test_coat_over_light_dress_in_winter(make_item, monkeypatch):
    light = make_item("dress", "white", warmth="light", sleeve_length="sleeveless", name="light dress")
    warm = make_item("dress", "white", warmth="medium", sleeve_length="long", name="warm dress")
    coat = make_item("coat", "black", warmth="heavy", sleeve_length="long", name="coat")
    assert _season([light, coat], "winter") > _season([light], "winter")
    assert _season([warm, coat], "winter") > _season([light, coat], "winter")   # couche intérieure
    # Pénalité uniquement : jamais plus que sans terme de couche intérieure
    with_inner = _season([light, coat], "winter")
    monkeypatch.setattr(outfit_engine, "INNER_LAYER_WEIGHT", 0.0)
    assert with_inner <= _season([light, coat], "winter")


def test_dress_not_treated_as_exposed_legs(make_item):
    _, reasons = season_score([make_item("dress", "black")], "winter")
    assert not any("peu adapté à la saison" in r and "dress" in r for r in reasons)


def test_dress_warmth_explanation_not_duplicated(make_item):
    dress = make_item("dress", "black", name="odd dress", warmth_source="text_contradictory")
    _, reasons = season_score([dress], "autumn")
    assert reasons.count("Chaleur de odd dress : description contradictoire, chaleur incertaine") == 1


def test_known_dress_style_drives_occasion(make_item):
    formal = make_item("dress", "black", style="formal", name="formal dress")
    casual = make_item("dress", "black", style="casual", name="casual dress")
    work = recommend_outfits([formal, casual], "work", "spring", top_k=1)[0]
    assert work["items"][0]["name"] == "formal dress"
    assert work["occasion_score"] == 100.0


# ---------------------------------------------------------------------------
# Non-régression des tenues classiques
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("season", SEASONS)
def test_adding_dresses_does_not_change_classic_outfits(make_item, season):
    classic = [i for i in mixed_wardrobe(make_item) if garment_role(i) != "dress"]
    with_dresses = mixed_wardrobe(make_item)
    before = {key(r): visible(r) for r in recommend_outfits(classic, "university", season, top_k=ALL, diversify=False)}
    after = {key(r): visible(r) for r in recommend_outfits(with_dresses, "university", season, top_k=ALL, diversify=False)
             if "dress" not in roles(r)}
    assert after == before


@pytest.mark.parametrize("season", SEASONS)
@pytest.mark.parametrize("diversify", [True, False])
def test_reference_wardrobe_without_dresses_unchanged(season, diversify):
    # Valeurs figées dans test_outfit_engine ; ici : pas de robe -> aucune tenue "robe".
    for r in recommend_outfits(REFERENCE_WARDROBE, "university", season, top_k=ALL, diversify=diversify):
        assert roles(r) in (["top", "bottom"], ["top", "bottom", "outerwear"])


# ---------------------------------------------------------------------------
# Déterminisme et diversification
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("season", SEASONS)
@pytest.mark.parametrize("diversify", [True, False])
def test_permutations_with_dresses(make_item, season, diversify):
    wardrobe = mixed_wardrobe(make_item)
    expected = [visible(r) for r in recommend_outfits(wardrobe, "university", season, top_k=5, diversify=diversify)]
    rng = random.Random(5)
    for _ in range(30):
        shuffled = wardrobe[:]
        rng.shuffle(shuffled)
        got = [visible(r) for r in recommend_outfits(shuffled, "university", season, top_k=5, diversify=diversify)]
        assert got == expected


def test_dress_alone_precedes_dress_with_jacket_on_equal_score(make_item):
    dress = make_item("dress", "red", id="9", warmth="medium", name="dress")
    jacket = make_item("jacket", "black", id="1", warmth="medium", name="jacket")
    results = recommend_outfits([jacket, dress], "university", "spring", top_k=ALL)
    assert results[0]["score"] == results[1]["score"]
    assert [len(r["items"]) for r in results] == [1, 2]


@pytest.mark.parametrize("season", SEASONS)
def test_diversification_invariants_with_dresses(make_item, season):
    wardrobe = mixed_wardrobe(make_item)
    ranked = recommend_outfits(wardrobe, "university", season, top_k=ALL, diversify=False)
    raw_visible = {key(r): visible(r) for r in ranked}
    best = ranked[0]["score"]
    window = [r for r in ranked if r["score"] >= best - DIVERSITY_SCORE_WINDOW]
    selected = recommend_outfits(wardrobe, "university", season, top_k=5)
    assert key(selected[0]) == key(ranked[0])
    assert selected == sorted(selected, key=outfit_sort_key)
    assert len({key(r) for r in selected}) == len(selected) == 5
    assert all(visible(r) == raw_visible[key(r)] for r in selected)
    counts = lambda rs: max(
        sum(1 for r in rs if i in key(r)) for i in {i for r in rs for i in key(r)})
    feasible = any(counts(c) <= DIVERSITY_ITEM_CAP for c in itertools.combinations(window, 5))
    if feasible:
        assert counts(selected) <= DIVERSITY_ITEM_CAP


# ---------------------------------------------------------------------------
# Adaptateur : robes du catalogue
# ---------------------------------------------------------------------------

def test_catalog_dresses_reach_the_engine():
    wardrobe = load_user_wardrobe(FakeConnection(REFERENCE_DB_ROWS + DRESS_DB_ROWS), 1)
    dresses = {i["name"]: i for i in wardrobe if i["category"] == "dress"}
    assert len(wardrobe) == 10 and len(dresses) == 5
    assert (dresses["Elva Dress"]["warmth"], dresses["Elva Dress"]["warmth_source"]) == ("light", "text")
    assert {name: d["sleeve_length"] for name, d in dresses.items()} == {
        "Panda Dress": "sleeveless",
        "Swift Dress(1)": "unknown",   # "long, slightly wider cuffed sleeves" : non détecté (limite)
        "2-PACK Justin dress": "short",
        "Mara off shoulder dress": "long",
        "Elva Dress": "sleeveless",
    }
    for season in SEASONS:
        for r in recommend_outfits(wardrobe, "university", season, top_k=ALL):
            assert roles(r) in VALID_STRUCTURES
