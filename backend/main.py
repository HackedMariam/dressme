"""
Local DressMe avatar-generation backend.

Runs Blender 5.4 headless with the MPFB2 extension to regenerate a body-shaped
GLB from avatar.blend. Bound to 127.0.0.1 only. No arbitrary paths or commands
are accepted from clients: only whitelisted MPFB parameter names and 0..1 floats.

Run:
  cd backend
  venv\Scripts\activate
  pip install -r requirements.txt
  uvicorn main:app --host 127.0.0.1 --port 8000
"""

import json
import os
import re
import shutil
import subprocess
import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

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

ALLOWED_PARAMS = {
    "gender", "age", "muscle", "weight",
    "height", "proportions", "cupsize", "firmness",
}
MAX_TARGETS = len(ALLOWED_PARAMS)

ALLOWED_GARMENTS = ["tshirt", "trousers", "jacket"]
MAX_GARMENTS = len(ALLOWED_GARMENTS)

_job_lock = threading.Lock()
app = FastAPI(title="DressMe avatar backend", version="1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8443", "http://127.0.0.1:8443"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)


class GenerateRequest(BaseModel):
    targets: dict[str, float] = Field(..., description="MPFB parameter name -> value in [0, 1]")
    outfit: list[str] = Field(default_factory=list, description="Garment ids to fit and export")


class GenerateResponse(BaseModel):
    jobId: str
    url: str
    params: dict[str, float]
    outfit: list[str]
    bytes: int
    elapsedSeconds: float


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


def validate_outfit(outfit: list[str]) -> list[str]:
    if len(outfit) > MAX_GARMENTS:
        raise HTTPException(status_code=422, detail=f"at most {MAX_GARMENTS} garments allowed")
    cleaned: list[str] = []
    for g in outfit:
        if g not in ALLOWED_GARMENTS:
            raise HTTPException(
                status_code=422,
                detail=f"unsupported garment '{g}'. Allowed: {ALLOWED_GARMENTS}",
            )
        if g not in cleaned:
            cleaned.append(g)
    return cleaned


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


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "blenderExists": Path(BLENDER_PATH).is_file(),
        "blendExists": Path(AVATAR_BLEND).is_file(),
        "dressedScriptExists": DRESSED_BLENDER_SCRIPT.is_file(),
        "allowedGarments": ALLOWED_GARMENTS,
    }


@app.post("/api/avatar/generate", response_model=GenerateResponse)
def generate(req: GenerateRequest) -> GenerateResponse:
    import time

    targets = validate_targets(req.targets)
    outfit = validate_outfit(req.outfit)
    script = DRESSED_BLENDER_SCRIPT if outfit else BLENDER_SCRIPT
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

        params_path = TEMP_DIR / f"params_{job_id}.json"
        temp_glb = TEMP_DIR / f"avatar_{job_id}.glb"
        params_path.write_text(json.dumps(targets), encoding="utf-8")

        cmd = [
            BLENDER_PATH,
            "--background",
            AVATAR_BLEND,
            "--python",
            str(script),
            "--",
            "--params",
            str(params_path),
            "--output",
            str(temp_glb),
        ]
        if outfit:
            cmd.extend(["--outfit", ",".join(outfit)])
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

        return GenerateResponse(
            jobId=job_id,
            url=f"/models/generated/{final_name}",
            params=targets,
            outfit=outfit,
            bytes=final_path.stat().st_size,
            elapsedSeconds=elapsed,
        )
    finally:
        _job_lock.release()
