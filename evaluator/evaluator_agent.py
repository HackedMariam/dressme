"""Evaluator Agent (LangGraph) : évalue les autres agents de DressMe par leurs endpoints existants.

    START -> load_cases -> call_agents -> code_checks -> llm_judge -> aggregate -> report -> END

- load_cases   : lit evaluator/cases/*.yaml (filtré par --agents).
- call_agents  : un tour de conversation par pas de test, avec le jeton du compte de test ; mesure la latence ; suit les
                 modifications de la garde-robe et remet en état ce qu'un cas de correction confirmée a changé.
- code_checks  : contrat, ancrage, règles métier, citations, routage, robustesse, performance (voir checks.py).
- llm_judge    : pertinence et utilité (1 à 5) pour les seules réponses dont les contrôles du code sont tous passés.
                 Le juge ne peut pas contredire un échec du code ; une note < 3 ne fait qu'un avertissement de qualité.
- aggregate    : score par agent et par critère, taux de réussite, latence médiane, liste des échecs avec la raison.
- report       : rapport JSON + Markdown dans evaluator/reports/.

Contrat commun : l'agent répond completed (rapport produit), input-required (agents inconnus, configuration ou service
de référence manquant : il dit quoi fournir) ou failed (erreur interne, jamais de trace technique).
"""
from __future__ import annotations

import datetime
import json
import statistics
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from . import adapters, cases as cases_mod, checks, config, judge as judge_mod
from .adapters import AGENTS, Reply

JUDGE_MIN = 3        # note du juge sous laquelle la réponse est un avertissement de qualité


class EvalState(TypedDict, total=False):
    agents: list[str]
    use_judge: bool
    cases: list
    runs: list[dict]
    results: list[dict]
    summary: dict
    report_paths: dict
    trace: list[str]


class Deps:
    """Tout ce que le graphe appelle : facile à remplacer par un faux agent dans les tests."""

    def __init__(self, *, token: str, wardrobe: Callable[[], list[dict]], ask=adapters.ask, judge=judge_mod.judge,
                 diff=None, restore=None, foreign_probe=None, reports_dir: Path | None = None, cases_dir: Path | None = None):
        self.token, self.wardrobe, self.ask, self.judge = token, wardrobe, ask, judge
        self.diff, self.restore, self.foreign_probe = diff, restore, foreign_probe
        self.reports_dir, self.cases_dir = reports_dir or config.REPORTS_DIR, cases_dir


def _trace(state: EvalState, line: str) -> list[str]:
    return [*(state.get("trace") or []), line]


def build_graph(deps: Deps):
    def load_cases(state: EvalState) -> dict:
        selected = [a for a in state.get("agents") or []] or None
        loaded = cases_mod.load_cases(selected, deps.cases_dir)
        return {"cases": loaded, "trace": _trace(state, f"load_cases -> {len(loaded)} cas")}

    def call_agents(state: EvalState) -> dict:
        runs: list[dict] = []
        for case in state["cases"]:
            context_id: Optional[str] = None
            originals: dict[str, dict] = {}
            for number, step in enumerate(case.steps, 1):
                before = deps.wardrobe()
                reply = deps.ask(case.agent, deps.token, step.text, step.data, context_id, step.service_down)
                context_id = reply.context_id or context_id
                changed: dict[str, dict] = {}
                if case.watch_changes and deps.diff:
                    changed = deps.diff(before, deps.wardrobe())
                    for item_id, fields in changed.items():
                        originals.setdefault(item_id, fields)
                runs.append({"case": case, "step": number, "step_def": step, "reply": reply, "wardrobe": before,
                             "changed": changed})
            if originals and deps.restore:
                deps.restore(originals)
        return {"runs": runs, "trace": _trace(state, f"call_agents -> {len(runs)} appel(s)")}

    def code_checks(state: EvalState) -> dict:
        results = []
        for run in state["runs"]:
            ctx = checks.Ctx(wardrobe=run["wardrobe"], changed_ids=list(run["changed"]), foreign_probe=deps.foreign_probe)
            expect = {**run["step_def"].expect, "service_down": run["step_def"].service_down}
            found = checks.run_checks(run["case"].agent, expect, run["reply"], ctx)
            results.append({**run, "checks": found, "code_ok": all(c.passed for c in found), "judge": None,
                            "judge_note": ""})
        return {"results": results, "trace": _trace(state, f"code_checks -> {sum(not r['code_ok'] for r in results)} échec(s)")}

    def llm_judge(state: EvalState) -> dict:
        judged = 0
        for result in state["results"]:
            reply: Reply = result["reply"]
            if not state.get("use_judge", True):
                result["judge_note"] = "juge désactivé"
            elif not result["code_ok"]:
                result["judge_note"] = "non jugé : échec détecté par le code"
            elif reply.state == "failed" or not reply.text.strip():
                result["judge_note"] = "non jugé : pas de réponse à juger"
            else:
                verdict = deps.judge(result["step_def"].text or json.dumps(result["step_def"].data)[:300], reply.text,
                                     result["step_def"].judge)
                if verdict is None:
                    result["judge_note"] = "juge indisponible (Ollama) : non jugé"
                else:
                    result["judge"], judged = verdict, judged + 1
        return {"results": state["results"], "trace": _trace(state, f"llm_judge -> {judged} réponse(s) jugée(s)")}

    def aggregate(state: EvalState) -> dict:
        return {"summary": summarise(state["results"]), "trace": _trace(state, "aggregate")}

    def report(state: EvalState) -> dict:
        paths = write_reports(state["summary"], deps.reports_dir)
        return {"report_paths": paths, "trace": _trace(state, f"report -> {paths['json']}")}

    graph = StateGraph(EvalState)
    for name, node in (("load_cases", load_cases), ("call_agents", call_agents), ("code_checks", code_checks),
                       ("llm_judge", llm_judge), ("aggregate", aggregate), ("report", report)):
        graph.add_node(name, node)
    graph.add_edge(START, "load_cases")
    for first, second in (("load_cases", "call_agents"), ("call_agents", "code_checks"), ("code_checks", "llm_judge"),
                          ("llm_judge", "aggregate"), ("aggregate", "report")):
        graph.add_edge(first, second)
    graph.add_edge("report", END)
    return graph.compile()


# --------------------------------------------------------------------------------------------- agrégation
def step_status(result: dict) -> str:
    if not result["code_ok"]:
        return "FAIL"
    judge = result.get("judge")
    if judge and min(judge[k] for k in judge_mod.GRID) < JUDGE_MIN:
        return "WARN"
    return "PASS"


def summarise(results: list[dict]) -> dict:
    by_agent: dict[str, list[dict]] = {}
    for result in results:
        by_agent.setdefault(result["case"].agent, []).append(result)
    agents = {}
    failures = []
    for name, rows in by_agent.items():
        criteria: dict[str, dict] = {}
        for row in rows:
            for check in row["checks"]:
                slot = criteria.setdefault(check.criterion, {"passed": 0, "total": 0})
                slot["total"] += 1
                slot["passed"] += int(check.passed)
        for slot in criteria.values():
            slot["score"] = round(100 * slot["passed"] / slot["total"], 1)
        judged = [r["judge"] for r in rows if r.get("judge")]
        statuses = [step_status(r) for r in rows]
        latencies = [r["reply"].latency_ms / 1000 for r in rows if r["reply"].http_status is not None]
        agents[name] = {
            "label": AGENTS[name].label, "steps": len(rows), "pass": statuses.count("PASS"), "warn": statuses.count("WARN"),
            "fail": statuses.count("FAIL"),
            "success_rate": round(100 * statuses.count("PASS") / len(rows), 1),
            "code_success_rate": round(100 * sum(r["code_ok"] for r in rows) / len(rows), 1),
            "criteria": criteria,
            "median_latency_s": round(statistics.median(latencies), 2) if latencies else None,
            "judge": ({k: round(statistics.mean(j[k] for j in judged), 2) for k in judge_mod.GRID} | {"n": len(judged)}) if judged else None,
        }
        for row in rows:
            label = f"{row['case'].id}#{row['step']}"
            for check in row["checks"]:
                if not check.passed:
                    failures.append({"agent": name, "case": label, "criterion": check.criterion, "check": check.name,
                                     "reason": check.reason or "échec", "state": row["reply"].state,
                                     "excerpt": row["reply"].text[:200]})
            if step_status(row) == "WARN":
                failures.append({"agent": name, "case": label, "criterion": "judge", "check": "pertinence / utilité < 3",
                                 "reason": row["judge"]["justification"], "state": row["reply"].state,
                                 "excerpt": row["reply"].text[:200]})
    total = len(results)
    all_status = [step_status(r) for r in results]
    return {"generated_at": datetime.datetime.now().isoformat(timespec="seconds"), "agents": agents,
            "overall": {"steps": total, "pass": all_status.count("PASS"), "warn": all_status.count("WARN"),
                        "fail": all_status.count("FAIL"),
                        "success_rate": round(100 * all_status.count("PASS") / total, 1) if total else 0.0},
            "failures": failures,
            "rule": "FAIL = un contrôle du code échoue (le juge ne peut pas l'effacer) ; WARN = code OK mais note du juge < 3 ; "
                    "taux de réussite = PASS / pas de test"}


# --------------------------------------------------------------------------------------------- rapports
def markdown(summary: dict) -> str:
    lines = ["# Évaluation des agents DressMe", "", f"Généré le {summary['generated_at']}.", "",
             f"**Global : {summary['overall']['success_rate']} % de réussite** "
             f"({summary['overall']['pass']} PASS, {summary['overall']['warn']} WARN, {summary['overall']['fail']} FAIL "
             f"sur {summary['overall']['steps']} pas de test).", "", f"> {summary['rule']}", "",
             "## Score par agent", "",
             "| Agent | Pas | Réussite | " + " | ".join(checks.CRITERIA) + " | Latence méd. (s) | Juge pert./util. |",
             "|---|---:|---:|" + "---:|" * len(checks.CRITERIA) + "---:|---:|"]
    for name, agent in summary["agents"].items():
        cells = [f"{agent['criteria'][c]['score']} %" if c in agent["criteria"] else "—" for c in checks.CRITERIA]
        judge = f"{agent['judge']['relevance']} / {agent['judge']['usefulness']} (n={agent['judge']['n']})" if agent["judge"] else "—"
        latency = agent["median_latency_s"] if agent["median_latency_s"] is not None else "—"
        lines.append(f"| {agent['label']} (`{name}`) | {agent['steps']} | {agent['success_rate']} % | " + " | ".join(cells)
                     + f" | {latency} | {judge} |")
    lines += ["", "## Échecs et avertissements", ""]
    if not summary["failures"]:
        lines.append("Aucun.")
    for failure in summary["failures"]:
        lines.append(f"- **{failure['agent']} / {failure['case']}** [{failure['criterion']}] {failure['check']} : {failure['reason']}")
    return "\n".join(lines) + "\n"


def write_reports(summary: dict, directory: Path) -> dict:
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    paths = {"json": directory / f"eval-{stamp}.json", "markdown": directory / f"eval-{stamp}.md"}
    paths["json"].write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    paths["markdown"].write_text(markdown(summary), encoding="utf-8")
    return {k: str(v) for k, v in paths.items()}


# --------------------------------------------------------------------------------------------- contrat commun
def run(agents: list[str] | None = None, *, use_judge: bool = True, env_file: str | None = None,
        deps: Deps | None = None, seed_shoes: bool = False) -> dict:
    """Lance l'évaluation. Renvoie {"state": completed | input-required | failed, "message", "summary", "report_paths"}."""
    wanted = [a.strip() for a in agents or [] if a.strip()]
    if not wanted or wanted == ["all"]:
        wanted = list(AGENTS)
    unknown = [a for a in wanted if a not in AGENTS]
    if unknown:
        return {"state": "input-required", "message": "Agents inconnus : " + ", ".join(unknown) + ". Disponibles : "
                + ", ".join(AGENTS) + ", all."}
    try:
        if deps is None:
            from .session import Session

            session = Session(config.load_credentials(env_file))
            deps = Deps(token=session.token, wardrobe=session.wardrobe, diff=session.diff, restore=session.restore,
                        foreign_probe=session.foreign_probe)
        else:
            session = None
    except RuntimeError as error:                    # configuration absente, compte refusé, BO1 arrêté
        return {"state": "input-required", "message": str(error)}
    try:
        if session is not None and seed_shoes:
            session.seed_shoes()
        final = build_graph(deps).invoke({"agents": wanted, "use_judge": use_judge})
    except cases_mod.CaseError as error:
        return {"state": "failed", "message": f"jeu de test invalide : {error}"}
    except Exception as error:                       # noqa: BLE001 - jamais de trace technique vers l'appelant
        return {"state": "failed", "message": f"évaluation interrompue ({type(error).__name__})"}
    finally:
        if session is not None:
            session.clear_orchestrator_history()
            if seed_shoes:
                session.unseed_shoes()
    return {"state": "completed", "message": "évaluation terminée", "summary": final["summary"],
            "report_paths": final["report_paths"]}
