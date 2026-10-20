"""In-process sliding-window rate limiter.

Fine for a single API container. For multiple replicas, move the counters to
Redis or put a limiter at the gateway.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_seconds: int = 60):
        self.limit = max(limit, 1)
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> tuple[bool, int]:
        now = time.monotonic()
        cutoff = now - self.window_seconds

        with self._lock:
            events = self._events[key]
            while events and events[0] < cutoff:
                events.popleft()

            if len(events) >= self.limit:
                retry_after = max(
                    1, int(self.window_seconds - (now - events[0])) + 1
                )
                return False, retry_after

            events.append(now)
            return True, 0
