"""Unified test and demo suite for 5-Step Dynamic Shopper Agent with check_outfit_compatibility."""

import unittest
from pathlib import Path
from schemas import CandidateItem, EvaluatePurchaseRequest, DecisionType, SessionStatus, Garment
from tools import calculate_purchase_value, find_similar_items, check_outfit_compatibility, analyze_wardrobe_gaps, analyze_item
from agent import PurchaseAgent


class TestSmartPurchasing(unittest.TestCase):

    def setUp(self):
        self.agent = PurchaseAgent()

    def test_purchase_score_math(self):
        """Test exact formula S = 0.30*O + 0.20*G + 0.20*V + 0.15*P + 0.15*(100-R) - Penalty."""
        res_buy = calculate_purchase_value(90.0, 85.0, 80.0, 90.0, 20.0)
        self.assertEqual(res_buy.overall_score, 85.5)
        self.assertEqual(res_buy.decision, DecisionType.BUY)

        # Test affordability penalty when price exceeds budget
        res_penalized = calculate_purchase_value(
            outfit_compatibility_score=90.0,
            wardrobe_gap_score=85.0,
            versatility_score=80.0,
            personal_style_score=90.0,
            redundancy_score=20.0,
            price=200.0,
            budget=100.0
        )
        self.assertLess(res_penalized.overall_score, 85.5)
        self.assertGreater(res_penalized.breakdown.budget_penalty, 0)

    def test_check_outfit_compatibility_wording(self):
        """Test check_outfit_compatibility tool return structure and wording."""
        cand = CandidateItem(category="blazer", color="camel")
        eval_res = check_outfit_compatibility(cand, self.agent.wardrobe, target_occasion="work")
        self.assertIn("compatible_count", eval_res)
        self.assertIn("This item is compatible with", eval_res["summary"])
        self.assertGreater(eval_res["compatible_count"], 0)

    def test_shopper_agent_step_4_dynamic_checkpoint(self):
        """Step 4: Agent detects missing budget and pauses with a clarification question."""
        cand = CandidateItem(
            name="Tailored Camel Blazer",
            category="blazer",
            price=149.99  # Price present, budget absent!
        )
        rec = self.agent.evaluate(EvaluatePurchaseRequest(candidate=cand))
        self.assertEqual(rec.status, SessionStatus.AWAITING_INPUT)
        self.assertIsNotNone(rec.clarification_question)
        self.assertIn("budget", rec.clarification_question.lower())

        # Step 5: Resume session by providing user response
        resumed = self.agent.evaluate(EvaluatePurchaseRequest(
            session_id=rec.session_id,
            user_response="My budget is $160"
        ))
        self.assertEqual(resumed.status, SessionStatus.COMPLETED)
        self.assertIsNotNone(resumed.overall_score)
        self.assertIsNotNone(resumed.decision)
        self.assertIn(resumed.engine_source, ["QWEN3-OLLAMA", "FALLBACK"])
        self.assertTrue(any("compatible with" in ev.lower() for ev in resumed.evidence))

    def test_shopper_agent_known_budget_skips_unnecessary_question(self):
        """When budget is already provided, agent skips Step 4 question and completes immediately."""
        cand = CandidateItem(
            name="Tailored Camel Blazer",
            category="blazer",
            price=149.99,
            budget=150.0  # Budget is already known!
        )
        rec = self.agent.evaluate(EvaluatePurchaseRequest(candidate=cand))
        self.assertEqual(rec.status, SessionStatus.COMPLETED)
        self.assertIsNone(rec.clarification_question)
        self.assertIn(rec.decision, [DecisionType.BUY, DecisionType.CONSIDER, DecisionType.SKIP])

    def test_perceptual_color_similarity_integration(self):
        """Tests that CIEDE2000 color similarity distinguishes white vs cream/ivory and prevents false cross-category redundancy."""
        from color_similarity import compare_colors

        # 1. White vs Ivory, White vs Cream, White vs Black
        res_ivory = compare_colors("white", "ivory")
        res_cream = compare_colors("white", "cream")
        res_black = compare_colors("white", "black")

        self.assertGreaterEqual(res_ivory.similarity_score, 0.85)
        self.assertGreaterEqual(res_cream.similarity_score, 0.80)
        self.assertLessEqual(res_black.similarity_score, 0.15)
        self.assertGreater(res_ivory.similarity_score, res_cream.similarity_score)

        # 2. Cross-category non-redundancy: Cream Skirt vs White Shirt
        skirt = CandidateItem(category="skirt", color="cream")
        shirt = Garment(id="W1", name="White Shirt", category="shirt", color="white")
        matches = find_similar_items(skirt, [shirt])
        for m in matches:
            self.assertFalse(m.functional_overlap)
            self.assertIsNone(m.redundancy_warning)

    def test_xgboost_ml_tool_duplicate_skip(self):
        """XGBoost ML tool must predict SKIP with high confidence for redundant/duplicate items."""
        from ml_model import predict_purchase_ml

        # High redundancy case
        pred = predict_purchase_ml(
            outfit_compatibility=85.0,
            wardrobe_gap=20.0,
            redundancy=95.0,
            versatility=80.0,
            style_match=75.0,
            budget_penalty=0.0
        )
        self.assertEqual(pred["ml_decision"], "SKIP")
        self.assertGreater(pred["confidence"], 0.80)
        self.assertIn("redundancy", pred["top_driver"].lower())

    def test_xgboost_ml_tool_wardrobe_gap_buy(self):
        """XGBoost ML tool must predict BUY for high gap, high compatibility items with low redundancy."""
        from ml_model import predict_purchase_ml

        pred = predict_purchase_ml(
            outfit_compatibility=90.0,
            wardrobe_gap=85.0,
            redundancy=10.0,
            versatility=85.0,
            style_match=85.0,
            budget_penalty=0.0
        )
        self.assertEqual(pred["ml_decision"], "BUY")
        self.assertGreater(pred["confidence"], 0.80)

    def test_black_tshirt_duplicate_skip_e2e(self):
        """Candidate black t-shirt must be classified as SKIP when ITEM012 (Black t-shirt) exists in wardrobe."""
        cand = CandidateItem(
            name="Black Crewneck T-Shirt",
            category="t-shirt",
            color="black",
            style=["casual"],
            price=25.0,
            budget=50.0
        )
        rec = self.agent.evaluate(EvaluatePurchaseRequest(candidate=cand), skip_llm=True)
        self.assertEqual(rec.decision, DecisionType.SKIP)
        self.assertLessEqual(rec.overall_score, 40.0)
        self.assertEqual(rec.ml_decision, "SKIP")
        self.assertIsNotNone(rec.ml_confidence)
        self.assertGreater(rec.ml_confidence, 0.80)
        self.assertTrue(any("direct duplicate" in ev.lower() for ev in rec.evidence))


    def test_vision_model_dressme_best_analysis(self):
        """Tests that dressme_best.pt analyzes garment image, extracts category, mask, and color."""
        img_path = Path(__file__).resolve().parent / "data" / "sample_camel_blazer.jpg"
        if not img_path.exists():
            return
        cand = CandidateItem(
            name="Tailored Camel Blazer",
            category="unknown",
            color="auto-detect",
            image_path=str(img_path)
        )
        analyzed = analyze_item(cand)
        self.assertIn(analyzed["category"], ["jacket", "blazer"])
        self.assertIn(analyzed["color"], ["camel", "taupe", "brown", "beige"])
        self.assertTrue(analyzed.get("has_mask", False))
        self.assertGreater(analyzed.get("confidence", 0.0), 0.70)
        self.assertEqual(len(analyzed["embedding"]), 64)


if __name__ == "__main__":
    unittest.main()
