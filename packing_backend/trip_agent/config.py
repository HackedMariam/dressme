"""Configuration and lightweight .env loading for the Trip Agent."""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PACKAGE_ROOT / "data"

DEFAULT_OPENAI_MODEL = "gpt-4o"
DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"
DEFAULT_LLM_TIMEOUT_SECONDS = 45
DEFAULT_WEATHER_TIMEOUT = (5.0, 12.0)
MAX_AGENT_ITERATIONS = 12
DEFAULT_OPTIMIZER_TIME_LIMIT_SECONDS = 30
DEFAULT_MAX_CANDIDATES_PER_DAY = 500


def load_dotenv(path: Path | None = None) -> None:
    """Load simple KEY=VALUE lines without adding a dependency.

    Existing environment variables always win, so production secrets are not
    overwritten by a local .env file.
    """
    env_path = path or (PROJECT_ROOT / ".env")
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not value.startswith(("'", '"')):
            value = value.split(" #", 1)[0].rstrip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if key:
            os.environ.setdefault(key, value)


load_dotenv()


def get_api_key() -> str | None:
    return os.environ.get("OPENAI_API_KEY") or None


def _clean_model(value: str | None) -> str | None:
    model = (value or "").strip()
    return model or None


def get_ai_model() -> str | None:
    """Generic model used by any provider without a specific override."""
    return _clean_model(os.environ.get("AI_MODEL"))


def get_openai_model() -> str:
    """Model for the OpenAI provider (``LLM_MODEL``)."""
    return (
        _clean_model(os.environ.get("LLM_MODEL"))
        or get_ai_model()
        or DEFAULT_OPENAI_MODEL
    )


def get_groq_model() -> str:
    """Model for the Groq provider (``GROQ_MODEL``, then ``AI_MODEL``)."""
    return (
        _clean_model(os.environ.get("GROQ_MODEL"))
        or get_ai_model()
        or DEFAULT_GROQ_MODEL
    )


def get_llm_providers() -> list[tuple[str, str, str]]:
    providers = []
    if os.environ.get("OPENAI_API_KEY"):
        providers.append(("openai", os.environ["OPENAI_API_KEY"], get_openai_model()))
    if os.environ.get("GROQ_API_KEY"):
        providers.append(("groq", os.environ["GROQ_API_KEY"], get_groq_model()))
    return providers


def get_model() -> str:
    """Backwards-compatible default model (OpenAI provider)."""
    return get_openai_model()


def llm_enabled() -> bool:
    flag = os.environ.get("TRIP_AGENT_USE_LLM", "1").strip().lower()
    return flag not in {"0", "false", "no", "off"}
