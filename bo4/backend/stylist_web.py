"""Interface web du Stylist Agent (FastAPI + HTML/CSS/JS, sans framework front).

- Gauche : conversation en langage naturel et tenues proposées, avec les images BO1.
- Droite : « coulisses de l'agent » : graphe LangGraph avec les nodes traversés,
  trace de chaque node et demande extraite (JSON). Utile pour montrer l'orchestration.

Lancement (PowerShell, depuis backend/) :
    .\\.venv\\Scripts\\python.exe stylist_web.py --port 8060
    .\\.venv\\Scripts\\python.exe stylist_web.py --port 8060 --fallback tests\\fixtures\\bo1_items_sample.json --no-llm
Puis ouvrir http://127.0.0.1:8060
"""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
import datetime as dt
import os
import uuid
from html import escape
from typing import Any, Callable, Optional

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

import bo1_api_adapter
import stylist_agent as sa
import stylist_feedback

NODE_ORDER = ("extract_intent", "record_feedback", "clarify", "get_weather", "fetch_wardrobe", "apply_constraints", "recommend", "style_advice", "respond")
SUBSCORES = ("color_score", "style_score", "occasion_score", "season_score")
DEFAULT_WEATHER = sa.default_weather()

_settings: dict[str, Any] = {
    "bo1_url": os.environ.get("BO1_API_URL"),
    "fallback": os.environ.get("STYLIST_FALLBACK") or None,
    "llm": None if os.environ.get("STYLIST_NO_LLM") == "1" else sa.ollama_extract,
    "loader": None,
    "today": None,
    # Open-Meteo, MET Norway, wttr.in, cache ; un seul fournisseur pour garder cache et sources en panne
    "weather": None if os.environ.get("STYLIST_NO_WEATHER") == "1" else DEFAULT_WEATHER,
    "city": os.environ.get("STYLIST_CITY", sa.DEFAULT_CITY),
    "feedback": stylist_feedback.FeedbackStore(os.environ.get("STYLIST_FEEDBACK_FILE", "stylist_feedback.json")),
    "advice": None,  # BO5 (RAG) désactivé par défaut : activé par --bo5-url
    "require_auth": False,  # --require-auth : jeton Supabase obligatoire (mode production)
    "identity": None,       # fonction jeton -> user_id ; par défaut GET /api/me de BO1
}
_graph = None


def configure(*, bo1_url: Optional[str] = None, fallback: Optional[str] = None,
              llm: Optional[Callable] = sa.ollama_extract, loader: Optional[Callable] = None,
              today: Optional[Callable[[], dt.date]] = None,
              weather: Optional[Callable] = DEFAULT_WEATHER, city: str = sa.DEFAULT_CITY,
              feedback: Optional[stylist_feedback.FeedbackStore] = None,
              advice: Optional[Callable[[str], dict]] = None, require_auth: bool = False,
              identity: Optional[Callable[[str], str]] = None) -> None:
    """(Re)configure l'agent : utilisé par main() et par les tests."""
    global _graph
    if require_auth and fallback:
        # Une panne de BO1 ne doit jamais basculer en silence sur une garde-robe d'exemple.
        raise ValueError("--require-auth est incompatible avec --fallback")
    _settings.update(bo1_url=bo1_url, fallback=fallback, llm=llm, loader=loader, today=today,
                     weather=weather, city=city, feedback=feedback or stylist_feedback.FeedbackStore(),
                     advice=advice, require_auth=require_auth, identity=identity)
    _graph = None


def _loader(token: Optional[str] = None) -> tuple[list[dict], dict]:
    """Garde-robe de l'utilisateur du jeton (sans jeton : BO1_TOKEN ou mode local, comme avant)."""
    if _settings["loader"]:
        return _settings["loader"](token=token) if token else _settings["loader"]()
    return bo1_api_adapter.load_wardrobe_from_bo1(_settings["bo1_url"], token=token,
                                                  fallback_file=_settings["fallback"])


# --------------------------------------------------------------------------------------
# Identité de l'utilisateur (jeton Supabase vérifié par BO1, pas de décodage local du JWT)
# --------------------------------------------------------------------------------------
def bo1_identity(token: str) -> str:
    """GET /api/me de BO1 avec le jeton : renvoie l'identifiant de l'utilisateur."""
    base = (_settings["bo1_url"] or bo1_api_adapter.BO1_API_URL).rstrip("/")
    request = urllib.request.Request(f"{base}/api/me", headers={"Accept": "application/json",
                                                                 "Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise HTTPException(401, "Jeton invalide ou expiré", headers={"WWW-Authenticate": "Bearer"}) from exc
        raise HTTPException(503, f"BO1 a répondu HTTP {exc.code} sur /api/me") from exc
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise HTTPException(503, "BO1 injoignable : identité de l'utilisateur impossible à vérifier") from exc
    user_id = payload.get("id") if isinstance(payload, dict) else None
    if not isinstance(user_id, str) or not user_id or ":" in user_id:
        raise HTTPException(503, "Réponse inattendue de BO1 sur /api/me")
    return user_id


def authenticate(authorization: Optional[str]) -> tuple[str, Optional[str]]:
    """(user_id, jeton) de la requête. Sans jeton et sans --require-auth : utilisateur « local »."""
    token = None
    if authorization:
        scheme, _, value = authorization.strip().partition(" ")
        if scheme.lower() != "bearer" or not value.strip():
            raise HTTPException(401, "En-tête attendu : Authorization: Bearer <jeton>",
                                headers={"WWW-Authenticate": "Bearer"})
        token = value.strip()
    if token is None:
        if _settings["require_auth"]:
            raise HTTPException(401, "Connexion requise : jeton Supabase manquant",
                                headers={"WWW-Authenticate": "Bearer"})
        return sa.DEFAULT_USER, None
    user_id = (_settings["identity"] or bo1_identity)(token)
    if _settings["require_auth"] and user_id == sa.DEFAULT_USER:
        # BO1 en mode local accepte n'importe quel jeton : pas d'isolation possible.
        raise HTTPException(503, "BO1 est en mode local (utilisateur unique) : --require-auth exige "
                                 "un BO1 branché sur Supabase")
    return user_id, token


def get_graph():
    global _graph
    if _graph is None:
        _graph = sa.build_graph(llm=_settings["llm"], wardrobe_loader=_loader, today=_settings["today"],
                                weather=_settings["weather"], default_city=_settings["city"],
                                feedback_store=_settings["feedback"], advice=_settings["advice"])
    return _graph


# --------------------------------------------------------------------------------------
# Mise en forme pour le navigateur
# --------------------------------------------------------------------------------------
def visited_nodes(trace: list[str]) -> list[str]:
    return [line.split()[0] for line in trace if line.split() and line.split()[0] in NODE_ORDER]


def mermaid_for(visited: list[str]) -> str:
    """Graphe du Stylist Agent, nodes traversés au dernier tour mis en évidence."""
    lines = [
        "flowchart TD",
        "  START([START]) --> extract_intent",
        "  extract_intent -->|occasion manquante| clarify",
        "  extract_intent -->|retour sur une tenue| record_feedback",
        "  record_feedback -->|merci| END",
        "  record_feedback -->|rejet : autre tenue| get_weather",
        "  extract_intent -->|occasion connue| get_weather",
        "  get_weather --> fetch_wardrobe",
        "  clarify --> END([END])",
        "  fetch_wardrobe -->|BO1 indisponible| respond",
        "  fetch_wardrobe -->|garde-robe lue| apply_constraints",
        "  apply_constraints --> recommend",
        "  recommend --> style_advice",
        "  style_advice --> respond",
        "  style_advice -.->|question sur la tenue 1| bo5_rag",
        "  respond --> END",
        '  extract_intent["extract_intent<br/>LLM + règles"]',
        '  get_weather["get_weather<br/>Open-Meteo · MET Norway · wttr.in"]',
        '  fetch_wardrobe["fetch_wardrobe<br/>BO1 : GET /api/items"]',
        '  apply_constraints["apply_constraints<br/>contraintes obligatoires"]',
        '  recommend["recommend<br/>moteur BO4 + profil"]',
        '  record_feedback["record_feedback<br/>I76 : 👍 / 👎"]',
        '  style_advice["style_advice<br/>conseil BO5 (optionnel)"]',
        '  bo5_rag[("BO5 RAG<br/>POST /ask")]',
        "  style bo5_rag stroke-dasharray:5 5",
        "  classDef visited fill:#556B2F,stroke:#3E4F22,color:#fff",
    ]
    if visited:
        lines.append(f"  class {','.join(dict.fromkeys(visited))} visited")
    return "\n".join(lines)


# --------------------------------------------------------------------------------------
# Schéma du graphe en SVG dessiné à la main (hors ligne, sans Mermaid)
# --------------------------------------------------------------------------------------
SVG_WIDTH, SVG_HEIGHT = 460, 600
NAME_SIZE, SUB_SIZE = 12, 11
OLIVE, BORDER, INK, MUTED = "#556B2F", "#E2E0D8", "#1C1C1C", "#8C8A82"
CENTER_X, CENTER_W, LEFT_X, LEFT_W, BOX_H = 200, 200, 20, 120, 44
ROW_Y = (50, 124, 198, 272, 346, 420, 494)          # haut de chaque boîte de la colonne centrale
# node -> (x, y, largeur, sous-titre)
GRAPH_NODES = {
    "extract_intent": (CENTER_X, ROW_Y[0], CENTER_W, "LLM + règles"),
    "get_weather": (CENTER_X, ROW_Y[1], CENTER_W, "3 sources météo + cache"),
    "fetch_wardrobe": (CENTER_X, ROW_Y[2], CENTER_W, "BO1 /api/items"),
    "apply_constraints": (CENTER_X, ROW_Y[3], CENTER_W, "contraintes"),
    "recommend": (CENTER_X, ROW_Y[4], CENTER_W, "moteur BO4 + profil"),
    "style_advice": (CENTER_X, ROW_Y[5], CENTER_W, "BO5 optionnel"),
    "respond": (CENTER_X, ROW_Y[6], CENTER_W, "réponse"),
    "clarify": (LEFT_X, ROW_Y[0], LEFT_W, "pose la question"),
    "record_feedback": (LEFT_X, ROW_Y[2], LEFT_W, "avis 👍 / 👎"),
}
CX = CENTER_X + CENTER_W // 2
START_Y, END_Y, PILL_H = 12, 562, 24
# (départ, arrivée) -> (points de la ligne brisée, étiquette, position de l'étiquette)
GRAPH_EDGES = {
    ("START", "extract_intent"): ([(CX, START_Y + PILL_H), (CX, ROW_Y[0])], None, None),
    ("extract_intent", "clarify"): ([(CENTER_X, 72), (LEFT_X + LEFT_W, 72)], "occasion ?", (170, 65)),
    ("extract_intent", "record_feedback"): ([(CENTER_X, 88), (125, ROW_Y[2])], "retour", (150, 120)),
    ("extract_intent", "get_weather"): ([(CX, ROW_Y[0] + BOX_H), (CX, ROW_Y[1])], None, None),
    ("record_feedback", "get_weather"): ([(LEFT_X + LEFT_W, 210), (CENTER_X, 152)], "rejet", (186, 204)),
    ("record_feedback", "END"): ([(LEFT_X, 220), (8, 220), (8, END_Y + 12), (CX - 30, END_Y + 12)], "merci", (13, 262)),
    ("clarify", "END"): ([(LEFT_X, 72), (8, 72), (8, END_Y + 12), (CX - 30, END_Y + 12)], None, None),
    ("get_weather", "fetch_wardrobe"): ([(CX, ROW_Y[1] + BOX_H), (CX, ROW_Y[2])], None, None),
    ("fetch_wardrobe", "apply_constraints"): ([(CX, ROW_Y[2] + BOX_H), (CX, ROW_Y[3])], None, None),
    ("fetch_wardrobe", "respond"): ([(CENTER_X + CENTER_W, 220), (436, 220), (436, 516),
                                     (CENTER_X + CENTER_W, 516)], "BO1 indisponible", (450, 368)),
    ("apply_constraints", "recommend"): ([(CX, ROW_Y[3] + BOX_H), (CX, ROW_Y[4])], None, None),
    ("recommend", "style_advice"): ([(CX, ROW_Y[4] + BOX_H), (CX, ROW_Y[5])], None, None),
    ("style_advice", "respond"): ([(CX, ROW_Y[5] + BOX_H), (CX, ROW_Y[6])], None, None),
    ("respond", "END"): ([(CX, ROW_Y[6] + BOX_H), (CX, END_Y)], None, None),
}


def visited_edges(visited: list[str]) -> set[tuple[str, str]]:
    """Flèches empruntées au dernier tour : START, nodes visités dans l'ordre, END."""
    if not visited:
        return set()
    path = ["START", *visited]
    if visited[-1] in {"respond", "clarify", "record_feedback"}:
        path.append("END")
    return {(a, b) for a, b in zip(path, path[1:]) if (a, b) in GRAPH_EDGES}


def _arrowhead(points: list[tuple[int, int]], size: float = 7.0) -> str:
    (x1, y1), (x2, y2) = points[-2], points[-1]
    length = max(((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5, 1e-6)
    ux, uy = (x2 - x1) / length, (y2 - y1) / length
    bx, by = x2 - ux * size, y2 - uy * size
    px, py = -uy * size * 0.55, ux * size * 0.55
    return f"{x2:.1f},{y2:.1f} {bx + px:.1f},{by + py:.1f} {bx - px:.1f},{by - py:.1f}"


def graph_svg(visited: list[str]) -> str:
    """Schéma du Stylist Agent, nodes et flèches du dernier tour en olive. Couleurs par défaut en
    attributs (SVG autonome) ; la page les surcharge par CSS pour le mode sombre."""
    seen, used = set(visited), visited_edges(visited)
    parts = [f'<svg class="gsvg" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {SVG_WIDTH} {SVG_HEIGHT}" '
             f'width="100%" role="img" aria-label="Graphe LangGraph du Stylist Agent : '
             f'{escape(" → ".join(visited)) if visited else "aucun tour"}" '
             f'font-family="Inter, system-ui, sans-serif">']
    for (src, dst), (points, label, label_at) in GRAPH_EDGES.items():
        on = (src, dst) in used
        color, width = (OLIVE, 2.6) if on else (MUTED, 1.2)
        klass = "e v" if on else "e"
        coords = " ".join(f"{x},{y}" for x, y in points)
        parts.append(f'<g class="{klass}"><polyline points="{coords}" fill="none" stroke="{color}" '
                     f'stroke-width="{width}" stroke-linejoin="round"/>'
                     f'<polygon points="{_arrowhead(points)}" fill="{color}"/></g>')
        if label:
            x, y = label_at
            rotate = f' transform="rotate(90 {x} {y})"' if (src, dst) == ("fetch_wardrobe", "respond") else ""
            anchor = "start" if (src, dst) == ("record_feedback", "END") else "middle"
            parts.append(f'<text class="lbl{" v" if on else ""}" x="{x}" y="{y}" font-size="{SUB_SIZE}" '
                         f'text-anchor="{anchor}" fill="{OLIVE if on else MUTED}"{rotate}>{escape(label)}</text>')
    for pill_y, name in ((START_Y, "START"), (END_Y, "END")):
        on = any(dst == "END" for _, dst in used) if name == "END" else bool(visited)
        parts.append(f'<g class="pill{" v" if on else ""}"><rect x="{CX - 30}" y="{pill_y}" width="60" '
                     f'height="{PILL_H}" rx="12" fill="{OLIVE if on else "none"}" stroke="{OLIVE if on else BORDER}"/>'
                     f'<text x="{CX}" y="{pill_y + 16}" font-size="{SUB_SIZE}" font-weight="600" text-anchor="middle" '
                     f'fill="{"#FFFFFF" if on else INK}">{name}</text></g>')
    for name, (x, y, w, sub) in GRAPH_NODES.items():
        on = name in seen
        parts.append(f'<g class="n{" v" if on else ""}"><rect x="{x}" y="{y}" width="{w}" height="{BOX_H}" rx="10" '
                     f'fill="{OLIVE if on else "none"}" stroke="{OLIVE if on else BORDER}" stroke-width="1.5"/>'
                     f'<text class="name" x="{x + w / 2:g}" y="{y + 19}" font-size="{NAME_SIZE}" font-weight="600" '
                     f'text-anchor="middle" fill="{"#FFFFFF" if on else INK}">{escape(name)}</text>'
                     f'<text class="sub" x="{x + w / 2:g}" y="{y + 35}" font-size="{SUB_SIZE}" text-anchor="middle" '
                     f'fill="{"#FFFFFF" if on else MUTED}">{escape(sub)}</text></g>')
    parts.append("</svg>")
    return "".join(parts)

def _item_view(item: dict, labels: Optional[dict] = None) -> dict:
    return {
        "id": item["id"], "name": (labels or {}).get(str(item["id"]), item.get("name")),
        "category": item.get("category"),
        "color": item.get("color"), "color_hex": item.get("color_hex"),
        "style": item.get("style"), "bo1_style": item.get("bo1_style"),
        "image": item.get("cutout_url") or item.get("image_url"),
    }


def turn_payload(state: dict, thread_id: str, user_id: str = sa.DEFAULT_USER) -> dict:
    wardrobe = state.get("wardrobe") or []
    outfits = []
    for rank, outfit in enumerate(state.get("outfits") or [], 1):
        items = sa._outfit_items(outfit, wardrobe)
        labels = sa.display_names(wardrobe)
        outfits.append({
            "rank": rank,
            "score": round(float(outfit.get("score", 0)), 1),
            "subscores": {k: round(float(outfit[k]), 1) for k in SUBSCORES if k in outfit},
            "explanations": sa._explanations(outfit),
            "formality": outfit.get("formality"),
            "personal_bonus": outfit.get("personal_bonus", 0),
            "dress_code_ok": outfit.get("dress_code_ok", True),
            "items": [_item_view(item, labels) for item in items],
        })
    trace = state.get("trace") or []
    visited = visited_nodes(trace)
    request = {k: v for k, v in (state.get("request") or {}).items() if k != "unsupported_now"}
    report = state.get("wardrobe_report") or {}
    return {
        "thread_id": thread_id,
        "response": state.get("response", ""),
        "outfits": outfits,
        "request": request,
        "trace": trace,
        "visited": visited,
        "mermaid": mermaid_for(visited),
        "graph_svg": graph_svg(visited),
        "wardrobe": {"source": report.get("source"), "received": report.get("received"),
                     "kept": report.get("kept"), "skipped": report.get("skipped")},
        "weather": state.get("weather") or {},
        "advice": state.get("advice") or {},
        "feedback_note": state.get("feedback_note") or "",
        "profile": profile_summary(user_id),
        "error": state.get("error") or "",
    }


def profile_summary(user_id: str = sa.DEFAULT_USER) -> dict:
    profile = _settings["feedback"].profile(user_id)
    return {k: profile[k] for k in ("likes", "dislikes", "liked_items", "disliked_items")} | {
        "colors": {c: v for c, v in profile["color_affinity"].items() if v}}


# --------------------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------------------
app = FastAPI(title="DressMe Stylist Agent (BO4)")


class ChatRequest(BaseModel):
    message: str
    thread_id: Optional[str] = None


@app.post("/api/chat")
def api_chat(body: ChatRequest, authorization: Optional[str] = Header(None)) -> dict:
    user_id, token = authenticate(authorization)
    message = body.message.strip()
    if not message:
        raise HTTPException(400, "Message vide")
    thread_id = body.thread_id or str(uuid.uuid4())
    graph = get_graph()
    # Fil « <user_id>:<thread_id> » ; le jeton passe par la configuration du tour, jamais par l'état.
    config = sa.turn_config(thread_id, user_id, token)
    graph.invoke(sa.new_turn(message), config)
    return turn_payload(graph.get_state(config).values, thread_id, user_id)


class FeedbackRequest(BaseModel):
    thread_id: str
    rank: int
    verdict: str


@app.post("/api/feedback")
def api_feedback(body: FeedbackRequest, authorization: Optional[str] = Header(None)) -> dict:
    """I76 : 👍 / 👎 sur une tenue du dernier tour (boutons de la page)."""
    user_id, _ = authenticate(authorization)
    if body.verdict not in {"like", "dislike"}:
        raise HTTPException(400, "verdict : like ou dislike")
    config = sa.turn_config(body.thread_id, user_id)
    state = get_graph().get_state(config).values or {}
    last = state.get("last_outfits") or []
    if not 1 <= body.rank <= len(last):
        raise HTTPException(404, f"Tenue n° {body.rank} introuvable dans les dernières propositions")
    by_id = {str(item["id"]): item for item in state.get("wardrobe") or []}
    items = [by_id[i] for i in last[body.rank - 1] if i in by_id]
    _settings["feedback"].add(body.verdict, items, (state.get("request") or {}).get("occasion"), user=user_id)
    labels = sa.display_names(state.get("wardrobe") or [])
    return {"ok": True, "items": [labels[str(item["id"])] for item in items], "profile": profile_summary(user_id)}


@app.get("/api/profile")
def api_profile(authorization: Optional[str] = Header(None)) -> dict:
    user_id, _ = authenticate(authorization)
    return profile_summary(user_id)


@app.get("/api/wardrobe")
def api_wardrobe(authorization: Optional[str] = Header(None)) -> dict:
    _, token = authenticate(authorization)
    try:
        wardrobe, report = _loader(token)
    except bo1_api_adapter.BO1UnavailableError as exc:
        raise HTTPException(503, str(exc)) from exc
    labels = sa.display_names(wardrobe)
    return {"report": report, "items": [_item_view(item, labels) for item in wardrobe]}


@app.get("/api/graph")
def api_graph() -> dict:
    return {"mermaid": mermaid_for([]), "graph_svg": graph_svg([])}


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return PAGE


PAGE = r"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DressMe · AI Stylist</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,500;0,600;0,700;1,400;1,500&family=Inter:wght@300;400;500;600;700&display=swap">
<style>
  /* Repris du template « DressMe UI Blueprint » (index.css, App.tsx) : mêmes couleurs, polices, composants. */
  :root {
    --font-display: "Playfair Display", Georgia, serif;
    --font-sans: "Inter", system-ui, "Segoe UI", sans-serif;
    --offwhite: #FAF9F6;      /* fond */
    --bone: #F0EFEA;          /* cartes claires */
    --charcoal: #1C1C1C;      /* barre latérale, carte sombre, texte */
    --charcoal-2: #2A2A2A;
    --olive: #556B2F;
    --olive-light: #6B8A3A;
    --olive-muted: #E8EDE0;
    --border: #E2E0D8;
    --muted: #8C8A82;
    --ink: #1C1C1C;
    --card-ink: #1C1C1C;
    --user-bg: #1C1C1C;
    --user-ink: #FAF9F6;
    --radius: 12px;
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      --offwhite: #141413; --bone: #22221F; --border: #34332E; --muted: #9A988F;
      --ink: #F0EFEA; --card-ink: #F0EFEA; --olive-muted: #2A3320;
      --user-bg: #F0EFEA; --user-ink: #1C1C1C; --charcoal: #0E0E0D; --charcoal-2: #1E1E1C;
      color-scheme: dark;
    }
    :root:not([data-theme="light"]) .pill { color: #A9C27A; }
  }
  * { box-sizing: border-box; }
  html, body { height: 100%; }
  body { margin: 0; background: var(--offwhite); color: var(--ink); font: 14px/1.5 var(--font-sans); }
  * { scrollbar-width: thin; scrollbar-color: #D4D2CA transparent; }
  button { font: inherit; }
  .muted { color: var(--muted); font-size: 13px; }

  /* ---------- Mise en page : barre latérale | conversation | coulisses ---------- */
  .app { display: grid; grid-template-columns: 240px minmax(0, 1fr) minmax(320px, 400px); height: 100vh; }

  .sidebar { background: #1C1C1C; color: #FAF9F6; display: flex; flex-direction: column; min-height: 0; }
  .brand { padding: 30px 26px 26px; border-bottom: 1px solid rgba(255,255,255,.1); }
  .logo { font-family: var(--font-display); font-size: 24px; font-weight: 600; display: flex; gap: 4px; align-items: baseline; }
  .logo .dress { font-style: italic; color: #FAF9F6; }
  .logo .me { color: var(--olive); }
  .brand p { margin: 2px 0 0; font-size: 11px; font-weight: 300; letter-spacing: .14em; text-transform: uppercase; color: rgba(255,255,255,.3); }
  .nav { flex: 1; padding: 18px 0; overflow-y: auto; }
  .nav-item { display: flex; align-items: center; gap: 12px; padding: 11px 26px; font-size: 14px; font-weight: 500;
              color: rgba(255,255,255,.5); }
  .nav-item .icon { opacity: .7; width: 16px; text-align: center; }
  .nav-item.disabled { color: rgba(255,255,255,.28); cursor: not-allowed; }
  .nav-item.active { background: rgba(85,107,47,.2); color: #FAF9F6; border-right: 2px solid var(--olive); }
  .sidebar-foot { padding: 18px 26px 22px; border-top: 1px solid rgba(255,255,255,.1); font-size: 11px; color: rgba(255,255,255,.35); }

  .main { display: flex; flex-direction: column; min-height: 0; min-width: 0; }
  .page-head { display: flex; align-items: flex-end; gap: 16px; padding: 30px 32px 18px; }
  .page-head h1 { margin: 0; font-family: var(--font-display); font-size: 30px; font-weight: 600; color: var(--ink); }
  .page-head p { margin: 4px 0 0; color: var(--muted); font-size: 13px; }
  .btn { border: 0; border-radius: 8px; padding: 10px 18px; font-weight: 600; cursor: pointer; }
  .btn-olive { background: var(--olive); color: #fff; }
  .btn-olive:hover { background: var(--olive-light); }
  .btn-ghost { background: var(--bone); color: var(--ink); border: 1px solid var(--border); }
  .btn:disabled { opacity: .5; cursor: wait; }
  .btn:focus-visible, .chip:focus-visible, .tab:focus-visible, .vote:focus-visible, input:focus-visible {
    outline: 2px solid var(--olive); outline-offset: 2px; }
  #reset { margin-left: auto; }

  #chat { flex: 1; overflow-y: auto; padding: 4px 32px 20px; display: flex; flex-direction: column; gap: 14px; min-height: 0; }
  .msg { max-width: 82%; padding: 11px 15px; border-radius: 14px; white-space: pre-wrap; }
  .msg.user { align-self: flex-end; background: var(--user-bg); color: var(--user-ink); border-bottom-right-radius: 4px; }
  .msg.bot { align-self: flex-start; background: var(--bone); color: var(--card-ink); border-bottom-left-radius: 4px; }
  .msg.bot.error { border: 1px solid #A7472F; }

  .composer { padding: 12px 32px 22px; border-top: 1px solid var(--border); }
  .chips { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 10px; }
  .chip { border: 0; background: var(--bone); color: var(--muted); border-radius: 8px; padding: 6px 12px; font-size: 12px;
          font-weight: 500; cursor: pointer; }
  .chip:hover { color: var(--ink); }
  form { display: flex; gap: 10px; }
  input { flex: 1; min-width: 0; padding: 11px 14px; border-radius: 8px; border: 1px solid var(--border);
          background: var(--bone); color: var(--ink); font: inherit; outline: none; }
  input:focus { border-color: var(--olive); }

  /* ---------- Tenue n° 1 : carte « AI Daily Recommendation » ---------- */
  .outfits { display: grid; gap: 14px; align-self: stretch; }
  .hero { background: var(--charcoal); color: #fff; border-radius: 16px; overflow: hidden; display: flex; min-height: 330px; }
  .hero-body { flex: 1; min-width: 0; padding: 28px 30px; display: flex; flex-direction: column; gap: 14px; justify-content: space-between; }
  .eyebrow { color: var(--olive-light); font-size: 11px; font-weight: 600; letter-spacing: .14em; text-transform: uppercase; }
  .hero h2 { margin: 6px 0 0; font-family: var(--font-display); font-size: 24px; font-weight: 500; line-height: 1.25; }
  .hero .meta { margin: 6px 0 0; color: rgba(255,255,255,.5); font-size: 13px; }
  .pieces { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 10px; }
  .piece { background: rgba(255,255,255,.05); border-radius: 8px; padding: 8px 12px; }
  .piece span { display: block; color: rgba(255,255,255,.4); font-size: 10px; letter-spacing: .06em; text-transform: uppercase; }
  .piece b { display: block; color: rgba(255,255,255,.85); font-size: 12px; font-weight: 500; margin-top: 2px; }
  .score-row { display: flex; align-items: center; gap: 14px; }
  .score-row b { display: block; font-weight: 600; }
  .score-row small { color: rgba(255,255,255,.45); font-size: 12px; }
  .ring { position: relative; flex: none; }
  .ring svg { transform: rotate(-90deg); display: block; }
  .ring .track { stroke: #E2E0D8; }
  .ring .value { stroke: var(--olive); }
  .ring span { position: absolute; inset: 0; display: grid; place-items: center; font-weight: 700; font-size: 14px; }
  .hero-photo { width: 280px; flex: none; margin: 0; position: relative; background: var(--charcoal-2); }
  .hero-photo .frame { position: absolute; inset: 0; background: #fff; display: grid; place-items: center; overflow: hidden; }
  .hero-photo img { width: 100%; height: 100%; object-fit: contain; opacity: .95; }
  .hero-photo figcaption { position: absolute; left: 0; right: 0; bottom: 0; padding: 40px 16px 16px;
                           background: linear-gradient(to top, rgba(0,0,0,.78), transparent); font-size: 12px; }
  .hero-photo figcaption span { display: block; color: rgba(255,255,255,.65); }
  .hero-photo figcaption p { margin: 4px 0 0; color: #fff; }
  .hero .vote { background: rgba(255,255,255,.08); color: #fff; }

  /* ---------- Tenues 2 et 3 : cartes claires compactes ---------- */
  .grid2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 14px; }
  .outfit-card { background: var(--bone); color: var(--card-ink); border-radius: var(--radius); padding: 16px; display: flex; flex-direction: column; gap: 12px; }
  .outfit-card header { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; }
  .outfit-card h3 { margin: 0; font-family: var(--font-display); font-size: 18px; font-weight: 500; }
  .pill { font-size: 12px; font-weight: 600; color: var(--olive); background: var(--olive-muted); padding: 2px 10px; border-radius: 999px; white-space: nowrap; }
  .thumbs { display: flex; gap: 10px; flex-wrap: wrap; }
  .thumb-wrap { width: 96px; }
  .thumb { width: 96px; height: 116px; border-radius: 10px; overflow: hidden; background: #fff; border: 1px solid var(--border);
           display: grid; place-items: center; }
  .thumb img { width: 100%; height: 100%; object-fit: contain; }
  .thumb-wrap b { display: block; font-size: 12px; font-weight: 600; margin-top: 5px; line-height: 1.25; }
  .thumb-wrap small { color: var(--muted); font-size: 11px; }
  .swatch { width: 48px; height: 48px; border-radius: 50%; border: 1px solid var(--border); }
  .bars { display: grid; grid-template-columns: 74px 1fr 34px; gap: 4px 8px; font-size: 12px; color: var(--muted); align-items: center; }
  .bar { height: 6px; background: var(--border); border-radius: 3px; overflow: hidden; }
  .bar i { display: block; height: 100%; background: var(--olive); border-radius: 3px; }
  .why { margin: 0; padding-left: 18px; font-size: 12px; color: var(--muted); }
  .why-title { margin: 0; font-size: 11px; font-weight: 600; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); }

  .actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
  .vote { border: 0; border-radius: 8px; padding: 6px 12px; font-size: 12px; font-weight: 500; cursor: pointer;
          background: var(--offwhite); color: var(--ink); }
  .vote:disabled { opacity: .5; cursor: default; }
  .done { font-size: 12px; color: var(--olive-light); }
  .hero .done { color: #A9C27A; }

  .advice { align-self: stretch; background: var(--olive-muted); color: var(--card-ink); border-radius: var(--radius); padding: 14px 16px; font-size: 13px; }
  .advice strong { display: block; color: var(--olive); font-size: 11px; letter-spacing: .1em; text-transform: uppercase; margin-bottom: 4px; }
  .advice .sources { margin-top: 6px; font-size: 12px; color: var(--muted); }

  /* ---------- Colonne de droite à onglets ---------- */
  .side { border-left: 1px solid var(--border); display: flex; flex-direction: column; min-height: 0; background: var(--offwhite); }
  .tabs { display: flex; gap: 8px; padding: 30px 20px 14px; }
  .tab { border: 0; border-radius: 8px; padding: 8px 14px; font-size: 12px; font-weight: 600; cursor: pointer;
         background: var(--bone); color: var(--muted); }
  .tab[aria-selected="true"] { background: var(--charcoal); color: #fff; }
  .panel { flex: 1; overflow-y: auto; padding: 0 20px 24px; min-height: 0; }
  .block { background: var(--bone); color: var(--card-ink); border-radius: var(--radius); padding: 14px 16px; margin-bottom: 12px; }
  .block h3 { margin: 0 0 8px; font-size: 11px; font-weight: 600; letter-spacing: .1em; text-transform: uppercase; color: var(--muted); }
  .graph-tools { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-top: 10px; }
  .path { margin: 0; font-size: 12px; line-height: 1.5; color: var(--card-ink); word-break: break-word; }
  .path b { font-weight: 600; color: var(--olive); }
  #graph { margin-top: 10px; }
  #graph svg, #modal-graph svg { display: block; max-width: 100%; height: auto; margin: 0 auto; }
  /* Schéma : couleurs par défaut en attributs SVG, surchargées ici pour suivre le thème. */
  .gsvg .n:not(.v) .name, .gsvg .pill:not(.v) text { fill: var(--ink); }
  .gsvg .n:not(.v) .sub, .gsvg .lbl:not(.v) { fill: var(--muted); }
  .gsvg .n:not(.v) rect, .gsvg .pill:not(.v) rect { stroke: var(--border); }
  .gsvg .e:not(.v) polyline { stroke: var(--muted); }
  .gsvg .e:not(.v) polygon { fill: var(--muted); }
  .modal { position: fixed; inset: 0; z-index: 100; background: rgba(28,28,28,.55); display: grid; place-items: center;
           padding: max(16px, env(safe-area-inset-top, 0px)) max(16px, env(safe-area-inset-right, 0px))
                    max(16px, env(safe-area-inset-bottom, 0px)) max(16px, env(safe-area-inset-left, 0px)); }
  .modal[hidden] { display: none; }
  .modal-box { background: var(--offwhite); color: var(--ink); border-radius: 16px; padding: 18px 20px; max-width: 100%;
               max-height: 100%; display: flex; flex-direction: column; gap: 12px; box-shadow: 0 20px 60px rgba(0,0,0,.3); }
  .modal-box header { display: flex; align-items: center; gap: 12px; }
  .modal-box h2 { margin: 0; font-family: var(--font-display); font-size: 20px; font-weight: 500; }
  .modal-box header .btn { margin-left: auto; }
  #modal-graph { overflow: auto; }
  #modal-graph svg { height: 80vh; width: auto; max-height: calc(100vh - 120px); }
  ol.trace { margin: 0; padding-left: 18px; font: 12px/1.45 ui-monospace, Consolas, monospace; }
  ol.trace li { margin-bottom: 6px; word-break: break-word; }
  pre { margin: 0; font: 12px/1.45 ui-monospace, Consolas, monospace; white-space: pre-wrap; background: var(--offwhite);
        padding: 10px; border-radius: 8px; color: var(--ink); }
  .wardrobe-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 12px; }
  .w-card { background: var(--bone); color: var(--card-ink); border-radius: var(--radius); overflow: hidden; }
  .w-card .photo { height: 150px; background: #fff; display: grid; place-items: center; overflow: hidden; border-bottom: 1px solid var(--border); }
  .w-card .photo img { width: 100%; height: 100%; object-fit: contain; }
  .w-card .body { padding: 10px 12px 12px; }
  .w-card .cat { font-size: 11px; font-weight: 500; letter-spacing: .06em; text-transform: uppercase; color: var(--muted); }
  .w-card .name { font-size: 13px; font-weight: 600; line-height: 1.25; margin-top: 2px; }
  .w-card .sub { font-size: 12px; color: var(--muted); margin-top: 4px; }

  /* ---------- Écrans étroits ---------- */
  @media (max-width: 1200px) {
    .app { grid-template-columns: 220px minmax(0, 1fr); height: auto; min-height: 100vh; }
    .side { grid-column: 2; border-left: 0; border-top: 1px solid var(--border); }
    #chat { min-height: 50vh; }
  }
  @media (max-width: 900px) {
    /* minmax(0, 1fr) : sinon la colonne prend la largeur du menu horizontal et la page déborde. */
    .app { grid-template-columns: minmax(0, 1fr); }
    .sidebar, .main, .side { min-width: 0; }
    .sidebar { flex-direction: row; flex-wrap: wrap; align-items: center; }
    .brand { padding: 14px 16px; border-bottom: 0; }
    .nav { display: flex; overflow-x: auto; padding: 0 8px; flex: 1 1 100%; order: 3; border-top: 1px solid rgba(255,255,255,.1); }
    .nav-item { padding: 10px 12px; white-space: nowrap; }
    .nav-item.active { border-right: 0; border-bottom: 2px solid var(--olive); }
    .sidebar-foot { display: none; }
    .side { grid-column: 1; }
    .page-head, #chat, .composer { padding-left: 16px; padding-right: 16px; }
    .tabs { padding: 16px 16px 12px; }
    .panel { padding: 0 16px 20px; }
  }
  @media (max-width: 640px) {
    .hero { flex-direction: column; }
    .hero-photo { width: 100%; height: 260px; }
    .msg { max-width: 95%; }
  }
</style>
</head>
<body>
<div class="app">
  <aside class="sidebar">
    <div class="brand">
      <div class="logo" aria-label="DressMe"><span class="dress">Dress</span><span class="me">Me</span></div>
      <p>AI Style Intelligence</p>
    </div>
    <nav class="nav" aria-label="Modules DressMe">
      <span class="nav-item disabled" aria-disabled="true" title="Module de l'équipe, dans l'application DressMe"><span class="icon">⊞</span>Dashboard</span>
      <span class="nav-item disabled" aria-disabled="true" title="Module de l'équipe, dans l'application DressMe"><span class="icon">◫</span>My Wardrobe</span>
      <span class="nav-item disabled" aria-disabled="true" title="Module de l'équipe, dans l'application DressMe"><span class="icon">✦</span>Outfit Studio</span>
      <span class="nav-item disabled" aria-disabled="true" title="Module de l'équipe, dans l'application DressMe"><span class="icon">◈</span>Help Me Pack</span>
      <span class="nav-item disabled" aria-disabled="true" title="Module de l'équipe, dans l'application DressMe"><span class="icon">◉</span>Style Profile</span>
      <span class="nav-item disabled" aria-disabled="true" title="Module de l'équipe, dans l'application DressMe"><span class="icon">◇</span>Should I Buy?</span>
      <span class="nav-item disabled" aria-disabled="true" title="Module de l'équipe, dans l'application DressMe"><span class="icon">◎</span>Find Similar</span>
      <span class="nav-item active" aria-current="page"><span class="icon">◆</span>AI Stylist</span>
    </nav>
    <div class="sidebar-foot">Démo BO4 · agent LangGraph · garde-robe BO1</div>
  </aside>

  <main class="main">
    <div class="page-head">
      <div>
        <h1>AI Stylist</h1>
        <p id="context">Ton styliste personnel, à partir de ta garde-robe BO1.</p>
      </div>
      <button class="btn btn-ghost" id="reset" type="button">Nouvelle conversation</button>
    </div>
    <div id="chat" aria-live="polite">
      <div class="msg bot">Bonjour ! Dis-moi pour quelle occasion tu veux une tenue, et tes contraintes éventuelles.</div>
    </div>
    <div class="composer">
      <div class="chips" id="chips">
        <button class="chip" type="button">Je veux une tenue</button>
        <button class="chip" type="button">Une tenue pour un entretien demain, sans talons</button>
        <button class="chip" type="button">Une autre</button>
        <button class="chip" type="button">Sans veste</button>
        <button class="chip" type="button">Pour une soirée, pas de noir</button>
        <button class="chip" type="button">J'aime la 1</button>
      </div>
      <form id="form">
        <label for="input" class="muted" hidden>Ta demande</label>
        <input id="input" autocomplete="off" placeholder="Ex. : une tenue pour aller en cours demain, sans jupe">
        <button class="btn btn-olive" id="send" type="submit">Envoyer</button>
      </form>
    </div>
  </main>

  <aside class="side">
    <div class="tabs" role="tablist" aria-label="Panneaux">
      <button class="tab" role="tab" id="tab-backstage" data-tab="backstage" aria-controls="panel-backstage" aria-selected="true" type="button">Coulisses de l'agent</button>
      <button class="tab" role="tab" id="tab-wardrobe" data-tab="wardrobe" aria-controls="panel-wardrobe" aria-selected="false" tabindex="-1" type="button">Garde-robe BO1</button>
    </div>
    <div class="panel" role="tabpanel" id="panel-backstage" aria-labelledby="tab-backstage">
      <div class="block">
        <h3>Graphe LangGraph · nodes du dernier tour en olive</h3>
        <p class="path" id="path"><b>Chemin :</b> aucun tour pour l'instant.</p>
        <div class="graph-tools">
          <button class="btn btn-ghost" id="toggle-graph" type="button" aria-expanded="false" aria-controls="graph-box">Afficher le graphe</button>
        </div>
        <div id="graph-box" hidden>
          <div id="graph"></div>
          <div class="graph-tools"><button class="btn btn-ghost" id="enlarge" type="button">Agrandir</button></div>
        </div>
      </div>
      <div class="block"><h3>Trace du dernier tour</h3><ol class="trace" id="trace"><li class="muted">Aucun tour pour l'instant.</li></ol></div>
      <div class="block"><h3>Demande comprise (mémoire de la conversation)</h3><pre id="request">{}</pre></div>
      <div class="block"><h3>Météo utilisée</h3><div id="weather" class="muted">-</div></div>
      <div class="block"><h3>Profil de style (retours 👍 / 👎)</h3><div id="profile" class="muted">Aucun retour pour l'instant.</div></div>
      <div class="block"><h3>Garde-robe utilisée</h3><div id="wardrobe" class="muted">-</div></div>
    </div>
    <div class="panel" role="tabpanel" id="panel-wardrobe" aria-labelledby="tab-wardrobe" hidden>
      <p class="muted" id="wardrobe-info">Chargement de la garde-robe…</p>
      <div class="wardrobe-grid" id="wardrobe-grid"></div>
    </div>
  </aside>
</div>
<div class="modal" id="graph-modal" hidden role="dialog" aria-modal="true" aria-labelledby="modal-title">
  <div class="modal-box">
    <header><h2 id="modal-title">Graphe LangGraph du Stylist Agent</h2>
      <button class="btn btn-ghost" id="close-modal" type="button">Fermer</button></header>
    <div id="modal-graph"></div>
  </div>
</div>
<script>
const $ = (id) => document.getElementById(id);
let threadId = null;
let wardrobeLoaded = false;
const DEFAULT_CONTEXT = "Ton styliste personnel, à partir de ta garde-robe BO1.";
const LABELS = {color_score: "Couleurs", style_score: "Style", occasion_score: "Occasion", season_score: "Saison"};
const OCCASION_FR = {university: "l'université", work: "le travail", evening: "une soirée", casual: "un moment décontracté"};
const SEASON_FR = {spring: "printemps", summer: "été", autumn: "automne", winter: "hiver"};
const DRESS_FR = {casual: "décontracté", smart_casual: "smart casual", business: "business", formal: "formel"};

function esc(text) {
  const div = document.createElement("div");
  div.textContent = text == null ? "" : String(text);
  return div.innerHTML;
}

function safeHex(hex) {
  return /^#[0-9a-f]{3,8}$/i.test(hex || "") ? hex : "#cccccc";
}

function scrollChat() { $("chat").scrollTop = $("chat").scrollHeight; }

function addMessage(text, who, extraClass) {
  const div = document.createElement("div");
  div.className = `msg ${who} ${extraClass || ""}`;
  div.textContent = text;
  $("chat").appendChild(div);
  scrollChat();
}

// Repli quand une image ne charge pas : pastille de la couleur du vêtement.
window.imgFallback = function (img) {
  const swatch = document.createElement("div");
  swatch.className = "swatch";
  swatch.style.background = safeHex(img.dataset.hex);
  img.replaceWith(swatch);
};

function picture(item) {
  const hex = safeHex(item.color_hex);
  return item.image
    ? `<img src="${esc(item.image)}" alt="${esc(item.name)}" data-hex="${esc(hex)}" onerror="imgFallback(this)">`
    : `<div class="swatch" style="background:${hex}"></div>`;
}

function ring(score, size) {
  const r = (size - 8) / 2, circ = 2 * Math.PI * r;
  const dash = Math.max(0, Math.min(100, score)) / 100 * circ;
  return `<div class="ring" style="width:${size}px;height:${size}px">
    <svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" aria-hidden="true">
      <circle class="track" cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke-width="4"/>
      <circle class="value" cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke-width="4"
              stroke-dasharray="${dash} ${circ}" stroke-linecap="round"/>
    </svg><span>${Math.round(score)}</span></div>`;
}

function actions(o) {
  const bonus = o.personal_bonus
    ? `<span class="done">bonus perso ${o.personal_bonus > 0 ? "+" : ""}${o.personal_bonus}</span>` : "";
  return `<div class="actions" data-rank="${o.rank}">
    <button class="vote" type="button" data-verdict="like">👍 J'aime</button>
    <button class="vote" type="button" data-verdict="dislike">👎 Pas pour moi</button>${bonus}</div>`;
}

function subscoreText(o) {
  return Object.entries(o.subscores).map(([k, v]) => `${LABELS[k] || k} ${Math.round(v)}`).join(" · ");
}

function heroCard(o, request) {
  const occasion = OCCASION_FR[request.occasion];
  const title = occasion ? `Pour ${occasion}` : "Ta tenue";
  const meta = [
    request.season ? `saison : ${SEASON_FR[request.season] || request.season}` : "",
    request.dress_code ? `dress code ${DRESS_FR[request.dress_code] || request.dress_code}` : "",
    o.formality != null ? `formalité ${o.formality}/5` : "",
    o.dress_code_ok === false ? "hors dress code" : "",
  ].filter(Boolean).join(" · ");
  const pieces = o.items.map((i) => `<div class="piece"><span>Pièce</span><b>${esc(i.name)}</b></div>`).join("");
  const why = o.explanations.slice(0, 3).map(esc).join(" · ") || "Classement du moteur BO4.";
  const first = o.items[0] || {};
  return `<article class="hero" aria-label="Tenue n° 1">
    <div class="hero-body">
      <div>
        <span class="eyebrow">Recommandation du stylist · tenue n° 1</span>
        <h2>${esc(title)}</h2>
        <p class="meta">${esc(meta)}</p>
      </div>
      <div class="pieces">${pieces}</div>
      <div class="score-row">${ring(o.score, 64)}
        <div><b>Score de compatibilité</b><small>${esc(subscoreText(o))}</small></div></div>
      ${actions(o)}
    </div>
    <figure class="hero-photo"><div class="frame">${picture(first)}</div>
      <figcaption><span>Pourquoi ça marche</span><p>${why}</p></figcaption></figure>
  </article>`;
}

function compactCard(o) {
  const thumbs = o.items.map((i) => `<div class="thumb-wrap"><div class="thumb">${picture(i)}</div>
    <b>${esc(i.name)}</b><small>${esc(i.category)} · ${esc(i.color)}</small></div>`).join("");
  const bars = Object.entries(o.subscores).map(([k, v]) =>
    `<span>${LABELS[k] || k}</span><span class="bar"><i style="width:${Math.max(0, Math.min(100, v))}%"></i></span><span>${Math.round(v)}</span>`).join("");
  const why = o.explanations.slice(0, 2).map((e) => `<li>${esc(e)}</li>`).join("");
  const tag = [o.formality != null ? `formalité ${o.formality}/5` : "", o.dress_code_ok === false ? "hors dress code" : ""]
    .filter(Boolean).join(" · ");
  return `<article class="outfit-card" aria-label="Tenue n° ${o.rank}">
    <header><h3>Tenue n° ${o.rank}</h3><span class="pill">${o.score}/100</span></header>
    ${tag ? `<span class="muted">${esc(tag)}</span>` : ""}
    <div class="thumbs">${thumbs}</div>
    <div class="bars">${bars}</div>
    ${why ? `<p class="why-title">Pourquoi ça marche</p><ul class="why">${why}</ul>` : ""}
    ${actions(o)}
  </article>`;
}

function addOutfits(outfits, request) {
  if (!outfits.length) return;
  const wrap = document.createElement("div");
  wrap.className = "outfits";
  const others = outfits.slice(1).map(compactCard).join("");
  wrap.innerHTML = heroCard(outfits[0], request || {}) + (others ? `<div class="grid2">${others}</div>` : "");
  $("chat").appendChild(wrap);
  scrollChat();
}

function addAdvice(advice) {
  if (!advice || !advice.answer) return;
  const div = document.createElement("div");
  div.className = "advice";
  const sources = (advice.sources || []).length
    ? `<div class="sources">Sources : ${(advice.sources || []).map(esc).join(" ; ")}</div>` : "";
  div.innerHTML = `<strong>Conseil BO5 (base de connaissances)</strong>${esc(advice.answer)}${sources}`;
  $("chat").appendChild(div);
  scrollChat();
}

// Schéma du graphe : SVG dessiné par le serveur (hors ligne), masqué par défaut.
// Le choix « affiché / masqué » est gardé pour la session (variable, pas de stockage).
let graphVisible = false;
let graphSvg = "";

function drawGraph(svg) {
  if (svg != null) graphSvg = svg;
  if (graphVisible) $("graph").innerHTML = graphSvg;
  if (!$("graph-modal").hidden) $("modal-graph").innerHTML = graphSvg;
}

function showPath(visited) {
  $("path").innerHTML = visited && visited.length
    ? `<b>Chemin :</b> ${visited.map(esc).join(" → ")}`
    : "<b>Chemin :</b> aucun tour pour l'instant.";
}

function setGraphVisible(on) {
  graphVisible = on;
  $("graph-box").hidden = !on;
  $("toggle-graph").textContent = on ? "Masquer le graphe" : "Afficher le graphe";
  $("toggle-graph").setAttribute("aria-expanded", on ? "true" : "false");
  if (on) drawGraph();
}

function openModal() {
  $("modal-graph").innerHTML = graphSvg;
  $("graph-modal").hidden = false;
  $("close-modal").focus();
}

function closeModal() {
  if ($("graph-modal").hidden) return;
  $("graph-modal").hidden = true;
  $("modal-graph").innerHTML = "";
  $("enlarge").focus();
}

// Bulle du bot : seulement le contexte quand des tenues sont affichées en cartes.
function bubbleText(data) {
  let text = data.response || "";
  if (data.advice && data.advice.answer) text = text.split("\n---\n")[0];
  if (!data.outfits || !data.outfits.length) return text;
  const lines = text.split("\n");
  const cut = lines.findIndex((l) => l.startsWith("Voici mes propositions") || l.startsWith("Voici d'autres propositions"));
  const head = cut >= 0 ? lines.slice(0, cut) : lines;
  const only = lines.find((l) => l.startsWith("Je ne propose que"));
  return [...head, ...(only ? [only] : [])].join("\n").trim();
}

function showProfile(p) {
  if (!p || !(p.likes || p.dislikes)) { $("profile").textContent = "Aucun retour pour l'instant."; return; }
  const colors = Object.entries(p.colors || {}).map(([c, v]) => `${esc(c)} ${v > 0 ? "+" : ""}${v}`).join(", ");
  $("profile").innerHTML = `<b>${p.likes}</b> 👍 · <b>${p.dislikes}</b> 👎`
    + (p.liked_items.length ? `<br>Aimés : ${p.liked_items.map(esc).join(", ")}` : "")
    + (p.disliked_items.length ? `<br>Moins aimés : ${p.disliked_items.map(esc).join(", ")}` : "")
    + (colors ? `<br>Couleurs : ${colors}` : "");
}

async function feedback(rank, verdict, box) {
  box.querySelectorAll("button").forEach((b) => { b.disabled = true; });
  try {
    const res = await fetch("/api/feedback", {method: "POST", headers: {"Content-Type": "application/json"},
                                              body: JSON.stringify({thread_id: threadId, rank, verdict})});
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.statusText);
    box.insertAdjacentHTML("beforeend", `<span class="done">${verdict === "like" ? "Noté 👍" : "Noté 👎"}</span>`);
    showProfile(data.profile);
    if (verdict === "dislike") send("Une autre");
  } catch (e) {
    box.insertAdjacentHTML("beforeend", `<span class="done">Erreur : ${esc(e.message)}</span>`);
  }
}

function updateSide(data) {
  showProfile(data.profile);
  drawGraph(data.graph_svg || "");
  showPath(data.visited);
  $("trace").innerHTML = data.trace.map((t) => `<li>${esc(t)}</li>`).join("") || "<li>-</li>";
  $("request").textContent = JSON.stringify(data.request, null, 2);
  const m = data.weather || {};
  if (m.city) {
    const tmin = Math.round(m.t_min), tmax = Math.round(m.t_max);
    const rain = m.rain_probability === null || m.rain_probability === undefined ? (m.rain_code ? "annoncée" : "?") : `${m.rain_probability} %`;
    $("weather").innerHTML = `${esc(m.city)}, ${esc(m.date)} : <b>${tmin} à ${tmax} °C</b>, pluie ${esc(rain)}`
      + `<br><span class="muted">Source : ${esc(m.source || "Open-Meteo")}${m.attribution ? " · " + esc(m.attribution) : ""}</span>`;
    $("context").textContent = `${m.city} · ${tmin} à ${tmax} °C · pluie ${rain} (${m.source || "Open-Meteo"}, prévision du ${m.date})`;
  } else {
    $("weather").textContent = m.unavailable ? "Météo indisponible (aucune source n'a répondu) : saison estimée d'après la date."
      : "Non utilisée pour ce tour (saison demandée ou météo désactivée).";
  }
  const w = data.wardrobe || {};
  if (w.source) {
    const skipped = Object.entries(w.skipped || {}).map(([reason, names]) => `${reason} : ${names.join(", ")}`).join(" | ");
    $("wardrobe").innerHTML = `Source : <b>${esc(w.source)}</b> · ${w.kept} vêtement(s) utilisable(s) sur ${w.received}`
      + (skipped ? `<br>Écartés : ${esc(skipped)}` : "");
  }
}

async function send(message) {
  if (!message.trim()) return;
  addMessage(message, "user");
  $("input").value = "";
  $("send").disabled = true;
  try {
    const res = await fetch("/api/chat", {method: "POST", headers: {"Content-Type": "application/json"},
                                         body: JSON.stringify({message, thread_id: threadId})});
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.statusText);
    threadId = data.thread_id;
    const advice = data.advice || {};
    // Tenues en cartes et conseil BO5 dans son bloc : la bulle ne garde que le contexte.
    const bubble = bubbleText(data);
    if (bubble) addMessage(bubble, "bot", data.error ? "error" : "");
    addOutfits(data.outfits, data.request);
    addAdvice(advice);
    updateSide(data);
  } catch (e) {
    addMessage(`Erreur : ${e.message}`, "bot", "error");
  } finally {
    $("send").disabled = false;
    $("input").focus();
  }
}

// ---------- Onglet « Garde-robe BO1 » (GET /api/wardrobe) ----------
function wardrobeCard(item) {
  const style = item.bo1_style || item.style || "style inconnu";
  return `<div class="w-card"><div class="photo">${picture(item)}</div>
    <div class="body"><div class="cat">${esc(item.category)}</div><div class="name">${esc(item.name)}</div>
    <div class="sub">${esc(item.color)} · ${esc(style)}</div></div></div>`;
}

async function loadWardrobe() {
  $("wardrobe-info").textContent = "Chargement de la garde-robe…";
  $("wardrobe-grid").innerHTML = "";
  try {
    const res = await fetch("/api/wardrobe");
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.statusText);
    const r = data.report || {};
    $("wardrobe-info").textContent = `Source : ${r.source || "BO1"} · ${r.kept} vêtement(s) utilisable(s) sur ${r.received}`;
    $("wardrobe-grid").innerHTML = data.items.map(wardrobeCard).join("");
    wardrobeLoaded = true;
  } catch (e) {
    $("wardrobe-info").textContent = `Garde-robe indisponible : ${e.message}`;
  }
}

function selectTab(name) {
  document.querySelectorAll('[role="tab"]').forEach((tab) => {
    const on = tab.dataset.tab === name;
    tab.setAttribute("aria-selected", on ? "true" : "false");
    tab.tabIndex = on ? 0 : -1;
  });
  document.querySelectorAll('[role="tabpanel"]').forEach((panel) => { panel.hidden = panel.id !== `panel-${name}`; });
  if (name === "wardrobe" && !wardrobeLoaded) loadWardrobe();
}

document.querySelectorAll('[role="tab"]').forEach((tab) => {
  tab.addEventListener("click", () => selectTab(tab.dataset.tab));
  tab.addEventListener("keydown", (e) => {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    const next = tab.dataset.tab === "backstage" ? "wardrobe" : "backstage";
    selectTab(next);
    $(`tab-${next}`).focus();
  });
});

$("form").addEventListener("submit", (e) => { e.preventDefault(); send($("input").value); });
$("chips").addEventListener("click", (e) => { if (e.target.tagName === "BUTTON") send(e.target.textContent); });
$("chat").addEventListener("click", (e) => {
  const verdict = e.target.dataset && e.target.dataset.verdict;
  if (!verdict || !threadId) return;
  const box = e.target.closest(".actions");
  feedback(Number(box.dataset.rank), verdict, box);
});
$("reset").addEventListener("click", () => {
  threadId = null;
  $("chat").innerHTML = '<div class="msg bot">Nouvelle conversation. Pour quelle occasion veux-tu une tenue ?</div>';
  $("trace").innerHTML = '<li class="muted">Aucun tour pour l\'instant.</li>';
  $("request").textContent = "{}";
  $("context").textContent = DEFAULT_CONTEXT;
  wardrobeLoaded = false;
  if (!$("panel-wardrobe").hidden) loadWardrobe();
  showPath([]);
  fetch("/api/graph").then((r) => r.json()).then((d) => drawGraph(d.graph_svg));
});

$("toggle-graph").addEventListener("click", () => setGraphVisible(!graphVisible));
$("enlarge").addEventListener("click", openModal);
$("close-modal").addEventListener("click", closeModal);
$("graph-modal").addEventListener("click", (e) => { if (e.target === $("graph-modal")) closeModal(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModal(); });
fetch("/api/graph").then((r) => r.json()).then((d) => drawGraph(d.graph_svg));
fetch("/api/profile").then((r) => r.json()).then(showProfile);
</script>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Interface web du Stylist Agent")
    parser.add_argument("--port", type=int, default=8060)
    parser.add_argument("--bo1-url", default=None, help="URL de BO1 (défaut : $BO1_API_URL ou :8000)")
    parser.add_argument("--fallback", default=None, help="JSON au format /api/items si BO1 est injoignable")
    parser.add_argument("--no-llm", action="store_true", help="extraction par règles uniquement")
    parser.add_argument("--no-weather", action="store_true", help="saison déduite de la date, sans météo")
    parser.add_argument("--city", default=sa.DEFAULT_CITY, help="ville par défaut pour la météo")
    parser.add_argument("--feedback-file", default="stylist_feedback.json",
                        help="fichier JSON des retours utilisateur (I76/I77)")
    parser.add_argument("--bo5-url", default=None,
                        help="URL de BO5 (RAG) : active le node style_advice (désactivé par défaut)")
    parser.add_argument("--require-auth", action="store_true",
                        help="mode production : jeton Supabase obligatoire (Authorization: Bearer), "
                             "identité vérifiée par GET /api/me de BO1 ; incompatible avec --fallback")
    args = parser.parse_args()
    if args.require_auth and args.fallback:
        parser.error("--require-auth est incompatible avec --fallback : une panne de BO1 ne doit jamais "
                     "basculer en silence sur une garde-robe d'exemple")
    configure(bo1_url=args.bo1_url, fallback=args.fallback, llm=None if args.no_llm else sa.ollama_extract,
              weather=None if args.no_weather else DEFAULT_WEATHER, city=args.city,
              feedback=stylist_feedback.FeedbackStore(args.feedback_file),
              advice=sa.bo5_advice(args.bo5_url), require_auth=args.require_auth)

    import uvicorn
    print(f"Stylist web : http://127.0.0.1:{args.port}")
    uvicorn.run(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
