r"""
Local DressMe avatar-generation backend.

Runs Blender 5.4 headless with the MPFB2 extension to regenerate a body-shaped
GLB from avatar.blend. Bound to 127.0.0.1 only. No arbitrary paths or commands
are accepted from clients: only whitelisted MPFB parameter names and 0..1 floats.

Run:
  cd backend
  venv\Scripts\activate
  pip install -r requirements.txt
  uvicorn main:app --host 127.0.0.1 --port 8001
"""

import base64
import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import httpx
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import avatar_store
import body_scan
import mpfb_details
import optimizer
import settings
import tryon_mapping
import vision
from avatar_auth import User, current_user

BACKEND_DIR = Path(__file__).resolve().parent
BLENDER_PATH = os.environ.get(
    "BLENDER_PATH",
    r"C:\Users\maria\Downloads\blender-5.4.0-alpha+main.29ff43161222-windows.amd64-release\blender-5.4.0-alpha+main.29ff43161222-windows.amd64-release\blender.exe",
)
BLENDER_SCRIPT = BACKEND_DIR / "blender" / "generate_avatar.py"
DRESSED_BLENDER_SCRIPT = BACKEND_DIR / "blender" / "generate_dressed_avatar.py"
AVATAR_BLEND = os.environ.get(
    "AVATAR_BLEND",
    r"C:\Users\maria\Desktop\5eme esprit\avatar.blend",
)
GENERATED_DIR = Path(
    os.environ.get(
        "GENERATED_DIR",
        r"C:\Users\maria\Desktop\5eme esprit\Dressme\DressMe UI Blueprint\public\models\generated",
    )
)
TEMP_DIR = BACKEND_DIR / "temp"
JOB_TIMEOUT_SECONDS = int(os.environ.get("JOB_TIMEOUT_SECONDS", "300"))
GENERATED_TTL_HOURS = float(os.environ.get("GENERATED_TTL_HOURS", "24"))
CATALOG_PATH = BACKEND_DIR.parent / "DressMe UI Blueprint" / "src" / "lib" / "garments.json"
WARDROBE_API_URL = os.environ.get("WARDROBE_API_URL", "http://127.0.0.1:8000").rstrip("/")


def load_garment_catalog() -> tuple[dict[str, dict], list[str]]:
    with open(CATALOG_PATH, "r", encoding="utf-8-sig") as f:
        data = json.load(f)
    garments = {g["id"]: g for g in data["garments"]}
    slots = list(data.get("slots", []))
    return garments, slots


GARMENT_CATALOG, GARMENT_SLOTS = load_garment_catalog()
AVATAR_STORE = avatar_store.get_avatar_store(GENERATED_DIR)

ALLOWED_PARAMS = {
    "gender", "age", "muscle", "weight",
    "height", "proportions", "cupsize", "firmness",
    "legLength",
}
MAX_TARGETS = len(ALLOWED_PARAMS)

ALLOWED_GARMENTS = list(GARMENT_CATALOG)
MAX_GARMENTS = len(GARMENT_SLOTS)

_job_lock = threading.Lock()
_opt_jobs: dict[str, dict] = {}
_opt_jobs_lock = threading.Lock()
app = FastAPI(title="DressMe avatar backend", version="1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8443",
        "http://127.0.0.1:8443",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_methods=["POST", "GET", "DELETE"],
    allow_headers=["*"],
)


class WardrobeItemInput(BaseModel):
    wardrobe_item_id: str | None = None
    template: str | None = None
    slot: str | None = None
    label: str | None = None
    color_hex: str | None = None
    category: str | None = None
    category_group: str | None = None
    subcategory: str | None = None
    material: str | None = None
    formality: int | None = None
    cutout_url: str | None = None
    mesh_url: str | None = None
    mesh_version: int | None = None


class GenerateRequest(BaseModel):
    targets: dict[str, float] = Field(..., description="MPFB parameter name -> value in [0, 1]")
    details: dict[str, float] = Field(
        default_factory=dict,
        description="Optional MPFB detail target name -> value in [0, 1]",
    )
    outfit: list[str] = Field(default_factory=list, description="Legacy garment template ids")
    wardrobe_item_ids: list[str] = Field(
        default_factory=list,
        description="Wardrobe item ids selected by the user",
    )
    wardrobe_items: list[WardrobeItemInput] = Field(
        default_factory=list,
        description="Local-dev fallback item specs (ignored when Supabase lookup is available)",
    )
    height_cm: float | None = Field(
        None,
        ge=140,
        le=220,
        description="Declared user height in centimetres; the generated avatar is scaled to match",
    )


class SavedAvatarItem(BaseModel):
    wardrobe_item_id: str
    template: str
    slot: str
    label: str
    color_hex: str
    cutout_url: str | None = None
    mesh_url: str | None = None
    mesh_version: int = 0
    category: str = ""


class GenerateResponse(BaseModel):
    jobId: str
    url: str
    params: dict[str, float]
    details: dict[str, float]
    outfit: list[str]
    bytes: int
    elapsedSeconds: float
    metrics: dict[str, float] = Field(default_factory=dict)
    items: list[SavedAvatarItem] = Field(default_factory=list)
    saved: bool = False
    savedAt: str | None = None
    saveError: str | None = None


class QuestionnaireRequest(BaseModel):
    height_cm: float = Field(..., ge=140, le=220)
    mass_kg: float = Field(..., ge=30, le=200)
    gender: Literal["female", "male"]
    body_shape: Literal["hourglass", "rectangle", "inverted_triangle", "pear", "apple"]
    belly: int = Field(..., ge=1, le=3)
    build: int = Field(..., ge=1, le=3)
    legs: int = Field(2, ge=1, le=3)
    arms: int = Field(2, ge=1, le=3)
    cupsize: str | None = None
    ancestry: str | None = "mixed"


class OptimizeRequest(BaseModel):
    targets: dict[str, float] = Field(..., description="Starting macro targets")
    details: dict[str, float] = Field(default_factory=dict, description="Starting detail targets")
    silhouettes: dict[str, str] = Field(..., description="Normalized front/side PNG data URLs")
    maxEvaluations: int = Field(36, ge=8, le=96)
    height_cm: float | None = Field(None, ge=140, le=220)


class MeasurementsRequest(BaseModel):
    height_cm: float = Field(..., ge=140, le=220)
    mass_kg: float | None = Field(None, ge=30, le=200)
    bmi: float | None = Field(None, ge=10, le=60)
    bust_cm: float | None = Field(None, ge=40, le=200)
    underbust_cm: float | None = Field(None, ge=40, le=200)
    waist_cm: float | None = Field(None, ge=40, le=200)
    hip_cm: float | None = Field(None, ge=50, le=220)
    shoulder_width_cm: float | None = Field(None, ge=20, le=80)
    inseam_cm: float | None = Field(None, ge=40, le=140)
    thigh_cm: float | None = Field(None, ge=25, le=120)
    upperarm_cm: float | None = Field(None, ge=15, le=80)
    neck_cm: float | None = Field(None, ge=20, le=70)
    calf_cm: float | None = Field(None, ge=20, le=80)
    wrist_cm: float | None = Field(None, ge=10, le=40)


def _body_scan_response(result: dict) -> dict:
    derived = body_scan.measurements_to_targets(result.get("measurements") or {})
    return {
        "ok": True,
        "source": result.get("model", body_scan.MODEL_NAME),
        "measurements": result.get("measurements") or {},
        "targets": derived["targets"],
        "ratios": derived["ratios"],
        "notes": derived["notes"],
    }


def validate_targets(targets: dict[str, float]) -> dict[str, float]:
    if not targets:
        raise HTTPException(status_code=422, detail="targets must not be empty")
    if len(targets) > MAX_TARGETS:
        raise HTTPException(status_code=422, detail=f"at most {MAX_TARGETS} targets allowed")
    cleaned: dict[str, float] = {}
    for key, value in targets.items():
        if key not in ALLOWED_PARAMS:
            raise HTTPException(
                status_code=422,
                detail=f"unsupported parameter '{key}'. Allowed: {sorted(ALLOWED_PARAMS)}",
            )
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise HTTPException(status_code=422, detail=f"parameter '{key}' must be a number")
        v = float(value)
        if not (0.0 <= v <= 1.0):
            raise HTTPException(status_code=422, detail=f"parameter '{key}' must be between 0.0 and 1.0")
        cleaned[key] = round(v, 4)
    return cleaned


def validate_details(details: dict[str, float]) -> dict[str, float]:
    try:
        return mpfb_details.validate_details(details)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def validate_outfit(outfit: list[str]) -> list[str]:
    if len(outfit) > MAX_GARMENTS:
        raise HTTPException(status_code=422, detail=f"at most {MAX_GARMENTS} garments allowed")

    cleaned: list[str] = []
    for g in outfit:
        if g not in GARMENT_CATALOG:
            raise HTTPException(
                status_code=422,
                detail=f"unsupported garment '{g}'. Allowed: {ALLOWED_GARMENTS}",
            )
        if g not in cleaned:
            cleaned.append(g)

    slots = [GARMENT_CATALOG[g]["slot"] for g in cleaned]
    if "dress" in slots and ("top" in slots or "bottom" in slots):
        raise HTTPException(
            status_code=422,
            detail="A dress replaces the top and bottom. Choose a dress or a top + bottom, not both.",
        )

    seen: set[str] = set()
    for garment in cleaned:
        slot = GARMENT_CATALOG[garment]["slot"]
        if slot in seen:
            raise HTTPException(
                status_code=422,
                detail=f"Only one '{slot}' garment can be worn at a time.",
            )
        seen.add(slot)

    return cleaned


def validate_tryon_specs(specs: list[dict]) -> None:
    if len(specs) > MAX_GARMENTS:
        raise HTTPException(status_code=422, detail=f"at most {MAX_GARMENTS} garments allowed")

    seen: set[str] = set()
    slots: list[str] = []
    for spec in specs:
        template = spec.get("template")
        if template not in GARMENT_CATALOG:
            raise HTTPException(status_code=422, detail=f"unsupported garment '{template}'")
        slot = GARMENT_CATALOG[template]["slot"]
        if slot in seen:
            raise HTTPException(
                status_code=422,
                detail=f"Only one '{slot}' garment can be worn at a time.",
            )
        seen.add(slot)
        slots.append(slot)

    if "dress" in slots and ("top" in slots or "bottom" in slots):
        raise HTTPException(
            status_code=422,
            detail="A dress replaces the top and bottom. Choose a dress or a top + bottom, not both.",
        )


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _template_spec(template: str) -> dict:
    meta = GARMENT_CATALOG[template]
    return {
        "wardrobe_item_id": f"template:{template}",
        "template": template,
        "slot": str(meta["slot"]),
        "label": str(meta.get("label") or template),
        "color_hex": str(meta.get("swatch") or "#9a9a9a"),
        "color": list(meta.get("color") or tryon_mapping.hex_to_rgb(meta.get("swatch"))),
        "cutout_url": None,
        "mesh_url": None,
        "mesh_version": 0,
        "category": "",
    }


def resolve_tryon_specs(req: GenerateRequest, user: User) -> list[dict]:
    requested = _unique(req.wardrobe_item_ids)
    payloads = [item.model_dump() for item in req.wardrobe_items]

    if requested and AVATAR_STORE.kind == "supabase":
        rows = AVATAR_STORE.list_owned_items(user.id, requested)
        by_id = {str(row.get("id")): row for row in rows}
        missing = [item_id for item_id in requested if item_id not in by_id]
        if missing:
            raise HTTPException(
                status_code=404,
                detail="Some wardrobe items were not found for this user.",
            )
        specs = []
        for item_id in requested:
            resolved = tryon_mapping.resolve_item(by_id[item_id], GARMENT_CATALOG)
            if not resolved:
                name = by_id[item_id].get("name") or item_id
                raise HTTPException(
                    status_code=422,
                    detail=f"'{name}' has no 3D try-on template.",
                )
            specs.append(resolved)
    elif requested and payloads:
        by_id = {
            str(payload.get("wardrobe_item_id")): payload
            for payload in payloads
            if payload.get("wardrobe_item_id")
        }
        specs = []
        for index, item_id in enumerate(requested):
            payload = by_id.get(item_id) or (payloads[index] if index < len(payloads) else None)
            resolved = (
                tryon_mapping.resolve_payload(payload, GARMENT_CATALOG)
                or tryon_mapping.resolve_item(payload, GARMENT_CATALOG)
                if payload
                else None
            )
            if not resolved:
                raise HTTPException(
                    status_code=422,
                    detail=f"Wardrobe item '{item_id}' has no 3D try-on template.",
                )
            resolved["wardrobe_item_id"] = item_id
            specs.append(resolved)
    elif payloads:
        specs = []
        for payload in payloads:
            resolved = tryon_mapping.resolve_payload(
                payload, GARMENT_CATALOG
            ) or tryon_mapping.resolve_item(payload, GARMENT_CATALOG)
            if not resolved:
                raise HTTPException(
                    status_code=422,
                    detail=f"'{payload.get('label') or payload.get('template') or 'Item'}' has no 3D try-on template.",
                )
            specs.append(resolved)
    elif req.outfit:
        specs = [_template_spec(template) for template in validate_outfit(req.outfit)]
    else:
        specs = []

    validate_tryon_specs(specs)
    return specs


def _blender_spec(specs: list[dict]) -> list[dict]:
    return [
        {
            "template": spec["template"],
            "color": spec["color"],
            "label": spec["label"],
            "wardrobe_item_id": spec.get("wardrobe_item_id") or "",
            "texture_path": spec.get("texture_path"),
            "mesh_path": spec.get("mesh_path"),
        }
        for spec in specs
    ]


def _snapshot(specs: list[dict]) -> list[SavedAvatarItem]:
    return [
        SavedAvatarItem(
            wardrobe_item_id=str(spec.get("wardrobe_item_id") or ""),
            template=str(spec["template"]),
            slot=str(spec["slot"]),
            label=str(spec["label"]),
            color_hex=str(spec.get("color_hex") or "#9a9a9a"),
            cutout_url=spec.get("cutout_url"),
            mesh_url=spec.get("mesh_url"),
            mesh_version=int(spec.get("mesh_version") or 0),
            category=str(spec.get("category") or ""),
        )
        for spec in specs
    ]


def _cutout_bytes(url: str) -> bytes:
    url = url.strip()
    if url.startswith("data:"):
        header, _, encoded = url.partition(",")
        if ";base64" not in header:
            raise ValueError("unsupported data URL")
        return base64.b64decode(encoded)
    if url.startswith("/"):
        url = WARDROBE_API_URL + url
    if url.startswith("http://") or url.startswith("https://"):
        response = httpx.get(url, timeout=25.0, follow_redirects=True)
        response.raise_for_status()
        return response.content
    raise ValueError("unsupported cutout URL")


def _materialise_textures(specs: list[dict], job_id: str) -> list[Path]:
    """Download item cutouts to local files so Blender does not need network access."""
    written: list[Path] = []
    for index, spec in enumerate(specs):
        url = str(spec.get("cutout_url") or "").strip()
        if not url:
            continue
        path = TEMP_DIR / f"texture_{job_id}_{index}.png"
        try:
            path.write_bytes(_cutout_bytes(url))
        except Exception as exc:  # noqa: BLE001 - fall back to the item colour
            print(f"[avatar] could not load cutout for {spec.get('label')}: {exc}", flush=True)
            continue
        spec["texture_path"] = str(path)
        written.append(path)
    return written


def _materialise_meshes(specs: list[dict], job_id: str) -> list[Path]:
    """Download generated item meshes for Blender without giving it network access."""
    written: list[Path] = []
    for index, spec in enumerate(specs):
        url = str(spec.get("mesh_url") or "").strip()
        if not url:
            continue
        path = TEMP_DIR / f"mesh_{job_id}_{index}.glb"
        try:
            data = _cutout_bytes(url)
            if data[:4] != b"glTF":
                raise ValueError("mesh URL did not return a valid GLB")
            path.write_bytes(data)
        except Exception as exc:  # noqa: BLE001 - template fitting remains available
            print(f"[avatar] could not load mesh for {spec.get('label')}: {exc}", flush=True)
            continue
        spec["mesh_path"] = str(path)
        written.append(path)
    return written


def _avatar_response(row: dict) -> dict:
    return {
        "found": True,
        "targets": row.get("targets") or {},
        "details": row.get("details") or {},
        "outfit": row.get("outfit") or [],
        "metrics": row.get("metrics") or {},
        "url": row.get("url") or "",
        "heightCm": row.get("height_cm"),
        "generatedAt": row.get("generated_at"),
        "updatedAt": row.get("updated_at"),
    }


def is_valid_glb(path: Path) -> bool:
    try:
        with open(path, "rb") as f:
            magic = f.read(4)
        return magic == b"glTF" and path.stat().st_size > 1000
    except OSError:
        return False


def extract_result_line(output: str) -> dict | None:
    matches = re.findall(r"^AVATAR_RESULT (\{.*\})$", output, flags=re.MULTILINE)
    if not matches:
        return None
    try:
        return json.loads(matches[-1])
    except json.JSONDecodeError:
        return None


def cleanup_generated(max_age_hours: float = GENERATED_TTL_HOURS) -> None:
    """Remove old generated GLBs so public/models/generated does not grow forever."""
    if max_age_hours <= 0 or not GENERATED_DIR.is_dir():
        return
    cutoff = time.time() - max_age_hours * 3600
    for path in GENERATED_DIR.glob("avatar_*.glb"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
        except OSError:
            continue


def cleanup_temp(max_age_hours: float = 1.0) -> None:
    if not TEMP_DIR.is_dir():
        return
    cutoff = time.time() - max_age_hours * 3600
    for path in TEMP_DIR.glob("*"):
        try:
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink()
        except OSError:
            continue


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "blenderExists": Path(BLENDER_PATH).is_file(),
        "blendExists": Path(AVATAR_BLEND).is_file(),
        "dressedScriptExists": DRESSED_BLENDER_SCRIPT.is_file(),
        "allowedGarments": ALLOWED_GARMENTS,
        "slots": GARMENT_SLOTS,
        "visionConfigured": vision.is_configured(),
        "authEnabled": settings.AUTH_ENABLED,
        "avatarStorage": AVATAR_STORE.kind,
    }


@app.get("/api/body/status")
def body_scan_status() -> dict:
    return {
        "configured": True,
        "source": body_scan.MODEL_NAME,
    }


@app.post("/api/body/questionnaire")
def scan_body_questionnaire(payload: QuestionnaireRequest) -> dict:
    result = body_scan.scan_questionnaire(payload.model_dump(exclude_none=True))
    return _body_scan_response(result)


@app.post("/api/body/measurements")
def body_measurements(payload: MeasurementsRequest) -> dict:
    measurements = payload.model_dump(exclude_none=True)
    derived = body_scan.measurements_to_targets(measurements)
    return {
        "ok": True,
        "source": "photo-measurements",
        "measurements": measurements,
        "targets": derived["targets"],
        "ratios": derived["ratios"],
        "notes": derived["notes"],
    }


async def _read_photo(upload: UploadFile) -> tuple[bytes, str]:
    content_type = (upload.content_type or "").lower()
    if content_type not in vision.ALLOWED_PHOTO_TYPES:
        raise HTTPException(status_code=422, detail="Upload a JPG, PNG, or WebP photo")
    data = await upload.read()
    if not data:
        raise HTTPException(status_code=422, detail="The uploaded photo is empty")
    if len(data) > vision.MAX_PHOTO_BYTES:
        raise HTTPException(status_code=413, detail="A photo is larger than 20 MB")
    return data, content_type


@app.post("/api/body/vision")
async def body_vision(
    front: UploadFile = File(...),
    side: UploadFile = File(...),
    height_cm: float = Form(...),
) -> dict:
    if not (140.0 <= height_cm <= 220.0):
        raise HTTPException(status_code=422, detail="height_cm must be between 140 and 220")
    front_bytes, front_type = await _read_photo(front)
    side_bytes, side_type = await _read_photo(side)
    try:
        return await vision.analyze_photos(front_bytes, front_type, side_bytes, side_type, height_cm)
    except vision.VisionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@app.post("/api/avatar/generate", response_model=GenerateResponse)
def generate(
    req: GenerateRequest,
    user: User = Depends(current_user),
) -> GenerateResponse:
    targets = validate_targets(req.targets)
    details = validate_details(req.details)
    specs = resolve_tryon_specs(req, user)
    outfit = [spec["template"] for spec in specs]
    script = DRESSED_BLENDER_SCRIPT if specs else BLENDER_SCRIPT
    if not script.is_file():
        raise HTTPException(status_code=500, detail=f"Generator script missing: {script}")

    if not Path(BLENDER_PATH).is_file():
        raise HTTPException(status_code=500, detail=f"Blender not found at {BLENDER_PATH}")
    if not Path(AVATAR_BLEND).is_file():
        raise HTTPException(status_code=500, detail=f"Avatar scene not found at {AVATAR_BLEND}")

    if not _job_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="A generation job is already running. Try again shortly.")
    try:
        job_id = uuid.uuid4().hex[:12]
        TEMP_DIR.mkdir(parents=True, exist_ok=True)
        GENERATED_DIR.mkdir(parents=True, exist_ok=True)
        cleanup_generated()
        cleanup_temp()

        params_path = TEMP_DIR / f"params_{job_id}.json"
        details_path = TEMP_DIR / f"details_{job_id}.json"
        spec_path = TEMP_DIR / f"spec_{job_id}.json"
        temp_glb = TEMP_DIR / f"avatar_{job_id}.glb"
        params_path.write_text(json.dumps(targets), encoding="utf-8")
        details_path.write_text(json.dumps(details), encoding="utf-8")
        texture_paths: list[Path] = []
        mesh_paths: list[Path] = []
        if specs:
            texture_paths = _materialise_textures(specs, job_id)
            mesh_paths = _materialise_meshes(specs, job_id)
            spec_path.write_text(json.dumps(_blender_spec(specs)), encoding="utf-8")

        cmd = [
            BLENDER_PATH,
            "--background",
            AVATAR_BLEND,
            "--python",
            str(script),
            "--",
            "--params",
            str(params_path),
            "--details",
            str(details_path),
            "--output",
            str(temp_glb),
        ]
        if specs:
            cmd.extend(["--spec", str(spec_path)])
        if req.height_cm is not None:
            cmd.extend(["--height-cm", str(req.height_cm)])
        started = time.monotonic()
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=JOB_TIMEOUT_SECONDS,
                shell=False,
            )
        except subprocess.TimeoutExpired:
            raise HTTPException(
                status_code=504,
                detail=f"Blender did not finish within {JOB_TIMEOUT_SECONDS}s",
            )
        finally:
            elapsed = round(time.monotonic() - started, 1)
            try:
                params_path.unlink(missing_ok=True)
                details_path.unlink(missing_ok=True)
                spec_path.unlink(missing_ok=True)
                for texture_path in texture_paths:
                    texture_path.unlink(missing_ok=True)
                for mesh_path in mesh_paths:
                    mesh_path.unlink(missing_ok=True)
            except OSError:
                pass

        combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
        result = extract_result_line(combined)

        if proc.returncode != 0 or not result or not result.get("ok"):
            detail = (result or {}).get("error") or f"Blender exited with code {proc.returncode}"
            tail = "\n".join(combined.strip().splitlines()[-8:])
            raise HTTPException(status_code=500, detail=f"{detail} | log tail: {tail}")

        if not temp_glb.is_file() or temp_glb.stat().st_size == 0 or not is_valid_glb(temp_glb):
            raise HTTPException(status_code=500, detail="Blender reported success but the GLB output is missing or invalid")

        final_name = f"avatar_{job_id}.glb"
        final_path = GENERATED_DIR / final_name
        shutil.move(str(temp_glb), str(final_path))

        metrics = result.get("metrics") or {}
        metrics = {k: float(v) for k, v in metrics.items() if isinstance(v, (int, float))}
        snapshots = _snapshot(specs)
        response_url = f"/models/generated/{final_name}"
        saved = False
        saved_at: str | None = None
        save_error: str | None = None

        try:
            row = AVATAR_STORE.save_avatar(
                user.id,
                {
                    "targets": targets,
                    "details": details,
                    "outfit": [item.model_dump() for item in snapshots],
                    "metrics": metrics,
                    "height_cm": req.height_cm,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                },
                final_path.read_bytes(),
            )
            response_url = str(row.get("url") or response_url)
            saved = True
            saved_at = row.get("updated_at") or row.get("generated_at")
        except Exception as exc:  # noqa: BLE001 - generation succeeds even if storage is down
            save_error = str(exc)
            print(f"[avatar] could not save latest avatar for {user.id}: {exc}", flush=True)

        return GenerateResponse(
            jobId=job_id,
            url=response_url,
            params=targets,
            details=details,
            outfit=outfit,
            bytes=final_path.stat().st_size,
            elapsedSeconds=elapsed,
            metrics=metrics,
            items=snapshots,
            saved=saved,
            savedAt=saved_at,
            saveError=save_error,
        )
    finally:
        _job_lock.release()


@app.get("/api/avatar/me")
def get_my_avatar(user: User = Depends(current_user)) -> dict:
    row = AVATAR_STORE.get_avatar(user.id)
    if not row:
        return {"found": False}
    return _avatar_response(row)


@app.delete("/api/avatar/me")
def delete_my_avatar(user: User = Depends(current_user)) -> dict:
    AVATAR_STORE.delete_avatar(user.id)
    return {"deleted": True}


def _update_opt_job(job_id: str, **fields) -> None:
    with _opt_jobs_lock:
        job = _opt_jobs.get(job_id)
        if job is not None:
            job.update(fields)


def _run_optimize(
    job_id: str,
    targets: dict[str, float],
    details: dict[str, float],
    silhouettes: dict[str, str],
    max_evaluations: int,
    height_cm: float | None = None,
) -> None:
    work_dir = TEMP_DIR / f"opt_{job_id}"
    config = {
        "blender": BLENDER_PATH,
        "avatar_blend": AVATAR_BLEND,
        "script": str(BLENDER_SCRIPT),
        "work_dir": str(work_dir),
        "eval_timeout": min(JOB_TIMEOUT_SECONDS, 180),
        "height_cm": height_cm,
    }

    def progress(payload: dict) -> None:
        _update_opt_job(job_id, progress=payload)

    try:
        result = optimizer.optimize(
            targets,
            details,
            silhouettes,
            config,
            max_evaluations=max_evaluations,
            progress=progress,
        )
        best_glb = Path(result.pop("glbPath"))
        final_name = f"avatar_opt_{job_id}.glb"
        final_path = GENERATED_DIR / final_name
        GENERATED_DIR.mkdir(parents=True, exist_ok=True)
        shutil.move(str(best_glb), str(final_path))
        result["jobId"] = job_id
        result["url"] = f"/models/generated/{final_name}"
        result["bytes"] = final_path.stat().st_size
        _update_opt_job(job_id, status="done", result=result)
    except Exception as exc:
        _update_opt_job(job_id, status="error", error=str(exc))
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
        _job_lock.release()


def _validate_silhouettes(silhouettes: dict[str, str]) -> None:
    for key in ("front", "side"):
        data = silhouettes.get(key)
        if not isinstance(data, str) or not data.startswith("data:image/png;base64,"):
            raise HTTPException(status_code=422, detail=f"{key} silhouette must be a PNG data URL")
        if len(data) > 8 * 1024 * 1024:
            raise HTTPException(status_code=413, detail=f"{key} silhouette is too large")


@app.post("/api/avatar/optimize")
def start_optimize(payload: OptimizeRequest) -> dict:
    targets = validate_targets(payload.targets)
    details = validate_details(payload.details)
    _validate_silhouettes(payload.silhouettes)
    if not _job_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="A Blender job is already running. Try again shortly.")

    job_id = uuid.uuid4().hex[:12]
    job = {
        "jobId": job_id,
        "status": "running",
        "createdAt": int(time.time()),
        "progress": {
            "evaluations": 0,
            "maxEvaluations": payload.maxEvaluations,
            "bestScore": None,
        },
    }
    with _opt_jobs_lock:
        _opt_jobs[job_id] = job

    try:
        thread = threading.Thread(
            target=_run_optimize,
            args=(job_id, targets, details, payload.silhouettes, payload.maxEvaluations, payload.height_cm),
            daemon=True,
        )
        thread.start()
    except Exception as exc:
        _job_lock.release()
        _update_opt_job(job_id, status="error", error=str(exc))
        raise HTTPException(status_code=500, detail="Could not start the optimizer") from exc

    return {"jobId": job_id, "status": "running", "progress": job["progress"]}


@app.get("/api/avatar/optimize/{job_id}")
def get_optimize(job_id: str) -> dict:
    with _opt_jobs_lock:
        job = _opt_jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Unknown optimization job")
        return dict(job)
