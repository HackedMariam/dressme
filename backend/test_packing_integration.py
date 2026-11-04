"""Packing integration against a simulated BO1 boundary and forecast."""
import json
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from packing_backend.trip_agent.schemas import WeatherData, WeatherDay


@pytest.fixture
def setup(monkeypatch):
    items = json.loads((Path(__file__).parents[1] / "bo4/backend/tests/fixtures/bo1_items_sample.json").read_text(encoding="utf-8"))
    users = {"Bearer alice": "alice", "Bearer bob": "bob"}

    class Response:
        def __init__(self, status, data):
            self.status_code, self.ok, self.data = status, status == 200, data
        def json(self):
            return self.data

    def bo1(url, headers, timeout):
        user = users.get(headers.get("Authorization"))
        if not user:
            return Response(401, {})
        return Response(200, {"id": user} if url.endswith("/api/me") else list(items))

    def forecast(destination, start, end, allow_network):
        days = [WeatherDay(date=start + timedelta(days=i), weather="cloudy", temperature_c=20,
                           precipitation_mm=0, source="open-meteo", synthetic=False)
                for i in range((end - start).days + 1)]
        return WeatherData(destination=destination, days=days, source="open-meteo")

    monkeypatch.setattr("backend.main.requests.get", bo1)
    monkeypatch.setattr("packing_backend.trip_agent.tools.fetch_weather", forecast)
    app = create_app(use_llm=False)
    with TestClient(app) as client:
        yield client, items


def test_real_items_and_cross_user_isolation(setup):
    client, items = setup
    created = client.post("/api/trips", headers={"Authorization": "Bearer alice"}, json={
        "mode": "structured", "trip": {"destination": "Rome", "start_date": "2027-06-01",
        "end_date": "2027-06-02", "activities": ["sightseeing"], "max_luggage_weight_kg": 8},
        "user_id": "bob", "wardrobe_items": [{"id": "forged"}],
    })
    assert created.status_code == 200, created.text
    result = created.json()
    assert result["status"] == "optimized", result
    selected = result["capsule"]["selected_items"]
    assert selected and {i["item_id"] for i in selected} <= {i["id"] for i in items}
    assert all(i["weight_estimated"] for i in selected)
    assert result["capsule"]["metadata"]["compatibility_estimated"] is True
    session = result["session_id"]
    assert client.get(f"/api/trips/{session}", headers={"Authorization": "Bearer bob"}).status_code == 404
    assert client.delete(f"/api/trips/{session}", headers={"Authorization": "Bearer bob"}).status_code == 404
    assert client.get(f"/api/trips/{session}").status_code == 401


def test_empty_wardrobe(setup):
    client, items = setup
    items.clear()
    response = client.post("/api/trips", headers={"Authorization": "Bearer alice"},
                           json={"mode": "text", "text": "pack for Paris"})
    assert response.status_code == 422 and "empty" in response.json()["detail"]


def test_unavailable_weather_is_not_used_for_optimization(setup, monkeypatch):
    client, _ = setup
    from packing_backend.trip_agent.weather import _synthetic_weather
    monkeypatch.setattr("packing_backend.trip_agent.tools.fetch_weather",
                        lambda destination, start, end, allow_network:
                        _synthetic_weather(destination, start, end, "unavailable"))
    response = client.post("/api/trips", headers={"Authorization": "Bearer alice"}, json={
        "mode": "structured", "trip": {"destination": "Rome", "start_date": "2027-06-01",
        "end_date": "2027-06-02", "activities": ["sightseeing"], "max_luggage_weight_kg": 8}})
    body = response.json()
    assert body["status"] == "failed" and body["capsule"] is None
    assert "forecast is unavailable" in body["errors"][-1]


def test_reoptimization_refreshes_changed_wardrobe(setup):
    client, items = setup
    headers = {"Authorization": "Bearer alice"}
    response = client.post("/api/trips", headers=headers, json={"mode": "structured", "trip": {
        "destination": "Rome", "start_date": "2027-06-01", "end_date": "2027-06-02",
        "activities": ["sightseeing"], "max_luggage_weight_kg": 8}})
    body = response.json()
    assert body["status"] == "optimized"
    removed = body["capsule"]["selected_items"][0]["item_id"]
    items[:] = [item for item in items if item["id"] != removed]
    updated = client.patch(f"/api/trips/{body['session_id']}", headers=headers,
                           json={"updates": {"max_luggage_weight_kg": 9}, "reoptimize": True})
    assert updated.status_code == 200, updated.text
    result = updated.json()
    if result["capsule"]:
        assert removed not in {item["item_id"] for item in result["capsule"]["selected_items"]}


def test_text_followup_updates_existing_trip(setup):
    client, _ = setup
    headers = {"Authorization": "Bearer alice"}
    response = client.post("/api/trips", headers=headers, json={"mode": "structured", "trip": {
        "destination": "Rome", "start_date": "2027-06-01", "end_date": "2027-06-02",
        "activities": ["sightseeing"], "max_luggage_weight_kg": 8}})
    body = response.json()
    continued = client.post(f"/api/trips/{body['session_id']}/messages", headers=headers,
                            json={"text": "Change the luggage limit to 6 kg"})
    assert continued.status_code == 200, continued.text
    assert continued.json()["trip_details"]["max_luggage_weight_kg"] == 6
    assert continued.json()["optimization_runs"] > body["optimization_runs"]


def test_preflight_does_not_require_identity(setup):
    client, _ = setup
    response = client.options("/api/trips", headers={"Origin": "http://localhost:8443",
                              "Access-Control-Request-Method": "POST",
                              "Access-Control-Request-Headers": "authorization,content-type"})
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:8443"


def test_missing_raincoat_is_reported_and_covered_once_added(setup, monkeypatch):
    client, items = setup
    items[:] = [
        {"id": "shirt", "name": "Shirt", "category": "top"},
        {"id": "shirt-2", "name": "Second shirt", "category": "top"},
        {"id": "pants", "name": "Trousers", "category": "pants"},
        {"id": "shoes", "name": "Sneakers", "category": "shoe"},
    ]

    def forecast(destination, start, end, allow_network):
        days = [WeatherDay(date=start + timedelta(days=i), weather="rainy" if i == 1 else "cloudy",
                           temperature_c=15, precipitation_mm=2 if i == 1 else 0,
                           source="open-meteo", synthetic=False)
                for i in range((end - start).days + 1)]
        return WeatherData(destination=destination, days=days, source="open-meteo")

    monkeypatch.setattr("packing_backend.trip_agent.tools.fetch_weather", forecast)
    headers = {"Authorization": "Bearer alice"}
    created = client.post("/api/trips", headers=headers, json={"mode": "structured", "trip": {
        "destination": "Rome", "start_date": "2027-06-01", "end_date": "2027-06-02",
        "activities": ["sightseeing"], "max_luggage_weight_kg": 8}})
    assert created.status_code == 200, created.text
    body = created.json()
    # No raincoat: the weather still gets a plan made of the clothes owned, and the gap is reported.
    assert body["status"] == "optimized", body
    assert "rain" in body["capsule"]["metadata"]["unmet_needs"]
    session_id = body["session_id"]
    restored = client.get(f"/api/trips/{session_id}", headers=headers).json()
    assert restored["capsule"]["metadata"]["unmet_needs"] == body["capsule"]["metadata"]["unmet_needs"]

    items.append({"id": "rain-jacket", "name": "Yellow Hooded Rain Jacket", "category": "jacket",
                  "material": "waterproof fabric", "description": "A bright yellow hooded rain jacket made from waterproof fabric.",
                  "tags": ["rain jacket", "yellow", "hooded", "waterproof"]})
    retry = client.patch(f"/api/trips/{session_id}", headers=headers,
                         json={"updates": {}, "reoptimize": True})
    assert retry.status_code == 200, retry.text
    result = retry.json()
    assert result["session_id"] == session_id
    assert result["status"] == "optimized", result
    assert "rain-jacket" in {item["item_id"] for item in result["capsule"]["selected_items"]}
    assert "rain" not in result["capsule"]["metadata"]["unmet_needs"]    # the new jacket covers it
    assert result["missing_items"] == []


def test_missing_base_outfit_is_reported_with_alternatives(setup):
    client, items = setup
    items[:] = [{"id": "shoes", "name": "Sneakers", "category": "shoe"}]
    headers = {"Authorization": "Bearer alice"}
    response = client.post("/api/trips", headers=headers, json={"mode": "structured", "trip": {
        "destination": "Rome", "start_date": "2027-06-01", "end_date": "2027-06-02",
        "activities": ["sightseeing"], "max_luggage_weight_kg": 8}})
    body = response.json()
    assert body["status"] == "infeasible"
    assert [item["key"] for item in body["missing_items"]] == ["base_outfit"]
    assert "both a top and a bottom" in body["missing_items"][0]["note"]
    items.append({"id": "dress", "name": "Dress", "category": "dress"})
    retry = client.patch(f"/api/trips/{body['session_id']}", headers=headers,
                         json={"updates": {}, "reoptimize": True})
    assert retry.status_code == 200, retry.text
    assert retry.json()["status"] == "infeasible", retry.text
    assert [item["key"] for item in retry.json()["missing_items"]] == ["variety"]
    assert retry.json()["can_repeat_outfits"] is True

    repeated = client.patch(f"/api/trips/{body['session_id']}", headers=headers,
                            json={"updates": {"allow_outfit_repeats": True}, "reoptimize": True})
    assert repeated.status_code == 200, repeated.text
    result = repeated.json()
    assert result["status"] == "optimized", result
    assert result["capsule"]["metadata"]["allow_outfit_repeats"] is True
    assert result["capsule"]["days"][0]["outfit_item_ids"] == result["capsule"]["days"][1]["outfit_item_ids"]
    assert result["can_repeat_outfits"] is False


def test_allowing_repeats_persists_choice_and_reports_missing_rain_gear(setup, monkeypatch):
    client, items = setup
    items[:] = [{"id": "shirt", "name": "Shirt", "category": "top"},
                {"id": "pants", "name": "Trousers", "category": "pants"},
                {"id": "shoes", "name": "Sneakers", "category": "shoe"}]

    def rainy_forecast(destination, start, end, allow_network):
        days = [WeatherDay(date=start + timedelta(days=i), weather="rainy", temperature_c=15,
                           precipitation_mm=2, source="open-meteo")
                for i in range((end - start).days + 1)]
        return WeatherData(destination=destination, days=days, source="open-meteo")

    monkeypatch.setattr("packing_backend.trip_agent.tools.fetch_weather", rainy_forecast)
    headers = {"Authorization": "Bearer alice"}
    created = client.post("/api/trips", headers=headers, json={"mode": "structured", "trip": {
        "destination": "Rome", "start_date": "2027-06-01", "end_date": "2027-06-02",
        "activities": ["sightseeing"], "max_luggage_weight_kg": 8}}).json()
    session = created["session_id"]
    # One shirt for two days: without repeats there is no variety, and repeating is the way out.
    assert created["status"] == "infeasible" and created["can_repeat_outfits"] is True
    attempted = client.patch(f"/api/trips/{session}", headers=headers,
                             json={"updates": {"allow_outfit_repeats": True}, "reoptimize": True}).json()
    assert attempted["status"] == "optimized"
    assert attempted["trip_details"]["allow_outfit_repeats"] is True
    assert "rain" in attempted["capsule"]["metadata"]["unmet_needs"]

    items.append({"id": "coat", "name": "Waterproof jacket", "category": "jacket"})
    retried = client.patch(f"/api/trips/{session}", headers=headers,
                           json={"updates": {}, "reoptimize": True}).json()
    assert retried["status"] == "optimized", retried
    assert retried["trip_details"]["allow_outfit_repeats"] is True
    assert retried["capsule"]["metadata"]["allow_outfit_repeats"] is True
    assert "rain" not in retried["capsule"]["metadata"]["unmet_needs"]


@pytest.mark.parametrize("description, is_rainwear", [
    ("Waterproof rain jacket", True),
    ("Raincoat", True),
    ("Veste imperméable", True),
    ("Jacket that is not waterproof", False),
    ("Ordinary jacket", False),
])
def test_real_outerwear_rain_classification(description, is_rainwear):
    from packing_backend.optimizer import build_item_roles
    from packing_backend.trip_agent.wardrobe import BO1WardrobeProvider
    provider = BO1WardrobeProvider([{"id": "coat", "name": description, "category": "jacket"}])
    roles = build_item_roles(provider.load()[0])["coat"]
    assert "outerwear" in roles
    assert ("rain" in roles) is is_rainwear


@pytest.mark.parametrize("fields, is_rainwear", [
    ({"material": "waterproof fabric"}, True),
    ({"tags": ["hooded", "rain jacket"]}, True),
    ({"material": "water-resistant fabric"}, False),
    ({"material": "non-waterproof fabric", "tags": ["rain jacket"]}, False),
])
def test_outerwear_rain_classification_uses_material_and_tags(fields, is_rainwear):
    from packing_backend.optimizer import build_item_roles
    from packing_backend.trip_agent.wardrobe import BO1WardrobeProvider
    provider = BO1WardrobeProvider([{"id": "coat", "name": "Hooded jacket", "category": "jacket", **fields}])
    assert ("rain" in build_item_roles(provider.load()[0])["coat"]) is is_rainwear


def test_very_cold_trip_asks_for_sufficiently_warm_layer(setup, monkeypatch):
    client, items = setup
    items[:] = [
        {"id": "sweater", "name": "Light sweater", "category": "sweater", "warmth": 1},
        {"id": "pants", "name": "Trousers", "category": "pants"},
        {"id": "shoes", "name": "Boots", "category": "shoe"},
        {"id": "jacket", "name": "Coat", "category": "jacket"},
    ]
    monkeypatch.setattr("packing_backend.trip_agent.tools.fetch_weather", lambda destination, start, end, allow_network:
                        WeatherData(destination=destination, source="open-meteo", days=[
                            WeatherDay(date=start, weather="cold", temperature_c=4,
                                       precipitation_mm=0, source="open-meteo")]))
    headers = {"Authorization": "Bearer alice"}
    created = client.post("/api/trips", headers=headers, json={"mode": "structured", "trip": {
        "destination": "Rome", "start_date": "2027-06-01", "end_date": "2027-06-01",
        "activities": ["sightseeing"], "max_luggage_weight_kg": 8}}).json()
    assert created["status"] == "infeasible"
    warm = next(item for item in created["missing_items"] if item["key"] == "warm")
    assert "at least 3" in warm["note"]
    items[0]["warmth"] = 4
    retried = client.patch(f"/api/trips/{created['session_id']}", headers=headers,
                           json={"updates": {}, "reoptimize": True})
    assert retried.status_code == 200, retried.text
    assert retried.json()["status"] == "optimized", retried.text


def test_repeat_option_is_not_offered_when_weight_still_blocks(setup):
    client, items = setup
    items[:] = [{"id": "shoes", "name": "Sneakers", "category": "shoe"},
                {"id": "dress", "name": "Dress", "category": "dress"}]
    created = client.post("/api/trips", headers={"Authorization": "Bearer alice"},
                          json={"mode": "structured", "trip": {
                              "destination": "Rome", "start_date": "2027-06-01", "end_date": "2027-06-02",
                              "activities": ["sightseeing"], "max_luggage_weight_kg": 0.3}}).json()
    assert created["status"] == "infeasible"
    assert created["can_repeat_outfits"] is False
    assert not any(item["key"] == "variety" for item in created["missing_items"])
