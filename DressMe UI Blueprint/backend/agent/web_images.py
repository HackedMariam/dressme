"""Free photos of Tunisian shops that illustrate a missing piece (no API key, no account).

How it works
    1. The query is built on the SERVER from the gap's own description ("a warm wool coat"). The browser never
       sends free text, otherwise this endpoint would be an open search proxy for anyone.
    2. The query is written in FRENCH with "tunisie prix TND" and the Tunisian region: Tunisian shops are indexed in
       French, and in a test with the English wording 29 of 36 pieces found fewer than 3 Tunisian shops.
    3. `ddgs` sends the same request as DuckDuckGo's "Images" tab and returns title / thumbnail / image / page url.
       It is not an official API: free and keyless, but DuckDuckGo may throttle it, hence the cache and the fallbacks.
    4. TUNISIA ONLY is enforced here, not trusted to the engine: a result is kept only if the page it comes from is
       on a ".tn" domain (celio.tn, zen.com.tn...). Nothing else is shown, even if that means no photo at all.
    5. Results are cleaned (https only, big enough, no duplicates) and cut to a few photos, preferring one per shop.
    6. We keep the *thumbnail* for display (a stable copy hosted by Bing; shops often block or remove the original
       image) and the *page url* as the link back to the shop, which also credits whoever owns the photo.

The web only ILLUSTRATES a gap that the rules and the ranker already found. It never decides what is missing.
"""

import json
import re
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
CACHE_FILE = DATA_DIR / "web_images_cache.json"   # gitignored; lets the demo work even if the search is blocked

REGION = "tn-fr"             # DuckDuckGo region: Tunisia, French
TUNISIAN_SUFFIXES = (".tn",)  # a page is Tunisian if its host ends like this (zen.com.tn, celio.tn...)
# Tunisian shops that sell on a non-.tn domain can be listed here once the team has checked them. Empty on purpose.
EXTRA_TUNISIAN_SHOPS: frozenset[str] = frozenset()
MARKET_WORDS = "tunisie prix TND"

CACHE_SECONDS = 6 * 3600     # the same piece gives the same photos for 6 h: fewer requests, faster cards
MAX_SEARCHES_PER_MINUTE = 20  # a free engine throttles abusers: stay well below that
MIN_SIDE = 300               # pixels; filters out icons and tiny thumbnails
FETCH_RESULTS = 30           # ask for many results: most come from non-Tunisian sites and are dropped
TIMEOUT_SECONDS = 10
RETRY_PAUSE_SECONDS = 1.5    # wait before the single automatic retry

# French names of the pieces in agent/coverage.py (the shops are indexed in French). A new piece without an
# entry still works with its English description, only with fewer Tunisian results.
PIECE_FR = {
    "a breathable cap": "casquette", "a breathable linen top": "haut en lin",
    "a breathable sports t-shirt": "t-shirt de sport", "a fleece pullover": "pull polaire",
    "a gym backpack": "sac à dos de sport", "a hiking backpack": "sac à dos de randonnée",
    "a large straw tote bag": "sac cabas en paille", "a light linen shirt or beach dress": "chemise en lin",
    "a lightweight track jacket": "veste de survêtement", "a silk blouse": "blouse en soie",
    "a small evening clutch": "pochette de soirée", "a small evening clutch bag": "pochette de soirée",
    "a sports headband": "bandeau de sport", "a straw sun hat": "chapeau de paille",
    "a swimsuit": "maillot de bain", "a tailored blazer": "blazer", "a warm wool coat": "manteau en laine",
    "a waterproof rain jacket": "veste imperméable", "a waterproof windbreaker": "veste coupe-vent",
    "a white button-down shirt": "chemise blanche", "a wide straw sun hat": "chapeau de paille",
    "a wool knit sweater": "pull en laine", "an elegant evening dress": "robe de soirée",
    "an elegant midi dress": "robe midi", "black leather loafers": "mocassins cuir noir",
    "classic black sunglasses": "lunettes de soleil noires", "elegant heeled shoes": "chaussures à talons",
    "flat leather sandals": "sandales plates cuir", "heeled ankle boots": "bottines à talons",
    "leather sandals": "sandales en cuir", "light linen trousers": "pantalon en lin",
    "running sneakers": "baskets running", "stretch running leggings": "legging de sport",
    "tailored wool trousers": "pantalon classique", "technical hiking trousers": "pantalon de randonnée",
    "waterproof hiking boots": "chaussures de randonnée",
    "plain cotton socks": "chaussettes en coton", "a leather belt": "ceinture en cuir",
    "opaque winter tights": "collants hiver", "a wool scarf": "écharpe en laine", "warm gloves": "gants hiver",
    "a compact umbrella": "parapluie compact",
    # Needs that only exist for men (agent/departments.py).
    "a dark formal suit": "costume noir", "black leather oxford shoes": "chaussures derby cuir noir",
    "a silk tie": "cravate en soie", "breathable running shorts": "short de running", "swim shorts": "short de bain",
    "a light linen shirt": "chemise en lin", "a canvas beach bag": "sac de plage",
    "a breathable linen shirt": "chemise en lin", "a fitted dress shirt": "chemise slim fit",
    "leather chelsea boots": "bottines chelsea cuir",
}
# Added to the query so a man is not shown women's coats and the other way round. A mixed or unknown
# department gets no word, which is the previous behaviour.
DEPARTMENT_WORD = {"women": "femme", "men": "homme"}

_lock = threading.Lock()
_cache: dict[str, dict[str, Any]] | None = None     # query -> {"at": timestamp, "images": [...]}
_recent_searches: list[float] = []


def build_query(description: str, department: str | None = None) -> str:
    """"a warm wool coat" -> "manteau en laine tunisie prix TND", or "... femme tunisie prix TND" for women
    (shop pages of Tunisian sellers)."""
    description = description.strip()
    name = PIECE_FR.get(description.lower()) or re.sub(r"^(a|an|the)\s+", "", description, flags=re.IGNORECASE)
    word = DEPARTMENT_WORD.get(department or "")
    return " ".join(part for part in (name, word, MARKET_WORDS) if part)


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def is_tunisian(page_url: str) -> bool:
    """True only for pages hosted on a Tunisian domain. "evil.tn.example.com" and "tn.com" do not pass."""
    host = _host(page_url)
    return host.endswith(TUNISIAN_SUFFIXES) or host in EXTRA_TUNISIAN_SHOPS


def _clean_text(value: Any, limit: int = 120) -> str:
    """Titles come from the open web: drop control characters and cap the length before they reach the UI."""
    text = re.sub(r"[\x00-\x1f\x7f]", " ", str(value or ""))
    return re.sub(r"\s+", " ", text).strip()[:limit]


def clean_results(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """Keep usable photos from Tunisian shops: https, big enough, with a page to link to, no duplicate.

    Variety first: one photo per shop. If that gives fewer than `limit` photos (some pieces are sold by one or
    two Tunisian shops only), the remaining places are filled with further photos of the same shops."""
    candidates, seen_images = [], set()
    for row in rows:
        thumbnail, page, image = row.get("thumbnail"), row.get("url"), row.get("image")
        if not (thumbnail and page and str(thumbnail).startswith("https://") and str(page).startswith("http")):
            continue
        if not is_tunisian(str(page)):          # Tunisia only: checked here, whatever the engine returned
            continue
        try:
            if min(int(row.get("width") or 0), int(row.get("height") or 0)) < MIN_SIDE:
                continue
        except (TypeError, ValueError):
            continue
        if thumbnail in seen_images:
            continue
        seen_images.add(thumbnail)
        candidates.append({
            "title": _clean_text(row.get("title")),
            "thumbnail": str(thumbnail),
            "image_url": str(image) if image else None,
            "page_url": str(page),
            "source": _host(str(page)),
        })

    photos, seen_sites = [], set()
    for photo in candidates:                       # pass 1: one per shop
        if photo["source"] not in seen_sites:
            seen_sites.add(photo["source"])
            photos.append(photo)
    for photo in candidates:                       # pass 2: fill the remaining places
        if len(photos) >= limit:
            break
        if photo not in photos:
            photos.append(photo)
    return photos[:limit]


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


def _search_web(query: str) -> list[dict[str, Any]]:
    from ddgs import DDGS    # imported here so the rest of BO3 still starts if the package is missing

    return DDGS(timeout=TIMEOUT_SECONDS).images(
        query, region=REGION, max_results=FETCH_RESULTS, safesearch="moderate"
    )


def search_images(description: str, limit: int = 3, department: str | None = None) -> dict[str, Any]:
    """Photos for one missing piece. Never raises: on any problem it answers with no images and a reason."""
    query, limit = build_query(description, department), max(1, min(limit, 6))
    with _lock:
        cache = _load_cache()
        entry = cache.get(query)
        if entry and time.time() - entry["at"] < CACHE_SECONDS and len(entry["images"]) >= 1:
            return {"query": query, "images": entry["images"][:limit], "cached": True, "message": None}
        allowed = _allowed_now()

    stale = entry["images"][:limit] if entry else []
    if not allowed:
        return {"query": query, "images": stale, "cached": bool(stale), "message": "Too many searches, try again in a minute."}
    images, failure = None, None
    for attempt in range(2):
        try:
            images = clean_results(_search_web(query), 6)
            break
        except Exception as error:   # blocked, offline, package missing...: the analysis itself must keep working
            failure = error
            if attempt == 0:         # the free engine often fails once and works a moment later (seen on 2 of 36)
                time.sleep(RETRY_PAUSE_SECONDS)
                with _lock:
                    if not _allowed_now():   # the retry counts in the per-minute limit like any other search
                        break
    if images is None:
        return {"query": query, "images": stale, "cached": bool(stale),
                "message": f"Photo search unavailable right now ({type(failure).__name__})."}
    if not images and DEPARTMENT_WORD.get(department or ""):
        # Nothing with "homme"/"femme" (a tie, or a unisex hat or sandal that shops do not label): one more search
        # without the word. Still Tunisian shops only, because clean_results applies the same filter.
        with _lock:
            fallback_allowed = _allowed_now()
        if fallback_allowed:
            try:
                images = clean_results(_search_web(build_query(description, None)), 6)
            except Exception:
                images = []
    if images:
        with _lock:
            _load_cache()[query] = {"at": time.time(), "images": images}
            _save_cache()
    return {"query": query, "images": images[:limit], "cached": False,
            "message": None if images else "No photo found on Tunisian shops for this piece."}
