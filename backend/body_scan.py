"""Clad Body Model API client and measurement-to-MPFB mapping.

The hosted Clad API turns a photo + height (or an 8-question form) into
ISO 8559-1 measurements. The API key is read from the repo-root `.env`
and is never sent to the browser.

Docs: https://api.clad.you/openapi.json
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

import httpx


def _load_env() -> None:
    """Load CLAD_* keys from the repo-root .env (and backend/.env if present)."""
    for path in (
        Path(__file__).resolve().parent.parent / ".env",
        Path(__file__).resolve().parent / ".env",
    ):
        if not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8-sig").splitlines()
        except OSError:
            continue
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if not key.startswith("CLAD_"):
                continue
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


_load_env()

CLAD_API_BASE = os.environ.get("CLAD_API_BASE_URL", "https://api.clad.you").rstrip("/")
CLAD_API_KEY = os.environ.get("CLAD_API_KEY", "")
CLAD_TIMEOUT_SECONDS = float(os.environ.get("CLAD_TIMEOUT_SECONDS", "120"))
CLAD_POLL_SECONDS = float(os.environ.get("CLAD_POLL_SECONDS", "1.5"))
CACHE_DIR = Path(
    os.environ.get(
        "CLAD_CACHE_DIR",
        str(Path(__file__).resolve().parent / "temp" / "clad_cache"),
    )
)

ALLOWED_PHOTO_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_PHOTO_BYTES = 20 * 1024 * 1024
CACHE_VERSION = "v2"


class CladError(Exception):
    def __init__(self, message: str, status_code: int = 502, payload: dict | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.payload = payload or {}


def is_configured() -> bool:
    return bool(CLAD_API_KEY)


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {CLAD_API_KEY}"}


def _absolute_url(url: str) -> str:
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return f"{CLAD_API_BASE}{url if url.startswith('/') else '/' + url}"


def _cache_key(data: bytes, height_cm: float, extra: str = "") -> str:
    digest = hashlib.sha256()
    digest.update(data)
    digest.update(str(round(height_cm, 1)).encode("utf-8"))
    digest.update(extra.encode("utf-8"))
    return digest.hexdigest()


def _read_cache(key: str) -> dict | None:
    path = CACHE_DIR / f"{key}.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _write_cache(key: str, payload: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{key}.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    tmp.replace(path)


def _error_from_response(response: httpx.Response) -> CladError:
    try:
        body: Any = response.json()
    except ValueError:
        body = {}

    message = f"Clad API HTTP {response.status_code}"
    payload: dict = body if isinstance(body, dict) else {}
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict):
            message = str(error.get("message") or error.get("code") or message)
            bucket = error.get("bucket")
            resets_at = error.get("resets_at")
            if bucket:
                message += f" (bucket: {bucket}"
                if resets_at:
                    message += f", resets at {resets_at}"
                message += ")"
        elif body.get("detail"):
            message = str(body["detail"])
    return CladError(message, response.status_code, payload)


async def _request(client: httpx.AsyncClient, method: str, url: str, **kwargs: Any) -> httpx.Response:
    try:
        response = await client.request(method, url, headers=_headers(), **kwargs)
    except httpx.HTTPError as exc:
        raise CladError(f"Could not reach Clad: {exc}", 502) from exc
    if response.status_code >= 400:
        raise _error_from_response(response)
    return response


async def scan_photo(
    image_bytes: bytes,
    filename: str,
    content_type: str,
    height_cm: float,
) -> dict:
    if not is_configured():
        raise CladError(
            "CLAD_API_KEY is not configured. Add it to the repo-root .env.",
            503,
        )

    cache_key = _cache_key(image_bytes, height_cm, f"{CACHE_VERSION}-clad-photo")
    cached = _read_cache(cache_key)
    if cached:
        return {**cached, "cached": True}

    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=15.0)) as client:
        response = await _request(
            client,
            "POST",
            f"{CLAD_API_BASE}/v1/body/from-photo",
            files={"photo": (filename or "photo.jpg", image_bytes, content_type or "image/jpeg")},
            data={"height_cm": f"{height_cm:.1f}"},
        )
        job = response.json()
        job_id = job.get("job_id")
        poll_url = job.get("poll_url") or f"/v1/jobs/{job_id}"
        quota = job.get("quota")
        if not job_id:
            raise CladError("Clad did not return a job id", 502, job)

        deadline = time.monotonic() + CLAD_TIMEOUT_SECONDS
        result: dict | None = None
        while time.monotonic() < deadline:
            await asyncio.sleep(CLAD_POLL_SECONDS)
            poll = await _request(client, "GET", _absolute_url(str(poll_url)))
            body = poll.json()
            status = body.get("status")
            if status == "completed":
                result = body.get("result") or {}
                break
            if status == "failed":
                error = body.get("error") or {}
                raise CladError(str(error.get("message") or "Clad photo job failed"), 502, body)

        if result is None:
            raise CladError("Clad photo job timed out", 504)

    measurements = result.get("measurements") or {}
    if not measurements:
        raise CladError("Clad returned no measurements", 502, result)
    measurements = calibrate_measurements(measurements, height_cm)

    payload = {
        "measurements": measurements,
        "params": result.get("params"),
        "model": "clad-body-photo",
        "quota": quota,
        "cached": False,
        "createdAt": int(time.time()),
    }
    _write_cache(cache_key, payload)
    return payload


async def scan_questionnaire(questionnaire: dict) -> dict:
    if not is_configured():
        raise CladError(
            "CLAD_API_KEY is not configured. Add it to the repo-root .env.",
            503,
        )

    body_json = json.dumps(questionnaire, sort_keys=True, separators=(",", ":"))
    cache_key = _cache_key(
        body_json.encode("utf-8"),
        float(questionnaire.get("height_cm", 0.0)),
        f"{CACHE_VERSION}-clad-questionnaire",
    )
    cached = _read_cache(cache_key)
    if cached:
        return {**cached, "cached": True}

    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=15.0)) as client:
        response = await _request(
            client,
            "POST",
            f"{CLAD_API_BASE}/v1/body/from-questionnaire",
            json=questionnaire,
        )
        body = response.json()

    measurements = body.get("measurements") or {}
    if not measurements:
        raise CladError("Clad returned no measurements", 502, body)

    input_height = float(questionnaire.get("height_cm", 0.0) or 0.0)
    raw_mass = questionnaire.get("mass_kg")
    input_mass = (
        float(raw_mass)
        if isinstance(raw_mass, (int, float)) and not isinstance(raw_mass, bool)
        else None
    )
    measurements = calibrate_measurements(measurements, input_height, input_mass)

    payload = {
        "measurements": measurements,
        "params": body.get("params"),
        "model": "clad-body-questionnaire",
        "quota": body.get("quota"),
        "cached": False,
        "createdAt": int(time.time()),
    }
    _write_cache(cache_key, payload)
    return payload


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


def calibrate_measurements(
    measurements: dict,
    height_cm: float,
    mass_kg: float | None = None,
) -> dict:
    """Scale Clad's generated body to the height the user actually entered.

    The hosted questionnaire model currently returns a body whose measured
    height can differ from the requested height. Rescaling keeps the avatar,
    inseam, and BMI consistent with the user's known height.
    """
    calibrated = {key: value for key, value in measurements.items()}
    returned_height = _optional_num(measurements, "height_cm")
    if returned_height and returned_height > 0 and height_cm > 0:
        scale = height_cm / returned_height
        if abs(scale - 1.0) > 1e-3:
            for key, value in list(calibrated.items()):
                if key.endswith("_cm") and isinstance(value, (int, float)):
                    calibrated[key] = float(value) * scale
                elif key == "volume_m3" and isinstance(value, (int, float)):
                    calibrated[key] = float(value) * (scale**3)
            if mass_kg is None and isinstance(calibrated.get("mass_kg"), (int, float)):
                calibrated["mass_kg"] = float(calibrated["mass_kg"]) * (scale**3)

    calibrated["height_cm"] = float(height_cm)
    if mass_kg is not None:
        calibrated["mass_kg"] = float(mass_kg)
    if isinstance(calibrated.get("mass_kg"), (int, float)) and height_cm > 0:
        calibrated["bmi"] = float(calibrated["mass_kg"]) / ((height_cm / 100.0) ** 2)
    return calibrated


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

    # Clad gives hip circumference, not hip width. A circle approximation
    # (width ~ circumference / 3) keeps the same scale as our MPFB ratio.
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
        "Shoulder-to-hip is approximated from shoulder width and hip circumference (hip width ≈ hip circumference / 3).",
        "Leg length comes from inseam / height; the torso-to-leg display uses (height − inseam) / inseam.",
        "Cup size is estimated from bust − underbust when both values are available.",
        "A single photo scan is an estimate, not a tape measure. Use the sliders to refine the result.",
    ]

    return {"targets": targets, "ratios": ratios, "notes": notes}
