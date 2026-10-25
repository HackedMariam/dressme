import base64
import io

from PIL import Image


def test_health_and_catalog(client):
    health = client.get("/health").json()
    assert health["status"] == "healthy"
    assert health["products_loaded"] >= 700
    assert health["products_in_database"] >= 700

    stats = client.get("/stats").json()
    assert stats["categories"] == 6
    assert stats["brands"] >= 20


def test_features_registry(client):
    data = client.get("/features").json()
    assert data["total"] == 31
    assert len(data["features"]) == 31


def test_duplicate_is_flagged(client, wardrobe):
    new_item = {"name": "Blue Casual Cotton Shirt", "category": "shirts", "color": "blue",
                "style": "casual", "material": "cotton", "use_case": "casual"}
    r = client.post("/analyze", json={"new_item": new_item, "wardrobe_items": wardrobe})
    assert r.status_code == 200
    data = r.json()
    assert data["recommendation"] in {"consider", "skip"}
    assert data["redundancy_score"] >= 50
    assert data["similar_items"][0]["name"] == "Blue Casual Cotton Shirt"
    assert data["alternatives"]
    assert data["catalog_matches"]


def test_unique_item_is_buy(client, wardrobe):
    new_item = {"name": "Burgundy Wool Coat", "category": "outerwear", "color": "burgundy",
                "style": "classic", "material": "wool"}
    data = client.post("/analyze", json={"new_item": new_item, "wardrobe_items": wardrobe}).json()
    assert data["recommendation"] == "buy"
    assert data["similar_items"] == []


def test_empty_wardrobe(client):
    new_item = {"name": "Red Dress", "category": "dresses", "color": "red", "style": "formal"}
    data = client.post("/analyze", json={"new_item": new_item, "wardrobe_items": []}).json()
    assert data["recommendation"] == "buy"


def test_analysis_persisted_and_feedback(client, wardrobe):
    new_item = {"name": "Navy Shirt", "category": "shirts", "color": "navy", "style": "business"}
    analysis = client.post("/analyze", json={"new_item": new_item, "wardrobe_items": wardrobe}).json()
    stored = client.get(f"/analysis/{analysis['analysis_id']}")
    assert stored.status_code == 200

    fb = client.post("/feedback", json={"item_id": analysis["analysis_id"], "feedback_type": "helpful", "rating": 4})
    assert fb.status_code == 200
    assert client.get("/stats").json()["total_feedback"] >= 1

    assert client.post("/feedback", json={"item_id": "x", "feedback_type": "helpful", "rating": 9}).status_code == 422


def test_feature_endpoint_errors(client):
    assert client.post("/feature/99", json={}).status_code == 404
    assert client.post("/feature/3", json={"unknown": 1}).status_code == 400


def _png_base64(color=(20, 40, 160)) -> str:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), color).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def test_upload_image(client):
    raw = base64.b64decode(_png_base64())
    r = client.post("/upload-image", files={"file": ("shirt.png", raw, "image/png")})
    assert r.status_code == 200
    data = r.json()
    assert data["analysis"]["colors"][0] in {"blue", "navy"}
    assert "suggested_item" in data

    bad = client.post("/upload-image", files={"file": ("a.txt", b"hello", "text/plain")})
    assert bad.status_code == 415


def test_camera_capture(client):
    r = client.post("/camera-capture", json={"image_base64": "data:image/png;base64," + _png_base64((200, 30, 30))})
    assert r.status_code == 200
    assert r.json()["analysis"]["colors"][0] == "red"
    assert "catalog_matches" in r.json() and "suggested_item" in r.json()

    assert client.post("/camera-capture", json={"image_base64": "not-an-image"}).status_code == 422


def test_agent_without_key_returns_503(client):
    assert client.post("/agent", json={"message": "Should I buy a blue shirt?"}).status_code == 503
