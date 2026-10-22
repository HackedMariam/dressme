"""Diversification du top-k par contrainte de couverture (ISSUE-07).

La diversification ne modifie ni les scores ni les explications : elle choisit
quelles tenues renvoyer. diversify=False rend exactement le classement brut
d'ISSUE-06.
"""

import collections
import itertools
import random

import pytest

from bo4_fixtures import REFERENCE_DB_ROWS, REFERENCE_WARDROBE, FakeConnection
from outfit_engine import (
    DIVERSITY_ITEM_CAP,
    DIVERSITY_SCORE_WINDOW,
    SEASONS,
    outfit_sort_key,
    recommend_outfits,
    select_diverse,
)
from wardrobe_db_adapter import load_user_wardrobe

ALL = 10_000


def key(result):
    return tuple(str(i.get("id")) for i in result["items"])


def visible(result):
    return (key(result), result["score"], result["color_score"], result["style_score"],
            result["occasion_score"], result["season_score"], tuple(result["explanations"]))


def max_repetition(results):
    return max(collections.Counter(i for r in results for i in key(r)).values())


def raw(wardrobe, season, top_k=ALL):
    return recommend_outfits(wardrobe, "university", season, top_k=top_k, diversify=False)


def diverse(wardrobe, season, top_k=5):
    return recommend_outfits(wardrobe, "university", season, top_k=top_k)


def tie_rich_wardrobe(make_item):
    return (
        [make_item("shirt", "white", id=i, name="white shirt") for i in ("2", "10", "9", "31")]
        + [make_item("trousers", "black", id=i, name="black trousers") for i in ("5", "50", "7")]
        + [make_item("jacket", "grey", id=i, name="grey jacket") for i in ("100", "11")]
    )


# ---------------------------------------------------------------------------
# Neutralité et invariants
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("season", SEASONS)
def test_diversify_false_is_exactly_the_raw_ranking(make_item, season):
    for wardrobe in (REFERENCE_WARDROBE, tie_rich_wardrobe(make_item)):
        for top_k in (1, 3, 5, ALL):
            expected = [visible(r) for r in raw(wardrobe, season)[:top_k]]
            assert [visible(r) for r in raw(wardrobe, season, top_k)] == expected


@pytest.mark.parametrize("season", SEASONS)
def test_invariants_of_diversified_selection(make_item, season):
    wardrobe = tie_rich_wardrobe(make_item)
    full = {key(r): visible(r) for r in raw(wardrobe, season)}
    for top_k in (1, 2, 3, 5, 8):
        selected = diverse(wardrobe, season, top_k)
        assert len(selected) == min(top_k, len(full))
        assert len({key(r) for r in selected}) == len(selected)               # pas de doublon
        assert selected == sorted(selected, key=outfit_sort_key)              # tri ISSUE-06
        assert key(selected[0]) == key(raw(wardrobe, season)[0])              # n°1 conservé
        for r in selected:
            assert visible(r) == full[key(r)]                                 # score/explications inchangés


@pytest.mark.parametrize("season", SEASONS)
def test_top_k_one_and_top_k_at_least_all_are_unchanged(make_item, season):
    wardrobe = tie_rich_wardrobe(make_item)
    everything = raw(wardrobe, season)
    assert [visible(r) for r in diverse(wardrobe, season, 1)] == [visible(everything[0])]
    for top_k in (len(everything), len(everything) + 5):
        assert [visible(r) for r in diverse(wardrobe, season, top_k)] == [visible(r) for r in everything]


def test_neutral_parameters_reproduce_raw_ranking(make_item):
    ranked = raw(tie_rich_wardrobe(make_item), "autumn")
    assert select_diverse(ranked, 5, window=0.0, cap=5) == ranked[:5]


# ---------------------------------------------------------------------------
# Compromis pertinence / diversité
# ---------------------------------------------------------------------------

def cap_feasible_in_window(ranked, top_k):
    """Force brute : existe-t-il top_k tenues de la fenêtre respectant le plafond ?"""
    best = ranked[0]["score"]
    window = [r for r in ranked if r["score"] >= best - DIVERSITY_SCORE_WINDOW]
    return any(
        max_repetition(list(combo)) <= DIVERSITY_ITEM_CAP
        for combo in itertools.combinations(window, top_k)
    )


@pytest.mark.parametrize("extra_jacket", [False, True])
@pytest.mark.parametrize("season", SEASONS)
def test_cap_respected_whenever_feasible(make_item, season, extra_jacket):
    """Garde-robe riche en ex aequo : plafond respecté s'il est réalisable dans la
    fenêtre ; sinon repli documenté, toujours dans la fenêtre."""
    wardrobe = tie_rich_wardrobe(make_item)
    if extra_jacket:  # rend le plafond réalisable quand seules les tenues avec veste sont dans la fenêtre
        wardrobe.append(make_item("jacket", "grey", id="12", name="grey jacket"))
    ranked = raw(wardrobe, season)
    before, after = ranked[:5], diverse(wardrobe, season, 5)
    best = ranked[0]["score"]
    assert max_repetition(before) > DIVERSITY_ITEM_CAP
    assert all(r["score"] >= best - DIVERSITY_SCORE_WINDOW for r in after)
    if cap_feasible_in_window(ranked, 5):
        assert max_repetition(after) <= DIVERSITY_ITEM_CAP
    else:
        assert max_repetition(after) < max_repetition(before)


def test_infeasible_cap_case_is_the_two_jacket_winter(make_item):
    """Documente le cas mesuré : en hiver, seules les tenues avec veste sont dans
    la fenêtre ; 2 vestes ne permettent que 4 tenues sous le plafond de 2."""
    ranked = raw(tie_rich_wardrobe(make_item), "winter")
    assert not cap_feasible_in_window(ranked, 5)
    assert cap_feasible_in_window(ranked, 4)


@pytest.mark.parametrize("season", SEASONS)
def test_diversity_gain_has_bounded_relevance_cost(make_item, season):
    wardrobe = tie_rich_wardrobe(make_item) + [
        make_item("trousers", "navy_blue", id="60", name="navy trousers"),
        make_item("shirt", "light_blue", id="61", name="light blue shirt"),
    ]
    before, after = raw(wardrobe, season, 5), diverse(wardrobe, season, 5)
    distinct = lambda rs: len({i for r in rs for i in key(r)})
    assert distinct(after) >= distinct(before)
    assert max_repetition(after) <= max_repetition(before)
    mean = lambda rs: sum(r["score"] for r in rs) / len(rs)
    assert mean(before) - mean(after) <= DIVERSITY_SCORE_WINDOW


# ---------------------------------------------------------------------------
# Repli (relâchement) et petites garde-robes
# ---------------------------------------------------------------------------

def test_relaxation_prefers_window_repetition_over_lower_quality(make_item):
    """Plafond irréalisable dans la fenêtre : on répète un vêtement proche du
    meilleur score plutôt que de descendre vers une tenue nettement moins bonne."""
    shirt = make_item("shirt", "white", id="1", name="white shirt")
    heavy = make_item("sweater", "white", id="2", warmth="heavy", name="heavy sweater")  # très pénalisé en été
    bottoms = [make_item("trousers", c, id=str(n), name=f"{c} trousers")
               for n, c in ((3, "black"), (4, "grey"), (5, "navy_blue"))]
    wardrobe = [shirt, heavy] + bottoms
    ranked = raw(wardrobe, "summer")
    best = ranked[0]["score"]
    assert ranked[3]["score"] < best - DIVERSITY_SCORE_WINDOW   # le pull est hors fenêtre
    selected = diverse(wardrobe, "summer", 3)
    names = [r["items"][0]["name"] for r in selected]
    assert names == ["white shirt"] * 3                         # plafond relâché dans la fenêtre
    assert all(r["score"] >= best - DIVERSITY_SCORE_WINDOW for r in selected)


def test_window_exceeded_only_when_window_is_too_small(make_item):
    """Cas documenté : moins de top_k tenues dans la fenêtre -> on complète avec
    les meilleures tenues restantes, au-delà des 3 points."""
    shirt = make_item("shirt", "white", id="1", name="white shirt")
    heavy = make_item("sweater", "white", id="2", warmth="heavy", name="heavy sweater")
    trousers = make_item("trousers", "black", id="3", name="trousers")
    wardrobe = [shirt, heavy, trousers]
    ranked = raw(wardrobe, "summer")
    selected = diverse(wardrobe, "summer", 2)
    assert [visible(r) for r in selected] == [visible(r) for r in ranked[:2]]
    assert selected[1]["score"] < selected[0]["score"] - DIVERSITY_SCORE_WINDOW


@pytest.mark.parametrize("season", SEASONS)
def test_reference_wardrobe_unchanged(season):
    """Un seul bas et une seule veste : le plafond est irréalisable, le repli
    redonne exactement le top 5 brut."""
    for wardrobe in (REFERENCE_WARDROBE, load_user_wardrobe(FakeConnection(REFERENCE_DB_ROWS), 1)):
        assert [visible(r) for r in diverse(wardrobe, season, 5)] == [visible(r) for r in raw(wardrobe, season, 5)]


@pytest.mark.parametrize("wardrobe_spec, expected_count", [
    ([], 0),
    ([("shirt", "1")], 0),
    ([("shirt", "1"), ("trousers", "2")], 1),
    ([("shirt", "1"), ("trousers", "2"), ("jacket", "3")], 2),
    ([("shirt", "1"), ("trousers", "2"), ("jeans", "3"), ("jacket", "4")], 4),
])
def test_small_wardrobes(make_item, wardrobe_spec, expected_count):
    wardrobe = [make_item(category, id=item_id, name=category) for category, item_id in wardrobe_spec]
    for season in SEASONS:
        selected = diverse(wardrobe, season, 5)
        assert len(selected) == expected_count
        assert [visible(r) for r in selected] == [visible(r) for r in raw(wardrobe, season, 5)]


# ---------------------------------------------------------------------------
# Déterminisme
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("season", SEASONS)
@pytest.mark.parametrize("top_k", [2, 3, 5])
def test_diversified_selection_stable_under_permutation(make_item, season, top_k):
    wardrobe = tie_rich_wardrobe(make_item)
    expected = [visible(r) for r in diverse(wardrobe, season, top_k)]
    rng = random.Random(7)
    for _ in range(30):
        shuffled = wardrobe[:]
        rng.shuffle(shuffled)
        assert [visible(r) for r in diverse(shuffled, season, top_k)] == expected
