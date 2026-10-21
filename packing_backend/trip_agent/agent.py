"""Custom LLM tool-calling agent loop for DressMe trip planning."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Callable

from .config import MAX_AGENT_ITERATIONS
from .llm import LLMClient, LLMError
from .logging_utils import log_event
from .schemas import AgentResponse, AgentState
from .tools import TripTools, tool_specs
from .wardrobe import WardrobeProvider

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
You are DressMe's Trip Agent. You decide which tools to call; Python validates
arguments and executes deterministic operations.

Core rules:
1. Never invent destination, dates, duration, activities, luggage limits,
   weather, wardrobe items, or optimizer results.
2. For a new trip or a clarification, call get_trip_details first. If the tool
   reports missing_fields, ask the user one concise question and stop.
3. Once details are complete: call get_weather, then get_wardrobe at most once,
   then get_activity_requirements, then optimize_trip.
4. After a successful optimization, call generate_checklist. After INFEASIBLE,
   call suggest_alternatives and present the options; never silently relax hard
   constraints.
5. Use update_trip only when the user asks to change an existing trip. Set
   reoptimize=true when the user wants the updated plan immediately.
6. Avoid repeated tool calls when the same state is already available.
7. Use update_checklist to mark packed items; never rerun the optimizer for that.
8. If a tool returns an error, inspect it and either correct the next tool call or
   explain the problem. Do not fabricate success.
9. Final answers must be concise and grounded in tool output. Include the
   optimization status, item count, total clothing weight, weather source, and
   checklist progress when available.
10. check_gaps is optional and may return unavailable; that is expected.
""".strip()


class TripAgent:
    """Stateful custom agent with a native LLM tool-calling loop."""

    def __init__(
        self,
        session_id: str | None = None,
        llm: LLMClient | None = None,
        wardrobe_provider: WardrobeProvider | None = None,
        gap_checker: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        max_iterations: int = MAX_AGENT_ITERATIONS,
        use_llm: bool | None = None,
        allow_weather_network: bool = True,
    ) -> None:
        self.llm = llm or LLMClient(enabled=use_llm)
        self.state = AgentState(
            session_id=session_id or f"trip-{uuid.uuid4().hex[:8]}"
        )
        self.tools = TripTools(
            state=self.state,
            llm=self.llm,
            wardrobe_provider=wardrobe_provider,
            gap_checker=gap_checker,
            allow_weather_network=allow_weather_network,
        )
        self.max_iterations = max_iterations

    # ------------------------------------------------------------------
    # Public interaction API
    # ------------------------------------------------------------------
    def handle(self, user_text: str, auto_continue: bool = True) -> AgentResponse:
        text = (user_text or "").strip()
        if not text:
            return self._response("Please describe the trip you want to plan.")

        self.state.add_user_message(text)
        use_llm = self.llm.available
        if use_llm:
            try:
                return self._run_llm_loop(text, auto_continue=auto_continue)
            except LLMError as exc:
                self._note_error(f"LLM unavailable: {exc}")
                log_event(logger, "agent_llm_fallback", error=str(exc), level=logging.WARNING)
                return self._run_fallback_loop(auto_continue=auto_continue)
            except Exception as exc:  # pragma: no cover - defensive boundary
                self._note_error(f"Agent loop failed: {type(exc).__name__}: {exc}")
                log_event(logger, "agent_loop_failed", error=str(exc), level=logging.ERROR)
                return self._run_fallback_loop(auto_continue=auto_continue)

        return self._run_fallback_loop(auto_continue=auto_continue)

    def handle_structured(
        self,
        structured: dict[str, Any],
        auto_continue: bool = True,
    ) -> AgentResponse:
        """Start from a structured trip payload instead of free text."""
        self.state.add_user_message(json.dumps(structured, ensure_ascii=False))
        result = self.tools.execute(
            "get_trip_details",
            {"structured": structured},
        )
        if not result.get("ok"):
            message = f"Could not validate structured input: {result.get('error')}"
            self.state.add_assistant_message(message)
            return self._response(message)
        if result.get("needs_clarification"):
            question = result.get("question") or "I need a few more trip details."
            self.state.add_assistant_message(question)
            return self._response(question)
        if auto_continue:
            self._complete_workflow()
        message = self._compose_completion_message()
        self.state.add_assistant_message(message)
        return self._response(message)

    def update_trip(
        self,
        updates: dict[str, Any],
        reoptimize: bool = True,
    ) -> AgentResponse:
        result = self.tools.execute(
            "update_trip",
            {"updates": updates, "reoptimize": reoptimize},
        )
        if not result.get("ok"):
            return self._response(self._compose_completion_message())
        if result.get("needs_clarification"):
            question = result.get("question") or "I need the missing trip details."
            self.state.add_assistant_message(question)
            return self._response(question)
        return self._response(self._compose_completion_message())

    def mark_packed(self, item_id: str, packed: bool = True) -> AgentResponse:
        result = self.tools.execute(
            "update_checklist",
            {"item_id": item_id, "packed": packed},
        )
        if not result.get("ok"):
            return self._response(
                f"Could not update checklist: {result.get('error', 'unknown error')}"
            )
        item = result.get("item") or {}
        message = (
            f"Marked {item.get('name', item_id)} as "
            f"{'packed' if packed else 'not packed'}."
        )
        self.state.add_assistant_message(message)
        return self._response(message)

    def suggest_alternatives(self) -> AgentResponse:
        self.tools.execute("suggest_alternatives", {})
        return self._response(self._compose_completion_message())

    def state_json(self) -> dict[str, Any]:
        return self.state.model_dump(mode="json")

    # ------------------------------------------------------------------
    # LLM loop
    # ------------------------------------------------------------------
    def _run_llm_loop(self, user_text: str, auto_continue: bool) -> AgentResponse:
        tools = tool_specs()
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    f"{SYSTEM_PROMPT}\n\nCurrent state summary:\n"
                    f"{json.dumps(self.state.context_summary(), default=str)}"
                ),
            }
        ]
        for message in self.state.messages[-16:]:
            messages.append({"role": message.role, "content": message.content})

        for iteration in range(self.max_iterations):
            log_event(
                logger,
                "agent_iteration",
                iteration=iteration + 1,
                status=self.state.status,
            )
            turn = self.llm.chat(messages, tools=tools)

            if turn.tool_calls:
                assistant_message: dict[str, Any] = {
                    "role": "assistant",
                    "content": turn.content or None,
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.name,
                                "arguments": call.raw_arguments or json.dumps(call.arguments),
                            },
                        }
                        for call in turn.tool_calls
                    ],
                }
                messages.append(assistant_message)

                for call in turn.tool_calls:
                    result = self.tools.execute(call.name, call.arguments)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "name": call.name,
                            "content": json.dumps(result, default=str),
                        }
                    )

                    if result.get("needs_clarification"):
                        question = result.get("question") or (
                            "I need a few more trip details before I can continue."
                        )
                        self.state.add_assistant_message(question)
                        return self._response(question)

                continue

            content = (turn.content or "").strip()
            if content:
                self.state.add_assistant_message(content)

            if auto_continue and self._should_complete():
                self._complete_workflow()
                message = self._compose_completion_message()
                if content and content not in message:
                    message = f"{content}\n\n{message}"
                return self._response(message)

            if not content:
                content = self._compose_completion_message()
                self.state.add_assistant_message(content)
            return self._response(content)

        # Bounded loop exhausted: deterministic completion still uses the same
        # validated tools and never invents optimizer output.
        if auto_continue and self._should_complete():
            self._complete_workflow()
        message = (
            "I reached the tool-call limit for this turn. "
            + self._compose_completion_message()
        )
        self.state.add_assistant_message(message)
        return self._response(message)

    # ------------------------------------------------------------------
    # Deterministic fallback / completion
    # ------------------------------------------------------------------
    def _run_fallback_loop(self, auto_continue: bool) -> AgentResponse:
        if self.state.trip_details is None or self.state.trip_details.missing_fields:
            latest = ""
            for message in reversed(self.state.messages):
                if message.role == "user":
                    latest = message.content
                    break
            result = self.tools.execute("get_trip_details", {"text": latest})
            if result.get("needs_clarification"):
                question = result.get("question") or (
                    "I need the missing trip details before I can continue."
                )
                self.state.add_assistant_message(question)
                return self._response(question)
            if auto_continue:
                self._complete_workflow()
        elif auto_continue:
            self._complete_workflow()

        message = self._compose_completion_message()
        self.state.add_assistant_message(message)
        return self._response(message)

    def _should_complete(self) -> bool:
        if self.state.needs_clarification:
            return False
        if self.state.trip_details is None:
            return False
        if self.state.capsule is not None and self.state.checklist is not None:
            return False
        if self.state.status == "optimized":
            return self.state.checklist is None
        return True

    def _complete_workflow(self) -> None:
        """Enforce dependencies with Python while reusing the same tools."""
        details = self.state.trip_details
        if details is None:
            latest = ""
            for message in reversed(self.state.messages):
                if message.role == "user":
                    latest = message.content
                    break
            self.tools.execute("get_trip_details", {"text": latest})
            details = self.state.trip_details

        if details is None or details.compute_missing_fields():
            self.state.needs_clarification = True
            self.state.missing_info = details.compute_missing_fields() if details else []
            self.state.clarification_question = (
                details.clarification_question()
                if details
                else "I need the missing trip details before I can continue."
            )
            return

        if self.state.weather is None:
            weather = self.tools.execute("get_weather", {})
            if not weather.get("ok"):
                return

        if not self.state.daily_requirements:
            requirements = self.tools.execute("get_activity_requirements", {})
            if not requirements.get("ok"):
                return

        if self.state.optimization_result is None:
            optimization = self.tools.execute("optimize_trip", {})
            if not optimization.get("ok"):
                return

        if self.state.status == "infeasible":
            self.tools.execute("suggest_alternatives", {})
            return

        if self.state.capsule is not None and self.state.checklist is None:
            self.tools.execute("generate_checklist", {})

    # ------------------------------------------------------------------
    # Response helpers
    # ------------------------------------------------------------------
    def _response(self, message: str) -> AgentResponse:
        self.state.touch()
        return AgentResponse(
            message=message,
            status=self.state.status,
            trip_details=self.state.trip_details,
            weather_source=self.state.weather.source if self.state.weather else None,
            weather_summary=self.state.weather.summary() if self.state.weather else [],
            daily_requirements=self.state.daily_requirements,
            capsule=self.state.capsule,
            checklist=self.state.checklist,
            missing_info=self.state.missing_info,
            suggestions=self.state.suggestions,
            errors=self.state.errors,
        )

    def _compose_completion_message(self) -> str:
        if self.state.needs_clarification:
            if self.state.clarification_question:
                return self.state.clarification_question
            if self.state.trip_details:
                return self.state.trip_details.clarification_question()
            return "I need a few more details before I can continue."

        if self.state.capsule is not None:
            capsule = self.state.capsule
            checklist = self.state.checklist or capsule.checklist
            weather_source = capsule.trip.weather_source
            lines = [
                (
                    f"Trip capsule ready for {capsule.trip.destination} "
                    f"({capsule.trip.start_date.isoformat()} to "
                    f"{capsule.trip.end_date.isoformat()}, "
                    f"{capsule.trip.duration_days} days)."
                ),
                (
                    f"Optimization: {capsule.optimization_status}; "
                    f"{capsule.number_of_items} unique clothing items; "
                    f"{capsule.total_weight_g / 1000:.2f} kg of clothing."
                ),
                (
                    f"Weather source: {weather_source}"
                    + (" (synthetic fallback, not a real forecast)"
                       if weather_source == "synthetic_fallback" else "")
                    + "."
                ),
                (
                    f"Checklist: {checklist.total_items} items, "
                    f"{checklist.packed_items} packed, "
                    f"{checklist.total_items - checklist.packed_items} remaining."
                ),
            ]
            if self.state.weather and self.state.weather.warning:
                lines.append(f"Weather note: {self.state.weather.warning}")
            return "\n".join(lines)

        if self.state.status == "infeasible" or (
            self.state.optimization_result
            and self.state.optimization_result.get("status") == "INFEASIBLE"
        ):
            reason = (
                self.state.optimization_result.get("reason")
                if self.state.optimization_result
                else None
            )
            lines = [
                "The optimizer returned INFEASIBLE; I did not relax any hard constraints."
            ]
            if reason:
                lines.append(f"Reason: {reason}")
            if self.state.suggestions:
                lines.append("Options to recover:")
                lines.extend(f"- {suggestion}" for suggestion in self.state.suggestions)
            else:
                lines.append(
                    "Call suggest_alternatives to inspect missing items or a tight "
                    "luggage limit."
                )
            return "\n".join(lines)

        if self.state.missing_info:
            labels = ", ".join(self.state.missing_info)
            return f"I still need: {labels}."

        if self.state.errors:
            return (
                "I could not complete the trip plan. "
                f"Last error: {self.state.errors[-1]}"
            )

        return (
            "I have updated the trip state but the workflow is not complete yet. "
            "Ask me to continue, or provide any missing trip details."
        )

    def _note_error(self, error: str) -> None:
        if error not in self.state.errors:
            self.state.errors.append(error)
            self.state.touch()
