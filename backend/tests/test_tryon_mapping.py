import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import avatar_store  # noqa: E402
import main  # noqa: E402
import tryon_mapping  # noqa: E402
from avatar_auth import User  # noqa: E402


def item(**overrides):
    base = {
        "id": "item-1",
        "name": "Test item",
        "category": "top",
        "category_group": "Tops",
        "subcategory": None,
        "material": None,
        "formality": 2,
        "color_hex": "#123456",
        "cutout_url": "https://example.test/cutout.png",
    }
    base.update(overrides)
    return base


def test_top_maps_to_tshirt():
    resolved = tryon_mapping.resolve_item(item(), main.GARMENT_CATALOG)
    assert resolved["template"] == "tshirt"
    assert resolved["slot"] == "top"
    assert resolved["color_hex"] == "#123456"
    assert resolved["color"] == pytest.approx([0x12 / 255, 0x34 / 255, 0x56 / 255])


def test_formal_top_maps_to_oxford():
    resolved = tryon_mapping.resolve_item(item(formality=5), main.GARMENT_CATALOG)
    assert resolved["template"] == "oxford"


def test_denim_pants_map_to_jeans():
    resolved = tryon_mapping.resolve_item(
        item(category="pants", category_group="Bottoms", material="denim"),
        main.GARMENT_CATALOG,
    )
    assert resolved["template"] == "jeans"


@pytest.mark.parametrize("category", ["skirt", "shorts", "bag", "belt", "watch"])
def test_unsupported_categories_are_rejected(category):
    assert tryon_mapping.resolve_item(item(category=category), main.GARMENT_CATALOG) is None


def test_local_payload_resolves_template_and_colour():
    resolved = tryon_mapping.resolve_payload(
        {
            "wardrobe_item_id": "abc",
            "template": "boots",
            "label": "Shoes",
            "color_hex": "#000000",
        },
        main.GARMENT_CATALOG,
    )
    assert resolved["template"] == "boots"
    assert resolved["slot"] == "shoes"
    assert resolved["color"] == [0.0, 0.0, 0.0]


def test_resolve_tryon_specs_rejects_unsupported_wardrobe_item(tmp_path, monkeypatch):
    monkeypatch.setattr(avatar_store.settings, "LOCAL_AVATAR_DIR", tmp_path / "avatars")
    monkeypatch.setattr(main, "AVATAR_STORE", avatar_store.LocalAvatarStore(tmp_path))
    request = main.GenerateRequest(
        targets={"muscle": 0.5},
        wardrobe_item_ids=["legacy-item"],
        wardrobe_items=[
            main.WardrobeItemInput(
                wardrobe_item_id="legacy-item",
                label="Pleated skirt",
                category="skirt",
                category_group="Bottoms",
            )
        ],
    )
    with pytest.raises(HTTPException) as exc:
        main.resolve_tryon_specs(request, User(id="test-user"))
    assert exc.value.status_code == 422


def test_resolve_tryon_specs_local_payload(tmp_path, monkeypatch):
    monkeypatch.setattr(avatar_store.settings, "LOCAL_AVATAR_DIR", tmp_path / "avatars")
    monkeypatch.setattr(main, "AVATAR_STORE", avatar_store.LocalAvatarStore(tmp_path))
    request = main.GenerateRequest(
        targets={"muscle": 0.5},
        wardrobe_item_ids=["item-1"],
        wardrobe_items=[
            main.WardrobeItemInput(
                wardrobe_item_id="item-1",
                template="tshirt",
                label="My tee",
                color_hex="#abcdef",
                category="top",
            )
        ],
    )
    specs = main.resolve_tryon_specs(request, User(id="test-user"))
    assert len(specs) == 1
    assert specs[0]["template"] == "tshirt"
    assert specs[0]["label"] == "My tee"
