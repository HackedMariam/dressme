"""Connexion du compte de test (Supabase Auth, mot de passe) : le jeton sert à appeler les agents au nom de ce compte."""
from __future__ import annotations

from .net import call


class AuthError(RuntimeError):
    pass


def login(config: dict[str, str]) -> dict:
    status, payload, error, _ = call(
        "POST", config["SUPABASE_URL"].rstrip("/") + "/auth/v1/token?grant_type=password",
        headers={"apikey": config["SUPABASE_ANON_KEY"]},
        body={"email": config["TEST_EMAIL"], "password": config["TEST_PASSWORD"]}, timeout=30)
    if status != 200 or not isinstance(payload, dict) or not payload.get("access_token"):
        raise AuthError(f"connexion du compte de test refusée (HTTP {status or error})")
    return {"token": payload["access_token"], "user_id": (payload.get("user") or {}).get("id", "")}
