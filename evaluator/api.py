"""Service HTTP de l'évaluateur (port 8090), à part : il n'ajoute aucune route aux services des autres agents.

    python -m uvicorn evaluator.api:app --host 127.0.0.1 --port 8090

POST /api/evaluator/run   {"agents": ["stylist", "outfit"] | "all", "judge": true}
    L'appelante envoie son propre jeton (Authorization: Bearer ...) : l'évaluation tourne sur SA garde-robe. Sans jeton,
    le compte de test (orchestrator/.env.test) est utilisé. Réponse : état completed / input-required / failed + rapport.
GET  /api/evaluator/agents  les agents évaluables.
"""
from __future__ import annotations

from typing import Optional, Union

from fastapi import FastAPI, Header
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from . import config, evaluator_agent
from .adapters import AGENTS, Reply
from .session import Session

app = FastAPI(title="DressMe Evaluator Agent")


class RunRequest(BaseModel):
    agents: Union[list[str], str] = Field(default="all")
    judge: bool = True


def _run(body: RunRequest, authorization: Optional[str]) -> dict:
    agents = [body.agents] if isinstance(body.agents, str) else body.agents
    token = (authorization or "").removeprefix("Bearer ").strip()
    deps = None
    if token:
        session = Session.__new__(Session)             # jeton de l'appelante : pas de connexion du compte de test
        session.token, session.user_id, session.bo1 = token, "", config.URLS["bo1"]
        try:
            session.wardrobe()
        except RuntimeError as error:
            return {"state": "input-required", "message": str(error)}
        deps = evaluator_agent.Deps(token=token, wardrobe=session.wardrobe, diff=session.diff, restore=session.restore,
                                    foreign_probe=session.foreign_probe)
    return evaluator_agent.run(agents, use_judge=body.judge, deps=deps)


@app.post("/api/evaluator/run")
async def evaluator_run(body: RunRequest, authorization: Optional[str] = Header(None)) -> dict:
    return await run_in_threadpool(_run, body, authorization)


@app.get("/api/evaluator/agents")
def evaluator_agents() -> dict:
    return {"agents": {name: {"label": spec.label, "kind": spec.kind, "service": spec.service, "path": spec.path}
                       for name, spec in AGENTS.items()}}
