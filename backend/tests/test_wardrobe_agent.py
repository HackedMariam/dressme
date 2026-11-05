"""The Wardrobe Agent (LangGraph) and the shared tool loop. The LLM is replaced by a fake."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent_kit import run_loop  # noqa: E402
from app import config, wardrobe_agent  # noqa: E402

ITEMS = [
    {"id": "a", "name": "Navy Blazer", "category": "jacket", "category_group": "Outerwear", "color_name": "navy",
     "color_family": "cool", "material": "wool", "style": "classic", "occasions": ["work"], "seasons": ["autumn"], "warmth": 3},
    {"id": "b", "name": "Grey Skirt", "category": "skirt", "category_group": "Bottoms", "color_name": "grey",
     "color_family": "neutral", "occasions": ["work"], "seasons": ["autumn"], "needs_review": True},
    {"id": "c", "name": "Charcoal Blazer", "category": "jacket", "category_group": "Outerwear", "color_name": "charcoal",
     "color_family": "neutral", "material": "wool", "style": "classic", "occasions": ["work"], "seasons": ["winter"]},
]


def tool_call(call_id, name, **arguments):
    function = SimpleNamespace(name=name, arguments=json.dumps(arguments))
    call = SimpleNamespace(id=call_id, function=function)
    call.model_dump = lambda: {"id": call_id, "type": "function", "function": {"name": name, "arguments": function.arguments}}
    return call


def message(content=None, tool_calls=None):
    return SimpleNamespace(content=content, tool_calls=tool_calls)


class FakeLLM:
    def __init__(self, script):
        self.script, self.calls = list(script), []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=self.script.pop(0))])


@pytest.fixture
def agent(monkeypatch):
    applied = []

    def validate(fields):
        if "category" in fields and fields["category"] not in ("jacket", "skirt"):
            raise ValueError("Unknown category")
        return fields

    def apply(user_id, item_id, fields):
        applied.append((user_id, item_id, fields))
        return {**next(i for i in ITEMS if i["id"] == item_id), **fields}

    monkeypatch.setattr(wardrobe_agent, "list_items", lambda user_id: ITEMS)
    monkeypatch.setattr(wardrobe_agent._ctx, "validate_patch", validate)
    monkeypatch.setattr(wardrobe_agent._ctx, "apply_patch", apply)
    monkeypatch.setattr(config, "OPENAI_API_KEY", "test")
    monkeypatch.setattr(wardrobe_agent, "_GRAPH", None)

    def install(script):
        llm = FakeLLM(script)
        monkeypatch.setattr("openai.OpenAI", lambda **kwargs: llm)
        return llm

    return install, applied


# ------------------------------------------------------------------------------------------------ the shared loop
def test_the_tool_loop_runs_tools_nudges_once_and_reports_how_it_ended():
    script = [message(tool_calls=[tool_call("1", "ping", x=1)]), message("first answer"), message("second answer")]
    seen = []

    def call_llm(messages):
        seen.append(len(messages))
        return script.pop(0)

    final, outcome = run_loop(messages=[{"role": "user", "content": "hi"}], call_llm=call_llm,
                              run_tool=lambda name, args: json.dumps({"pong": args["x"]}), max_rounds=5,
                              nudge=lambda content: "Look again." if content == "first answer" else None)
    assert (final, outcome) == ("second answer", "answer")
    assert seen == [1, 3, 5]                               # the nudge was added once, after the first answer


def test_the_tool_loop_gives_up_cleanly():
    always_tools = lambda messages: message(tool_calls=[tool_call("1", "ping")])
    assert run_loop(messages=[], call_llm=always_tools, run_tool=lambda n, a: "{}", max_rounds=3)[1] == "exhausted"

    def boom(messages):
        raise RuntimeError("down")
    assert run_loop(messages=[], call_llm=boom, run_tool=lambda n, a: "{}", max_rounds=3) == (None, "error")


# ------------------------------------------------------------------------------------------------ reading
def test_a_search_request_returns_the_pieces_the_llm_found_and_the_filters_it_chose(agent):
    install, _ = agent
    llm = install([message(tool_calls=[tool_call("1", "search_wardrobe", category="jacket", occasion="work")]),
                   message("You own two blazers for work.")])
    reply = wardrobe_agent.converse("u1", "Which jackets can I wear to work?")
    assert reply["reply"] == "You own two blazers for work." and reply["state"] == "completed"
    assert [i["id"] for i in reply["items"]] == ["a", "c"]
    assert reply["filters"] == [{"category": "jacket", "occasion": "work"}] and reply["pending"] is None
    assert {t["function"]["name"] for t in llm.calls[0]["tools"]} == {"search_wardrobe", "find_similar", "wardrobe_stats", "update_item"}


def test_stats_and_similar_pieces_are_computed_by_code():
    counts = wardrobe_agent.stats(ITEMS)
    assert counts["total"] == 3 and counts["by_category"] == {"jacket": 2, "skirt": 1} and counts["needs_review"] == 1
    close = wardrobe_agent.similar(ITEMS, {"item_id": "a"})
    assert [row["id"] for row in close] == ["c"] and "same type" in close[0]["why"]
    assert wardrobe_agent.similar(ITEMS, {"category": "skirt", "color_name": "grey"})[0]["id"] == "b"


# ------------------------------------------------------------------------------------------------ writing needs a yes
def propose(install):
    return install([message(tool_calls=[tool_call("1", "search_wardrobe", text="grey")]),
                    message(tool_calls=[tool_call("2", "update_item", item_id="b", fields={"color_name": "navy"})]),
                    message("I can change the colour of Grey Skirt from grey to navy. Do you confirm?")])


def test_a_correction_is_only_proposed_and_nothing_is_saved_before_the_user_confirms(agent):
    install, applied = agent
    propose(install)
    reply = wardrobe_agent.converse("u1", "My grey skirt is navy, fix it", context_id="conv-1")
    assert reply["state"] == "input-required" and reply["context_id"] == "conv-1"
    assert reply["pending"] == {"item_id": "b", "item_name": "Grey Skirt", "fields": {"color_name": "navy"},
                                "before": {"color_name": "grey"}}
    assert applied == []                                                     # not written


@pytest.mark.parametrize("answer, kwargs", [("yes", {}), ("Oui", {}), ("anything", {"confirm": True})])
def test_the_change_is_written_only_after_a_yes_in_the_same_conversation(agent, answer, kwargs):
    install, applied = agent
    propose(install)
    wardrobe_agent.converse("u1", "fix my grey skirt", context_id="conv-2")
    reply = wardrobe_agent.converse("u1", answer, context_id="conv-2", **kwargs)
    assert applied == [("u1", "b", {"color_name": "navy"})]
    assert reply["state"] == "completed" and reply["reply"].startswith("Done.") and reply["updated"]["color_name"] == "navy"
    wardrobe_agent.converse("u1", "yes", context_id="conv-2")                   # the proposal is spent: nothing more is written
    assert len(applied) == 1


def test_no_or_a_different_request_or_another_user_never_writes(agent):
    install, applied = agent
    propose(install)
    wardrobe_agent.converse("u1", "fix my grey skirt", context_id="conv-3")
    assert wardrobe_agent.converse("u1", "no", context_id="conv-3")["reply"] == "Okay, nothing was changed."
    wardrobe_agent.converse("u1", "yes", context_id="conv-3")                    # too late: the "no" cancelled it
    assert applied == []

    propose(install)
    wardrobe_agent.converse("u1", "fix my grey skirt", context_id="conv-4")
    assert wardrobe_agent.converse("u2", "yes", context_id="conv-4")["reply"].startswith("Done.") is False    # other user
    install([message("You own 3 pieces.")])
    wardrobe_agent.converse("u1", "How many pieces do I own?", context_id="conv-4")                          # new request
    assert wardrobe_agent.pending.get("u1", "conv-4") is None and applied == []


def test_an_unknown_piece_a_forbidden_field_or_an_invalid_value_is_refused_to_the_llm(agent):
    install, applied = agent
    llm = install([message(tool_calls=[tool_call("1", "update_item", item_id="zzz", fields={"color_name": "navy"}),
                                       tool_call("2", "update_item", item_id="b", fields={"user_id": "evil"}),
                                       tool_call("3", "update_item", item_id="b", fields={"category": "spaceship"})]),
                   message("I could not prepare that change.")])
    reply = wardrobe_agent.converse("u1", "change things", context_id="conv-5")
    tool_results = [m["content"] for m in llm.calls[1]["messages"] if m["role"] == "tool"]
    assert all("error" in json.loads(content) for content in tool_results) and len(tool_results) == 3
    assert reply["pending"] is None and applied == []


def test_the_duplicate_check_of_the_live_scan_uses_the_search_tool_and_answers_in_json(agent):
    install, _ = agent
    install([message(tool_calls=[tool_call("1", "search_wardrobe", category="jacket", color_name="navy")]),
             message(json.dumps({"duplicate": True, "similar_item_id": "a", "note": "Same blazer scanned twice."}))])
    verdict = wardrobe_agent.check_duplicate(ITEMS, {"category": "jacket", "color_name": "navy"})
    assert verdict == {"duplicate": True, "similar_item_id": "a", "note": "Same blazer scanned twice."}
    assert wardrobe_agent.check_duplicate([], {"category": "jacket"})["duplicate"] is False


def test_an_empty_request_asks_what_to_do_and_a_failing_llm_is_reported(agent, monkeypatch):
    install, _ = agent
    assert wardrobe_agent.converse("u1", "")["state"] == "input-required"

    def boom(**kwargs):
        raise RuntimeError("down")

    llm = install([])
    monkeypatch.setattr(llm.chat.completions, "create", boom)
    assert wardrobe_agent.converse("u1", "show my jackets")["state"] == "failed"
