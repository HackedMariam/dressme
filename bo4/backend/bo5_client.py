"""Client minimal de BO5 (RAG de conseils de style), pour le Stylist Agent.

Appelle POST {base_url}/ask du service BO5 (branche rag/try1, rag_backend/app.py) :
- corps : {"question": str, "top_k": int} (AskRequest) ;
- clé facultative dans le header `X-API-Key` (RAG_API_KEY_HEADER par défaut côté BO5,
  qui accepte aussi « Authorization: Bearer ») ;
- réponse AskResponse : {"answer": str, "sources": [{"title", "source", "page", ...}], ...}.

On ne garde que la réponse et les titres (ou noms de fichiers) des sources.
urllib uniquement, comme bo1_api_adapter : aucune dépendance supplémentaire.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Optional

DEFAULT_BO5_URL = "http://localhost:8001"
API_KEY_HEADER = os.environ.get("BO5_API_KEY_HEADER", "X-API-Key")


class BO5UnavailableError(RuntimeError):
    """BO5 ne répond pas ou renvoie une réponse inattendue."""


def _source_label(source: object) -> Optional[str]:
    if isinstance(source, str):
        return source.strip() or None
    if isinstance(source, dict):
        for key in ("title", "source"):
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def ask_bo5(question: str, base_url: Optional[str] = None, api_key: Optional[str] = None,
            top_k: int = 3, timeout: float = 20.0) -> dict:
    """Pose une question à BO5 ; renvoie {"answer": str, "sources": [str]}."""
    base_url = (base_url or os.environ.get("BO5_API_URL") or DEFAULT_BO5_URL).rstrip("/")
    api_key = os.environ.get("BO5_API_KEY") if api_key is None else api_key
    body = json.dumps({"question": question, "top_k": top_k}).encode("utf-8")
    request = urllib.request.Request(f"{base_url}/ask", data=body, method="POST",
                                     headers={"Content-Type": "application/json",
                                              "Accept": "application/json"})
    if api_key:
        request.add_header(API_KEY_HEADER, api_key)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise BO5UnavailableError(f"BO5 a répondu HTTP {exc.code} sur /ask") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise BO5UnavailableError(f"BO5 injoignable à {base_url} : {exc}") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise BO5UnavailableError("Réponse de BO5 non JSON") from exc

    if not isinstance(payload, dict) or not isinstance(payload.get("answer"), str):
        raise BO5UnavailableError("Réponse de BO5 inattendue : champ « answer » manquant")
    raw_sources = payload.get("sources") or []
    if not isinstance(raw_sources, list):
        raise BO5UnavailableError("Réponse de BO5 inattendue : « sources » doit être une liste")
    sources: list[str] = []
    for source in raw_sources:
        label = _source_label(source)
        if label and label not in sources:
            sources.append(label)
    return {"answer": payload["answer"].strip(), "sources": sources}
