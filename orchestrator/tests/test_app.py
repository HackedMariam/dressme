"""Tests de l'API FastAPI de l'orchestrateur (services simulés)."""
import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi import testclient  # noqa: E402

import app as orch_app  # noqa: E402
from services import Gateway  # noqa: E402
from test_orchestrator import SERVICES, TOKEN, FakeServices  # noqa: E402


@pytest.fixture
def client():
    fake = FakeServices()
    orch_app.configure(gateway=Gateway(SERVICES, transport=fake), llm=None)
    yield testclient.TestClient(orch_app.app), fake
    orch_app._settings.clear()


@pytest.fixture
def strict():
    fake = FakeServices()
    orch_app.configure(gateway=Gateway(SERVICES, transport=fake), llm=None, require_auth=True)
    yield testclient.TestClient(orch_app.app), fake
    orch_app._settings.clear()


def test_local_chat_without_token(client):
    http, fake = client
    data = http.post("/api/chat", json={"message": "Est-ce que j'ai une jupe noire ?"}).json()
    assert data["route"] == "wardrobe" and data["thread_id"] and data["mode"] == "démo"
    assert data["visited"] == ["route_intent", "wardrobe", "respond"]
    assert 'class="n v"' in data["svg"] and "#556B2F" in data["svg"]
    assert fake.to("bo1")[0]["auth"] is None


def test_token_is_checked_by_bo1_and_forwarded(client):
    http, fake = client
    data = http.post("/api/chat", json={"message": "J'ai un entretien demain, que porter ?", "thread_id": "abc"},
                     headers={"Authorization": f"Bearer {TOKEN}"}).json()
    assert data["route"] == "stylist" and data["thread_id"] == "abc" and data["mode"] == "connecté"
    assert fake.to("bo1")[0]["path"] == "/api/me"
    assert fake.to("stylist")[0]["auth"] == f"Bearer {TOKEN}"
    assert TOKEN not in str(data)


def test_require_auth(strict):
    http, _ = strict
    assert http.post("/api/chat", json={"message": "Bonjour"}).status_code == 401
    bad = http.post("/api/chat", json={"message": "Bonjour"}, headers={"Authorization": "Bearer faux"})
    assert bad.status_code == 401
    malformed = http.post("/api/chat", json={"message": "Bonjour"}, headers={"Authorization": "Token x"})
    assert malformed.status_code == 401
    ok = http.post("/api/chat", json={"message": "Bonjour"}, headers={"Authorization": f"Bearer {TOKEN}"})
    assert ok.status_code == 200 and ok.json()["route"] == "clarify"


def test_bo1_down_gives_503_when_a_token_is_sent(client):
    http, fake = client
    fake.down.add("bo1")
    response = http.post("/api/chat", json={"message": "Bonjour"}, headers={"Authorization": f"Bearer {TOKEN}"})
    assert response.status_code == 503 and "ne répond pas" in response.json()["detail"]


def test_graph_endpoint_and_page(client):
    http, _ = client
    data = http.get("/api/graph", params={"visited": "route_intent,knowledge,respond,bidon"}).json()
    assert data["visited"] == ["route_intent", "knowledge", "respond"]
    assert data["svg"].count('class="n v"') == 3
    page = http.get("/").text
    assert "<svg" in page and "Coulisses" in page and "__GRAPH__" not in page


def test_thread_id_with_colon_is_refused(client):
    http, _ = client
    assert http.post("/api/chat", json={"message": "Bonjour", "thread_id": "a:b"}).status_code == 422


# ------------------------------------------------------------------ connexion et page
import json  # noqa: E402
import re  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402

ENV = {"SUPABASE_URL": "https://exemple.supabase.co", "SUPABASE_ANON_KEY": "anon-public-de-test"}


def test_without_env_the_page_stays_in_demo_mode(client):
    http, _ = client
    config = http.get("/api/config").json()
    assert config == {"auth_available": False, "supabase_url": "", "supabase_anon_key": "", "require_auth": False}
    page = http.get("/").text
    assert "Mode démo : garde-robe d'exemple" in page
    assert '"auth_available": false' in page


def test_with_env_the_page_can_sign_in():
    orch_app.configure(gateway=Gateway(SERVICES, transport=FakeServices()), llm=None, env=ENV)
    try:
        http = testclient.TestClient(orch_app.app)
        assert http.get("/api/config").json()["auth_available"] is True
        page = http.get("/").text
        assert "https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.45.4/dist/umd/supabase.js" in page
        assert "persistSession: false" in page and "Se déconnecter" in page
    finally:
        orch_app._settings.clear()


def test_service_role_like_values_are_never_needed(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("# commentaire\nSUPABASE_URL=https://x.supabase.co\nSUPABASE_ANON_KEY='abc'\nAUTRE=1\n",
                        encoding="utf-8")
    values = orch_app.read_env(env_file)
    assert values["SUPABASE_URL"] == "https://x.supabase.co" and values["SUPABASE_ANON_KEY"] == "abc"
    assert orch_app.public_auth_config({"SUPABASE_URL": "http://pas-https", "SUPABASE_ANON_KEY": "k"})["auth_available"] is False


def page_scripts(page):
    return re.findall(r"<script>(.*?)</script>", page, flags=re.DOTALL)


def test_page_never_stores_the_token_nor_uses_inner_html(client):
    http, _ = client
    page = http.get("/").text
    scripts = "\n".join(page_scripts(page))
    assert "innerHTML" not in scripts and "outerHTML" not in scripts and "insertAdjacentHTML" not in scripts
    assert "localStorage" not in scripts                                      # jeton en mémoire seulement
    assert 'headers.Authorization = "Bearer " + accessToken' in scripts       # envoyé après connexion
    assert "Réponse en anglais (base de connaissances anglophone)" in scripts


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js absent")
def test_page_javascript_syntax(client, tmp_path):
    http, _ = client
    for index, script in enumerate(page_scripts(http.get("/").text)):
        path = tmp_path / f"script{index}.js"
        path.write_text(script, encoding="utf-8")
        result = subprocess.run(["node", "--check", str(path)], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
