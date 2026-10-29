"""Prompt E2 version 3 : e2-prompt/2 + deux consignes ciblées.

Constat sur output_prompt_v2 : le cardigan multicolore (0793493001) boucle sur
primary_color (« the largest areas are the patterned sections, but the
color that… ») sans jamais choisir `multicolor` ; les deux cardigans restent
classés `jacket`.

Ajouts (une seule intention : trancher plutôt que boucler) :
- règle explicite pour primary_color (couleur dominante, multicolor, détails) ;
- distinction cardigan / jacket avec les seules valeurs de la taxonomie.

v1, v2, la taxonomie et le schéma ne sont pas modifiés ; v3 réutilise le texte
de v2 et ne remplace que la consigne de catégorie.
"""

import hashlib
import json

from experiments.qwen3vl_e2 import prompt_v2
from experiments.qwen3vl_e2.taxonomy import DIMENSIONS, RULES

PROMPT_VERSION = "e2-prompt/3"

PATTERN_GUIDE = list(prompt_v2.PATTERN_GUIDE)
COLOUR_GUIDE = [
    "If one colour clearly covers most of the garment, choose that colour.",
    "If two or more colours each cover large areas and none clearly dominates (for example an all-over "
    "multicolour pattern), choose multicolor.",
    "Ignore small details (trims, patches, buttons, zips, small logos) when choosing primary_color.",
    "If still unsure, choose the best value, lower certainty and move on; do not compare areas again.",
]
CATEGORY_GUIDE = [
    "cardigan: a knitted top layer (visible knit or soft knit-like fabric) that opens at the front with "
    "buttons or a zip.",
    "jacket: a top layer that opens at the front, made of woven, technical, denim, leather-like or padded "
    "fabric (not knitted).",
    "blazer: a tailored jacket with lapels. hoodie: has a hood and sweatshirt fabric. coat: long outerwear.",
    "If unsure between cardigan and jacket, look at the fabric: knitted means cardigan, otherwise jacket.",
]
# Consignes de décision de v2, sans sa phrase de catégorie (remplacée par CATEGORY_GUIDE).
DECISION_RULES = [rule for rule in prompt_v2.DECISION_RULES if not rule.startswith("For category")]
DECISION_RULES.insert(1, "For category, choose the most specific allowed value (a shirt with a collar and "
                         "buttons is shirt_blouse, not top).")


def system_prompt():
    lines = [
        "You annotate a single garment from a product photo.",
        "Return one JSON object with exactly these fields, one allowed value per field.",
        "",
        "Fields:",
    ]
    for name, spec in DIMENSIONS.items():
        lines.append(f"- {name}: {spec['question']} Allowed: {', '.join(spec['values'])}.")
    lines += ["", "Rules:"] + [f"- {rule}" for rule in RULES]
    lines += ["", "How to choose category among top layers:"] + [f"- {rule}" for rule in CATEGORY_GUIDE]
    lines += ["", "How to choose primary_color:"] + [f"- {rule}" for rule in COLOUR_GUIDE]
    lines += ["", "How to choose pattern:"] + [f"- {rule}" for rule in PATTERN_GUIDE]
    lines += ["", "How to decide:"] + [f"- {rule}" for rule in DECISION_RULES]
    lines += ["", "Answer with the JSON object only."]
    return "\n".join(lines)


USER_PROMPT = prompt_v2.USER_PROMPT


def build_messages(image_b64):
    return [
        {"role": "system", "content": system_prompt()},
        {"role": "user", "content": USER_PROMPT, "images": [image_b64]},
    ]


def prompt_fingerprint():
    payload = json.dumps({"version": PROMPT_VERSION, "system": system_prompt(), "user": USER_PROMPT})
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
