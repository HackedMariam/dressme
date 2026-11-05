"""LLM side of BO3: the tool-calling gap agent, and the one-shot stylist reading of a ranking."""

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import sys

from dotenv import load_dotenv
from openai import OpenAI

_ROOT = Path(__file__).resolve().parents[3]            # agent_kit/ sits at the root of the repository
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from agent_kit import run_loop  # noqa: E402

from .coverage import GOALS
from .tools import TOOL_SCHEMAS, GapAgentTools

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
load_dotenv(Path(__file__).resolve().parents[3] / ".env")  # repo-root .env

# Any OpenAI-compatible endpoint works: OpenAI by default, or Groq/Gemini via LLM_BASE_URL.
DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"
MAX_STEPS = 6

logger = logging.getLogger("dressme.bo3.interpreter")

GOAL_LINES = "\n".join(f"- `{goal_id}`: {goal['label']} ({goal['season']})" for goal_id, goal in GOALS.items())

SYSTEM_PROMPT = f"""You are the DressMe Wardrobe Gap Agent (BO3) for a user in Tunisia.
Your job is to tell the user what their wardrobe is structurally unable to do, using only tool results.

Available goals:
{GOAL_LINES}

How to work:
1. Map the user's request to one goal. If none fits, say which goals you support and ask them to choose.
2. Call `rank_gaps` for that goal. Call `get_wardrobe` only if you need item details.
3. If the user asks what changed or refers to earlier advice, call `get_past_analyses`.
4. Whenever you name owned items (what already covers a requirement, a `closest_owned_item`, or pieces the user
   asks to see), call `show_items` with their ids so the user sees them as photo cards. Take the ids from
   `matched_item_ids`, `closest_owned_item_id` or `get_wardrobe`. Show only items you actually talk about, at most 8.
   If the user just asks to see some of their pieces (for example their shoes), call `get_wardrobe`, pick the
   matching items and show them.

Rules:
- Never invent gaps, items, scores or features. Every claim must come from a tool result.
- A gap is only real if the coverage rules flagged it. The ranker only orders gaps; its score is not a probability.
- Give a prioritised list, not a shopping list. Mention owned items that already cover parts of the goal.
- Mention closest_owned_item only when redundancy_score >= 0.6: then say the user may already own something
  similar (name it). Below 0.6, do not mention closest_owned_item at all.
- "Already covered" lists the goal's covered requirements (the `covered` field), not individual items.
- `not_analysed` lists pieces the wardrobe scanner cannot detect from photos (for example underwear and sleepwear).
  Say they are not analysed when it is relevant; never claim the user lacks them and never list them as gaps.
- The profile's `department` (women, men, both, or empty) says whose wardrobe the suggestions are for. The gaps and
  their suggested items already follow it: never add a piece from another department on your own (no dress for a
  man, no tie for a woman) and never guess a gender. If `department` is empty, you may say the user can set it in
  their profile to get more fitting suggestions.
- Be honest about uncertainty: the wardrobe analysis is real, but the ranker that orders gaps is trained on
  synthetic data until real user feedback is collected.
- Reply in the user's language (English, French or Tunisian Arabic).

Answer format (Markdown):
**Goal:** <goal label>
For each gap, in rank order: `<rank>. <name>` — priority, why it matters (cite coverage owned/required, outfit gain,
use frequency), and suggested item.
**Already covered:** short list.
**Confidence:** one sentence on limits of this analysis.
"""


@dataclass
class AgentResult:
    answer: str
    trace: list[dict[str, Any]] = field(default_factory=list)
    ranking: dict[str, Any] | None = None
    items: list[dict[str, Any]] = field(default_factory=list)   # owned items to show as photo cards


def llm_settings() -> tuple[str | None, str, str]:
    return (
        os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY"),
        os.getenv("LLM_BASE_URL", DEFAULT_BASE_URL),
        os.getenv("LLM_MODEL", DEFAULT_MODEL),
    )


class GapAgent:
    def __init__(self, tools: GapAgentTools) -> None:
        api_key, base_url, self.model = llm_settings()
        if not api_key:
            raise RuntimeError("Set OPENAI_API_KEY (or LLM_API_KEY) in the repo-root .env (see .env.example).")
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.tools = tools

    def run(self, user_message: str, history: list[dict[str, str]]) -> AgentResult:
        """history holds earlier user/assistant turns (short-term memory)."""
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            *history,
            {"role": "user", "content": user_message},
        ]

        trace: list[dict[str, Any]] = []
        self.tools.last_ranking = None
        self.tools.shown_items = []
        step = 0

        def call_llm(msgs: list[dict[str, Any]]):
            nonlocal step
            step += 1
            return self.client.chat.completions.create(
                model=self.model, messages=msgs, tools=TOOL_SCHEMAS, tool_choice="auto", temperature=0.2,
            ).choices[0].message

        def run_tool(name: str, arguments: dict[str, Any]) -> str:
            result = self.tools.call(name, arguments)
            trace.append({"step": step, "tool": name, "arguments": arguments, "result": result})
            return json.dumps(result, default=str)

        # The tool loop is the shared LangGraph graph (agent_kit): llm -> tools -> llm ... -> answer.
        final, outcome = run_loop(messages=messages, call_llm=call_llm, run_tool=run_tool, max_rounds=MAX_STEPS)
        if outcome == "answer":
            return AgentResult(final or "", trace, self.tools.last_ranking, self.tools.shown_items)
        if outcome == "error":
            raise RuntimeError("The gap agent could not reach the language model.")
        return AgentResult(
            "I could not finish the analysis within the step limit. Please rephrase your request.",
            trace,
            self.tools.last_ranking,
            self.tools.shown_items,
        )


# --- One-shot stylist reading of a ranking (GET /api/bo3/gaps?interpret=true) -----------------

def interpret_gaps_with_gpt(gaps_data: dict[str, Any]) -> Optional[str]:
    """Generates an elegant styling interpretation of the wardrobe gaps for the given goal.

    Non-intrusive: If OPENAI_API_KEY is missing or the API call fails, returns None.
    """
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY")
    if not api_key:
        return None

    model = os.getenv("LLM_MODEL", "gpt-4o")

    # If all requirements are already met:
    if not gaps_data.get("ranked_gaps"):
        return (
            f"Your wardrobe fully satisfies every essential requirement for {gaps_data.get('goal_label', 'this occasion')}. "
            "You have complete outfit coverage with no critical gaps."
        )

    goal_label = gaps_data.get("goal_label") or gaps_data.get("goal", "the selected goal")
    season = gaps_data.get("season", "current")

    summary_gaps = []
    for g in gaps_data.get("ranked_gaps", [])[:5]:
        summary_gaps.append({
            "piece": g.get("name"),
            "priority": g.get("priority"),
            "description": g.get("description") or g.get("suggested_item"),
            "deficit": g.get("coverage_deficit"),
        })

    # `covered` holds requirement dicts ({"name": "Work trousers", "matched_items": [...], ...}).
    covered = [c.get("name", "") if isinstance(c, dict) else str(c) for c in gaps_data.get("covered", [])]
    covered = [name for name in covered if name]

    system_prompt = (
        "You are DressMe Personal Stylist. You interpret wardrobe gap analysis results into "
        "concise, sophisticated, and practical fashion guidance for the user. "
        "Do NOT use emojis. Maintain a clear, professional, and encouraging tone."
    )

    user_prompt = (
        f"Wardrobe Goal: {goal_label} ({season} season)\n"
        f"Pieces you already have covered: {', '.join(covered) if covered else 'None'}\n\n"
        f"Ranked Wardrobe Gaps Identified by the AI Ranker:\n"
        f"{json.dumps(summary_gaps, indent=2)}\n\n"
        "Please provide a concise stylist interpretation with:\n"
        "1. Overall Capsule Assessment (1-2 sentences on how well their closet is prepared)\n"
        "2. Priority Recommendations (explain why the top 1-2 missing pieces are essential to complete outfits)\n"
        "3. Shopping Tip (smart advice on silhouettes or colors to look for)\n"
        "Remember: Do not use emojis."
    )

    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
            max_tokens=350,
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        logger.warning("[BO3 Interpreter] OpenAI call failed: %s", exc)
        return None
