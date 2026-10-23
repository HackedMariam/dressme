"""
Claude integration (Anthropic SDK)
- explain(): rewrites the rule-based explanation as shopper-friendly advice
- run_agent(): autonomous tool-use agent over the shared toolset (agent_tools.py)
Everything degrades gracefully: without an API key the app keeps working with rule-based text.
"""

import json
import logging
import time
from typing import Dict, List, Optional

from prompts import OptimizedPrompts

logger = logging.getLogger(__name__)

# Server-side refusal fallback: if Claude declines, the API retries on Anthropic's recommended model
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class ClaudeClient:
    """Thin wrapper around the Anthropic SDK with graceful fallback"""

    provider = "claude"

    def __init__(self, api_key: str, model: str, effort: str = "low", agent_effort: str = "medium",
                 max_tokens: int = 16000, enabled: bool = True):
        self.model = model
        self.effort = effort
        self.agent_effort = agent_effort
        self.max_tokens = max_tokens
        self.client = None
        self.error: Optional[str] = None
        self.paused_until = 0.0  # set after billing/auth errors to avoid a failing call per request

        if not enabled:
            self.error = "LLM disabled by configuration (LLM_ENABLED=False)"
        elif not api_key or "your" in api_key.lower():
            self.error = "CLAUDE_API_KEY is not set in .env"
        else:
            try:
                import anthropic
                self.client = anthropic.Anthropic(api_key=api_key, timeout=120.0)
            except ImportError as e:
                self.error = f"anthropic SDK not installed: {e}"

        if self.client:
            logger.info(f"✅ Claude client ready (model: {model})")
        else:
            logger.warning(f"⚠️ Claude unavailable - {self.error}. Using rule-based explanations.")

    @property
    def available(self) -> bool:
        return self.client is not None and time.time() >= self.paused_until

    def status(self) -> Dict:
        return {"available": self.available, "provider": self.provider, "model": self.model, "effort": self.effort,
                "agent_effort": self.agent_effort, "error": self.error,
                "paused_for_s": max(0, round(self.paused_until - time.time()))}

    def pause(self, reason: str, seconds: int = 300) -> None:
        """Stop calling Claude for a while after a non-transient error (no credits, bad key)"""
        self.error = reason
        self.paused_until = time.time() + seconds
        logger.error(f"Claude paused for {seconds}s: {reason}")

    def handle_api_error(self, e) -> None:
        """Pause on errors that will not fix themselves between two requests"""
        import anthropic

        if isinstance(e, (anthropic.AuthenticationError, anthropic.PermissionDeniedError)):
            self.pause("clé CLAUDE_API_KEY invalide ou sans permission")
        elif isinstance(e, anthropic.BadRequestError) and "credit balance" in str(e.message).lower():
            self.pause("plus de crédits sur le compte Anthropic (console.anthropic.com → Plans & Billing)")

    @staticmethod
    def _text(message) -> str:
        return "".join(block.text for block in message.content if block.type == "text").strip()

    # ------------------------------------------------------------------
    # Explanations (Feature 12, LLM version)
    # ------------------------------------------------------------------

    def explain(self, item_name: str, result: Dict, language: str = "English") -> Optional[str]:
        """Return a Claude explanation, or None to keep the rule-based one"""
        if not self.available:
            return None

        import anthropic

        similar = "\n".join(
            f"- {m['name']} ({m.get('color') or '?'} {m.get('material') or ''} {m.get('style') or ''}, "
            f"similarity {m['similarity']:.0%})"
            for m in result.get("similar_items", [])[:5]
        ) or "- none"

        prompt = OptimizedPrompts.format_prompt(
            OptimizedPrompts.PROMPT_EXPLANATION,
            item_name=item_name,
            score=result["redundancy_score"],
            recommendation=result["recommendation"],
            saturation=round(result.get("category_saturation", 0)),
            contribution=round(result.get("outfit_contribution", 0)),
            similar_items=similar,
            language=language,
        )

        try:
            message = self.client.beta.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=OptimizedPrompts.SYSTEM_ANALYZER,
                output_config={"effort": self.effort},
                betas=[FALLBACK_BETA],
                fallbacks="default",
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.RateLimitError:
            logger.warning("Claude: rate limited - using rule-based explanation")
            return None
        except anthropic.APIStatusError as e:
            logger.error(f"Claude API error {e.status_code}: {e.message} (request {getattr(e, 'request_id', None)})")
            self.handle_api_error(e)
            return None
        except anthropic.APIConnectionError as e:
            logger.error(f"Claude connection error: {e}")
            return None

        if message.stop_reason == "refusal":
            logger.warning("Claude declined the explanation request")
            return None
        return self._text(message) or None

    # ------------------------------------------------------------------
    # Autonomous agent (tool use)
    # ------------------------------------------------------------------

    def summarize(self, headline: str, reasons: List[str], actions: List[str]) -> Optional[str]:
        """Phrase the agent's final decision as a short message to the shopper (decision unchanged)"""
        if not self.available:
            return None
        import anthropic

        lines = (["<decision>", headline, "Raisons:"] + [f"- {r}" for r in reasons]
                 + ["Actions:"] + [f"- {a}" for a in actions] + ["</decision>", "", ""])
        prompt = ("\n".join(lines) +
                  "Rédige ce verdict pour l'utilisateur en 3 à 4 phrases, en français, ton direct et bienveillant. "
                  "Ne change pas le verdict et n'invente aucun article.")
        try:
            message = self.client.beta.messages.create(
                model=self.model, max_tokens=self.max_tokens, system=OptimizedPrompts.SYSTEM_ANALYZER,
                output_config={"effort": self.effort}, betas=[FALLBACK_BETA], fallbacks="default",
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.APIStatusError as e:
            self.handle_api_error(e)
            return None
        except anthropic.APIConnectionError:
            return None
        return self._text(message) if message.stop_reason != "refusal" else None

    def run_agent(self, user_message: str, wardrobe: List[Dict], engine, max_iterations: int = 8,
                  on_step=None, image: Optional[str] = None, profile: Optional[Dict] = None,
                  history: Optional[List[Dict]] = None) -> Dict:
        """Tool-use loop over the shared toolset (agent_tools) - same tools and prompt as the GPT agent"""
        if not self.available:
            raise RuntimeError(self.error or "Claude unavailable")
        from agent_tools import anthropic_tools, build_tools

        steps: List[Dict] = []

        def record(tool: str, tool_input: Dict, output, cards: Optional[Dict] = None) -> str:
            text = json.dumps(output, default=str, ensure_ascii=False)
            step = {"n": len(steps) + 1, "tool": tool, "input": tool_input, "output_preview": text[:500], "cards": cards}
            steps.append(step)
            if on_step:
                on_step(step)
            return text

        tools = build_tools(engine, wardrobe, record, profile)
        wardrobe_text = "\n".join(
            f"- {i.get('name')} ({i.get('category')}, {i.get('color')}, {i.get('material')}, {i.get('style')})"
            for i in wardrobe) or "- (vide)"
        content = [{"type": "text", "text": OptimizedPrompts.agent_user_message(wardrobe_text, user_message, bool(history))}]
        if image:
            media_type, data = "image/jpeg", image
            if image.startswith("data:"):
                header, data = image.split(",", 1)
                media_type = header[5:].split(";")[0] or media_type
            content.insert(0, {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}})
        messages = [{"role": turn["role"], "content": turn["content"]} for turn in (history or [])[-10:]]
        messages.append({"role": "user", "content": content})

        start = time.time()
        usage = {"input_tokens": 0, "output_tokens": 0}
        final = None
        for iteration in range(max_iterations):
            # Grounding: the first turn must call a tool (look at the wardrobe) before answering
            final = self.client.beta.messages.create(
                model=self.model, max_tokens=self.max_tokens, system=OptimizedPrompts.agent_system(profile),
                output_config={"effort": self.agent_effort}, betas=[FALLBACK_BETA], fallbacks="default",
                tools=anthropic_tools(tools), tool_choice={"type": "any" if iteration == 0 else "auto"},
                messages=messages)
            usage["input_tokens"] += final.usage.input_tokens
            usage["output_tokens"] += final.usage.output_tokens
            calls = [block for block in final.content if block.type == "tool_use"]
            if final.stop_reason != "tool_use" or not calls:
                break
            messages.append({"role": "assistant", "content": final.content})
            results = []
            for call in calls:
                func = tools.get(call.name, (None,))[0]
                try:
                    output = func(**(call.input or {})) if func else json.dumps({"error": f"unknown tool {call.name}"})
                    is_error = func is None
                except Exception as e:  # bad arguments -> the model can retry
                    output, is_error = json.dumps({"error": f"{type(e).__name__}: {e}"}), True
                results.append({"type": "tool_result", "tool_use_id": call.id, "content": output, "is_error": is_error})
            messages.append({"role": "user", "content": results})

        if final is None:
            raise RuntimeError("Agent produced no response")
        answer = self._text(final) if final.stop_reason != "refusal" else "La demande a été refusée par le modèle."
        return {
            "answer": answer or "Nombre maximal d'étapes atteint.",
            "stop_reason": final.stop_reason,
            "model": getattr(final, "model", self.model),
            "steps": steps,
            "iterations": len(steps),
            "usage": usage,
            "execution_time_ms": round((time.time() - start) * 1000, 1),
        }
