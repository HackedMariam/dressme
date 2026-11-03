"""Photos of Tunisian shops for missing pieces: query, Tunisia-only filter, cache and failure handling.

Run from "DressMe UI Blueprint/backend":  python -m unittest discover -s tests -v
No internet: the real search (`_search_web`) is replaced by fake results.
"""

import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent import web_images
from agent.coverage import GOALS


def row(site="celio.tn", n=1, width=800, height=1200, **extra):
    return {"title": f"Manteau {n}", "thumbnail": f"https://ts1.mm.bing.net/th?id={site}{n}",
            "image": f"https://{site}/coat{n}.jpg", "url": f"https://{site}/products/coat{n}",
            "source": site, "width": width, "height": height, **extra}


class QueryTest(unittest.TestCase):
    def test_known_pieces_are_searched_in_french_with_the_tunisian_market(self):
        self.assertEqual(web_images.build_query("a warm wool coat"), "manteau en laine tunisie prix TND")
        self.assertEqual(web_images.build_query("black leather loafers"), "mocassins cuir noir tunisie prix TND")

    def test_unknown_piece_falls_back_to_its_english_name(self):
        self.assertEqual(web_images.build_query("a velvet cape"), "velvet cape tunisie prix TND")

    def test_every_piece_of_the_rules_has_a_french_name(self):
        pieces = {r["description"] for goal in GOALS.values() for r in goal["requirements"]}
        self.assertEqual(sorted(p for p in pieces if p.lower() not in web_images.PIECE_FR), [])


class TunisiaOnlyTest(unittest.TestCase):
    def test_only_tunisian_domains_pass(self):
        for url in ("https://celio.tn/p/1", "https://www.zen.com.tn/p/1", "https://shop.kiabi.tn/p/1"):
            self.assertTrue(web_images.is_tunisian(url), url)
        for url in ("https://shop.mango.com/p/1", "https://etsy.com/listing/1", "https://tn.com/p/1",
                    "https://celio.tn.evil.com/p/1", "https://evil.com/celio.tn", "https://example.com/?u=a.tn"):
            self.assertFalse(web_images.is_tunisian(url), url)

    def test_non_tunisian_results_are_dropped_even_if_the_engine_returned_them(self):
        rows = [row("etsy.com", 1), row("celio.tn", 2), row("shop.mango.com", 3), row("celio.tn.evil.com", 4)]
        self.assertEqual([p["source"] for p in web_images.clean_results(rows, limit=5)], ["celio.tn"])

    def test_a_shop_listed_in_the_extra_list_is_accepted(self):
        with mock.patch.object(web_images, "EXTRA_TUNISIAN_SHOPS", frozenset({"hraier.com"})):
            self.assertTrue(web_images.is_tunisian("https://www.hraier.com/p/1"))
        self.assertFalse(web_images.is_tunisian("https://www.hraier.com/p/1"))


class FilterTest(unittest.TestCase):
    def test_one_photo_per_shop_first_then_the_same_shops_fill_the_rest(self):
        rows = [row("celio.tn", 1), row("celio.tn", 2), row("kiabi.tn", 3), row("celio.tn", 4)]
        photos = web_images.clean_results(rows, limit=3)
        self.assertEqual([p["source"] for p in photos], ["celio.tn", "kiabi.tn", "celio.tn"])
        self.assertEqual(len({p["thumbnail"] for p in photos}), 3)

    def test_with_many_shops_each_appears_once(self):
        rows = [row("celio.tn", 1), row("celio.tn", 2), row("kiabi.tn", 3), row("zen.com.tn", 4)]
        self.assertEqual([p["source"] for p in web_images.clean_results(rows, limit=3)],
                         ["celio.tn", "kiabi.tn", "zen.com.tn"])

    def test_a_duplicate_image_is_kept_once(self):
        photos = web_images.clean_results([row("celio.tn", 1), row("celio.tn", 1)], limit=5)
        self.assertEqual(len(photos), 1)

    def test_small_images_and_non_https_thumbnails_are_dropped(self):
        rows = [row("tiny.tn", 1, width=120, height=150),
                {**row("plain.tn", 2), "thumbnail": "http://insecure.example/x.jpg"},
                row("good.tn", 3)]
        self.assertEqual([p["source"] for p in web_images.clean_results(rows, limit=5)], ["good.tn"])

    def test_rows_missing_a_page_or_thumbnail_are_dropped(self):
        rows = [{**row("a.tn", 1), "url": None}, {**row("b.tn", 2), "thumbnail": None}, row("c.tn", 3)]
        self.assertEqual([p["source"] for p in web_images.clean_results(rows, limit=5)], ["c.tn"])

    def test_titles_are_cleaned_and_the_limit_is_respected(self):
        rows = [row(f"shop{i}.tn", i, title="Coat\x00\n  with   odd\tspaces " + "x" * 300) for i in range(6)]
        photos = web_images.clean_results(rows, limit=3)
        self.assertEqual(len(photos), 3)
        self.assertLessEqual(len(photos[0]["title"]), 120)
        self.assertNotRegex(photos[0]["title"], r"[\x00-\x1f]")


class SearchTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        for patcher in (
            mock.patch.object(web_images, "CACHE_FILE", Path(folder.name) / "cache.json"),
            mock.patch.object(web_images, "_cache", None),
            mock.patch.object(web_images, "_recent_searches", []),
            mock.patch.object(web_images, "RETRY_PAUSE_SECONDS", 0),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_the_search_asks_for_the_tunisian_region(self):
        fake = mock.MagicMock()
        fake.return_value.images.return_value = [row("celio.tn", 1)]
        with mock.patch.dict(sys.modules, {"ddgs": mock.MagicMock(DDGS=fake)}):
            web_images.search_images("a warm wool coat")
        kwargs = fake.return_value.images.call_args.kwargs
        self.assertEqual(kwargs["region"], "tn-fr")
        self.assertEqual(fake.return_value.images.call_args.args[0], "manteau en laine tunisie prix TND")

    def test_second_search_for_the_same_piece_comes_from_the_cache(self):
        with mock.patch.object(web_images, "_search_web", return_value=[row("a.tn", 1), row("b.tn", 2)]) as search:
            first = web_images.search_images("a warm wool coat", 2)
            second = web_images.search_images("a warm wool coat", 2)
        self.assertEqual(search.call_count, 1)
        self.assertFalse(first["cached"])
        self.assertTrue(second["cached"])
        self.assertEqual(first["images"], second["images"])

    def test_a_search_with_only_foreign_results_shows_nothing_with_a_clear_message(self):
        with mock.patch.object(web_images, "_search_web", return_value=[row("etsy.com", 1), row("walmart.com", 2)]):
            result = web_images.search_images("a warm wool coat")
        self.assertEqual(result["images"], [])
        self.assertEqual(result["message"], "No photo found on Tunisian shops for this piece.")

    def test_a_blocked_search_returns_a_message_and_never_raises(self):
        with mock.patch.object(web_images, "_search_web", side_effect=RuntimeError("blocked")) as search:
            result = web_images.search_images("a warm wool coat")
        self.assertEqual(result["images"], [])
        self.assertIn("unavailable", result["message"])
        self.assertEqual(search.call_count, 2)               # one try plus a single retry, never more

    def test_a_search_that_fails_once_is_retried_and_succeeds(self):
        with mock.patch.object(web_images, "_search_web", side_effect=[RuntimeError("hiccup"), [row("celio.tn", 1)]]):
            result = web_images.search_images("a warm wool coat")
        self.assertEqual(len(result["images"]), 1)
        self.assertIsNone(result["message"])

    def test_an_expired_cache_is_served_when_the_search_fails(self):
        with mock.patch.object(web_images, "_search_web", return_value=[row("a.tn", 1)]):
            web_images.search_images("a warm wool coat")
        web_images._cache["manteau en laine tunisie prix TND"]["at"] = time.time() - web_images.CACHE_SECONDS - 5
        with mock.patch.object(web_images, "_search_web", side_effect=RuntimeError("blocked")):
            result = web_images.search_images("a warm wool coat")
        self.assertEqual(len(result["images"]), 1)           # old photos beat an empty card
        self.assertTrue(result["cached"])

    def test_no_result_is_not_cached(self):
        with mock.patch.object(web_images, "_search_web", return_value=[]) as search:
            web_images.search_images("a unicorn cape")
            web_images.search_images("a unicorn cape")
        self.assertEqual(search.call_count, 2)               # an empty answer is retried, not remembered

    def test_searches_are_rate_limited(self):
        with mock.patch.object(web_images, "_search_web", return_value=[row("a.tn", 1)]) as search:
            for i in range(web_images.MAX_SEARCHES_PER_MINUTE + 3):
                result = web_images.search_images(f"piece number {i}")
        self.assertEqual(search.call_count, web_images.MAX_SEARCHES_PER_MINUTE)
        self.assertIn("Too many", result["message"])

    def test_limit_is_capped_between_1_and_6(self):
        rows = [row(f"shop{i}.tn", i) for i in range(10)]
        with mock.patch.object(web_images, "_search_web", return_value=rows):
            self.assertEqual(len(web_images.search_images("a coat", 99)["images"]), 6)
            self.assertEqual(len(web_images.search_images("a coat", 0)["images"]), 1)


if __name__ == "__main__":
    unittest.main()
