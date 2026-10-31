"""Fixtures partagées des tests BO4.

Les données sont écrites en dur : aucun accès au CSV, à la base ou aux images,
pour que les tests unitaires restent rapides et hermétiques.
"""

from pathlib import Path

import pytest

from bo4_fixtures import REFERENCE_WARDROBE

# Dataset H&M (bo4/data/, ignoré par git, non fourni : voir bo4/README.md). Les tests marqués « hm_images »
# vérifient les empreintes SHA-256 des vraies images E1/E2 : aucun jeu de remplacement ne peut les satisfaire.
HM_IMAGES_DIR = Path(__file__).resolve().parents[2] / "data" / "hm" / "images"


def pytest_runtest_setup(item):
    if item.get_closest_marker("hm_images") and not any(HM_IMAGES_DIR.glob("*/*.jpg")):
        pytest.skip(f"images H&M absentes ({HM_IMAGES_DIR} ; dataset non fourni, voir bo4/README.md)")


@pytest.fixture(autouse=True)
def weather_without_network(monkeypatch):
    """Aucun test n'appelle les vrais services météo : la météo par défaut (stylist_web) passe en mode
    démo hors ligne. Les tests de weather_sources fixent offline=False et simulent chaque source."""
    monkeypatch.setenv("STYLIST_WEATHER_OFFLINE", "1")


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
