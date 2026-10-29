"""Node générique « module externe » : routage, désactivation, sonde, requête wardrobe_items, réponse."""
import json
import re

import pytest

import graph as og
from services import Gateway, load_modules, modules_from_dict
from test_orchestrator import SERVICES, TOKEN, WARDROBE, FakeServices

pytest.importorskip("langgraph")

SP_REPLY = {"status": "success", "agent_verdict": {"decision": "skip", "score": 31,
                                                    "reasons": ["Very close to your Black Leather Jacket."]},
            "tool_evidence": {"redundancy_score": 88.5, "closest_wardrobe_match": "Black Leather Jacket"}}
HMP_REPLY = {"message": "Your 3-day capsule for Rome is ready.", "status": "complete", "optimization_status": "OPTIMAL",
             "clarification_question": None}
BO3_REPLY = {"goal": "winter_work", "goal_label": "Winter work days",
             "ranked_gaps": [{"rank": 1, "name": "Warm outerwear coat", "priority": "high"},
                             {"rank": 2, "name": "Closed work shoes", "priority": "medium"}]}

CONFIG = {
    "smart_purchasing": {"label": "Smart Purchasing", "url": "http://sp.test", "health": "/health",
                         "path": "/api/purchase/evaluate", "enabled": True,
                         "keywords": [r"https?://\S+\.(jpe?g|png|webp)\b", r"\b(cette photo|this photo)\b"],
                         "request": {"wardrobe_items": "$wardrobe_items", "user_id": "$user_id", "prompt": "$message",
                                     "candidate": {"image_url": "$first_url", "price": "$price", "budget": "$budget"}},
                         "response": {"fields": [{"label": "Décision", "path": "agent_verdict.decision"},
                                                 {"label": "Redondance", "path": "tool_evidence.redundancy_score",
                                                  "suffix": " %"}],
                                      "text": ["agent_verdict.reasons"]}},
    "helpmepack": {"label": "HelpMePack", "url": "http://hmp.test", "health": "/api/health", "path": "/api/trips",
                   "enabled": True, "keywords": [r"\b(valises?|voyages?|packing|pack|trip|suitcase)\b"],
                   "request": {"mode": "text", "text": "Trip: $message", "wardrobe_items": "$wardrobe_items"},
                   "response": {"fields": [{"label": "Statut", "path": "status"}],
                                "text": ["message", "clarification_question"]}},
    "bo3": {"label": "BO3 Wardrobe Gaps", "url": "http://bo3.test", "health": "/api/health", "path": "/api/bo3/gaps",
            "enabled": True, "keywords": [r"\b(me manque|what am i missing|gaps?)\b"],
            "request": {"goal": "winter_work", "wardrobe_items": "$wardrobe_items", "user_id": "$user_id"},
            "response": {"fields": [{"label": "Objectif", "path": "goal_label"}],
                         "list": {"path": "ranked_gaps", "format": "{rank}. {name} (priorité {priority})"}}},
}
REPLIES = {"sp": SP_REPLY, "hmp": HMP_REPLY, "bo3": BO3_REPLY}


class FakeWithModules(FakeServices):
    """Services simulés + trois modules externes (sonde de santé et endpoint du contrat)."""

    def __call__(self, request, timeout):
        host = request.full_url.split("//", 1)[1].split(".test", 1)[0]
        if host not in REPLIES:
            return super().__call__(request, timeout)
        path = request.full_url.split(".test", 1)[1]
        body = json.loads(request.data) if request.data else None
        self.calls.append({"host": host, "path": path, "body": body, "auth": request.get_header("Authorization"),
                           "method": request.get_method()})
        if host in self.down:
            import urllib.error
            raise urllib.error.URLError(ConnectionRefusedError("refusé"))
        if request.get_method() == "GET":
            return 200, b'{"status": "ok"}'
        return 200, json.dumps(REPLIES[host]).encode()


def modules(**overrides):
    out = {}
    for name, conf in CONFIG.items():
        out[name] = modules_from_dict(name, {**conf, **overrides.get(name, {})})
    return out


@pytest.fixture
def fake():
    return FakeWithModules()


def make(fake, llm=None, mods=None):
    return og.build_graph(gateway=Gateway(dict(SERVICES), transport=fake), llm=llm,
                          modules=modules() if mods is None else mods)


def run(graph, message, user="uuid-alice", token=TOKEN, thread="t1"):
    config = og.turn_config(thread, user, token)
    graph.invoke(og.new_turn(message), config)
    return graph.get_state(config).values


# ------------------------------------------------------------------ routage FR / EN
@pytest.mark.parametrize("message, route", [
    ("Que penses-tu de cette photo https://shop.test/manteau.jpg à 80 € ?", "external:smart_purchasing"),
    ("Check this photo https://shop.test/coat.png", "external:smart_purchasing"),
    ("Prépare ma valise pour trois jours à Rome", "external:helpmepack"),
    ("Help me pack for a trip to London", "external:helpmepack"),
    ("Qu'est-ce qui me manque pour l'hiver au bureau ?", "external:bo3"),
    ("What am I missing for winter work?", "external:bo3"),
])
def test_module_keywords_route_fr_and_en(message, route):
    assert og.rule_candidates(message, modules()) == [route]
    assert og.decide_route(message, {}, None, modules())[:2] == (route, "règles")


def test_existing_routes_are_unchanged_with_modules():
    assert og.rule_candidates("J'ai un entretien demain, que porter ?", modules()) == ["stylist"]
    assert og.rule_candidates("Est-ce que j'ai une jupe noire ?", modules()) == ["wardrobe"]


# ------------------------------------------------------------------ désactivé / arrêté
def test_disabled_module_says_it_is_not_plugged_yet(fake):
    mods = modules(helpmepack={"enabled": False})
    state = run(make(fake, mods=mods), "Prépare ma valise pour trois jours à Rome")
    assert state["route"] == "external:helpmepack" and state["result"]["ok"] is False
    assert "n'est pas encore branché" in state["response"] and "POST /api/trips" in state["response"]
    assert fake.calls == []                                          # ni sonde, ni BO1, ni module
    assert og.visited_nodes(state["trace"]) == ["route_intent", "external", "respond"]


def test_disabled_module_never_steals_a_working_route():
    mods = modules(smart_purchasing={"enabled": False})
    message = "Est-ce que je devrais acheter ce manteau https://shop.test/coat.jpg ?"
    assert og.rule_candidates(message, mods) == ["purchase"]
    assert og.rule_candidates(message, modules()) == ["purchase", "external:smart_purchasing"]


def test_stopped_module_gives_a_clear_message(fake):
    fake.down.add("bo3")
    state = run(make(fake), "Qu'est-ce qui me manque pour l'hiver au bureau ?")
    assert "ne répond pas pour l'instant" in state["response"] and "http://bo3.test" in state["response"]
    assert [c["method"] for c in fake.to("bo3")] == ["GET"]           # sonde seulement
    assert not fake.to("bo1")                                          # garde-robe non lue


def test_bo1_down_means_no_module_call(fake):
    fake.down.add("bo1")
    state = run(make(fake), "What am I missing for winter work?")
    assert "Sans ta garde-robe, BO3 Wardrobe Gaps ne peut pas répondre" in state["response"]
    assert [c["method"] for c in fake.to("bo3")] == ["GET"]


# ------------------------------------------------------------------ requête selon le contrat
def test_module_receives_wardrobe_items_not_the_token(fake):
    state = run(make(fake), "Que penses-tu de cette photo https://shop.test/manteau.jpg à 80 € ? budget 60 €")
    post = [c for c in fake.to("sp") if c["method"] == "POST"][0]
    body = post["body"]
    assert post["path"] == "/api/purchase/evaluate" and post["auth"] is None   # jeton non transmis au module
    assert fake.to("bo1")[0]["auth"] == f"Bearer {TOKEN}"                       # mais utilisé pour lire BO1
    assert body["user_id"] == "uuid-alice" and body["prompt"].startswith("Que penses-tu")
    assert body["candidate"] == {"image_url": "https://shop.test/manteau.jpg", "price": 80.0, "budget": 60.0}
    assert len(body["wardrobe_items"]) == len(WARDROBE)
    assert all(set(item) == set(og.WARDROBE_FIELDS) for item in body["wardrobe_items"])
    assert state["result"]["details"]["wardrobe_sent"] == len(WARDROBE)
    assert "**Décision** : skip" in state["response"] and "**Redondance** : 88.5 %" in state["response"]
    assert "- Very close to your Black Leather Jacket." in state["response"]


def test_text_template_and_list_rendering(fake):
    state = run(make(fake), "Help me pack for a trip to London")
    body = [c for c in fake.to("hmp") if c["method"] == "POST"][0]["body"]
    assert body["mode"] == "text" and body["text"] == "Trip: Help me pack for a trip to London"
    assert "**Statut** : complete" in state["response"] and "Your 3-day capsule" in state["response"]
    state = run(make(fake), "What am I missing for winter work?", thread="t2")
    assert "1. Warm outerwear coat (priorité high)\n2. Closed work shoes (priorité medium)" in state["response"]


def test_trace_has_one_line_per_call(fake):
    state = run(make(fake), "What am I missing for winter work?")
    lines = [line for line in state["trace"] if line.startswith("external -> ")]
    assert re.match(r"external -> bo3 GET /api/health : HTTP 200 en \d+ ms", lines[0])
    assert re.match(r"external -> bo1 GET /api/items : HTTP 200 en \d+ ms", lines[1])
    assert re.match(r"external -> bo3 POST /api/bo3/gaps : HTTP 200 en \d+ ms", lines[2])


def test_contract_item_strips_private_fields():
    row = {**WARDROBE[0], "user_id": "uuid-alice", "detection": {"box": [1]}, "field_confidence": {}, "seasons": None}
    item = og.contract_item(row)
    assert "user_id" not in item and "detection" not in item and "field_confidence" not in item
    assert item["seasons"] == [] and item["tags"] == [] and item["needs_review"] is False


# ------------------------------------------------------------------ garde-fou du LLM avec les modules
def test_llm_may_choose_an_enabled_module_among_cues(fake):
    message = "Est-ce que je devrais acheter ce manteau https://shop.test/coat.jpg ?"
    state = run(make(fake, llm=lambda s, m, sc: {"route": "external:smart_purchasing"}), message)
    assert state["route"] == "external:smart_purchasing" and state["route_source"] == "LLM qwen2.5:3b"


def test_llm_cannot_choose_a_disabled_module(fake):
    mods = modules(bo3={"enabled": False})
    state = run(make(fake, llm=lambda s, m, sc: {"route": "external:bo3"}, mods=mods), "Une petite question mode")
    assert state["route"] == "clarify" and "valeur non autorisée" in state["route_source"]


def test_build_graph_does_not_touch_the_callers_gateway(fake):
    services = dict(SERVICES)
    og.build_graph(gateway=Gateway(services, transport=fake), llm=None, modules=modules())
    assert set(services) == set(SERVICES)
    with pytest.raises(ValueError, match="déjà pris"):
        og.build_graph(gateway=Gateway(dict(SERVICES), transport=fake), llm=None,
                       modules={"bo1": modules_from_dict("bo1", CONFIG["bo3"])})


def test_render_template_keeps_types():
    out = og.render_template({"a": "$wardrobe_items", "b": "x $message y", "c": ["$price"], "d": 3},
                             {"wardrobe_items": [{"id": "1"}], "message": "hello", "price": 80.0})
    assert out == {"a": [{"id": "1"}], "b": "x hello y", "c": [80.0], "d": 3}


# ------------------------------------------------------------------ services.yaml livré
def test_shipped_services_yaml_declares_three_disabled_modules():
    mods = load_modules()
    assert set(mods) == {"smart_purchasing", "helpmepack", "bo3"}
    assert not any(m.enabled for m in mods.values())
    assert {m.url.rsplit(":", 1)[1] for m in mods.values()} == {"8050", "8020", "8030"}
    for module in mods.values():
        assert module.keywords and og.uses_var(module.request, "wardrobe_items")
        for pattern in module.keywords:
            re.compile(pattern)
