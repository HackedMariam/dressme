"""A2A (Agent2Agent) for DressMe: a server (Agent Card + JSON-RPC) and a client, shared by every agent service."""
from .client import A2AClient, A2AError
from .server import AgentCall, AgentResult, Skill, build_card, build_router

__all__ = ["A2AClient", "A2AError", "AgentCall", "AgentResult", "Skill", "build_card", "build_router"]
