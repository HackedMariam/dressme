"""Vocabulary: the names BO1 really gives to pieces must reach the rules with a canonical subcategory, and the
labels a user gives to gaps must come back with the ranking (stored per user on the server, not in the browser).

Run from "DressMe UI Blueprint/backend":  python -m unittest discover -s tests -v
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.coverage import compute_coverage
from agent.memory import AgentMemory
from agent.wardrobe_source import to_bo3_item


def converted(category, subcategory, name=None):
    return to_bo3_item({"id": "x", "category": category, "subcategory": subcategory, "name": name or subcategory})


def piece(category, subcategory, seasons=()):
    return {"id": f"{category}-{subcategory}", "name": subcategory, "category": category, "subcategory": subcategory,
            "colors": [], "materials": [], "seasons": list(seasons), "occasion_tags": [], "style_tags": []}


class JacketVocabularyTest(unittest.TestCase):
    def test_real_bo1_jacket_names_get_a_canonical_subcategory(self):
        expected = {"bomber jacket": "bomber_jacket", "biker jacket": "leather_jacket", "military jacket": "field_jacket",
                    "lightweight jacket": "light_jacket", "casual jacket": "casual_jacket", "jacket": "casual_jacket",
                    "padded jacket": "puffer", "quilted jacket": "puffer", "utility jacket": "field_jacket"}
        for subcategory, canonical in expected.items():
            self.assertEqual(converted("jacket", subcategory)["subcategory"], canonical, subcategory)

    def test_the_classic_names_still_win(self):
        expected = {"wool coat": "coat", "leather coat": "coat", "trench coat": "trench", "denim jacket": "denim_jacket",
                    "rain jacket": "rain_jacket", "blazer": "blazer", "track jacket": "track_jacket", "parka": "parka"}
        for subcategory, canonical in expected.items():
            self.assertEqual(converted("jacket", subcategory)["subcategory"], canonical, subcategory)

    def test_a_vague_subcategory_does_not_hide_a_precise_name(self):
        # The fallback only runs when neither the subcategory nor the name matched a precise keyword.
        self.assertEqual(converted("jacket", "jacket", "Black Puffer Jacket")["subcategory"], "puffer")
        self.assertEqual(converted("jacket", "jacket", "Navy Blazer")["subcategory"], "blazer")

    def test_vest_and_other_detected_classes_are_not_lost_in_other(self):
        item = converted("vest", "sleeveless vest")
        self.assertEqual((item["category"], item["subcategory"]), ("outerwear", "vest"))
        self.assertEqual(converted("watch", "analog watch")["subcategory"], "watch")
        self.assertEqual(converted("dress", "maxi dress")["subcategory"], "maxi_dress")
        self.assertEqual(converted("dress", "evening gown dress")["subcategory"], "evening_dress")


class JacketCoverageTest(unittest.TestCase):
    def covered_ids(self, goal, wardrobe):
        return {c["candidate_id"] for c in compute_coverage(wardrobe, goal)["covered"]}

    def test_a_leather_jacket_is_a_smart_layer_for_a_dinner(self):
        self.assertIn("smart_layer", self.covered_ids("dinner_date", [piece("outerwear", "leather_jacket")]))

    def test_a_light_or_bomber_jacket_is_a_warm_up_layer(self):
        for subcategory in ("light_jacket", "bomber_jacket"):
            self.assertIn("warm_up_layer", self.covered_ids("sport_gym", [piece("outerwear", subcategory)]), subcategory)

    def test_these_jackets_do_not_pass_for_a_warm_coat_or_a_rain_jacket(self):
        wardrobe = [piece("outerwear", s, ["winter"]) for s in ("leather_jacket", "bomber_jacket", "light_jacket", "field_jacket", "casual_jacket")]
        covered = self.covered_ids("winter_work", wardrobe)
        self.assertNotIn("warm_coat", covered)
        self.assertNotIn("rain_protection", covered)


class FeedbackComesBackWithTheRankingTest(unittest.TestCase):
    """The API adds `feedback` to every ranked gap from the signed-in user's stored labels."""

    def setUp(self):
        import api   # imported here: it builds the app and the memory when loaded

        self.api = api
        folder = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(folder.cleanup)
        self.memory = AgentMemory(Path(folder.name) / "memory.sqlite3")
        gaps = [{"candidate_id": "warm_coat", "name": "Warm outerwear coat"}, {"candidate_id": "rain_protection", "name": "Rain layer"},
                {"candidate_id": "closed_work_shoes", "name": "Shoes"}]
        patcher = mock.patch.object(api, "GapAgentTools")
        tools = patcher.start()
        self.addCleanup(patcher.stop)
        tools.return_value.rank_gaps.side_effect = lambda goal: {"goal": goal, "ranked_gaps": [dict(g) for g in gaps], "covered": []}
        memory_patch = mock.patch.object(api, "memory", self.memory)
        memory_patch.start()
        self.addCleanup(memory_patch.stop)

    def labels(self, user):
        result = self.api.gaps(goal="winter_work", interpret=False, user_id=user)
        return {g["candidate_id"]: g["feedback"] for g in result["ranked_gaps"]}

    def test_each_user_sees_only_their_own_labels(self):
        self.memory.set_feedback("arij", "winter_work", "warm_coat", {}, 3)
        self.memory.set_feedback("arij", "winter_work", "rain_protection", {}, 0)
        self.memory.set_feedback("sami", "winter_work", "warm_coat", {}, 0)
        self.assertEqual(self.labels("arij"), {"warm_coat": 3, "rain_protection": 0, "closed_work_shoes": None})
        self.assertEqual(self.labels("sami"), {"warm_coat": 0, "rain_protection": None, "closed_work_shoes": None})
        self.assertEqual(self.labels("nobody"), {"warm_coat": None, "rain_protection": None, "closed_work_shoes": None})

    def test_a_label_of_another_context_is_not_shown(self):
        self.memory.set_feedback("arij", "summer_casual", "warm_coat", {}, 3)
        self.assertIsNone(self.labels("arij")["warm_coat"])

    def test_removing_a_label_removes_it_from_the_ranking(self):
        self.memory.set_feedback("arij", "winter_work", "warm_coat", {}, 3)
        self.memory.delete_feedback("arij", "winter_work", "warm_coat")
        self.assertIsNone(self.labels("arij")["warm_coat"])


if __name__ == "__main__":
    unittest.main()
