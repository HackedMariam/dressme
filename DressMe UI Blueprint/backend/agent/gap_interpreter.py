"""GPT-4 Stylist Interpretation for BO3 Wardrobe Gaps."""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

logger = logging.getLogger("dressme.bo3.interpreter")


def interpret_gaps_with_gpt(gaps_data: dict[str, Any]) -> Optional[str]:
    """Generates an elegant styling interpretation of the wardrobe gaps for the given goal.

    Non-intrusive: If OPENAI_API_KEY is missing or the API call fails, returns None.
    """
    if not (os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY") or os.getenv("GROQ_API_KEY")):
        return None

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
            "description": g.get("description"),
            "deficit": g.get("coverage_deficit"),
        })

    covered = gaps_data.get("covered", [])

    system_prompt = (
        "You are DressMe Personal Stylist. You interpret wardrobe gap analysis results into "
        "concise, sophisticated, and practical fashion guidance for the user. "
        "Do NOT use emojis. Maintain a clear, professional, and encouraging tone."
    )

    user_prompt = (
        f"Wardrobe Goal: {goal_label} ({season} season)\n"
        f"Pieces you already have covered: {', '.join(str(item.get('name', '')) for item in covered) if covered else 'None'}\n\n"
        f"Ranked Wardrobe Gaps Identified by the AI Ranker:\n"
        f"{json.dumps(summary_gaps, indent=2)}\n\n"
        "Please provide a concise stylist interpretation with:\n"
        "1. Overall Capsule Assessment (1-2 sentences on how well their closet is prepared)\n"
        "2. Priority Recommendations (explain why the top 1-2 missing pieces are essential to complete outfits)\n"
        "3. Shopping Tip (smart advice on silhouettes or colors to look for)\n"
        "Remember: Do not use emojis."
    )

    try:
        from .gap_agent import llm_clients
        response = None
        last_error = None
        for _, model, client in llm_clients():
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "system", "content": system_prompt},
                              {"role": "user", "content": user_prompt}],
                    temperature=0.7, max_tokens=350)
                break
            except Exception as error:
                last_error = error
        if response is None:
            raise RuntimeError("All configured LLM providers failed.") from last_error
        return response.choices[0].message.content.strip()
    except Exception as exc:
        logger.warning("[BO3 Interpreter] OpenAI call failed: %s", exc)
        return None
