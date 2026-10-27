"""Map wardrobe items to the shared 3D garment templates.

The catalogue and the category rules live in the frontend `src/lib` folder so
the browser and Blender cannot drift apart. A wardrobe item is represented by a
template silhouette plus its own colour; this is deliberately an approximation,
not a bespoke mesh for every garment.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent
LIB_DIR = BACKEND_DIR.parent / "DressMe UI Blueprint" / "src" / "lib"
MAPPING_PATH = LIB_DIR / "tryon_mapping.json"
DEFAULT_COLOR = "#9a9a9a"
DEFAULT_RGB = (0.6, 0.6, 0.6)


def load_mapping(path: Path = MAPPING_PATH) -> dict:
    with open(path, "r", encoding="utf-8-sig") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("tryon_mapping.json must be an object")
    return data


MAPPING = load_mapping()
CATEGORY_RULES = dict(MAPPING.get("categories") or {})
GROUP_RULES = dict(MAPPING.get("groups") or {})
UNSUPPORTED = {str(value) for value in (MAPPING.get("unsupported") or [])}
FORMAL_AT = int(MAPPING.get("formal_at") or 4)


def normalize_hex(value: Any) -> str:
    text = str(value or "").strip()
    if len(text) == 7 and text.startswith("#"):
        try:
            int(text[1:], 16)
            return text.lower()
        except ValueError:
            pass
    return DEFAULT_COLOR


def hex_to_rgb(value: Any) -> tuple[float, float, float]:
    text = normalize_hex(value)
    if text == DEFAULT_COLOR:
        return DEFAULT_RGB
    return (
        int(text[1:3], 16) / 255.0,
        int(text[3:5], 16) / 255.0,
        int(text[5:7], 16) / 255.0,
    )


def resolve_template(item: dict) -> str | None:
    category = str(item.get("category") or "").strip().lower()
    if category in UNSUPPORTED:
        return None
    group = str(item.get("category_group") or "").strip().lower()
    text = " ".join(
        str(item.get(key) or "")
        for key in ("name", "subcategory", "material")
    ).lower()
    rule = CATEGORY_RULES.get(category)
    formal = float(item.get("formality") or 0) >= FORMAL_AT

    template = None
    if isinstance(rule, dict):
        template = rule.get("default")
        if rule.get("formal") and formal:
            template = rule["formal"]
        if rule.get("denim") and ("denim" in text or "jean" in text):
            template = rule["denim"]
    if not template and not rule and group:
        template = GROUP_RULES.get(group)
    return str(template) if template else None


def resolve_item(item: dict, garments: dict[str, dict]) -> dict | None:
    template = resolve_template(item)
    if not template or template not in garments:
        return None

    color_hex = normalize_hex(item.get("color_hex"))
    return {
        "wardrobe_item_id": str(item.get("id") or item.get("wardrobe_item_id") or ""),
        "template": template,
        "slot": str(garments[template]["slot"]),
        "label": str(item.get("name") or garments[template].get("label") or template),
        "color_hex": color_hex,
        "color": list(hex_to_rgb(color_hex)),
        "cutout_url": item.get("cutout_url") or item.get("image_url"),
        "mesh_url": item.get("mesh_url"),
        "mesh_version": item.get("mesh_version") or 0,
        "category": str(item.get("category") or ""),
    }


def resolve_payload(payload: dict, garments: dict[str, dict]) -> dict | None:
    """Resolve the local-dev payload that already contains a template id."""
    template = str(payload.get("template") or "").strip()
    if not template or template not in garments:
        return None
    color_hex = normalize_hex(payload.get("color_hex"))
    return {
        "wardrobe_item_id": str(payload.get("wardrobe_item_id") or ""),
        "template": template,
        "slot": str(garments[template]["slot"]),
        "label": str(payload.get("label") or garments[template].get("label") or template),
        "color_hex": color_hex,
        "color": list(hex_to_rgb(color_hex)),
        "cutout_url": payload.get("cutout_url"),
        "mesh_url": payload.get("mesh_url"),
        "mesh_version": payload.get("mesh_version") or 0,
        "category": str(payload.get("category") or ""),
    }
