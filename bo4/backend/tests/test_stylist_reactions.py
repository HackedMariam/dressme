"""Réactions courtes sur les dernières tenues (sans numéro) : 👎 enregistré et nouvelles tenues, 👍 enregistré,
merci / pourquoi / couleur : réponse courte sans nouvelle recommandation."""
import pytest

import stylist_agent as sa
import stylist_feedback
from test_stylist_agent import TODAY, fixture_loader


@pytest.fixture
def stylist(tmp_path):
    pytest.importorskip("langgraph")
    pytest.importorskip("outfit_engine")
    store = stylist_feedback.FeedbackStore(tmp_path / "feedback.json")
    loads = []

    def loader(token=None):
        loads.append(token)
        return fixture_loader()
    graph = sa.build_graph(llm=None, wardrobe_loader=loader, today=lambda: TODAY, weather=None, feedback_store=store)
    return graph, store, loads


def say(graph, message):
    config = {"configurable": {"thread_id": "fil"}}
    graph.invoke(sa.new_turn(message), config)
    return graph.get_state(config).values


def ids(state):
    return {frozenset(sa._outfit_ids(o)) for o in state.get("outfits") or []}


@pytest.mark.parametrize("reaction", ["j'aime pas", "je n'aime pas", "bof", "pas terrible", "non", "I don't like it"])
def test_negative_reaction_records_a_dislike_and_proposes_other_outfits(stylist, reaction):
    graph, store, _ = stylist
    first = say(graph, "J'ai un entretien demain")
    shown = len(first["outfits"])
    after = say(graph, reaction)
    assert store.profile(sa.DEFAULT_USER)["dislikes"] == shown                 # 👎 sur chaque tenue montrée
    assert after["outfits"] and not ids(first) & ids(after)                    # de nouvelles tenues
    assert after["response"].startswith(f"C'est noté : ces {shown} tenues ne te plaisent pas")
    assert "record_feedback" in after["trace"][1] and after["request"]["occasion"] == "work"


@pytest.mark.parametrize("reaction", ["j'aime", "top", "pas mal", "super !"])
def test_positive_reaction_records_a_like_on_the_first_outfit(stylist, reaction):
    graph, store, _ = stylist
    first = say(graph, "J'ai un entretien demain")
    after = say(graph, reaction)
    profile = store.profile(sa.DEFAULT_USER)
    assert profile["likes"] == 1 and profile["dislikes"] == 0 and not after["outfits"]
    assert "C'est noté : tu aimes la tenue 1" in after["response"]
    if len(first["outfits"]) > 1:
        assert "« j'aime la 2 »" in after["response"]


@pytest.mark.parametrize("reaction, expected", [
    ("merci", "Avec plaisir !"),
    ("pourquoi ?", "Je les ai choisies pour l'occasion « travail »"),
    ("et en bleu ?", "Je ne sais pas encore chercher une couleur précise"),
])
def test_other_reactions_answer_without_a_new_recommendation(stylist, reaction, expected):
    graph, store, loads = stylist
    say(graph, "J'ai un entretien demain")
    after = say(graph, reaction)
    assert expected in after["response"] and not after["outfits"]
    assert len(loads) == 1                                                      # garde-robe non relue
    assert store.profile(sa.DEFAULT_USER)["likes"] == store.profile(sa.DEFAULT_USER)["dislikes"] == 0


def test_reaction_without_previous_outfits_asks_for_the_occasion(stylist):
    graph, store, loads = stylist
    state = say(graph, "j'aime pas")
    assert "pour quelle occasion" in state["response"] and not state["outfits"] and loads == []
    assert store.profile(sa.DEFAULT_USER)["dislikes"] == 0


def test_numbered_feedback_and_real_requests_are_unchanged(stylist):
    graph, store, _ = stylist
    say(graph, "J'ai un entretien demain")
    liked = say(graph, "j'aime la 2")
    assert "tu aimes la tenue 2" in liked["response"]
    excluded = say(graph, "une tenue pour le travail sans veste")
    assert excluded["request"]["exclude_categories"] == ["outerwear"] and excluded["outfits"]
