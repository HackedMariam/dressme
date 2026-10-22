import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import main  # noqa: E402
import mpfb_details  # noqa: E402


def test_manifest_contains_silhouette_targets():
    assert "measure-waist-circ-incr" in mpfb_details.ALLOWED_DETAILS
    assert "measure-hips-circ-decr" in mpfb_details.ALLOWED_DETAILS
    assert "measure-shoulder-dist-incr" in mpfb_details.ALLOWED_DETAILS
    assert "measure-thigh-circ-incr" in mpfb_details.ALLOWED_DETAILS
    assert "measure-calf-circ-decr" in mpfb_details.ALLOWED_DETAILS
    assert "torso-scale-depth-incr" in mpfb_details.ALLOWED_DETAILS
    assert "buttocks-volume-incr" in mpfb_details.ALLOWED_DETAILS
    assert "gender" not in mpfb_details.ALLOWED_DETAILS


def test_manifest_categories_have_expected_shape():
    for category, names in mpfb_details.DETAIL_CATEGORIES.items():
        assert category
        assert names
        assert names == sorted(names)


def test_validate_details_cleans_values():
    cleaned = main.validate_details({"measure-waist-circ-incr": 0.4, "torso-scale-depth-decr": 0.25})
    assert cleaned == {"measure-waist-circ-incr": 0.4, "torso-scale-depth-decr": 0.25}


def test_validate_details_accepts_an_empty_object():
    assert main.validate_details({}) == {}


@pytest.mark.parametrize(
    "details",
    [
        {"not-a-real-target": 0.5},
        {"measure-waist-circ-incr": 1.2},
        {"measure-waist-circ-incr": -0.1},
        {"measure-waist-circ-incr": "wide"},
        {"measure-waist-circ-incr": True},
    ],
)
def test_validate_details_rejects_invalid_input(details):
    with pytest.raises(HTTPException) as exc:
        main.validate_details(details)
    assert exc.value.status_code == 422


def test_validate_details_rejects_too_many_targets():
    too_many = {name: 0.1 for name in list(mpfb_details.ALLOWED_DETAILS)[: mpfb_details.MAX_DETAILS + 1]}
    with pytest.raises(ValueError):
        mpfb_details.validate_details(too_many)
