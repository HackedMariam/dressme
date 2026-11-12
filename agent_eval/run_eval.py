"""Run the LLM judge over every agent (or some), and write a report.

  python -m agent_eval.run_eval                      # every agent, cases that carry a recorded `output`
  python -m agent_eval.run_eval stylist outfit       # some agents
  python -m agent_eval.run_eval --live --token JWT   # call the running agents over A2A (cases without `output` too)
  python -m agent_eval.run_eval --min-pass 0.8       # exit code 1 if fewer than 80 % of the cases pass (CI gate)

Cases: agent_eval/cases/<agent>.jsonl, one JSON per line: {"id", "input", "data"?, "context"?, "output"?}.
Results: agent_eval/results/<timestamp>.json and a table on screen.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .judge import judge_case, openai_complete
from .rubrics import RUBRICS

HERE = Path(__file__).resolve().parent
CASES = HERE / "cases"
RESULTS = HERE / "results"


def load_cases(agent: str, directory: Path = CASES) -> list:
    path = directory / f"{agent}.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def evaluate(agents: list, complete, live: bool = False, token: str | None = None, directory: Path = CASES) -> list:
    results = []
    for agent in agents:
        for case in load_cases(agent, directory):
            if "output" not in case:
                if not live:
                    results.append({"agent": agent, "id": case.get("id"), "skipped": "no recorded output (use --live)"})
                    continue
                from .live import run_live
                try:
                    case = run_live(agent, case, token)
                except Exception as error:   # service down, refusal...: reported, never hides the other cases
                    results.append({"agent": agent, "id": case.get("id"), "error": f"agent call failed: {error}", "passed": False})
                    continue
            results.append(judge_case(agent, case, complete))
    return results


def summarize(results: list) -> dict:
    out = {}
    for agent in sorted({r["agent"] for r in results}):
        rows = [r for r in results if r["agent"] == agent and not r.get("skipped")]
        scored = [r for r in rows if "average" in r]
        out[agent] = {"cases": len(rows), "passed": sum(1 for r in rows if r.get("passed")),
                      "errors": sum(1 for r in rows if r.get("error")),
                      "average": round(sum(r["average"] for r in scored) / len(scored), 2) if scored else None,
                      "skipped": sum(1 for r in results if r["agent"] == agent and r.get("skipped"))}
    return out


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("agents", nargs="*", help=f"default: all ({', '.join(RUBRICS)})")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--token", help="Supabase JWT of the user (live mode, when auth is on)")
    parser.add_argument("--model", help="judge model (default: JUDGE_MODEL, then LLM_MODEL)")
    parser.add_argument("--min-pass", type=float, default=None, help="minimum share of passing cases, else exit 1")
    args = parser.parse_args(argv)

    try:
        from dotenv import load_dotenv
        load_dotenv(HERE.parent / ".env")
    except ImportError:
        pass
    unknown = [a for a in args.agents if a not in RUBRICS]
    if unknown:
        parser.error(f"unknown agent(s): {', '.join(unknown)}")
    agents = args.agents or list(RUBRICS)
    results = evaluate(agents, openai_complete(args.model), live=args.live, token=args.token)
    summary = summarize(results)

    print(f"{'agent':<13}{'cases':>6}{'passed':>7}{'errors':>7}{'avg/5':>7}{'skipped':>8}")
    for agent, s in summary.items():
        print(f"{agent:<13}{s['cases']:>6}{s['passed']:>7}{s['errors']:>7}{s['average'] if s['average'] is not None else '-':>7}{s['skipped']:>8}")
    for r in results:
        if r.get("failed_hard") or r.get("error"):
            print(f"  ! {r['agent']}/{r.get('id')}: {r.get('error') or 'hard criterion failed: ' + ', '.join(r['failed_hard'])}")

    RESULTS.mkdir(exist_ok=True)
    path = RESULTS / f"{time.strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"report: {path}")

    judged = [r for r in results if not r.get("skipped")]
    if args.min_pass is not None and judged:
        return 0 if sum(1 for r in judged if r.get("passed")) / len(judged) >= args.min_pass else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
