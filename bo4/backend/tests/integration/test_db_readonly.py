"""Tests d'intégration PostgreSQL : contrat entre la base, l'adaptateur et le moteur.

Ils ne dépendent pas des données de démonstration (pas d'article_id ni de score
attendu) : ils vérifient des invariants valables pour n'importe quel contenu.
"""

from pathlib import Path

import psycopg
import pytest

from outfit_engine import garment_role, normalize, recommend_outfits
from wardrobe_db_adapter import load_user_wardrobe, public_item

pytestmark = pytest.mark.db

DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "hm"

REQUIRED_COLUMNS = {
    "app_users": {"id"},
    "wardrobe_items": {"id", "user_id", "article_id", "image_path", "available"},
    "catalog_products": {
        "article_id", "prod_name", "product_type_name", "colour_group_name", "image_path", "detail_desc",
    },
}

VALID_STRUCTURES = (
    ["top", "bottom"], ["top", "bottom", "outerwear"], ["dress"], ["dress", "outerwear"],
)

PUBLIC_KEYS = ["id", "user_id", "article_id", "name", "category", "color", "style", "image_path"]
INTERNAL_KEYS = {
    "warmth", "warmth_source", "warmth_evidence", "text_warmth_levels", "sleeve_length", "sleeve_source",
}


def test_connection_is_read_only(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("SHOW transaction_read_only")
        assert cur.fetchone()[0] == "on"


@pytest.mark.parametrize("table", sorted(REQUIRED_COLUMNS))
def test_required_columns_exist(db_conn, table):
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = %s",
            (table,),
        )
        columns = {row[0] for row in cur.fetchall()}
    assert REQUIRED_COLUMNS[table] <= columns


def test_adapter_works_with_dict_row_connection(db_conn, user_with_items):
    """La connexion FastAPI utilise dict_row : l'adaptateur doit rester compatible."""
    db_conn.row_factory = psycopg.rows.dict_row
    try:
        wardrobe = load_user_wardrobe(db_conn, user_with_items)
    finally:
        db_conn.row_factory = psycopg.rows.tuple_row
    assert isinstance(wardrobe, list)


def test_wardrobe_item_contract(db_conn, user_with_items):
    wardrobe = load_user_wardrobe(db_conn, user_with_items)
    ids = [item["id"] for item in wardrobe]
    assert len(ids) == len(set(ids))
    for item in wardrobe:
        assert list(public_item(item)) == PUBLIC_KEYS
        assert set(item) == set(PUBLIC_KEYS) | INTERNAL_KEYS
        assert item["warmth"] in ("light", "medium", "heavy", "unknown")
        for fragment in item["warmth_evidence"]:
            assert isinstance(fragment, str) and fragment
        assert isinstance(item["id"], str)
        assert item["user_id"] == user_with_items
        assert garment_role(item) is not None
        assert normalize(item["category"]) == item["category"]
        assert normalize(item["color"]) == item["color"]


def test_wardrobe_count_not_above_available_rows(db_conn, user_with_items):
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM wardrobe_items WHERE user_id = %s AND available = TRUE",
            (user_with_items,),
        )
        available = cur.fetchone()[0]
    assert len(load_user_wardrobe(db_conn, user_with_items)) <= available


def test_unknown_user_has_empty_wardrobe(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("SELECT COALESCE(MAX(user_id), 0) + 1 FROM wardrobe_items")
        missing_user = cur.fetchone()[0]
    assert load_user_wardrobe(db_conn, missing_user) == []


def test_catalog_image_paths_resolve_to_files(db_conn, user_with_items):
    for item in load_user_wardrobe(db_conn, user_with_items):
        path = item["image_path"]
        if path and path.startswith("images/"):
            assert (DATA_DIR / path).is_file(), path


@pytest.mark.parametrize("occasion", ["university", "work", "evening", "casual"])
@pytest.mark.parametrize("season", ["spring", "summer", "autumn", "winter"])
def test_recommendation_invariants(db_conn, user_with_items, occasion, season):
    wardrobe = load_user_wardrobe(db_conn, user_with_items)
    results = recommend_outfits(wardrobe, occasion, season, top_k=5)
    assert len(results) <= 5
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True)
    for r in results:
        assert 0 <= r["score"] <= 100
        ids = [i["id"] for i in r["items"]]
        assert len(ids) == len(set(ids))
        roles = [garment_role(i) for i in r["items"]]
        assert roles in VALID_STRUCTURES
