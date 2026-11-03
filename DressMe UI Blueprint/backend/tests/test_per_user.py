"""Per-user behaviour of BO3: wardrobe source, profile and ranker model.

Run from "DressMe UI Blueprint/backend":  python -m unittest discover -s tests -v
(pytest also works). No network and no Supabase: the fetch functions are replaced.
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent import learning, profile_source, wardrobe_source
from agent.memory import AgentMemory
from agent.tools import GapAgentTools

REAL_USER = "11111111-1111-1111-1111-111111111111"
OTHER_USER = "22222222-2222-2222-2222-222222222222"
ONE_ITEM = [{"id": "x", "name": "Navy coat", "category": "outerwear", "subcategory": "coat",
             "colors": ["navy"], "materials": [], "seasons": ["winter"], "occasion_tags": [], "style_tags": []}]


class WardrobeSourceTest(unittest.TestCase):
    def setUp(self):
        wardrobe_source._cache.clear()

    def test_real_user_without_pieces_gets_an_empty_wardrobe_not_the_sample(self):
        with mock.patch.object(wardrobe_source, "_fetch_supabase", return_value=[]):
            self.assertEqual(wardrobe_source.load_wardrobe(REAL_USER), [])
            info = wardrobe_source.source_info(REAL_USER)
        self.assertEqual(info["source"], "empty")
        self.assertTrue(info["message"])

    def test_real_user_with_a_supabase_error_gets_an_error_not_the_sample(self):
        with mock.patch.object(wardrobe_source, "_fetch_supabase", side_effect=RuntimeError("down")):
            self.assertEqual(wardrobe_source.load_wardrobe(REAL_USER), [])
            info = wardrobe_source.source_info(REAL_USER)
        self.assertEqual(info["source"], "error")
        self.assertIn("down", info["reason"])

    def test_demo_user_without_supabase_gets_the_sample_with_a_message(self):
        with mock.patch.object(wardrobe_source, "_fetch_supabase", side_effect=RuntimeError("not configured")):
            items = wardrobe_source.load_wardrobe("demo_user")
            info = wardrobe_source.source_info(None)
        self.assertGreater(len(items), 0)
        self.assertEqual(info["source"], "sample")
        self.assertTrue(info["message"])

    def test_real_pieces_have_no_banner_message(self):
        with mock.patch.object(wardrobe_source, "_fetch_supabase", return_value=ONE_ITEM):
            info = wardrobe_source.source_info(REAL_USER)
        self.assertEqual(info["source"], "supabase")
        self.assertIsNone(info["message"])

    def test_source_is_per_user(self):
        def fetch(user_id):
            return ONE_ITEM if user_id == REAL_USER else []

        with mock.patch.object(wardrobe_source, "_fetch_supabase", side_effect=fetch):
            self.assertEqual(wardrobe_source.source_info(REAL_USER)["source"], "supabase")
            self.assertEqual(wardrobe_source.source_info(OTHER_USER)["source"], "empty")
            self.assertEqual(wardrobe_source.source_info(REAL_USER)["source"], "supabase")

    def test_rank_gaps_reports_instead_of_inventing_gaps_for_an_empty_wardrobe(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:   # Windows keeps the SQLite file open
            memory = AgentMemory(Path(folder) / "memory.sqlite3")
            with mock.patch.object(wardrobe_source, "_fetch_supabase", return_value=[]), \
                 mock.patch.object(profile_source, "_rest", return_value=None):
                result = GapAgentTools(memory, REAL_USER).rank_gaps("winter_work")
        self.assertEqual(result["ranked_gaps"], [])
        self.assertEqual(result["wardrobe_source"]["source"], "empty")
        self.assertIn("No pieces", result["note"])


class ProfileTest(unittest.TestCase):
    def test_style_profile_is_mapped_to_the_ranker_vocabulary(self):
        profile = profile_source.build_profile(
            REAL_USER,
            {"display_name": "Arij", "location": {"city": "Tunis"}},
            {"preferred_styles": ["Minimalist", "Classic / Timeless"], "preferred_colors": ["Navy", "Camel"],
             "avoided_colors": ["Red"], "preferred_occasions": ["Work / Office", "Formal Event"]},
        )
        self.assertEqual(profile["profile_source"], "profile")
        self.assertEqual(profile["preferred_styles"], ["minimal", "classic"])
        self.assertEqual(profile["preferred_colors"], ["navy", "camel"])
        self.assertEqual(profile["avoided_colors"], ["red"])
        self.assertEqual(profile["city"], "Tunis")
        frequency = profile["occasion_frequency"]
        self.assertGreater(frequency["work"], frequency["beach"])
        self.assertGreater(frequency["formal"], frequency["sport"])

    def test_empty_preferences_are_flagged_and_stay_neutral(self):
        profile = profile_source.build_profile(REAL_USER, {"display_name": "Arij"}, {"preferred_styles": []})
        self.assertEqual(profile["profile_source"], "default")
        self.assertEqual(profile["occasion_frequency"], {})      # the ranker then uses its neutral 0.5
        self.assertNotIn("Demo", profile["display_name"])

    def test_unreadable_profile_falls_back_to_neutral_not_to_the_sample_persona(self):
        profile_source._cache.clear()
        with mock.patch.object(profile_source, "_rest", side_effect=RuntimeError("down")):
            profile = profile_source.load_profile(REAL_USER)
        self.assertEqual(profile["profile_source"], "default")
        self.assertEqual(profile["preferred_styles"], [])

    def test_demo_user_keeps_the_sample_profile(self):
        self.assertEqual(profile_source.load_profile("demo_user")["profile_source"], "sample")
        self.assertEqual(profile_source.load_profile(None)["profile_source"], "sample")


class ModelPerUserTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        patcher = mock.patch.object(learning, "USER_MODELS_DIR", Path(self.folder.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.folder.cleanup)

    def test_each_user_has_their_own_model_file(self):
        self.assertNotEqual(learning.user_model_path(REAL_USER), learning.user_model_path(OTHER_USER))

    def test_user_ids_cannot_escape_the_models_folder(self):
        path = learning.user_model_path("../../etc/passwd")
        self.assertEqual(path.parent, Path(self.folder.name))

    def test_without_a_retrained_model_the_shared_demo_model_is_used(self):
        self.assertEqual(learning.active_model_path(REAL_USER), learning.DEMO_MODEL_PATH)

    def test_reset_only_removes_the_callers_model(self):
        for user in (REAL_USER, OTHER_USER):
            learning.user_model_path(user).write_text("{}")
            learning._meta_path(user).write_text("{}")
        learning.reset_model(REAL_USER)
        self.assertFalse(learning.user_model_path(REAL_USER).exists())
        self.assertTrue(learning.user_model_path(OTHER_USER).exists())
        self.assertEqual(learning.active_model_path(REAL_USER), learning.DEMO_MODEL_PATH)
        self.assertEqual(learning.active_model_path(OTHER_USER), learning.user_model_path(OTHER_USER))


if __name__ == "__main__":
    unittest.main()
