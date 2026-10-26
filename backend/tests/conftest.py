import os
import sys
import tempfile
from pathlib import Path

# Force local single-user mode and no LLM before the app is imported
# (load_dotenv never overrides variables that are already set).
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = ""
os.environ["OPENAI_API_KEY"] = ""
os.environ["LOCAL_DATA_DIR"] = tempfile.mkdtemp(prefix="dressme-test-")

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import main  # noqa: E402
from avatar_auth import User  # noqa: E402

main.app.dependency_overrides[main.current_user] = lambda: User(id="test-user")
