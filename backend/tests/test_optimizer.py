import base64
import io
import sys
from pathlib import Path

import numpy as np
import pytest
from fastapi import HTTPException
from PIL import Image

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import main  # noqa: E402
import optimizer  # noqa: E402


def mask_data_url() -> str:
    image = Image.new("RGBA", (64, 96), (0, 0, 0, 0))
    pixels = np.array(image)
    pixels[8:88, 18:46] = (255, 255, 255, 255)
    buffer = io.BytesIO()
    Image.fromarray(pixels).save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


def test_initial_vector_and_payload_roundtrip():
    vector = optimizer.initial_vector(
        {"weight": 0.6, "muscle": 0.4, "proportions": 0.5, "legLength": 0.55},
        {"measure-waist-circ-decr": 0.2, "measure-hips-circ-incr": 0.15},
    )
    targets, details = optimizer.vector_to_payload(
        vector,
        {"height": 0.5, "weight": 0.6, "muscle": 0.4, "proportions": 0.5, "legLength": 0.55},
        {"age": 0.3},
    )
    assert targets["height"] == 0.5
    assert targets["weight"] == 0.6
    assert details["age"] == 0.3
    assert details["measure-waist-circ-decr"] == pytest.approx(0.2)
    assert details["measure-hips-circ-incr"] == pytest.approx(0.15)


def test_mask_normalization_and_identical_score():
    mask = optimizer._load_data_url(mask_data_url())
    normalized = optimizer._normalize(mask)
    assert normalized.shape == (512, 512)
    score, fit = optimizer._score(normalized, normalized, normalized, normalized)
    assert score == pytest.approx(0.0, abs=1e-9)
    assert fit["iouFront"] == 1.0
    assert fit["iouSide"] == 1.0


def test_mask_iou_detects_difference():
    mask = optimizer._normalize(optimizer._load_data_url(mask_data_url()))
    shifted = np.zeros_like(mask)
    shifted[:, 20:] = mask[:, :-20]
    assert 0.0 < optimizer._iou(mask, shifted) < 1.0


def test_bad_silhouette_url_is_rejected():
    with pytest.raises(optimizer.OptimizerError):
        optimizer._load_data_url("not-a-data-url")


def test_optimize_loop_with_mocked_blender(monkeypatch, tmp_path):
    calls = {"count": 0}

    def fake_run(vector, base_targets, base_details, config, work_dir, index):
        calls["count"] += 1
        return (
            0.2 + abs(float(vector[0]) - 0.5),
            {"height": 0.5},
            Path(config["work_dir"]) / f"eval_{index}.glb",
            {},
            {"iouFront": 0.8, "iouSide": 0.8, "profileRmseFront": 0.01, "profileRmseSide": 0.01},
            {},
        )

    monkeypatch.setattr(optimizer, "_run_blender", fake_run)
    result = optimizer.optimize(
        {"height": 0.5, "weight": 0.5},
        {},
        {"front": mask_data_url(), "side": mask_data_url()},
        {"work_dir": str(tmp_path)},
        max_evaluations=2,
    )
    assert result["ok"] is True
    assert result["evaluations"] >= 1
    assert result["targets"]["height"] == 0.5
    assert calls["count"] >= 1


def test_optimize_request_validation():
    with pytest.raises(HTTPException) as exc:
        main.start_optimize(
            main.OptimizeRequest(
                targets={"weight": 0.5},
                details={},
                silhouettes={"front": "nope", "side": "nope"},
            )
        )
    assert exc.value.status_code == 422


def test_validate_silhouettes_rejects_missing_side():
    with pytest.raises(HTTPException) as exc:
        main._validate_silhouettes({"front": mask_data_url()})
    assert exc.value.status_code == 422
