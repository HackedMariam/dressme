"""DressMe API.

Pipeline for one photo:
  1. YOLO11m-seg  -> category + mask        (detector.py)
  2. mask pixels  -> colours + cut-out PNG  (detector.py / colors.py)
  3. GPT-4        -> occasion, style, colour, season, pattern, description (enricher.py)
  4. Storage      -> images + row in `items`, scoped to the signed-in user (storage.py)
"""
from __future__ import annotations

import base64
import hashlib
import io
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from . import agent, avatar, config, quality
from . import a2a_agents, outfit_agent as outfit_agent_module, wardrobe_agent
from .auth import User, current_user
from .colors import COLOR_NAMES
from .detector import GarmentDetector
from .enricher import color_family_of, enrich, fallback_enrich
from .storage import LocalStore, get_store, item_folder
from .taxonomy import (CLASS_TO_GROUP, COLOR_FAMILIES, GROUP_TO_ZONE, GROUPS, MODEL_CLASSES,
                       OCCASIONS, PATTERNS, SEASONS, STYLES)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("dressme")


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        GarmentDetector.get()
        log.info("Model loaded: %s", config.MODEL_PATH)
    except Exception:
        log.exception("Could not load model at %s", config.MODEL_PATH)
    log.info("Storage: %s | auth: %s | LLM: %s", store.kind, config.AUTH_ENABLED,
             config.LLM_MODEL if config.OPENAI_API_KEY else "off (rules)")
    yield


app = FastAPI(title="DressMe API", version="2.0", lifespan=lifespan)


# Registered before CORS so CORS wraps it: an unexpected error still reaches the
# browser as a readable JSON 500 instead of a CORS-blocked "network error".
@app.middleware("http")
async def json_errors(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as e:
        log.exception("Unhandled error on %s %s", request.method, request.url.path)
        detail = "Internal server error"
        if "schema cache" in str(e) or "PGRST2" in str(e):
            detail = ("The Supabase database schema is out of date. "
                      "Run supabase/schema.sql again in the Supabase SQL Editor.")
        return JSONResponse({"detail": detail}, status_code=500)


app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_credentials=True,
                   allow_methods=["GET", "POST", "PATCH", "DELETE"], allow_headers=["*"])

store = get_store()
if isinstance(store, LocalStore):
    app.mount("/files", StaticFiles(directory=store.root / "files"), name="files")

# fields the user can correct, and which are tracked for accuracy
EDITABLE = {"name", "category", "subcategory", "color_name", "color_hex", "color_family", "pattern",
            "material", "seasons", "style", "occasions", "formality", "warmth", "description", "tags"}
TRACKED = ["category", "color_name", "pattern", "seasons", "style", "occasions", "material"]


# ---------------------------------------------------------------------------
@app.get("/api/health")
def health() -> dict:
    try:
        GarmentDetector.get()
        model_ok = True
    except Exception:
        model_ok = False
    return {"ok": model_ok, "model_loaded": model_ok, "model": config.MODEL_PATH.name,
            "store": store.kind, "auth": config.AUTH_ENABLED,
            "llm": bool(config.OPENAI_API_KEY), "llm_model": config.LLM_MODEL,
            "avatar": avatar.is_configured()}


@app.get("/api/taxonomy")
def taxonomy() -> dict:
    return {"classes": MODEL_CLASSES, "class_to_group": CLASS_TO_GROUP, "groups": GROUPS,
            "patterns": PATTERNS, "seasons": SEASONS, "styles": STYLES, "occasions": OCCASIONS,
            "colors": COLOR_NAMES, "color_families": COLOR_FAMILIES}


@app.get("/api/me")
def me(user: User = Depends(current_user)) -> dict:
    return {"id": user.id, "email": user.email}


# ---------------------------------------------------------------------------
def classify_fields(det: dict, llm: dict) -> dict:
    """Merge detector + LLM output into the item fields, and decide if it needs review."""
    category = llm.get("category") if llm.get("category") in MODEL_CLASSES else det["category"]
    primary = (det.get("colors") or [{"name": "grey", "hex": "#8a8a8a"}])[0]
    conf = llm.get("confidence", {})
    category_conf = det["confidence"] if category == det["category"] \
        else min(det["confidence"], conf.get("category", 0.5))
    needs_review = (
        category_conf < config.REVIEW_THRESHOLD
        or category != det["category"]
        or min(conf.get("season", 1), conf.get("style", 1), conf.get("occasion", 1)) < 0.5
    )
    group = CLASS_TO_GROUP.get(category, "Accessories")
    color_name = llm.get("color_name") or primary["name"]
    fields = {
        "name": llm.get("name") or f"{color_name.title()} {category.title()}",
        "category": category,
        "category_group": group,
        "subcategory": llm.get("subcategory"),
        "color_name": color_name,
        "color_hex": primary["hex"],
        "color_family": llm.get("color_family") or color_family_of(color_name),
        "colors": det.get("colors"),
        "pattern": llm.get("pattern"),
        "material": llm.get("material"),
        "seasons": llm.get("seasons") or [],
        "style": llm.get("style"),
        "occasions": llm.get("occasions") or [],
        "formality": llm.get("formality"),
        "warmth": llm.get("warmth"),
        "description": llm.get("description"),
        "styling_tips": llm.get("styling_tips") or [],
        "tags": llm.get("tags") or [],
        "confidence": round(float(category_conf), 4),
        "field_confidence": {"category": round(float(category_conf), 3),
                             **{k: conf.get(k) for k in ("color", "pattern", "season", "style",
                                                         "occasion", "material")}},
        "needs_review": bool(needs_review),
        "status": "review" if needs_review else "auto",
        "zone": GROUP_TO_ZONE.get(group, "shelf"),
        "detection": det,
        "enrichment_source": llm.get("source"),
    }
    fields["predicted"] = {k: fields[k] for k in TRACKED}
    return fields


async def _read_upload(file: UploadFile) -> bytes:
    limit = int(config.MAX_UPLOAD_MB * 1024 * 1024)
    data = await file.read(limit + 1)
    if not data:
        raise HTTPException(400, "Empty file")
    if len(data) > limit:
        raise HTTPException(413, f"Image too large (max {config.MAX_UPLOAD_MB:g} MB)")
    return data


@app.post("/api/items/analyze")
async def analyze(file: UploadFile = File(...),
                  all_items: bool = Query(False, description="Save every garment found in the photo"),
                  save: bool = Query(True, description="False = preview only, nothing stored"),
                  fast: bool = Query(False, description="Skip the GPT-4 step for an instant save "
                                     "(category/colour only); call /reclassify afterwards to fill "
                                     "in the rest. Used by the live camera scan."),
                  force: bool = Query(False, description="Save even if the photo looks poor or like an "
                                     "item already in the wardrobe (the user confirmed)"),
                  only: int | None = Query(None, description="With force: save only the detection with this "
                                           "index (the one the user confirmed)"),
                  user: User = Depends(current_user)) -> dict[str, Any]:
    data = await _read_upload(file)
    return await run_in_threadpool(_analyze_sync, data, all_items, save, fast, user, force, only)


def _analyze_sync(data: bytes, all_items: bool, save: bool, fast: bool, user: User,
                  force: bool = False, only: int | None = None) -> dict[str, Any]:
    try:
        img = GarmentDetector.load_image(data)
    except Exception:
        raise HTTPException(400, "Unreadable image. Use a JPG, PNG, WEBP or HEIC photo.")
    try:
        detector = GarmentDetector.get()
    except Exception:
        log.exception("model unavailable")
        raise HTTPException(503, "The detection model is not available on the server.")

    detections = detector.detect(img, all_items=all_items)
    if not detections:
        raise HTTPException(422, "No clothing item detected. Try a photo of a single item on a plain background.")

    dets = [d.to_dict() for d in detections]
    for det, d in zip(detections, dets):
        d["signature"] = quality.signature(det.cutout_png) if det.cutout_png else None

    skipped: list[dict] = []
    if save:
        indexes = list(range(len(detections)))
        if only is not None:   # the user confirmed this one detection
            indexes = [only] if 0 <= only < len(detections) else []
        elif not force:
            # Nothing is saved without a look: poor captures and items that look like one already
            # owned come back with the reason, and the user decides ("Add anyway" = force + only).
            owned = store.list_items(user.id)
            kept = []
            for n in indexes:
                det = detections[n]
                problem = quality.live_problem(category=det.category, confidence=det.confidence, box=det.box,
                                               size=img.size, area_ratio=det.area_ratio, strict=fast)
                twin = None if problem else quality.find_duplicate(store, user.id, owned, det.category,
                                                                   dets[n]["signature"])
                if problem or twin:
                    skipped.append({"index": n, "category": det.category,
                                    "reason": "quality" if problem else "duplicate", "similar_item": twin,
                                    "note": problem or f"Looks like your {twin.get('name') or twin['category']}."})
                else:
                    kept.append(n)
            indexes = kept
        detections = [detections[n] for n in indexes]
        dets = [dets[n] for n in indexes]
        if skipped:
            log.info("user=%s not saved without confirmation: %s", user.id,
                     ", ".join(f"{k['category']}({k['reason']})" for k in skipped))
        if not detections:
            return {"items": [], "skipped": skipped[0] if skipped else None, "skipped_items": skipped}

    if fast:
        llms = [fallback_enrich(d) for d in dets]
    else:
        with ThreadPoolExecutor(max_workers=min(4, len(detections))) as pool:
            llms = list(pool.map(lambda pair: enrich(pair[0], pair[1].cutout_png), zip(dets, detections)))

    orig_bytes = b""
    if save:  # original, resized once (shared by every item of this photo)
        orig = img.copy()
        orig.thumbnail((1600, 1600))
        buf = io.BytesIO()
        orig.save(buf, format="JPEG", quality=88)
        orig_bytes = buf.getvalue()

    items = []
    for det, d, llm in zip(detections, dets, llms):
        item_id = str(uuid.uuid4())
        row = {"id": item_id, "user_id": user.id, **classify_fields(d, llm)}
        if save:
            folder = item_folder(user.id, item_id)
            row["image_url"] = store.upload(f"{folder}/original.jpg", orig_bytes, "image/jpeg")
            row["cutout_url"] = store.upload(f"{folder}/cutout.png", det.cutout_png, "image/png")
            try:
                row = store.insert_item(row)
            except Exception:
                store.delete_item(user.id, item_id)  # don't leave orphan images in the bucket
                raise
        else:
            row["image_url"] = ""
            row["cutout_url"] = "data:image/png;base64," + base64.b64encode(det.cutout_png).decode()
        items.append(row)
    log.info("user=%s analysed %d item(s): %s", user.id, len(items),
             ", ".join(f"{i['category']}/{i['enrichment_source']}" for i in items))
    return {"items": items, "skipped": skipped[0] if skipped else None, "skipped_items": skipped}


@app.get("/api/items")
def list_items(user: User = Depends(current_user)) -> list[dict]:
    return store.list_items(user.id)


@app.post("/api/items/quick-detect")
async def quick_detect(file: UploadFile = File(...), user: User = Depends(current_user)) -> dict[str, Any]:
    """Cheap preview detection for the live camera scan: YOLO only, no save, no GPT-4.
    Called repeatedly (every few hundred ms) while the camera is pointed at something,
    so it never raises â€” an unreadable frame or an empty view just means no detection.
    """
    data = await _read_upload(file)
    return await run_in_threadpool(_quick_detect_sync, data)


def _quick_detect_sync(data: bytes) -> dict[str, Any]:
    try:
        img = GarmentDetector.load_image(data)
        detector = GarmentDetector.get()
    except Exception:
        return {"detections": []}

    out = []
    for det in detector.detect(img, all_items=False):
        d = det.to_dict()
        primary = (d.get("colors") or [{}])[0]
        out.append({"category": d["category"], "group": d["group"], "confidence": d["confidence"],
                    "box": d["box"], "color_name": primary.get("name"),
                    "problem": quality.live_problem(category=det.category, confidence=det.confidence,
                                                    box=det.box, size=img.size, area_ratio=det.area_ratio)})
    return {"detections": out}


@app.post("/api/search/photo")
async def search_by_photo(file: UploadFile = File(...), user: User = Depends(current_user)) -> dict[str, Any]:
    """Find wardrobe items that look like the garment in this photo.

    Skips the LLM enrichment step (enrich() calls GPT-4) so this stays fast
    enough for a "take a photo to search" interaction.
    """
    data = await _read_upload(file)
    return await run_in_threadpool(_search_by_photo_sync, data, user)


def _search_by_photo_sync(data: bytes, user: User) -> dict[str, Any]:
    try:
        img = GarmentDetector.load_image(data)
    except Exception:
        raise HTTPException(400, "Unreadable image. Use a JPG, PNG, WEBP or HEIC photo.")
    try:
        detector = GarmentDetector.get()
    except Exception:
        log.exception("model unavailable")
        raise HTTPException(503, "The detection model is not available on the server.")

    detections = detector.detect(img, all_items=False)
    if not detections:
        raise HTTPException(422, "No clothing item detected. Try a photo of a single item on a plain background.")

    det = detections[0].to_dict()
    category = det["category"]
    group = CLASS_TO_GROUP.get(category, "Accessories")
    primary = (det.get("colors") or [{}])[0]
    color_name = primary.get("name")
    color_family = color_family_of(color_name) if color_name else None

    # Same garment class first; only widen to the whole group (e.g. "top" vs "sweater")
    # if nothing of that exact class is in the wardrobe.
    items = store.list_items(user.id)
    candidates = [i for i in items if i.get("category") == category] \
        or [i for i in items if i.get("category_group") == group]

    def score(item: dict) -> int:
        if color_name and item.get("color_name") == color_name:
            return 2
        if color_family and item.get("color_family") == color_family:
            return 1
        return 0

    best = max(candidates, key=score, default=None)
    return {"category": category, "group": group, "color_name": color_name, "match": best}


class AgentRequest(BaseModel):
    message: str
    city: str = ""          # where the user lives: the stylist checks the real weather there
    country: str = ""
    unit: str = ""          # "Celsius" or "Fahrenheit"


@app.post("/api/agent/search")
async def agent_search(body: AgentRequest, user: User = Depends(current_user)) -> dict[str, Any]:
    """Ask the AI stylist a free-form question; it searches the real wardrobe before answering."""
    items = wardrobe_agent.list_items(user.id)
    place = {"city": body.city[:80], "country": body.country[:80], "unit": body.unit[:12]}
    return await run_in_threadpool(agent.chat, items, body.message, place)


# Agent2Agent: Agent Cards and JSON-RPC endpoints of the AI Stylist and the Outfit Builder (see a2a_agents.py).
app.include_router(a2a_agents.stylist_router)
app.include_router(a2a_agents.outfit_router)
app.include_router(a2a_agents.wardrobe_router)


class WardrobeAgentRequest(BaseModel):
    message: str = ""
    confirm: bool | None = None         # True / False answers a change the agent proposed
    context_id: str | None = None       # the conversation: ties a proposal to its confirmation


@app.post("/api/wardrobe/agent")
async def wardrobe_agent_chat(body: WardrobeAgentRequest, user: User = Depends(current_user)) -> dict[str, Any]:
    """Talk to the Wardrobe Agent: find, compare, count or correct pieces. Changes need the user's confirmation."""
    return await run_in_threadpool(wardrobe_agent.converse, user.id, body.message[:1000],
                                   confirm=body.confirm, context_id=body.context_id)


class OutfitAgentRequest(BaseModel):
    occasion: str = "everyday"
    season: str = "autumn"
    city: str = ""
    country: str = ""
    unit: str = ""
    avoid: list[list[str]] = []     # outfits already shown (lists of item ids): the agent builds different ones


@app.post("/api/outfits/agent")
async def outfit_agent(body: OutfitAgentRequest, user: User = Depends(current_user)) -> dict[str, Any]:
    """The Outfit Builder agent (LangGraph): weather + wardrobe + fashion books -> complete, validated outfits."""
    items = wardrobe_agent.list_items(user.id)
    place = {"city": body.city[:80], "country": body.country[:80], "unit": body.unit[:12]}
    try:
        return await run_in_threadpool(outfit_agent_module.build, items, body.occasion[:40], body.season[:20],
                                       place, body.avoid[:10])
    except RuntimeError as error:
        raise HTTPException(503, str(error)) from error


class DuplicateCheckRequest(BaseModel):
    id: str | None = None   # the item just saved: left out of the comparison so it is not its own duplicate
    category: str
    color_name: str | None = None
    pattern: str | None = None
    material: str | None = None


@app.post("/api/agent/check-duplicate")
async def agent_check_duplicate(body: DuplicateCheckRequest, user: User = Depends(current_user)) -> dict[str, Any]:
    """Run right after a live-scan capture: the agent decides whether to search the wardrobe for
    a near-duplicate of the item that was just saved, and flags it if it finds a confident match.
    """
    items = [i for i in wardrobe_agent.list_items(user.id) if i["id"] != body.id]
    return await run_in_threadpool(agent.check_duplicate, items, body.model_dump())


# ---------------------------------------------------------------------------
# 3D avatar and virtual try-on (fal.ai). Everything is scoped to the signed-in user.
# Generations take 1-2 minutes: they run as background jobs that the browser polls.
def _avatar_errors(fn):
    try:
        return fn()
    except avatar.AvatarError as error:
        raise HTTPException(error.status_code, error.message) from error


def _file(data: bytes | None, media_type: str, what: str) -> Response:
    if data is None:
        raise HTTPException(404, f"No {what} yet")
    return Response(content=data, media_type=media_type, headers={"Cache-Control": "private, max-age=300"})


@app.get("/api/avatar")
def avatar_status(user: User = Depends(current_user)) -> dict:
    return avatar.status(store, user.id)


@app.post("/api/avatar")
async def avatar_create(file: UploadFile = File(...), consent: bool = Form(False),
                        user: User = Depends(current_user)) -> dict:
    """Full-body photo -> 3D avatar (background job). The photo is kept privately for later try-ons."""
    if not consent:
        raise HTTPException(400, "Consent is required: the photo is sent to fal.ai to create the 3D avatar.")
    data = await _read_upload(file)

    def create() -> dict:
        photo = avatar.normalize_photo(data)
        avatar.check_quota(user.id, "avatars", config.AVATAR_CREATIONS_PER_DAY, 24 * 3600)

        def work() -> None:
            avatar.save_avatar(store, user.id, photo, avatar.image_to_3d(photo))

        return {"job_id": avatar.start_job(user.id, "avatar", work, quota=("avatars", 1))}

    return await run_in_threadpool(lambda: _avatar_errors(create))


@app.get("/api/avatar/jobs/{job_id}")
def avatar_job(job_id: str, user: User = Depends(current_user)) -> dict:
    return _avatar_errors(lambda: avatar.get_job(user.id, job_id))


@app.delete("/api/avatar")
def avatar_delete(user: User = Depends(current_user)) -> dict:
    avatar.delete_all(store, user.id)
    return avatar.status(store, user.id)


@app.get("/api/avatar/model")
def avatar_model(user: User = Depends(current_user)) -> Response:
    return _file(avatar.load_model(store, user.id), "model/gltf-binary", "avatar")


@app.get("/api/avatar/photo")
def avatar_photo(user: User = Depends(current_user)) -> Response:
    return _file(avatar.load_photo(store, user.id), "image/jpeg", "photo")


class TryOnRequest(BaseModel):
    item_id: str
    refresh: bool = False   # redo it (costs money) instead of returning the saved result


@app.post("/api/avatar/tryon")
def avatar_tryon(body: TryOnRequest, user: User = Depends(current_user)) -> dict[str, Any]:
    """Put a wardrobe piece on the user, in 3D (background job). A finished result is returned for free."""
    item = _get_or_404(user, body.item_id)
    category = avatar.tryon_category(item)
    if category is None:
        raise HTTPException(422, "Try-on works for tops, jackets, bottoms and dresses (not shoes, bags or accessories).")

    def start() -> dict:
        has_png = avatar.load_tryon(store, user.id, item["id"], "png") is not None
        has_glb = avatar.load_tryon(store, user.id, item["id"], "glb") is not None
        if has_glb and not body.refresh:
            return {"cached": True}
        photo = avatar.load_photo(store, user.id)
        if photo is None:
            raise avatar.AvatarError(409, "Create your 3D avatar first.")
        avatar.check_quota(user.id, "try-ons", config.AVATAR_TRYONS_PER_HOUR, 3600)

        def work() -> None:
            if has_png and not body.refresh:   # the 2D step already worked: only the 3D conversion is left
                dressed = avatar.load_tryon(store, user.id, item["id"], "png")
            else:
                garment = store.download(f"{item_folder(user.id, item['id'])}/cutout.png")
                dressed = avatar.try_on_image(photo, garment, category)
                avatar.save_tryon(store, user.id, item["id"], dressed, "png")
            avatar.save_tryon(store, user.id, item["id"], avatar.image_to_3d(dressed), "glb")

        return {"cached": False, "job_id": avatar.start_job(user.id, "tryon", work, quota=("try-ons", 1))}

    return _avatar_errors(start)


@app.get("/api/avatar/tryon/{item_id}/model")
def avatar_tryon_model(item_id: str, user: User = Depends(current_user)) -> Response:
    return _avatar_errors(lambda: _file(avatar.load_tryon(store, user.id, item_id, "glb"), "model/gltf-binary", "try-on"))


@app.get("/api/avatar/tryon/{item_id}/image")
def avatar_tryon_image(item_id: str, user: User = Depends(current_user)) -> Response:
    return _avatar_errors(lambda: _file(avatar.load_tryon(store, user.id, item_id, "png"), "image/png", "try-on"))


@app.post("/api/avatar/tryon-garment")
async def avatar_tryon_garment(group: str = Form(...), image_url: str | None = Form(None),
                               file: UploadFile | None = File(None),
                               user: User = Depends(current_user)) -> dict[str, Any]:
    """Try on a piece the user does not own yet (a shop photo, or a link to one). 2D only (about $0.075), background job.
    The result is read from GET /api/avatar/tryon/{tryon_id}/image."""
    category = avatar.tryon_category_for_group(group)
    if category is None:
        raise HTTPException(422, "Try-on works for tops, jackets, bottoms and dresses (not shoes, bags or accessories).")
    if file is None and not image_url:
        raise HTTPException(400, "Send a garment photo or an image link.")
    data = await _read_upload(file) if file is not None else None

    def start() -> dict:
        garment = data if data is not None else avatar.fetch_remote_image(image_url or "")
        photo = avatar.load_photo(store, user.id)
        if photo is None:
            raise avatar.AvatarError(409, "Create your 3D avatar first.")
        avatar.check_quota(user.id, "try-ons", config.AVATAR_TRYONS_PER_HOUR, 3600)
        tryon_id = f"shop-{uuid.uuid4().hex[:16]}"

        def work() -> None:
            dressed = avatar.try_on_image(photo, avatar.normalize_photo(garment), category)
            avatar.save_tryon(store, user.id, tryon_id, dressed, "png")

        return {"tryon_id": tryon_id, "job_id": avatar.start_job(user.id, "tryon", work, quota=("try-ons", 1))}

    return await run_in_threadpool(lambda: _avatar_errors(start))


class OutfitTryOnRequest(BaseModel):
    item_ids: list[str]
    refresh: bool = False


# Layering order for a whole outfit: each garment is put on the picture produced by the previous one.
_LAYER_ORDER = {"one-pieces": 0, "bottoms": 1, "tops": 2}


@app.post("/api/avatar/tryon-outfit")
def avatar_tryon_outfit(body: OutfitTryOnRequest, user: User = Depends(current_user)) -> dict[str, Any]:
    """Try on a whole outfit of wardrobe pieces, in 2D (background job, about $0.075 per garment).
    Shoes, bags and accessories are skipped. The result is read from GET /api/avatar/tryon/{tryon_id}/image."""
    if not body.item_ids or len(body.item_ids) > 6:
        raise HTTPException(400, "Send between 1 and 6 pieces.")
    garments = []
    for item_id in dict.fromkeys(body.item_ids):
        item = _get_or_404(user, item_id)
        category = avatar.tryon_category(item)
        if category is not None:
            garments.append((item, category))
    if not garments:
        raise HTTPException(422, "Try-on works for tops, jackets, bottoms and dresses (not shoes, bags or accessories).")
    if sum(1 for _, category in garments if category == "one-pieces") and len(garments) > 1:
        garments = [pair for pair in garments if pair[1] == "one-pieces"][:1] + \
                   [pair for pair in garments if pair[1] != "one-pieces" and pair[0].get("category_group") == "Outerwear"]
    # Outerwear goes on last, over the top.
    garments.sort(key=lambda pair: (pair[0].get("category_group") == "Outerwear", _LAYER_ORDER[pair[1]]))
    tryon_id = "outfit-" + hashlib.sha1("|".join(sorted(item["id"] for item, _ in garments)).encode()).hexdigest()[:16]

    def start() -> dict:
        if avatar.load_tryon(store, user.id, tryon_id, "png") is not None and not body.refresh:
            return {"cached": True, "tryon_id": tryon_id}
        photo = avatar.load_photo(store, user.id)
        if photo is None:
            raise avatar.AvatarError(409, "Create your 3D avatar first.")
        units = avatar.try_on_units(len(garments))
        for _ in range(units):   # every paid request counts once
            avatar.check_quota(user.id, "try-ons", config.AVATAR_TRYONS_PER_HOUR, 3600)

        def work() -> None:
            cutouts = [(store.download(f"{item_folder(user.id, item['id'])}/cutout.png"), category)
                       for item, category in garments]
            avatar.save_tryon(store, user.id, tryon_id, avatar.try_on_outfit(photo, cutouts), "png")

        return {"cached": False, "tryon_id": tryon_id, "job_id": avatar.start_job(user.id, "tryon", work, quota=("try-ons", units)),
                "garments": len(garments)}

    return _avatar_errors(start)


def _get_or_404(user: User, item_id: str) -> dict:
    item = store.get_item(user.id, item_id)
    if not item:
        raise HTTPException(404, "Item not found")
    return item


@app.get("/api/items/{item_id}")
def get_item(item_id: str, user: User = Depends(current_user)) -> dict:
    return _get_or_404(user, item_id)


class ItemPatch(BaseModel):
    fields: dict[str, Any] = {}
    confirm: bool = True  # "Save correction" / "Looks right" both confirm the item


_ENUMS = {"category": MODEL_CLASSES, "color_name": COLOR_NAMES, "color_family": COLOR_FAMILIES,
          "pattern": PATTERNS, "style": STYLES}
_LISTS = {"seasons": SEASONS, "occasions": OCCASIONS}


def _validate_patch(fields: dict) -> dict:
    patch = {}
    for k, v in fields.items():
        if k not in EDITABLE:
            continue
        if k in _ENUMS and v not in _ENUMS[k]:
            raise HTTPException(400, f"Invalid value for {k}: {v!r}")
        if k in _LISTS:
            if not isinstance(v, list) or any(x not in _LISTS[k] for x in v):
                raise HTTPException(400, f"Invalid value for {k}")
            v = list(dict.fromkeys(v))
        if k in ("formality", "warmth"):
            if not isinstance(v, int) or not 1 <= v <= 5:
                raise HTTPException(400, f"{k} must be an integer between 1 and 5")
        if k == "tags":
            if not isinstance(v, list):
                raise HTTPException(400, "tags must be a list")
            v = [str(t).strip().lower()[:40] for t in v if str(t).strip()][:12]
        if k in ("name", "subcategory", "material", "description", "color_hex"):
            v = str(v or "").strip()[:600 if k == "description" else 80]
            if k == "name" and not v:
                raise HTTPException(400, "Name cannot be empty")
        patch[k] = v
    if "category" in patch:
        group = CLASS_TO_GROUP[patch["category"]]
        patch["category_group"] = group
        patch["zone"] = GROUP_TO_ZONE[group]
    if "color_name" in patch and "color_family" not in patch:
        patch["color_family"] = color_family_of(patch["color_name"])
    return patch


def _apply_patch(user_id: str, item: dict, patch: dict, confirm: bool = False) -> dict:
    """The one validated write path for an item: PATCH /api/items/{id} and the Wardrobe Agent (after the user's yes)."""
    item_id = item["id"]
    # log what the model/LLM got wrong - this is how accuracy is measured
    predicted = item.get("predicted") or {}
    corrections = [
        {"item_id": item_id, "field": k, "predicted": predicted[k], "corrected": v,
         "model_confidence": item.get("confidence")}
        for k, v in patch.items()
        if k in TRACKED and k in predicted and _norm(predicted[k]) != _norm(v)
    ]
    store.insert_corrections(corrections)

    if confirm:
        patch["status"] = "confirmed"
        patch["needs_review"] = False
    return store.update_item(user_id, item_id, patch)


@app.patch("/api/items/{item_id}")
def update_item(item_id: str, body: ItemPatch, user: User = Depends(current_user)) -> dict:
    item = _get_or_404(user, item_id)
    return _apply_patch(user.id, item, _validate_patch(body.fields), body.confirm)


def _norm(v):
    return sorted(v) if isinstance(v, list) else v


@app.post("/api/items/{item_id}/reclassify")
def reclassify(item_id: str, user: User = Depends(current_user)) -> dict:
    """Run the LLM again on a stored item (e.g. after adding an API key or changing model)."""
    item = _get_or_404(user, item_id)
    det = item.get("detection")
    if not det:
        raise HTTPException(409, "This item has no stored detection to reclassify")
    try:
        cutout = store.download(f"{item_folder(user.id, item_id)}/cutout.png")
    except Exception:
        cutout = None
    fields = classify_fields(det, enrich(det, cutout))
    for k in ("detection", "colors", "color_hex"):
        fields.pop(k)
    return store.update_item(user.id, item_id, fields)


@app.delete("/api/items/{item_id}")
def delete_item(item_id: str, user: User = Depends(current_user)) -> dict:
    _get_or_404(user, item_id)
    store.delete_item(user.id, item_id)
    return {"deleted": item_id}


# ---------------------------------------------------------------------------
# Shopping Assistant — wraps smart_purchasing.inference.DressMeInferenceEngine
# ---------------------------------------------------------------------------
@app.post("/api/shopping-assistant/evaluate")
async def shopping_assistant_evaluate(
    image_file: UploadFile | None = File(default=None),
    image_url: str = "",
    prompt: str = "Should I buy this?",
    price: float = 0.0,
    budget: float = 0.0,
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """Run the full DressMe purchase-evaluation pipeline on a candidate item."""
    import sys
    import tempfile
    import urllib.request
    from pathlib import Path as _Path

    _sm_dir = _Path(__file__).resolve().parents[2] / "smart_purchasing"
    if str(_sm_dir) not in sys.path:
        sys.path.insert(0, str(_sm_dir))

    try:
        from inference import DressMeInferenceEngine  # type: ignore
    except Exception as exc:
        log.exception("Could not import smart_purchasing inference engine")
        raise HTTPException(503, f"Shopping assistant engine unavailable: {exc}") from exc

    tmp_path: str | None = None
    try:
        if image_file and image_file.filename:
            data = await image_file.read()
            suffix = _Path(image_file.filename).suffix or ".jpg"
        elif image_url.strip():
            suffix = ".jpg"
            req = urllib.request.Request(image_url.strip(), headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = resp.read()
        else:
            raise HTTPException(422, "Provide either image_file or image_url.")
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        tmp.write(data); tmp.close()
        tmp_path = tmp.name

        # What is this item? The same pipeline that classifies the closet answers (detector + GPT vision on the
        # cut-out): far more reliable than the purchase engine's own vision step, and it uses the same vocabulary.
        analysed = await run_in_threadpool(_analyze_sync, data, False, False, False, user)
        recognised = analysed["items"][0]

        def _run():
            from wardrobe_loader import row_to_garment  # type: ignore

            engine = DressMeInferenceEngine(skip_llm=False, user_id=user.id)   # the signed-in user's own closet
            result = engine.evaluate(
                image_path=tmp_path,
                price=float(price or 0),
                budget=float(budget or 0),
                user_prompt=prompt or "Should I buy this?",
                detected=row_to_garment(recognised),
            )
            result["detected_item"] = {key: recognised.get(key) for key in (
                "name", "category", "category_group", "color_name", "material", "pattern", "style",
                "seasons", "occasions", "description")}
            return result

        return await run_in_threadpool(_run)

    except HTTPException:
        raise
    except Exception as exc:
        log.exception("Shopping assistant evaluation failed")
        raise HTTPException(500, f"Evaluation failed: {type(exc).__name__}: {exc}") from exc
    finally:
        if tmp_path:
            try:
                import os as _os
                _os.unlink(tmp_path)
            except Exception:
                pass

@app.get("/api/stats/accuracy")
def accuracy(user: User = Depends(current_user)) -> list[dict]:
    """Real accuracy per field, over the items this user has reviewed."""
    reviewed = {i["id"] for i in store.list_items(user.id) if i.get("status") == "confirmed"}
    corrections = store.list_corrections(user.id)
    out = []
    for field in TRACKED:
        wrong = {c["item_id"] for c in corrections if c["field"] == field and c["item_id"] in reviewed}
        n = len(reviewed)
        out.append({"field": field, "reviewed": n, "corrected": len(wrong),
                    "accuracy": round(1 - len(wrong) / n, 3) if n else None})
    return out


# The Wardrobe Agent writes through the same validated path as PATCH /api/items/{id}.
def _agent_apply(user_id: str, item_id: str, fields: dict) -> dict:
    item = store.get_item(user_id, item_id)
    if not item:
        raise HTTPException(404, "Item not found")
    return _apply_patch(user_id, item, _validate_patch(dict(fields)), confirm=True)


wardrobe_agent.bind(store, _validate_patch, _agent_apply)
