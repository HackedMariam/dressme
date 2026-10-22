"""Local questionnaire-to-measurement estimator and MPFB target mapping.

The 8-question sizing flow is answered in the browser and turned into a
consistent set of body measurements here. No photo, API key, or network call is
involved. `measurements_to_targets` then maps those measurements onto the MPFB
parameters used by the Blender avatar generator.
"""

from __future__ import annotations

import time

BODY_SHAPES = {"hourglass", "rectangle", "inverted_triangle", "pear", "apple"}
CUP_DELTAS_CM = {"A": 10.0, "B": 12.5, "C": 15.0, "D": 17.5, "E": 20.0, "F": 22.5}
MODEL_NAME = "local-questionnaire"


def is_configured() -> bool:
    return True


def _clamp01(value: float) -> float:
    return min(1.0, max(0.0, value))


def _round(value: float) -> float:
    return round(value, 2)


def _num(measurements: dict, key: str, default: float) -> float:
    try:
        value = float(measurements.get(key))
    except (TypeError, ValueError):
        return default
    return value if value == value else default


def _optional_num(measurements: dict, key: str) -> float | None:
    try:
        value = float(measurements.get(key))
    except (TypeError, ValueError):
        return None
    return value if value == value else None


def _choice(questionnaire: dict, key: str, allowed: tuple[str, ...], default: str) -> str:
    value = str(questionnaire.get(key) or default)
    return value if value in allowed else default


def _level(questionnaire: dict, key: str, default: int = 2) -> int:
    try:
        value = int(questionnaire.get(key, default))
    except (TypeError, ValueError):
        return default
    return min(3, max(1, value))


def _shape_scale(shape: str) -> dict[str, float]:
    if shape == "hourglass":
        return {"shoulder": 1.0, "bust": 1.04, "waist": 0.93, "hip": 1.04, "thigh": 1.0}
    if shape == "rectangle":
        return {"shoulder": 1.02, "bust": 0.99, "waist": 1.03, "hip": 0.98, "thigh": 1.0}
    if shape == "inverted_triangle":
        return {"shoulder": 1.06, "bust": 1.02, "waist": 1.0, "hip": 0.96, "thigh": 0.98}
    if shape == "pear":
        return {"shoulder": 0.96, "bust": 0.98, "waist": 0.98, "hip": 1.06, "thigh": 1.04}
    return {"shoulder": 1.0, "bust": 1.03, "waist": 1.08, "hip": 0.98, "thigh": 1.0}


def estimate_measurements(questionnaire: dict) -> dict:
    """Derive a coherent measurement set from the questionnaire answers.

    The formulas are anthropometric approximations, not a tape measure. They are
    deterministic: the same answers always produce the same avatar, and every
    value stays inside a plausible adult range.
    """
    height_cm = min(220.0, max(140.0, _num(questionnaire, "height_cm", 170.0)))
    mass_kg = min(200.0, max(30.0, _num(questionnaire, "mass_kg", 65.0)))
    gender = _choice(questionnaire, "gender", ("female", "male"), "female")
    shape = _choice(questionnaire, "body_shape", tuple(BODY_SHAPES), "hourglass")
    belly = _level(questionnaire, "belly")
    build = _level(questionnaire, "build")
    legs = _level(questionnaire, "legs")
    arms = _level(questionnaire, "arms")
    cup = _choice(questionnaire, "cupsize", tuple(CUP_DELTAS_CM), "")

    bmi = mass_kg / ((height_cm / 100.0) ** 2)
    bmi_offset = bmi - 22.0
    width_scale = min(1.12, max(0.92, 1.0 + bmi_offset * 0.003))
    build_scale = (0.96, 1.0, 1.04)[build - 1]
    shape_scale = _shape_scale(shape)

    if gender == "male":
        shoulder = height_cm * 0.255 * width_scale * build_scale * shape_scale["shoulder"]
        bust = height_cm * (0.52 + bmi_offset * 0.010) * build_scale * shape_scale["bust"]
        underbust = None
    else:
        shoulder = height_cm * 0.23 * width_scale * build_scale * shape_scale["shoulder"]
        bust = height_cm * (0.52 + bmi_offset * 0.010) * build_scale * shape_scale["bust"]
        cup_delta = CUP_DELTAS_CM[cup] if cup else CUP_DELTAS_CM["B"]
        underbust = max(55.0, bust - cup_delta)

    waist = height_cm * (0.40 + bmi_offset * 0.015) * shape_scale["waist"]
    waist *= 1.0 + 0.04 * (belly - 1)
    if shape == "apple":
        waist *= 1.03

    hip = height_cm * (0.55 + bmi_offset * 0.010) * shape_scale["hip"]
    inseam = height_cm * (0.46 + 0.012 * (legs - 2))
    thigh = height_cm * (0.29 + bmi_offset * 0.010) * shape_scale["thigh"]
    thigh *= 1.0 + 0.015 * (legs - 2)
    upperarm = height_cm * (0.155 + bmi_offset * 0.007) * build_scale
    upperarm *= 1.0 + 0.02 * (arms - 2)
    neck = height_cm * (0.19 + bmi_offset * 0.004) * build_scale
    calf = height_cm * (0.21 + bmi_offset * 0.008)
    wrist = height_cm * 0.10

    measurements: dict[str, float] = {
        "height_cm": _round(height_cm),
        "bust_cm": _round(max(60.0, bust)),
        "waist_cm": _round(max(45.0, waist)),
        "hip_cm": _round(max(60.0, hip)),
        "shoulder_width_cm": _round(max(28.0, shoulder)),
        "inseam_cm": _round(max(55.0, inseam)),
        "thigh_cm": _round(max(35.0, thigh)),
        "upperarm_cm": _round(max(18.0, upperarm)),
        "neck_cm": _round(max(25.0, neck)),
        "calf_cm": _round(max(24.0, calf)),
        "wrist_cm": _round(max(13.0, wrist)),
        "mass_kg": _round(mass_kg),
        "bmi": _round(bmi),
    }
    if underbust is not None:
        measurements["underbust_cm"] = _round(underbust)
    return measurements


def scan_questionnaire(questionnaire: dict) -> dict:
    measurements = estimate_measurements(questionnaire)
    return {
        "measurements": measurements,
        "params": questionnaire,
        "model": MODEL_NAME,
        "createdAt": int(time.time()),
    }


def height_from_cm(cm: float) -> float:
    return _round(_clamp01(0.5 + (cm - 170.0) / 60.0))


def measurements_to_targets(measurements: dict) -> dict:
    height_cm = min(220.0, max(140.0, _num(measurements, "height_cm", 170.0)))
    inseam = _num(measurements, "inseam_cm", height_cm * 0.47)
    shoulder = _num(measurements, "shoulder_width_cm", height_cm * 0.235)
    hip = _num(measurements, "hip_cm", height_cm * 0.58)
    waist = _num(measurements, "waist_cm", height_cm * 0.46)
    bust = _num(measurements, "bust_cm", height_cm * 0.53)
    upperarm = _num(measurements, "upperarm_cm", height_cm * 0.17)
    thigh = _num(measurements, "thigh_cm", height_cm * 0.32)
    underbust = _optional_num(measurements, "underbust_cm")

    bmi = _optional_num(measurements, "bmi")
    if bmi is None:
        mass = _optional_num(measurements, "mass_kg")
        bmi = mass / ((height_cm / 100.0) ** 2) if mass else 22.0

    leg_fraction = inseam / height_cm if height_cm > 0 else 0.47
    leg_length = _clamp01(0.5 + (leg_fraction - 0.48) * 5.0)

    hip_width = max(hip / 3.0, 1.0)
    shoulder_to_hip = min(2.4, max(0.6, shoulder / hip_width))

    muscle = _clamp01(
        0.5
        + (upperarm / height_cm - 0.17) * 2.5
        + (thigh / height_cm - 0.32) * 1.5
        + (shoulder / height_cm - 0.235) * 1.0
    )
    weight = _clamp01(0.5 + (bmi - 22.0) / 12.0)
    waist_to_hip = waist / hip if hip > 0 else 0.8
    proportions = _clamp01(0.5 - (waist_to_hip - 0.8) * 2.0)

    targets: dict[str, float] = {
        "height": height_from_cm(height_cm),
        "legLength": _round(leg_length),
        "muscle": _round(muscle),
        "weight": _round(weight),
        "proportions": _round(proportions),
    }
    if underbust is not None and bust > 0:
        targets["cupsize"] = _round(_clamp01((bust - underbust) / 25.0))

    ratios: dict[str, float | None] = {
        "shoulderToHip": round(shoulder_to_hip, 3),
        "legFraction": round(leg_fraction, 3),
        "torsoToLeg": round((height_cm - inseam) / inseam, 3) if inseam > 0 else None,
        "waistToHip": round(waist_to_hip, 3),
    }

    notes = [
        "Measurements are estimated from the questionnaire answers, not measured directly.",
        "Shoulder-to-hip is approximated from shoulder width and hip circumference (hip width ≈ hip circumference / 3).",
        "Leg length comes from inseam / height; the torso-to-leg display uses (height − inseam) / inseam.",
        "Cup size is estimated from bust − underbust when both values are available.",
        "Use the sliders to refine the result before generating the avatar.",
    ]

    return {"targets": targets, "ratios": ratios, "notes": notes}
