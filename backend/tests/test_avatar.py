"""3D avatar + virtual try-on, with fal.ai replaced by an in-memory fake (no network, no money)."""
import io
import json
import threading
import time

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import avatar, config, main
from app.storage import LocalStore

REAL_CLIENT = avatar._client   # the fixture below replaces it with a fake
GLB = b"glTF" + b"\x02\x00\x00\x00" + b"x" * 40
HUNYUAN = "fal-ai/hunyuan3d/v2"
FASHN = "fal-ai/fashn/tryon/v1.6"


def _png(color=(120, 80, 60), size=(64, 96)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


class FakeFal:
    """Plays the fal queue API and the CDN that serves the generated files."""

    def __init__(self):
        self.runs: list[tuple[str, dict]] = []
        self.fail_models: set[str] = set()       # submit answers HTTP 500 for these
        self.status_error: str | None = None     # status answers with an error message
        self.locked = False                      # account without credit: uploads are cut off, probes get HTTP 403
        self.offline = False                     # every request fails at the network level

    def models(self) -> list[str]:
        return [model for model, _ in self.runs]

    def handler(self, request: httpx.Request) -> httpx.Response:
        host, path = request.url.host, request.url.path
        assert request.headers["authorization"] == "Key test-key"
        if self.offline:
            raise httpx.ConnectError("no network", request=request)
        if self.locked:
            if request.method == "POST":
                raise httpx.WriteError("connection closed while uploading", request=request)
            return httpx.Response(403, json={"detail": "User is locked. Reason: Exhausted balance."})
        if host == "cdn.fal.test":
            return httpx.Response(200, content=GLB if path.endswith(".glb") else _png((200, 10, 10)))
        if request.method == "POST":
            model = path.lstrip("/")
            if model in self.fail_models:
                return httpx.Response(500, json={"detail": "boom"})
            self.runs.append((model, json.loads(request.content)))
            rid = f"r{len(self.runs)}"
            base = "https://queue.fal.run/" + "/".join(model.split("/")[:2]) + f"/requests/{rid}"
            return httpx.Response(200, json={"request_id": rid, "status_url": base + "/status", "response_url": base})
        if path.endswith("/status"):
            if self.status_error:
                return httpx.Response(200, json={"status": "IN_PROGRESS", "error": self.status_error})
            return httpx.Response(200, json={"status": "COMPLETED"})
        rid = path.rsplit("/", 1)[1]
        model = self.runs[int(rid[1:]) - 1][0]
        if model == HUNYUAN:
            return httpx.Response(200, json={"model_mesh": {"url": f"https://cdn.fal.test/{rid}.glb"}})
        return httpx.Response(200, json={"images": [{"url": f"https://cdn.fal.test/{rid}.png"}]})


@pytest.fixture
def fal(monkeypatch, tmp_path):
    fake = FakeFal()
    monkeypatch.setattr(config, "FAL_KEY", "test-key")
    monkeypatch.setattr(config, "LOCAL_DATA_DIR", tmp_path)
    monkeypatch.setattr(main, "store", LocalStore())
    monkeypatch.setattr(avatar, "_events", {})
    monkeypatch.setattr(avatar, "_jobs", {})
    monkeypatch.setattr(avatar, "_client", lambda: avatar.FalClient(
        "test-key", 5, transport=httpx.MockTransport(fake.handler), poll_interval=0))
    return fake


@pytest.fixture
def client(fal):
    return TestClient(main.app)


def _wait(client, job_id) -> dict:
    for _ in range(200):
        job = client.get(f"/api/avatar/jobs/{job_id}").json()
        if job["status"] != "running":
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def _create(client, wait=True, **form):
    reply = client.post("/api/avatar", data={"consent": "true", **form},
                        files={"file": ("me.png", _png(), "image/png")})
    if wait and reply.status_code == 200:
        return reply, _wait(client, reply.json()["job_id"])
    return reply, None


def _add_item(group="Tops", name="Navy sweater") -> str:
    item = main.store.insert_item({"id": f"item-{group}", "user_id": config.LOCAL_USER_ID, "name": name,
                                   "category": "top", "category_group": group})
    main.store.upload(f"{config.LOCAL_USER_ID}/{item['id']}/cutout.png", _png((0, 0, 120)), "image/png")
    return item["id"]


def _tryon(client, item, wait=True, **extra):
    reply = client.post("/api/avatar/tryon", json={"item_id": item, **extra})
    job = _wait(client, reply.json()["job_id"]) if wait and reply.status_code == 200 and "job_id" in reply.json() else None
    return reply, job


def test_status_before_any_avatar(client):
    assert client.get("/api/avatar").json() == {"configured": True, "exists": False, "created_at": None,
                                                "tryons": [], "job": None}


def test_create_avatar_turns_the_photo_into_a_3d_model_and_keeps_it_privately(client, fal):
    reply, job = _create(client)
    assert reply.status_code == 200 and job["status"] == "done", job

    model, inputs = fal.runs[0]
    assert model == HUNYUAN and inputs["textured_mesh"] is True
    assert inputs["input_image_url"].startswith("data:image/jpeg;base64,")

    assert sorted(main.store.private_list(config.LOCAL_USER_ID)) == ["avatar.glb", "meta.json", "photo.jpg"]
    served = client.get("/api/avatar/model")
    assert served.status_code == 200 and served.headers["content-type"] == "model/gltf-binary"
    assert served.content.startswith(b"glTF")
    assert client.get("/api/avatar/photo").status_code == 200
    assert client.get("/api/avatar").json()["exists"] is True


def test_consent_is_required_and_nothing_is_sent_without_it(client, fal):
    reply = client.post("/api/avatar", data={"consent": "false"}, files={"file": ("m.png", _png(), "image/png")})
    assert reply.status_code == 400 and "consent" in reply.json()["detail"].lower()
    assert fal.runs == []


def test_not_configured_says_what_to_set(client, monkeypatch):
    monkeypatch.setattr(config, "FAL_KEY", "")
    monkeypatch.setattr(avatar, "_client", REAL_CLIENT)
    reply, job = _create(client)
    assert reply.status_code == 200 and job["status"] == "failed" and "FAL_KEY" in job["error"]


def test_a_locked_account_is_reported_as_missing_credit_not_as_a_network_problem(client, fal):
    fal.locked = True
    _, job = _create(client)
    assert job["status"] == "failed"
    assert "credit" in job["error"] and "FAL_KEY" in job["error"] and "Cannot reach" not in job["error"]


def test_a_real_network_failure_still_says_so(client, fal):
    fal.offline = True
    _, job = _create(client)
    assert job["status"] == "failed" and "Cannot reach fal.ai" in job["error"] and "ConnectError" in job["error"]


def test_unreadable_image_is_a_400_and_starts_no_job(client, fal):
    reply = client.post("/api/avatar", data={"consent": "true"}, files={"file": ("x.png", b"not an image", "image/png")})
    assert reply.status_code == 400 and fal.runs == []


def test_a_failed_generation_is_reported_and_saves_nothing(client, fal):
    fal.status_error = "model crashed"
    _, job = _create(client)
    assert job["status"] == "failed" and "model crashed" in job["error"]
    assert client.get("/api/avatar").json()["exists"] is False


def test_try_on_needs_an_avatar_first(client):
    assert _tryon(client, _add_item())[0].status_code == 409


def test_try_on_dresses_the_photo_then_converts_it_to_3d_and_is_cached(client, fal):
    item = _add_item()
    _create(client)
    reply, job = _tryon(client, item)
    assert reply.json()["cached"] is False and job["status"] == "done", job

    assert fal.models()[1:] == [FASHN, HUNYUAN]            # 2D try-on, then 3D on the dressed photo
    fashn_inputs = fal.runs[1][1]
    assert fashn_inputs["category"] == "tops"
    assert fashn_inputs["model_image"].startswith("data:image/jpeg") and fashn_inputs["garment_image"].startswith("data:image/jpeg")

    assert client.get(f"/api/avatar/tryon/{item}/model").content.startswith(b"glTF")
    assert client.get(f"/api/avatar/tryon/{item}/image").status_code == 200
    assert client.get("/api/avatar").json()["tryons"] == [{"item_id": item, "has_3d": True}]

    runs = len(fal.runs)
    assert _tryon(client, item)[0].json() == {"cached": True} and len(fal.runs) == runs    # free
    redo, redo_job = _tryon(client, item, refresh=True)
    assert redo_job["status"] == "done" and len(fal.runs) == runs + 2


def test_if_only_the_3d_step_fails_the_2d_result_is_kept_and_a_retry_runs_only_the_3d_step(client, fal):
    item = _add_item()
    _create(client)
    fal.fail_models = {HUNYUAN}
    _, job = _tryon(client, item)
    assert job["status"] == "failed"
    assert client.get("/api/avatar").json()["tryons"] == [{"item_id": item, "has_3d": False}]

    fal.fail_models = set()
    runs = len(fal.runs)
    _, retry = _tryon(client, item)
    assert retry["status"] == "done" and fal.models()[runs:] == [HUNYUAN]    # no second 2D charge


@pytest.mark.parametrize("group, category", [("Tops", "tops"), ("Outerwear", "tops"), ("Bottoms", "bottoms"), ("Dresses", "one-pieces")])
def test_wardrobe_groups_map_to_try_on_categories(client, fal, group, category):
    item = _add_item(group)
    _create(client)
    assert _tryon(client, item)[1]["status"] == "done"
    assert fal.runs[1][1]["category"] == category


def test_shoes_and_bags_are_refused_without_calling_fal(client, fal):
    item = _add_item("Shoes", "Sneakers")
    _create(client)
    runs = len(fal.runs)
    reply = client.post("/api/avatar/tryon", json={"item_id": item})
    assert reply.status_code == 422 and "tops" in reply.json()["detail"].lower() and len(fal.runs) == runs


def test_unknown_item_is_404(client):
    _create(client)
    assert client.post("/api/avatar/tryon", json={"item_id": "nope"}).status_code == 404


def test_a_new_avatar_discards_try_ons_made_on_the_old_photo(client):
    item = _add_item()
    _create(client)
    _tryon(client, item)
    assert len(client.get("/api/avatar").json()["tryons"]) == 1
    _create(client)
    assert client.get("/api/avatar").json()["tryons"] == []


def test_delete_removes_everything(client):
    item = _add_item()
    _create(client)
    _tryon(client, item)
    assert client.delete("/api/avatar").json()["exists"] is False
    assert main.store.private_list(config.LOCAL_USER_ID) in ([], ["tryon"])      # an empty local folder may remain
    assert main.store.private_list(f"{config.LOCAL_USER_ID}/tryon") == []
    assert client.get("/api/avatar/model").status_code == 404


def test_money_is_protected_by_a_per_user_limit(client, monkeypatch):
    monkeypatch.setattr(config, "AVATAR_CREATIONS_PER_DAY", 2)
    assert _create(client)[1]["status"] == "done"
    assert _create(client)[1]["status"] == "done"
    assert _create(client, wait=False)[0].status_code == 429


def test_only_one_generation_runs_at_a_time_per_user():
    gate = threading.Event()
    first = avatar.start_job("someone", "avatar", gate.wait)
    with pytest.raises(avatar.AvatarError) as busy:
        avatar.start_job("someone", "avatar", lambda: None)
    assert busy.value.status_code == 409
    avatar.start_job("someone-else", "avatar", lambda: None)      # another user is not blocked
    gate.set()
    for _ in range(100):
        if avatar.get_job("someone", first)["status"] != "running":
            break
        time.sleep(0.02)
    assert avatar.get_job("someone", first)["status"] == "done"


def test_a_job_belongs_to_its_user():
    job = avatar.start_job("alice", "avatar", lambda: None)
    with pytest.raises(avatar.AvatarError) as denied:
        avatar.get_job("bob", job)
    assert denied.value.status_code == 404


def test_item_ids_from_the_url_cannot_reach_other_folders(client):
    _create(client)
    assert client.get("/api/avatar/tryon/..%2Fphoto/model").status_code == 404


def _garment(client, wait=True, **form):
    reply = client.post("/api/avatar/tryon-garment", data=form, files={"file": ("shop.png", _png(), "image/png")})
    job = _wait(client, reply.json()["job_id"]) if wait and reply.status_code == 200 else None
    return reply, job


def test_a_shop_photo_is_tried_on_in_2d_only_and_stored_privately(client, fal):
    _create(client)
    runs = len(fal.runs)
    reply, job = _garment(client, group="Outerwear")
    assert reply.status_code == 200 and job["status"] == "done", job
    assert fal.models()[runs:] == [FASHN] and fal.runs[-1][1]["category"] == "tops"    # no 3D step: cheaper
    tryon_id = reply.json()["tryon_id"]
    assert tryon_id.startswith("shop-")
    assert client.get(f"/api/avatar/tryon/{tryon_id}/image").status_code == 200


def test_a_shop_photo_try_on_needs_an_avatar_and_a_supported_group(client, fal):
    assert _garment(client, group="Tops")[0].status_code == 409
    _create(client)
    runs = len(fal.runs)
    assert _garment(client, group="Shoes")[0].status_code == 422 and len(fal.runs) == runs
    assert client.post("/api/avatar/tryon-garment", data={"group": "Tops"}).status_code == 400


@pytest.mark.parametrize("url", ["http://example.com/a.jpg", "https://127.0.0.1/a.jpg", "https://localhost/a.jpg",
                                 "https://169.254.169.254/latest/meta-data"])
def test_remote_garment_images_cannot_reach_the_servers_own_network(url):
    with pytest.raises(avatar.AvatarError):
        avatar.fetch_remote_image(url)


def _outfit(client, ids, wait=True, **extra):
    reply = client.post("/api/avatar/tryon-outfit", json={"item_ids": ids, **extra})
    job = _wait(client, reply.json()["job_id"]) if wait and reply.status_code == 200 and "job_id" in reply.json() else None
    return reply, job


def test_an_outfit_is_tried_on_garment_by_garment_in_layer_order_and_cached(client, fal):
    ids = [_add_item("Outerwear", "Coat"), _add_item("Tops", "Shirt"), _add_item("Bottoms", "Trousers"),
           _add_item("Shoes", "Sneakers")]
    _create(client)
    runs = len(fal.runs)
    reply, job = _outfit(client, ids)
    assert reply.status_code == 200 and job["status"] == "done", job
    assert fal.models()[runs:] == [FASHN, FASHN, FASHN]                         # shoes are skipped, no 3D step
    assert [inputs["category"] for _, inputs in fal.runs[runs:]] == ["bottoms", "tops", "tops"]
    tryon_id = reply.json()["tryon_id"]
    assert tryon_id.startswith("outfit-") and client.get(f"/api/avatar/tryon/{tryon_id}/image").status_code == 200

    again = _outfit(client, list(reversed(ids)))[0]                              # same pieces, any order: free
    assert again.json() == {"cached": True, "tryon_id": tryon_id} and len(fal.runs) == runs + 3


def test_an_outfit_needs_an_avatar_and_at_least_one_wearable_piece(client, fal):
    top = _add_item("Tops", "Shirt")
    assert _outfit(client, [top])[0].status_code == 409
    _create(client)
    runs = len(fal.runs)
    assert _outfit(client, [_add_item("Shoes", "Sneakers")])[0].status_code == 422 and len(fal.runs) == runs
    assert _outfit(client, [])[0].status_code == 400
    assert _outfit(client, ["nope"])[0].status_code == 404


def test_a_dress_is_not_combined_with_a_top_or_a_bottom(client, fal):
    ids = [_add_item("Dresses", "Dress"), _add_item("Tops", "Shirt")]
    _create(client)
    runs = len(fal.runs)
    assert _outfit(client, ids)[1]["status"] == "done"
    assert [inputs["category"] for _, inputs in fal.runs[runs:]] == ["one-pieces"]


def test_a_key_restricted_to_other_models_gets_an_actionable_message():
    error = avatar._http_error(403, {"detail": "API key does not have access to model: fal-ai/hunyuan3d/v2",
                                     "type": "resource_restricted"})
    assert "fal-ai/hunyuan3d/v2" in error.message and "fal.ai/dashboard/keys" in error.message
    assert "credit" not in error.message                       # the account is funded: do not send the user to billing
    assert "billing" in avatar._http_error(403, {}).message    # a plain refusal still points to the key and the credit


def test_attempts_fal_refused_do_not_use_up_the_allowance_but_paid_failures_do(client, fal):
    # A refused key (403) did nothing and cost nothing: unlimited retries, no "limit reached".
    fal.locked = True
    for _ in range(config.AVATAR_CREATIONS_PER_DAY + 2):
        reply, job = _create(client)
        assert reply.status_code == 200 and job["status"] == "failed", (reply.text, job)
    fal.locked = False

    # A failure on fal.ai's side after accepting the work may have been charged: it keeps counting.
    fal.fail_models = {HUNYUAN}
    for _ in range(config.AVATAR_CREATIONS_PER_DAY):
        assert _create(client)[0].status_code == 200
    assert _create(client, wait=False)[0].status_code == 429
