"""The Gap Agent reads the wardrobe through the Wardrobe Agent (A2A) and falls back on Supabase.

Run from "DressMe UI Blueprint/backend":  python -m unittest discover -s tests -v
"""

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from a2a_protocol import A2AError
from agent import a2a_wardrobe, wardrobe_source

USER = "11111111-1111-1111-1111-111111111111"
ROW = {"id": "r1", "name": "Navy Blazer", "category": "jacket", "category_group": "Outerwear", "color_name": "navy",
       "color_family": "cool", "seasons": ["autumn"], "occasions": ["work"], "style": "classic", "material": "wool"}


class FakeClient:
    calls = []
    rows = [ROW]
    error = None

    def __init__(self, url, token=None, timeout=0, transport=None):
        FakeClient.calls.append((url, token))

    def send(self, text="", data=None, context_id=None):
        FakeClient.calls.append(data)
        if FakeClient.error:
            raise FakeClient.error
        return {"status": {"state": "completed"}, "artifacts": [{"parts": [{"kind": "data", "data": {"items": FakeClient.rows}}]}]}

    state_of = staticmethod(lambda task: task["status"]["state"])
    data_of = staticmethod(lambda task: task["artifacts"][0]["parts"][0]["data"])


class WardrobeOverA2ATest(unittest.TestCase):
    def setUp(self):
        FakeClient.calls, FakeClient.rows, FakeClient.error = [], [ROW], None
        wardrobe_source._cache.clear()
        a2a_wardrobe._tokens.clear()
        patcher = mock.patch.object(a2a_wardrobe, "A2AClient", FakeClient)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_the_wardrobe_is_asked_to_the_wardrobe_agent_with_the_users_token(self):
        a2a_wardrobe.remember(USER, "tok-1")
        with mock.patch.object(wardrobe_source, "_fetch_supabase", side_effect=AssertionError("Supabase must not be read")):
            items = wardrobe_source.load_wardrobe(USER)
            info = wardrobe_source.source_info(USER)
        self.assertEqual([item["id"] for item in items], ["r1"])
        self.assertIn("Wardrobe Agent", info["reason"])
        self.assertIn(("http://127.0.0.1:8000/a2a/wardrobe", "tok-1"), FakeClient.calls)
        self.assertIn({"action": "list"}, FakeClient.calls)

    def test_without_a_token_or_when_the_agent_is_down_supabase_is_read_as_before(self):
        with mock.patch.object(wardrobe_source, "_fetch_supabase", return_value=[{"id": "s1"}]) as fetch:
            self.assertEqual(wardrobe_source.load_wardrobe(USER), [{"id": "s1"}])          # no token remembered
            fetch.assert_called_once()
        wardrobe_source._cache.clear()
        a2a_wardrobe.remember(USER, "tok-2")
        FakeClient.error = A2AError("unreachable")
        with mock.patch.object(wardrobe_source, "_fetch_supabase", return_value=[{"id": "s2"}]):
            self.assertEqual(wardrobe_source.load_wardrobe(USER), [{"id": "s2"}])

    def test_the_demo_user_never_goes_through_the_wardrobe_agent(self):
        a2a_wardrobe.remember(wardrobe_source.DEMO_USER, "tok-3")
        wardrobe_source.load_wardrobe(None)
        self.assertEqual(FakeClient.calls, [])

    def test_tokens_expire_and_belong_to_one_user(self):
        a2a_wardrobe.remember(USER, "tok-4")
        self.assertIsNone(a2a_wardrobe.fetch_rows("someone-else"))
        with mock.patch.object(a2a_wardrobe.time, "time", return_value=10 ** 12):
            self.assertIsNone(a2a_wardrobe.fetch_rows(USER))


if __name__ == "__main__":
    unittest.main()
