"""The BO3 Gap Agent as an A2A agent: Agent Card at /a2a/gap/.well-known/agent-card.json, JSON-RPC at POST /a2a/gap.

Ask it what a wardrobe is missing, either with a structured goal (fast, no LLM) or in plain words (the Gap Agent then
chooses its tools). The caller's Supabase token decides whose wardrobe is analysed.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:      # a2a_protocol/ sits at the root of the repository
    sys.path.insert(0, str(ROOT))

from a2a_protocol import AgentCall, AgentResult, Skill, build_router  # noqa: E402

from agent.coverage import GOALS  # noqa: E402
from agent.gap_agent import GapAgent  # noqa: E402
from agent.tools import GapAgentTools  # noqa: E402


def _gap_line(rank: int, gap: dict) -> str:
    detail = gap.get("description") or gap.get("suggested_item") or ""
    return f"{rank}. {gap.get('name', '?')} ({gap.get('priority', '?')})" + (f": {detail}" if detail else "")


def make_router(memory, principal):
    def handle(call: AgentCall) -> AgentResult:
        user_id = str(call.principal)
        goal = str(call.data.get("goal") or "")
        if goal:
            if goal not in GOALS:
                return AgentResult(text=f"Unknown goal {goal!r}. Known goals: {', '.join(GOALS)}.", state="failed")
            items = call.data.get("wardrobe_items")
            if not isinstance(items, list):
                return AgentResult(text="The orchestrator must provide the wardrobe snapshot.", state="failed")
            ranking = GapAgentTools(memory, user_id, wardrobe_items=items).rank_gaps(goal)
            gaps = ranking.get("ranked_gaps", [])
            label = ranking.get("goal_label") or goal
            text = (f"Wardrobe gaps for {label}:\n" + "\n".join(_gap_line(n, g) for n, g in enumerate(gaps[:5], 1))
                    if gaps else f"Your wardrobe covers everything essential for {label}.")
            return AgentResult(text=text, data={"goal": goal, "ranking": ranking})

        if not call.text:
            return AgentResult(text="Tell me what you want to be able to wear (for example: winter work days).",
                               state="input-required")
        context = ""
        capsule = call.data.get("capsule")
        if isinstance(capsule, dict):   # another agent (the Trip Agent) shares what it is planning
            trip = capsule.get("trip") or {}
            context = (f"\n\nContext from the Trip Agent: trip to {trip.get('destination', 'an unknown place')}, "
                       f"activities: {', '.join(trip.get('activities') or []) or 'unspecified'}, "
                       f"{len(capsule.get('days') or [])} day(s). Pick the goal that fits best.")
        conversation_id = memory.start_conversation(user_id)
        items = call.data.get("wardrobe_items")
        if not isinstance(items, list):
            return AgentResult(text="The orchestrator must provide the wardrobe snapshot.", state="failed")
        tools = GapAgentTools(memory, user_id, conversation_id, wardrobe_items=items)
        result = GapAgent(tools).run(call.text + context, [])
        memory.add_message(conversation_id, "user", call.text)
        memory.add_message(conversation_id, "assistant", result.answer)
        return AgentResult(text=result.answer, data={"ranking": result.ranking, "items": result.items})

    return build_router(
        prefix="/a2a/gap", name="DressMe Gap Agent", version="1.0.0", handler=handle, principal=principal,
        description="Tells a user what their wardrobe cannot do yet for a goal (winter work days...), ranked by "
                    "priority, with owned pieces already covering it. Rules decide what is a gap; XGBoost only "
                    "orders them. Data: goal (optional), capsule (optional, from the Trip Agent).",
        skills=[Skill("wardrobe-gaps", "Wardrobe gaps", "Ranks the pieces missing for a goal such as winter_work.",
                      ["wardrobe", "gaps", "shopping"],
                      ["What is my wardrobe missing for winter work?", "Quels vetements me manquent pour un voyage ?"])])
