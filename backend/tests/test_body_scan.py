import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import body_scan  # noqa: E402
import main  # noqa: E402

client = TestClient(main.app)

QUESTIONNAIRE = {
    "height_cm": 170,
    "mass_kg": 65,
    "gender": "female",
    "body_shape": "hourglass",
    "belly": 2,
    "build": 2,
    "legs": 2,
    "arms": 2,
}


def test_height_from_cm():
    assert body_scan.height_from_cm(170) == 0.5
    assert body_scan.height_from_cm(140) == 0.0
    assert body_scan.height_from_cm(200) == 1.0


def test_estimate_measurements_returns_expected_values():
    measurements = body_scan.estimate_measurements(QUESTIONNAIRE)

    assert measurements["height_cm"] == 170
    assert measurements["mass_kg"] == 65
    assert measurements["bmi"] == pytest.approx(65 / (1.7**2), abs=1e-2)
    for key in (
        "bust_cm",
        "waist_cm",
        "hip_cm",
        "shoulder_width_cm",
        "inseam_cm",
        "thigh_cm",
        "upperarm_cm",
        "underbust_cm",
    ):
        assert measurements[key] > 0


def test_measurements_to_targets_is_bounded():
    measurements = body_scan.estimate_measurements(QUESTIONNAIRE)
    result = body_scan.measurements_to_targets(measurements)

    for key in ("height", "legLength", "muscle", "weight", "proportions", "cupsize"):
        assert 0.0 <= result["targets"][key] <= 1.0
    assert result["ratios"]["shoulderToHip"] > 0
    assert result["ratios"]["waistToHip"] > 0
    assert result["ratios"]["torsoToLeg"] > 0


def test_measurements_to_targets_handles_missing_values():
    result = body_scan.measurements_to_targets({"height_cm": 165})
    assert 0.0 <= result["targets"]["muscle"] <= 1.0
    assert "cupsize" not in result["targets"]


def test_shape_changes_the_body_widths():
    hourglass = body_scan.estimate_measurements(QUESTIONNAIRE)
    rectangle = body_scan.estimate_measurements({**QUESTIONNAIRE, "body_shape": "rectangle"})
    pear = body_scan.estimate_measurements({**QUESTIONNAIRE, "body_shape": "pear"})
    apple = body_scan.estimate_measurements({**QUESTIONNAIRE, "body_shape": "apple"})

    assert rectangle["waist_cm"] > hourglass["waist_cm"]
    assert pear["hip_cm"] > hourglass["hip_cm"]
    assert apple["waist_cm"] > hourglass["waist_cm"]


def test_questionnaire_levels_change_the_measurements():
    low = body_scan.estimate_measurements(
        {**QUESTIONNAIRE, "belly": 1, "build": 1, "legs": 1, "arms": 1}
    )
    high = body_scan.estimate_measurements(
        {**QUESTIONNAIRE, "belly": 3, "build": 3, "legs": 3, "arms": 3}
    )

    assert high["waist_cm"] > low["waist_cm"]
    assert high["shoulder_width_cm"] > low["shoulder_width_cm"]
    assert high["inseam_cm"] > low["inseam_cm"]
    assert high["upperarm_cm"] > low["upperarm_cm"]


def test_male_questionnaire_does_not_estimate_a_cup_size():
    measurements = body_scan.estimate_measurements({**QUESTIONNAIRE, "gender": "male"})
    assert "underbust_cm" not in measurements
    assert "cupsize" not in body_scan.measurements_to_targets(measurements)["targets"]


def test_questionnaire_route_returns_applicable_targets():
    response = client.post("/api/body/questionnaire", json=QUESTIONNAIRE)

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["source"] == "local-questionnaire"
    assert body["measurements"]["height_cm"] == 170
    assert body["targets"]["height"] == 0.5
    main.validate_targets(body["targets"])


def test_questionnaire_validation():
    response = client.post(
        "/api/body/questionnaire",
        json={**QUESTIONNAIRE, "height_cm": 100},
    )
    assert response.status_code == 422


def test_measurements_route_maps_photo_values():
    response = client.post(
        "/api/body/measurements",
        json={
            "height_cm": 170,
            "bust_cm": 90,
            "waist_cm": 70,
            "hip_cm": 96,
            "shoulder_width_cm": 40,
            "inseam_cm": 80,
            "thigh_cm": 55,
            "upperarm_cm": 28,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "photo-measurements"
    assert body["measurements"]["height_cm"] == 170
    assert 0.0 <= body["targets"]["muscle"] <= 1.0
    assert body["ratios"]["shoulderToHip"] > 0
    main.validate_targets(body["targets"])


def test_measurements_route_rejects_bad_height():
    response = client.post("/api/body/measurements", json={"height_cm": 100})
    assert response.status_code == 422


def test_body_status_is_local():
    response = client.get("/api/body/status")
    assert response.status_code == 200
    assert response.json() == {"configured": True, "source": "local-questionnaire"}
