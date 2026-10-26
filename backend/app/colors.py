"""Dominant colour extraction on the garment pixels only (mask-aware)."""
from __future__ import annotations

import numpy as np
from sklearn.cluster import KMeans

# Fashion-oriented named palette (name, hex).
PALETTE = [
    ("black", "#1c1c1c"), ("charcoal", "#3d3d3d"), ("grey", "#8a8a8a"),
    ("light grey", "#c8c8c8"), ("white", "#f5f5f2"), ("cream", "#efe6d2"),
    ("beige", "#d6bf98"), ("camel", "#b58a57"), ("tan", "#c9a27a"),
    ("brown", "#7a4a2a"), ("chocolate", "#4a2c1d"), ("khaki", "#b5a77a"),
    ("olive", "#6b6b2f"), ("green", "#3f8a4a"), ("forest green", "#24452c"),
    ("mint", "#a8dcc2"), ("teal", "#1f7a7a"), ("navy", "#1f2a4d"),
    ("blue", "#3666b0"), ("denim blue", "#4a6890"), ("light blue", "#9cc3e6"),
    ("purple", "#6a3d8f"), ("lavender", "#bfa8dc"), ("burgundy", "#6e1f2e"),
    ("red", "#c0282d"), ("coral", "#ef7f6a"), ("pink", "#e8a0b4"),
    ("hot pink", "#d63c84"), ("orange", "#e0772a"), ("mustard", "#d1a12c"),
    ("yellow", "#f0d43a"), ("gold", "#c9a94b"), ("silver", "#b8b8bc"),
]


def _srgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    """rgb: (..., 3) in 0..255 -> CIELAB (D65)."""
    c = rgb.astype(np.float64) / 255.0
    c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    m = np.array([[0.4124, 0.3576, 0.1805],
                  [0.2126, 0.7152, 0.0722],
                  [0.0193, 0.1192, 0.9505]])
    xyz = c @ m.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    L = 116 * f[..., 1] - 16
    a = 500 * (f[..., 0] - f[..., 1])
    b = 200 * (f[..., 1] - f[..., 2])
    return np.stack([L, a, b], axis=-1)


def _hex_to_rgb(h: str) -> np.ndarray:
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)])


_PALETTE_LAB = _srgb_to_lab(np.array([_hex_to_rgb(h) for _, h in PALETTE]))


COLOR_NAMES = [n for n, _ in PALETTE]


def nearest_name(rgb: np.ndarray) -> str:
    lab = _srgb_to_lab(np.asarray(rgb)[None, :])[0]
    if lab[0] < 12:  # too dark for a hue to be visible on fabric
        return "black"
    d = np.linalg.norm(_PALETTE_LAB - lab, axis=1)
    return PALETTE[int(d.argmin())][0]


def to_hex(rgb) -> str:
    r, g, b = (int(round(x)) for x in rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


def dominant_colors(pixels: np.ndarray, k: int = 4, max_samples: int = 6000) -> list[dict]:
    """pixels: (N, 3) uint8 RGB of the garment only.

    Returns clusters sorted by share: [{name, hex, share}], merged by name.
    """
    if len(pixels) == 0:
        return [{"name": "unknown", "hex": "#999999", "share": 1.0}]
    if len(pixels) > max_samples:
        idx = np.random.default_rng(0).choice(len(pixels), max_samples, replace=False)
        pixels = pixels[idx]
    k = max(1, min(k, len(np.unique(pixels, axis=0))))
    # Cluster in Lab so distances match perception.
    lab = _srgb_to_lab(pixels)
    km = KMeans(n_clusters=k, n_init=4, random_state=0).fit(lab)
    counts = np.bincount(km.labels_, minlength=k)
    merged: dict[str, dict] = {}
    for ci in range(k):
        members = pixels[km.labels_ == ci]
        if len(members) == 0:
            continue
        rgb = np.median(members, axis=0)
        name = nearest_name(rgb)
        share = counts[ci] / counts.sum()
        if name in merged:
            merged[name]["share"] += share
        else:
            merged[name] = {"name": name, "hex": to_hex(rgb), "share": share}
    out = sorted(merged.values(), key=lambda c: -c["share"])
    for c in out:
        c["share"] = round(float(c["share"]), 3)
    return out
