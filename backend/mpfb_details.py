"""Whitelisted MPFB detail targets for local body-shape optimization.

The manifest is generated from the MPFB target library and committed with the
backend, so the Blender scripts never accept arbitrary target names. Macro
controls stay in `main.validate_targets`; this module only handles the local
shape targets (torso, limbs, hips, stomach, ...).
"""

from __future__ import annotations

import json
from pathlib import Path

MANIFEST_PATH = Path(__file__).with_name("mpfb_targets.json")
MAX_DETAILS = 128


def _load_manifest() -> dict[str, list[str]]:
    with open(MANIFEST_PATH, "r", encoding="utf-8-sig") as f:
        data = json.load(f)
    return {
        str(category): sorted(str(name) for name in names)
        for category, names in data.items()
    }


DETAIL_CATEGORIES = _load_manifest()
ALLOWED_DETAILS = frozenset(name for names in DETAIL_CATEGORIES.values() for name in names)


def validate_details(details: dict[str, float]) -> dict[str, float]:
    if not isinstance(details, dict):
        raise ValueError("details must be an object of target name -> value")
    if len(details) > MAX_DETAILS:
        raise ValueError(f"at most {MAX_DETAILS} detail targets allowed")

    cleaned: dict[str, float] = {}
    for name, value in details.items():
        if name not in ALLOWED_DETAILS:
            raise ValueError(f"unsupported detail target '{name}'")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"detail target '{name}' must be a number")
        number = float(value)
        if not (0.0 <= number <= 1.0):
            raise ValueError(f"detail target '{name}' must be between 0.0 and 1.0")
        cleaned[name] = round(number, 4)
    return cleaned
