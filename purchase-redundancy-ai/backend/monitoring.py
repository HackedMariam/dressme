"""
Monitoring - in-process request metrics (count, errors, latency percentiles per route),
exported as JSON (/analytics/system) and in the Prometheus text format (/metrics).
Metrics reset when the process restarts; business analytics are persisted in the database.
"""

import threading
import time
from collections import defaultdict, deque
from typing import Callable, Dict, List, Optional

LATENCY_SAMPLES = 1000  # per route


def _percentile(sorted_values: List[float], q: float) -> Optional[float]:
    if not sorted_values:
        return None
    return round(sorted_values[min(len(sorted_values) - 1, int(len(sorted_values) * q))], 1)


class RouteStats:
    __slots__ = ("count", "client_errors", "server_errors", "total_ms", "latencies")

    def __init__(self):
        self.count = self.client_errors = self.server_errors = 0
        self.total_ms = 0.0
        self.latencies = deque(maxlen=LATENCY_SAMPLES)


class RequestMetrics:
    def __init__(self):
        self.started = time.time()
        self.routes: Dict[str, RouteStats] = defaultdict(RouteStats)
        self.recent = deque(maxlen=20000)  # request timestamps (throughput)
        self.status_counts: Dict[int, int] = defaultdict(int)
        self._lock = threading.Lock()

    def record(self, method: str, route: str, status: int, duration_ms: float) -> None:
        with self._lock:
            stats = self.routes[f"{method} {route}"]
            stats.count += 1
            stats.total_ms += duration_ms
            stats.latencies.append(duration_ms)
            if 400 <= status < 500:
                stats.client_errors += 1
            elif status >= 500:
                stats.server_errors += 1
            self.status_counts[status] += 1
            self.recent.append(time.time())

    def summary(self) -> Dict:
        with self._lock:
            now = time.time()
            routes = []
            for name, s in self.routes.items():
                lat = sorted(s.latencies)
                routes.append({
                    "route": name, "count": s.count,
                    "errors_4xx": s.client_errors, "errors_5xx": s.server_errors,
                    "avg_ms": round(s.total_ms / s.count, 1) if s.count else None,
                    "p50_ms": _percentile(lat, 0.5), "p95_ms": _percentile(lat, 0.95), "p99_ms": _percentile(lat, 0.99),
                })
            total = sum(s.count for s in self.routes.values())
            server_errors = sum(s.server_errors for s in self.routes.values())
            return {
                "uptime_s": round(now - self.started),
                "requests": total,
                "requests_last_minute": sum(1 for t in self.recent if t >= now - 60),
                "error_rate_5xx": round(server_errors / total, 4) if total else 0.0,
                "status_codes": dict(sorted(self.status_counts.items())),
                "routes": sorted(routes, key=lambda r: -r["count"]),
            }

    def prometheus(self, gauges: Dict[str, float]) -> str:
        """Prometheus text exposition format 0.0.4"""
        lines = ["# HELP pr_requests_total HTTP requests by route and outcome", "# TYPE pr_requests_total counter"]
        with self._lock:
            snapshot = [(name, s.count, s.client_errors, s.server_errors, s.total_ms, sorted(s.latencies))
                        for name, s in self.routes.items()]
        for name, count, e4, e5, total_ms, _ in snapshot:
            method, route = name.split(" ", 1)
            labels = f'method="{method}",route="{route}"'
            lines.append(f'pr_requests_total{{{labels},outcome="ok"}} {count - e4 - e5}')
            lines.append(f'pr_requests_total{{{labels},outcome="client_error"}} {e4}')
            lines.append(f'pr_requests_total{{{labels},outcome="server_error"}} {e5}')
        lines += ["# HELP pr_request_duration_ms Request latency (last 1000 requests per route)",
                  "# TYPE pr_request_duration_ms summary"]
        for name, count, _, _, total_ms, lat in snapshot:
            method, route = name.split(" ", 1)
            labels = f'method="{method}",route="{route}"'
            for q in (0.5, 0.95, 0.99):
                value = _percentile(lat, q)
                if value is not None:
                    lines.append(f'pr_request_duration_ms{{{labels},quantile="{q}"}} {value}')
            lines.append(f"pr_request_duration_ms_sum{{{labels}}} {round(total_ms, 1)}")
            lines.append(f"pr_request_duration_ms_count{{{labels}}} {count}")
        for gauge, value in gauges.items():
            lines += [f"# TYPE pr_{gauge} gauge", f"pr_{gauge} {value}"]
        lines.append(f"pr_uptime_seconds {round(time.time() - self.started)}")
        return "\n".join(lines) + "\n"


class MetricsMiddleware:
    """Pure ASGI middleware: request id, structured access log, metrics. Route = the matched path
    template (/wardrobe/{item_id}), so ids never explode the number of series."""

    def __init__(self, app, metrics_getter: Callable[[], Optional[RequestMetrics]], logger, request_id_var):
        self.app = app
        self.metrics_getter = metrics_getter
        self.logger = logger
        self.request_id_var = request_id_var

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        import uuid

        incoming = dict(scope.get("headers") or []).get(b"x-request-id", b"").decode()[:64]
        request_id = incoming if incoming and incoming.replace("-", "").isalnum() else uuid.uuid4().hex[:16]
        token = self.request_id_var.set(request_id)
        start = time.perf_counter()
        status_holder = {"status": 500}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                message["headers"] = list(message.get("headers", [])) + [(b"x-request-id", request_id.encode())]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration = (time.perf_counter() - start) * 1000
            path = scope["path"]
            route = getattr(scope.get("route"), "path", None)
            if route is None:
                route = "/images/*" if path.startswith("/images/") else "/uploads/*" if path.startswith("/uploads/") else "unmatched"
            metrics = self.metrics_getter()
            if metrics is not None:
                metrics.record(scope["method"], route, status_holder["status"], duration)
            if not path.startswith(("/images/", "/uploads/")):
                status = status_holder["status"]
                level = 40 if status >= 500 else 30 if status >= 400 else 20
                self.logger.log(level, f"{scope['method']} {path} -> {status} ({duration:.0f} ms)",
                                extra={"method": scope["method"], "path": path, "status": status,
                                       "duration_ms": round(duration, 1),
                                       "client": (scope.get("client") or ("?",))[0]})
            self.request_id_var.reset(token)


class BodySizeLimitMiddleware:
    """Reject bodies above max_bytes with 413 - checked on Content-Length and while streaming"""

    def __init__(self, app, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def reject():
            import json

            body = json.dumps({"detail": f"Requête trop volumineuse (max {self.max_bytes // (1024 * 1024)} Mo)."}).encode()
            await send({"type": "http.response.start", "status": 413,
                        "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
            await send({"type": "http.response.body", "body": body})

        length = dict(scope.get("headers") or []).get(b"content-length")
        if length is not None and length.isdigit() and int(length) > self.max_bytes:
            return await reject()

        # Chunked uploads (no Content-Length): count while reading. FastAPI turns a body-read error
        # into its own 400, so the response it sends is replaced by the 413.
        received = 0
        too_large = False

        async def limited_receive():
            nonlocal received, too_large
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    too_large = True
                    raise ValueError("body too large")
            return message

        rejected = False

        async def guarded_send(message):
            nonlocal rejected
            if too_large:
                if not rejected:
                    rejected = True
                    await reject()
                return
            await send(message)

        try:
            await self.app(scope, limited_receive, guarded_send)
        except ValueError:
            if not too_large:
                raise
            if not rejected:
                await reject()
