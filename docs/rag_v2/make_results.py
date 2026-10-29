"""Regénère results.md (table avant / après) à partir des fichiers de runs/ produits par evaluate.py."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNS = HERE / "runs"
# (fichier, étape, mode affiché)
ORDER = [
    ("0_baseline_retrieve_raw", "0. Baseline (rag/try1)", "retrieve, question brute"),
    ("0_baseline_ask", "0. Baseline (rag/try1)", "ask (réécriture LLM)"),
    ("1_translation_retrieve", "1. Traduction FR→EN", "retrieve, question traduite"),
    ("1_translation_ask", "1. Traduction FR→EN", "ask"),
    ("2_citations_retrieve", "2. Prompt de citation", "retrieve, question traduite"),
    ("2_citations_ask", "2. Prompt de citation", "ask"),
    ("3_corpus_v2_simulation_retrieve", "3. Corpus v2 (SIMULATION, table non créée)", "retrieve, question traduite"),
    ("4_corpus_v2_retrieve", "4. Corpus v2 + nouvelles sources", "retrieve, question traduite"),
    ("4_corpus_v2_ask", "4. Corpus v2 + nouvelles sources", "ask"),
]
COLUMNS = [("hit@5", "Hit@5"), ("mrr@5", "MRR@5"), ("precision@5", "Préc.@5"),
           ("titre_signale_dans_sources", "Titre signalé (sources)"), ("grounded", "Avec citation"),
           ("citation_pertinente", "Citation pertinente"), ("je_ne_sais_pas", "« I don't know » injustifié"),
           ("refus_attendu_respecte", "Refus attendu respecté"),
           ("latence_mediane_s", "Latence méd. (s)")]


def cell(summary: dict, key: str) -> str:
    value = summary.get(key)
    if value is None:
        return "—"
    return f"{value:g}" if key == "latence_mediane_s" else f"{value:g} %"


def main() -> None:
    lines = ["# RAG v2 : résultats avant / après", "",
             "**Chiffres provisoires** : le gold set (`gold_set.jsonl`, 40 questions, 20 sujets en FR et en EN) est un "
             "brouillon non validé. Une exécution par ligne ; le LLM varie d'un appel à l'autre. `top_k = 5`.",
             "", "Depuis l'étape 4, le sujet « tendances » (2 questions) n'a plus de source : réponse attendue "
             "« I don't know », hors Hit@5 / MRR / précision (36 questions mesurées). Les lignes 0 à 3 utilisent "
             "l'ancien gold set (40 questions mesurées, attendus de la v1).", ""]
    for scope, title in (("tout", "Ensemble (40 questions)"), ("fr", "Questions en français (20)"),
                         ("en", "Questions en anglais (20)")):
        lines += [f"## {title}", "", "| Étape | Mode | " + " | ".join(label for _, label in COLUMNS) + " |",
                  "|---|---|" + "---:|" * len(COLUMNS)]
        for name, step, mode in ORDER:
            path = RUNS / f"{name}.json"
            if not path.exists():
                continue
            summary = json.loads(path.read_text(encoding="utf-8"))["summary"][scope]
            lines.append(f"| {step} | {mode} | " + " | ".join(cell(summary, key) for key, _ in COLUMNS) + " |")
        lines.append("")
    lines += ["## Paires FR / EN (Hit@5 sur le même sujet)", "",
              "| Étape | Mode | Les deux | Anglais seul | Français seul | Aucune |", "|---|---|---:|---:|---:|---:|"]
    for name, step, mode in ORDER:
        path = RUNS / f"{name}.json"
        if path.exists():
            p = json.loads(path.read_text(encoding="utf-8"))["summary"]["paires"]
            lines.append(f"| {step} | {mode} | {p['les_deux']} | {p['anglais_seulement']} | "
                         f"{p['francais_seulement']} | {p['aucune']} |")
    (HERE / "results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("results.md regénéré")


if __name__ == "__main__":
    main()
