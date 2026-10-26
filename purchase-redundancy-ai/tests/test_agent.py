"""Wardrobe persistence, catalog images and the autonomous agent (local mode, offline)"""

import json

from test_api import _png_base64


def run_agent(client, **payload):
    r = client.post("/agent/run", json=payload)
    assert r.status_code == 200, r.text
    events = [json.loads(line) for line in r.text.splitlines() if line.strip()]
    assert events[0]["type"] in {"start", "error"}
    return events


def test_catalog_images_served(client):
    product = client.get("/products?limit=1").json()["products"][0]
    assert product["image_url"].startswith(("/images/products/", "/images/real/"))
    r = client.get(product["image_url"])
    assert r.status_code == 200 and r.headers["content-type"].startswith("image/")


def test_semantic_catalog_search(client):
    data = client.get("/products?q=leather boots&category=shoes&limit=5").json()
    assert len(data["products"]) == 5 and data["total"] >= 5  # semantic results are paginated too
    assert all(p["category"] == "shoes" for p in data["products"])


def test_wardrobe_crud_and_sample(client):
    client.delete("/wardrobe")
    sample = client.post("/wardrobe/sample?replace=true").json()
    assert sample["added"] >= 6
    items = client.get("/wardrobe").json()["items"]
    assert all(i["image_url"] for i in items)

    photo = client.post("/wardrobe", json={"image_base64": "data:image/png;base64," + _png_base64((20, 40, 160)),
                                           "name": "Ma chemise bleue", "category": "shirts"}).json()
    assert photo["image_url"].startswith("/uploads/")
    assert client.get(photo["image_url"]).status_code == 200

    assert client.delete(f"/wardrobe/{photo['id']}").status_code == 200
    assert client.delete("/wardrobe/does-not-exist").status_code == 404
    assert client.post("/wardrobe", json={"color": "red"}).status_code == 400


def test_analyze_uses_saved_wardrobe(client):
    client.post("/wardrobe/sample?replace=true")
    owned = client.get("/wardrobe").json()["items"][0]
    item = {k: owned[k] for k in ("name", "category", "color", "style", "material")}
    data = client.post("/analyze", json={"new_item": item, "language": "fr"}).json()
    assert data["similar_items"] and data["similar_items"][0]["name"] == owned["name"]
    assert data["recommendation"] in {"consider", "skip"}
    assert "Vous possédez déjà" in data["explanation"]


def test_agent_purchase_from_text(client):
    client.post("/wardrobe/sample?replace=true")
    events = run_agent(client, mission="purchase", message="Je veux acheter une chemise bleue en coton à 45 €", mode="local")
    steps = [e for e in events if e["type"] == "step" and e["status"] == "done"]
    assert {s["id"] for s in steps} >= {"understand", "wardrobe", "redundancy", "compat", "market", "quality", "decide"}
    final = events[-1]
    assert final["type"] == "final"
    assert final["verdict"] in {"buy", "consider", "skip"}
    assert final["item"]["category"] == "shirts" and final["item"]["color"] == "blue" and final["item"]["price"] == 45
    assert final["reasons"]


def test_agent_purchase_from_photo(client):
    events = run_agent(client, mission="purchase", image_base64="data:image/png;base64," + _png_base64(), mode="local",
                       item={"category": "shirts"})
    vision = next(e for e in events if e.get("id") == "vision" and e["status"] == "done")
    assert "colors" in vision["data"]
    assert events[-1]["type"] == "final"


def test_agent_needs_something_to_analyze(client):
    events = run_agent(client, mission="purchase", message="bonjour", mode="local")
    assert events[-1]["type"] == "error"


def test_agent_audit(client):
    client.post("/wardrobe/sample?replace=true")
    client.post("/wardrobe/sample?replace=true")  # sample replaces -> still a single copy
    events = run_agent(client, mission="audit", mode="local")
    final = events[-1]
    assert final["type"] == "final" and final["mission"] == "audit"
    assert "outfits" in final and "suggestions" in final


def test_agent_claude_mode_unavailable(client):
    events = run_agent(client, mission="purchase", message="robe rouge", mode="claude")
    assert events[-1]["type"] == "error"


def test_history_and_savings(client):
    client.post("/wardrobe/sample?replace=true")
    owned = client.get("/wardrobe").json()["items"][0]
    item = {k: owned[k] for k in ("name", "category", "color", "style", "material")}
    item["price"] = 40
    analysis = client.post("/analyze", json={"new_item": item, "image_base64": "data:image/png;base64," + _png_base64(),
                                             "language": "fr"}).json()
    history = client.get("/analyses?limit=5").json()["items"]
    assert history[0]["analysis_id"] == analysis["analysis_id"]
    assert history[0]["image_url"].startswith("/uploads/analysis-")
    stats = client.get("/stats").json()
    assert {"duplicates_avoided", "money_saved", "sources", "priced_products"} <= set(stats)


def test_analyze_catalog_product(client):
    product = client.get("/products?limit=1").json()["products"][0]
    item = {"name": product["name"], "category": product["category"], "color": product["primary_color"]}
    r = client.post("/analyze", json={"new_item": item, "product_id": product["id"], "language": "fr"})
    assert r.status_code == 200
    assert client.post("/analyze", json={"new_item": item, "product_id": "nope"}).status_code == 404


def test_wardrobe_edit(client):
    client.post("/wardrobe/sample?replace=true")
    item = client.get("/wardrobe").json()["items"][0]
    updated = client.patch(f"/wardrobe/{item['id']}", json={"name": "Ma chemise préférée", "color": "navy"}).json()
    assert updated["name"] == "Ma chemise préférée" and updated["color"] == "navy"
    assert client.patch("/wardrobe/nope", json={"name": "x"}).status_code == 404


def test_catalog_filters(client):
    priced = client.get("/products?priced=true&limit=200").json()["products"]
    assert all(p["price"] for p in priced)


def test_owned_products_not_suggested(client):
    client.post("/wardrobe/sample?replace=true")
    owned = client.get("/wardrobe").json()["items"][0]
    item = {k: owned[k] for k in ("name", "category", "color", "style", "material")}
    data = client.post("/analyze", json={"new_item": item, "product_id": owned["product_id"], "language": "fr"}).json()
    assert owned["product_id"] not in {m["id"] for m in data["catalog_matches"]}


def test_price_ceiling_excludes_unknown_prices(client):
    import main

    results = main.state["engine"].search_catalog({"name": "shirt", "category": "shirts"}, top_k=10, max_price=40)
    assert results and all(r["price"] is not None and r["price"] <= 40 for r in results)  # "cheaper" needs a known price
