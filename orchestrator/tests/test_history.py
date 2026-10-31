"""Historique de conversation (Supabase simulé, sans réseau) et mémoire persistante de l'orchestrateur.

Le faux Supabase imite PostgREST et la RLS de docs/chat_history.sql : chaque jeton ne voit, n'écrit et ne
supprime que les lignes de son utilisatrice ; il refuse toute clé autre que la clé anon.
"""
import json
import urllib.parse
import uuid

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi import testclient  # noqa: E402

import app as orch_app  # noqa: E402
import graph as og  # noqa: E402
from history import ChatHistory  # noqa: E402
from services import Gateway  # noqa: E402
from test_orchestrator import SERVICES, TOKEN, WARDROBE, FakeServices  # noqa: E402

ANON = "cle-anon-publique"
BOB_TOKEN = "jeton-secret-bob"
USERS = {TOKEN: "uuid-alice", BOB_TOKEN: "uuid-bob"}


class TwoUsers(FakeServices):
    """BO1 simulé qui connaît Alice (TOKEN) et Bob (BOB_TOKEN)."""

    def __call__(self, request, timeout):
        if request.full_url.startswith("http://bo1.test") and request.get_header("Authorization") == f"Bearer {BOB_TOKEN}":
            path = request.full_url.split(".test", 1)[1]
            self.calls.append({"host": "bo1", "path": path, "body": None, "auth": f"Bearer {BOB_TOKEN}"})
            return 200, json.dumps({"id": "uuid-bob"} if path == "/api/me" else WARDROBE).encode()
        return super().__call__(request, timeout)


class FakeSupabase:
    """PostgREST minimal pour chat_threads et chat_messages, avec la RLS (auth.uid() = user_id)."""

    def __init__(self):
        self.threads, self.messages, self.requests = [], [], []
        self.down = False
        self.fail_with = None       # (statut HTTP, code PostgREST) renvoyé à toutes les requêtes
        self.clock = 0

    def tick(self):
        self.clock += 1
        return f"2026-11-01T10:00:{self.clock:02d}+00:00"

    def __call__(self, request, timeout):
        headers = {k.lower(): v for k, v in request.header_items()}
        self.requests.append({"method": request.get_method(), "url": request.full_url, "headers": headers})
        if self.down:
            raise ConnectionError("Supabase injoignable")
        if self.fail_with:
            status, code = self.fail_with
            return status, json.dumps({"code": code, "message": f"erreur simulée {code}"}).encode()
        if headers.get("apikey") != ANON:
            return 401, b'{"message": "Invalid API key"}'
        uid = USERS.get(headers.get("authorization", "").removeprefix("Bearer "))
        if uid is None:
            return 401, b'{"message": "JWT invalid"}'
        parsed = urllib.parse.urlparse(request.full_url)
        table = parsed.path.rsplit("/", 1)[-1]
        query = dict(urllib.parse.parse_qsl(parsed.query))
        body = json.loads(request.data) if request.data else None
        method = request.get_method()
        if table == "chat_threads" and method == "GET":
            rows = sorted((t for t in self.threads if t["user_id"] == uid), key=lambda t: t["updated_at"], reverse=True)
            return 200, json.dumps([{k: t[k] for k in ("id", "title", "created_at", "updated_at")} for t in rows]).encode()
        if table == "chat_threads" and method == "POST":
            now = self.tick()
            row = {"id": str(uuid.uuid4()), "user_id": uid, "title": body["title"], "created_at": now, "updated_at": now}
            self.threads.append(row)
            return 201, json.dumps([{"id": row["id"]}]).encode()
        if table == "chat_threads" and method == "DELETE":
            mine = {t["id"] for t in self.threads if t["user_id"] == uid}
            self.threads = [t for t in self.threads if t["id"] not in mine]
            self.messages = [m for m in self.messages if m["thread_id"] not in mine]   # on delete cascade
            return 204, b""
        if table == "chat_messages" and method == "GET":
            thread = query["thread_id"].removeprefix("eq.")
            rows = [m for m in self.messages if m["thread_id"] == thread and m["user_id"] == uid]
            return 200, json.dumps([{k: m[k] for k in ("role", "content", "route", "created_at")} for m in rows]).encode()
        if table == "chat_messages" and method == "POST":
            if len({frozenset(row) for row in body}) > 1:      # règle réelle de PostgREST sur les envois groupés
                return 400, b'{"code": "PGRST102", "message": "All object keys must match"}'
            for row in body:   # clé étrangère composite (thread_id, user_id) : seulement ses propres fils
                owner = next((t for t in self.threads if t["id"] == row["thread_id"]), None)
                if owner is None or owner["user_id"] != uid:
                    return 409, b'{"message": "violates foreign key constraint"}'
            for row in body:
                now = self.tick()
                self.messages.append({**row, "route": row.get("route"), "user_id": uid, "created_at": now})
                next(t for t in self.threads if t["id"] == row["thread_id"])["updated_at"] = now
            return 201, b""
        return 404, b"{}"


@pytest.fixture
def env(tmp_path):
    services, supabase = TwoUsers(), FakeSupabase()

    def start(checkpointer=None):
        orch_app.configure(gateway=Gateway(SERVICES, transport=services), llm=None,
                           history=ChatHistory("https://projet.supabase.co", ANON, transport=supabase),
                           checkpointer=checkpointer)
        return testclient.TestClient(orch_app.app)
    yield start, services, supabase
    orch_app._settings.clear()


def chat(http, message, token=TOKEN, thread_id=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    response = http.post("/api/chat", json={"message": message, "thread_id": thread_id}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def auth(token=TOKEN):
    return {"Authorization": f"Bearer {token}"}


def test_turn_is_saved_and_the_stylist_gets_the_saved_thread_id(env):
    start, services, supabase = env
    http = start()
    data = chat(http, "J'ai un entretien demain, que porter ?")
    assert data["history"] == {"enabled": True, "saved": True, "error": None, "kind": None}
    thread = supabase.threads[0]
    assert data["thread_id"] == thread["id"] and thread["title"] == "J'ai un entretien demain, que porter ?"
    assert [m["role"] for m in supabase.messages] == ["user", "assistant"]
    assert supabase.messages[1]["route"] == "stylist" and supabase.messages[1]["content"] == data["response"]
    assert services.to("stylist")[0]["body"]["thread_id"] == thread["id"]      # le contexte suit le fil enregistré


def test_only_the_anon_key_and_the_user_token_reach_supabase(env):
    start, _, supabase = env
    http = start()
    chat(http, "J'ai un entretien demain, que porter ?")
    http.get("/api/history", headers=auth())
    assert supabase.requests
    for request in supabase.requests:
        assert request["headers"]["apikey"] == ANON
        assert request["headers"]["authorization"] == f"Bearer {TOKEN}"
        assert "service_role" not in json.dumps(request)


def test_two_users_never_see_each_other(env):
    start, _, supabase = env
    http = start()
    alice = chat(http, "J'ai un entretien demain, que porter ?")
    bob = chat(http, "Est-ce que j'ai une jupe noire ?", token=BOB_TOKEN)
    alice_threads = http.get("/api/history", headers=auth()).json()["threads"]
    bob_threads = http.get("/api/history", headers=auth(BOB_TOKEN)).json()["threads"]
    assert [t["id"] for t in alice_threads] == [alice["thread_id"]]
    assert [t["id"] for t in bob_threads] == [bob["thread_id"]]
    # Bob ne lit pas le fil d'Alice, n'y écrit pas, et son effacement ne touche pas Alice
    assert http.get(f"/api/history/{alice['thread_id']}", headers=auth(BOB_TOKEN)).json()["messages"] == []
    sneaky = chat(http, "Est-ce que j'ai une jupe noire ?", token=BOB_TOKEN, thread_id=alice["thread_id"])
    assert sneaky["history"]["saved"] is False
    assert http.delete("/api/history", headers=auth(BOB_TOKEN)).json() == {"deleted": 1}
    assert len(http.get(f"/api/history/{alice['thread_id']}", headers=auth()).json()["messages"]) == 2
    assert {m["user_id"] for m in supabase.messages} == {"uuid-alice"}


def test_logout_then_login_brings_the_conversation_back(env):
    start, _, _ = env
    http = start()
    first = chat(http, "J'ai un entretien demain, que porter ?")
    chat(http, "Est-ce que j'ai une jupe noire ?", thread_id=first["thread_id"])
    # déconnexion : la page oublie tout (thread_id compris) ; reconnexion : elle redemande l'historique
    threads = http.get("/api/history", headers=auth()).json()["threads"]
    assert threads[0]["id"] == first["thread_id"]
    messages = http.get(f"/api/history/{threads[0]['id']}", headers=auth()).json()["messages"]
    assert [(m["role"], m["content"]) for m in messages][::2] == [
        ("user", "J'ai un entretien demain, que porter ?"), ("user", "Est-ce que j'ai une jupe noire ?")]
    assert [m["role"] for m in messages] == ["user", "assistant", "user", "assistant"]


def test_server_restart_keeps_the_agent_context(env, tmp_path):
    start, services, _ = env
    db = tmp_path / "checkpoints.sqlite"
    http = start(og.sqlite_checkpointer(db))
    first = chat(http, "J'ai un entretien demain, que porter ?")
    http = start(og.sqlite_checkpointer(db))                     # « redémarrage » : nouvelle mémoire, même fichier
    again = chat(http, "une autre", thread_id=first["thread_id"])
    assert again["route"] == "stylist" and "suite" in again["route_source"]   # contexte relu depuis le fichier
    raw = db.read_bytes() + b"".join(p.read_bytes() for p in tmp_path.glob("checkpoints.sqlite-*"))
    assert TOKEN.encode() not in raw and b"__bo1_token" not in raw            # jamais le jeton dans la mémoire


def test_history_failure_never_blocks_the_answer(env):
    start, _, supabase = env
    http = start()
    supabase.down = True
    data = chat(http, "J'ai un entretien demain, que porter ?")
    assert data["response"] and data["route"] == "stylist"
    assert data["history"]["saved"] is False and "injoignable" in data["history"]["error"]
    assert data["history"]["kind"] == "réseau"
    supabase.down = False
    first = chat(http, "Est-ce que j'ai une jupe noire ?")
    supabase.down = True                                          # panne après la création du fil
    later = chat(http, "Est-ce que j'ai une jupe noire ?", thread_id=first["thread_id"])
    assert later["response"] and later["history"]["saved"] is False


def test_clear_history_removes_threads_messages_and_agent_memory(env):
    start, _, supabase = env
    http = start()
    data = chat(http, "J'ai un entretien demain, que porter ?")
    chat(http, "Est-ce que j'ai une jupe noire ?")
    assert http.delete("/api/history", headers=auth()).json() == {"deleted": 2}
    assert supabase.threads == [] and supabase.messages == []
    assert http.get("/api/history", headers=auth()).json()["threads"] == []
    memory = orch_app.settings()["graph"].get_state(og.turn_config(data["thread_id"], "uuid-alice"))
    assert not memory.values                                      # mémoire de l'orchestrateur effacée aussi


def test_demo_mode_has_no_history(env):
    start, _, supabase = env
    http = start()
    data = chat(http, "Est-ce que j'ai une jupe noire ?", token=None)
    assert data["history"] == {"enabled": False, "saved": False, "error": None, "kind": None}
    assert supabase.requests == []
    assert http.get("/api/history").status_code == 401
    assert http.delete("/api/history").status_code == 401


def test_history_disabled_without_supabase_config():
    orch_app.configure(gateway=Gateway(SERVICES, transport=TwoUsers()), llm=None, env={})
    try:
        http = testclient.TestClient(orch_app.app)
        assert chat(http, "Est-ce que j'ai une jupe noire ?")["history"]["enabled"] is False
        assert http.get("/api/history", headers=auth()).status_code == 503
    finally:
        orch_app._settings.clear()


def test_invalid_thread_id_is_rejected(env):
    start, _, _ = env
    http = start()
    assert http.get("/api/history/abc;drop", headers=auth()).status_code == 422


def test_page_has_history_controls_with_in_page_confirmation(env):
    start, _, _ = env
    html = start().get("/").text
    for element in ('id="history"', 'id="new-thread"', 'id="clear-history"', 'id="confirm-clear"', 'id="do-clear"'):
        assert element in html
    assert "confirm(" not in html and "alert(" not in html       # aucune boîte de dialogue du navigateur


def test_question_and_answer_rows_have_identical_keys(env):
    """Panne réelle du 31/10 : la ligne de la question n'avait pas « route » -> 400 PGRST102 sur chat_messages."""
    start, _, supabase = env
    data = chat(start(), "J'ai un entretien demain, que porter ?")
    assert data["history"]["saved"] is True
    post = next(r for r in supabase.requests if r["method"] == "POST" and r["url"].endswith("/chat_messages"))
    assert "/rest/v1/chat_messages" in post["url"] and post["headers"]["prefer"] == "return=minimal"
    create = next(r for r in supabase.requests if r["method"] == "POST" and "/chat_threads" in r["url"])
    assert create["headers"]["prefer"] == "return=representation"
    assert supabase.requests.index(create) < supabase.requests.index(post)     # le fil avant les messages
    rows = supabase.messages
    assert set(rows[0]) == set(rows[1]) and rows[0]["route"] is None


@pytest.mark.parametrize("status, code, kind", [
    (401, "42501", "droits"), (403, "42501", "droits"), (404, "PGRST205", "table"), (400, "PGRST102", "requête"),
    (401, "PGRST301", "session"),
])
def test_history_error_kinds(env, status, code, kind):
    start, _, supabase = env
    http = start()
    supabase.fail_with = (status, code)
    data = chat(http, "J'ai un entretien demain, que porter ?")
    assert data["response"] and data["history"]["saved"] is False
    assert data["history"]["kind"] == kind and code in data["history"]["error"]


def test_tls_failure_is_reported_as_tls(env):
    import ssl
    import urllib.error
    start, _, supabase = env
    http = start()

    def refuse(request, timeout):
        raise urllib.error.URLError(ssl.SSLCertVerificationError("[SSL: CERTIFICATE_VERIFY_FAILED]"))
    orch_app.settings()["history"].transport = refuse
    data = chat(http, "J'ai un entretien demain, que porter ?")
    assert data["history"]["kind"] == "tls" and "certificat TLS refusé" in data["history"]["error"]


def test_page_explains_each_failure_kind(env):
    start, _, _ = env
    html = start().get("/").text
    for text in ("droits refusés par Supabase", "table d'historique introuvable", "réseau : Supabase injoignable",
                 "certificat TLS refusé"):
        assert text in html


def test_new_conversation_banner_is_removed_by_the_first_message(env):
    """Le bandeau « Nouvelle conversation… » disparaît au premier message et n'apparaît pas en rouvrant un fil."""
    start, _, _ = env
    html = start().get("/").text
    ask = html[html.index("async function ask(message)"):]
    assert ask.index("dropNewThreadNote();") < ask.index("addUser(message);")
    reopen = html[html.index("async function openThread(id)"):html.index("$(\"new-thread\")")]
    assert "newThreadNote = null;" in reopen and "note(" not in reopen.split("catch")[0]
    assert 'newThreadNote = note("Nouvelle conversation' in html
