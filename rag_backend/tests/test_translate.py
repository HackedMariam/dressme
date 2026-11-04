"""Query step: French questions are translated into English, never rewritten."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from rag import translate


def _reply(text):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


@pytest.fixture
def llm(monkeypatch):
    """Fake LLM: records the messages and returns a fixed translation."""
    calls = []

    def fake_chat_completion(**kwargs):
        calls.append(kwargs)
        return _reply(calls_reply[0])

    calls_reply = ["How do I wash a wool sweater?"]
    import rag.llm_client
    monkeypatch.setattr(rag.llm_client, "chat_completion", fake_chat_completion)
    monkeypatch.setenv("QUERY_REWRITE_ENABLED", "true")
    from config import reload_settings
    reload_settings()
    return calls, calls_reply


@pytest.mark.parametrize("question, french", [
    ("Comment laver un pull en laine ?", True),
    ("Quelles couleurs associer au bleu marine ?", True),
    ("Que porter pour un entretien d'embauche ?", True),
    ("How do I wash a wool sweater?", False),
    ("Which colours go with navy blue?", False),
])
def test_is_french(question, french):
    assert translate.is_french(question) is french


def test_english_question_is_sent_unchanged(llm):
    calls, _ = llm
    assert translate.translate_query("How do I tie and wear a scarf?") == "How do I tie and wear a scarf?"
    assert calls == []                                     # no LLM call, no rewrite


def test_french_question_is_translated_only(llm):
    calls, _ = llm
    assert translate.translate_query("Comment laver un pull en laine ?") == "How do I wash a wool sweater?"
    assert calls[0]["temperature"] == 0.0
    system = calls[0]["messages"][0]["content"]
    assert "Translate only" in system and "do not add" in system


def test_glossary_fixes_french_garment_words(llm):
    _, reply = llm
    reply[0] = "How to wear a black col roule with a wide pantalon?"
    assert translate.translate_query("Comment porter un col roulé noir avec un pantalon large ?") == \
        "How to wear a black turtleneck with a wide trousers?"


@pytest.mark.parametrize("reply", ["", "x" * 400])
def test_unusable_translation_falls_back_to_the_question(llm, reply):
    _, replies = llm
    replies[0] = reply
    question = "Comment laver un pull en laine ?"
    assert translate.translate_query(question) == question


def test_llm_down_falls_back_to_the_question(monkeypatch):
    import rag.llm_client

    def down(**kwargs):
        raise rag.llm_client.LLMUnavailable("down")
    monkeypatch.setattr(rag.llm_client, "chat_completion", down)
    monkeypatch.setenv("QUERY_REWRITE_ENABLED", "true")
    from config import reload_settings
    reload_settings()
    assert translate.translate_query("Comment laver un pull en laine ?") == "Comment laver un pull en laine ?"


def test_switch_off_keeps_the_question(llm, monkeypatch):
    calls, _ = llm
    monkeypatch.setenv("QUERY_REWRITE_ENABLED", "false")
    from config import reload_settings
    reload_settings()
    assert translate.translate_query("Comment laver un pull en laine ?") == "Comment laver un pull en laine ?"
    assert calls == []


def test_rag_service_uses_translation_not_rewrite():
    from pathlib import Path
    source = (Path(translate.__file__).with_name("rag_service.py")).read_text(encoding="utf-8")
    assert "translate_query(question)" in source and "rewrite_query(" not in source


def test_generation_prompt_requires_citations_and_dont_know():
    from pathlib import Path
    source = (Path(translate.__file__).with_name("rag_service.py")).read_text(encoding="utf-8")
    assert 'DONT_KNOW_ANSWER = "I don\'t know: none of the DressMe sources answers this question."' in source
    assert "Every bullet must end with" in source and "General guidance" not in source


@pytest.mark.parametrize("french, sent", [
    ("Quelles couleurs associer au bleu marine ?", "Quelles couleurs associer au navy blue ?"),
    ("Comment choisir des talons confortables ?", "Comment choisir des heels confortables ?"),
    ("Comment les tendances de mode sont-elles prévues ?", "Comment les trends de mode sont-elles forecast ?"),
])
def test_source_terms_are_replaced_before_translation(llm, french, sent):
    calls, _ = llm
    translate.translate_query(french)
    assert calls[0]["messages"][1]["content"] == sent


@pytest.mark.parametrize("english, fixed", [
    ("What colours go with blue marine?", "What colours go with navy blue?"),
    ("How to choose comfortable talons?", "How to choose comfortable heels?"),
    ("How are fashion tendances forecast?", "How are fashion trends forecast?"),
])
def test_glossary_fixes_colour_heels_and_trends(english, fixed):
    assert translate.apply_glossary(english) == fixed
