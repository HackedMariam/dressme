"""Historique de conversation dans Supabase (tables chat_threads et chat_messages, docs/chat_history.sql).

Chaque appel part avec la clé anon ET le jeton de l'utilisatrice : la RLS de Supabase limite la lecture,
l'écriture et la suppression à ses propres lignes. La clé service_role n'est jamais utilisée ici.
Transport injectable (tests sans réseau) : transport(request, timeout) -> (status, corps en octets).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Optional

TITLE_MAX = 60


class HistoryError(RuntimeError):
    """Supabase injoignable, jeton refusé, table absente ou réponse inattendue."""


def urllib_transport(request: urllib.request.Request, timeout: float) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read() or b""


def title_from(message: str) -> str:
    text = " ".join(message.split())
    return text if len(text) <= TITLE_MAX else text[:TITLE_MAX - 1].rstrip() + "…"


class ChatHistory:
    def __init__(self, supabase_url: str, anon_key: str, transport: Callable = urllib_transport,
                 timeout: float = 5.0):
        self.base = supabase_url.rstrip("/") + "/rest/v1"
        self._anon_key, self.transport, self.timeout = anon_key, transport, timeout

    def __repr__(self) -> str:  # jamais la clé
        return f"ChatHistory({self.base!r})"

    def _call(self, method: str, path: str, token: str, query: Optional[dict] = None, body: Any = None,
              prefer: Optional[str] = None) -> Any:
        if not token:
            raise HistoryError("jeton manquant : l'historique n'existe qu'en mode connecté")
        url = f"{self.base}/{path}" + (f"?{urllib.parse.urlencode(query)}" if query else "")
        headers = {"apikey": self._anon_key, "Authorization": f"Bearer {token}", "Accept": "application/json"}
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if prefer:
            headers["Prefer"] = prefer
        request = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            status, raw = self.transport(request, self.timeout)
        except Exception as exc:  # réseau, DNS, TLS, délai
            raise HistoryError(f"Supabase injoignable : {type(exc).__name__}") from exc
        if not 200 <= status < 300:
            raise HistoryError(f"Supabase a répondu HTTP {status} sur {path}")
        if not raw:
            return None
        try:
            return json.loads(raw.decode("utf-8"))
        except ValueError as exc:
            raise HistoryError(f"réponse non JSON de Supabase sur {path}") from exc

    # ---------------------------------------------------------------- lecture
    def list_threads(self, token: str, limit: int = 30) -> list[dict]:
        rows = self._call("GET", "chat_threads", token, {"select": "id,title,created_at,updated_at",
                                                         "order": "updated_at.desc", "limit": str(limit)})
        return rows if isinstance(rows, list) else []

    def messages(self, token: str, thread_id: str, limit: int = 500) -> list[dict]:
        rows = self._call("GET", "chat_messages", token, {"select": "role,content,route,created_at",
                                                          "thread_id": f"eq.{thread_id}",
                                                          "order": "created_at.asc", "limit": str(limit)})
        return rows if isinstance(rows, list) else []

    # ---------------------------------------------------------------- écriture
    def create_thread(self, token: str, first_message: str) -> str:
        rows = self._call("POST", "chat_threads", token, {"select": "id"}, {"title": title_from(first_message) or
                                                                            "Nouvelle conversation"},
                          prefer="return=representation")
        if not isinstance(rows, list) or not rows or not rows[0].get("id"):
            raise HistoryError("création du fil : identifiant absent de la réponse")
        return str(rows[0]["id"])

    def append_turn(self, token: str, thread_id: str, user_message: str, answer: str,
                    route: Optional[str]) -> None:
        """La question et la réponse, en une requête (user_id = auth.uid() côté base)."""
        rows = [{"thread_id": thread_id, "role": "user", "content": user_message[:20000] or " "},
                {"thread_id": thread_id, "role": "assistant", "content": answer[:20000] or " ",
                 "route": (route or None) and str(route)[:60]}]
        self._call("POST", "chat_messages", token, body=rows, prefer="return=minimal")

    def delete_all(self, token: str) -> None:
        """Supprime tous les fils de l'utilisatrice (ses messages suivent par cascade). PostgREST refuse un DELETE
        sans filtre : id=not.is.null vise toutes les lignes que la RLS laisse voir, donc les siennes seulement."""
        self._call("DELETE", "chat_threads", token, {"id": "not.is.null"}, prefer="return=minimal")
