"""A2A (Agent2Agent) server side: an Agent Card and the JSON-RPC endpoint of one agent.

What the protocol gives DressMe: every agent publishes who it is and what it can do (its Agent Card), and any other
agent can discover it and hand it a task over plain HTTP, with a task state to follow (completed, failed,
input-required...). Implemented here: protocol version 0.3 over JSON-RPC 2.0 with the methods `message/send`,
`tasks/get` and `tasks/cancel`; the card is served at `<agent url>/.well-known/agent-card.json`.
Not implemented (declared as such in the card): streaming and push notifications.

An agent is plugged in with `build_router(...)`: it supplies a synchronous `handler(call) -> AgentResult` (run in a
thread pool, because the agents call an LLM) and, optionally, a FastAPI dependency that authenticates the caller
(the same Supabase bearer token the rest of the API uses).
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

log = logging.getLogger("dressme.a2a")

PROTOCOL_VERSION = "0.3.0"
CARD_PATH = "/.well-known/agent-card.json"

# JSON-RPC and A2A error codes
PARSE_ERROR, INVALID_REQUEST, METHOD_NOT_FOUND, INVALID_PARAMS, INTERNAL_ERROR = -32700, -32600, -32601, -32602, -32603
TASK_NOT_FOUND, TASK_NOT_CANCELABLE, UNSUPPORTED_OPERATION = -32001, -32002, -32004

TERMINAL_STATES = {"completed", "failed", "canceled", "rejected"}


@dataclass
class Skill:
    id: str
    name: str
    description: str
    tags: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)

    def card(self) -> dict:
        return {"id": self.id, "name": self.name, "description": self.description, "tags": self.tags,
                "examples": self.examples, "inputModes": ["text/plain", "application/json"],
                "outputModes": ["text/plain", "application/json"]}


@dataclass
class AgentCall:
    """What a handler receives: the user's words, optional structured data, who is asking and the conversation."""
    text: str
    data: dict
    context_id: str
    principal: Any
    message_id: str


@dataclass
class AgentResult:
    """What a handler returns. `state` is an A2A task state; `data` is the structured answer (an artifact)."""
    text: str = ""
    data: Optional[dict] = None
    state: str = "completed"
    context_id: Optional[str] = None   # lets the agent name the conversation (the Trip Agent uses its session id)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _message(role: str, parts: list[dict], context_id: str, task_id: str | None = None) -> dict:
    message = {"kind": "message", "role": role, "parts": parts, "messageId": str(uuid.uuid4()), "contextId": context_id}
    if task_id:
        message["taskId"] = task_id
    return message


class TaskStore:
    """Recent tasks, kept in memory so that `tasks/get` works; bounded, and each task belongs to its caller."""

    def __init__(self, limit: int = 200) -> None:
        self.limit = limit
        self._tasks: "OrderedDict[str, tuple[str, dict]]" = OrderedDict()
        self._lock = threading.Lock()

    def put(self, owner: str, task: dict) -> None:
        with self._lock:
            self._tasks[task["id"]] = (owner, task)
            self._tasks.move_to_end(task["id"])
            while len(self._tasks) > self.limit:
                self._tasks.popitem(last=False)

    def get(self, owner: str, task_id: str) -> dict | None:
        with self._lock:
            entry = self._tasks.get(task_id)
        return entry[1] if entry and entry[0] == owner else None


def _owner(principal: Any) -> str:
    return str(getattr(principal, "id", principal))


def _rpc_error(request_id: Any, code: int, message: str, status: int = 200) -> JSONResponse:
    return JSONResponse({"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}},
                        status_code=status)


def _split_message(message: Any) -> tuple[str, dict, str | None]:
    """The text, the structured data and the contextId of an incoming A2A message (raises ValueError if malformed)."""
    if not isinstance(message, dict) or not isinstance(message.get("parts"), list) or not message["parts"]:
        raise ValueError("message.parts must be a non-empty list")
    if message.get("role", "user") != "user":
        raise ValueError("message.role must be 'user'")
    texts, data = [], {}
    for part in message["parts"]:
        if not isinstance(part, dict):
            raise ValueError("each part must be an object")
        kind = part.get("kind")
        if kind == "text" and isinstance(part.get("text"), str):
            texts.append(part["text"])
        elif kind == "data" and isinstance(part.get("data"), dict):
            data.update(part["data"])
        else:
            raise ValueError(f"unsupported part kind {kind!r}: use 'text' or 'data'")
    context_id = message.get("contextId")
    return "\n".join(texts).strip(), data, str(context_id) if context_id else None


def build_card(*, name: str, description: str, version: str, skills: list[Skill], url: str, authenticated: bool) -> dict:
    card = {
        "protocolVersion": PROTOCOL_VERSION,
        "name": name,
        "description": description,
        "url": url,
        "preferredTransport": "JSONRPC",
        "version": version,
        "provider": {"organization": "DressMe", "url": "https://github.com/HackedMariam/dressme"},
        "capabilities": {"streaming": False, "pushNotifications": False, "stateTransitionHistory": False},
        "defaultInputModes": ["text/plain", "application/json"],
        "defaultOutputModes": ["text/plain", "application/json"],
        "skills": [skill.card() for skill in skills],
    }
    if authenticated:
        card["securitySchemes"] = {"bearer": {"type": "http", "scheme": "bearer", "bearerFormat": "Supabase session token"}}
        card["security"] = [{"bearer": []}]
    return card


def build_router(*, prefix: str, name: str, description: str, version: str, skills: list[Skill],
                 handler: Callable[[AgentCall], AgentResult],
                 principal: Callable[..., Any] | None = None) -> APIRouter:
    """The router of one agent: GET `<prefix>/.well-known/agent-card.json` and POST `<prefix>` (JSON-RPC)."""
    router = APIRouter(prefix=prefix, tags=[f"a2a:{name}"])
    tasks = TaskStore()
    authenticated = principal is not None

    @router.get(CARD_PATH)
    async def agent_card(request: Request) -> dict:
        base = str(request.base_url).rstrip("/")
        return build_card(name=name, description=description, version=version, skills=skills,
                          url=base + prefix, authenticated=authenticated)

    async def current_principal(request: Request) -> Any:
        if principal is None:
            return "anonymous"
        # The caller's dependency may need the Authorization header: call it the FastAPI way.
        return await _resolve(principal, request)

    @router.post("")
    async def rpc(request: Request, caller: Any = Depends(current_principal)) -> JSONResponse:
        try:
            body = await request.json()
        except ValueError:
            return _rpc_error(None, PARSE_ERROR, "Invalid JSON")
        if not isinstance(body, dict) or body.get("jsonrpc") != "2.0" or not isinstance(body.get("method"), str):
            return _rpc_error(body.get("id") if isinstance(body, dict) else None, INVALID_REQUEST, "Not a JSON-RPC 2.0 request")
        request_id, method, params = body.get("id"), body["method"], body.get("params") or {}
        if not isinstance(params, dict):
            return _rpc_error(request_id, INVALID_PARAMS, "params must be an object")
        owner = _owner(caller)

        if method == "message/send":
            try:
                text, data, context_id = _split_message(params.get("message"))
            except ValueError as error:
                return _rpc_error(request_id, INVALID_PARAMS, str(error))
            if not text and not data:
                return _rpc_error(request_id, INVALID_PARAMS, "The message is empty")
            task_id, context_id = str(uuid.uuid4()), context_id or str(uuid.uuid4())
            call = AgentCall(text=text, data=data, context_id=context_id, principal=caller,
                             message_id=str(params["message"].get("messageId") or uuid.uuid4()))
            started = time.perf_counter()
            try:
                result = await run_in_threadpool(handler, call)
            except Exception:   # the agent failed: report a failed task, never the internals
                log.exception("A2A agent %s failed", name)
                result = AgentResult(text=f"{name} could not complete this request.", state="failed")
            if result.context_id:
                context_id = result.context_id
            log.info("A2A %s message/send -> %s in %.0f ms", name, result.state, (time.perf_counter() - started) * 1000)
            task = {
                "kind": "task", "id": task_id, "contextId": context_id,
                "status": {"state": result.state, "timestamp": _now(),
                           "message": _message("agent", [{"kind": "text", "text": result.text}], context_id, task_id)},
                "history": [_message("user", [{"kind": "text", "text": text}] + ([{"kind": "data", "data": data}] if data else []),
                                     context_id, task_id)],
            }
            if result.data is not None:
                task["artifacts"] = [{"artifactId": str(uuid.uuid4()), "name": "result",
                                      "parts": [{"kind": "data", "data": result.data}]}]
            tasks.put(owner, task)
            return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": task})

        if method in ("tasks/get", "tasks/cancel"):
            task_id = params.get("id")
            task = tasks.get(owner, task_id) if isinstance(task_id, str) else None
            if task is None:
                return _rpc_error(request_id, TASK_NOT_FOUND, "Task not found")
            if method == "tasks/cancel":
                if task["status"]["state"] in TERMINAL_STATES:
                    return _rpc_error(request_id, TASK_NOT_CANCELABLE, "The task is already finished")
                task["status"] = {"state": "canceled", "timestamp": _now()}
            return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": task})

        if method in ("message/stream", "tasks/resubscribe") or method.startswith("tasks/pushNotificationConfig"):
            return _rpc_error(request_id, UNSUPPORTED_OPERATION, "This agent does not support streaming or push notifications")
        return _rpc_error(request_id, METHOD_NOT_FOUND, f"Unknown method {method!r}")

    return router


async def _resolve(dependency: Callable[..., Any], request: Request) -> Any:
    """Run an authentication dependency of the host application with the request's Authorization header."""
    import inspect

    authorization = request.headers.get("authorization")
    parameters = inspect.signature(dependency).parameters
    kwargs: dict[str, Any] = {}
    for param_name in parameters:
        if param_name == "authorization":
            kwargs[param_name] = authorization
        elif param_name == "request":
            kwargs[param_name] = request
    if inspect.iscoroutinefunction(dependency):
        return await dependency(**kwargs)
    return await run_in_threadpool(dependency, **kwargs)   # the host's check may call Supabase: keep the loop free
