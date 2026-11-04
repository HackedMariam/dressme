"""Wardrobe source for BO3: the user's pieces detected by BO1 (Supabase `items`), or the bundled sample.

Configuration (repo-root .env, or backend/.env which wins):
    SUPABASE_URL                e.g. https://<project-ref>.supabase.co
    SUPABASE_SERVICE_ROLE_KEY   server-side key (SUPABASE_SERVICE_KEY also accepted); `items` is protected by row-level security
    WARDROBE_USER_ID            only when nobody is signed in (Streamlit, scripts); the API passes the signed-in user instead

load_wardrobe(user_id) returns that user's pieces, and source_info(user_id) says where they came from:
    supabase  the user's real pieces
    sample    data/sample_wardrobe.json, ONLY for the demo user (nobody signed in / Supabase not configured)
    empty     a signed-in user with no pieces: an empty wardrobe, never someone else's or a sample one
    error     a signed-in user whose pieces could not be loaded: an empty wardrobe and a message
The UI shows a banner for everything except "supabase".
"""

import json
import os
import re
import time
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

from . import piece_classifier

BACKEND_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BACKEND_DIR / "data"
load_dotenv(BACKEND_DIR / ".env")
load_dotenv(BACKEND_DIR.parents[1] / ".env")  # repo-root .env

CACHE_SECONDS = 60
ERROR_CACHE_SECONDS = 10    # a failed load is retried soon, but not on every request
DEMO_USER = "demo_user"     # the shared user BO3 uses when Supabase is not configured

MESSAGES = {
    "sample": "Sample data: this is a demo wardrobe, not your pieces.",
    "empty": "No pieces found in your wardrobe yet. Add pieces to My Wardrobe to get gap suggestions.",
    "error": "Your wardrobe could not be loaded right now, so no gaps are shown. Please try again in a moment.",
}
# per user: id -> (loaded at, items, source info). Source info is per user, so two users never see each other's.
_cache: dict[str, tuple[float, list[dict[str, Any]], dict[str, Any]]] = {}

# BO1 category -> BO3 category (the vocabulary of agent/coverage.py).
CATEGORY_MAP = {
    "top": "top", "shirt": "top", "blouse": "top", "sweater": "top", "t-shirt": "top", "tshirt": "top",
    "pants": "bottom", "trousers": "bottom", "jeans": "bottom", "shorts": "bottom", "skirt": "bottom",
    "dress": "dress",
    "jacket": "outerwear", "coat": "outerwear", "blazer": "outerwear", "outerwear": "outerwear",
    "vest": "outerwear", "waistcoat": "outerwear", "gilet": "outerwear",
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
    "dress": [("evening", "evening_dress"), ("cocktail", "cocktail_dress"), ("maxi", "maxi_dress"), ("midi", "midi_dress")],
    # The names BO1's language model really gives to jackets (bomber, biker, military, casual...) come after the
    # classic ones. A plain "jacket" is handled by FALLBACK_RULES, so a name such as "Black Puffer Jacket" still
    # reaches its "puffer" keyword first.
    "outerwear": [("track", "track_jacket"), ("windbreaker", "windbreaker"), ("softshell", "windbreaker"),
                  ("fleece", "fleece"), ("hoodie", "hoodie"), ("waterproof", "rain_jacket"), ("rain", "rain_jacket"), ("trench", "trench"), ("parka", "parka"), ("puffer", "puffer"),
                  ("padded", "puffer"), ("quilted", "puffer"), ("down jacket", "puffer"),
                  ("suit", "suit_jacket"), ("blazer", "blazer"), ("denim", "denim_jacket"), ("coat", "coat"),
                  ("bomber", "bomber_jacket"), ("biker", "leather_jacket"), ("leather", "leather_jacket"),
                  ("military", "field_jacket"), ("field", "field_jacket"), ("utility", "field_jacket"),
                  ("vest", "vest"), ("gilet", "vest"), ("waistcoat", "vest"),
                  ("lightweight", "light_jacket"), ("light jacket", "light_jacket")],
    "shoes": [("hiking", "hiking_boots"), ("trek", "hiking_boots"), ("running", "sneakers"), ("trainer", "sneakers"),
              ("ankle boot", "ankle_boots"), ("boot", "boots"), ("loafer", "loafers"), ("derby", "derbies"),
              ("oxford", "oxfords"), ("heel", "heels"), ("pump", "pumps"), ("sandal", "sandals"),
              ("espadrille", "espadrilles"), ("slide", "slides"), ("sneaker", "sneakers")],
    "accessory": [("clutch", "clutch"), ("evening bag", "evening_bag"), ("gym", "gym_bag"), ("duffel", "gym_bag"),
                  ("backpack", "backpack"), ("rucksack", "backpack"), ("beach bag", "beach_bag"), ("tote", "tote"),
                  ("bag", "bag"), ("belt", "belt"), ("headband", "headband"), ("sock", "socks"),
                  ("tights", "tights"), ("glove", "gloves"), ("umbrella", "umbrella"), ("scarf", "scarf"),
                  ("sunglass", "sunglasses"), ("hat", "hat"), ("cap", "cap"), ("tie", "tie"), ("jewel", "jewelry"),
                  ("watch", "watch")],
}

# Last resort when no keyword above matched in the subcategory NOR in the name: a general word that is too vague to
# be checked first (it would hide the more precise keywords of the name).
FALLBACK_RULES: dict[str, list[tuple[str, str]]] = {
    "outerwear": [("jacket", "casual_jacket")],
}


# The subcategories the rules of coverage.py understand, per category: the closed list the language model chooses from.
CANONICAL: dict[str, list[str]] = {
    category: sorted({canonical for _, canonical in rules}
                     | {canonical for _, canonical in FALLBACK_RULES.get(category, [])}
                     | ({"polo"} if category == "top" else set()))
    for category, rules in SUBCATEGORY_RULES.items()
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
    for keyword, canonical in FALLBACK_RULES.get(category, []):
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


def refine_unrecognised(rows: list[dict[str, Any]], items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pieces whose name the keyword rules did not recognise get a subcategory from the language model, chosen in
    CANONICAL or not at all (see piece_classifier.py). The rules always go first; a failure changes nothing."""
    unknown = [(row, item) for row, item in zip(rows, items)
               if item["category"] in CANONICAL and item["subcategory"] not in CANONICAL[item["category"]]]
    if not unknown:
        return items
    texts = {id(item): piece_classifier.clean_text(row.get("subcategory") or row.get("name")) for row, item in unknown}
    answers = piece_classifier.classify_many([(item["category"], texts[id(item)]) for _, item in unknown], CANONICAL)
    for _, item in unknown:
        choice = answers.get((item["category"], texts[id(item)]))
        if choice:
            item["subcategory"], item["subcategory_source"] = choice, "llm"
    return items


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
    rows = response.json()
    return refine_unrecognised(rows, [to_bo3_item(row) for row in rows])


def is_demo_user(user_id: str | None) -> bool:
    return user_id in (None, DEMO_USER)


def _info(source: str, item_count: int, reason: str = "") -> dict[str, Any]:
    return {"source": source, "item_count": item_count, "reason": reason[:160], "message": MESSAGES.get(source)}


def _load(user_id: str | None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    demo = is_demo_user(user_id)
    try:
        items = _fetch_supabase(None if demo else user_id)
        if items:
            return items, _info("supabase", len(items), "BO1 pieces from Supabase items")
        reason = "no pieces found in Supabase `items` for this user"
    except Exception as error:
        reason = f"{type(error).__name__}: {error}"
        if not demo:
            return [], _info("error", 0, reason)
    if not demo:
        return [], _info("empty", 0, reason)
    # Demo user only: the bundled sample keeps the offline demo and the Streamlit pages working.
    sample = json.loads((DATA_DIR / "sample_wardrobe.json").read_text(encoding="utf-8"))
    return sample, _info("sample", len(sample), reason)


def _cached(user_id: str | None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    cache_key = DEMO_USER if is_demo_user(user_id) else user_id
    now = time.time()
    hit = _cache.get(cache_key)
    if hit:
        ttl = ERROR_CACHE_SECONDS if hit[2]["source"] == "error" else CACHE_SECONDS
        if now - hit[0] < ttl:
            return hit[1], hit[2]
    items, info = _load(user_id)
    _cache[cache_key] = (now, items, info)
    return items, info


def load_wardrobe(user_id: str | None = None) -> list[dict[str, Any]]:
    """The user's pieces. Only the demo user (None / "demo_user") can get the sample wardrobe."""
    return _cached(user_id)[0]


def source_info(user_id: str | None = None) -> dict[str, Any]:
    """Where this user's wardrobe came from: source, item_count, reason and a message for the UI banner."""
    return _cached(user_id)[1]
