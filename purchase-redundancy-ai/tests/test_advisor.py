"""Wardrobe insights (dashboard), the agent's missions, intent routing, conversation memory, Claude tool loop"""

import json
import uuid
from types import SimpleNamespace

import pytest


def account(client, gender="Men", starter=True, **profile):
    email = f"advisor-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/auth/register", json={"email": email, "password": "Advisor-2026", "gender": gender,
                                            "starter_wardrobe": starter, **profile})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def events_of(client, headers, **payload):
    r = client.post("/agent/run", json={"mode": "local", **payload}, headers=headers)
    assert r.status_code == 200, r.text
    return [json.loads(line) for line in r.text.splitlines() if line.strip()]

# ----------------------------------------------------------------------------
# Insights
# ----------------------------------------------------------------------------

def test_insights_full_report(client):
    headers = account(client, "Women", favorite_colors=["black"])
    report = client.get("/insights", headers=headers).json()
    assert report["pieces"] >= 40 and 0 <= report["health"] <= 100
    assert set(report["scores"]) == {"balance", "uniqueness", "versatility", "harmony"}
    assert {r["category"] for r in report["composition"]} >= {"shirts", "pants", "dresses", "shoes", "accessories"}
    assert report["palette"]["colors"] and report["outfits"]["good_outfits"] >= 0
    assert report["tips"] and all({"severity", "title", "detail"} <= set(t) for t in report["tips"])
    assert client.get("/insights", headers=headers).json() == report  # cached until the wardrobe changes


def test_insights_groups_duplicates_and_invalidates_cache(client):
    headers = account(client, starter=False)
    product = client.get("/products?category=shirts&limit=1").json()["products"][0]
    base = {"name": product["name"], "category": "shirts", "color": product["primary_color"], "style": "casual"}
    for _ in range(3):  # three copies of the same shirt = ONE group with two extra pieces
        client.post("/wardrobe", json=base, headers=headers)
    client.post("/wardrobe", json={"name": "Black jeans", "category": "pants", "color": "black"}, headers=headers)
    report = client.get("/insights", headers=headers).json()
    assert len(report["duplicates"]) == 1 and len(report["duplicates"][0]["items"]) == 3
    assert report["extra_pieces"] == 2 and report["tips"][0]["id"] == "duplicates"
    client.delete(f"/wardrobe/{report['duplicates'][0]['extra'][0]}", headers=headers)
    assert client.get("/insights", headers=headers).json()["extra_pieces"] == 1  # recomputed


def test_insights_suggestions_respect_gender(client):
    headers = account(client, "Men", starter=False)
    client.post("/wardrobe", json={"name": "White tee", "category": "shirts", "color": "white"}, headers=headers)
    report = client.get("/insights", headers=headers).json()
    catalog = {p["id"]: p for off in (0, 200, 400, 600) for p in client.get(f"/products?limit=200&offset={off}").json()["products"]}
    assert report["suggestions"]
    assert all(s["category"] != "dresses" for s in report["suggestions"])
    if any(p.get("gender") for p in catalog.values()):
        assert all(catalog[s["id"]].get("gender") in ("Men", "Unisex", None) for s in report["suggestions"])


def test_empty_wardrobe_insights(client):
    headers = account(client, starter=False)
    report = client.get("/insights", headers=headers).json()
    assert report["empty"] and report["tips"][0]["action"]["type"] == "starter"

# ----------------------------------------------------------------------------
# Agent missions (local planner)
# ----------------------------------------------------------------------------

def test_audit_mission_uses_insights(client):
    final = events_of(client, account(client, "Women"), mission="audit")[-1]
    assert final["type"] == "final" and final["mission"] == "audit"
    assert 0 <= final["insights"]["health"] <= 100 and final["insights"]["tips"]


def test_outfits_mission(client):
    events = events_of(client, account(client, "Men"), mission="outfits", message="Que porter pour un entretien cet hiver ?")
    understand = next(e for e in events if e.get("id") == "understand" and e["status"] == "done")
    assert understand["data"] == {"occasion": "interview", "season": "winter"}
    final = events[-1]
    assert final["mission"] == "outfits" and final["outfits"]
    ids = [p["id"] for o in final["outfits"] for p in o["pieces"] if p["category"] in ("shirts", "pants", "dresses")]
    assert len(ids) == len(set(ids))  # different outfits, not the same shirt three times


def test_shopping_and_declutter_missions(client):
    headers = account(client, "Women")
    shopping = events_of(client, headers, mission="shopping", budget=200)[-1]
    assert shopping["mission"] == "shopping" and shopping["reasons"]
    assert all((s.get("price") or 0) <= 200 for s in shopping["suggestions"])
    declutter = events_of(client, headers, mission="declutter")[-1]
    assert declutter["mission"] == "declutter" and "to_remove" in declutter


@pytest.mark.parametrize("message,mission", [
    ("Que mettre pour un mariage ?", "outfits"),
    ("Je veux revendre ce que j'ai en double", "declutter"),
    ("Il me manque quoi pour cet hiver ?", "shopping"),
    ("Fais le bilan de ma garde-robe", "audit"),
    ("Je pense acheter une chemise bleue à 40 €", "purchase"),
])
def test_ask_routes_free_text(client, message, mission):
    events = events_of(client, account(client, "Men"), mission="ask", message=message)
    assert events[0]["type"] == "start" and events[0]["mission"] == mission


def test_agent_history_validation(client):
    headers = account(client, starter=False)
    bad = client.post("/agent/run", json={"mission": "ask", "history": [{"role": "system", "content": "x"}]}, headers=headers)
    assert bad.status_code == 422  # only user / assistant turns
    too_long = client.post("/agent/run", json={"history": [{"role": "user", "content": "x"}] * 13}, headers=headers)
    assert too_long.status_code == 422

# ----------------------------------------------------------------------------
# LLM paths with fake clients (no network, no cost)
# ----------------------------------------------------------------------------

def test_openai_agent_gets_profile_history_and_cards(client):
    import main
    from test_llm_offline import FakeToolCall, _response, fake_openai

    agent = main.state["agent"]
    saved = agent.llm
    llm, completions = fake_openai([
        _response(tool_calls=[FakeToolCall("c1", "get_wardrobe_insights", {}),
                              FakeToolCall("c2", "suggest_outfits", {"occasion": "office", "season": "winter"})],
                  finish="tool_calls"),
        _response(content="Votre garde-robe est en bonne santé ; voici trois tenues pour le bureau."),
    ])
    agent.llm = llm
    try:
        headers = account(client, "Men", clothing_size="L")
        history = [{"role": "user", "content": "Bonjour"}, {"role": "assistant", "content": "Bonjour, que puis-je faire ?"}]
        r = client.post("/agent/run", json={"mission": "ask", "message": "Et pour le bureau ?", "mode": "llm",
                                            "history": history}, headers=headers)
        events = [json.loads(line) for line in r.text.splitlines()]
    finally:
        agent.llm = saved
    assert completions.requests[0]["tool_choice"] == "required"   # grounding: look at the data first
    assert completions.requests[1]["tool_choice"] == "auto"
    first = completions.requests[0]["messages"]
    assert "Gender: man" in first[0]["content"] and "Clothing size: L" in first[0]["content"]  # profile in the system prompt
    assert [m["content"] for m in first[1:3]] == ["Bonjour", "Bonjour, que puis-je faire ?"]   # conversation memory
    final = events[-1]
    assert final["type"] == "final" and final["insights"]["health"] is not None and "outfits" in final
    assert {e["title"] for e in events if e["type"] == "step"} >= {"Diagnostiquer la garde-robe", "Composer des tenues"}


def test_claude_agent_tool_loop_with_shared_tools(client):
    import main
    from llm_client import ClaudeClient

    class FakeMessages:
        def __init__(self):
            self.requests = []
            self.script = [
                SimpleNamespace(stop_reason="tool_use", usage=SimpleNamespace(input_tokens=50, output_tokens=10), model="claude-opus-5-5",
                                content=[SimpleNamespace(type="text", text="Je regarde."),
                                         SimpleNamespace(type="tool_use", id="tu1", name="plan_declutter", input={}),
                                         SimpleNamespace(type="tool_use", id="tu2", name="nope", input={})]),
                SimpleNamespace(stop_reason="end_turn", usage=SimpleNamespace(input_tokens=80, output_tokens=20), model="claude-opus-5-5",
                                content=[SimpleNamespace(type="text", text="Revendez les doublons.")]),
            ]

        def create(self, **kwargs):
            self.requests.append(kwargs)
            return self.script.pop(0)

    claude = ClaudeClient("", "claude-opus-5-5", enabled=False)
    fake = FakeMessages()
    claude.client = SimpleNamespace(beta=SimpleNamespace(messages=fake))
    claude.error = None
    wardrobe = [{"id": "a", "name": "Black tee", "category": "shirts", "color": "black"},
                {"id": "b", "name": "Black tee 2", "category": "shirts", "color": "black"}]
    result = claude.run_agent("Que revendre ?", wardrobe, main.state["engine"], profile={"gender": "Men"},
                              history=[{"role": "user", "content": "Salut"}, {"role": "assistant", "content": "Salut !"}])
    assert result["answer"] == "Revendez les doublons." and result["usage"] == {"input_tokens": 130, "output_tokens": 30}
    assert [s["tool"] for s in result["steps"]] == ["plan_declutter"]
    first, second = fake.requests
    assert {t["name"] for t in first["tools"]} >= {"get_wardrobe_insights", "suggest_outfits", "plan_shopping", "plan_declutter"}
    assert all("input_schema" in t for t in first["tools"]) and "Gender: man" in first["system"]
    assert first["tool_choice"] == {"type": "any"} and second["tool_choice"] == {"type": "auto"}
    assert first["messages"][0]["content"] == "Salut"
    tool_results = second["messages"][-1]["content"]
    assert [r["tool_use_id"] for r in tool_results] == ["tu1", "tu2"] and tool_results[1]["is_error"] is True


def test_different_colors_are_not_duplicates(client):
    import main

    engine = main.state["engine"]
    wardrobe = [{"id": "w", "name": "Puma watch", "category": "accessories", "color": "silver", "style": "casual"},
                {"id": "g", "name": "Puma watch", "category": "accessories", "color": "gold", "style": "casual"},
                {"id": "w2", "name": "Puma watch", "category": "accessories", "color": "silver", "style": "casual"}]
    pairs = {frozenset((p["item_a_id"], p["item_b_id"])) for p in engine.find_internal_duplicates(wardrobe)}
    assert frozenset(("w", "w2")) in pairs          # same watch, same color: duplicate
    assert frozenset(("w", "g")) not in pairs        # silver vs gold: not a duplicate


def test_starter_wardrobe_avoids_repeating_looks():
    from collections import Counter

    from wardrobe_builder import build_starter_wardrobe

    catalog = [{"id": f"p{i}", "category": "shirts", "subcategory": "t-shirt", "gender": "Men",
                "primary_color": ("black", "white", "navy", "gray", "green", "red", "blue", "beige", "brown")[i % 9]}
               for i in range(60)]
    chosen = build_starter_wardrobe(catalog, "Men", colors=["black"], seed=3, minimum=0)
    looks = Counter((p["subcategory"], p["primary_color"]) for p in chosen)
    assert len(chosen) >= 9 and max(looks.values()) <= -(-len(chosen) // 9)  # spread over the colors available


def test_children_products_never_in_adult_wardrobes():
    from wardrobe_builder import build_starter_wardrobe, fits

    catalog = [{"id": "k", "category": "pants", "subcategory": "skirt", "gender": "Kids", "primary_color": "blue"},
               {"id": "w", "category": "pants", "subcategory": "skirt", "gender": "Women", "primary_color": "blue"}]
    assert not fits(catalog[0], "Women") and not fits(catalog[0], "Unspecified") and fits(catalog[1], "Women")
    assert [p["id"] for p in build_starter_wardrobe(catalog, "Women", minimum=2)] == ["w"]


def test_wedding_outfits_respect_the_dress_code():
    from wardrobe_insights import compose_outfits

    wardrobe = [
        {"id": "t", "name": "Silk blouse", "category": "shirts", "subcategory": "top", "color": "white", "style": "casual"},
        {"id": "c", "name": "Boyfriend cargo pants", "category": "pants", "subcategory": "trousers", "color": "blue", "style": "casual"},
        {"id": "j", "name": "Blue jeans", "category": "pants", "subcategory": "jeans", "color": "blue", "style": "casual"},
        {"id": "p", "name": "Black tailored trousers", "category": "pants", "subcategory": "trousers", "color": "black", "style": "casual"},
        {"id": "d", "name": "Navy midi dress", "category": "dresses", "subcategory": "dress", "color": "navy", "style": "casual"},
        {"id": "s", "name": "White sneakers", "category": "shoes", "subcategory": "sneakers", "color": "white", "style": "casual"},
        {"id": "h", "name": "Black heels", "category": "shoes", "subcategory": "heels", "color": "black", "style": "casual"},
    ]
    result = compose_outfits(wardrobe, {"formal", "classic"}, {"sporty"}, "summer", dress_code="formal")
    used = {p["id"] for o in result["outfits"] for p in o["pieces"]}
    assert result["outfits"] and not used & {"c", "j", "s"}  # no cargo, jeans or sneakers at a wedding
    casual = compose_outfits(wardrobe, {"casual"}, set(), "summer", dress_code="casual")
    assert {p["id"] for o in casual["outfits"] for p in o["pieces"]} & {"c", "j", "s"}


def test_advisor_sees_catalog_subcategories(client):
    import main

    headers = account(client, "Men")
    me = client.get("/auth/me", headers=headers).json()["user"]["id"]
    pieces = main._full_wardrobe(me)
    assert pieces and all(p.get("subcategory") for p in pieces if p.get("product_id"))


def test_outfits_keep_shoes_whatever_their_season_label():
    from wardrobe_insights import compose_outfits

    wardrobe = [
        {"id": "d", "name": "Navy midi dress", "category": "dresses", "subcategory": "dress", "color": "navy", "season": "all-season"},
        {"id": "h", "name": "Black heels", "category": "shoes", "subcategory": "heels", "color": "black", "season": "fall"},
        {"id": "w", "name": "Wool coat", "category": "outerwear", "subcategory": "jacket", "color": "gray", "season": "winter"},
    ]
    outfit = compose_outfits(wardrobe, {"formal"}, set(), "summer", dress_code="formal")["outfits"][0]
    ids = [p["id"] for p in outfit["pieces"]]
    assert "h" in ids and "w" not in ids  # heels tagged "fall" are fine in summer, a winter coat is not
