"""Client of the fashion-knowledge RAG service (rag_backend/, port 8010).

The AI stylist calls it as a tool: it answers a style question from a corpus of fashion books and returns the
passages it used as numbered sources ([S1], [S2]...). The service is optional: when it is down, slow or not
configured, `advise` returns None and the stylist answers from the wardrobe alone.
"""
from __future__ import annotations

import logging

import httpx

from . import config

log = logging.getLogger("dressme.rag")


def advise(question: str, *, transport: httpx.BaseTransport | None = None) -> dict | None:
    """Ask the RAG service. Returns {"answer": str, "sources": [{"marker", "title", "page", "source"}]} or None."""
    question = (question or "").strip()
    if not question or not config.RAG_URL:
        return None
    headers = {config.RAG_API_KEY_HEADER: config.RAG_API_KEY} if config.RAG_API_KEY else {}
    try:
        with httpx.Client(timeout=config.RAG_TIMEOUT, transport=transport) as client:
            reply = client.post(f"{config.RAG_URL.rstrip('/')}/ask", json={"question": question[:1000], "top_k": 5},
                                headers=headers)
        reply.raise_for_status()
        body = reply.json()
    except (httpx.HTTPError, ValueError) as error:
        log.warning("fashion knowledge unavailable: %s: %s", type(error).__name__, error)
        return None

    answer = str(body.get("answer") or "").strip()
    if not answer:
        return None
    seen: set[str] = set()
    sources = []
    for citation in body.get("citations") or []:
        marker = str(citation.get("marker") or "").strip()
        if not marker or marker in seen:
            continue
        seen.add(marker)
        sources.append({"marker": marker, "title": citation.get("title") or citation.get("source") or "Fashion book",
                        "page": citation.get("page"), "source": citation.get("source")})
    if not sources:
        # No cited passage = the service found nothing relevant ("I don't know..."): that is not advice.
        return None
    return {"answer": answer, "sources": sources, "grounded": bool(body.get("grounded"))}
