import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import config, enricher, main
from app.detector import Detection
from app.storage import LocalStore


def _png(color=(30, 50, 120)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), color).save(buf, format="PNG")
    return buf.getvalue()


class FakeDetector:
    def __init__(self, dets):
        self.dets = dets

    def detect(self, img, all_items=False):
        return self.dets if all_items else self.dets[:1]


def _det(category="dress", conf=0.9):
    return Detection(category=category, group="Dresses", confidence=conf, box=[0, 0, 60, 60],
                     area_ratio=0.8, colors=[{"name": "navy", "hex": "#1f2a4d", "share": 0.9}],
                     cutout_png=_png())


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main.GarmentDetector, "get", classmethod(lambda cls: FakeDetector([_det(), _det("shoe", 0.4)])))
    return TestClient(main.app)


def _upload(client, **params):
    return client.post("/api/items/analyze", params=params,
                       files={"file": ("photo.png", _png(), "image/png")})


def test_health(client):
    h = client.get("/api/health").json()
    assert h["store"] == "local" and h["auth"] is False and h["llm"] is False


def test_analyze_saves_item_with_rules_fallback(client):
    r = _upload(client)
    assert r.status_code == 200, r.text
    item = r.json()["items"][0]
    assert item["category"] == "dress" and item["category_group"] == "Dresses"
    assert item["color_name"] == "navy" and item["color_family"] == "neutral"
    assert item["occasions"] and item["style"]
    assert item["enrichment_source"].startswith("rules")
    assert item["user_id"] == config.LOCAL_USER_ID
    assert any(i["id"] == item["id"] for i in client.get("/api/items").json())
    assert client.get(item["cutout_url"].replace(config.PUBLIC_API_URL, "")).status_code == 200


def test_all_items_and_low_confidence_review(client):
    items = _upload(client, all_items="true").json()["items"]
    assert [i["category"] for i in items] == ["dress", "shoe"]
    assert items[1]["needs_review"] is True and items[1]["status"] == "review"


def test_llm_output_is_used_and_sanitized(client, monkeypatch):
    monkeypatch.setattr(config, "OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(enricher, "_call_openai", lambda det, png: {
        "name": "Navy Satin Slip Dress", "category": "dress", "subcategory": "slip dress",
        "color_name": "navy", "color_family": "neutral", "pattern": "solid", "material": "satin",
        "seasons": ["summer", "summer", "winterish"], "style": "elegant",
        "occasions": ["party", "date night", "wedding", "ceremony", "work"],
        "formality": 9, "warmth": 0, "description": "A slip dress.",
        "styling_tips": ["Gold heels.", "Cropped blazer."], "tags": ["Satin", "Evening"],
        "confidence": {"category": 0.95, "color": 0.9, "pattern": 0.9, "season": 0.8,
                       "style": 0.9, "occasion": 0.85, "material": 1.7},
    })
    item = _upload(client).json()["items"][0]
    assert item["name"] == "Navy Satin Slip Dress"
    assert item["seasons"] == ["summer"]
    assert item["occasions"] == ["party", "date night", "wedding", "ceremony"]
    assert item["formality"] == 5 and item["warmth"] == 1
    assert item["tags"] == ["satin", "evening"]
    assert item["field_confidence"]["material"] == 1.0
    assert item["enrichment_source"] == f"llm:{config.LLM_MODEL}"
    assert item["needs_review"] is False


def test_llm_error_falls_back_to_rules(client, monkeypatch):
    monkeypatch.setattr(config, "OPENAI_API_KEY", "sk-test")
    def boom(det, png):
        raise TimeoutError("slow")
    monkeypatch.setattr(enricher, "_call_openai", boom)
    item = _upload(client).json()["items"][0]
    assert item["enrichment_source"] == "rules (LLM error: TimeoutError)"


def test_correction_is_validated_and_logged(client):
    item = _upload(client).json()["items"][0]
    bad = client.patch(f"/api/items/{item['id']}", json={"fields": {"style": "pyjama-core"}})
    assert bad.status_code == 400
    r = client.patch(f"/api/items/{item['id']}",
                     json={"fields": {"style": "formal", "color_name": "burgundy", "seasons": ["winter"]}})
    assert r.status_code == 200
    up = r.json()
    assert up["status"] == "confirmed" and up["color_family"] == "warm"
    acc = {a["field"]: a for a in client.get("/api/stats/accuracy").json()}
    assert acc["style"]["corrected"] >= 1 and acc["category"]["accuracy"] is not None


def test_rejects_non_images_and_unknown_items(client):
    r = client.post("/api/items/analyze", files={"file": ("x.txt", b"hello", "text/plain")})
    assert r.status_code == 400
    assert client.patch("/api/items/nope", json={"fields": {}}).status_code == 404
    assert client.delete("/api/items/nope").status_code == 404


def test_delete(client):
    item = _upload(client).json()["items"][0]
    assert client.delete(f"/api/items/{item['id']}").status_code == 200
    assert client.get(f"/api/items/{item['id']}").status_code == 404


def test_store_isolates_users(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LOCAL_DATA_DIR", tmp_path)
    s = LocalStore()
    s.insert_item({"id": "a", "user_id": "alice", "name": "A"})
    s.insert_item({"id": "b", "user_id": "bob", "name": "B"})
    assert [i["id"] for i in s.list_items("alice")] == ["a"]
    assert s.get_item("bob", "a") is None
    with pytest.raises(KeyError):
        s.update_item("bob", "a", {"name": "hacked"})
    s.delete_item("bob", "a")
    assert s.get_item("alice", "a")["name"] == "A"
