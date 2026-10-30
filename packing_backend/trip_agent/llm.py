"""Thin native OpenAI chat-completions wrapper with tool calling."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from .config import (
    DEFAULT_LLM_TIMEOUT_SECONDS,
    get_llm_providers,
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
        self.api_key = api_key
        self.timeout = timeout
        self.enabled = llm_enabled() if enabled is None else enabled
        self._clients: list[tuple[str, str, Any]] = []

    @property
    def available(self) -> bool:
        return bool(self.enabled and (self.api_key or get_llm_providers()))

    def _get_clients(self):
        if not self._clients:
            try:
                from openai import OpenAI
            except ImportError as exc:  # pragma: no cover - environment dependent
                raise LLMError("The openai package is not installed") from exc
            providers = [("openai", self.api_key, self.model)] if self.api_key else get_llm_providers()
            for name, key, model in providers:
                self._clients.append((
                    name,
                    model,
                    OpenAI(
                        api_key=key,
                        base_url="https://api.groq.com/openai/v1" if name == "groq" else None,
                        timeout=self.timeout,
                        max_retries=1,
                    ),
                ))
        return self._clients

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str = "auto",
    ) -> AssistantTurn:
        if not self.available:
            raise LLMError("LLM is disabled or no LLM API key is configured")

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice

        last_error = None
        response = None
        for provider, model, client in self._get_clients():
            try:
                response = client.chat.completions.create(**{**kwargs, "model": model})
                break
            except Exception as exc:  # pragma: no cover - network/provider dependent
                last_error = exc
                log_event(logger, "llm_request_failed", provider=provider, error=str(exc))
        if response is None:
            raise LLMError(f"LLM request failed: {last_error}") from last_error

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
            raise LLMError("LLM is disabled or no LLM API key is configured")

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

        response = None
        last_error = None
        for provider, model, client in self._get_clients():
            try:
                response = client.chat.completions.create(**{**request, "model": model})
                break
            except Exception as first_error:
                logger.warning("%s structured-output request failed; retrying plain: %s", provider, first_error)
                try:
                    plain_request = {key: value for key, value in request.items() if key != "response_format"}
                    response = client.chat.completions.create(**{**plain_request, "model": model})
                    break
                except Exception as exc:  # pragma: no cover - network dependent
                    last_error = exc
        if response is None:
            raise LLMError(f"LLM extraction failed: {last_error}") from last_error

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
