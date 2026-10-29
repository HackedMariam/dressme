"""Comparaison prompt v1 / prompt v2 (E2), sans nouvelle inférence.

v1 : output_optim_confirm/R1U (896 px, num_ctx 6144, num_predict 2048,
déchargement entre images ; résultats déterministes, vérifiés lors de la
confirmation). v2 : output_prompt_v2/R1U-P2, mêmes paramètres.

Critères fixés AVANT l'exécution de v2 :
1. le gilet blanc à empiècement bleu (0680192004) termine (`stop`) avec un JSON valide ;
2. au moins autant de réponses valides que v1 (9/10) ;
3. moins de jetons générés (médiane) OU latence médiane plus faible ;
4. pas de dégradation manifeste : sur les 4 images annotées, au plus 1
   correspondance de moins que v1 avec l'annotation humaine (32 comparaisons).
   EXPLORATOIRE : 1 annotateur, 4 images, sans valeur d'évaluation indépendante.

Une seconde paire (--pair v2v3) compare v2 à v3 avec ses propres critères
(voir verdict_v3), eux aussi fixés avant l'exécution de v3.

Usage (depuis backend/) :
    .\\.venv\\Scripts\\python.exe -m experiments.qwen3vl_e2.compare_prompts
    .\\.venv\\Scripts\\python.exe -m experiments.qwen3vl_e2.compare_prompts --pair v2v3
"""

import argparse
import csv
import json
import statistics
import sys
from pathlib import Path

from experiments.qwen3vl_e2.run_microbench import percentile
from experiments.qwen3vl_e2.taxonomy import DIMENSIONS

E2_DIR = Path(__file__).resolve().parent
V1_RESULTS = E2_DIR / "output_optim_confirm" / "R1U" / "results.jsonl"
V2_RESULTS = E2_DIR / "output_prompt_v2" / "R1U-P2" / "results.jsonl"
HUMAN_DIR = E2_DIR / "output_human_eval"
OUTPUT = E2_DIR / "output_prompt_v2" / "comparison_v1_v2.json"
BLOCKED_ITEM = "0680192004"
SCORED = tuple(d for d in DIMENSIONS if d != "certainty")
MAX_HUMAN_MATCH_LOSS = 1


def load_measured(path):
    rows = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    return {r["article_id"]: r for r in rows if r["phase"] != "warmup"}


def load_human(human_dir=HUMAN_DIR):
    """Valeurs humaines par image et attribut, depuis l'unique comparaison_*.csv existante."""
    files = sorted(Path(human_dir).glob("comparaison_*.csv"))
    if len(files) != 1:
        raise ValueError(f"une seule comparaison humaine attendue, trouvé : {[f.name for f in files]}")
    human = {}
    with files[0].open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            human.setdefault(row["article_id"], {})[row["attribute"]] = row["human"]
    return human


def version_metrics(records):
    rows = list(records.values())
    ok = [r for r in rows if r["error"] is None]
    walls = [r["wall_s"] for r in ok]
    evals = [r["eval_count"] for r in rows if r.get("eval_count")]
    rams = [r["ram_min_available_mib"] for r in rows if r.get("ram_min_available_mib") is not None]
    vram = [r["vram_peak_mib"] for r in rows if r.get("vram_peak_mib") is not None]
    return {
        "calls": len(rows), "schema_valid": sum(r["schema_valid"] for r in rows),
        "done_stop": sum(r["done_reason"] == "stop" for r in rows),
        "blocked_length": sorted(r["article_id"] for r in rows if r["done_reason"] == "length"),
        "errors": sorted(r["article_id"] for r in rows if r["error"]),
        "eval_count_median": statistics.median(evals) if evals else None,
        "eval_count_max": max(evals, default=None), "eval_count_total": sum(evals),
        "latency_p50_s": percentile(walls, 0.5), "latency_p95_s": percentile(walls, 0.95),
        "wall_minus_load_p50_s": percentile([r["wall_minus_load_s"] for r in ok], 0.5),
        "ram_min_available_mib": min(rams, default=None), "vram_peak_mib": max(vram, default=None),
        "prompt_eval_count": sorted({r.get("prompt_eval_count") for r in rows if r.get("prompt_eval_count")}),
    }


def attribute_changes(v1, v2, labels=("v1", "v2")):
    changes = {}
    for article_id in sorted(set(v1) & set(v2)):
        a1, a2 = v1[article_id].get("attributes"), v2[article_id].get("attributes")
        if a1 is None or a2 is None:
            changes[article_id] = "comparaison impossible (réponse invalide d'un côté)"
            continue
        diff = {d: {labels[0]: a1[d], labels[1]: a2[d]} for d in DIMENSIONS if a1[d] != a2[d]}
        if diff:
            changes[article_id] = diff
    return changes


def human_matches(records, human):
    per_item = {}
    for article_id, values in human.items():
        attrs = (records.get(article_id) or {}).get("attributes")
        per_item[article_id] = None if attrs is None else sum(attrs[d] == values[d] for d in SCORED)
    return {"by_item": per_item, "total": sum(v or 0 for v in per_item.values()), "compared": len(per_item) * len(SCORED)}


def verdict(m1, m2, v2, h1, h2):
    blocked = v2.get(BLOCKED_ITEM, {})
    checks = {
        "blocked_item_fixed": blocked.get("done_reason") == "stop" and bool(blocked.get("schema_valid")),
        "valid_not_lower": m2["schema_valid"] >= m1["schema_valid"],
        "fewer_tokens_or_faster": (m2["eval_count_median"] or 0) < (m1["eval_count_median"] or 0)
                                  or (m2["latency_p50_s"] or 0) < (m1["latency_p50_s"] or 0),
        "no_manifest_degradation_exploratory": h2["total"] >= h1["total"] - MAX_HUMAN_MATCH_LOSS,
    }
    return {"checks": checks, "promising": all(checks.values())}


def compare(v1_path=V1_RESULTS, v2_path=V2_RESULTS, human_dir=HUMAN_DIR):
    v1, v2 = load_measured(v1_path), load_measured(v2_path)
    if set(v1) != set(v2):
        raise ValueError(f"images différentes : v1 {sorted(v1)} / v2 {sorted(v2)}")
    human = load_human(human_dir)
    m1, m2 = version_metrics(v1), version_metrics(v2)
    h1, h2 = human_matches(v1, human), human_matches(v2, human)
    per_image = {a: {"eval_v1": v1[a].get("eval_count"), "eval_v2": v2[a].get("eval_count"),
                     "done_v1": v1[a]["done_reason"], "done_v2": v2[a]["done_reason"],
                     "wall_v1": round(v1[a]["wall_s"], 1), "wall_v2": round(v2[a]["wall_s"], 1)} for a in sorted(v1)}
    return {
        "v1": m1, "v2": m2, "per_image": per_image, "attribute_changes": attribute_changes(v1, v2),
        "human_exploratory": {"v1": h1, "v2": h2,
                              "warning": "1 annotateur, 4 images : indicatif, pas une évaluation indépendante."},
        "verdict": verdict(m1, m2, v2, h1, h2),
    }


# ---------------------------------------------------------------------------
# v2 / v3 (critères fixés AVANT l'exécution de v3)
# ---------------------------------------------------------------------------
V3_RESULTS = E2_DIR / "output_prompt_v3" / "R1U-P3" / "results.jsonl"
OUTPUT_V3 = E2_DIR / "output_prompt_v3" / "comparison_v2_v3.json"
WATCHED_V3 = {"0783144006": ("primary_color",), "0793493001": ("category", "primary_color"),
              "0680192004": ("category", "primary_color")}
TOKEN_LATENCY_TOLERANCE = 1.20                      # v3 <= v2 x 1,2 (médiane jetons et latence hors chargement)
SELECTION_CSV = E2_DIR / "data" / "microbench_e2.csv"


def finished(records, article_id):
    record = records.get(article_id, {})
    return record.get("done_reason") == "stop" and bool(record.get("schema_valid"))


def verdict_v3(m2, m3, v3, h2, h3):
    def within(new, old):
        return new is not None and old is not None and new <= old * TOKEN_LATENCY_TOLERANCE
    checks = {
        "multicolour_cardigan_fixed": finished(v3, "0793493001"),
        "white_cardigan_still_fixed": finished(v3, "0680192004"),
        "valid_not_lower": m3["schema_valid"] >= m2["schema_valid"],
        "tokens_and_latency_kept": within(m3["eval_count_median"], m2["eval_count_median"])
                                   and within(m3["wall_minus_load_p50_s"], m2["wall_minus_load_p50_s"]),
        "no_manifest_degradation_exploratory": h3["total"] >= h2["total"] - MAX_HUMAN_MATCH_LOSS,
    }
    return {"checks": checks, "promising": all(checks.values()),
            "target_10_of_10": m3["schema_valid"] == m3["calls"] == 10}


def watched_attributes(v2, v3, selection_csv=SELECTION_CSV):
    """Couleurs et catégories surveillées ; les métadonnées H&M sont un signal, pas une preuve."""
    meta = {}
    if Path(selection_csv).is_file():
        with Path(selection_csv).open(encoding="utf-8", newline="") as handle:
            meta = {r["article_id"]: r for r in csv.DictReader(handle)}
    out = {}
    for article_id, fields in WATCHED_V3.items():
        a2 = (v2.get(article_id) or {}).get("attributes") or {}
        a3 = (v3.get(article_id) or {}).get("attributes") or {}
        row = meta.get(article_id, {})
        out[article_id] = {f: {"v2": a2.get(f), "v3": a3.get(f)} for f in fields}
        out[article_id]["hm_metadata_signal_not_proof"] = {"product_type": row.get("product_type_name"),
                                                          "colour_group": row.get("colour_group_name")}
    return out


def compare_v2_v3(v2_path=V2_RESULTS, v3_path=V3_RESULTS, human_dir=HUMAN_DIR, selection_csv=SELECTION_CSV):
    v2, v3 = load_measured(v2_path), load_measured(v3_path)
    if set(v2) != set(v3):
        raise ValueError(f"images différentes : v2 {sorted(v2)} / v3 {sorted(v3)}")
    human = load_human(human_dir)
    m2, m3 = version_metrics(v2), version_metrics(v3)
    h2, h3 = human_matches(v2, human), human_matches(v3, human)
    per_image = {a: {"eval_v2": v2[a].get("eval_count"), "eval_v3": v3[a].get("eval_count"),
                     "done_v2": v2[a]["done_reason"], "done_v3": v3[a]["done_reason"],
                     "wall_v2": round(v2[a]["wall_s"], 1), "wall_v3": round(v3[a]["wall_s"], 1)} for a in sorted(v2)}
    return {
        "v2": m2, "v3": m3, "per_image": per_image,
        "attribute_changes": attribute_changes(v2, v3, ("v2", "v3")),
        "watched": watched_attributes(v2, v3, selection_csv),
        "human_exploratory": {"v2": h2, "v3": h3,
                              "warning": "1 annotateur, 4 images : indicatif, pas une évaluation indépendante."},
        "verdict": verdict_v3(m2, m3, v3, h2, h3),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pair", choices=("v1v2", "v2v3"), default="v1v2")
    args = parser.parse_args()
    output = OUTPUT if args.pair == "v1v2" else OUTPUT_V3
    if output.exists():
        sys.exit(f"{output} existe déjà : rien n'est écrasé")
    try:
        result = compare() if args.pair == "v1v2" else compare_v2_v3()
    except (ValueError, FileNotFoundError) as error:
        sys.exit(str(error))
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
