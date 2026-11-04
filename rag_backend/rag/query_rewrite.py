"""Rewrite vague chat questions into retrieval-friendly queries."""

from __future__ import annotations

import logging

from config import get_settings
from rag.llm_client import LLMUnavailable, chat_completion

logger = logging.getLogger(__name__)

REWRITE_PROMPT = """You rewrite a user's fashion question into a short,
specific search query for a retrieval system. Keep the user's intent and any
constraints (occasion, season, body, colour, budget). Do not answer the
question. Return only the rewritten query, on one line, with no quotes."""


def rewrite_query(question: str, history: list[dict] | None = None) -> str:
    """Return a rewritten query, falling back to the original on failure."""
    settings = get_settings()
    if not settings.query_rewrite_enabled or not question.strip():
        return question

    recent = [
        f"{message.get('role')}: {message.get('content')}"
        for message in (history or [])[-4:]
    ]
    history_text = "\n".join(recent)

    messages = [{"role": "system", "content": REWRITE_PROMPT}]
    if history_text:
        messages.append(
            {
                "role": "user",
                "content": (
                    f"Recent conversation:\n{history_text}\n\n"
                    f"Question to rewrite:\n{question}"
                ),
            }
        )
    else:
        messages.append(
            {
                "role": "user",
                "content": f"Question to rewrite:\n{question}",
            }
        )

    try:
        response = chat_completion(
            model=settings.llm_model,
            messages=messages,
            temperature=0.0,
            max_tokens=80,
        )
        rewritten = (response.choices[0].message.content or "").strip()
        rewritten = rewritten.splitlines()[0].strip().strip('"').strip("'")
        if 2 <= len(rewritten) <= 300:
            return rewritten
    except LLMUnavailable as error:
        logger.info("Query rewrite unavailable: %s", error)
    except Exception as error:  # pragma: no cover - defensive
        logger.warning("Query rewrite failed: %s", error)

    return question
