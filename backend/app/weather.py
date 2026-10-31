"""Location-aware weather retrieval with an Open-Meteo to MET fallback."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from urllib.parse import quote
from urllib.request import Request, urlopen

log = logging.getLogger("dressme.weather")

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
MET_URL = "https://api.met.no/weatherapi/locationforecast/2.0/compact"


def _get_json(url: str) -> dict:
    request = Request(url, headers={"User-Agent": "DressMe/1.0 weather client"})
    with urlopen(request, timeout=12) as response:
        return json.loads(response.read().decode("utf-8"))


def resolve_location(city: str, country: str | None = None) -> dict:
    query = ", ".join(part for part in (city.strip(), (country or "").strip()) if part)
    if not query:
        raise ValueError("Set your city in Settings to use live weather.")
    data = _get_json(f"{GEOCODING_URL}?name={quote(query)}&count=1&language=en&format=json")
    results = data.get("results") or []
    if not results:
        raise ValueError(f"Could not find weather for {query}.")
    result = results[0]
    return {
        "name": result.get("name") or city.strip(),
        "country": result.get("country"),
        "latitude": float(result["latitude"]),
        "longitude": float(result["longitude"]),
    }


def _open_meteo(location: dict) -> dict:
    params = (
        f"latitude={location['latitude']}&longitude={location['longitude']}"
        "&daily=weather_code,temperature_2m_max,temperature_2m_min,"
        "precipitation_sum,precipitation_probability_max,wind_speed_10m_max,uv_index_max"
        "&current=temperature_2m,relative_humidity_2m,apparent_temperature,"
        "weather_code,wind_speed_10m&forecast_days=7&timezone=auto"
    )
    data = _get_json(f"{OPEN_METEO_URL}?{params}")
    daily = data.get("daily") or {}
    dates = daily.get("time") or []
    if not dates:
        raise ValueError("Open-Meteo returned no forecast days.")
    current = data.get("current") or {}
    return {
        "source": "open-meteo",
        "current": {
            "temperature_c": current.get("temperature_2m"),
            "feels_like_c": current.get("apparent_temperature"),
            "humidity_percent": current.get("relative_humidity_2m"),
            "wind_speed_kmh": current.get("wind_speed_10m"),
            "weather_code": current.get("weather_code"),
        },
        "days": [
            {
                "date": date,
                "temperature_max_c": daily["temperature_2m_max"][i],
                "temperature_min_c": daily["temperature_2m_min"][i],
                "precipitation_mm": daily["precipitation_sum"][i],
                "precipitation_probability": daily["precipitation_probability_max"][i],
                "wind_speed_kmh": daily["wind_speed_10m_max"][i],
                "uv_index": daily["uv_index_max"][i],
                "weather_code": daily["weather_code"][i],
            }
            for i, date in enumerate(dates)
        ],
    }


def _met(location: dict) -> dict:
    data = _get_json(
        f"{MET_URL}?lat={location['latitude']:.6f}&lon={location['longitude']:.6f}"
    )
    by_date: dict[str, dict] = {}
    for entry in data.get("properties", {}).get("timeseries", []):
        timestamp = entry.get("time")
        details = entry.get("data", {}).get("instant", {}).get("details", {})
        if not timestamp or "air_temperature" not in details:
            continue
        day = timestamp[:10]
        item = by_date.setdefault(day, {"temps": [], "winds": [], "humidity": [], "precipitation": 0.0})
        item["temps"].append(float(details["air_temperature"]))
        if details.get("wind_speed") is not None:
            item["winds"].append(float(details["wind_speed"]) * 3.6)
        if details.get("relative_humidity") is not None:
            item["humidity"].append(float(details["relative_humidity"]))
        next_hour = entry.get("data", {}).get("next_1_hours", {}).get("details", {})
        item["precipitation"] += float(next_hour.get("precipitation_amount") or 0)
    days = []
    for day, values in list(sorted(by_date.items()))[:7]:
        days.append({
            "date": day,
            "temperature_max_c": round(max(values["temps"]), 1),
            "temperature_min_c": round(min(values["temps"]), 1),
            "precipitation_mm": round(values["precipitation"], 1),
            "precipitation_probability": None,
            "wind_speed_kmh": round(max(values["winds"]), 1) if values["winds"] else None,
            "uv_index": None,
            "weather_code": None,
        })
    if not days:
        raise ValueError("MET Norway returned no forecast days.")
    first = days[0]
    return {
        "source": "met-no",
        "current": {
            "temperature_c": first["temperature_max_c"],
            "feels_like_c": None,
            "humidity_percent": round(sum(by_date[first["date"]]["humidity"]) / len(by_date[first["date"]]["humidity"]))
            if by_date[first["date"]]["humidity"] else None,
            "wind_speed_kmh": first["wind_speed_kmh"],
            "weather_code": None,
        },
        "days": days,
    }


def forecast(city: str, country: str | None = None) -> dict:
    location = resolve_location(city, country)
    errors = []
    for provider in (_open_meteo, _met):
        try:
            result = provider(location)
            return {
                "location": location,
                **result,
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "fallback_used": result["source"] != "open-meteo",
                "warning": "Open-Meteo was unavailable; using MET Norway."
                if result["source"] == "met-no" else None,
            }
        except Exception as error:
            errors.append(f"{provider.__name__}: {error}")
            log.warning("Weather provider failed: %s", errors[-1])
    raise RuntimeError("Weather providers are unavailable. " + " | ".join(errors))
