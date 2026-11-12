import json

from agent_eval.judge import judge_case, parse_verdict
from agent_eval.rubrics import RUBRICS
from agent_eval.run_eval import evaluate, load_cases, summarize


def fake(score_by_criterion=None, default=5):
    def complete(messages):
        agent = messages[1]["content"].split("\n")[0].split()[1]
        scores = {c.name: {"score": (score_by_criterion or {}).get(c.name, default), "evidence": "x"} for c in RUBRICS[agent].criteria}
        return json.dumps({"scores": scores, "summary": "ok"})
    return complete


CASE = {"id": "t", "input": "a warm jacket", "context": {"wardrobe": []}, "output": "Wear the grey coat."}


def test_pass_and_average():
    r = judge_case("stylist", CASE, fake())
    assert r["passed"] and r["average"] == 5


def test_hard_criterion_fails_even_with_high_average():
    r = judge_case("stylist", CASE, fake({"grounded": 1}))
    assert not r["passed"] and r["failed_hard"] == ["grounded"] and r["average"] >= 3.5


def test_low_average_fails():
    assert not judge_case("outfit", CASE, fake(default=2))["passed"]


def test_invalid_judge_output_is_an_error_not_a_pass():
    r = judge_case("rag", CASE, lambda m: "not json")
    assert r["passed"] is False and "error" in r


def test_parse_rejects_out_of_range_and_missing():
    rubric = RUBRICS["gap"]
    assert parse_verdict('{"scores": {"gap_relevance": 9}}', rubric) is None
    assert parse_verdict("", rubric) is None


def test_every_agent_has_cases_and_they_are_valid():
    for agent in RUBRICS:
        cases = load_cases(agent)
        assert cases, agent
        assert all("id" in c and "input" in c for c in cases)


def test_evaluate_all_recorded_cases_and_summary():
    results = evaluate(list(RUBRICS), fake())
    summary = summarize(results)
    assert set(summary) == set(RUBRICS)
    assert all(not r.get("error") for r in results)


def test_case_without_output_is_skipped_offline(tmp_path):
    (tmp_path / "gap.jsonl").write_text(json.dumps({"id": "a", "input": "x"}) + "\n", encoding="utf-8")
    assert evaluate(["gap"], fake(), directory=tmp_path)[0]["skipped"]
