"""DressMe RAG API: grounded /ask, SSE streaming, health, conversations."""

from __future__ import annotations

import json
import logging
import secrets
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from config import configure_logging, get_settings
from conversations import ConversationStore
from rag import rag_service
from rag.llm_client import LLMUnavailable, get_llm_client
from rag.retriever import RetrievalUnavailable, get_index_embedding_versions
from rag.supabase_client import SupabaseUnavailable, execute_with_retries, get_supabase
from rate_limit import SlidingWindowLimiter

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    settings = get_settings()
    errors = settings.validate(strict=False)

    if errors and not settings.skip_startup_validation:
        raise RuntimeError(
            "Invalid RAG configuration: " + "; ".join(errors)
        )
    if errors:
        logger.warning(
            "RAG configuration is incomplete (startup checks skipped): %s",
            "; ".join(errors),
        )
    if not settings.api_key:
        logger.warning(
            "RAG_API_KEY is not set; /ask is unauthenticated. Set it in "
            "production."
        )

    app.state.settings = settings
    app.state.conversations = ConversationStore(settings.conversations_db)
    app.state.rate_limiter = SlidingWindowLimiter(
        settings.rate_limit_per_minute
    )
    logger.info(
        "DressMe RAG API started (env=%s, hybrid=%s, min_similarity=%.2f)",
        settings.environment,
        settings.hybrid_enabled,
        settings.min_similarity,
    )
    yield


app = FastAPI(
    title="DressMe RAG API",
    description=(
        "Grounded fashion and wardrobe answers with hybrid retrieval, "
        "inline citations, streaming, and conversation history."
    ),
    version="2.0.0",
    lifespan=lifespan,
)

_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=[
        "Content-Type",
        "Authorization",
        _settings.api_key_header,
        "X-Request-ID",
    ],
    expose_headers=["X-Request-ID"],
    max_age=600,
)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)
    conversation_id: str | None = Field(default=None, max_length=100)
    min_similarity: float | None = Field(default=None, ge=0.0, le=1.0)


class Source(BaseModel):
    chunk_id: str | None = None
    chunk_ids: list[str] | None = None
    source: str | None = None
    page: int | None = None
    title: str | None = None
    section: str | None = None
    category: str | None = None
    topics: list[str] = Field(default_factory=list)
    document_id: str | None = None
    similarity: float | None = None
    retrieval: str | None = None


class Citation(BaseModel):
    marker: str
    chunk_id: str | None = None
    source: str | None = None
    page: int | None = None
    title: str | None = None
    section: str | None = None
    similarity: float | None = None


class AskResponse(BaseModel):
    answer: str
    sources: list[Source]
    citations: list[Citation] = Field(default_factory=list)
    conversation_id: str
    rewritten_query: str | None = None
    grounded: bool = False
    usage: dict | None = None


class ConversationResponse(BaseModel):
    conversation_id: str
    messages: list[dict]


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        host = forwarded.split(",")[0].strip()
    else:
        host = request.client.host if request.client else "unknown"
    return f"{host}:{request.url.path}"


def enforce_rate_limit(request: Request) -> None:
    limiter: SlidingWindowLimiter = request.app.state.rate_limiter
    allowed, retry_after = limiter.check(_client_key(request))
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please slow down.",
            headers={"Retry-After": str(retry_after)},
        )


def require_api_key(request: Request) -> None:
    settings = request.app.state.settings
    if not settings.api_key:
        return

    provided = request.headers.get(settings.api_key_header)
    if not provided:
        authorization = request.headers.get("Authorization", "")
        if authorization.lower().startswith("bearer "):
            provided = authorization[7:].strip()

    if not provided or not secrets.compare_digest(
        provided, settings.api_key
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key.",
            headers={"WWW-Authenticate": settings.api_key_header},
        )


def _store(request: Request) -> ConversationStore:
    return request.app.state.conversations


@app.get("/")
def root() -> dict:
    return {
        "service": "DressMe RAG API",
        "version": "2.0.0",
        "endpoints": ["/ask", "/ask/stream", "/health", "/conversations"],
    }


def _check_supabase() -> dict:
    try:
        response = execute_with_retries(
            lambda: get_supabase()
            .table("knowledge_chunks")
            .select("chunk_id", count="exact")
            .limit(1),
            attempts=1,
        )
        return {
            "ok": True,
            "chunks": response.count,
            "embedding_versions": sorted(
                get_index_embedding_versions()
            ),
        }
    except Exception as error:
        return {"ok": False, "error": str(error)}


def _check_llm() -> dict:
    settings = get_settings()
    if not settings.llm_configured:
        return {"ok": False, "error": "LLM is not configured"}

    try:
        client = get_llm_client()
        if hasattr(client, "with_options"):
            client = client.with_options(timeout=8.0)
        client.chat.completions.create(
            model=settings.llm_model,
            messages=[{"role": "user", "content": "Reply with OK."}],
            temperature=0.0,
            max_tokens=1,
        )
        return {"ok": True, "model": settings.llm_model}
    except Exception as error:
        return {"ok": False, "error": str(error)}


@app.get("/health")
def health(response: Response) -> dict:
    settings = get_settings()
    supabase = _check_supabase()
    llm = _check_llm()
    healthy = supabase["ok"] and llm["ok"]

    if not healthy:
        response.status_code = 503

    version_mismatch = (
        supabase.get("ok")
        and supabase.get("embedding_versions")
        and settings.embedding_version
        not in supabase["embedding_versions"]
    )

    return {
        "status": "ok" if healthy else "degraded",
        "checks": {"supabase": supabase, "llm": llm},
        "embedding_version": settings.embedding_version,
        "embedding_version_mismatch": bool(version_mismatch),
    }


@app.post(
    "/ask",
    response_model=AskResponse,
    dependencies=[Depends(require_api_key), Depends(enforce_rate_limit)],
)
def ask(payload: AskRequest, request: Request) -> dict:
    question = payload.question.strip()
    if not question:
        raise HTTPException(
            status_code=400, detail="Question must not be empty."
        )

    store = _store(request)
    conversation_id = store.get_or_create(payload.conversation_id)
    history = store.history(conversation_id)
    store.append(conversation_id, "user", question)

    try:
        result = rag_service.answer_question(
            question,
            top_k=payload.top_k,
            history=history,
            min_similarity=payload.min_similarity,
        )
    except RetrievalUnavailable as error:
        logger.error("Retrieval failed: %s", error)
        raise HTTPException(
            status_code=503,
            detail=(
                "The fashion knowledge index is unavailable. "
                "Please try again shortly."
            ),
        ) from error
    except LLMUnavailable as error:
        logger.error("LLM failed: %s", error)
        raise HTTPException(
            status_code=502,
            detail=(
                "The styling model is unavailable. "
                "Please try again shortly."
            ),
        ) from error
    except SupabaseUnavailable as error:
        logger.error("Supabase failed: %s", error)
        raise HTTPException(
            status_code=503,
            detail="The knowledge database is unavailable.",
        ) from error
    except Exception as error:  # pragma: no cover - defensive
        logger.exception("Unexpected /ask failure: %s", error)
        raise HTTPException(
            status_code=500,
            detail="The styling service hit an unexpected error.",
        ) from error

    store.append(
        conversation_id,
        "assistant",
        result["answer"],
        sources=result.get("sources"),
        citations=result.get("citations"),
        rewritten_query=result.get("rewritten_query"),
    )

    result["conversation_id"] = conversation_id
    return result


def _sse(event: dict) -> str:
    data = json.dumps(event, ensure_ascii=False, default=str)
    return f"event: {event.get('type', 'message')}\ndata: {data}\n\n"


@app.post(
    "/ask/stream",
    dependencies=[Depends(require_api_key), Depends(enforce_rate_limit)],
)
def ask_stream(payload: AskRequest, request: Request) -> StreamingResponse:
    question = payload.question.strip()
    if not question:
        raise HTTPException(
            status_code=400, detail="Question must not be empty."
        )

    store = _store(request)
    conversation_id = store.get_or_create(payload.conversation_id)
    history = store.history(conversation_id)

    def event_stream():
        store.append(conversation_id, "user", question)
        answer_parts: list[str] = []
        sources: list[dict] = []
        citations: list[dict] = []
        rewritten = None

        try:
            for event in rag_service.stream_answer(
                question,
                top_k=payload.top_k,
                history=history,
                min_similarity=payload.min_similarity,
            ):
                event["conversation_id"] = conversation_id
                if event["type"] == "sources":
                    sources = event.get("sources") or []
                    rewritten = event.get("rewritten_query")
                elif event["type"] == "token":
                    answer_parts.append(event.get("text") or "")
                elif event["type"] == "done":
                    citations = event.get("citations") or []
                    rewritten = event.get("rewritten_query") or rewritten
                    store.append(
                        conversation_id,
                        "assistant",
                        "".join(answer_parts),
                        sources=sources,
                        citations=citations,
                        rewritten_query=rewritten,
                    )
                yield _sse(event)
        except RetrievalUnavailable as error:
            logger.error("Streaming retrieval failed: %s", error)
            yield _sse(
                {
                    "type": "error",
                    "message": "The fashion knowledge index is unavailable.",
                    "conversation_id": conversation_id,
                }
            )
        except Exception as error:  # pragma: no cover - defensive
            logger.exception("Streaming failed: %s", error)
            yield _sse(
                {
                    "type": "error",
                    "message": "The styling service hit an unexpected error.",
                    "conversation_id": conversation_id,
                }
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.post(
    "/conversations",
    dependencies=[Depends(require_api_key), Depends(enforce_rate_limit)],
)
def create_conversation(request: Request) -> dict:
    return {"conversation_id": _store(request).create()}


@app.get(
    "/conversations/{conversation_id}",
    response_model=ConversationResponse,
    dependencies=[Depends(require_api_key), Depends(enforce_rate_limit)],
)
def get_conversation(conversation_id: str, request: Request) -> dict:
    store = _store(request)
    if not store.exists(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return {
        "conversation_id": conversation_id,
        "messages": store.messages(conversation_id),
    }


@app.delete(
    "/conversations/{conversation_id}",
    status_code=204,
    dependencies=[Depends(require_api_key), Depends(enforce_rate_limit)],
)
def delete_conversation(conversation_id: str, request: Request) -> Response:
    if not _store(request).delete(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return Response(status_code=204)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, error: Exception):
    logger.exception("Unhandled error: %s", error)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error."},
    )
