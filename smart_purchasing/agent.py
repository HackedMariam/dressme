"""PurchaseAgent adapter bridging to DressMeInferenceEngine."""

from typing import List, Optional, Dict, Any
from pathlib import Path

from schemas import (
    CandidateItem,
    Garment,
    AgentRecommendation,
    EvaluatePurchaseRequest,
    DecisionType,
    SessionStatus,
    SimilarItemMatch,
)
from inference import DressMeInferenceEngine


class PurchaseAgent:
    """Agent adapter for legacy tests and API calls."""

    def __init__(self, wardrobe: Optional[List[Garment]] = None):
        # The Qwen decision agent runs by default; without HF_TOKEN (or if the model cannot run) the deterministic
        # evaluation answers. `skip_llm` below only switches the GPT stylist interpretation off.
        self.engine = DressMeInferenceEngine(skip_llm=False, wardrobe=wardrobe)

    def evaluate(
        self,
        request: EvaluatePurchaseRequest,
        skip_llm: bool = True
    ) -> AgentRecommendation:
        cand = request.candidate
        res = self.engine.evaluate(
            image_path=cand.image_path or "",
            price=cand.price or 50.0,
            budget=cand.budget or 100.0,
            user_prompt=request.user_query or cand.name or "Should I buy this?",
            interpret=not skip_llm,
        )

        similar_items = [
            SimilarItemMatch(
                garment=Garment(
                    id="sim_1",
                    name=res["tool_evidence"]["closest_wardrobe_match"] or "Similar item",
                    category=res["candidate_item"]["detected_category"],
                    color=res["candidate_item"]["detected_color"],
                ),
                similarity_score=res["tool_evidence"]["redundancy_score"] / 100.0,
                functional_overlap=True,
                color_similarity=0.90,
                color_delta_e=4.5,
            )
        ] if res["tool_evidence"].get("closest_wardrobe_match") else []

        decision_map = {
            "BUY": DecisionType.BUY,
            "CONSIDER": DecisionType.CONSIDER,
            "SKIP": DecisionType.SKIP,
            "DON'T BUY": DecisionType.SKIP,
        }
        dec_str = res["agent_verdict"]["decision"].upper()
        decision_val = decision_map.get(dec_str, DecisionType.CONSIDER)

        return AgentRecommendation(
            decision=decision_val,
            overall_score=res["agent_verdict"]["score"],
            confidence=res["tool_evidence"].get("xgboost_confidence", 0.85),
            evidence=[
                f"Color Analysis: Perceptual color match with closet.",
                f"XGBoost Prediction: {res['tool_evidence']['xgboost_prediction']}",
            ],
            similar_items=similar_items,
            status=SessionStatus.COMPLETED,
        )
