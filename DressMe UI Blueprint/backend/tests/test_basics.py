"""Everyday basics: what the scanner can see (socks, belt, tights, scarf, gloves, umbrella) and what it cannot
(underwear, sleepwear), which must never become a gap.

Run from "DressMe UI Blueprint/backend":  python -m unittest discover -s tests -v
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent import profile_source, wardrobe_source
from agent.coverage import GOALS, NOT_ANALYSED_REASON, compute_coverage, requirements_for
from agent.memory import AgentMemory
from agent.tools import GapAgentTools
from agent.wardrobe_source import to_bo3_item

USER = "11111111-1111-1111-1111-111111111111"


def accessory(subcategory, n=1):
    return [{"id": f"{subcategory}-{i}", "name": subcategory, "category": "accessory", "subcategory": subcategory,
             "colors": [], "materials": [], "seasons": [], "occasion_tags": [], "style_tags": []} for i in range(n)]


class ScannerVocabularyTest(unittest.TestCase):
    """BO1 detects sock, tights, glove, scarf, belt and umbrella: they must reach the rules with the right names."""

    def test_detected_classes_become_the_subcategories_the_rules_use(self):
        expected = {("sock", "ankle socks"): "socks", ("tights", "sheer tights"): "tights", ("glove", "leather gloves"): "gloves",
                    ("scarf", "wool scarf"): "scarf", ("umbrella", "compact umbrella"): "umbrella", ("belt", "leather belt"): "belt"}
        for (category, subcategory), canonical in expected.items():
            row = {"id": "x", "category": category, "subcategory": subcategory, "name": subcategory}
            item = to_bo3_item(row)
            self.assertEqual((item["category"], item["subcategory"]), ("accessory", canonical), (category, subcategory))

    def test_the_new_subcategories_do_not_change_how_other_accessories_are_named(self):
        for category, subcategory, canonical in [("hat", "straw sun hat", "hat"), ("bag", "tote bag", "tote"),
                                                 ("glasses", "round sunglasses", "sunglasses"), ("headband", "sports headband", "headband")]:
            item = to_bo3_item({"id": "x", "category": category, "subcategory": subcategory, "name": subcategory})
            self.assertEqual(item["subcategory"], canonical, subcategory)


class BasicsGoalTest(unittest.TestCase):
    def test_the_goal_exists_and_has_no_season_filter(self):
        self.assertEqual(GOALS["daily_basics"]["label"], "Everyday basics")
        self.assertEqual(GOALS["daily_basics"]["season"], "all-year")

    def test_an_empty_wardrobe_lacks_every_basic_but_underwear_is_never_a_gap(self):
        result = compute_coverage([], "daily_basics")
        ids = {c["candidate_id"] for c in result["candidates"]}
        self.assertEqual(ids, {"everyday_socks", "everyday_belt", "winter_tights", "winter_scarf", "winter_gloves", "rain_umbrella"})
        names = " ".join(c["name"].lower() for c in result["candidates"] + result["covered"])
        self.assertNotIn("underwear", names)
        self.assertNotIn("sleepwear", names)

    def test_underwear_and_sleepwear_are_listed_as_not_analysed_with_a_reason(self):
        result = compute_coverage([], "daily_basics")
        self.assertEqual([n["name"] for n in result["not_analysed"]], ["Underwear", "Sleepwear"])
        self.assertTrue(all(n["reason"] == NOT_ANALYSED_REASON for n in result["not_analysed"]))
        self.assertEqual(compute_coverage([], "winter_work")["not_analysed"], [])      # other goals have none

    def test_owning_the_basics_covers_them(self):
        wardrobe = accessory("socks", 3) + accessory("belt") + accessory("tights") + accessory("scarf") + accessory("gloves") + accessory("umbrella")
        result = compute_coverage(wardrobe, "daily_basics")
        self.assertEqual(result["candidates"], [])
        self.assertEqual(len(result["covered"]), 6)

    def test_two_pairs_of_socks_are_not_enough(self):
        result = compute_coverage(accessory("socks", 2), "daily_basics")
        socks = next(c for c in result["candidates"] if c["candidate_id"] == "everyday_socks")
        self.assertEqual((socks["owned_count"], socks["required_count"]), (2, 3))

    def test_men_are_not_asked_for_tights_but_women_and_unknown_are(self):
        ids = lambda department: [r["id"] for r in requirements_for("daily_basics", department)]
        self.assertNotIn("winter_tights", ids("men"))
        for department in ("women", "both", None):
            self.assertIn("winter_tights", ids(department))
        self.assertEqual(len(ids("men")), 5)


class RankingTest(unittest.TestCase):
    def test_the_ranked_result_carries_not_analysed_and_no_underwear_gap(self):
        folder = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(folder.cleanup)
        memory = AgentMemory(Path(folder.name) / "memory.sqlite3")
        wardrobe_source._cache.clear()
        profile_source._cache.clear()
        with mock.patch.object(wardrobe_source, "_fetch_supabase", return_value=accessory("socks", 1)), \
             mock.patch.object(profile_source, "_rest", return_value=None), \
             mock.patch("agent.tools.redundancy_scores",
                        side_effect=lambda d, w: [{"redundancy_score": 0.1, "closest_owned_item": "x", "closest_owned_item_id": "x", "method": "test"} for _ in d]):
            result = GapAgentTools(memory, USER).rank_gaps("daily_basics")
        self.assertEqual([n["name"] for n in result["not_analysed"]], ["Underwear", "Sleepwear"])
        gap_ids = [g["candidate_id"] for g in result["ranked_gaps"]]
        self.assertIn("everyday_socks", gap_ids)
        self.assertTrue(all("underwear" not in g["name"].lower() for g in result["ranked_gaps"]))


if __name__ == "__main__":
    unittest.main()
