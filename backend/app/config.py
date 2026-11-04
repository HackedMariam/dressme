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
LIVE_MIN_CONFIDENCE = _float("LIVE_MIN_CONFIDENCE", 0.50)  # live scan never saves a detection below this
IMG_SIZE = int(os.getenv("IMG_SIZE", 640))

# --- LLM (OpenAI GPT-4) -----------------------------------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o")
LLM_SEND_IMAGE = _bool("LLM_SEND_IMAGE", True)
LLM_IMAGE_DETAIL = os.getenv("LLM_IMAGE_DETAIL", "low")  # low | high | auto
LLM_TIMEOUT = _float("LLM_TIMEOUT", 45)

# --- Supabase -------------------------------------------------------------
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SERVICE_KEY", "")
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "wardrobe")
USE_SUPABASE = bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)

# Auth: with Supabase every request must carry a Supabase Auth JWT and each user
# only sees their own wardrobe. Local mode (no Supabase) is single-user, for dev.
AUTH_ENABLED = USE_SUPABASE
LOCAL_USER_ID = "local"

# Local fallback storage (used when Supabase isn't configured)
LOCAL_DATA_DIR = Path(os.getenv("LOCAL_DATA_DIR", BASE_DIR / "local_data"))

# --- 3D avatar and virtual try-on (fal.ai: one key, pay per use) ---------------
# Fashion-knowledge RAG service (rag_backend/): the AI stylist asks it for book-based advice. Empty URL = off.
RAG_URL = os.getenv("RAG_URL", "http://127.0.0.1:8010")
RAG_API_KEY = os.getenv("RAG_API_KEY", "")
RAG_API_KEY_HEADER = os.getenv("RAG_API_KEY_HEADER", "X-API-Key")
RAG_TIMEOUT = float(os.getenv("RAG_TIMEOUT", 60))

# Provider of the 3D avatar and the virtual try-on: "auto" uses WaveSpeed when WAVESPEED_API_KEY is set, else fal.ai.
AVATAR_PROVIDER = os.getenv("AVATAR_PROVIDER", "auto").strip().lower()   # auto | wavespeed | fal
WAVESPEED_API_KEY = os.getenv("WAVESPEED_API_KEY", "")
WAVESPEED_3D_MODEL = os.getenv("WAVESPEED_3D_MODEL", "wavespeed-ai/hunyuan3d-v3/image-to-3d")   # about $0.30
WAVESPEED_TRYON_MODEL = os.getenv("WAVESPEED_TRYON_MODEL", "bria/virtual-try-on")               # about $0.04, up to 3 garments
WAVESPEED_FACE_COUNT = int(os.getenv("WAVESPEED_FACE_COUNT", 150000))    # mesh size: smaller loads faster in the browser
FAL_KEY = os.getenv("FAL_KEY", "")
FAL_3D_MODEL = os.getenv("FAL_3D_MODEL", "fal-ai/hunyuan3d/v2")             # image -> textured GLB (about $0.48)
FAL_TRYON_MODEL = os.getenv("FAL_TRYON_MODEL", "fal-ai/fashn/tryon/v1.6")   # 2D try-on step
FAL_TRYON_MODE = os.getenv("FAL_TRYON_MODE", "balanced")                    # performance | balanced | quality
FAL_TIMEOUT = _float("FAL_TIMEOUT", 300)                                    # seconds to wait for one generation
AVATAR_BUCKET = os.getenv("AVATAR_BUCKET", "avatar-media")                  # private Supabase bucket
AVATAR_CREATIONS_PER_DAY = int(os.getenv("AVATAR_CREATIONS_PER_DAY", 3))    # credit protection, per user
AVATAR_TRYONS_PER_HOUR = int(os.getenv("AVATAR_TRYONS_PER_HOUR", 10))

# --- HTTP -----------------------------------------------------------------
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]
PUBLIC_API_URL = os.getenv("PUBLIC_API_URL", "http://localhost:8000").rstrip("/")
MAX_UPLOAD_MB = _float("MAX_UPLOAD_MB", 15)
