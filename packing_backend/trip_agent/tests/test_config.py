"""Tests for LLM environment-variable model resolution."""

from __future__ import annotations

from packing_backend.trip_agent import config


def _provider_models() -> dict[str, str]:
    return {
        name: model
        for name, _key, model in config.get_llm_providers()
    }


def test_provider_models_use_dedicated_variables(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.setenv("GROQ_API_KEY", "groq-key")
    monkeypatch.setenv("LLM_MODEL", "gpt-4.1")
    monkeypatch.setenv("AI_MODEL", "generic-model")
    monkeypatch.setenv("GROQ_MODEL", "groq-model")

    assert _provider_models() == {
        "openai": "gpt-4.1",
        "groq": "groq-model",
    }
    assert config.get_model() == "gpt-4.1"


def test_ai_model_is_the_generic_fallback(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.setenv("GROQ_API_KEY", "groq-key")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("GROQ_MODEL", raising=False)
    monkeypatch.setenv("AI_MODEL", "generic-model")

    assert _provider_models() == {
        "openai": "generic-model",
        "groq": "generic-model",
    }


def test_defaults_apply_when_models_are_unset(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.setenv("GROQ_API_KEY", "groq-key")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("AI_MODEL", raising=False)
    monkeypatch.delenv("GROQ_MODEL", raising=False)

    assert _provider_models() == {
        "openai": config.DEFAULT_OPENAI_MODEL,
        "groq": config.DEFAULT_GROQ_MODEL,
    }


def test_blank_model_values_fall_back(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.setenv("GROQ_API_KEY", "groq-key")
    monkeypatch.setenv("LLM_MODEL", "  ")
    monkeypatch.setenv("AI_MODEL", "")
    monkeypatch.setenv("GROQ_MODEL", " ")

    assert _provider_models() == {
        "openai": config.DEFAULT_OPENAI_MODEL,
        "groq": config.DEFAULT_GROQ_MODEL,
    }
