"""HTTP API around the Smart Purchasing engine, used by the React "Should I buy?" page.

Run from the smart_purchasing folder:
    python -m uvicorn api:app --host 127.0.0.1 --port 8050
"""

import os
import tempfile
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

from inference import DressMeInferenceEngine

app = FastAPI(title="DressMe Smart Purchasing API")
engine = DressMeInferenceEngine(skip_llm=False)


@app.get("/api/smart-purchasing/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "wardrobe_items": len(engine.wardrobe),
        "llm": engine.openai_client is not None,
        "llm_model": engine.model_id,
    }


@app.post("/api/smart-purchasing/evaluate")
async def evaluate(
    file: UploadFile = File(...),
    price: float = Form(..., gt=0),
    budget: float = Form(..., gt=0),
    prompt: str = Form("Should I buy this?"),
) -> dict[str, Any]:
    """Photo + price + budget + the user's own question -> decision, evidence and GPT interpretation."""
    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty image.")
    handle, path = tempfile.mkstemp(suffix=".jpg")
    try:
        with os.fdopen(handle, "wb") as image:
            image.write(data)
        return await run_in_threadpool(engine.evaluate, path, price, budget, prompt.strip() or "Should I buy this?")
    except Exception as error:
        raise HTTPException(500, f"{type(error).__name__}: {error}") from error
    finally:
        os.remove(path)
