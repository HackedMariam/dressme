"""A2A client: discover another agent by its Agent Card and hand it a task.

    client = A2AClient("http://127.0.0.1:8001/a2a/gap", token=user_token)
    card = client.card()                       # who is this agent, what are its skills?
    task = client.send("What is my wardrobe missing for winter work?", data={"goal": "winter_work"})
    client.text_of(task), client.data_of(task)

Any failure (service down, refusal, JSON-RPC error) raises `A2AError`, so the calling agent can degrade gracefully.
"""
from __future__ import annotations

import uuid
from typing import Any

import httpx

CARD_PATH = "/.well-known/agent-card.json"


class A2AError(RuntimeError):
    def __init__(self, message: str, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code


class A2AClient:
    def __init__(self, base_url: str, token: str | None = None, timeout: float = 90,
                 transport: httpx.BaseTransport | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.transport = transport

    # ------------------------------------------------------------------------------------------ plumbing
    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = self.token if self.token.lower().startswith("bearer ") else f"Bearer {self.token}"
        return headers

    def _client(self) -> httpx.Client:
        return httpx.Client(timeout=self.timeout, transport=self.transport)

    def _call(self, method: str, params: dict) -> dict:
        payload = {"jsonrpc": "2.0", "id": str(uuid.uuid4()), "method": method, "params": params}
        try:
            with self._client() as client:
                reply = client.post(self.base_url, json=payload, headers=self._headers())
        except httpx.HTTPError as error:
            raise A2AError(f"Agent unreachable at {self.base_url}: {type(error).__name__}") from error
        if reply.status_code in (401, 403):
            raise A2AError("The agent refused the credentials (sign in again)", reply.status_code)
        try:
            body = reply.json()
        except ValueError as error:
            raise A2AError(f"Invalid answer from the agent (HTTP {reply.status_code})") from error
        if not isinstance(body, dict):
            raise A2AError("Invalid answer from the agent")
        if body.get("error"):
            error = body["error"]
            raise A2AError(str(error.get("message", "Agent error")), error.get("code"))
        if "result" not in body:
            raise A2AError(f"The agent answered HTTP {reply.status_code} without a result")
        return body["result"]

    # ------------------------------------------------------------------------------------------ public API
    def card(self) -> dict:
        """The Agent Card (public, no credentials needed)."""
        try:
            with self._client() as client:
                reply = client.get(self.base_url + CARD_PATH)
            reply.raise_for_status()
            card = reply.json()
        except (httpx.HTTPError, ValueError) as error:
            raise A2AError(f"No Agent Card at {self.base_url}{CARD_PATH}: {type(error).__name__}") from error
        if not isinstance(card, dict) or "name" not in card or "skills" not in card:
            raise A2AError("Invalid Agent Card")
        return card

    def send(self, text: str = "", data: dict | None = None, context_id: str | None = None) -> dict:
        """Send one message and return the Task (`message/send`)."""
        parts: list[dict[str, Any]] = []
        if text:
            parts.append({"kind": "text", "text": text})
        if data:
            parts.append({"kind": "data", "data": data})
        if not parts:
            raise A2AError("Nothing to send")
        message: dict[str, Any] = {"kind": "message", "role": "user", "parts": parts, "messageId": str(uuid.uuid4())}
        if context_id:
            message["contextId"] = context_id
        return self._call("message/send", {"message": message})

    def get_task(self, task_id: str) -> dict:
        return self._call("tasks/get", {"id": task_id})

    # ------------------------------------------------------------------------------------------ helpers
    @staticmethod
    def state_of(task: dict) -> str:
        return (task.get("status") or {}).get("state", "unknown")

    @staticmethod
    def text_of(task: dict) -> str:
        message = (task.get("status") or {}).get("message") or {}
        return "\n".join(p.get("text", "") for p in message.get("parts", []) if p.get("kind") == "text").strip()

    @staticmethod
    def data_of(task: dict) -> dict:
        merged: dict = {}
        for artifact in task.get("artifacts") or []:
            for part in artifact.get("parts", []):
                if part.get("kind") == "data" and isinstance(part.get("data"), dict):
                    merged.update(part["data"])
        return merged
