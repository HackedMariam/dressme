"""Who is calling: Supabase Auth JWT in production, a single local user in dev."""
from __future__ import annotations

import hashlib
import logging
import threading
import time
from dataclasses import dataclass

from fastapi import Header, HTTPException

from . import config

log = logging.getLogger("dressme.auth")

_CACHE_TTL = 300  # seconds a verified token is trusted without asking Supabase again
_cache: dict[str, tuple[float, "User"]] = {}
_lock = threading.Lock()
_client = None


@dataclass(frozen=True)
class User:
    id: str
    email: str | None = None


def _supabase():
    global _client
    if _client is None:
        from supabase import create_client

        _client = create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_ROLE_KEY)
    return _client


def current_user(authorization: str | None = Header(None)) -> User:
    if not config.AUTH_ENABLED:
        return User(id=config.LOCAL_USER_ID)

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Not signed in")
    token = authorization.split(" ", 1)[1].strip()
    key = hashlib.sha256(token.encode()).hexdigest()
    now = time.time()

    with _lock:
        hit = _cache.get(key)
        if hit and hit[0] > now:
            return hit[1]

    try:
        res = _supabase().auth.get_user(token)
    except Exception:
        raise HTTPException(401, "Session expired, please sign in again")
    if not res or not res.user:
        raise HTTPException(401, "Session expired, please sign in again")

    user = User(id=res.user.id, email=res.user.email)
    with _lock:
        if len(_cache) > 5000:  # drop expired entries
            for k in [k for k, (exp, _) in _cache.items() if exp <= now]:
                _cache.pop(k, None)
        _cache[key] = (now + _CACHE_TTL, user)
    return user
