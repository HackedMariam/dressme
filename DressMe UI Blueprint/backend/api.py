"""HTTP API exposing the BO3 gap agent to the React frontend.

Run from the repository root:
    backend/.venv/Scripts/python.exe -m uvicorn api:app --app-dir backend --port 8000
"""

from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from agent.coverage import GOALS, compute_coverage
from agent.gap_agent import GapAgent
from agent.learning import learning_status, reset_model, retrain
from agent.memory import AgentMemory
from agent.tools import GapAgentTools, load_profile, load_wardrobe, score_candidates
from agent.wardrobe_source import SOURCE_INFO
from agent.gap_interpreter import interpret_gaps_with_gpt
from xgboost_ranker import FEATURES

USER_ID = "demo_user"

app = FastAPI(title="DressMe BO3 Gap Agent API")
memory = AgentMemory()


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
def context() -> dict[str, Any]:
    wardrobe = load_wardrobe()
    return {"profile": load_profile(), "item_count": len(wardrobe), "wardrobe_source": SOURCE_INFO}


@app.get("/api/bo3/gaps")
def gaps(goal: str = "winter_work", interpret: bool = True) -> dict[str, Any]:
    """Pipeline (rules -> features -> XGBoost) with optional GPT-4 interpretation."""
    if goal not in GOALS:
        raise HTTPException(404, f"Unknown goal {goal!r}.")
    result = GapAgentTools(memory, USER_ID).rank_gaps(goal)
    if interpret:
        interpretation = interpret_gaps_with_gpt(result)
        if interpretation:
            result["stylist_interpretation"] = interpretation
    return result


@app.post("/api/bo3/feedback")
def feedback(request: FeedbackRequest) -> dict[str, Any]:
    if request.goal not in GOALS:
        raise HTTPException(404, f"Unknown goal {request.goal!r}.")
    if request.relevance is None:
        memory.delete_feedback(USER_ID, request.goal, request.candidate_id)
        return learning_status(memory, USER_ID)

    # Store the features the server computes, not values sent by the browser.
    wardrobe, profile = load_wardrobe(), load_profile()
    candidates = compute_coverage(wardrobe, request.goal)["candidates"]
    scored = {c["candidate_id"]: c for c in score_candidates(request.goal, candidates, wardrobe, profile)}
    if request.candidate_id not in scored:
        raise HTTPException(404, f"{request.candidate_id!r} is not a current gap for {request.goal!r}.")
    features = {name: scored[request.candidate_id][name] for name in FEATURES}
    memory.set_feedback(USER_ID, request.goal, request.candidate_id, features, request.relevance)
    return learning_status(memory, USER_ID)


@app.get("/api/bo3/learning")
def learning() -> dict[str, Any]:
    return learning_status(memory, USER_ID)


@app.post("/api/bo3/retrain")
def retrain_ranker() -> dict[str, Any]:
    try:
        return {"training": retrain(memory, USER_ID), "status": learning_status(memory, USER_ID)}
    except ValueError as error:
        raise HTTPException(400, str(error)) from error


@app.post("/api/bo3/reset-model")
def reset_ranker() -> dict[str, Any]:
    reset_model()
    return learning_status(memory, USER_ID)


@app.post("/api/bo3/chat")
def chat(request: ChatRequest) -> dict[str, Any]:
    conversation_id = request.conversation_id or memory.start_conversation(USER_ID)
    tools = GapAgentTools(memory, USER_ID, conversation_id)
    try:
        result = GapAgent(tools).run(request.message, [turn.model_dump() for turn in request.history])
    except RuntimeError as error:
        raise HTTPException(503, str(error)) from error

    memory.add_message(conversation_id, "user", request.message)
    memory.add_message(conversation_id, "assistant", result.answer)
    return {
        "conversation_id": conversation_id,
        "answer": result.answer,
        "ranking": result.ranking,
        "trace": result.trace,
    }
