"""Wardrobe source for BO3: the user's pieces detected by BO1 (Supabase `items`), or the bundled sample.

Configuration (repo-root .env, or backend/.env which wins):
    SUPABASE_URL                e.g. https://<project-ref>.supabase.co
    SUPABASE_SERVICE_ROLE_KEY   server-side key (SUPABASE_SERVICE_KEY also accepted); `items` is protected by row-level security
    WARDROBE_USER_ID            only when nobody is signed in (Streamlit, scripts); the API passes the signed-in user instead

load_wardrobe(user_id) returns that user's pieces. Without Supabase configured, without a user id, or if
Supabase cannot be reached, BO3 uses data/sample_wardrobe.json.
`SOURCE_INFO` records which one was used so the UI can say so.
"""

import json
import os
import re
import time
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BACKEND_DIR / "data"
load_dotenv(BACKEND_DIR / ".env")
load_dotenv(BACKEND_DIR.parents[1] / ".env")  # repo-root .env

CACHE_SECONDS = 60
SOURCE_INFO: dict[str, Any] = {"source": "sample", "item_count": 0, "reason": "not loaded yet"}
_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}  # per user: id -> (loaded at, items)

# BO1 category -> BO3 category (the vocabulary of agent/coverage.py).
CATEGORY_MAP = {
    "top": "top", "shirt": "top", "blouse": "top", "sweater": "top", "t-shirt": "top", "tshirt": "top",
    "pants": "bottom", "trousers": "bottom", "jeans": "bottom", "shorts": "bottom", "skirt": "bottom",
    "dress": "dress",
    "jacket": "outerwear", "coat": "outerwear", "blazer": "outerwear", "outerwear": "outerwear",
    "shoe": "shoes", "shoes": "shoes", "sneakers": "shoes", "boots": "shoes", "sandals": "shoes",
    "bag": "accessory", "belt": "accessory", "hat": "accessory", "glasses": "accessory",
    "watch": "accessory", "tights": "accessory", "scarf": "accessory", "jewelry": "accessory",
    "headband": "accessory", "sock": "accessory", "glove": "accessory", "umbrella": "accessory",
    "accessory": "accessory",
    "swimwear": "other",
}

# Keyword -> BO3 subcategory, checked in order against the BO1 subcategory (then the name).
SUBCATEGORY_RULES: dict[str, list[tuple[str, str]]] = {
    "top": [("sport", "sports_top"), ("athletic", "sports_top"), ("gym", "sports_top"), ("running", "sports_top"),
            ("training", "sports_top"), ("jersey", "sports_top"), ("hoodie", "hoodie"), ("t-shirt", "t-shirt"), ("tee", "t-shirt"), ("linen shirt", "linen_shirt"), ("blouse", "blouse"),
            ("shirt", "shirt"), ("turtleneck", "turtleneck"), ("cardigan", "cardigan"), ("tank", "tank_top"),
            ("sweater", "sweater"), ("knit", "sweater"), ("jumper", "sweater")],
    "bottom": [("legging", "leggings"), ("jogger", "joggers"), ("sweatpant", "joggers"), ("track", "joggers"),
               ("jeans", "jeans"), ("chino", "chinos"), ("short", "shorts"), ("linen", "linen_trousers"),
               ("skirt", "skirt"), ("trouser", "trousers"), ("pants", "trousers")],
    "dress": [("evening", "evening_dress"), ("cocktail", "cocktail_dress")],
    "outerwear": [("track", "track_jacket"), ("windbreaker", "windbreaker"), ("softshell", "windbreaker"),
                  ("fleece", "fleece"), ("hoodie", "hoodie"), ("waterproof", "rain_jacket"), ("rain", "rain_jacket"), ("trench", "trench"), ("parka", "parka"), ("puffer", "puffer"),
                  ("suit", "suit_jacket"), ("blazer", "blazer"), ("denim", "denim_jacket"), ("coat", "coat")],
    "shoes": [("hiking", "hiking_boots"), ("trek", "hiking_boots"), ("running", "sneakers"), ("trainer", "sneakers"),
              ("ankle boot", "ankle_boots"), ("boot", "boots"), ("loafer", "loafers"), ("derby", "derbies"),
              ("oxford", "oxfords"), ("heel", "heels"), ("pump", "pumps"), ("sandal", "sandals"),
              ("espadrille", "espadrilles"), ("slide", "slides"), ("sneaker", "sneakers")],
    "accessory": [("clutch", "clutch"), ("evening bag", "evening_bag"), ("gym", "gym_bag"), ("duffel", "gym_bag"),
                  ("backpack", "backpack"), ("rucksack", "backpack"), ("beach bag", "beach_bag"), ("tote", "tote"),
                  ("bag", "bag"), ("belt", "belt"), ("headband", "headband"), ("sock", "socks"),
                  ("sunglass", "sunglasses"), ("hat", "hat"), ("cap", "cap"), ("tie", "tie"), ("jewel", "jewelry")],
}


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def _subcategory(category: str, row: dict[str, Any]) -> str:
    text = f"{row.get('subcategory') or ''} {row.get('name') or ''}".lower()
    for keyword, canonical in SUBCATEGORY_RULES.get(category, []):
        if keyword in (row.get("subcategory") or "").lower():
            return canonical
    for keyword, canonical in SUBCATEGORY_RULES.get(category, []):
        if keyword in text:
            return canonical
    return _slug(row.get("subcategory") or row.get("category") or "other")


def to_bo3_item(row: dict[str, Any]) -> dict[str, Any]:
    """One BO1 `items` row in the shape the BO3 rules and ranker expect."""
    category = CATEGORY_MAP.get(_slug(row.get("category") or "").replace("_", "-"), None)
    category = category or CATEGORY_MAP.get(_slug(row.get("category") or ""), "other")
    color = (row.get("color_name") or "").lower().strip()
    material = (row.get("material") or "").lower().strip()
    style = (row.get("style") or "").lower().strip()
    return {
        "id": row["id"],
        "name": row.get("name") or row.get("subcategory") or row.get("category") or "Unnamed piece",
        "category": category,
        "subcategory": _subcategory(category, row),
        "colors": [color] if color else [],
        "materials": [material] if material else [],
        "seasons": [s.lower() for s in (row.get("seasons") or [])],
        "occasion_tags": [_slug(o) for o in (row.get("occasions") or [])],
        "style_tags": [style] if style else [],
        "image_url": row.get("cutout_url") or row.get("image_url") or None,   # shown in the agent chat
    }


def _fetch_supabase(user_id: str | None) -> list[dict[str, Any]]:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SERVICE_KEY")
    user_id = user_id or os.getenv("WARDROBE_USER_ID")   # no login (Streamlit, scripts): old behaviour
    if not (url and key and user_id):
        raise RuntimeError("SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY and a user id are not all set")
    response = httpx.get(
        f"{url.rstrip('/')}/rest/v1/items",
        params={"user_id": f"eq.{user_id}", "select": "*", "order": "created_at.asc"},
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
        timeout=15,
    )
    response.raise_for_status()
    return [to_bo3_item(row) for row in response.json()]


def load_wardrobe(user_id: str | None = None) -> list[dict[str, Any]]:
    """The signed-in user's pieces. user_id=None keeps the old WARDROBE_USER_ID / sample behaviour."""
    if user_id == "demo_user":      # the shared user BO3 uses when Supabase is not configured
        user_id = None
    cache_key = user_id or "default"
    now = time.time()
    hit = _cache.get(cache_key)
    if hit and now - hit[0] < CACHE_SECONDS:
        return hit[1]
    try:
        items = _fetch_supabase(user_id)
        if not items:
            raise RuntimeError("no pieces found in Supabase `items` for this user")
        SOURCE_INFO.update(source="supabase", item_count=len(items), reason="BO1 pieces from Supabase items")
    except Exception as error:  # fall back to the sample so the demo keeps working
        items = json.loads((DATA_DIR / "sample_wardrobe.json").read_text(encoding="utf-8"))
        SOURCE_INFO.update(source="sample", item_count=len(items), reason=str(error)[:160])
    _cache[cache_key] = (now, items)
    return items
