"""The agents of BO1 talk to the Wardrobe Agent over A2A, like the agents of the other services do.

The AI Stylist, the Similar Agent, the Outfit Builder and the orchestrator no longer read the wardrobe by calling a
function: they send an A2A task to /a2a/wardrobe with the user's own token (`list` to read the pieces, `ask` to ask in
plain words, read-only). When that is not possible (no token, the service not reachable, a refusal) they fall back on
the in-process Wardrobe Agent, so an answer never depends on the network hop.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from a2a_protocol import A2AClient, A2AError  # noqa: E402

from . import wardrobe_agent  # noqa: E402

log = logging.getLogger("dressme.wardrobe_a2a")


def url() -> str:
    return os.getenv("WARDROBE_A2A_URL", "http://127.0.0.1:8000/a2a/wardrobe").strip()


def _task(authorization: Optional[str], data: dict, timeout: float) -> Optional[dict]:
    """The structured result of a Wardrobe Agent task, or None when it cannot be had over A2A."""
    if not (url() and authorization):
        return None
    client = A2AClient(url(), token=authorization, timeout=timeout)
    try:
        task = client.send(data=data)
        if client.state_of(task) == "completed":
            return client.data_of(task)
    except A2AError as error:
        log.warning("Wardrobe Agent unavailable over A2A (%s): using it in-process", error)
    return None


def list_items(user_id: str, authorization: Optional[str] = None) -> list[dict]:
    """The user's pieces, asked to the Wardrobe Agent (A2A `list`)."""
    result = _task(authorization, {"action": "list"}, timeout=30)
    if result is not None and isinstance(result.get("items"), list):
        return result["items"]
    return wardrobe_agent.list_items(user_id)


def ask(items: list[dict], request: str, authorization: Optional[str] = None) -> dict:
    """Ask the Wardrobe Agent, in plain words, for pieces (A2A `ask`, read-only): {"reply", "items", "filters"}."""
    result = _task(authorization, {"action": "ask", "request": request}, timeout=60)
    if result is not None and isinstance(result.get("items"), list):
        return {"reply": str(result.get("reply") or ""), "items": result["items"], "filters": result.get("filters") or []}
    return wardrobe_agent.ask(items, request)
