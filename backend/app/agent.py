"""Conversational wardrobe search agent.

Unlike the plain text/photo search (deterministic filtering in the frontend),
this lets the user ask a free-form question ("something warm for a rainy work
day") and has an LLM decide how to search: it calls the search_wardrobe tool
with whatever filters it thinks fit, can look again with different filters if
the first search comes back empty, and only then writes a reply - grounded in
the user's real items instead of guessing.
"""
from __future__ import annotations

import json
import logging

from . import config
from .taxonomy import GROUPS, MODEL_CLASSES, OCCASIONS, PATTERNS, SEASONS, STYLES

log = logging.getLogger("dressme.agent")

MAX_ROUNDS = 4
MAX_RESULTS_PER_CALL = 20
RESULT_FIELDS = ("id", "name", "category", "category_group", "color_name", "pattern",
                 "material", "seasons", "style", "occasions", "formality", "warmth")

TOOLS = [{
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
}]

SYSTEM = (
    "You are the styling assistant inside DressMe, a personal wardrobe app. "
    "You may only talk about items the user actually owns: always call search_wardrobe at least "
    "once before answering, and call it again with different filters if a search comes back "
    "empty or clearly too broad. Keep replies short (1-3 sentences), friendly, and specific - "
    "name the actual items you found by name. If nothing in the wardrobe fits, say so plainly "
    "instead of inventing something."
)


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


def _run_search(items: list[dict], args: dict) -> list[dict]:
    return [i for i in items if _matches(i, args)][:MAX_RESULTS_PER_CALL]


def chat(items: list[dict], message: str) -> dict:
    """One user turn: returns {"reply": str, "items": [...]} grounded in `items`."""
    message = (message or "").strip()
    if not message:
        return {"reply": "Ask me something like \"a warm jacket for work\".", "items": []}
    if not config.OPENAI_API_KEY and not config.GROQ_API_KEY:
        return {"reply": "The AI stylist needs an LLM API key configured on the server.", "items": []}
    messages: list[dict] = [{"role": "system", "content": SYSTEM},
                            {"role": "user", "content": message[:1000]}]
    found: dict[str, dict] = {}

    for _ in range(MAX_ROUNDS):
        try:
            from .llm import call_with_fallback
            resp = call_with_fallback(
                lambda client, _provider, model: client.chat.completions.create(
                    model=model, temperature=0.3, max_completion_tokens=400,
                    messages=messages, tools=TOOLS))
        except Exception:
            log.exception("agent LLM call failed")
            return {"reply": "The AI stylist is having trouble right now, try again in a moment.",
                    "items": list(found.values())}

        msg = resp.choices[0].message
        if not msg.tool_calls:
            return {"reply": msg.content or "", "items": list(found.values())}

        messages.append({"role": "assistant", "content": msg.content,
                         "tool_calls": [tc.model_dump() for tc in msg.tool_calls]})
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            results = _run_search(items, args)
            trimmed = [{k: i.get(k) for k in RESULT_FIELDS} for i in results]
            for i, t in zip(results, trimmed):
                found[i["id"]] = t
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(trimmed)})

    return {"reply": "That search is taking more digging than usual - try asking more specifically.",
           "items": list(found.values())}


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
    """Agentic duplicate check run right after a live-scan capture: the LLM decides whether (and
    how) to search the wardrobe for a near-duplicate of the item that was just saved, instead of
    a fixed rule - it can look, weigh what it finds, and only flag a genuine match.
    """
    empty = {"duplicate": False, "similar_item_id": None, "note": ""}
    if not (config.OPENAI_API_KEY or config.GROQ_API_KEY) or not items:
        return empty
    facts = {k: candidate.get(k) for k in ("category", "color_name", "pattern", "material") if candidate.get(k)}
    messages: list[dict] = [{"role": "system", "content": DUPLICATE_SYSTEM},
                            {"role": "user", "content": "Just captured: " + json.dumps(facts)}]

    for _ in range(MAX_ROUNDS):
        try:
            from .llm import call_with_fallback
            resp = call_with_fallback(
                lambda client, _provider, model: client.chat.completions.create(
                    model=model, temperature=0.1, max_completion_tokens=250,
                    messages=messages, tools=TOOLS, response_format={"type": "json_object"}))
        except Exception:
            log.exception("duplicate-check LLM call failed")
            return empty

        msg = resp.choices[0].message
        if not msg.tool_calls:
            try:
                data = json.loads(msg.content or "{}")
            except json.JSONDecodeError:
                return empty
            return {"duplicate": bool(data.get("duplicate")),
                   "similar_item_id": data.get("similar_item_id") or None,
                   "note": str(data.get("note") or "")[:200]}

        messages.append({"role": "assistant", "content": msg.content,
                         "tool_calls": [tc.model_dump() for tc in msg.tool_calls]})
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            trimmed = [{k: i.get(k) for k in RESULT_FIELDS} for i in _run_search(items, args)]
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(trimmed)})

    return empty
