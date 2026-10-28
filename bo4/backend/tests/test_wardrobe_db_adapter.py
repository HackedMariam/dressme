"""Tests de caractérisation de wardrobe_db_adapter.py, sans base de données.

La connexion PostgreSQL est remplacée par FakeConnection (voir conftest.py).
"""

import psycopg
import pytest

from bo4_fixtures import (
    AMERICAN,
    DENISE,
    HUFFEL,
    LEGOLAS,
    REFERENCE_DB_ROWS,
    REFERENCE_WARDROBE,
    SKINNY,
    FakeConnection,
    outfit_key,
)
from outfit_engine import color_family, garment_role, is_neutral, recommend_outfits
from wardrobe_db_adapter import (
    PUBLIC_ITEM_FIELDS,
    load_user_wardrobe,
    normalize_category,
    normalize_color,
    public_item,
)

pytestmark = pytest.mark.characterization


# ---------------------------------------------------------------------------
# normalize_category : types H&M réels (catalogue, articles avec image)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("product_type, expected, role", [
    ("Vest top", "top", "top"),
    ("Top", "top", "top"),
    ("T-shirt", "tshirt", "top"),
    ("Shirt", "shirt", "top"),
    ("Blouse", "blouse", "top"),
    ("Sweater", "sweater", "top"),
    ("Hoodie", "hoodie", "top"),
    ("Trousers", "trousers", "bottom"),
    ("Shorts", "shorts", "bottom"),
    ("Skirt", "skirt", "bottom"),
    ("Jacket", "jacket", "outerwear"),
    ("Coat", "coat", "outerwear"),
    ("Blazer", "blazer", "outerwear"),
    ("Cardigan", "cardigan", "outerwear"),
])
def test_supported_hm_types(product_type, expected, role):
    category = normalize_category(product_type)
    assert category == expected
    assert garment_role({"category": category}) == role


def test_pants_mapped_to_trousers():
    assert normalize_category("Pants") == "trousers"


@pytest.mark.parametrize("product_type", [
    "Polo shirt", "Outdoor trousers", "Leggings/Tights", "Tailored Waistcoat", "Bodysuit",
    "Jumpsuit/Playsuit", "Dungarees", "Underdress", "Pyjama jumpsuit/playsuit", "Unknown", None,
])
def test_unsupported_hm_types_have_no_role(product_type):
    """Types exclus de la garde-robe (ISSUE-05 : seule la catégorie Dress est ajoutée)."""
    assert garment_role({"category": normalize_category(product_type)}) is None


# ---------------------------------------------------------------------------
# normalize_color : couleurs H&M réelles
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw, expected", [
    ("Black", "black"),
    ("White", "white"),
    ("Grey", "grey"),
    ("Gray", "grey"),
    ("Dark Blue", "navy_blue"),
    ("Light Blue", "light_blue"),
    ("Blue", "blue"),
    ("Beige", "beige"),
    ("Dark Grey", "dark_grey"),
    ("Light Grey", "light_grey"),
    ("Light Pink", "light_pink"),
    ("Dark Green", "dark_green"),
    ("Red", "red"),
    (None, "unknown"),
])
def test_normalize_color(raw, expected):
    assert normalize_color(raw) == expected


@pytest.mark.parametrize("raw, expected", [
    ("Off White", "off_white"),
    ("Light Beige", "light_beige"),
    ("Dark Beige", "dark_beige"),
    ("Dark Red", "dark_red"),
    ("Light Purple", "light_purple"),
    ("Greenish Khaki", "greenish_khaki"),
    ("Yellowish Brown", "yellowish_brown"),
])
def test_hm_color_variants_preserved(raw, expected):
    """L'adaptateur conserve la nuance H&M (champ "color" de l'API inchangé) ;
    c'est le moteur qui l'interprète (ISSUE-02, voir test_hm_color_classification)."""
    assert normalize_color(raw) == expected


# Toutes les couleurs observées dans le catalogue (articles avec image) :
# (nom H&M, neutre ?, famille).
HM_COLOR_CLASSIFICATION = [
    ("Black", True, "black"), ("White", True, "white"), ("Grey", True, "grey"),
    ("Dark Grey", True, "grey"), ("Light Grey", True, "grey"),
    ("Beige", True, "beige"), ("Light Beige", True, "beige"), ("Dark Beige", True, "beige"),
    ("Off White", True, "white"), ("Dark Blue", True, "blue"),
    ("Blue", False, "blue"), ("Light Blue", False, "blue"),
    ("Pink", False, "pink"), ("Light Pink", False, "pink"),
    ("Dark Pink", False, "pink"), ("Other Pink", False, "pink"),
    ("Red", False, "red"), ("Dark Red", False, "red"),
    ("Light Red", False, "red"), ("Other Red", False, "red"),
    ("Green", False, "green"), ("Dark Green", False, "green"), ("Light Green", False, "green"),
    ("Other Green", False, "green"), ("Greenish Khaki", False, "green"),
    ("Yellow", False, "yellow"), ("Dark Yellow", False, "yellow"),
    ("Light Yellow", False, "yellow"), ("Other Yellow", False, "yellow"),
    ("Yellowish Brown", False, "brown"),
    ("Orange", False, "orange"), ("Light Orange", False, "orange"),
    ("Dark Orange", False, "orange"), ("Other Orange", False, "orange"),
    ("Purple", False, "purple"), ("Light Purple", False, "purple"),
    ("Turquoise", False, "turquoise"), ("Light Turquoise", False, "turquoise"),
    ("Dark Turquoise", False, "turquoise"),
    # Limite connue : métalliques non classés (famille = elles-mêmes).
    ("Gold", False, "gold"), ("Silver", False, "silver"),
    ("Bronze/Copper", False, "bronze/copper"),
]


@pytest.mark.parametrize("raw, neutral, family", HM_COLOR_CLASSIFICATION)
def test_hm_color_classification(raw, neutral, family):
    color = normalize_color(raw)
    assert is_neutral(color) is neutral
    assert color_family(color) == family


# ---------------------------------------------------------------------------
# load_user_wardrobe avec une connexion simulée
# ---------------------------------------------------------------------------

def test_uses_tuple_row_factory():
    """Le correctif dict_row / tuple_row doit rester en place."""
    conn = FakeConnection([])
    load_user_wardrobe(conn, 1)
    assert conn.row_factories == [psycopg.rows.tuple_row]


def test_query_parameters_and_filters():
    conn = FakeConnection([])
    load_user_wardrobe(conn, 42)
    assert len(conn.executed) == 1
    query, params = conn.executed[0]
    assert params == (42,)
    assert "w.user_id = %s" in query
    assert "w.available = TRUE" in query
    assert "LEFT JOIN catalog_products" in query


def test_empty_result_returns_empty_list():
    assert load_user_wardrobe(FakeConnection([]), 1) == []


def test_reference_rows_mapped_to_engine_items():
    """Les 8 champs publics sont inchangés par l'ajout des attributs internes."""
    wardrobe = load_user_wardrobe(FakeConnection(REFERENCE_DB_ROWS), 1)
    assert [public_item(i) for i in wardrobe] == REFERENCE_WARDROBE


# (nom, warmth, warmth_source, warmth_evidence, sleeve_length)
EXPECTED_REFERENCE_ATTRIBUTES = [
    (SKINNY, "unknown", "none", [], "unknown"),
    (DENISE, "unknown", "none", [], "long"),       # "buttons down" n'est pas du duvet
    (HUFFEL, "heavy", "text", ["puffer", "padded"], "long"),
    (LEGOLAS, "unknown", "none", [], "short"),
    (AMERICAN, "unknown", "none", [], "long"),     # "long raglan sleeves"
]


def test_reference_internal_attributes():
    wardrobe = load_user_wardrobe(FakeConnection(REFERENCE_DB_ROWS), 1)
    actual = [
        (i["name"], i["warmth"], i["warmth_source"], i["warmth_evidence"], i["sleeve_length"])
        for i in wardrobe
    ]
    assert actual == EXPECTED_REFERENCE_ATTRIBUTES


def test_query_selects_detail_desc():
    conn = FakeConnection([])
    load_user_wardrobe(conn, 1)
    assert "p.detail_desc" in conn.executed[0][0]


def test_missing_description_gives_unknown_attributes():
    row = REFERENCE_DB_ROWS[2][:7] + (None,)
    item = load_user_wardrobe(FakeConnection([row]), 1)[0]
    # Le nom "Huffel puffer jacket" suffit encore : "puffer" est une preuve.
    assert (item["warmth"], item["warmth_evidence"]) == ("heavy", ["puffer"])
    row = (6, 1, "0000000006", None, "Basic jacket", "Jacket", "Black", None)
    item = load_user_wardrobe(FakeConnection([row]), 1)[0]
    assert (item["warmth"], item["warmth_source"], item["sleeve_length"]) == ("unknown", "none", "unknown")


# ---------------------------------------------------------------------------
# Contrat JSON public
# ---------------------------------------------------------------------------

def test_public_item_fields_are_the_historical_eight():
    assert PUBLIC_ITEM_FIELDS == (
        "id", "user_id", "article_id", "name", "category", "color", "style", "image_path",
    )


def test_public_item_strips_internal_attributes():
    item = load_user_wardrobe(FakeConnection(REFERENCE_DB_ROWS[2:3]), 1)[0]
    assert "warmth" in item
    public = public_item(item)
    assert list(public) == list(PUBLIC_ITEM_FIELDS)
    assert public == REFERENCE_WARDROBE[2]


def test_item_id_is_string_and_style_unknown():
    item = load_user_wardrobe(FakeConnection(REFERENCE_DB_ROWS[:1]), 1)[0]
    assert item["id"] == "1"
    assert item["style"] == "unknown"
    assert item["image_path"] == "images/039/0399201042.jpg"


def test_unsupported_and_orphan_rows_are_dropped():
    rows = REFERENCE_DB_ROWS[:2] + [
        (10, 1, "0000000001", None, "Some dungarees", "Dungarees", "Black", "Dungarees in denim."),
        # Article absent du catalogue : le LEFT JOIN renvoie des NULL.
        (11, 1, "9999999999", None, None, None, None, None),
    ]
    wardrobe = load_user_wardrobe(FakeConnection(rows), 1)
    assert [i["id"] for i in wardrobe] == ["1", "2"]


def test_reference_rows_end_to_end():
    wardrobe = load_user_wardrobe(FakeConnection(REFERENCE_DB_ROWS), 1)
    best = recommend_outfits(wardrobe, "university", "autumn", top_k=1)[0]
    assert best["score"] == 76.5
    assert outfit_key(best) == (AMERICAN, SKINNY)
