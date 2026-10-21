"""Thin native OpenAI chat-completions wrapper with tool calling."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from .config import (
    DEFAULT_LLM_TIMEOUT_SECONDS,
    get_api_key,
    get_model,
    llm_enabled,
)
from .logging_utils import log_event

logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    """Raised when the configured LLM cannot be used or returns invalid data."""


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]
    raw_arguments: str = ""


@dataclass
class AssistantTurn:
    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw_message: Any = None


class LLMClient:
    """Small wrapper that keeps the provider integration in one place."""

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        timeout: float = DEFAULT_LLM_TIMEOUT_SECONDS,
        enabled: bool | None = None,
    ) -> None:
        self.model = model or get_model()
        self.api_key = api_key or get_api_key()
        self.timeout = timeout
        self.enabled = llm_enabled() if enabled is None else enabled
        self._client = None

    @property
    def available(self) -> bool:
        return bool(self.enabled and self.api_key)

    def _get_client(self):
        if self._client is None:
            if not self.api_key:
                raise LLMError("OPENAI_API_KEY is not configured")
            try:
                from openai import OpenAI
            except ImportError as exc:  # pragma: no cover - environment dependent
                raise LLMError("The openai package is not installed") from exc
            self._client = OpenAI(
                api_key=self.api_key,
                timeout=self.timeout,
                max_retries=1,
            )
        return self._client

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str = "auto",
    ) -> AssistantTurn:
        if not self.available:
            raise LLMError("LLM is disabled or OPENAI_API_KEY is missing")

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice

        try:
            response = self._get_client().chat.completions.create(**kwargs)
        except Exception as exc:  # pragma: no cover - network/provider dependent
            log_event(logger, "llm_request_failed", error=str(exc))
            raise LLMError(f"LLM request failed: {exc}") from exc

        message = response.choices[0].message
        calls: list[ToolCall] = []
        for call in message.tool_calls or []:
            raw_arguments = call.function.arguments or "{}"
            try:
                arguments = json.loads(raw_arguments)
                if not isinstance(arguments, dict):
                    arguments = {"_invalid_arguments": arguments}
            except json.JSONDecodeError:
                arguments = {"_invalid_json": raw_arguments}
            calls.append(
                ToolCall(
                    id=call.id,
                    name=call.function.name,
                    arguments=arguments,
                    raw_arguments=raw_arguments,
                )
            )

        log_event(
            logger,
            "llm_response",
            content_chars=len(message.content or ""),
            tool_calls=[call.name for call in calls],
        )
        return AssistantTurn(
            content=message.content,
            tool_calls=calls,
            raw_message=message,
        )

    def extract_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        """Ask the LLM for one JSON object (structured extraction)."""
        if not self.available:
            raise LLMError("LLM is disabled or OPENAI_API_KEY is missing")

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        request: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }

        try:
            response = self._get_client().chat.completions.create(**request)
        except Exception as first_error:
            # Some compatible providers/models reject response_format. Retry
            # once without it before falling back to the deterministic parser.
            logger.warning("Structured-output request failed; retrying plain: %s", first_error)
            try:
                request.pop("response_format", None)
                response = self._get_client().chat.completions.create(**request)
            except Exception as exc:  # pragma: no cover - network dependent
                raise LLMError(f"LLM extraction failed: {exc}") from exc

        content = response.choices[0].message.content or ""
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            start = content.find("{")
            end = content.rfind("}")
            if start < 0 or end <= start:
                raise LLMError("LLM extraction did not return valid JSON")
            try:
                parsed = json.loads(content[start:end + 1])
            except json.JSONDecodeError as exc:
                raise LLMError("LLM extraction returned malformed JSON") from exc
        if not isinstance(parsed, dict):
            raise LLMError("LLM extraction JSON must be an object")
        return parsed
