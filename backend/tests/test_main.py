import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import main  # noqa: E402

client = TestClient(main.app)


def test_validate_targets_accepts_leg_length():
    cleaned = main.validate_targets({"muscle": 0.62, "legLength": 0.7})
    assert cleaned == {"muscle": 0.62, "legLength": 0.7}


@pytest.mark.parametrize(
    "targets",
    [
        {},
        {"unknown": 0.5},
        {"height": 1.2},
        {"weight": -0.1},
        {"weight": "heavy"},
        {"weight": True},
    ],
)
def test_validate_targets_rejects_invalid_input(targets):
    with pytest.raises(HTTPException) as exc:
        main.validate_targets(targets)
    assert exc.value.status_code == 422


def test_validate_outfit_dedupes_and_keeps_slot_order():
    cleaned = main.validate_outfit(["trousers", "tshirt", "trousers", "boots"])
    assert cleaned == ["trousers", "tshirt", "boots"]


def test_validate_outfit_rejects_unknown_garment():
    with pytest.raises(HTTPException):
        main.validate_outfit(["cape"])


def test_validate_outfit_rejects_dress_with_top_or_bottom():
    with pytest.raises(HTTPException):
        main.validate_outfit(["dress", "tshirt"])


def test_validate_outfit_rejects_two_items_in_same_slot():
    with pytest.raises(HTTPException):
        main.validate_outfit(["trousers", "jeans"])


def test_validate_outfit_allows_full_layered_look():
    outfit = ["trousers", "oxford", "blazer", "boots"]
    assert main.validate_outfit(outfit) == outfit


def test_health_reports_catalog():
    result = main.health()
    assert result["ok"] is True
    assert "tshirt" in result["allowedGarments"]
    assert "boots" in result["allowedGarments"]
    assert "dress" in result["slots"]


def test_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert "trousers" in body["allowedGarments"]


def test_generate_rejects_invalid_outfit_before_running_blender():
    response = client.post(
        "/api/avatar/generate",
        json={"targets": {"muscle": 0.5}, "outfit": ["dress", "tshirt"]},
    )
    assert response.status_code == 422
    assert "dress" in response.json()["detail"].lower()


def test_generate_accepts_height_cm():
    req = main.GenerateRequest(targets={"muscle": 0.5}, height_cm=172)
    assert req.height_cm == 172


def test_generate_rejects_out_of_range_height_cm():
    response = client.post(
        "/api/avatar/generate",
        json={"targets": {"muscle": 0.5}, "height_cm": 300},
    )
    assert response.status_code == 422


def test_is_valid_glb(tmp_path):
    valid = tmp_path / "model.glb"
    valid.write_bytes(b"glTF" + b"0" * 2000)
    assert main.is_valid_glb(valid) is True

    invalid = tmp_path / "bad.glb"
    invalid.write_bytes(b"nope" + b"0" * 2000)
    assert main.is_valid_glb(invalid) is False
