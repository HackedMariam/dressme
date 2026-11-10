"""Tests de l'évaluateur lui-même : des FAUX agents (aucun service, aucun LLM) pour prouver que les contrôles du code
détectent bien ce qu'ils doivent détecter, et que le juge ne peut pas effacer un échec."""
from __future__ import annotations

import json

import pytest

from evaluator import cases as cases_mod
from evaluator import checks, evaluator_agent, judge as judge_mod
from evaluator.adapters import AGENTS, Reply
from evaluator.checks import Ctx, run_checks
from evaluator.evaluator_agent import Deps

WARDROBE = [
    {"id": "t1", "name": "White Cotton Shirt", "category": "top", "group": "Tops"},
    {"id": "b1", "name": "Black Tailored Trousers", "category": "pants", "group": "Bottoms"},
    {"id": "d1", "name": "Grey Wrap Dress", "category": "dress", "group": "Dresses"},
    {"id": "s1", "name": "Black Leather Oxford Shoes", "category": "shoe", "group": "Shoes"},
    {"id": "j1", "name": "Olive Military Jacket", "category": "jacket", "group": "Outerwear"},
    {"id": "m1", "name": "Plaid Wool Mini Skirt", "category": "skirt", "group": "Bottoms", "subcategory": "mini skirt"},
    {"id": "o1", "name": "Beige Off-Shoulder Sweater", "category": "sweater", "group": "Tops", "subcategory": "off-shoulder sweater"},
]


def ids(*values):
    return [{"id": v} for v in values]


def outfit_reply(*outfits, weather=None, state="completed", text="ok"):
    data = {"outfits": [{"title": f"Tenue {n}", "items": o} for n, o in enumerate(outfits, 1)]}
    if weather:
        data["weather"] = weather
    return Reply(state=state, text=text, data=data, latency_ms=1200, http_status=200)


def failed(results):
    return [r for r in results if not r.passed]


def criteria_failed(results):
    return {r.criterion for r in failed(results)}


@pytest.fixture
def ctx():
    return Ctx(wardrobe=WARDROBE)


# ------------------------------------------------------------------------------------------- ancrage
def test_invented_item_id_fails(ctx):
    reply = outfit_reply(ids("t1", "b1", "s1") + [{"id": "zzz-inventé", "name": "Veste imaginaire"}])
    results = run_checks("outfit", {"state": "completed"}, reply, ctx)
    assert "grounding" in criteria_failed(results)
    assert any("inventée ou d'une autre utilisatrice" in r.reason for r in failed(results))


def test_item_of_another_user_is_reported_as_isolation_leak():
    context = Ctx(wardrobe=WARDROBE, foreign_probe=lambda item_id: 200)
    results = run_checks("outfit", {}, outfit_reply(ids("t1", "autre-utilisatrice")), context)
    assert any("fuite d'isolation" in r.reason for r in failed(results))


def test_real_item_ids_pass_grounding(ctx):
    results = run_checks("outfit", {"state": "completed"}, outfit_reply(ids("t1", "b1", "s1")), ctx)
    assert "grounding" not in criteria_failed(results)


# ------------------------------------------------------------------------------------------- règles métier
def test_outfit_without_shoes_fails(ctx):
    results = run_checks("outfit", {"rules": ["complete_outfit"]}, outfit_reply(ids("t1", "b1")), ctx)
    assert any("pas de chaussures" in r.reason for r in failed(results))


def test_outfit_with_top_bottom_shoes_passes(ctx):
    results = run_checks("outfit", {"rules": ["complete_outfit"]}, outfit_reply(ids("t1", "b1", "s1")), ctx)
    assert not failed(results)


def test_dress_alone_with_shoes_is_complete(ctx):
    assert not failed(run_checks("outfit", {"rules": ["complete_outfit"]}, outfit_reply(ids("d1", "s1")), ctx))


def test_top_without_bottom_fails(ctx):
    results = run_checks("outfit", {"rules": ["complete_outfit"]}, outfit_reply(ids("t1", "s1")), ctx)
    assert any("ni robe, ni haut + bas" in r.reason for r in failed(results))


def test_cold_weather_requires_a_layer(ctx):
    cold = {"temp_max": 8, "unit": "C"}
    results = run_checks("outfit", {"rules": ["complete_outfit"]}, outfit_reply(ids("t1", "b1", "s1"), weather=cold), ctx)
    assert any("couche supplémentaire" in r.reason for r in failed(results))
    with_jacket = outfit_reply(ids("t1", "b1", "s1", "j1"), weather=cold)
    assert not failed(run_checks("outfit", {"rules": ["complete_outfit"]}, with_jacket, ctx))


def test_fahrenheit_is_converted_before_judging_the_cold(ctx):
    mild = {"temp_max": 77, "unit": "F"}                                  # 25 °C : pas de couche exigée
    assert not failed(run_checks("outfit", {"rules": ["complete_outfit"]}, outfit_reply(ids("t1", "b1", "s1"), weather=mild), ctx))


def test_rain_requires_a_layer_even_when_mild(ctx):
    results = run_checks("bo4", {"rules": ["complete_outfit"], "rain": True}, outfit_reply(ids("t1", "b1", "s1")), ctx)
    assert any("couche supplémentaire" in r.reason for r in failed(results))


def test_mini_skirt_and_bare_shoulders_fail_the_business_dress_code(ctx):
    bad = outfit_reply(ids("t1", "m1", "s1"), ids("o1", "b1", "s1"), ids("t1", "b1", "s1"))
    results = [r for r in run_checks("bo4", {"rules": ["dress_code_business"]}, bad, ctx) if r.criterion == "rules"]
    assert [r.passed for r in results] == [False, False, True]
    assert "Plaid Wool Mini Skirt" in results[0].reason and "Off-Shoulder" in results[1].reason


def test_stylist_flat_item_list_counts_as_one_outfit(ctx):
    reply = Reply(state="completed", text="Voici ta tenue", data={"items": ids("t1", "m1", "s1")}, latency_ms=900, http_status=200)
    assert failed(run_checks("stylist", {"rules": ["dress_code_business"]}, reply, ctx))


def test_wardrobe_change_without_confirmation_fails():
    reply = Reply(state="completed", text="Fait.", data={"updated": True}, latency_ms=800, http_status=200)
    results = run_checks("wardrobe", {"rules": ["no_change_without_confirmation"]}, reply, Ctx(WARDROBE, changed_ids=["t1"]))
    assert any("avant toute confirmation" in r.reason for r in failed(results))


def test_wardrobe_proposal_without_change_passes():
    reply = Reply(state="input-required", text="Je change la couleur, tu confirmes ?", data={"pending": {"id": "b1"}},
                  latency_ms=800, http_status=200)
    assert not failed(run_checks("wardrobe", {"state": "input-required", "rules": ["no_change_without_confirmation"]},
                                 reply, Ctx(WARDROBE)))


def test_trip_silently_relaxing_a_constraint_fails():
    silent = Reply(state="completed", text="Voici ta valise de 14 jours : 6 pièces.", data={"status": "success"},
                   latency_ms=2000, http_status=200)
    explicit = Reply(state="completed", text="Impossible avec 2 pièces : voici des alternatives.", data={}, latency_ms=2000,
                     http_status=200)
    assert failed(run_checks("trip", {"rules": ["trip_constraints"]}, silent, Ctx()))
    assert not failed(run_checks("trip", {"rules": ["trip_constraints"]}, explicit, Ctx()))


def test_refusal_rule_requires_dont_know_and_no_invented_sources():
    refusal = Reply(state="completed", text="I don't know: no source covers next year's trends.", data={"sources": []},
                    latency_ms=3000, http_status=200)
    invented = Reply(state="completed", text="Next year: neon [S1].", data={"sources": [{"title": "x"}]}, latency_ms=3000,
                     http_status=200)
    assert not failed(run_checks("rag", {"rules": ["refuses"]}, refusal, Ctx()))
    assert failed(run_checks("rag", {"rules": ["refuses"]}, invented, Ctx()))


# ------------------------------------------------------------------------------------------- citations
def rag_reply(text, sources):
    return Reply(state="completed", text=text, data={"sources": sources, "citations": [{"marker": f"S{n}"} for n in range(1, len(sources) + 1)]},
                 latency_ms=3000, http_status=200)


def test_citation_s9_absent_from_the_sources_fails():
    reply = rag_reply("Wash wool by hand [S1]. Lay flat [S9].", [{"title": "a"}, {"title": "b"}])
    results = run_checks("rag", {}, reply, Ctx())
    assert "citations" in criteria_failed(results)
    assert any("[S9]" in r.reason for r in failed(results))


def test_citations_matching_the_sources_pass():
    reply = rag_reply("Wash wool by hand [S1]. Lay flat [S2].", [{"title": "a"}, {"title": "b"}])
    assert "citations" not in criteria_failed(run_checks("rag", {}, reply, Ctx()))


def test_markers_come_from_the_citations_list_when_present():
    reply = Reply(state="completed", text="Tip [S3].", data={"sources": [{"title": "a"}], "citations": [{"marker": "S3"}]},
                  latency_ms=1000, http_status=200)
    assert "citations" not in criteria_failed(run_checks("rag", {}, reply, Ctx()))


# ------------------------------------------------------------------------------------------- contrat, routage, robustesse
def test_state_outside_the_contract_fails():
    reply = Reply(state="working", text="...", latency_ms=10, http_status=200)
    assert "contract" in criteria_failed(run_checks("stylist", {}, reply, Ctx()))


def test_expected_state_can_be_a_list():
    reply = Reply(state="input-required", text="Où vas-tu ?", latency_ms=10, http_status=200)
    assert not failed(run_checks("trip", {"state": ["completed", "input-required"]}, reply, Ctx()))


def test_required_field_missing_fails():
    reply = Reply(state="completed", text="ok", data={}, latency_ms=10, http_status=200)
    assert any("champ obligatoire" in r.reason for r in failed(run_checks("outfit", {"required_fields": ["outfits"]}, reply, Ctx())))


def test_wrong_route_fails():
    reply = Reply(state="completed", text="ok", latency_ms=10, http_status=200, route="outfit")
    results = run_checks("orchestrator_bo1", {"route": "stylist"}, reply, Ctx())
    assert criteria_failed(results) == {"routing"} and "outfit" in failed(results)[0].reason


def test_http_500_fails_robustness_and_a_stopped_service_must_say_failed():
    crashed = Reply(state="failed", text="Internal Server Error", latency_ms=10, http_status=500)
    assert "robustness" in criteria_failed(run_checks("stylist", {"service_down": True}, crashed, Ctx()))
    clean = Reply(state="failed", text="", latency_ms=10, http_status=None, error="injoignable")
    assert not failed(run_checks("stylist", {"state": "failed", "service_down": True}, clean, Ctx()))


def test_a_stopped_service_that_pretends_to_complete_fails():
    pretend = Reply(state="completed", text="Voici ma réponse", latency_ms=10, http_status=200)
    assert "robustness" in criteria_failed(run_checks("stylist", {"service_down": True}, pretend, Ctx()))


def test_slow_answer_fails_performance():
    slow = Reply(state="completed", text="ok", latency_ms=99_000, http_status=200)
    assert "performance" in criteria_failed(run_checks("stylist", {}, slow, Ctx()))
    assert "performance" in criteria_failed(run_checks("similar", {}, Reply(state="completed", text="ok", latency_ms=20_000, http_status=200), Ctx()))


# ------------------------------------------------------------------------------------------- juge
def test_judge_parse_accepts_only_a_valid_grid():
    good = judge_mod.parse(json.dumps({"relevance": 4, "usefulness": "5", "justification": "clair"}))
    assert good == {"relevance": 4, "usefulness": 5, "justification": "clair"}
    assert judge_mod.parse(json.dumps({"relevance": 9, "usefulness": 2})) is None
    assert judge_mod.parse(json.dumps({"relevance": 3})) is None
    assert judge_mod.parse("pas du json") is None


def make_graph(tmp_path, ask, judge, wardrobe=WARDROBE):
    cases_dir = tmp_path / "cases"
    cases_dir.mkdir(exist_ok=True)
    (cases_dir / "outfit.yaml").write_text(
        "agent: outfit\ncases:\n  - id: c1\n    steps:\n      - input: {text: build, data: {occasion: work}}\n"
        "        expect: {state: completed, rules: [complete_outfit]}\n        judge: tenue pro\n", encoding="utf-8")
    deps = Deps(token="faux", wardrobe=lambda: wardrobe, ask=ask, judge=judge, reports_dir=tmp_path / "reports", cases_dir=cases_dir)
    return evaluator_agent.build_graph(deps)


def test_judge_cannot_overturn_a_code_failure(tmp_path):
    """Le faux agent invente un item_id ; le juge enthousiaste (5/5) ne doit pas sauver le cas, ni même être appelé."""
    called = []
    ask = lambda *a, **k: outfit_reply(ids("t1", "b1", "s1", "inventé"))
    judge = lambda *a, **k: called.append(1) or {"relevance": 5, "usefulness": 5, "justification": "super"}
    final = make_graph(tmp_path, ask, judge).invoke({"agents": ["outfit"], "use_judge": True})
    result = final["results"][0]
    assert not result["code_ok"] and evaluator_agent.step_status(result) == "FAIL"
    assert not called and "échec détecté par le code" in result["judge_note"]
    assert final["summary"]["agents"]["outfit"]["success_rate"] == 0.0


def test_judge_low_score_is_only_a_warning(tmp_path):
    ask = lambda *a, **k: outfit_reply(ids("t1", "b1", "s1"))
    judge = lambda *a, **k: {"relevance": 2, "usefulness": 2, "justification": "hors sujet"}
    final = make_graph(tmp_path, ask, judge).invoke({"agents": ["outfit"], "use_judge": True})
    result = final["results"][0]
    assert result["code_ok"] and evaluator_agent.step_status(result) == "WARN"
    assert final["summary"]["agents"]["outfit"]["code_success_rate"] == 100.0
    assert any(f["criterion"] == "judge" for f in final["summary"]["failures"])


def test_graph_produces_json_and_markdown_reports(tmp_path):
    ask = lambda *a, **k: outfit_reply(ids("t1", "b1", "s1"))
    judge = lambda *a, **k: {"relevance": 5, "usefulness": 4, "justification": "bien"}
    final = make_graph(tmp_path, ask, judge).invoke({"agents": ["outfit"], "use_judge": True})
    paths = final["report_paths"]
    report = json.loads(open(paths["json"], encoding="utf-8").read())
    assert report["agents"]["outfit"]["success_rate"] == 100.0 and report["agents"]["outfit"]["judge"]["relevance"] == 5
    markdown = open(paths["markdown"], encoding="utf-8").read()
    assert "Score par agent" in markdown and "outfit" in markdown
    assert [line.split(" ->")[0] for line in final["trace"]] == ["load_cases", "call_agents", "code_checks", "llm_judge", "aggregate", "report"]


def test_judge_unavailable_means_not_judged_never_an_invented_score(tmp_path):
    ask = lambda *a, **k: outfit_reply(ids("t1", "b1", "s1"))
    final = make_graph(tmp_path, ask, lambda *a, **k: None).invoke({"agents": ["outfit"], "use_judge": True})
    assert final["results"][0]["judge"] is None and "indisponible" in final["results"][0]["judge_note"]
    assert final["summary"]["agents"]["outfit"]["judge"] is None


def test_confirmed_correction_is_restored(tmp_path):
    """Un cas qui modifie la garde-robe : l'évaluateur remet les champs d'origine (pas de pollution du compte de test)."""
    state = {"wardrobe": [dict(i) for i in WARDROBE]}
    restored = {}

    def ask(*a, **k):
        state["wardrobe"][1]["color_name"] = "navy"                      # le faux agent modifie une pièce
        return Reply(state="completed", text="Changé.", data={"updated": True}, latency_ms=50, http_status=200)

    def diff(before, after):
        return {i["id"]: {"color_name": None} for i, j in zip(before, after) if i.get("color_name") != j.get("color_name")}

    cases_dir = tmp_path / "cases"
    cases_dir.mkdir()
    (cases_dir / "wardrobe.yaml").write_text("agent: wardrobe\ncases:\n  - id: w1\n    watch_changes: true\n    steps:\n"
                                             "      - input: {text: change}\n        expect: {state: completed}\n", encoding="utf-8")
    deps = Deps(token="faux", wardrobe=lambda: [dict(i) for i in state["wardrobe"]], ask=ask, judge=lambda *a, **k: None, diff=diff,
                restore=lambda originals: restored.update(originals), reports_dir=tmp_path / "r", cases_dir=cases_dir)
    evaluator_agent.build_graph(deps).invoke({"agents": ["wardrobe"], "use_judge": False})
    assert list(restored) == ["b1"]


# ------------------------------------------------------------------------------------------- jeu de test et contrat
def test_every_case_file_loads_and_covers_each_agent_in_fr_and_en():
    loaded = cases_mod.load_cases()
    for name in AGENTS:
        mine = [c for c in loaded if c.agent == name]
        assert 5 <= len(mine) <= 10, f"{name} : {len(mine)} cas"
        assert {"fr", "en"} <= {c.lang for c in mine}, f"{name} : FR et EN attendus"
        assert any(s.service_down for c in mine for s in c.steps), f"{name} : un cas « service arrêté » attendu"


def test_required_scenarios_are_present():
    texts = " ".join(s.text.lower() for c in cases_mod.load_cases() for s in c.steps)
    for fragment in ("entretien", "black tie", "pleut", "black skirt", "couleur", "valise", "winter work", "blazer", "tendances"):
        assert fragment in texts, fragment


def test_every_rule_named_in_the_cases_exists():
    used = {r for c in cases_mod.load_cases() for s in c.steps for r in s.expect.get("rules", [])}
    assert used <= set(checks.RULES), used - set(checks.RULES)


def test_unknown_agent_asks_for_input_instead_of_failing():
    outcome = evaluator_agent.run(["stylist", "inconnu"])
    assert outcome["state"] == "input-required" and "inconnu" in outcome["message"]


def test_missing_credentials_is_input_required_without_leaking_values(monkeypatch):
    from evaluator import config

    monkeypatch.setattr(config, "load_credentials", lambda env_file=None: (_ for _ in ()).throw(RuntimeError("configuration incomplète : TEST_EMAIL")))
    outcome = evaluator_agent.run(["stylist"])
    assert outcome["state"] == "input-required" and "TEST_EMAIL" in outcome["message"]
