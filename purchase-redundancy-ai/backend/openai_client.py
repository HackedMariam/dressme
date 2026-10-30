"""
OpenAI (GPT) integration - same interface as llm_client.ClaudeClient:
explain(), summarize(), run_agent() (tool-use loop, photo passed to GPT vision), status(), handle_api_error().
"""

import json
import logging
import os
import time
from typing import Dict, List, Optional

from prompts import OptimizedPrompts

logger = logging.getLogger(__name__)


class OpenAIClient:
    provider = "openai"

    def __init__(self, api_key: str, model: str = "gpt-4.1", enabled: bool = True,
                 base_url: str | None = None):
        self.model = model
        self.client = None
        self.error: Optional[str] = None
        self.paused_until = 0.0
        self.fallback = None

        if not enabled:
            self.error = "LLM disabled by configuration (LLM_ENABLED=False)"
        elif not api_key:
            self.error = "OPENAI_API_KEY is not set in .env"
        else:
            try:
                from openai import OpenAI
                self.client = OpenAI(api_key=api_key, base_url=base_url, timeout=120.0, max_retries=2)
            except ImportError as e:
                self.error = f"openai SDK not installed: {e}"

        if self.client:
            logger.info(f"✅ OpenAI client ready (model: {model})")
        else:
            logger.warning(f"⚠️ OpenAI unavailable - {self.error}")

    @property
    def available(self) -> bool:
        return self.client is not None and time.time() >= self.paused_until

    def status(self) -> Dict:
        return {"available": self.available, "provider": self.provider, "model": self.model, "error": self.error,
                "paused_for_s": max(0, round(self.paused_until - time.time()))}

    def pause(self, reason: str, seconds: int = 300) -> None:
        self.error = reason
        self.paused_until = time.time() + seconds
        logger.error(f"OpenAI paused for {seconds}s: {reason}")

    def handle_api_error(self, e) -> None:
        """Pause on errors that will not fix themselves between two requests"""
        import openai

        if isinstance(e, (openai.AuthenticationError, openai.PermissionDeniedError)):
            self.pause("clé OPENAI_API_KEY invalide ou révoquée")
        elif isinstance(e, openai.RateLimitError) and "quota" in str(e).lower():
            self.pause("quota OpenAI épuisé (platform.openai.com → Billing)")
        elif isinstance(e, openai.NotFoundError):
            self.pause(f"modèle {self.model} indisponible pour cette clé")

    def _chat(self, messages, **kwargs):
        import openai

        try:
            return self.client.chat.completions.create(model=self.model, messages=messages, **kwargs)
        except openai.APIError as e:
            logger.error(f"OpenAI API error: {e}")
            self.handle_api_error(e)
            if self.fallback and self.fallback.available:
                logger.warning("Falling back from %s to %s", self.provider, self.fallback.provider)
                return self.fallback._chat(messages, **kwargs)
            return None

    def explain(self, item_name: str, result: Dict, language: str = "English") -> Optional[str]:
        if not self.available:
            return None
        similar = "\n".join(
            f"- {m['name']} ({m.get('color') or '?'} {m.get('material') or ''} {m.get('style') or ''}, "
            f"similarity {m['similarity']:.0%})" for m in result.get("similar_items", [])[:5]) or "- none"
        prompt = OptimizedPrompts.format_prompt(
            OptimizedPrompts.PROMPT_EXPLANATION, item_name=item_name, score=result["redundancy_score"],
            recommendation=result["recommendation"], saturation=round(result.get("category_saturation", 0)),
            contribution=round(result.get("outfit_contribution", 0)), similar_items=similar, language=language)
        response = self._chat([{"role": "system", "content": OptimizedPrompts.SYSTEM_ANALYZER},
                               {"role": "user", "content": prompt}], max_tokens=400, temperature=0.4)
        return response.choices[0].message.content.strip() if response else None

    def summarize(self, headline: str, reasons: List[str], actions: List[str]) -> Optional[str]:
        if not self.available:
            return None
        lines = (["<decision>", headline, "Raisons:"] + [f"- {r}" for r in reasons]
                 + ["Actions:"] + [f"- {a}" for a in actions] + ["</decision>", ""])
        prompt = ("\n".join(lines) + "Rédige ce verdict pour l'utilisateur en 3 à 4 phrases, en français, ton direct "
                  "et bienveillant. Ne change pas le verdict et n'invente aucun article.")
        response = self._chat([{"role": "system", "content": OptimizedPrompts.SYSTEM_ANALYZER},
                               {"role": "user", "content": prompt}], max_tokens=300, temperature=0.4)
        return response.choices[0].message.content.strip() if response else None

    def run_agent(self, user_message: str, wardrobe: List[Dict], engine, max_iterations: int = 8,
                  on_step=None, image: Optional[str] = None, profile: Optional[Dict] = None,
                  history: Optional[List[Dict]] = None, actions=None) -> Dict:
        """Tool-use loop: GPT picks the tools; the photo (data URL) goes to GPT vision directly"""
        if not self.available:
            raise RuntimeError(self.error or "OpenAI unavailable")
        import openai
        from agent_tools import build_tools

        steps: List[Dict] = []

        def record(tool: str, tool_input: Dict, output, cards: Optional[Dict] = None) -> str:
            text = json.dumps(output, default=str, ensure_ascii=False)
            step = {"n": len(steps) + 1, "tool": tool, "input": tool_input, "output_preview": text[:500], "cards": cards}
            steps.append(step)
            if on_step:
                on_step(step)
            return text

        tools = build_tools(engine, wardrobe, record, profile, actions)
        wardrobe_text = "\n".join(
            f"- {i.get('name')} ({i.get('category')}, {i.get('color')}, {i.get('material')}, {i.get('style')})"
            for i in wardrobe) or "- (vide)"
        content = [{"type": "text", "text": OptimizedPrompts.agent_user_message(wardrobe_text, user_message, bool(history))}]
        if image:
            url = image if image.startswith("data:") else f"data:image/jpeg;base64,{image}"
            content.append({"type": "image_url", "image_url": {"url": url, "detail": "low"}})
        messages = [{"role": "system", "content": OptimizedPrompts.agent_system(profile)}]
        for turn in (history or [])[-10:]:  # earlier turns of the conversation (text only)
            messages.append({"role": turn["role"], "content": turn["content"]})
        messages.append({"role": "user", "content": content})

        start = time.time()
        usage = {"input_tokens": 0, "output_tokens": 0}
        answer, finish = "", None
        for iteration in range(max_iterations):
            try:
                # Grounding: the first turn must look at the data (models otherwise answer from general
                # knowledge and invent pieces); afterwards the model decides when it has enough
                response = self.client.chat.completions.create(
                    model=self.model, messages=messages, tools=[spec for _, spec in tools.values()],
                    tool_choice="required" if iteration == 0 else "auto", temperature=0.2, max_tokens=1500)
            except openai.APIError as e:
                self.handle_api_error(e)
                if self.fallback and self.fallback.available:
                    logger.warning("Falling back from %s to %s", self.provider, self.fallback.provider)
                    return self.fallback.run_agent(
                        user_message, wardrobe, engine, max_iterations, on_step, image, profile, history, actions)
                raise
            usage["input_tokens"] += response.usage.prompt_tokens
            usage["output_tokens"] += response.usage.completion_tokens
            choice = response.choices[0]
            finish = choice.finish_reason
            message = choice.message
            if not message.tool_calls:
                answer = (message.content or "").strip()
                break
            messages.append({"role": "assistant", "content": message.content,
                             "tool_calls": [tc.model_dump() for tc in message.tool_calls]})
            for call in message.tool_calls:
                func = tools.get(call.function.name, (None,))[0]
                try:
                    args = json.loads(call.function.arguments or "{}")
                    output = func(**args) if func else json.dumps({"error": f"unknown tool {call.function.name}"})
                except Exception as e:  # bad arguments -> the model can retry
                    output = json.dumps({"error": f"{type(e).__name__}: {e}"})
                messages.append({"role": "tool", "tool_call_id": call.id, "content": output})
        else:
            answer = answer or "Nombre maximal d'étapes atteint."

        return {"answer": answer, "stop_reason": finish, "model": self.model, "steps": steps,
                "iterations": len(steps), "usage": usage,
                "execution_time_ms": round((time.time() - start) * 1000, 1)}


def make_llm_client(provider: str, claude_key: str, claude_model: str, openai_key: str, openai_model: str,
                    effort: str, agent_effort: str, max_tokens: int, enabled: bool):
    """LLM_PROVIDER = openai | claude | auto (auto: OpenAI when its key is set, else Claude)"""
    from llm_client import ClaudeClient

    provider = (provider or "auto").lower()
    if provider == "auto":
        provider = "openai" if openai_key else "claude"
    if provider == "openai":
        primary = OpenAIClient(openai_key, openai_model, enabled=enabled)
        if os.getenv("GROQ_API_KEY"):
            primary.fallback = OpenAIClient(
                os.getenv("GROQ_API_KEY", ""),
                os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
                enabled=enabled,
                base_url=os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
            )
        return primary
    return ClaudeClient(claude_key, claude_model, effort=effort, agent_effort=agent_effort,
                        max_tokens=max_tokens, enabled=enabled)
