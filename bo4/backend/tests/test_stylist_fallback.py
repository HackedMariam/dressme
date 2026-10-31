"""Repli du Stylist après des 👎 : les règles de dress code (formalité, O2, O3, O4) et de pluie (daim, soie) sont
ABSOLUES, seules les préférences (👎, bonus de goût) s'assouplissent ; « j'aime pas la 2 » sans tenue 2 ;
magasin de retours (comptage, réinitialisation d'un seul utilisateur) ; route /api/profile/reset."""
import pytest

import bo1_api_adapter
import stylist_agent as sa
import stylist_feedback
from test_stylist_agent import TODAY, fixture_loader

MINI, OFF_SHOULDER, SILK = "mini-skirt", "off-shoulder", "silk-blouse"


def risky_wardrobe():
    """Garde-robe de la panne : une minijupe (O3), un pull épaules dénudées (O4) et un chemisier en soie, tous très
    « habillés » (formalité 4) : sans les règles absolues, ils seraient proposés pour un entretien."""
    wardrobe, report = fixture_loader()
    skirt = next(i for i in wardrobe if i["category"] == "skirt")
    shirt = next(i for i in wardrobe if i["category"] == "shirt")
    wardrobe = wardrobe + [
        {**skirt, "id": MINI, "name": "Plaid Wool Mini Skirt", "subcategory": "mini skirt", "formality": 4},
        {**shirt, "id": OFF_SHOULDER, "name": "Beige Off-Shoulder Sweater", "subcategory": "off-shoulder sweater",
         "color": "beige", "formality": 4},
        {**shirt, "id": SILK, "name": "Silk Blouse", "material": "100% silk", "formality": 4},
    ]
    return wardrobe, report


def one_outfit_wardrobe():
    wardrobe, report = fixture_loader()
    keep = {"Light Blue Shirt", "Beige Chinos", "Navy Blazer"}
    return [item for item in wardrobe if item["name"] in keep], report


@pytest.fixture
def stylist(tmp_path):
    pytest.importorskip("langgraph")
    pytest.importorskip("outfit_engine")

    def factory(loader=risky_wardrobe, weather=None):
        store = stylist_feedback.FeedbackStore(tmp_path / "feedback.json")
        graph = sa.build_graph(llm=None, wardrobe_loader=lambda token=None: loader(), today=lambda: TODAY,
                               weather=weather, feedback_store=store)
        return graph, store
    return factory


def say(graph, message, thread="fil"):
    config = {"configurable": {"thread_id": thread}}
    graph.invoke(sa.new_turn(message), config)
    return graph.get_state(config).values


def used(state):
    return {i for o in state.get("outfits") or [] for i in sa._outfit_ids(o)}


def exhaust(graph, first_message="J'ai un entretien demain", limit=15):
    """Envoie la demande puis « j'aime pas » jusqu'à ce que plus aucune tenue ne soit proposée ; renvoie tous les états."""
    states = [say(graph, first_message)]
    for _ in range(limit):
        if not states[-1]["outfits"]:
            return states
        states.append(say(graph, "j'aime pas"))
    pytest.fail("les tenues ne s'épuisent jamais")


# ---------------------------------------------------------------- 1. règles absolues
def test_forbidden_pieces_never_appear_even_when_every_conforming_outfit_was_rejected(stylist):
    graph, store = stylist()
    states = exhaust(graph)
    assert len(states) > 2 and states[0]["outfits"]
    for state in states:
        assert not used(state) & {MINI, OFF_SHOULDER}, state["response"]
        assert all(o["dress_code_ok"] for o in state["outfits"])
    last = states[-1]
    assert last["outfit_fallback"] == "all_rejected" and not last["outfits"]
    assert "Tu as écarté toutes les tenues conformes" in last["response"] and "Pièce à ajouter" in last["response"]
    assert "plus proches" not in last["response"]
    assert store.profile(sa.DEFAULT_USER)["dislikes"] >= 3


def test_pieces_banned_by_the_dress_code_are_reported(stylist):
    graph, _ = stylist()
    state = say(graph, "J'ai un entretien demain")
    assert "Écarté pour ce dress code : Beige Off-Shoulder Sweater (épaules dénudées)." in state["response"]
    assert "Écarté (trop court pour ce dress code) : Plaid Wool Mini Skirt." in state["response"]


def test_least_rejected_outfits_are_replayed_and_the_fallback_is_announced(stylist):
    graph, store = stylist()
    states = exhaust(graph)
    shown = {frozenset(sa._outfit_ids(o)) for s in states for o in s["outfits"]}
    wardrobe = {str(i["id"]): i for i in risky_wardrobe()[0]}
    worst = max(shown, key=sorted)                                   # une tenue rejetée trois fois de plus
    for _ in range(3):
        store.add("dislike", [wardrobe[i] for i in worst], "work", user=sa.DEFAULT_USER)
    counts = store.dislike_counts(sa.DEFAULT_USER)
    assert counts[worst] == 4 and min(counts.values()) == 1

    again = say(graph, "Une tenue pour le travail")                  # nouvelle demande : tout est rejeté
    assert again["outfit_fallback"] == "replay_rejected" and again["outfits"]
    assert again["response"].count("Tu as écarté toutes les tenues conformes ; voici celles que tu as le moins "
                                   "rejetées.") == 1
    assert "Voici mes propositions" not in again["response"]
    shown_now = {frozenset(sa._outfit_ids(o)) for o in again["outfits"]}
    assert worst not in shown_now and all(counts[o] == 1 for o in shown_now)   # les moins rejetées d'abord
    assert not used(again) & {MINI, OFF_SHOULDER} and all(o["dress_code_ok"] for o in again["outfits"])


def test_replay_never_brings_back_what_was_just_rejected_in_the_same_series(stylist):
    graph, _ = stylist()
    states = exhaust(graph)
    seen = [frozenset(sa._outfit_ids(o)) for s in states for o in s["outfits"]]
    assert len(seen) == len(set(seen))                               # aucune tenue montrée deux fois dans la série


@pytest.mark.parametrize("weather", [lambda city, day: {"city": city, "t_min": 12, "t_max": 18, "rain_probability": 70}])
def test_rain_rules_stay_absolute_in_the_fallback(stylist, weather):
    graph, _ = stylist(weather=weather)
    states = exhaust(graph, "J'ai un entretien demain")
    for state in states:
        assert SILK not in used(state) and not used(state) & {MINI, OFF_SHOULDER}
        assert all(any(sa.is_rain_outerwear(i) for i in sa._outfit_items(o, risky_wardrobe()[0]))
                   for o in state["outfits"])                          # pièce de dessus dans chaque tenue
    replay = say(graph, "Une tenue pour le travail")
    assert SILK not in used(replay) and not used(replay) & {MINI, OFF_SHOULDER}
    assert "Écarté à cause de la pluie (daim, soie) : Silk Blouse." in replay["response"]


def test_no_conforming_outfit_at_all_says_so_without_relaxing_anything(stylist):
    def casual_only():
        wardrobe, report = fixture_loader()
        return [i for i in wardrobe if i["name"] in {"White Tee", "Blue Jeans", "Black Puffer"}], report
    graph, _ = stylist(loader=casual_only)
    state = say(graph, "Une tenue pour un mariage")
    assert not state["outfits"] and state["outfit_fallback"] == "none_conform"
    assert "Pièce à ajouter : un blazer (veste structurée)." in state["response"]


# ---------------------------------------------------------------- 3. « j'aime pas la 2 » sans tenue 2
@pytest.mark.parametrize("message", ["j'aime pas la 2", "je n'aime pas la 2", "j'aime la 2", "bof la 2"])
def test_feedback_on_a_missing_outfit_only_says_so(stylist, message):
    graph, store = stylist(loader=one_outfit_wardrobe)
    first = say(graph, "J'ai un entretien demain")
    assert len(first["outfits"]) == 1
    state = say(graph, message)
    assert state["response"] == "Je ne trouve pas de tenue n° 2 dans mes dernières propositions."
    assert not state["outfits"]
    assert [line.split()[0] for line in state["trace"]] == ["extract_intent", "record_feedback"]   # pas de recommend
    profile = store.profile(sa.DEFAULT_USER)
    assert profile["likes"] == profile["dislikes"] == 0                                           # ni 👎 ni 👍


def test_feedback_on_an_existing_outfit_still_records_and_proposes_others(stylist):
    graph, store = stylist()
    first = say(graph, "J'ai un entretien demain")
    state = say(graph, "je n'aime pas la 1")
    assert state["response"].startswith("C'est noté : tu n'aimes pas la tenue 1")
    assert state["outfits"] and store.profile(sa.DEFAULT_USER)["dislikes"] == 1
    assert sa._outfit_ids(first["outfits"][0]) not in [sa._outfit_ids(o) for o in state["outfits"]]


def test_dislike_with_nothing_to_note_does_not_recommend_unless_asked(stylist):
    calls = {"fail": False}

    def flaky():
        if calls["fail"]:
            calls["fail"] = False
            raise bo1_api_adapter.BO1UnavailableError("BO1 a répondu HTTP 500")
        return risky_wardrobe()
    graph, store = stylist(loader=flaky)
    say(graph, "J'ai un entretien demain")
    calls["fail"] = True
    assert not say(graph, "Une tenue pour une soirée")["outfits"]                 # erreur : aucune tenue
    nothing = say(graph, "j'aime pas")
    assert nothing["response"] == "Il n'y a pas de tenue à noter dans ma dernière réponse."
    assert not nothing["outfits"] and store.profile(sa.DEFAULT_USER)["dislikes"] == 0
    calls["fail"] = True
    say(graph, "Une tenue pour une soirée")
    asked = say(graph, "j'aime pas, une autre")                                   # demande explicite : on continue
    assert asked["outfits"] and store.profile(sa.DEFAULT_USER)["dislikes"] == 0


# ---------------------------------------------------------------- magasin de retours
def item(identifier, name="x", color="black"):
    return {"id": identifier, "name": name, "color": color}


def test_dislike_counts_are_per_outfit_and_per_user():
    store = stylist_feedback.FeedbackStore()
    for _ in range(3):
        store.add("dislike", [item("1"), item("2")], user="alice")
    store.add("dislike", [item("3")], user="alice")
    store.add("like", [item("1")], user="alice")
    store.add("dislike", [item("1"), item("2")], user="bob")
    assert store.dislike_counts("alice") == {frozenset({"1", "2"}): 3, frozenset({"3"}): 1}
    assert store.dislike_counts("bob") == {frozenset({"1", "2"}): 1}


def test_reset_removes_only_that_users_records_and_survives_a_reload(tmp_path):
    path = tmp_path / "feedback.json"
    store = stylist_feedback.FeedbackStore(path)
    store.add("dislike", [item("1")], user="alice")
    store.add("like", [item("2")], user="alice")
    store.add("dislike", [item("3")], user="bob")
    assert store.reset("alice") == 2
    assert store.profile("alice")["likes"] == store.profile("alice")["dislikes"] == 0
    assert store.profile("bob")["dislikes"] == 1 and store.reset("alice") == 0     # rejouable, sans effet
    reloaded = stylist_feedback.FeedbackStore(path)
    assert [r["user"] for r in reloaded.records("bob")] == ["bob"] and reloaded.records("alice") == []


def test_reset_needs_a_user():
    store = stylist_feedback.FeedbackStore()
    store.add("dislike", [item("1")], user="alice")
    for user in ("", None):
        with pytest.raises(ValueError):
            store.reset(user)
    assert len(store.records("alice")) == 1


# ---------------------------------------------------------------- route /api/profile/reset
@pytest.fixture
def web(tmp_path):
    pytest.importorskip("langgraph")
    testclient = pytest.importorskip("fastapi.testclient")
    import stylist_web
    store = stylist_feedback.FeedbackStore(tmp_path / "feedback.json")
    store.add("dislike", [item("1")], user="uuid-alice")
    store.add("dislike", [item("2")], user="uuid-alice")
    store.add("like", [item("3")], user="uuid-bob")
    tokens = {"jeton-alice": "uuid-alice", "jeton-bob": "uuid-bob"}

    def identity(token):
        if token not in tokens:
            raise stylist_web.HTTPException(401, "Jeton invalide")
        return tokens[token]
    stylist_web.configure(llm=None, loader=fixture_loader, today=lambda: TODAY, weather=None, feedback=store,
                          identity=identity)
    yield testclient.TestClient(stylist_web.app), store
    stylist_web.configure()


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_profile_reset_route_requires_a_token(web):
    http, store = web
    assert http.post("/api/profile/reset").status_code == 401
    assert http.post("/api/profile/reset", headers=bearer("jeton-inconnu")).status_code == 401
    assert len(store.records("uuid-alice")) == 2                                 # rien n'a été supprimé


def test_profile_reset_route_only_touches_the_token_owner(web):
    http, store = web
    # un identifiant glissé dans la requête est ignoré : seule l'identité vérifiée par BO1 compte
    response = http.post("/api/profile/reset?user=uuid-bob", json={"user": "uuid-bob"}, headers=bearer("jeton-alice"))
    assert response.status_code == 200 and response.json()["removed"] == 2
    assert response.json()["profile"]["dislikes"] == 0
    assert store.records("uuid-alice") == [] and len(store.records("uuid-bob")) == 1
    assert http.get("/api/profile", headers=bearer("jeton-bob")).json()["likes"] == 1
    assert http.post("/api/profile/reset", headers=bearer("jeton-alice")).json()["removed"] == 0     # rejouable
