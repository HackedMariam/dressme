"""Web photos for missing pieces: query building, filtering, cache and failure handling.

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


def row(site="shop-a.com", n=1, width=800, height=1200, **extra):
    return {"title": f"Wool coat {n}", "thumbnail": f"https://ts1.mm.bing.net/th?id={site}{n}",
            "image": f"https://{site}/coat{n}.jpg", "url": f"https://{site}/products/coat{n}",
            "source": site, "width": width, "height": height, **extra}


class QueryAndFilterTest(unittest.TestCase):
    def test_query_drops_the_article_and_asks_for_product_photos(self):
        self.assertEqual(web_images.build_query("a warm wool coat"), "warm wool coat product photo")
        self.assertEqual(web_images.build_query("black leather loafers"), "black leather loafers product photo")

    def test_one_photo_per_shop_and_no_duplicate_image(self):
        rows = [row("etsy.com", 1), row("etsy.com", 2), row("walmart.com", 3), row("walmart.com", 3)]
        photos = web_images.clean_results(rows, limit=5)
        self.assertEqual([p["source"] for p in photos], ["etsy.com", "walmart.com"])

    def test_small_images_and_non_https_thumbnails_are_dropped(self):
        rows = [row("tiny.com", 1, width=120, height=150),
                {**row("plain.com", 2), "thumbnail": "http://insecure.example/x.jpg"},
                row("good.com", 3)]
        self.assertEqual([p["source"] for p in web_images.clean_results(rows, limit=5)], ["good.com"])

    def test_rows_missing_a_page_or_thumbnail_are_dropped(self):
        rows = [{**row("a.com", 1), "url": None}, {**row("b.com", 2), "thumbnail": None}, row("c.com", 3)]
        self.assertEqual([p["source"] for p in web_images.clean_results(rows, limit=5)], ["c.com"])

    def test_limit_is_respected_and_titles_are_cleaned(self):
        rows = [row(f"shop{i}.com", i, title="Coat\x00\n  with   odd\tspaces " + "x" * 300) for i in range(6)]
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
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_second_search_for_the_same_piece_comes_from_the_cache(self):
        with mock.patch.object(web_images, "_search_web", return_value=[row("a.com", 1), row("b.com", 2)]) as search:
            first = web_images.search_images("a warm wool coat", 2)
            second = web_images.search_images("a warm wool coat", 2)
        self.assertEqual(search.call_count, 1)
        self.assertFalse(first["cached"])
        self.assertTrue(second["cached"])
        self.assertEqual(first["images"], second["images"])

    def test_a_blocked_search_returns_a_message_and_never_raises(self):
        with mock.patch.object(web_images, "_search_web", side_effect=RuntimeError("blocked")):
            result = web_images.search_images("a warm wool coat")
        self.assertEqual(result["images"], [])
        self.assertIn("unavailable", result["message"])

    def test_an_expired_cache_is_served_when_the_search_fails(self):
        with mock.patch.object(web_images, "_search_web", return_value=[row("a.com", 1)]):
            web_images.search_images("a warm wool coat")
        web_images._cache["warm wool coat product photo"]["at"] = time.time() - web_images.CACHE_SECONDS - 5
        with mock.patch.object(web_images, "_search_web", side_effect=RuntimeError("blocked")):
            result = web_images.search_images("a warm wool coat")
        self.assertEqual(len(result["images"]), 1)           # old photos beat an empty card
        self.assertTrue(result["cached"])

    def test_no_result_is_reported_and_not_cached(self):
        with mock.patch.object(web_images, "_search_web", return_value=[]) as search:
            first = web_images.search_images("a unicorn cape")
            web_images.search_images("a unicorn cape")
        self.assertEqual(first["images"], [])
        self.assertEqual(first["message"], "No photo found for this piece.")
        self.assertEqual(search.call_count, 2)               # an empty answer is retried, not remembered

    def test_searches_are_rate_limited(self):
        with mock.patch.object(web_images, "_search_web", return_value=[row("a.com", 1)]) as search:
            for i in range(web_images.MAX_SEARCHES_PER_MINUTE + 3):
                result = web_images.search_images(f"piece number {i}")
        self.assertEqual(search.call_count, web_images.MAX_SEARCHES_PER_MINUTE)
        self.assertIn("Too many", result["message"])

    def test_limit_is_capped_between_1_and_6(self):
        rows = [row(f"shop{i}.com", i) for i in range(10)]
        with mock.patch.object(web_images, "_search_web", return_value=rows):
            self.assertEqual(len(web_images.search_images("a coat", 99)["images"]), 6)
            self.assertEqual(len(web_images.search_images("a coat", 0)["images"]), 1)


if __name__ == "__main__":
    unittest.main()
