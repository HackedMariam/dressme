"""Data contracts and Pydantic models for Smart Purchasing."""

from typing import List, Optional, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field


class DecisionType(str, Enum):
    BUY = "BUY"
    CONSIDER = "CONSIDER"
    SKIP = "SKIP"


class SessionStatus(str, Enum):
    IN_PROGRESS = "IN_PROGRESS"
    AWAITING_INPUT = "AWAITING_INPUT"
    COMPLETED = "COMPLETED"


class Garment(BaseModel):
    """An owned garment in the user's wardrobe."""
    id: str
    name: str
    category: str
    color: str
    style: List[str] = Field(default_factory=list)
    seasons: List[str] = Field(default_factory=list)
    occasions: List[str] = Field(default_factory=list)
    image_path: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    embedding: Optional[List[float]] = None
    item_type: Optional[str] = None
    warmth_level: Optional[int] = None
    water_resistance: Optional[int] = None
    weight_g: Optional[int] = None
    versatility: Optional[float] = None
    formality_level: Optional[int] = None
    clean_items_available: Optional[bool] = None
    description: Optional[str] = None


class CandidateItem(BaseModel):
    """Candidate item considered for purchase."""
    id: Optional[str] = "candidate_001"
    name: Optional[str] = "Candidate Item"
    category: str
    color: str = "unknown"
    style: List[str] = Field(default_factory=list)
    seasons: List[str] = Field(default_factory=list)
    occasions: List[str] = Field(default_factory=list)
    price: Optional[float] = None
    budget: Optional[float] = None
    image_path: Optional[str] = None
    target_occasion: Optional[str] = None


class SimilarItemMatch(BaseModel):
    """Similar item found in the user's wardrobe."""
    garment: Garment
    similarity_score: float = Field(..., ge=0.0, le=1.0)
    functional_overlap: bool = False
    redundancy_warning: Optional[str] = None
    color_similarity: Optional[float] = None
    color_delta_e: Optional[float] = None


class OutfitRecommendation(BaseModel):
    """Generated outfit pairing."""
    outfit_id: str
    candidate_item_category: str
    paired_garments: List[Garment]
    compatibility_score: float = Field(..., ge=0.0, le=100.0)
    occasion: str
    description: str


class GapAnalysisResult(BaseModel):
    """Result of wardrobe gap coverage check."""
    category: str
    underrepresented_occasions: List[str] = Field(default_factory=list)
    underrepresented_seasons: List[str] = Field(default_factory=list)
    gap_fill_score: float = Field(..., ge=0.0, le=100.0)
    reasoning: str


class PurchaseScoreBreakdown(BaseModel):
    """Mathematical contributions for each signal."""
    outfit_compatibility: float
    outfit_contribution: float
    gap_contribution_score: float
    gap_contribution: float
    versatility_score: float
    versatility_contribution: float
    style_match_score: float
    style_contribution: float
    redundancy_raw_score: float
    low_redundancy_contribution: float
    budget_penalty: float = 0.0
    color_similarity_score: Optional[float] = None


class PurchaseScoreResult(BaseModel):
    """Deterministic score result."""
    overall_score: float = Field(..., ge=0.0, le=100.0)
    decision: DecisionType
    breakdown: PurchaseScoreBreakdown
    summary: str


class AgentRecommendation(BaseModel):
    """Final grounded purchase recommendation from the agent."""
    session_id: str
    status: SessionStatus = SessionStatus.COMPLETED
    decision: Optional[DecisionType] = None
    overall_score: Optional[float] = None
    summary: str
    engine_source: str = "QWEN3-OLLAMA"  # Either 'QWEN3-OLLAMA' or 'FALLBACK'
    qwen_summary: Optional[str] = None
    fallback_summary: Optional[str] = None
    compatible_outfits_count: Optional[int] = None
    clarification_question: Optional[str] = None
    interim_findings: List[str] = Field(default_factory=list)
    evidence: List[str] = Field(default_factory=list)
    similar_items: List[SimilarItemMatch] = Field(default_factory=list)
    outfit_examples: List[OutfitRecommendation] = Field(default_factory=list)
    gap_analysis: Optional[GapAnalysisResult] = None
    score_breakdown: Optional[PurchaseScoreBreakdown] = None
    detected_color: Optional[str] = None
    detected_category: Optional[str] = None
    detected_style: Optional[str] = None
    detected_occasion: Optional[str] = None
    user_query: Optional[str] = None




class EvaluatePurchaseRequest(BaseModel):
    """API request payload supporting new requests and continuing checkpoints."""
    session_id: Optional[str] = None
    candidate: Optional[CandidateItem] = None
    user_query: Optional[str] = "Should I buy this item?"
    user_response: Optional[str] = None
    budget: Optional[float] = None
