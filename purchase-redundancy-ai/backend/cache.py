"""
Cache - Redis when REDIS_URL is set and reachable, otherwise an in-process TTL + LRU cache.
Both backends share the same API, so the app works identically with or without Redis.
Values are JSON-serialized (numpy arrays/scalars are converted).
"""

import hashlib
import json
import logging
import threading
import time
from collections import OrderedDict
from functools import wraps
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


def _json_default(value):
    if hasattr(value, "tolist"):  # numpy arrays and scalars
        return value.tolist()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    raise TypeError(f"Not JSON serializable: {type(value).__name__}")


def make_key(prefix: str, *parts: Any) -> str:
    """Stable key: same arguments -> same key, whatever their order in dicts"""
    raw = json.dumps(parts, sort_keys=True, default=_json_default, ensure_ascii=False)
    return f"pr:{prefix}:{hashlib.sha1(raw.encode()).hexdigest()}"


class MemoryCache:
    backend = "memory"

    def __init__(self, max_items: int = 2048):
        self._data: "OrderedDict[str, tuple]" = OrderedDict()
        self._lock = threading.Lock()
        self.max_items = max_items

    def get(self, key: str) -> Optional[str]:
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            expires, value = entry
            if expires < time.monotonic():
                del self._data[key]
                return None
            self._data.move_to_end(key)
            return value

    def set(self, key: str, value: str, ttl: int) -> None:
        with self._lock:
            self._data[key] = (time.monotonic() + ttl, value)
            self._data.move_to_end(key)
            while len(self._data) > self.max_items:
                self._data.popitem(last=False)

    def delete_prefix(self, prefix: str) -> int:
        with self._lock:
            keys = [k for k in self._data if k.startswith(prefix)]
            for k in keys:
                del self._data[k]
            return len(keys)

    def incr(self, key: str, ttl: int) -> int:
        """Counter that expires `ttl` seconds after its creation (used by the rate limiter)"""
        with self._lock:
            now = time.monotonic()
            expires, value = self._data.get(key, (0, 0))
            if expires < now:
                expires, value = now + ttl, 0
            self._data[key] = (expires, value + 1)
            return value + 1

    def ping(self) -> bool:
        return True


class RedisCache:
    backend = "redis"

    def __init__(self, url: str):
        import redis

        self.client = redis.Redis.from_url(url, socket_connect_timeout=2, socket_timeout=2, decode_responses=True)
        self.client.ping()

    def get(self, key: str) -> Optional[str]:
        return self.client.get(key)

    def set(self, key: str, value: str, ttl: int) -> None:
        self.client.set(key, value, ex=ttl)

    def delete_prefix(self, prefix: str) -> int:
        keys = list(self.client.scan_iter(match=f"{prefix}*", count=500))
        return self.client.delete(*keys) if keys else 0

    def incr(self, key: str, ttl: int) -> int:
        pipe = self.client.pipeline()
        pipe.incr(key)
        pipe.expire(key, ttl, nx=True)
        return int(pipe.execute()[0])

    def ping(self) -> bool:
        try:
            return bool(self.client.ping())
        except Exception:
            return False


class Cache:
    """Facade: picks the backend, counts hits/misses, never lets a cache failure break a request"""

    def __init__(self, redis_url: str = "", default_ttl: int = 300):
        self.default_ttl = default_ttl
        self.hits = self.misses = self.errors = 0
        self.store = MemoryCache()
        if redis_url:
            try:
                self.store = RedisCache(redis_url)
                logger.info("Cache: Redis connected")
            except Exception as e:
                logger.warning(f"Cache: Redis unavailable ({e}) - using the in-memory cache")

    @property
    def backend(self) -> str:
        return self.store.backend

    def get(self, key: str) -> Any:
        try:
            raw = self.store.get(key)
        except Exception as e:
            self.errors += 1
            logger.warning(f"Cache read failed: {e}")
            return None
        if raw is None:
            self.misses += 1
            return None
        self.hits += 1
        return json.loads(raw)

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        try:
            self.store.set(key, json.dumps(value, default=_json_default, ensure_ascii=False), ttl or self.default_ttl)
        except Exception as e:
            self.errors += 1
            logger.warning(f"Cache write failed: {e}")

    def invalidate(self, prefix: str) -> int:
        try:
            return self.store.delete_prefix(f"pr:{prefix}")
        except Exception as e:
            self.errors += 1
            logger.warning(f"Cache invalidation failed: {e}")
            return 0

    def incr(self, key: str, ttl: int) -> int:
        return self.store.incr(key, ttl)

    def cached(self, prefix: str, ttl: Optional[int] = None) -> Callable:
        """Decorator - caches a function's JSON-serializable result by its arguments"""
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                key = make_key(prefix, args, kwargs)
                value = self.get(key)
                if value is None:
                    value = func(*args, **kwargs)
                    self.set(key, value, ttl)
                return value
            return wrapper
        return decorator

    def stats(self) -> dict:
        total = self.hits + self.misses
        return {"backend": self.backend, "hits": self.hits, "misses": self.misses, "errors": self.errors,
                "hit_rate": round(self.hits / total, 3) if total else None, "healthy": self.store.ping()}
