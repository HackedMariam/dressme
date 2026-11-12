"""Calls a running agent over A2A and returns what the judge needs: the answer and the facts the agent had.

Only agents exposed over A2A can be run live. For the others (orchestrator, purchase, rag), put the recorded
`output` (and `context`) in the case file.
"""
from __future__ import annotations

import os

from a2a_protocol.client import A2AClient

URLS = {
    "stylist": os.getenv("STYLIST_A2A_URL", "http://127.0.0.1:8000/a2a/stylist"),
    "outfit": os.getenv("OUTFIT_A2A_URL", "http://127.0.0.1:8000/a2a/outfit"),
    "wardrobe": os.getenv("WARDROBE_A2A_URL", "http://127.0.0.1:8000/a2a/wardrobe"),
    "similar": os.getenv("SIMILAR_A2A_URL", "http://127.0.0.1:8000/a2a/similar"),
    "trip": os.getenv("TRIP_A2A_URL", "http://127.0.0.1:8020/a2a/trip"),
    "gap": os.getenv("GAP_A2A_URL", "http://127.0.0.1:8001/a2a/gap"),
}


def _wardrobe_facts(token: str | None) -> list:
    """The user's real wardrobe, trimmed to what the judge needs to check grounding."""
    task = A2AClient(URLS["wardrobe"], token=token).send("list", data={"action": "list"})
    keys = ("id", "name", "category", "color", "colors", "pattern", "material", "season", "style")
    return [{k: i[k] for k in keys if k in i} for i in A2AClient.data_of(task).get("items", [])]


def run_live(agent: str, case: dict, token: str | None = None) -> dict:
    """Returns the case completed with `output` and `context` (the case's own `context` is kept if given)."""
    if agent not in URLS:
        raise ValueError(f"{agent} cannot be run live: record its output in the case file")
    client = A2AClient(URLS[agent], token=token)
    task = client.send(case.get("input", ""), data=case.get("data") or None)
    output = {"text": client.text_of(task), "data": client.data_of(task), "state": client.state_of(task)}
    context = case.get("context") or {"wardrobe": _wardrobe_facts(token)}
    return {**case, "output": output, "context": context}
