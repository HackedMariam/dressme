"""Official A2A transport for the BO3 wardrobe-gap agent."""

from __future__ import annotations

import json
import os
from typing import Any

from a2a.helpers import get_message_text, new_task_from_user_message, new_text_message, new_text_part
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill, TaskState
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from .memory import AgentMemory
from .tools import GapAgentTools


def _goal_for_trip(capsule: dict[str, Any]) -> str:
    activities = {
        str(value).lower().replace("_", "-")
        for value in capsule.get("activities", [])
    }
    if activities & {"business-meeting", "conference", "work"}:
        return "winter_work"
    if activities & {"wedding", "gala", "formal-dinner", "ceremony"}:
        return "formal_event"
    return "daily_basics"


class GapAgentExecutor(AgentExecutor):
    """Execute one deterministic BO3 ranking through the A2A task protocol."""

    def __init__(self, memory: AgentMemory) -> None:
        self.memory = memory

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        task = context.current_task or new_task_from_user_message(context.message)
        if context.current_task is None:
            await event_queue.enqueue_event(task)
        updater = TaskUpdater(
            event_queue=event_queue, task_id=task.id, context_id=task.context_id
        )
        await updater.update_status(
            state=TaskState.TASK_STATE_WORKING,
            message=new_text_message("Gap Agent analysing the trip capsule"),
        )

        try:
            request = json.loads(get_message_text(context.message) or "{}")
            user_id = str(request["user_id"])
            capsule = request["capsule"]
            if not isinstance(capsule, dict):
                raise ValueError("capsule must be an object")
            goal = str(request.get("goal") or _goal_for_trip(capsule))
            conversation_id = str(request.get("conversation_id") or task.context_id)
            result = GapAgentTools(self.memory, user_id, conversation_id).rank_gaps(goal)
            payload = {"goal": goal, "findings": result, "source": "bo3-gap-agent"}
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            payload = {"error": f"Invalid A2A gap request: {exc}"}

        await updater.add_artifact(
            parts=[new_text_part(text=json.dumps(payload, ensure_ascii=False), media_type="application/json")]
        )
        await updater.update_status(
            state=TaskState.TASK_STATE_COMPLETED,
            message=new_text_message("Gap analysis completed"),
        )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise NotImplementedError("Gap analysis cancellation is not supported.")


def build_a2a_app(memory: AgentMemory, public_url: str = "http://127.0.0.1:8001/a2a") -> Starlette:
    public_url = public_url.rstrip("/") + "/"
    skill = AgentSkill(
        id="wardrobe_gap_analysis",
        name="Wardrobe gap analysis",
        description="Ranks wardrobe gaps for a trip or occasion using BO3 coverage rules and XGBoost.",
        input_modes=["text/plain"],
        output_modes=["application/json"],
        tags=["dressme", "wardrobe", "gaps", "trip"],
        examples=['{"user_id":"demo_user","capsule":{"activities":["business-meeting"]}}'],
    )
    card = AgentCard(
        name="DressMe Wardrobe Gap Agent",
        description="Deterministic wardrobe coverage and gap ranking agent.",
        version="1.0.0",
        default_input_modes=["text/plain"],
        default_output_modes=["application/json"],
        capabilities=AgentCapabilities(streaming=False),
        supported_interfaces=[
            AgentInterface(protocol_binding="JSONRPC", url=public_url, protocol_version="1.0")
        ],
        skills=[skill],
    )
    handler = DefaultRequestHandler(
        agent_executor=GapAgentExecutor(memory),
        task_store=InMemoryTaskStore(),
        agent_card=card,
    )
    routes = create_agent_card_routes(card)
    routes.extend(create_jsonrpc_routes(handler, "/"))
    app = Starlette(routes=routes)
    expected_key = os.getenv("GAP_AGENT_A2A_KEY", "")

    if expected_key:
        class A2AKeyMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                if request.headers.get("X-A2A-Key") != expected_key:
                    return JSONResponse({"detail": "Invalid A2A credentials"}, status_code=401)
                return await call_next(request)

        app.add_middleware(A2AKeyMiddleware)
    return app
