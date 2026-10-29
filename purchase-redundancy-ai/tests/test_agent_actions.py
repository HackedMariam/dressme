"""Outfit Studio scoring, pairwise similarity, the agent's actions (proposals + approval) and its proactive watcher"""

import json
import uuid

from test_advisor import account


def pieces_by_category(client, headers):
    items = client.get("/wardrobe", headers=headers).json()["items"]
    by_cat = {}
    for item in items:
        by_cat.setdefault(item["category"], []).append(item)
    return by_cat


# ----------------------------------------------------------------------------
# Outfit Studio
# ----------------------------------------------------------------------------

def test_outfit_score_rewards_complete_looks(client):
    headers = account(client, "Men")
    cat = pieces_by_category(client, headers)
    full = [cat["shirts"][0]["id"], cat["pants"][0]["id"], cat["shoes"][0]["id"]]
    one = client.post("/outfits/score", json={"item_ids": full[:1]}, headers=headers).json()
    look = client.post("/outfits/score", json={"item_ids": full}, headers=headers).json()
    assert look["score"] > one["score"] and set(look["breakdown"]) >= {"harmony", "completeness", "coherence", "season"}
    assert any("base" in f or "chaussures" in f for f in one["feedback"]) and one["add"]  # what to add, from the wardrobe
    doubled = client.post("/outfits/score", json={"item_ids": full + [cat["pants"][1]["id"]]}, headers=headers).json()
    assert doubled["breakdown"]["doubled_roles"] == 1 and doubled["score"] < look["score"]


def test_outfit_score_only_accepts_owned_pieces(client):
    alice, bob = account(client, "Women"), account(client, "Men")
    alice_piece = client.get("/wardrobe", headers=alice).json()["items"][0]["id"]
    assert client.post("/outfits/score", json={"item_ids": [alice_piece]}, headers=bob).status_code == 404
    assert client.post("/outfits/score", json={"item_ids": []}, headers=bob).status_code == 422


def test_save_list_delete_outfits_and_daily_look(client):
    headers = account(client, "Women")
    cat = pieces_by_category(client, headers)
    ids = [cat["dresses"][0]["id"], cat["shoes"][0]["id"]]
    saved = client.post("/outfits", json={"name": "Dîner", "item_ids": ids, "occasion": "date"}, headers=headers)
    assert saved.status_code == 201 and saved.json()["score"] is not None
    listed = client.get("/outfits", headers=headers).json()
    assert listed["total"] == 1 and [p["id"] for p in listed["items"][0]["pieces"]] == ids
    assert client.delete(f"/outfits/{saved.json()['id']}", headers=headers).status_code == 200
    assert client.get("/outfits", headers=headers).json()["total"] == 0

    daily = client.get("/outfits/daily", headers=headers).json()
    assert daily["outfit"]["pieces"] and 0 <= daily["outfit"]["score"] <= 100 and daily["why"]
    assert client.get("/outfits/daily", headers=headers).json()["outfit"] == daily["outfit"]  # stable within the day


def test_compare_two_pieces(client):
    headers = account(client, "Men", starter=False)
    base = {"name": "Navy oxford shirt", "category": "shirts", "color": "navy", "style": "classic"}
    a = client.post("/wardrobe?watch=false", json=base, headers=headers).json()
    b = client.post("/wardrobe?watch=false", json=base, headers=headers).json()
    c = client.post("/wardrobe?watch=false", json={"name": "Red running shoes", "category": "shoes", "color": "red"},
                    headers=headers).json()
    same = client.post("/wardrobe/compare", json={"item_a": a["id"], "item_b": b["id"]}, headers=headers).json()
    other = client.post("/wardrobe/compare", json={"item_a": a["id"], "item_b": c["id"]}, headers=headers).json()
    assert same["duplicate"] and same["same_category"] and same["similarity"] >= 0.75
    assert not other["duplicate"] and not other["same_category"]
    assert client.post("/wardrobe/compare", json={"item_a": a["id"], "item_b": a["id"]}, headers=headers).status_code == 422

# ----------------------------------------------------------------------------
# Proactive watcher + approval
# ----------------------------------------------------------------------------

def test_watcher_flags_a_new_duplicate_and_approval_removes_it(client):
    headers = account(client, "Men", starter=False)
    piece = {"name": "Black leather belt", "category": "accessories", "color": "black", "style": "classic"}
    first = client.post("/wardrobe", json=piece, headers=headers).json()
    assert "agent_alert" not in first                       # nothing to compare with yet
    second = client.post("/wardrobe", json=piece, headers=headers).json()
    alert = second["agent_alert"]
    assert alert["kind"] == "duplicate_alert" and alert["status"] == "pending" and alert["source"] == "watcher"
    assert client.get("/agent/actions?status=pending", headers=headers).json()["pending"] == 1

    done = client.post(f"/agent/actions/{alert['id']}/approve", headers=headers).json()
    assert done["status"] == "done" and done["result"]["removed"] == ["Black leather belt"]
    assert [i["id"] for i in client.get("/wardrobe", headers=headers).json()["items"]] == [first["id"]]
    assert client.post(f"/agent/actions/{alert['id']}/approve", headers=headers).status_code == 409  # only once


def test_rejecting_keeps_the_piece_and_actions_are_private(client):
    headers, other = account(client, "Men", starter=False), account(client, "Men", starter=False)
    piece = {"name": "White sneakers", "category": "shoes", "color": "white", "style": "casual"}
    client.post("/wardrobe", json=piece, headers=headers)
    alert = client.post("/wardrobe", json=piece, headers=headers).json()["agent_alert"]
    assert client.post(f"/agent/actions/{alert['id']}/approve", headers=other).status_code == 404  # not yours
    assert client.post(f"/agent/actions/{alert['id']}/reject", headers=headers).json()["status"] == "rejected"
    assert len(client.get("/wardrobe", headers=headers).json()["items"]) == 2
    assert client.get("/agent/actions", headers=other).json()["items"] == []


def test_bulk_imports_do_not_trigger_the_watcher(client):
    headers = account(client, "Women")  # starter wardrobe: 50 pieces, no alert
    assert client.get("/agent/actions", headers=headers).json()["items"] == []

# ----------------------------------------------------------------------------
# The agent acts
# ----------------------------------------------------------------------------

def test_local_declutter_prepares_the_removal(client):
    headers = account(client, "Men", starter=False)
    piece = {"name": "Grey hoodie", "category": "shirts", "color": "gray", "style": "casual"}
    for _ in range(2):
        client.post("/wardrobe?watch=false", json=piece, headers=headers)
    client.post("/wardrobe?watch=false", json={"name": "Blue jeans", "category": "pants", "color": "blue"}, headers=headers)
    r = client.post("/agent/run", json={"mission": "declutter", "mode": "local"}, headers=headers)
    final = [json.loads(line) for line in r.text.splitlines()][-1]
    assert final["proposals"] and final["proposals"][0]["kind"] == "remove_items"
    assert len(client.get("/wardrobe", headers=headers).json()["items"]) == 3  # nothing removed before approval
    client.post(f"/agent/actions/{final['proposals'][0]['id']}/approve", headers=headers)
    assert len(client.get("/wardrobe", headers=headers).json()["items"]) == 2


def test_llm_agent_scores_saves_and_proposes(client):
    import main
    from test_llm_offline import FakeToolCall, _response, fake_openai

    headers = account(client, "Men")
    cat = pieces_by_category(client, headers)
    look = [cat["shirts"][0]["id"], cat["pants"][0]["id"], cat["shoes"][0]["id"]]
    extra = cat["shirts"][1]["id"]
    agent = main.state["agent"]
    saved_llm = agent.llm
    agent.llm, completions = fake_openai([
        _response(tool_calls=[FakeToolCall("c1", "score_outfit", {"item_ids": look}),
                              FakeToolCall("c2", "compare_items", {"item_a": look[0], "item_b": extra}),
                              FakeToolCall("c3", "save_outfit", {"name": "Bureau", "item_ids": look, "occasion": "office"}),
                              FakeToolCall("c4", "propose_remove_items", {"item_ids": [extra], "reason": "En double"})],
                  finish="tool_calls"),
        _response(content="Tenue enregistrée ; le retrait attend votre accord."),
    ])
    try:
        r = client.post("/agent/run", json={"mission": "ask", "message": "Note et garde ma tenue", "mode": "llm"},
                        headers=headers)
        final = [json.loads(line) for line in r.text.splitlines()][-1]
    finally:
        agent.llm = saved_llm
    assert final["outfit_score"]["score"] > 0 and final["comparison"]["a"]["id"] == look[0]
    assert final["saved_outfit"]["name"] == "Bureau" and final["proposals"][0]["kind"] == "remove_items"
    assert client.get("/outfits", headers=headers).json()["items"][0]["source"] == "agent"
    assert extra in {i["id"] for i in client.get("/wardrobe", headers=headers).json()["items"]}  # proposal only
    tool_names = {t["function"]["name"] for t in completions.requests[0]["tools"]}
    assert {"score_outfit", "compare_items", "save_outfit", "propose_remove_items", "propose_add_items"} <= tool_names
