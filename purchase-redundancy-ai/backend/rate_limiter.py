"""
Rate limiting - fixed one-minute windows per client IP and bucket, shared through Redis when the
cache uses it (several API workers then share the counters), in memory otherwise.

Buckets:
  auth    login / register                          (brute-force protection)
  heavy   analyses, agent, image processing, LLM    (CPU / paid API calls)
  default everything else
Static files and health checks are never limited.
"""

import json
import logging
import time
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

WINDOW = 60  # seconds

HEAVY_PATHS = ("/analyze", "/agent", "/camera-capture", "/upload-image", "/wardrobe/sample")
AUTH_PATHS = ("/auth/login", "/auth/register")
EXEMPT_PREFIXES = ("/images/", "/uploads/", "/health", "/metrics", "/docs", "/openapi.json", "/redoc", "/ws/")


def bucket_for(method: str, path: str) -> Optional[str]:
    if method == "OPTIONS" or path.startswith(EXEMPT_PREFIXES):
        return None
    if path.startswith(AUTH_PATHS):
        return "auth"
    if method == "POST" and (path.startswith(HEAVY_PATHS) or (path == "/wardrobe")):
        return "heavy"
    return "default"


class RateLimiter:
    def __init__(self, cache, limits: Dict[str, int], enabled: bool = True):
        self.cache = cache
        self.limits = limits
        self.enabled = enabled
        self.rejected = 0

    def hit(self, client: str, bucket: str) -> Tuple[bool, int, int, int]:
        """-> (allowed, limit, remaining, seconds until the window resets)"""
        limit = self.limits[bucket]
        window_start = int(time.time()) // WINDOW * WINDOW
        reset = window_start + WINDOW - int(time.time())
        try:
            count = self.cache.incr(f"pr:rl:{bucket}:{client}:{window_start}", WINDOW + 5)
        except Exception as e:  # a broken cache must not take the API down
            logger.warning(f"Rate limiter disabled for this request: {e}")
            return True, limit, limit, reset
        return count <= limit, limit, max(0, limit - count), reset


class RateLimitMiddleware:
    """Pure ASGI middleware (keeps streaming responses streaming)"""

    def __init__(self, app, limiter_getter):
        self.app = app
        self.limiter_getter = limiter_getter  # read lazily: the limiter is created in the app lifespan

    async def __call__(self, scope, receive, send):
        limiter: Optional[RateLimiter] = self.limiter_getter()
        if scope["type"] != "http" or limiter is None or not limiter.enabled:
            return await self.app(scope, receive, send)

        bucket = bucket_for(scope["method"], scope["path"])
        if bucket is None:
            return await self.app(scope, receive, send)

        client = (scope.get("client") or ("unknown", 0))[0]
        allowed, limit, remaining, reset = limiter.hit(client, bucket)
        headers = [(b"x-ratelimit-limit", str(limit).encode()),
                   (b"x-ratelimit-remaining", str(remaining).encode()),
                   (b"x-ratelimit-reset", str(reset).encode())]

        if not allowed:
            limiter.rejected += 1
            logger.warning(f"Rate limit exceeded: {client} {bucket} ({limit}/min) on {scope['path']}")
            body = json.dumps({"detail": f"Trop de requêtes - limite de {limit} par minute. Réessayez dans {reset} s."}).encode()
            await send({"type": "http.response.start", "status": 429,
                        "headers": headers + [(b"retry-after", str(reset).encode()),
                                              (b"content-type", b"application/json"),
                                              (b"content-length", str(len(body)).encode())]})
            await send({"type": "http.response.body", "body": body})
            return

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                message["headers"] = list(message.get("headers", [])) + headers
            await send(message)

        await self.app(scope, receive, send_with_headers)
