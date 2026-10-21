"""Adapter around the existing deterministic OR-Tools optimizer."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd

from .. import optimizer
from .requirements import requirements_to_dataframe
from .schemas import (
    CapsuleDay,
    CapsuleTripInfo,
    DailyRequirement,
    OutfitItem,
    PackingChecklist,
    TripCapsule,
    TripDetails,
    WeatherData,
)


def run_optimization(
    wardrobe: pd.DataFrame,
    compatibility: pd.DataFrame,
    requirements: list[DailyRequirement],
    max_weight_g: int,
    max_candidates_per_day: int = 500,
    time_limit_seconds: int = 30,
    random_seed: int = 42,
) -> dict[str, Any]:
    if max_weight_g <= 0:
        raise ValueError("max_weight_g must be positive")
    frame = requirements_to_dataframe(requirements)
    return optimizer.optimize_packing(
        wardrobe=wardrobe,
        trips=frame,
        compatibility_df=compatibility,
        max_weight_g=max_weight_g,
        max_candidates_per_day=max_candidates_per_day,
        time_limit_seconds=time_limit_seconds,
        random_seed=random_seed,
    )


def _safe_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, bool, int)):
        return value
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return str(value)
    if pd.isna(numeric):
        return None
    if numeric.is_integer():
        return int(numeric)
    return numeric


def selected_items_from_result(
    wardrobe: pd.DataFrame,
    result: dict[str, Any],
) -> list[OutfitItem]:
    garment_map = {
        str(row["item_id"]): row.to_dict()
        for _, row in wardrobe.iterrows()
    }
    items: list[OutfitItem] = []
    for raw in result.get("selected_items") or []:
        item_id = str(raw["item_id"])
        item = garment_map.get(item_id, raw)
        items.append(
            OutfitItem(
                item_id=item_id,
                name=str(item.get("name", item_id)),
                category=str(item.get("category", "unknown")),
                item_type=(
                    str(item.get("item_type"))
                    if item.get("item_type") is not None
                    else None
                ),
                weight_g=int(float(item.get("weight_g", 0))),
                style=(
                    str(item.get("style"))
                    if item.get("style") is not None
                    else None
                ),
                color=(
                    str(item.get("color"))
                    if item.get("color") is not None
                    else None
                ),
            )
        )
    return items


def build_capsule(
    trip: TripDetails,
    weather: WeatherData,
    requirements: list[DailyRequirement],
    wardrobe: pd.DataFrame,
    result: dict[str, Any],
) -> TripCapsule:
    if trip.start_date is None or trip.end_date is None or trip.duration_days is None:
        raise ValueError("Cannot build a capsule from incomplete trip details")
    if result.get("status") not in {"OPTIMAL", "FEASIBLE"}:
        raise ValueError("Cannot build a capsule from an unsuccessful optimization")

    garment_map = {
        str(row["item_id"]): row.to_dict()
        for _, row in wardrobe.iterrows()
    }
    selected_items = selected_items_from_result(wardrobe, result)
    item_by_id = {item.item_id: item for item in selected_items}
    requirement_by_day = {
        requirement.day_number: requirement for requirement in requirements
    }

    days: list[CapsuleDay] = []
    for outfit in result.get("daily_outfits") or []:
        day_number = int(outfit["day_number"])
        requirement = requirement_by_day[day_number]
        item_ids = [str(item_id) for item_id in outfit.get("item_ids", [])]
        outfit_items: list[OutfitItem] = []
        for item_id in item_ids:
            if item_id in item_by_id:
                outfit_items.append(item_by_id[item_id])
                continue
            item = garment_map.get(item_id)
            if item:
                outfit_items.append(
                    OutfitItem(
                        item_id=item_id,
                        name=str(item.get("name", item_id)),
                        category=str(item.get("category", "unknown")),
                        item_type=(
                            str(item.get("item_type"))
                            if item.get("item_type") is not None
                            else None
                        ),
                        weight_g=int(float(item.get("weight_g", 0))),
                        style=(
                            str(item.get("style"))
                            if item.get("style") is not None
                            else None
                        ),
                        color=(
                            str(item.get("color"))
                            if item.get("color") is not None
                            else None
                        ),
                    )
                )

        days.append(
            CapsuleDay(
                day_number=day_number,
                date=requirement.date,
                activity=requirement.activity,
                activities=requirement.activities or [requirement.activity],
                weather=requirement.weather,
                temperature_c=requirement.temperature_c,
                precipitation_mm=requirement.precipitation_mm,
                required_style=requirement.required_style,
                outfit_item_ids=item_ids,
                outfit_items=outfit_items,
                compatibility=_safe_value(outfit.get("compatibility")),
                quality=_safe_value(outfit.get("quality")),
            )
        )

    checklist = PackingChecklist(
        items=[
            {
                "item_id": item.item_id,
                "name": item.name,
                "category": item.category,
                "item_type": item.item_type,
                "weight_g": item.weight_g,
                "quantity": 1,
                "packed": False,
            }
            for item in selected_items
        ]
    )

    return TripCapsule(
        trip=CapsuleTripInfo(
            destination=trip.destination or "Unknown",
            country=trip.country,
            start_date=trip.start_date,
            end_date=trip.end_date,
            duration_days=trip.duration_days,
            activities=trip.activities,
            dress_code=trip.dress_code,
            max_luggage_weight_kg=float(trip.max_luggage_weight_kg or 0),
            weather_source=weather.source,
        ),
        days=sorted(days, key=lambda day: day.day_number),
        selected_items=selected_items,
        total_weight_g=int(result.get("total_weight_g") or 0),
        optimization_status=str(result.get("status")),
        number_of_items=int(result.get("number_of_items") or len(selected_items)),
        checklist=checklist,
        created_at=datetime.now(timezone.utc),
        metadata={
            "solver": "OR-Tools CP-SAT",
            "optimizer_time_limit_seconds": None,
            "weather_warning": weather.warning,
            "synthetic_weather": weather.source == "synthetic_fallback",
        },
    )


def compact_result(result: dict[str, Any]) -> dict[str, Any]:
    """LLM-safe, compact optimizer result (no numpy/pandas values)."""
    outfits = []
    for outfit in result.get("daily_outfits") or []:
        outfits.append(
            {
                "day_number": _safe_value(outfit.get("day_number")),
                "activity": outfit.get("activity"),
                "required_style": outfit.get("required_style"),
                "weather": outfit.get("weather"),
                "item_ids": [str(item) for item in outfit.get("item_ids", [])],
                "compatibility": _safe_value(outfit.get("compatibility")),
                "quality": _safe_value(outfit.get("quality")),
            }
        )
    selected = []
    for item in result.get("selected_items") or []:
        selected.append(
            {
                "item_id": str(item.get("item_id")),
                "name": str(item.get("name", "")),
                "category": str(item.get("category", "")),
                "item_type": str(item.get("item_type", "")),
                "weight_g": _safe_value(item.get("weight_g")),
            }
        )
    return {
        "status": result.get("status"),
        "reason": result.get("reason"),
        "total_weight_g": _safe_value(result.get("total_weight_g")),
        "number_of_items": _safe_value(result.get("number_of_items")),
        "number_of_outfits": _safe_value(result.get("number_of_outfits")),
        "daily_outfits": outfits,
        "selected_items": selected,
    }
