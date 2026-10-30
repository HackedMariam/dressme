"""Open-Meteo forecast retrieval with an explicitly labeled synthetic fallback."""

from __future__ import annotations

import hashlib
import logging
import math
import random
import re
import time
import unicodedata
from dataclasses import dataclass, replace
from datetime import date, timedelta
from typing import Callable

import requests

from .config import DEFAULT_WEATHER_TIMEOUT
from .logging_utils import log_event
from .schemas import WeatherData, WeatherDay

logger = logging.getLogger(__name__)


class DestinationResolutionError(ValueError):
    """The destination is fictional or cannot be confidently resolved."""


GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
FORECAST_HORIZON_DAYS = 15
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
ARCHIVE_LAG_DAYS = 7  # the archive trails real time by a few days


def _normalize_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


COUNTRY_ALIASES = {
    "usa": "United States",
    "u s a": "United States",
    "us": "United States",
    "united states of america": "United States",
    "uk": "United Kingdom",
    "u k": "United Kingdom",
    "great britain": "United Kingdom",
    "uae": "United Arab Emirates",
    "u a e": "United Arab Emirates",
    "turkiye": "Türkiye",
    "korea": "South Korea",
    "czech republic": "Czechia",
}

# Country-level requests are better served by a well-known city than by a
# country centroid in the middle of nowhere. Other real countries still work:
# their PCLI result is accepted and labelled as a country-level forecast.
COUNTRY_REPRESENTATIVE_CITY = {
    "france": "Paris",
    "italy": "Rome",
    "spain": "Madrid",
    "germany": "Berlin",
    "united kingdom": "London",
    "ireland": "Dublin",
    "portugal": "Lisbon",
    "netherlands": "Amsterdam",
    "belgium": "Brussels",
    "switzerland": "Zurich",
    "austria": "Vienna",
    "tunisia": "Tunis",
    "morocco": "Marrakech",
    "egypt": "Cairo",
    "turkiye": "Istanbul",
    "turkey": "Istanbul",
    "greece": "Athens",
    "poland": "Warsaw",
    "czechia": "Prague",
    "hungary": "Budapest",
    "romania": "Bucharest",
    "sweden": "Stockholm",
    "norway": "Oslo",
    "denmark": "Copenhagen",
    "united states": "New York",
    "canada": "Toronto",
    "mexico": "Mexico City",
    "brazil": "Sao Paulo",
    "argentina": "Buenos Aires",
    "united arab emirates": "Dubai",
    "saudi arabia": "Riyadh",
    "south africa": "Cape Town",
    "india": "Delhi",
    "japan": "Tokyo",
    "south korea": "Seoul",
    "china": "Beijing",
    "singapore": "Singapore",
    "thailand": "Bangkok",
    "indonesia": "Jakarta",
    "malaysia": "Kuala Lumpur",
    "vietnam": "Hanoi",
    "philippines": "Manila",
    "australia": "Sydney",
    "new zealand": "Auckland",
    "russia": "Moscow",
    "ukraine": "Kyiv",
}

# Open-Meteo performs fuzzy matching. These names are common fictional
# destinations that otherwise resolve to unrelated real places. A country hint
# (e.g. "Atlantis, South Africa") is still allowed through.
FICTIONAL_PLACES = {
    "atlantis",
    "avalon",
    "el dorado",
    "shangri la",
    "narnia",
    "wakanda",
    "freedonia",
    "genovia",
    "latveria",
    "zamunda",
    "elbonia",
    "ruritania",
    "syldavia",
    "borduria",
    "florin",
    "guilder",
    "sodor",
    "westeros",
    "mordor",
    "neverland",
    "wonderland",
    "camelot",
}

FEATURE_SCORES = {
    "PCLI": 35,
    "PPLC": 25,
    "PPLA": 18,
    "PPLA2": 14,
    "PPLA3": 10,
    "PPLA4": 8,
    "PPL": 4,
}

NON_RESIDENTIAL_FEATURES = {
    "PRK",
    "AMUS",
    "AIRH",
    "AIRP",
    "MT",
    "ISLF",
    "PPLX",
    "FRM",
    "HSP",
    "RSTN",
    "SCH",
    "STM",
    "ZOO",
}


@dataclass(frozen=True)
class GeocodeResolution:
    latitude: float
    longitude: float
    name: str
    country: str | None = None
    country_code: str | None = None
    admin1: str | None = None
    feature_code: str | None = None
    population: int | None = None
    requested_country: bool = False
    note: str | None = None


@dataclass(frozen=True)
class _PreparedDestination:
    query: str
    requested_country: bool = False
    note: str | None = None
    invalid_reason: str | None = None

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


def _split_destination(destination: str) -> tuple[str, str | None, str | None]:
    parts = [part.strip() for part in destination.split(",") if part.strip()]
    if not parts:
        return destination.strip(), None, None
    if len(parts) == 1:
        return parts[0], None, None
    country = parts[-1]
    admin = parts[1] if len(parts) >= 3 else None
    return parts[0], country, admin


def _prepare_destination(destination: str) -> _PreparedDestination:
    original = " ".join(destination.split()).strip()
    if not original:
        return _PreparedDestination(
            query="",
            invalid_reason="Destination is empty.",
        )

    _name, country_hint, _admin_hint = _split_destination(original)
    normalized_full = _normalize_text(original)

    if country_hint is None and normalized_full in FICTIONAL_PLACES:
        return _PreparedDestination(
            query=original,
            invalid_reason=(
                f"'{original}' is not a recognized real city or country. "
                "Use a real destination or add a country, for example "
                "'Atlantis, South Africa'."
            ),
        )

    if country_hint is None:
        alias = COUNTRY_ALIASES.get(normalized_full)
        display_country = (alias or original).title()
        if alias:
            normalized_full = _normalize_text(alias)

        representative_city = COUNTRY_REPRESENTATIVE_CITY.get(normalized_full)
        if representative_city:
            return _PreparedDestination(
                query=f"{representative_city}, {display_country}",
                requested_country=True,
                note=(
                    f"Country request '{destination.strip()}' was resolved to "
                    f"{representative_city}, {display_country} for a "
                    "representative forecast."
                ),
            )
        if alias:
            return _PreparedDestination(
                query=display_country,
                requested_country=True,
            )

    return _PreparedDestination(query=original)


def _get_with_retry(url: str, params: dict, attempts: int = 5) -> requests.Response:
    """Open-Meteo connections time out intermittently; retry before giving up."""
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return requests.get(url, params=params, timeout=DEFAULT_WEATHER_TIMEOUT)
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_error = exc
            time.sleep(0.8 * (attempt + 1))
    assert last_error is not None
    raise last_error


_GEOCODE_CACHE: dict[str, list[dict]] = {}


def _fetch_geocode_results(query: str) -> list[dict]:
    if query in _GEOCODE_CACHE:
        return _GEOCODE_CACHE[query]
    response = _get_with_retry(
        GEOCODING_URL,
        {"name": query, "count": 10, "language": "en", "format": "json"},
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("error"):
        raise ValueError(payload.get("reason", "Open-Meteo geocoding returned an error"))
    results = list(payload.get("results") or [])
    if results:
        _GEOCODE_CACHE[query] = results
    return results


def _score_geocode_result(
    query_name: str,
    country_hint: str | None,
    admin_hint: str | None,
    result: dict,
    requested_country: bool,
) -> tuple[float, bool]:
    name = _normalize_text(result.get("name"))
    country = _normalize_text(result.get("country"))
    country_code = _normalize_text(result.get("country_code"))
    admin = _normalize_text(result.get("admin1"))
    feature_code = str(result.get("feature_code") or "").upper()

    query_name = _normalize_text(query_name)
    country_hint_norm = _normalize_text(country_hint) if country_hint else None
    admin_hint_norm = _normalize_text(admin_hint) if admin_hint else None

    exact = bool(query_name and name == query_name)
    score = 0.0
    if exact:
        score += 100
    elif query_name and len(query_name) >= 4 and query_name in name:
        score += 25
    elif name and len(name) >= 4 and name in query_name:
        score += 15

    has_location_hint = bool(country_hint_norm or admin_hint_norm)
    if country_hint_norm:
        if (
            country_hint_norm == country
            or country_hint_norm in country
            or country_code == country_hint_norm
        ):
            score += 40
    if admin_hint_norm and (
        admin_hint_norm == admin
        or admin_hint_norm in admin
        or admin in admin_hint_norm
    ):
        score += 20

    if not exact and not has_location_hint:
        # Fuzzy matches without a country/admin hint are exactly how fake
        # destinations silently become unrelated real towns.
        return -1.0, False

    score += FEATURE_SCORES.get(feature_code, 0)
    if feature_code in NON_RESIDENTIAL_FEATURES:
        score -= 50

    population = result.get("population")
    try:
        population = int(population) if population is not None else None
    except (TypeError, ValueError):
        population = None

    if population and population > 0:
        score += min(25.0, max(0.0, (math.log10(population) - 2.0) * 10.0))
    elif feature_code == "PPL":
        # A PPL with no population is a very weak match. This rejects typical
        # fictional-name collisions such as "Narnia" in Bangladesh.
        score -= 15

    if requested_country and feature_code == "PCLI":
        score += 20

    if feature_code in NON_RESIDENTIAL_FEATURES:
        return -1.0, exact

    return score, exact


def _select_geocode_result(
    destination_query: str,
    results: list[dict],
    requested_country: bool = False,
) -> GeocodeResolution | None:
    name, country_hint, admin_hint = _split_destination(destination_query)
    best: tuple[float, dict, bool] | None = None

    for result in results:
        score, exact = _score_geocode_result(
            name,
            country_hint,
            admin_hint,
            result,
            requested_country,
        )
        if score < 0:
            continue
        if best is None or score > best[0]:
            best = (score, result, exact)

    if best is None or best[0] < 100:
        return None

    _score_value, result, _exact = best
    feature_code = str(result.get("feature_code") or "").upper()
    try:
        latitude = float(result["latitude"])
        longitude = float(result["longitude"])
    except (KeyError, TypeError, ValueError):
        return None

    population = result.get("population")
    try:
        population = int(population) if population is not None else None
    except (TypeError, ValueError):
        population = None

    note = None
    is_country_result = feature_code == "PCLI"
    if is_country_result:
        label = str(result.get("name") or destination_query)
        note = (
            f"Country-level forecast uses the centre of {label}. "
            "Enter a city for a more precise forecast."
        )

    return GeocodeResolution(
        latitude=latitude,
        longitude=longitude,
        name=str(result.get("name") or destination_query),
        country=(
            str(result.get("country")) if result.get("country") is not None else None
        ),
        country_code=(
            str(result.get("country_code"))
            if result.get("country_code") is not None
            else None
        ),
        admin1=(
            str(result.get("admin1"))
            if result.get("admin1") is not None
            else None
        ),
        feature_code=feature_code or None,
        population=population,
        requested_country=requested_country or is_country_result,
        note=note,
    )


def resolve_destination(
    destination: str,
    fetcher: Callable[[str], list[dict]] | None = None,
) -> GeocodeResolution | None:
    """Resolve a destination confidently, rejecting fuzzy fictional matches."""
    prepared = _prepare_destination(destination)
    if prepared.invalid_reason or not prepared.query:
        log_event(
            logger,
            "geocode_rejected",
            destination=destination,
            reason=prepared.invalid_reason,
            level=logging.WARNING,
        )
        return None

    try:
        results = (fetcher or _fetch_geocode_results)(prepared.query)
    except Exception as exc:
        raise ValueError(f"Open-Meteo geocoding request failed: {exc}") from exc

    resolution = _select_geocode_result(
        prepared.query,
        results,
        requested_country=prepared.requested_country,
    )
    if resolution is None:
        log_event(
            logger,
            "geocode_ambiguous",
            destination=destination,
            query=prepared.query,
            candidates=len(results),
            level=logging.WARNING,
        )
        return None

    if prepared.note:
        resolution = replace(resolution, note=prepared.note)

    log_event(
        logger,
        "geocode_resolved",
        destination=destination,
        resolved_name=resolution.name,
        resolved_country=resolution.country,
        feature_code=resolution.feature_code,
        population=resolution.population,
        requested_country=resolution.requested_country,
    )
    return resolution


def _geocode(destination: str) -> tuple[float | None, float | None]:
    """Backward-compatible tuple helper used by older callers."""
    resolution = resolve_destination(destination)
    if resolution is None:
        return None, None
    return resolution.latitude, resolution.longitude


def _shift_year(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year + years)
    except ValueError:  # 29 February in a non-leap year
        return value.replace(year=value.year + years, day=28)


def _historical(
    destination: str, latitude: float, longitude: float, start: date, end: date
) -> WeatherData:
    """Observed weather for the same dates in a past year, used beyond the forecast horizon."""
    latest = date.today() - timedelta(days=ARCHIVE_LAG_DAYS)
    years = 1
    while _shift_year(end, -years) > latest:
        years += 1
    return _forecast(
        destination,
        latitude,
        longitude,
        _shift_year(start, -years),
        _shift_year(end, -years),
        url=ARCHIVE_URL,
        source="open-meteo-archive",
        shift_years=years,  # rows come back dated last year; shift them onto the trip dates
    )


def _forecast(
    destination: str,
    latitude: float,
    longitude: float,
    start: date,
    end: date,
    *,
    url: str = FORECAST_URL,
    source: str = "open-meteo",
    shift_years: int = 0,
) -> WeatherData:
    daily_variables = (
        "weather_code,temperature_2m_max,temperature_2m_min,"
        "precipitation_sum,wind_speed_10m_max"
    )
    if url == FORECAST_URL:
        daily_variables += ",precipitation_probability_max,uv_index_max"
    response = _get_with_retry(
        url,
        {
            "latitude": latitude,
            "longitude": longitude,
            "daily": daily_variables,
            "timezone": "auto",
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
        },
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
        current = _shift_year(date.fromisoformat(raw_date), shift_years)
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
                source=source,
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

    # Obvious fictional names should be rejected even when network weather is
    # disabled, otherwise the UI would plan a trip to a non-existent place.
    prepared = _prepare_destination(destination)
    if prepared.invalid_reason:
        raise DestinationResolutionError(prepared.invalid_reason)

    today = date.today()
    forecast_start = max(start, today - timedelta(days=1))
    forecast_end = min(end, today + timedelta(days=FORECAST_HORIZON_DAYS))

    if allow_network:
        try:
            resolution = resolve_destination(destination)
            if resolution is None:
                raise DestinationResolutionError(
                    f"Could not confidently resolve destination '{destination}' "
                    "to a real city or country"
                )
            days: list[WeatherDay] = []
            if forecast_start <= forecast_end:
                days += _forecast(
                    destination, resolution.latitude, resolution.longitude, forecast_start, forecast_end
                ).days
                # Trip days before / after the forecast window use last year's observed weather.
                gaps = [(start, forecast_start - timedelta(days=1)), (forecast_end + timedelta(days=1), end)]
            else:
                gaps = [(start, end)]
            historical = False
            estimated = False
            for gap_start, gap_end in gaps:
                if gap_start > gap_end:
                    continue
                historical = True
                try:
                    days += _historical(
                        destination, resolution.latitude, resolution.longitude, gap_start, gap_end
                    ).days
                except Exception as exc:  # archive unreachable: seasonal estimate, clearly labelled
                    estimated = True
                    log_event(logger, "weather_archive_failed", destination=destination,
                              error=str(exc), level=logging.WARNING)
                    days += _synthetic_weather(destination, gap_start, gap_end, str(exc)).days
            warning = None
            if historical:
                warning = (
                    f"Part of this trip is outside the {FORECAST_HORIZON_DAYS}-day forecast window, so those days "
                    + ("use a typical seasonal estimate for the destination's month (the historical weather "
                       "service could not be reached)"
                       if estimated else
                       "use the observed weather of the same dates in a previous year")
                    + " - a climate estimate, not a forecast."
                )
            days = sorted({d.date: d for d in days}.values(), key=lambda d: d.date)
            weather = WeatherData(
                destination=destination,
                latitude=resolution.latitude,
                longitude=resolution.longitude,
                days=days,
                source="open-meteo" if any(not d.synthetic for d in days) else "synthetic_fallback",
                warning=warning,
                resolved_name=resolution.name,
                resolved_country=resolution.country,
                requested_country=resolution.requested_country,
                geocoding_note=resolution.note,
            )
            log_event(
                logger,
                "weather_fetched",
                destination=destination,
                resolved_name=resolution.name,
                source=weather.source,
                days=len(weather.days),
                historical=historical,
            )
            return weather
        except DestinationResolutionError:
            raise
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

    reason = "Network weather retrieval was disabled."
    log_event(logger, "weather_synthetic_fallback", destination=destination, reason=reason)
    return _synthetic_weather(destination, start, end, reason)
