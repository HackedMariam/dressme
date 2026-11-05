"""The Wardrobe Agent (LangGraph): the one agent that owns the user's wardrobe.

    START -> gate --(a change is waiting and the user answered yes)--> apply  -> END
                  \\--(a change is waiting and the user answered no)--> cancel -> END
                  \\--(anything else)---------------------------------> assist -> END

`assist` is the tool loop (agent_kit): the LLM reads the request, calls tools and answers in plain words.
Tools: search_wardrobe, find_similar, wardrobe_stats, update_item.

Writing is guarded in code, not by the prompt: `update_item` only PROPOSES a change (nothing is saved). The change is
applied by the `apply` node, and only when the user answers yes in their next message (or sends confirm=true). The
LLM never has a tool that writes.

The other agents read the wardrobe through this module (`list_items`, `search`), and a duplicate check for the live
scan lives here too (`check_duplicate`).
"""
from __future__ import annotations

import json
import logging
import re
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Optional, TypedDict

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:          # agent_kit/ and a2a_protocol/ sit at the root of the repository
    sys.path.insert(0, str(ROOT))

from agent_kit import run_loop  # noqa: E402
from langgraph.graph import END, START, StateGraph  # noqa: E402

from . import config  # noqa: E402
from .taxonomy import GROUPS, MODEL_CLASSES, OCCASIONS, PATTERNS, SEASONS, STYLES  # noqa: E402

log = logging.getLogger("dressme.wardrobe_agent")

MAX_ROUNDS = 6
MAX_RESULTS_PER_CALL = 20
PENDING_TTL = 15 * 60
RESULT_FIELDS = ("id", "name", "category", "category_group", "color_name", "pattern",
                 "material", "seasons", "style", "occasions", "formality", "warmth")
EDITABLE = ("name", "category", "color_name", "pattern", "material", "style", "seasons", "occasions", "formality", "warmth")

SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "search_wardrobe",
        "description": "Search the user's own wardrobe. Always call this before answering any "
                       "question about what the user owns or could wear - never guess or invent "
                       "items. You can call it more than once (e.g. loosen filters if it returns "
                       "nothing, or narrow down if it returns too much).",
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "category": {"type": "string", "enum": MODEL_CLASSES,
                             "description": "Exact garment type, e.g. 'dress', 'jacket'."},
                "category_group": {"type": "string", "enum": GROUPS,
                                   "description": "Broader group, use when no single category fits."},
                "color_name": {"type": "string", "description": "Exact colour the user asked for, if any."},
                "season": {"type": "string", "enum": SEASONS},
                "occasion": {"type": "string", "enum": OCCASIONS},
                "style": {"type": "string", "enum": STYLES},
                "pattern": {"type": "string", "enum": PATTERNS},
                "min_warmth": {"type": "integer", "description": "1-5. Set for 'warm'/'cold' requests."},
                "text": {"type": "string", "description": "Free text to match against name, "
                                                           "material, description and tags."},
            },
            "required": [],
        },
    },
}

FIND_SIMILAR_TOOL = {
    "type": "function",
    "function": {
        "name": "find_similar",
        "description": "Find the owned pieces most similar to one piece (give item_id) or to a description "
                       "(category, color_name, material, style). Use it for 'do I already have something like...'.",
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {"item_id": {"type": "string", "description": "An id returned by search_wardrobe."},
                           "category": {"type": "string", "enum": MODEL_CLASSES},
                           "color_name": {"type": "string"}, "material": {"type": "string"},
                           "style": {"type": "string", "enum": STYLES}},
            "required": [],
        },
    },
}

STATS_TOOL = {
    "type": "function",
    "function": {
        "name": "wardrobe_stats",
        "description": "Counts for the whole wardrobe: total, by group, category, colour family, season, occasion, "
                       "and how many pieces need a review. Use it for 'how many...' questions.",
        "parameters": {"type": "object", "additionalProperties": False, "properties": {}, "required": []},
    },
}

UPDATE_TOOL = {
    "type": "function",
    "function": {
        "name": "update_item",
        "description": "PROPOSE a correction to one piece (name, category, color_name, pattern, material, style, "
                       "seasons, occasions, formality, warmth). Nothing is saved: the user must confirm in their next "
                       "message, so after calling it, tell the user exactly what will change and ask them to confirm.",
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {"item_id": {"type": "string", "description": "An id returned by search_wardrobe."},
                           "fields": {"type": "object", "description": "Only the fields to change."}},
            "required": ["item_id", "fields"],
        },
    },
}

TOOLS = [SEARCH_TOOL, FIND_SIMILAR_TOOL, STATS_TOOL, UPDATE_TOOL]

SYSTEM = (
    "You are the Wardrobe Agent of DressMe: you look after the user's wardrobe. Reply in the language the user wrote in, "
    "in one to three plain sentences, no markdown, no emojis. Never invent a piece: always call search_wardrobe (or "
    "find_similar / wardrobe_stats) before talking about what the user owns, and call search_wardrobe again with other "
    "filters when a search comes back empty or too broad. To correct a piece, find it first, then call update_item: it "
    "only PROPOSES the change, so tell the user precisely what would change (piece, field, old value, new value) and ask "
    "them to confirm. Never say a change was made. You do not give styling advice or build outfits: say that the AI "
    "Stylist and the Outfit Builder do that."
)

YES = re.compile(r"^\s*(yes|y|yeah|yep|ok|okay|sure|confirm|confirmed|do it|go ahead|oui|ouais|d'accord|confirme|vas-y)\b", re.I)
NO = re.compile(r"^\s*(no|n|nope|cancel|stop|non|annule|annuler|laisse)\b", re.I)


# ------------------------------------------------------------------------------------------ binding to the app
class _Context:
    store: Any = None
    validate_patch: Callable[[dict], dict] | None = None
    apply_patch: Callable[[str, str, dict], dict] | None = None


_ctx = _Context()


def bind(store, validate_patch: Callable[[dict], dict], apply_patch: Callable[[str, str, dict], dict]) -> None:
    """Wire the agent to the app's store and to the same validated write path as PATCH /api/items/{id}."""
    _ctx.store, _ctx.validate_patch, _ctx.apply_patch = store, validate_patch, apply_patch


def list_items(user_id: str) -> list[dict]:
    """Every other agent reads the wardrobe through here."""
    return _ctx.store.list_items(user_id)


# ------------------------------------------------------------------------------------------ search
def _matches(item: dict, args: dict) -> bool:
    if args.get("category") and item.get("category") != args["category"]:
        return False
    if args.get("category_group") and item.get("category_group") != args["category_group"]:
        return False
    if args.get("color_name") and item.get("color_name") != args["color_name"]:
        return False
    if args.get("season") and args["season"] not in (item.get("seasons") or []):
        return False
    if args.get("occasion") and args["occasion"] not in (item.get("occasions") or []):
        return False
    if args.get("style") and item.get("style") != args["style"]:
        return False
    if args.get("pattern") and item.get("pattern") != args["pattern"]:
        return False
    if args.get("min_warmth") and (item.get("warmth") or 0) < args["min_warmth"]:
        return False
    if args.get("text"):
        hay = " ".join(str(item.get(k, "")) for k in ("name", "subcategory", "material", "description"))
        hay += " " + " ".join(item.get("tags") or [])
        if args["text"].lower() not in hay.lower():
            return False
    return True


def search(items: list[dict], args: dict) -> list[dict]:
    return [i for i in items if _matches(i, args)][:MAX_RESULTS_PER_CALL]


_run_search = search      # the name the AI Stylist used before this module existed


def trim(item: dict) -> dict:
    return {k: item.get(k) for k in RESULT_FIELDS}


def similar(items: list[dict], args: dict) -> list[dict]:
    """The owned pieces closest to a reference piece or description, best first, with the reasons."""
    reference = next((i for i in items if i.get("id") == args.get("item_id")), None) if args.get("item_id") else None
    ref = {**(reference or {}), **{k: v for k, v in args.items() if k != "item_id" and v}}
    ranked = []
    for item in items:
        if reference and item.get("id") == reference.get("id"):
            continue
        score, reasons = 0.0, []
        if ref.get("category") and item.get("category") == ref["category"]:
            score += 3; reasons.append("same type")
        elif ref.get("category_group") and item.get("category_group") == ref["category_group"]:
            score += 1; reasons.append("same group")
        if ref.get("color_name") and item.get("color_name") == ref["color_name"]:
            score += 2; reasons.append("same colour")
        elif ref.get("color_family") and item.get("color_family") == ref["color_family"]:
            score += 1; reasons.append("same colour family")
        if ref.get("material") and item.get("material") == ref["material"]:
            score += 1; reasons.append("same material")
        if ref.get("style") and item.get("style") == ref["style"]:
            score += 1; reasons.append("same style")
        score += 0.5 * len(set(ref.get("occasions") or []) & set(item.get("occasions") or []))
        score += 0.25 * len(set(ref.get("seasons") or []) & set(item.get("seasons") or []))
        if score >= 3:
            ranked.append((score, reasons, item))
    ranked.sort(key=lambda row: -row[0])
    return [{**trim(item), "similarity": round(score, 2), "why": reasons} for score, reasons, item in ranked[:6]]


def stats(items: list[dict]) -> dict:
    def count(field: str) -> dict:
        counts: dict[str, int] = {}
        for item in items:
            values = item.get(field)
            for value in (values if isinstance(values, list) else [values]):
                if value:
                    counts[str(value)] = counts.get(str(value), 0) + 1
        return dict(sorted(counts.items(), key=lambda kv: -kv[1]))
    return {"total": len(items), "by_group": count("category_group"), "by_category": count("category"),
            "by_color_family": count("color_family"), "by_season": count("seasons"), "by_occasion": count("occasions"),
            "needs_review": sum(1 for i in items if i.get("needs_review")),
            "without_photo": sum(1 for i in items if not i.get("cutout_url") and not i.get("image_url"))}


# ------------------------------------------------------------------------------------------ pending changes
class PendingStore:
    """Changes proposed and waiting for the user's yes, per user and conversation."""

    def __init__(self) -> None:
        self._data: dict[tuple[str, str], dict] = {}
        self._lock = threading.Lock()

    def put(self, user_id: str, context_id: str, change: dict) -> None:
        with self._lock:
            self._data[(user_id, context_id)] = {**change, "created": time.time()}

    def get(self, user_id: str, context_id: str) -> dict | None:
        with self._lock:
            change = self._data.get((user_id, context_id))
            if change and time.time() - change["created"] > PENDING_TTL:
                del self._data[(user_id, context_id)]
                return None
            return change

    def drop(self, user_id: str, context_id: str) -> None:
        with self._lock:
            self._data.pop((user_id, context_id), None)


pending = PendingStore()


def _describe(change: dict) -> str:
    return "; ".join(f"{field}: {change['before'].get(field)!r} -> {value!r}" for field, value in change["fields"].items())


# ------------------------------------------------------------------------------------------ the graph
class State(TypedDict, total=False):
    user_id: str
    text: str
    confirm: Optional[bool]
    context_id: str
    items: list[dict]
    waiting: Optional[dict]
    reply: str
    shown: list[dict]
    filters: list[dict]
    proposed: Optional[dict]
    updated: Optional[dict]
    state: str
    read_only: bool


def _decision(state: State) -> Optional[bool]:
    if state.get("confirm") is not None:
        return bool(state["confirm"])
    text = state.get("text") or ""
    if YES.match(text):
        return True
    if NO.match(text):
        return False
    return None


def node_gate(state: State) -> dict:
    waiting = pending.get(state["user_id"], state["context_id"])
    return {"waiting": waiting}


def route_gate(state: State) -> str:
    if state.get("waiting"):
        decision = _decision(state)
        if decision is True:
            return "apply"
        if decision is False:
            return "cancel"
        pending.drop(state["user_id"], state["context_id"])   # a new request replaces the old proposal
    return "assist"


def node_apply(state: State) -> dict:
    change = state["waiting"]
    pending.drop(state["user_id"], state["context_id"])
    try:
        updated = _ctx.apply_patch(state["user_id"], change["item_id"], change["fields"])
    except Exception as error:
        log.warning("wardrobe change refused: %s", error)
        detail = getattr(error, "detail", None) or str(error)
        return {"reply": f"I could not save the change: {detail}", "state": "failed"}
    return {"reply": f"Done. {change['item_name']} was updated ({_describe(change)}).", "updated": updated,
            "shown": [updated], "state": "completed"}


def node_cancel(state: State) -> dict:
    pending.drop(state["user_id"], state["context_id"])
    return {"reply": "Okay, nothing was changed.", "state": "completed"}


def node_assist(state: State) -> dict:
    items, user_id, context_id = state["items"], state["user_id"], state["context_id"]
    found: dict[str, dict] = {}
    filters: list[dict] = []
    proposal: dict[str, Any] = {}

    def run_tool(name: str, args: dict) -> str:
        if name == "wardrobe_stats":
            return json.dumps(stats(items))
        if name == "find_similar":
            rows = similar(items, args)
            for row in rows:
                found[row["id"]] = row
            return json.dumps(rows)
        if name == "update_item":
            item = next((i for i in items if i.get("id") == args.get("item_id")), None)
            fields = args.get("fields")
            if item is None or not isinstance(fields, dict) or not fields:
                return json.dumps({"error": "Unknown item_id or no fields: search the piece first."})
            fields = {k: v for k, v in fields.items() if k in EDITABLE}
            if not fields:
                return json.dumps({"error": f"Only these fields can change: {', '.join(EDITABLE)}."})
            try:
                _ctx.validate_patch(dict(fields))
            except Exception as error:
                return json.dumps({"error": str(getattr(error, "detail", None) or error)})
            change = {"item_id": item["id"], "item_name": item.get("name") or item["id"], "fields": fields,
                      "before": {k: item.get(k) for k in fields}}
            pending.put(user_id, context_id, change)
            proposal.update(change)
            return json.dumps({"status": "awaiting_user_confirmation", "item": change["item_name"],
                               "changes": _describe(change), "saved": False})
        results = search(items, args)           # search_wardrobe
        if args:
            filters.append(args)
        trimmed = [trim(i) for i in results]
        for i in trimmed:
            found[i["id"]] = i
        return json.dumps(trimmed)

    from openai import OpenAI

    client = OpenAI(api_key=config.OPENAI_API_KEY, timeout=config.LLM_TIMEOUT, max_retries=2)
    read_only = bool(state.get("read_only"))
    tools = [t for t in TOOLS if not (read_only and t["function"]["name"] == "update_item")]
    system = SYSTEM + (" This request comes from another agent: it is read-only, never propose a change, and answer in one "
                       "short sentence listing what you found. Be generous: when the request is about what to wear for an "
                       "occasion, a season or the weather, search each role separately (tops, bottoms, dresses, outerwear, "
                       "shoes) and use occasion or season filters only when they still return pieces, otherwise search "
                       "without them: the other agent chooses among your results." if read_only else "")

    def call_llm(messages: list[dict]):
        return client.chat.completions.create(model=config.LLM_MODEL, temperature=0.2, max_completion_tokens=700,
                                              messages=messages, tools=tools).choices[0].message

    messages = [{"role": "system", "content": system}, {"role": "user", "content": state["text"][:1000]}]
    final, outcome = run_loop(messages=messages, call_llm=call_llm, run_tool=run_tool, max_rounds=MAX_ROUNDS)
    if outcome == "error":
        return {"reply": "The wardrobe agent is having trouble right now, try again in a moment.", "state": "failed",
                "shown": [], "filters": filters}
    if outcome == "exhausted":
        return {"reply": "That took more digging than usual: try asking more specifically.", "state": "failed",
                "shown": list(found.values()), "filters": filters}
    return {"reply": (final or "").strip(), "shown": list(found.values()), "filters": filters,
            "proposed": proposal or None, "state": "input-required" if proposal else "completed"}


def build_graph():
    graph = StateGraph(State)
    graph.add_node("gate", node_gate)
    graph.add_node("apply", node_apply)
    graph.add_node("cancel", node_cancel)
    graph.add_node("assist", node_assist)
    graph.add_edge(START, "gate")
    graph.add_conditional_edges("gate", route_gate, {"apply": "apply", "cancel": "cancel", "assist": "assist"})
    for node in ("apply", "cancel", "assist"):
        graph.add_edge(node, END)
    return graph.compile()


_GRAPH = None


def converse(user_id: str, text: str, *, confirm: Optional[bool] = None, context_id: Optional[str] = None) -> dict:
    """One turn with the Wardrobe Agent. `context_id` ties a proposal to the confirmation that follows it."""
    global _GRAPH
    text = (text or "").strip()
    context_id = context_id or str(uuid.uuid4())
    base = {"context_id": context_id, "items": [], "filters": [], "pending": None, "updated": None}
    if not text and confirm is None:
        return {**base, "reply": "Ask me to find, compare, count or correct pieces of your wardrobe.", "state": "input-required"}
    waiting = pending.get(user_id, context_id)
    if not waiting and not config.OPENAI_API_KEY:
        return {**base, "reply": "The wardrobe agent needs an OPENAI_API_KEY configured on the server.", "state": "failed"}
    _GRAPH = _GRAPH or build_graph()
    result = _GRAPH.invoke({"user_id": user_id, "text": text, "confirm": confirm, "context_id": context_id,
                            "items": list_items(user_id)})
    proposed = result.get("proposed")
    return {**base, "reply": result.get("reply", ""), "state": result.get("state", "completed"),
            "items": result.get("shown") or [], "filters": result.get("filters") or [],
            "pending": ({"item_id": proposed["item_id"], "item_name": proposed["item_name"], "fields": proposed["fields"],
                         "before": proposed["before"]} if proposed else None),
            "updated": result.get("updated")}


def ask(items: list[dict], request: str) -> dict:
    """Agent to agent: another agent asks the Wardrobe Agent, in plain words, for pieces of the wardrobe (read-only).

    The Wardrobe Agent's own LLM chooses the filters and looks again if the first search is empty; the caller gets its
    short answer, the pieces it found and the filters it used."""
    request = (request or "").strip()
    if not request or not config.OPENAI_API_KEY:
        return {"reply": "", "items": [], "filters": []}
    result = node_assist({"user_id": "", "context_id": "", "text": request, "items": items, "read_only": True})
    return {"reply": result.get("reply", ""), "items": result.get("shown") or [], "filters": result.get("filters") or []}


# ------------------------------------------------------------------------------------------ duplicate check (live scan)
DUPLICATE_SYSTEM = (
    "You help catalogue a wardrobe that's being scanned live from a camera. An item was just "
    "detected and saved. Decide whether the wardrobe already contains a near-duplicate of it - "
    "call search_wardrobe (at least once) to check, looking at category, colour and whatever else "
    "you're told. Only call it a duplicate if you're genuinely confident it's the same physical "
    "garment seen twice (e.g. the user scanned it by accident, or it's a second photo of the same "
    "jacket) - NOT just 'another navy t-shirt' or 'another pair of jeans', which are normal to own "
    "more than one of. When you're done, reply with ONLY a compact JSON object, no other text: "
    '{"duplicate": true or false, "similar_item_id": "<id or null>", "note": "<one short sentence '
    'for the user if duplicate, else empty>"}.'
)


def check_duplicate(items: list[dict], candidate: dict) -> dict:
    """Agentic duplicate check run right after a live-scan capture (LangGraph tool loop, search tool only)."""
    empty = {"duplicate": False, "similar_item_id": None, "note": ""}
    if not config.OPENAI_API_KEY or not items:
        return empty

    from openai import OpenAI

    client = OpenAI(api_key=config.OPENAI_API_KEY, timeout=config.LLM_TIMEOUT, max_retries=2)
    facts = {k: candidate.get(k) for k in ("category", "color_name", "pattern", "material") if candidate.get(k)}
    messages = [{"role": "system", "content": DUPLICATE_SYSTEM}, {"role": "user", "content": "Just captured: " + json.dumps(facts)}]

    def call_llm(msgs: list[dict]):
        return client.chat.completions.create(model=config.LLM_MODEL, temperature=0.1, max_completion_tokens=250,
                                              messages=msgs, tools=[SEARCH_TOOL],
                                              response_format={"type": "json_object"}).choices[0].message

    def run_tool(name: str, args: dict) -> str:
        return json.dumps([trim(i) for i in search(items, args)])

    final, outcome = run_loop(messages=messages, call_llm=call_llm, run_tool=run_tool, max_rounds=4)
    if outcome != "answer":
        return empty
    try:
        data = json.loads(final or "{}")
    except json.JSONDecodeError:
        return empty
    return {"duplicate": bool(data.get("duplicate")), "similar_item_id": data.get("similar_item_id") or None,
            "note": str(data.get("note") or "")[:200]}
