"""
User authentication - email + password accounts, JWT bearer tokens (HS256).

Passwords: PBKDF2-HMAC-SHA256 (Python standard library), random 16-byte salt, 600 000 iterations
(OWASP 2023 recommendation), constant-time comparison.

Anonymous use stays possible unless AUTH_REQUIRED=True: requests without a token act on the shared
"local" guest wardrobe, so the app keeps working exactly as before for a single user.
"""

import base64
import hashlib
import hmac
import logging
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Optional

import jwt
from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)

GUEST_USER_ID = "local"
ALGORITHM = "HS256"
PBKDF2_ITERATIONS = int(os.getenv("PASSWORD_HASH_ITERATIONS", "600000"))
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[A-Za-z]{2,}$")


# ----------------------------------------------------------------------------
# Passwords
# ----------------------------------------------------------------------------

def hash_password(password: str, iterations: int = PBKDF2_ITERATIONS) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"pbkdf2_sha256${iterations}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iterations, salt, digest = stored.split("$")
        if scheme != "pbkdf2_sha256":
            return False
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt), int(iterations))
        return hmac.compare_digest(candidate, base64.b64decode(digest))
    except (ValueError, TypeError):
        return False


def password_problem(password: str) -> Optional[str]:
    """French message describing why a password is too weak, None when it is acceptable"""
    if len(password) < 8:
        return "Le mot de passe doit contenir au moins 8 caractères."
    if len(password) > 128:
        return "Le mot de passe ne doit pas dépasser 128 caractères."
    if password.isalpha() or password.isdigit():
        return "Le mot de passe doit mélanger lettres et chiffres (ou symboles)."
    return None


# ----------------------------------------------------------------------------
# Tokens
# ----------------------------------------------------------------------------

class TokenService:
    def __init__(self, secret_key: str, expire_hours: int, secret_file: Path):
        self.expire_hours = expire_hours
        self.secret_key = secret_key or self._load_or_create_secret(secret_file)

    @staticmethod
    def _load_or_create_secret(path: Path) -> str:
        """No SECRET_KEY configured: generate one once and keep it, so tokens survive restarts"""
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
        secret = secrets.token_urlsafe(48)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(secret, encoding="utf-8")
        logger.warning(f"SECRET_KEY not set - generated one in {path}. Set SECRET_KEY in .env for production.")
        return secret

    def create(self, user: Dict) -> Dict:
        now = datetime.now(timezone.utc)
        expires = now + timedelta(hours=self.expire_hours)
        token = jwt.encode({"sub": user["id"], "email": user["email"], "iat": now, "exp": expires, "typ": "access"},
                           self.secret_key, algorithm=ALGORITHM)
        return {"access_token": token, "token_type": "bearer", "expires_at": expires.isoformat(),
                "expires_in": self.expire_hours * 3600}

    def decode(self, token: str) -> Dict:
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[ALGORITHM], options={"require": ["sub", "exp"]})
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Session expirée - reconnectez-vous.",
                                headers={"WWW-Authenticate": "Bearer"})
        except jwt.PyJWTError:
            raise HTTPException(status_code=401, detail="Jeton d'authentification invalide.",
                                headers={"WWW-Authenticate": "Bearer"})
        if payload.get("typ") != "access":
            raise HTTPException(status_code=401, detail="Jeton d'authentification invalide.")
        return payload


def bearer_token(request: Request) -> Optional[str]:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() == "bearer" and token.strip():
        return token.strip()
    return None


def resolve_user_id(token: Optional[str], tokens: TokenService, auth_required: bool) -> str:
    """Token -> user id; no token -> guest (or 401 when accounts are mandatory)"""
    if token:
        return tokens.decode(token)["sub"]
    if auth_required:
        raise HTTPException(status_code=401, detail="Connexion requise.", headers={"WWW-Authenticate": "Bearer"})
    return GUEST_USER_ID
