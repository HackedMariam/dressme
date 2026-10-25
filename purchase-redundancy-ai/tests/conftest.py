"""
Test setup: fast & offline (simulated embeddings, no Claude calls, temporary SQLite database).
Run from the project root:  backend/venv/Scripts/python -m pytest tests   (Linux/Mac: backend/venv/bin/python)
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

_tmp = Path(tempfile.mkdtemp(prefix="doublon-tests-"))
_tmp_db = _tmp / "test.db"
# Never touch the real photos, logs or caches: tests used to write into data/uploads and logs/app.log
os.environ["DATA_DIR"] = str(_tmp / "data")
os.environ["LOG_DIR"] = str(_tmp / "logs")
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{_tmp_db.as_posix()}"  # TEST_DATABASE_URL: run on PostgreSQL
os.environ["CLIP_ENABLED"] = "False"
os.environ["LLM_ENABLED"] = "False"
os.environ["RATE_LIMIT_ENABLED"] = "False"     # enabled explicitly by the rate-limit tests
os.environ["PASSWORD_HASH_ITERATIONS"] = "1000"  # fast hashing in tests (600 000 in production)
os.environ["REDIS_URL"] = os.environ.get("TEST_REDIS_URL", "")  # in-memory cache unless a test Redis is given
os.environ["SECRET_KEY"] = "test-secret-key-0123456789abcdef0123456789abcdef"


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient
    import main

    with TestClient(main.app) as c:
        yield c


@pytest.fixture
def wardrobe():
    return [
        {"id": "w1", "name": "Navy Oxford Shirt", "category": "shirts", "color": "navy", "style": "business",
         "material": "cotton", "use_case": "office", "season": "all-season", "price": 60},
        {"id": "w2", "name": "Blue Casual Cotton Shirt", "category": "shirts", "color": "blue", "style": "casual",
         "material": "cotton", "use_case": "casual", "season": "summer", "price": 40},
        {"id": "w3", "name": "Black Slim Jeans", "category": "pants", "color": "black", "style": "casual",
         "material": "denim", "use_case": "everyday", "season": "all-season", "price": 80},
        {"id": "w4", "name": "White Leather Sneakers", "category": "shoes", "color": "white", "style": "minimalist",
         "material": "leather", "use_case": "everyday", "season": "all-season", "price": 110},
    ]
