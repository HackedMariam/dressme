"""The AI Stylist and the Outfit Builder as A2A agents (Agent Cards + JSON-RPC endpoints on BO1).

    GET  /a2a/stylist/.well-known/agent-card.json      POST /a2a/stylist
    GET  /a2a/outfit/.well-known/agent-card.json       POST /a2a/outfit

Both authenticate the caller with the same Supabase bearer token as the rest of the API and work on that user's
wardrobe. Another agent (or the orchestrator) can therefore ask them for advice or for outfits without going through
the React app.

    GET  /a2a/wardrobe/.well-known/agent-card.json     POST /a2a/wardrobe

The Wardrobe Agent also answers structured requests without any LLM (data.action = list | search | check-duplicate),
which is how the other agents, even those running in another service, read the wardrobe.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:      # a2a_protocol/ sits at the root of the repository
    sys.path.insert(0, str(ROOT))

from a2a_protocol import AgentCall, AgentResult, Skill, build_router  # noqa: E402

from . import agent, outfit_agent, similar_agent, wardrobe_a2a, wardrobe_agent  # noqa: E402
from .auth import current_user  # noqa: E402
from .taxonomy import OCCASIONS, SEASONS  # noqa: E402

VERSION = "1.0.0"


def _place(data: dict) -> dict:
    return {"city": str(data.get("city") or "")[:80], "country": str(data.get("country") or "")[:80],
            "unit": str(data.get("unit") or "")[:12]}


def _season_now(today: date | None = None) -> str:
    month = (today or date.today()).month
    return "spring" if 3 <= month <= 5 else "summer" if 6 <= month <= 8 else "autumn" if 9 <= month <= 11 else "winter"


def _word_in(text: str, options: list[str]) -> str | None:
    lowered = text.lower()
    return next((option for option in options if option in lowered), None)


# ------------------------------------------------------------------------------------------------ AI Stylist
def handle_stylist(call: AgentCall) -> AgentResult:
    items = wardrobe_a2a.list_items(call.principal.id, call.authorization)
    if not call.text:
        return AgentResult(text="Ask me what to wear, how to style a piece, or to find something in the wardrobe.",
                           state="input-required")
    reply = agent.chat(items, call.text, _place(call.data), call.authorization)
    return AgentResult(text=reply["reply"], data={
        "sections": reply.get("sections"), "weather": reply.get("weather"), "sources": reply.get("sources", []),
        "items": [{"id": i.get("id"), "name": i.get("name"), "category": i.get("category")} for i in reply.get("items", [])],
    })


# ------------------------------------------------------------------------------------------------ Outfit Builder
def handle_outfit(call: AgentCall) -> AgentResult:
    items = wardrobe_a2a.list_items(call.principal.id, call.authorization)
    if not items:
        return AgentResult(text="The wardrobe is empty: add clothes before building outfits.", state="failed")
    occasion = str(call.data.get("occasion") or _word_in(call.text, OCCASIONS) or "everyday")
    season = str(call.data.get("season") or _word_in(call.text, SEASONS) or _season_now())
    avoid = [[str(i) for i in group] for group in (call.data.get("avoid") or []) if isinstance(group, list)][:10]
    built = outfit_agent.build(items, occasion[:40], season[:20], _place(call.data), avoid)
    by_id = {i["id"]: i for i in items}
    outfits = [{"title": o["title"], "weather_note": o["weather_note"], "why": o["why"],
                "items": [{"id": i, "name": by_id[i].get("name"), "category": by_id[i].get("category")} for i in o["items"]]}
               for o in built["outfits"]]
    if not outfits:
        return AgentResult(text="No complete outfit could be built from this wardrobe for that request.",
                           data={"outfits": [], "missing": built["missing"]})
    lines = [f"{n}. {o['title']}: " + " + ".join(piece["name"] or "?" for piece in o["items"]) for n, o in enumerate(outfits, 1)]
    return AgentResult(text="\n".join(lines), data={"outfits": outfits, "weather": built["weather"],
                                                    "sources": built["sources"], "missing": built["missing"]})


stylist_router = build_router(
    prefix="/a2a/stylist", name="DressMe AI Stylist", version=VERSION, handler=handle_stylist, principal=current_user,
    description="Personal stylist. Searches the user's real wardrobe, checks the weather of their city and answers "
                "with the advice of a library of fashion books, with sources.",
    skills=[Skill("style-advice", "Style advice", "What to wear, which colours or fabrics go together, how to style a piece.",
                  ["style", "weather", "rag"], ["What should I wear tomorrow for a dinner?", "Which colours go with navy?"]),
            Skill("wardrobe-search", "Wardrobe search", "Finds pieces in the user's wardrobe from a free-form request.",
                  ["search", "wardrobe"], ["Show me a warm jacket for work"])])

outfit_router = build_router(
    prefix="/a2a/outfit", name="DressMe Outfit Builder", version=VERSION, handler=handle_outfit, principal=current_user,
    description="Builds complete, validated outfits from the user's wardrobe for an occasion and a season, using the "
                "real weather and fashion-book advice. Data: occasion, season, city, country, unit, avoid.",
    skills=[Skill("build-outfits", "Build outfits", "Three complete outfits (top and bottom or dress, shoes, layer when cold) "
                  "with the reasons for each choice.", ["outfit", "weather", "rag"],
                  ["Build me outfits for work this winter"])])


# ------------------------------------------------------------------------------------------------ Wardrobe Agent
def handle_wardrobe(call: AgentCall) -> AgentResult:
    user_id = call.principal.id
    action = str(call.data.get("action") or "")
    if action == "list":
        items = wardrobe_agent.list_items(user_id)
        return AgentResult(text=f"{len(items)} piece(s) in the wardrobe.", data={"items": items})
    if action == "ask":                      # another agent asks in plain words: read-only, with the pieces it found
        found = wardrobe_agent.ask(wardrobe_agent.list_items(user_id), str(call.data.get("request") or call.text))
        return AgentResult(text=found["reply"], data={"reply": found["reply"], "items": [wardrobe_agent.trim(i) for i in found["items"]],
                                                      "filters": found["filters"]})
    if action == "search":
        filters = call.data.get("filters") if isinstance(call.data.get("filters"), dict) else {}
        found = [wardrobe_agent.trim(i) for i in wardrobe_agent.search(wardrobe_agent.list_items(user_id), filters)]
        return AgentResult(text=f"{len(found)} piece(s) found.", data={"items": found})
    if action == "check-duplicate":
        candidate = call.data.get("candidate") if isinstance(call.data.get("candidate"), dict) else {}
        verdict = wardrobe_agent.check_duplicate(wardrobe_agent.list_items(user_id), candidate)
        return AgentResult(text=verdict["note"] or ("Possible duplicate." if verdict["duplicate"] else "No duplicate."), data=verdict)
    confirm = call.data.get("confirm")
    reply = wardrobe_agent.converse(user_id, call.text, confirm=confirm if isinstance(confirm, bool) else None,
                                    context_id=call.context_id)
    return AgentResult(text=reply["reply"], state=reply["state"], context_id=reply["context_id"], data={
        "items": [{"id": i.get("id"), "name": i.get("name"), "category": i.get("category")} for i in reply["items"]],
        "filters": reply["filters"], "pending": reply["pending"], "updated": reply["updated"]})


wardrobe_router = build_router(
    prefix="/a2a/wardrobe", name="DressMe Wardrobe Agent", version=VERSION, handler=handle_wardrobe, principal=current_user,
    description="Owns the user's wardrobe: finds, compares and counts pieces, and corrects them. A correction is only "
                "proposed (task state input-required) and saved when the same conversation (contextId) answers yes or "
                "sends data.confirm=true. Structured requests need no LLM: data.action = list | search | check-duplicate.",
    skills=[Skill("wardrobe-search", "Search the wardrobe", "Finds pieces from a free-form request; the LLM chooses the filters.",
                  ["wardrobe", "search"], ["Show me a warm jacket for work"]),
            Skill("wardrobe-read", "Read the wardrobe", "Lists or filters the wardrobe without an LLM (data.action).",
                  ["wardrobe", "read"], ["list"]),
            Skill("wardrobe-correct", "Correct a piece", "Proposes a correction and applies it only after confirmation.",
                  ["wardrobe", "write", "confirmation"], ["Change the colour of my grey skirt to navy"]),
            Skill("wardrobe-stats", "Wardrobe statistics", "Counts by group, category, colour, season and occasion.",
                  ["wardrobe", "stats"], ["How many tops do I own?"]),
            Skill("wardrobe-similar", "Find similar pieces", "Which owned pieces look like this one?",
                  ["wardrobe", "similarity"], ["Do I already have something like my navy blazer?"]),
            Skill("duplicate-check", "Duplicate check", "Is this just-scanned piece already in the wardrobe?",
                  ["wardrobe", "scan"], ["data.action = check-duplicate"])])


# ------------------------------------------------------------------------------------------------ Similar Agent
def handle_similar(call: AgentCall) -> AgentResult:
    pieces = call.data.get("pieces")
    if not isinstance(pieces, list) or not pieces:
        return AgentResult(text="Send the pieces of the look as data.pieces (category, color_name, material, style...).",
                           state="input-required")
    verdict = similar_agent.compare(wardrobe_a2a.list_items(call.principal.id, call.authorization), pieces, call.authorization)
    lines = [f"{p['index'] + 1}. {p['status']}: {p['reason']}" for p in verdict["pieces"]]
    summary = verdict["summary"] + "\n" if verdict["summary"] else ""
    return AgentResult(text=summary + "\n".join(lines), data=verdict)


similar_router = build_router(
    prefix="/a2a/similar", name="DressMe Similar Agent", version=VERSION, handler=handle_similar, principal=current_user,
    description="Tells, for each garment of a look, whether the user already owns it, owns something close or owns "
                "nothing like it. It asks the Wardrobe Agent and never reads the wardrobe itself. Data: pieces.",
    skills=[Skill("find-similar", "Find similar pieces", "owned / close / missing for every detected piece of a look.",
                  ["wardrobe", "similarity", "shopping"], ["Do I already own this look?"])])
