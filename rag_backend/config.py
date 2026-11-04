"""Central configuration for the DressMe RAG backend.

All default paths are resolved relative to this file, never the current
working directory. This keeps the pipeline safe to run from cron, Docker, or
an IDE without silently reading/writing a stray ``data/`` folder.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

RAG_ROOT = Path(__file__).resolve().parent
DEFAULT_PDF_DIR = RAG_ROOT / "ingestion" / "pdfs"
DEFAULT_DATA_DIR = RAG_ROOT / "data"
DEFAULT_EXTRACTION_CACHE_DIR = DEFAULT_DATA_DIR / "extraction_cache"

DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_CORS_ORIGINS = "http://localhost:5173,http://localhost:8443"

# Load the repo-level .env for local scripts and the API. Existing environment
# variables always win, so Docker/CI configuration is not overwritten.
try:
    from dotenv import load_dotenv as _load_dotenv

    _load_dotenv(RAG_ROOT.parent / ".env")
    _load_dotenv(RAG_ROOT / ".env")
except ImportError:  # pragma: no cover - dotenv is a declared dependency
    pass


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None:
        return default
    value = value.strip()
    return value or default


def _env_bool(name: str, default: bool) -> bool:
    value = _env(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = _env(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    value = _env(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _env_list(name: str, default: str) -> list[str]:
    return [
        item.strip()
        for item in (_env(name, default) or default).split(",")
        if item.strip()
    ]


def _resolve_path(value: str | None, default: Path) -> Path:
    if not value:
        return default
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = RAG_ROOT / path
    return path.resolve()


@dataclass(frozen=True)
class Settings:
    supabase_url: str | None
    supabase_key: str | None
    llm_api_key: str | None
    llm_base_url: str | None
    llm_model: str | None

    pdf_dir: Path = DEFAULT_PDF_DIR
    data_dir: Path = DEFAULT_DATA_DIR
    extracted_file: Path = DEFAULT_DATA_DIR / "extracted_pages.json"
    chunks_file: Path = DEFAULT_DATA_DIR / "chunks.jsonl"
    embedded_file: Path = DEFAULT_DATA_DIR / "embedded_chunks.jsonl"
    quality_report_file: Path = DEFAULT_DATA_DIR / "quality_report.json"
    conversations_db: Path = DEFAULT_DATA_DIR / "conversations.sqlite3"
    extraction_cache_dir: Path = DEFAULT_EXTRACTION_CACHE_DIR

    embedding_model: str = DEFAULT_EMBEDDING_MODEL
    embedding_version: str = f"{DEFAULT_EMBEDDING_MODEL}-v1"
    chunk_size: int = 1000
    chunk_overlap: int = 150
    embedding_batch_size: int = 32

    hybrid_enabled: bool = True
    candidate_k: int = 30
    default_top_k: int = 5
    min_similarity: float = 0.25
    rrf_constant: int = 60
    max_context_chars: int = 12000

    ocr_enabled: bool = True
    ocr_min_chars: int = 24
    ocr_dpi: int = 200
    ocr_language: str = "eng"
    tesseract_cmd: str | None = None

    query_rewrite_enabled: bool = True
    llm_timeout_seconds: float = 45.0
    llm_max_retries: int = 2
    llm_temperature: float = 0.2
    llm_max_tokens: int = 900

    cors_origins: list[str] = field(default_factory=list)
    api_key: str | None = None
    api_key_header: str = "X-API-Key"
    rate_limit_per_minute: int = 30
    environment: str = "development"
    log_level: str = "INFO"
    skip_startup_validation: bool = False
    # Knowledge table used for retrieval; its RPCs are match_<table> and search_<table>
    # (knowledge_chunks -> match_knowledge_chunks, knowledge_chunks_v2 -> match_knowledge_chunks_v2).
    rag_table: str = "knowledge_chunks"

    @property
    def match_rpc(self) -> str:
        return f"match_{self.rag_table}"

    @property
    def search_rpc(self) -> str:
        return f"search_{self.rag_table}"

    def validate(self, *, strict: bool = True) -> list[str]:
        errors: list[str] = []

        if not self.supabase_url:
            errors.append("SUPABASE_URL is required")
        elif not self.supabase_url.startswith(("http://", "https://")):
            errors.append("SUPABASE_URL must start with http:// or https://")

        if not self.supabase_key:
            errors.append(
                "SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_ANON_KEY / "
                "SUPABASE_KEY) is required"
            )

        if not self.llm_api_key:
            errors.append("LLM_API_KEY or OPENAI_API_KEY is required")

        if not self.llm_model:
            errors.append("LLM_MODEL is required")

        if not 0.0 <= self.min_similarity <= 1.0:
            errors.append("MIN_SIMILARITY must be between 0 and 1")

        if self.chunk_size <= self.chunk_overlap:
            errors.append("CHUNK_SIZE must be greater than CHUNK_OVERLAP")

        if "*" in self.cors_origins:
            errors.append(
                "CORS_ORIGINS may not contain '*' when credentials are enabled"
            )

        if not re.fullmatch(r"[a-z_][a-z0-9_]{0,55}", self.rag_table or ""):
            errors.append(
                "RAG_TABLE must be a lowercase table name (letters, digits, _)"
            )

        if strict and errors:
            raise RuntimeError(
                "Invalid RAG configuration: " + "; ".join(errors)
            )

        return errors

    @property
    def supabase_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_key)

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_api_key and self.llm_model)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    data_dir = _resolve_path(_env("RAG_DATA_DIR"), DEFAULT_DATA_DIR)
    embedding_model = _env("EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL) or (
        DEFAULT_EMBEDDING_MODEL
    )
    embedding_version = _env(
        "EMBEDDING_VERSION", f"{embedding_model}-v1"
    ) or f"{embedding_model}-v1"

    return Settings(
        supabase_url=_env("SUPABASE_URL"),
        supabase_key=(
            _env("SUPABASE_SERVICE_ROLE_KEY")
            or _env("SUPABASE_ANON_KEY")
            or _env("SUPABASE_KEY")
        ),
        llm_api_key=_env("LLM_API_KEY") or _env("OPENAI_API_KEY"),
        llm_base_url=_env("LLM_BASE_URL"),
        llm_model=_env("LLM_MODEL"),
        pdf_dir=_resolve_path(_env("RAG_PDF_DIR"), DEFAULT_PDF_DIR),
        data_dir=data_dir,
        extracted_file=data_dir / "extracted_pages.json",
        chunks_file=data_dir / "chunks.jsonl",
        embedded_file=data_dir / "embedded_chunks.jsonl",
        quality_report_file=data_dir / "quality_report.json",
        conversations_db=data_dir / "conversations.sqlite3",
        extraction_cache_dir=_resolve_path(
            _env("RAG_EXTRACTION_CACHE_DIR"),
            data_dir / "extraction_cache",
        ),
        embedding_model=embedding_model,
        embedding_version=embedding_version,
        chunk_size=_env_int("CHUNK_SIZE", 1000),
        chunk_overlap=_env_int("CHUNK_OVERLAP", 150),
        embedding_batch_size=_env_int("EMBEDDING_BATCH_SIZE", 32),
        hybrid_enabled=_env_bool("RAG_HYBRID_ENABLED", True),
        candidate_k=_env_int("RAG_CANDIDATE_K", 30),
        default_top_k=_env_int("RAG_TOP_K", 5),
        min_similarity=_env_float("RAG_MIN_SIMILARITY", 0.25),
        rrf_constant=_env_int("RAG_RRF_CONSTANT", 60),
        max_context_chars=_env_int("RAG_MAX_CONTEXT_CHARS", 12000),
        ocr_enabled=_env_bool("OCR_ENABLED", True),
        ocr_min_chars=_env_int("OCR_MIN_CHARS", 24),
        ocr_dpi=_env_int("OCR_DPI", 200),
        ocr_language=_env("OCR_LANGUAGE", "eng") or "eng",
        tesseract_cmd=_env("TESSERACT_CMD"),
        query_rewrite_enabled=_env_bool("QUERY_REWRITE_ENABLED", True),
        llm_timeout_seconds=_env_float("LLM_TIMEOUT_SECONDS", 45.0),
        llm_max_retries=_env_int("LLM_MAX_RETRIES", 2),
        llm_temperature=_env_float("LLM_TEMPERATURE", 0.2),
        llm_max_tokens=_env_int("LLM_MAX_TOKENS", 900),
        cors_origins=_env_list("CORS_ORIGINS", DEFAULT_CORS_ORIGINS),
        api_key=_env("RAG_API_KEY"),
        api_key_header=_env("RAG_API_KEY_HEADER", "X-API-Key") or "X-API-Key",
        rate_limit_per_minute=_env_int("RAG_RATE_LIMIT_PER_MINUTE", 30),
        environment=_env("ENVIRONMENT", "development") or "development",
        log_level=(_env("LOG_LEVEL", "INFO") or "INFO").upper(),
        skip_startup_validation=_env_bool(
            "RAG_SKIP_STARTUP_VALIDATION", False
        ),
        rag_table=_env("RAG_TABLE", "knowledge_chunks") or "knowledge_chunks",
    )


def reload_settings() -> Settings:
    get_settings.cache_clear()
    return get_settings()


def configure_logging(level: str | None = None) -> None:
    import logging

    class RequestIdFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            if not hasattr(record, "request_id"):
                record.request_id = "-"
            return True

    logging.basicConfig(
        level=(level or get_settings().log_level),
        format=(
            "%(asctime)s %(levelname)s %(name)s "
            "request_id=%(request_id)s %(message)s"
        ),
    )

    log_filter = RequestIdFilter()
    for handler in logging.getLogger().handlers:
        handler.addFilter(log_filter)
