import asyncio
import os
import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import body_scan  # noqa: E402
import main  # noqa: E402

client = TestClient(main.app)

SAMPLE_MEASUREMENTS = {
    "height_cm": 170,
    "bust_cm": 90,
    "underbust_cm": 78,
    "waist_cm": 74,
    "hip_cm": 100,
    "shoulder_width_cm": 40,
    "inseam_cm": 80,
    "thigh_cm": 56,
    "upperarm_cm": 30,
    "bmi": 22.5,
}


def test_height_from_cm():
    assert body_scan.height_from_cm(170) == 0.5
    assert body_scan.height_from_cm(140) == 0.0
    assert body_scan.height_from_cm(200) == 1.0


def test_calibrate_measurements_scales_to_input_height():
    raw = {
        "height_cm": 187.03,
        "inseam_cm": 90.76,
        "mass_kg": 70.52,
        "bmi": 18.86,
        "volume_m3": 0.07,
    }
    calibrated = body_scan.calibrate_measurements(raw, 170, 65)
    assert calibrated["height_cm"] == 170
    assert calibrated["mass_kg"] == 65
    assert calibrated["bmi"] == pytest.approx(65 / (1.7**2), abs=1e-3)
    assert calibrated["inseam_cm"] < raw["inseam_cm"]
    assert calibrated["volume_m3"] < raw["volume_m3"]


def test_measurements_to_targets_is_bounded():
    result = body_scan.measurements_to_targets(SAMPLE_MEASUREMENTS)
    targets = result["targets"]

    assert targets["height"] == 0.5
    for key in ("legLength", "muscle", "weight", "proportions", "cupsize"):
        assert 0.0 <= targets[key] <= 1.0
    assert result["ratios"]["shoulderToHip"] > 0
    assert result["ratios"]["legFraction"] == pytest.approx(80 / 170, abs=1e-3)
    assert result["ratios"]["torsoToLeg"] == pytest.approx(90 / 80, abs=1e-3)


def test_measurements_to_targets_handles_missing_values():
    result = body_scan.measurements_to_targets({"height_cm": 165})
    assert 0.0 <= result["targets"]["muscle"] <= 1.0
    assert "cupsize" not in result["targets"]


def test_cache_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(body_scan, "CACHE_DIR", tmp_path)
    body_scan._write_cache("abc", {"measurements": {"bust_cm": 90}})
    assert body_scan._read_cache("abc") == {"measurements": {"bust_cm": 90}}
    assert body_scan._read_cache("missing") is None


def test_error_from_response_includes_quota_details():
    response = httpx.Response(
        429,
        json={
            "error": {
                "code": "quota_exceeded",
                "message": "Weekly photo quota exhausted",
                "bucket": "photo",
                "resets_at": "2026-10-26T00:00:00Z",
            }
        },
    )
    error = body_scan._error_from_response(response)
    assert error.status_code == 429
    assert "photo" in error.message
    assert "2026-10-26" in error.message


def test_body_status_reports_configured(monkeypatch):
    monkeypatch.setattr(body_scan, "CLAD_API_KEY", "ck_live_test")
    response = client.get("/api/body/status")
    assert response.status_code == 200
    assert response.json() == {"configured": True, "source": "clad"}


def test_body_scan_requires_api_key(monkeypatch):
    monkeypatch.setattr(body_scan, "CLAD_API_KEY", "")
    response = client.post(
        "/api/body/scan",
        files={"photo": ("person.jpg", b"fake-image", "image/jpeg")},
        data={"height_cm": "170"},
    )
    assert response.status_code == 503


def test_body_scan_rejects_non_image(monkeypatch):
    monkeypatch.setattr(body_scan, "CLAD_API_KEY", "ck_live_test")
    response = client.post(
        "/api/body/scan",
        files={"photo": ("person.txt", b"not-an-image", "text/plain")},
        data={"height_cm": "170"},
    )
    assert response.status_code == 422


def test_body_scan_rejects_bad_height(monkeypatch):
    monkeypatch.setattr(body_scan, "CLAD_API_KEY", "ck_live_test")
    response = client.post(
        "/api/body/scan",
        files={"photo": ("person.jpg", b"fake-image", "image/jpeg")},
        data={"height_cm": "100"},
    )
    assert response.status_code == 422


def test_body_scan_route_maps_measurements(monkeypatch):
    async def fake_scan_photo(image_bytes, filename, content_type, height_cm):
        assert image_bytes == b"fake-image"
        assert height_cm == 170
        return {
            "measurements": SAMPLE_MEASUREMENTS,
            "model": "clad-body-photo",
            "cached": True,
            "quota": {"photo": {"limit": 10, "used_this_week": 1}},
        }

    monkeypatch.setattr(body_scan, "CLAD_API_KEY", "ck_live_test")
    monkeypatch.setattr(body_scan, "scan_photo", fake_scan_photo)

    response = client.post(
        "/api/body/scan",
        files={"photo": ("person.jpg", b"fake-image", "image/jpeg")},
        data={"height_cm": "170"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["cached"] is True
    assert body["targets"]["height"] == 0.5
    assert body["measurements"]["bust_cm"] == 90
    assert body["quota"]["photo"]["limit"] == 10


def test_questionnaire_route_maps_measurements(monkeypatch):
    async def fake_scan_questionnaire(payload):
        assert payload["height_cm"] == 170
        assert payload["body_shape"] == "hourglass"
        return {
            "measurements": SAMPLE_MEASUREMENTS,
            "model": "clad-body-questionnaire",
            "cached": False,
            "quota": {"questionnaire": {"limit": 50, "used_this_week": 2}},
        }

    monkeypatch.setattr(body_scan, "CLAD_API_KEY", "ck_live_test")
    monkeypatch.setattr(body_scan, "scan_questionnaire", fake_scan_questionnaire)

    response = client.post(
        "/api/body/questionnaire",
        json={
            "height_cm": 170,
            "mass_kg": 65,
            "gender": "female",
            "body_shape": "hourglass",
            "belly": 2,
            "build": 2,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "clad-body-questionnaire"
    assert body["targets"]["weight"] is not None


def test_questionnaire_validation():
    response = client.post(
        "/api/body/questionnaire",
        json={
            "height_cm": 100,
            "mass_kg": 65,
            "gender": "female",
            "body_shape": "hourglass",
            "belly": 2,
            "build": 2,
        },
    )
    assert response.status_code == 422


@pytest.mark.skipif(
    not os.environ.get("RUN_LIVE_CLAD"),
    reason="Set RUN_LIVE_CLAD=1 to spend one questionnaire API call.",
)
def test_live_questionnaire():
    result = asyncio.run(
        body_scan.scan_questionnaire(
            {
                "height_cm": 170,
                "mass_kg": 65,
                "gender": "female",
                "body_shape": "hourglass",
                "belly": 2,
                "build": 2,
                "legs": 2,
                "arms": 2,
            }
        )
    )
    assert result["measurements"]
    assert result["measurements"].get("height_cm")
