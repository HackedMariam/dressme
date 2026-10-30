"""Supabase Wardrobe Integration & Fallback Loader.

Loads the user's live digital wardrobe directly from Supabase (`items` table),
mapping database rows to typed Garment domain models with automatic fallback
to bundled datasets when offline or unconfigured.
"""

from __future__ import annotations

import csv
import json
import logging
import os
from pathlib import Path
from typing import Any, List, Optional

import httpx

if __package__:
    from .schemas import Garment
else:
    from schemas import Garment

logger = logging.getLogger("smart_purchasing.wardrobe")

# Category normalization mapping
CATEGORY_MAP = {
    "top": "top",
    "shirt": "shirt",
    "blouse": "blouse",
    "sweater": "sweater",
    "t-shirt": "t_shirt",
    "tshirt": "t_shirt",
    "t_shirt": "t_shirt",
    "pants": "trousers",
    "trousers": "trousers",
    "jeans": "jeans",
    "shorts": "shorts",
    "skirt": "skirt",
    "dress": "dress",
    "jacket": "jacket",
    "coat": "coat",
    "blazer": "blazer",
    "outerwear": "outerwear",
    "shoes": "shoes",
    "sneakers": "sneakers",
    "sandals": "sandals",
    "boots": "boots",
}


def row_to_garment(row: dict[str, Any]) -> Garment:
    """Converts a Supabase `items` row into a typed Garment model."""
    raw_cat = str(row.get("category") or "").lower().strip().replace("-", "_")
    category = CATEGORY_MAP.get(raw_cat, raw_cat or "top")

    raw_color = str(row.get("color_name") or row.get("color_family") or "neutral").lower().strip()
    color = raw_color.replace("-", "_").replace(" ", "_")

    styles = []
    if row.get("style"):
        styles.append(str(row["style"]).lower().strip())
    if row.get("subcategory") and str(row["subcategory"]).lower().strip() not in styles:
        styles.append(str(row["subcategory"]).lower().strip())

    seasons = [str(s).lower().strip() for s in (row.get("seasons") or [])]
    occasions = [str(o).lower().strip().replace(" ", "_") for o in (row.get("occasions") or [])]

    return Garment(
        id=str(row.get("id", f"garment_{id(row)}")),
        name=str(row.get("name") or row.get("subcategory") or f"{color.title()} {category.title()}"),
        category=category,
        color=color,
        style=styles,
        seasons=seasons,
        occasions=occasions,
        image_path=row.get("image_url"),
        tags=list(row.get("tags") or []),
        warmth_level=row.get("warmth"),
        formality_level=row.get("formality"),
        description=row.get("description"),
    )


def load_wardrobe_from_csv(csv_path: Path) -> List[Garment]:
    """Loads wardrobe items from CSV fallback."""
    garments: List[Garment] = []
    if not csv_path.exists():
        return garments

    with open(csv_path, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            category = row.get("category", "").lower().strip()
            color = row.get("color", "").lower().strip()
            style_field = row.get("style", "")
            styles = [s.strip().lower() for s in style_field.split(",") if s.strip()] if style_field else []
            seasons_field = row.get("seasons", "")
            seasons = [s.strip().lower() for s in seasons_field.split(",") if s.strip()] if seasons_field else []
            occasions_field = row.get("occasions", "")
            occasions = [o.strip().lower() for o in occasions_field.split(",") if o.strip()] if occasions_field else []
            tags_field = row.get("tags", "")
            tags = [t.strip().lower() for t in tags_field.split(",") if t.strip()] if tags_field else []

            garments.append(Garment(
                id=row.get("id") or f"csv_{len(garments)+1}",
                name=row.get("name") or f"{color.title()} {category.title()}",
                category=category,
                color=color,
                style=styles,
                seasons=seasons,
                occasions=occasions,
                image_path=row.get("image_path"),
                tags=tags,
                item_type=row.get("item_type"),
                warmth_level=int(row["warmth_level"]) if row.get("warmth_level") else None,
                water_resistance=int(row["water_resistance"]) if row.get("water_resistance") else None,
                weight_g=int(row["weight_g"]) if row.get("weight_g") else None,
                versatility=float(row["versatility"]) if row.get("versatility") else None,
                formality_level=int(row["formality_level"]) if row.get("formality_level") else None,
                clean_items_available=row.get("clean_items_available", "true").lower() == "true",
                description=row.get("description"),
            ))
    return garments


def load_wardrobe_from_json(json_path: Path) -> List[Garment]:
    """Loads wardrobe from sample_wardrobe.json."""
    if not json_path.exists():
        return []
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return [Garment(**it) if isinstance(it, dict) and "id" in it else row_to_garment(it) for it in data]
    except Exception as e:
        logger.warning("Failed to load sample wardrobe JSON: %s", e)
        return []


def load_user_wardrobe(
    user_id: Optional[str] = None,
    supabase_url: Optional[str] = None,
    service_key: Optional[str] = None,
    allow_fallback: bool = True
) -> List[Garment]:
    """Fetches user wardrobe from Supabase with graceful local fallback.

    Args:
        user_id: Specific user UUID to filter items. If None, checks WARDROBE_USER_ID or returns all available.
        supabase_url: Supabase endpoint (defaults to env SUPABASE_URL).
        service_key: Admin service key (defaults to SUPABASE_SERVICE_ROLE_KEY or SUPABASE_SERVICE_KEY).
        allow_fallback: If True, falls back to local sample JSON/CSV on error.
    """
    url = (supabase_url or os.getenv("SUPABASE_URL") or "https://gxmvxegwlntqpcardrjq.supabase.co").rstrip("/")
    key = service_key or os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SERVICE_KEY")
    uid = user_id or os.getenv("WARDROBE_USER_ID")

    # If Supabase credentials and a user id are configured, fetch live user wardrobe
    if key and (uid or os.getenv("FETCH_ALL_WARDROBE", "").lower() in ("1", "true")):
        headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
        }
        params: dict[str, str] = {
            "select": "*",
            "order": "created_at.desc",
            "limit": "150",
        }
        if uid:
            params["user_id"] = f"eq.{uid}"

        try:
            resp = httpx.get(f"{url}/rest/v1/items", headers=headers, params=params, timeout=12)
            if resp.status_code == 200:
                rows = resp.json()
                if rows:
                    items = [row_to_garment(r) for r in rows]
                    logger.info("[Wardrobe] Loaded %d live items from Supabase", len(items))
                    return items
        except Exception as exc:
            logger.warning("[Wardrobe] Supabase request error: %s. Using fallback.", exc)

    if not allow_fallback:
        return []

    # Local fallback hierarchy
    base_dirs = [
        Path(__file__).resolve().parent,
        Path.cwd(),
        Path.cwd() / "smart_purchasing",
    ]
    for d in base_dirs:
        csv_file = d / "wardrobe.csv"
        if csv_file.exists():
            items = load_wardrobe_from_csv(csv_file)
            if items:
                logger.info("[Wardrobe] Loaded %d items from CSV (%s)", len(items), csv_file.name)
                return items

        sample_json = d / "data" / "sample_wardrobe.json"
        if sample_json.exists():
            items = load_wardrobe_from_json(sample_json)
            if items:
                logger.info("[Wardrobe] Loaded %d items from sample JSON (%s)", len(items), sample_json.name)
                return items

    print("[Wardrobe Warning] No wardrobe items found in Supabase or local files.")
    return []
