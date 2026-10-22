"""DressMe API.

Pipeline for one photo:
  1. YOLO11m-seg  -> category + mask        (detector.py)
  2. mask pixels  -> colours + cut-out PNG  (detector.py / colors.py)
  3. GPT-4        -> occasion, style, colour, season, pattern, description (enricher.py)
  4. Storage      -> images + row in `items`, scoped to the signed-in user (storage.py)
"""
from __future__ import annotations

import base64
import io
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from . import agent, config
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
            "llm": bool(config.OPENAI_API_KEY), "llm_model": config.LLM_MODEL}


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
                  user: User = Depends(current_user)) -> dict[str, Any]:
    data = await _read_upload(file)
    return await run_in_threadpool(_analyze_sync, data, all_items, save, fast, user)


def _analyze_sync(data: bytes, all_items: bool, save: bool, fast: bool, user: User) -> dict[str, Any]:
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
    return {"items": items}


@app.get("/api/items")
def list_items(user: User = Depends(current_user)) -> list[dict]:
    return store.list_items(user.id)


@app.post("/api/items/quick-detect")
async def quick_detect(file: UploadFile = File(...), user: User = Depends(current_user)) -> dict[str, Any]:
    """Cheap preview detection for the live camera scan: YOLO only, no save, no GPT-4.
    Called repeatedly (every few hundred ms) while the camera is pointed at something,
    so it never raises — an unreadable frame or an empty view just means no detection.
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
                    "box": d["box"], "color_name": primary.get("name")})
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


@app.post("/api/agent/search")
async def agent_search(body: AgentRequest, user: User = Depends(current_user)) -> dict[str, Any]:
    """Ask the AI stylist a free-form question; it searches the real wardrobe before answering."""
    items = store.list_items(user.id)
    return await run_in_threadpool(agent.chat, items, body.message)


class DuplicateCheckRequest(BaseModel):
    category: str
    color_name: str | None = None
    pattern: str | None = None
    material: str | None = None


@app.post("/api/agent/check-duplicate")
async def agent_check_duplicate(body: DuplicateCheckRequest, user: User = Depends(current_user)) -> dict[str, Any]:
    """Run right after a live-scan capture: the agent decides whether to search the wardrobe for
    a near-duplicate of the item that was just saved, and flags it if it finds a confident match.
    """
    items = store.list_items(user.id)
    return await run_in_threadpool(agent.check_duplicate, items, body.model_dump())


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


@app.patch("/api/items/{item_id}")
def update_item(item_id: str, body: ItemPatch, user: User = Depends(current_user)) -> dict:
    item = _get_or_404(user, item_id)
    patch = _validate_patch(body.fields)

    # log what the model/LLM got wrong — this is how accuracy is measured
    predicted = item.get("predicted") or {}
    corrections = [
        {"item_id": item_id, "field": k, "predicted": predicted[k], "corrected": v,
         "model_confidence": item.get("confidence")}
        for k, v in patch.items()
        if k in TRACKED and k in predicted and _norm(predicted[k]) != _norm(v)
    ]
    store.insert_corrections(corrections)

    if body.confirm:
        patch["status"] = "confirmed"
        patch["needs_review"] = False
    return store.update_item(user.id, item_id, patch)


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
