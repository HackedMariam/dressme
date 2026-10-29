"""Tests de l'adaptateur BO1 -> BO4.

Les données de `fixtures/bo1_items_sample.json` sont ILLUSTRATIVES : elles respectent
exactement le format de GET /api/items (branche wardrobe, main.py L122-151 et L209-214),
mais ce ne sont pas de vrais vêtements d'utilisateur.
"""

import io
import json
import urllib.error
from pathlib import Path

import pytest

import bo1_api_adapter as adapter

FIXTURE = Path(__file__).parent / "fixtures" / "bo1_items_sample.json"
GARMENT_IDS = {f"a1000000-0000-4000-8000-0000000000{n:02d}" for n in range(1, 11)}
SHOE_ID = "a1000000-0000-4000-8000-000000000011"
BAG_ID = "a1000000-0000-4000-8000-000000000012"


@pytest.fixture
def bo1_items():
    return adapter.load_bo1_items_from_file(FIXTURE)


@pytest.fixture
def by_name(bo1_items):
    wardrobe, _ = adapter.adapt_wardrobe(bo1_items)
    return {item["name"]: item for item in wardrobe}


# ---------------------------------------------------------------- filtrage
def test_accessories_shoes_and_bags_are_skipped(bo1_items):
    wardrobe, report = adapter.adapt_wardrobe(bo1_items)
    ids = {item["id"] for item in wardrobe}
    assert ids == GARMENT_IDS
    assert SHOE_ID not in ids and BAG_ID not in ids
    assert report["received"] == 12 and report["kept"] == 10
    skipped = [name for names in report["skipped"].values() for name in names]
    assert sorted(skipped) == ["Tan Tote", "White Sneakers"]


def test_needs_review_items_can_be_excluded(bo1_items):
    wardrobe, report = adapter.adapt_wardrobe(bo1_items, include_needs_review=False)
    assert "Charcoal Vest" not in {item["name"] for item in wardrobe}
    assert report["skipped"]["needs_review"] == ["Charcoal Vest"]


def test_item_without_id_is_skipped():
    assert adapter.bo1_item_to_bo4({"category": "top", "name": "x"}) is None


# ---------------------------------------------------------------- catégories
@pytest.mark.parametrize("name, expected", [
    ("White Tee", "t_shirt"),
    ("Light Blue Shirt", "shirt"),
    ("Grey Knit", "sweater"),
    ("Navy Blazer", "blazer"),
    ("Black Puffer", "jacket"),
    ("Beige Chinos", "trousers"),
    ("Blue Jeans", "jeans"),
    ("Black Skirt", "skirt"),
    ("Burgundy Dress", "dress"),
    ("Charcoal Vest", "top"),
])
def test_category_mapping(by_name, name, expected):
    assert by_name[name]["category"] == expected


def test_sweatshirt_is_not_mapped_to_shirt():
    item = {"id": "x", "category": "top", "subcategory": "grey sweatshirt"}
    assert adapter.bo1_item_to_bo4(item)["category"] == "hoodie"


def test_coat_refinement():
    item = {"id": "x", "category": "jacket", "subcategory": "wool trench coat"}
    assert adapter.bo1_item_to_bo4(item)["category"] == "coat"


# ---------------------------------------------------------------- couleurs, styles, chaleur
def test_color_name_is_renamed_to_color(by_name):
    assert by_name["Light Blue Shirt"]["color"] == "light blue"
    assert by_name["Charcoal Vest"]["color"] == "dark_grey"


def test_missing_color_becomes_unknown_with_note():
    item = adapter.bo1_item_to_bo4({"id": "x", "category": "top"})
    assert item["color"] == "unknown"
    assert "couleur absente dans BO1" in item["mapping_notes"]


@pytest.mark.parametrize("bo1_style, bo4_style", [
    ("casual", "casual"), ("sporty", "casual"), ("streetwear", "casual"), ("bohemian", "casual"),
    ("classic", "smart_casual"), ("minimalist", "smart_casual"), ("romantic", "smart_casual"),
    ("business", "formal"), ("elegant", "formal"), ("formal", "formal"),
    ("unexpected", "unknown"), (None, "unknown"),
])
def test_style_mapping(bo1_style, bo4_style):
    assert adapter.map_style(bo1_style) == bo4_style


def test_every_bo1_style_is_mapped():
    bo1_styles = ["casual", "elegant", "formal", "business", "sporty", "streetwear",
                  "bohemian", "minimalist", "classic", "romantic"]  # taxonomy.STYLES
    assert all(adapter.map_style(s) in {"casual", "smart_casual", "formal"} for s in bo1_styles)


@pytest.mark.parametrize("warmth, expected", [
    (1, "light"), (2, "light"), (3, "medium"), (4, "heavy"), (5, "heavy"),
    (0, None), (6, None), (None, None), ("3", None), (True, None),
])
def test_warmth_mapping(warmth, expected):
    assert adapter.map_warmth(warmth) == expected


def test_missing_warmth_is_left_to_engine():
    item = adapter.bo1_item_to_bo4({"id": "x", "category": "top", "color_name": "red"})
    assert "warmth" not in item


# ---------------------------------------------------------------- manches et champs conservés
def test_sleeve_detection(by_name):
    assert by_name["White Tee"]["sleeve_length"] == "short"
    assert by_name["Light Blue Shirt"]["sleeve_length"] == "long"
    assert by_name["Charcoal Vest"]["sleeve_length"] == "sleeveless"
    assert by_name["Beige Chinos"]["sleeve_length"] == "unknown"


def test_bo1_fields_are_kept_for_the_agent(by_name):
    blazer = by_name["Navy Blazer"]
    assert blazer["occasions"] == ["work", "ceremony"]
    assert blazer["formality"] == 4
    assert blazer["image_url"].endswith("/original.jpg")
    assert blazer["bo1_style"] == "business" and blazer["bo1_warmth"] == 3


def test_ids_are_strings(by_name):
    assert all(isinstance(item["id"], str) for item in by_name.values())


# ---------------------------------------------------------------- appel HTTP (simulé)
class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_fetch_sends_bearer_token_and_parses_list(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["auth"] = request.get_header("Authorization")
        return _FakeResponse(FIXTURE.read_bytes())

    monkeypatch.setattr(adapter.urllib.request, "urlopen", fake_urlopen)
    items = adapter.fetch_bo1_items("http://bo1.test/", token="abc")
    assert captured["url"] == "http://bo1.test/api/items"
    assert captured["auth"] == "Bearer abc"
    assert len(items) == 12


def test_fetch_without_token_sends_no_auth_header(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["auth"] = request.get_header("Authorization")
        return _FakeResponse(b"[]")

    monkeypatch.setattr(adapter.urllib.request, "urlopen", fake_urlopen)
    assert adapter.fetch_bo1_items("http://bo1.test", token="") == []
    assert captured["auth"] is None


def test_unreachable_bo1_raises_clear_error(monkeypatch):
    def fake_urlopen(request, timeout):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(adapter.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(adapter.BO1UnavailableError):
        adapter.fetch_bo1_items("http://bo1.test", token="")


def test_non_list_response_is_rejected(monkeypatch):
    monkeypatch.setattr(adapter.urllib.request, "urlopen",
                        lambda request, timeout: _FakeResponse(json.dumps({"detail": "x"}).encode()))
    with pytest.raises(adapter.BO1UnavailableError):
        adapter.fetch_bo1_items("http://bo1.test", token="")


def test_fallback_file_is_used_when_bo1_is_down(monkeypatch):
    def fake_urlopen(request, timeout):
        raise urllib.error.URLError("down")

    monkeypatch.setattr(adapter.urllib.request, "urlopen", fake_urlopen)
    wardrobe, report = adapter.load_wardrobe_from_bo1("http://bo1.test", token="", fallback_file=FIXTURE)
    assert report["source"] == "fichier:bo1_items_sample.json"
    assert len(wardrobe) == 10


# ---------------------------------------------------------------- intégration avec le moteur BO4
def _ids(outfit):
    return {item["id"] if isinstance(item, dict) else str(item) for item in outfit["items"]}


def test_engine_accepts_every_adapted_item(by_name):
    engine = pytest.importorskip("outfit_engine")
    for item in by_name.values():
        assert engine.garment_role(item) is not None, item["name"]


@pytest.mark.parametrize("season", ["spring", "summer", "autumn", "winter"])
@pytest.mark.parametrize("occasion", ["university", "work", "evening", "casual"])
def test_engine_recommends_only_bo1_garments(bo1_items, occasion, season):
    engine = pytest.importorskip("outfit_engine")
    wardrobe, _ = adapter.adapt_wardrobe(bo1_items)
    outfits = engine.recommend_outfits(wardrobe, occasion=occasion, season=season, top_k=3)
    assert outfits, "le moteur doit proposer au moins une tenue"
    for outfit in outfits:
        assert _ids(outfit) <= GARMENT_IDS
        assert 0 <= outfit["score"] <= 100


def test_occasion_now_changes_the_ranking(bo1_items):
    """Avec les styles BO1 mappés, l'occasion doit enfin influencer le classement
    (ce n'était pas le cas avec les vêtements H&M au style inconnu)."""
    engine = pytest.importorskip("outfit_engine")
    wardrobe, _ = adapter.adapt_wardrobe(bo1_items)
    work = engine.recommend_outfits(wardrobe, occasion="work", season="autumn", top_k=3)
    casual = engine.recommend_outfits(wardrobe, occasion="casual", season="autumn", top_k=3)
    assert [_ids(o) for o in work] != [_ids(o) for o in casual]
