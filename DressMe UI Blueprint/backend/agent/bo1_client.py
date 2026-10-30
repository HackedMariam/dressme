"""Verify the caller with BO1 and fetch only that caller's wardrobe."""

import os
from dataclasses import dataclass, field
from typing import Any

import httpx
from fastapi import Header, HTTPException

from .wardrobe_source import to_bo3_item


@dataclass(frozen=True)
class WardrobeUser:
    id: str
    authorization: str = field(repr=False)


def _bo1_get(path: str, authorization: str) -> Any:
    base = os.getenv("BO1_URL", "http://127.0.0.1:8000").rstrip("/")
    try:
        response = httpx.get(base + path, headers={"Authorization": authorization}, timeout=10)
    except httpx.RequestError as error:
        raise HTTPException(503, "Wardrobe service is unavailable.") from error
    if response.status_code in (401, 403):
        raise HTTPException(401, "Please sign in again.")
    if response.status_code != 200:
        raise HTTPException(503, "Wardrobe service failed. Please try again.")
    try:
        return response.json()
    except ValueError as error:
        raise HTTPException(503, "Wardrobe service returned an invalid response.") from error


def current_user(authorization: str | None = Header(default=None)) -> WardrobeUser:
    if not authorization or not authorization.lower().startswith("bearer ") or not authorization[7:].strip():
        raise HTTPException(401, "Please sign in to use Wardrobe Gaps.")
    identity = _bo1_get("/api/me", authorization)
    if not isinstance(identity, dict) or not isinstance(identity.get("id"), str) or not identity["id"].strip():
        raise HTTPException(503, "Wardrobe identity is unavailable.")
    if identity["id"] == "local":
        raise HTTPException(503, "BO1 must enable authentication to verify your session.")
    return WardrobeUser(identity["id"], authorization)


def user_wardrobe(user: WardrobeUser) -> list[dict[str, Any]]:
    rows = _bo1_get("/api/items", user.authorization)
    if not isinstance(rows, list) or any(not isinstance(row, dict) or not row.get("id") for row in rows):
        raise HTTPException(503, "Wardrobe service returned invalid items.")
    try:
        return [to_bo3_item(row) for row in rows]
    except (TypeError, ValueError, AttributeError, KeyError) as error:
        raise HTTPException(503, "Wardrobe service returned invalid items.") from error
