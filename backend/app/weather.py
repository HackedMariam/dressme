"""Weather for the AI stylist (Open-Meteo: free, no key). The forecast of one day in the user's city, so that outfit
advice can be about the real weather. Any failure (no city, unknown city, offline) returns None: the stylist then
answers without weather instead of failing."""
from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta

import httpx

log = logging.getLogger("dressme.weather")

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
FORECAST_DAYS = 16          # what the free forecast covers
CACHE_SECONDS = 30 * 60

# WMO weather codes -> words the stylist (and the user) can use.
CONDITIONS = {
    0: "clear sky", 1: "mostly clear", 2: "partly cloudy", 3: "overcast", 45: "fog", 48: "freezing fog",
    51: "light drizzle", 53: "drizzle", 55: "heavy drizzle", 56: "freezing drizzle", 57: "freezing drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain", 66: "freezing rain", 67: "freezing rain",
    71: "light snow", 73: "snow", 75: "heavy snow", 77: "snow grains", 80: "rain showers", 81: "rain showers",
    82: "violent rain showers", 85: "snow showers", 86: "snow showers", 95: "thunderstorm", 96: "thunderstorm with hail",
    99: "thunderstorm with hail",
}

_cache: dict[tuple, tuple[float, object]] = {}


def _cached(key: tuple, load):
    now = time.time()
    hit = _cache.get(key)
    if hit and now - hit[0] < CACHE_SECONDS:
        return hit[1]
    value = load()
    if value is not None:
        _cache[key] = (now, value)
    return value


def _search(client: httpx.Client, name: str, country: str) -> dict | None:
    reply = client.get(GEOCODE_URL, params={"name": name, "count": 20, "language": "en", "format": "json"})
    reply.raise_for_status()
    results = reply.json().get("results") or []
    wanted = country.strip().lower()
    for result in results:
        if not wanted or wanted in (str(result.get("country", "")).lower(), str(result.get("country_code", "")).lower()):
            return result
    return results[0] if results and not wanted else None


def _place(client: httpx.Client, city: str, country: str) -> dict | None:
    """The place for a city name. A small town the geocoder does not know ("Ariana Soghra") falls back on its
    first words ("Ariana"), then on the nearest name it does know."""
    words = city.replace(",", " ").replace("-", " ").split()
    for count in range(len(words), 0, -1):
        found = _search(client, " ".join(words[:count]), country)
        if found:
            return found
    return None


def _forecast(client: httpx.Client, latitude: float, longitude: float) -> dict | None:
    reply = client.get(FORECAST_URL, params={
        "latitude": latitude, "longitude": longitude, "timezone": "auto", "forecast_days": FORECAST_DAYS,
        "current": "temperature_2m,apparent_temperature",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum,"
                 "weather_code,wind_speed_10m_max",
    })
    reply.raise_for_status()
    return reply.json()


def _fahrenheit(celsius: float) -> int:
    return round(celsius * 9 / 5 + 32)


def day_forecast(city: str, country: str = "", days_ahead: int = 0, *,
                 transport: httpx.BaseTransport | None = None) -> dict | None:
    """The weather of one day (0 = today) in `city`, or None when it cannot be known."""
    city = (city or "").strip()
    if not city or not 0 <= days_ahead < FORECAST_DAYS:
        return None
    try:
        with httpx.Client(timeout=10, transport=transport) as client:
            place = _cached(("place", city.lower(), country.strip().lower()), lambda: _place(client, city, country))
            if not place:
                return None
            data = _cached(("forecast", place["latitude"], place["longitude"]),
                           lambda: _forecast(client, place["latitude"], place["longitude"]))
    except (httpx.HTTPError, ValueError, KeyError) as error:
        log.warning("weather unavailable for %s: %s: %s", city, type(error).__name__, error)
        return None
    if not data:
        return None

    daily = data.get("daily") or {}
    try:
        day = date.fromisoformat(daily["time"][days_ahead])
        low, high = float(daily["temperature_2m_min"][days_ahead]), float(daily["temperature_2m_max"][days_ahead])
        code = int(daily["weather_code"][days_ahead])
    except (KeyError, IndexError, TypeError, ValueError):
        return None
    rain_chance = daily.get("precipitation_probability_max", [None] * FORECAST_DAYS)[days_ahead]
    rain_mm = daily.get("precipitation_sum", [None] * FORECAST_DAYS)[days_ahead]
    wind = daily.get("wind_speed_10m_max", [None] * FORECAST_DAYS)[days_ahead]
    current = (data.get("current") or {}) if days_ahead == 0 else {}

    condition = CONDITIONS.get(code, "variable")
    result = {
        "city": place.get("name") or city, "country": place.get("country") or country,
        "date": day.isoformat(), "weekday": day.strftime("%A"), "days_ahead": days_ahead,
        "condition": condition,
        "temp_min_c": round(low), "temp_max_c": round(high),
        "temp_min_f": _fahrenheit(low), "temp_max_f": _fahrenheit(high),
        "rain_chance_percent": None if rain_chance is None else int(rain_chance),
        "rain_mm": None if rain_mm is None else round(float(rain_mm), 1),
        "wind_kmh": None if wind is None else round(float(wind)),
    }
    if current.get("temperature_2m") is not None:
        result["temp_now_c"] = round(float(current["temperature_2m"]))
        result["feels_like_c"] = round(float(current.get("apparent_temperature", current["temperature_2m"])))
    rain = f", {result['rain_chance_percent']}% chance of rain" if result["rain_chance_percent"] is not None else ""
    result["summary"] = (f"{result['weekday']} {day.day} {day.strftime('%B')} in {result['city']}: {condition}, "
                         f"{result['temp_min_c']} to {result['temp_max_c']} C{rain}")
    return result


def when_to_days_ahead(text: str, today: date | None = None) -> int | None:
    """'friday' / 'tomorrow' / 'demain' / 'vendredi' -> number of days from today (None when no day is named)."""
    today = today or date.today()
    lowered = (text or "").lower()
    if any(word in lowered for word in ("tomorrow", "demain")):
        return 1
    if any(word in lowered for word in ("today", "tonight", "aujourd", "ce soir")):
        return 0
    names = {"monday": 0, "lundi": 0, "tuesday": 1, "mardi": 1, "wednesday": 2, "mercredi": 2, "thursday": 3,
             "jeudi": 3, "friday": 4, "vendredi": 4, "saturday": 5, "samedi": 5, "sunday": 6, "dimanche": 6}
    for word, weekday in names.items():
        if word in lowered:
            return (weekday - today.weekday()) % 7
    return None


def describe(days_ahead: int, today: date | None = None) -> str:
    today = today or date.today()
    return (today + timedelta(days=days_ahead)).strftime("%A %d %B")


__all__ = ["day_forecast", "when_to_days_ahead", "describe", "datetime"]
