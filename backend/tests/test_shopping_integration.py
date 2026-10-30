import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import config, main
from app.auth import User, current_user
from app.storage import LocalStore


def image_bytes():
    output = io.BytesIO()
    Image.new("RGB", (30, 30), "navy").save(output, format="PNG")
    return output.getvalue()


@pytest.fixture
def shopping(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "LOCAL_DATA_DIR", tmp_path)
    store = LocalStore()
    store.insert_item({"id": "a", "user_id": "alice", "name": "Alice coat", "category": "jacket", "color_name": "navy"})
    store.insert_item({"id": "b", "user_id": "bob", "name": "Bob top", "category": "top", "color_name": "red"})
    monkeypatch.setattr(main, "store", store)
    calls = []

    class FakeEngine:
        def __init__(self, *, skip_llm, wardrobe):
            self.wardrobe = wardrobe

        def evaluate(self, *, image_path, price, budget, user_prompt):
            calls.append({"wardrobe": self.wardrobe, "image": Path(image_path).read_bytes(),
                          "path": image_path, "price": price, "budget": budget, "prompt": user_prompt})
            return {"status": "success", "candidate_item": {"image_source": image_path}}

    monkeypatch.setattr(main, "_shopping_components", lambda: (FakeEngine, lambda row: row["id"]))
    yield TestClient(main.app), calls
    main.app.dependency_overrides.pop(current_user, None)


def test_multipart_upload_uses_callers_wardrobe_and_all_form_fields(shopping):
    client, calls = shopping
    main.app.dependency_overrides[current_user] = lambda: User(id="alice")
    response = client.post("/api/shopping-assistant/evaluate",
                           files={"image_file": ("coat.png", image_bytes(), "image/png")},
                           data={"prompt": "For a work meeting?", "price": "85.25", "budget": "100"})
    assert response.status_code == 200, response.text
    assert response.json()["candidate_item"]["image_source"] == "uploaded image"
    assert calls[0]["wardrobe"] == ["a"]
    assert calls[0]["image"] == image_bytes()
    assert (calls[0]["prompt"], calls[0]["price"], calls[0]["budget"]) == ("For a work meeting?", 85.25, 100)
    assert not Path(calls[0]["path"]).exists()

    main.app.dependency_overrides[current_user] = lambda: User(id="bob")
    assert client.post("/api/shopping-assistant/evaluate", files={"image_file": ("x.png", image_bytes(), "image/png")}).status_code == 200
    assert calls[1]["wardrobe"] == ["b"]

    main.app.dependency_overrides[current_user] = lambda: User(id="new-user")
    assert client.post("/api/shopping-assistant/evaluate", files={"image_file": ("x.png", image_bytes(), "image/png")}).status_code == 200
    assert calls[2]["wardrobe"] == []


def test_image_url_and_invalid_inputs(shopping, monkeypatch):
    client, calls = shopping
    main.app.dependency_overrides[current_user] = lambda: User(id="alice")
    urls = []
    monkeypatch.setattr(main, "_download_shopping_image", lambda url: urls.append(url) or image_bytes())
    response = client.post("/api/shopping-assistant/evaluate", data={"image_url": "https://example.com/a.png", "price": "9", "budget": "12", "prompt": "Weekend"})
    assert response.status_code == 200, response.text
    assert urls == ["https://example.com/a.png"]
    assert response.json()["candidate_item"]["image_source"] == urls[0]
    assert (calls[0]["price"], calls[0]["budget"], calls[0]["prompt"]) == (9, 12, "Weekend")
    assert client.post("/api/shopping-assistant/evaluate", data={"price": "1"}).status_code == 422
    assert client.post("/api/shopping-assistant/evaluate", files={"image_file": ("a.txt", b"not an image", "text/plain")}).status_code == 400
    assert client.post("/api/shopping-assistant/evaluate", files={"image_file": ("x.png", image_bytes(), "image/png")}, data={"price": "-1"}).status_code == 422


def test_store_failure_never_falls_back_to_sample_wardrobe(shopping, monkeypatch):
    client, calls = shopping
    def fail(_user_id):
        raise RuntimeError("store unavailable")
    monkeypatch.setattr(main.store, "list_items", fail)
    response = client.post("/api/shopping-assistant/evaluate", files={"image_file": ("x.png", image_bytes(), "image/png")})
    assert response.status_code == 503
    assert not calls


def test_download_rejects_unsupported_urls_and_oversized_images(monkeypatch):
    from fastapi import HTTPException
    from urllib import request

    with pytest.raises(HTTPException) as invalid:
        main._download_shopping_image("file:///local/image.jpg")
    assert invalid.value.status_code == 400

    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            pass
        def read(self, _limit):
            return b"12345"

    monkeypatch.setattr(config, "MAX_UPLOAD_MB", 4 / (1024 * 1024))
    monkeypatch.setattr(request, "urlopen", lambda *_args, **_kwargs: Response())
    with pytest.raises(HTTPException) as oversized:
        main._download_shopping_image("https://example.com/image.jpg")
    assert oversized.value.status_code == 413


def test_engine_package_import_and_real_wardrobe_mapping():
    engine, convert = main._shopping_components()
    garment = convert({"id": "a", "name": "Navy coat", "category": "jacket", "color_name": "navy", "formality": 3})
    assert (garment.id, garment.name, garment.color, garment.formality_level) == ("a", "Navy coat", "navy", 3)
    assert engine(skip_llm=True, wardrobe=[]).wardrobe == []


def test_request_runs_real_engine_with_callers_items(shopping, monkeypatch):
    client, _ = shopping
    from smart_purchasing import inference
    from smart_purchasing.wardrobe_loader import row_to_garment

    monkeypatch.setattr(inference, "analyze_item", lambda _candidate: {"category": "jacket", "color": "navy"})
    monkeypatch.setattr(main, "_shopping_components", lambda: (
        lambda **kwargs: inference.DressMeInferenceEngine(skip_llm=True, wardrobe=kwargs["wardrobe"]),
        row_to_garment,
    ))
    main.app.dependency_overrides[current_user] = lambda: User(id="alice")
    response = client.post("/api/shopping-assistant/evaluate",
                           files={"image_file": ("x.png", image_bytes(), "image/png")},
                           data={"prompt": "Should I buy this for work?", "price": "80", "budget": "50"})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["candidate_item"]["price"] == 80
    assert result["candidate_item"]["budget"] == 50
    assert result["user_query"] == "Should I buy this for work?"
    assert result["tool_evidence"]["closest_wardrobe_match"] == "Alice coat"
    assert result["tool_evidence"]["budget_penalty"] > 0
    assert result["tool_evidence"]["prediction_source"] in {"xgboost", "heuristic"}


def test_uploaded_image_runs_real_vision_and_engine(shopping, monkeypatch):
    client, _ = shopping
    from smart_purchasing import inference
    from smart_purchasing.wardrobe_loader import row_to_garment

    monkeypatch.setattr(main, "_shopping_components", lambda: (
        lambda **kwargs: inference.DressMeInferenceEngine(skip_llm=True, wardrobe=kwargs["wardrobe"]),
        row_to_garment,
    ))
    main.app.dependency_overrides[current_user] = lambda: User(id="alice")
    sample = Path(__file__).resolve().parents[2] / "smart_purchasing" / "data" / "sample_camel_blazer.jpg"
    response = client.post("/api/shopping-assistant/evaluate",
                           files={"image_file": ("blazer.jpg", sample.read_bytes(), "image/jpeg")},
                           data={"prompt": "Is this good for work?", "price": "80", "budget": "50"})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["candidate_item"]["detected_category"] == "jacket"
    assert result["candidate_item"]["image_source"] == "uploaded image"
    assert result["tool_evidence"]["budget_penalty"] > 0
