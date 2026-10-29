"""Départage déterministe des ex aequo (ISSUE-06).

Le départage par identifiant est purement technique : il rend le classement
indépendant de l'ordre de la garde-robe. Il ne modifie ni les scores ni les
explications, et n'exprime aucune pertinence ou diversité.
"""

import itertools
import random

import pytest

import outfit_engine
from bo4_fixtures import REFERENCE_DB_ROWS, REFERENCE_WARDROBE, FakeConnection
from outfit_engine import SEASONS, _item_sort_key, recommend_outfits
from wardrobe_db_adapter import PUBLIC_ITEM_FIELDS, load_user_wardrobe

ALL = 10_000


def snapshot(results):
    """Tout ce qui est visible d'un résultat, dans l'ordre renvoyé."""
    return [
        (
            tuple(str(i.get("id")) for i in r["items"]),
            r["score"], r["color_score"], r["style_score"], r["occasion_score"], r["season_score"],
            tuple(r["explanations"]),
        )
        for r in results
    ]


def public_snapshot(results):
    return [
        (tuple(tuple(i.get(f) for f in PUBLIC_ITEM_FIELDS) for i in r["items"]), r["score"])
        for r in results
    ]


def tie_rich_wardrobe(make_item):
    """Beaucoup de vêtements équivalents : presque tout est ex aequo."""
    return (
        [make_item("shirt", "white", id=i, name="white shirt") for i in ("2", "10", "9", "31")]
        + [make_item("trousers", "black", id=i, name="black trousers") for i in ("5", "50", "7")]
        + [make_item("jacket", "grey", id=i, name="grey jacket") for i in ("100", "11")]
    )


# ---------------------------------------------------------------------------
# Permutations
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("season", SEASONS)
def test_all_120_permutations_of_reference(season):
    expected = snapshot(recommend_outfits(REFERENCE_WARDROBE, "university", season, top_k=ALL))
    for permutation in itertools.permutations(REFERENCE_WARDROBE):
        assert snapshot(recommend_outfits(list(permutation), "university", season, top_k=ALL)) == expected


@pytest.mark.parametrize("season", SEASONS)
def test_all_120_permutations_of_reference_with_extracted_attributes(season):
    wardrobe = load_user_wardrobe(FakeConnection(REFERENCE_DB_ROWS), 1)
    expected = snapshot(recommend_outfits(wardrobe, "university", season, top_k=ALL))
    for permutation in itertools.permutations(wardrobe):
        assert snapshot(recommend_outfits(list(permutation), "university", season, top_k=ALL)) == expected


@pytest.mark.parametrize("season", SEASONS)
@pytest.mark.parametrize("top_k", [1, 3, 5, ALL])
def test_permutations_of_tie_rich_wardrobe(make_item, season, top_k):
    wardrobe = tie_rich_wardrobe(make_item)
    expected = snapshot(recommend_outfits(wardrobe, "university", season, top_k=top_k))
    rng = random.Random(20261014)
    for _ in range(30):
        shuffled = wardrobe[:]
        rng.shuffle(shuffled)
        assert snapshot(recommend_outfits(shuffled, "university", season, top_k=top_k)) == expected


@pytest.mark.parametrize("season", SEASONS)
def test_top_k_cut_inside_tie_group_is_stable(make_item, season):
    wardrobe = tie_rich_wardrobe(make_item)
    full = recommend_outfits(wardrobe, "university", season, top_k=ALL)
    best = full[0]["score"]
    group = [r for r in full if r["score"] == best]
    assert len(group) > 3, "le scénario doit couper un groupe d'ex aequo"
    # Classement brut (ISSUE-06) ; la sélection diversifiée est testée dans test_diversity.py.
    cut = recommend_outfits(list(reversed(wardrobe)), "university", season, top_k=3, diversify=False)
    assert snapshot(cut) == snapshot(group[:3])


# ---------------------------------------------------------------------------
# Identifiants : numériques, textuels, manquants, vides, dupliqués
# ---------------------------------------------------------------------------

def test_natural_order_of_numeric_ids(make_item):
    wardrobe = [make_item("shirt", "white", id=i, name=f"shirt {i}") for i in ("10", "9", "2")]
    wardrobe.append(make_item("trousers", "black", id="1", name="trousers"))
    order = [r["items"][0]["id"] for r in recommend_outfits(wardrobe, top_k=ALL)]
    assert order == ["2", "9", "10"]


@pytest.mark.parametrize("ids, expected", [
    (["10", "9", "2"], ["2", "9", "10"]),
    (["b", "3", "a", "20"], ["3", "20", "a", "b"]),          # numériques d'abord
    ([None, "4", "", "x", "  "], ["4", "x", None, "", "  "]),  # manquants/vides en dernier
    ([7, "8", "6"], ["6", 7, "8"]),                           # entiers acceptés
    (["007", "7", "10"], ["007", "7", "10"]),                 # même valeur : départage textuel
])
def test_item_sort_key_order(ids, expected):
    items = [{"id": i} for i in ids]
    assert [i["id"] for i in sorted(items, key=_item_sort_key)] == expected


def test_missing_ids_ranked_after_identified_items(make_item):
    trousers = make_item("trousers", "black", id="1", name="trousers")
    wardrobe = [
        make_item("shirt", "white", id=None, name="no id"),
        make_item("shirt", "white", id="3", name="id 3"),
        trousers,
    ]
    for permutation in itertools.permutations(wardrobe):
        names = [r["items"][0]["name"] for r in recommend_outfits(list(permutation), top_k=ALL)]
        assert names == ["id 3", "no id"]


def test_homonyms_ordered_by_id_not_by_name(make_item):
    trousers = make_item("trousers", "black", id="1", name="trousers")
    a = make_item("top", "white", id="7", name="Strap top")
    b = make_item("top", "white", id="3", name="Strap top")
    for permutation in itertools.permutations([a, b, trousers]):
        ids = [r["items"][0]["id"] for r in recommend_outfits(list(permutation), top_k=ALL)]
        assert ids == ["3", "7"]


def test_swapping_names_does_not_change_order(make_item):
    trousers = make_item("trousers", "black", id="1", name="trousers")
    first = [make_item("shirt", "white", id="4", name="Alpha"), make_item("shirt", "white", id="8", name="Zulu")]
    second = [make_item("shirt", "white", id="4", name="Zulu"), make_item("shirt", "white", id="8", name="Alpha")]
    order = lambda w: [r["items"][0]["id"] for r in recommend_outfits(w + [trousers], top_k=ALL)]
    assert order(first) == order(second) == ["4", "8"]


def test_duplicate_ids_use_public_fields_as_fallback(make_item):
    trousers = make_item("trousers", "black", id="1", name="trousers")
    x = make_item("shirt", "white", id="5", name="shirt X", article_id="0002")
    y = make_item("shirt", "white", id="5", name="shirt Y", article_id="0001")
    for permutation in itertools.permutations([x, y, trousers]):
        names = [r["items"][0]["name"] for r in recommend_outfits(list(permutation), top_k=ALL)]
        assert names == ["shirt Y", "shirt X"]  # article_id "0001" < "0002"


def test_indistinguishable_items_give_identical_public_output(make_item):
    """Limite documentée : deux vêtements identiques sur tous les champs publics
    ne sont pas départagés, mais le JSON public produit est le même."""
    trousers = make_item("trousers", "black", id="1", name="trousers")
    twin_a = {"id": "5", "name": "twin", "category": "shirt", "color": "white", "style": "unknown", "source": "a"}
    twin_b = dict(twin_a, source="b")  # ne diffère que par un champ non public
    outputs = {
        tuple(public_snapshot(recommend_outfits(list(p), top_k=ALL)))
        for p in itertools.permutations([twin_a, twin_b, trousers])
    }
    assert len(outputs) == 1


def test_two_piece_precedes_its_jacket_variant_on_equal_score(make_item):
    # Couleurs toutes neutres et distinctes, chaleur identique, printemps :
    # la veste ne change ni la couleur moyenne ni la saison.
    top = make_item("sweater", "white", id="2", warmth="medium", name="top")
    bottom = make_item("trousers", "black", id="3", warmth="medium", name="bottom")
    jacket = make_item("jacket", "grey", id="1", warmth="medium", name="jacket")
    results = recommend_outfits([jacket, bottom, top], "university", "spring", top_k=ALL)
    assert results[0]["score"] == results[1]["score"]
    assert [len(r["items"]) for r in results] == [2, 3]


# ---------------------------------------------------------------------------
# Scores et explications inchangés : seul l'ordre change
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("season", SEASONS)
def test_scores_and_explanations_unchanged_by_tie_break(make_item, monkeypatch, season):
    wardrobe = tie_rich_wardrobe(make_item) + load_user_wardrobe(FakeConnection(REFERENCE_DB_ROWS), 1)
    new = recommend_outfits(wardrobe, "university", season, top_k=ALL)
    # Ancien tri : score seul (stable sur l'ordre d'entrée).
    monkeypatch.setattr(outfit_engine, "outfit_sort_key", lambda r: -r["score"])
    old = recommend_outfits(wardrobe, "university", season, top_k=ALL)
    assert sorted(snapshot(new)) == sorted(snapshot(old))
    assert [r["score"] for r in new] == [r["score"] for r in old]


@pytest.mark.parametrize("season", SEASONS)
def test_scores_non_increasing(make_item, season):
    scores = [r["score"] for r in recommend_outfits(tie_rich_wardrobe(make_item), "university", season, top_k=ALL)]
    assert scores == sorted(scores, reverse=True)
