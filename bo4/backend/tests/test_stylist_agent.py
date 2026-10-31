"""Tests du Stylist Agent (I79 + I80).

- Partie 1 : extraction d'intention, validation du LLM, saisons (sans LangGraph ni Ollama).
- Partie 2 : graphe LangGraph complet avec le vrai moteur BO4 et la garde-robe d'exemple
  au format BO1. Le LLM est désactivé ou simulé : les tests ne dépendent pas d'Ollama.
"""

import datetime as dt
import urllib.error
from pathlib import Path

import pytest

import bo1_api_adapter
import stylist_agent as sa
import stylist_feedback

FIXTURE = Path(__file__).parent / "fixtures" / "bo1_items_sample.json"
TODAY = dt.date(2026, 10, 22)  # date fixe : saison déduite = automne
OUTERWEAR = {"jacket", "blazer", "coat", "cardigan"}


# ===================================================================== Partie 1
@pytest.mark.parametrize("message, occasion", [
    ("Je veux une tenue professionnelle pour demain, sans talons.", "work"),
    ("J'ai un entretien demain", "work"),
    ("Une tenue pour aller en cours", "university"),
    ("Qu'est-ce que je mets pour une soirée ?", "evening"),
    ("Un look pour un mariage", "evening"),
    ("Tenue décontractée pour le week-end", "casual"),
    ("Outfit for a job interview", "work"),
    ("Je veux une tenue", None),
])
def test_rules_occasion(message, occasion):
    assert sa.extract_with_rules(message)["occasion"] == occasion


@pytest.mark.parametrize("message, season", [
    ("une tenue pour l'hiver", "winter"),
    ("il fait froid aujourd'hui", "winter"),
    ("une tenue d'été", "summer"),
    ("au printemps", "spring"),
    ("ça a été une longue journée", None),   # « été » participe passé, pas la saison
])
def test_rules_season(message, season):
    assert sa.extract_with_rules(message)["season"] == season


def test_rules_constraints():
    result = sa.extract_with_rules("Pour une soirée, sans veste ni jupe, et pas de noir. Sans talons !")
    assert result["exclude_categories"] == ["outerwear", "skirt"]
    assert result["exclude_colors"] == ["black"]
    assert result["unsupported"] == ["talons"]


def test_rules_when_and_another():
    assert sa.extract_with_rules("pour demain")["when"] == "tomorrow"
    assert sa.extract_with_rules("pour ce soir")["when"] == "today"
    assert sa.extract_with_rules("Je n'aime pas, une autre ?")["wants_another"] is True
    assert sa.extract_with_rules("une tenue pour le travail")["wants_another"] is False


def test_noir_is_not_read_as_negation():
    assert sa.extract_with_rules("une tenue noire pour le travail")["exclude_colors"] == []


@pytest.mark.parametrize("raw", [None, "texte", 42, []])
def test_invalid_llm_output_is_rejected(raw):
    assert sa.validate_llm_output(raw) is None


def test_llm_output_is_restricted_to_allowed_values():
    clean = sa.validate_llm_output({
        "occasion": "beach", "season": "winter", "exclude_categories": ["dress", "socks"],
        "exclude_colors": ["Black", "fluo"], "wants_another": "yes"})
    assert clean == {"occasion": None, "season": "winter", "exclude_categories": ["dress"],
                     "exclude_colors": ["black"], "wants_another": False}


def _llm(**overrides):
    base = {"occasion": "work", "season": None, "exclude_categories": [], "exclude_colors": [],
            "wants_another": False}
    base.update(overrides)
    return base


def test_hallucinated_llm_constraints_are_rejected():
    """Cas réel observé avec qwen2.5:3b : contraintes inventées alors que rien n'était demandé."""
    clean = _llm(season="autumn", exclude_categories=["skirt", "jeans"], exclude_colors=["black"],
                 wants_another=True)
    grounded, rejected = sa.ground_llm_output(clean, "Je présente mon projet devant un jury jeudi")
    assert grounded == _llm()
    assert len(rejected) == 5


def test_stated_llm_constraints_are_kept():
    clean = _llm(exclude_categories=["skirt"], exclude_colors=["black"], season="winter")
    grounded, rejected = sa.ground_llm_output(clean, "Évite le noir, pas de jupe, il fait froid")
    assert grounded == clean and rejected == []


def test_constraint_word_without_negation_is_rejected():
    grounded, _ = sa.ground_llm_output(_llm(exclude_categories=["dress"]), "Je veux une robe")
    assert grounded["exclude_categories"] == []


@pytest.mark.parametrize("month, season", [(1, "winter"), (4, "spring"), (7, "summer"),
                                           (10, "autumn"), (12, "winter")])
def test_season_for(month, season):
    assert sa.season_for(dt.date(2026, month, 15)) == season


def test_ollama_unavailable_returns_none(monkeypatch):
    def fake_urlopen(*args, **kwargs):
        raise urllib.error.URLError("refused")
    monkeypatch.setattr(sa.urllib.request, "urlopen", fake_urlopen)
    assert sa.ollama_extract("une tenue pour le travail") is None


# ===================================================================== Partie 2
def fixture_loader():
    wardrobe, report = bo1_api_adapter.adapt_wardrobe(bo1_api_adapter.load_bo1_items_from_file(FIXTURE))
    report["source"] = "fixture"
    return wardrobe, report


@pytest.fixture
def wardrobe_by_id():
    wardrobe, _ = fixture_loader()
    return {item["id"]: item for item in wardrobe}


@pytest.fixture
def make_graph():
    pytest.importorskip("langgraph")
    pytest.importorskip("outfit_engine")

    def factory(llm=None, loader=fixture_loader, weather=None, feedback=None, engine=None, advice=None):
        return sa.build_graph(llm=llm, wardrobe_loader=loader, today=lambda: TODAY, weather=weather,
                              feedback_store=feedback, engine=engine, advice=advice)
    return factory


def run(graph, message, thread="t1"):
    config = {"configurable": {"thread_id": thread}}
    graph.invoke(sa.new_turn(message), config)
    return graph.get_state(config).values


def outfit_items(state, wardrobe_by_id):
    return [[wardrobe_by_id[i] for i in sa._outfit_ids(o)] for o in state["outfits"]]


def test_missing_occasion_triggers_clarification(make_graph):
    state = run(make_graph(), "Je veux une tenue")
    assert "Pour quelle occasion" in state["response"]
    assert state["outfits"] == []
    assert [line.split()[0] for line in state["trace"]] == ["extract_intent", "clarify"]


def test_full_pipeline_recommends_only_wardrobe_items(make_graph, wardrobe_by_id):
    state = run(make_graph(), "J'ai un entretien demain")
    assert state["request"]["occasion"] == "work"
    assert state["request"]["season"] == "autumn"
    assert 1 <= len(state["outfits"]) <= 3
    for outfit in state["outfits"]:
        assert set(sa._outfit_ids(outfit)) <= set(wardrobe_by_id)
    assert [line.split()[0] for line in state["trace"]] == [
        "extract_intent", "get_weather", "fetch_wardrobe", "apply_constraints", "recommend",
        "style_advice", "respond"]
    assert "score" in state["response"]


def test_conversation_memory_across_turns(make_graph):
    graph = make_graph()
    first = run(graph, "Je veux une tenue")
    assert first["outfits"] == []
    second = run(graph, "Pour le travail")
    assert second["request"]["occasion"] == "work"
    assert second["outfits"]
    assert len(second["history"]) == 4  # 2 messages utilisateur + 2 réponses


def test_regeneration_returns_new_outfits(make_graph):
    graph = make_graph()
    first = run(graph, "Une tenue décontractée pour le week-end")
    second = run(graph, "Je n'aime pas, une autre ?")
    first_sets = {frozenset(sa._outfit_ids(o)) for o in first["outfits"]}
    second_sets = {frozenset(sa._outfit_ids(o)) for o in second["outfits"]}
    assert second["request"]["occasion"] == "casual"   # contexte conservé
    assert not first_sets & second_sets


def test_hard_constraint_without_jacket(make_graph, wardrobe_by_id):
    state = run(make_graph(), "Une tenue pour le travail, sans veste")
    assert state["outfits"]
    for items in outfit_items(state, wardrobe_by_id):
        assert not {item["category"] for item in items} & OUTERWEAR


def test_hard_constraint_without_black(make_graph, wardrobe_by_id):
    state = run(make_graph(), "Une tenue pour une soirée, pas de noir")
    for items in outfit_items(state, wardrobe_by_id):
        assert all("black" not in item["color"] for item in items)


def test_constraints_are_remembered(make_graph, wardrobe_by_id):
    graph = make_graph()
    run(graph, "Une tenue pour le travail, sans veste")
    state = run(graph, "une autre")
    for items in outfit_items(state, wardrobe_by_id):
        assert not {item["category"] for item in items} & OUTERWEAR


def test_unsupported_shoe_constraint_is_reported(make_graph):
    state = run(make_graph(), "Je veux une tenue professionnelle pour demain, sans talons.")
    assert "talons" in state["response"]
    assert "chaussures" in state["response"]


def test_bo1_down_gives_clear_message(make_graph):
    def broken_loader():
        raise bo1_api_adapter.BO1UnavailableError("BO1 injoignable")
    state = run(make_graph(loader=broken_loader), "Une tenue pour le travail")
    assert "BO1" in state["response"]
    assert state["outfits"] == []


def test_llm_fills_occasion_when_rules_find_nothing(make_graph):
    fake_llm = lambda message: {"occasion": "work", "season": None, "exclude_categories": [],
                                "exclude_colors": [], "wants_another": False}
    state = run(make_graph(llm=fake_llm), "Je présente mon projet devant un jury")
    assert state["request"]["occasion"] == "work"
    assert "llm+règles" in state["trace"][0]


def test_hallucinating_llm_cannot_remove_garments(make_graph):
    fake_llm = lambda message: _llm(exclude_categories=["skirt", "jeans"])
    state = run(make_graph(llm=fake_llm), "Je présente mon projet devant un jury jeudi")
    assert state["request"]["occasion"] == "work"
    assert state["request"]["exclude_categories"] == []
    assert state["excluded"] == []
    assert "LLM ignoré" in state["trace"][0]


def test_broken_llm_falls_back_to_rules(make_graph):
    state = run(make_graph(llm=lambda message: "pas du JSON"), "Une tenue pour une soirée")
    assert state["request"]["occasion"] == "evening"
    assert "[règles]" in state["trace"][0]


def test_graph_can_be_drawn(make_graph):
    mermaid = make_graph().get_graph().draw_mermaid()
    for node in ("extract_intent", "record_feedback", "clarify", "get_weather", "fetch_wardrobe",
                 "apply_constraints",
                 "recommend", "respond"):
        assert node in mermaid


# ===================================================================== Dress code (I83)
@pytest.mark.parametrize("message, code", [
    ("J'ai un entretien demain", "business"),
    ("Une tenue pour un mariage", "formal"),
    ("Une tenue chic pour une soirée", "smart_casual"),
    ("Tenue smart casual pour le travail", "smart_casual"),
    ("Une tenue pour aller en cours", None),
])
def test_rules_dress_code(message, code):
    assert sa.extract_with_rules(message)["dress_code"] == code


@pytest.mark.parametrize("levels, code, expected", [
    ([3, 3], "business", (True, 3.0)),
    ([2, 3], "business", (False, 2.5)),     # moyenne trop basse
    ([5, 1], "business", (False, 3.0)),     # une pièce trop décontractée
    ([4, 4], "formal", (True, 4.0)),
    ([1, 1], "casual", (True, 1.0)),
    ([1, 1], None, (True, 1.0)),
])
def test_dress_code_check(levels, code, expected):
    items = [{"id": str(i), "formality": level} for i, level in enumerate(levels)]
    assert sa.dress_code_check(items, code) == expected


def test_dress_code_without_formality_is_not_blocking():
    assert sa.dress_code_check([{"id": "1"}, {"id": "2", "formality": None}], "formal") == (True, None)


@pytest.mark.parametrize("item", [
    {"category": "shorts", "name": "Linen Bermuda"},
    {"category": "skirt", "name": "Plaid Wool Skirt", "subcategory": "mini skirt"},
    {"category": "dress", "name": "Black Mini Dress"},
    {"category": "skirt", "name": "Mini-jupe en jean"},
    {"category": "trousers", "name": "Denim Hot Pants"},
])
@pytest.mark.parametrize("code", ["business", "formal"])
def test_short_cuts_break_business_and_formal(item, code):
    outfit = [{"id": "1", "formality": 5, **item}, {"id": "2", "formality": 5, "category": "top", "name": "Silk Blouse"}]
    assert sa.dress_code_check(outfit, code) == (False, 5.0)


@pytest.mark.parametrize("item", [
    {"category": "skirt", "name": "Black Skirt", "subcategory": "a-line midi skirt"},
    {"category": "top", "name": "Short-Sleeve Shirt", "subcategory": "short sleeve shirt"},
    {"category": "sweater", "name": "Grey Knit", "style": "minimalist"},
])
def test_midi_skirt_and_short_sleeves_stay_business(item):
    assert sa.dress_code_check([{"id": "1", "formality": 3, **item}], "business") == (True, 3.0)


@pytest.mark.parametrize("code", ["casual", "smart_casual", None])
def test_short_cuts_are_fine_without_strict_dress_code(code):
    outfit = [{"id": "1", "formality": 3, "category": "skirt", "subcategory": "mini skirt"}]
    assert sa.dress_code_check(outfit, code) == (True, 3.0)


def test_short_cut_without_formality_is_still_refused():
    assert sa.dress_code_check([{"id": "1", "category": "shorts"}], "business") == (False, None)


def test_interview_never_proposes_a_mini_skirt(make_graph, wardrobe_by_id):
    keep = {"Light Blue Shirt", "Grey Knit", "Navy Blazer", "Beige Chinos", "Black Skirt"}

    def with_mini():
        # Deux bas seulement : sans O3, la mini-jupe (formalité 3, conforme à l'ancienne règle) est proposée.
        wardrobe, report = fixture_loader()
        wardrobe = [item for item in wardrobe if item["name"] in keep]
        for item in wardrobe:
            if item["name"] == "Black Skirt":
                item.update(name="Plaid Mini Skirt", subcategory="mini skirt")
        return wardrobe, report
    mini_id = next(i["id"] for i in with_mini()[0] if i["name"] == "Plaid Mini Skirt")
    state = run(make_graph(loader=with_mini), "J'ai un entretien demain")
    assert state["outfits"] and not state["outfit_fallback"]
    assert all(mini_id not in sa._outfit_ids(o) for o in state["outfits"])
    weekend = run(make_graph(loader=with_mini), "Une tenue décontractée pour le week-end", thread="t2")
    assert weekend["request"]["dress_code"] == "casual"


@pytest.mark.parametrize("item, expected", [
    ({"category": "blazer"}, True),
    ({"category": "jacket", "formality": 4}, True),
    ({"category": "jacket", "formality": 3}, False),      # biker, bomber, veste militaire d'Arij
    ({"category": "jacket"}, False),
    ({"category": "coat", "formality": 5}, False),        # un manteau n'est pas une veste de costume
    ({"category": "top", "formality": 5}, False),
])
def test_is_structured_jacket(item, expected):
    assert sa.is_structured_jacket(item) is expected


def test_dress_code_check_with_required_jacket():
    shirt, chinos = {"id": "1", "category": "shirt", "formality": 3}, {"id": "2", "category": "trousers", "formality": 3}
    blazer = {"id": "3", "category": "blazer", "formality": 4}
    assert sa.dress_code_check([shirt, chinos], "business", require_structured_jacket=True) == (False, 3.0)
    assert sa.dress_code_check([shirt, chinos, blazer], "business", require_structured_jacket=True)[0]
    assert sa.dress_code_check([shirt, chinos], "smart_casual", require_structured_jacket=True)[0]
    assert sa.dress_code_check([shirt, chinos], "business")[0]


NO_JACKET_MESSAGE = "pas de veste structurée"


def _without_blazer():
    wardrobe, report = fixture_loader()
    return [item for item in wardrobe if item["name"] != "Navy Blazer"], report


def test_interview_requires_the_blazer_when_owned(make_graph, wardrobe_by_id):
    state = run(make_graph(), "J'ai un entretien demain")
    assert state["outfits"] and not state["outfit_fallback"]
    for items in outfit_items(state, wardrobe_by_id):
        assert any(item["name"] == "Navy Blazer" for item in items)
    assert NO_JACKET_MESSAGE not in state["response"]


# ----------------------------------------------------------------- O4 : hauts trop décontractés
@pytest.mark.parametrize("item, reason", [
    ({"category": "top", "name": "Beige Off-Shoulder Sweater"}, "épaules dénudées"),
    ({"category": "sweater", "name": "Knit", "subcategory": "off-the-shoulder sweater"}, "épaules dénudées"),
    ({"category": "top", "name": "Haut épaules dénudées"}, "épaules dénudées"),
    ({"category": "top", "name": "White Crop Top"}, "crop top"),
    ({"category": "t_shirt", "name": "Tee", "subcategory": "cropped t-shirt"}, "crop top"),
    ({"category": "blouse", "name": "Blouse dos nu"}, "dos nu"),
    ({"category": "top", "name": "Black Backless Top"}, "dos nu"),
    ({"category": "top", "name": "Satin Bustier"}, "bustier"),
    ({"category": "top", "name": "Top", "subcategory": "strapless top"}, "bustier"),
    ({"category": "top", "name": "Débardeur blanc"}, "débardeur"),
    ({"category": "top", "name": "Grey Tank Top"}, "débardeur"),
    ({"category": "top", "name": "Silk Cami", "subcategory": "camisole"}, "débardeur"),
])
def test_casual_top_reason(item, reason):
    assert sa.casual_top_reason(item) == reason


@pytest.mark.parametrize("item", [
    {"category": "top", "name": "Black Ribbed Turtleneck"},
    {"category": "shirt", "name": "Short-Sleeve Shirt", "subcategory": "short sleeve shirt"},
    {"category": "trousers", "name": "Cropped Trousers"},       # pas un haut
    {"category": "dress", "name": "Strapless Dress"},           # robe : hors périmètre de O4
    {"category": "top", "name": "Shoulder Bag Print Tee"},
])
def test_regular_tops_are_not_casual(item):
    assert sa.casual_top_reason(item) is None


@pytest.mark.parametrize("code, expected", [("business", False), ("formal", False), ("smart_casual", True),
                                            ("casual", True)])
def test_casual_top_breaks_only_strict_dress_codes(code, expected):
    outfit = [{"id": "1", "category": "top", "name": "Beige Off-Shoulder Sweater", "formality": 4},
              {"id": "2", "category": "trousers", "name": "Grey Wide-Leg Pants", "formality": 4}]
    assert sa.dress_code_check(outfit, code)[0] is expected


OFF_SHOULDER = "Beige Off-Shoulder Sweater"


def _with_off_shoulder():
    # Peu de hauts : sans O4, ce haut (formalité 4, style formel) serait proposé pour un entretien.
    wardrobe, report = fixture_loader()
    keep = {"Light Blue Shirt", "Beige Chinos", "Black Skirt", "Navy Blazer"}
    wardrobe = [item for item in wardrobe if item["name"] in keep]
    shirt = next(item for item in wardrobe if item["name"] == "Light Blue Shirt")
    wardrobe.append({**shirt, "id": "off-shoulder", "name": OFF_SHOULDER, "subcategory": "off-shoulder sweater",
                     "color": "beige", "style": "formal", "formality": 4})
    return wardrobe, report


def test_interview_no_longer_proposes_the_off_shoulder_sweater(make_graph):
    state = run(make_graph(loader=_with_off_shoulder), "J'ai un entretien demain")
    assert state["outfits"] and not state["outfit_fallback"]
    assert all("off-shoulder" not in sa._outfit_ids(o) for o in state["outfits"])
    assert state["casual_tops_excluded"] == [f"{OFF_SHOULDER} (épaules dénudées)"]
    assert f"Écarté pour ce dress code : {OFF_SHOULDER} (épaules dénudées)." in state["response"]
    assert state["response"].count("Écarté pour ce dress code") == 1           # une seule ligne


def test_off_shoulder_sweater_is_fine_for_a_casual_outing(make_graph):
    state = run(make_graph(loader=_with_off_shoulder), "Une tenue décontractée pour le week-end")
    assert state["casual_tops_excluded"] == [] and "Écarté pour ce dress code" not in state["response"]


def test_ollama_keeps_the_model_loaded(monkeypatch):
    sent = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b'{"message": {"content": "{}"}}'

    def fake_urlopen(request, timeout=None):
        sent.update(sa.json.loads(request.data))
        return Response()
    monkeypatch.setattr(sa.urllib.request, "urlopen", fake_urlopen)
    sa.ollama_extract("une tenue pour le travail")
    assert sent["keep_alive"] == "30m" == sa.OLLAMA_KEEP_ALIVE


def test_interview_without_structured_jacket_explains_it(make_graph):
    state = run(make_graph(loader=_without_blazer), "J'ai un entretien demain")
    assert state["outfits"] and not state["outfit_fallback"]
    assert state["no_structured_jacket"] and NO_JACKET_MESSAGE in state["response"]


@pytest.mark.parametrize("message", ["Une tenue pour une soirée", "Une tenue pour aller en cours"])
def test_no_jacket_message_only_for_business_or_formal(make_graph, message):
    state = run(make_graph(loader=_without_blazer), message)
    assert not state["no_structured_jacket"] and NO_JACKET_MESSAGE not in state["response"]


def test_without_jacket_constraint_disables_the_requirement(make_graph, wardrobe_by_id):
    state = run(make_graph(), "J'ai un entretien demain, sans veste")
    assert state["outfits"] and not state["outfit_fallback"]
    for items in outfit_items(state, wardrobe_by_id):
        assert all(item["category"] not in {"blazer", "jacket"} for item in items)
    assert NO_JACKET_MESSAGE not in state["response"]


def _formality_ok(items, min_mean, min_item):
    levels = [item["formality"] for item in items]
    return sum(levels) / len(levels) >= min_mean and min(levels) >= min_item


def test_interview_applies_business_dress_code(make_graph, wardrobe_by_id):
    state = run(make_graph(), "J'ai un entretien demain")
    assert state["request"]["dress_code"] == "business"
    assert state["outfits"] and not state["outfit_fallback"]
    for items in outfit_items(state, wardrobe_by_id):
        assert _formality_ok(items, 3.0, 2)
    assert "Dress code : business" in state["response"]


def test_university_has_no_formality_filter(make_graph):
    state = run(make_graph(), "Une tenue pour aller en cours")
    assert state["request"]["dress_code"] == "casual"
    assert all(o["dress_code_ok"] for o in state["outfits"])


def test_dress_code_is_kept_then_reset_with_new_occasion(make_graph):
    graph = make_graph()
    run(graph, "J'ai un entretien demain")
    assert run(graph, "une autre")["request"]["dress_code"] == "business"
    state = run(graph, "Finalement c'est pour une soirée")
    assert state["request"]["dress_code"] == "smart_casual"
    assert state["request"]["dress_code_source"] == "par défaut pour l'occasion"


def test_impossible_dress_code_proposes_nothing_and_suggests_a_piece(make_graph):
    """Les règles de dress code sont absolues : jamais de repli « les plus proches » (ancien comportement)."""
    def casual_only():
        wardrobe, report = fixture_loader()
        keep = {"White Tee", "Blue Jeans", "Black Puffer"}
        return [item for item in wardrobe if item["name"] in keep], report
    state = run(make_graph(loader=casual_only), "Une tenue pour un mariage")
    assert state["request"]["dress_code"] == "formal"
    assert not state["outfits"] and state["outfit_fallback"] == "none_conform"
    assert "Aucune tenue de ta garde-robe ne convient à ce dress code" in state["response"]
    assert "Pièce à ajouter : un blazer" in state["response"] and "plus proches" not in state["response"]


# ===================================================================== Météo (I71)
@pytest.mark.parametrize("t_min, t_max, month, season", [
    (2, 9, 1, "winter"), (6, 14, 10, "winter"), (12, 20, 10, "autumn"), (12, 20, 4, "spring"),
    (18, 30, 7, "summer"), (16, 28, 10, "summer"),
])
def test_season_from_temperature(t_min, t_max, month, season):
    assert sa.season_from_temperature(t_min, t_max, month) == season


@pytest.mark.parametrize("message, city", [
    ("Une tenue pour un entretien demain à Paris", "Paris"),
    ("Je pars in London pour le week-end", "London"),
    ("Une tenue pour aller en cours à ESPRIT", None),
    ("On se voit à demain", None),
    ("Une tenue pour le travail", None),
])
def test_extract_city(message, city):
    assert sa.extract_city(message) == city


class _FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        import json
        return json.dumps(self.payload).encode()


def test_open_meteo_forecast_parsing(monkeypatch):
    calls = []

    def fake_urlopen(url, timeout):
        calls.append(url)
        if "geocoding" in url:
            return _FakeResponse({"results": [{"name": "Tunis", "latitude": 36.8, "longitude": 10.18}]})
        return _FakeResponse({"daily": {"time": ["2026-10-22", "2026-10-23"],
                                        "temperature_2m_min": [17.1, 15.2],
                                        "temperature_2m_max": [25.3, 22.4],
                                        "precipitation_probability_max": [10, 70]}})
    monkeypatch.setattr(sa.urllib.request, "urlopen", fake_urlopen)
    forecast = sa.open_meteo_forecast("Tunis", dt.date(2026, 10, 23))
    assert forecast == {"city": "Tunis", "date": "2026-10-23", "t_min": 15.2, "t_max": 22.4,
                        "rain_probability": 70}
    assert "name=Tunis" in calls[0] and "latitude=36.8" in calls[1]


def test_open_meteo_unknown_city(monkeypatch):
    monkeypatch.setattr(sa.urllib.request, "urlopen", lambda url, timeout: _FakeResponse({}))
    with pytest.raises(sa.WeatherError):
        sa.open_meteo_forecast("Nullepart", TODAY)


def test_open_meteo_network_error(monkeypatch):
    def fake_urlopen(url, timeout):
        raise urllib.error.URLError("offline")
    monkeypatch.setattr(sa.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(sa.WeatherError):
        sa.open_meteo_forecast("Tunis", TODAY)


def _fake_weather(t_min, t_max, rain=0, calls=None):
    def weather(city, day):
        if calls is not None:
            calls.append((city, day))
        return {"city": city, "date": day.isoformat(), "t_min": t_min, "t_max": t_max,
                "rain_probability": rain}
    return weather


def test_weather_sets_the_season(make_graph):
    calls = []
    state = run(make_graph(weather=_fake_weather(3, 8, calls=calls)), "J'ai un entretien demain")
    assert calls == [("Tunis", TODAY + dt.timedelta(days=1))]
    assert state["request"]["season"] == "winter"
    assert "météo Tunis" in state["request"]["season_source"]
    assert "météo Tunis" in state["response"]


def test_city_from_message_is_used_and_remembered(make_graph):
    calls = []
    graph = make_graph(weather=_fake_weather(12, 20, calls=calls))
    run(graph, "Une tenue pour le travail à Paris")
    run(graph, "une autre")
    assert [city for city, _ in calls] == ["Paris"]  # 2e tour : prévision mise en cache


def test_explicit_season_skips_weather(make_graph):
    calls = []
    state = run(make_graph(weather=_fake_weather(30, 35, calls=calls)), "Une tenue pour une soirée en hiver")
    assert calls == []
    assert state["request"]["season"] == "winter"


def test_weather_failure_falls_back_to_date(make_graph):
    def broken(city, day):
        raise sa.WeatherError("Open-Meteo injoignable")
    state = run(make_graph(weather=broken), "Une tenue pour le travail")
    assert state["request"]["season"] == "autumn"
    assert state["request"]["season_source"] == "déduite de la date"
    assert "indisponible" in state["trace"][1]
    assert state["outfits"]


def test_rain_warning(make_graph):
    state = run(make_graph(weather=_fake_weather(12, 18, rain=80)), "Une tenue pour aller en cours")
    assert "Pluie probable (80 %)" in state["response"]


# ===================================================================== Feedback (I76) et profil (I77)
@pytest.mark.parametrize("message, expected", [
    ("j'aime la 2", {"verdict": "like", "rank": 2}),
    ("J'adore la tenue 1 !", {"verdict": "like", "rank": 1}),
    ("je n'aime pas la 3", {"verdict": "dislike", "rank": 3}),
    ("j'aime pas la tenue 1", {"verdict": "dislike", "rank": 1}),
    ("Je n'aime pas, une autre ?", {"verdict": "dislike", "rank": None}),   # réaction + suite : 👎 sans numéro
    ("Une tenue pour le 2 novembre", None),
])
def test_extract_feedback(message, expected):
    assert sa.extract_with_rules(message)["feedback"] == expected


def test_dislike_with_rank_asks_for_another():
    assert sa.extract_with_rules("j'aime pas la 2")["wants_another"] is True


def ids_of(state):
    return [frozenset(sa._outfit_ids(o)) for o in state["outfits"]]


def test_like_only_records_and_answers(make_graph):
    store = stylist_feedback.FeedbackStore()
    graph = make_graph(feedback=store)
    first = run(graph, "Une tenue décontractée pour le week-end")
    state = run(graph, "J'aime la 2")
    assert [line.split()[0] for line in state["trace"]] == ["extract_intent", "record_feedback"]
    assert state["outfits"] == []
    assert "C'est noté" in state["response"]
    assert store.records()[0]["item_ids"] == sorted(sa._outfit_ids(first["outfits"][1]))


def test_liked_outfit_gets_a_bonus_next_time(make_graph):
    store = stylist_feedback.FeedbackStore()
    graph = make_graph(feedback=store)
    liked = ids_of(run(graph, "Une tenue décontractée pour le week-end"))[2]
    run(graph, "j'aime la 3")
    again = run(graph, "Une tenue décontractée pour le week-end")
    # Les pièces aimées remontent : au moins une tenue proposée les contient et reçoit un bonus.
    boosted = [o for o in again["outfits"] if o["personal_bonus"] > 0]
    assert boosted and all(liked & set(sa._outfit_ids(o)) for o in boosted)
    assert "selon tes goûts)" in again["response"]          # score final affiché : « 89,8/100 (96,3 + … ) »


def test_dislike_records_regenerates_and_never_shows_again(make_graph):
    store = stylist_feedback.FeedbackStore()
    graph = make_graph(feedback=store)
    rejected = ids_of(run(graph, "Une tenue pour le travail"))[0]
    state = run(graph, "je n'aime pas la 1")
    assert [line.split()[0] for line in state["trace"]][:3] == ["extract_intent", "record_feedback", "get_weather"]
    assert state["outfits"] and rejected not in ids_of(state)
    assert state["response"].startswith("C'est noté : tu n'aimes pas la tenue 1")
    fresh = run(graph, "Une tenue pour le travail")   # nouvelle demande : la tenue reste écartée
    assert rejected not in ids_of(fresh)


def test_feedback_on_unknown_rank(make_graph):
    graph = make_graph(feedback=stylist_feedback.FeedbackStore())
    run(graph, "Une tenue pour le travail")
    state = run(graph, "j'aime la 7")
    assert "Je ne trouve pas de tenue n° 7" in state["response"]


def test_feedback_without_store(make_graph):
    graph = make_graph(feedback=None)
    run(graph, "Une tenue pour le travail")
    assert "désactivé" in run(graph, "j'aime la 1")["response"]


class _StubEngine:
    """Moteur factice à scores fixes, pour vérifier précisément le reclassement."""
    def __init__(self, wardrobe_ids):
        self.outfits = [{"items": [{"id": i} for i in ids], "score": score, "explanations": []}
                        for ids, score in zip(wardrobe_ids, (80.0, 79.0, 78.0))]

    def recommend_outfits(self, wardrobe, occasion, season, top_k):
        return list(self.outfits)


def test_personal_bonus_reorders_outfits(make_graph, wardrobe_by_id):
    ids = list(wardrobe_by_id)
    combos = [[ids[0], ids[5]], [ids[1], ids[6]], [ids[2], ids[7]]]
    store = stylist_feedback.FeedbackStore()
    graph = make_graph(feedback=store, engine=_StubEngine(combos))  # occasion casual : pas de filtre de formalité
    first = run(graph, "Une tenue décontractée pour le week-end")
    assert [sa._outfit_ids(o) for o in first["outfits"]] == combos
    run(graph, "j'aime la 3")
    second = run(graph, "Une tenue décontractée pour le week-end")
    assert sa._outfit_ids(second["outfits"][0]) == combos[2]   # 78 + bonus > 80


# ===================================================================== Diversité (I89) et noms en double
def _o(*ids):
    return {"items": [{"id": i} for i in ids], "score": 80.0}


def test_overlap():
    assert sa.overlap(["dress"], ["dress", "jacket"]) == 1.0
    assert sa.overlap(["dress", "blazer"], ["dress", "puffer"]) == 0.5
    assert sa.overlap(["top", "skirt"], ["shirt", "jeans"]) == 0.0


def test_diversify_skips_near_duplicates():
    ranked = [_o("dress"), _o("dress", "jacket"), _o("dress", "puffer"), _o("top", "skirt"),
              _o("shirt", "jeans")]
    picked = sa.diversify(ranked, k=3)
    assert [sa._outfit_ids(o) for o in picked] == [["dress"], ["top", "skirt"], ["shirt", "jeans"]]


def test_diversify_fills_up_when_needed():
    ranked = [_o("dress"), _o("dress", "jacket"), _o("dress", "puffer")]
    picked = sa.diversify(ranked, k=3)
    # Complément limité à MIN_PROPOSALS : mieux vaut 2 tenues vraiment différentes que 3 presque identiques.
    assert len(picked) == sa.MIN_PROPOSALS == 2
    assert sa._outfit_ids(picked[0]) == ["dress"]


def test_diversify_sorts_by_personal_score():
    ranked = [{**_o("top", "skirt"), "personal_score": 80.0},
              {**_o("shirt", "jeans"), "personal_score": 90.0},
              {**_o("dress"), "personal_score": 85.0}]
    picked = sa.diversify(ranked, k=3)
    assert [o["personal_score"] for o in picked] == [90.0, 85.0, 80.0]


def _piece(item_id, category, color, name):
    return {"id": item_id, "category": category, "color": color, "name": name}


def test_piece_key():
    assert sa.piece_key(_piece("a", "skirt", "grey", "Plaid Mini Skirt n° 2")) == \
        sa.piece_key(_piece("b", "Skirt", "Grey", "plaid mini skirt"))
    assert sa.piece_key(_piece("a", "skirt", "grey", "Plaid Skirt")) != \
        sa.piece_key(_piece("b", "skirt", "black", "Plaid Skirt"))
    assert sa.piece_key({"id": "x"}) == "x" and sa.piece_key("y") == "y"


def test_diversify_treats_identical_pieces_as_one():
    top = _piece("t", "top", "black", "Turtleneck")
    twin_1, twin_2 = _piece("s1", "skirt", "grey", "Plaid Skirt"), _piece("s2", "skirt", "grey", "Plaid Skirt")
    trousers = _piece("p", "trousers", "brown", "Wide Trousers")
    ranked = [{"items": [top, twin_1], "score": 98.5}, {"items": [top, twin_2], "score": 98.5},
              {"items": [top, trousers], "score": 96.3}]
    picked = sa.diversify(ranked, k=3)
    assert [sa._outfit_ids(o) for o in picked] == [["t", "s1"], ["t", "p"]]


def test_diversify_keeps_same_name_in_another_color():
    top = _piece("t", "top", "black", "Turtleneck")
    grey, black = _piece("s1", "skirt", "grey", "Plaid Skirt"), _piece("s2", "skirt", "black", "Plaid Skirt")
    picked = sa.diversify([{"items": [top, grey], "score": 90.0}, {"items": [top, black], "score": 89.0}], k=3)
    assert len(picked) == 2


def test_duplicated_garment_is_not_proposed_twice(make_graph):
    def twin_skirts():
        wardrobe, report = fixture_loader()
        skirt = next(item for item in wardrobe if item["name"] == "Black Skirt")
        return wardrobe + [{**skirt, "id": "skirt-twin"}], report
    state = run(make_graph(loader=twin_skirts), "J'ai un entretien demain")
    keys = [sorted(map(repr, sa._piece_keys(o))) for o in state["outfits"]]
    assert state["outfits"] and len(keys) == len({tuple(k) for k in keys})
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            assert sa.overlap(keys[i], keys[j]) <= sa.MAX_OVERLAP


def test_too_similar_outfits_are_announced(make_graph):
    keep = {"Burgundy Dress", "Navy Blazer", "Black Puffer"}

    def dress_and_jackets():
        wardrobe, report = fixture_loader()
        return [item for item in wardrobe if item["name"] in keep], report
    state = run(make_graph(loader=dress_and_jackets), "Une tenue pour une soirée")
    assert 1 <= len(state["outfits"]) < 3
    assert "Je ne propose que" in state["response"]


def test_outfits_shown_together_are_diverse(make_graph):
    state = run(make_graph(), "Une tenue décontractée pour le week-end")
    ids = [sa._outfit_ids(o) for o in state["outfits"]]
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            assert sa.overlap(ids[i], ids[j]) <= sa.MAX_OVERLAP


def test_duplicate_names_are_numbered():
    wardrobe = [{"id": "a", "name": "Charcoal Jacket"}, {"id": "b", "name": "Red Dress"},
                {"id": "c", "name": "Charcoal Jacket"}]
    assert sa.display_names(wardrobe) == {"a": "Charcoal Jacket n° 1", "b": "Red Dress",
                                         "c": "Charcoal Jacket n° 2"}


def test_duplicate_names_are_distinguished_in_the_answer(make_graph):
    def twin_jackets():
        wardrobe, report = fixture_loader()
        for item in wardrobe:
            if item["category"] in {"blazer", "jacket"}:
                item["name"] = "Charcoal Jacket"
        return wardrobe, report
    state = run(make_graph(loader=twin_jackets), "Une tenue pour le travail")
    assert "Charcoal Jacket (" not in state["response"]


# ===================================================================== BO5 : conseil de style (optionnel)
def test_style_advice_disabled_by_default(make_graph):
    state = run(make_graph(), "J'ai un entretien demain")
    assert "style_advice -> BO5 désactivé" in state["trace"]
    assert state["advice"] == {}
    assert "Conseil de style" not in state["response"]


def test_style_advice_is_shown_after_the_outfits(make_graph, wardrobe_by_id):
    questions = []

    def fake_advice(question):
        questions.append(question)
        return {"answer": "Associe une chemise unie à un pantalon bien coupé.",
                "sources": ["Dress to Impress Guide 2020.pdf", "Career Closet"]}
    state = run(make_graph(advice=fake_advice), "J'ai un entretien demain")
    assert len(questions) == 1
    assert questions[0].startswith("Quels conseils de style pour porter ")
    assert "pour travail, dress code business ?" in questions[0]
    assert state["advice"]["answer"].startswith("Associe")
    response = state["response"]
    assert "Conseil de style (base de connaissances BO5) : Associe" in response
    assert "Sources : Dress to Impress Guide 2020.pdf ; Career Closet" in response
    # Le conseil vient après la liste des tenues, qui reste complète.
    assert response.index("1. ") < response.index("Conseil de style")
    assert state["outfits"] and all(set(sa._outfit_ids(o)) <= set(wardrobe_by_id) for o in state["outfits"])
    assert any(line.startswith("style_advice -> conseil BO5 reçu (2 source(s))") for line in state["trace"])


def test_style_advice_failure_keeps_the_answer(make_graph):
    def broken_advice(question):
        raise RuntimeError("connexion refusée")
    state = run(make_graph(advice=broken_advice), "J'ai un entretien demain")
    assert state["outfits"]
    assert "Voici mes propositions" in state["response"]
    assert "Conseil de style" not in state["response"]
    assert any(line.startswith("style_advice -> BO5 indisponible (connexion refusée)") for line in state["trace"])
    assert state["trace"][-1].startswith("respond")


def test_advice_is_reset_each_turn(make_graph):
    answers = iter([{"answer": "Conseil 1", "sources": []}])

    def advice_once(question):
        return next(answers)
    graph = make_graph(advice=advice_once)
    first = run(graph, "J'ai un entretien demain")
    assert first["advice"]["answer"] == "Conseil 1"
    second = run(graph, "Je veux une tenue")              # tour de clarification : pas de recommandation
    assert second["advice"] == {}


def test_bo5_advice_factory():
    assert sa.bo5_advice(None) is None and sa.bo5_advice("") is None
    assert callable(sa.bo5_advice("http://localhost:8001"))


# ===================================================================== Corrections issues de l'évaluation I79
@pytest.mark.parametrize("message, categories, colors", [
    ("Une tenue pour un mariage, évite le blanc", [], ["white"]),               # éval. n° 36
    ("Soirée chez des amis : je préfère éviter les robes", ["dress"], []),    # éval. n° 38
    ("Pour le travail, évitez la jupe", ["skirt"], []),
    ("Pour la fac, j'aimerais éviter l'orange", [], ["orange"]),
    ("Une tenue pour une soirée, évite de noir", [], ["black"]),
])
def test_rules_understand_eviter(message, categories, colors):
    result = sa.extract_with_rules(message)
    assert result["exclude_categories"] == categories and result["exclude_colors"] == colors


def test_eviter_is_a_negation_cue_for_the_guard():
    clean = _llm(occasion="evening", exclude_colors=["white"], exclude_categories=["dress"])
    grounded, rejected = sa.ground_llm_output(clean, "Pour un mariage, évite le blanc et les robes")
    assert grounded["exclude_colors"] == ["white"] and grounded["exclude_categories"] == ["dress"]
    assert rejected == []


def test_liking_is_not_asking_for_another_outfit():                             # éval. n° 47
    grounded, rejected = sa.ground_llm_output(_llm(wants_another=True), "J'aime bien la première")
    assert grounded["wants_another"] is False and rejected == ["demande d'une autre tenue"]


@pytest.mark.parametrize("message", ["Je n'aime pas trop celle-ci", "Pas convaincu, tu as mieux ?",
                                     "Change la veste", "Show me something else", "Une autre idée ?"])
def test_another_cues_still_accept_real_rejections(message):
    grounded, _ = sa.ground_llm_output(_llm(wants_another=True), message)
    assert grounded["wants_another"] is True


@pytest.mark.parametrize("message, feedback, another", [
    ("La 2 me plaît beaucoup", {"verdict": "like", "rank": 2}, False),                  # éval. n° 46
    ("J'aime bien la première", {"verdict": "like", "rank": 1}, False),                 # éval. n° 47
    ("Pas convaincu par la tenue 2, tu as mieux ?", {"verdict": "dislike", "rank": 2}, True),  # n° 49
    ("Bof la deuxième", {"verdict": "dislike", "rank": 2}, True),
    ("Pas convaincue par la troisième", {"verdict": "dislike", "rank": 3}, True),
    ("La 3, bof", {"verdict": "dislike", "rank": 3}, True),
    ("j'aime la 2", {"verdict": "like", "rank": 2}, False),
    ("je n'aime pas la 1", {"verdict": "dislike", "rank": 1}, True),
])
def test_rephrased_feedback(message, feedback, another):
    result = sa.extract_with_rules(message)
    assert result["feedback"] == feedback
    assert result["wants_another"] is another


def test_last_outfit_rank_depends_on_previous_turn():
    assert sa.extract_with_rules("Je n'aime pas la dernière")["feedback"] == {"verdict": "dislike", "rank": 3}
    assert sa.extract_with_rules("Je n'aime pas la dernière", last_count=2)["feedback"]["rank"] == 2


def test_tu_as_mieux_asks_for_another_outfit():
    assert sa.extract_with_rules("Tu as mieux ?")["wants_another"] is True
    assert sa.extract_with_rules("Bof, sans plus")["feedback"] is None     # « bof » sans rang : pas de retour


@pytest.mark.parametrize("message, keyword, ambiguous", [
    ("J'ai un rendez-vous avec la DRH de l'entreprise", "rendez-vous", True),   # éval. n° 27
    ("I'm meeting my girlfriend's parents for the first time tonight", "meeting", True),  # n° 29
    ("Une tenue pour le travail", "travail", False),
    ("Rendez-vous au bureau demain", "rendez-vous", False),     # « bureau » n'est pas ambigu
    ("Je veux une tenue", None, False),
])
def test_rules_report_the_occasion_keyword(message, keyword, ambiguous):
    result = sa.extract_with_rules(message)
    assert result["occasion_keyword"] == keyword and result["occasion_ambiguous"] is ambiguous


def test_merge_occasion_prefers_llm_only_for_ambiguous_keywords():
    drh = sa.extract_with_rules("J'ai un rendez-vous avec la DRH de l'entreprise")
    assert drh["occasion"] == "evening"
    assert sa.merge_occasion(drh, "work") == "work"            # mot ambigu + autre occasion du LLM
    assert sa.merge_occasion(drh, None) == "evening"           # pas d'avis du LLM : on garde les règles
    assert sa.merge_occasion(drh, "beach") == "evening"        # occasion invalide ignorée
    clear = sa.extract_with_rules("Une tenue pour une soirée")
    assert sa.merge_occasion(clear, "work") == "evening"       # mot non ambigu : les règles priment
    assert sa.merge_occasion(sa.extract_with_rules("Je veux une tenue"), "casual") == "casual"


def test_ambiguous_keyword_uses_llm_occasion_in_graph(make_graph):
    fake_llm = lambda message: _llm(occasion="evening")
    state = run(make_graph(llm=fake_llm), "I'm meeting my girlfriend's parents for the first time tonight")
    assert state["request"]["occasion"] == "evening"


def test_last_outfit_feedback_in_graph(make_graph):
    graph = make_graph()
    first = run(graph, "J'ai un entretien demain")
    second = run(graph, "Je n'aime pas la dernière")
    assert second["request"]["feedback"] == {"verdict": "dislike", "rank": len(first["outfits"])}
