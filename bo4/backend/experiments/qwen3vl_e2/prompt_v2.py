"""Prompt E2 version 2 : mêmes champs, mêmes valeurs, mêmes règles que v1, plus
des consignes contre les boucles de raisonnement observées.

Constats sur output_optim_confirm (prompt v1) :
- gilet blanc à empiècement bleu : oscillation sans fin entre `solid` et un
  motif (« a single-colour surface is solid » ne couvre pas un petit empiècement) ;
- catégories voisines (shirt_blouse / top, jacket / cardigan) rediscutées ;
- double passe de vérification (« Yes, that seems right… (correct) ») ;
- lot de plusieurs articles sur une photo sans consigne.

v1 (prompt.py), la taxonomie (taxonomy.py) et le schéma (schema.py) ne sont
pas modifiés ; le schéma reste imposé par `format`, il n'est plus recopié dans
le texte du prompt.
"""

import hashlib
import json

from experiments.qwen3vl_e2.taxonomy import DIMENSIONS, RULES

PROMPT_VERSION = "e2-prompt/2"

# Consignes ajoutées par v2 (les règles de la taxonomie restent toutes présentes).
PATTERN_GUIDE = [
    "solid: one colour covers almost all of the garment. Small contrasting areas (a patch, pocket, collar, "
    "cuffs, trim, piping, zip, buttons, a small logo or label) do NOT make a pattern: keep pattern=solid.",
    "striped: repeated parallel lines across the fabric. dotted: repeated small dots or spots. "
    "checked: lines crossing in a grid (checks, plaid, gingham).",
    "floral: flowers or leaves. animal: animal-skin imitation (leopard, zebra, snake).",
    "graphic_print: a picture, text or large logo printed as a motif (for example a front print).",
    "abstract_geometric: repeated non-floral shapes all over the fabric.",
    "Colour blocking (two or more LARGE areas of different solid colours, none of them a small detail): "
    "other_pattern. Any other repeated motif: other_pattern.",
]
DECISION_RULES = [
    "If several items are shown (for example a multipack), describe them as one garment using the main item.",
    "For category, choose the most specific allowed value (a shirt with a collar and buttons is shirt_blouse, "
    "not top; a buttoned knitted jacket is cardigan).",
    "Decide each field ONCE. If two values seem plausible, pick the one that fits best, set certainty to "
    "medium or low, and move on. Do not reconsider a field you have already decided.",
    "Do not re-check the whole answer at the end. Keep your reasoning to about one short line per field.",
    "Never invent details that cannot be seen in the photo; use not_visible where it is allowed.",
]


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
    lines += ["", "How to choose pattern:"] + [f"- {rule}" for rule in PATTERN_GUIDE]
    lines += ["", "How to decide:"] + [f"- {rule}" for rule in DECISION_RULES]
    lines += ["", "Answer with the JSON object only."]
    return "\n".join(lines)


USER_PROMPT = "Describe the garment in the image. Decide quickly and answer with the JSON object only."


def build_messages(image_b64):
    return [
        {"role": "system", "content": system_prompt()},
        {"role": "user", "content": USER_PROMPT, "images": [image_b64]},
    ]


def prompt_fingerprint():
    payload = json.dumps({"version": PROMPT_VERSION, "system": system_prompt(), "user": USER_PROMPT})
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
