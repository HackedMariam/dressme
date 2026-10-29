"""Interface web et API de l'orchestrateur DressMe (port 8070).

- POST /api/chat  : {message, thread_id} ; Authorization: Bearer <jeton Supabase> facultatif en local,
                    obligatoire avec --require-auth. L'identité vient de BO1 GET /api/me.
- GET  /api/graph : SVG du graphe (nodes visités en olive, paramètre ?visited=route_intent,stylist,respond).
- GET  /api/config: configuration publique de la connexion (URL Supabase et clé anon, publiques par nature).
- GET  /          : page de chat au style DressMe : connexion Supabase (supabase-js), panneau « coulisses ».

Connexion : SUPABASE_URL et SUPABASE_ANON_KEY lus dans orchestrator/.env (ignoré par git, voir .env.example).
Sans ce fichier, ou sans connexion, la page reste en mode démo (pas de jeton).

Lancement : python app.py [--port 8070] [--require-auth] [--no-llm] [--services services.yaml]
"""
from __future__ import annotations

import argparse
import json
import os
import uuid
from html import escape
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

import graph as og
from services import Gateway, load_modules, load_services

app = FastAPI(title="DressMe Orchestrator")
_settings: dict[str, Any] = {}
HERE = Path(__file__).resolve().parent
ENV_FILE = HERE / ".env"
MARKDOWN_JS = (HERE / "static" / "markdown.js").read_text(encoding="utf-8")
SUPABASE_JS = "https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.45.4/dist/umd/supabase.js"


def read_env(path: Path = ENV_FILE) -> dict[str, str]:
    """Variables KEY=VALUE d'un fichier .env (sans dépendance) ; l'environnement du processus l'emporte."""
    values: dict[str, str] = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            key, sep, value = line.strip().partition("=")
            if sep and key and not key.startswith("#"):
                values[key.strip()] = value.strip().strip('"').strip("'")
    for key in ("SUPABASE_URL", "SUPABASE_ANON_KEY"):
        if os.environ.get(key):
            values[key] = os.environ[key]
    return values


def public_auth_config(env: dict[str, str]) -> dict:
    """Ce que la page reçoit pour se connecter : URL et clé anon (publique, prévue pour le navigateur)."""
    url, anon = env.get("SUPABASE_URL", ""), env.get("SUPABASE_ANON_KEY", "")
    available = url.startswith("https://") and bool(anon)
    return {"auth_available": available, "supabase_url": url if available else "",
            "supabase_anon_key": anon if available else ""}


def configure(*, gateway: Optional[Gateway] = None, llm: Any = "ollama", require_auth: bool = False,
              env: Optional[dict[str, str]] = None, modules: Optional[dict] = None) -> None:
    gateway = gateway or Gateway(load_services())
    _settings.clear()
    _settings.update(gateway=gateway, require_auth=require_auth, auth=public_auth_config(env or {}),
                     graph=og.build_graph(gateway=gateway, llm=llm, modules=modules))


def settings() -> dict:
    if not _settings:
        configure()
    return _settings


# --------------------------------------------------------------------------------------
# Identité : jeton Supabase vérifié par BO1 (GET /api/me), comme le Stylist
# --------------------------------------------------------------------------------------
def authenticate(authorization: Optional[str]) -> tuple[str, Optional[str]]:
    """(user_id, jeton). Sans jeton : utilisateur « local », sauf avec --require-auth (401)."""
    token = None
    if authorization:
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() != "bearer" or not value.strip():
            raise HTTPException(401, "En-tête Authorization invalide : attendu « Bearer <jeton> ».")
        token = value.strip()
    if token is None:
        if settings()["require_auth"]:
            raise HTTPException(401, "Connexion requise : jeton Supabase manquant.")
        return og.DEFAULT_USER, None
    call = settings()["gateway"].call("bo1", "GET", "/api/me", token=token)
    if call.status in (401, 403):
        raise HTTPException(401, "Jeton refusé par BO1 : reconnecte-toi.")
    if not call.ok or not isinstance(call.data, dict) or not call.data.get("id"):
        raise HTTPException(503, f"Identité indisponible : {call.error or 'réponse de BO1 inattendue'}.")
    user_id = str(call.data["id"])
    if ":" in user_id:
        raise HTTPException(503, "Identifiant utilisateur inattendu renvoyé par BO1.")
    if settings()["require_auth"] and user_id == og.DEFAULT_USER:
        raise HTTPException(503, "BO1 tourne en mode local (sans Supabase) : impossible d'identifier l'utilisateur.")
    return user_id, token


# --------------------------------------------------------------------------------------
# Schéma du graphe en SVG (même rendu que le Stylist : nodes visités en olive)
# --------------------------------------------------------------------------------------
OLIVE, BORDER, INK, MUTED = "#556B2F", "#E2E0D8", "#1C1C1C", "#8C8A82"
SVG_W, SVG_H, BOX_H = 690, 330, 44
ROW = {"top": 56, "mid": 150, "bottom": 244}
BRANCH_W, BRANCH_GAP = 108, 6
BRANCHES = (("stylist", "BO4 Stylist"), ("wardrobe", "BO1 Wardrobe"), ("purchase", "Purchase Redundancy"),
            ("knowledge", "BO5 RAG"), ("external", "modules externes"), ("clarify", "question"))
WIDE_W, CX = 200, SVG_W // 2


def _box(name: str, sub: str, x: float, y: int, w: float, on: bool) -> str:
    return (f'<g class="n{" v" if on else ""}"><rect x="{x:g}" y="{y}" width="{w:g}" height="{BOX_H}" rx="10" '
            f'fill="{OLIVE if on else "none"}" stroke="{OLIVE if on else BORDER}" stroke-width="1.5"/>'
            f'<text class="name" x="{x + w / 2:g}" y="{y + 19}" font-size="12" font-weight="600" text-anchor="middle" '
            f'fill="{"#FFFFFF" if on else INK}">{escape(name)}</text>'
            f'<text class="sub" x="{x + w / 2:g}" y="{y + 35}" font-size="10" text-anchor="middle" '
            f'fill="{"#FFFFFF" if on else MUTED}">{escape(sub)}</text></g>')


def _edge(x1: float, y1: float, x2: float, y2: float, on: bool) -> str:
    color, width = (OLIVE, 2.6) if on else (MUTED, 1.1)
    length = max(((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5, 1e-6)
    ux, uy = (x2 - x1) / length, (y2 - y1) / length
    bx, by, px, py = x2 - ux * 7, y2 - uy * 7, -uy * 3.9, ux * 3.9
    return (f'<g class="e{" v" if on else ""}"><line x1="{x1:g}" y1="{y1:g}" x2="{x2:g}" y2="{y2:g}" stroke="{color}" '
            f'stroke-width="{width}"/><polygon points="{x2:.1f},{y2:.1f} {bx + px:.1f},{by + py:.1f} '
            f'{bx - px:.1f},{by - py:.1f}" fill="{color}"/></g>')


def graph_svg(visited: list[str]) -> str:
    seen = set(visited)
    total = len(BRANCHES) * BRANCH_W + (len(BRANCHES) - 1) * BRANCH_GAP
    left = (SVG_W - total) / 2
    parts = [f'<svg class="gsvg" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {SVG_W} {SVG_H}" width="100%" '
             f'role="img" aria-label="Graphe de l\'orchestrateur : {escape(" → ".join(visited)) or "aucun tour"}" '
             f'font-family="Inter, system-ui, sans-serif">']
    started = bool(visited)
    parts.append(_edge(CX, 34, CX, ROW["top"], started))
    for i, (name, _) in enumerate(BRANCHES):
        bx = left + i * (BRANCH_W + BRANCH_GAP) + BRANCH_W / 2
        parts.append(_edge(CX, ROW["top"] + BOX_H, bx, ROW["mid"], name in seen))
        parts.append(_edge(bx, ROW["mid"] + BOX_H, CX, ROW["bottom"], name in seen and "respond" in seen))
    parts.append(_edge(CX, ROW["bottom"] + BOX_H, CX, SVG_H - 34, "respond" in seen))
    for y, label, on in ((10, "START", started), (SVG_H - 34, "END", "respond" in seen)):
        parts.append(f'<g class="pill{" v" if on else ""}"><rect x="{CX - 30}" y="{y}" width="60" height="24" rx="12" '
                     f'fill="{OLIVE if on else "none"}" stroke="{OLIVE if on else BORDER}"/><text x="{CX}" y="{y + 16}" '
                     f'font-size="11" font-weight="600" text-anchor="middle" fill="{"#FFFFFF" if on else INK}">'
                     f'{label}</text></g>')
    parts.append(_box("route_intent", "règles FR/EN + qwen", CX - WIDE_W / 2, ROW["top"], WIDE_W, "route_intent" in seen))
    for i, (name, sub) in enumerate(BRANCHES):
        parts.append(_box(name, sub, left + i * (BRANCH_W + BRANCH_GAP), ROW["mid"], BRANCH_W, name in seen))
    parts.append(_box("respond", "réponse", CX - WIDE_W / 2, ROW["bottom"], WIDE_W, "respond" in seen))
    parts.append("</svg>")
    return "".join(parts)


# --------------------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------------------
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    thread_id: Optional[str] = Field(default=None, max_length=100)


@app.post("/api/chat")
def api_chat(body: ChatRequest, authorization: Optional[str] = Header(None)) -> dict:
    user_id, token = authenticate(authorization)
    thread_id = body.thread_id or uuid.uuid4().hex[:12]
    if ":" in thread_id:
        raise HTTPException(422, "thread_id ne doit pas contenir « : ».")
    config = og.turn_config(thread_id, user_id, token)
    graph = settings()["graph"]
    graph.invoke(og.new_turn(body.message), config)
    state = graph.get_state(config).values
    visited = og.visited_nodes(state.get("trace") or [])
    return {"thread_id": thread_id, "mode": "connecté" if token else "démo",
            "response": state.get("response", ""), "route": state.get("route"),
            "route_source": state.get("route_source"), "candidates": state.get("candidates") or [],
            "result": state.get("result") or {}, "trace": state.get("trace") or [], "visited": visited,
            "svg": graph_svg(visited)}


@app.get("/api/graph")
def api_graph(visited: str = "") -> dict:
    names = [n for n in visited.split(",") if n in og.NODE_ORDER]
    return {"nodes": list(og.NODE_ORDER), "visited": names, "svg": graph_svg(names)}


@app.get("/api/config")
def api_config() -> dict:
    return {**settings()["auth"], "require_auth": settings()["require_auth"]}


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    boot = json.dumps({**settings()["auth"], "require_auth": settings()["require_auth"]})
    return (PAGE.replace("__GRAPH__", graph_svg([]))
                .replace("__SUPABASE_JS__", SUPABASE_JS)
                .replace("__MARKDOWN_JS__", MARKDOWN_JS)
                .replace("__BOOT__", boot.replace("<", "\\u003c")))


PAGE = r"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DressMe · Orchestrateur</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,600;1,600&family=Inter:wght@400;500;600&display=swap">
<style>
  /* Couleurs et polices du template « DressMe UI Blueprint », comme la page du Stylist. */
  :root { --offwhite:#FAF9F6; --bone:#F0EFEA; --ink:#1C1C1C; --olive:#556B2F; --olive-muted:#E8EDE0;
          --border:#E2E0D8; --muted:#8C8A82; --user-bg:#1C1C1C; --user-ink:#FAF9F6; --danger:#9B3B2E;
          --amber:#8A6D1F; --amber-bg:#F6EFD9; }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) { --offwhite:#141413; --bone:#22221F; --ink:#F0EFEA; --olive-muted:#2A3320;
      --border:#34332E; --muted:#9A988F; --user-bg:#F0EFEA; --user-ink:#1C1C1C; --danger:#E08A7C;
      --amber:#E3C877; --amber-bg:#332B14; color-scheme:dark; }
    :root:not([data-theme="light"]) .gsvg .n:not(.v) text.name, :root:not([data-theme="light"]) .gsvg .pill:not(.v) text { fill:#F0EFEA; }
    :root:not([data-theme="light"]) .gsvg .n:not(.v) rect, :root:not([data-theme="light"]) .gsvg .pill:not(.v) rect { stroke:#34332E; }
  }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--offwhite); color:var(--ink); font:14px/1.5 Inter, system-ui, sans-serif; }
  button { font:inherit; }
  .app { display:grid; grid-template-columns:minmax(0,1fr) minmax(300px,440px); height:100vh; }
  .main { display:flex; flex-direction:column; min-height:0; min-width:0; }
  header { padding:22px 28px 12px; }
  .topbar { display:flex; align-items:center; gap:12px; flex-wrap:wrap; }
  .logo { font-family:"Playfair Display", Georgia, serif; font-size:24px; font-weight:600; margin-right:auto; }
  .logo i { color:var(--ink); } .logo b { color:var(--olive); font-weight:600; }
  .who { font-size:13px; color:var(--muted); }
  .who strong { color:var(--ink); font-weight:600; }
  .demo { font-size:12px; font-weight:600; color:var(--amber); background:var(--amber-bg); border-radius:999px; padding:4px 11px; }
  .btn { border:1px solid var(--border); background:none; color:var(--ink); border-radius:10px; padding:7px 13px; cursor:pointer; }
  .btn:hover { border-color:var(--olive); color:var(--olive); }
  .btn.primary { background:var(--olive); border-color:var(--olive); color:#fff; }
  .btn:disabled { opacity:.5; cursor:not-allowed; }
  header p.lead { margin:8px 0 0; color:var(--muted); font-size:13px; }
  .chips { display:flex; flex-wrap:wrap; gap:6px; margin-top:12px; }
  .chip { border:1px solid var(--border); background:none; color:var(--ink); border-radius:999px; padding:5px 11px;
          font:12px Inter, sans-serif; cursor:pointer; }
  .chip:hover { border-color:var(--olive); color:var(--olive); }
  #log { flex:1; overflow-y:auto; padding:8px 28px 20px; display:flex; flex-direction:column; gap:12px; }
  .msg { max-width:760px; }
  .user { align-self:flex-end; background:var(--user-bg); color:var(--user-ink); padding:10px 14px;
          border-radius:14px 14px 4px 14px; white-space:pre-wrap; }
  .card { align-self:flex-start; background:var(--bone); border:1px solid var(--border); border-radius:12px; padding:14px 16px; }
  .card .head { display:flex; flex-wrap:wrap; gap:6px; align-items:center; margin-bottom:6px; }
  .card .tag { font-size:11px; font-weight:600; letter-spacing:.04em; text-transform:uppercase;
               color:var(--olive); background:var(--olive-muted); border-radius:999px; padding:2px 9px; }
  .card .lang { font-size:11px; color:var(--muted); border:1px solid var(--border); border-radius:999px; padding:1px 8px; }
  .card.err .tag { color:var(--danger); }
  .card .body p { margin:0 0 8px; } .card .body p:last-child { margin-bottom:0; }
  .card .body ul, .card .body ol { margin:4px 0 8px; padding-left:20px; }
  .card .body h4 { margin:8px 0 4px; font-size:14px; }
  .card .body code { font:12px ui-monospace, Consolas, monospace; background:var(--offwhite); padding:0 4px; border-radius:4px; }
  .card .sources { margin-top:10px; padding-top:8px; border-top:1px solid var(--border); font-size:13px; }
  .card .sources ul { margin:4px 0 0; padding-left:20px; }
  .card .why { color:var(--muted); font-size:12px; margin-top:8px; }
  .card .card-login { margin-top:10px; }
  form#f { display:flex; gap:8px; padding:14px 28px 22px; border-top:1px solid var(--border); }
  input { font:inherit; color:var(--ink); background:var(--offwhite); border:1px solid var(--border); border-radius:10px; padding:10px 12px; }
  #q { flex:1; min-width:0; }
  button.send { background:var(--olive); color:#fff; border:0; border-radius:10px; padding:10px 18px; cursor:pointer; }
  button.send:disabled { opacity:.5; }
  aside { border-left:1px solid var(--border); padding:22px 20px; overflow-y:auto; min-width:0; }
  aside h2 { font-family:"Playfair Display", Georgia, serif; font-size:18px; margin:0 0 4px; }
  aside .muted { color:var(--muted); font-size:12px; margin:0 0 12px; }
  #trace { font:12px/1.55 ui-monospace, Consolas, monospace; background:var(--bone); border:1px solid var(--border);
           border-radius:10px; padding:10px 12px; white-space:pre-wrap; word-break:break-word; margin-top:14px; }
  /* Écran de connexion */
  .overlay { position:fixed; inset:0; background:rgba(20,20,19,.55); display:none; align-items:center; justify-content:center; padding:16px; }
  .overlay.open { display:flex; }
  .login { width:100%; max-width:380px; background:var(--offwhite); border:1px solid var(--border); border-radius:14px; padding:24px; }
  .login h2 { font-family:"Playfair Display", Georgia, serif; margin:0 0 4px; font-size:22px; }
  .login p { margin:0 0 16px; color:var(--muted); font-size:13px; }
  .login label { display:block; font-size:12px; font-weight:600; margin:10px 0 4px; }
  .login input { width:100%; }
  .login .row { display:flex; gap:8px; justify-content:flex-end; margin-top:18px; }
  .login .error { color:var(--danger); font-size:13px; min-height:18px; margin-top:10px; }
  @media (max-width: 860px) { .app { grid-template-columns:1fr; height:auto; } aside { border-left:0; border-top:1px solid var(--border); }
    #log { min-height:50vh; } header, #log, form#f { padding-left:16px; padding-right:16px; } }
</style>
</head>
<body>
<div class="app">
  <section class="main">
    <header>
      <div class="topbar">
        <div class="logo"><i>Dress</i><b>Me</b> · orchestrateur</div>
        <span class="demo" id="demo">Mode démo : garde-robe d'exemple</span>
        <span class="who" id="who" hidden>Connecté : <strong id="email"></strong></span>
        <button class="btn primary" id="open-login" type="button">Se connecter</button>
        <button class="btn" id="logout" type="button" hidden>Se déconnecter</button>
      </div>
      <p class="lead">Une seule conversation : tenues (BO4 Stylist), garde-robe (BO1 Wardrobe), achats (Purchase Redundancy) et conseils (BO5 RAG).</p>
      <div class="chips">
        <button class="chip" type="button">J'ai un entretien demain, que porter ?</button>
        <button class="chip" type="button">Est-ce que j'ai une jupe noire ?</button>
        <button class="chip" type="button">Est-ce que je devrais acheter une veste en cuir noire à 80 € ?</button>
        <button class="chip" type="button">Comment porter un col roulé noir avec un pantalon large ?</button>
      </div>
    </header>
    <div id="log" aria-live="polite"></div>
    <form id="f">
      <input id="q" autocomplete="off" placeholder="Écris ta demande…" aria-label="Message">
      <button class="send" id="send">Envoyer</button>
    </form>
  </section>
  <aside>
    <h2>Coulisses</h2>
    <p class="muted">Chemin du dernier message dans le graphe LangGraph (en olive) et appels aux services.</p>
    <div id="graph">__GRAPH__</div>
    <div id="trace">Aucun message pour l'instant.</div>
  </aside>
</div>

<div class="overlay" id="overlay" role="dialog" aria-modal="true" aria-labelledby="login-title">
  <form class="login" id="login-form">
    <h2 id="login-title">Connexion</h2>
    <p>Compte DressMe (Supabase). Le jeton de session reste dans cette page, jamais enregistré.</p>
    <label for="login-email">E-mail</label>
    <input id="login-email" type="email" autocomplete="username" required>
    <label for="login-password">Mot de passe</label>
    <input id="login-password" type="password" autocomplete="current-password" required>
    <div class="error" id="login-error" role="alert"></div>
    <div class="row">
      <button class="btn" type="button" id="cancel-login">Rester en mode démo</button>
      <button class="btn primary" type="submit" id="do-login">Se connecter</button>
    </div>
  </form>
</div>

<script>__MARKDOWN_JS__</script>
<script src="__SUPABASE_JS__"></script>
<script>
  "use strict";
  // Configuration publique (URL Supabase, clé anon) fournie par le serveur depuis orchestrator/.env.
  const BOOT = __BOOT__;
  const $ = (id) => document.getElementById(id);
  const log = $("log"), q = $("q"), send = $("send");
  const LABELS = { stylist: "BO4 Stylist", wardrobe: "BO1 Wardrobe", purchase: "Purchase Redundancy", knowledge: "BO5 RAG",
                   clarify: "Clarification" };
  let accessToken = null;    // jeton de session : en mémoire seulement, jamais dans le stockage du navigateur
  let threadId = null;
  let client = null;

  // ---------------------------------------------------------------- connexion (supabase-js)
  const memoryStorage = (() => { const m = new Map(); return {
    getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, v) => { m.set(k, v); }, removeItem: (k) => { m.delete(k); } }; })();
  if (BOOT.auth_available && window.supabase && window.supabase.createClient) {
    client = window.supabase.createClient(BOOT.supabase_url, BOOT.supabase_anon_key, {
      auth: { persistSession: false, autoRefreshToken: true, detectSessionInUrl: false, storage: memoryStorage } });
    client.auth.onAuthStateChange((_event, session) => { setSession(session); });
  } else {
    $("open-login").disabled = true;
    $("open-login").title = BOOT.auth_available ? "supabase-js n'a pas pu être chargé" : "Connexion indisponible : orchestrator/.env non configuré";
  }

  function setSession(session) {
    const changed = (session ? session.access_token : null) !== accessToken;
    accessToken = session ? session.access_token : null;
    const email = session && session.user ? session.user.email || "" : "";
    $("demo").hidden = Boolean(accessToken);
    $("who").hidden = !accessToken;
    $("email").textContent = email;
    $("open-login").hidden = Boolean(accessToken);
    $("logout").hidden = !accessToken;
    if (changed) threadId = null;   // un nouvel utilisateur commence un nouveau fil
  }
  function openLogin() { $("login-error").textContent = ""; $("overlay").classList.add("open"); $("login-email").focus(); }
  function closeLogin() { $("overlay").classList.remove("open"); $("login-password").value = ""; }
  $("open-login").addEventListener("click", openLogin);
  $("cancel-login").addEventListener("click", closeLogin);
  $("overlay").addEventListener("keydown", (e) => { if (e.key === "Escape") closeLogin(); });
  $("login-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!client) return;
    $("do-login").disabled = true;
    $("login-error").textContent = "";
    try {
      const { data, error } = await client.auth.signInWithPassword({ email: $("login-email").value.trim(), password: $("login-password").value });
      if (error) { $("login-error").textContent = "Connexion refusée : vérifie l'e-mail et le mot de passe."; return; }
      setSession(data.session);
      closeLogin();
      note("Connecté. Les réponses utilisent maintenant ta vraie garde-robe.");
    } catch (err) {
      $("login-error").textContent = "Supabase ne répond pas.";
    } finally { $("do-login").disabled = false; }
  });
  $("logout").addEventListener("click", async () => {
    try { if (client) await client.auth.signOut(); } catch (err) { /* le jeton est effacé quand même */ }
    setSession(null);
    note("Déconnecté : retour au mode démo.");
  });

  // ---------------------------------------------------------------- conversation
  function note(text) {
    const div = document.createElement("div");
    div.className = "msg card";
    div.textContent = text;
    log.appendChild(div); log.scrollTop = log.scrollHeight;
  }
  function addUser(text) {
    const div = document.createElement("div");
    div.className = "msg user"; div.textContent = text;
    log.appendChild(div); log.scrollTop = log.scrollHeight;
  }
  function addCard(data) {
    const res = data.result || {};
    const card = document.createElement("div");
    card.className = "msg card" + (res.ok === false ? " err" : "");
    const head = document.createElement("div"); head.className = "head";
    const tag = document.createElement("span"); tag.className = "tag";
    tag.textContent = LABELS[data.route] || res.label || data.route || "Réponse";
    head.appendChild(tag);
    const details = res.details || {};
    const isBo5 = data.route === "knowledge" && res.ok !== false && typeof details.answer === "string";
    if (isBo5) {
      const lang = document.createElement("span"); lang.className = "lang";
      lang.textContent = "Réponse en anglais (base de connaissances anglophone)";
      head.appendChild(lang);
    }
    card.appendChild(head);
    const body = document.createElement("div"); body.className = "body";
    body.appendChild(window.DressMeMarkdown.render(isBo5 ? details.answer : data.response, document));
    card.appendChild(body);
    if (details.login_required && !accessToken) {
      // Service protégé et aucune session : bouton de connexion directement dans la carte.
      const login = document.createElement("button");
      login.type = "button"; login.className = "btn primary card-login"; login.textContent = "Se connecter";
      if (client) login.addEventListener("click", openLogin);
      else { login.disabled = true; login.title = "Connexion indisponible : orchestrator/.env non configuré"; }
      card.appendChild(login);
    }
    if (isBo5) {
      const box = document.createElement("div"); box.className = "sources";
      const sources = details.sources || [], masked = details.masked_sources || 0;
      const title = document.createElement("strong");
      title.textContent = sources.length ? "Sources citées"
        : masked ? masked + " source(s) citée(s), toutes au titre peu fiable (masquées) : conseil à vérifier."
        : "Aucune source citée : conseil à prendre avec prudence.";
      box.appendChild(title);
      if (sources.length) {
        const ul = document.createElement("ul");
        sources.forEach((s) => { const li = document.createElement("li"); li.textContent = s; ul.appendChild(li); });
        box.appendChild(ul);
        if (masked) {
          const m = document.createElement("div"); m.className = "why";
          m.textContent = masked + " autre(s) source(s) citée(s) au titre peu fiable masquée(s).";
          box.appendChild(m);
        }
      }
      card.appendChild(box);
    }
    const why = document.createElement("div"); why.className = "why";
    why.textContent = "Routage : " + data.route_source + (data.candidates.length ? " (indices : " + data.candidates.join(", ") + ")" : "")
      + " · " + (data.mode === "connecté" ? "connecté" : "mode démo");
    card.appendChild(why);
    log.appendChild(card); log.scrollTop = log.scrollHeight;
  }
  function showGraph(svgText) {
    // SVG produit par ce serveur ; analysé comme XML puis importé (aucune insertion de HTML brut).
    const doc = new DOMParser().parseFromString(svgText, "image/svg+xml");
    const graph = $("graph");
    graph.replaceChildren(document.importNode(doc.documentElement, true));
  }
  async function ask(message) {
    addUser(message);
    send.disabled = true;
    const headers = { "Content-Type": "application/json" };
    if (accessToken) headers.Authorization = "Bearer " + accessToken;
    try {
      const r = await fetch("/api/chat", { method: "POST", headers, body: JSON.stringify({ message, thread_id: threadId }) });
      const data = await r.json();
      if (!r.ok) {
        const err = document.createElement("div"); err.className = "msg card err";
        err.textContent = typeof data.detail === "string" ? data.detail : "Erreur HTTP " + r.status;
        log.appendChild(err);
        if (r.status === 401 && client) openLogin();
        return;
      }
      threadId = data.thread_id;
      addCard(data);
      showGraph(data.svg);
      $("trace").textContent = data.trace.join("\n");
    } catch (e) {
      note("L'orchestrateur ne répond pas.");
    } finally { send.disabled = false; q.focus(); }
  }
  $("f").addEventListener("submit", (e) => { e.preventDefault(); const m = q.value.trim(); if (m) { q.value = ""; ask(m); } });
  document.querySelectorAll(".chip").forEach((b) => b.addEventListener("click", () => ask(b.textContent)));
  setSession(null);
  if (BOOT.require_auth) { $("demo").textContent = "Connexion requise"; if (client) openLogin(); }
</script>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Orchestrateur DressMe (LangGraph)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8070)
    parser.add_argument("--services", default=None, help="fichier de services (défaut : services.yaml)")
    parser.add_argument("--require-auth", action="store_true", help="jeton Supabase obligatoire")
    parser.add_argument("--no-llm", action="store_true", help="routage par règles seulement (pas d'Ollama)")
    args = parser.parse_args()
    services = load_services(args.services) if args.services else load_services()
    modules = load_modules(args.services) if args.services else load_modules()
    configure(gateway=Gateway(services), llm=None if args.no_llm else "ollama", require_auth=args.require_auth,
              env=read_env(), modules=modules)
    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
