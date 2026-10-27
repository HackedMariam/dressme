"""Optional GPT-4 Vision second opinion for the two-photo capture flow.

The model is only used for *relative* observations (narrow/average/broad) and
bounded detail-target hints. It is never treated as a tape measure, and its
suggestions are merged with the MediaPipe measurements rather than replacing
them. The API key is read from the repo-root `.env` and never reaches the
browser.
"""

from __future__ import annotations

import base64
import json
import os
import re
import time
from pathlib import Path
from typing import Any

import httpx


def _load_env() -> None:
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
            if not (key.startswith("OPENAI_") or key.startswith("LLM_")):
                continue
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


_load_env()

OPENAI_API_BASE = os.environ.get("OPENAI_API_BASE", "https://api.openai.com/v1").rstrip("/")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_VISION_MODEL = (
    os.environ.get("OPENAI_VISION_MODEL")
    or os.environ.get("LLM_MODEL")
    or "gpt-4o"
)
OPENAI_VISION_DETAIL = os.environ.get("LLM_IMAGE_DETAIL", "high")
OPENAI_TIMEOUT_SECONDS = float(os.environ.get("OPENAI_TIMEOUT_SECONDS", "90"))

ALLOWED_PHOTO_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_PHOTO_BYTES = 20 * 1024 * 1024
ALLOWED_SHAPES = {"hourglass", "rectangle", "inverted_triangle", "pear", "apple", "unknown"}
ALLOWED_DETAIL_KEYS = {
    "shoulders",
    "bust",
    "underbust",
    "waist",
    "hips",
    "waistToHip",
    "chestDepth",
    "torsoDepth",
    "vShape",
    "hipWidth",
    "hipDepth",
    "belly",
    "buttocks",
    "upperArm",
    "armLength",
    "thigh",
    "calf",
    "upperLegHeight",
    "lowerLegHeight",
}
OBSERVATION_KEYS = {
    "shoulders",
    "bust",
    "waist",
    "hips",
    "belly",
    "arms",
    "thighs",
    "calves",
    "legs",
}
ALLOWED_TARGET_KEYS = {
    "gender",
    "age",
    "muscle",
    "weight",
    "proportions",
    "cupsize",
    "firmness",
    "legLength",
}


class VisionError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def is_configured() -> bool:
    return bool(OPENAI_API_KEY)


def _clamp(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))


def _number(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number == number else default


def _data_url(data: bytes, content_type: str) -> str:
    return f"data:{content_type};base64,{base64.b64encode(data).decode('ascii')}"


PROMPT = """You are the body-shape analyst for a virtual try-on avatar.

Look at the front and side photos of the same person. The user's height is
{height_cm:.1f} cm, so do NOT estimate or return height in centimetres. Your job
is to choose MPFB avatar parameters from the *relative* shape you see.

Return one JSON object with exactly this structure:
{{
  "body_shape": "hourglass|rectangle|inverted_triangle|pear|apple|unknown",
  "confidence": 0.0,
  "photo_quality": {{"front": 0.0, "side": 0.0, "notes": ["..."]}},
  "posture": {{"shoulders": "...", "spine": "...", "stance": "...", "camera": "..."}},
  "observations": {{
    "shoulders": {{"relative": "narrow|average|broad", "confidence": 0.0}},
    "bust": {{"relative": "small|average|large", "confidence": 0.0}},
    "waist": {{"relative": "narrow|average|wide", "confidence": 0.0}},
    "hips": {{"relative": "narrow|average|wide", "confidence": 0.0}},
    "belly": {{"relative": "flat|average|projected", "confidence": 0.0}},
    "arms": {{"relative": "slim|average|full", "confidence": 0.0}},
    "thighs": {{"relative": "slim|average|full", "confidence": 0.0}},
    "calves": {{"relative": "slim|average|full", "confidence": 0.0}},
    "legs": {{"relative": "short|average|long", "confidence": 0.0}}
  }},
  "targets": {{
    "gender": 0.5, "age": 0.5, "muscle": 0.5, "weight": 0.5,
    "proportions": 0.5, "cupsize": 0.5, "firmness": 0.5, "legLength": 0.5
  }},
  "detail_values": {{
    "shoulders": 0.0, "bust": 0.0, "underbust": 0.0, "waist": 0.0,
    "hips": 0.0, "waistToHip": 0.0, "chestDepth": 0.0, "torsoDepth": 0.0,
    "vShape": 0.0, "hipWidth": 0.0, "hipDepth": 0.0, "belly": 0.0,
    "buttocks": 0.0, "upperArm": 0.0, "armLength": 0.0, "thigh": 0.0,
    "calf": 0.0, "upperLegHeight": 0.0, "lowerLegHeight": 0.0
  }},
  "notes": ["short, useful caveats"]
}}

Rules:
- All targets are 0.0-1.0, with 0.5 as neutral. gender: 0 feminine, 1 masculine.
  age: 0 young, 1 old. muscle/weight/proportions: 0 low, 1 high. cupsize and
  firmness are relative. legLength: 0 short, 1 long.
- All detail_values are -1.0 to 1.0, with 0 meaning no change, positive meaning
  larger/longer, and negative meaning smaller/shorter.
- confidence and every observation confidence are 0.0-1.0.
- Use the front photo for widths and the side photo for depth/posture.
- Do not return centimetres, do not claim exact measurements, and do not guess
  identity or sensitive attributes. If something is unclear, stay near 0.5/0.0
  and lower the confidence.
- Mention clothing, pose, camera angle, and lighting problems in the notes."""


def _clean_analysis(raw: dict) -> dict:
    shape = str(raw.get("body_shape") or "unknown").lower()
    if shape not in ALLOWED_SHAPES:
        shape = "unknown"

    quality = raw.get("photo_quality") if isinstance(raw.get("photo_quality"), dict) else {}
    quality_notes = quality.get("notes") if isinstance(quality.get("notes"), list) else []
    posture = raw.get("posture") if isinstance(raw.get("posture"), dict) else {}

    observations: dict[str, dict] = {}
    raw_observations = raw.get("observations") if isinstance(raw.get("observations"), dict) else {}
    for key, value in raw_observations.items():
        if key not in OBSERVATION_KEYS or not isinstance(value, dict):
            continue
        observations[key] = {
            "relative": str(value.get("relative") or "unknown")[:40],
            "confidence": round(_clamp(_number(value.get("confidence")), 0.0, 1.0), 3),
        }

    targets: dict[str, float] = {}
    raw_targets = raw.get("targets") if isinstance(raw.get("targets"), dict) else {}
    for key, value in raw_targets.items():
        if key not in ALLOWED_TARGET_KEYS:
            continue
        targets[key] = round(_clamp(_number(value, 0.5), 0.0, 1.0), 3)

    detail_values: dict[str, float] = {}
    raw_details = raw.get("detail_values") if isinstance(raw.get("detail_values"), dict) else {}
    if not raw_details and isinstance(raw.get("suggested_details"), dict):
        raw_details = raw["suggested_details"]
    for key, value in raw_details.items():
        if key not in ALLOWED_DETAIL_KEYS:
            continue
        number = _clamp(_number(value), -1.0, 1.0)
        if abs(number) >= 0.01:
            detail_values[key] = round(number, 2)

    notes = raw.get("notes") if isinstance(raw.get("notes"), list) else []
    return {
        "body_shape": shape,
        "confidence": round(_clamp(_number(raw.get("confidence"), 0.5), 0.0, 1.0), 3),
        "photo_quality": {
            "front": round(_clamp(_number(quality.get("front"), 0.0), 0.0, 1.0), 3),
            "side": round(_clamp(_number(quality.get("side"), 0.0), 0.0, 1.0), 3),
            "notes": [str(note)[:200] for note in quality_notes][:6],
        },
        "posture": {str(key)[:40]: str(value)[:120] for key, value in list(posture.items())[:8]},
        "observations": observations,
        "targets": targets,
        "detail_values": detail_values,
        "notes": [str(note)[:240] for note in notes][:8],
    }


async def analyze_photos(
    front_bytes: bytes,
    front_type: str,
    side_bytes: bytes,
    side_type: str,
    height_cm: float,
) -> dict:
    if not is_configured():
        raise VisionError("OPENAI_API_KEY is not configured. Add it to the repo-root .env.", 503)

    payload = {
        "model": OPENAI_VISION_MODEL,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": "You analyze body shape for a virtual try-on avatar. Return JSON only.",
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT.format(height_cm=height_cm)},
                    {
                        "type": "image_url",
                        "image_url": {"url": _data_url(front_bytes, front_type), "detail": OPENAI_VISION_DETAIL},
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": _data_url(side_bytes, side_type), "detail": OPENAI_VISION_DETAIL},
                    },
                ],
            },
        ],
    }

    async with httpx.AsyncClient(timeout=httpx.Timeout(OPENAI_TIMEOUT_SECONDS, connect=15.0)) as client:
        try:
            response = await client.post(
                f"{OPENAI_API_BASE}/chat/completions",
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                json=payload,
            )
        except httpx.HTTPError as exc:
            raise VisionError(f"Could not reach OpenAI: {exc}", 502) from exc

    if response.status_code >= 400:
        message = f"OpenAI HTTP {response.status_code}"
        try:
            body = response.json()
            error = body.get("error") if isinstance(body, dict) else None
            if isinstance(error, dict) and error.get("message"):
                message = str(error["message"])
        except ValueError:
            pass
        raise VisionError(message, response.status_code)

    try:
        content = response.json()["choices"][0]["message"]["content"]
        raw = json.loads(content)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise VisionError("OpenAI did not return valid JSON.", 502) from exc

    if not isinstance(raw, dict):
        raise VisionError("OpenAI returned an unexpected payload.", 502)

    return {
        "ok": True,
        "model": OPENAI_VISION_MODEL,
        "analysis": _clean_analysis(raw),
        "createdAt": int(time.time()),
    }
