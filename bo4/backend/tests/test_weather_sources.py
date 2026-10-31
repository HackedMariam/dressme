"""Météo robuste du Stylist (sans réseau : chaque source est simulée).

Sources dans l'ordre : Open-Meteo, MET Norway, wttr.in, puis cache, puis saison déduite de la date.
Contrainte de pluie : appliquée dans apply_constraints (pas dans le score du moteur BO4).
"""

import datetime as dt
import json
import time
import urllib.error

import pytest

import stylist_agent as sa
import weather_sources as ws
from test_stylist_agent import TODAY, fixture_loader, run

DAY = TODAY


def ok(t_min, t_max, rain=10, calls=None, name="", **extra):
    def source(city, day, timeout=3):
        if calls is not None:
            calls.append(name)
        return {"city": city, "t_min": t_min, "t_max": t_max, "rain_probability": rain, **extra}
    return source


def down(calls=None, name="", error=None):
    def source(city, day, timeout=3):
        if calls is not None:
            calls.append(name)
        raise error or ws.WeatherError(f"{name} injoignable")
    return source


class Clock:
    def __init__(self, now=1_000_000.0):
        self.now = now

    def __call__(self):
        return self.now


def robust(sources, clock=None, **kwargs):
    clock = clock or Clock()
    return ws.RobustWeather(sources, cache=ws.WeatherCache(path=None, clock=clock), clock=clock, offline=False,
                            **kwargs)


# ---------------------------------------------------------------- format commun et Open-Meteo
def test_normalize_rejects_null_temperatures_and_cleans_values():
    with pytest.raises(ws.WeatherError):
        ws.normalize({"t_min": None, "t_max": None}, "Tunis", DAY, "Open-Meteo")
    forecast = ws.normalize({"t_min": 18, "t_max": 9, "rain_probability": 140.4}, "Tunis", DAY, "wttr.in")
    assert (forecast["t_min"], forecast["t_max"], forecast["rain_probability"]) == (9, 18, 100)
    assert forecast["season"] == "autumn" and forecast["source"] == "wttr.in"
    assert set(forecast) >= {"city", "date", "t_min", "t_max", "rain_probability", "rain_code", "season"}


def test_open_meteo_null_temperature_is_a_weather_error(monkeypatch):
    """Cause de la panne reproduite : des températures null faisaient planter /api/chat (TypeError)."""
    def fake(url, params, timeout):
        if "geocoding" in url:
            return {"results": [{"name": "Tunis", "latitude": 36.8, "longitude": 10.18}]}
        return {"daily": {"time": [DAY.isoformat()], "temperature_2m_min": [None], "temperature_2m_max": [None],
                          "precipitation_probability_max": [None]}}
    monkeypatch.setattr(sa, "_get_json", fake)
    with pytest.raises(sa.WeatherError, match="température absente"):
        sa.open_meteo_forecast("Tunis", DAY)


def test_open_meteo_html_page_is_reported_as_non_json(monkeypatch):
    def captive_portal(url, params, timeout):
        raise json.JSONDecodeError("Expecting value", "<html>", 0)
    monkeypatch.setattr(sa, "_get_json", captive_portal)
    with pytest.raises(sa.WeatherError, match="non JSON"):
        sa.open_meteo_forecast("Tunis", DAY)


# ---------------------------------------------------------------- MET Norway et wttr.in
MET_SAMPLE = {"properties": {"timeseries": [
    {"time": f"{DAY.isoformat()}T06:00:00Z", "data": {
        "instant": {"details": {"air_temperature": 11.2}},
        "next_6_hours": {"summary": {"symbol_code": "lightrainshowers_day"},
                         "details": {"probability_of_precipitation": 63.0}}}},
    {"time": f"{DAY.isoformat()}T15:00:00Z", "data": {"instant": {"details": {"air_temperature": 17.8}},
                                                      "next_1_hours": {"summary": {"symbol_code": "cloudy"}}}},
    {"time": f"{(DAY + dt.timedelta(days=1)).isoformat()}T12:00:00Z",
     "data": {"instant": {"details": {"air_temperature": 30.0}}}},
]}}


def test_met_norway_parsing_uses_known_coordinates_and_four_decimals():
    calls = []

    def get(url, params, timeout):
        calls.append((url, params))
        return MET_SAMPLE
    forecast = ws.met_norway_forecast("Tunis", DAY, get=get)
    assert forecast == {"city": "Tunis", "t_min": 11.2, "t_max": 17.8, "rain_probability": 63.0, "rain_code": True}
    assert len(calls) == 1 and calls[0][0] == ws.MET_NORWAY_URL      # Tunis connue : pas de géocodage
    assert calls[0][1] == {"lat": 36.8065, "lon": 10.1815}


def test_met_norway_requests_carry_the_dressme_user_agent(monkeypatch):
    seen = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(MET_SAMPLE).encode()

    def fake_urlopen(request, timeout):
        seen.append((request.full_url, request.get_header("User-agent"), timeout))
        return Response()
    monkeypatch.setattr(ws.urllib.request, "urlopen", fake_urlopen)
    ws.met_norway_forecast("Paris", DAY, timeout=3)
    url, agent, timeout = seen[0]
    assert url.startswith("https://api.met.no/weatherapi/locationforecast/2.0/") and timeout == 3
    assert agent.startswith("DressMe/") and "github.com" in agent


def test_wttr_parsing():
    sample = {"nearest_area": [{"areaName": [{"value": "Tunis"}]}],
              "weather": [{"date": DAY.isoformat(), "mintempC": "12", "maxtempC": "19",
                           "hourly": [{"chanceofrain": "20", "weatherCode": "116"},
                                      {"chanceofrain": "71", "weatherCode": "296"}]}]}
    forecast = ws.wttr_forecast("Tunis", DAY, get=lambda url, params, timeout: sample)
    assert forecast == {"city": "Tunis", "t_min": "12", "t_max": "19", "rain_probability": 71, "rain_code": True}
    assert ws.normalize(forecast, "Tunis", DAY, "wttr.in")["t_max"] == 19


# ---------------------------------------------------------------- chaîne de secours
def test_first_source_answers():
    calls = []
    forecast = robust([("Open-Meteo", ok(12, 18, calls=calls, name="om")),
                       ("MET Norway", ok(0, 1, calls=calls, name="met"))])("Tunis", DAY)
    assert calls == ["om"] and forecast["source"] == "Open-Meteo" and "failures" not in forecast


@pytest.mark.parametrize("broken, used", [(1, "MET Norway"), (2, "wttr.in")])
def test_each_source_down_one_after_the_other(broken, used):
    calls = []
    names = ["Open-Meteo", "MET Norway", "wttr.in"]
    sources = [(n, down(calls, n) if i < broken else ok(12, 18, calls=calls, name=n)) for i, n in enumerate(names)]
    forecast = robust(sources)("Tunis", DAY)
    assert forecast["source"] == used and calls == names[:broken + 1]
    assert len(forecast["failures"]) == broken and forecast["attribution"] == ws.ATTRIBUTION[used]


def test_all_sources_down_raise_a_weather_error():
    sources = [(n, down(name=n)) for n in ("Open-Meteo", "MET Norway", "wttr.in")]
    with pytest.raises(ws.WeatherError, match="aucune source"):
        robust(sources)("Tunis", DAY)


def test_slow_source_is_abandoned_after_the_deadline():
    def hanging(city, day, timeout):      # DNS ou pare-feu silencieux : urllib ne rendrait pas la main
        time.sleep(1.0)
        return {"t_min": 1, "t_max": 2}
    start = time.perf_counter()
    forecast = robust([("Open-Meteo", hanging), ("MET Norway", ok(12, 18))], deadline_s=0.1)("Tunis", DAY)
    assert time.perf_counter() - start < 0.6
    assert forecast["source"] == "MET Norway" and "délai de 0.1 s dépassé" in forecast["failures"][0]


def test_failed_source_is_skipped_for_the_backoff_period():
    clock, calls = Clock(), []
    weather = robust([("Open-Meteo", down(calls, "om")), ("MET Norway", ok(12, 18, calls=calls, name="met"))],
                     clock=clock)
    weather("Tunis", DAY)
    weather.cache = ws.WeatherCache(path=None, clock=clock)     # vide le cache : la chaîne est rejouée
    clock.now += 30
    weather("Tunis", DAY)
    assert calls == ["om", "met", "met"]                          # Open-Meteo ignorée 60 s
    weather.cache = ws.WeatherCache(path=None, clock=clock)
    clock.now += 61
    weather("Tunis", DAY)
    assert calls[-2:] == ["om", "met"]


def test_fresh_cache_avoids_the_network():
    clock, calls = Clock(), []
    weather = robust([("Open-Meteo", ok(12, 18, calls=calls, name="om"))], clock=clock)
    weather("Tunis", DAY)
    clock.now += 20 * 60
    forecast = weather("Tunis", DAY)
    assert calls == ["om"] and forecast["source"].startswith("Open-Meteo (cache, il y a 20 min")


def test_stale_cache_is_the_fallback_when_every_source_is_down():
    clock = Clock()
    weather = robust([("Open-Meteo", ok(12, 18))], clock=clock)
    weather("Tunis", DAY)
    weather.sources = [(n, down(name=n)) for n in ("Open-Meteo", "MET Norway", "wttr.in")]
    clock.now += 2 * 3600
    forecast = weather("Tunis", DAY)
    assert forecast["t_max"] == 18 and "cache de secours, il y a 2.0 h" in forecast["source"]
    clock.now += 23 * 3600                                         # 25 h : trop vieux
    with pytest.raises(ws.WeatherError):
        weather("Tunis", DAY)


def test_cache_file_survives_a_restart(tmp_path):
    clock = Clock()
    ws.WeatherCache(path=tmp_path / "cache.json", clock=clock).put(
        "Tunis", DAY, ws.normalize({"t_min": 9, "t_max": 14}, "Tunis", DAY, "MET Norway"))
    again = ws.WeatherCache(path=tmp_path / "cache.json", clock=clock).get("tunis", DAY, ws.FRESH_CACHE_S)
    assert again and again[0]["source"] == "MET Norway"


def test_offline_mode_uses_the_recorded_forecast_without_any_source(monkeypatch):
    monkeypatch.setenv("STYLIST_WEATHER_OFFLINE", "1")
    calls = []
    weather = ws.RobustWeather([("Open-Meteo", down(calls, "om"))], cache=ws.WeatherCache(path=None))
    forecast = weather("Paris", DAY)
    recorded = json.loads(ws.OFFLINE_FILE.read_text(encoding="utf-8"))
    assert calls == [] and forecast["source"] == "prévision enregistrée (démo hors ligne)"
    assert (forecast["t_min"], forecast["t_max"], forecast["rain_probability"]) == (
        recorded["t_min"], recorded["t_max"], recorded["rain_probability"])
    assert forecast["city"] == "Paris" and forecast["date"] == DAY.isoformat()


# ---------------------------------------------------------------- dans l'agent (graphe complet)
@pytest.fixture
def graph_with():
    pytest.importorskip("langgraph")
    pytest.importorskip("outfit_engine")

    def factory(weather, loader=fixture_loader):
        return sa.build_graph(llm=None, wardrobe_loader=loader, today=lambda: TODAY, weather=weather)
    return factory


def test_all_sources_down_never_break_the_turn(graph_with):
    weather = robust([(n, down(name=n, error=urllib.error.URLError("getaddrinfo failed")))
                      for n in ("Open-Meteo", "MET Norway", "wttr.in")])
    state = run(graph_with(weather), "Une tenue pour aller à l'université")
    assert state["outfits"] and state["request"]["season"] == "autumn"
    assert "Météo indisponible, saison estimée d'après la date." in state["response"]


def test_unexpected_provider_output_never_breaks_the_turn(graph_with):
    state = run(graph_with(lambda city, day: {"t_min": None, "t_max": "chaud"}), "Une tenue pour le travail")
    assert state["outfits"] and "Météo indisponible" in state["response"]


def test_trace_names_the_source_that_answered(graph_with):
    weather = robust([("Open-Meteo", down(name="Open-Meteo")), ("MET Norway", ok(3, 8))])
    state = run(graph_with(weather), "Une tenue pour le travail")
    line = next(t for t in state["trace"] if t.startswith("get_weather"))
    assert "MET Norway" in line and "Open-Meteo" in line and state["request"]["season"] == "winter"
    assert state["weather"]["source"] == "MET Norway"


def test_rain_at_63_percent_puts_an_outer_layer_in_every_outfit(graph_with):
    state = run(graph_with(ok(12, 18, rain=63)), "Une tenue pour aller à l'université")
    wardrobe = {item["id"]: item for item in fixture_loader()[0]}
    assert state["outfits"]
    for outfit in state["outfits"]:
        assert any(sa.is_rain_outerwear(wardrobe[i]) for i in sa._outfit_ids(outfit))
    assert "Pluie probable (63 %) : chaque tenue comprend une veste ou un manteau." in state["response"]
    assert "ne tient pas encore compte" not in state["response"]


def test_rain_code_alone_triggers_the_constraint(graph_with):
    state = run(graph_with(ok(12, 18, rain=None, rain_code=True)), "Une tenue pour aller à l'université")
    assert "Pluie annoncée : chaque tenue comprend une veste ou un manteau." in state["response"]


def test_light_rain_chance_keeps_outfits_unconstrained(graph_with):
    state = run(graph_with(ok(12, 18, rain=30)), "Une tenue pour aller à l'université")
    assert state["rain_plan"] == {} and "Pluie" not in state["response"]


def test_rain_without_outer_layer_suggests_an_umbrella(graph_with):
    def no_outerwear():
        wardrobe, report = fixture_loader()
        return [i for i in wardrobe if i["category"] not in {"jacket", "coat", "blazer", "cardigan"}], report
    state = run(graph_with(ok(12, 18, rain=80), loader=no_outerwear), "Une tenue pour aller à l'université")
    assert state["outfits"] and "Pluie probable (80 %) : prévois un parapluie" in state["response"]


def test_rain_removes_suede_and_silk_when_the_material_is_known(graph_with):
    def with_fragile():
        wardrobe, report = fixture_loader()
        silk = {**next(i for i in wardrobe if i["category"] == "shirt"), "id": "silk-1", "name": "Silk Shirt",
                "material": "100% silk"}
        unknown = {**silk, "id": "plain-1", "name": "Plain Shirt", "material": None}
        return wardrobe + [silk, unknown], report
    state = run(graph_with(ok(12, 18, rain=70), loader=with_fragile), "Une tenue pour aller à l'université")
    assert state["rain_plan"]["fragile_excluded"] == ["Silk Shirt"]
    assert all("silk-1" not in sa._outfit_ids(o) for o in state["outfits"])
    assert "Écarté à cause de la pluie (daim, soie) : Silk Shirt." in state["response"]


def test_rain_does_not_change_engine_scores(graph_with):
    """La pluie filtre les tenues ; les scores du moteur BO4 restent ceux qu'il a calculés."""
    import outfit_engine
    state = run(graph_with(ok(12, 18, rain=63)), "Une tenue pour aller à l'université")
    candidates = {i["id"]: i for i in fixture_loader()[0]}
    for outfit in state["outfits"]:
        items = [candidates[i] for i in sa._outfit_ids(outfit)]
        expected = outfit_engine.evaluate_outfit(items, "university", state["request"]["season"])["score"]
        assert outfit["score"] == expected


# ---------------------------------------------------------------- API web du Stylist
def test_api_chat_answers_200_whatever_the_weather_does():
    testclient = pytest.importorskip("fastapi.testclient")
    import stylist_web

    def exploding(city, day):
        raise RuntimeError("erreur inattendue de la météo")
    try:
        for provider in (exploding, lambda city, day: {"t_min": None, "t_max": None}):
            stylist_web.configure(llm=None, loader=fixture_loader, today=lambda: TODAY, weather=provider)
            response = testclient.TestClient(stylist_web.app).post("/api/chat",
                                                                   json={"message": "Une tenue pour le travail"})
            assert response.status_code == 200
            assert response.json()["outfits"] and response.json()["weather"]["unavailable"] is True
    finally:
        stylist_web.configure()


def test_page_payload_names_the_weather_source():
    testclient = pytest.importorskip("fastapi.testclient")
    import stylist_web
    weather = robust([("Open-Meteo", down(name="Open-Meteo")), ("MET Norway", ok(12, 18, rain=63))])
    try:
        stylist_web.configure(llm=None, loader=fixture_loader, today=lambda: TODAY, weather=weather)
        data = testclient.TestClient(stylist_web.app).post(
            "/api/chat", json={"message": "Une tenue pour le travail"}).json()
        assert data["weather"]["source"] == "MET Norway" and "api.met.no" in data["weather"]["attribution"]
    finally:
        stylist_web.configure()


def test_wttr_patchy_rain_possible_alone_is_not_announced_rain():
    sample = {"weather": [{"date": DAY.isoformat(), "mintempC": "15", "maxtempC": "23",
                           "hourly": [{"chanceofrain": "31", "weatherCode": "176"},
                                      {"chanceofrain": "10", "weatherCode": "116"}]}]}
    forecast = ws.wttr_forecast("Tunis", DAY, get=lambda url, params, timeout: sample)
    assert forecast["rain_code"] is False and forecast["rain_probability"] == 31


def test_met_norway_one_hour_shower_does_not_override_dry_six_hour_periods():
    sample = {"properties": {"timeseries": [
        {"time": f"{DAY.isoformat()}T06:00:00Z", "data": {
            "instant": {"details": {"air_temperature": 12}},
            "next_1_hours": {"summary": {"symbol_code": "lightrainshowers_day"}},
            "next_6_hours": {"summary": {"symbol_code": "partlycloudy_day"}}}}]}}
    assert ws.met_norway_forecast("Tunis", DAY, get=lambda url, params, timeout: sample)["rain_code"] is False
