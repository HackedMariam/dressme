"""
FastAPI Application - Purchase Redundancy Detection
Main API with all endpoints
"""

import json
import logging
import time
import uuid
from collections import Counter
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import (
    API_TITLE, API_VERSION, API_DESCRIPTION, API_HOST, API_PORT, CORS_ORIGINS,
    LLM_API_KEY, LLM_MODEL, LLM_EFFORT, LLM_AGENT_EFFORT, LLM_MAX_TOKENS, LLM_ENABLED,
    LLM_PROVIDER, OPENAI_API_KEY, OPENAI_MODEL,
    CLIP_MODEL, CLIP_ENABLED, CLIP_QUANTIZE, USE_CUDA, SATURATION_LIMIT, MAX_IMAGE_SIZE, ALLOWED_IMAGE_TYPES,
    SEED_DATA_FILE, LOG_FILE, LOG_LEVEL, LOG_FORMAT, LOG_MAX_BYTES, LOG_BACKUP_COUNT, BUILD_FEATURES, BACKUP_FEATURES,
    CATALOG_IMAGE_ROOT, UPLOAD_DIR, CACHE_DIR, DATABASE_PATH,
    REDIS_URL, CACHE_TTL, SECRET_KEY, JWT_EXPIRE_HOURS, AUTH_REQUIRED,
    RATE_LIMIT_ENABLED, RATE_LIMIT_DEFAULT, RATE_LIMIT_HEAVY, RATE_LIMIT_AUTH, MAX_BODY_SIZE,
)
from logger import setup_logging, request_id_var

setup_logging(LOG_LEVEL, LOG_FILE, LOG_FORMAT, LOG_MAX_BYTES, LOG_BACKUP_COUNT)

from agent import AutonomousAgent  # noqa: E402 - logging must be configured before the heavy imports log
from auth import (EMAIL_RE, GUEST_USER_ID, TokenService, bearer_token, hash_password, password_problem,  # noqa: E402
                  resolve_user_id, verify_password)
from cache import Cache, make_key  # noqa: E402
from clip_integration import CLIPEmbedding, ImageProcessor, CameraCapture, load_image  # noqa: E402
from engine import RedundancyEngine  # noqa: E402
from features import FeatureSet  # noqa: E402
from live import LiveHub  # noqa: E402
from models import DatabaseManager  # noqa: E402
from monitoring import BodySizeLimitMiddleware, MetricsMiddleware, RequestMetrics  # noqa: E402
from openai_client import make_llm_client  # noqa: E402
from pagination import PageParams, page_envelope, paginate  # noqa: E402
from prompts import OptimizedPrompts  # noqa: E402
from rate_limiter import RateLimiter, RateLimitMiddleware  # noqa: E402
from validators import (  # noqa: E402
    AgentRequest, AgentRunRequest, AnalysisRequest, CameraCaptureRequest, ClientEventBatch, FeedbackRequest,
    LoginRequest, ProfileUpdate, RegisterRequest, WardrobeItemRequest, WardrobeUpdateRequest,
)
from wardrobe_builder import build_starter_wardrobe, plan_summary  # noqa: E402
from wardrobe_insights import analyze_wardrobe  # noqa: E402

logger = logging.getLogger(__name__)
access_logger = logging.getLogger("api.access")

# ============================================================================
# APPLICATION STATE (initialized in lifespan)
# ============================================================================

state: Dict[str, Any] = {"metrics": RequestMetrics(), "auth_required": AUTH_REQUIRED}
hub = LiveHub()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Application starting up...")

    logger.info("Initializing database...")
    db = DatabaseManager.init_db()
    total = db.seed_products(SEED_DATA_FILE)
    catalog = db.load_products()
    logger.info(f"✅ Loaded {len(catalog)} products from {db.dialect} (seed file: {SEED_DATA_FILE.name}, rows: {total})")

    cache = Cache(REDIS_URL, CACHE_TTL)
    logger.info(f"Cache backend: {cache.backend}")

    logger.info("Initializing CLIP model...")
    clip = CLIPEmbedding(model_name=CLIP_MODEL, use_cuda=USE_CUDA, enabled=CLIP_ENABLED, quantize=CLIP_QUANTIZE)
    image_processor = ImageProcessor(clip)

    FeatureSet.image_processor = image_processor
    FeatureSet.catalog = catalog

    engine = RedundancyEngine(clip, catalog, saturation_limit=SATURATION_LIMIT,
                              image_root=CATALOG_IMAGE_ROOT, cache_dir=CACHE_DIR, cache=cache)
    llm = make_llm_client(LLM_PROVIDER, LLM_API_KEY, LLM_MODEL, OPENAI_API_KEY, OPENAI_MODEL,
                          LLM_EFFORT, LLM_AGENT_EFFORT, LLM_MAX_TOKENS, LLM_ENABLED)
    hub.bind_loop()
    categories = Counter(p.get("category") for p in catalog)
    state.update(
        db=db,
        cache=cache,
        tokens=TokenService(SECRET_KEY, JWT_EXPIRE_HOURS, DATABASE_PATH / ".secret_key"),
        limiter=RateLimiter(cache, {"default": RATE_LIMIT_DEFAULT, "heavy": RATE_LIMIT_HEAVY, "auth": RATE_LIMIT_AUTH},
                            enabled=RATE_LIMIT_ENABLED),
        catalog=catalog,
        catalog_by_id={p["id"]: p for p in catalog},
        catalog_stats={  # the catalog never changes while the app runs
            "products_in_catalog": len(catalog),
            "categories": len(categories),
            "category_breakdown": dict(categories),
            "brands": len({p.get("brand") for p in catalog}),
            "sources": dict(Counter(p.get("data_source") or "illustrations" for p in catalog)),
            "priced_products": sum(1 for p in catalog if p.get("price")),
        },
        clip=clip,
        image_processor=image_processor,
        camera=CameraCapture(clip),
        engine=engine,
        llm=llm,
        agent=AutonomousAgent(engine, image_processor, llm),
        started_at=datetime.now(),
    )

    logger.info(f"   API: {API_TITLE} v{API_VERSION}")
    logger.info(f"   CLIP: {'Available (' + clip.mode + ')' if clip.clip_available else 'Using simulated embeddings'}")
    logger.info(f"   LLM: {llm.provider} {'ready (' + llm.model + ')' if llm.available else 'unavailable - ' + str(llm.error)}")
    logger.info(f"   Products: {len(catalog)} loaded")
    logger.info(f"   Auth: {'required' if AUTH_REQUIRED else 'optional (guest wardrobe for anonymous visitors)'}")
    logger.info(f"   Rate limits / min: default {RATE_LIMIT_DEFAULT}, heavy {RATE_LIMIT_HEAVY}, auth {RATE_LIMIT_AUTH}"
                f"{'' if RATE_LIMIT_ENABLED else ' (disabled)'}")
    yield
    logger.info("👋 Application shutting down...")
    for key in [k for k in state if k not in ("metrics", "auth_required")]:
        state.pop(key)


# ============================================================================
# FASTAPI APP
# ============================================================================

app = FastAPI(
    title=API_TITLE,
    description=API_DESCRIPTION,
    version=API_VERSION,
    lifespan=lifespan,
)


class CachedStaticFiles(StaticFiles):
    """StaticFiles + Cache-Control, so browsers and a CDN in front of the API keep the images"""

    def __init__(self, *args, cache_control: str, **kwargs):
        super().__init__(*args, **kwargs)
        self.cache_control = cache_control

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        if response.status_code in (200, 304):
            response.headers["Cache-Control"] = self.cache_control
        return response


# Catalog images never change for a given id; wardrobe photos are private and may be deleted
app.mount("/images", CachedStaticFiles(directory=CATALOG_IMAGE_ROOT / "images", check_dir=False,
                                       cache_control="public, max-age=604800, immutable"), name="images")
app.mount("/uploads", CachedStaticFiles(directory=UPLOAD_DIR, cache_control="private, max-age=86400"), name="uploads")

# Added inner -> outer: gzip, body size, rate limit, CORS (so 429 responses carry CORS headers), metrics + access log
class SelectiveGZipMiddleware(GZipMiddleware):
    """GZip buffers streamed bodies - the agent's NDJSON events must reach the browser one by one"""

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"].startswith("/agent/run"):
            return await self.app(scope, receive, send)
        await super().__call__(scope, receive, send)


app.add_middleware(SelectiveGZipMiddleware, minimum_size=1024)
app.add_middleware(BodySizeLimitMiddleware, max_bytes=MAX_BODY_SIZE)
app.add_middleware(RateLimitMiddleware, limiter_getter=lambda: state.get("limiter"))
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials="*" not in CORS_ORIGINS,  # credentials are not allowed with a wildcard origin
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-RateLimit-Limit", "X-RateLimit-Remaining", "Retry-After"],
)
app.add_middleware(MetricsMiddleware, metrics_getter=lambda: state.get("metrics"), logger=access_logger,
                   request_id_var=request_id_var)

# ============================================================================
# RESPONSE MODELS
# ============================================================================

class AnalysisResponse(BaseModel):
    analysis_id: str
    new_item: Dict
    similar_items: List[Dict]
    catalog_matches: List[Dict] = []
    redundancy_score: int
    recommendation: str
    warning: Dict = {}
    explanation: str
    explanation_source: str = "rules"
    alternatives: List[Dict]
    scores: Dict = {}
    confidence: float
    embedding_mode: str = "simulated"
    execution_time_ms: float
    timestamp: str

# ============================================================================
# HELPERS
# ============================================================================

def current_user(request: Request) -> str:
    """Authenticated user id, or the guest wardrobe id when no token is sent (and auth is optional)"""
    return resolve_user_id(bearer_token(request), state["tokens"], state["auth_required"])


def _dump(item: BaseModel) -> Dict:
    return item.model_dump(exclude_none=True)


async def _read_image(file: UploadFile) -> bytes:
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=415, detail=f"Unsupported image type {file.content_type}. Allowed: {sorted(ALLOWED_IMAGE_TYPES)}")
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(contents) > MAX_IMAGE_SIZE:
        raise HTTPException(status_code=413, detail=f"Image larger than {MAX_IMAGE_SIZE // (1024 * 1024)} MB")
    return contents


def _image_catalog_matches(analysis: Dict, category: Optional[str]) -> List[Dict]:
    """Photo -> catalog retrieval (CLIP image embedding vs the catalog image embeddings)"""
    import numpy as np

    if "embedding_full" not in analysis:
        return []
    return state["engine"].search_catalog_by_image(
        np.asarray(analysis["embedding_full"], dtype=np.float32),
        category=category if category and category != "unknown" else "", top_k=5,
    )


def _suggested_item(attributes: Dict) -> Dict:
    """Prefill the analyze form from image attributes"""
    category = attributes.get("category")
    noun = {"shirts": "shirt", "pants": "pants", "dresses": "dress", "shoes": "shoes",
            "outerwear": "jacket", "accessories": "accessory"}.get(category, "item")
    return {
        "name": " ".join(w for w in (attributes.get("primary_color"), attributes.get("style"), noun) if w and w != "unknown").title(),
        "category": category if category and category != "unknown" else "shirts",
        "color": attributes.get("primary_color", "unknown"),
        "style": attributes.get("style") if attributes.get("style") not in (None, "unknown") else "casual",
        "material": attributes.get("material_appearance") if attributes.get("material_appearance") not in (None, "unknown") else "cotton",
    }

# ============================================================================
# API ENDPOINTS
# ============================================================================

# --------
# HEALTH & INFO
# --------

@app.get("/")
def root():
    """Root endpoint - service info"""
    return {
        "service": API_TITLE,
        "version": API_VERSION,
        "status": "online",
        "features": 31,
        "product_catalog": len(state["catalog"]),
        "docs": "/docs",
    }


@app.get("/health")
def health_check():
    """Health check endpoint - database, cache, CLIP and LLM status"""
    database_ok = state["db"].ping()
    return {
        "status": "healthy" if database_ok else "degraded",
        "timestamp": datetime.now().isoformat(),
        "clip_available": state["clip"].clip_available,
        "clip_mode": state["clip"].mode,
        "clip_error": state["clip"].load_error,
        "llm": state["llm"].status(),
        "database": state["db"].dialect if database_ok else "unreachable",
        "cache": state["cache"].backend,
        "auth_required": state["auth_required"],
        "products_loaded": len(state["catalog"]),
        "products_in_database": state["db"].count_products(),
    }

# --------
# ACCOUNTS (JWT)
# --------

_DUMMY_HASH = hash_password("timing-equalizer", iterations=1000)


@app.post("/auth/register", status_code=201)
def register(body: RegisterRequest):
    """Create an account - optionally moving the guest wardrobe and history into it"""
    if not EMAIL_RE.match(body.email):
        raise HTTPException(status_code=422, detail="Adresse e-mail invalide.")
    problem = password_problem(body.password)
    if problem:
        raise HTTPException(status_code=422, detail=problem)

    profile = body.model_dump(include={"gender", "clothing_size", "shoe_size", "style_preferences", "favorite_colors"},
                              exclude_none=True)
    user = state["db"].create_user(f"u_{uuid.uuid4().hex[:16]}", body.email, hash_password(body.password),
                                   body.display_name or body.email.split("@")[0], profile)
    if user is None:
        raise HTTPException(status_code=409, detail="Un compte existe déjà avec cette adresse e-mail.")
    imported = state["db"].claim_guest_data(user["id"]) if body.import_guest_data else None
    starter = _add_starter_wardrobe(user["id"], user) if body.starter_wardrobe else None
    logger.info(f"New account {user['id']} ({user.get('gender') or 'no gender'})"
                + (f", imported {imported}" if imported else "") + (f", starter {starter['added']} pieces" if starter else ""))
    return {"user": user, "imported": imported, "starter": starter, **state["tokens"].create(user)}


@app.post("/auth/login")
def login(body: LoginRequest):
    """Email + password -> bearer token"""
    credentials = state["db"].get_user_credentials(body.email)
    # Same work whether the account exists or not (no user enumeration through timing)
    valid = verify_password(body.password, credentials["password_hash"] if credentials else _DUMMY_HASH)
    if not credentials or not valid:
        raise HTTPException(status_code=401, detail="E-mail ou mot de passe incorrect.")
    state["db"].touch_login(credentials["id"])
    user = {k: v for k, v in credentials.items() if k != "password_hash"}
    return {"user": user, **state["tokens"].create(user)}


@app.patch("/auth/me")
def update_profile(body: ProfileUpdate, user_id: str = Depends(current_user)):
    """Edit the profile (gender, sizes, preferred styles and colors, name)"""
    if user_id == GUEST_USER_ID:
        raise HTTPException(status_code=401, detail="Connectez-vous pour enregistrer un profil.")
    user = state["db"].update_user(user_id, body.model_dump(exclude_unset=True))
    if user is None:
        raise HTTPException(status_code=401, detail="Ce compte n'existe plus.")
    return {"user": user}


@app.get("/auth/me")
def me(user_id: str = Depends(current_user)):
    """Current account (authenticated: false for the guest)"""
    if user_id == GUEST_USER_ID:
        return {"authenticated": False, "user": None, "auth_required": state["auth_required"]}
    user = state["db"].get_user(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Ce compte n'existe plus.")
    return {"authenticated": True, "user": user, "auth_required": state["auth_required"]}

# --------
# MAIN ANALYSIS
# --------

@app.post("/analyze", response_model=AnalysisResponse)
def analyze_item(request: AnalysisRequest, user_id: str = Depends(current_user)):
    """
    Complete redundancy analysis (Features 1-13 integrated).
    Compares the new item with the user's wardrobe; catalog matches give market context.
    """
    start = time.perf_counter()
    analysis_id = uuid.uuid4().hex[:12]

    new_item = _dump(request.new_item)
    if request.wardrobe_items is None:
        wardrobe = state["db"].list_wardrobe(user_id, with_embedding=True)
    else:
        wardrobe = [_dump(i) for i in request.wardrobe_items]

    image_embedding = None
    if request.image_base64:
        try:
            photo = load_image(request.image_base64)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Invalid image: {e}")
        image_embedding = state["clip"].get_image_embedding(photo)
        photo.thumbnail((400, 400))
        photo.save(UPLOAD_DIR / f"analysis-{analysis_id}.jpg", "JPEG", quality=82)
        new_item["image_url"] = f"/uploads/analysis-{analysis_id}.jpg"
    elif request.product_id:
        product = state["catalog_by_id"].get(request.product_id)
        if not product:
            raise HTTPException(status_code=404, detail=f"Product {request.product_id} not found")
        image_embedding = state["engine"].image_embedding_for({"product_id": request.product_id})
        new_item.setdefault("image_url", product.get("image_url"))

    lang = "fr" if request.language.lower().startswith("fr") else "en"
    try:
        result = state["engine"].analyze(new_item, wardrobe, image_embedding=image_embedding, lang=lang)
    except Exception as e:
        logger.exception("Analysis error")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {e}")

    # Feature 12 - LLM explanation (optional, falls back to the rule-based text)
    if request.use_llm and state["llm"].available:
        llm_text = state["llm"].explain(new_item["name"], result, language=request.language)
        if llm_text:
            result["explanation"] = llm_text
            result["explanation_source"] = state["llm"].provider  # "openai" or "claude"

    execution_time = (time.perf_counter() - start) * 1000
    result["execution_time_ms"] = execution_time

    try:
        state["db"].save_analysis(analysis_id, new_item, result, user_id=user_id)
    except Exception as e:
        logger.warning(f"Could not persist analysis {analysis_id}: {e}")
    state["db"].log_execution(uuid.uuid4().hex[:12], "analysis", "success", execution_time)
    logger.info(f"Analysis {analysis_id}: {new_item.get('name')!r} -> {result['recommendation']} "
                f"({result['redundancy_score']}) in {execution_time:.0f} ms")
    hub.publish(user_id, "analysis.created", {"analysis_id": analysis_id, "name": new_item.get("name"),
                                              "recommendation": result["recommendation"],
                                              "redundancy_score": result["redundancy_score"]})

    return AnalysisResponse(
        analysis_id=analysis_id,
        new_item=new_item,
        similar_items=result["similar_items"],
        catalog_matches=result["catalog_matches"],
        redundancy_score=result["redundancy_score"],
        recommendation=result["recommendation"],
        warning=result["warning"],
        explanation=result["explanation"],
        explanation_source=result["explanation_source"],
        alternatives=result["alternatives"],
        scores={
            "visual_similarity": result["visual_similarity"],
            "functional_similarity": result["functional_similarity"],
            "category_saturation": result["category_saturation"],
            "outfit_contribution": result["outfit_contribution"],
        },
        confidence=result["confidence"],
        embedding_mode=result["embedding_mode"],
        execution_time_ms=round(execution_time, 1),
        timestamp=datetime.now().isoformat(),
    )


@app.get("/analyses")
def list_analyses(limit: int = Query(10, ge=1, le=50), offset: int = Query(0, ge=0),
                  user_id: str = Depends(current_user)):
    """Most recent analyses (history), paginated"""
    db = state["db"]
    return page_envelope(db.list_analyses(limit, offset, user_id=user_id), db.count_analyses(user_id), limit, offset)


@app.get("/analysis/{analysis_id}")
def get_analysis(analysis_id: str, user_id: str = Depends(current_user)):
    """Fetch a stored analysis (only your own)"""
    analysis = state["db"].get_analysis(analysis_id, user_id=user_id)
    if not analysis:
        raise HTTPException(status_code=404, detail=f"Analysis {analysis_id} not found")
    return analysis

# --------
# WARDROBE (one per account, guest wardrobe for anonymous visitors; photos in data/uploads)
# --------

def _save_photo(image_data: str, item_id: str):
    """Decode, downscale and store a photo; return (url, CLIP analysis)"""
    try:
        image = load_image(image_data)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid image: {e}")
    image.thumbnail((640, 640))
    image.save(UPLOAD_DIR / f"{item_id}.jpg", "JPEG", quality=85)
    analysis = state["image_processor"].process_image(image)
    return f"/uploads/{item_id}.jpg", analysis


def _full_wardrobe(user_id: str) -> List[Dict]:
    """Wardrobe with CLIP embeddings and the catalog subcategory (jeans, sneakers, heels...) of each piece -
    the advisor's dress codes and the dashboard need it"""
    items = state["db"].list_wardrobe(user_id, with_embedding=True)
    for item in items:
        product = state["catalog_by_id"].get(item.get("product_id"))
        if product:
            item.setdefault("subcategory", product.get("subcategory"))
    return items


def _wardrobe_changed(user_id: str, action: str, item: Optional[Dict] = None) -> None:
    hub.publish(user_id, "wardrobe.changed", {"action": action, "item_id": (item or {}).get("id"),
                                              "name": (item or {}).get("name")})


@app.get("/wardrobe")
def get_wardrobe(limit: Optional[int] = Query(None, ge=1, le=500), offset: int = Query(0, ge=0),
                 user_id: str = Depends(current_user)):
    """Your wardrobe - all items, or one page with ?limit=&offset="""
    db = state["db"]
    items = db.list_wardrobe(user_id, limit=limit, offset=offset)
    total = db.count_wardrobe(user_id) if (limit is not None or offset) else len(items)
    return page_envelope(items, total, limit or total, offset, extra={"total_value": db.wardrobe_value(user_id)})


def _add_item(request: WardrobeItemRequest, user_id: str) -> Dict:
    item_id = uuid.uuid4().hex[:12]
    item = request.model_dump(exclude_none=True, exclude={"image_base64"})
    item["id"] = item_id

    if request.product_id:
        product = state["catalog_by_id"].get(request.product_id)
        if not product:
            raise HTTPException(status_code=404, detail=f"Product {request.product_id} not found")
        for key, source in (("name", "name"), ("category", "category"), ("color", "primary_color"),
                            ("style", "style"), ("material", "material"), ("use_case", "use_case"),
                            ("season", "season"), ("brand", "brand"), ("price", "price"), ("image_url", "image_url")):
            item.setdefault(key, product.get(source))
        emb = state["engine"].image_embedding_for({"product_id": request.product_id})
        if emb is not None:
            item["image_embedding"] = emb.tolist()

    if request.image_base64:
        url, analysis = _save_photo(request.image_base64, item_id)
        item["image_url"] = url
        if analysis.get("status") == "success":
            attrs = analysis["attributes"]
            item["image_embedding"] = analysis["embedding_full"]
            suggested = _suggested_item(attrs)
            for key in ("category", "color", "style", "material"):
                item.setdefault(key, suggested[key])
            item.setdefault("name", suggested["name"])

    if not item.get("name") or not item.get("category"):
        raise HTTPException(status_code=400, detail="Provide a name and category, a product_id or a photo")
    item.setdefault("style", "casual")
    item.setdefault("material", "cotton")
    return state["db"].add_wardrobe_item(item, user_id=user_id)


@app.post("/wardrobe")
def add_wardrobe_item(request: WardrobeItemRequest, user_id: str = Depends(current_user)):
    """Add an item - from the catalog (product_id), a photo (attributes auto-detected) or manual fields"""
    item = _add_item(request, user_id)
    _wardrobe_changed(user_id, "added", item)
    return item


@app.patch("/wardrobe/{item_id}")
def update_wardrobe_item(item_id: str, request: WardrobeUpdateRequest, user_id: str = Depends(current_user)):
    """Edit an owned item (fix what the photo detection got wrong)"""
    updated = state["db"].update_wardrobe_item(item_id, request.model_dump(exclude_none=True), user_id=user_id)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Item {item_id} not found")
    _wardrobe_changed(user_id, "updated", updated)
    return updated


def _delete_photo(item_id: str) -> None:
    photo = UPLOAD_DIR / f"{item_id}.jpg"
    if photo.exists():
        photo.unlink()


@app.delete("/wardrobe/{item_id}")
def delete_wardrobe_item(item_id: str, user_id: str = Depends(current_user)):
    deleted = state["db"].delete_wardrobe_item(item_id, user_id=user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Item {item_id} not found")
    _delete_photo(item_id)
    _wardrobe_changed(user_id, "deleted", deleted)
    return {"status": "deleted", "item": deleted}


def _clear(user_id: str) -> int:
    """Delete the user's items and only their photos (other accounts' photos share the folder)"""
    for item in state["db"].list_wardrobe(user_id):
        _delete_photo(item["id"])
    return state["db"].clear_wardrobe(user_id)


@app.delete("/wardrobe")
def clear_wardrobe(user_id: str = Depends(current_user)):
    deleted = _clear(user_id)
    _wardrobe_changed(user_id, "cleared")
    return {"status": "cleared", "deleted": deleted}


def _add_starter_wardrobe(user_id: str, profile: Optional[Dict], gender: Optional[str] = None) -> Dict:
    """40+ real catalog pieces adapted to the profile (gender, styles, colors), sized for the user"""
    profile = profile or {}
    gender = gender or profile.get("gender") or "Unspecified"
    owned = {i.get("product_id") for i in state["db"].list_wardrobe(user_id) if i.get("product_id")}
    products = build_starter_wardrobe(state["catalog"], gender, profile.get("style_preferences") or (),
                                      profile.get("favorite_colors") or (), exclude=owned)
    added = []
    for product in products:
        size = profile.get("shoe_size") if product["category"] == "shoes" else (
            None if product["category"] == "accessories" else profile.get("clothing_size"))
        added.append(_add_item(WardrobeItemRequest(product_id=product["id"], size=size), user_id))
    _wardrobe_changed(user_id, "sample")
    return {"status": "loaded", "gender": gender, "added": len(added),
            "by_category": dict(Counter(i["category"] for i in added)), "items": added}


@app.get("/wardrobe/starter-plan")
def starter_plan(gender: Literal["Women", "Men", "Unspecified"] = "Unspecified"):
    """Pieces per category of the starter wardrobe for a gender (preview in the sign-up form)"""
    summary = plan_summary(gender)
    return {"gender": gender, "total": sum(summary.values()), "by_category": summary}


@app.post("/wardrobe/sample")
def load_sample_wardrobe(replace: bool = Query(False, description="True: empty the wardrobe first"),
                         gender: Optional[Literal["Women", "Men", "Unspecified"]] = Query(
                             None, description="Default: the account's gender, else a mixed wardrobe"),
                         user_id: str = Depends(current_user)):
    """Add a starter wardrobe of 40+ real pieces adapted to the profile - never deletes anything unless replace=true"""
    if replace:
        _clear(user_id)
    profile = state["db"].get_user(user_id) if user_id != GUEST_USER_ID else None
    return _add_starter_wardrobe(user_id, profile, gender)


# --------
# WARDROBE INSIGHTS (dashboard)
# --------

@app.get("/insights")
def wardrobe_insights(budget: Optional[float] = Query(None, ge=0, le=1_000_000), user_id: str = Depends(current_user)):
    """Wardrobe diagnosis: health score, composition vs ideal, duplicate groups, colors, versatility, tips, suggestions.
    Cached until the wardrobe or the profile changes."""
    wardrobe = _full_wardrobe(user_id)
    profile = state["db"].get_user(user_id) if user_id != GUEST_USER_ID else None
    signature = [(i["id"], i.get("category"), i.get("color"), i.get("style"), i.get("season")) for i in wardrobe]
    key = make_key("insights", user_id, signature, profile and {k: profile.get(k) for k in
                   ("gender", "favorite_colors", "style_preferences")}, budget)
    report = state["cache"].get(key)
    if report is None:
        start = time.perf_counter()
        report = analyze_wardrobe(wardrobe, state["engine"], state["catalog"], profile, budget)
        report["computed_ms"] = round((time.perf_counter() - start) * 1000)
        state["cache"].set(key, report, ttl=600)
    return report

# --------
# AUTONOMOUS AGENT (streamed)
# --------

@app.post("/agent/run")
def agent_run(request: AgentRunRequest, user_id: str = Depends(current_user)):
    """Run the autonomous agent - streams NDJSON events (plan, steps, final report)"""
    wardrobe = _full_wardrobe(user_id)
    profile = state["db"].get_user(user_id) if user_id != GUEST_USER_ID else None
    events = state["agent"].run(request.mission, wardrobe, message=request.message, item=request.item,
                                image=request.image_base64, budget=request.budget, mode=request.mode,
                                profile=profile, history=[t.model_dump() for t in request.history])

    def stream():
        start = time.perf_counter()
        for event in events:
            yield json.dumps(event, ensure_ascii=False, default=str) + "\n"
        state["db"].log_execution(uuid.uuid4().hex[:12], f"agent_{request.mission}", "success",
                                  (time.perf_counter() - start) * 1000)

    return StreamingResponse(stream(), media_type="application/x-ndjson")

# --------
# AGENT (LLM tool use)
# --------

@app.post("/agent")
def run_agent(request: AgentRequest):
    """Autonomous LLM agent: orchestrates the redundancy engine and the 31 features"""
    llm = state["llm"]
    if not llm.available:
        raise HTTPException(status_code=503, detail=f"{llm.provider} unavailable: {llm.error}")

    try:
        result = llm.run_agent(request.message, [_dump(i) for i in request.wardrobe_items],
                               state["engine"], max_iterations=request.max_iterations)
    except Exception as e:
        llm.handle_api_error(e)
        raise HTTPException(status_code=503 if not llm.available else 502,
                            detail=f"{llm.provider} error: {llm.error or e}")

    state["db"].log_execution(uuid.uuid4().hex[:12], "agent", "success", result["execution_time_ms"])
    return result


@app.get("/llm/status")
def llm_status():
    """LLM integration status"""
    return state["llm"].status()

# --------
# FEATURE ENDPOINTS
# --------

@app.post("/feature/{feature_id}")
def run_feature(feature_id: int, data: Dict[str, Any]):
    """Run specific feature by ID (1-31) - body = the feature's keyword arguments"""
    feature_func = FeatureSet.get_feature(feature_id)
    if not feature_func:
        raise HTTPException(status_code=404, detail=f"Feature {feature_id} not found (valid: 1-31)")

    start = time.perf_counter()
    try:
        result = feature_func(**data)
    except TypeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid arguments for feature {feature_id}: {e}")
    except Exception as e:
        logger.exception(f"Feature {feature_id} error")
        raise HTTPException(status_code=500, detail=str(e))

    state["db"].log_execution(uuid.uuid4().hex[:12], "feature", "success", (time.perf_counter() - start) * 1000, feature_id=feature_id)
    return {
        "feature_id": feature_id,
        "feature_name": BUILD_FEATURES.get(feature_id) or BACKUP_FEATURES.get(feature_id),
        "result": result,
        "timestamp": datetime.now().isoformat()
    }

# --------
# IMAGE UPLOAD & ANALYSIS (Features 6-7)
# --------

@app.post("/upload-image")
async def upload_image(file: UploadFile = File(...)):
    """Upload and analyze image (in memory - nothing is written to disk)"""
    contents = await _read_image(file)
    analysis = state["image_processor"].process_image(contents)
    if analysis.get("status") != "success":
        raise HTTPException(status_code=422, detail=f"Could not process image: {analysis.get('error')}")

    attributes = analysis.get("attributes", {})
    catalog_matches = _image_catalog_matches(analysis, attributes.get("category"))
    analysis.pop("embedding_full", None)

    return {
        "status": "success",
        "filename": file.filename,
        "analysis": analysis,
        "suggested_item": _suggested_item(attributes),
        "catalog_matches": catalog_matches,
    }


@app.post("/camera-capture")
def camera_capture(request: CameraCaptureRequest):
    """Analyze an image from the camera (base64 or data URL in the JSON body)"""
    result = state["camera"].capture_and_analyze(request.image_base64)
    if result.get("status") != "success":
        raise HTTPException(status_code=422, detail=result.get("error") or "Invalid image")
    attributes = result["analysis"].get("attributes", {})
    result["catalog_matches"] = _image_catalog_matches(result["analysis"], attributes.get("category"))
    result["analysis"].pop("embedding_full", None)
    result["suggested_item"] = _suggested_item(attributes)
    return result

# --------
# FEEDBACK (Feature 10)
# --------

@app.post("/feedback")
def submit_feedback(request: FeedbackRequest, user_id: str = Depends(current_user)):
    """Submit user feedback (persisted)"""
    feedback = FeatureSet.feature_10_user_feedback(
        request.item_id, request.feedback_type, request.rating, request.comment or ""
    )
    feedback["helped_decision"] = request.helped_decision
    feedback_id = uuid.uuid4().hex[:12]
    state["db"].save_feedback(feedback_id, feedback, user_id=user_id)
    return {"status": "success", "feedback_id": feedback_id, "feedback": feedback}

# --------
# CATALOG (filters, semantic search, facets, sorting, pagination)
# --------

SORTS = {
    "price_asc": (lambda p: (p.get("price") is None, p.get("price") or 0), False),
    "price_desc": (lambda p: (p.get("price") is None, -(p.get("price") or 0)), False),
    "name": (lambda p: (p.get("name") or "").lower(), False),
}


def _semantic_search(q: str, category: Optional[str]) -> List[Dict]:
    """CLIP text search - up to 100 relevant products, cached (Redis or memory) per query"""
    key = make_key("search", q.lower(), category or "")
    hits = state["cache"].get(key)
    if hits is None:
        results = state["engine"].search_catalog({"name": q, "category": category or ""}, top_k=100,
                                                 same_category=bool(category))
        hits = [[r["id"], r["similarity"]] for r in results]
        state["cache"].set(key, hits)
    by_id = state["catalog_by_id"]
    return [dict(by_id[pid], similarity=sim) for pid, sim in hits if pid in by_id]


def _facets(products: List[Dict]) -> Dict:
    def count(values):
        return dict(Counter(v for v in values if v).most_common())

    return {
        "category": count(p.get("category") for p in products),
        "source": count((p.get("data_source") or "seed").split(" (")[0] for p in products),
        "color": count(p.get("primary_color") for p in products),
        "gender": count(p.get("gender") for p in products),
        "priced": sum(1 for p in products if p.get("price")),
    }


@app.get("/products")
def list_products(page: PageParams = Depends(),
                  category: Optional[str] = Query(None, max_length=30),
                  brand: Optional[str] = Query(None, max_length=100),
                  q: Optional[str] = Query(None, max_length=200, description="Semantic search (CLIP), e.g. navy wool coat"),
                  source: Optional[str] = Query(None, max_length=60),
                  color: Optional[str] = Query(None, max_length=30),
                  gender: Optional[str] = Query(None, max_length=20),
                  min_price: Optional[float] = Query(None, ge=0),
                  max_price: Optional[float] = Query(None, ge=0),
                  priced: bool = False,
                  sort: Literal["relevance", "price_asc", "price_desc", "name"] = "relevance",
                  facets: bool = Query(False, description="Add counts per category, source, color, gender")):
    """Browse the product catalog - filters, CLIP semantic search (q), sorting, facets and pagination"""
    products = _semantic_search(q.strip(), category) if q and q.strip() else state["catalog"]

    def matches(p: Dict) -> bool:
        if category and (p.get("category") or "").lower() != category.lower():
            return False
        if brand and (p.get("brand") or "").lower() != brand.lower():
            return False
        if source and source.lower() not in (p.get("data_source") or "seed").lower():
            return False
        if color and (p.get("primary_color") or "").lower() != color.lower():
            return False
        if gender and (p.get("gender") or "").lower() not in (gender.lower(), "unisex"):
            return False
        price = p.get("price")
        if (priced or min_price is not None or max_price is not None) and not price:
            return False
        if min_price is not None and price < min_price:
            return False
        if max_price is not None and price > max_price:
            return False
        return True

    products = [p for p in products if matches(p)]
    if sort in SORTS:
        key, reverse = SORTS[sort]
        products = sorted(products, key=key, reverse=reverse)
    return paginate(products, page.limit, page.offset, key="products",
                    extra={"facets": _facets(products)} if facets else None)


@app.get("/stats")
def get_stats(user_id: str = Depends(current_user)):
    """System statistics - catalog (global) and your wardrobe, analyses and savings"""
    db = state["db"]
    return {
        **state["catalog_stats"],
        "clip_available": state["clip"].clip_available,
        "llm_available": state["llm"].available,
        "analyses_run": db.count_analyses(user_id),
        **db.savings_summary(user_id),
        "wardrobe_items": db.count_wardrobe(user_id),
        "wardrobe_value": db.wardrobe_value(user_id),
        **db.feedback_summary(),
        "timestamp": datetime.now().isoformat()
    }

# --------
# ANALYTICS & MONITORING
# --------

@app.post("/analytics/events", status_code=202)
def track_events(batch: ClientEventBatch, user_id: str = Depends(current_user)):
    """Product analytics from the frontend (page views, actions) - batched, no personal data"""
    accepted = state["db"].save_client_events([e.model_dump(exclude_none=True) for e in batch.events],
                                              user_id, batch.session_id)
    return {"accepted": accepted}


@app.get("/analytics/summary")
def analytics_summary(days: int = Query(30, ge=1, le=365), user_id: str = Depends(current_user)):
    """Your analytics: analyses per day and verdict, categories, money saved, LLM usage, usage events"""
    db = state["db"]
    summary = db.analytics_summary(user_id, days)
    wardrobe = db.list_wardrobe(user_id)
    summary["wardrobe"] = {
        "items": len(wardrobe),
        "value": db.wardrobe_value(user_id),
        "categories": dict(Counter(i.get("category") for i in wardrobe).most_common()),
        "colors": dict(Counter(i.get("color") for i in wardrobe if i.get("color")).most_common(8)),
    }
    return summary


@app.get("/analytics/system")
def analytics_system():
    """Technical monitoring: traffic, latency per route, error rate, cache, rate limiting, live connections"""
    return {
        **state["metrics"].summary(),
        "cache": state["cache"].stats(),
        "rate_limit": {"enabled": state["limiter"].enabled, "limits_per_minute": state["limiter"].limits,
                       "rejected": state["limiter"].rejected},
        "database": {"dialect": state["db"].dialect, "healthy": state["db"].ping()},
        "live_connections": hub.count,
        "users": state["db"].count_users(),
        "clip_mode": state["clip"].mode,
        "llm": {"provider": state["llm"].provider, "available": state["llm"].available},
    }


@app.get("/metrics", response_class=PlainTextResponse)
def prometheus_metrics():
    """Prometheus scrape endpoint"""
    cache_stats = state["cache"].stats()
    gauges = {
        "products": len(state["catalog"]),
        "users": state["db"].count_users(),
        "live_connections": hub.count,
        "cache_hits_total": cache_stats["hits"],
        "cache_misses_total": cache_stats["misses"],
        "rate_limited_total": state["limiter"].rejected,
        "llm_available": int(state["llm"].available),
        "clip_available": int(state["clip"].clip_available),
    }
    return PlainTextResponse(state["metrics"].prometheus(gauges), media_type="text/plain; version=0.0.4")

# --------
# REAL-TIME (WebSocket)
# --------

@app.websocket("/ws/live")
async def live_updates(websocket: WebSocket, token: Optional[str] = None):
    """Push 'analysis.created' / 'wardrobe.changed' events to every open tab of the user (?token=JWT)"""
    try:
        user_id = resolve_user_id(token, state["tokens"], state["auth_required"])
    except HTTPException:
        await websocket.close(code=1008, reason="invalid token")
        return
    if not await hub.connect(websocket, user_id):
        return
    try:
        await websocket.send_json({"type": "hello", "data": {"authenticated": user_id != GUEST_USER_ID}})
        while True:
            if await websocket.receive_text() == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        hub.disconnect(websocket, user_id)

# --------
# PROMPTS & FEATURES
# --------

@app.get("/prompts")
def get_prompts():
    """Get available prompts"""
    return OptimizedPrompts.get_all_prompts()


@app.get("/features")
def get_features():
    """Get all available features"""
    return {
        "total": 31,
        "build_features": 13,
        "backup_features": 18,
        "features": FeatureSet.get_all_features()
    }

# ============================================================================
# MAIN
# ============================================================================

def _port_in_use(port: int) -> bool:
    """On Windows, binding 0.0.0.0 succeeds even if another app holds 127.0.0.1:<port>,
    and 'localhost' requests then silently reach the other app - check first."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


if __name__ == "__main__":
    import sys
    import uvicorn

    if _port_in_use(API_PORT):
        logger.error(f"❌ Port {API_PORT} is already used by another program. "
                     f"Stop it, or set API_PORT=8001 in .env (and BACKEND_URL=http://127.0.0.1:8001 for the frontend).")
        sys.exit(1)

    logger.info("Starting FastAPI server...")
    uvicorn.run("main:app", host=API_HOST, port=API_PORT, reload=False, log_level="info", access_log=False)
