"""A2A client used by BO1/Trip Agent to consult the BO3 Gap Agent."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import httpx
from a2a.client import A2ACardResolver, ClientConfig, create_client
from a2a.helpers import new_text_message
from a2a.types import Role, SendMessageRequest


class A2AGapChecker:
    def __init__(self, base_url: str | None = None, api_key: str | None = None) -> None:
        self.base_url = (base_url or os.getenv("GAP_AGENT_A2A_URL", "http://127.0.0.1:8001/a2a")).rstrip("/")
        self.api_key = api_key or os.getenv("GAP_AGENT_A2A_KEY", "")

    def __call__(self, capsule: dict[str, Any]) -> dict[str, Any]:
        try:
            return asyncio.run(self._call(capsule))
        except Exception as exc:
            return {"available": False, "error": f"A2A Gap Agent failed: {type(exc).__name__}: {exc}"}

    async def _call(self, capsule: dict[str, Any]) -> dict[str, Any]:
        headers = {"X-A2A-Key": self.api_key} if self.api_key else {}
        async with httpx.AsyncClient(headers=headers, timeout=60.0, trust_env=False) as http_client:
            resolver = A2ACardResolver(httpx_client=http_client, base_url=self.base_url)
            card = await resolver.get_agent_card()
            client = await create_client(
                agent=card,
                client_config=ClientConfig(streaming=False, httpx_client=http_client),
            )
            try:
                request = SendMessageRequest(
                    message=new_text_message(
                        json.dumps(
                            {
                                "user_id": capsule.get("user_id") or os.getenv("WARDROBE_USER_ID", "local"),
                                "capsule": capsule,
                            },
                            ensure_ascii=False,
                        ),
                        role=Role.ROLE_USER,
                    )
                )
                async for response in client.send_message(request):
                    for candidate in _response_candidates(response):
                        if "findings" in candidate or "error" in candidate:
                            return candidate
                return {"available": False, "error": "A2A Gap Agent returned no result"}
            finally:
                await client.close()


def _json_candidates(text: str) -> list[dict[str, Any]]:
    decoder = json.JSONDecoder()
    result: list[dict[str, Any]] = []
    for index, character in enumerate(text):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            result.append(value)
    return result


def _response_candidates(response: Any) -> list[dict[str, Any]]:
    if hasattr(response, "model_dump"):
        return _json_candidates(json.dumps(response.model_dump(mode="json"), ensure_ascii=False))
    result: list[dict[str, Any]] = []
    task = getattr(response, "task", None)
    for artifact in getattr(task, "artifacts", []) or getattr(response, "artifacts", []):
        for part in getattr(artifact, "parts", []):
            text = getattr(getattr(part, "root", part), "text", "")
            if text:
                try:
                    value = json.loads(text)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    result.append(value)
    return result
