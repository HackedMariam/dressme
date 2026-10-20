"""Lazy LLM client with timeouts, retries, and domain errors."""

from __future__ import annotations

import logging
import time
from functools import lru_cache
from typing import Any

from config import get_settings

logger = logging.getLogger(__name__)


class LLMUnavailable(RuntimeError):
    """Raised when the LLM is not configured or a call fails."""


@lru_cache(maxsize=1)
def get_llm_client():
    settings = get_settings()

    if not settings.llm_configured:
        raise LLMUnavailable(
            "LLM is not configured. Set LLM_API_KEY (or OPENAI_API_KEY) "
            "and LLM_MODEL."
        )

    from openai import OpenAI

    return OpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url or None,
        timeout=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
    )


def chat_completion(**kwargs: Any):
    """Call the chat completions endpoint with a normalized error type."""
    settings = get_settings()
    client = get_llm_client()

    last_error: Exception | None = None
    for attempt in range(1, settings.llm_max_retries + 2):
        try:
            return client.chat.completions.create(**kwargs)
        except Exception as error:
            last_error = error
            if attempt > settings.llm_max_retries:
                break
            delay = 0.5 * (2 ** (attempt - 1))
            logger.warning(
                "LLM call failed (attempt %s/%s): %s; retrying in %.1fs",
                attempt,
                settings.llm_max_retries + 1,
                error,
                delay,
            )
            time.sleep(delay)

    raise LLMUnavailable(str(last_error)) from last_error
