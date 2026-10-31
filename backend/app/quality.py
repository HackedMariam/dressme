"""Quality and duplicate gate for the live camera scan.

The live scan saves a capture without asking, so a bad frame (garment cut off by the edge of the
camera, ragged cut-out, low confidence) or the same item held in front of the camera twice ends up
in the wardrobe. These checks run BEFORE anything is saved:

- live_problem(): is this detection good enough to keep? Returns a hint for the user, or None.
- signature():    a small appearance fingerprint of a cut-out (colour histogram + aspect ratio).
- find_duplicate(): is there already an item of the same category that looks the same?
"""
from __future__ import annotations

import io
import logging
import threading
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from PIL import Image

from . import config

log = logging.getLogger("dressme.quality")

EDGE_MARGIN = 0.012      # a box within 1.2% of the frame edge is considered cut off
MIN_AREA_RATIO = 0.04    # smaller than 4% of the frame: too far away to classify
BINS = 4                 # 4x4x4 RGB histogram = 64 values

# Widest plausible width/height of a whole garment. A top far wider than tall is a torn or
# half-visible capture (measured on a real wardrobe: bad captures were 1.4-2.5, good ones <= 1.0).
MAX_ASPECT = {"top": 1.3, "sweater": 1.3, "jacket": 1.3, "vest": 1.3, "dress": 1.1, "pants": 0.95}

# A candidate this close to a saved item of the same category is treated as the same item.
# Calibrated on a real wardrobe: true duplicates scored 0.86-1.00 with aspect 0.00-0.19, while
# different black items scored up to 0.97 but with aspect >= 0.24.
SAME_HISTOGRAM = 0.80
SAME_ASPECT = 0.20       # relative aspect-ratio difference

_signatures: dict[str, dict] = {}   # item id -> signature of its stored cut-out
_lock = threading.Lock()


def _alpha_pixels(png: bytes) -> tuple[np.ndarray, np.ndarray]:
    img = Image.open(io.BytesIO(png)).convert("RGBA")
    arr = np.asarray(img)
    return arr[..., :3], arr[..., 3] > 127


def signature(png: bytes) -> dict | None:
    """Colour histogram of the garment pixels + width/height ratio of the cut-out."""
    try:
        rgb, mask = _alpha_pixels(png)
    except Exception:
        return None
    pixels = rgb[mask]
    if len(pixels) < 200:
        return None
    idx = (pixels // (256 // BINS)).astype(int)
    flat = idx[:, 0] * BINS * BINS + idx[:, 1] * BINS + idx[:, 2]
    hist = np.bincount(flat, minlength=BINS ** 3).astype(float)
    hist /= hist.sum()
    ys, xs = np.where(mask)
    width, height = xs.max() - xs.min() + 1, ys.max() - ys.min() + 1
    return {"hist": hist.round(4).tolist(), "aspect": round(float(width / height), 3)}


def similarity(a: dict, b: dict) -> tuple[float, float]:
    """(histogram intersection 0..1, relative aspect-ratio difference)."""
    inter = float(np.minimum(np.asarray(a["hist"]), np.asarray(b["hist"])).sum())
    big = max(a["aspect"], b["aspect"]) or 1.0
    return inter, abs(a["aspect"] - b["aspect"]) / big


def live_problem(*, category: str, confidence: float, box: list[float], size: tuple[int, int],
                 area_ratio: float, strict: bool = True) -> str | None:
    """A short reason when this detection should not be saved without asking, else None.

    strict=True is the live camera (framing matters). strict=False is an uploaded photo, where a
    garment filling the frame is normal, so only the confidence is checked.
    """
    W, H = size
    x1, y1, x2, y2 = box
    if confidence < config.LIVE_MIN_CONFIDENCE:
        if not strict:
            return "Not sure what this is. A clear photo of a single item on a plain background works best."
        return "Not sure what this is. Hold it up against a plain background."
    if not strict:
        return None
    if x1 <= EDGE_MARGIN * W or y1 <= EDGE_MARGIN * H or x2 >= (1 - EDGE_MARGIN) * W or y2 >= (1 - EDGE_MARGIN) * H:
        return "Show the whole item: part of it is cut off by the edge of the camera."
    if area_ratio < MIN_AREA_RATIO:
        return "Move a little closer to the item."
    height = y2 - y1
    if height > 0 and (x2 - x1) / height > MAX_ASPECT.get(category, 99):
        return "Only part of the item is visible. Hold it up so the whole garment is in view."
    return None


def _stored_signature(store, user_id: str, item: dict) -> dict | None:
    """Signature of a saved item, computed once from its cut-out and cached."""
    saved = (item.get("detection") or {}).get("signature")
    if saved:
        return saved
    with _lock:
        if item["id"] in _signatures:
            return _signatures[item["id"]]
    try:
        from .storage import item_folder

        sig = signature(store.download(f"{item_folder(user_id, item['id'])}/cutout.png"))
    except Exception:
        log.debug("no cut-out to fingerprint for %s", item.get("id"), exc_info=True)
        sig = None
    with _lock:
        _signatures[item["id"]] = sig
    return sig


def find_duplicate(store, user_id: str, items: list[dict], category: str, sig: dict | None) -> dict | None:
    """The saved item of the same category that looks the same as this capture, if any."""
    if not sig:
        return None
    same = [i for i in items if i.get("category") == category]
    if not same:
        return None
    with ThreadPoolExecutor(max_workers=min(8, len(same))) as pool:
        sigs = list(pool.map(lambda i: _stored_signature(store, user_id, i), same))
    best, best_score = None, 0.0
    for item, other in zip(same, sigs):
        if not other:
            continue
        hist, aspect = similarity(sig, other)
        if hist >= SAME_HISTOGRAM and aspect <= SAME_ASPECT and hist > best_score:
            best, best_score = item, hist
    return best
