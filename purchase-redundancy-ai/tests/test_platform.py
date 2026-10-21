"""Accounts, per-user data, pagination, search, validation, rate limiting, cache, analytics, monitoring, WebSocket"""

import time
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from test_api import _png_base64

PASSWORD = "Garde-robe2026"


def register(client, email=None, **extra):
    email = email or f"user-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/auth/register", json={"email": email, "password": PASSWORD, **extra})
    assert r.status_code == 201, r.text
    data = r.json()
    return {"Authorization": f"Bearer {data['access_token']}"}, data


@pytest.fixture
def limiter():
    import main

    limiter = main.state["limiter"]
    saved = (limiter.enabled, dict(limiter.limits))
    yield limiter
    limiter.enabled, limiter.limits = saved[0], saved[1]


# ----------------------------------------------------------------------------
# Accounts
# ----------------------------------------------------------------------------

def test_register_login_me(client):
    email = f"ana-{uuid.uuid4().hex[:6]}@example.com"
    headers, data = register(client, email=email, display_name="Ana")
    assert data["user"]["email"] == email and data["token_type"] == "bearer"

    me = client.get("/auth/me", headers=headers).json()
    assert me["authenticated"] and me["user"]["display_name"] == "Ana"
    assert client.get("/auth/me").json()["authenticated"] is False  # guest

    login = client.post("/auth/login", json={"email": email.upper(), "password": PASSWORD})  # emails are case-insensitive
    assert login.status_code == 200 and login.json()["access_token"]


def test_register_rejects_bad_input(client):
    email = f"dup-{uuid.uuid4().hex[:6]}@example.com"
    register(client, email=email)
    assert client.post("/auth/register", json={"email": email, "password": PASSWORD}).status_code == 409
    assert client.post("/auth/register", json={"email": "not-an-email", "password": PASSWORD}).status_code == 422
    assert client.post("/auth/register", json={"email": "a@b.co", "password": "short1"}).status_code == 422
    assert client.post("/auth/register", json={"email": "a@b.co", "password": "onlyletters"}).status_code == 422
    assert client.post("/auth/register", json={"email": "a@b.co", "password": PASSWORD, "role": "admin"}).status_code == 422


def test_login_failures_are_identical(client):
    email = f"bob-{uuid.uuid4().hex[:6]}@example.com"
    register(client, email=email)
    wrong_password = client.post("/auth/login", json={"email": email, "password": "Wrong-pass1"})
    unknown_user = client.post("/auth/login", json={"email": "nobody@example.com", "password": PASSWORD})
    assert wrong_password.status_code == unknown_user.status_code == 401
    assert wrong_password.json() == unknown_user.json()  # no user enumeration


def test_invalid_and_expired_tokens(client):
    import main

    assert client.get("/wardrobe", headers={"Authorization": "Bearer garbage"}).status_code == 401
    secret = main.state["tokens"].secret_key
    expired = jwt.encode({"sub": "u_x", "typ": "access", "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
                         secret, algorithm="HS256")
    r = client.get("/wardrobe", headers={"Authorization": f"Bearer {expired}"})
    assert r.status_code == 401 and "expirée" in r.json()["detail"]
    forged = jwt.encode({"sub": "u_x", "typ": "access", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
                        "another-secret-of-sufficient-length-1234567890", algorithm="HS256")
    assert client.get("/wardrobe", headers={"Authorization": f"Bearer {forged}"}).status_code == 401


def test_auth_required_mode(client):
    import main

    main.state["auth_required"] = True
    try:
        assert client.get("/wardrobe").status_code == 401
        headers, _ = register(client)
        assert client.get("/wardrobe", headers=headers).status_code == 200
        assert client.get("/products?limit=1").status_code == 200  # the catalog stays public
    finally:
        main.state["auth_required"] = False


def test_wardrobes_and_history_are_private(client):
    alice, _ = register(client)
    bob, _ = register(client)
    product = client.get("/products?limit=1").json()["products"][0]
    item = client.post("/wardrobe", json={"product_id": product["id"]}, headers=alice).json()

    assert [i["id"] for i in client.get("/wardrobe", headers=alice).json()["items"]] == [item["id"]]
    assert client.get("/wardrobe", headers=bob).json()["items"] == []
    assert client.delete(f"/wardrobe/{item['id']}", headers=bob).status_code == 404
    assert client.patch(f"/wardrobe/{item['id']}", json={"name": "x"}, headers=bob).status_code == 404

    analysis = client.post("/analyze", headers=alice, json={"new_item": {"name": "Blue shirt", "category": "shirts"}}).json()
    assert client.get(f"/analysis/{analysis['analysis_id']}", headers=alice).status_code == 200
    assert client.get(f"/analysis/{analysis['analysis_id']}", headers=bob).status_code == 404
    assert client.get("/analyses", headers=bob).json()["items"] == []


def test_clear_only_deletes_own_photos(client):
    alice, _ = register(client)
    bob, _ = register(client)
    photo = "data:image/png;base64," + _png_base64((30, 30, 120))
    alice_item = client.post("/wardrobe", json={"image_base64": photo, "name": "Pull", "category": "shirts"}, headers=alice).json()
    client.post("/wardrobe", json={"image_base64": photo, "name": "Pull", "category": "shirts"}, headers=bob)
    client.delete("/wardrobe", headers=bob)
    assert client.get(alice_item["image_url"]).status_code == 200  # used to wipe every photo of the folder


def test_import_guest_data_on_signup(client):
    client.delete("/wardrobe")
    product = client.get("/products?limit=1").json()["products"][0]
    client.post("/wardrobe", json={"product_id": product["id"]})
    headers, data = register(client, import_guest_data=True)
    assert data["imported"]["wardrobe_items"] == 1
    assert len(client.get("/wardrobe", headers=headers).json()["items"]) == 1
    assert client.get("/wardrobe").json()["items"] == []


def test_password_hashing():
    from auth import hash_password, verify_password

    stored = hash_password("S3cret-pass", iterations=1000)
    assert stored.startswith("pbkdf2_sha256$1000$") and "S3cret" not in stored
    assert verify_password("S3cret-pass", stored)
    assert not verify_password("s3cret-pass", stored)
    assert hash_password("S3cret-pass", iterations=1000) != stored  # random salt
    assert not verify_password("x", "garbage")

# ----------------------------------------------------------------------------
# Pagination & search
# ----------------------------------------------------------------------------

def test_products_pagination(client):
    first = client.get("/products?limit=10&offset=0").json()
    second = client.get("/products?limit=10&offset=10").json()
    assert first["has_more"] and first["next_offset"] == 10
    assert {p["id"] for p in first["products"]}.isdisjoint({p["id"] for p in second["products"]})
    last = client.get(f"/products?limit=10&offset={first['total'] - 3}").json()
    assert len(last["products"]) == 3 and not last["has_more"] and last["next_offset"] is None
    assert client.get("/products?limit=0").status_code == 422
    assert client.get("/products?limit=1000").status_code == 422
    assert client.get("/products?offset=-1").status_code == 422


def test_products_filters_sort_facets(client):
    data = client.get("/products?priced=true&sort=price_asc&facets=true&limit=200").json()
    prices = [p["price"] for p in data["products"]]
    assert prices == sorted(prices) and all(prices)
    assert data["facets"]["priced"] == data["total"]
    assert sum(data["facets"]["category"].values()) == data["total"]

    ranged = client.get("/products?min_price=20&max_price=60&limit=200").json()["products"]
    assert ranged and all(20 <= p["price"] <= 60 for p in ranged)

    color = next(iter(client.get("/products?facets=true&limit=1").json()["facets"]["color"]))
    assert all(p["primary_color"] == color for p in client.get(f"/products?color={color}&limit=50").json()["products"])
    assert client.get("/products?sort=random").status_code == 422


def test_wardrobe_and_history_pagination(client):
    headers, _ = register(client)
    client.post("/wardrobe/sample", headers=headers)
    everything = client.get("/wardrobe", headers=headers).json()
    page = client.get("/wardrobe?limit=3&offset=3", headers=headers).json()
    assert page["total"] == everything["total"] and [i["id"] for i in page["items"]] == [i["id"] for i in everything["items"][3:6]]
    assert everything["total_value"] >= 0

    for name in ("A shirt", "B shirt", "C shirt"):
        client.post("/analyze", headers=headers, json={"new_item": {"name": name, "category": "shirts"}})
    history = client.get("/analyses?limit=2", headers=headers).json()
    assert history["total"] == 3 and len(history["items"]) == 2 and history["has_more"]

# ----------------------------------------------------------------------------
# Validation
# ----------------------------------------------------------------------------

@pytest.mark.parametrize("item", [
    {"name": "", "category": "shirts"},
    {"name": "x" * 500, "category": "shirts"},
    {"name": "Hat", "category": "hats"},
    {"name": "Shirt", "category": "shirts", "price": -5},
    {"name": "Shirt", "category": "shirts", "price": 10_000_000},
])
def test_analyze_rejects_invalid_items(client, item):
    assert client.post("/analyze", json={"new_item": item}).status_code == 422


def test_validation_normalizes_and_bounds(client):
    r = client.post("/analyze", json={"new_item": {"name": "  Navy shirt  ", "category": " Shirts "}, "wardrobe_items": []})
    assert r.status_code == 200 and r.json()["new_item"]["name"] == "Navy shirt"
    assert client.post("/analyze", json={"new_item": {"name": "x", "category": "shirts"}, "language": "<script>"}).status_code == 422
    assert client.post("/agent/run", json={"mission": "hack"}).status_code == 422
    assert client.post("/agent/run", json={"message": "x" * 5000}).status_code == 422
    assert client.post("/feedback", json={"item_id": "../etc", "feedback_type": "helpful", "rating": 3}).status_code == 422
    assert client.post("/wardrobe", json={"product_id": "x' OR 1=1 --"}).status_code == 422


def test_body_size_limit(client):
    huge = "A" * (16 * 1024 * 1024)
    r = client.post("/camera-capture", content=f'{{"image_base64": "{huge}"}}', headers={"content-type": "application/json"})
    assert r.status_code == 413

# ----------------------------------------------------------------------------
# Rate limiting
# ----------------------------------------------------------------------------

def test_rate_limit_heavy_endpoints(client, limiter):
    limiter.enabled = True
    limiter.limits["heavy"] = 3
    item = {"new_item": {"name": "Shirt", "category": "shirts"}, "wardrobe_items": []}
    codes = [client.post("/analyze", json=item).status_code for _ in range(5)]
    if codes[-1] != 429:  # the one-minute window rolled over during the test - retry once
        codes = [client.post("/analyze", json=item).status_code for _ in range(5)]
    assert codes.count(429) >= 1
    blocked = client.post("/analyze", json=item)
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) > 0 and blocked.headers["x-ratelimit-remaining"] == "0"
    assert client.get("/health").status_code == 200  # health checks are never limited


def test_rate_limit_login_bruteforce(client, limiter):
    limiter.enabled = True
    limiter.limits["auth"] = 2
    codes = {client.post("/auth/login", json={"email": "x@example.com", "password": "Nope-1234"}).status_code
             for _ in range(4)}
    assert 429 in codes


def test_rate_limit_headers_present(client, limiter):
    limiter.enabled = True
    r = client.get("/products?limit=1")
    assert int(r.headers["x-ratelimit-limit"]) == limiter.limits["default"]

# ----------------------------------------------------------------------------
# Cache
# ----------------------------------------------------------------------------

def test_memory_cache_ttl_lru_and_counter():
    from cache import Cache, MemoryCache, make_key

    cache = Cache("", default_ttl=60)
    assert cache.backend == "memory"
    key = make_key("t", {"b": 1, "a": 2})
    assert key == make_key("t", {"a": 2, "b": 1})  # stable whatever the dict order
    assert cache.get(key) is None
    cache.set(key, {"value": [1, 2]})
    assert cache.get(key) == {"value": [1, 2]}
    assert cache.stats()["hits"] == 1 and cache.stats()["misses"] == 1
    cache.set("pr:short", 1, ttl=-1)
    assert cache.get("pr:short") is None  # expired
    assert cache.invalidate("t") == 1 and cache.get(key) is None

    small = MemoryCache(max_items=2)
    for k in "abc":
        small.set(k, k, 60)
    assert small.get("a") is None and small.get("c") == "c"  # least recently used evicted
    assert [small.incr("n", 60) for _ in range(3)] == [1, 2, 3]


def test_unreachable_redis_falls_back_to_memory():
    from cache import Cache

    cache = Cache("redis://127.0.0.1:1/0")
    assert cache.backend == "memory"


def test_semantic_search_is_cached(client):
    import main

    cache = main.state["cache"]
    q = f"red wool scarf {uuid.uuid4().hex[:4]}"
    hits = cache.hits
    first = client.get("/products", params={"q": q, "limit": 5}).json()
    second = client.get("/products", params={"q": q, "limit": 5}).json()
    assert first == second and cache.hits > hits

# ----------------------------------------------------------------------------
# Logging, analytics, monitoring
# ----------------------------------------------------------------------------

def test_request_id_header(client):
    assert len(client.get("/health").headers["x-request-id"]) == 16
    assert client.get("/health", headers={"X-Request-ID": "abc-123"}).headers["x-request-id"] == "abc-123"


def test_json_log_formatter():
    import json
    import logging

    from logger import JsonFormatter

    record = logging.LogRecord("api", logging.INFO, __file__, 1, "GET /x -> 200", None, None)
    record.request_id, record.status = "r1", 200
    line = json.loads(JsonFormatter().format(record))
    assert line["message"] == "GET /x -> 200" and line["request_id"] == "r1" and line["status"] == 200


def test_client_events_and_summary(client):
    headers, _ = register(client)
    batch = {"session_id": "sess-12345678", "events": [{"name": "page_view", "page": "scan"},
                                                        {"name": "page_view", "page": "catalog"},
                                                        {"name": "camera_open", "properties": {"source": "scan"}}]}
    assert client.post("/analytics/events", json=batch, headers=headers).json() == {"accepted": 3}
    client.post("/analyze", headers=headers, json={"new_item": {"name": "Shirt", "category": "shirts", "price": 30}})

    summary = client.get("/analytics/summary?days=7", headers=headers).json()
    assert summary["analyses"] == 1 and sum(summary["verdicts"].values()) == 1
    assert summary["timeline"][0]["date"] == datetime.now(timezone.utc).date().isoformat()
    assert summary["page_views"] == {"scan": 1, "catalog": 1} and summary["events"]["camera_open"] == 1
    assert summary["categories"] == {"shirts": 1} and summary["explanation_sources"] == {"rules": 1}


@pytest.mark.parametrize("batch", [
    {"events": []},
    {"events": [{"name": "Bad Name!"}]},
    {"events": [{"name": "x_event", "properties": {"nested": {"a": 1}}}]},
    {"events": [{"name": "x_event"}] * 51},
    {"events": [{"name": "x_event", "email": "a@b.c"}]},
])
def test_client_events_validation(client, batch):
    assert client.post("/analytics/events", json=batch).status_code == 422


def test_system_metrics_and_prometheus(client):
    client.get("/products?limit=1")
    client.get("/analysis/does-not-exist")
    system = client.get("/analytics/system").json()
    routes = {r["route"]: r for r in system["routes"]}
    assert routes["GET /products"]["count"] >= 1 and routes["GET /products"]["p95_ms"] is not None
    assert routes["GET /analysis/{analysis_id}"]["errors_4xx"] >= 1  # path templates, not raw ids
    assert system["cache"]["backend"] in {"memory", "redis"} and system["database"]["healthy"]

    text = client.get("/metrics").text
    assert 'pr_requests_total{method="GET",route="/products",outcome="ok"}' in text
    assert "pr_products " in text and "# TYPE pr_request_duration_ms summary" in text


def test_health_reports_infrastructure(client):
    health = client.get("/health").json()
    assert health["database"] in {"sqlite", "postgresql"} and health["cache"] in {"memory", "redis"}

# ----------------------------------------------------------------------------
# HTTP caching & compression
# ----------------------------------------------------------------------------

def test_static_cache_headers_and_gzip(client):
    product = client.get("/products?limit=1").json()["products"][0]
    image = client.get(product["image_url"])
    assert "immutable" in image.headers["cache-control"]
    big = client.get("/products?limit=200", headers={"Accept-Encoding": "gzip"})
    assert big.headers.get("content-encoding") == "gzip"


def test_agent_stream_not_gzipped(client):
    r = client.post("/agent/run", json={"mission": "audit"}, headers={"Accept-Encoding": "gzip"})
    assert r.status_code == 200 and "content-encoding" not in r.headers

# ----------------------------------------------------------------------------
# Real-time
# ----------------------------------------------------------------------------

def test_websocket_receives_own_events_only(client):
    alice, alice_data = register(client)
    _, bob_data = register(client)
    with client.websocket_connect(f"/ws/live?token={alice_data['access_token']}") as alice_ws, \
            client.websocket_connect(f"/ws/live?token={bob_data['access_token']}") as bob_ws:
        assert alice_ws.receive_json()["type"] == "hello" and bob_ws.receive_json()["type"] == "hello"
        client.post("/analyze", headers=alice, json={"new_item": {"name": "Live shirt", "category": "shirts"}})
        event = alice_ws.receive_json()
        assert event["type"] == "analysis.created" and event["data"]["name"] == "Live shirt"
        bob_ws.send_text("ping")
        assert bob_ws.receive_json()["type"] == "pong"  # bob got nothing before his pong


def test_websocket_rejects_bad_token(client):
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/live?token=garbage") as ws:
            ws.receive_json()

# ----------------------------------------------------------------------------
# Database migration tool
# ----------------------------------------------------------------------------

def test_migrate_db_copies_every_table(client, tmp_path):
    import os

    from migrate_db import migrate

    register(client)
    target = f"sqlite:///{(tmp_path / 'copy.db').as_posix()}"
    copied = migrate(os.environ["DATABASE_URL"], target)
    assert copied["products"] >= 700 and copied["users"] >= 1
    with pytest.raises(SystemExit):
        migrate(os.environ["DATABASE_URL"], target)  # never overwrites silently
    assert migrate(os.environ["DATABASE_URL"], target, replace=True) == copied


def test_tests_never_touch_real_data(client):
    import config

    real = config.PROJECT_ROOT / "data"
    assert real not in config.UPLOAD_DIR.parents and config.UPLOAD_DIR != real / "uploads"
    assert config.PROJECT_ROOT / "logs" != config.LOG_FILE.parent


def test_sample_wardrobe_never_deletes_by_default(client):
    headers, _ = register(client)
    photo = "data:image/png;base64," + _png_base64((180, 40, 40))
    mine = client.post("/wardrobe", json={"image_base64": photo, "name": "Ma robe rouge", "category": "dresses"},
                       headers=headers).json()
    first = client.post("/wardrobe/sample", headers=headers).json()
    again = client.post("/wardrobe/sample", headers=headers).json()
    items = client.get("/wardrobe", headers=headers).json()["items"]
    assert mine["id"] in {i["id"] for i in items}            # the user's own piece survives
    assert client.get(mine["image_url"]).status_code == 200    # ...and so does its photo
    assert len(items) == 1 + first["added"] + again["added"]
    assert len({i.get("product_id") for i in items if i.get("product_id")}) == first["added"] + again["added"]  # no duplicates
    replaced = client.post("/wardrobe/sample?replace=true", headers=headers).json()
    assert mine["id"] not in {i["id"] for i in client.get("/wardrobe", headers=headers).json()["items"]}
    assert replaced["added"] >= 6

# ----------------------------------------------------------------------------
# Profiles & starter wardrobes (40+ pieces adapted to the gender)
# ----------------------------------------------------------------------------

def _catalog_by_id(client):
    return {p["id"]: p for p in client.get("/products?limit=200&offset=0").json()["products"]
            + client.get("/products?limit=200&offset=200").json()["products"]
            + client.get("/products?limit=200&offset=400").json()["products"]
            + client.get("/products?limit=200&offset=600").json()["products"]}


@pytest.mark.parametrize("gender,forbidden", [("Men", {"dresses"}), ("Women", set())])
def test_signup_with_profile_builds_starter_wardrobe(client, gender, forbidden):
    headers, data = register(client, display_name="Profil", gender=gender, clothing_size="M", shoe_size="42",
                             style_preferences=["casual"], favorite_colors=["black", "navy"], starter_wardrobe=True)
    assert data["user"]["gender"] == gender and data["user"]["clothing_size"] == "M"
    assert data["starter"]["added"] >= 40
    items = client.get("/wardrobe", headers=headers).json()["items"]
    assert len(items) >= 40
    categories = {i["category"] for i in items}
    assert not categories & forbidden
    assert sum(i["category"] == "accessories" for i in items) >= 5 and sum(i["category"] == "shoes" for i in items) >= 5
    if gender == "Women":
        assert "dresses" in categories
    catalog = _catalog_by_id(client)
    genders = {catalog[i["product_id"]].get("gender") for i in items if i["product_id"] in catalog}
    if any(p.get("gender") for p in catalog.values()):  # real catalog: only this gender or unisex pieces
        assert genders <= {gender, "Unisex", None}
    sizes = {(i["category"], i["size"]) for i in items}
    assert all(size == "42" for category, size in sizes if category == "shoes")
    assert all(size == "M" for category, size in sizes if category in ("shirts", "pants", "dresses", "outerwear"))
    assert all(size is None for category, size in sizes if category == "accessories")


def test_profile_update_and_validation(client):
    headers, _ = register(client)
    r = client.patch("/auth/me", json={"gender": "Women", "shoe_size": "38.5", "favorite_colors": ["pink"]}, headers=headers)
    assert r.status_code == 200 and r.json()["user"]["gender"] == "Women" and r.json()["user"]["shoe_size"] == "38.5"
    assert client.get("/auth/me", headers=headers).json()["user"]["favorite_colors"] == ["pink"]
    assert client.patch("/auth/me", json={"gender": "Robot"}, headers=headers).status_code == 422
    assert client.patch("/auth/me", json={"shoe_size": "99"}, headers=headers).status_code == 422
    assert client.patch("/auth/me", json={"email": "x@y.z"}, headers=headers).status_code == 422  # not editable here
    assert client.patch("/auth/me", json={"gender": "Men"}).status_code == 401  # guest


def test_starter_plan_and_guest_sample(client):
    for gender in ("Women", "Men", "Unspecified"):
        plan = client.get(f"/wardrobe/starter-plan?gender={gender}").json()
        assert plan["total"] >= 40 and plan["by_category"]["accessories"] >= 5
    assert "dresses" not in client.get("/wardrobe/starter-plan?gender=Men").json()["by_category"]
    client.delete("/wardrobe")
    sample = client.post("/wardrobe/sample?gender=Men").json()
    assert sample["added"] >= 40 and sample["gender"] == "Men" and "dresses" not in sample["by_category"]
    assert client.post("/wardrobe/sample?gender=Alien").status_code == 422
    client.delete("/wardrobe")


def test_starter_builder_without_gender_data():
    from wardrobe_builder import build_starter_wardrobe

    # The illustrated catalog has no gender field: the builder must still reach 40 pieces
    catalog = [{"id": f"p{i}", "category": c, "subcategory": s, "primary_color": "black"}
               for i, (c, s) in enumerate([("shirts", "t-shirt"), ("pants", "jeans"), ("shoes", "sneakers"),
                                           ("accessories", "watch"), ("dresses", "dress"), ("outerwear", "jacket")] * 20)]
    chosen = build_starter_wardrobe(catalog, "Women", seed=1)
    assert len(chosen) >= 40 and len({p["id"] for p in chosen}) == len(chosen)


def test_catalog_gender_filter_includes_unisex(client):
    products = client.get("/products?gender=Men&limit=200").json()["products"]
    assert products and {p.get("gender") for p in products} <= {"Men", "Unisex"}
