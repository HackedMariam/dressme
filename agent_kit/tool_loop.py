"""The tool-calling loop of every DressMe agent, as a LangGraph graph.

    START -> llm --(tool calls)--> tools -> llm ...
                 \\--(answer the agent should reconsider, once)--> nudge -> llm
                 \\--(final answer, error or too many rounds)--> END

An agent plugs in four things and keeps all its own rules:
  call_llm(messages)        -> an OpenAI-style message (`.content`, `.tool_calls`)
  run_tool(name, args)      -> the tool's result as a string (the code, never the LLM, touches the data)
  nudge(content)            -> a reminder to send back to the model (or None): used once, for example when the model
                               answered a style question without consulting the fashion books
  max_rounds                -> LLM calls allowed before giving up

`run_loop` returns the final text plus how it ended: "answer", "error" or "exhausted".
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

log = logging.getLogger("dressme.agent_kit")


class LoopState(TypedDict, total=False):
    messages: list[dict]
    rounds: int
    nudged: bool
    last: Any            # the last model message
    final: Optional[str]
    outcome: str         # "answer" | "error" | "exhausted"


def _assistant_message(message: Any) -> dict:
    entry: dict[str, Any] = {"role": "assistant", "content": message.content if message.content is not None else ""}
    if getattr(message, "tool_calls", None):
        entry["tool_calls"] = [call.model_dump() for call in message.tool_calls]
    return entry


def build_tool_loop(*, call_llm: Callable[[list[dict]], Any], run_tool: Callable[[str, dict], str],
                    max_rounds: int, nudge: Callable[[str], Optional[str]] | None = None):
    """Compile the loop graph for one agent."""

    def llm(state: LoopState) -> dict:
        if state.get("rounds", 0) >= max_rounds:
            return {"outcome": "exhausted", "last": None}
        try:
            message = call_llm(state["messages"])
        except Exception:
            log.exception("agent LLM call failed")
            return {"outcome": "error", "last": None, "rounds": state.get("rounds", 0) + 1}
        return {"last": message, "rounds": state.get("rounds", 0) + 1, "outcome": ""}

    def route(state: LoopState) -> str:
        if state.get("outcome") in ("error", "exhausted"):
            return END
        message = state["last"]
        if getattr(message, "tool_calls", None):
            return "tools"
        if nudge and not state.get("nudged") and nudge(message.content or ""):
            return "nudge"
        return "finish"

    def tools(state: LoopState) -> dict:
        message = state["last"]
        messages = [*state["messages"], _assistant_message(message)]
        for call in message.tool_calls:
            try:
                args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            if not isinstance(args, dict):
                args = {}
            messages.append({"role": "tool", "tool_call_id": call.id, "content": run_tool(call.function.name, args)})
        return {"messages": messages}

    def nudge_node(state: LoopState) -> dict:
        message = state["last"]
        reminder = nudge(message.content or "") if nudge else None
        return {"messages": [*state["messages"], {"role": "assistant", "content": message.content or ""},
                            {"role": "user", "content": reminder or ""}], "nudged": True}

    def finish(state: LoopState) -> dict:
        return {"final": state["last"].content or "", "outcome": "answer"}

    graph = StateGraph(LoopState)
    graph.add_node("llm", llm)
    graph.add_node("tools", tools)
    graph.add_node("nudge", nudge_node)
    graph.add_node("finish", finish)
    graph.add_edge(START, "llm")
    graph.add_conditional_edges("llm", route, {"tools": "tools", "nudge": "nudge", "finish": "finish", END: END})
    graph.add_edge("tools", "llm")
    graph.add_edge("nudge", "llm")
    graph.add_edge("finish", END)
    return graph.compile()


def run_loop(*, messages: list[dict], call_llm: Callable[[list[dict]], Any], run_tool: Callable[[str, dict], str],
             max_rounds: int, nudge: Callable[[str], Optional[str]] | None = None) -> tuple[Optional[str], str]:
    """Run the loop; returns (final text or None, outcome)."""
    graph = build_tool_loop(call_llm=call_llm, run_tool=run_tool, max_rounds=max_rounds, nudge=nudge)
    # Each tool round is two graph steps: allow plenty of supersteps for max_rounds.
    state = graph.invoke({"messages": messages, "rounds": 0, "nudged": False}, {"recursion_limit": max_rounds * 4 + 8})
    return state.get("final"), state.get("outcome", "error")
