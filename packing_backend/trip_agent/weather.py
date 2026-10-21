"""Open-Meteo forecast retrieval with an explicitly labeled synthetic fallback."""

from __future__ import annotations

import hashlib
import logging
import random
from datetime import date, timedelta

import requests

from .config import DEFAULT_WEATHER_TIMEOUT
from .logging_utils import log_event
from .schemas import WeatherData, WeatherDay

logger = logging.getLogger(__name__)

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
FORECAST_HORIZON_DAYS = 15

MONTH_BASE_TEMPERATURE = {
    1: 7,
    2: 8,
    3: 12,
    4: 16,
    5: 20,
    6: 24,
    7: 27,
    8: 27,
    9: 23,
    10: 17,
    11: 12,
    12: 8,
}


def _normalize_weather(code: int | None, temperature: float, wind: float) -> str:
    if code is None:
        condition = "cloudy"
    elif code == 0:
        condition = "sunny"
    elif code in {1, 2, 3, 45, 48}:
        condition = "cloudy"
    elif code in {71, 73, 75, 77, 85, 86}:
        condition = "cold"
    elif code in {95, 96, 99}:
        condition = "rainy"
    elif 51 <= code <= 67 or 80 <= code <= 82:
        condition = "rainy"
    else:
        condition = "cloudy"

    if temperature >= 28 and condition in {"sunny", "cloudy"}:
        return "hot"
    if temperature <= 5 and condition not in {"rainy"}:
        return "cold"
    if wind >= 35 and condition not in {"rainy", "sunny"}:
        return "windy"
    return condition


def _synthetic_weather(
    destination: str,
    start: date,
    end: date,
    reason: str,
) -> WeatherData:
    seed_source = f"{destination.lower()}|{start.isoformat()}|{end.isoformat()}"
    seed = int(hashlib.sha256(seed_source.encode("utf-8")).hexdigest()[:16], 16)
    rng = random.Random(seed)

    days: list[WeatherDay] = []
    current = start
    while current <= end:
        base = MONTH_BASE_TEMPERATURE.get(current.month, 16)
        average = base + rng.uniform(-3.5, 3.5)
        minimum = average - rng.uniform(2.0, 5.0)
        maximum = average + rng.uniform(2.0, 5.0)

        if current.month in {12, 1, 2}:
            weather = rng.choices(
                ["cloudy", "rainy", "cold", "windy", "sunny"],
                weights=[0.30, 0.24, 0.20, 0.16, 0.10],
            )[0]
        elif current.month in {6, 7, 8}:
            weather = rng.choices(
                ["sunny", "hot", "cloudy", "rainy"],
                weights=[0.42, 0.24, 0.22, 0.12],
            )[0]
        else:
            weather = rng.choices(
                ["sunny", "cloudy", "rainy", "windy", "cold"],
                weights=[0.30, 0.30, 0.18, 0.14, 0.08],
            )[0]

        precipitation = (
            round(rng.uniform(2.0, 10.0), 1)
            if weather == "rainy"
            else round(rng.uniform(0.0, 0.9), 1)
        )
        wind = round(rng.uniform(5.0, 32.0), 1)
        uv = (
            round(rng.uniform(5.0, 9.0), 1)
            if weather in {"sunny", "hot"}
            else round(rng.uniform(1.0, 5.0), 1)
        )

        days.append(
            WeatherDay(
                date=current,
                weather=weather,
                temperature_c=round(average, 1),
                temperature_min_c=round(minimum, 1),
                temperature_max_c=round(maximum, 1),
                precipitation_mm=precipitation,
                precipitation_probability=(
                    round(rng.uniform(55, 95), 0) if weather == "rainy" else round(rng.uniform(0, 40), 0)
                ),
                wind_speed_kmh=wind,
                uv_index=uv,
                source="synthetic_fallback",
                synthetic=True,
            )
        )
        current += timedelta(days=1)

    return WeatherData(
        destination=destination,
        days=days,
        source="synthetic_fallback",
        warning=(
            f"{reason} Synthetic weather was generated for "
            f"{start.isoformat()} to {end.isoformat()} and is explicitly labeled; "
            "it is not a real forecast."
        ),
    )


def _geocode(destination: str) -> tuple[float | None, float | None]:
    response = requests.get(
        GEOCODING_URL,
        params={"name": destination, "count": 1, "language": "en", "format": "json"},
        timeout=DEFAULT_WEATHER_TIMEOUT,
    )
    response.raise_for_status()
    results = response.json().get("results") or []
    if not results:
        return None, None
    return float(results[0]["latitude"]), float(results[0]["longitude"])


def _forecast(
    destination: str,
    latitude: float,
    longitude: float,
    start: date,
    end: date,
) -> WeatherData:
    response = requests.get(
        FORECAST_URL,
        params={
            "latitude": latitude,
            "longitude": longitude,
            "daily": (
                "weather_code,temperature_2m_max,temperature_2m_min,"
                "precipitation_sum,precipitation_probability_max,"
                "wind_speed_10m_max,uv_index_max"
            ),
            "timezone": "auto",
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
        },
        timeout=DEFAULT_WEATHER_TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("error"):
        raise ValueError(payload.get("reason", "Open-Meteo returned an error"))

    daily = payload.get("daily") or {}
    times = daily.get("time") or []
    if not times:
        raise ValueError("Open-Meteo returned no daily forecast rows")

    days: list[WeatherDay] = []
    for index, raw_date in enumerate(times):
        current = date.fromisoformat(raw_date)
        minimum = daily.get("temperature_2m_min", [None])[index]
        maximum = daily.get("temperature_2m_max", [None])[index]
        if minimum is None or maximum is None:
            continue
        average = (float(minimum) + float(maximum)) / 2.0
        wind = float((daily.get("wind_speed_10m_max") or [0])[index] or 0)
        code = (daily.get("weather_code") or [None])[index]
        condition = _normalize_weather(
            int(code) if code is not None else None, average, wind
        )
        days.append(
            WeatherDay(
                date=current,
                weather=condition,
                temperature_c=round(average, 1),
                temperature_min_c=float(minimum),
                temperature_max_c=float(maximum),
                precipitation_mm=float(
                    (daily.get("precipitation_sum") or [0])[index] or 0
                ),
                precipitation_probability=(
                    float((daily.get("precipitation_probability_max") or [None])[index])
                    if (daily.get("precipitation_probability_max") or [None])[index]
                    is not None
                    else None
                ),
                wind_speed_kmh=wind,
                uv_index=(
                    float((daily.get("uv_index_max") or [None])[index])
                    if (daily.get("uv_index_max") or [None])[index] is not None
                    else None
                ),
                source="open-meteo",
                synthetic=False,
            )
        )

    if not days:
        raise ValueError("Open-Meteo forecast contained no usable temperature rows")

    return WeatherData(
        destination=destination,
        latitude=latitude,
        longitude=longitude,
        days=days,
        source="open-meteo",
    )


def fetch_weather(
    destination: str,
    start: date,
    end: date,
    allow_network: bool = True,
) -> WeatherData:
    """Fetch a forecast, falling back to labeled synthetic weather on failure."""
    if end < start:
        start, end = end, start

    today = date.today()
    within_forecast_window = (
        start >= today - timedelta(days=1)
        and end <= today + timedelta(days=FORECAST_HORIZON_DAYS)
    )

    if allow_network and within_forecast_window:
        try:
            latitude, longitude = _geocode(destination)
            if latitude is None or longitude is None:
                raise ValueError(f"Could not geocode destination '{destination}'")
            weather = _forecast(destination, latitude, longitude, start, end)
            log_event(
                logger,
                "weather_fetched",
                destination=destination,
                source=weather.source,
                days=len(weather.days),
            )
            return weather
        except Exception as exc:
            reason = f"Open-Meteo weather retrieval failed: {exc}."
            log_event(
                logger,
                "weather_fallback",
                destination=destination,
                error=str(exc),
                level=logging.WARNING,
            )
            return _synthetic_weather(destination, start, end, reason)

    if not within_forecast_window:
        reason = (
            "Requested dates are outside the Open-Meteo forecast window "
            f"({(today - timedelta(days=1)).isoformat()} to "
            f"{(today + timedelta(days=FORECAST_HORIZON_DAYS)).isoformat()})."
        )
    else:
        reason = "Network weather retrieval was disabled."
    log_event(logger, "weather_synthetic_fallback", destination=destination, reason=reason)
    return _synthetic_weather(destination, start, end, reason)
