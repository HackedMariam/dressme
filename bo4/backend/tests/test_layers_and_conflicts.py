"""Couche intérieure, manches et conflits texte/catégorie (moteur saisonnier).

Comprend des tests de QUALITÉ DE CLASSEMENT : ils vérifient des préférences
relatives attendues (à conditions équivalentes), pas des valeurs absolues.
"""

import pytest

import outfit_engine
from bo4_fixtures import outfit_key
from outfit_engine import (
    SEASONS,
    WARMTH_LEVELS,
    item_warmth,
    recommend_outfits,
    season_score,
    sleeve_coverage,
)

ALL = 100


def _season(items, season):
    return season_score(items, season)[0]


@pytest.fixture
def puffer(make_item):
    return make_item("jacket", "black", warmth="heavy", sleeve_length="long", name="puffer")


@pytest.fixture
def trousers(make_item):
    return make_item("trousers", "black", name="trousers")


def _top_variants(make_item):
    """Hauts de chaleur et de manches variées (même couleur, même style)."""
    return [
        make_item("top", "white", sleeve_length="sleeveless", name="tank"),
        make_item("top", "white", warmth="light", sleeve_length="sleeveless", name="light tank"),
        make_item("shirt", "white", sleeve_length="short", name="short-sleeved shirt"),
        make_item("shirt", "white", sleeve_length="long", name="long-sleeved shirt"),
        make_item("tshirt", "white", name="tee"),
        make_item("sweater", "white", sleeve_length="long", name="sweater"),
        make_item("sweater", "white", warmth="heavy", sleeve_length="long", name="heavy sweater"),
        make_item("shirt", "white", name="shirt (no info)"),
    ]


def _without_inner_layer(monkeypatch, items, season):
    monkeypatch.setattr(outfit_engine, "INNER_LAYER_WEIGHT", 0.0)
    try:
        return _season(items, season)
    finally:
        monkeypatch.undo()


# ---------------------------------------------------------------------------
# Qualité des classements
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("tank_attrs", [
    {"sleeve_length": "sleeveless"},
    {"sleeve_length": "sleeveless", "warmth": "light"},
    {"sleeve_length": "short"},
])
def test_winter_sweater_under_puffer_beats_sleeveless_under_puffer(make_item, puffer, trousers, tank_attrs):
    sweater = make_item("sweater", "white", sleeve_length="long", name="sweater")
    tank = make_item("top", "white", name="tank", **tank_attrs)
    ranking = [outfit_key(r) for r in recommend_outfits([tank, sweater, trousers, puffer], "university", "winter", top_k=ALL)]
    assert ranking.index(("sweater", "trousers", "puffer")) < ranking.index(("tank", "trousers", "puffer"))


def test_winter_light_top_under_puffer_still_beats_light_top_alone(make_item, puffer, trousers):
    tank = make_item("top", "white", sleeve_length="sleeveless", name="tank")
    assert _season([tank, trousers, puffer], "winter") > _season([tank, trousers], "winter")


@pytest.mark.parametrize("season", SEASONS)
def test_inner_layer_is_penalty_only(make_item, puffer, trousers, monkeypatch, season):
    """La couche intérieure ne peut jamais augmenter le score."""
    for top in _top_variants(make_item):
        for jacket in (puffer, make_item("jacket", "beige", warmth="light", name="light jacket"),
                       make_item("blazer", "grey", name="blazer")):
            items = [top, trousers, jacket]
            assert _season(items, season) <= _without_inner_layer(monkeypatch, items, season) + 1e-12


def test_summer_hot_jacket_gets_no_compensation(make_item, puffer, trousers, monkeypatch):
    """En été, un haut léger sous une doudoune ne "rattrape" rien."""
    for top in _top_variants(make_item):
        with_puffer = [top, trousers, puffer]
        assert _season(with_puffer, "summer") == _without_inner_layer(monkeypatch, with_puffer, "summer")
        assert _season(with_puffer, "summer") <= _season([top, trousers], "summer")
        if top.get("warmth") != "heavy":
            # Un haut déjà "heavy" sature le niveau de chaleur : la doudoune
            # ne peut pas l'aggraver dans ce modèle (limite documentée).
            assert _season(with_puffer, "summer") < _season([top, trousers], "summer")


@pytest.mark.parametrize("season", SEASONS)
def test_outfits_without_jacket_ignore_inner_layer(make_item, trousers, monkeypatch, season):
    """Sans veste, le terme de couche intérieure n'a aucun effet."""
    for top in _top_variants(make_item):
        items = [top, trousers]
        assert _season(items, season) == _without_inner_layer(monkeypatch, items, season)


@pytest.mark.parametrize("season", SEASONS)
def test_outfits_without_new_attributes_unchanged_by_sleeves(make_item, trousers, monkeypatch, season):
    """Sans sleeve_length, le facteur manches est neutre (non-régression)."""
    top = make_item("shirt", "white")
    neutral = {s: {k: 1.0 for k in table} for s, table in outfit_engine.SLEEVE_FACTOR.items()}
    expected = _season([top, trousers], season)
    monkeypatch.setattr(outfit_engine, "SLEEVE_FACTOR", neutral)
    assert _season([top, trousers], season) == expected


@pytest.mark.parametrize("season", SEASONS)
def test_sleeve_effect_is_exactly_the_documented_factor(make_item, trousers, season):
    """Sans veste, les manches multiplient le buste par SLEEVE_FACTOR, rien d'autre."""
    plain = make_item("shirt", "white")
    torso = outfit_engine._expected_suitability([("light", "medium")], outfit_engine.TORSO_SUITABILITY[season])
    for sleeve, factor in outfit_engine.SLEEVE_FACTOR[season].items():
        sleeved = make_item("shirt", "white", sleeve_length=sleeve)
        delta = _season([plain, trousers], season) - _season([sleeved, trousers], season)
        assert delta == pytest.approx(outfit_engine.TORSO_WEIGHT * torso * (1 - factor))
        assert delta >= 0


# ---------------------------------------------------------------------------
# Manches : facteur distinct de la chaleur
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("sleeve", ["short", "sleeveless", "long", "three_quarter"])
def test_sleeves_never_change_warmth_levels(sleeve):
    assert item_warmth({"category": "shirt", "sleeve_length": sleeve}) == (("light", "medium"), "category")
    assert item_warmth({"category": "sweater", "sleeve_length": sleeve}) == (("medium", "heavy"), "category")


@pytest.mark.parametrize("sleeves, expected", [
    (["short", "long"], "long"),
    (["short", "unknown"], "unknown"),       # la pièce inconnue pourrait couvrir plus
    (["long", "unknown"], "long"),
    (["sleeveless", "sleeveless"], "sleeveless"),
    (["three_quarter"], "three_quarter"),
    (["bogus"], "unknown"),
    ([], "unknown"),
])
def test_sleeve_coverage(sleeves, expected):
    assert sleeve_coverage([{"sleeve_length": s} for s in sleeves]) == expected


def test_long_sleeves_in_summer_explained(make_item, trousers):
    _, reasons = season_score([make_item("shirt", sleeve_length="long"), trousers], "summer")
    assert "Bras couverts (manches longues) : un peu chaud pour l'été" in reasons


def test_sleeveless_in_winter_explained(make_item, trousers):
    _, reasons = season_score([make_item("top", sleeve_length="sleeveless"), trousers], "winter")
    assert "Bras peu couverts (sans manches) pour la saison : winter" in reasons


def test_inner_layer_explained_in_winter(make_item, puffer, trousers):
    tank = make_item("top", "white", sleeve_length="sleeveless", name="tank")
    _, reasons = season_score([tank, trousers, puffer], "winter")
    assert ("Couche intérieure (tank) légère ou peu couvrante : prévoir une couche "
            "intermédiaire si la veste est retirée") in reasons


# ---------------------------------------------------------------------------
# Conflits, contradictions, indices partiels
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("item, expected", [
    # Union exacte, sans niveau intermédiaire ajouté
    ({"category": "shorts", "warmth_source": "text_conflict", "text_warmth_levels": ["heavy"]},
     (("light", "heavy"), "conflict")),
    ({"category": "sweater", "warmth_source": "text_conflict", "text_warmth_levels": ["light"]},
     (("light", "medium", "heavy"), "conflict")),
    ({"category": "tshirt", "warmth_source": "text_conflict", "text_warmth_levels": ["heavy"]},
     (("light", "heavy"), "conflict")),
    # Contradiction interne : incertitude explicite, pas de retour à la catégorie
    ({"category": "sweater", "warmth_source": "text_contradictory", "text_warmth_levels": []},
     (WARMTH_LEVELS, "contradictory")),
    ({"category": "tshirt", "warmth_source": "text_contradictory"},
     (WARMTH_LEVELS, "contradictory")),
    # Indices partiels : restreignent la catégorie
    ({"category": "jacket", "warmth_source": "text_partial", "text_warmth_levels": ["medium", "heavy"]},
     (("medium", "heavy"), "text_partial")),
    ({"category": "coat", "warmth_source": "text_partial", "text_warmth_levels": ["medium", "heavy"]},
     (("medium", "heavy"), "text_partial")),
    # Informations incomplètes : comportement antérieur
    ({"category": "sweater", "warmth_source": "text_conflict"}, (("medium", "heavy"), "category")),
    ({"category": "shirt", "warmth_source": "text_partial", "text_warmth_levels": ["heavy"]},
     (("light", "medium"), "category")),
    # Un attribut tranché reste prioritaire
    ({"category": "jacket", "warmth": "heavy", "warmth_source": "text"}, (("heavy",), "attribute")),
])
def test_item_warmth_sources(item, expected):
    assert item_warmth(item) == expected


def test_conflict_expectation_uses_discrete_union(make_item):
    """{light, heavy} : espérance sur ces deux niveaux seulement (pas de medium)."""
    tee = make_item("tshirt", "white", warmth_source="text_conflict", text_warmth_levels=["heavy"])
    expected_torso = (1.0 + 0.1) / 2  # TORSO_SUITABILITY summer : light 1.0, heavy 0.1
    expected = 0.65 * expected_torso + 0.35 * 1.0
    assert _season([tee, make_item("shorts")], "summer") == pytest.approx(expected)


def test_conflict_and_contradiction_are_explained(make_item, trousers):
    sweater = make_item("sweater", name="light jumper", warmth_source="text_conflict", text_warmth_levels=["light"])
    _, reasons = season_score([sweater, trousers], "winter")
    assert "Chaleur de light jumper : description et catégorie divergent, plusieurs niveaux retenus" in reasons
    tee = make_item("tshirt", name="odd tee", warmth_source="text_contradictory")
    _, reasons = season_score([tee, trousers], "winter")
    assert "Chaleur de odd tee : description contradictoire, chaleur incertaine" in reasons


def test_conflict_moves_estimate_towards_text(make_item, trousers):
    """Un pull décrit "lightweight" est moins pénalisé en été qu'un pull ordinaire."""
    plain = make_item("sweater", "white")
    light = make_item("sweater", "white", warmth_source="text_conflict", text_warmth_levels=["light"])
    assert _season([light, trousers], "summer") > _season([plain, trousers], "summer")
    assert _season([light, trousers], "winter") < _season([plain, trousers], "winter")
