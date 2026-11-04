from __future__ import annotations

import os
from pathlib import Path

import pytest

TEST_DATA_DIR = Path(__file__).resolve().parent / ".tmp_data"

os.environ["RAG_SKIP_STARTUP_VALIDATION"] = "1"
os.environ["RAG_DATA_DIR"] = str(TEST_DATA_DIR)
os.environ["SUPABASE_URL"] = "https://example.supabase.co"
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = "test-service-key"
os.environ["LLM_API_KEY"] = "test-llm-key"
os.environ["LLM_MODEL"] = "test-model"
os.environ["QUERY_REWRITE_ENABLED"] = "false"
os.environ["RAG_HYBRID_ENABLED"] = "false"
os.environ["RAG_API_KEY"] = ""
os.environ["OCR_ENABLED"] = "false"

from config import get_settings, reload_settings  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("RAG_DATA_DIR", str(tmp_path))
    reload_settings()
    yield
    reload_settings()


@pytest.fixture
def settings():
    return get_settings()
