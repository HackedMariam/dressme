"""The Similar Agent and the agent-to-agent sub-call to the Wardrobe Agent. The LLM is replaced by a fake."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import config, similar_agent, wardrobe_agent  # noqa: E402

ITEMS = [
    {"id": "a", "name": "Navy Blazer", "category": "jacket", "category_group": "Outerwear", "color_name": "navy",
     "color_family": "cool", "material": "wool", "style": "classic", "occasions": ["work"], "seasons": ["autumn"]},
    {"id": "b", "name": "Black Pleated Skirt", "category": "skirt", "category_group": "Bottoms", "color_name": "black",
     "color_family": "neutral", "style": "classic", "occasions": ["work"], "seasons": ["autumn"]},
]
PIECES = [{"category": "jacket", "category_group": "Outerwear", "color_name": "navy", "color_family": "cool", "material": "wool"},
          {"category": "skirt", "category_group": "Bottoms", "color_name": "red", "color_family": "bright"},
          {"category": "shoe", "category_group": "Shoes", "color_name": "white", "color_family": "neutral"}]


def call(call_id, name, **arguments):
    function = SimpleNamespace(name=name, arguments=json.dumps(arguments))
    result = SimpleNamespace(id=call_id, function=function)
    result.model_dump = lambda: {"id": call_id, "type": "function", "function": {"name": name, "arguments": function.arguments}}
    return result


class FakeLLM:
    def __init__(self, script):
        self.script, self.calls = list(script), []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=self.script.pop(0))])


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setattr(config, "OPENAI_API_KEY", "test")
    monkeypatch.setattr(similar_agent, "_GRAPH", None)
    asked = []

    def ask(items, request):
        asked.append(request)
        return {"reply": "found", "items": [i for i in items if any(w in request.lower() for w in (i["category"], i["color_name"]))], "filters": []}

    monkeypatch.setattr(similar_agent, "_ask_wardrobe", ask)

    def install(script):
        llm = FakeLLM(script)
        monkeypatch.setattr("openai.OpenAI", lambda **kwargs: llm)
        return llm

    return install, asked


def test_the_agent_asks_the_wardrobe_agent_then_judges_every_piece(env):
    install, asked = env
    install([SimpleNamespace(content=None, tool_calls=[call("1", "ask_wardrobe_agent", request="navy wool jackets"),
                                                       call("2", "ask_wardrobe_agent", request="red skirts")]),
             SimpleNamespace(content=json.dumps({"pieces": [
                 {"index": 0, "status": "owned", "closest_item_id": "a", "reason": "You own the Navy Blazer."},
                 {"index": 1, "status": "close", "closest_item_id": "b", "reason": "Your skirt is black, not red."},
                 {"index": 2, "status": "missing", "closest_item_id": None, "reason": "No white shoes."}],
                 "summary": "You can recreate two thirds of this look."}), tool_calls=None)])
    result = similar_agent.compare(ITEMS, PIECES)
    assert asked == ["navy wool jackets", "red skirts"]
    assert [(p["status"], p["closest_item_id"], p["by"]) for p in result["pieces"]] == [
        ("owned", "a", "agent"), ("close", "b", "agent"), ("missing", None, "agent")]
    assert result["summary"].startswith("You can recreate")
    assert result["pieces"][0]["score"] > result["pieces"][1]["score"] > result["pieces"][2]["score"] == 0


def test_an_invented_piece_or_a_forgotten_one_is_decided_by_the_wardrobe_rules(env):
    install, _ = env
    install([SimpleNamespace(content=json.dumps({"pieces": [
        {"index": 0, "status": "owned", "closest_item_id": "ghost", "reason": "invented"},
        {"index": 1, "status": "maybe", "closest_item_id": "b", "reason": "bad status"}]}), tool_calls=None)])
    result = similar_agent.compare(ITEMS, PIECES)
    first = result["pieces"][0]
    assert first["by"] == "rules" and first["closest_item_id"] == "a" and first["status"] == "owned"   # the real blazer
    assert result["pieces"][1]["by"] == "rules" and result["pieces"][2]["status"] == "missing"


def test_without_the_llm_the_wardrobe_agents_ranking_answers(env, monkeypatch):
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
    result = similar_agent.compare(ITEMS, PIECES)
    assert [p["status"] for p in result["pieces"]] == ["owned", "close", "missing"]
    assert all(p["by"] == "rules" for p in result["pieces"]) and similar_agent.compare(ITEMS, []) == {"pieces": [], "summary": ""}


def test_the_sub_call_to_the_wardrobe_agent_is_read_only(monkeypatch):
    monkeypatch.setattr(config, "OPENAI_API_KEY", "test")
    llm = FakeLLM([SimpleNamespace(content=None, tool_calls=[call("1", "search_wardrobe", category="jacket")]),
                   SimpleNamespace(content="You own a navy blazer.", tool_calls=None)])
    monkeypatch.setattr("openai.OpenAI", lambda **kwargs: llm)
    answer = wardrobe_agent.ask(ITEMS, "any jackets?")
    assert answer["reply"] == "You own a navy blazer." and [i["id"] for i in answer["items"]] == ["a"]
    assert "update_item" not in {t["function"]["name"] for t in llm.calls[0]["tools"]}
    assert "read-only" in llm.calls[0]["messages"][0]["content"]
