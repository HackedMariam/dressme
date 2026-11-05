"""The Outfit Builder as an agent (LangGraph).

A small graph, one node per job, the LLM only decides where judgement is needed:

    weather -> closet -> knowledge -> compose -> validate --(invalid pieces, first time)--> compose
                                                    \\--> END

- weather   : the real forecast of the user's city (weather.py), or nothing when it cannot be known.
- closet    : the pieces the user owns, grouped by role (tops, bottoms, dresses, outerwear, shoes) with their facts.
- knowledge : what the fashion books say about this occasion and these colours / fabrics (RAG, with sources).
- compose   : the LLM builds outfits from the closet ids only, and explains each choice with real facts.
- validate  : plain code checks every outfit (real ids, one top + one bottom or a dress, shoes, no duplicate role)
              and sends the model back once with what is wrong. Only valid outfits are returned.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from . import config, rag_client, weather

log = logging.getLogger("dressme.outfit_agent")

COUNT = 3
FACTS = ("id", "name", "category", "category_group", "color_name", "color_family", "pattern", "material",
         "seasons", "style", "occasions", "formality", "warmth")
BODY_GROUPS = {"Tops", "Bottoms", "Dresses", "Outerwear", "Shoes"}
COLD = ("autumn", "winter")

SYSTEM = (
    "You are the outfit-building agent of DressMe, a personal wardrobe app. Build complete outfits using ONLY the "
    "pieces listed in the closet (refer to them by their id). Rules: every outfit is either one dress or one top plus "
    "one bottom, always with one pair of shoes, and one outerwear piece when the weather or season is cold or rainy "
    "(optional otherwise); never two pieces of the same role; never invent a piece. The outfits must be different from "
    "each other (do not reuse the same piece in more than one outfit when the closet allows it). Fit the real weather "
    "(warmth, rain, wind), the occasion and its formality, and the season; combine colours as the book advice says. "
    "Reply with ONLY a JSON object, plain text, no markdown, no emojis: "
    '{"outfits": [{"title": "a short name for the look", "items": ["<id>", ...], '
    '"weather_note": "one sentence on how this outfit answers the forecast (empty if no forecast)", '
    '"why": ["3 to 5 short reasons, each pointing to a real fact of the pieces (colour, material, warmth, season, '
    'occasion, style) and to the book advice with its [S1]-style marker when it applies"]}], '
    '"missing": ["a piece the closet lacks for a better outfit, e.g. \'a rain jacket\' (empty if nothing)"]}. '
    "Give " + str(COUNT) + " outfits when the closet allows it, fewer when it does not."
)


class State(TypedDict, total=False):
    items: list[dict]
    occasion: str
    season: str
    place: dict
    avoid: list[list[str]]           # outfits already shown (item ids): build different ones
    forecast: dict | None
    closet: dict[str, list[dict]]
    advice: list[dict]
    sources: dict[str, dict]
    draft: list[dict]
    missing: list[str]
    problems: list[str]
    tries: int
    outfits: list[dict]


# ---------------------------------------------------------------------------------------------------- nodes
def node_weather(state: State) -> dict:
    place = state.get("place") or {}
    city = (place.get("city") or "").strip() or "Tunis"
    country = (place.get("country") or "").strip() or "Tunisia"
    forecast = weather.day_forecast(city, country, 0)
    if not forecast and city.lower() != "tunis":
        forecast = weather.day_forecast("Tunis", "Tunisia", 0)
    return {"forecast": forecast}


def node_closet(state: State) -> dict:
    closet: dict[str, list[dict]] = {}
    for item in state["items"]:
        group = item.get("category_group")
        if group in BODY_GROUPS:
            closet.setdefault(group, []).append({key: item.get(key) for key in FACTS})
    return {"closet": closet}


def node_knowledge(state: State) -> dict:
    occasion, season = state["occasion"], state["season"]
    forecast = state.get("forecast")
    climate = f"{season}" + (f" with {forecast['condition']} and {forecast['temp_min_c']} to {forecast['temp_max_c']} C"
                             if forecast else "")
    questions = [f"What is the right dress code and level of formality for an {occasion} occasion?",
                 f"Which colour combinations and fabrics work best for outfits in {climate}?"]
    advice, sources = [], {}
    for question in questions:
        found = rag_client.advise(question)
        if found:
            advice.append({"question": question, "advice": found["answer"]})
            for source in found["sources"]:
                sources.setdefault(source["marker"], source)
    return {"advice": advice, "sources": sources}


def _brief(state: State) -> str:
    forecast = state.get("forecast")
    lines = [f"Occasion: {state['occasion']}. Season: {state['season']}."]
    lines.append(f"Forecast today: {forecast['summary']}; wind {forecast.get('wind_kmh')} km/h." if forecast
                 else "Forecast: unavailable, say nothing invented about the weather.")
    if state.get("advice"):
        lines.append("Book advice (keep the [S#] markers when you use it): " + json.dumps(state["advice"]))
    if state.get("avoid"):
        lines.append("Already shown, build DIFFERENT outfits from these (lists of piece ids): "
                     + json.dumps(state["avoid"][-6:]))
    lines.append("Closet by role: " + json.dumps(state["closet"]))
    return "\n".join(lines)


def node_compose(state: State) -> dict:
    from openai import OpenAI

    client = OpenAI(api_key=config.OPENAI_API_KEY, timeout=config.LLM_TIMEOUT, max_retries=2)
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": _brief(state)}]
    if state.get("problems"):
        messages.append({"role": "assistant", "content": json.dumps({"outfits": state.get("draft", [])})})
        messages.append({"role": "user", "content": "Fix these problems and answer again with the same JSON format: "
                         + " ".join(state["problems"])})
    try:
        resp = client.chat.completions.create(
            model=config.LLM_MODEL, temperature=0.6, max_completion_tokens=2200, messages=messages,
            response_format={"type": "json_object"})
        data = json.loads(resp.choices[0].message.content or "{}")
    except Exception:
        log.exception("outfit agent LLM call failed")
        return {"draft": [], "missing": [], "tries": state.get("tries", 0) + 1, "problems": []}
    draft = [o for o in (data.get("outfits") or []) if isinstance(o, dict)]
    return {"draft": draft, "missing": _lines(data.get("missing")), "tries": state.get("tries", 0) + 1}


def _lines(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    out = []
    for entry in value:
        text = re.sub(r"^\s*(?:[-•]|\d+[.)])\s*", "", re.sub(r"[*_`#]+", "", str(entry))).strip()
        if text:
            out.append(text)
    return out


def check_outfit(ids: list[str], by_id: dict[str, dict], cold: bool) -> list[str]:
    """What is wrong with one outfit (empty list = valid)."""
    problems = []
    if len(set(ids)) != len(ids):
        problems.append("a piece appears twice")
    pieces = [by_id[i] for i in ids if i in by_id]
    unknown = [i for i in ids if i not in by_id]
    if unknown:
        problems.append(f"unknown ids {unknown}")
    groups = [p.get("category_group") for p in pieces]
    for group in BODY_GROUPS:
        if groups.count(group) > 1:
            problems.append(f"two pieces of role {group}")
    has_dress = "Dresses" in groups
    if has_dress and ("Tops" in groups or "Bottoms" in groups):
        problems.append("a dress is worn alone, without a top or bottom")
    if not has_dress and not ("Tops" in groups and "Bottoms" in groups):
        problems.append("it needs a dress, or a top and a bottom")
    if "Shoes" not in groups:
        problems.append("it has no shoes")
    if cold and "Outerwear" not in groups and any(p.get("category_group") == "Outerwear" for p in by_id.values()):
        problems.append("the weather is cold: add an outerwear piece")
    return problems


def node_validate(state: State) -> dict:
    by_id = {i["id"]: i for g in state["closet"].values() for i in g}
    forecast = state.get("forecast")
    cold = state["season"] in COLD or bool(forecast and (forecast["temp_min_c"] < 14 or (forecast.get("rain_chance_percent") or 0) >= 60))
    good, problems = [], []
    for number, outfit in enumerate(state.get("draft", []), 1):
        ids = [str(i) for i in (outfit.get("items") or [])]
        found = check_outfit(ids, by_id, cold)
        if found:
            problems.append(f"Outfit {number}: " + "; ".join(found) + ".")
            continue
        good.append({"title": " ".join(_lines(outfit.get("title"))) or f"Outfit {number}", "items": ids,
                     "weather_note": " ".join(_lines(outfit.get("weather_note"))), "why": _lines(outfit.get("why"))})
    if problems and state.get("tries", 0) < 2:
        return {"problems": problems, "outfits": good}
    return {"problems": [], "outfits": good[:COUNT]}


def after_validate(state: State) -> str:
    return "compose" if state.get("problems") else END


def build_graph():
    graph = StateGraph(State)
    graph.add_node("weather", node_weather)
    graph.add_node("closet", node_closet)
    graph.add_node("knowledge", node_knowledge)
    graph.add_node("compose", node_compose)
    graph.add_node("validate", node_validate)
    graph.add_edge(START, "weather")
    graph.add_edge("weather", "closet")
    graph.add_edge("closet", "knowledge")
    graph.add_edge("knowledge", "compose")
    graph.add_edge("compose", "validate")
    graph.add_conditional_edges("validate", after_validate, {"compose": "compose", END: END})
    return graph.compile()


_GRAPH = None


def build(items: list[dict], occasion: str, season: str, place: dict | None = None,
          avoid: list[list[str]] | None = None) -> dict:
    """Run the agent: {"outfits": [{title, items: [ids], weather_note, why}], "weather", "sources", "missing"}."""
    global _GRAPH
    if not config.OPENAI_API_KEY:
        raise RuntimeError("The outfit agent needs an OPENAI_API_KEY configured on the server.")
    _GRAPH = _GRAPH or build_graph()
    state = _GRAPH.invoke({"items": items, "occasion": occasion, "season": season, "place": place or {},
                           "avoid": avoid or [], "tries": 0})
    outfits = state.get("outfits") or []
    cited = " ".join(" ".join([o["weather_note"], *o["why"]]) for o in outfits)
    sources = [s for marker, s in (state.get("sources") or {}).items() if marker in cited]
    forecast = state.get("forecast")
    unit = str((place or {}).get("unit") or "")
    return {"outfits": outfits, "sources": sources, "missing": state.get("missing") or [],
            "weather": _view(forecast, unit)}


def _view(forecast: dict | None, unit: str) -> dict | None:
    if not forecast:
        return None
    fahrenheit = unit.lower().startswith("f")
    low, high = (forecast["temp_min_f"], forecast["temp_max_f"]) if fahrenheit else (forecast["temp_min_c"], forecast["temp_max_c"])
    return {**forecast, "unit": "F" if fahrenheit else "C", "temp_min": low, "temp_max": high}
