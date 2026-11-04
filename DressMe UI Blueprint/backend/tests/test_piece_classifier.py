"""Filing unknown piece names with the language model: closed list, cache, and no change on any failure.

No test here reaches the network: the model call is replaced by a fake.

Run from "DressMe UI Blueprint/backend":  python -m unittest discover -s tests -v
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent import piece_classifier as pc
from agent import wardrobe_source
from agent.coverage import GOALS
from agent.wardrobe_source import CANONICAL, refine_unrecognised, to_bo3_item


def row(category, subcategory, name=None, ident="x"):
    return {"id": ident, "category": category, "subcategory": subcategory, "name": name or subcategory}


class IsolatedCache(unittest.TestCase):
    """Each test gets an empty cache file and an API key, so nothing depends on the developer's machine."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(folder.cleanup)
        for patcher in (mock.patch.object(pc, "CACHE_FILE", Path(folder.name) / "cache.json"),
                        mock.patch.object(pc, "_cache", None),
                        mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key", "BO3_LLM_SUBCATEGORIES": "1"})):
            patcher.start()
            self.addCleanup(patcher.stop)


class ClosedListTest(IsolatedCache):
    def fake_model(self, content):
        reply = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(content)))])
        client = mock.Mock()
        client.chat.completions.create.return_value = reply
        return mock.patch("openai.OpenAI", return_value=client), client

    def test_a_valid_answer_is_kept_and_an_invented_one_becomes_unknown(self):
        patcher, _ = self.fake_model({"answers": [{"id": 0, "subcategory": "trench"},
                                                  {"id": 1, "subcategory": "spacesuit"},
                                                  {"id": 9, "subcategory": "coat"}]})
        with patcher:
            answers = pc._ask([("outerwear", "mac"), ("outerwear", "cape")], CANONICAL)
        self.assertEqual(answers, {("outerwear", "mac"): "trench", ("outerwear", "cape"): pc.UNKNOWN})

    def test_an_answer_from_another_category_is_rejected(self):
        patcher, _ = self.fake_model({"answers": [{"id": 0, "subcategory": "sandals"}]})   # a shoe for a jacket
        with patcher:
            self.assertEqual(pc._ask([("outerwear", "mac")], CANONICAL), {("outerwear", "mac"): pc.UNKNOWN})

    def test_only_the_category_and_the_text_are_sent(self):
        patcher, client = self.fake_model({"answers": []})
        with patcher:
            pc._ask([("accessory", "fanny pack")], CANONICAL)
        prompt = client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        self.assertIn("fanny pack", prompt)
        self.assertNotIn("test-key", prompt)
        self.assertEqual(client.chat.completions.create.call_args.kwargs["temperature"], 0)


class ClassifyManyTest(IsolatedCache):
    def test_one_request_for_all_the_unknown_names_then_the_cache(self):
        with mock.patch.object(pc, "_ask", return_value={("shoes", "mules"): "slides", ("top", "kaftan top"): pc.UNKNOWN}) as ask:
            first = pc.classify_many([("shoes", "mules"), ("top", "kaftan top"), ("shoes", "mules")], CANONICAL)
            second = pc.classify_many([("shoes", "mules"), ("top", "kaftan top")], CANONICAL)
        self.assertEqual(first, {("shoes", "mules"): "slides"})
        self.assertEqual(second, first)
        self.assertEqual(ask.call_count, 1)                       # duplicates share one question; the 2nd call is cached
        self.assertEqual(sorted(ask.call_args.args[0]), [("shoes", "mules"), ("top", "kaftan top")])

    def test_unknown_is_cached_too_so_it_is_not_asked_again(self):
        with mock.patch.object(pc, "_ask", return_value={("top", "kaftan top"): pc.UNKNOWN}) as ask:
            pc.classify_many([("top", "kaftan top")], CANONICAL)
            pc.classify_many([("top", "kaftan top")], CANONICAL)
        self.assertEqual(ask.call_count, 1)

    def test_a_failed_request_changes_nothing_and_is_tried_again_later(self):
        with mock.patch.object(pc, "_ask", side_effect=ConnectionError("offline")) as ask:
            self.assertEqual(pc.classify_many([("shoes", "mules")], CANONICAL), {})
            pc.classify_many([("shoes", "mules")], CANONICAL)
        self.assertEqual(ask.call_count, 2)                       # nothing was cached by the failure

    def test_a_name_that_only_repeats_the_category_is_not_asked(self):
        with mock.patch.object(pc, "_ask") as ask:
            self.assertEqual(pc.classify_many([("top", "top"), ("accessory", "bag"), ("outerwear", "jacket"), ("top", "")], CANONICAL), {})
        ask.assert_not_called()

    def test_without_a_key_or_when_turned_off_nothing_is_sent(self):
        for env in ({"OPENAI_API_KEY": "", "LLM_API_KEY": ""}, {"BO3_LLM_SUBCATEGORIES": "0"}):
            with mock.patch.dict(os.environ, env), mock.patch.object(pc, "_ask") as ask:
                self.assertEqual(pc.classify_many([("shoes", "mules")], CANONICAL), {})
            ask.assert_not_called()

    def test_a_longer_vocabulary_asks_the_old_unknowns_again(self):
        with mock.patch.object(pc, "_ask", return_value={("top", "kaftan top"): pc.UNKNOWN}) as ask:
            pc.classify_many([("top", "kaftan top")], CANONICAL)
            grown = {**CANONICAL, "top": [*CANONICAL["top"], "kaftan"]}
            pc.classify_many([("top", "kaftan top")], grown)
        self.assertEqual(ask.call_count, 2)


class RefineTest(IsolatedCache):
    def refine(self, rows, answers):
        items = [to_bo3_item(r) for r in rows]
        with mock.patch.object(pc, "_ask", return_value=answers) as ask:
            return refine_unrecognised(rows, items), ask

    def test_the_rules_go_first_and_known_names_are_never_sent(self):
        items, ask = self.refine([row("jacket", "trench coat"), row("shoes", "loafers")], {})
        ask.assert_not_called()
        self.assertEqual([i["subcategory"] for i in items], ["trench", "loafers"])

    def test_an_unknown_name_is_filed_by_the_model_and_marked_as_such(self):
        items, ask = self.refine([row("shoes", "mules"), row("jacket", "bomber jacket")], {("shoes", "mules"): "slides"})
        self.assertEqual(ask.call_args.args[0], [("shoes", "mules")])
        self.assertEqual((items[0]["subcategory"], items[0].get("subcategory_source")), ("slides", "llm"))
        self.assertNotIn("subcategory_source", items[1])           # filed by the rules

    def test_an_unknown_answer_leaves_the_raw_subcategory(self):
        items, _ = self.refine([row("top", "kaftan top")], {("top", "kaftan top"): pc.UNKNOWN})
        self.assertEqual(items[0]["subcategory"], "kaftan_top")

    def test_the_filed_piece_now_counts_for_a_need(self):
        from agent.coverage import compute_coverage

        def covered_ids(wardrobe):
            wardrobe[0]["seasons"] = ["summer"]
            return {c["candidate_id"] for c in compute_coverage(wardrobe, "summer_casual")["covered"]}

        self.assertNotIn("summer_shoes", covered_ids([to_bo3_item(row("shoes", "mules", ident="m"))]))
        filed, _ = self.refine([row("shoes", "mules", ident="m")], {("shoes", "mules"): "slides"})
        self.assertIn("summer_shoes", covered_ids(filed))


class VocabularyConsistencyTest(unittest.TestCase):
    def test_the_closed_list_covers_what_the_rules_ask_for(self):
        """A subcategory a need accepts must be reachable, otherwise a piece could never satisfy it by name."""
        missing = set()
        for goal in GOALS.values():
            for requirement in goal["requirements"]:
                for condition in requirement["match"]:
                    category = condition["category"]
                    for sub in condition.get("subcategories", []):
                        if category in CANONICAL and sub not in CANONICAL[category]:
                            missing.add((category, sub))
        # Known and accepted: "wool_coat" is only a synonym of "coat", and "shawl" has no keyword yet.
        self.assertLessEqual(missing, {("outerwear", "wool_coat"), ("outerwear", "shawl")})


if __name__ == "__main__":
    unittest.main()
