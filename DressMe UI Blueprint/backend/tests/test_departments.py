"""Women's, men's and mixed wardrobes: which department, which needs, and that nothing leaks or changes by accident.

Run from "DressMe UI Blueprint/backend":  python -m unittest discover -s tests -v
No network and no Supabase.
"""

import copy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent import profile_source, web_images, wardrobe_source
from agent.coverage import GOALS, compute_coverage, get_requirement, requirements_for
from agent.departments import MEN_VARIANTS, adapt, all_variants, resolve_department
from agent.memory import AgentMemory
from agent.tools import GapAgentTools

USER = "11111111-1111-1111-1111-111111111111"


def ids(goal, department):
    return [r["id"] for r in requirements_for(goal, department)]


def item(category, subcategory, name=None, seasons=("summer", "winter")):
    return {"id": f"{category}-{subcategory}", "name": name or subcategory, "category": category, "subcategory": subcategory,
            "colors": [], "materials": [], "seasons": list(seasons), "occasion_tags": [], "style_tags": []}


class ResolveDepartmentTest(unittest.TestCase):
    def test_shopping_for_wins_over_gender(self):
        self.assertEqual(resolve_department("men", "female"), ("men", "shopping_for"))
        self.assertEqual(resolve_department("both", "male"), ("both", "shopping_for"))

    def test_gender_is_used_when_shopping_for_is_empty(self):
        self.assertEqual(resolve_department(None, "female"), ("women", "gender"))
        self.assertEqual(resolve_department(None, "male"), ("men", "gender"))
        self.assertEqual(resolve_department(None, "non_binary"), ("both", "gender"))

    def test_nothing_known_keeps_the_original_rules(self):
        self.assertEqual(resolve_department(None, None), (None, None))
        self.assertEqual(resolve_department(None, "prefer_not_to_say"), (None, None))
        self.assertEqual(resolve_department("everyone", "robot"), (None, None))     # unknown values are ignored


class RulesTest(unittest.TestCase):
    def test_unknown_and_women_get_exactly_the_original_rules(self):
        for goal, definition in GOALS.items():
            for department in (None, "women"):
                self.assertEqual(requirements_for(goal, department), definition["requirements"], (goal, department))

    def test_the_base_rules_are_never_modified(self):
        before = copy.deepcopy(GOALS)
        for goal in GOALS:
            for department in (None, "women", "men", "both"):
                requirements_for(goal, department)
        self.assertEqual(GOALS, before)

    def test_men_get_a_suit_and_a_tie_instead_of_a_dress_and_a_clutch(self):
        men = ids("formal_event", "men")
        self.assertIn("formal_suit", men)
        self.assertIn("formal_tie", men)
        self.assertNotIn("formal_outfit", men)
        self.assertNotIn("evening_accessory", men)
        suit = get_requirement("formal_event", "formal_suit", "men")
        self.assertEqual(suit["description"], "a dark formal suit")
        self.assertEqual(get_requirement("formal_event", "formal_shoes", "men")["description"], "black leather oxford shoes")

    def test_men_do_not_get_the_needs_that_have_no_equivalent(self):
        men = ids("dinner_date", "men")
        self.assertNotIn("date_outfit", men)
        self.assertNotIn("evening_bag_date", men)
        self.assertEqual(men, ["dressy_tops", "date_shoes", "smart_layer"])

    def test_men_are_asked_for_swim_shorts_in_place(self):
        for goal in ("summer_casual", "beach_pool"):
            self.assertEqual(get_requirement(goal, "swimwear", "men")["description"], "swim shorts")
            self.assertEqual(get_requirement(goal, "swimwear", "women")["description"], "a swimsuit")

    def test_both_gets_the_original_needs_plus_the_new_men_needs(self):
        both = ids("formal_event", "both")
        for need in ("formal_outfit", "evening_accessory", "formal_suit", "formal_tie"):
            self.assertIn(need, both)
        self.assertEqual(len(both), len(set(both)))
        # In-place changes are not applied to a mixed wardrobe: a swimsuit stays a swimsuit.
        self.assertEqual(get_requirement("beach_pool", "swimwear", "both")["description"], "a swimsuit")
        # Needs without a men's equivalent stay.
        self.assertIn("date_outfit", ids("dinner_date", "both"))

    def test_a_goal_without_variants_is_the_same_for_everyone(self):
        for department in (None, "women", "men", "both"):
            self.assertEqual(ids("winter_work", department), ids("winter_work", None))
            self.assertEqual(ids("hiking_outdoor", department), ids("hiking_outdoor", None))

    def test_every_variant_targets_a_real_need(self):
        for goal, variants in MEN_VARIANTS.items():
            base_ids = {r["id"] for r in GOALS[goal]["requirements"]}
            self.assertLessEqual(set(variants), base_ids, goal)

    def test_a_new_need_has_a_new_id_so_answers_never_mix(self):
        for goal, variants in MEN_VARIANTS.items():
            for base_id, change in variants.items():
                if change and "id" in change:
                    self.assertNotEqual(change["id"], base_id)
                    self.assertNotIn(change["id"], {r["id"] for r in GOALS[goal]["requirements"]})

    def test_a_need_of_another_department_is_still_found_by_id(self):
        # A stored answer about "formal_suit" must not crash for a user who is now a woman.
        self.assertEqual(get_requirement("formal_event", "formal_suit", "women")["id"], "formal_suit")
        with self.assertRaises(KeyError):
            get_requirement("formal_event", "does_not_exist", "men")

    def test_all_variants_lists_every_possible_need(self):
        every = {r["id"] for r in all_variants("formal_event", GOALS["formal_event"]["requirements"])}
        self.assertTrue({"formal_outfit", "formal_suit", "formal_tie", "evening_accessory"} <= every)


class CoverageTest(unittest.TestCase):
    def test_a_man_without_a_suit_is_not_asked_for_an_evening_dress(self):
        wardrobe = [item("top", "shirt")]
        men = compute_coverage(wardrobe, "formal_event", "men")
        self.assertIn("formal_suit", [c["candidate_id"] for c in men["candidates"]])
        self.assertNotIn("formal_outfit", [c["candidate_id"] for c in men["candidates"]])
        women = compute_coverage(wardrobe, "formal_event", "women")
        self.assertIn("formal_outfit", [c["candidate_id"] for c in women["candidates"]])
        self.assertNotIn("formal_suit", [c["candidate_id"] for c in women["candidates"]])

    def test_owning_a_suit_jacket_covers_the_mens_suit_need(self):
        wardrobe = [item("outerwear", "suit_jacket"), item("shoes", "oxfords"), item("accessory", "tie")]
        covered = [c["candidate_id"] for c in compute_coverage(wardrobe, "formal_event", "men")["covered"]]
        self.assertTrue({"formal_suit", "formal_shoes", "formal_tie"} <= set(covered))

    def test_a_dress_does_not_count_for_a_man(self):
        wardrobe = [item("dress", "evening_dress")]
        men = compute_coverage(wardrobe, "formal_event", "men")
        self.assertEqual([c for c in men["covered"] if c["candidate_id"] == "formal_suit"], [])

    def test_no_department_gives_the_same_result_as_before(self):
        wardrobe = [item("top", "shirt"), item("shoes", "loafers")]
        for goal in GOALS:
            self.assertEqual(compute_coverage(wardrobe, goal), compute_coverage(wardrobe, goal, None))


class ProfileTest(unittest.TestCase):
    def test_department_comes_from_shopping_for_then_gender(self):
        row = {"display_name": "Arij", "gender": "female"}
        self.assertEqual(profile_source.build_profile(USER, row, {})["department"], "women")
        self.assertEqual(profile_source.build_profile(USER, row, {"shopping_for": "men"})["department"], "men")
        self.assertIsNone(profile_source.build_profile(USER, {"display_name": "x"}, {})["department"])

    def test_the_raw_gender_never_reaches_the_profile(self):
        profile = profile_source.build_profile(USER, {"display_name": "Arij", "gender": "female"}, {"shopping_for": "women"})
        self.assertNotIn("gender", profile)
        self.assertNotIn("female", str(profile).replace("femme", ""))      # not hidden under another key either
        self.assertEqual(profile["department_source"], "shopping_for")

    def test_the_demo_user_has_no_department(self):
        self.assertIsNone(profile_source.load_profile("demo_user").get("department"))


class RankingTest(unittest.TestCase):
    """The whole path: profile -> department -> needs -> ranked gaps, for the same empty-ish wardrobe."""

    def setUp(self):
        wardrobe_source._cache.clear()
        profile_source._cache.clear()
        folder = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(folder.cleanup)
        self.memory = AgentMemory(Path(folder.name) / "memory.sqlite3")

    def rank(self, gender, shopping_for=None):
        rows = {"profiles": {"display_name": "T", "gender": gender}, "style_profiles": {"shopping_for": shopping_for}}
        with mock.patch.object(wardrobe_source, "_fetch_supabase", return_value=[item("top", "shirt")]), \
             mock.patch.object(profile_source, "_rest", side_effect=lambda table, params: rows[table]), \
             mock.patch("agent.tools.redundancy_scores",
                        side_effect=lambda d, w: [{"redundancy_score": 0.1, "closest_owned_item": "x", "closest_owned_item_id": "x", "method": "test"} for _ in d]):
            wardrobe_source._cache.clear()
            profile_source._cache.clear()
            return GapAgentTools(self.memory, USER).rank_gaps("formal_event")

    def test_a_woman_and_a_man_get_different_gaps_and_suggestions(self):
        woman, man = self.rank("female"), self.rank("male")
        woman_ids = [g["candidate_id"] for g in woman["ranked_gaps"]]
        man_ids = [g["candidate_id"] for g in man["ranked_gaps"]]
        self.assertIn("formal_outfit", woman_ids)
        self.assertIn("formal_suit", man_ids)
        self.assertNotIn("formal_outfit", man_ids)
        self.assertEqual({g["suggested_item"] for g in man["ranked_gaps"] if g["candidate_id"] == "formal_suit"}, {"a dark formal suit"})
        self.assertEqual((woman["department"], man["department"]), ("women", "men"))

    def test_shopping_for_overrides_the_gender(self):
        result = self.rank("female", "men")
        self.assertEqual(result["department"], "men")
        self.assertIn("formal_suit", [g["candidate_id"] for g in result["ranked_gaps"]])

    def test_without_any_department_the_original_gaps_are_returned(self):
        result = self.rank(None)
        self.assertIsNone(result["department"])
        self.assertIn("formal_outfit", [g["candidate_id"] for g in result["ranked_gaps"]])


class PhotoQueryTest(unittest.TestCase):
    def test_the_department_word_is_added_for_women_and_men_only(self):
        self.assertEqual(web_images.build_query("a warm wool coat", "women"), "manteau en laine femme tunisie prix TND")
        self.assertEqual(web_images.build_query("a warm wool coat", "men"), "manteau en laine homme tunisie prix TND")
        self.assertEqual(web_images.build_query("a warm wool coat", "both"), "manteau en laine tunisie prix TND")
        self.assertEqual(web_images.build_query("a warm wool coat", None), "manteau en laine tunisie prix TND")

    def test_every_piece_of_every_department_has_a_french_name(self):
        pieces = set()
        for goal in GOALS:
            for department in (None, "women", "men", "both"):
                pieces |= {r["description"] for r in requirements_for(goal, department)}
        self.assertEqual(sorted(p for p in pieces if p.lower() not in web_images.PIECE_FR), [])

    def _search(self, results_by_query, description="a silk tie", department="men"):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder, \
             mock.patch.object(web_images, "CACHE_FILE", Path(folder) / "cache.json"), \
             mock.patch.object(web_images, "_cache", None), mock.patch.object(web_images, "_recent_searches", []), \
             mock.patch.object(web_images, "_search_web", side_effect=lambda q: results_by_query.get(q, [])) as search:
            return web_images.search_images(description, 3, department), search

    @staticmethod
    def _row(site):
        return {"title": "t", "thumbnail": f"https://ts1.mm.bing.net/th?id={site}", "image": f"https://{site}/a.jpg",
                "url": f"https://{site}/p/1", "source": site, "width": 800, "height": 1000}

    def test_when_nothing_is_found_with_the_department_word_a_search_without_it_is_tried(self):
        result, search = self._search({"cravate en soie tunisie prix TND": [self._row("celio.tn")]})
        self.assertEqual([p["source"] for p in result["images"]], ["celio.tn"])
        self.assertEqual([c.args[0] for c in search.call_args_list],
                         ["cravate en soie homme tunisie prix TND", "cravate en soie tunisie prix TND"])

    def test_the_fallback_is_still_tunisia_only(self):
        result, _ = self._search({"cravate en soie tunisie prix TND": [self._row("etsy.com"), self._row("shop.mango.com")]})
        self.assertEqual(result["images"], [])
        self.assertEqual(result["message"], "No photo found on Tunisian shops for this piece.")

    def test_no_fallback_when_the_department_search_already_has_photos_or_no_department_is_set(self):
        _, search = self._search({"cravate en soie homme tunisie prix TND": [self._row("celio.tn")]})
        self.assertEqual(search.call_count, 1)
        _, search = self._search({}, department=None)
        self.assertEqual(search.call_count, 1)                    # nothing to drop from the query
        _, search = self._search({}, department="both")
        self.assertEqual(search.call_count, 1)

    def test_the_search_uses_the_department_in_its_query(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder, \
             mock.patch.object(web_images, "CACHE_FILE", Path(folder) / "cache.json"), \
             mock.patch.object(web_images, "_cache", None), mock.patch.object(web_images, "_recent_searches", []), \
             mock.patch.object(web_images, "_search_web", return_value=[]) as search:
            web_images.search_images("a dark formal suit", 3, "men")
        # The department word comes first; with no result a second search without it follows (tested above).
        self.assertEqual(search.call_args_list[0].args[0], "costume noir homme tunisie prix TND")


if __name__ == "__main__":
    unittest.main()
