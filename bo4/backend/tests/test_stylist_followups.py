"""Suites de conversation du Stylist : réaction + demande, garde-robe du fil réutilisée, 👍 sans tenue, score
personnalisé affiché, « monochrome neutre » corrigé à l'affichage, pluriels."""
import pytest

import bo1_api_adapter
import stylist_agent as sa
import stylist_feedback
from test_stylist_agent import TODAY, fixture_loader


class Loader:
    """Garde-robe simulée : compte les lectures de BO1 ; `fail` = erreurs à lever d'abord, dans l'ordre."""

    def __init__(self, fail=()):
        self.calls, self.fail = 0, list(fail)

    def __call__(self, token=None):
        self.calls += 1
        if self.fail:
            raise self.fail.pop(0)
        return fixture_loader()


@pytest.fixture
def stylist(tmp_path):
    pytest.importorskip("langgraph")
    pytest.importorskip("outfit_engine")

    def factory(loader=None):
        store = stylist_feedback.FeedbackStore(tmp_path / "feedback.json")
        loader = loader or Loader()
        graph = sa.build_graph(llm=None, wardrobe_loader=loader, today=lambda: TODAY, weather=None,
                               feedback_store=store)
        return graph, store, loader
    return factory


def say(graph, message):
    config = {"configurable": {"thread_id": "fil"}}
    graph.invoke(sa.new_turn(message), config)
    return graph.get_state(config).values


def ids(state):
    return {frozenset(sa._outfit_ids(o)) for o in state.get("outfits") or []}


# ---------------------------------------------------------------- 1. réaction + demande de suite
@pytest.mark.parametrize("message", ["j'aime pas, donne moi un autre", "j'aime pas, une autre", "bof, autre chose",
                                     "non, donne-moi autre chose"])
def test_reaction_plus_request_records_the_dislike_then_proposes_others(stylist, message):
    graph, store, _ = stylist()
    first = say(graph, "J'ai un entretien demain")
    after = say(graph, message)
    assert store.profile(sa.DEFAULT_USER)["dislikes"] == len(first["outfits"])   # 👎 enregistré
    assert after["outfits"] and not ids(first) & ids(after)                      # PUIS d'autres tenues
    assert after["response"].startswith("C'est noté :") and "Voici d'autres propositions" in after["response"]


# ---------------------------------------------------------------- 2. garde-robe du fil, nouvel essai, 127.0.0.1
def test_follow_up_reuses_the_wardrobe_read_in_this_thread(stylist, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(sa, "WARDROBE_CLOCK", lambda: clock[0])
    graph, _, loader = stylist()
    say(graph, "J'ai un entretien demain")
    clock[0] += 60
    again = say(graph, "j'aime pas")
    assert loader.calls == 1 and again["outfits"]                                 # BO1 non relu
    assert any("garde-robe du fil réutilisée" in line for line in again["trace"])
    clock[0] += sa.WARDROBE_REUSE_S + 1                                           # trop vieille : relue
    say(graph, "une autre")
    assert loader.calls == 2


def test_new_request_still_reads_bo1(stylist):
    graph, _, loader = stylist()
    say(graph, "J'ai un entretien demain")
    say(graph, "Une tenue pour une soirée")
    assert loader.calls == 2


def test_timeout_is_retried_once(stylist):
    timeout = bo1_api_adapter.BO1UnavailableError("BO1 injoignable à http://127.0.0.1:8000 : timed out")
    graph, _, loader = stylist(Loader(fail=[timeout]))
    state = say(graph, "J'ai un entretien demain")
    assert state["outfits"] and loader.calls == 2
    assert any("nouvel essai" in line for line in state["trace"])


def test_second_timeout_gives_up_and_other_errors_are_not_retried(stylist):
    timeout = bo1_api_adapter.BO1UnavailableError("BO1 injoignable à http://127.0.0.1:8000 : timed out")
    graph, _, loader = stylist(Loader(fail=[timeout, timeout]))
    state = say(graph, "J'ai un entretien demain")
    assert not state["outfits"] and loader.calls == 2 and "garde-robe" in state["response"]
    graph, _, loader = stylist(Loader(fail=[bo1_api_adapter.BO1UnavailableError("BO1 a répondu HTTP 500")]))
    say(graph, "J'ai un entretien demain")
    assert loader.calls == 1


def test_bo1_and_ollama_default_to_ipv4_loopback():
    assert bo1_api_adapter.BO1_API_URL.startswith("http://127.0.0.1:") or "BO1_API_URL" in __import__("os").environ
    assert sa.OLLAMA_URL.startswith("http://127.0.0.1:") or "OLLAMA_URL" in __import__("os").environ


# ---------------------------------------------------------------- 3. 👍 quand la dernière réponse n'a pas de tenue
def test_like_after_a_feedback_only_answer_records_nothing(stylist):
    graph, store, _ = stylist()
    say(graph, "J'ai un entretien demain")
    say(graph, "j'aime la 2")                                    # réponse : simple accusé, sans tenue
    after = say(graph, "top")
    assert after["response"] == "Il n'y a pas de tenue à noter dans ma dernière réponse."
    assert store.profile(sa.DEFAULT_USER)["likes"] == 1 and "()" not in after["response"]


def test_like_after_an_error_records_nothing(stylist):
    graph, store, loader = stylist()
    say(graph, "J'ai un entretien demain")
    loader.fail = [bo1_api_adapter.BO1UnavailableError("BO1 a répondu HTTP 500")]
    error = say(graph, "Une tenue pour une soirée")
    assert not error["outfits"]
    after = say(graph, "j'aime")
    assert after["response"] == "Il n'y a pas de tenue à noter dans ma dernière réponse."
    assert store.profile(sa.DEFAULT_USER)["likes"] == 0


# ---------------------------------------------------------------- 4. score final affiché
def test_displayed_score_is_the_ranking_score_with_the_taste_adjustment(stylist):
    graph, _, _ = stylist()
    first = say(graph, "Une tenue décontractée pour le week-end")
    say(graph, "j'aime la 1")
    again = say(graph, "Une tenue décontractée pour le week-end")
    adjusted = [o for o in again["outfits"] if o["personal_bonus"]]
    assert adjusted and first["outfits"]
    for outfit in adjusted:
        text = sa.score_text(outfit)
        final, base, bonus = outfit["personal_score"], outfit["score"], outfit["personal_bonus"]
        assert text == (f"score {final:.1f}/100 ({base:.1f} {'+' if bonus > 0 else '−'} {abs(bonus):.1f} "
                        "selon tes goûts)").replace(".", ",")
        assert text in again["response"]
    finals = [o.get("personal_score", o["score"]) for o in again["outfits"]]
    assert finals == sorted(finals, reverse=True)                # l'ordre affiché suit le score affiché


def test_score_text_without_bonus_and_with_a_penalty():
    assert sa.score_text({"score": 96.3}) == "score 96,3/100"
    assert sa.score_text({"score": 96.3, "personal_bonus": -6.5, "personal_score": 89.8}) == \
        "score 89,8/100 (96,3 − 6,5 selon tes goûts)"


# ---------------------------------------------------------------- 5. textes
@pytest.mark.parametrize("items, shown", [
    ([{"color": "black", "name": "Black Top"}, {"color": "black", "name": "Black Trousers"}],
     "Ensemble monochrome neutre"),
    ([{"color": "black", "name": "Black Top"}, {"color": "burgundy", "name": "Burgundy Military Jacket"}],
     "Deux pièces dans la même teinte neutre"),
    ([{"color": "black", "name": "Black Top"}, {"color": "black", "name": "Burgundy Military Jacket"}],
     "Deux pièces dans la même teinte neutre"),                  # couleur BO1 mal détectée, le nom dit bordeaux
])
def test_monochrome_neutral_only_when_every_piece_is_neutral(items, shown):
    outfit = {"explanations": ["Ensemble monochrome neutre", "Styles cohérents"]}
    assert sa._explanations(outfit, items) == [shown, "Styles cohérents"]
    assert sa._explanations(outfit) == ["Ensemble monochrome neutre", "Styles cohérents"]   # sans pièces : inchangé


def test_plurals():
    assert sa._n(1, "tenue", "tenues") == "1 tenue" and sa._n(2, "tenue", "tenues") == "2 tenues"
    assert sa._n(0, "vêtement écarté", "vêtements écartés") == "0 vêtements écartés"


def test_no_parenthesised_plurals_in_answers(stylist):
    graph, _, _ = stylist()
    states = [say(graph, "Une tenue pour le travail sans noir"), say(graph, "une autre"), say(graph, "une autre")]
    for state in states:
        assert "(s)" not in state["response"]
