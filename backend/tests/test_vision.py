import sys
from pathlib import Path

from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import main  # noqa: E402
import vision  # noqa: E402

client = TestClient(main.app)


def test_vision_status_reports_configuration(monkeypatch):
    monkeypatch.setattr(vision, "OPENAI_API_KEY", "sk-test")
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["visionConfigured"] is True


def test_vision_route_returns_cleaned_analysis(monkeypatch):
    async def fake_analyze(front_bytes, front_type, side_bytes, side_type, height_cm):
        assert front_bytes == b"front-image"
        assert side_bytes == b"side-image"
        assert height_cm == 170
        return {
            "ok": True,
            "model": "gpt-test",
            "analysis": {
                "body_shape": "pear",
                "confidence": 0.8,
                "targets": {"weight": 0.6, "legLength": 0.55},
                "detail_values": {"hips": 0.2},
                "photo_quality": {"front": 0.8, "side": 0.7, "notes": []},
                "posture": {},
                "observations": {},
                "notes": [],
            },
            "createdAt": 1,
        }

    monkeypatch.setattr(vision, "analyze_photos", fake_analyze)
    response = client.post(
        "/api/body/vision",
        files={
            "front": ("front.jpg", b"front-image", "image/jpeg"),
            "side": ("side.jpg", b"side-image", "image/jpeg"),
        },
        data={"height_cm": "170"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["analysis"]["body_shape"] == "pear"
    assert body["analysis"]["targets"]["weight"] == 0.6
    assert body["analysis"]["detail_values"]["hips"] == 0.2


def test_vision_route_requires_both_photos():
    response = client.post(
        "/api/body/vision",
        files={"front": ("front.jpg", b"front-image", "image/jpeg")},
        data={"height_cm": "170"},
    )
    assert response.status_code == 422


def test_vision_route_rejects_non_image(monkeypatch):
    monkeypatch.setattr(vision, "OPENAI_API_KEY", "sk-test")
    response = client.post(
        "/api/body/vision",
        files={
            "front": ("front.txt", b"front-image", "text/plain"),
            "side": ("side.jpg", b"side-image", "image/jpeg"),
        },
        data={"height_cm": "170"},
    )
    assert response.status_code == 422


def test_vision_route_reports_missing_key(monkeypatch):
    monkeypatch.setattr(vision, "OPENAI_API_KEY", "")
    response = client.post(
        "/api/body/vision",
        files={
            "front": ("front.jpg", b"front-image", "image/jpeg"),
            "side": ("side.jpg", b"side-image", "image/jpeg"),
        },
        data={"height_cm": "170"},
    )
    assert response.status_code == 503


def test_clean_analysis_clamps_and_filters():
    cleaned = vision._clean_analysis(
        {
            "body_shape": "banana",
            "photo_quality": {"front": 2, "side": -1, "notes": ["blurry"]},
            "posture": {"shoulders": "level"},
            "observations": {
                "waist": {"relative": "narrow", "confidence": 2},
                "bogus": {"relative": "wide", "confidence": 1},
            },
            "confidence": 2,
            "targets": {"weight": 2, "bogus": 0.5},
            "detail_values": {"waist": 5, "hips": -0.4, "bogus": 0.5},
            "notes": ["clothing hides the waist"],
        }
    )
    assert cleaned["body_shape"] == "unknown"
    assert cleaned["confidence"] == 1.0
    assert cleaned["photo_quality"]["front"] == 1.0
    assert cleaned["photo_quality"]["side"] == 0.0
    assert cleaned["observations"]["waist"]["confidence"] == 1.0
    assert "bogus" not in cleaned["observations"]
    assert cleaned["targets"] == {"weight": 1.0}
    assert cleaned["detail_values"] == {"waist": 1.0, "hips": -0.4}
