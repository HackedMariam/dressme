"""Avis d'achat : article traduit en anglais, catégorie, matière, prix, garde-robe BO1 envoyée à POST /analyze."""
import importlib.util
import sys
from pathlib import Path

import pytest

import graph as og
from test_orchestrator import WARDROBE

PURCHASE_BACKEND = Path(__file__).resolve().parents[2] / "purchase-redundancy-ai" / "backend"


@pytest.mark.parametrize("message, expected", [
    ("Est-ce que je devrais acheter un col roulé noir ?",
     {"name": "black turtleneck", "category": "shirts", "color": "black", "style": None}),
    ("Est-ce que je devrais acheter un blazer noir ?",
     {"name": "black blazer", "category": "outerwear", "color": "black", "style": None}),
    ("Est-ce que je devrais acheter une veste en cuir noire à 80 € ?",
     {"name": "black leather jacket", "category": "outerwear", "color": "black", "material": "leather",
      "price": 80.0, "style": None}),
    ("Should I buy a grey wool sweater for 45 euros?",
     {"name": "grey wool sweater", "category": "shirts", "color": "grey", "material": "wool", "price": 45.0,
      "style": None}),
    ("Acheter des bottines en daim marron ?",
     {"name": "brown suede ankle boots", "category": "shoes", "color": "brown", "material": "suede", "style": None}),
])
def test_new_item_is_translated_with_category_material_and_price(message, expected):
    assert og.new_item_from_message(message) == expected


def test_request_sends_the_bo1_wardrobe_with_neutral_style():
    body = og.purchase_request(og.new_item_from_message("acheter un col roulé noir ?"), WARDROBE, "French", False)
    assert [i["name"] for i in body["wardrobe_items"]] == [i["name"] for i in WARDROBE]
    assert all(i["style"] is None for i in body["wardrobe_items"])   # null : pas de « casual » inventé par /analyze
    assert body["new_item"]["style"] is None and body["language"] == "French" and body["use_llm"] is False


def test_material_is_dropped_from_the_wardrobe_only_when_the_article_has_none():
    wardrobe = [{**WARDROBE[0], "material": "wool knit"}, {**WARDROBE[3], "material": "leather"}]
    plain = og.purchase_request(og.new_item_from_message("acheter un col roulé noir ?"), wardrobe, "French", False)
    assert all("material" not in i for i in plain["wardrobe_items"])
    leather = og.purchase_request(og.new_item_from_message("acheter une veste en cuir noire ?"), wardrobe, "French",
                                  False)
    assert [i.get("material") for i in leather["wardrobe_items"]] == ["wool knit", "leather"]


# ---------------------------------------------------------------- moteur réel de Purchase Redundancy
def load_module(alias: str, filename: str):
    spec = importlib.util.spec_from_file_location(alias, PURCHASE_BACKEND / f"{filename}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def purchase_engine():
    """Validateur et moteur de purchase-redundancy-ai (lecture seule, embeddings « simulated » sans CLIP), comme
    POST /analyze : validation AnalysisRequest, puis RedundancyEngine.analyze. Ignoré si le module est absent."""
    if not PURCHASE_BACKEND.is_dir():
        pytest.skip("purchase-redundancy-ai absent")
    pytest.importorskip("PIL")
    # chargés par chemin : « validators » est aussi un paquet PyPI ; les noms courts que engine.py importe
    # (cache, clip_integration, features) ne restent pas dans sys.modules après le chargement
    saved = {name: sys.modules.pop(name) for name in ("cache", "clip_integration", "features") if name in sys.modules}
    try:
        for name in ("cache", "clip_integration", "features"):
            sys.modules[name] = load_module(name, name)
        validators = load_module("purchase_validators", "validators")
        engine_module = load_module("purchase_engine", "engine")
        clip_module = sys.modules["clip_integration"]
    finally:
        for name in ("cache", "clip_integration", "features"):
            sys.modules.pop(name, None)
        sys.modules.update(saved)
    engine = engine_module.RedundancyEngine(clip_module.CLIPEmbedding(enabled=False), catalog=[])

    def redundancy(message: str, wardrobe: list) -> int:
        request = validators.AnalysisRequest(**og.purchase_request(og.new_item_from_message(message), wardrobe,
                                                                   "French", False))
        new_item = request.new_item.model_dump(exclude_none=True)
        owned = [i.model_dump(exclude_none=True) for i in request.wardrobe_items]
        return engine.analyze(new_item, owned, lang="fr")["redundancy_score"]
    return redundancy


# garde-robe sans veste : le blazer et la veste en cuir n'ont rien de proche
NO_JACKET = [i for i in WARDROBE if i["category"] != "jacket"]


@pytest.mark.parametrize("wardrobe", [NO_JACKET, [{**i, "material": "wool knit"} if i["id"] == "1" else i
                                                  for i in NO_JACKET]], ids=["bo1", "bo1-avec-matiere"])
def test_owned_turtleneck_scores_far_above_a_blazer(purchase_engine, wardrobe):
    turtleneck = purchase_engine("Est-ce que je devrais acheter un col roulé noir ?", wardrobe)
    blazer = purchase_engine("Est-ce que je devrais acheter un blazer noir ?", wardrobe)
    assert turtleneck >= blazer + 25, (turtleneck, blazer)


def test_owned_leather_jacket_is_flagged(purchase_engine):
    assert purchase_engine("veste en cuir noire à 80 € ?", WARDROBE) >= 60    # « Black Leather Jacket » possédée
