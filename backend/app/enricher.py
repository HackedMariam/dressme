"""LLM step (OpenAI GPT-4): turn raw model output into a classified wardrobe item.

The YOLO model knows *what* the item is and the pixels give the colour.
It can't know occasion, style, season, pattern or material — GPT-4 looks at the
detector result (and the cut-out image) and classifies the item on those axes,
with its own confidence per field so the UI can ask the user to review
uncertain items.

The response is constrained with a strict JSON schema (structured outputs) and
then sanitised again here, so a value outside the vocabularies can never reach
the database.
"""
from __future__ import annotations

import base64
import json
import logging

from . import config
from .colors import COLOR_NAMES
from .taxonomy import (CLASS_TO_GROUP, COLOR_FAMILIES, MODEL_CLASSES, OCCASIONS, PATTERNS,
                       SEASONS, STYLES)

log = logging.getLogger("dressme.enricher")

CONFIDENCE_KEYS = ("category", "color", "pattern", "season", "style", "occasion", "material")


def _s(description: str, **kw) -> dict:
    return {"type": "string", "description": description, **kw}


# Strict mode: every property required, no additionalProperties, no min/max keywords
# (bounds are enforced in sanitize()).
ITEM_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "name": _s("Short shop-style name, 2-4 words, e.g. 'Sand Linen Midi Dress'."),
        "category": _s("Keep the detector's category unless the image clearly shows otherwise.",
                       enum=MODEL_CLASSES),
        "category_changed_reason": _s("Empty string if you kept the detector's category."),
        "subcategory": _s("Precise type, e.g. 'midi slip dress', 'chelsea boots', 'crew-neck t-shirt'."),
        "color_name": _s("Main colour, chosen from the palette. Start from the measured colours.",
                         enum=COLOR_NAMES),
        "color_family": _s("Colour family used to match outfits.", enum=COLOR_FAMILIES),
        "pattern": _s("Surface pattern.", enum=PATTERNS),
        "material": _s("Most likely fabric, e.g. 'cotton jersey', 'denim', 'wool knit', 'leather'."),
        "seasons": {"type": "array", "description": "1 to 4 seasons.",
                    "items": {"type": "string", "enum": SEASONS}},
        "style": _s("Dominant style.", enum=STYLES),
        "occasions": {"type": "array", "description": "1 to 4 occasions, most suitable first.",
                      "items": {"type": "string", "enum": OCCASIONS}},
        "formality": {"type": "integer", "description": "1 = loungewear ... 5 = black tie."},
        "warmth": {"type": "integer", "description": "1 = very light ... 5 = very warm."},
        "description": _s("2-3 natural sentences describing the item for the user's wardrobe."),
        "styling_tips": {"type": "array", "description": "2 or 3 short, concrete tips.",
                         "items": {"type": "string"}},
        "tags": {"type": "array", "description": "Up to 8 lowercase search tags.",
                 "items": {"type": "string"}},
        "confidence": {
            "type": "object",
            "description": "Your own confidence between 0 and 1 for each classification.",
            "additionalProperties": False,
            "properties": {k: {"type": "number"} for k in CONFIDENCE_KEYS},
            "required": list(CONFIDENCE_KEYS),
        },
    },
    "required": ["name", "category", "category_changed_reason", "subcategory", "color_name",
                 "color_family", "pattern", "material", "seasons", "style", "occasions", "formality",
                 "warmth", "description", "styling_tips", "tags", "confidence"],
}

SYSTEM = (
    "You are the cataloguing assistant of DressMe, a personal wardrobe app. "
    "A segmentation model has detected a clothing item and measured its colours from the pixels. "
    "Classify it into a clean wardrobe entry: occasion, style, colour, season, pattern, material.\n"
    "Rules:\n"
    "- The detector's category is usually right. Change it only if the image clearly shows another "
    "category, and explain why in category_changed_reason.\n"
    "- The measured colours come from the actual garment pixels: pick color_name from the palette "
    "closest to the dominant measured colour, unless the image clearly shows the measurement is off "
    "(shadows, reflections).\n"
    "- Occasions: list only those where the item would genuinely be worn, most suitable first.\n"
    "- Be honest in your confidence scores: if the image is ambiguous, give a low score instead of "
    "guessing confidently.\n"
    "- Write in English, concise and friendly."
)


def enrich(detection: dict, cutout_png: bytes | None) -> dict:
    """Return classified fields. Falls back to rules if no API key or on error."""
    if not config.OPENAI_API_KEY:
        return _fallback(detection, reason="no OPENAI_API_KEY set")
    try:
        raw = _call_openai(detection, cutout_png)
        out = sanitize(raw, detection)
        out["source"] = f"llm:{config.LLM_MODEL}"
        return out
    except Exception as e:  # never block the upload because of the LLM
        log.exception("LLM enrichment failed")
        return _fallback(detection, reason=f"LLM error: {type(e).__name__}")


def _call_openai(detection: dict, cutout_png: bytes | None) -> dict:
    from openai import OpenAI

    client = OpenAI(api_key=config.OPENAI_API_KEY, timeout=config.LLM_TIMEOUT, max_retries=2)
    facts = {
        "detected_category": detection["category"],
        "detector_confidence": detection["confidence"],
        "other_categories_considered": detection.get("alternatives", []),
        "measured_colors": detection.get("colors", []),
    }
    content: list[dict] = [{"type": "text", "text":
                            "Detector output (JSON):\n" + json.dumps(facts, indent=2) +
                            "\n\nThe image (if any) is the item cut out from its background."}]
    if cutout_png and config.LLM_SEND_IMAGE:
        content.append({"type": "image_url", "image_url": {
            "url": "data:image/png;base64," + base64.b64encode(cutout_png).decode(),
            "detail": config.LLM_IMAGE_DETAIL}})

    resp = client.chat.completions.create(
        model=config.LLM_MODEL,
        temperature=0.2,
        max_completion_tokens=1200,
        messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": content}],
        response_format={"type": "json_schema", "json_schema": {
            "name": "wardrobe_item", "strict": True, "schema": ITEM_SCHEMA}},
    )
    choice = resp.choices[0]
    if getattr(choice.message, "refusal", None):
        raise RuntimeError(f"model refused: {choice.message.refusal}")
    if choice.finish_reason == "length":
        raise RuntimeError("response truncated")
    return json.loads(choice.message.content)


# ---------------------------------------------------------------------------
def _clamp(v, lo, hi, default):
    try:
        return max(lo, min(hi, type(default)(v)))
    except (TypeError, ValueError):
        return default


def _pick(v, allowed: list[str], default: str) -> str:
    return v if v in allowed else default


def _pick_many(v, allowed: list[str], default: list[str], limit: int) -> list[str]:
    out = []
    for x in v if isinstance(v, list) else []:
        if x in allowed and x not in out:
            out.append(x)
    return out[:limit] or default


def _texts(v, limit: int, lower: bool = False) -> list[str]:
    out = []
    for x in v if isinstance(v, list) else []:
        if isinstance(x, str) and x.strip():
            x = x.strip()[:120]
            x = x.lower() if lower else x
            if x not in out:
                out.append(x)
    return out[:limit]


def sanitize(raw: dict, det: dict) -> dict:
    """Coerce an LLM answer into valid values (enums, bounds, lengths)."""
    base = _fallback(det, reason="")
    measured = (det.get("colors") or [{"name": base["color_name"]}])[0]["name"]
    conf_in = raw.get("confidence") if isinstance(raw.get("confidence"), dict) else {}
    category = _pick(raw.get("category"), MODEL_CLASSES, det["category"])
    return {
        "name": (str(raw.get("name") or "").strip()[:60]) or base["name"],
        "category": category,
        "category_changed_reason": str(raw.get("category_changed_reason") or "").strip()[:300]
        if category != det["category"] else "",
        "subcategory": (str(raw.get("subcategory") or "").strip()[:60]) or category,
        "color_name": _pick(raw.get("color_name"), COLOR_NAMES, measured),
        "color_family": _pick(raw.get("color_family"), COLOR_FAMILIES, base["color_family"]),
        "pattern": _pick(raw.get("pattern"), PATTERNS, "solid"),
        "material": (str(raw.get("material") or "").strip()[:60]) or base["material"],
        "seasons": _pick_many(raw.get("seasons"), SEASONS, base["seasons"], 4),
        "style": _pick(raw.get("style"), STYLES, base["style"]),
        "occasions": _pick_many(raw.get("occasions"), OCCASIONS, base["occasions"], 4),
        "formality": _clamp(raw.get("formality"), 1, 5, base["formality"]),
        "warmth": _clamp(raw.get("warmth"), 1, 5, base["warmth"]),
        "description": (str(raw.get("description") or "").strip()[:600]) or base["description"],
        "styling_tips": _texts(raw.get("styling_tips"), 3) or base["styling_tips"],
        "tags": _texts(raw.get("tags"), 8, lower=True),
        "confidence": {k: round(_clamp(conf_in.get(k), 0.0, 1.0, 0.5), 3) for k in CONFIDENCE_KEYS},
    }


# ---------------------------------------------------------------------------
# Rule-based fallback, so the app still works offline / without a key.
_RULES = {
    "top": (["spring", "summer"], "casual", ["everyday"], 2, 2, "cotton"),
    "sweater": (["autumn", "winter"], "casual", ["everyday", "work"], 2, 4, "knit"),
    "jacket": (["spring", "autumn"], "classic", ["everyday", "work"], 3, 3, "cotton blend"),
    "vest": (["spring", "autumn"], "classic", ["work", "everyday"], 3, 2, "wool blend"),
    "pants": (["spring", "summer", "autumn", "winter"], "casual", ["everyday", "work"], 2, 3, "cotton"),
    "shorts": (["summer"], "casual", ["everyday", "beach"], 1, 1, "cotton"),
    "skirt": (["spring", "summer"], "elegant", ["everyday", "work"], 3, 2, "cotton blend"),
    "dress": (["spring", "summer"], "elegant", ["party", "date night"], 3, 2, "viscose"),
    "shoe": (["spring", "summer", "autumn", "winter"], "casual", ["everyday"], 2, 2, "leather"),
    "bag": (["spring", "summer", "autumn", "winter"], "classic", ["everyday", "work"], 3, 1, "leather"),
    "scarf": (["autumn", "winter"], "classic", ["everyday", "outdoor"], 2, 4, "wool"),
    "glove": (["winter"], "classic", ["outdoor"], 2, 5, "wool"),
    "hat": (["summer", "winter"], "casual", ["outdoor"], 2, 2, "cotton"),
}

_FAMILY = {
    "neutral": {"black", "charcoal", "grey", "light grey", "white", "cream", "beige", "navy"},
    "earth": {"camel", "tan", "brown", "chocolate", "khaki", "olive", "forest green"},
    "pastel": {"mint", "light blue", "lavender", "pink"},
    "warm": {"burgundy", "red", "coral", "orange", "mustard", "yellow"},
    "cool": {"green", "teal", "blue", "denim blue", "purple"},
    "bright": {"hot pink"},
    "metallic": {"gold", "silver"},
}


def color_family_of(name: str) -> str:
    return next((f for f, names in _FAMILY.items() if name in names), "neutral")


def fallback_enrich(detection: dict) -> dict:
    """Instant, rule-based classification (no GPT-4 call) for the live-scan fast path.
    The item is saved right away with this; call enrich() via /reclassify afterwards
    to replace it with the full LLM classification.
    """
    return _fallback(detection, reason="fast capture - full classification pending")


def _fallback(det: dict, reason: str) -> dict:
    cat = det["category"]
    seasons, style, occ, formality, warmth, material = _RULES.get(
        cat, (["spring", "summer", "autumn", "winter"], "casual", ["everyday"], 2, 2, "unknown"))
    color = (det.get("colors") or [{"name": "grey"}])[0]["name"]
    if color not in COLOR_NAMES:
        color = "grey"
    return {
        "name": f"{color.title()} {cat.title()}", "category": cat, "category_changed_reason": "",
        "subcategory": cat, "color_name": color, "color_family": color_family_of(color),
        "pattern": "solid", "material": material, "seasons": seasons, "style": style,
        "occasions": occ, "formality": formality, "warmth": warmth,
        "description": f"A {color} {cat} from your wardrobe.",
        "styling_tips": ["Pair with neutral basics.", "Add one accent accessory."],
        "tags": [cat, color, CLASS_TO_GROUP.get(cat, "").lower()],
        # rule-based guesses: neutral 0.5 so only the detector's confidence decides "Needs review"
        "confidence": {"category": det["confidence"], "color": 0.8, "pattern": 0.5, "season": 0.5,
                       "style": 0.5, "occasion": 0.5, "material": 0.3},
        "source": f"rules ({reason})",
    }
