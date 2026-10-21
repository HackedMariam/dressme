"""Wardrobe/compatibility providers.

The provider interface is intentionally small so a real user wardrobe can be
plugged in later without touching the agent or optimizer contract.
"""

from __future__ import annotations

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
