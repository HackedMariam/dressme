"""Contrat JSON public de GET /users/{user_id}/recommendations (sans base).

main.py lit POSTGRES_PASSWORD à l'import (sinon il le demande au clavier) :
on fournit une valeur factice ; aucune connexion n'est ouverte, get_connection
est remplacé par une connexion simulée.
"""

import importlib

import pytest

from bo4_fixtures import DRESS_DB_ROWS, REFERENCE_DB_ROWS, REFERENCE_WARDROBE, FakeConnection

PUBLIC_ITEM_KEYS = ["id", "user_id", "article_id", "name", "category", "color", "style", "image_path"]
RECOMMENDATION_KEYS = {
    "items", "occasion", "season", "score", "color_score", "style_score",
    "occasion_score", "season_score", "explanations",
}


class FakeApiCursor:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, query, params=None):
        self.conn.queries.append(query)

    def fetchone(self):
        return (1,) if self.conn.user_exists else None


class FakeApiConnection(FakeConnection):
    """Connexion simulée : vérification d'utilisateur + garde-robe de référence."""

    def __init__(self, user_exists=True, rows=REFERENCE_DB_ROWS):
        super().__init__(rows)
        self.user_exists = user_exists
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def cursor(self, row_factory=None):
        if row_factory is None:
            return FakeApiCursor(self)
        return super().cursor(row_factory)


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("POSTGRES_PASSWORD", "unused-in-tests")
    module = importlib.import_module("main")
    return module


def call(api, monkeypatch, user_exists=True, rows=REFERENCE_DB_ROWS, **params):
    monkeypatch.setattr(api, "get_connection", lambda: FakeApiConnection(user_exists, rows))
    args = {"occasion": "university", "season": "autumn", "top_k": 5}
    args.update(params)
    return api.get_user_recommendations(1, **args)


def test_response_top_level_structure(api, monkeypatch):
    response = call(api, monkeypatch)
    assert list(response) == [
        "user_id", "occasion", "season", "wardrobe_count", "recommendations_count", "recommendations",
    ]
    assert response["wardrobe_count"] == 5
    assert response["recommendations_count"] == len(response["recommendations"]) == 5


@pytest.mark.parametrize("season", ["spring", "summer", "autumn", "winter"])
def test_items_expose_exactly_the_eight_public_fields(api, monkeypatch, season):
    response = call(api, monkeypatch, season=season, top_k=20)
    for recommendation in response["recommendations"]:
        assert set(recommendation) == RECOMMENDATION_KEYS
        assert list(recommendation)[0] == "items"
        for item in recommendation["items"]:
            assert list(item) == PUBLIC_ITEM_KEYS
            assert item in REFERENCE_WARDROBE


def test_internal_attributes_do_not_leak(api, monkeypatch):
    response = call(api, monkeypatch, season="summer", top_k=20)
    for recommendation in response["recommendations"]:
        for item in recommendation["items"]:
            assert not {"warmth", "warmth_source", "warmth_evidence", "text_warmth_levels",
                        "sleeve_length", "sleeve_source"} & set(item)


def test_internal_attributes_still_used_for_scoring(api, monkeypatch):
    """La doudoune reconnue "heavy" (texte) est pénalisée en été."""
    response = call(api, monkeypatch, season="summer", top_k=20)
    with_puffer = [r for r in response["recommendations"]
                   if any(i["name"] == "Huffel puffer jacket" for i in r["items"])]
    assert with_puffer
    assert all("Huffel puffer jacket trop chaud pour l'été (attribut)" in r["explanations"]
               for r in with_puffer)


def test_unknown_user_is_404(api, monkeypatch):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as error:
        call(api, monkeypatch, user_exists=False)
    assert error.value.status_code == 404


VALID_STRUCTURES = (
    ["top", "bottom"], ["top", "bottom", "outerwear"], ["dress"], ["dress", "outerwear"],
)


@pytest.mark.parametrize("season", ["spring", "summer", "autumn", "winter"])
def test_dress_outfits_keep_public_contract(api, monkeypatch, season):
    """ISSUE-05 : items contient 1 à 3 vêtements, chacun avec les 8 champs publics."""
    from outfit_engine import garment_role

    response = call(api, monkeypatch, rows=REFERENCE_DB_ROWS + DRESS_DB_ROWS, season=season, top_k=20)
    assert response["wardrobe_count"] == 10
    counts = set()
    for recommendation in response["recommendations"]:
        assert set(recommendation) == RECOMMENDATION_KEYS
        assert 1 <= len(recommendation["items"]) <= 3
        counts.add(len(recommendation["items"]))
        for item in recommendation["items"]:
            assert list(item) == PUBLIC_ITEM_KEYS
        assert [garment_role(i) for i in recommendation["items"]] in VALID_STRUCTURES
    assert 1 in counts  # au moins une robe seule dans le top 20
