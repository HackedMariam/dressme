"""The weather helper of the AI stylist, with Open-Meteo replaced by a fake."""
from datetime import date

import httpx
import pytest

from app import weather


@pytest.fixture(autouse=True)
def _fresh_cache():
    weather._cache.clear()


def _open_meteo(calls=None):
    days = [f"2026-11-{5 + i:02d}" for i in range(16)]

    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(request.url.host)
        if "geocoding" in request.url.host:
            return httpx.Response(200, json={"results": [
                {"name": "Tunis", "country": "Tunisia", "country_code": "TN", "latitude": 36.8, "longitude": 10.18}]})
        return httpx.Response(200, json={
            "current": {"temperature_2m": 15.4, "apparent_temperature": 13.6},
            "daily": {"time": days, "temperature_2m_max": [18.2] * 16, "temperature_2m_min": [11.6] * 16,
                      "precipitation_probability_max": [70] * 16, "precipitation_sum": [3.24] * 16,
                      "weather_code": [61] * 16, "wind_speed_10m_max": [24.6] * 16}})
    return httpx.MockTransport(handler)


def test_the_forecast_of_a_day_is_read_in_both_units_with_plain_words():
    forecast = weather.day_forecast("Tunis", "Tunisia", 1, transport=_open_meteo())
    assert forecast["city"] == "Tunis" and forecast["date"] == "2026-11-06" and forecast["condition"] == "light rain"
    assert (forecast["temp_min_c"], forecast["temp_max_c"]) == (12, 18)
    assert (forecast["temp_min_f"], forecast["temp_max_f"]) == (53, 65)
    assert forecast["rain_chance_percent"] == 70 and forecast["rain_mm"] == 3.2 and forecast["wind_kmh"] == 25
    assert "temp_now_c" not in forecast                                   # only for today
    assert weather.day_forecast("Tunis", "", 0, transport=_open_meteo())["feels_like_c"] == 14
    assert "70% chance of rain" in forecast["summary"]


def test_the_same_city_is_not_asked_twice():
    calls = []
    transport = _open_meteo(calls)
    weather.day_forecast("Tunis", "Tunisia", 0, transport=transport)
    weather.day_forecast("tunis", "tunisia", 3, transport=transport)
    assert len(calls) == 2                                                # one geocoding + one forecast


@pytest.mark.parametrize("city,days", [("", 0), ("Tunis", -1), ("Tunis", 16)])
def test_nothing_is_asked_without_a_city_or_for_a_day_out_of_range(city, days):
    def fail(request):
        raise AssertionError("no request expected")
    assert weather.day_forecast(city, "", days, transport=httpx.MockTransport(fail)) is None


def test_an_unknown_city_or_a_down_service_gives_none():
    empty = httpx.MockTransport(lambda request: httpx.Response(200, json={}))
    assert weather.day_forecast("Atlantis", "", 0, transport=empty) is None
    down = httpx.MockTransport(lambda request: httpx.Response(503))
    assert weather.day_forecast("Tunis", "", 0, transport=down) is None


def test_the_day_the_user_means_is_understood_in_english_and_french():
    monday = date(2026, 11, 2)
    assert weather.when_to_days_ahead("What to wear tomorrow?", monday) == 1
    assert weather.when_to_days_ahead("Que mettre demain ?", monday) == 1
    assert weather.when_to_days_ahead("a look for friday", monday) == 4
    assert weather.when_to_days_ahead("tenue pour lundi", monday) == 0
    assert weather.when_to_days_ahead("something warm", monday) is None
