"""Convert trip details + weather + activities into optimizer requirements."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pandas as pd

from .schemas import DailyRequirement, TripDetails, WeatherData, normalize_activity

STYLE_BY_ACTIVITY = {
    "sightseeing": "casual",
    "shopping": "casual",
    "walking": "casual",
    "museum": "smart-casual",
    "restaurant": "smart-casual",
    "night-out": "smart-casual",
    "formal-dinner": "formal",
    "business-meeting": "formal",
    "wedding": "formal",
    "gala": "formal",
    "conference": "smart-casual",
    "hiking": "sporty",
    "beach": "casual",
    "skiing": "sporty",
    "sport": "sporty",
    "workout": "sporty",
}

FORMAL_ACTIVITIES = {
    "formal-dinner",
    "business-meeting",
    "wedding",
    "gala",
}

ACTIVITY_PRIORITY = {
    "wedding": 100,
    "gala": 100,
    "formal-dinner": 95,
    "business-meeting": 90,
    "conference": 80,
    "restaurant": 70,
    "night-out": 60,
    "museum": 50,
    "shopping": 40,
    "sightseeing": 30,
    "walking": 25,
    "hiking": 20,
    "beach": 15,
    "skiing": 15,
    "sport": 15,
    "workout": 15,
}

OUTDOOR_ACTIVITIES = {
    "sightseeing",
    "shopping",
    "walking",
    "hiking",
    "beach",
    "skiing",
    "sport",
}

REQUIREMENT_COLUMNS = [
    "trip_id",
    "day_number",
    "date",
    "activity",
    "weather",
    "temperature_c",
    "precipitation_mm",
    "required_style",
    "needs_outerwear",
    "needs_warm_layer",
    "needs_rain_protection",
    "needs_sun_protection",
]


def _ordered_daily_activities(trip: TripDetails) -> dict[int, list[str]]:
    if not trip.duration_days:
        raise ValueError("Trip duration is required before generating requirements")

    activities = [normalize_activity(a) for a in trip.activities]
    if not activities and trip.daily_activities:
        activities = [
            activity
            for values in trip.daily_activities.values()
            for activity in values
        ]
    if not activities:
        raise ValueError("At least one activity is required")

    one_off_activities = [
        activity for activity in activities if activity in FORMAL_ACTIVITIES
    ]
    recurring_activities = [
        activity for activity in activities if activity not in FORMAL_ACTIVITIES
    ] or activities

    result: dict[int, list[str]] = {}
    for day in range(1, trip.duration_days + 1):
        explicit = [
            normalize_activity(a)
            for a in trip.daily_activities.get(day, [])
            if normalize_activity(a)
        ]
        if explicit:
            result[day] = explicit
        else:
            result[day] = [
                recurring_activities[(day - 1) % len(recurring_activities)]
            ]

    # Formal/one-off occasions should happen once rather than repeating every
    # time the recurring activity cycle wraps around.
    explicit_days = {
        day for day in result if trip.daily_activities.get(day)
    }
    reserved_days = sorted(set(result) - explicit_days) or sorted(result)
    for index, activity in enumerate(one_off_activities):
        day = (
            reserved_days[-(index + 1)]
            if index < len(reserved_days)
            else reserved_days[-1]
        )
        result[day] = [activity]

    return result


def _primary_activity(activities: list[str]) -> str:
    return max(
        activities,
        key=lambda activity: (
            ACTIVITY_PRIORITY.get(activity, 0),
            1 if activity in FORMAL_ACTIVITIES else 0,
        ),
    )


def _required_style(trip: TripDetails, activities: list[str]) -> str:
    primary = _primary_activity(activities)
    if primary in FORMAL_ACTIVITIES:
        return "formal"

    dress_code = (trip.dress_code or "").strip().lower().replace(" ", "-")
    if dress_code in {"casual", "smart-casual", "formal", "sporty"}:
        if dress_code == "formal" and primary not in {"hiking", "beach", "skiing", "sport", "workout"}:
            return "formal"
        if dress_code:
            return dress_code
    return STYLE_BY_ACTIVITY.get(primary, "casual")


def build_daily_requirements(
    trip: TripDetails,
    weather: WeatherData,
) -> list[DailyRequirement]:
    if not trip.is_complete or trip.start_date is None or trip.duration_days is None:
        missing = ", ".join(trip.compute_missing_fields())
        raise ValueError(f"Trip details are incomplete: {missing}")

    daily_activities = _ordered_daily_activities(trip)
    requirements: list[DailyRequirement] = []

    for day_number in range(1, trip.duration_days + 1):
        current_date = trip.start_date + timedelta(days=day_number - 1)
        weather_day = weather.day_for(current_date, day_number - 1)
        activities = daily_activities[day_number]
        primary = _primary_activity(activities)

        needs_outerwear = weather_day.needs_outerwear
        if primary in OUTDOOR_ACTIVITIES and weather_day.temperature_c <= 18:
            needs_outerwear = True
        needs_rain = weather_day.needs_rain_protection
        if primary in {"hiking", "beach", "skiing"} and weather_day.precipitation_mm >= 0.5:
            needs_rain = True

        requirements.append(
            DailyRequirement(
                trip_id="AGENT_TRIP",
                day_number=day_number,
                date=current_date,
                activity=primary,
                weather=weather_day.weather,
                temperature_c=weather_day.temperature_c,
                precipitation_mm=weather_day.precipitation_mm,
                required_style=_required_style(trip, activities),
                needs_outerwear=bool(needs_outerwear),
                needs_warm_layer=bool(weather_day.needs_warm_layer),
                needs_rain_protection=bool(needs_rain),
                needs_sun_protection=bool(weather_day.needs_sun_protection),
                activities=activities,
                weather_source=weather_day.source,
            )
        )

    return requirements


def requirements_to_dataframe(
    requirements: list[DailyRequirement],
) -> pd.DataFrame:
    if not requirements:
        raise ValueError("No daily requirements to convert")
    rows = [requirement.model_dump(mode="python") for requirement in requirements]
    frame = pd.DataFrame(rows)
    # The optimizer reads these fields through pandas; keep only its contract
    # plus harmless diagnostics and normalize booleans explicitly.
    for column in REQUIREMENT_COLUMNS:
        if column not in frame.columns:
            raise ValueError(f"Generated requirement is missing {column}")
    for column in [
        "needs_outerwear",
        "needs_warm_layer",
        "needs_rain_protection",
        "needs_sun_protection",
    ]:
        frame[column] = frame[column].astype(bool)
    frame["temperature_c"] = pd.to_numeric(frame["temperature_c"], errors="raise")
    frame["precipitation_mm"] = pd.to_numeric(
        frame["precipitation_mm"], errors="raise"
    )
    frame["day_number"] = frame["day_number"].astype(int)
    return frame.sort_values("day_number").reset_index(drop=True)


def requirement_summary(requirements: list[DailyRequirement]) -> list[dict[str, Any]]:
    return [
        {
            "day_number": requirement.day_number,
            "date": requirement.date.isoformat(),
            "activities": requirement.activities or [requirement.activity],
            "weather": requirement.weather,
            "temperature_c": requirement.temperature_c,
            "precipitation_mm": requirement.precipitation_mm,
            "required_style": requirement.required_style,
            "protections": {
                "outerwear": requirement.needs_outerwear,
                "warm": requirement.needs_warm_layer,
                "rain": requirement.needs_rain_protection,
                "sun": requirement.needs_sun_protection,
            },
        }
        for requirement in requirements
    ]
