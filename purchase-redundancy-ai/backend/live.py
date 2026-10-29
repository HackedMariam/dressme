"""
Real-time updates over WebSocket (/ws/live).

Each connection belongs to one user (guest or JWT via ?token=). The API publishes small events
("analysis.created", "wardrobe.changed") and every open tab of that user refreshes itself -
e.g. the dashboard updates live when an analysis is made from the phone.

publish() is thread-safe: sync endpoints run in FastAPI's thread pool, so events are handed to the
event loop with run_coroutine_threadsafe.
"""

import asyncio
import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, Optional, Set

from fastapi import WebSocket

logger = logging.getLogger(__name__)

MAX_CONNECTIONS_PER_USER = 10


class LiveHub:
    def __init__(self):
        self.connections: Dict[str, Set[WebSocket]] = defaultdict(set)
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.sent = 0

    def bind_loop(self) -> None:
        self.loop = asyncio.get_running_loop()

    @property
    def count(self) -> int:
        return sum(len(c) for c in self.connections.values())

    async def connect(self, websocket: WebSocket, user_id: str) -> bool:
        if len(self.connections[user_id]) >= MAX_CONNECTIONS_PER_USER:
            await websocket.close(code=1008, reason="too many connections")
            return False
        await websocket.accept()
        self.connections[user_id].add(websocket)
        return True

    def disconnect(self, websocket: WebSocket, user_id: str) -> None:
        self.connections[user_id].discard(websocket)
        if not self.connections[user_id]:
            self.connections.pop(user_id, None)

    async def _broadcast(self, user_id: str, message: str) -> None:
        for websocket in list(self.connections.get(user_id, ())):
            try:
                await websocket.send_text(message)
                self.sent += 1
            except Exception:  # closed tab - forget it
                self.disconnect(websocket, user_id)

    def publish(self, user_id: str, event_type: str, data: Optional[Dict] = None) -> None:
        if not self.connections.get(user_id) or self.loop is None or self.loop.is_closed():
            return
        message = json.dumps({"type": event_type, "data": data or {},
                              "at": datetime.now(timezone.utc).isoformat(timespec="seconds")},
                             ensure_ascii=False, default=str)
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is self.loop:
            self.loop.create_task(self._broadcast(user_id, message))
        else:
            asyncio.run_coroutine_threadsafe(self._broadcast(user_id, message), self.loop)
