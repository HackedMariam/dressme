"""Central configuration, read from environment variables (.env supported)."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR.parent / ".env")


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


def _bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    return default if v is None or v.strip() == "" else v.strip().lower() in ("1", "true", "yes", "on")


# --- Vision model -----------------------------------------------------------
MODEL_PATH = Path(os.getenv("MODEL_PATH", BASE_DIR / "models" / "dressme_best.pt"))
if not MODEL_PATH.is_absolute():
    MODEL_PATH = BASE_DIR / MODEL_PATH
DETECT_CONF = _float("DETECT_CONF", 0.25)        # min confidence to keep a detection
REVIEW_THRESHOLD = _float("REVIEW_THRESHOLD", 0.60)  # below this -> "Needs review"
IMG_SIZE = int(os.getenv("IMG_SIZE", 640))

# --- LLM (OpenAI GPT-4) -----------------------------------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o")
LLM_SEND_IMAGE = _bool("LLM_SEND_IMAGE", True)
LLM_IMAGE_DETAIL = os.getenv("LLM_IMAGE_DETAIL", "low")  # low | high | auto
LLM_TIMEOUT = _float("LLM_TIMEOUT", 45)

# --- Supabase -------------------------------------------------------------
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "wardrobe")
USE_SUPABASE = bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)

# Auth: with Supabase every request must carry a Supabase Auth JWT and each user
# only sees their own wardrobe. Local mode (no Supabase) is single-user, for dev.
AUTH_ENABLED = USE_SUPABASE
LOCAL_USER_ID = "local"

# Local fallback storage (used when Supabase isn't configured)
LOCAL_DATA_DIR = Path(os.getenv("LOCAL_DATA_DIR", BASE_DIR / "local_data"))

# --- Per-item 3D meshes -----------------------------------------------------
BLENDER_PATH = Path(os.getenv(
    "BLENDER_PATH",
    r"C:\Users\maria\Downloads\blender-5.4.0-alpha+main.29ff43161222-windows.amd64-release"
    r"\blender-5.4.0-alpha+main.29ff43161222-windows.amd64-release\blender.exe",
))
ITEM_MESH_SCRIPT = BASE_DIR / "blender" / "generate_item_mesh.py"
ITEM_TEXTURE_SCRIPT = BASE_DIR / "blender" / "texture_item_mesh.py"
ITEM_NORMALIZE_SCRIPT = BASE_DIR / "blender" / "normalize_item_mesh.py"
ITEM_MESH_TIMEOUT_SECONDS = int(os.getenv("ITEM_MESH_TIMEOUT_SECONDS", "120"))
ITEM_MESH_GRID = int(os.getenv("ITEM_MESH_GRID", "160"))
ITEM_MESH_TARGET_FACES = int(os.getenv("ITEM_MESH_TARGET_FACES", "30000"))
ITEM_MESH_WORK_DIR = Path(os.getenv("ITEM_MESH_WORK_DIR", BASE_DIR / "temp" / "item_mesh"))

# Optional image-to-3D provider. "cutout-2.5d" is the fast CPU fallback.
# "hunyuan3d" calls the official Tencent/Hunyuan3D-2.1 Hugging Face Space.
ITEM_MESH_PROVIDER = os.getenv("ITEM_MESH_PROVIDER", "cutout-2.5d").strip().lower()
HF_TOKEN = os.getenv("HF_TOKEN", "").strip()
HF_3D_SPACE = os.getenv("HF_3D_SPACE", "tencent/Hunyuan3D-2.1").strip()
HF_3D_API_NAME = os.getenv("HF_3D_API_NAME", "/generation_all").strip()
HF_3D_TIMEOUT_SECONDS = int(os.getenv("HF_3D_TIMEOUT_SECONDS", "900"))
HF_3D_STEPS = int(os.getenv("HF_3D_STEPS", "30"))
HF_3D_OCTREE_RESOLUTION = int(os.getenv("HF_3D_OCTREE_RESOLUTION", "256"))
HF_3D_CAPTION = os.getenv("HF_3D_CAPTION", "").strip()
HF_3D_TARGET_FACES = int(os.getenv("HF_3D_TARGET_FACES", "30000"))
HF_3D_SHAPE_FALLBACK = _bool("HF_3D_SHAPE_FALLBACK", True)
MESH_PROVIDERS = ("cutout-2.5d", "hunyuan3d")

# --- HTTP -----------------------------------------------------------------
CORS_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:8443,http://127.0.0.1:8443,http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if o.strip()
]
PUBLIC_API_URL = os.getenv("PUBLIC_API_URL", "http://localhost:8000").rstrip("/")
MAX_UPLOAD_MB = _float("MAX_UPLOAD_MB", 15)
