"""Calculs prévus pour E1, à exécuter UNIQUEMENT sur des annotations humaines réelles.

- Accord inter-annotateurs : kappa de Cohen par attribut (2 évaluateurs).
- Référence de consensus : vêtements où les deux évaluateurs donnent la même
  classe (« incertain » et « non visible » exclus et comptés à part).
- Exactitude et matrice de confusion de FashionCLIP sur ce consensus.

La commande refuse de s'exécuter sans au moins deux fichiers d'annotations.

Usage (depuis backend/), une fois les annotations reçues :
    .\\.venv\\Scripts\\python.exe -m experiments.fashionclip_e1.agreement annotations_A1.csv annotations_B2.csv
"""

import argparse
import csv
import json
import sys
from pathlib import Path

from experiments.fashionclip_e1.attributes import ATTRIBUTES, HUMAN_EXTRA_OPTIONS
from experiments.fashionclip_e1.run_e1 import OUTPUT_DIR

NON_LABELS = set(HUMAN_EXTRA_OPTIONS)


def read_annotations(path):
    """{article_id: {attribut: réponse}} et le pseudonyme de l'annotateur."""
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    annotators = {r["annotateur"] for r in rows}
    if len(annotators) != 1:
        raise ValueError(f"{path} : un seul annotateur attendu, trouvé {sorted(annotators)}")
    return annotators.pop(), {r["article_id"]: {a: r.get(a, "") for a in ATTRIBUTES} for r in rows}


def cohen_kappa(labels_a, labels_b, categories):
    """Kappa de Cohen sur deux listes alignées de classes (déjà filtrées)."""
    if len(labels_a) != len(labels_b):
        raise ValueError("listes de tailles différentes")
    n = len(labels_a)
    if n == 0:
        return None
    observed = sum(a == b for a, b in zip(labels_a, labels_b)) / n
    expected = sum((labels_a.count(c) / n) * (labels_b.count(c) / n) for c in categories)
    if expected == 1:
        return None  # un seul libellé utilisé par les deux : kappa indéfini
    return (observed - expected) / (1 - expected)


def confusion_matrix(truth, predicted, categories):
    matrix = {t: {p: 0 for p in categories} for t in categories}
    for t, p in zip(truth, predicted):
        matrix[t][p] += 1
    return matrix


def analyse_attribute(attribute, annotations_a, annotations_b, predictions):
    categories = list(ATTRIBUTES[attribute]["classes"])
    common = sorted(set(annotations_a) & set(annotations_b))
    both_labelled = [i for i in common
                     if annotations_a[i][attribute] in categories and annotations_b[i][attribute] in categories]
    excluded = len(common) - len(both_labelled)
    a = [annotations_a[i][attribute] for i in both_labelled]
    b = [annotations_b[i][attribute] for i in both_labelled]
    consensus = [i for i in both_labelled if annotations_a[i][attribute] == annotations_b[i][attribute]]
    truth = [annotations_a[i][attribute] for i in consensus]
    model = [predictions[i][attribute] for i in consensus]
    correct = sum(t == m for t, m in zip(truth, model))
    return {
        "items_common": len(common),
        "items_both_labelled": len(both_labelled),
        "items_excluded_uncertain_or_not_visible": excluded,
        "cohen_kappa": cohen_kappa(a, b, categories),
        "raw_agreement": (sum(x == y for x, y in zip(a, b)) / len(a)) if a else None,
        "consensus_items": len(consensus),
        "model_accuracy_on_consensus": (correct / len(consensus)) if consensus else None,
        "confusion_consensus_vs_model": confusion_matrix(truth, model, categories),
    }


def read_predictions(path):
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return {r["article_id"]: {a: r[f"{a}_prediction"] for a in ATTRIBUTES} for r in csv.DictReader(handle)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("annotations", nargs="*", type=Path)
    parser.add_argument("--predictions", type=Path, default=OUTPUT_DIR / "predictions.csv")
    parser.add_argument("--output", type=Path, default=OUTPUT_DIR / "analyse_humaine.json")
    args = parser.parse_args()
    if len(args.annotations) != 2:
        sys.exit("Deux fichiers d'annotations humaines réelles sont requis : rien n'est calculé.")
    (name_a, ann_a), (name_b, ann_b) = (read_annotations(p) for p in args.annotations)
    if name_a == name_b:
        sys.exit("Les deux fichiers proviennent du même annotateur : rien n'est calculé.")
    predictions = read_predictions(args.predictions)
    report = {"annotators": [name_a, name_b],
              "attributes": {a: analyse_attribute(a, ann_a, ann_b, predictions) for a in ATTRIBUTES}}
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({a: {k: v for k, v in r.items() if k != "confusion_consensus_vs_model"}
                      for a, r in report["attributes"].items()}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
