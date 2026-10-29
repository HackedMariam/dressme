"""Mini-benchmark E2 : 3 images de la sélection, UN appel par image.

Prolonge le test sur une image (0840606004 réussi avec num_predict=2048,
num_ctx=6144) à trois autres rôles et motifs. Prompt, taxonomie, schéma et
critères inchangés. Trop petit pour un verdict d'acceptation : les critères
sont seulement rapportés à titre indicatif.

Contrôle RAM avant CHAQUE appel (>= 1 500 Mio, + 418 Mio si le modèle n'est pas
chargé) ; arrêt de toute nouvelle inférence si un contrôle échoue ou si un
appel fait descendre la RAM disponible sous 300 Mio. Résultats dans
output_mini3/ ; aucun résultat existant n'est écrasé.

Usage (depuis backend/), après validation explicite :
    .\\.venv\\Scripts\\python.exe -m experiments.qwen3vl_e2.run_mini_bench
"""

import argparse
import datetime
import json
import statistics
import sys
from pathlib import Path

from evaluation.common import DATA_HM_DIR, sha256_file
from experiments.qwen3vl_e2.monitor import ResourceMonitor, sample_ram_available_mib
from experiments.qwen3vl_e2.ollama_client import OllamaClient
from experiments.qwen3vl_e2.prompt import prompt_fingerprint
from experiments.qwen3vl_e2.run_microbench import (
    ACCEPTANCE, OUTPUT_DIR, SELECTION_CSV, ModelMissing, OutputExists, build_options, ensure_model_present,
    ensure_output_free, load_selection, low_ram, model_loaded, ram_preflight, run_call)
from experiments.qwen3vl_e2.run_single_check import SINGLE_OUTPUT_DIR
from experiments.qwen3vl_e2.taxonomy import TAXONOMY_VERSION, taxonomy_fingerprint

E2_DIR = Path(__file__).resolve().parent
MINI_OUTPUT_DIR = E2_DIR / "output_mini3"
# Haut à pois (adulte), veste unie (adulte), robe à motif (enfant) : trois rôles
# et trois motifs différents du pantalon rayé déjà testé.
DEFAULT_ARTICLES = ("0781758009", "0783144006", "0801843006")
MAX_IMAGES = 3
RESULT_FILES = ("results.jsonl", "summary.json", "metadata.json")


def pick_items(selection, article_ids):
    if len(set(article_ids)) != len(article_ids):
        raise ValueError("identifiants en double")
    if not 1 <= len(article_ids) <= MAX_IMAGES:
        raise ValueError(f"1 à {MAX_IMAGES} images, un appel chacune")
    by_id = {i["article_id"]: i for i in selection}
    missing = [a for a in article_ids if a not in by_id]
    if missing:
        raise ValueError(f"absents de la sélection E2 : {missing}")
    return [by_id[a] for a in article_ids]


def mini_bench(client, model, items, options, images_root=DATA_HM_DIR, monitor_factory=ResourceMonitor,
               ram_sampler=sample_ram_available_mib):
    """Un appel par image ; s'arrête au premier contrôle mémoire défavorable."""
    ensure_model_present(client, model)
    preflights, records, stop_reason = [], [], None
    for index, item in enumerate(items):
        loaded, model_ram = model_loaded(client.ps(), model)
        check = {"article_id": item["article_id"], **ram_preflight(ram_sampler(), loaded),
                 "model_ram_in_use_mib": model_ram}
        preflights.append(check)
        if not check["ok"]:
            stop_reason = f"contrôle RAM échoué avant {item['article_id']}"
            break
        records.append(run_call(client, model, item, "mini", index, images_root, monitor_factory, options=options))
        if low_ram(records[-1]):
            stop_reason = f"RAM sous 300 Mio pendant {item['article_id']}"
            break
    return preflights, records, stop_reason


def summarize_mini(records, options, planned):
    """Résumé descriptif ; latence aussi hors chargement (le 1er appel peut charger le modèle)."""
    answered = [r for r in records if r["error"] is None]
    latency = [r["wall_s"] for r in answered]
    no_load = [r["wall_s"] - (r.get("load_duration") or 0) / 1e9 for r in answered]
    rates = [r["eval_count"] / (r["eval_duration"] / 1e9) for r in answered
             if r.get("eval_count") and r.get("eval_duration")]
    vram = [r["vram_peak_mib"] for r in records if r["vram_peak_mib"] is not None]
    ram = [r["ram_min_available_mib"] for r in records if r["ram_min_available_mib"] is not None]
    summary = {
        "planned_calls": planned, "calls": len(records),
        "errors": [r["error"] for r in records if r["error"]],
        "done_stop": sum(r["done_reason"] == "stop" for r in records),
        "json_parsed": sum(r["json_parsed"] for r in records),
        "schema_valid": sum(r["schema_valid"] for r in records),
        "eval_count_hit_limit": sum(r.get("eval_count") == options["num_predict"] for r in records),
        "eval_count": [r.get("eval_count") for r in records],
        "thinking_chars": [r["thinking_chars"] for r in records],
        "wall_s": latency, "wall_minus_load_s": no_load,
        "wall_median_s": statistics.median(latency) if latency else None,
        "wall_max_s": max(latency) if latency else None,
        "eval_tokens_per_s": rates,
        "vram_peak_mib": max(vram) if vram else None,
        "ram_min_available_mib": min(ram) if ram else None,
        "gpu_share": [r["gpu_share"] for r in records],
    }
    # Indicatif seulement : 3 appels ne permettent pas de conclure sur des seuils fixés pour 30.
    summary["indicative_vs_acceptance"] = {
        "latency_within_p50_max": [s <= ACCEPTANCE["latency_p50_max_s"] for s in latency],
        "latency_within_p95_max": [s <= ACCEPTANCE["latency_p95_max_s"] for s in latency],
        "ram_ok": summary["ram_min_available_mib"] is not None
                  and summary["ram_min_available_mib"] >= ACCEPTANCE["ram_available_min_mib"],
        "vram_ok": summary["vram_peak_mib"] is not None and summary["vram_peak_mib"] <= ACCEPTANCE["vram_max_mib"],
    }
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="qwen3-vl:2b")
    parser.add_argument("--article-ids", nargs="+", default=list(DEFAULT_ARTICLES))
    parser.add_argument("--num-predict", type=int, default=2048)
    parser.add_argument("--num-ctx", type=int, default=6144)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--host", default="http://localhost:11434")
    parser.add_argument("--output-dir", type=Path, default=MINI_OUTPUT_DIR)
    args = parser.parse_args()
    if args.output_dir.resolve() in {OUTPUT_DIR.resolve(), SINGLE_OUTPUT_DIR.resolve()}:
        sys.exit("dossier réservé à des résultats précédents : en choisir un autre")
    try:
        options = build_options(args.num_predict, args.num_ctx)
        for name in RESULT_FILES:
            ensure_output_free(args.output_dir, name)
        items = pick_items(load_selection(), args.article_ids)
    except (ValueError, OutputExists) as error:
        sys.exit(str(error))
    client = OllamaClient(args.host, args.timeout)
    try:
        preflights, records, stop_reason = mini_bench(client, args.model, items, options)
    except ModelMissing as error:
        sys.exit(str(error))
    summary = {**summarize_mini(records, options, len(items)), "stop_reason": stop_reason, "preflights": preflights}
    tag = next((m for m in client.tags() if m.get("name") == args.model or m.get("model") == args.model), {})
    metadata = {
        "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "model": args.model, "model_digest": tag.get("digest"), "ollama_version": client.version(),
        "options": options, "think": False, "timeout_s": args.timeout,
        "images": {i["article_id"]: i["image_sha256"] for i in items},
        "taxonomy_version": TAXONOMY_VERSION, "taxonomy_sha256": taxonomy_fingerprint(),
        "prompt_sha256": prompt_fingerprint(), "selection_sha256": sha256_file(SELECTION_CSV),
        "note": "Mini-benchmark de faisabilité (1 appel par image) : ni exactitude, ni verdict d'acceptation.",
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with (args.output_dir / "results.jsonl").open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    for name, content in (("summary.json", summary), ("metadata.json", metadata)):
        (args.output_dir / name).write_text(json.dumps(content, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if stop_reason:
        sys.exit(f"arrêt : {stop_reason}")


if __name__ == "__main__":
    main()
