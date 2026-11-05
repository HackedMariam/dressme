"""The Orchestrator (LangGraph): one conversation, the right agent for each request.

    START -> route --+-> stylist  -+
                     +-> wardrobe -+
                     +-> outfit   -+
                     +-> trip     -+--> respond -> END
                     +-> gap      -+
                     +-> redirect -+   (Should I buy / Find Similar: they need a photo, so the answer points to the page)
                     +-> clarify  -+

`route` picks the agent: the LLM (JSON, only the agents listed below are accepted) with the FR/EN rules as a safety net
when it is unavailable or answers badly. A conversation is a LangGraph thread with a checkpointer, so the orchestrator
remembers the last turns: a question the Trip Agent or the Wardrobe Agent left open (`input-required`, or a change
waiting for the user's yes) is continued with the SAME agent on the next message, whatever the words.

How the agents are reached: the AI Stylist, the Wardrobe Agent and the Outfit Builder run in this service (direct
calls); the Trip Agent (Help Me Pack) and the Gap Agent (BO3) are other services: they are called over A2A with the
user's own token, exactly like any other A2A client would.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import Callable, Optional, TypedDict

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from a2a_protocol import A2AClient, A2AError, AgentCall  # noqa: E402
from langchain_core.runnables import RunnableConfig  # noqa: E402
from langgraph.graph import END, START, StateGraph  # noqa: E402

from . import a2a_agents, agent, config, wardrobe_a2a, wardrobe_agent  # noqa: E402

log = logging.getLogger("dressme.orchestrator")

TRIP_URL = os.getenv("TRIP_A2A_URL", "http://127.0.0.1:8020/a2a/trip")
GAP_URL = os.getenv("GAP_A2A_URL", "http://127.0.0.1:8001/a2a/gap")
HISTORY_TURNS = 8

AGENTS = {
    "stylist": ("AI Stylist", "advice on what to wear, colours, fabrics, how to style a piece (uses the weather and fashion books)"),
    "wardrobe": ("Wardrobe Agent", "find, count or compare the user's own pieces, correct a piece (changes need a confirmation)"),
    "outfit": ("Outfit Builder", "build complete outfits from the wardrobe for an occasion and a season"),
    "trip": ("Trip Agent", "plan a trip: what to pack, a suitcase, a packing checklist"),
    "gap": ("Gap Agent", "what the wardrobe is missing, what to buy for a goal"),
    "redirect": ("Shopping pages", "should I buy this item / find the pieces of a look in a photo: needs a photo, handled by a page"),
    "clarify": ("Assistant", "the request is too vague or is small talk: ask what the user wants"),
}

# FR / EN safety net: the words that point to one agent.
RULES = [
    ("trip", r"\b(valise|bagages?|suitcase|luggage|pack(ing)?|voyage|trip|travel|vacances|holiday|partir)\b"),
    ("gap", r"\b(manque|manquent|missing|lacunes?|gaps?|what should i buy|que dois-je acheter|what to buy)\b"),
    ("redirect", r"\b(should i buy|dois-je acheter|worth (buying|it)|vaut-il|similar to this|ressemble|recreate this look|cette photo|this photo)\b"),
    ("outfit", r"\b(build|make|create|compose|g[eé]n[eè]re|cr[eé]e|fais|propose)\b.*\b(outfits?|tenues?|looks?)\b"),
    ("wardrobe", r"\b(how many|combien|do i (have|own)|ai-je|est-ce que j'ai|show me my|montre|find my|trouve|cherche|corrige|fix|change the colou?r|count|compare|similar)\b"),
    ("stylist", r"\b(wear|porter|mettre|habiller|style|colou?rs?|couleurs?|assortir|match|conseil|advice|fabric|tissu|dress ?code)\b"),
]
YES_NO = re.compile(r"^\s*(yes|y|ok|okay|sure|confirm|oui|non|no|n|cancel|annule)\b", re.I)


def rule_candidates(message: str) -> list[str]:
    lowered = message.lower()
    return [name for name, pattern in RULES if re.search(pattern, lowered)]


ROUTER_SYSTEM = (
    "You are the router of DressMe, a personal wardrobe app. Choose the ONE agent that must answer the user's latest "
    "message, using the recent conversation for follow-ups. Agents:\n"
    + "\n".join(f"- {name}: {description}" for name, (_, description) in AGENTS.items())
    + '\nAnswer with ONLY a JSON object: {"agent": "<one of the names above>", "why": "<five words>"}. '
      "A question about what to wear or how to combine things is stylist; building complete outfits is outfit; "
      "packing or a trip is trip; what is missing or what to buy is gap."
)


def decide_route(message: str, history: list[dict], llm: Optional[Callable[[list[dict]], str]]) -> tuple[str, str]:
    """(agent, why). The LLM chooses; the rules decide when it cannot or when it answers outside the list."""
    candidates = rule_candidates(message)
    if llm is not None:
        recent = [{"role": "user" if t["role"] == "user" else "assistant", "content": t["text"][:300]} for t in history[-4:]]
        try:
            data = json.loads(llm([{"role": "system", "content": ROUTER_SYSTEM}, *recent, {"role": "user", "content": message[:500]}]))
            chosen = str(data.get("agent", "")).strip().lower()
            if chosen in AGENTS:
                return chosen, " ".join(str(data.get("why", "")).split())[:80] or "llm"
        except Exception:
            log.warning("router LLM unusable, falling back on the rules", exc_info=True)
    if candidates:
        return candidates[0], "rules"
    return "clarify", "no rule matched"


# ------------------------------------------------------------------------------------------------ the graph
class State(TypedDict, total=False):
    message: str
    user_id: str
    place: dict
    context_id: str
    history: list[dict]
    awaiting: Optional[dict]
    agent: str
    why: str
    reply: str
    items: list[dict]
    data: dict
    action: Optional[dict]
    state: str
    agents_called: list[str]


class RequestToken:
    """Request credential kept in runtime configuration, never in graph state."""

    __slots__ = ("_value",)

    def __init__(self, value: str):
        self._value = value

    def reveal(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return "RequestToken(***)"


def _request_token(config: Optional[dict]) -> Optional[str]:
    configurable = (config or {}).get("configurable") or {}
    token = configurable.get("__authorization")
    return token.reveal() if isinstance(token, RequestToken) else None


def _client(url: str, authorization: Optional[str]) -> A2AClient:
    return A2AClient(url, token=authorization, timeout=120)


def make_router_llm() -> Optional[Callable[[list[dict]], str]]:
    if not config.OPENAI_API_KEY:
        return None
    from openai import OpenAI

    client = OpenAI(api_key=config.OPENAI_API_KEY, timeout=config.LLM_TIMEOUT, max_retries=1)

    def llm(messages: list[dict]) -> str:
        return client.chat.completions.create(model=config.LLM_MODEL, temperature=0, max_completion_tokens=60, messages=messages,
                                              response_format={"type": "json_object"}).choices[0].message.content or "{}"
    return llm


def node_route(state: State) -> dict:
    reset = {"reply": "", "items": [], "data": {}, "action": None, "state": "completed", "agents_called": []}
    waiting = state.get("awaiting")
    # An agent is waiting for this answer. A pending change only continues on yes / no: anything else is a new request.
    if waiting and (waiting["agent"] != "wardrobe" or YES_NO.match(state["message"])):
        return {**reset, "agent": waiting["agent"], "why": "continues the open question"}
    agent_name, why = decide_route(state["message"], state.get("history", []), make_router_llm())
    return {**reset, "agent": agent_name, "why": why}


def pick(state: State) -> str:
    return state["agent"]


def node_stylist(state: State, config: RunnableConfig) -> dict:
    authorization = _request_token(config)
    result = agent.chat(wardrobe_a2a.list_items(state["user_id"], authorization), state["message"], state.get("place"), authorization)
    return {"reply": result["reply"], "items": result.get("items", []), "agents_called": ["AI Stylist"], "awaiting": None,
            "data": {k: result.get(k) for k in ("sections", "weather", "sources", "filters")}}


def node_wardrobe(state: State) -> dict:
    waiting = state.get("awaiting") or {}
    context = waiting.get("context") or state["context_id"]
    result = wardrobe_agent.converse(state["user_id"], state["message"], context_id=context)
    awaiting = {"agent": "wardrobe", "context": result["context_id"]} if result["pending"] else None
    return {"reply": result["reply"], "items": result["items"], "awaiting": awaiting, "state": result["state"],
            "agents_called": ["Wardrobe Agent"], "data": {"pending": result["pending"], "filters": result["filters"]}}


def node_outfit(state: State, config: RunnableConfig) -> dict:
    result = a2a_agents.handle_outfit(AgentCall(text=state["message"], data=dict(state.get("place") or {}), context_id=state["context_id"],
                                                principal=SimpleUser(state["user_id"]), message_id="",
                                                authorization=_request_token(config)))
    return {"reply": result.text, "state": result.state, "awaiting": None, "agents_called": ["Outfit Builder"], "data": result.data or {}}


class SimpleUser:
    def __init__(self, user_id: str) -> None:
        self.id = user_id


def _a2a(state: State, url: str, label: str, key: str, config: RunnableConfig) -> dict:
    waiting = state.get("awaiting") or {}
    client = _client(url, _request_token(config))
    try:
        task = client.send(state["message"], data={}, context_id=waiting.get("context"))
    except A2AError as error:
        return {"reply": f"The {label} is not reachable right now ({error}). Try again in a moment.", "state": "failed",
                "awaiting": None, "agents_called": [f"{label} (unreachable)"], "data": {}}
    open_question = client.state_of(task) == "input-required"
    # The trip lives in the Trip Agent's session (its A2A contextId): the page Help Me Pack can open that very trip.
    action = ({"page": "help-me-pack", "label": "Open Help Me Pack", "session_id": task.get("contextId")}
              if key == "trip" and client.state_of(task) in ("completed", "input-required") and task.get("contextId") else None)
    return {"reply": client.text_of(task), "state": client.state_of(task), "agents_called": [f"{label} (A2A)"], "action": action,
            "awaiting": {"agent": key, "context": task.get("contextId")} if open_question else None,
            # kept under its own key: the page reads data.weather / data.sections only for the AI Stylist's answers
            "data": {"a2a_result": client.data_of(task)}}


def node_trip(state: State, config: RunnableConfig) -> dict:
    return _a2a(state, TRIP_URL, "Trip Agent", "trip", config)


def node_gap(state: State, config: RunnableConfig) -> dict:
    return _a2a(state, GAP_URL, "Gap Agent", "gap", config)


def node_redirect(state: State) -> dict:
    buying = bool(re.search(r"buy|acheter|worth|vaut", state["message"], re.I))
    page, title = ("should-i-buy", "Should I buy this?") if buying else ("find-similar", "Find Similar")
    return {"reply": f"For this I need a photo: open {title}, add the picture, and the agent will answer there.",
            "action": {"page": page, "label": f"Open {title}"}, "awaiting": None, "agents_called": [title]}


def node_clarify(state: State) -> dict:
    return {"reply": "I can pick outfits and style advice, find or correct pieces of your wardrobe, plan your suitcase, "
                     "or tell you what your wardrobe is missing. What would you like?", "awaiting": None, "agents_called": []}


def node_respond(state: State) -> dict:
    turn = {"role": "user", "text": state["message"]}
    answer = {"role": "assistant", "text": state.get("reply", ""), "agent": state.get("agent")}
    return {"history": [*state.get("history", []), turn, answer][-HISTORY_TURNS * 2:]}


NODES = {"stylist": node_stylist, "wardrobe": node_wardrobe, "outfit": node_outfit, "trip": node_trip, "gap": node_gap,
         "redirect": node_redirect, "clarify": node_clarify}


def build_graph():
    graph = StateGraph(State)
    graph.add_node("route", node_route)
    for name, fn in NODES.items():
        graph.add_node(name, fn)
        graph.add_edge(name, "respond")
    graph.add_node("respond", node_respond)
    graph.add_edge(START, "route")
    graph.add_conditional_edges("route", pick, {name: name for name in NODES})
    graph.add_edge("respond", END)
    return graph.compile(checkpointer=_checkpoint_saver())


def _checkpoint_saver():
    """Create the durable orchestrator saver and initialize its schema."""
    from langgraph.checkpoint.sqlite import SqliteSaver

    config.ORCHESTRATOR_CHECKPOINT_DB.parent.mkdir(parents=True, exist_ok=True)
    saver = SqliteSaver(sqlite3.connect(str(config.ORCHESTRATOR_CHECKPOINT_DB), check_same_thread=False))
    saver.setup()
    return saver


_GRAPH = None


def chat(user_id: str, message: str, *, authorization: Optional[str] = None, place: Optional[dict] = None,
         thread_id: Optional[str] = None) -> dict:
    """One turn of the conversation: routes the message, runs the agent, remembers the thread."""
    global _GRAPH
    import uuid

    message = (message or "").strip()
    thread_id = thread_id or str(uuid.uuid4())
    if not message:
        return {"reply": "Ask me anything about your wardrobe, outfits, a trip or what to buy.", "agent": "clarify",
                "agent_label": AGENTS["clarify"][0], "thread_id": thread_id, "items": [], "data": {}, "action": None,
                "state": "input-required", "agents_called": [], "why": "empty"}
    _GRAPH = _GRAPH or build_graph()
    invoke_config = {"configurable": {"thread_id": f"{user_id}:{thread_id}", "user_id": user_id}}
    if authorization:
        invoke_config["configurable"]["__authorization"] = RequestToken(authorization)
    state = _GRAPH.invoke({"message": message[:1000], "user_id": user_id, "place": place or {},
                           "context_id": thread_id}, invoke_config)
    name = state["agent"]
    return {"reply": state.get("reply", ""), "agent": name, "agent_label": AGENTS[name][0], "why": state.get("why", ""),
            "agents_called": state.get("agents_called", []), "items": state.get("items", []), "data": state.get("data") or {},
            "action": state.get("action"), "state": state.get("state", "completed"), "thread_id": thread_id}
