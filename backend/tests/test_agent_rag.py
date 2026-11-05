"""The AI stylist asks the fashion-knowledge RAG as a tool. The LLM and the RAG service are replaced by fakes."""
import json
from types import SimpleNamespace

import httpx
import pytest

from app import agent, config, rag_client

ITEMS = [{"id": "jacket-1", "name": "Navy blazer", "category": "jacket", "category_group": "Outerwear",
          "color_name": "navy", "seasons": ["autumn"], "occasions": ["work"], "style": "classic", "warmth": 3}]


# --------------------------------------------------------------------------------------------- rag_client
def _rag(handler):
    return httpx.MockTransport(handler)


def test_advise_returns_the_answer_with_deduplicated_numbered_sources(monkeypatch):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"], seen["key"], seen["body"] = str(request.url), request.headers.get("x-api-key"), json.loads(request.content)
        return httpx.Response(200, json={
            "answer": "Wear a dark suit [S1][S2].", "grounded": True,
            "citations": [{"marker": "[S1]", "title": "Mens wardrobe", "page": 12, "source": "mens.pdf"},
                          {"marker": "[S1]", "title": "Mens wardrobe", "page": 12},
                          {"marker": "[S2]", "title": None, "source": "accessories.pdf", "page": None}]})

    monkeypatch.setattr(config, "RAG_URL", "http://rag.test:8010/")
    monkeypatch.setattr(config, "RAG_API_KEY", "secret")
    advice = rag_client.advise("What to wear to a wedding?", transport=_rag(handler))
    assert seen["url"] == "http://rag.test:8010/ask" and seen["key"] == "secret"
    assert seen["body"]["question"] == "What to wear to a wedding?"
    assert advice["answer"].startswith("Wear a dark suit")
    assert [s["marker"] for s in advice["sources"]] == ["[S1]", "[S2]"]
    assert advice["sources"][1]["title"] == "accessories.pdf"           # falls back to the file name


@pytest.mark.parametrize("reply", [httpx.Response(503, json={"detail": "index unavailable"}),
                                   httpx.Response(200, json={"answer": "  ", "citations": []}),
                                   httpx.Response(200, json={"answer": "I don't know: no source answers this.",
                                                             "citations": [], "grounded": False}),
                                   httpx.Response(200, text="not json")])
def test_advise_is_none_when_the_service_cannot_help(monkeypatch, reply):
    monkeypatch.setattr(config, "RAG_URL", "http://rag.test:8010")
    assert rag_client.advise("question", transport=_rag(lambda request: reply)) is None


def test_advise_is_none_when_the_service_is_down_or_switched_off(monkeypatch):
    def down(request):
        raise httpx.ConnectError("refused", request=request)

    monkeypatch.setattr(config, "RAG_URL", "http://rag.test:8010")
    assert rag_client.advise("question", transport=_rag(down)) is None
    monkeypatch.setattr(config, "RAG_URL", "")
    assert rag_client.advise("question") is None
    assert rag_client.advise("   ") is None


# ------------------------------------------------------------------------------------------- the agent
class FakeLLM:
    """Plays an OpenAI client: each call answers with the next scripted message."""

    def __init__(self, script):
        self.script, self.calls = list(script), []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        message = self.script.pop(0)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _tool_call(call_id, name, **arguments):
    function = SimpleNamespace(name=name, arguments=json.dumps(arguments))
    call = SimpleNamespace(id=call_id, function=function)
    call.model_dump = lambda: {"id": call_id, "type": "function", "function": {"name": name, "arguments": function.arguments}}
    return call


def _message(content=None, tool_calls=None):
    return SimpleNamespace(content=content, tool_calls=tool_calls)


@pytest.fixture
def llm(monkeypatch):
    holder = {}

    def install(script):
        holder["llm"] = FakeLLM(script)
        monkeypatch.setattr("openai.OpenAI", lambda **kwargs: holder["llm"])
        monkeypatch.setattr(config, "OPENAI_API_KEY", "test")
        return holder["llm"]

    return install


def test_the_stylist_combines_the_wardrobe_with_book_advice_and_keeps_only_cited_sources(monkeypatch, llm):
    asked = []

    def advise(question):
        asked.append(question)
        return {"answer": "Navy pairs with grey and white [S1]. Avoid black with navy [S2].", "grounded": True,
                "sources": [{"marker": "[S1]", "title": "Color Harmony Workbook", "page": 8, "source": "c.pdf"},
                            {"marker": "[S2]", "title": "Dress to Impress Guide", "page": 3, "source": "d.pdf"}]}

    monkeypatch.setattr(rag_client, "advise", advise)
    fake = llm([
        _message(tool_calls=[_tool_call("a", "search_wardrobe", text="navy"),
                             _tool_call("b", "fashion_advice", question="Which colours go with navy?")]),
        _message("Your Navy blazer works with grey trousers [S1]."),
    ])
    reply = agent.chat(ITEMS, "Quelles couleurs avec mon blazer marine ?")

    assert asked == ["Which colours go with navy?"]
    assert [item["id"] for item in reply["items"]] == ["jacket-1"]            # still only owned items
    assert [s["marker"] for s in reply["sources"]] == ["[S1]"]                # [S2] was not used in the answer
    assert reply["sources"][0]["title"] == "Color Harmony Workbook"
    offered = [tool["function"]["name"] for tool in fake.calls[0]["tools"]]
    assert offered == ["search_wardrobe", "fashion_advice", "get_weather"]
    tool_messages = [m for m in fake.calls[1]["messages"] if m["role"] == "tool"]
    assert "Navy pairs with grey" in tool_messages[1]["content"]              # the advice reaches the model


def test_without_the_knowledge_service_the_stylist_still_answers_from_the_wardrobe(monkeypatch, llm):
    monkeypatch.setattr(rag_client, "advise", lambda question: None)
    fake = llm([
        _message(tool_calls=[_tool_call("b", "fashion_advice", question="How to style a blazer?"),
                             _tool_call("a", "search_wardrobe", text="blazer")]),
        _message("Wear your Navy blazer with jeans."),
    ])
    reply = agent.chat(ITEMS, "How do I style my blazer?")
    assert reply["reply"] == "Wear your Navy blazer with jeans." and reply["sources"] == []
    tool_messages = [m for m in fake.calls[1]["messages"] if m["role"] == "tool"]
    assert json.loads(tool_messages[0]["content"])["advice"] is None          # the model is told it is unavailable


def test_the_duplicate_check_cannot_call_the_knowledge_base(llm):
    fake = llm([_message('{"duplicate": false, "similar_item_id": null, "note": ""}')])
    agent.check_duplicate(ITEMS, {"category": "jacket", "color_name": "navy"})
    assert [tool["function"]["name"] for tool in fake.calls[0]["tools"]] == ["search_wardrobe"]


def test_a_style_question_answered_without_the_knowledge_base_is_sent_back_to_consult_it_once(monkeypatch, llm):
    monkeypatch.setattr(rag_client, "advise", lambda question: {
        "answer": "Wool is the warmest winter fabric [S1].", "grounded": True,
        "sources": [{"marker": "[S1]", "title": "Textilepedia", "page": 40, "source": "t.pdf"}]})
    fake = llm([
        _message("Wool is great in winter."),                                    # skipped fashion_advice
        _message(tool_calls=[_tool_call("c", "fashion_advice", question="Best winter fabric?")]),
        _message("Wool keeps you warmest [S1]."),
    ])
    reply = agent.chat(ITEMS, "Quel tissu est le plus adapte pour l'hiver ?")
    assert reply["reply"] == "Wool keeps you warmest [S1]." and [s["title"] for s in reply["sources"]] == ["Textilepedia"]
    assert {"role": "user", "content": agent.ADVICE_REMINDER} in fake.calls[1]["messages"]
    assert [m for m in fake.calls[2]["messages"] if m["content"] == agent.ADVICE_REMINDER].__len__() == 1   # only once


def test_a_plain_item_search_is_not_sent_to_the_knowledge_base(monkeypatch, llm):
    monkeypatch.setattr(rag_client, "advise", lambda question: pytest.fail("the knowledge base was not needed"))
    fake = llm([_message(tool_calls=[_tool_call("a", "search_wardrobe", color_name="navy")]),
                _message("Here is your Navy blazer.")])
    reply = agent.chat(ITEMS, "Show me my navy pieces")
    assert reply["reply"] == "Here is your Navy blazer." and reply["sources"] == [] and len(fake.calls) == 2


def test_the_reminder_is_skipped_when_the_knowledge_service_is_switched_off(monkeypatch, llm):
    monkeypatch.setattr(config, "RAG_URL", "")
    fake = llm([_message("Wool.")])
    assert agent.chat(ITEMS, "Which fabric for winter?")["reply"] == "Wool." and len(fake.calls) == 1


# ------------------------------------------------------------------------- structured answer (sections)
ITEMS2 = ITEMS + [
    {"id": "jeans-1", "name": "Light Blue Jeans", "category": "pants", "category_group": "Bottoms", "color_name": "blue",
     "seasons": ["autumn"], "occasions": ["work"], "style": "casual", "warmth": 2},
    {"id": "shoes-1", "name": "Brown Suede Sneakers", "category": "shoe", "category_group": "Shoes",
     "color_name": "brown", "seasons": ["autumn"], "occasions": ["work"], "style": "casual", "warmth": 2},
]


def test_the_answer_comes_in_sections_with_the_outfit_pieces_and_only_the_sources_it_cites(monkeypatch, llm):
    monkeypatch.setattr(rag_client, "advise", lambda question: {
        "answer": "x", "grounded": True,
        "sources": [{"marker": "[S1]", "title": "Color Harmony Workbook", "page": 8, "source": "c.pdf"},
                    {"marker": "[S2]", "title": "Dress to Impress Guide", "page": 3, "source": "d.pdf"}]})
    llm([
        _message(tool_calls=[_tool_call("a", "search_wardrobe", season="autumn"),
                             _tool_call("b", "fashion_advice", question="Colours that go with navy?")]),
        _message(json.dumps({
            "answer": "Try your **Navy blazer** with light jeans.",
            "outfit": ["Navy blazer + Light Blue Jeans + Brown Suede Sneakers"],
            "why": ["- Navy pairs well with light blue [S1].", "A relaxed fit keeps it casual."],
            "tips": "Roll the sleeves.\nKeep the shoes clean [S1].",
        })),
    ])
    reply = agent.chat(ITEMS2, "Quelles couleurs avec mon blazer marine ?")

    assert reply["reply"] == "Try your Navy blazer with light jeans."          # markdown stripped
    assert reply["sections"] == {"weather": [], "outfit": ["Navy blazer + Light Blue Jeans + Brown Suede Sneakers"],
                                 "why": ["Navy pairs well with light blue [S1].", "A relaxed fit keeps it casual."],
                                 "alternatives": [], "tips": ["Roll the sleeves.", "Keep the shoes clean [S1]."]}
    assert reply["weather"] is None
    assert [i["id"] for i in reply["items"]] == ["jacket-1", "jeans-1", "shoes-1"]   # the outfit, in the order named
    assert [s["marker"] for s in reply["sources"]] == ["[S1]"]                       # [S2] was never cited


def test_a_plain_search_answer_keeps_every_item_found_and_has_empty_sections(monkeypatch, llm):
    monkeypatch.setattr(rag_client, "advise", lambda question: pytest.fail("not needed"))
    llm([_message(tool_calls=[_tool_call("a", "search_wardrobe", color_name="navy")]),
         _message(json.dumps({"answer": "Here is your Navy blazer.", "outfit": [], "why": [], "tips": []}))])
    reply = agent.chat(ITEMS2, "Show me my navy pieces")
    assert reply["reply"] == "Here is your Navy blazer." and [i["id"] for i in reply["items"]] == ["jacket-1"]
    assert all(lines == [] for lines in reply["sections"].values()) and reply["sources"] == []


def test_a_model_that_ignores_the_format_still_gets_its_text_shown(llm):
    llm([_message(tool_calls=[_tool_call("a", "search_wardrobe", text="blazer")]), _message("Wear the Navy blazer.")])
    reply = agent.chat(ITEMS2, "Show me a blazer")
    assert reply["reply"] == "Wear the Navy blazer." and reply["sections"] is None


def test_every_model_call_asks_for_the_json_answer(llm):
    fake = llm([_message(json.dumps({"answer": "Hi."}))])
    agent.chat(ITEMS2, "Hello")
    assert fake.calls[0]["response_format"] == {"type": "json_object"}


# ------------------------------------------------------------------------------------------------ weather
FORECAST = {"city": "Tunis", "country": "Tunisia", "date": "2026-11-06", "weekday": "Friday", "days_ahead": 1,
            "condition": "light rain", "temp_min_c": 12, "temp_max_c": 17, "temp_min_f": 54, "temp_max_f": 63,
            "rain_chance_percent": 70, "rain_mm": 3.2, "wind_kmh": 25, "summary": "Friday 6 November in Tunis: light rain"}


def test_the_stylist_checks_the_weather_of_the_users_city_and_returns_it_with_the_answer(monkeypatch, llm):
    asked = []
    monkeypatch.setattr(agent.weather, "day_forecast",
                        lambda city, country="", days_ahead=0: asked.append((city, country, days_ahead)) or FORECAST)
    monkeypatch.setattr(rag_client, "advise", lambda question: None)
    fake = llm([
        _message(tool_calls=[_tool_call("a", "get_weather", days_ahead=1), _tool_call("b", "search_wardrobe"),
                             _tool_call("c", "fashion_advice", question="Dress code?")]),
        _message(json.dumps({"answer": "My pick: the Navy blazer.", "weather": "12 to 17 C and 70% chance of rain.",
                             "outfit": ["Navy blazer"], "why": ["Warmth 3 suits 12 C."], "alternatives": ["No coat."],
                             "tips": ["Take an umbrella."]})),
    ])
    reply = agent.chat(ITEMS, "What should I wear tomorrow?", {"city": "Tunis", "country": "Tunisia", "unit": "Fahrenheit"})

    assert asked == [("Tunis", "Tunisia", 1)]
    assert reply["sections"]["weather"] == ["12 to 17 C and 70% chance of rain."]
    assert reply["sections"]["alternatives"] == ["No coat."]
    assert reply["weather"]["condition"] == "light rain" and reply["weather"]["unit"] == "F"
    assert (reply["weather"]["temp_min"], reply["weather"]["temp_max"]) == (54, 63)
    system = fake.calls[0]["messages"][0]["content"]
    assert "Tunis, Tunisia" in system and "days_ahead 1" in system


def test_a_failing_weather_service_does_not_break_the_answer(monkeypatch, llm):
    monkeypatch.setattr(agent.weather, "day_forecast", lambda *args, **kwargs: None)
    monkeypatch.setattr(rag_client, "advise", lambda question: None)
    fake = llm([_message(tool_calls=[_tool_call("a", "get_weather"), _tool_call("b", "fashion_advice", question="x")]),
                _message(json.dumps({"answer": "I could not check the weather.", "weather": "Not checked."}))])
    reply = agent.chat(ITEMS, "Que mettre aujourd'hui ?", {"city": "Nowhere"})
    assert reply["weather"] is None and reply["reply"] == "I could not check the weather."
    assert any("could not be checked" in str(m["content"]) for m in fake.calls[1]["messages"] if m["role"] == "tool")


def test_the_model_that_skips_the_weather_on_an_outfit_question_is_reminded_once(monkeypatch, llm):
    monkeypatch.setattr(agent.weather, "day_forecast", lambda *args, **kwargs: FORECAST)
    monkeypatch.setattr(rag_client, "advise", lambda question: None)
    fake = llm([_message(tool_calls=[_tool_call("b", "fashion_advice", question="x")]),
                _message(json.dumps({"answer": "Wear the blazer."})),
                _message(tool_calls=[_tool_call("a", "get_weather")]),
                _message(json.dumps({"answer": "Wear the blazer.", "weather": "Rainy."}))])
    reply = agent.chat(ITEMS, "What should I wear?", {"city": "Tunis"})
    assert any("call get_weather" in str(m["content"]) for m in fake.calls[2]["messages"] if m["role"] == "user")
    assert reply["weather"]["city"] == "Tunis"


def test_without_a_city_the_weather_is_the_one_of_tunis(monkeypatch, llm):
    asked = []
    monkeypatch.setattr(agent.weather, "day_forecast",
                        lambda city, country="", days_ahead=0: asked.append((city, country)) or FORECAST)
    monkeypatch.setattr(rag_client, "advise", lambda question: None)
    fake = llm([_message(tool_calls=[_tool_call("a", "get_weather"), _tool_call("b", "fashion_advice", question="x")]),
                _message(json.dumps({"answer": "Wear the blazer.", "weather": "Rainy."}))])
    reply = agent.chat(ITEMS, "Que mettre ce soir ?", {"country": ""})
    assert asked == [("Tunis", "Tunisia")] and reply["weather"]["city"] == "Tunis"
    assert "Tunis, Tunisia" in fake.calls[0]["messages"][0]["content"]


def test_a_town_unknown_to_the_weather_service_falls_back_on_tunis(monkeypatch, llm):
    asked = []

    def forecast(city, country="", days_ahead=0):
        asked.append(city)
        return FORECAST if city == "Tunis" else None

    monkeypatch.setattr(agent.weather, "day_forecast", forecast)
    monkeypatch.setattr(rag_client, "advise", lambda question: None)
    llm([_message(tool_calls=[_tool_call("a", "get_weather"), _tool_call("b", "fashion_advice", question="x")]),
         _message(json.dumps({"answer": "Wear the blazer.", "weather": "Rainy in Tunis."}))])
    reply = agent.chat(ITEMS, "What to wear?", {"city": "Tiny Village", "country": "Tunisia"})
    assert asked == ["Tiny Village", "Tunis"] and reply["weather"]["city"] == "Tunis"
