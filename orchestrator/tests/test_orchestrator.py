"""Tests de l'orchestrateur avec des services simulés (aucun appel réseau)."""
import json
import urllib.error

import pytest

import graph as og
from services import Gateway, Service

pytest.importorskip("langgraph")

TOKEN = "jeton-secret-alice"
WARDROBE = [
    {"id": "1", "name": "Black Ribbed Turtleneck", "category": "top", "color_name": "black", "style": "minimalist",
     "seasons": ["autumn"], "needs_review": False},
    {"id": "2", "name": "Plaid Wool Mini Skirt", "category": "skirt", "color_name": "grey", "style": "classic",
     "seasons": ["autumn"], "needs_review": False},
    {"id": "3", "name": "Black Pleated Skirt", "category": "skirt", "color_name": "black", "style": "classic",
     "needs_review": False},
    {"id": "4", "name": "Black Leather Jacket", "category": "jacket", "color_name": "black", "style": "streetwear",
     "needs_review": True},
    {"id": "5", "name": "Brown Leather Strap Watch", "category": "watch", "color_name": "brown", "needs_review": True},
]
SERVICES = {
    "bo1": Service("bo1", "BO1 Wardrobe", "http://bo1.test", 5),
    "stylist": Service("stylist", "BO4 Stylist", "http://stylist.test", 5),
    "purchase": Service("purchase", "Purchase Redundancy", "http://purchase.test", 5),
    "bo5": Service("bo5", "BO5 RAG", "http://bo5.test", 5),
    "ollama": Service("ollama", "Ollama qwen2.5:3b", "http://ollama.test", 5, extra={"model": "qwen2.5:3b"}),
}


class FakeServices:
    """Transport simulé : répond selon l'hôte et la route, garde chaque requête (en-têtes, corps)."""

    def __init__(self):
        self.calls = []
        self.down = set()
        self.purchase_reply = None      # réponse de /analyze à la place de celle par défaut

    def __call__(self, request, timeout):
        host = request.full_url.split("//", 1)[1].split(".test", 1)[0]
        path = request.full_url.split(".test", 1)[1]
        body = json.loads(request.data) if request.data else None
        auth = request.get_header("Authorization")
        self.calls.append({"host": host, "path": path, "body": body, "auth": auth})
        if host in self.down:
            raise urllib.error.URLError(ConnectionRefusedError("refusé"))
        if host == "bo1":
            if auth not in (None, f"Bearer {TOKEN}"):
                return 401, b'{"detail": "Session expired"}'
            if path == "/api/me":
                return 200, json.dumps({"id": "uuid-alice" if auth else "local"}).encode()
            return 200, json.dumps(WARDROBE).encode()
        if host == "stylist":
            payload = {"response": "1. Black Ribbed Turtleneck + Chocolate Trousers", "visited": ["recommend"],
                       "outfits": [{"rank": 1, "score": 96.3, "items": [{"name": "Black Ribbed Turtleneck"}]}]}
            return 200, json.dumps(payload).encode()
        if host == "purchase":
            payload = self.purchase_reply or {
                "redundancy_score": 72, "recommendation": "skip", "explanation": "Very close to what you own.",
                "similar_items": [{"name": "Black Leather Jacket", "similarity": 0.91}]}
            return 200, json.dumps(payload).encode()
        if host == "bo5":
            payload = {"answer": "From [S1], pair it with a **structured blazer** [S1].\n"
                                 "- A parka (Figure 69 from [S5]) for cooler days [S2, S3].\n"
                                 "- See FIGURE 12 for details.", "grounded": True,
                       "citations": [{"marker": "S1", "title": "Work clothes", "page": 95},
                                     {"marker": "S2", "title": "Slide 1", "page": 3},
                                     {"marker": "S3", "title": "Textilepedia (z-library.sk, 1lib.sk)", "page": 9},
                                     {"marker": "S4", "title": "Work clothes", "page": 95}],
                       "sources": [{"title": "36916.indb"}, {"title": "Work clothes"}]}
            return 200, json.dumps(payload).encode()
        return 404, b"{}"

    def to(self, host):
        return [c for c in self.calls if c["host"] == host]


@pytest.fixture
def fake():
    return FakeServices()


def make(fake, llm=None):
    return og.build_graph(gateway=Gateway(SERVICES, transport=fake), llm=llm)


def run(graph, message, thread="t1", user="local", token=None):
    config = og.turn_config(thread, user, token)
    graph.invoke(og.new_turn(message), config)
    return graph.get_state(config).values


# ------------------------------------------------------------------ routage par règles
@pytest.mark.parametrize("message, route", [
    ("J'ai un entretien demain, que porter ?", "stylist"),
    ("Quelle tenue pour un mariage ?", "stylist"),
    ("What should I wear to a job interview?", "stylist"),
    ("Est-ce que j'ai une jupe noire ?", "wardrobe"),
    ("Combien de vêtements dans ma garde-robe ?", "wardrobe"),
    ("Do I have a black skirt?", "wardrobe"),
    ("Est-ce que je devrais acheter une veste en cuir noire ?", "purchase"),
    ("Ce pull serait un doublon ?", "purchase"),
    ("Should I buy a black leather jacket?", "purchase"),
    ("Comment porter une robe longue gris clair ?", "knowledge"),
    ("Pourquoi le beige va avec le marine ?", "knowledge"),
    ("How do I wear a plaid mini skirt in autumn?", "knowledge"),
])
def test_rules_route_fr_and_en(message, route):
    assert og.rule_candidates(message) == [route]
    assert og.decide_route(message, {}, None)[:2] == (route, "règles")


def test_garde_robe_is_not_a_dress():
    assert og.find_categories("Combien de vêtements dans ma garde-robe ?") == []
    assert og.find_categories("Est-ce que j'ai une robe ?") == ["dress"]


@pytest.mark.parametrize("message, route", [
    ("J'ai un entretien demain, que porter ?", "stylist"),
    ("Est-ce que j'ai une jupe noire ?", "wardrobe"),
    ("Should I buy a black leather jacket?", "purchase"),
    ("How do I wear a plaid mini skirt in autumn?", "knowledge"),
])
def test_graph_follows_each_route(fake, message, route):
    state = run(make(fake), message)
    assert state["route"] == route
    assert og.visited_nodes(state["trace"]) == ["route_intent", route, "respond"]
    assert state["response"]


# ------------------------------------------------------------------ clarification
def test_greeting_asks_for_clarification(fake):
    state = run(make(fake), "Bonjour !")
    assert state["route"] == "clarify" and "Réponds par 1, 2, 3 ou 4" in state["response"]
    assert fake.calls == []                               # aucun service appelé


def test_ambiguous_request_without_llm_asks(fake):
    state = run(make(fake), "Quels conseils pour une tenue de soirée ?")   # indices : stylist et knowledge
    assert state["route"] == "clarify" and state["candidates"] == ["stylist", "knowledge"]


def test_answer_to_clarification_reuses_the_question(fake):
    graph = make(fake)
    run(graph, "Quels conseils pour une tenue de soirée ?")
    state = run(graph, "1")
    assert state["route"] == "stylist"
    assert fake.to("stylist")[-1]["body"]["message"] == "Quels conseils pour une tenue de soirée ?"


def test_follow_up_goes_back_to_the_stylist(fake):
    graph = make(fake)
    run(graph, "J'ai un entretien demain, que porter ?")
    assert run(graph, "une autre")["route"] == "stylist"


# ------------------------------------------------------------------ garde-fou du LLM
def fixed_llm(route):
    return lambda system, message, schema: {"route": route}


def test_llm_choice_within_rule_cues_is_accepted(fake):
    state = run(make(fake, llm=fixed_llm("knowledge")), "Quels conseils pour une tenue de soirée ?")
    assert state["route"] == "knowledge" and state["route_source"] == "LLM qwen2.5:3b"


def test_llm_choice_outside_rule_cues_is_rejected(fake):
    state = run(make(fake, llm=fixed_llm("purchase")), "Quels conseils pour une tenue de soirée ?")
    assert state["route"] == "clarify" and "hors des indices" in state["route_source"]
    assert not fake.to("purchase")


@pytest.mark.parametrize("raw", [{"route": "delete_wardrobe"}, {"route": None}, {}, None, "stylist"])
def test_llm_invalid_values_are_rejected(fake, raw):
    state = run(make(fake, llm=lambda s, m, sc: raw), "Une petite question mode")
    assert state["route"] == "clarify"


def test_llm_routes_a_message_without_cues(fake):
    state = run(make(fake, llm=fixed_llm("stylist")), "Demain c'est la soutenance, aide-moi")
    assert state["route"] == "stylist" and state["candidates"] == []


def test_ground_route():
    assert og.ground_route({"route": "wardrobe"}, []) == ("wardrobe", None)
    assert og.ground_route({"route": "clarify"}, ["stylist", "knowledge"]) == ("clarify", None)
    assert og.ground_route({"route": "x"}, [])[0] is None


# ------------------------------------------------------------------ services arrêtés : message clair
@pytest.mark.parametrize("host, message", [
    ("stylist", "J'ai un entretien demain, que porter ?"),
    ("bo1", "Est-ce que j'ai une jupe noire ?"),
    ("purchase", "Should I buy a black leather jacket?"),
    ("bo5", "How do I wear a plaid mini skirt in autumn?"),
])
def test_stopped_service_gives_a_clear_message(fake, host, message):
    fake.down.add(host)
    state = run(make(fake), message)
    assert state["result"]["ok"] is False
    assert "ne répond pas" in state["response"] and "Réessaie" in state["response"]
    assert any("injoignable" in line for line in state["trace"])


def test_purchase_without_bo1_does_not_call_purchase(fake):
    fake.down.add("bo1")
    state = run(make(fake), "Should I buy a black leather jacket?")
    assert "Sans ta garde-robe" in state["response"] and not fake.to("purchase")


def test_ollama_down_falls_back_to_clarify(fake):
    fake.down.add("ollama")
    state = run(make(fake, llm="ollama"), "Quels conseils pour une tenue de soirée ?")
    assert state["route"] == "clarify"
    assert any(line.startswith("route_intent -> ollama POST /api/chat : injoignable") for line in state["trace"])


# ------------------------------------------------------------------ jeton : transmis, jamais stocké
def test_token_is_forwarded_and_never_stored(fake):
    graph = make(fake)
    run(graph, "J'ai un entretien demain, que porter ?", user="uuid-alice", token=TOKEN)
    run(graph, "Est-ce que j'ai une jupe noire ?", user="uuid-alice", token=TOKEN)
    assert fake.to("stylist")[0]["auth"] == f"Bearer {TOKEN}"
    assert fake.to("stylist")[0]["body"]["thread_id"] == "t1"           # même fil côté Stylist
    assert fake.to("bo1")[0]["auth"] == f"Bearer {TOKEN}"
    saver = graph.checkpointer
    dump = repr([(t.config, t.metadata, t.checkpoint) for t in saver.list(None)]) + repr(saver.storage)
    assert TOKEN not in dump and "uuid-alice:t1" in dump
    assert repr(og.RequestToken(TOKEN)) == "RequestToken(***)"


def test_threads_are_isolated_per_user(fake):
    graph = make(fake)
    run(graph, "J'ai un entretien demain, que porter ?", user="uuid-alice", token=TOKEN)
    state = run(graph, "une autre", user="uuid-bob")                    # Bob, même thread_id
    assert state["route"] == "clarify"                                  # pas de suite : le fil d'Alice est à part


# ------------------------------------------------------------------ garde-robe : faits
def test_wardrobe_counts_and_filters(fake):
    state = run(make(fake), "Est-ce que j'ai une jupe noire ?")
    text = state["response"]
    assert "5 vêtement(s)" in text and "Jupes (noir) : 1 — Black Pleated Skirt" in text
    assert "2 vêtement(s) sont marqués « à vérifier »" in text
    assert not any(c["path"] == "/api/agent/search" for c in fake.calls)   # exige une clé OpenAI côté BO1


def test_wardrobe_without_filter_gives_breakdown(fake):
    state = run(make(fake), "Combien de vêtements dans ma garde-robe ?")
    assert "Répartition : 2 jupes" in state["response"]


# ------------------------------------------------------------------ achat : garde-robe BO1 envoyée à Purchase Redundancy
def test_purchase_sends_the_bo1_wardrobe(fake):
    state = run(make(fake), "Est-ce que je devrais acheter une veste en cuir noire à 80 € ?", token=TOKEN)
    body = fake.to("purchase")[0]["body"]
    assert body["new_item"] == {"name": "black leather jacket", "category": "outerwear", "color": "black",
                                "material": "leather", "price": 80.0, "style": None}
    assert body["language"] == "French" and body["use_llm"] is False
    assert {i["category"] for i in body["wardrobe_items"]} <= {"shirts", "pants", "dresses", "shoes", "outerwear",
                                                              "accessories"}
    assert [i["category"] for i in body["wardrobe_items"]] == ["shirts", "pants", "pants", "outerwear", "accessories"]
    assert fake.to("purchase")[0]["auth"] is None                      # authentification propre : jeton non transmis
    # une phrase d'introduction (article tel qu'écrit, tutoiement), puis l'avis de Purchase tel quel, sans synthèse
    # qui le répète
    assert state["response"].splitlines() == [
        "Avis de Purchase Redundancy sur « veste en cuir noire », comparé aux 5 pièces de ta garde-robe :",
        "Very close to what you own."]


def test_purchase_without_explanation_falls_back_to_a_short_summary(fake):
    fake.purchase_reply = {"redundancy_score": 72, "recommendation": "skip",
                           "similar_items": [{"name": "Black Leather Jacket", "similarity": 0.91}]}
    state = run(make(fake), "Est-ce que je devrais acheter un col roulé noir ?", token=TOKEN)
    assert fake.to("purchase")[0]["body"]["new_item"]["name"] == "black turtleneck"   # anglais pour /analyze
    assert state["response"].splitlines() == [
        "Avis de Purchase Redundancy sur « col roulé noir », comparé aux 5 pièces de ta garde-robe :",
        "Redondance : 72/100 → inutile, tu as déjà l'équivalent. Pièces proches : Black Leather Jacket (91 %)."]


def test_purchase_in_english_keeps_the_english_article(fake):
    state = run(make(fake), "Should I buy a black leather jacket for 80 euros?", token=TOKEN)
    assert state["response"].splitlines()[0] == ("Purchase Redundancy's opinion on \"black leather jacket\", "
                                                 "compared with the 5 items in your wardrobe:")
    assert fake.to("purchase")[0]["body"]["language"] == "English"


def test_purchase_without_item_asks_what(fake):
    state = run(make(fake), "Est-ce que je devrais acheter quelque chose ?")
    assert "Quel article" in state["response"] and not fake.calls


# ------------------------------------------------------------------ BO5 : anglais, sources citées, titres masqués
def test_knowledge_translates_and_masks_titles(fake):
    def llm(system, message, schema):
        return {"english": "How do I wear a black turtleneck with wide trousers?"} if "english" in schema["properties"] \
            else None
    state = run(make(fake, llm=llm), "Comment porter un col roulé noir avec un pantalon large ?")
    assert fake.to("bo5")[0]["body"]["question"] == "How do I wear a black turtleneck with wide trousers?"
    text, details = state["response"], state["result"]["details"]
    assert details["answer"] == "Pair it with a **structured blazer**.\n- A parka for cooler days."
    assert details["language"] == "en" and details["sources"] == ["Work clothes (p. 95)"]   # citées, sans doublon
    assert "**Sources citées**\n- Work clothes (p. 95)" in text
    assert "2 autre(s) source(s) citée(s) au titre peu fiable masquée(s)" in text
    for hidden in ("Slide 1", "z-library", ".indb", "36916", "[S", "Figure", "FIGURE"):
        assert hidden not in text


@pytest.mark.parametrize("raw, clean", [
    ("Pair it with a blazer [S1]. Add boots [S2, S3][S4].", "Pair it with a blazer. Add boots."),
    ("From [S1], we learn about capsules.", "We learn about capsules."),
    ("Based on [S2] and [S4], navy works well.", "Navy works well."),
    ("- A parka (Figure 69 from [S5]) for cooler nights.", "- A parka for cooler nights."),
    ("Layer it over a black top, as shown in Figure 50.", "Layer it over a black top."),
    ("A dress (FIGURE 58 from [S3]) with heels. See FIGURE 12 for details.", "A dress with heels."),
    ("The **LBD** is versatile [S1].", "The **LBD** is versatile."),
    ("No marker here.", "No marker here."),
])
def test_clean_bo5_answer(raw, clean):
    assert og.clean_bo5_answer(raw) == clean


def test_bo5_without_citation_says_so(fake):
    original = fake.__call__

    def no_citation(request, timeout):
        status, raw = original(request, timeout)
        if "bo5.test" in request.full_url:
            data = json.loads(raw)
            data["citations"] = []
            raw = json.dumps(data).encode()
        return status, raw
    graph = og.build_graph(gateway=Gateway(SERVICES, transport=no_citation), llm=None)
    state = run(graph, "How do I wear a plaid mini skirt in autumn?")
    assert state["result"]["details"]["sources"] == []
    assert "Aucune source citée" in state["response"]


def test_bo5_with_only_masked_sources_says_so(fake):
    original = fake.__call__

    def only_masked(request, timeout):
        status, raw = original(request, timeout)
        if "bo5.test" in request.full_url:
            data = json.loads(raw)
            data["citations"] = [c for c in data["citations"] if c["title"] != "Work clothes"]
            raw = json.dumps(data).encode()
        return status, raw
    graph = og.build_graph(gateway=Gateway(SERVICES, transport=only_masked), llm=None)
    state = run(graph, "How do I wear a plaid mini skirt in autumn?")
    assert "2 source(s) citée(s), toutes au titre peu fiable (masquées)" in state["response"]
    assert "Aucune source citée" not in state["response"]


def test_french_garment_words_left_by_the_translation_are_fixed(fake):
    llm = lambda s, m, sc: {"english": "How can I wear a black col roule with wide leg pantalon?"}  # noqa: E731
    run(make(fake, llm=llm), "Comment porter un col roulé noir avec un pantalon large ?")
    assert fake.to("bo5")[0]["body"]["question"] == "How can I wear a black turtleneck with wide leg trousers?"


@pytest.mark.parametrize("text, expected", [
    ("a grey écossaise mini-jupe", "a grey plaid mini skirt"),
    ("Cols roulés and vestes", "turtleneck and jacket"),
    ("a robe dress", "a dress dress"),
])
def test_apply_glossary(text, expected):
    assert og.apply_glossary(text) == expected


def test_knowledge_sends_original_question_when_translation_fails(fake):
    state = run(make(fake, llm=lambda s, m, sc: None), "Comment porter une robe longue ?")
    assert fake.to("bo5")[0]["body"]["question"] == "Comment porter une robe longue ?"
    assert any("traduction indisponible" in line for line in state["trace"])


def test_english_question_is_not_translated(fake):
    calls = []
    run(make(fake, llm=lambda s, m, sc: calls.append(m)), "How do I wear a plaid mini skirt in autumn?")
    assert calls == []


def test_cited_sources_only():
    shown, masked = og.cited_sources({"citations": [], "sources": [{"title": "Work clothes"}]})
    assert shown == [] and masked == 0


# ------------------------------------------------------------------ trace
def test_each_node_writes_a_trace_line(fake):
    state = run(make(fake), "Should I buy a black leather jacket?")
    assert state["trace"][0].startswith("route_intent -> purchase [règles")
    assert any(line.startswith("purchase -> bo1 GET /api/items : HTTP 200 en") for line in state["trace"])
    assert any(line.startswith("purchase -> purchase POST /analyze : HTTP 200 en") for line in state["trace"])
    assert state["trace"][-1].startswith("respond -> ")


# ------------------------------------------------------------------ connexion requise / jeton expiré
class ProtectedFake(FakeServices):
    """Stylist et BO1 protégés (comme en production) : sans jeton -> 401 ; jeton inconnu -> 401."""

    def __call__(self, request, timeout):
        host = request.full_url.split("//", 1)[1].split(".test", 1)[0]
        auth = request.get_header("Authorization")
        if host in ("stylist", "bo1") and auth != f"Bearer {TOKEN}":
            self.calls.append({"host": host, "path": request.full_url.split(".test", 1)[1], "body": None, "auth": auth})
            return 401, b'{"detail": "Connexion requise"}'
        return super().__call__(request, timeout)


@pytest.mark.parametrize("message, text", [
    ("J'ai un entretien demain, que porter ?", "Connecte-toi pour utiliser le Stylist."),
    ("Est-ce que j'ai une jupe noire ?", "Connecte-toi pour utiliser ta garde-robe."),
    ("Should I buy a black leather jacket?", "Connecte-toi pour utiliser l'avis d'achat."),
])
def test_without_login_the_answer_asks_to_sign_in(message, text):
    state = run(og.build_graph(gateway=Gateway(SERVICES, transport=ProtectedFake()), llm=None), message)
    assert state["response"].startswith(text) and "reconnecte-toi" not in state["response"]
    assert state["result"]["details"]["login_required"] is True


def test_expired_token_still_says_sign_in_again():
    state = run(og.build_graph(gateway=Gateway(SERVICES, transport=ProtectedFake()), llm=None),
                "J'ai un entretien demain, que porter ?", user="uuid-alice", token="jeton-expire")
    assert "reconnecte-toi" in state["response"] and "Connecte-toi pour utiliser" not in state["response"]
    assert state["result"]["details"]["login_required"] is False


def test_ollama_calls_keep_the_model_loaded(fake):
    run(make(fake, llm="ollama"), "Quels conseils pour une tenue de soirée ?")
    body = fake.to("ollama")[0]["body"]
    assert body["keep_alive"] == "30m"
