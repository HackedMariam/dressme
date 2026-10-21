"""GPT tool-use loop, explanations and LLM fallback - with a scripted fake OpenAI client (no network, no cost)"""

import json
from types import SimpleNamespace

import pytest


class FakeToolCall:
    def __init__(self, call_id, name, arguments):
        self.id = call_id
        self.type = "function"
        self.function = SimpleNamespace(name=name, arguments=json.dumps(arguments))

    def model_dump(self):
        return {"id": self.id, "type": "function",
                "function": {"name": self.function.name, "arguments": self.function.arguments}}


def _response(content=None, tool_calls=None, finish="stop"):
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason=finish)],
                           usage=SimpleNamespace(prompt_tokens=100, completion_tokens=20))


class FakeCompletions:
    """Replays scripted responses and records every request"""

    def __init__(self, script):
        self.script = list(script)
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def fake_openai(script):
    from openai_client import OpenAIClient

    client = OpenAIClient("", "gpt-test", enabled=False)
    completions = FakeCompletions(script)
    client.client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    client.error = None
    return client, completions


AGENT_SCRIPT = [
    _response(tool_calls=[FakeToolCall("c1", "get_wardrobe", {}),
                          FakeToolCall("c2", "analyze_redundancy", {"name": "Navy Oxford Shirt", "category": "shirts",
                                                                    "color": "navy", "style": "business"})],
              finish="tool_calls"),
    _response(tool_calls=[FakeToolCall("c3", "run_feature", {"feature_id": 25, "arguments_json": json.dumps({"price": 80, "brand": "Zara"})}),
                          FakeToolCall("c4", "search_catalog", {"query": "navy shirt", "category": "shirts", "top_k": 3}),
                          FakeToolCall("c5", "no_such_tool", {})],
              finish="tool_calls"),
    _response(content="Verdict : à éviter, vous avez déjà une chemise oxford marine."),
]


def test_openai_tool_loop(client, wardrobe):
    import main

    llm, completions = fake_openai(list(AGENT_SCRIPT))
    steps = []
    result = llm.run_agent("Dois-je acheter une chemise oxford marine ?", wardrobe, main.state["engine"],
                           on_step=steps.append, image="aGVsbG8=")
    assert result["answer"].startswith("Verdict")
    assert [s["tool"] for s in result["steps"]] == ["get_wardrobe", "analyze_redundancy", "run_feature", "search_catalog"]
    assert steps == result["steps"] and result["usage"] == {"input_tokens": 300, "output_tokens": 60}

    analysis = json.loads(completions.requests[1]["messages"][4]["content"])  # tool result fed back to the model
    assert analysis["similar_owned_items"][0]["name"] == "Navy Oxford Shirt"
    feature = json.loads(completions.requests[2]["messages"][-3]["content"])
    assert "estimated_resale" in json.dumps(feature)  # flat item fields were wrapped into {"item": ...}
    assert "unknown tool" in completions.requests[2]["messages"][-1]["content"]  # the model is told, not crashed
    photo = completions.requests[0]["messages"][1]["content"][1]
    assert photo["type"] == "image_url" and photo["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert {t["function"]["name"] for t in completions.requests[0]["tools"]} >= {"analyze_redundancy", "run_feature"}


def test_openai_max_iterations():
    import main

    loop = [_response(tool_calls=[FakeToolCall(f"c{i}", "get_wardrobe", {})], finish="tool_calls") for i in range(3)]
    llm, _ = fake_openai(loop)
    result = llm.run_agent("boucle", [], main.state["engine"], max_iterations=3)
    assert result["answer"] == "Nombre maximal d'étapes atteint." and len(result["steps"]) == 3


def test_openai_explain_and_summarize():
    llm, completions = fake_openai([_response(content="  Explication courte.  "), _response(content="Résumé.")])
    result = {"redundancy_score": 72, "recommendation": "skip", "category_saturation": 60, "outfit_contribution": 20,
              "similar_items": [{"name": "Navy Oxford Shirt", "color": "navy", "similarity": 0.83}]}
    assert llm.explain("Navy shirt", result, language="French") == "Explication courte."
    assert "Navy Oxford Shirt" in completions.requests[0]["messages"][1]["content"]
    assert llm.summarize("À éviter", ["doublon"], ["garder l'argent"]) == "Résumé."


def test_openai_errors_pause_the_client():
    import httpx
    import openai

    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    auth_error = openai.AuthenticationError("bad key", response=httpx.Response(401, request=request), body=None)
    llm, _ = fake_openai([auth_error])
    assert llm.explain("x", {"redundancy_score": 1, "recommendation": "buy"}) is None
    assert not llm.available and "invalide" in llm.error


def test_agent_stream_uses_llm_then_falls_back(client):
    import main

    agent = main.state["agent"]
    saved = agent.llm
    try:
        agent.llm, _ = fake_openai(list(AGENT_SCRIPT) + [_response(content="Résumé final.")] * 3)
        events = [json.loads(line) for line in
                  client.post("/agent/run", json={"mission": "purchase", "message": "chemise oxford marine", "mode": "llm"}).text.splitlines()]
        assert events[0]["type"] == "start" and events[0]["mode"] == "openai"
        assert sum(e["type"] == "step" for e in events) >= 4
        assert events[-1]["type"] == "final"

        import httpx
        import openai

        boom = openai.APIConnectionError(request=httpx.Request("POST", "https://api.openai.com"))
        agent.llm, _ = fake_openai([boom, boom])  # the run fails, then the optional summary fails too
        events = [json.loads(line) for line in
                  client.post("/agent/run", json={"mission": "purchase", "message": "chemise bleue", "mode": "auto"}).text.splitlines()]
        assert any(e["type"] == "notice" for e in events)          # user is told the LLM failed
        assert events[-1]["type"] == "final"                        # ...and still gets the local planner's verdict
    finally:
        agent.llm = saved


@pytest.mark.parametrize("provider,expected", [("openai", "openai"), ("claude", "claude"), ("auto", "openai")])
def test_make_llm_client_provider(provider, expected):
    from openai_client import make_llm_client

    llm = make_llm_client(provider, "", "claude-opus-5-5", "sk-test", "gpt-4.1", "low", "medium", 1000, enabled=False)
    assert llm.provider == expected and not llm.available
