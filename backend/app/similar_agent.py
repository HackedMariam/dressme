"""The Similar Agent (LangGraph): "do I already own the pieces of this look?"

Find Similar detects the garments of a photo; this agent decides, for each one, whether the user already owns it
(`owned`), owns something close (`close`) or does not own anything like it (`missing`), and says why.

    START -> ask -> judge -> check -> END

  ask    the tool loop (agent_kit): the LLM asks the Wardrobe Agent, in plain words, about each detected piece
  judge  the LLM's JSON verdict, one entry per piece
  check  code only: statuses must be known, the closest piece must exist in the wardrobe, and any piece the LLM
         forgot (or the whole answer, if the LLM is down) is decided by the Wardrobe Agent's similarity ranking

The agent never reads the wardrobe itself: everything it knows about it comes from the Wardrobe Agent.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any, Optional, TypedDict

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent_kit import run_loop  # noqa: E402
from langgraph.graph import END, START, StateGraph  # noqa: E402

from . import config, wardrobe_agent  # noqa: E402

log = logging.getLogger("dressme.similar_agent")

MAX_PIECES = 8
MAX_ROUNDS = 10
STATUSES = ("owned", "close", "missing")
PIECE_FIELDS = ("name", "category", "category_group", "color_name", "color_family", "material", "style", "pattern")

# Same words the wardrobe agent exposes: the agent asks the Wardrobe Agent, never the database.
_ask_wardrobe = wardrobe_agent.ask

ASK_TOOL = {
    "type": "function",
    "function": {
        "name": "ask_wardrobe_agent",
        "description": "Ask the Wardrobe Agent, in plain words, which pieces of the user's wardrobe look like a piece "
                       "(for example 'navy wool blazers' or 'any white sneakers').",
        "parameters": {"type": "object", "additionalProperties": False,
                       "properties": {"request": {"type": "string"}}, "required": ["request"]},
    },
}

SYSTEM = (
    "You are the Similar Agent of DressMe. A user shows a look; its garments were detected and are listed with an index. "
    "For EACH piece, call ask_wardrobe_agent to find what the user already owns that looks like it, then decide: "
    "owned = the same type of garment in the same colour is already in the wardrobe; close = the same type but another "
    "colour, material or style; missing = nothing like it. Answer with ONLY a JSON object, plain text, no markdown: "
    '{"pieces": [{"index": 0, "status": "owned|close|missing", "closest_item_id": "<id returned by the Wardrobe Agent '
    'or null>", "reason": "one short sentence naming the owned piece and what matches or differs"}], '
    '"summary": "one sentence on how much of the look the user can already recreate"}. Never invent an id.'
)


class State(TypedDict, total=False):
    items: list[dict]
    pieces: list[dict]
    authorization: Optional[str]
    draft: Optional[str]
    outcome: str
    result: dict


def _describe(index: int, piece: dict) -> str:
    facts = ", ".join(f"{k}: {piece[k]}" for k in PIECE_FIELDS if piece.get(k))
    return f"{index}. {facts}"


def node_ask(state: State) -> dict:
    if not config.OPENAI_API_KEY:
        return {"draft": None, "outcome": "error"}
    from openai import OpenAI

    client = OpenAI(api_key=config.OPENAI_API_KEY, timeout=config.LLM_TIMEOUT, max_retries=2)
    items, pieces = state["items"], state["pieces"]

    def call_llm(messages: list[dict]):
        return client.chat.completions.create(model=config.LLM_MODEL, temperature=0.1, max_completion_tokens=1200,
                                              messages=messages, tools=[ASK_TOOL]).choices[0].message

    def run_tool(name: str, args: dict) -> str:
        request_text = str(args.get("request") or "")
        answer = _ask_wardrobe(items, request_text)
        return json.dumps({"wardrobe_agent_says": answer["reply"],
                           "pieces": [{k: i.get(k) for k in ("id", "name", "category", "color_name", "material", "style")}
                                      for i in answer["items"]]})

    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": "The look:\n" + "\n".join(_describe(n, p) for n, p in enumerate(pieces))}]
    final, outcome = run_loop(messages=messages, call_llm=call_llm, run_tool=run_tool, max_rounds=MAX_ROUNDS)
    return {"draft": final, "outcome": outcome}


def _deterministic(items: list[dict], piece: dict) -> dict:
    """The Wardrobe Agent's similarity ranking decides when the LLM cannot."""
    ranked = wardrobe_agent.similar(items, {k: v for k, v in piece.items() if k in PIECE_FIELDS and v})
    top = ranked[0] if ranked else None
    status = "owned" if top and top["similarity"] >= 5 else "close" if top else "missing"
    reason = (f"You own {top['name']} ({', '.join(top['why'])})." if top else "Nothing in your wardrobe looks like it.")
    return {"status": status, "closest_item_id": top["id"] if top else None, "reason": reason,
            "score": min(100, round(top["similarity"] * 12)) if top else 0}


def node_check(state: State) -> dict:
    items, pieces = state["items"], state["pieces"]
    ids = {i["id"] for i in items}
    judged: dict[int, dict] = {}
    summary = ""
    if state.get("outcome") == "answer" and state.get("draft"):
        try:
            data = json.loads(state["draft"])
            summary = " ".join(str(data.get("summary") or "").split())[:300]
            for entry in data.get("pieces") or []:
                index = entry.get("index")
                if isinstance(index, int) and 0 <= index < len(pieces) and entry.get("status") in STATUSES:
                    closest = entry.get("closest_item_id")
                    closest = closest if closest in ids else None
                    if entry["status"] != "missing" and closest is None:
                        continue                         # "owned" without a real piece: decided by code below
                    base = _deterministic(items, pieces[index])
                    score = base["score"] if base["closest_item_id"] == closest else {"owned": 90, "close": 60, "missing": 0}[entry["status"]]
                    judged[index] = {"status": entry["status"], "closest_item_id": closest,
                                     "reason": " ".join(str(entry.get("reason") or "").split())[:240] or base["reason"],
                                     "score": score}
        except (ValueError, AttributeError):
            judged = {}
    out = []
    for index, piece in enumerate(pieces):
        verdict = judged.get(index) or {**_deterministic(items, piece), "by": "rules"}
        out.append({"index": index, **verdict, "by": verdict.get("by", "agent")})
    return {"result": {"pieces": out, "summary": summary}}


def build_graph():
    graph = StateGraph(State)
    graph.add_node("ask", node_ask)
    graph.add_node("check", node_check)
    graph.add_edge(START, "ask")
    graph.add_edge("ask", "check")
    graph.add_edge("check", END)
    return graph.compile()


_GRAPH = None


def compare(items: list[dict], pieces: list[dict], authorization: Optional[str] = None) -> dict:
    """{"pieces": [{index, status, closest_item_id, reason, score, by}], "summary": str} for the detected pieces."""
    global _GRAPH
    pieces = [p for p in pieces if isinstance(p, dict)][:MAX_PIECES]
    if not pieces:
        return {"pieces": [], "summary": ""}
    _GRAPH = _GRAPH or build_graph()
    return _GRAPH.invoke({"items": items, "pieces": pieces, "authorization": authorization})["result"]
