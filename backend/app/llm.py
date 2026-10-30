"""OpenAI-compatible LLM clients with a Groq failover."""

from __future__ import annotations

import logging
from typing import Any, Callable

from . import config

logger = logging.getLogger(__name__)


def clients() -> list[tuple[str, str, Any]]:
    from openai import OpenAI

    configured: list[tuple[str, str, str]] = []
    if config.OPENAI_API_KEY:
        configured.append(("openai", config.OPENAI_API_KEY, config.LLM_MODEL))
    if config.GROQ_API_KEY:
        configured.append(("groq", config.GROQ_API_KEY, config.GROQ_MODEL))
    return [
        (
            provider,
            model,
            OpenAI(api_key=key, base_url=base_url, timeout=config.LLM_TIMEOUT, max_retries=2),
        )
        for provider, key, model, base_url in (
            (provider, key, model, config.GROQ_BASE_URL if provider == "groq" else None)
            for provider, key, model in configured
        )
    ]


def call_with_fallback(operation: Callable[[Any, str, str], Any]) -> Any:
    available = clients()
    if not available:
        raise RuntimeError("No LLM API key is configured.")
    last_error: Exception | None = None
    for provider, model, client in available:
        try:
            return operation(client, provider, model)
        except Exception as error:
            last_error = error
            logger.warning("%s LLM call failed; trying the next provider: %s", provider, error)
    assert last_error is not None
    raise last_error
