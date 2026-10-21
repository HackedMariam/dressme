"""API integration tests for the DressMe Trip Agent backend."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app

SAMPLE_TEXT = (
    "I'm going to Paris for 5 days for sightseeing, shopping, and a formal "
    "dinner. My clothing luggage limit is 8 kg."
)
DATES = "June 3-7, 2027"


@pytest.fixture()
def client() -> TestClient:
    app = create_app(use_llm=False, allow_weather_network=False)
    with TestClient(app) as test_client:
        yield test_client


def create_complete_trip(client: TestClient) -> dict:
    response = client.post(
        "/api/trips",
        json={
            "mode": "structured",
            "trip": {
                "destination": "Paris",
                "start_date": "2027-06-03",
                "end_date": "2027-06-07",
                "activities": ["sightseeing", "shopping", "formal-dinner"],
                "max_luggage_weight_kg": 8,
            },
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_health_and_cors_preflight(client: TestClient) -> None:
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.json()["gap_agent"] == "mock"

    preflight = client.options(
        "/api/trips",
        headers={
            "Origin": "http://localhost:8443",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers.get("access-control-allow-origin") == "http://localhost:8443"


def test_text_trip_clarification_then_optimized_capsule(client: TestClient) -> None:
    created = client.post(
        "/api/trips",
        json={"mode": "text", "text": SAMPLE_TEXT},
    )
    assert created.status_code == 200, created.text
    payload = created.json()
    assert payload["status"] == "needs_clarification"
    assert "start_date" in payload["missing_info"]
    assert payload["trip_details"]["destination"] == "Paris"
    session_id = payload["session_id"]

    resumed = client.post(
        f"/api/trips/{session_id}/messages",
        json={"text": DATES},
    )
    assert resumed.status_code == 200, resumed.text
    payload = resumed.json()
    assert payload["status"] == "optimized"
    assert payload["weather"]["source"] == "synthetic_fallback"
    assert payload["weather"]["warning"]
    assert len(payload["daily_requirements"]) == 5
    assert payload["capsule"]["optimization_status"] in {"OPTIMAL", "FEASIBLE"}
    assert len(payload["capsule"]["days"]) == 5
    assert payload["capsule"]["selected_items"]
    assert payload["checklist"]["items"]
    assert all(item["packed"] is False for item in payload["checklist"]["items"])

    state = client.get(f"/api/trips/{session_id}")
    assert state.status_code == 200
    assert state.json()["capsule"]["number_of_items"] == len(
        payload["capsule"]["selected_items"]
    )


def test_manual_structured_trip_and_weather_requirements_endpoints(
    client: TestClient,
) -> None:
    payload = create_complete_trip(client)
    session_id = payload["session_id"]

    weather = client.post(
        f"/api/trips/{session_id}/weather",
        json={"force_refresh": False},
    )
    assert weather.status_code == 200, weather.text
    assert weather.json()["result"]["source"] == "synthetic_fallback"

    requirements = client.post(f"/api/trips/{session_id}/requirements")
    assert requirements.status_code == 200, requirements.text
    result = requirements.json()["result"]
    assert len(result["requirements"]) == 5
    assert result["requirements"][0]["required_style"] in {
        "casual",
        "smart-casual",
        "formal",
        "sporty",
    }

    capsule = client.get(f"/api/trips/{session_id}/capsule")
    assert capsule.status_code == 200
    assert capsule.json()["capsule"]["days"]


def test_checklist_update_does_not_rerun_optimizer(client: TestClient) -> None:
    payload = create_complete_trip(client)
    session_id = payload["session_id"]
    item_id = payload["checklist"]["items"][0]["item_id"]
    runs_before = payload["optimization_runs"]

    updated = client.patch(
        f"/api/trips/{session_id}/checklist/{item_id}",
        json={"packed": True},
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["checklist"]["items"][0]["packed"] is True
    assert body["checklist"]["packed_items"] == 1
    assert body["optimizer_rerun"] is False
    assert body["optimization_runs"] == runs_before

    checklist = client.get(f"/api/trips/{session_id}/checklist")
    assert checklist.status_code == 200
    assert checklist.json()["checklist"]["packed_items"] == 1


def test_trip_update_infeasible_recovery_and_reoptimization(
    client: TestClient,
) -> None:
    payload = create_complete_trip(client)
    session_id = payload["session_id"]
    runs_before = payload["optimization_runs"]

    infeasible = client.patch(
        f"/api/trips/{session_id}",
        json={
            "updates": {"max_luggage_weight_kg": 0.3},
            "reoptimize": True,
        },
    )
    assert infeasible.status_code == 200, infeasible.text
    body = infeasible.json()
    assert body["status"] == "infeasible"
    assert body["suggestions"]
    assert body["optimization_runs"] > runs_before

    fixed = client.patch(
        f"/api/trips/{session_id}",
        json={
            "updates": {"max_luggage_weight_kg": 8},
            "reoptimize": True,
        },
    )
    assert fixed.status_code == 200, fixed.text
    body = fixed.json()
    assert body["status"] == "optimized"
    assert body["capsule"]["trip"]["max_luggage_weight_kg"] == 8


def test_update_activities_regenerates_requirements(client: TestClient) -> None:
    payload = create_complete_trip(client)
    session_id = payload["session_id"]

    updated = client.patch(
        f"/api/trips/{session_id}",
        json={
            "updates": {"activities": ["sightseeing", "shopping"]},
            "reoptimize": True,
        },
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert "formal-dinner" not in body["trip_details"]["activities"]
    assert all(
        "formal-dinner" not in requirement["activities"]
        for requirement in body["daily_requirements"]
    )


def test_optional_mock_gap_analysis(client: TestClient) -> None:
    payload = create_complete_trip(client)
    session_id = payload["session_id"]

    gap = client.post(f"/api/trips/{session_id}/gap-analysis")
    assert gap.status_code == 200, gap.text
    body = gap.json()
    analysis = body["gap_analysis"]
    assert analysis["available"] is True
    assert analysis["findings"]["provider"] == "mock_gap_agent"
    assert "gaps" in analysis["findings"]
    assert body["capsule"]["selected_items"]


def test_missing_session_returns_404(client: TestClient) -> None:
    response = client.get("/api/trips/does-not-exist")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_structured_incomplete_asks_for_missing_fields(client: TestClient) -> None:
    response = client.post(
        "/api/trips",
        json={
            "mode": "structured",
            "trip": {
                "destination": "Rome",
                "duration_days": 3,
                "activities": ["sightseeing"],
            },
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "needs_clarification"
    assert "start_date" in body["missing_info"]
    assert "max_luggage_weight_kg" in body["missing_info"]


def test_capsule_and_checklist_not_ready_return_404(client: TestClient) -> None:
    created = client.post(
        "/api/trips",
        json={"mode": "text", "text": SAMPLE_TEXT},
    )
    session_id = created.json()["session_id"]

    capsule = client.get(f"/api/trips/{session_id}/capsule")
    assert capsule.status_code == 404
    checklist = client.get(f"/api/trips/{session_id}/checklist")
    assert checklist.status_code == 404
