"""Small environment loader shared by the avatar backend modules.

Only the public-safe Supabase connection settings and avatar options are read
here. The service-role key never leaves the backend process.
"""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent

_KEYS = {
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_SERVICE_KEY",
    "SUPABASE_ANON_KEY",
    "AVATAR_BUCKET",
    "AVATAR_AUTH_ENABLED",
    "LOCAL_USER_ID",
    "LOCAL_AVATAR_DIR",
}


def _load_env() -> None:
    for path in (PROJECT_ROOT / ".env", BASE_DIR / ".env"):
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
            if key not in _KEYS:
                continue
            os.environ.setdefault(key, value.strip().strip('"').strip("'"))


_load_env()


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


SUPABASE_URL = (
    os.getenv("SUPABASE_URL")
    or os.getenv("VITE_SUPABASE_URL")
    or ""
).rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = (
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    or os.getenv("SUPABASE_SERVICE_KEY")
    or ""
)
SUPABASE_CONFIGURED = bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)
AUTH_ENABLED = _bool("AVATAR_AUTH_ENABLED", SUPABASE_CONFIGURED)
LOCAL_USER_ID = os.getenv("LOCAL_USER_ID", "local")
AVATAR_BUCKET = os.getenv("AVATAR_BUCKET", "avatars")
AVATARS_TABLE = "user_avatars"
ITEMS_TABLE = "items"
LOCAL_AVATAR_DIR = Path(
    os.getenv("LOCAL_AVATAR_DIR") or BASE_DIR / "local_data" / "avatars"
)
SIGNED_URL_TTL_SECONDS = 60 * 60
