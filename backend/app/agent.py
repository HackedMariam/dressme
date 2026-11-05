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

from . import config, rag_client, weather
from .taxonomy import GROUPS, MODEL_CLASSES, OCCASIONS, PATTERNS, SEASONS, STYLES

log = logging.getLogger("dressme.agent")

MAX_ROUNDS = 4
AGENT_ROUNDS = 8   # the stylist may search the closet, the weather and the books several times
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
}, {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "The real weather forecast for one day in the user's city (or another city they name): "
                       "temperatures, rain chance, wind, conditions. Call it for any question about what to "
                       "wear, pack or choose, with days_ahead = 0 for today, 1 for tomorrow, and so on (up to "
                       "15). The outfit must then fit this weather.",
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "days_ahead": {"type": "integer", "description": "0 = today, 1 = tomorrow... (max 15)."},
                "city": {"type": "string", "description": "Only when the user names another city than their own."},
            },
            "required": [],
        },
    },
}]

SYSTEM = (
    "You are the styling assistant inside DressMe, a personal wardrobe app. "
    "You may only talk about items the user actually owns: always call search_wardrobe at least "
    "once before answering, and call it again with different filters if a search comes back "
    "empty or clearly too broad. Reply in the language the user wrote in. If nothing in the wardrobe "
    "fits, say so plainly instead of inventing something. "
    "WEATHER: whenever the user asks what to wear, for an outfit or a look, or which piece to choose, call "
    "get_weather for the day they mean (days_ahead 0 = today, 1 = tomorrow...) and build the answer on it: "
    "warmth and layers for the temperatures, a waterproof piece or closed shoes when rain is likely, light "
    "fabrics when it is hot, wind. Quote the real numbers. If get_weather returns nothing, say the weather "
    "could not be checked and do not invent it. "
    "BOOKS: whenever the user asks WHAT, WHICH or HOW about style - what to wear, a dress code or occasion, "
    "colours that go together, a fabric or material, a season or climate, how to wear, combine or care "
    "for something - you MUST also call fashion_advice, once per topic (up to three, each question in English "
    "and about ONE topic: for an outfit, ask about the occasion or dress code, about the colours, and about the "
    "fabrics for this weather). A plain request to find or show items needs search_wardrobe only. Never "
    "present book advice as if it came from the wardrobe, and do not invent sources: if fashion_advice "
    "returns nothing, answer from the wardrobe alone. "
    "Be convincing, and honest: when the user asks for advice, take a clear position and justify it in "
    "detail. "
    "Your FINAL message (after the tool calls) must be ONLY a JSON object, plain text without markdown, "
    "asterisks or emojis, with these keys: "
    '"answer": two sentences at most. When the user asks for advice, what to wear or which piece to '
    'choose, start with your pick ("My pick: ...", or the same in the user\'s language) naming the exact '
    "pieces, then the single strongest reason (the weather or the occasion) it is the right choice. "
    "When the user only asks to find or show items, say in one sentence what you found, with no pick, and "
    "leave every other key empty; "
    '"weather": 1 or 2 sentences (empty when you did not need the weather): the real forecast in numbers '
    "(temperatures, rain chance, wind) and what it means for what to wear, for example which layer or "
    "shoes it calls for; "
    '"outfit": 0 to 3 strings, best first, each one outfit built only from the user\'s own pieces, written '
    "with the exact item names joined by ' + ' (leave empty if the user did not ask what to wear or for a "
    "look); "
    '"why": 4 to 6 detailed reasons, each 1 or 2 sentences, explaining WHY these pieces were chosen: '
    "(1) how the outfit answers the weather (warmth rating and material of the pieces against the "
    "temperature, rain, wind), (2) how it suits the occasion or dress code and its formality, (3) why the "
    "colours work together, (4) why the fabrics or materials are right, (5) the role of each key piece. "
    "Each reason must point to a concrete fact about the user's real pieces (colour, material, warmth, "
    "season, occasion or style as returned by search_wardrobe), and, whenever fashion_advice gave a relevant "
    "rule, link it to that rule and keep its source marker such as [S1] right after the claim (when the books "
    "answered, at least two reasons must rest on them). Never state a "
    "fact about a piece that the search did not return; "
    '"alternatives": 0 to 3 short lines saying what else you considered in the closet and why you did not '
    "pick it (too warm, wrong formality, clashing colour...), or a second option for another mood; "
    '"tips": 2 or 3 short practical tips that make the look work even better (colours, fabrics, how to wear '
    "or finish it, what to bring if the weather changes), with [S1]-style markers when they come from "
    "fashion_advice. If something is a trade-off or a weakness (for example the rule says avoid a colour "
    "pairing), say so in one line and offer the fix: that is what makes the recommendation credible. Use an "
    "empty list or string for a section that does not apply."
)


# A question that asks for style knowledge (not just "show me my black pieces"), in English or French.
KNOWLEDGE_QUESTION = re.compile(
    r"\b(how|what|which|why|best|suits?|suitable|match(es)?|combine|pair|go(es)? with|dress ?code|fabrics?|"
    r"materials?|colou?rs?|wear|outfits?|looks?|quel(le)?s?|comment|pourquoi|tissus?|mati[e\u00e8]res?|couleurs?|"
    r"associer|assortir|porter|mettre|tenues?|convient|adapt[\u00e9e]e?s?)\b", re.IGNORECASE)

# A request for something to wear or choose: the weather matters.
WEAR_QUESTION = re.compile(
    r"\b(wear|outfits?|looks?|dress|go with|choose|pick|pack|style me|porter|mettre|tenues?|habiller|"
    r"quoi|choisir|que mettre)\b", re.IGNORECASE)

ADVICE_REMINDER = ("This is a style knowledge question. Before answering, call fashion_advice with the "
                   "question in English, then answer using its advice and keep its [S1]-style markers.")
WEATHER_REMINDER = ("This is a question about what to wear: call get_weather for the day the user means "
                    "before answering, and build the outfit and the reasons on the real forecast.")


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


SECTION_KEYS = ("weather", "outfit", "why", "alternatives", "tips")


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


def _forecast_view(forecast: dict | None, unit: str) -> dict | None:
    """What the page needs to draw the weather strip."""
    if not forecast:
        return None
    fahrenheit = (unit or "").lower().startswith("f")
    low, high = (forecast["temp_min_f"], forecast["temp_max_f"]) if fahrenheit else (forecast["temp_min_c"], forecast["temp_max_c"])
    return {**forecast, "unit": "F" if fahrenheit else "C", "temp_min": low, "temp_max": high}


def chat(items: list[dict], message: str, place: dict | None = None) -> dict:
    """One user turn: returns {"reply": str, "items": [...]} grounded in `items`.

    `place` ({"city", "country", "unit"}) is where the user lives: the stylist can then check the real weather."""
    message = (message or "").strip()
    if not message:
        return {"reply": "Ask me something like \"a warm jacket for work\".", "items": []}
    if not config.OPENAI_API_KEY:
        return {"reply": "The AI stylist needs an OPENAI_API_KEY configured on the server.", "items": []}

    from openai import OpenAI

    place = place or {}
    city, country, unit = (str(place.get(k) or "").strip() for k in ("city", "country", "unit"))
    today = weather.describe(0)
    context = f" Today is {today}."
    if city:
        context += f" The user lives in {city}{', ' + country if country else ''}: use that city for the weather."
    else:
        context += " The user's city is unknown: say so if the weather would matter, and do not invent it."
    asked_day = weather.when_to_days_ahead(message)
    if asked_day is not None:
        context += f" The user is asking about {weather.describe(asked_day)} (days_ahead {asked_day})."

    client = OpenAI(api_key=config.OPENAI_API_KEY, timeout=config.LLM_TIMEOUT, max_retries=2)
    messages: list[dict] = [{"role": "system", "content": SYSTEM + context},
                            {"role": "user", "content": message[:1000]}]
    found: dict[str, dict] = {}
    filters: list[dict] = []   # the filters the model chose, shown to the user as chips
    sources: dict[str, dict] = {}   # book passages the answer may cite, by marker ([S1]...)
    forecasts: list[dict] = []      # the forecasts the model looked at (the last one is shown)

    advice_asked = False   # has the model consulted the fashion knowledge base yet?
    weather_asked = False  # ...and the weather?
    reminded = False       # the reminder below is given at most once

    def result(content: str, structured: bool = True) -> dict:
        parsed = parse_reply(content) if structured else None
        if not parsed:   # a plain message (an error, or a model that ignored the format)
            used = [src for marker, src in sources.items() if marker in content]
            return {"reply": content, "items": list(found.values()), "filters": filters, "sources": used,
                    "sections": None, "weather": None}
        text = " ".join([parsed["answer"], *(line for key in SECTION_KEYS for line in parsed[key])])
        used = [src for marker, src in sources.items() if marker in text]
        # The pieces of the suggested outfit (in the order they are named), else everything the search found.
        outfit_text = " ".join(parsed["outfit"]).lower()
        named = sorted((outfit_text.find(str(i.get("name") or "").lower()), i["id"])
                       for i in found.values() if i.get("name") and str(i["name"]).lower() in outfit_text)
        shown = [found[item_id] for _, item_id in named] or list(found.values())
        return {"reply": parsed["answer"], "items": shown, "filters": filters, "sources": used,
                "sections": {key: parsed[key] for key in SECTION_KEYS},
                "weather": _forecast_view(forecasts[-1], unit) if forecasts and parsed["weather"] else None}

    for _ in range(AGENT_ROUNDS):
        try:
            resp = client.chat.completions.create(
                model=config.LLM_MODEL, temperature=0.3, max_completion_tokens=1800,
                messages=messages, tools=TOOLS, response_format={"type": "json_object"})
        except Exception:
            log.exception("agent LLM call failed")
            return result("The AI stylist is having trouble right now, try again in a moment.", structured=False)

        msg = resp.choices[0].message
        if not msg.tool_calls:
            missing = []
            if not advice_asked and config.RAG_URL and KNOWLEDGE_QUESTION.search(message):
                missing.append(ADVICE_REMINDER)
            if not weather_asked and city and WEAR_QUESTION.search(message):
                missing.append(WEATHER_REMINDER)
            if missing and not reminded:
                # The model skipped the books or the weather on a question that needs them: ask it once.
                reminded = True
                messages.append({"role": "assistant", "content": msg.content or ""})
                messages.append({"role": "user", "content": " ".join(missing)})
                continue
            return result(msg.content or "")

        messages.append({"role": "assistant", "content": msg.content,
                         "tool_calls": [tc.model_dump() for tc in msg.tool_calls]})
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            if tc.function.name == "get_weather":
                weather_asked = True
                try:
                    days_ahead = int(args.get("days_ahead", asked_day if asked_day is not None else 0))
                except (TypeError, ValueError):
                    days_ahead = 0
                where = str(args.get("city") or city).strip()
                forecast = weather.day_forecast(where, "" if args.get("city") else country, days_ahead)
                if forecast:
                    forecasts.append(forecast)
                    content = json.dumps(forecast)
                else:
                    content = json.dumps({"weather": None, "note": "The weather could not be checked (no city, "
                                          "unknown city or service down): say so and do not invent it."})
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": content})
                continue
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
