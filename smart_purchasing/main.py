"""FastAPI web server for Smart Purchasing."""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from schemas import EvaluatePurchaseRequest, AgentRecommendation
from agent import PurchaseAgent

app = FastAPI(
    title="DressMe - Smart Purchasing API",
    description="Tool-orchestrated Purchase Agent evaluating candidate items against user wardrobe.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Singleton Agent instance
purchase_agent = PurchaseAgent()


@app.get("/health")
def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "Smart Purchasing API",
        "wardrobe_size": len(purchase_agent.wardrobe)
    }


@app.get("/api/v1/wardrobe")
def get_wardrobe():
    """Returns currently loaded wardrobe items."""
    return {"wardrobe": purchase_agent.wardrobe, "count": len(purchase_agent.wardrobe)}


@app.post("/api/v1/purchase/evaluate", response_model=AgentRecommendation)
def evaluate_purchase(request: EvaluatePurchaseRequest):
    """Evaluates candidate garment purchase using the 5 specialized tools."""
    try:
        recommendation = purchase_agent.evaluate(request)
        return recommendation
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
