"""Lazy Supabase client with bounded retries."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from functools import lru_cache
from typing import Any, TypeVar

from config import get_settings

logger = logging.getLogger(__name__)

T = TypeVar("T")


class SupabaseUnavailable(RuntimeError):
    """Raised when Supabase is not configured or cannot be reached."""


@lru_cache(maxsize=1)
def get_supabase():
    settings = get_settings()

    if not settings.supabase_configured:
        raise SupabaseUnavailable(
            "Supabase is not configured. Set SUPABASE_URL and "
            "SUPABASE_SERVICE_ROLE_KEY."
        )

    from supabase import create_client

    return create_client(settings.supabase_url, settings.supabase_key)


def _is_retryable(error: Exception) -> bool:
    """PostgREST returns permanent 4xx errors that should not be retried."""
    text = str(error).lower()
    permanent_markers = (
        "pgrst202",
        "pgrst204",
        "could not find the function",
        "does not exist",
        "permission denied",
        "invalid api key",
        "unauthorized",
        "violates",
    )
    if any(marker in text for marker in permanent_markers):
        return False

    code = getattr(error, "code", None)
    if isinstance(code, str):
        if code.startswith("PGRST"):
            return False
        if code.startswith("42"):
            return False
    return True


def execute_with_retries(
    build_query: Callable[[], Any],
    *,
    attempts: int = 3,
    base_delay: float = 0.4,
) -> Any:
    """Execute a Supabase query, retrying transient failures."""
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            return build_query().execute()
        except Exception as error:  # supabase raises several client errors
            last_error = error
            if attempt == attempts or not _is_retryable(error):
                break
            delay = base_delay * (2 ** (attempt - 1))
            logger.warning(
                "Supabase query failed (attempt %s/%s): %s; retrying in %.1fs",
                attempt,
                attempts,
                error,
                delay,
            )
            time.sleep(delay)

    raise SupabaseUnavailable(str(last_error)) from last_error
