from app import weather


def _geocode():
    return {
        "results": [{
            "name": "Test City",
            "country": "Test Country",
            "latitude": 10.0,
            "longitude": 20.0,
        }]
    }


def _open_meteo():
    return {
        "current": {
            "temperature_2m": 20,
            "relative_humidity_2m": 60,
            "apparent_temperature": 19,
            "weather_code": 1,
            "wind_speed_10m": 10,
        },
        "daily": {
            "time": ["2026-10-30"],
            "temperature_2m_max": [23],
            "temperature_2m_min": [15],
            "precipitation_sum": [0],
            "precipitation_probability_max": [10],
            "wind_speed_10m_max": [15],
            "uv_index_max": [3],
            "weather_code": [1],
        },
    }


def test_weather_uses_open_meteo_first(monkeypatch):
    calls = []

    def fake_get(url):
        calls.append(url)
        return _geocode() if "geocoding" in url else _open_meteo()

    monkeypatch.setattr(weather, "_get_json", fake_get)
    result = weather.forecast("Test City", "Test Country")
    assert result["source"] == "open-meteo"
    assert result["fallback_used"] is False
    assert "lat=10.000000&lon=20.000000" not in calls[1]


def test_weather_falls_back_to_met_at_resolved_coordinates(monkeypatch):
    calls = []

    def fake_get(url):
        calls.append(url)
        if "geocoding" in url:
            return _geocode()
        if "open-meteo" in url:
            raise OSError("Open-Meteo unavailable")
        return {
            "properties": {
                "timeseries": [{
                    "time": "2026-10-30T12:00:00Z",
                    "data": {"instant": {"details": {
                        "air_temperature": 21,
                        "wind_speed": 2,
                        "relative_humidity": 55,
                    }}},
                }]
            }
        }

    monkeypatch.setattr(weather, "_get_json", fake_get)
    result = weather.forecast("Test City", "Test Country")
    assert result["source"] == "met-no"
    assert result["fallback_used"] is True
    assert "lat=10.000000&lon=20.000000" in calls[-1]
