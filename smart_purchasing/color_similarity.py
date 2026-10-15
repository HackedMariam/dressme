"""Perceptual Color Similarity Module for DressMe Smart Purchasing Agent.

Implements color conversion from sRGB to CIELAB and calculates perceptual color
differences using the industry-standard CIEDE2000 (Delta E) formula.
Converts perceptual distance into a normalized similarity score in [0.0, 1.0].
"""

import math
import json
import re
from pathlib import Path
from typing import Dict, Tuple, Optional, Any
from dataclasses import dataclass


# =====================================================================
# Color Space Math: sRGB -> CIEXYZ -> CIELAB (D65 Illuminant)
# =====================================================================

def srgb_to_xyz(rgb: Tuple[int, int, int]) -> Tuple[float, float, float]:
    """Converts 8-bit sRGB [0..255] to CIEXYZ (D65 standard illuminant)."""
    def _pivot(c: int) -> float:
        v = c / 255.0
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4

    r_lin = _pivot(rgb[0])
    g_lin = _pivot(rgb[1])
    b_lin = _pivot(rgb[2])

    # Standard sRGB to XYZ matrix (D65 2-degree observer)
    x = (r_lin * 0.4124564 + g_lin * 0.3575761 + b_lin * 0.1804375) * 100.0
    y = (r_lin * 0.2126729 + g_lin * 0.7151522 + b_lin * 0.0721750) * 100.0
    z = (r_lin * 0.0193339 + g_lin * 0.1191920 + b_lin * 0.9503041) * 100.0
    return x, y, z


def xyz_to_lab(xyz: Tuple[float, float, float]) -> Tuple[float, float, float]:
    """Converts CIEXYZ to CIELAB using reference white D65 (Xn=95.047, Yn=100.0, Zn=108.883)."""
    xn, yn, zn = 95.047, 100.000, 108.883
    x, y, z = xyz[0] / xn, xyz[1] / yn, xyz[2] / zn

    delta = 6.0 / 29.0  # ~0.20689
    delta3 = delta ** 3  # ~0.008856

    def _f(t: float) -> float:
        return t ** (1.0 / 3.0) if t > delta3 else (t / (3.0 * delta * delta)) + (4.0 / 29.0)

    fx = _f(x)
    fy = _f(y)
    fz = _f(z)

    l_val = max(0.0, 116.0 * fy - 16.0)
    a_val = 500.0 * (fx - fy)
    b_val = 200.0 * (fy - fz)
    return l_val, a_val, b_val


def rgb_to_lab(rgb: Tuple[int, int, int]) -> Tuple[float, float, float]:
    """Convenience function: directly converts 8-bit sRGB to CIELAB (L*, a*, b*)."""
    return xyz_to_lab(srgb_to_xyz(rgb))


# =====================================================================
# Perceptual Difference: CIEDE2000 (Delta E 00)
# =====================================================================

def ciede2000(
    lab1: Tuple[float, float, float],
    lab2: Tuple[float, float, float],
    k_l: float = 1.0,
    k_c: float = 1.0,
    k_h: float = 1.0
) -> float:
    """Calculates the CIEDE2000 color difference (Delta E 00) between two CIELAB colors.
    
    Implementation follows the technical recommendation by Sharma, Wu, and Dalal (2005).
    """
    l1, a1, b1 = lab1
    l2, a2, b2 = lab2

    c1 = math.hypot(a1, b1)
    c2 = math.hypot(a2, b2)
    c_bar = (c1 + c2) / 2.0
    c_bar7 = c_bar ** 7

    g = 0.5 * (1.0 - math.sqrt(c_bar7 / (c_bar7 + 25.0 ** 7)))
    a1_prime = (1.0 + g) * a1
    a2_prime = (1.0 + g) * a2
    c1_prime = math.hypot(a1_prime, b1)
    c2_prime = math.hypot(a2_prime, b2)

    def _hue_deg(a_prime: float, b_val: float) -> float:
        if a_prime == 0.0 and b_val == 0.0:
            return 0.0
        deg = math.degrees(math.atan2(b_val, a_prime))
        return deg if deg >= 0.0 else deg + 360.0

    h1_prime = _hue_deg(a1_prime, b1)
    h2_prime = _hue_deg(a2_prime, b2)

    delta_l_prime = l2 - l1
    delta_c_prime = c2_prime - c1_prime

    if c1_prime * c2_prime == 0.0:
        delta_h_prime = 0.0
    elif abs(h2_prime - h1_prime) <= 180.0:
        delta_h_prime = h2_prime - h1_prime
    elif h2_prime - h1_prime > 180.0:
        delta_h_prime = (h2_prime - h1_prime) - 360.0
    else:
        delta_h_prime = (h2_prime - h1_prime) + 360.0

    delta_h_capital = 2.0 * math.sqrt(c1_prime * c2_prime) * math.sin(math.radians(delta_h_prime / 2.0))

    l_bar_prime = (l1 + l2) / 2.0
    c_bar_prime = (c1_prime + c2_prime) / 2.0

    if c1_prime * c2_prime == 0.0:
        h_bar_prime = h1_prime + h2_prime
    elif abs(h1_prime - h2_prime) <= 180.0:
        h_bar_prime = (h1_prime + h2_prime) / 2.0
    elif (h1_prime + h2_prime) < 360.0:
        h_bar_prime = (h1_prime + h2_prime + 360.0) / 2.0
    else:
        h_bar_prime = (h1_prime + h2_prime - 360.0) / 2.0

    t = (1.0 - 0.17 * math.cos(math.radians(h_bar_prime - 30.0))
             + 0.24 * math.cos(math.radians(2.0 * h_bar_prime))
             + 0.32 * math.cos(math.radians(3.0 * h_bar_prime + 6.0))
             - 0.20 * math.cos(math.radians(4.0 * h_bar_prime - 63.0)))

    delta_theta = 30.0 * math.exp(-(((h_bar_prime - 275.0) / 25.0) ** 2))
    c_bar_prime7 = c_bar_prime ** 7
    r_c = 2.0 * math.sqrt(c_bar_prime7 / (c_bar_prime7 + 25.0 ** 7))
    s_l = 1.0 + (0.015 * ((l_bar_prime - 50.0) ** 2)) / math.sqrt(20.0 + ((l_bar_prime - 50.0) ** 2))
    s_c = 1.0 + 0.045 * c_bar_prime
    s_h = 1.0 + 0.015 * c_bar_prime * t
    r_t = -math.sin(math.radians(2.0 * delta_theta)) * r_c

    term_l = delta_l_prime / (k_l * s_l)
    term_c = delta_c_prime / (k_c * s_c)
    term_h = delta_h_capital / (k_h * s_h)

    val = term_l ** 2 + term_c ** 2 + term_h ** 2 + r_t * term_c * term_h
    return math.sqrt(max(0.0, val))


def delta_e_to_similarity(delta_e: float, same_family: bool = False) -> float:
    """Converts a CIEDE2000 Delta E difference into a normalized perceptual similarity score in [0.0, 1.0].
    
    Human color perception falls off non-linearly with Delta E:
    - Delta E = 0.00 -> 1.00 (identical)
    - Delta E <= 10.0 -> 1.00 down to 0.82 (closely related tints e.g. white vs ivory ~0.89, white vs cream ~0.86)
    - Delta E in (10, 25] -> 0.82 down to 0.37 (noticeable tonal shifts e.g. charcoal vs black)
    - Delta E in (25, 50] -> 0.37 down to 0.14 (distinct colors e.g. white vs camel ~0.31, NOT highly similar)
    - Delta E > 50.0 -> <= 0.14 down to 0.02 (e.g. black vs white ~0.03)
      * If colors share the same hue family (e.g. navy vs light blue), a tonal family baseline of ~0.24 is retained.
    """
    if delta_e <= 0.0:
        return 1.0
    if delta_e <= 10.0:
        val = 1.0 - (delta_e / 10.0) * 0.18
    elif delta_e <= 25.0:
        val = 0.82 - ((delta_e - 10.0) / 15.0) * 0.45
    elif delta_e <= 50.0:
        val = 0.37 - ((delta_e - 25.0) / 25.0) * 0.23
    else:
        val = max(0.02, 0.14 - ((delta_e - 50.0) / 50.0) * 0.12)
    
    if same_family and val < 0.25:
        val = min(0.35, val + 0.15)
        
    return max(0.0, min(1.0, round(val, 4)))


# =====================================================================
# Structured Data Types & Reusable Service
# =====================================================================

@dataclass
class ColorComparisonResult:
    """Structured report of perceptual color comparison."""
    color1: str
    color2: str
    delta_e: float
    similarity_score: float
    family1: Optional[str]
    family2: Optional[str]
    is_same_family: bool
    explanation: str


class ColorSimilarityService:
    """Reusable service for color management, CIELAB conversion, and similarity evaluation."""

    _instance: Optional["ColorSimilarityService"] = None

    def __init__(self, colors_file: Optional[Path] = None):
        self.colors_dict: Dict[str, Dict[str, Any]] = {}
        self.lab_cache: Dict[str, Tuple[float, float, float]] = {}
        self._load_colors(colors_file)

    @classmethod
    def get_instance(cls) -> "ColorSimilarityService":
        """Singleton accessor for convenience and caching."""
        if cls._instance is None:
            cls._instance = ColorSimilarityService()
        return cls._instance

    def _load_colors(self, colors_file: Optional[Path] = None):
        """Loads color definitions from colors.json."""
        search_paths = [
            colors_file,
            Path(__file__).resolve().parent / "data" / "colors.json",
            Path(__file__).resolve().parent / "colors.json",
            Path(__file__).resolve().parent.parent / "data" / "colors.json",
        ]
        chosen_path: Optional[Path] = None
        for p in search_paths:
            if p and p.exists():
                chosen_path = p
                break

        if not chosen_path:
            # Fallback inline definitions if file is not found
            self._init_default_colors()
            return

        try:
            with open(chosen_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.colors_dict = data.get("colors", {})
        except Exception as err:
            print(f"Warning: Failed to load colors from {chosen_path}: {err}. Falling back to defaults.")
            self._init_default_colors()

        # Precompute CIELAB coordinates
        for cname, cinfo in self.colors_dict.items():
            rgb = tuple(cinfo.get("rgb", [128, 128, 128]))
            self.lab_cache[cname] = rgb_to_lab((rgb[0], rgb[1], rgb[2]))

    def _init_default_colors(self):
        """Fallback color definitions if colors.json cannot be read."""
        self.colors_dict = {
            "white": {"rgb": [255, 255, 255], "family": "white"},
            "ivory": {"rgb": [255, 253, 240], "family": "white"},
            "cream": {"rgb": [253, 244, 227], "family": "white"},
            "black": {"rgb": [15, 15, 15], "family": "black"},
            "navy": {"rgb": [10, 25, 60], "family": "blue"},
            "light_blue": {"rgb": [173, 216, 230], "family": "blue"},
            "grey": {"rgb": [128, 128, 128], "family": "grey"},
        }
        for cname, cinfo in self.colors_dict.items():
            rgb = tuple(cinfo["rgb"])
            self.lab_cache[cname] = rgb_to_lab((rgb[0], rgb[1], rgb[2]))

    def normalize_color_name(self, raw_color: Optional[str]) -> str:
        """Cleans and canonicalizes color labels (e.g. 'off-white' -> 'off_white', 'light blue' -> 'light_blue')."""
        if not raw_color:
            return "unknown"
        c = raw_color.lower().strip()
        c = re.sub(r"[^\w\s-]", "", c)
        c = c.replace("-", "_").replace(" ", "_")

        # Direct match in colors_dict
        if c in self.colors_dict:
            return c

        # Common aliases & synonym normalization
        alias_map = {
            "gray": "grey",
            "dark_jeans": "dark_blue",
            "midnight_blue": "navy",
            "army_green": "olive",
            "maroon": "burgundy",
            "wine": "burgundy",
            "melange": "grey",
        }
        if c in alias_map and alias_map[c] in self.colors_dict:
            return alias_map[c]

        # Substring / keyword matching (e.g. 'vintage_cream' -> 'cream', 'soft_ivory' -> 'ivory')
        for key in sorted(self.colors_dict.keys(), key=len, reverse=True):
            if key in c:
                return key

        return c

    def get_color_lab(self, color_name: str) -> Optional[Tuple[float, float, float]]:
        """Returns the pre-cached CIELAB (L*, a*, b*) coordinate for a color."""
        norm = self.normalize_color_name(color_name)
        return self.lab_cache.get(norm)

    def get_color_family(self, color_name: str) -> Optional[str]:
        """Returns the color family (e.g. 'white', 'blue', 'neutral')."""
        norm = self.normalize_color_name(color_name)
        info = self.colors_dict.get(norm)
        return info.get("family") if info else None

    def compare_colors(self, color1: str, color2: str) -> ColorComparisonResult:
        """Performs perceptual color difference calculation between two color names.
        
        Gracefully handles unknown color labels without crashing.
        """
        c1_norm = self.normalize_color_name(color1)
        c2_norm = self.normalize_color_name(color2)

        # Exact normalized string match
        if c1_norm == c2_norm and c1_norm != "unknown":
            fam = self.get_color_family(c1_norm)
            return ColorComparisonResult(
                color1=c1_norm,
                color2=c2_norm,
                delta_e=0.0,
                similarity_score=1.0,
                family1=fam,
                family2=fam,
                is_same_family=True,
                explanation=f"Exact color match: both garments are {c1_norm}."
            )

        lab1 = self.get_color_lab(c1_norm)
        lab2 = self.get_color_lab(c2_norm)

        # Graceful handling when one or both colors are unknown
        if lab1 is None or lab2 is None:
            unknowns = []
            if lab1 is None:
                unknowns.append(str(color1 if color1 is not None else "unknown"))
            if lab2 is None:
                unknowns.append(str(color2 if color2 is not None else "unknown"))
            
            # If both are non-empty and raw names match exactly
            s1 = (color1 or "").lower().strip()
            s2 = (color2 or "").lower().strip()
            if s1 and s2 and s1 == s2:
                return ColorComparisonResult(
                    color1=c1_norm,
                    color2=c2_norm,
                    delta_e=0.0,
                    similarity_score=1.0,
                    family1=None,
                    family2=None,
                    is_same_family=True,
                    explanation=f"Exact string match for custom color '{color1}'."
                )

            return ColorComparisonResult(
                color1=c1_norm,
                color2=c2_norm,
                delta_e=80.0,
                similarity_score=0.20,
                family1=self.get_color_family(c1_norm),
                family2=self.get_color_family(c2_norm),
                is_same_family=False,
                explanation=f"Unrecognized color label(s) ({', '.join(unknowns)}); assigned default neutral baseline."
            )

        # Perceptual CIEDE2000 Delta E
        d_e = ciede2000(lab1, lab2)
        fam1 = self.get_color_family(c1_norm)
        fam2 = self.get_color_family(c2_norm)
        is_same_fam = (fam1 == fam2 and fam1 is not None)
        sim = delta_e_to_similarity(d_e, same_family=is_same_fam)

        # Formulate human-readable explanation
        if d_e <= 3.0:
            rel_desc = "Nearly indistinguishable / interchangeable shade"
        elif d_e <= 8.0:
            rel_desc = "Closely related tint/shade in the same tonal family"
        elif d_e <= 20.0:
            rel_desc = "Related shade with noticeable tonal variation"
        elif d_e <= 50.0:
            rel_desc = "Distinct color with noticeable contrast (complementary)"
        else:
            rel_desc = "High-contrast distinct color"

        explanation = (
            f"{rel_desc}: '{c1_norm}' vs '{c2_norm}' (Delta E: {d_e:.2f}, "
            f"perceptual similarity: {sim*100:.1f}%)."
        )

        return ColorComparisonResult(
            color1=c1_norm,
            color2=c2_norm,
            delta_e=round(d_e, 2),
            similarity_score=sim,
            family1=fam1,
            family2=fam2,
            is_same_family=is_same_fam,
            explanation=explanation
        )

    def get_color_similarity(self, color1: str, color2: str) -> float:
        """Returns the normalized color similarity score in [0.0, 1.0]."""
        return self.compare_colors(color1, color2).similarity_score


# =====================================================================
# Module Convenience Functions
# =====================================================================

def compute_color_similarity(color1: str, color2: str) -> float:
    """Convenience function returning perceptual similarity score in [0.0, 1.0]."""
    return ColorSimilarityService.get_instance().get_color_similarity(color1, color2)


def compare_colors(color1: str, color2: str) -> ColorComparisonResult:
    """Convenience function returning full comparison report."""
    return ColorSimilarityService.get_instance().compare_colors(color1, color2)
