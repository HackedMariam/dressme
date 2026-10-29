"""Grounded fashion answers with inline citations and streaming."""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from typing import Any

from config import get_settings
from rag.llm_client import LLMUnavailable, chat_completion
from rag.translate import translate_query
from rag.retriever import retrieve

logger = logging.getLogger(__name__)

CITATION_RE = re.compile(r"\[S(\d+)\]")

NO_INFO_ANSWER = (
    "I don't have enough information in the DressMe knowledge base to "
    "answer that confidently. I can still help with general styling "
    "reasoning if you want, but I won't pretend it came from the sources."
)

SYSTEM_PROMPT = """You are DressMe, a fashion and wardrobe assistant.

Grounding rules:
1. Use the supplied knowledge context as the primary evidence.
2. Cite every factual claim taken from the context with an inline marker:
   [S1], [S2], ... matching the source labels in the context.
3. If the context is insufficient, say so clearly. Do not invent citations,
   page numbers, author claims, or "facts" that are not in the context.
4. You may add general styling reasoning, but label it explicitly as
   "General guidance" and keep it separate from source-backed statements.
5. Prefer concrete, actionable advice. Respect constraints the user gives
   (occasion, season, body, budget, colour, destination).
6. Do not claim the retrieved context says something it does not say.

Formatting: concise paragraphs and short bullet lists. Put citations inline,
not only in a trailing source list."""


def _dedupe_sources(passages: list[dict]) -> list[dict]:
    sources: dict[tuple, dict] = {}

    for passage in passages:
        key = (passage.get("source"), passage.get("page"))
        existing = sources.get(key)
        item = {
            "chunk_id": passage.get("chunk_id"),
            "source": passage.get("source"),
            "page": passage.get("page"),
            "title": passage.get("title"),
            "section": passage.get("section"),
            "category": passage.get("category"),
            "topics": passage.get("topics") or [],
            "document_id": passage.get("document_id"),
            "similarity": passage.get("similarity"),
            "retrieval": passage.get("retrieval"),
        }
        if existing is None or (item["similarity"] or 0) > (
            existing["similarity"] or 0
        ):
            if existing:
                item["chunk_ids"] = list(
                    dict.fromkeys(
                        (existing.get("chunk_ids") or [])
                        + [existing.get("chunk_id"), item.get("chunk_id")]
                    )
                )
            sources[key] = item
        else:
            existing.setdefault("chunk_ids", []).append(item["chunk_id"])

    return list(sources.values())


def _build_context(
    passages: list[dict],
) -> tuple[str, list[dict], dict[str, dict]]:
    settings = get_settings()
    parts = []
    used = 0
    included = []

    for index, passage in enumerate(passages, start=1):
        body = passage.get("content") or ""
        header = (
            f"[S{index}] Source: {passage.get('source', 'Unknown')}, "
            f"page {passage.get('page', '?')}"
        )
        if passage.get("title"):
            header += f", title: {passage['title']}"
        if passage.get("section"):
            header += f", section: {passage['section']}"
        block = f"{header}\n{body}"

        if used + len(block) > settings.max_context_chars and included:
            break

        parts.append(block)
        used += len(block)
        included.append({"marker": f"S{index}", **passage})

    source_lookup = {
        item["marker"]: {
            "chunk_id": item.get("chunk_id"),
            "source": item.get("source"),
            "page": item.get("page"),
            "title": item.get("title"),
            "section": item.get("section"),
            "similarity": item.get("similarity"),
        }
        for item in included
    }
    return "\n\n---\n\n".join(parts), included, source_lookup


def _history_messages(history: list[dict] | None) -> list[dict]:
    messages = []
    for message in (history or [])[-8:]:
        role = message.get("role")
        content = (message.get("content") or "").strip()
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content})
    return messages


def _user_prompt(question: str, context: str) -> str:
    return (
        f"User question:\n{question}\n\n"
        f"Retrieved knowledge (cite as [S1], [S2], ...):\n{context}\n\n"
        "Answer the question using the retrieved evidence. If the evidence "
        "does not cover the question, say that the knowledge base does not "
        "contain enough information."
    )


def _public_sources(passages: list[dict]) -> list[dict]:
    return _dedupe_sources(passages)


def _citations(answer: str, lookup: dict[str, dict]) -> list[dict]:
    markers = list(dict.fromkeys(CITATION_RE.findall(answer or "")))
    citations = []
    for marker in markers:
        source = lookup.get(f"S{marker}")
        if source:
            citations.append({"marker": f"[S{marker}]", **source})
    return citations


def _base_response(question: str, rewritten: str, passages: list[dict]) -> dict:
    source_lookup = {
        f"S{index}": {
            "chunk_id": passage.get("chunk_id"),
            "source": passage.get("source"),
            "page": passage.get("page"),
            "title": passage.get("title"),
            "section": passage.get("section"),
            "similarity": passage.get("similarity"),
        }
        for index, passage in enumerate(passages, start=1)
    }
    return {
        "question": question,
        "rewritten_query": rewritten,
        "sources": _public_sources(passages),
        "source_lookup": source_lookup,
    }


def answer_question(
    question: str,
    top_k: int = 5,
    *,
    history: list[dict] | None = None,
    min_similarity: float | None = None,
) -> dict:
    """Generate a grounded answer with inline citations."""
    settings = get_settings()
    rewritten = translate_query(question)  # French -> English translation, no free rewrite
    passages = retrieve(
        rewritten,
        top_k=top_k,
        min_similarity=min_similarity,
    )

    if not passages:
        return {
            "answer": NO_INFO_ANSWER,
            "sources": [],
            "citations": [],
            "rewritten_query": rewritten,
            "grounded": False,
        }

    context, _included, _lookup = _build_context(passages)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *_history_messages(history),
        {"role": "user", "content": _user_prompt(question, context)},
    ]

    response = chat_completion(
        model=settings.llm_model,
        messages=messages,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
    )

    answer = response.choices[0].message.content or ""
    base = _base_response(question, rewritten, passages)
    citations = _citations(answer, base["source_lookup"])

    usage = getattr(response, "usage", None)
    if usage is not None and hasattr(usage, "model_dump"):
        usage = usage.model_dump()

    return {
        "answer": answer,
        "sources": base["sources"],
        "citations": citations,
        "rewritten_query": rewritten,
        "grounded": bool(citations),
        "usage": usage,
    }


def stream_answer(
    question: str,
    top_k: int = 5,
    *,
    history: list[dict] | None = None,
    min_similarity: float | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield SSE-friendly events: sources, token, citations, done, error."""
    settings = get_settings()
    rewritten = translate_query(question)  # French -> English translation, no free rewrite
    passages = retrieve(
        rewritten,
        top_k=top_k,
        min_similarity=min_similarity,
    )

    if not passages:
        yield {"type": "sources", "sources": [], "rewritten_query": rewritten}
        yield {"type": "token", "text": NO_INFO_ANSWER}
        yield {
            "type": "done",
            "citations": [],
            "grounded": False,
            "rewritten_query": rewritten,
        }
        return

    context, _included, _lookup = _build_context(passages)
    base = _base_response(question, rewritten, passages)
    yield {
        "type": "sources",
        "sources": base["sources"],
        "rewritten_query": rewritten,
    }

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *_history_messages(history),
        {"role": "user", "content": _user_prompt(question, context)},
    ]

    answer_parts: list[str] = []
    try:
        stream = chat_completion(
            model=settings.llm_model,
            messages=messages,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content or ""
            if delta:
                answer_parts.append(delta)
                yield {"type": "token", "text": delta}
    except LLMUnavailable as error:
        logger.error("LLM stream failed: %s", error)
        yield {
            "type": "error",
            "message": "The styling model is temporarily unavailable.",
        }
        return
    except Exception as error:  # pragma: no cover - provider specific
        logger.exception("LLM stream failed: %s", error)
        yield {
            "type": "error",
            "message": "The styling model returned an unexpected error.",
        }
        return

    answer = "".join(answer_parts)
    yield {
        "type": "done",
        "citations": _citations(answer, base["source_lookup"]),
        "grounded": bool(_citations(answer, base["source_lookup"])),
        "rewritten_query": rewritten,
    }


if __name__ == "__main__":
    question = input("Ask DressMe: ")
    result = answer_question(question)

    print("\nDressMe:", result["answer"])
    if result.get("rewritten_query") and result["rewritten_query"] != question:
        print(f"\nRetrieval query: {result['rewritten_query']}")
    print("\nSources:")
    for source in result["sources"]:
        print(
            f"- {source['source']}, page {source['page']}, "
            f"similarity {source.get('similarity') or 0:.3f}, "
            f"chunk {source.get('chunk_id')}"
        )
