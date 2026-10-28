"""Accès HTTP aux services DressMe pour l'orchestrateur.

Chaque appel a un délai maximum et ne lève jamais d'exception : il renvoie un `CallResult` avec le code HTTP
(ou None si le service est injoignable), la durée et un message d'erreur lisible. Le jeton utilisateur est
transmis dans l'en-tête Authorization et n'apparaît jamais dans les messages ni dans la trace.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

import yaml

CONFIG_FILE = Path(__file__).with_name("services.yaml")


@dataclass(frozen=True)
class Service:
    name: str
    label: str
    url: str
    timeout: float
    api_key_env: Optional[str] = None
    extra: dict = field(default_factory=dict)


def load_services(path: Path | str = CONFIG_FILE, overrides: Optional[dict[str, str]] = None) -> dict[str, Service]:
    """Lit services.yaml ; `overrides` remplace des URL ({"bo1": "http://..."})."""
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))["services"]
    services = {}
    for name, conf in raw.items():
        known = {"label", "url", "timeout", "api_key_env"}
        url = (overrides or {}).get(name) or conf["url"]
        services[name] = Service(name=name, label=conf.get("label", name), url=url.rstrip("/"),
                                 timeout=float(conf.get("timeout", 10)), api_key_env=conf.get("api_key_env"),
                                 extra={k: v for k, v in conf.items() if k not in known})
    return services


@dataclass
class CallResult:
    service: str
    method: str
    path: str
    status: Optional[int]          # None : service injoignable ou délai dépassé
    ms: int
    data: Any = None
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.status is not None and 200 <= self.status < 300

    def trace(self) -> str:
        code = f"HTTP {self.status}" if self.status is not None else "injoignable"
        return f"{self.service} {self.method} {self.path} : {code} en {self.ms} ms"


# Transport : (requête, délai) -> (code HTTP, corps). Remplacé par un faux dans les tests.
Transport = Callable[[urllib.request.Request, float], tuple[int, bytes]]


def urllib_transport(request: urllib.request.Request, timeout: float) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def _detail(data: Any) -> str:
    if isinstance(data, dict) and data.get("detail"):
        detail = data["detail"]
        return detail if isinstance(detail, str) else json.dumps(detail, ensure_ascii=False)[:200]
    return ""


class Gateway:
    """Appels aux services de services.yaml, avec délai maximum et erreurs converties en messages."""

    def __init__(self, services: dict[str, Service], transport: Transport = urllib_transport):
        self.services = services
        self.transport = transport

    def call(self, name: str, method: str, path: str, body: Any = None, token: Optional[str] = None,
             timeout: Optional[float] = None) -> CallResult:
        service = self.services[name]
        headers = {"Accept": "application/json"}
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode("utf-8")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if service.api_key_env and os.environ.get(service.api_key_env):
            headers["X-API-Key"] = os.environ[service.api_key_env]
        request = urllib.request.Request(f"{service.url}{path}", data=data, headers=headers, method=method)
        start = time.perf_counter()
        try:
            status, raw = self.transport(request, timeout or service.timeout)
        except Exception as exc:  # connexion refusée, délai dépassé, DNS...
            reason = getattr(exc, "reason", None) or exc
            return CallResult(name, method, path, None, int((time.perf_counter() - start) * 1000),
                              error=f"{service.label} ne répond pas ({service.url}) : {type(reason).__name__}")
        ms = int((time.perf_counter() - start) * 1000)
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else None
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = None
        result = CallResult(name, method, path, status, ms, data=payload)
        if not result.ok:
            detail = _detail(payload)
            result.error = f"{service.label} a répondu HTTP {status}" + (f" : {detail}" if detail else "")
        return result
