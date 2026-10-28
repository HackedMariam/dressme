"""Évaluation de l'extraction d'intention (I79) du Stylist Agent.

Compare trois configurations sur intent_cases.jsonl (50 demandes annotées à la main) :
  A. règles seules          : stylist_agent.extract_with_rules
  B. LLM seul               : ollama_extract + validate_llm_output, sans garde-fou
  C. système complet        : règles + LLM + ground_llm_output, fusion identique à extract_intent
                              (occasion/saison des règles en priorité, sinon du LLM ; listes unies ;
                              wants_another = règles OU LLM ; feedback = règles)
Le schéma JSON du LLM n'a pas de champ « feedback » : B ne peut jamais en extraire.

Usage (depuis backend/, Ollama démarré) :
    .\\.venv\\Scripts\\python.exe evaluation\\intent\\eval_intent.py
Écrit results.json et report.md à côté de ce fichier. Aucun fichier existant n'est modifié.
"""

from __future__ import annotations

import datetime as dt
import json
import statistics
import sys
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent.parent
sys.path.insert(0, str(BACKEND))

import stylist_agent as sa  # noqa: E402

CASES_FILE = HERE / "intent_cases.jsonl"
RESULTS_FILE = HERE / "results.json"
REPORT_FILE = HERE / "report.md"
CONFIGS = {"A": "Règles seules", "B": "LLM seul (sans garde-fou)", "C": "Système complet (production)"}
CATEGORIES = ("simple", "paraphrase", "contrainte", "sans_occasion", "retour")
FIELDS = ("occasion", "season", "feedback", "wants_another")


def load_cases(path: Path = CASES_FILE) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# --------------------------------------------------------------------------------------
# Les trois configurations (sorties ramenées au même format)
# --------------------------------------------------------------------------------------
def predict_rules(message: str) -> dict:
    r = sa.extract_with_rules(message)
    return {"occasion": r["occasion"], "season": r["season"], "exclude_categories": r["exclude_categories"],
            "exclude_colors": r["exclude_colors"], "feedback": r["feedback"], "wants_another": r["wants_another"]}


def predict_llm(clean: dict | None) -> dict:
    clean = clean or {}
    return {"occasion": clean.get("occasion"), "season": clean.get("season"),
            "exclude_categories": list(clean.get("exclude_categories") or []),
            "exclude_colors": list(clean.get("exclude_colors") or []),
            "feedback": None, "wants_another": bool(clean.get("wants_another"))}


def predict_full(message: str, clean: dict | None) -> tuple[dict, list[str]]:
    """Même fusion que extract_intent (un seul tour, sans mémoire de conversation)."""
    rules = sa.extract_with_rules(message)
    rejected: list[str] = []
    llm = {}
    if clean:
        llm, rejected = sa.ground_llm_output(clean, message)
    # Même règle que la production : merge_occasion (mots-clés ambigus) si elle existe,
    # sinon l'ancienne priorité stricte des règles (version évaluée « avant »).
    merge = getattr(sa, "merge_occasion", None)
    occasion = merge(rules, llm.get("occasion")) if merge else rules["occasion"] or llm.get("occasion")
    return {
        "occasion": occasion,
        "season": rules["season"] or llm.get("season"),
        "exclude_categories": sa._union(rules["exclude_categories"], llm.get("exclude_categories")),
        "exclude_colors": sa._union(rules["exclude_colors"], llm.get("exclude_colors")),
        "feedback": rules["feedback"],
        "wants_another": bool(rules["wants_another"] or llm.get("wants_another", False)),
    }, rejected


# --------------------------------------------------------------------------------------
# Métriques
# --------------------------------------------------------------------------------------
def exclusions(record: dict) -> set[str]:
    return ({f"catégorie:{c}" for c in record.get("exclude_categories") or []}
            | {f"couleur:{c}" for c in record.get("exclude_colors") or []})


def field_ok(field: str, expected, predicted) -> bool:
    if field == "wants_another":
        return bool(expected) == bool(predicted)
    return expected == predicted


def score(rows: list[dict], config: str) -> dict:
    n = len(rows)
    out = {"n": n}
    for field in FIELDS:
        good = sum(field_ok(field, r["expected"][field], r[config][field]) for r in rows)
        out[f"{field}_accuracy"] = round(good / n, 3) if n else None
        out[f"{field}_correct"] = good
    tp = fp = fn = 0
    invented_cases = 0
    for r in rows:
        exp, pred = exclusions(r["expected"]), exclusions(r[config])
        tp += len(exp & pred)
        fp += len(pred - exp)
        fn += len(exp - pred)
        invented_cases += bool(pred - exp)
    out.update({
        "exclusion_tp": tp, "exclusion_fp": fp, "exclusion_fn": fn,
        "exclusion_precision": round(tp / (tp + fp), 3) if tp + fp else None,
        "exclusion_recall": round(tp / (tp + fn), 3) if tp + fn else None,
        "invented_constraints": fp, "cases_with_invented_constraints": invented_cases,
        "all_fields_correct": sum(not errors(r, config) for r in rows),
    })
    return out


def errors(row: dict, config: str) -> list[str]:
    wrong = [f for f in FIELDS if not field_ok(f, row["expected"][f], row[config][f])]
    if exclusions(row["expected"]) != exclusions(row[config]):
        wrong.append("exclusions")
    return wrong


# --------------------------------------------------------------------------------------
# Exécution
# --------------------------------------------------------------------------------------
def ollama_version() -> str | None:
    try:
        with urllib.request.urlopen(f"{sa.OLLAMA_URL}/api/version", timeout=5) as response:
            return json.loads(response.read().decode("utf-8")).get("version")
    except Exception:
        return None


def run(cases: list[dict]) -> dict:
    version = ollama_version()
    if version is None:
        raise SystemExit(f"Ollama ne répond pas sur {sa.OLLAMA_URL} : lance-le avant l'évaluation.")
    warmup = sa.ollama_extract("Une tenue pour le travail")       # préchauffage, non mesuré
    if warmup is None:
        raise SystemExit(f"Le modèle {sa.OLLAMA_MODEL} ne répond pas (absent ou en erreur).")

    rows, latencies, llm_failures = [], [], 0
    for case in cases:
        start = time.perf_counter()
        raw = sa.ollama_extract(case["message"])                  # temperature 0 (dans ollama_extract)
        latencies.append(time.perf_counter() - start)
        clean = sa.validate_llm_output(raw)
        llm_failures += clean is None
        full, rejected = predict_full(case["message"], clean)
        rows.append({
            "id": case["id"], "category": case["category"], "message": case["message"],
            "expected": {k: case[k] for k in (*FIELDS, "exclude_categories", "exclude_colors")},
            "A": predict_rules(case["message"]), "B": predict_llm(clean), "C": full,
            "llm_raw": raw, "guard_rejected": rejected,
        })
        print(f"  {case['id']:>2} {latencies[-1]:5.2f} s  {case['message'][:60]}")

    summary = {c: score(rows, c) for c in CONFIGS}
    by_category = {cat: {c: score([r for r in rows if r["category"] == cat], c) for c in CONFIGS}
                   for cat in CATEGORIES}
    return {
        "created": dt.datetime.now().isoformat(timespec="seconds"),
        "model": sa.OLLAMA_MODEL, "ollama_version": version, "temperature": 0, "n_cases": len(cases),
        "llm_latency_s": {"median": round(statistics.median(latencies), 3), "max": round(max(latencies), 3),
                          "min": round(min(latencies), 3), "calls": len(latencies)},
        "llm_failures": llm_failures,
        "guard_rejections": sum(bool(r["guard_rejected"]) for r in rows),
        "summary": summary, "by_category": by_category, "rows": rows,
    }


# --------------------------------------------------------------------------------------
# Rapport
# --------------------------------------------------------------------------------------
def pct(value) -> str:
    return "n/a" if value is None else f"{value * 100:.0f} %"


def fmt(record: dict) -> str:
    parts = [f"occasion={record['occasion']}"]
    if record.get("season"):
        parts.append(f"saison={record['season']}")
    excl = sorted(exclusions(record))
    if excl:
        parts.append("exclusions=" + ",".join(e.split(":", 1)[1] for e in excl))
    if record.get("feedback"):
        parts.append(f"feedback={record['feedback']['verdict']}:{record['feedback']['rank']}")
    if record.get("wants_another"):
        parts.append("autre=oui")
    return " · ".join(parts)


def report(results: dict) -> str:
    s, lat = results["summary"], results["llm_latency_s"]
    lines = [
        "# Évaluation de l'extraction d'intention (I79)", "",
        f"{results['n_cases']} demandes annotées à la main · modèle `{results['model']}` (Ollama "
        f"{results['ollama_version']}, temperature 0) · {results['created']}", "",
        "## Comparaison des trois configurations", "",
        "| Mesure | A. Règles seules | B. LLM seul | C. Système complet |",
        "|---|---|---|---|",
    ]
    rows = [
        ("Occasion exacte", "occasion_accuracy"), ("Saison explicite exacte", "season_accuracy"),
        ("Feedback exact", "feedback_accuracy"), ("« Une autre » exact", "wants_another_accuracy"),
        ("Précision des exclusions", "exclusion_precision"), ("Rappel des exclusions", "exclusion_recall"),
    ]
    for label, key in rows:
        lines.append(f"| {label} | " + " | ".join(pct(s[c][key]) for c in CONFIGS) + " |")
    lines.append("| Contraintes inventées (exclusions en trop) | "
                 + " | ".join(str(s[c]["invented_constraints"]) for c in CONFIGS) + " |")
    lines.append("| Demandes entièrement correctes | "
                 + " | ".join(f"{s[c]['all_fields_correct']}/{s[c]['n']}" for c in CONFIGS) + " |")
    lines += ["",
              f"Latence du LLM (B et C, un appel par demande, après préchauffage) : médiane "
              f"{lat['median']:.2f} s, max {lat['max']:.2f} s. Réponses LLM inexploitables : "
              f"{results['llm_failures']}. Demandes où le garde-fou a retiré quelque chose : "
              f"{results['guard_rejections']}.", "",
              "B n'a pas de champ « feedback » dans son schéma : son score feedback ne mesure que les "
              "demandes sans retour.", "",
              "## Par catégorie (occasion exacte · contraintes inventées · demandes entièrement correctes)", "",
              "| Catégorie | n | A | B | C |", "|---|---|---|---|---|"]
    for cat, scores in results["by_category"].items():
        cells = [f"{pct(scores[c]['occasion_accuracy'])} · {scores[c]['invented_constraints']} · "
                 f"{scores[c]['all_fields_correct']}/{scores[c]['n']}" for c in CONFIGS]
        lines.append(f"| {cat} | {scores['A']['n']} | " + " | ".join(cells) + " |")
    lines += ["", "## Erreurs du système complet (C)", ""]
    errs = [r for r in results["rows"] if errors(r, "C")]
    if not errs:
        lines.append("Aucune erreur.")
    else:
        lines += ["| # | Catégorie | Message | Attendu | Prédit | Champs faux |", "|---|---|---|---|---|---|"]
        for r in errs:
            lines.append(f"| {r['id']} | {r['category']} | {r['message']} | {fmt(r['expected'])} | "
                         f"{fmt(r['C'])} | {', '.join(errors(r, 'C'))} |")
    lines += ["", "## Limites", "",
              "- **50 phrases écrites par nous** : elles ne représentent pas la variété des vraies demandes "
              "(fautes, abréviations, messages longs, mélange de langues).",
              "- **Un seul annotateur** : certaines étiquettes sont discutables (par exemple un jury de "
              "recrutement classé « work », une remise de diplôme avec cocktail classée « evening ») ; "
              "aucun accord inter-annotateurs n'est mesuré.",
              "- **Petit modèle local** (`qwen2.5:3b`, quantifié, CPU/GPU modeste) : les résultats ne "
              "préjugent pas d'un modèle plus grand ; la latence dépend de la machine et de sa charge.",
              "- Chaque demande est évaluée **isolément** : la mémoire de conversation (occasion reprise du "
              "tour précédent) n'est pas mesurée.",
              "- Les pourcentages par catégorie portent sur 6 à 15 demandes : un écart d'une demande change "
              "le score de 7 à 17 points.",
              ]
    return "\n".join(lines) + "\n"


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Évaluation de l'extraction d'intention (I79)")
    parser.add_argument("--cases", type=Path, default=CASES_FILE, help="jeu de demandes annotées (JSONL)")
    parser.add_argument("--results", type=Path, default=None, help="fichier de résultats JSON à écrire")
    parser.add_argument("--report", type=Path, default=None,
                        help="rapport Markdown à écrire (par défaut : report.md pour le jeu principal "
                             "seulement ; aucun rapport pour un autre jeu)")
    args = parser.parse_args()
    main_set = args.cases.resolve() == CASES_FILE.resolve()
    results_file = args.results or (RESULTS_FILE if main_set else HERE / f"results_{args.cases.stem}.json")
    report_file = args.report or (REPORT_FILE if main_set else None)

    cases = load_cases(args.cases)
    print(f"{len(cases)} demandes ({args.cases.name}), modèle {sa.OLLAMA_MODEL}")
    results = run(cases)
    results["cases_file"] = args.cases.name
    results_file.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nRésultats : {results_file}")
    if report_file:
        report_file.write_text(report(results), encoding="utf-8")
        print(f"Rapport   : {report_file}")


if __name__ == "__main__":
    main()
