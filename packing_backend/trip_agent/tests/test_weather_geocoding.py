"""Regression tests for Open-Meteo geocoding confidence and country handling."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
import requests

from packing_backend.trip_agent import TripAgent, weather
from packing_backend.trip_agent.schemas import WeatherData, WeatherDay
from packing_backend.trip_agent.weather import (
    DestinationResolutionError,
    GeocodeResolution,
    _select_geocode_result,
    resolve_destination,
)


def geocode_result(
    name: str,
    country: str,
    *,
    country_code: str = "XX",
    admin1: str | None = None,
    latitude: float = 0.0,
    longitude: float = 0.0,
    feature_code: str = "PPL",
    population: int | None = None,
) -> dict:
    return {
        "name": name,
        "country": country,
        "country_code": country_code,
        "admin1": admin1,
        "latitude": latitude,
        "longitude": longitude,
        "feature_code": feature_code,
        "population": population,
    }


def test_country_request_uses_representative_city() -> None:
    calls: list[str] = []

    def fetcher(query: str) -> list[dict]:
        calls.append(query)
        return [
            geocode_result(
                "Paris",
                "France",
                country_code="FR",
                latitude=48.85,
                longitude=2.35,
                feature_code="PPLC",
                population=2_138_551,
            )
        ]

    resolution = resolve_destination("France", fetcher=fetcher)

    assert calls == ["Paris, France"]
    assert resolution is not None
    assert resolution.name == "Paris"
    assert resolution.country == "France"
    assert resolution.requested_country is True
    assert "representative forecast" in (resolution.note or "")


def test_lowercase_country_request_is_normalized() -> None:
    calls: list[str] = []

    def fetcher(query: str) -> list[dict]:
        calls.append(query)
        return [
            geocode_result(
                "Paris",
                "France",
                country_code="FR",
                latitude=48.85,
                longitude=2.35,
                feature_code="PPLC",
                population=2_138_551,
            )
        ]

    resolution = resolve_destination("france", fetcher=fetcher)

    assert calls == ["Paris, France"]
    assert resolution is not None
    assert resolution.name == "Paris"


def test_other_real_country_centroid_is_accepted_and_labelled() -> None:
    def fetcher(_query: str) -> list[dict]:
        return [
            geocode_result(
                "Peru",
                "Peru",
                country_code="PE",
                latitude=-9.19,
                longitude=-75.02,
                feature_code="PCLI",
                population=33_000_000,
            )
        ]

    resolution = resolve_destination("Peru", fetcher=fetcher)

    assert resolution is not None
    assert resolution.requested_country is True
    assert "Country-level forecast" in (resolution.note or "")


def test_fictional_country_is_rejected_without_fetching() -> None:
    called = False

    def fetcher(_query: str) -> list[dict]:
        nonlocal called
        called = True
        return []

    assert resolve_destination("Wakanda", fetcher=fetcher) is None
    assert called is False


def test_fuzzy_non_matching_place_is_rejected() -> None:
    def fetcher(_query: str) -> list[dict]:
        return [
            geocode_result("Bellevue", "United States", country_code="US"),
            geocode_result("Fredonia", "United States", country_code="US"),
        ]

    assert resolve_destination("Freedonia", fetcher=fetcher) is None


def test_low_confidence_exact_place_is_rejected() -> None:
    # "Narnia" also exists as a tiny village in Bangladesh with no population.
    resolution = _select_geocode_result(
        "Narnia",
        [
            geocode_result(
                "Narnia",
                "Bangladesh",
                country_code="BD",
                feature_code="PPL",
                population=None,
            )
        ],
    )
    assert resolution is None


def test_populated_exact_place_with_country_hint_is_accepted() -> None:
    def fetcher(_query: str) -> list[dict]:
        return [
            geocode_result(
                "Atlantis",
                "South Africa",
                country_code="ZA",
                latitude=-33.56,
                longitude=18.48,
                feature_code="PPL",
                population=82_736,
            )
        ]

    resolution = resolve_destination("Atlantis, South Africa", fetcher=fetcher)
    assert resolution is not None
    assert resolution.name == "Atlantis"
    assert resolution.country == "South Africa"


def test_non_residential_park_result_is_rejected() -> None:
    resolution = _select_geocode_result(
        "Wakanda",
        [
            geocode_result(
                "Wakanda Park",
                "United States",
                country_code="US",
                admin1="Wisconsin",
                feature_code="PRK",
            )
        ],
    )
    assert resolution is None


def test_unresolved_destination_raises_resolution_error(monkeypatch) -> None:
    monkeypatch.setattr(weather, "resolve_destination", lambda _destination: None)
    start = date.today() + timedelta(days=2)
    end = start + timedelta(days=2)

    with pytest.raises(DestinationResolutionError):
        weather.fetch_weather("Wakanda", start, end, allow_network=True)


def test_network_failure_still_uses_synthetic_fallback(monkeypatch) -> None:
    def failing_resolver(_destination: str):
        raise ValueError("geocoding network unavailable")

    monkeypatch.setattr(weather, "resolve_destination", failing_resolver)
    start = date.today() + timedelta(days=2)
    end = start + timedelta(days=2)

    result = weather.fetch_weather("Paris", start, end, allow_network=True)

    assert result.source == "synthetic_fallback"
    assert result.warning
    assert all(day.synthetic for day in result.days)


def test_weather_request_retries_transient_timeout(monkeypatch) -> None:
    calls = []
    class Response:
        def raise_for_status(self):
            pass
    def request(url, params, timeout):
        calls.append((url, params, timeout))
        if len(calls) == 1:
            raise requests.Timeout("temporary timeout")
        return Response()
    monkeypatch.setattr(weather.requests, "get", request)
    assert isinstance(weather._weather_request("https://example.test", {"name": "Paris"}), Response)
    assert len(calls) == 2


def test_weather_request_does_not_retry_client_error(monkeypatch) -> None:
    calls = []
    response = requests.Response()
    response.status_code = 400
    def request(url, params, timeout):
        calls.append(url)
        return response
    monkeypatch.setattr(weather.requests, "get", request)
    with pytest.raises(requests.HTTPError):
        weather._weather_request("https://example.test", {})
    assert len(calls) == 1


def test_agent_asks_for_destination_when_geocoding_is_unresolved(monkeypatch) -> None:
    monkeypatch.setattr(weather, "resolve_destination", lambda _destination: None)
    start = date.today() + timedelta(days=2)
    end = start + timedelta(days=2)
    agent = TripAgent(use_llm=False, allow_weather_network=True)

    response = agent.handle_structured(
        {
            "destination": "Wakanda",
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "activities": ["sightseeing"],
            "max_luggage_weight_kg": 8,
        }
    )

    assert response.status == "needs_clarification"
    assert "destination" in response.missing_info
    assert "couldn't verify 'Wakanda'" in response.message
    assert response.capsule is None
    assert response.trip_details is not None
    assert response.trip_details.destination is None


def test_network_weather_keeps_resolved_location_metadata(monkeypatch) -> None:
    start = date.today() + timedelta(days=2)
    end = start + timedelta(days=1)

    monkeypatch.setattr(
        weather,
        "resolve_destination",
        lambda _destination: GeocodeResolution(
            latitude=48.85,
            longitude=2.35,
            name="Paris",
            country="France",
            country_code="FR",
            feature_code="PPLC",
            population=2_138_551,
            requested_country=True,
            note="Country request resolved to Paris.",
        ),
    )

    def fake_forecast(
        destination: str,
        _latitude: float,
        _longitude: float,
        _start: date,
        _end: date,
    ) -> WeatherData:
        return WeatherData(
            destination=destination,
            days=[
                WeatherDay(
                    date=_start,
                    weather="sunny",
                    temperature_c=20,
                    source="open-meteo",
                )
            ],
            source="open-meteo",
        )

    monkeypatch.setattr(weather, "_forecast", fake_forecast)

    result = weather.fetch_weather("France", start, end, allow_network=True)

    assert result.source == "open-meteo"
    assert result.resolved_name == "Paris"
    assert result.resolved_country == "France"
    assert result.requested_country is True
    assert result.geocoding_note == "Country request resolved to Paris."


def test_past_dates_inside_provider_range_use_real_forecast(monkeypatch) -> None:
    start = date.today() - timedelta(days=7)
    end = start + timedelta(days=2)
    called = {}

    monkeypatch.setattr(
        weather,
        "resolve_destination",
        lambda _destination: GeocodeResolution(
            latitude=48.85, longitude=2.35, name="Paris", country="France"
        ),
    )

    def fake_forecast(destination, _latitude, _longitude, _start, _end):
        called["start"], called["end"] = _start, _end
        return WeatherData(
            destination=destination,
            days=[
                WeatherDay(
                    date=_start + timedelta(days=i),
                    weather="cloudy",
                    temperature_c=15,
                    source="open-meteo",
                )
                for i in range((_end - _start).days + 1)
            ],
            source="open-meteo",
        )

    monkeypatch.setattr(weather, "_forecast", fake_forecast)

    result = weather.fetch_weather("Paris", start, end, allow_network=True)

    assert result.source == "open-meteo"
    assert called == {"start": start, "end": end}


def test_met_fallback_sends_identifying_user_agent(monkeypatch) -> None:
    captured = {}

    class Response:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {
                "properties": {
                    "timeseries": [
                        {
                            "time": "2026-10-30T12:00:00Z",
                            "data": {
                                "instant": {"details": {"air_temperature": 15.0}},
                                "next_1_hours": {"details": {"precipitation_amount": 0.0}},
                            },
                        }
                    ]
                }
            }

    def request(url, params, timeout, headers=None):
        captured["headers"] = headers
        return Response()

    monkeypatch.setattr(weather.requests, "get", request)

    result = weather._forecast_met(
        "Paris",
        48.85,
        2.35,
        date(2026, 10, 30),
        date(2026, 10, 31),
    )

    assert result.source == "met-no"
    assert captured["headers"]["User-Agent"] == weather.WEATHER_USER_AGENT
    assert "python-requests" not in captured["headers"]["User-Agent"]
