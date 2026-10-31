"""Adaptateur BO1 (API réelle, branche `wardrobe`) -> format attendu par le moteur BO4.

Ce module NE MODIFIE NI BO1 NI outfit_engine.py. Il :
  1. lit la garde-robe via l'API REST de BO1 (GET /api/items) ou un fichier JSON au même format ;
  2. convertit chaque vêtement BO1 vers les champs lus par outfit_engine.recommend_outfits().

Champs lus par le moteur BO4 : id, name, category, color, style, warmth, sleeve_length.
Les autres champs BO1 utiles à l'agent (seasons, occasions, formality...) sont conservés
tels quels : le moteur les ignore.

Toutes les correspondances ci-dessous sont des CHOIX DE CONCEPTION documentés, pas des
vérités issues d'un modèle. Elles sont regroupées dans des dictionnaires pour être
faciles à relire, à justifier à l'oral et à modifier.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

# 127.0.0.1 et non localhost : sous Windows, localhost essaie d'abord IPv6 (::1), refusé au bout de ~2 s.
BO1_API_URL = os.environ.get("BO1_API_URL", "http://127.0.0.1:8000")
BO1_TOKEN = os.environ.get("BO1_TOKEN", "")  # vide en mode dev BO1 (utilisateur "local")


class BO1UnavailableError(RuntimeError):
    """BO1 ne répond pas ou renvoie une réponse inattendue."""


# --------------------------------------------------------------------------------------
# 1. Catégories
# --------------------------------------------------------------------------------------
# Classes BO1 (taxonomy.MODEL_CLASSES) qui sont des vêtements portés en tenue.
# Les 12 autres classes (shoe, bag, hat, belt, watch, ...) ne sont pas gérées par BO4.
BO1_GARMENT_CLASSES = {"top", "sweater", "vest", "jacket", "pants", "shorts", "skirt", "dress"}

# `vest` est dans le groupe "Tops" de BO1 mais inconnu de BO4 : on le traite comme un haut.
BASE_CATEGORY = {"vest": "top"}

# Raffinement par mots-clés trouvés dans `subcategory` ou `name` de BO1.
# L'ordre compte : "t-shirt" et "sweatshirt" sont testés avant "shirt".
CATEGORY_REFINEMENT: dict[str, list[tuple[str, str]]] = {
    "top": [
        (r"\bt[\s-]?shirt\b|\btee\b", "t_shirt"),
        (r"\bhoodie\b|\bsweatshirt\b", "hoodie"),
        (r"\bblouse\b", "blouse"),
        (r"\bshirt\b", "shirt"),
    ],
    "sweater": [
        (r"\bcardigan\b", "cardigan"),
        (r"\bhoodie\b|\bsweatshirt\b", "hoodie"),
    ],
    "jacket": [
        (r"\bblazer\b", "blazer"),
        (r"\bcardigan\b", "cardigan"),
        (r"\bcoat\b|\btrench\b|\bparka\b|\bovercoat\b", "coat"),
    ],
    "pants": [
        (r"\bjeans?\b", "jeans"),
        (r"\btrousers?\b|\bchinos?\b", "trousers"),
    ],
}

# --------------------------------------------------------------------------------------
# 2. Couleurs : `color_name` BO1 (33 noms avec espaces) -> `color` BO4
# --------------------------------------------------------------------------------------
# Seules les couleurs que BO4 ne classe pas correctement sont renommées
# (rapport d'intégration §12.2). Les autres passent telles quelles : le moteur
# convertit déjà les espaces en "_" ("light grey" -> "light_grey").
COLOR_MAP = {
    "charcoal": "dark_grey",       # neutre dans BO1, inconnu dans BO4
    "chocolate": "brown",
    "forest green": "dark_green",
    "mint": "light_green",
    "hot pink": "pink",
}

# --------------------------------------------------------------------------------------
# 3. Styles : 10 styles BO1 -> 3 styles BO4 (casual, smart_casual, formal)
# --------------------------------------------------------------------------------------
STYLE_MAP = {
    "casual": "casual",
    "sporty": "casual",
    "streetwear": "casual",
    "bohemian": "casual",
    "classic": "smart_casual",
    "minimalist": "smart_casual",
    "romantic": "smart_casual",
    "business": "formal",
    "elegant": "formal",
    "formal": "formal",
}

# --------------------------------------------------------------------------------------
# 4. Chaleur : entier BO1 1..5 -> light / medium / heavy
# --------------------------------------------------------------------------------------
WARMTH_MAP = {1: "light", 2: "light", 3: "medium", 4: "heavy", 5: "heavy"}

# --------------------------------------------------------------------------------------
# 5. Manches : BO1 n'a pas de champ dédié ; on cherche des mots-clés dans son texte.
# --------------------------------------------------------------------------------------
SLEEVE_PATTERNS = [
    (r"sleeveless|strapless|\btank\b|camisole|spaghetti strap", "sleeveless"),
    (r"short[\s-]sleeve", "short"),
    (r"3/4[\s-]sleeve|three[\s-]quarter", "three_quarter"),
    (r"long[\s-]sleeve", "long"),
]

# Champs BO1 conservés pour l'agent (ignorés par le moteur BO4).
PASSTHROUGH_FIELDS = (
    "seasons", "occasions", "formality", "pattern", "material", "color_family",
    "color_hex", "subcategory", "needs_review", "status", "image_url", "cutout_url",
)


# --------------------------------------------------------------------------------------
# Lecture de BO1
# --------------------------------------------------------------------------------------
def fetch_bo1_items(base_url: str | None = None, token: str | None = None,
                    timeout: float = 10.0) -> list[dict]:
    """Appelle GET {base_url}/api/items et renvoie la liste brute des vêtements BO1."""
    base_url = (base_url or BO1_API_URL).rstrip("/")
    token = BO1_TOKEN if token is None else token
    request = urllib.request.Request(f"{base_url}/api/items", headers={"Accept": "application/json"})
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise BO1UnavailableError(f"BO1 a répondu HTTP {exc.code} sur /api/items") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise BO1UnavailableError(f"BO1 injoignable à {base_url} : {exc}") from exc
    except json.JSONDecodeError as exc:
        raise BO1UnavailableError("Réponse de BO1 non JSON") from exc
    if not isinstance(payload, list):
        raise BO1UnavailableError("Réponse de BO1 inattendue : une liste était attendue")
    return payload


def load_bo1_items_from_file(path: str | Path) -> list[dict]:
    """Lit un fichier JSON au format de GET /api/items (mode hors ligne / tests)."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Le fichier doit contenir une liste de vêtements BO1")
    return payload


# --------------------------------------------------------------------------------------
# Conversion
# --------------------------------------------------------------------------------------
def _text(item: dict, *fields: str) -> str:
    parts: list[str] = []
    for field in fields:
        value = item.get(field)
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, list):
            parts.extend(str(v) for v in value)
    return " ".join(parts).lower()


def map_category(item: dict) -> str | None:
    """Catégorie BO4, ou None si le vêtement n'est pas géré par BO4."""
    bo1_category = str(item.get("category") or "").lower().strip()
    if bo1_category not in BO1_GARMENT_CLASSES:
        return None
    base = BASE_CATEGORY.get(bo1_category, bo1_category)
    text = _text(item, "subcategory", "name")
    for pattern, refined in CATEGORY_REFINEMENT.get(base, []):
        if re.search(pattern, text):
            return refined
    return base


def map_color(color_name: Any) -> str:
    if not isinstance(color_name, str) or not color_name.strip():
        return "unknown"
    name = color_name.lower().strip()
    return COLOR_MAP.get(name, name)


def map_style(style: Any) -> str:
    if not isinstance(style, str):
        return "unknown"
    return STYLE_MAP.get(style.lower().strip(), "unknown")


def map_warmth(warmth: Any) -> str | None:
    if isinstance(warmth, bool) or not isinstance(warmth, (int, float)):
        return None
    return WARMTH_MAP.get(int(warmth))


def map_sleeve(item: dict, bo1_category: str) -> str:
    if bo1_category == "vest":
        return "sleeveless"
    text = _text(item, "subcategory", "name", "description", "tags")
    for pattern, value in SLEEVE_PATTERNS:
        if re.search(pattern, text):
            return value
    return "unknown"


def bo1_item_to_bo4(item: dict) -> dict | None:
    """Convertit un vêtement BO1 en vêtement BO4. Renvoie None s'il n'est pas utilisable."""
    category = map_category(item)
    if category is None or not item.get("id"):
        return None

    bo1_category = str(item.get("category")).lower().strip()
    notes: list[str] = []

    color = map_color(item.get("color_name"))
    if color == "unknown":
        notes.append("couleur absente dans BO1")

    style = map_style(item.get("style"))
    if style == "unknown":
        notes.append(f"style BO1 non reconnu : {item.get('style')!r}")

    converted: dict[str, Any] = {
        "id": str(item["id"]),
        "name": item.get("name") or category,
        "category": category,
        "color": color,
        "style": style,
        "sleeve_length": map_sleeve(item, bo1_category),
        "source": "bo1",
        "bo1_category": bo1_category,
        "bo1_style": item.get("style"),
        "bo1_warmth": item.get("warmth"),
    }

    warmth = map_warmth(item.get("warmth"))
    if warmth is not None:
        converted["warmth"] = warmth
    else:
        notes.append("chaleur absente : estimée par le moteur d'après la catégorie")

    for field in PASSTHROUGH_FIELDS:
        if field in item:
            converted[field] = item[field]

    converted["mapping_notes"] = notes
    return converted


def adapt_wardrobe(bo1_items: list[dict], include_needs_review: bool = True) -> tuple[list[dict], dict]:
    """Convertit toute la garde-robe et renvoie (vêtements BO4, rapport de conversion)."""
    wardrobe: list[dict] = []
    skipped: dict[str, list[str]] = {}
    for item in bo1_items:
        label = str(item.get("name") or item.get("id"))
        if not include_needs_review and item.get("needs_review"):
            skipped.setdefault("needs_review", []).append(label)
            continue
        converted = bo1_item_to_bo4(item)
        if converted is None:
            reason = f"catégorie non gérée par BO4 : {item.get('category')}"
            skipped.setdefault(reason, []).append(label)
            continue
        wardrobe.append(converted)
    report = {
        "received": len(bo1_items),
        "kept": len(wardrobe),
        "skipped": skipped,
    }
    return wardrobe, report


def load_wardrobe_from_bo1(base_url: str | None = None, token: str | None = None,
                           fallback_file: str | Path | None = None,
                           include_needs_review: bool = True) -> tuple[list[dict], dict]:
    """Point d'entrée pour l'agent : lit BO1 (API, sinon fichier de secours) puis convertit."""
    try:
        bo1_items = fetch_bo1_items(base_url, token)
        source = "bo1_api"
    except BO1UnavailableError:
        if fallback_file is None:
            raise
        bo1_items = load_bo1_items_from_file(fallback_file)
        source = f"fichier:{Path(fallback_file).name}"
    wardrobe, report = adapt_wardrobe(bo1_items, include_needs_review)
    report["source"] = source
    return wardrobe, report
