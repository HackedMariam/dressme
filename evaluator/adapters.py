"""Un adaptateur par agent : appelle l'endpoint existant et ramène la réponse à une forme commune (Reply).

Aucun code d'agent n'est importé : tout passe par HTTP, avec le jeton du compte de test.
- Agents A2A (JSON-RPC `message/send`) : AI Stylist, Outfit Builder, Wardrobe, Similar (BO1 :8000), Trip (:8020),
  Gap (BO3 :8001). États natifs : completed / input-required / failed.
- Agents REST : orchestrateur BO1 (/api/assistant/chat), Stylist BO4 (:8061 /api/chat), orchestrateur (:8070 /api/chat,
  qui porte aussi Purchase Redundancy et le RAG). Leur état est déduit de la réponse.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from . import config
from .net import call


@dataclass
class Reply:
    state: str                          # completed | input-required | failed | unknown (réponse hors contrat)
    text: str = ""
    data: dict = field(default_factory=dict)
    context_id: str | None = None
    latency_ms: float = 0.0
    http_status: int | None = None
    error: str | None = None            # injoignable | timeout | None
    route: str | None = None            # orchestrateurs : l'agent choisi


@dataclass
class AgentSpec:
    name: str
    label: str
    kind: str                           # a2a | bo1_chat | orch_chat | bo4_chat | rag
    service: str                        # clé de config.URLS
    path: str
    timeout: float = 120.0
    llm: bool = True                    # appelle un LLM : budget de latence plus large


AGENTS: dict[str, AgentSpec] = {s.name: s for s in [
    AgentSpec("orchestrator_bo1", "Orchestrateur BO1", "bo1_chat", "bo1", "/api/assistant/chat"),
    AgentSpec("stylist", "AI Stylist", "a2a", "bo1", "/a2a/stylist"),
    AgentSpec("wardrobe", "Wardrobe Agent", "a2a", "bo1", "/a2a/wardrobe"),
    AgentSpec("similar", "Similar Agent", "a2a", "bo1", "/a2a/similar", llm=False),
    AgentSpec("outfit", "Outfit Builder", "a2a", "bo1", "/a2a/outfit"),
    AgentSpec("trip", "Trip Agent", "a2a", "trip", "/a2a/trip", timeout=180.0),
    AgentSpec("gap", "Gap Agent (BO3)", "a2a", "bo3", "/a2a/gap"),
    AgentSpec("purchase", "Purchase Redundancy (via l'orchestrateur)", "orch_chat", "orchestrator", "/api/chat", llm=False),
    AgentSpec("rag", "RAG BO5 (livres de mode)", "rag", "rag", "/ask"),
    AgentSpec("bo4", "Stylist BO4", "bo4_chat", "bo4", "/api/chat", llm=False),
    AgentSpec("orchestrator", "Orchestrateur (8070) + RAG", "orch_chat", "orchestrator", "/api/chat"),
]}


def _failed(status, error, latency, text="") -> Reply:
    return Reply(state="failed", text=text, http_status=status, error=error, latency_ms=latency)


def _text_of(parts: Any) -> str:
    return "\n".join(p.get("text", "") for p in (parts or []) if isinstance(p, dict) and p.get("kind") == "text")


def _a2a(spec: AgentSpec, base: str, token: str, text: str, data: dict, context_id: str | None) -> Reply:
    parts: list[dict] = []
    if text:
        parts.append({"kind": "text", "text": text})
    if data:
        parts.append({"kind": "data", "data": data})
    message: dict[str, Any] = {"kind": "message", "role": "user", "parts": parts, "messageId": str(uuid.uuid4())}
    if context_id:
        message["contextId"] = context_id
    body = {"jsonrpc": "2.0", "id": str(uuid.uuid4()), "method": "message/send", "params": {"message": message}}
    status, payload, error, ms = call("POST", base + spec.path, token=token, body=body, timeout=spec.timeout)
    if error or not isinstance(payload, dict):
        return _failed(status, error, ms)
    if payload.get("error") or not isinstance(payload.get("result"), dict):
        return _failed(status, None, ms, str((payload.get("error") or {}).get("message", "")))
    task = payload["result"]
    state = (task.get("status") or {}).get("state", "unknown")
    answer = _text_of(((task.get("status") or {}).get("message") or {}).get("parts"))
    artifacts = task.get("artifacts") or []
    result: dict = {}
    for artifact in artifacts:
        for part in artifact.get("parts") or []:
            if part.get("kind") == "data" and isinstance(part.get("data"), dict):
                result = part["data"]
    return Reply(state=state, text=answer, data=result, context_id=task.get("contextId"), latency_ms=ms, http_status=status)


def _rest(spec: AgentSpec, base: str, token: str, body: dict) -> tuple[int | None, dict, str | None, float]:
    status, payload, error, ms = call("POST", base + spec.path, token=token, body=body, timeout=spec.timeout)
    return status, payload if isinstance(payload, dict) else {}, error, ms


def _bo1_chat(spec, base, token, text, data, context_id) -> Reply:
    body = {"message": text, "thread_id": context_id, **{k: data[k] for k in ("city", "country", "unit") if k in data}}
    status, payload, error, ms = _rest(spec, base, token, body)
    if error or status != 200 or not payload:
        return _failed(status, error, ms)
    return Reply(state=payload.get("state", "unknown"), text=str(payload.get("reply", "")), context_id=payload.get("thread_id"),
                 data={"items": payload.get("items") or [], "result": payload.get("data") or {},
                       "agents_called": payload.get("agents_called") or [], "action": payload.get("action")},
                 latency_ms=ms, http_status=status, route=payload.get("agent"))


def _orch_chat(spec, base, token, text, data, context_id) -> Reply:
    status, payload, error, ms = _rest(spec, base, token, {"message": text, "thread_id": context_id})
    if error or status != 200 or not payload:
        return _failed(status, error, ms)
    result = payload.get("result") or {}
    details = result.get("details") or {}
    route = payload.get("route")
    state = "input-required" if route == "clarify" else ("completed" if result.get("ok", route != "clarify") else "failed")
    return Reply(state=state, text=str(payload.get("response", "")), context_id=payload.get("thread_id"),
                 data={"result": result, "details": details, "sources": details.get("sources") or [],
                       "trace": payload.get("trace") or [], "candidates": payload.get("candidates") or []},
                 latency_ms=ms, http_status=status, route=route)


def _bo4_chat(spec, base, token, text, data, context_id) -> Reply:
    status, payload, error, ms = _rest(spec, base, token, {"message": text, "thread_id": context_id})
    if error or status != 200 or not payload:
        return _failed(status, error, ms)
    outfits = payload.get("outfits") or []
    return Reply(state=payload.get("state") or "completed", text=str(payload.get("response", "")),
                 context_id=payload.get("thread_id"), data={"outfits": outfits, "request": payload.get("request") or {},
                                                            "trace": payload.get("trace") or []},
                 latency_ms=ms, http_status=status, route="stylist")


def _rag(spec, base, token, text, data, context_id) -> Reply:
    key = config.rag_key()
    status, payload, error, ms = call("POST", base + spec.path, body={"question": text, "top_k": 5}, timeout=spec.timeout,
                                      headers={"X-API-Key": key} if key else None)
    if error or status != 200 or not isinstance(payload, dict) or "answer" not in payload:
        return _failed(status, error, ms)
    return Reply(state="completed", text=str(payload.get("answer", "")), context_id=payload.get("conversation_id"),
                 data={"sources": payload.get("sources") or [], "citations": payload.get("citations") or [],
                       "grounded": bool(payload.get("grounded"))}, latency_ms=ms, http_status=status, route="knowledge")


def ask(agent: str, token: str, text: str = "", data: dict | None = None, context_id: str | None = None,
        service_down: bool = False) -> Reply:
    """Un tour de conversation avec l'agent. `service_down` : l'appel part vers un port fermé (cas « service arrêté »)."""
    spec = AGENTS[agent]
    base = config.URLS["down"] if service_down else config.URLS[spec.service]
    data = data or {}
    if spec.kind == "a2a":
        return _a2a(spec, base, token, text, data, context_id)
    return {"bo1_chat": _bo1_chat, "orch_chat": _orch_chat, "bo4_chat": _bo4_chat, "rag": _rag}[spec.kind](spec, base, token, text, data, context_id)
