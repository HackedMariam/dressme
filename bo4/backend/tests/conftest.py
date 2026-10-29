"""Fixtures partagées des tests BO4.

Les données sont écrites en dur : aucun accès au CSV, à la base ou aux images,
pour que les tests unitaires restent rapides et hermétiques.
"""

import pytest

from bo4_fixtures import REFERENCE_WARDROBE


@pytest.fixture
def reference_wardrobe():
    return [dict(item) for item in REFERENCE_WARDROBE]


@pytest.fixture
def make_item():
    counter = {"next": 1000}

    def _make(category, color="black", style="unknown", **overrides):
        counter["next"] += 1
        item = {
            "id": str(counter["next"]),
            "name": f"{category}-{color}-{counter['next']}",
            "category": category,
            "color": color,
            "style": style,
        }
        item.update(overrides)
        return item

    return _make
