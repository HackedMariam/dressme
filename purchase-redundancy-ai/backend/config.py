"""
Configuration for Purchase Redundancy Detection System
Production-grade settings
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Windows consoles default to cp1252: emojis in logs/prints would raise UnicodeEncodeError
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Load .env from the project root (works whatever the current directory is)
load_dotenv(PROJECT_ROOT / ".env")

# ============================================================================
# ENVIRONMENT
# ============================================================================

DEBUG = os.getenv("DEBUG", "False").lower() == "true"
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

# ============================================================================
# LLM CONFIGURATION (Claude)
# ============================================================================

# LLM_* names (not CLAUDE_*) avoid clashing with variables set by Claude tooling
LLM_MODEL = os.getenv("LLM_MODEL", "claude-opus-5-5")
LLM_API_KEY = os.getenv("CLAUDE_API_KEY") or os.getenv("ANTHROPIC_API_KEY", "")
LLM_EFFORT = os.getenv("LLM_EFFORT", "low")  # explanations - low | medium | high | xhigh | max
LLM_AGENT_EFFORT = os.getenv("LLM_AGENT_EFFORT", "medium")  # multi-step agent runs
LLM_MAX_TOKENS = 16000
LLM_ENABLED = os.getenv("LLM_ENABLED", "True").lower() == "true"
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "auto")   # openai | claude | auto (OpenAI when OPENAI_API_KEY is set)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1")
CONFIDENCE_THRESHOLD = 0.85

# ============================================================================
# CLIP CONFIGURATION
# ============================================================================

CLIP_MODEL = "openai/clip-vit-base-patch32"
CLIP_ENABLED = os.getenv("CLIP_ENABLED", "True").lower() == "true"
USE_CUDA = os.getenv("USE_CUDA", "False").lower() == "true"
EMBEDDING_DIMENSION = 512

# ============================================================================
# DATABASE CONFIGURATION
# ============================================================================

# DATABASE_URL wins when set (any SQLAlchemy URL, e.g. postgresql://user:pass@host:5432/db).
# Otherwise DB_TYPE=postgresql builds it from DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME, and the default is SQLite.
DB_TYPE = os.getenv("DB_TYPE", "sqlite")  # sqlite, postgresql
# Runtime data (SQLite file, photos, caches, signing key) and logs - overridable, e.g. to isolate tests
DATA_DIR = Path(os.getenv("DATA_DIR") or PROJECT_ROOT / "data")
DATABASE_PATH = DATA_DIR
DATABASE_PATH.mkdir(parents=True, exist_ok=True)

if os.getenv("DATABASE_URL"):
    DATABASE_URL = os.environ["DATABASE_URL"]
elif DB_TYPE == "postgresql":
    from urllib.parse import quote_plus

    DATABASE_URL = (f"postgresql://{os.getenv('DB_USER', 'postgres')}:{quote_plus(os.getenv('DB_PASSWORD', ''))}"
                    f"@{os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', '5432')}/{os.getenv('DB_NAME', 'purchase_redundancy')}")
else:
    DATABASE_URL = f"sqlite:///{(DATABASE_PATH / 'redundancy.db').as_posix()}"
DB_TYPE = "postgresql" if DATABASE_URL.startswith("postgres") else "sqlite"
# psycopg 3 is the supported PostgreSQL driver: "postgresql://" -> "postgresql+psycopg://"
if DATABASE_URL.startswith(("postgresql://", "postgres://")):
    DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL.split("://", 1)[1]

DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "5"))         # PostgreSQL connection pool
DB_MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "10"))
DB_POOL_RECYCLE = int(os.getenv("DB_POOL_RECYCLE", "1800"))  # seconds - drop connections idle servers may have closed

# ============================================================================
# CACHE (Redis when REDIS_URL is set and reachable, in-memory otherwise)
# ============================================================================

REDIS_URL = os.getenv("REDIS_URL", "")
CACHE_TTL = int(os.getenv("CACHE_TTL", "300"))  # seconds

# ============================================================================
# AUTHENTICATION (JWT)
# ============================================================================

SECRET_KEY = os.getenv("SECRET_KEY", "")  # empty: generated once and stored in data/.secret_key
JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "168"))  # 7 days
AUTH_REQUIRED = os.getenv("AUTH_REQUIRED", "False").lower() == "true"  # False: anonymous visitors share a guest wardrobe

# ============================================================================
# RATE LIMITING & REQUEST LIMITS
# ============================================================================

RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "True").lower() == "true"
RATE_LIMIT_DEFAULT = int(os.getenv("RATE_LIMIT_DEFAULT", "300"))  # requests / minute / client
RATE_LIMIT_HEAVY = int(os.getenv("RATE_LIMIT_HEAVY", "30"))       # analyses, agent, image processing
RATE_LIMIT_AUTH = int(os.getenv("RATE_LIMIT_AUTH", "10"))         # login / register attempts
MAX_BODY_SIZE = 15 * 1024 * 1024  # a 10 MB image is ~13.4 MB once base64-encoded

# ============================================================================
# CLIP OPTIMIZATION
# ============================================================================

CLIP_QUANTIZE = os.getenv("CLIP_QUANTIZE", "False").lower() == "true"  # int8 dynamic quantization (CPU only)

# ============================================================================
# API CONFIGURATION
# ============================================================================

API_TITLE = "Purchase Redundancy Detection API"
API_VERSION = "1.0.0"
API_DESCRIPTION = "Intelligent wardrobe analysis with AI-powered redundancy detection"
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))

# ============================================================================
# SIMILARITY THRESHOLDS
# ============================================================================

SIMILARITY_THRESHOLD = 0.7  # 70% similarity = potential redundancy
SATURATION_LIMIT = 5  # Max items per category
AGENT_MAX_ITERATIONS = 5
AGENT_TIMEOUT = 30  # seconds

# ============================================================================
# IMAGE PROCESSING
# ============================================================================

MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
IMAGE_RESIZE_SIZE = (224, 224)

# ============================================================================
# FEATURES
# ============================================================================

ENABLED_FEATURES = list(range(1, 32))  # All 31 features (1-31)

BUILD_FEATURES = {
    1: "Visual Similarity Detection",
    2: "Similarity Score",
    3: "Attribute Comparison",
    4: "Similar Items Retrieval",
    5: "Redundancy Score",
    6: "Camera / In-Store Scan",
    7: "Screenshot Analysis",
    8: "Outfit Contribution",
    9: "Category Saturation",
    10: "User Feedback",
    11: "Duplicate Warning",
    12: "Explain Redundancy",
    13: "Alternatives",
}

BACKUP_FEATURES = {
    14: "Advanced Recommendations",
    15: "Multi-Wardrobe Analysis",
    16: "Seasonal Rotation",
    17: "Color Harmony",
    18: "Style Consistency",
    19: "Budget Optimization",
    20: "Trend Analysis",
    21: "Event Planning",
    22: "Personal Brand",
    23: "Quality Assessment",
    24: "Sustainability Tracking",
    25: "Resale Value",
    26: "Capsule Builder",
    27: "Outfit Matching",
    28: "Size Optimization",
    29: "Care Recommendations",
    30: "Fashion Score",
    31: "Market Intelligence",
}

# ============================================================================
# LOGGING
# ============================================================================

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = os.getenv("LOG_FORMAT", "text")  # text | json (one JSON object per line, for log aggregators)
LOG_MAX_BYTES = 10 * 1024 * 1024              # rotate logs/app.log at 10 MB
LOG_BACKUP_COUNT = 5
LOG_FILE = Path(os.getenv("LOG_DIR") or PROJECT_ROOT / "logs") / "app.log"
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

# ============================================================================
# CORS
# ============================================================================

CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]

# ============================================================================
# SEED DATA
# ============================================================================

# Real scraped catalog (database/scrape_real_catalog.py) when present, else the illustrated one
_REAL_CATALOG = PROJECT_ROOT / "database" / "products_real.json"
CATALOG = os.getenv("CATALOG", "real" if _REAL_CATALOG.exists() else "illustrated")
SEED_DATA_FILE = _REAL_CATALOG if CATALOG == "real" else PROJECT_ROOT / "database" / "products_700.json"
CATALOG_IMAGE_ROOT = PROJECT_ROOT / "database"          # image_url "/images/products/<id>.png" lives under it
UPLOAD_DIR = DATA_DIR / "uploads"                       # wardrobe photos
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR = DATA_DIR
