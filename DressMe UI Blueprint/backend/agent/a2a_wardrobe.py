"""The Gap Agent reads the wardrobe through the Wardrobe Agent (A2A), like every other agent.

The wardrobe is owned by the Wardrobe Agent (BO1, /a2a/wardrobe). BO3 only knows the user's id once a request has been
authenticated, so the route remembers the user's bearer token for a few minutes (`remember`); `fetch_rows` then asks the
Wardrobe Agent for the user's pieces with that token. When it is not possible (no token, BO1 stopped, A2A refused) it
returns None and BO3 reads Supabase as before: the Gap Agent never stops working because another service is down.
"""
from __future__ import annotations

import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[3]            # a2a_protocol/ sits at the root of the repository
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from a2a_protocol import A2AClient, A2AError  # noqa: E402

log = logging.getLogger("dressme.bo3.wardrobe_a2a")

TOKEN_TTL = 300
_tokens: dict[str, tuple[float, str]] = {}
_lock = threading.Lock()


def wardrobe_url() -> str:
    return os.getenv("WARDROBE_A2A_URL", "http://127.0.0.1:8000/a2a/wardrobe").strip()


def remember(user_id: str, token: str) -> None:
    """Keep the verified bearer token of a user, to call the Wardrobe Agent on their behalf."""
    with _lock:
        _tokens[user_id] = (time.time() + TOKEN_TTL, token)


def _token(user_id: str) -> str | None:
    with _lock:
        hit = _tokens.get(user_id)
    return hit[1] if hit and hit[0] > time.time() else None


def fetch_rows(user_id: str | None, *, transport=None) -> list[dict[str, Any]] | None:
    """The user's wardrobe rows as the Wardrobe Agent lists them, or None when it cannot be asked."""
    url, token = wardrobe_url(), _token(user_id) if user_id else None
    if not (url and token):
        return None
    try:
        client = A2AClient(url, token=token, timeout=30, transport=transport)
        task = client.send(data={"action": "list"})
        rows = client.data_of(task).get("items")
        if client.state_of(task) == "completed" and isinstance(rows, list):
            return rows
    except A2AError as error:
        log.warning("Wardrobe Agent unavailable over A2A (%s): reading Supabase instead", error)
    return None
