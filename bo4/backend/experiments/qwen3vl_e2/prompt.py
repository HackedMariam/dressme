"""Prompt E2 : définitions de la taxonomie, règles et schéma JSON (fixés a priori)."""

import hashlib
import json

from experiments.qwen3vl_e2.schema import ollama_format_schema
from experiments.qwen3vl_e2.taxonomy import DIMENSIONS, RULES

PROMPT_VERSION = "e2-prompt/1"


def system_prompt():
    lines = [
        "You annotate a single garment from a product photo.",
        "Fill every field of the JSON object using exactly one allowed value per field.",
        "",
        "Fields:",
    ]
    for name, spec in DIMENSIONS.items():
        lines.append(f"- {name}: {spec['question']} Allowed: {', '.join(spec['values'])}.")
    lines += ["", "Rules:"] + [f"- {rule}" for rule in RULES]
    lines += ["", "Return only JSON matching this schema:", json.dumps(ollama_format_schema(), sort_keys=True)]
    return "\n".join(lines)


USER_PROMPT = "Describe the garment in the image using the JSON schema."


def build_messages(image_b64):
    return [
        {"role": "system", "content": system_prompt()},
        {"role": "user", "content": USER_PROMPT, "images": [image_b64]},
    ]


def prompt_fingerprint():
    payload = json.dumps({"version": PROMPT_VERSION, "system": system_prompt(), "user": USER_PROMPT})
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
