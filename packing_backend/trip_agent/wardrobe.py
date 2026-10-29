"""Wardrobe/compatibility providers.

The provider interface is intentionally small so a real user wardrobe can be
plugged in later without touching the agent or optimizer contract.
"""

from __future__ import annotations

from itertools import combinations
import re
from typing import Any, Protocol

import pandas as pd

from .. import optimizer

REQUIRED_WARDROBE_COLUMNS = [
    "item_id",
    "name",
    "category",
    "item_type",
    "color",
    "style",
    "season",
    "warmth_level",
    "water_resistance",
    "weight_g",
    "versatility",
    "formality_level",
    "clean_items_available",
    "image_url",
    "description",
]


class WardrobeProvider(Protocol):
    name: str

    def load(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Return (wardrobe, compatibility) and validate their schema."""

    def items_payload(self, category: str | None = None, style: str | None = None,
                      limit: int = 50) -> dict[str, Any]: ...


class BO1WardrobeProvider:
    """A snapshot of the authenticated user's BO1 items, adapted for CP-SAT."""

    name = "bo1"
    CATEGORIES = {"top": "top", "sweater": "top", "vest": "top", "pants": "bottom",
                  "shorts": "bottom", "skirt": "bottom", "dress": "dress",
                  "jacket": "outerwear", "shoe": "shoes"}
    WEIGHTS = {"top": 250, "bottom": 450, "dress": 400, "outerwear": 800,
               "shoes": 700, "accessory": 150}

    def __init__(self, items: list[dict[str, Any]]) -> None:
        rows = []
        seen = set()
        for item in items:
            item_id = str(item.get("id") or "")
            if not item_id or item_id in seen:
                continue
            seen.add(item_id)
            source_category = str(item.get("category") or "").lower()
            category = self.CATEGORIES.get(source_category, "accessory")
            text = " ".join(str(item.get(k) or "") for k in ("name", "subcategory", "description")).lower()
            kind = next((t for t in ("raincoat", "parka", "cardigan", "sweater", "hoodie", "fleece",
                                      "sandals", "sneakers", "boots", "sunglasses", "hat", "jacket", "coat")
                         if t in text), source_category)
            if category == "outerwear":
                tags = item.get("tags") or []
                if isinstance(tags, str):
                    tags = [tags]
                rain_text = " ".join([text, str(item.get("material") or ""),
                                      *(str(tag) for tag in tags)]).lower()
                explicitly_not_waterproof = re.search(
                    r"\b(?:not|non|pas)[\s-]+(?:a\s+)?(?:waterproof|rainproof|imperm[eé]able|[eé]tanche)\b",
                    rain_text,
                )
                rainwear = re.search(
                    r"\b(?:waterproof|rainproof|rain[ -]?(?:coat|jacket)|imperm[eé]able|[eé]tanche)\b",
                    rain_text,
                )
                if explicitly_not_waterproof and kind == "raincoat":
                    kind = "jacket"
                elif rainwear and not explicitly_not_waterproof:
                    kind = "raincoat"
            rows.append({"item_id": item_id, "name": item.get("name") or source_category or "Item",
                         "category": category, "item_type": kind, "color": item.get("color_name") or "",
                         "style": item.get("style") or "", "season": ",".join(item.get("seasons") or []),
                         "warmth_level": item.get("warmth") or 0, "water_resistance": 0,
                         "weight_g": self.WEIGHTS[category], "versatility": 1,
                         "formality_level": item.get("formality") or 0, "clean_items_available": True,
                         "image_url": item.get("cutout_url") or item.get("image_url"),
                         "description": item.get("description") or "", "weight_estimated": True,
                         "needs_review": bool(item.get("needs_review"))})
        self._wardrobe = pd.DataFrame(rows, columns=REQUIRED_WARDROBE_COLUMNS + ["weight_estimated", "needs_review"])
        pairs = []
        for a, b in combinations(rows, 2):
            # A heuristic, not a measured compatibility score. Unknown attributes stay neutral.
            score = 0.5
            if a["color"] and b["color"] and a["color"].lower() == b["color"].lower():
                score += 0.1
            if a["style"] and b["style"] and a["style"].lower() == b["style"].lower():
                score += 0.2
            pairs.append({"item_id_a": a["item_id"], "item_id_b": b["item_id"], "compatibility_score": score})
        self._compatibility = pd.DataFrame(pairs, columns=["item_id_a", "item_id_b", "compatibility_score"])

    def load(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        return self._wardrobe, self._compatibility

    def items_payload(self, category: str | None = None, style: str | None = None,
                      limit: int = 50) -> dict[str, Any]:
        frame = self._wardrobe
        if category:
            frame = frame[frame["category"].str.lower() == category.lower()]
        if style:
            frame = frame[frame["style"].str.lower() == style.lower()]
        return {"provider": self.name, "total_items": len(self._wardrobe), "matched_items": len(frame),
                "items": frame.head(limit).to_dict("records"),
                "by_category": self._wardrobe["category"].value_counts().to_dict(),
                "available_roles": {}, "filters": {"category": category, "style": style, "limit": limit}}


class SyntheticWardrobeProvider:
    """CSV-backed provider using the existing synthetic DressMe dataset."""

    name = "synthetic_csv"

    def __init__(self) -> None:
        self._wardrobe: pd.DataFrame | None = None
        self._compatibility: pd.DataFrame | None = None

    def load(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        if self._wardrobe is None or self._compatibility is None:
            # Reuse the optimizer's existing validation and type coercion.
            wardrobe, _trips, compatibility = optimizer.load_data()
            self._wardrobe = wardrobe
            self._compatibility = compatibility
        return self._wardrobe, self._compatibility

    def items_payload(
        self,
        category: str | None = None,
        style: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        wardrobe, _ = self.load()
        filtered = wardrobe
        if category:
            filtered = filtered[
                filtered["category"].astype(str).str.lower() == category.lower()
            ]
        if style:
            filtered = filtered[
                filtered["style"].astype(str).str.lower() == style.lower()
            ]

        item_roles = optimizer.build_item_roles(wardrobe)
        role_counts: dict[str, int] = {}
        for roles in item_roles.values():
            for role in roles:
                role_counts[role] = role_counts.get(role, 0) + 1

        by_category = (
            wardrobe["category"].astype(str).value_counts().sort_index().to_dict()
        )
        records = filtered.head(limit).to_dict("records")
        compact_items = [
            {
                "item_id": str(item["item_id"]),
                "name": str(item["name"]),
                "category": str(item["category"]),
                "item_type": str(item["item_type"]),
                "style": str(item["style"]),
                "weight_g": int(item["weight_g"]),
                "water_resistance": item.get("water_resistance"),
                "warmth_level": item.get("warmth_level"),
            }
            for item in records
        ]

        return {
            "provider": self.name,
            "total_items": int(len(wardrobe)),
            "matched_items": int(len(filtered)),
            "by_category": {str(k): int(v) for k, v in by_category.items()},
            "available_roles": role_counts,
            "items": compact_items,
            "filters": {"category": category, "style": style, "limit": limit},
        }
