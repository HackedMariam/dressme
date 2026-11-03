"""Free web photos that illustrate a missing piece (no API key, no account).

How it works
    1. The query is built on the SERVER from the gap's own description ("a warm wool coat"). The browser never
       sends free text, otherwise this endpoint would be an open search proxy for anyone.
    2. `ddgs` sends the same request as DuckDuckGo's "Images" tab and returns title / thumbnail / image / page url.
       It is not an official API: free and keyless, but DuckDuckGo may throttle it, hence the cache and the fallbacks.
    3. Results are cleaned (https only, big enough, one per shop, no duplicates) and cut to a few photos.
    4. We keep the *thumbnail* for display (a stable copy hosted by Bing; shops often block or remove the original
       image) and the *page url* as the link back to the source, which also credits whoever owns the photo.

The web only ILLUSTRATES a gap that the rules and the ranker already found. It never decides what is missing.
"""

import json
import re
import threading
import time
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
CACHE_FILE = DATA_DIR / "web_images_cache.json"   # gitignored; lets the demo work even if the search is blocked

CACHE_SECONDS = 6 * 3600     # the same piece gives the same photos for 6 h: fewer requests, faster cards
MAX_SEARCHES_PER_MINUTE = 20  # a free engine throttles abusers: stay well below that
MIN_SIDE = 300               # pixels; filters out icons and tiny thumbnails
FETCH_FACTOR = 4             # ask for 4x more results than needed, since filtering removes many
TIMEOUT_SECONDS = 10

_lock = threading.Lock()
_cache: dict[str, dict[str, Any]] | None = None     # query -> {"at": timestamp, "images": [...]}
_recent_searches: list[float] = []


def build_query(description: str) -> str:
    """"a warm wool coat" -> "warm wool coat product photo" (shop pictures rather than mood photos)."""
    text = re.sub(r"^(a|an|the)\s+", "", description.strip(), flags=re.IGNORECASE)
    return f"{text} product photo"


def _clean_text(value: Any, limit: int = 120) -> str:
    """Titles come from the open web: drop control characters and cap the length before they reach the UI."""
    text = re.sub(r"[\x00-\x1f\x7f]", " ", str(value or ""))
    return re.sub(r"\s+", " ", text).strip()[:limit]


def clean_results(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """Keep usable, varied photos: https, big enough, with a page to link to, at most one per shop."""
    photos, seen_sites, seen_images = [], set(), set()
    for row in rows:
        thumbnail, page, image = row.get("thumbnail"), row.get("url"), row.get("image")
        if not (thumbnail and page and str(thumbnail).startswith("https://") and str(page).startswith("http")):
            continue
        try:
            if min(int(row.get("width") or 0), int(row.get("height") or 0)) < MIN_SIDE:
                continue
        except (TypeError, ValueError):
            continue
        site = _clean_text(row.get("source") or re.sub(r"^https?://([^/]+).*$", r"\1", str(page)), 60).lower()
        if site in seen_sites or thumbnail in seen_images:
            continue
        seen_sites.add(site)
        seen_images.add(thumbnail)
        photos.append({
            "title": _clean_text(row.get("title")),
            "thumbnail": str(thumbnail),
            "image_url": str(image) if image else None,
            "page_url": str(page),
            "source": site,
        })
        if len(photos) == limit:
            break
    return photos


def _load_cache() -> dict[str, dict[str, Any]]:
    global _cache
    if _cache is None:
        try:
            _cache = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _cache = {}
    return _cache


def _save_cache() -> None:
    try:
        CACHE_FILE.write_text(json.dumps(_cache, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass   # the cache is a bonus: never fail a request because it cannot be written


def _allowed_now() -> bool:
    """Sliding one-minute window shared by all users."""
    now = time.time()
    _recent_searches[:] = [t for t in _recent_searches if now - t < 60]
    if len(_recent_searches) >= MAX_SEARCHES_PER_MINUTE:
        return False
    _recent_searches.append(now)
    return True


def _search_web(query: str, wanted: int) -> list[dict[str, Any]]:
    from ddgs import DDGS    # imported here so the rest of BO3 still starts if the package is missing

    return DDGS(timeout=TIMEOUT_SECONDS).images(query, max_results=wanted * FETCH_FACTOR, safesearch="moderate")


def search_images(description: str, limit: int = 3) -> dict[str, Any]:
    """Photos for one missing piece. Never raises: on any problem it answers with no images and a reason."""
    query, limit = build_query(description), max(1, min(limit, 6))
    with _lock:
        cache = _load_cache()
        entry = cache.get(query)
        if entry and time.time() - entry["at"] < CACHE_SECONDS and len(entry["images"]) >= 1:
            return {"query": query, "images": entry["images"][:limit], "cached": True, "message": None}
        allowed = _allowed_now()

    stale = entry["images"][:limit] if entry else []
    if not allowed:
        return {"query": query, "images": stale, "cached": bool(stale), "message": "Too many searches, try again in a minute."}
    try:
        images = clean_results(_search_web(query, limit), 6)
    except Exception as error:   # blocked, offline, package missing...: the analysis itself must keep working
        return {"query": query, "images": stale, "cached": bool(stale),
                "message": f"Photo search unavailable right now ({type(error).__name__})."}
    if images:
        with _lock:
            _load_cache()[query] = {"at": time.time(), "images": images}
            _save_cache()
    return {"query": query, "images": images[:limit], "cached": False,
            "message": None if images else "No photo found for this piece."}
