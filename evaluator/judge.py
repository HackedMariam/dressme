"""LLM-juge (Ollama qwen2.5:3b, température 0, JSON) : seulement la PERTINENCE et l'UTILITÉ de la réponse.

Le juge n'est jamais appelé quand le code a déjà détecté un échec, et son verdict ne peut pas effacer cet échec.
Grille notée de 1 à 5 + une justification courte. Si Ollama ne répond pas : « non jugé », jamais une note inventée.
"""
from __future__ import annotations

import json

from . import config
from .net import call

GRID = ("relevance", "usefulness")
SYSTEM = (
    "You are a strict reviewer of a fashion assistant's answer. You only judge two things, each from 1 to 5.\n"
    "relevance: does the answer address what the user asked (5 = exactly, 3 = partly, 1 = off topic)?\n"
    "usefulness: could the user act on it (5 = concrete and complete, 3 = vague, 1 = useless or empty)?\n"
    "Do not judge facts you cannot check. Do not reward length. Answer with JSON only: "
    '{"relevance": <1-5>, "usefulness": <1-5>, "justification": "<one short sentence>"}.'
)
MAX_ANSWER_CHARS = 1800


def clamp(value) -> int | None:
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        return None
    return number if 1 <= number <= 5 else None


def parse(raw: str) -> dict | None:
    """Notes valides (1 à 5) et justification courte, sinon None : une réponse hors grille n'est pas un verdict."""
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    scores = {key: clamp(data.get(key)) for key in GRID}
    if any(score is None for score in scores.values()):
        return None
    return {**scores, "justification": str(data.get("justification", "")).strip()[:240]}


def judge(question: str, answer: str, hint: str = "", timeout: float = 120.0) -> dict | None:
    prompt = f"User request: {question}\n"
    if hint:
        prompt += f"What a good answer should do: {hint}\n"
    prompt += f"Assistant answer:\n{answer[:MAX_ANSWER_CHARS]}"
    body = {"model": config.JUDGE_MODEL, "stream": False, "format": "json", "keep_alive": "30m",
            "options": {"temperature": 0, "seed": 0},
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]}
    status, payload, error, _ = call("POST", config.URLS["ollama"] + "/api/chat", body=body, timeout=timeout)
    if error or status != 200 or not isinstance(payload, dict):
        return None
    return parse((payload.get("message") or {}).get("content", ""))
