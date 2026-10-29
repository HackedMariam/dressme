"""Query step for retrieval: translate French questions into English, without rewriting them.

Copied from the DressMe orchestrator (orchestrator/graph.py: is_french, TRANSLATE_PROMPT, GLOSSARY,
apply_glossary), not imported from it. It replaces the free LLM rewrite of rag/query_rewrite.py, which
added constraints the user never asked for ("budget 30 euros", "without shoes", "2023") and changed
garments (wool -> linen, scarf -> hat).

- English question: returned unchanged (no rewrite at all).
- French question: translated by the LLM at temperature 0 with a translation-only instruction, then a
  deterministic glossary fixes garment words the small model leaves in French ("col roule" -> turtleneck).
- Any failure (LLM down, empty or overlong output): the original question is used.
"""

from __future__ import annotations

import logging
import re
import unicodedata

logger = logging.getLogger(__name__)

TRANSLATE_PROMPT = (
    "Translate the user's fashion question into natural English. Translate only: do not add, remove or "
    "change any detail (no new occasion, season, budget, colour or garment). Keep garment names precise "
    "(col roule = turtleneck, veste = jacket, jupe = skirt, pull = sweater, foulard = scarf, laine = wool). "
    "Return only the English question, on one line, with no quotes."
)

# French garment words qwen2.5:3b sometimes leaves in its translation ("black col roule").
# Replaced after translation, with or without accents; order matters ("mini-jupe" before "jupe").
GLOSSARY = (
    (r"cols? roul[eé]s?", "turtleneck"), (r"mini-?jupes?", "mini skirt"), (r"jupes?", "skirt"),
    (r"pantalons?", "trousers"), (r"vestes?", "jacket"), (r"blousons?", "jacket"), (r"manteaux?", "coat"),
    (r"pulls?", "sweater"), (r"chemises?", "shirt"), (r"robes?", "dress"), (r"chaussures?", "shoes"),
    (r"[ée]cossaise?s?", "plaid"), (r"foulards?", "scarf"), (r"laine", "wool"), (r"lin", "linen"),
)


def plain(text: str) -> str:
    """Lowercase, without accents, straight apostrophes."""
    text = unicodedata.normalize("NFKD", text.lower().replace("’", "'"))
    return "".join(c for c in text if not unicodedata.combining(c))


def is_french(text: str) -> bool:
    value = plain(text)
    return bool(re.search(r"\b(je|j'|est-ce|que|quel(le)?s?|comment|pourquoi|une?|des|mes|ma|mon|pour|avec|"
                          r"acheter|porter|tenue|quand|selon|faire)\b", value)) and not re.search(
        r"\b(the|should|what|how|my|which|do|does)\b", value)


def apply_glossary(text: str) -> str:
    for pattern, english in GLOSSARY:
        text = re.sub(rf"\b{pattern}\b", english, text, flags=re.IGNORECASE)
    return text


def translate_query(question: str) -> str:
    """Query sent to retrieval: the question itself, translated into English when it is French."""
    if not question.strip() or not is_french(question):
        return question
    from config import get_settings                      # lazy: keeps this module importable in tests
    from rag.llm_client import LLMUnavailable, chat_completion

    if not get_settings().query_rewrite_enabled:         # same switch as the former rewrite step
        return question
    try:
        response = chat_completion(
            model=get_settings().llm_model,
            messages=[{"role": "system", "content": TRANSLATE_PROMPT},
                      {"role": "user", "content": question}],
            temperature=0.0,
            max_tokens=120,
        )
        english = (response.choices[0].message.content or "").strip()
        english = english.splitlines()[0].strip().strip('"').strip("'") if english else ""
        if 2 <= len(english) <= 300:
            return apply_glossary(english)
    except LLMUnavailable as error:
        logger.info("Query translation unavailable: %s", error)
    except Exception as error:  # pragma: no cover - defensive
        logger.warning("Query translation failed: %s", error)
    return question
