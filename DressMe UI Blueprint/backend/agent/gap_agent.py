"""Tool-calling loop for the BO3 wardrobe gap agent."""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from .prompts import SYSTEM_PROMPT
from .tools import TOOL_SCHEMAS, GapAgentTools

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
load_dotenv(Path(__file__).resolve().parents[3] / ".env")

# Any OpenAI-compatible endpoint works: OpenAI by default, or Groq/Gemini via LLM_BASE_URL.
DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"
MAX_STEPS = 6


@dataclass
class AgentResult:
    answer: str
    trace: list[dict[str, Any]] = field(default_factory=list)
    ranking: dict[str, Any] | None = None


def llm_settings() -> tuple[str | None, str, str]:
    return (
        os.getenv("LLM_API_KEY"),
        os.getenv("LLM_BASE_URL", DEFAULT_BASE_URL),
        os.getenv("LLM_MODEL", DEFAULT_MODEL),
    )


def llm_clients() -> list[tuple[str, str, OpenAI]]:
    api_key, base_url, model = llm_settings()
    configured = []
    if api_key:
        configured.append(("primary", api_key, base_url, model))
    groq_key = os.getenv("GROQ_API_KEY")
    if groq_key:
        configured.append(("groq", groq_key, "https://api.groq.com/openai/v1",
                           os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")))
    return [(name, selected_model, OpenAI(api_key=key, base_url=url))
            for name, key, url, selected_model in configured]


class GapAgent:
    def __init__(self, tools: GapAgentTools) -> None:
        providers = llm_clients()
        if not providers:
            raise RuntimeError("Set LLM_API_KEY or GROQ_API_KEY in backend/.env (see backend/.env.example).")
        self.providers = providers
        self.client = providers[0][2]
        self.model = providers[0][1]
        self.tools = tools

    def run(self, user_message: str, history: list[dict[str, str]]) -> AgentResult:
        """history holds earlier user/assistant turns (short-term memory)."""
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            *history,
            {"role": "user", "content": user_message},
        ]

        trace: list[dict[str, Any]] = []
        self.tools.last_ranking = None
        for step in range(1, MAX_STEPS + 1):
            response = None
            last_error = None
            for provider, model, client in self.providers:
                try:
                    response = client.chat.completions.create(
                        model=model, messages=messages, tools=TOOL_SCHEMAS,
                        tool_choice="auto", temperature=0.2)
                    break
                except Exception as error:
                    last_error = error
                    if provider != self.providers[-1][0]:
                        continue
            if response is None:
                raise RuntimeError(
                    "I can still analyse your wardrobe with DressMe's built-in rules, "
                    "but the conversational AI is taking a short break. Please try again soon."
                ) from last_error
            message = response.choices[0].message
            if not message.tool_calls:
                return AgentResult(message.content or "", trace, self.tools.last_ranking)

            messages.append(
                {
                    "role": "assistant",
                    "content": message.content or "",
                    "tool_calls": [call.model_dump() for call in message.tool_calls],
                }
            )
            for call in message.tool_calls:
                try:
                    arguments = json.loads(call.function.arguments or "{}") or {}
                except json.JSONDecodeError:
                    arguments = {}
                result = self.tools.call(call.function.name, arguments)
                trace.append({"step": step, "tool": call.function.name, "arguments": arguments, "result": result})
                messages.append(
                    {"role": "tool", "tool_call_id": call.id, "content": json.dumps(result, default=str)}
                )

        return AgentResult(
            "I could not finish the analysis within the step limit. Please rephrase your request.",
            trace,
            self.tools.last_ranking,
        )
