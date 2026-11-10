"""Appels HTTP JSON minimalistes (urllib) : ne lèvent jamais, renvoient (statut, JSON, erreur, durée)."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request


def call(method: str, url: str, *, token: str | None = None, body=None, headers: dict | None = None,
         timeout: float = 120.0) -> tuple[int | None, object, str | None, float]:
    """(statut HTTP ou None si injoignable, JSON ou None, erreur courte ou None, durée en ms)."""
    head = {"Accept": "application/json", **(headers or {})}
    data = None
    if token:
        head["Authorization"] = f"Bearer {token}"
    if body is not None:
        head["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    started = time.perf_counter()
    request = urllib.request.Request(url, data=data, headers=head, method=method)
    status, payload, error = None, None, None
    try:
        with urllib.request.urlopen(request, timeout=timeout) as reply:
            status, raw = reply.status, reply.read()
    except urllib.error.HTTPError as exc:
        status, raw = exc.code, exc.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        error = "timeout" if isinstance(exc, TimeoutError) or "timed out" in str(reason) else "injoignable"
        raw = b""
    if raw:
        try:
            payload = json.loads(raw.decode("utf-8", errors="replace"))
        except ValueError:
            payload = None
    return status, payload, error, (time.perf_counter() - started) * 1000
