"""URLs des agents et identifiants du compte de test. Aucun secret n'est affiché ni écrit dans les rapports."""
from __future__ import annotations

import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
CASES_DIR = HERE / "cases"
REPORTS_DIR = HERE / "reports"
ORCHESTRATOR_DIR = REPO / "orchestrator"

# 127.0.0.1 et non localhost : sous Windows, localhost essaie d'abord IPv6 (::1), refusé au bout de ~2 s.
URLS = {
    "bo1": os.environ.get("EVAL_BO1_URL", "http://127.0.0.1:8000"),
    "bo3": os.environ.get("EVAL_BO3_URL", "http://127.0.0.1:8001"),
    "trip": os.environ.get("EVAL_TRIP_URL", "http://127.0.0.1:8020"),
    "bo4": os.environ.get("EVAL_BO4_URL", "http://127.0.0.1:8061"),
    "orchestrator": os.environ.get("EVAL_ORCHESTRATOR_URL", "http://127.0.0.1:8070"),
    "rag": os.environ.get("EVAL_RAG_URL", "http://127.0.0.1:8010"),
    "ollama": os.environ.get("EVAL_OLLAMA_URL", "http://127.0.0.1:11434"),
    "down": "http://127.0.0.1:9",      # port fermé : sert aux cas « service arrêté »
}
JUDGE_MODEL = os.environ.get("EVAL_JUDGE_MODEL", "qwen2.5:3b")
VALID_STATES = ("completed", "input-required", "failed")


def read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            key, sep, value = line.strip().partition("=")
            if sep and key and not key.startswith("#"):
                values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load_credentials(env_file: str | None = None) -> dict[str, str]:
    """SUPABASE_URL / SUPABASE_ANON_KEY (environnement, --env-file, orchestrator/.env, .env racine) et
    TEST_EMAIL / TEST_PASSWORD (environnement, orchestrator/.env.test). Lève RuntimeError sans citer une valeur."""
    sources = ([Path(env_file)] if env_file else []) + [ORCHESTRATOR_DIR / ".env", REPO / ".env"]
    out: dict[str, str] = {}
    for key in ("SUPABASE_URL", "SUPABASE_ANON_KEY"):
        out[key] = os.environ.get(key, "")
        for source in sources:
            out[key] = out[key] or read_env_file(source).get(key, "")
    test = read_env_file(ORCHESTRATOR_DIR / ".env.test")
    for key in ("TEST_EMAIL", "TEST_PASSWORD"):
        out[key] = os.environ.get(key) or test.get(key, "")
    missing = [k for k, v in out.items() if not v]
    if missing:
        raise RuntimeError("configuration incomplète : " + ", ".join(missing)
                           + " (SUPABASE_* : --env-file ou orchestrator/.env ; TEST_* : orchestrator/.env.test)")
    return out


def rag_key() -> str:
    """Clé X-API-Key de BO5 (BO5_API_KEY ou RAG_API_KEY : environnement, orchestrator/.env, .env racine). Jamais affichée."""
    for name in ("BO5_API_KEY", "RAG_API_KEY"):
        value = os.environ.get(name, "")
        for source in (ORCHESTRATOR_DIR / ".env", REPO / ".env", REPO / "rag_backend" / ".env"):
            value = value or read_env_file(source).get(name, "")
        if value:
            return value
    return ""
