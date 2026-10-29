"""Test de diagnostic E2 : UN SEUL appel sur UNE image, budget de sortie élargi.

Isole l'effet de `num_predict` / `num_ctx` après l'échec du benchmark initial
(raisonnement tronqué à 256 jetons). Prompt, taxonomie, schéma et critères
inchangés. Résultats dans output_single_check/ (output/ n'est jamais touché).

Ordre : modèle présent (aucun téléchargement) -> /api/show (sans inférence)
-> contrôle RAM -> un seul /api/chat. Si la RAM est insuffisante, aucun appel
d'inférence n'est fait et seul le contrôle est enregistré.

Usage (depuis backend/) :
    .\\.venv\\Scripts\\python.exe -m experiments.qwen3vl_e2.run_single_check --num-predict 2048 --num-ctx 6144
"""

import argparse
import datetime
import hashlib
import json
import sys
from pathlib import Path

import requests

from evaluation.common import DATA_HM_DIR
from experiments.qwen3vl_e2.monitor import ResourceMonitor, sample_ram_available_mib
from experiments.qwen3vl_e2.ollama_client import OllamaClient
from experiments.qwen3vl_e2.prompt import prompt_fingerprint
from experiments.qwen3vl_e2.run_optim import prepare_image
from experiments.qwen3vl_e2.run_microbench import (
    OBSERVED_PROMPT_TOKENS, OUTPUT_DIR, RAM_STOP_MIN_MIB, ModelMissing, OutputExists, build_options, ensure_model_present,
    ensure_output_free, load_selection, low_ram, model_loaded, ram_preflight, run_call)
from experiments.qwen3vl_e2.taxonomy import TAXONOMY_VERSION, taxonomy_fingerprint

E2_DIR = Path(__file__).resolve().parent
SINGLE_OUTPUT_DIR = E2_DIR / "output_single_check"
DEFAULT_ARTICLE = "0840606004"
RESULT_FILE = "single_check.json"
# Entrée mesurée à 896 px (output_optim R1 et R1U : 2207 jetons pour toutes les images).
R1_PROMPT_TOKENS = 2207


def result_filename(report):
    """Un refus de contrôle est journalisé à part, sans bloquer une relance."""
    if report["inference_done"]:
        return RESULT_FILE
    stamp = report["metadata"]["created_utc"].replace(":", "").replace("+0000", "Z")
    return f"preflight_refused_{stamp}.json"


def summarize_show(info):
    """Résumé des métadonnées /api/show (le gabarit n'est pas recopié en entier)."""
    template = info.get("template") or ""
    model_info = info.get("model_info") or {}
    return {
        "capabilities": info.get("capabilities"),
        "details": info.get("details"),
        "parameters": info.get("parameters"),
        "template_chars": len(template),
        "template_sha256": hashlib.sha256(template.encode("utf-8")).hexdigest(),
        "template_mentions_think": "think" in template.lower(),
        "context_length": {k: v for k, v in model_info.items() if k.endswith("context_length")},
    }


def single_check(client, model, item, options, images_root=DATA_HM_DIR, monitor_factory=ResourceMonitor,
                 ram_sampler=sample_ram_available_mib, image_bytes=None):
    """Renvoie le rapport ; `inference_done` est False si un contrôle a échoué."""
    ensure_model_present(client, model)
    report = {"article_id": item["article_id"], "options": options, "inference_done": False}
    try:
        report["show"] = summarize_show(client.show(model))
    except requests.RequestException as error:
        report["show"] = {"error": f"http: {type(error).__name__}"}
    loaded, model_ram = model_loaded(client.ps(), model)
    report["preflight"] = {**ram_preflight(ram_sampler(), loaded), "model_ram_in_use_mib": model_ram}
    if not report["preflight"]["ok"]:
        return report
    record = run_call(client, model, item, "single_check", 0, images_root, monitor_factory, options=options,
                      image_bytes=image_bytes)
    report.update({"inference_done": True, "result": record,
                   "eval_count_hit_limit": record.get("eval_count") == options["num_predict"],
                   "stop_further_inference": low_ram(record, RAM_STOP_MIN_MIB)})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="qwen3-vl:2b")
    parser.add_argument("--article-id", default=DEFAULT_ARTICLE)
    parser.add_argument("--num-predict", type=int, default=2048)
    parser.add_argument("--num-ctx", type=int, default=6144)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--host", default="http://localhost:11434")
    parser.add_argument("--output-dir", type=Path, default=SINGLE_OUTPUT_DIR)
    parser.add_argument("--max-side", type=int, default=None,
                        help="réduction en mémoire (grand côté, px) ; l'image source n'est pas modifiée")
    args = parser.parse_args()
    if args.output_dir.resolve() == OUTPUT_DIR.resolve():
        sys.exit("output/ contient le benchmark initial : choisir un autre dossier")
    try:
        prompt_tokens = R1_PROMPT_TOKENS if args.max_side == 896 else OBSERVED_PROMPT_TOKENS
        options = build_options(args.num_predict, args.num_ctx, prompt_tokens=prompt_tokens)
        ensure_output_free(args.output_dir, RESULT_FILE)
    except (ValueError, OutputExists) as error:
        sys.exit(str(error))
    item = next((i for i in load_selection() if i["article_id"] == args.article_id), None)
    if item is None:
        sys.exit(f"{args.article_id} absent de la sélection E2")
    image_bytes, image_info = prepare_image(DATA_HM_DIR / item["image_path"], args.max_side)
    client = OllamaClient(args.host, args.timeout)
    try:
        report = single_check(client, args.model, item, options, image_bytes=image_bytes)
        report["image"] = image_info
    except ModelMissing as error:
        sys.exit(str(error))
    tag = next((m for m in client.tags() if m.get("name") == args.model or m.get("model") == args.model), {})
    report["metadata"] = {
        "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "model": args.model, "model_digest": tag.get("digest"), "ollama_version": client.version(),
        "think": False, "timeout_s": args.timeout, "image_sha256": item["image_sha256"],
        "taxonomy_version": TAXONOMY_VERSION, "taxonomy_sha256": taxonomy_fingerprint(),
        "prompt_sha256": prompt_fingerprint(),
        "note": "Diagnostic sur une image : ni exactitude, ni verdict d'acceptation.",
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / result_filename(report)).write_text(json.dumps(report, indent=2, ensure_ascii=False),
                                                           encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if not report["inference_done"]:
        sys.exit("contrôle RAM échoué : aucune inférence lancée")


if __name__ == "__main__":
    main()
