"""FastAPI layer for the existing DressMe Trip Agent.

The agent, tools, schemas, and OR-Tools optimizer are reused as-is. This module
only adds HTTP session management, request validation, and response shaping.
"""

from __future__ import annotations

import logging
import os
import re
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field
import requests

if __package__ in {None, ""}:  # allow `python backend/main.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packing_backend.trip_agent.agent import TripAgent
from packing_backend.trip_agent.config import get_api_key, llm_enabled
from packing_backend.trip_agent.logging_utils import configure_logging, log_event
from packing_backend.trip_agent.schemas import AgentResponse
from packing_backend.trip_agent.wardrobe import BO1WardrobeProvider

logger = logging.getLogger("dressme.api")


# ----------------------------------------------------------------------
# Request models
# ----------------------------------------------------------------------
class CreateTripRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["text", "structured"] = "text"
    text: str | None = None
    trip: dict[str, Any] | None = None
    session_id: str | None = None
    # Accepted for orchestrator contract compatibility. BO1 is always queried
    # directly with the caller's token; client-supplied wardrobe is never trusted.
    wardrobe_items: list[dict[str, Any]] | None = None
    user_id: str | None = None


class MessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)


class UpdateTripRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    updates: dict[str, Any]
    reoptimize: bool = True


class ChecklistUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    packed: bool = True


class OptimizeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_weight_g: int | None = Field(default=None, gt=0, le=50000)
    max_candidates_per_day: int = Field(default=500, ge=10, le=5000)
    time_limit_seconds: int = Field(default=30, ge=1, le=120)
    random_seed: int = 42


class WeatherRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    force_refresh: bool = False


# ----------------------------------------------------------------------
# In-memory session storage (temporary development storage)
# ----------------------------------------------------------------------
@dataclass
class TripSession:
    agent: TripAgent
    user_id: str
    lock: threading.Lock = field(default_factory=threading.Lock)


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, TripSession] = {}
        self._lock = threading.Lock()

    def add(self, agent: TripAgent, user_id: str) -> TripSession:
        session = TripSession(agent=agent, user_id=user_id)
        with self._lock:
            self._sessions[agent.state.session_id] = session
        return session

    def get(self, session_id: str) -> TripSession:
        with self._lock:
            session = self._sessions.get(session_id)
        if session is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"Trip session '{session_id}' was not found. It may have been "
                    "cleared by a backend restart; start a new trip."
                ),
            )
        return session

    def delete(self, session_id: str) -> bool:
        with self._lock:
            return self._sessions.pop(session_id, None) is not None

    def count(self) -> int:
        with self._lock:
            return len(self._sessions)


# ----------------------------------------------------------------------
# Optional mock Gap Agent
# ----------------------------------------------------------------------
def mock_gap_checker(capsule: dict[str, Any]) -> dict[str, Any]:
    """Simple deterministic stand-in for the teammate's future Gap Agent."""
    items = capsule.get("selected_items") or []
    days = capsule.get("days") or []

    categories: dict[str, int] = {}
    types: set[str] = set()
    styles: set[str] = set()
    for item in items:
        category = str(item.get("category", "unknown"))
        categories[category] = categories.get(category, 0) + 1
        if item.get("item_type"):
            types.add(str(item["item_type"]).lower())
        if item.get("style"):
            styles.add(str(item["style"]).lower())

    gaps: list[dict[str, Any]] = []

    def add_gap(
        category: str,
        severity: str,
        suggestion: str,
    ) -> None:
        gaps.append(
            {
                "type": "category_gap",
                "category": category,
                "severity": severity,
                "suggestion": suggestion,
            }
        )

    if not categories.get("shoes"):
        add_gap("shoes", "high", "Add at least one versatile pair of shoes.")
    if not categories.get("outerwear") and any(
        day.get("weather") in {"rainy", "windy", "cold"} for day in days
    ):
        add_gap(
            "outerwear",
            "high",
            "Weather suggests a jacket, coat, or raincoat would improve coverage.",
        )
    if not categories.get("accessory"):
        add_gap(
            "accessory",
            "low",
            "Consider a hat, scarf, belt, or bag to extend outfit variety.",
        )

    formal_days = [
        day
        for day in days
        if str(day.get("required_style", "")).lower() == "formal"
    ]
    if formal_days and not (
        {"formal-dress", "blouse", "shirt"} & types or "formal" in styles
    ):
        gaps.append(
            {
                "type": "occasion_gap",
                "severity": "high",
                "category": "formalwear",
                "suggestion": (
                    f"{len(formal_days)} formal day(s) are planned; add a clearly "
                    "formal top/dress or verify the formal outfit."
                ),
            }
        )

    return {
        "provider": "mock_gap_agent",
        "status": "ok",
        "capsule_days": len(days),
        "selected_categories": categories,
        "gaps": gaps,
        "summary": (
            "No obvious mock gaps detected."
            if not gaps
            else f"{len(gaps)} potential wardrobe gap(s) detected by the mock agent."
        ),
    }


# ----------------------------------------------------------------------
# Response shaping
# ----------------------------------------------------------------------
def _weather_payload(agent: TripAgent) -> dict[str, Any] | None:
    if agent.state.weather is None:
        return None
    return agent.state.weather.model_dump(mode="json")


def _capsule_payload(agent: TripAgent) -> dict[str, Any] | None:
    if agent.state.capsule is None:
        return None
    payload = agent.state.capsule.model_dump(mode="json")
    payload["checklist"] = agent.state.capsule.checklist.summary()
    return payload


def _checklist_payload(agent: TripAgent) -> dict[str, Any] | None:
    if agent.state.checklist is None:
        return None
    return agent.state.checklist.summary()


def _state_payload(agent: TripAgent) -> dict[str, Any]:
    state = agent.state
    return {
        "session_id": state.session_id,
        "status": state.status,
        "user_request": state.user_request,
        "trip_details": (
            state.trip_details.model_dump(mode="json")
            if state.trip_details
            else None
        ),
        "weather": _weather_payload(agent),
        "daily_requirements": [
            requirement.model_dump(mode="json")
            for requirement in state.daily_requirements
        ],
        "optimization_status": (
            state.optimization_result.get("status")
            if state.optimization_result
            else None
        ),
        "optimization_runs": state.optimization_runs,
        "capsule": _capsule_payload(agent),
        "checklist": _checklist_payload(agent),
        "missing_info": state.missing_info,
        "clarification_question": state.clarification_question,
        "suggestions": state.suggestions,
        "missing_items": [item.model_dump(mode="json") for item in state.missing_items],
        "can_repeat_outfits": state.can_repeat_outfits,
        "errors": state.errors,
        "messages": [message.model_dump(mode="json") for message in state.messages],
    }


def _response_payload(
    agent: TripAgent,
    response: AgentResponse,
) -> dict[str, Any]:
    payload = response.to_json_dict()
    payload["session_id"] = agent.state.session_id
    payload["weather"] = _weather_payload(agent)
    payload["capsule"] = _capsule_payload(agent)
    payload["checklist"] = _checklist_payload(agent)
    payload["optimization_status"] = (
        agent.state.optimization_result.get("status")
        if agent.state.optimization_result
        else None
    )
    payload["optimization_runs"] = agent.state.optimization_runs
    payload["clarification_question"] = agent.state.clarification_question
    return payload


# ----------------------------------------------------------------------
# Application factory
# ----------------------------------------------------------------------
# The dev frontend may be opened as localhost, 127.0.0.1, 0.0.0.0 or this machine's LAN address, on any
# port. The service only listens on 127.0.0.1 and authenticates with bearer tokens (no cookies), so these
# origins are safe to accept; anything else is still refused.
DEV_ORIGIN_REGEX = (
    r"^https?://(localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1\]|10(\.\d{1,3}){3}|192\.168(\.\d{1,3}){2}"
    r"|172\.(1[6-9]|2\d|3[01])(\.\d{1,3}){2})(:\d+)?$"
)


def create_app(
    use_llm: bool | None = None,
    allow_weather_network: bool | None = None,
    gap_checker: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    bo1_url: str | None = None,
    wardrobe_provider_factory: Callable[[list[dict[str, Any]]], Any] = BO1WardrobeProvider,
) -> FastAPI:
    configure_logging(verbose=os.getenv("TRIP_AGENT_VERBOSE", "0") == "1")
    app = FastAPI(
        title="DressMe Trip Agent API",
        version="1.0.0",
        description=(
            "REST API for the existing DressMe Trip Agent, OR-Tools optimizer, "
            "capsule, checklist, and optional Gap Agent."
        ),
    )

    app.state.store = SessionStore()
    app.state.use_llm = llm_enabled() if use_llm is None else use_llm
    app.state.allow_weather_network = (
        os.getenv("TRIP_AGENT_ALLOW_WEATHER", "1").strip().lower()
        not in {"0", "false", "no", "off"}
        if allow_weather_network is None
        else allow_weather_network
    )
    if gap_checker is None and os.getenv("GAP_AGENT_A2A_ENABLED", "1").strip().lower() not in {
        "0", "false", "no", "off"
    }:
        from .app.a2a_gap_client import A2AGapChecker

        gap_checker = A2AGapChecker()
    app.state.gap_checker = gap_checker
    app.state.bo1_url = (bo1_url or os.getenv("BO1_URL", "http://127.0.0.1:8000")).rstrip("/")

    def bo1_get(path: str, authorization: str | None) -> Any:
        headers = {"Authorization": authorization} if authorization else {}
        try:
            response = requests.get(app.state.bo1_url + path, headers=headers, timeout=10)
        except requests.RequestException as exc:
            raise HTTPException(503, "Wardrobe service is unavailable") from exc
        if response.status_code in (401, 403):
            raise HTTPException(401, "Please sign in again")
        if not response.ok:
            raise HTTPException(503, "Wardrobe service failed")
        try:
            return response.json()
        except ValueError as exc:
            raise HTTPException(503, "Invalid response from wardrobe service") from exc

    origins = {
        "http://localhost:8443",
        "http://127.0.0.1:8443",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    }
    for origin in os.getenv("CORS_ORIGINS", "").split(","):
        origin = origin.strip()
        if origin:
            origins.add(origin)

    @app.middleware("http")
    async def request_logging(request: Request, call_next):
        started = time.perf_counter()
        try:
            if request.url.path.startswith("/api/trips") and request.method != "OPTIONS":
                authorization = request.headers.get("authorization")
                if authorization and not authorization.lower().startswith("bearer "):
                    raise HTTPException(401, "Invalid authorization header")
                identity = await run_in_threadpool(bo1_get, "/api/me", authorization)
                if not isinstance(identity, dict) or not identity.get("id"):
                    raise HTTPException(503, "Wardrobe identity is unavailable")
                if authorization and identity["id"] == "local":
                    raise HTTPException(503, "BO1 must enable authentication to verify your session")
                request.state.user_id = str(identity["id"])
                request.state.authorization = authorization
                match = re.match(r"^/api/trips/([^/]+)", request.url.path)
                if match and app.state.store.get(match.group(1)).user_id != request.state.user_id:
                    raise HTTPException(404, "Trip session not found")
            response = await call_next(request)
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
        except Exception:
            log_event(
                logger,
                "http_request_failed",
                method=request.method,
                path=request.url.path,
                duration_ms=round((time.perf_counter() - started) * 1000, 1),
                level=logging.ERROR,
            )
            raise
        log_event(
            logger,
            "http_request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=round((time.perf_counter() - started) * 1000, 1),
        )
        return response

    app.add_middleware(
        CORSMiddleware,
        allow_origins=sorted(origins),
        allow_origin_regex=DEV_ORIGIN_REGEX,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def log_rejected_origin(request: Request, call_next):
        # Outermost: sees the preflight answer. A refused origin shows up in the browser only as
        # "Failed to fetch", so say which origin it was.
        response = await call_next(request)
        if request.method == "OPTIONS" and response.status_code == 400 and request.headers.get("origin"):
            log_event(logger, "cors_origin_rejected", level=logging.WARNING, origin=request.headers["origin"])
        return response

    @app.exception_handler(Exception)
    async def unhandled_exception(request: Request, exc: Exception):
        logger.exception("Unhandled API error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": f"Internal server error: {type(exc).__name__}"},
        )

    def new_agent(wardrobe_items: list[dict[str, Any]]) -> TripAgent:
        return TripAgent(
            user_id=request.state.user_id if hasattr(request.state, "user_id") else "local",
            use_llm=app.state.use_llm,
            allow_weather_network=app.state.allow_weather_network,
            gap_checker=app.state.gap_checker,
            wardrobe_provider=wardrobe_provider_factory(wardrobe_items),
        )

    def session_or_404(session_id: str) -> TripSession:
        return app.state.store.get(session_id)

    def refresh_wardrobe(session: TripSession, request: Request) -> None:
        items = bo1_get("/api/items", request.state.authorization)
        if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
            raise HTTPException(503, "Invalid wardrobe response")
        if not items:
            raise HTTPException(422, "Your wardrobe is empty. Add clothing before planning a trip.")
        if len(items) > 500:
            raise HTTPException(422, "Packing currently supports up to 500 wardrobe items.")
        provider = wardrobe_provider_factory(items)
        previous = session.agent.tools.wardrobe_provider
        if not previous.load()[0].equals(provider.load()[0]):
            state = session.agent.state
            session.agent.tools.wardrobe_provider = provider
            state.wardrobe_items = []
            state.compatibility_data = []
            state.optimization_result = None
            state.capsule = None
            state.checklist = None
            state.suggestions = []
            state.missing_items = []
            state.can_repeat_outfits = False

    # ------------------------------------------------------------------
    # Meta / health
    # ------------------------------------------------------------------
    @app.get("/")
    def root() -> dict[str, Any]:
        return {
            "service": "DressMe Trip Agent API",
            "docs": "/docs",
            "health": "/api/health",
        }

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "sessions": app.state.store.count(),
            "llm_configured": bool(get_api_key()),
            "llm_enabled": bool(app.state.use_llm and get_api_key()),
            "weather_network_enabled": bool(app.state.allow_weather_network),
            "gap_agent": "configured" if app.state.gap_checker else "unavailable",
        }

    # ------------------------------------------------------------------
    # Trip lifecycle
    # ------------------------------------------------------------------
    @app.post("/api/trips")
    def create_trip(body: CreateTripRequest, request: Request) -> dict[str, Any]:
        if body.session_id:
            session = session_or_404(body.session_id)
            if session.user_id != request.state.user_id:
                raise HTTPException(404, "Trip session not found")
            agent = session.agent
        else:
            items = bo1_get("/api/items", request.state.authorization)
            if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
                raise HTTPException(503, "Invalid wardrobe response")
            if not items:
                raise HTTPException(422, "Your wardrobe is empty. Add clothing before planning a trip.")
            if len(items) > 500:
                raise HTTPException(422, "Packing currently supports up to 500 wardrobe items.")
            session = app.state.store.add(new_agent(items), request.state.user_id)
            agent = session.agent

        with session.lock:
            try:
                if body.session_id:
                    refresh_wardrobe(session, request)
                if body.mode == "structured":
                    if not body.trip:
                        raise HTTPException(
                            status_code=422,
                            detail="mode=structured requires a non-empty trip object",
                        )
                    response = agent.handle_structured(body.trip)
                else:
                    text = (body.text or "").strip()
                    if not text:
                        raise HTTPException(
                            status_code=422,
                            detail="mode=text requires non-empty text",
                        )
                    response = agent.handle(text)
            except HTTPException:
                raise
            except Exception as exc:
                logger.exception("Trip creation failed")
                raise HTTPException(
                    status_code=500,
                    detail=f"Trip Agent failed: {type(exc).__name__}: {exc}",
                ) from exc
            return _response_payload(agent, response)

    @app.post("/api/trips/{session_id}/messages")
    def send_message(session_id: str, body: MessageRequest, request: Request) -> dict[str, Any]:
        session = session_or_404(session_id)
        with session.lock:
            try:
                refresh_wardrobe(session, request)
                response = session.agent.handle(body.text)
            except HTTPException:
                raise
            except Exception as exc:
                logger.exception("Trip continuation failed")
                raise HTTPException(
                    status_code=500,
                    detail=f"Trip Agent failed: {type(exc).__name__}: {exc}",
                ) from exc
            return _response_payload(session.agent, response)

    @app.get("/api/trips/{session_id}")
    def get_trip(session_id: str) -> dict[str, Any]:
        session = session_or_404(session_id)
        with session.lock:
            return _state_payload(session.agent)

    @app.delete("/api/trips/{session_id}")
    def delete_trip(session_id: str) -> dict[str, Any]:
        deleted = app.state.store.delete(session_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Trip session not found")
        return {"ok": True, "session_id": session_id}

    # ------------------------------------------------------------------
    # Agent operations
    # ------------------------------------------------------------------
    @app.post("/api/trips/{session_id}/weather")
    def get_weather(session_id: str, body: WeatherRequest) -> dict[str, Any]:
        session = session_or_404(session_id)
        with session.lock:
            result = session.agent.tools.execute(
                "get_weather",
                {"force_refresh": body.force_refresh},
            )
            if not result.get("ok"):
                raise HTTPException(status_code=409, detail=result)
            return {
                "session_id": session_id,
                "result": result,
                "state": _state_payload(session.agent),
            }

    @app.post("/api/trips/{session_id}/requirements")
    def get_requirements(session_id: str) -> dict[str, Any]:
        session = session_or_404(session_id)
        with session.lock:
            if session.agent.state.daily_requirements:
                result = {
                    "ok": True,
                    "cached": True,
                    "requirements": [
                        requirement.model_dump(mode="json")
                        for requirement in session.agent.state.daily_requirements
                    ],
                }
            else:
                result = session.agent.tools.execute(
                    "get_activity_requirements", {}
                )
            if not result.get("ok"):
                raise HTTPException(status_code=409, detail=result)
            return {
                "session_id": session_id,
                "result": result,
                "state": _state_payload(session.agent),
            }

    @app.post("/api/trips/{session_id}/optimize")
    def optimize(session_id: str, body: OptimizeRequest, request: Request) -> dict[str, Any]:
        session = session_or_404(session_id)
        with session.lock:
            refresh_wardrobe(session, request)
            arguments = body.model_dump(exclude_none=True)
            result = session.agent.tools.execute("optimize_trip", arguments)
            if not result.get("ok"):
                raise HTTPException(status_code=409, detail=result)
            if result.get("status") in {"OPTIMAL", "FEASIBLE"}:
                session.agent.tools.execute("generate_checklist", {})
            elif result.get("status") == "INFEASIBLE":
                session.agent.tools.execute("suggest_alternatives", {})
            return {
                "session_id": session_id,
                "result": result,
                "state": _state_payload(session.agent),
            }

    @app.post("/api/trips/{session_id}/suggest-alternatives")
    def suggest_alternatives(session_id: str) -> dict[str, Any]:
        session = session_or_404(session_id)
        with session.lock:
            result = session.agent.tools.execute("suggest_alternatives", {})
            if not result.get("ok"):
                raise HTTPException(status_code=409, detail=result)
            return {"session_id": session_id, "result": result}

    # ------------------------------------------------------------------
    # Capsule / checklist
    # ------------------------------------------------------------------
    @app.get("/api/trips/{session_id}/capsule")
    def get_capsule(session_id: str) -> dict[str, Any]:
        session = session_or_404(session_id)
        with session.lock:
            capsule = session.agent.state.capsule
            if capsule is None:
                raise HTTPException(
                    status_code=404,
                    detail={
                        "message": "Capsule is not ready yet.",
                        "status": session.agent.state.status,
                        "missing_info": session.agent.state.missing_info,
                        "suggestions": session.agent.state.suggestions,
                    },
                )
            return {
                "session_id": session_id,
                "capsule": _capsule_payload(session.agent),
            }

    @app.get("/api/trips/{session_id}/checklist")
    def get_checklist(session_id: str) -> dict[str, Any]:
        session = session_or_404(session_id)
        with session.lock:
            checklist = session.agent.state.checklist
            if checklist is None:
                raise HTTPException(
                    status_code=404,
                    detail="Checklist is not ready yet.",
                )
            return {
                "session_id": session_id,
                "checklist": _checklist_payload(session.agent),
            }

    @app.patch("/api/trips/{session_id}/checklist/{item_id}")
    def update_checklist(
        session_id: str,
        item_id: str,
        body: ChecklistUpdateRequest,
    ) -> dict[str, Any]:
        session = session_or_404(session_id)
        with session.lock:
            response = session.agent.mark_packed(item_id, body.packed)
            if response.checklist is None:
                raise HTTPException(
                    status_code=404,
                    detail={"message": "Checklist is not ready.", "errors": response.errors},
                )
            return {
                "session_id": session_id,
                "message": response.message,
                "checklist": _checklist_payload(session.agent),
                "optimization_runs": session.agent.state.optimization_runs,
                "optimizer_rerun": False,
            }

    # ------------------------------------------------------------------
    # Trip editing / optional gap analysis
    # ------------------------------------------------------------------
    @app.patch("/api/trips/{session_id}")
    def update_trip(session_id: str, body: UpdateTripRequest, request: Request) -> dict[str, Any]:
        session = session_or_404(session_id)
        with session.lock:
            try:
                refresh_wardrobe(session, request)
                response = session.agent.update_trip(
                    body.updates,
                    reoptimize=body.reoptimize,
                )
            except HTTPException:
                raise
            except Exception as exc:
                logger.exception("Trip update failed")
                raise HTTPException(
                    status_code=500,
                    detail=f"Trip update failed: {type(exc).__name__}: {exc}",
                ) from exc
            return _response_payload(session.agent, response)

    @app.post("/api/trips/{session_id}/gap-analysis")
    def gap_analysis(session_id: str) -> dict[str, Any]:
        session = session_or_404(session_id)
        with session.lock:
            if session.agent.state.capsule is None:
                raise HTTPException(
                    status_code=409,
                    detail="A successful trip capsule is required for gap analysis.",
                )
            result = session.agent.tools.execute("check_gaps", {})
            if not result.get("ok"):
                raise HTTPException(status_code=409, detail=result)
            return {
                "session_id": session_id,
                "gap_analysis": result,
                "capsule": _capsule_payload(session.agent),
            }

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=os.getenv("BACKEND_HOST", "127.0.0.1"),
        port=int(os.getenv("BACKEND_PORT", "8020")),
    )
