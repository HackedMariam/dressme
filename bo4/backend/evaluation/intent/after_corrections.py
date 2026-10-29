"""Ajoute (ou remplace) la section « Après corrections » de report.md.

Lit results.json (50 phrases, avant), results_after.json (50 phrases, après),
results_holdout_before.json et results_holdout_after.json (jeu mis de côté).
Usage (depuis backend/) :
    .\\.venv\\Scripts\\python.exe evaluation\\intent\\after_corrections.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from eval_intent import CONFIGS, REPORT_FILE, errors, fmt, pct  # noqa: E402

MARKER = "## Après corrections"
ROWS = [
    ("Occasion exacte", "occasion_accuracy", pct), ("Saison explicite exacte", "season_accuracy", pct),
    ("Feedback exact", "feedback_accuracy", pct), ("« Une autre » exact", "wants_another_accuracy", pct),
    ("Précision des exclusions", "exclusion_precision", pct), ("Rappel des exclusions", "exclusion_recall", pct),
    ("Contraintes inventées", "invented_constraints", str),
]


def load(name: str) -> dict:
    return json.loads((HERE / name).read_text(encoding="utf-8"))


def table(before: dict, after: dict) -> list[str]:
    head = " | ".join(f"{c} avant | {c} après" for c in CONFIGS)
    lines = [f"| Mesure | {head} |", "|---|" + "---|" * (2 * len(CONFIGS))]
    for label, key, show in ROWS:
        cells = " | ".join(f"{show(before['summary'][c][key])} | {show(after['summary'][c][key])}" for c in CONFIGS)
        lines.append(f"| {label} | {cells} |")
    cells = " | ".join(f"{before['summary'][c]['all_fields_correct']}/{before['n_cases']} | "
                       f"{after['summary'][c]['all_fields_correct']}/{after['n_cases']}" for c in CONFIGS)
    lines.append(f"| Demandes entièrement correctes | {cells} |")
    return lines


def remaining_errors(results: dict) -> list[str]:
    rows = [r for r in results["rows"] if errors(r, "C")]
    if not rows:
        return ["Aucune erreur restante."]
    out = ["| # | Message | Attendu | Prédit | Champs faux |", "|---|---|---|---|---|"]
    out += [f"| {r['id']} | {r['message']} | {fmt(r['expected'])} | {fmt(r['C'])} | {', '.join(errors(r, 'C'))} |"
            for r in rows]
    return out


def section() -> str:
    main_before, main_after = load("results.json"), load("results_after.json")
    hold_before, hold_after = load("results_holdout_before.json"), load("results_holdout_after.json")
    lines = [
        MARKER, "",
        "Corrections apportées à `stylist_agent.py` après l'évaluation ci-dessus :",
        "1. négation « éviter » (évite, éviter, évitez + le/la/les/l'/de/des) dans les règles et le garde-fou ;",
        "2. le garde-fou n'accepte plus « aime » seul comme demande d'une autre tenue ;",
        "3. retours reformulés (« me plait », « j'aime bien », « pas convaincu(e) », « bof », ordinaux, "
        "« la dernière ») et « tu as mieux » → autre tenue ;",
        "4. mots-clés d'occasion ambigus (rendez-vous, meeting) : s'ils sont seuls, l'occasion du LLM l'emporte.",
        "",
        "B (LLM seul, sans règles ni garde-fou) n'est pas concerné par ces corrections : ses chiffres ne changent pas.",
        "",
        f"### Les 50 phrases ({main_after['created']})", "",
        "**Chiffre optimiste** : les corrections ont été écrites en regardant les erreurs de ces 50 phrases.", "",
        *table(main_before, main_after), "",
        "Erreurs restantes du système complet (C) :", "", *remaining_errors(main_after), "",
        f"### Jeu mis de côté : {hold_after['n_cases']} nouvelles demandes (`intent_holdout.jsonl`)", "",
        "**Chiffre honnête** : ces demandes ont été écrites et annotées à la main, et mesurées « avant », "
        "AVANT toute modification du code ; elles n'ont servi à écrire aucune correction. Attention : leur "
        "composition (2 « éviter », 3 retours reformulés, 3 mots ambigus) cible volontairement les défauts "
        "corrigés, ce qui avantage les corrections ; 15 demandes, c'est peu (une demande = 7 points).", "",
        *table(hold_before, hold_after), "",
        "Erreurs restantes du système complet (C) :", "", *remaining_errors(hold_after), "",
        f"Latence du LLM après corrections : médiane {main_after['llm_latency_s']['median']:.2f} s "
        f"(50 phrases), {hold_after['llm_latency_s']['median']:.2f} s (jeu mis de côté) ; "
        "les corrections ne touchent que les règles et le garde-fou.",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    text = REPORT_FILE.read_text(encoding="utf-8")
    text = text.split(MARKER)[0].rstrip() + "\n\n"
    REPORT_FILE.write_text(text + section(), encoding="utf-8")
    print(f"Section « Après corrections » écrite dans {REPORT_FILE}")


if __name__ == "__main__":
    main()
