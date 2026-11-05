"""The decision agent of "Should I buy this?": fine-tuned Qwen, driving the purchase tools.

    item + wardrobe ->  Qwen agent (LangGraph tool loop, agent_kit)  ->  JSON verdict  ->  GPT stylist interpreter

Qwen is the autonomous agent: it decides which tools to call (analyze_item, find_similar_items,
check_outfit_compatibility, analyze_wardrobe_gaps, predict_purchase_ml, calculate_purchase_value), reads their
results and ends with a JSON verdict {decision: BUY | CONSIDER | SKIP, score, matching_item_ids, reasons}. The tools
are Python functions computed on the real wardrobe: they are authoritative (Qwen's own arguments never replace the
measured values). GPT is NOT part of this file: it only rewrites the verdict as stylist advice, afterwards.

The model is Qwen/Qwen2.5-3B-Instruct + the LoRA adapter meriemgharbi123/dressme_qwen3b_lora, loaded from Hugging Face
(HF_TOKEN in .env). No Ollama. Backends (QWEN_BACKEND): "local" (transformers + peft in this process), "hf_api"
(Hugging Face InferenceClient, optionally on a dedicated endpoint: HF_ENDPOINT_URL), "auto" (endpoint, else local when
peft is installed, else the Hugging Face API) or "off". Without HF_TOKEN, or when the model cannot run (no GPU/RAM, no
network), `run_decision_agent` returns None and the caller falls back to the deterministic evaluation.
"""
from __future__ import annotations

import importlib.util
import json
import logging
import os
import re
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1] if (Path(__file__).resolve().parent.name == "smart_purchasing") else Path(__file__).resolve().parent
if str(ROOT) not in sys.path:          # agent_kit/ sits at the root of the repository
    sys.path.insert(0, str(ROOT))

from agent_kit import run_loop  # noqa: E402

log = logging.getLogger("dressme.decision_agent")

BASE_MODEL = os.getenv("QWEN_BASE_MODEL", "Qwen/Qwen2.5-3B-Instruct")
LORA_ADAPTER = os.getenv("QWEN_LORA_ADAPTER", "meriemgharbi123/dressme_qwen3b_lora")
MAX_ROUNDS = 6
DECISIONS = {"BUY": "BUY", "CONSIDER": "CONSIDER", "SKIP": "SKIP", "DON'T BUY": "SKIP", "DONT BUY": "SKIP"}

SYSTEM = (
    "You are the DressMe purchase decision agent. A shopper shows an item and asks whether to buy it. Decide by calling "
    "your tools, never from guesses: analyze_item, find_similar_items, check_outfit_compatibility, "
    "analyze_wardrobe_gaps, predict_purchase_ml and calculate_purchase_value. Read what they return, then answer with "
    'ONLY a JSON object: {"decision": "BUY" | "CONSIDER" | "SKIP", "score": <0-100>, "matching_item_ids": [<ids of '
    'owned pieces that make outfits with it>], "reasons": [<short factual reasons based on the tool results>]}.'
)


# ------------------------------------------------------------------------------------------------ the model
class QwenBackend:
    """Fine-tuned Qwen on Hugging Face, behind one `chat(messages, tools)` call."""

    def __init__(self, mode: Optional[str] = None, token: Optional[str] = None) -> None:
        self.requested = (mode or os.getenv("QWEN_BACKEND", "auto")).strip().lower()
        self.token = token if token is not None else os.getenv("HF_TOKEN")
        self.mode = self._pick()
        self._local: Any = None
        self._client: Any = None

    def _pick(self) -> Optional[str]:
        if self.requested == "off" or not self.token:
            return None                                   # no token: the deterministic evaluation answers
        if self.requested in ("local", "hf_api"):
            return self.requested
        if os.getenv("HF_ENDPOINT_URL"):
            return "hf_api"
        if importlib.util.find_spec("peft") and importlib.util.find_spec("torch"):
            return "local"
        return "hf_api"

    @property
    def available(self) -> bool:
        return self.mode is not None

    @property
    def label(self) -> str:
        return f"{BASE_MODEL} + {LORA_ADAPTER} ({self.mode})"

    # -------------------------------------------------------------------------------- Hugging Face API
    def _chat_api(self, messages: List[dict], tools: List[dict]) -> dict:
        if self._client is None:
            from huggingface_hub import InferenceClient
            self._client = InferenceClient(model=os.getenv("HF_ENDPOINT_URL") or LORA_ADAPTER, token=self.token, timeout=90)
        message = self._client.chat_completion(messages=messages, tools=tools, max_tokens=700, temperature=0.1).choices[0].message
        calls = []
        for call in getattr(message, "tool_calls", None) or []:
            arguments = call.function.arguments
            calls.append({"name": call.function.name, "arguments": arguments if isinstance(arguments, dict) else json.loads(arguments or "{}")})
        return {"content": message.content or "", "tool_calls": calls}

    # -------------------------------------------------------------------------------- local transformers + peft
    def _load_local(self) -> Any:
        if self._local is None:
            import torch
            from peft import PeftModel
            from transformers import AutoModelForCausalLM, AutoTokenizer

            tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL, token=self.token)
            cuda = torch.cuda.is_available()
            model = AutoModelForCausalLM.from_pretrained(
                BASE_MODEL, token=self.token, torch_dtype=torch.float16 if cuda else torch.bfloat16,
                device_map="auto" if cuda else None, low_cpu_mem_usage=True)
            model = PeftModel.from_pretrained(model, LORA_ADAPTER, token=self.token)
            model.eval()
            self._local = (tokenizer, model)
        return self._local

    def _chat_local(self, messages: List[dict], tools: List[dict]) -> dict:
        import torch

        tokenizer, model = self._load_local()
        prompt = tokenizer.apply_chat_template(_for_template(messages), tools=tools, add_generation_prompt=True, tokenize=False)
        inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
        with torch.no_grad():
            output = model.generate(**inputs, max_new_tokens=600, do_sample=False)
        text = tokenizer.decode(output[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
        return parse_generation(text)

    def chat(self, messages: List[dict], tools: List[dict]) -> dict:
        return self._chat_local(messages, tools) if self.mode == "local" else self._chat_api(messages, tools)


def _for_template(messages: List[dict]) -> List[dict]:
    """Qwen's chat template wants tool-call arguments as objects, the OpenAI format carries them as JSON text."""
    out = []
    for message in messages:
        if message.get("tool_calls"):
            calls = [{"type": "function", "function": {"name": c["function"]["name"],
                                                        "arguments": json.loads(c["function"]["arguments"] or "{}")}}
                     for c in message["tool_calls"]]
            out.append({"role": "assistant", "content": message.get("content") or "", "tool_calls": calls})
        else:
            out.append({"role": message["role"], "content": message.get("content") or ""})
    return out


TOOL_CALL = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)


def parse_generation(text: str) -> dict:
    """Qwen writes tool calls as <tool_call>{"name": ..., "arguments": {...}}</tool_call>."""
    calls = []
    for block in TOOL_CALL.findall(text):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        if isinstance(data, dict) and data.get("name"):
            arguments = data.get("arguments") or {}
            calls.append({"name": str(data["name"]), "arguments": arguments if isinstance(arguments, dict) else {}})
    return {"content": TOOL_CALL.sub("", text).strip(), "tool_calls": calls}


def _as_message(reply: dict) -> Any:
    """The reply as an OpenAI-style message, which is what the shared tool loop reads."""
    calls = []
    for call in reply.get("tool_calls") or []:
        arguments = json.dumps(call["arguments"])
        function = SimpleNamespace(name=call["name"], arguments=arguments)
        entry = SimpleNamespace(id=f"call_{uuid.uuid4().hex[:8]}", function=function)
        entry.model_dump = (lambda e=entry, f=function: {"id": e.id, "type": "function",
                                                         "function": {"name": f.name, "arguments": f.arguments}})
        calls.append(entry)
    return SimpleNamespace(content=reply.get("content") or "", tool_calls=calls or None)


# ------------------------------------------------------------------------------------------------ the tools
class PurchaseToolbox:
    """The purchase tools bound to one candidate and one wardrobe. Results are cached and authoritative."""

    def __init__(self, *, candidate, wardrobe, price: float, budget: float, occasion: str, tools: SimpleNamespace) -> None:
        self.candidate, self.wardrobe, self.price, self.budget, self.occasion = candidate, wardrobe, price, budget, occasion
        self.t = tools                      # the real functions: find_similar_items, check_outfit_compatibility, ...
        self.called: List[str] = []
        self._sims = self._compat = self._gap = self._ml = self._val = None

    # evidence, computed once
    @property
    def sims(self):
        if self._sims is None:
            self._sims = self.t.find_similar_items(self.candidate, self.wardrobe, top_k=3)
        return self._sims

    @property
    def redundancy_pct(self) -> float:
        return round((self.sims[0].similarity_score if self.sims else 0.0) * 100.0, 1)

    def compat(self, occasion: Optional[str] = None):
        if self._compat is None:
            self._compat = self.t.check_outfit_compatibility(self.candidate, self.wardrobe, target_occasion=occasion or self.occasion)
        return self._compat

    @property
    def gap(self):
        if self._gap is None:
            self._gap = self.t.analyze_wardrobe_gaps(self.candidate, self.wardrobe)
        return self._gap

    @property
    def penalty(self) -> float:
        b, p = self.budget, self.price
        return min(25.0, round(((p - b) / b) * 20.0, 2)) if b > 0 and p > b else 0.0

    @property
    def versatility(self) -> float:
        return min(100.0, 50.0 + self.compat()["compatible_count"] * 15.0)

    @property
    def ml(self) -> dict:
        if self._ml is None:
            self._ml = self.t.predict_purchase_ml(
                outfit_compatibility=self.compat()["average_score"], wardrobe_gap=self.gap.gap_fill_score,
                redundancy=self.redundancy_pct, versatility=self.versatility, style_match=80.0, budget_penalty=self.penalty)
        return self._ml

    @property
    def value(self):
        if self._val is None:
            self._val = self.t.calculate_purchase_value(
                outfit_compatibility_score=self.compat()["average_score"], wardrobe_gap_score=self.gap.gap_fill_score,
                versatility_score=self.versatility, personal_style_score=80.0, redundancy_score=self.redundancy_pct,
                price=self.price, budget=self.budget, ml_decision=self.ml["ml_decision"], ml_confidence=self.ml["confidence"])
        return self._val

    @property
    def paired_item_ids(self) -> List[str]:
        ids: List[str] = []
        for combo in self.compat().get("combinations", [])[:3]:
            for g in combo.paired_garments:
                if g.id not in ids:
                    ids.append(g.id)
        return ids

    # what the model sees
    def call(self, name: str, args: Dict[str, Any]) -> str:
        self.called.append(name)
        c = self.candidate
        if name == "analyze_item":
            out = {"name": c.name, "category": c.category, "color": c.color, "occasion": self.occasion,
                   "style": list(c.style or []), "seasons": list(c.seasons or []), "price": self.price, "budget": self.budget}
        elif name == "find_similar_items":
            out = [{"item_id": s.garment.id, "name": s.garment.name, "similarity_percent": round(s.similarity_score * 100, 1)}
                   for s in self.sims]
        elif name == "check_outfit_compatibility":
            compat = self.compat(args.get("occasion") if isinstance(args.get("occasion"), str) else None)
            out = {"compatible_count": compat["compatible_count"], "average_score": round(compat["average_score"], 1),
                   "outfits": [{"paired_item_ids": [g.id for g in combo.paired_garments],
                                "paired_names": [g.name for g in combo.paired_garments],
                                "score": round(combo.compatibility_score, 1)} for combo in compat.get("combinations", [])[:3]]}
        elif name == "analyze_wardrobe_gaps":
            out = {"gap_fill_score": self.gap.gap_fill_score}
        elif name == "predict_purchase_ml":
            out = {"ml_decision": self.ml["ml_decision"], "confidence": round(self.ml["confidence"], 3)}
        elif name == "calculate_purchase_value":
            out = {"overall_score": round(self.value.overall_score, 1), "decision": self.value.decision.value}
        else:
            out = {"error": f"Unknown tool {name}"}
        return json.dumps(out, default=str)

    def complete(self) -> None:
        """Make sure every piece of evidence exists (the page shows it), whatever Qwen chose to call."""
        _ = (self.sims, self.compat(), self.gap, self.ml, self.value)


# ------------------------------------------------------------------------------------------------ the agent
def validate_verdict(raw: str, known_ids: set) -> Optional[dict]:
    """Qwen's final JSON, checked: a known decision, a score in 0..100, real wardrobe ids and short reasons."""
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        match = re.search(r"\{.*\}", raw or "", re.DOTALL)
        try:
            data = json.loads(match.group(0)) if match else None
        except ValueError:
            data = None
    if not isinstance(data, dict):
        return None
    decision = DECISIONS.get(str(data.get("decision", "")).strip().upper())
    try:
        score = max(0.0, min(100.0, float(data.get("score"))))
    except (TypeError, ValueError):
        return None
    if decision is None:
        return None
    ids = [i for i in (data.get("matching_item_ids") or []) if isinstance(i, str) and i in known_ids]
    reasons = [" ".join(str(r).split())[:240] for r in (data.get("reasons") or []) if str(r).strip()][:6]
    return {"decision": decision, "score": round(score, 1), "matching_item_ids": ids, "reasons": reasons}


def run_decision_agent(box: PurchaseToolbox, backend: QwenBackend, user_query: str, tools_schema: List[dict]) -> Optional[dict]:
    """Run Qwen as the tool-calling agent; returns its validated verdict, or None when it cannot run or answers badly."""
    if backend is None or not backend.available:
        return None
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": f"The shopper asks: \"{user_query}\". Item: {box.candidate.category}, {box.candidate.color}. "
                                            f"Price {box.price}, budget {box.budget}."}]
    try:
        final, outcome = run_loop(
            messages=messages, call_llm=lambda msgs: _as_message(backend.chat(msgs, tools_schema)),
            run_tool=lambda name, args: box.call(name, args), max_rounds=MAX_ROUNDS)
    except Exception:
        log.exception("Qwen decision agent failed")
        return None
    if outcome != "answer":
        return None
    verdict = validate_verdict(final or "", {g.id for g in box.wardrobe})
    if verdict is None:
        log.warning("Qwen answered without a usable verdict")
    return verdict
