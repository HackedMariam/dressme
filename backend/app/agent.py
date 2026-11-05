"""Conversational wardrobe search agent.

Unlike the plain text/photo search (deterministic filtering in the frontend),
this lets the user ask a free-form question ("something warm for a rainy work
day") and has an LLM decide how to search: it calls the search_wardrobe tool
with whatever filters it thinks fit, can look again with different filters if
the first search comes back empty, and only then writes a reply - grounded in
the user's real items instead of guessing.

For general style knowledge (fabrics, colour combinations, dress codes, how to wear a piece...) it also has a
second tool, fashion_advice, that asks the RAG service for an answer taken from fashion books, with sources.
"""
from __future__ import annotations

import json
import logging
import re

from . import config, rag_client
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
}, {
    "type": "function",
    "function": {
        "name": "fashion_advice",
        "description": "Ask the fashion knowledge base (a library of fashion books) for expert advice: what "
                       "suits an occasion or dress code, how to combine colours or fabrics, how to style or "
                       "care for a type of garment, what to wear for a climate or trip. Use it for any "
                       "'how / what / why' style question, and phrase the question in English. It never "
                       "knows the user's wardrobe, so combine it with search_wardrobe. The answer carries "
                       "numbered sources like [S1]: keep those markers when you use its advice.",
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "properties": {"question": {"type": "string",
                                        "description": "One focused style question in English, one topic only "
                                                       "(e.g. 'Which fabrics are best for winter clothes?'): "
                                                       "ask again separately for another topic."}},
            "required": ["question"],
        },
    },
}]

SYSTEM = (
    "You are the styling assistant inside DressMe, a personal wardrobe app. "
    "You may only talk about items the user actually owns: always call search_wardrobe at least "
    "once before answering, and call it again with different filters if a search comes back "
    "empty or clearly too broad. Reply in the language the user wrote in. If nothing in the wardrobe "
    "fits, say so plainly instead of inventing something. "
    "Whenever the user asks WHAT, WHICH or HOW about style knowledge - a dress code or occasion, "
    "colours that go together, a fabric or material, a season or climate, how to wear, combine or care "
    "for something - you MUST also call fashion_advice (together with search_wardrobe). A plain request "
    "to find or show items needs search_wardrobe only. Never present book advice as if it came from the "
    "wardrobe, and do not invent sources: if fashion_advice returns nothing, answer from the wardrobe alone. "
    "Be convincing, and honest: when the user asks for advice, take a clear position and justify it. "
    "Your FINAL message (after the tool calls) must be ONLY a JSON object, plain text without markdown, "
    "asterisks or emojis, with these keys: "
    '"answer": two sentences at most. When the user asks for advice, what to wear or which piece to '
    'choose, start with your pick ("My pick: ...", or the same in the user\'s language) naming the exact '
    "pieces, then the single strongest reason it is the right choice for this occasion, weather or goal. "
    "When the user only asks to find or show items, say in one sentence what you found, with no pick, and "
    "leave outfit, why and tips empty; "
    '"outfit": 0 to 3 strings, best first, each one outfit built only from the user\'s own pieces, written '
    "with the exact item names joined by ' + ' (leave empty if the user did not ask what to wear or for a "
    "look); "
    '"why": 3 or 4 short evidence-based reasons. Each one must point to a concrete fact about the user\'s '
    "real pieces (their colour, material, warmth, season, occasion or style as returned by search_wardrobe), "
    "and, whenever fashion_advice gave a relevant rule, link it to that rule and keep its source marker such "
    "as [S1] right after the claim. Never state a fact about a piece that the search did not return; "
    '"tips": 2 or 3 short practical tips that make the look work even better (colours, fabrics, how to wear '
    "or finish it), with [S1]-style markers when they come from fashion_advice. If something is a trade-off "
    "or a weakness (for example the rule says avoid a colour pairing), say so in one line and offer the fix: "
    "that is what makes the recommendation credible. Use an empty list for a section that does not apply."
)


# A question that asks for style knowledge (not just "show me my black pieces"), in English or French.
KNOWLEDGE_QUESTION = re.compile(
    r"\b(how|what|which|why|best|suits?|suitable|match(es)?|combine|pair|go(es)? with|dress ?code|fabrics?|"
    r"materials?|colou?rs?|quel(le)?s?|comment|pourquoi|tissus?|mati[eè]res?|couleurs?|associer|assortir|"
    r"porter|convient|adapt[ée]e?s?)\b", re.IGNORECASE)

ADVICE_REMINDER = ("This is a style knowledge question. Before answering, call fashion_advice with the "
                   "question in English, then answer using its advice and keep its [S1]-style markers.")


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


SECTION_KEYS = ("outfit", "why", "tips")


def _lines(value) -> list[str]:
    """A section as a list of short plain-text lines (the model may answer with a string or a list)."""
    if isinstance(value, str):
        value = value.split("\n")
    if not isinstance(value, list):
        return []
    lines = []
    for entry in value:
        text = re.sub(r"[*_`#]+", "", str(entry))
        text = re.sub(r"^\s*(?:[-\u2022]|\d+[.)])\s*", "", text).strip()
        if text:
            lines.append(text)
    return lines


def parse_reply(content: str) -> dict | None:
    """The model's final message {"answer", "outfit", "why", "tips"} cleaned up, or None when it is not that."""
    try:
        data = json.loads(content)
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    answer = " ".join(_lines(data.get("answer")))
    if not answer:
        return None
    return {"answer": answer, **{key: _lines(data.get(key)) for key in SECTION_KEYS}}


def chat(items: list[dict], message: str) -> dict:
    """One user turn: returns {"reply": str, "items": [...]} grounded in `items`."""
    message = (message or "").strip()
    if not message:
        return {"reply": "Ask me something like \"a warm jacket for work\".", "items": []}
    if not config.OPENAI_API_KEY:
        return {"reply": "The AI stylist needs an OPENAI_API_KEY configured on the server.", "items": []}

    from openai import OpenAI

    client = OpenAI(api_key=config.OPENAI_API_KEY, timeout=config.LLM_TIMEOUT, max_retries=2)
    messages: list[dict] = [{"role": "system", "content": SYSTEM},
                            {"role": "user", "content": message[:1000]}]
    found: dict[str, dict] = {}
    filters: list[dict] = []   # the filters the model chose, shown to the user as chips
    sources: dict[str, dict] = {}   # book passages the answer may cite, by marker ([S1]...)

    advice_asked = False   # has the model consulted the fashion knowledge base yet?
    reminded = False       # the reminder below is given at most once

    def result(content: str, structured: bool = True) -> dict:
        parsed = parse_reply(content) if structured else None
        if not parsed:   # a plain message (an error, or a model that ignored the format)
            used = [src for marker, src in sources.items() if marker in content]
            return {"reply": content, "items": list(found.values()), "filters": filters, "sources": used,
                    "sections": None}
        text = " ".join([parsed["answer"], *parsed["outfit"], *parsed["why"], *parsed["tips"]])
        used = [src for marker, src in sources.items() if marker in text]
        # The pieces of the suggested outfit (in the order they are named), else everything the search found.
        outfit_text = " ".join(parsed["outfit"]).lower()
        named = sorted((outfit_text.find(str(i.get("name") or "").lower()), i["id"])
                       for i in found.values() if i.get("name") and str(i["name"]).lower() in outfit_text)
        shown = [found[item_id] for _, item_id in named] or list(found.values())
        return {"reply": parsed["answer"], "items": shown, "filters": filters, "sources": used,
                "sections": {key: parsed[key] for key in SECTION_KEYS}}

    for _ in range(MAX_ROUNDS):
        try:
            resp = client.chat.completions.create(
                model=config.LLM_MODEL, temperature=0.3, max_completion_tokens=900,
                messages=messages, tools=TOOLS, response_format={"type": "json_object"})
        except Exception:
            log.exception("agent LLM call failed")
            return result("The AI stylist is having trouble right now, try again in a moment.", structured=False)

        msg = resp.choices[0].message
        if not msg.tool_calls:
            if (not advice_asked and not reminded and config.RAG_URL and KNOWLEDGE_QUESTION.search(message)):
                # The model skipped the knowledge base on a question that needs it: ask it to consult it first.
                reminded = True
                messages.append({"role": "assistant", "content": msg.content or ""})
                messages.append({"role": "user", "content": ADVICE_REMINDER})
                continue
            return result(msg.content or "")

        messages.append({"role": "assistant", "content": msg.content,
                         "tool_calls": [tc.model_dump() for tc in msg.tool_calls]})
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            if tc.function.name == "fashion_advice":
                advice_asked = True
                advice = rag_client.advise(str(args.get("question") or message))
                if advice:
                    for source in advice["sources"]:
                        sources.setdefault(source["marker"], source)
                    content = json.dumps({"advice": advice["answer"], "sources": advice["sources"]})
                else:
                    content = json.dumps({"advice": None, "note": "The fashion knowledge base is unavailable "
                                          "or has nothing on this: answer from the wardrobe alone."})
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": content})
                continue
            results = _run_search(items, args)
            if args:
                filters.append(args)
            trimmed = [{k: i.get(k) for k in RESULT_FIELDS} for i in results]
            for i, t in zip(results, trimmed):
                found[i["id"]] = t
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(trimmed)})

    return result("That search is taking more digging than usual - try asking more specifically.", structured=False)


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
    if not config.OPENAI_API_KEY or not items:
        return empty

    from openai import OpenAI

    client = OpenAI(api_key=config.OPENAI_API_KEY, timeout=config.LLM_TIMEOUT, max_retries=2)
    facts = {k: candidate.get(k) for k in ("category", "color_name", "pattern", "material") if candidate.get(k)}
    messages: list[dict] = [{"role": "system", "content": DUPLICATE_SYSTEM},
                            {"role": "user", "content": "Just captured: " + json.dumps(facts)}]

    for _ in range(MAX_ROUNDS):
        try:
            resp = client.chat.completions.create(
                model=config.LLM_MODEL, temperature=0.1, max_completion_tokens=250,
                messages=messages, tools=TOOLS[:1], response_format={"type": "json_object"})
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
