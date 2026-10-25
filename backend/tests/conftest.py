import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import main  # noqa: E402
from avatar_auth import User  # noqa: E402

main.app.dependency_overrides[main.current_user] = lambda: User(id="test-user")
