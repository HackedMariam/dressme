"""The Outfit Builder agent (LangGraph graph). The LLM, the weather and the RAG service are replaced by fakes."""
import json
from types import SimpleNamespace

import pytest

from app import config, outfit_agent, rag_client

CLOSET = [
    {"id": "t1", "name": "White Tee", "category": "t-shirt", "category_group": "Tops", "color_family": "neutral", "warmth": 1},
    {"id": "t2", "name": "Navy Knit", "category": "sweater", "category_group": "Tops", "color_family": "cool", "warmth": 4},
    {"id": "b1", "name": "Grey Trousers", "category": "pants", "category_group": "Bottoms", "color_family": "neutral"},
    {"id": "b2", "name": "Blue Jeans", "category": "pants", "category_group": "Bottoms", "color_family": "cool"},
    {"id": "d1", "name": "Black Dress", "category": "dress", "category_group": "Dresses", "color_family": "neutral"},
    {"id": "s1", "name": "White Sneakers", "category": "shoe", "category_group": "Shoes", "color_family": "neutral"},
    {"id": "o1", "name": "Black Trench", "category": "jacket", "category_group": "Outerwear", "color_family": "neutral", "warmth": 3},
]
FORECAST = {"city": "Tunis", "country": "Tunisia", "date": "2026-11-05", "weekday": "Thursday", "days_ahead": 0,
            "condition": "light rain", "temp_min_c": 12, "temp_max_c": 17, "temp_min_f": 54, "temp_max_f": 63,
            "rain_chance_percent": 70, "wind_kmh": 20, "summary": "Thursday 5 November in Tunis: light rain, 12 to 17 C"}


class FakeLLM:
    def __init__(self, script):
        self.script, self.calls = list(script), []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        content = self.script.pop(0)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(content)))])


@pytest.fixture
def agent_env(monkeypatch):
    def install(script, forecast=FORECAST):
        llm = FakeLLM(script)
        monkeypatch.setattr("openai.OpenAI", lambda **kwargs: llm)
        monkeypatch.setattr(config, "OPENAI_API_KEY", "test")
        monkeypatch.setattr(outfit_agent.weather, "day_forecast", lambda *a, **k: forecast)
        monkeypatch.setattr(rag_client, "advise", lambda question: {
            "answer": "Neutrals pair with anything [S1].", "grounded": True,
            "sources": [{"marker": "[S1]", "title": "Color Harmony Workbook", "page": 8, "source": "c.pdf"},
                        {"marker": "[S2]", "title": "Unused", "page": 1, "source": "u.pdf"}]})
        monkeypatch.setattr(outfit_agent, "_GRAPH", None)
        return llm

    return install


def test_the_agent_builds_validated_outfits_from_the_weather_the_closet_and_the_books(agent_env):
    llm = agent_env([{"outfits": [
        {"title": "Rainy day casual", "items": ["t2", "b2", "s1", "o1"], "weather_note": "12 to 17 C and rain: knit + trench.",
         "why": ["Navy Knit has warmth 4 [S1]."]},
        {"title": "Dress up", "items": ["d1", "s1", "o1"], "why": ["Neutral palette."]}], "missing": ["a rain jacket"]}])
    result = outfit_agent.build(CLOSET, "everyday", "autumn", {"city": "Tunis", "unit": "Fahrenheit"})

    assert [o["items"] for o in result["outfits"]] == [["t2", "b2", "s1", "o1"], ["d1", "s1", "o1"]]
    assert result["outfits"][0]["title"] == "Rainy day casual"
    assert result["missing"] == ["a rain jacket"]
    assert result["weather"]["condition"] == "light rain" and (result["weather"]["temp_min"], result["weather"]["unit"]) == (54, "F")
    assert [s["marker"] for s in result["sources"]] == ["[S1]"]                 # only the cited book passage
    brief = llm.calls[0]["messages"][1]["content"]
    assert "light rain" in brief and "Neutrals pair" in brief and "Black Trench" in brief


def test_an_invalid_outfit_is_sent_back_once_and_only_valid_ones_are_returned(agent_env):
    llm = agent_env([
        {"outfits": [{"title": "Bad", "items": ["t1", "s1"], "why": []},                     # no bottom
                     {"title": "Ghost", "items": ["t1", "b1", "s1", "nope"], "why": []},     # unknown piece
                     {"title": "Good", "items": ["t1", "b1", "s1", "o1"], "why": ["ok"]}]},
        {"outfits": [{"title": "Fixed", "items": ["t2", "b1", "s1", "o1"], "why": ["warm"]}]},
    ])
    result = outfit_agent.build(CLOSET, "work", "winter")
    assert len(llm.calls) == 2
    feedback = llm.calls[1]["messages"][-1]["content"]
    assert "Outfit 1" in feedback and "needs a dress, or a top and a bottom" in feedback and "unknown ids" in feedback
    assert [o["title"] for o in result["outfits"]] == ["Good", "Fixed"] or [o["title"] for o in result["outfits"]] == ["Fixed"]


def test_the_rules_of_a_valid_outfit():
    by_id = {i["id"]: i for i in CLOSET}
    assert outfit_agent.check_outfit(["t1", "b1", "s1"], by_id, cold=False) == []
    assert outfit_agent.check_outfit(["d1", "s1"], by_id, cold=False) == []
    assert "it has no shoes" in outfit_agent.check_outfit(["d1"], by_id, cold=False)
    assert "a dress is worn alone, without a top or bottom" in outfit_agent.check_outfit(["d1", "t1", "s1"], by_id, cold=False)
    assert "two pieces of role Tops" in outfit_agent.check_outfit(["t1", "t2", "b1", "s1"], by_id, cold=False)
    assert "the weather is cold: add an outerwear piece" in outfit_agent.check_outfit(["t1", "b1", "s1"], by_id, cold=True)


def test_the_agent_still_works_without_a_forecast_and_with_a_failing_llm(agent_env, monkeypatch):
    llm = agent_env([{"outfits": [{"title": "Simple", "items": ["t1", "b1", "s1"], "why": ["Neutral."]}]}], forecast=None)
    result = outfit_agent.build(CLOSET, "everyday", "summer")
    assert result["weather"] is None and len(result["outfits"]) == 1
    assert "unavailable" in llm.calls[0]["messages"][1]["content"]

    def boom(**kwargs):
        raise RuntimeError("down")

    monkeypatch.setattr(llm.chat.completions, "create", boom)
    monkeypatch.setattr(outfit_agent, "_GRAPH", None)
    assert outfit_agent.build(CLOSET, "everyday", "summer")["outfits"] == []


def test_the_route_returns_the_agents_outfits(agent_env, monkeypatch):
    from fastapi.testclient import TestClient

    from app import main
    from app.auth import User, current_user

    agent_env([{"outfits": [{"title": "Simple", "items": ["t1", "b1", "s1"], "why": []}]}], forecast=None)
    monkeypatch.setattr(main.store, "list_items", lambda user_id: CLOSET)
    main.app.dependency_overrides[current_user] = lambda: User(id="u1")
    try:
        reply = TestClient(main.app).post("/api/outfits/agent", json={"occasion": "work", "season": "summer", "city": "Tunis"})
    finally:
        main.app.dependency_overrides.clear()
    assert reply.status_code == 200 and reply.json()["outfits"][0]["items"] == ["t1", "b1", "s1"]
