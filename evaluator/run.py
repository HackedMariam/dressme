"""Lancement en ligne de commande.

    python -m evaluator.run --agents all
    python -m evaluator.run --agents stylist,outfit --no-judge
    python -m evaluator.run --list

Prérequis : les services à évaluer démarrés (start_all.ps1) ; identifiants du compte de test dans
orchestrator/.env.test (TEST_EMAIL, TEST_PASSWORD) et SUPABASE_URL / SUPABASE_ANON_KEY dans orchestrator/.env
(ou --env-file). Aucun secret n'est affiché. Code de sortie : 0 si aucun FAIL, 1 sinon, 2 si la configuration manque.
"""
from __future__ import annotations

import argparse
import sys

from . import evaluator_agent
from .adapters import AGENTS
from .cases import load_cases


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="python -m evaluator.run", description="Evaluator Agent de DressMe")
    parser.add_argument("--agents", default="all", help="all ou une liste séparée par des virgules : " + ", ".join(AGENTS))
    parser.add_argument("--no-judge", action="store_true", help="sans LLM-juge (contrôles du code seulement)")
    parser.add_argument("--env-file", help="fichier .env contenant SUPABASE_URL et SUPABASE_ANON_KEY")
    parser.add_argument("--seed-shoes", action="store_true",
                        help="ajoute 3 paires de chaussures (tag eval-test) au compte de test pendant l'évaluation, puis les retire")
    parser.add_argument("--list", action="store_true", help="liste les agents et le nombre de cas, sans rien appeler")
    args = parser.parse_args(argv)

    if args.list:
        cases = load_cases()
        for name, spec in AGENTS.items():
            mine = [c for c in cases if c.agent == name]
            print(f"{name:18} {spec.label:46} {len(mine)} cas / {sum(len(c.steps) for c in mine)} pas")
        return 0

    outcome = evaluator_agent.run(args.agents.split(","), use_judge=not args.no_judge, env_file=args.env_file,
                                  seed_shoes=args.seed_shoes)
    if outcome["state"] != "completed":
        print(f"[{outcome['state']}] {outcome['message']}")
        return 2 if outcome["state"] == "input-required" else 1
    summary = outcome["summary"]
    print(f"{'agent':18} {'pas':>4} {'réussite':>9} {'latence méd.':>13}  juge (pert./util.)")
    for name, agent in summary["agents"].items():
        judge = f"{agent['judge']['relevance']}/{agent['judge']['usefulness']}" if agent["judge"] else "—"
        latency = f"{agent['median_latency_s']} s" if agent["median_latency_s"] is not None else "—"
        print(f"{name:18} {agent['steps']:>4} {agent['success_rate']:>8}% {latency:>13}  {judge}")
    overall = summary["overall"]
    print(f"\nGlobal : {overall['success_rate']} % ({overall['pass']} PASS, {overall['warn']} WARN, {overall['fail']} FAIL)")
    for failure in summary["failures"][:25]:
        print(f"  - {failure['agent']}/{failure['case']} [{failure['criterion']}] {failure['check']} : {failure['reason']}")
    if len(summary["failures"]) > 25:
        print(f"  ... {len(summary['failures']) - 25} autre(s) dans le rapport")
    print("\nRapports :", outcome["report_paths"]["json"], "|", outcome["report_paths"]["markdown"])
    return 1 if overall["fail"] else 0


if __name__ == "__main__":
    sys.exit(main())
