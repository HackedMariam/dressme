"""Réinitialisation des goûts : POST /api/profile/reset et option reset_profile de DELETE /api/history.
Le jeton de l'utilisatrice est transmis tel quel au Stylist, qui identifie l'utilisatrice auprès de BO1."""
import json
import re

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi import testclient  # noqa: E402

import app as orch_app  # noqa: E402
from history import ChatHistory  # noqa: E402
from services import Gateway  # noqa: E402
from test_history import ANON, BOB_TOKEN, FakeSupabase, TwoUsers, auth, chat  # noqa: E402
from test_orchestrator import SERVICES, TOKEN  # noqa: E402


class ResetServices(TwoUsers):
    """Stylist simulé qui connaît la route de réinitialisation et garde le jeton reçu pour chaque appel."""

    def __init__(self):
        super().__init__()
        self.resets = []
        self.stylist_reset_down = False

    def __call__(self, request, timeout):
        if request.full_url.startswith("http://stylist.test/api/profile/reset"):
            self.calls.append({"host": "stylist", "path": "/api/profile/reset", "body": None,
                               "auth": request.get_header("Authorization")})
            if self.stylist_reset_down:
                return 503, b'{"detail": "BO1 injoignable"}'
            self.resets.append(request.get_header("Authorization"))
            return 200, json.dumps({"removed": 4, "profile": {"likes": 0, "dislikes": 0}}).encode()
        return super().__call__(request, timeout)


@pytest.fixture
def env():
    services, supabase = ResetServices(), FakeSupabase()
    orch_app.configure(gateway=Gateway(SERVICES, transport=services), llm=None,
                       history=ChatHistory("https://projet.supabase.co", ANON, transport=supabase))
    yield testclient.TestClient(orch_app.app), services, supabase
    orch_app._settings.clear()


def test_profile_reset_requires_a_token(env):
    http, services, _ = env
    assert http.post("/api/profile/reset").status_code == 401
    assert services.resets == []                                             # le Stylist n'est même pas appelé


def test_profile_reset_forwards_the_callers_own_token(env):
    http, services, _ = env
    assert http.post("/api/profile/reset", headers=auth()).json() == {"removed": 4}
    assert http.post("/api/profile/reset", headers=auth(BOB_TOKEN)).json() == {"removed": 4}
    assert services.resets == [f"Bearer {TOKEN}", f"Bearer {BOB_TOKEN}"]     # chacune pour son propre compte


def test_profile_reset_reports_a_stylist_failure(env):
    http, services, _ = env
    services.stylist_reset_down = True
    response = http.post("/api/profile/reset", headers=auth())
    assert response.status_code == 502 and "Réinitialisation des goûts impossible" in response.json()["detail"]


def test_clearing_history_does_not_touch_the_taste_profile_by_default(env):
    http, services, supabase = env
    chat(http, "J'ai un entretien demain, que porter ?")
    assert http.delete("/api/history", headers=auth()).json() == {"deleted": 1}
    assert services.resets == [] and supabase.threads == []


def test_clearing_history_can_also_reset_the_taste_profile(env):
    http, services, supabase = env
    chat(http, "J'ai un entretien demain, que porter ?")
    chat(http, "Est-ce que j'ai une jupe noire ?", token=BOB_TOKEN)
    result = http.delete("/api/history?reset_profile=true", headers=auth()).json()
    assert result == {"deleted": 1, "profile_reset": True, "profile_removed": 4}
    assert services.resets == [f"Bearer {TOKEN}"]                            # Alice seulement, pas Bob
    assert [t["user_id"] for t in supabase.threads] == ["uuid-bob"]          # le fil de Bob est intact


def test_stylist_failure_does_not_undo_the_history_deletion(env):
    http, services, supabase = env
    chat(http, "J'ai un entretien demain, que porter ?")
    services.stylist_reset_down = True
    result = http.delete("/api/history?reset_profile=true", headers=auth()).json()
    assert result["deleted"] == 1 and result["profile_reset"] is False and "profile_error" in result
    assert supabase.threads == []                                            # l'historique, lui, est bien effacé


def test_delete_history_needs_a_token_even_with_the_option(env):
    http, services, _ = env
    assert http.delete("/api/history?reset_profile=true").status_code == 401 and services.resets == []


# ---------------------------------------------------------------- la page
def test_page_offers_the_reset_checkbox_inside_the_confirmation(env):
    http, _, _ = env
    html = http.get("/").text
    confirm = html[html.index('id="confirm-clear"'):html.index('id="do-clear"')]
    assert 'id="reset-profile"' in confirm and 'type="checkbox"' in confirm and "goûts" in confirm
    assert "?reset_profile=true" in html


def test_clear_button_is_away_from_new_conversation_and_the_confirmation_is_really_hidden(env):
    http, _, _ = env
    html = http.get("/").text
    rows = re.findall(r'<div class="row[^"]*">(.*?)</div>', html[html.index('id="history"'):], re.S)
    new_row = next(r for r in rows if 'id="new-thread"' in r)
    clear_row = next(r for r in rows if 'id="clear-history"' in r)
    assert new_row is not clear_row and 'id="clear-history"' not in new_row
    assert html.index('id="threads"') < html.index('id="clear-history"')      # sous la liste des conversations
    assert "danger-zone" in html and "[hidden] { display:none !important; }" in html   # le panneau caché l'est vraiment
