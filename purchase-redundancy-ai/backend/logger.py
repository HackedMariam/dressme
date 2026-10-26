"""
Logging - console + rotating file (logs/app.log), text or JSON lines, with the request id of the
current HTTP request on every record (set by the middleware in main.py).
"""

import json
import logging
from contextvars import ContextVar
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per line - readable by Loki, ELK, Datadog, CloudWatch..."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "time": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", "-"),
            "message": record.getMessage(),
        }
        for key in ("method", "path", "status", "duration_ms", "client", "user_id"):
            if hasattr(record, key):
                entry[key] = getattr(record, key)
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


def setup_logging(level: str = "INFO", log_file: Path = None, fmt: str = "text",
                  max_bytes: int = 10 * 1024 * 1024, backup_count: int = 5) -> None:
    """Configure the root logger once (idempotent - safe when the app is imported several times)"""
    root = logging.getLogger()
    if getattr(root, "_purchase_redundancy_configured", False):
        return

    formatter = JsonFormatter() if fmt == "json" else logging.Formatter(
        "%(asctime)s %(levelname)-7s [%(request_id)s] %(name)s - %(message)s")
    handlers = [logging.StreamHandler()]
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(RotatingFileHandler(log_file, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"))

    for handler in handlers:
        handler.setFormatter(formatter)
        handler.addFilter(RequestIdFilter())
        root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Our request log replaces uvicorn's access log; keep third-party noise down
    for noisy in ("uvicorn.access", "httpx", "httpcore", "urllib3", "PIL"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    root._purchase_redundancy_configured = True
