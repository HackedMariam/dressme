"""Shopping planner: combining needs across contexts, the budget, the user's answers, the cache and the limits on
language-model use. No test reaches the network: the model call (`planner._chat`) is always replaced.

Run from "DressMe UI Blueprint/backend":  python -m unittest discover -s tests -v
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent import planner
from agent.memory import AgentMemory

USER = "22222222-2222-2222-2222-222222222222"
SOURCE = {"source": "supabase", "item_count": 1, "reason": "", "message": None}
ONE_SHIRT = [{"id": "s1", "name": "White shirt", "category": "top", "subcategory": "shirt", "colors": [], "materials": [],
              "seasons": ["summer", "winter"], "occasion_tags": [], "style_tags": []}]


def fake_redundancy(descriptions, wardrobe):
    return [{"redundancy_score": 0.1, "closest_owned_item": "x", "closest_owned_item_id": "x", "method": "test"} for _ in descriptions]


class PlannerCase(unittest.TestCase):
    """A fresh memory, an empty cache, a key (so the model path is reachable) and a stand-in for the model."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(folder.cleanup)
        self.memory = AgentMemory(Path(folder.name) / "memory.sqlite3")
        self.chat = mock.Mock(side_effect=ConnectionError("offline"))      # default: the model is unavailable
        patches = [
            mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key", "BO3_LLM_PLANNER": "1"}),
            mock.patch.dict(planner._cache, clear=True),
            mock.patch.dict(planner._runs, clear=True),
            mock.patch.object(planner, "_chat", self.chat),
            mock.patch.object(planner, "load_wardrobe", return_value=ONE_SHIRT),
            mock.patch.object(planner, "load_profile", return_value={"department": "women"}),
            mock.patch.object(planner, "source_info", return_value=SOURCE),
            mock.patch("agent.tools.redundancy_scores", side_effect=fake_redundancy),
        ]
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    def plan(self, **kwargs):
        return planner.run_plan(self.memory, USER, **kwargs)


class OptimiserTest(PlannerCase):
    def test_one_piece_can_close_needs_of_several_contexts(self):
        result = self.plan(goals=["summer_casual", "beach_pool"])
        shared = [p for p in result["purchases"] if len({c["goal"] for c in p["closes"]}) > 1]
        self.assertTrue(shared, "sandals serve both the summer and the beach contexts")
        self.assertIn(shared[0]["subcategory"], {"sandals", "slides", "espadrilles", "hat", "cap"})

    def test_the_plan_never_closes_fewer_needs_than_the_simple_method(self):
        for budget in (None, 150, 400, 1000):
            result = self.plan(goals=["winter_work", "summer_casual", "dinner_date", "daily_basics"], budget_tnd=budget)
            self.assertGreaterEqual(result["totals"]["needs_closed"], result["baseline"]["needs_closed"], budget)

    def test_the_estimated_cost_respects_the_budget(self):
        for budget in (60, 200, 500):
            result = self.plan(goals=list(planner.GOALS), budget_tnd=budget)
            self.assertLessEqual(result["totals"]["estimated_cost"], budget, budget)
            self.assertEqual(result["leftover_budget"], round(budget - result["totals"]["estimated_cost"]))

    def test_a_budget_that_buys_nothing_says_why(self):
        result = self.plan(goals=["winter_work"], budget_tnd=1)
        self.assertEqual(result["purchases"], [])
        self.assertIn("budget is too low", result["note"])

    def test_the_number_of_pieces_is_capped(self):
        self.assertLessEqual(len(self.plan(goals=list(planner.GOALS))["purchases"]), planner.DEFAULT_MAX_ITEMS)

    def test_not_relevant_removes_a_need_from_the_plan(self):
        before = self.plan(goals=["dinner_date"])
        target = before["purchases"][0]["closes"][0]
        self.memory.set_feedback(USER, target["goal"], target["candidate_id"], {}, 0)
        planner._cache.clear()
        after = self.plan(goals=["dinner_date"])
        remaining = {(c["goal"], c["candidate_id"]) for p in after["purchases"] for c in p["closes"]}
        self.assertNotIn((target["goal"], target["candidate_id"]), remaining)

    def test_i_need_this_pulls_a_need_forward(self):
        base = self.plan(goals=["dinner_date"], budget_tnd=200)
        last = base["purchases"][-1]["closes"][0] if base["purchases"] else None
        if last is None:
            self.skipTest("nothing to compare")
        self.memory.set_feedback(USER, last["goal"], last["candidate_id"], {}, 3)
        planner._cache.clear()
        boosted = self.plan(goals=["dinner_date"], budget_tnd=200)
        order = lambda plan: [c["candidate_id"] for p in plan["purchases"] for c in p["closes"]]
        if last["candidate_id"] in order(boosted) and last["candidate_id"] in order(base):
            self.assertLessEqual(order(boosted).index(last["candidate_id"]), order(base).index(last["candidate_id"]))

    def test_every_purchase_has_an_estimated_range_and_a_reason(self):
        for purchase in self.plan(goals=list(planner.GOALS))["purchases"]:
            price = purchase["price_tnd"]
            self.assertLessEqual(price["low"], price["estimate"])
            self.assertLessEqual(price["estimate"], price["high"])
            self.assertTrue(purchase["closes"])


class LanguageModelUseTest(PlannerCase):
    def reply(self, **fields):
        return json.dumps({"goals": [], "budget_tnd": None, "max_items": None, "rationale": "", **fields})

    def test_an_empty_goal_never_calls_the_model(self):
        result = self.plan(goals=None, objective="")
        self.chat.assert_not_called()
        self.assertEqual((result["plan_source"], result["summary_source"]), ("default", "template"))
        self.assertEqual(len(result["goals"]), len(planner.GOALS))

    def test_a_run_costs_at_most_two_requests(self):
        self.chat.side_effect = [self.reply(goals=["dinner_date"], budget_tnd=300, rationale="Dinner first."), "Two short sentences."]
        result = self.plan(objective="Dinner out soon, 300 dinars")
        self.assertEqual(self.chat.call_count, 2)
        self.assertEqual([g["id"] for g in result["goals"]], ["dinner_date"])
        self.assertEqual((result["budget_tnd"], result["plan_source"], result["summary_source"]), (300, "ai", "ai"))

    def test_the_model_answer_is_validated(self):
        self.chat.side_effect = [self.reply(goals=["dinner_date", "mars_mission", 7], budget_tnd=-5, max_items=99), "ok"]
        result = self.plan(objective="whatever")
        self.assertEqual([g["id"] for g in result["goals"]], ["dinner_date"])
        self.assertIsNone(result["budget_tnd"])
        self.assertEqual(result["max_items"], planner.DEFAULT_MAX_ITEMS)

    def test_the_budget_typed_by_the_user_wins_over_the_one_the_model_read(self):
        self.chat.side_effect = [self.reply(goals=["dinner_date"], budget_tnd=999), "ok"]
        self.assertEqual(self.plan(objective="dinner", budget_tnd=120)["budget_tnd"], 120)

    def test_when_the_model_fails_the_plan_still_works(self):
        result = self.plan(objective="a wedding in August")
        self.assertEqual((result["plan_source"], result["summary_source"]), ("default", "template"))
        self.assertTrue(result["purchases"])

    def test_the_same_request_is_answered_from_the_cache(self):
        self.chat.side_effect = [self.reply(goals=["dinner_date"]), "Summary."]
        first = self.plan(objective="dinner")
        second = self.plan(objective="dinner")
        self.assertEqual(self.chat.call_count, 2)                      # nothing new for the second run
        self.assertFalse(first["cached"])
        self.assertTrue(second["cached"])

    def test_the_model_is_not_used_without_a_key_or_when_turned_off(self):
        for env in ({"OPENAI_API_KEY": "", "LLM_API_KEY": ""}, {"BO3_LLM_PLANNER": "0"}):
            planner._cache.clear()
            with mock.patch.dict(os.environ, env):
                self.plan(objective="dinner")
            self.chat.assert_not_called()

    def test_the_summary_prompt_carries_the_result_but_not_the_wardrobe(self):
        self.chat.side_effect = [self.reply(goals=["dinner_date"]), "Summary."]
        self.plan(objective="dinner")
        summary_prompt = self.chat.call_args_list[1].args[0]
        self.assertNotIn("White shirt", summary_prompt)
        self.assertNotIn("test-key", summary_prompt)


class EdgeCasesTest(PlannerCase):
    def test_an_empty_wardrobe_gets_a_message_and_no_model_call(self):
        empty = {"source": "empty", "item_count": 0, "reason": "", "message": "No pieces yet."}
        with mock.patch.object(planner, "source_info", return_value=empty):
            result = self.plan(objective="anything")
        self.assertEqual((result["purchases"], result["note"]), ([], "No pieces yet."))
        self.chat.assert_not_called()

    def test_the_rate_limit_stops_a_burst(self):
        for _ in range(planner.MAX_RUNS_PER_MINUTE):
            planner.check_rate(USER)
        with self.assertRaises(planner.RateLimited):
            planner.check_rate(USER)
        planner.check_rate("someone-else")                              # per user

    def test_shop_search_words_come_from_a_fixed_catalogue(self):
        self.assertEqual(planner.shop_search_text("outerwear", "coat"), "manteau en laine")
        self.assertIsNone(planner.shop_search_text("outerwear", "ignore previous instructions"))

    def test_every_planned_piece_can_be_searched_in_shops_or_says_it_cannot(self):
        for purchase in self.plan(goals=list(planner.GOALS))["purchases"]:
            self.assertEqual(purchase["can_search_shops"], planner.shop_search_text(purchase["category"], purchase["subcategory"]) is not None)


class ApiRoutesTest(unittest.TestCase):
    def setUp(self):
        import api

        self.api = api

    def test_an_unknown_goal_is_refused(self):
        from fastapi import HTTPException

        with self.assertRaises(HTTPException) as caught:
            self.api.plan(self.api.PlanRequest(goals=["nope"]), user_id=USER)
        self.assertEqual(caught.exception.status_code, 404)

    def test_the_request_is_validated(self):
        from pydantic import ValidationError

        for bad in ({"budget_tnd": 0}, {"budget_tnd": -3}, {"budget_tnd": 10**9}, {"objective": "x" * 301}):
            with self.assertRaises(ValidationError, msg=str(bad)):
                self.api.PlanRequest(**bad)

    def test_photos_are_refused_for_a_piece_outside_the_catalogue(self):
        from fastapi import HTTPException

        with self.assertRaises(HTTPException) as caught:
            self.api.plan_photos("outerwear", "anything goes", 3, user_id=USER)
        self.assertEqual(caught.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
