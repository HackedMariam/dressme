"""Réactions courtes (« j'aime pas », « top », « merci », « pourquoi ? », « et en bleu ? ») : envoyées au DERNIER
module du fil, avant toute règle et avant le LLM ; clarification limitée aux routes actives."""
import pytest

import graph as og
from services import Gateway, Service, modules_from_dict
from test_orchestrator import SERVICES, TOKEN, FakeServices, make, run

pytest.importorskip("langgraph")


@pytest.fixture
def fake():
    return FakeServices()


class RecordingLLM:
    """LLM simulé : enregistre chaque appel (il ne doit pas être consulté pour une réaction courte)."""

    def __init__(self, route="clarify"):
        self.calls, self.route = [], route

    def __call__(self, system, message, schema):
        self.calls.append(message)
        return {"route": self.route}


def turns(graph, *messages):
    state = None
    for message in messages:
        state = run(graph, message, token=TOKEN, user="uuid-alice")
    return state


@pytest.mark.parametrize("reaction, kind", [
    ("j'aime pas", "dislike"), ("Je n'aime pas.", "dislike"), ("bof", "dislike"), ("pas terrible", "dislike"),
    ("non", "dislike"), ("I don't like it", "dislike"), ("pas mal", "like"), ("j'aime", "like"), ("top !", "like"),
    ("merci", "thanks"), ("Pourquoi ?", "why"), ("et en bleu ?", "color"), ("what about in blue?", "color"),
])
def test_short_reactions_are_recognised(reaction, kind):
    assert og.reaction_kind(reaction) == kind


@pytest.mark.parametrize("message", ["Est-ce que j'ai une jupe noire ?", "j'aime la 2", "une autre",
                                     "je n'aime pas le noir", "Comment porter un col roulé noir ?"])
def test_real_requests_are_not_reactions(message):
    assert og.reaction_kind(message) is None


def test_dislike_after_purchase_answers_without_calling_purchase_again(fake):
    llm = RecordingLLM()
    state = turns(make(fake, llm=llm), "Est-ce que je devrais acheter un col roulé noir ?", "j'aime pas")
    assert state["route"] == "purchase" and state["route_source"] == "réaction à la réponse précédente"
    assert len(fake.to("purchase")) == 1 and llm.calls == []                   # ni Purchase ni LLM rappelés
    assert state["response"] == ("Noté. Tu veux que je compare avec une autre pièce, ou que je te propose des "
                                 "tenues avec « col roulé noir » ?")


@pytest.mark.parametrize("reaction, expected", [
    ("top", "Noté ! Tu veux que je compare avec une autre pièce"),
    ("merci", "Avec plaisir ! Tu veux un avis sur une autre pièce ?"),
    ("pourquoi ?", "Le score compare « col roulé noir » à ta garde-robe"),
    ("et en bleu ?", "Pour un avis sur la même pièce en bleu"),
])
def test_other_reactions_after_purchase(fake, reaction, expected):
    state = turns(make(fake), "Est-ce que je devrais acheter un col roulé noir ?", reaction)
    assert state["route"] == "purchase" and expected in state["response"] and len(fake.to("purchase")) == 1


def test_dislike_after_stylist_is_forwarded_to_the_stylist_on_the_same_thread(fake):
    llm = RecordingLLM()
    state = turns(make(fake, llm=llm), "J'ai un entretien demain, que porter ?", "j'aime pas")
    calls = fake.to("stylist")
    assert state["route"] == "stylist" and state["route_source"] == "réaction à la réponse précédente"
    assert len(calls) == 2 and calls[1]["body"]["message"] == "j'aime pas"
    assert calls[1]["body"]["thread_id"] == calls[0]["body"]["thread_id"]       # même fil : le Stylist a le contexte
    assert llm.calls == []


def test_reaction_after_wardrobe_offers_to_refine_the_search(fake):
    state = turns(make(fake), "Est-ce que j'ai une jupe noire ?", "bof")
    items_calls = [c for c in fake.to("bo1") if c["path"] == "/api/items"]
    assert state["route"] == "wardrobe" and len(items_calls) == 1
    assert state["response"].startswith("Tu veux que je précise la recherche ?")


def test_reaction_at_the_start_of_a_thread_asks_for_clarification(fake):
    llm = RecordingLLM(route="stylist")
    state = turns(make(fake, llm=llm), "j'aime pas")
    assert state["route"] == "clarify" and state["route_source"] == "réaction sans réponse précédente"
    assert llm.calls == [] and not fake.calls


def test_real_change_of_subject_after_a_reaction_follows_the_normal_rules(fake):
    state = turns(make(fake), "Est-ce que je devrais acheter un col roulé noir ?", "j'aime pas",
                  "Est-ce que j'ai une jupe noire ?")
    assert state["route"] == "wardrobe" and state["route_source"] == "règles"


def test_clarification_lists_only_active_routes(fake):
    services = {**SERVICES, "bo5": Service("bo5", "BO5 RAG", "http://bo5.test", 5, extra={"enabled": False})}
    graph = og.build_graph(gateway=Gateway(services, transport=fake), llm=None, modules={})
    state = run(graph, "Que penses-tu de tout ça ?", token=TOKEN, user="uuid-alice")
    assert state["route"] == "clarify" and "conseil de style" not in state["response"]
    assert "Réponds par 1, 2 ou 3, ou reformule." in state["response"]
    assert state["result"]["details"]["choices"] == ["stylist", "wardrobe", "purchase"]
    chosen = run(graph, "3", token=TOKEN, user="uuid-alice")                     # 3 = achat, pas un service éteint
    assert chosen["route"] == "purchase" and chosen["route_source"] == "réponse à la question de clarification"


def test_clarification_adds_active_modules_in_french(fake):
    modules = {"helpmepack": modules_from_dict("helpmepack", {
        "label": "HelpMePack", "description": "pack a suitcase for a trip", "enabled": True,
        "url": "http://helpmepack.test", "path": "/api/trips", "keywords": [r"\bvalise\b"]}),
               "bo3": modules_from_dict("bo3", {"label": "BO3", "enabled": False, "url": "http://bo3.test",
                                                   "path": "/api/bo3/gaps"})}
    graph = og.build_graph(gateway=Gateway(SERVICES, transport=fake), llm=None, modules=modules)
    state = run(graph, "Que penses-tu de tout ça ?", token=TOKEN, user="uuid-alice")
    assert "5. préparer ta valise pour un voyage (HelpMePack) ?" in state["response"]
    assert "pack a suitcase" not in state["response"] and "BO3" not in state["response"]   # module éteint : absent
    assert "Réponds par 1, 2, 3, 4 ou 5, ou reformule." in state["response"]
    assert run(graph, "5", token=TOKEN, user="uuid-alice")["route"] == "external:helpmepack"
