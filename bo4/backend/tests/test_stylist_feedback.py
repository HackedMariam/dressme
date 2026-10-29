"""Tests du feedback (I76) et du profil de style (I77)."""

import json

import pytest

import stylist_feedback as fb

SHIRT = {"id": "1", "name": "Light Blue Shirt", "color": "light blue"}
CHINOS = {"id": "2", "name": "Beige Chinos", "color": "beige"}
JEANS = {"id": "3", "name": "Blue Jeans", "color": "denim blue"}


def test_empty_profile_gives_no_bonus():
    store = fb.FeedbackStore()
    assert store.profile()["likes"] == 0
    assert fb.personal_bonus([SHIRT, CHINOS], store.profile()) == 0.0
    assert fb.personal_bonus([SHIRT], None) == 0.0


def test_like_gives_positive_bonus_to_items_and_colors():
    store = fb.FeedbackStore()
    store.add("like", [SHIRT, CHINOS], "work")
    profile = store.profile()
    assert profile["likes"] == 1 and profile["liked_items"] == ["Light Blue Shirt", "Beige Chinos"]
    assert fb.personal_bonus([SHIRT, CHINOS], profile) == 2 * fb.ITEM_WEIGHT + 2 * fb.COLOR_WEIGHT
    assert fb.personal_bonus([SHIRT, JEANS], profile) == fb.ITEM_WEIGHT + fb.COLOR_WEIGHT
    assert fb.personal_bonus([JEANS], profile) == 0.0


def test_dislike_gives_negative_bonus_and_is_remembered():
    store = fb.FeedbackStore()
    store.add("dislike", [JEANS, CHINOS])
    assert fb.personal_bonus([JEANS], store.profile()) < 0
    assert store.disliked_outfits() == {frozenset({"2", "3"})}


def test_bonus_is_capped():
    store = fb.FeedbackStore()
    for _ in range(10):
        store.add("like", [SHIRT, CHINOS, JEANS])
    assert fb.personal_bonus([SHIRT, CHINOS, JEANS], store.profile()) == fb.BONUS_CAP


def test_invalid_verdict_is_rejected():
    with pytest.raises(ValueError):
        fb.FeedbackStore().add("love", [SHIRT])


def test_records_are_persisted_to_json(tmp_path):
    path = tmp_path / "feedback.json"
    fb.FeedbackStore(path).add("like", [SHIRT], "work")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["records"][0]["item_ids"] == ["1"]
    assert fb.FeedbackStore(path).profile()["likes"] == 1   # relu au redémarrage


def test_profiles_are_per_user():
    store = fb.FeedbackStore()
    store.add("like", [SHIRT], user="alice")
    assert store.profile("local")["likes"] == 0
    assert store.profile("alice")["likes"] == 1


def test_dislike_weighs_less_than_like():
    store = fb.FeedbackStore()
    store.add("dislike", [SHIRT, CHINOS])
    penalty = fb.personal_bonus([SHIRT, CHINOS], store.profile())
    assert penalty == -(2 * fb.ITEM_WEIGHT + 2 * fb.COLOR_WEIGHT) * fb.DISLIKE_WEIGHT
