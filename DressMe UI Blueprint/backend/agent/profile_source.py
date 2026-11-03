"""Style profile for BO3: the signed-in user's Supabase profile, or the bundled sample for the demo user.

The ranker uses three things from the profile: preferred_styles and preferred_colors (preference_match) and
occasion_frequency (use_frequency). The app's profile page stores style, colour and occasion *preferences*, not
how often each occasion happens, so occasion_frequency is an estimate: occasions the user ticked get a high
value, the others a low one. If they ticked none, the dict stays empty and the ranker uses its neutral default.

profile_source tells the UI how real the profile is:
    profile   built from the user's own `style_profiles` row
    default   signed-in user who has not filled in any preference yet: neutral values, no sample persona
    sample    data/sample_profile.json, for the demo user only
"""

import json
import os
import time
from pathlib import Path
from typing import Any

import httpx

from .wardrobe_source import is_demo_user

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
CACHE_SECONDS = 60

# Style options of the profile page (src/features/profile/options.ts) -> style tags of agent/coverage.py.
STYLE_TAGS = {
    "minimalist": ["minimal"],
    "classic / timeless": ["classic"],
    "smart casual": ["classic", "practical"],
    "editorial / fashion-forward": ["elegant"],
    "boho / relaxed": ["relaxed"],
    "elegant": ["elegant"],
    "sporty": ["sporty"],
    "streetwear": ["relaxed", "sporty"],
}
# Occasion options of the profile page -> occasion keys of agent/coverage.py.
OCCASION_KEYS = {
    "work / office": ["work"],
    "smart casual": ["smart_casual"],
    "weekend leisure": ["casual", "outdoor"],
    "evening / dinner": ["date_night"],
    "travel": ["outdoor"],
    "formal event": ["formal"],
    "wedding / ceremony": ["formal"],
    "sport / active": ["sport"],
    "everyday casual": ["casual"],
}
ALL_OCCASIONS = ("work", "casual", "smart_casual", "formal", "outdoor", "sport", "beach", "date_night")
CHOSEN, NOT_CHOSEN = 0.85, 0.3

_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def _sample_profile() -> dict[str, Any]:
    profile = json.loads((DATA_DIR / "sample_profile.json").read_text(encoding="utf-8"))
    return {**profile, "profile_source": "sample"}


def build_profile(user_id: str, profile_row: dict[str, Any] | None, style_row: dict[str, Any] | None) -> dict[str, Any]:
    """Turn the Supabase rows into the profile dict the ranker reads. Pure function, easy to test."""
    style_row = style_row or {}
    styles: list[str] = []
    for label in style_row.get("preferred_styles") or []:
        for tag in STYLE_TAGS.get(str(label).strip().lower(), []):
            if tag not in styles:
                styles.append(tag)

    occasions: dict[str, float] = {}
    chosen = style_row.get("preferred_occasions") or []
    if chosen:
        occasions = {key: NOT_CHOSEN for key in ALL_OCCASIONS}
        for label in chosen:
            for key in OCCASION_KEYS.get(str(label).strip().lower(), []):
                occasions[key] = CHOSEN

    colors = [str(c).strip().lower() for c in style_row.get("preferred_colors") or []]
    avoided = [str(c).strip().lower() for c in style_row.get("avoided_colors") or []]
    has_preferences = bool(styles or colors or avoided or occasions)
    location = (profile_row or {}).get("location")
    return {
        "user_id": user_id,
        "display_name": (profile_row or {}).get("display_name") or "",
        "city": location.get("city", "") if isinstance(location, dict) else "",
        "preferred_styles": styles,
        "preferred_colors": colors,
        "avoided_colors": avoided,
        "occasion_frequency": occasions,
        "profile_source": "profile" if has_preferences else "default",
    }


def _rest(table: str, params: dict[str, str]) -> dict[str, Any] | None:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SERVICE_KEY")
    if not (url and key):
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are not both set")
    response = httpx.get(
        f"{url.rstrip('/')}/rest/v1/{table}",
        params={**params, "select": "*", "limit": "1"},
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
        timeout=15,
    )
    response.raise_for_status()
    rows = response.json()
    return rows[0] if rows else None


def load_profile(user_id: str | None = None) -> dict[str, Any]:
    """The user's style profile. Demo user: the sample persona. Signed-in user: their own preferences."""
    if is_demo_user(user_id):
        return _sample_profile()
    now = time.time()
    hit = _cache.get(user_id)
    if hit and now - hit[0] < CACHE_SECONDS:
        return hit[1]
    try:
        profile = build_profile(
            user_id,
            _rest("profiles", {"id": f"eq.{user_id}"}),
            _rest("style_profiles", {"user_id": f"eq.{user_id}"}),
        )
    except Exception:
        # A profile that cannot be read must not stop the analysis, and must not borrow the sample persona.
        profile = build_profile(user_id, None, None)
        _cache[user_id] = (now - CACHE_SECONDS + 10, profile)    # retry in ~10 s
        return profile
    _cache[user_id] = (now, profile)
    return profile
