"""HTTP API exposing the BO3 gap agent to the React frontend.

Run from "DressMe UI Blueprint/" (port 8001: BO1 uses 8000, and the Vite proxy sends /api/bo3 here):
    python -m uvicorn api:app --app-dir backend --port 8001

Every route except /health and /goals needs the user's Supabase session (Authorization: Bearer <token>);
the wardrobe, feedback and conversations are then that user's. Without Supabase configured, BO3 serves
the shared demo user and the sample wardrobe.
"""

import hashlib
import logging
import os
import socket
import threading
import time
from typing import Any, Literal

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from agent.coverage import GOALS, compute_coverage, get_requirement
from agent.gap_agent import GapAgent, interpret_gaps_with_gpt
from agent.learning import learning_status, reset_model, retrain
from agent.memory import AgentMemory
from agent.tools import GapAgentTools, load_profile, load_wardrobe, score_candidates
from agent.wardrobe_source import source_info
from agent.web_images import search_images
from xgboost_ranker import FEATURES

# This network cannot reach Supabase over IPv6: without this every new connection waits ~40 s.
_getaddrinfo = socket.getaddrinfo
socket.getaddrinfo = lambda *a, **k: [r for r in _getaddrinfo(*a, **k) if r[0] == socket.AF_INET] or _getaddrinfo(*a, **k)

DEMO_USER = "demo_user"
_TOKEN_TTL = 300                      # seconds a verified token is trusted
_tokens: dict[str, tuple[float, str]] = {}
_tokens_lock = threading.Lock()


def _supabase_key() -> str | None:
    return os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SERVICE_KEY")


def current_user(authorization: str | None = Header(None)) -> str:
    """Supabase user id from the session token. Without Supabase configured: the shared demo user."""
    url, key = os.getenv("SUPABASE_URL"), _supabase_key()
    if not (url and key):
        return DEMO_USER
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Not signed in")
    token = authorization.split(" ", 1)[1].strip()
    cache_key = hashlib.sha256(token.encode()).hexdigest()
    now = time.time()
    with _tokens_lock:
        hit = _tokens.get(cache_key)
        if hit and hit[0] > now:
            return hit[1]
    try:
        reply = httpx.get(f"{url.rstrip('/')}/auth/v1/user",
                          headers={"apikey": key, "Authorization": f"Bearer {token}"}, timeout=10)
    except httpx.HTTPError as error:
        raise HTTPException(503, "Cannot reach Supabase to verify the session") from error
    if reply.status_code != 200 or not reply.json().get("id"):
        raise HTTPException(401, "Session expired, please sign in again")
    user_id = reply.json()["id"]
    with _tokens_lock:
        _tokens[cache_key] = (now + _TOKEN_TTL, user_id)
    return user_id


app = FastAPI(title="DressMe BO3 Gap Agent API")
memory = AgentMemory()


def _warm_up() -> None:
    """Load the embedding model once at startup: the first ranking otherwise takes ~10 s longer."""
    try:
        GapAgentTools(memory, DEMO_USER).rank_gaps("winter_work")
    except Exception:
        logging.getLogger("dressme.bo3").warning("warm-up failed", exc_info=True)


threading.Thread(target=_warm_up, daemon=True).start()


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    history: list[ChatTurn] = []
    conversation_id: str | None = None


class FeedbackRequest(BaseModel):
    goal: str
    candidate_id: str
    # 3 = "I need this", 0 = "Not relevant", None = remove the label.
    relevance: Literal[0, 3] | None


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/bo3/goals")
def goals() -> list[dict[str, str]]:
    return [{"id": goal_id, "label": goal["label"], "season": goal["season"]} for goal_id, goal in GOALS.items()]


@app.get("/api/bo3/context")
def context(user_id: str = Depends(current_user)) -> dict[str, Any]:
    wardrobe, profile = load_wardrobe(user_id), load_profile(user_id)
    return {"profile": profile, "profile_source": profile.get("profile_source"),
            "item_count": len(wardrobe), "wardrobe_source": source_info(user_id)}


@app.get("/api/bo3/gaps")
def gaps(goal: str = "winter_work", interpret: bool = True, user_id: str = Depends(current_user)) -> dict[str, Any]:
    """Pipeline (rules -> features -> XGBoost) with optional GPT-4 interpretation."""
    if goal not in GOALS:
        raise HTTPException(404, f"Unknown goal {goal!r}.")
    result = GapAgentTools(memory, user_id).rank_gaps(goal)
    if interpret:
        # The GPT interpretation is optional: if it fails, the ranked gaps are still returned.
        try:
            interpretation = interpret_gaps_with_gpt(result)
        except Exception:
            logging.getLogger("dressme.bo3").exception("gap interpretation failed")
            interpretation = None
        if interpretation:
            result["stylist_interpretation"] = interpretation
    return result


@app.get("/api/bo3/gaps/{candidate_id}/images")
def gap_images(candidate_id: str, goal: str = "winter_work", limit: int = 3,
               user_id: str = Depends(current_user)) -> dict[str, Any]:
    """Web photos of a missing piece. A separate route from /gaps: each search takes about a second, and the
    ranking must not wait for six of them. The search text comes from the rules, never from the browser."""
    if goal not in GOALS:
        raise HTTPException(404, f"Unknown goal {goal!r}.")
    department = load_profile(user_id).get("department")
    try:
        requirement = get_requirement(goal, candidate_id, department)
    except KeyError:
        raise HTTPException(404, f"{candidate_id!r} is not a requirement of {goal!r}.") from None
    return {"candidate_id": candidate_id, "piece": requirement["description"], "department": department,
            **search_images(requirement["description"], limit, department)}


@app.post("/api/bo3/feedback")
def feedback(request: FeedbackRequest, user_id: str = Depends(current_user)) -> dict[str, Any]:
    if request.goal not in GOALS:
        raise HTTPException(404, f"Unknown goal {request.goal!r}.")
    if request.relevance is None:
        memory.delete_feedback(user_id, request.goal, request.candidate_id)
        return learning_status(memory, user_id)

    # Store the features the server computes, not values sent by the browser.
    wardrobe, profile = load_wardrobe(user_id), load_profile(user_id)
    candidates = compute_coverage(wardrobe, request.goal, profile.get("department"))["candidates"]
    scored = {c["candidate_id"]: c for c in score_candidates(request.goal, candidates, wardrobe, profile)}
    if request.candidate_id not in scored:
        raise HTTPException(404, f"{request.candidate_id!r} is not a current gap for {request.goal!r}.")
    features = {name: scored[request.candidate_id][name] for name in FEATURES}
    memory.set_feedback(user_id, request.goal, request.candidate_id, features, request.relevance)
    return learning_status(memory, user_id)


@app.get("/api/bo3/learning")
def learning(user_id: str = Depends(current_user)) -> dict[str, Any]:
    return learning_status(memory, user_id)


@app.post("/api/bo3/retrain")
def retrain_ranker(user_id: str = Depends(current_user)) -> dict[str, Any]:
    try:
        return {"training": retrain(memory, user_id), "status": learning_status(memory, user_id)}
    except ValueError as error:
        raise HTTPException(400, str(error)) from error


@app.post("/api/bo3/reset-model")
def reset_ranker(user_id: str = Depends(current_user)) -> dict[str, Any]:
    """Back to the synthetic demo model for THIS user only: each user has their own retrained model."""
    reset_model(user_id)
    return learning_status(memory, user_id)


@app.post("/api/bo3/chat")
def chat(request: ChatRequest, user_id: str = Depends(current_user)) -> dict[str, Any]:
    conversation_id = request.conversation_id or memory.start_conversation(user_id)
    tools = GapAgentTools(memory, user_id, conversation_id)
    try:
        result = GapAgent(tools).run(request.message, [turn.model_dump() for turn in request.history])
    except RuntimeError as error:
        raise HTTPException(503, str(error)) from error

    memory.add_message(conversation_id, "user", request.message)
    memory.add_message(conversation_id, "assistant", result.answer)
    return {"conversation_id": conversation_id, "answer": result.answer,
            "ranking": result.ranking, "trace": result.trace, "items": result.items}
