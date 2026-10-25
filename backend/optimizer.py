"""SciPy silhouette fitting over MPFB macro + detail controls.

Each objective evaluation runs Blender once: it applies the candidate targets,
exports a GLB, and renders transparent front/side masks in the same process.
The photo masks arrive as base64 PNG data URLs from the browser. Both sides are
normalized to a 512 px tall canvas before comparison, so the optimizer fits
shape rather than camera distance.
"""

from __future__ import annotations

import base64
import io
import json
import math
import re
import subprocess
import time
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image
from scipy.optimize import minimize

AVATAR_RESULT_RE = re.compile(r"^AVATAR_RESULT (\{.*\})$", flags=re.MULTILINE)
PROFILE_BINS = 32
CANVAS = 512

MACRO_VARS = ("weight", "muscle", "proportions", "legLength")
DETAIL_VARS = (
    ("shoulders", "measure-shoulder-dist-incr", "measure-shoulder-dist-decr"),
    ("waist", "measure-waist-circ-incr", "measure-waist-circ-decr"),
    ("hips", "measure-hips-circ-incr", "measure-hips-circ-decr"),
    ("chestDepth", "measure-frontchest-dist-incr", "measure-frontchest-dist-decr"),
    ("torsoDepth", "torso-scale-depth-incr", "torso-scale-depth-decr"),
    ("hipWidth", "hip-scale-horiz-incr", "hip-scale-horiz-decr"),
    ("hipDepth", "hip-scale-depth-incr", "hip-scale-depth-decr"),
    ("belly", "stomach-navel-out", "stomach-navel-in"),
    ("buttocks", "buttocks-volume-incr", "buttocks-volume-decr"),
    ("thigh", "measure-thigh-circ-incr", "measure-thigh-circ-decr"),
    ("calf", "measure-calf-circ-incr", "measure-calf-circ-decr"),
)
MANAGED_DETAILS = {name for _, incr, decr in DETAIL_VARS for name in (incr, decr)}


class OptimizerError(Exception):
    pass


def _clamp(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))


def _round(value: float) -> float:
    return round(float(value), 4)


def _bounds(initial: list[float]) -> list[tuple[float, float]]:
    bounds: list[tuple[float, float]] = []
    for index, value in enumerate(initial):
        if index < len(MACRO_VARS):
            low = 0.1 if MACRO_VARS[index] == "legLength" else 0.15
            high = 0.9 if MACRO_VARS[index] == "legLength" else 0.85
            bounds.append((low, high))
        else:
            bounds.append((-0.75, 0.75))
    return bounds


def initial_vector(targets: dict, details: dict) -> list[float]:
    vector = [float(targets.get(name, 0.5)) for name in MACRO_VARS]
    for _key, incr, decr in DETAIL_VARS:
        value = float(details.get(incr, 0.0)) - float(details.get(decr, 0.0))
        vector.append(_clamp(value, -0.75, 0.75))
    return vector


def vector_to_payload(
    vector: list[float],
    base_targets: dict,
    base_details: dict,
) -> tuple[dict, dict]:
    targets = {key: float(value) for key, value in base_targets.items()}
    for index, name in enumerate(MACRO_VARS):
        targets[name] = _round(_clamp(vector[index], 0.0, 1.0))

    details = {
        key: float(value)
        for key, value in base_details.items()
        if key not in MANAGED_DETAILS
    }
    offset = len(MACRO_VARS)
    for index, (_key, incr, decr) in enumerate(DETAIL_VARS):
        value = _clamp(vector[offset + index], -0.75, 0.75)
        if abs(value) < 1e-3:
            continue
        details[incr if value > 0 else decr] = _round(abs(value))
    return targets, details


def _load_mask(path: str | Path) -> np.ndarray:
    image = Image.open(path).convert("RGBA")
    data = np.array(image)
    mask = data[:, :, 3] > 127
    if not mask.any():
        mask = data[:, :, :3].mean(axis=2) < 240
    return mask


def _load_data_url(data_url: str) -> np.ndarray:
    if not isinstance(data_url, str) or "," not in data_url:
        raise OptimizerError("Silhouette masks must be base64 PNG data URLs")
    header, encoded = data_url.split(",", 1)
    if "base64" not in header:
        raise OptimizerError("Silhouette masks must use base64 encoding")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise OptimizerError("Could not decode a silhouette mask") from exc
    try:
        image = Image.open(io.BytesIO(raw)).convert("RGBA")
    except Exception as exc:
        raise OptimizerError("Could not open a silhouette mask") from exc
    data = np.array(image)
    mask = data[:, :, 3] > 127
    if not mask.any():
        mask = data[:, :, :3].mean(axis=2) < 240
    return mask


def _normalize(mask: np.ndarray) -> np.ndarray:
    ys, xs = np.where(mask)
    if len(ys) == 0:
        raise OptimizerError("A silhouette mask is empty")
    crop = mask[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
    height, width = crop.shape
    scale = CANVAS / max(height, width)
    new_width = max(1, int(round(width * scale)))
    new_height = max(1, int(round(height * scale)))
    resized = np.array(
        Image.fromarray((crop * 255).astype(np.uint8)).resize(
            (new_width, new_height), Image.NEAREST
        )
    ) > 127

    canvas = np.zeros((CANVAS, CANVAS), dtype=bool)
    x0 = (CANVAS - new_width) // 2
    y0 = CANVAS - new_height
    canvas[y0 : y0 + new_height, x0 : x0 + new_width] = resized
    return canvas


def _iou(a: np.ndarray, b: np.ndarray) -> float:
    union = np.logical_or(a, b).sum()
    return float(np.logical_and(a, b).sum() / union) if union else 0.0


def _width_profile(mask: np.ndarray) -> np.ndarray:
    rows = mask.sum(axis=1).astype(np.float64) / mask.shape[1]
    chunks = np.array_split(rows, PROFILE_BINS)
    return np.array([chunk.mean() for chunk in chunks])


def _profile_rmse(a: np.ndarray, b: np.ndarray) -> float:
    return float(math.sqrt(float(np.mean((a - b) ** 2))))


def _score(
    photo_front: np.ndarray,
    photo_side: np.ndarray,
    avatar_front: np.ndarray,
    avatar_side: np.ndarray,
) -> tuple[float, dict]:
    iou_front = _iou(photo_front, avatar_front)
    iou_side = _iou(photo_side, avatar_side)
    rmse_front = _profile_rmse(_width_profile(photo_front), _width_profile(avatar_front))
    rmse_side = _profile_rmse(_width_profile(photo_side), _width_profile(avatar_side))

    shape_error = 0.6 * (1.0 - iou_front) + 0.4 * (1.0 - iou_side)
    profile_error = (rmse_front + rmse_side) / 2.0
    score = shape_error + profile_error * 6.0
    return score, {
        "iouFront": round(iou_front, 4),
        "iouSide": round(iou_side, 4),
        "profileRmseFront": round(rmse_front, 4),
        "profileRmseSide": round(rmse_side, 4),
    }


def _run_blender(
    vector: list[float],
    base_targets: dict,
    base_details: dict,
    config: dict,
    work_dir: Path,
    index: int,
) -> tuple[float, dict, Path, dict, dict, dict]:
    targets, details = vector_to_payload(vector, base_targets, base_details)

    params_path = work_dir / f"eval_{index}_params.json"
    details_path = work_dir / f"eval_{index}_details.json"
    glb_path = work_dir / f"eval_{index}.glb"
    sil_prefix = work_dir / f"eval_{index}_sil"
    params_path.write_text(json.dumps(targets), encoding="utf-8")
    details_path.write_text(json.dumps(details), encoding="utf-8")

    cmd = [
        str(config["blender"]),
        "--background",
        str(config["avatar_blend"]),
        "--python",
        str(config["script"]),
        "--",
        "--params",
        str(params_path),
        "--details",
        str(details_path),
        "--silhouettes",
        str(sil_prefix),
        "--output",
        str(glb_path),
    ]
    if config.get("height_cm") is not None:
        cmd.extend(["--height-cm", str(config["height_cm"])])
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=int(config.get("eval_timeout", 120)),
            shell=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise OptimizerError("Blender timed out during an optimization evaluation") from exc

    combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
    matches = AVATAR_RESULT_RE.findall(combined)
    result = {}
    if matches:
        try:
            result = json.loads(matches[-1])
        except json.JSONDecodeError:
            result = {}
    if proc.returncode != 0 or not result.get("ok"):
        tail = "\n".join(combined.strip().splitlines()[-6:])
        raise OptimizerError(f"Blender evaluation failed: {result.get('error') or tail}")

    silhouettes = result.get("silhouettes") or {}
    if "front" not in silhouettes or "side" not in silhouettes:
        raise OptimizerError("Blender did not write the front/side silhouettes")

    photo_front = config["photo_front_norm"]
    photo_side = config["photo_side_norm"]
    avatar_front = _normalize(_load_mask(silhouettes["front"]))
    avatar_side = _normalize(_load_mask(silhouettes["side"]))
    score, metrics = _score(photo_front, photo_side, avatar_front, avatar_side)
    return score, targets, glb_path, details, metrics, result.get("metrics") or {}


def optimize(
    initial_targets: dict,
    initial_details: dict,
    photo_silhouettes: dict[str, str],
    config: dict,
    max_evaluations: int = 48,
    progress: Callable[[dict], None] | None = None,
) -> dict:
    if "front" not in photo_silhouettes or "side" not in photo_silhouettes:
        raise OptimizerError("Both front and side silhouette masks are required")

    config = dict(config)
    config["photo_front"] = _load_data_url(photo_silhouettes["front"])
    config["photo_side"] = _load_data_url(photo_silhouettes["side"])
    config["photo_front_norm"] = _normalize(config["photo_front"])
    config["photo_side_norm"] = _normalize(config["photo_side"])

    work_dir = Path(config["work_dir"])
    work_dir.mkdir(parents=True, exist_ok=True)

    x0 = initial_vector(initial_targets, initial_details)
    bounds = _bounds(x0)
    starts = [float(value) for value in x0]
    cache: dict[tuple[float, ...], tuple] = {}
    started = time.monotonic()
    best: tuple | None = None

    def evaluate(vector) -> float:
        nonlocal best
        key = tuple(round(float(value), 3) for value in vector)
        if key in cache:
            return cache[key][0]

        index = len(cache) + 1
        score, targets, glb_path, details, fit, metrics = _run_blender(
            [float(value) for value in vector],
            initial_targets,
            initial_details,
            config,
            work_dir,
            index,
        )
        regression = float(
            np.mean(
                [
                    ((float(vector[i]) - starts[i]) / max(1e-6, bounds[i][1] - bounds[i][0])) ** 2
                    for i in range(len(vector))
                ]
            )
        )
        score += regression * 0.08
        entry = (score, targets, glb_path, details, fit, metrics)
        cache[key] = entry
        if best is None or score < best[0]:
            best = entry
        if progress:
            progress(
                {
                    "evaluations": len(cache),
                    "maxEvaluations": max_evaluations,
                    "bestScore": round(float(best[0]), 5),
                    "latest": fit,
                }
            )
        return score

    result = minimize(
        evaluate,
        x0,
        method="Powell",
        bounds=bounds,
        options={
            "maxfev": max_evaluations,
            "xtol": 0.03,
            "ftol": 0.003,
            "disp": False,
        },
    )

    if best is None:
        raise OptimizerError("The optimizer did not complete a single evaluation")

    score, targets, glb_path, details, fit, metrics = best
    return {
        "ok": True,
        "score": round(float(score), 5),
        "fit": fit,
        "targets": targets,
        "details": details,
        "glbPath": str(glb_path),
        "metrics": metrics,
        "evaluations": len(cache),
        "maxEvaluations": max_evaluations,
        "elapsedSeconds": round(time.monotonic() - started, 1),
        "scipy": {
            "success": bool(result.success),
            "message": str(result.message),
            "iterations": int(result.nit),
            "functionEvaluations": int(result.nfev),
        },
    }
