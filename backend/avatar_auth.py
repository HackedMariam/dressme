"""Supabase Auth dependency for the avatar backend.

When Supabase is not configured the backend runs in single-user local mode and
returns ``User(id="local")``. In production the caller must send the Supabase
access token as ``Authorization: Bearer <token>``.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Header, HTTPException

import settings
from avatar_store import get_supabase


@dataclass(frozen=True)
class User:
    id: str
    email: str | None = None


def current_user(authorization: str | None = Header(None)) -> User:
    if not settings.AUTH_ENABLED:
        return User(id=settings.LOCAL_USER_ID)

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Sign in to use the virtual try-on.")

    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Sign in to use the virtual try-on.")

    try:
        result = get_supabase().auth.get_user(token)
    except Exception as exc:  # noqa: BLE001 - supabase client raises several types
        raise HTTPException(
            status_code=401,
            detail="Your session expired. Sign in again.",
        ) from exc

    user = getattr(result, "user", None)
    if user is None or not getattr(user, "id", None):
        raise HTTPException(status_code=401, detail="Your session expired. Sign in again.")

    return User(id=str(user.id), email=getattr(user, "email", None))
