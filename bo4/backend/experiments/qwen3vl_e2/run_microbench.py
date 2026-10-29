"""Microbenchmark de FAISABILITÉ de Qwen3-VL 2B via Ollama local (E2).

Mesure latence, validité JSON (schéma Pydantic strict), RAM, VRAM, part GPU,
erreurs et stabilité sur 10 images de développement hors E1 x N répétitions.
Ne mesure AUCUNE exactitude et n'ajuste rien.

Sécurités : le modèle doit déjà être présent localement (aucun téléchargement) ;
hôte local uniquement ; aucune base de données.

Garde-fous : contrôle RAM avant de commencer (>= 1 500 Mio, plus la part du
modèle s'il n'est pas chargé) ; arrêt de toute nouvelle inférence si un appel
fait descendre la RAM disponible sous 300 Mio ; refus d'écraser des résultats.

Usage (depuis backend/), après validation explicite :
    .\\.venv\\Scripts\\python.exe -m experiments.qwen3vl_e2.run_microbench --model qwen3-vl:2b --repeats 3
    (ajouter --num-predict 2048 --num-ctx 6144 --output-dir <nouveau dossier> pour le profil élargi)
"""

import argparse
import base64
import collections
import csv
import datetime
import json
import platform
import random
import statistics
import sys
import time
from pathlib import Path

import requests

from evaluation.common import DATA_HM_DIR, sha256_file
from experiments.qwen3vl_e2.monitor import ResourceMonitor, sample_ram_available_mib
from experiments.qwen3vl_e2.ollama_client import OllamaClient
from experiments.qwen3vl_e2.prompt import build_messages, prompt_fingerprint
from experiments.qwen3vl_e2.schema import ollama_format_schema, validate_response
from experiments.qwen3vl_e2.taxonomy import DIMENSIONS, TAXONOMY_VERSION, taxonomy_fingerprint

E2_DIR = Path(__file__).resolve().parent
SELECTION_CSV = E2_DIR / "data" / "microbench_e2.csv"
OUTPUT_DIR = E2_DIR / "output"
# Configuration du benchmark initial (conservée par défaut pour pouvoir le rejouer à l'identique).
OPTIONS = {"temperature": 0, "seed": 0, "num_ctx": 4096, "num_predict": 256}
# Jetons d'entrée observés (prompt + image d'origine) lors du benchmark initial.
OBSERVED_PROMPT_TOKENS = 3107
# Garde-fous mémoire (Mio de RAM disponible).
RAM_PREFLIGHT_MIN_MIB = 1500.0
RAM_STOP_MIN_MIB = 300.0
# Part du modèle hors VRAM observée (2 350 194 357 - 1 911 669 390 octets) : à
# réserver en plus si le modèle n'est pas encore chargé.
MODEL_RAM_ESTIMATE_MIB = 418.0
# Part du modèle en VRAM : 0,736 observé avec num_ctx=6144 ; 0,396 lors d'un
# chargement dégradé (appel à froid > 180 s). En dessous, on n'insiste pas.
MIN_GPU_SHARE = 0.70
PREVIEW_CHARS = 200

# Critères d'acceptation fixés AVANT le benchmark (faisabilité uniquement).
ACCEPTANCE = {
    "valid_schema_min_rate": 29 / 30,
    "done_stop_min_rate": 29 / 30,
    "latency_p50_max_s": 10.0,
    "latency_p95_max_s": 20.0,
    "ram_available_min_mib": 300.0,
    "vram_max_mib": 4096,
    "stability_min_field_agreement": 0.90,
}


class ModelMissing(RuntimeError):
    pass


class OutputExists(RuntimeError):
    pass


def build_options(num_predict=None, num_ctx=None, prompt_tokens=OBSERVED_PROMPT_TOKENS):
    """Options Ollama : celles du benchmark initial, sauf surcharge explicite.

    Refuse un contexte qui ne peut pas contenir l'entrée observée plus la sortie.
    """
    options = dict(OPTIONS)
    if num_predict is not None:
        options["num_predict"] = num_predict
    if num_ctx is not None:
        options["num_ctx"] = num_ctx
    if options["num_ctx"] < prompt_tokens + options["num_predict"]:
        raise ValueError(f"num_ctx={options['num_ctx']} < {prompt_tokens} jetons d'entrée observés "
                         f"+ num_predict={options['num_predict']}")
    return options


def model_loaded(ps_models, model):
    _, size, vram = gpu_share(ps_models, model)
    return size is not None, (size - vram) / 2**20 if size else None


def ram_preflight(available_mib, loaded, minimum=RAM_PREFLIGHT_MIN_MIB, model_estimate=MODEL_RAM_ESTIMATE_MIB):
    """Modèle déjà chargé : sa consommation est déjà déduite de la RAM disponible.
    Sinon, on réserve en plus sa part hors VRAM estimée."""
    required = minimum + (0.0 if loaded else model_estimate)
    return {"available_mib": available_mib, "model_loaded": loaded, "required_mib": required,
            "ok": available_mib is not None and available_mib >= required}


def low_ram(record, threshold=RAM_STOP_MIN_MIB):
    ram = record.get("ram_min_available_mib")
    return ram is not None and ram < threshold


def ensure_output_free(output_dir, filename):
    if (Path(output_dir) / filename).exists():
        raise OutputExists(f"{Path(output_dir) / filename} existe déjà : résultats conservés, rien n'est écrasé")


def load_selection(path=SELECTION_CSV):
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def ensure_model_present(client, model):
    names = {m.get("name") for m in client.tags()} | {m.get("model") for m in client.tags()}
    if model not in names:
        raise ModelMissing(f"modèle {model} absent localement : aucun téléchargement n'est effectué")


def call_plan(items, repeats, seed):
    """Ordre des appels à chaud : répétition par répétition, mélangé avec une graine fixe."""
    plan = []
    for rep in range(repeats):
        order = list(items)
        random.Random(seed + rep).shuffle(order)
        plan += [(rep, item) for item in order]
    return plan


def gpu_share(ps_models, model):
    for entry in ps_models:
        if entry.get("name") == model or entry.get("model") == model:
            size, vram = entry.get("size") or 0, entry.get("size_vram") or 0
            return (vram / size) if size else None, size, vram
    return None, None, None


def previews(text, n=PREVIEW_CHARS):
    """Longueur et extraits (début, fin) ; jamais le texte complet."""
    return {"chars": len(text), "head": text[:n], "tail": text[-n:] if len(text) > n else ""}


def run_call(client, model, item, phase, rep, images_root=DATA_HM_DIR, monitor_factory=ResourceMonitor,
             clock=time.perf_counter, options=None, image_bytes=None, messages_builder=build_messages):
    """`image_bytes` : image déjà préparée (ex. réduite en mémoire) ; sinon le fichier d'origine."""
    options = OPTIONS if options is None else options
    if image_bytes is None:
        image_bytes = (Path(images_root) / item["image_path"]).read_bytes()
    image_b64 = base64.b64encode(image_bytes).decode("ascii")
    record = {"article_id": item["article_id"], "phase": phase, "repeat": rep, "error": None}
    with monitor_factory() as monitor:
        start = clock()
        try:
            response = client.chat(model, messages_builder(image_b64), ollama_format_schema(), options, think=False)
        except requests.Timeout:
            response, record["error"] = None, "timeout"
        except requests.RequestException as error:
            response, record["error"] = None, f"http: {type(error).__name__}"
        record["wall_s"] = clock() - start
    record["vram_peak_mib"] = monitor.vram_peak_mib
    record["ram_min_available_mib"] = monitor.ram_min_available_mib
    if response is not None:
        message = response.get("message") or {}
        thinking = message.get("thinking") or ""
        content = message.get("content") or ""
        parsed, valid, attributes, problem = validate_response(content)
        content_p, thinking_p = previews(content), previews(thinking)
        record.update({
            "done_reason": response.get("done_reason"),
            "thinking_present": bool(thinking), "thinking_chars": len(thinking),
            "thinking_head": thinking_p["head"], "thinking_tail": thinking_p["tail"],
            "content_chars": content_p["chars"], "content_head": content_p["head"], "content_tail": content_p["tail"],
            "json_parsed": parsed, "schema_valid": valid, "validation_error": problem,
            "attributes": attributes,
            **{k: response.get(k) for k in ("total_duration", "load_duration", "prompt_eval_count",
                                            "prompt_eval_duration", "eval_count", "eval_duration")},
        })
    else:
        record.update({"done_reason": None, "thinking_present": False, "thinking_chars": 0, "content_chars": 0,
                       "json_parsed": False, "schema_valid": False, "validation_error": None, "attributes": None})
    try:
        share, size, vram = gpu_share(client.ps(), model)
    except requests.RequestException:
        share, size, vram = None, None, None
    record.update({"gpu_share": share, "loaded_size": size, "loaded_size_vram": vram})
    return record


def percentile(values, q):
    data = sorted(values)
    if not data:
        return None
    k = (len(data) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(data) - 1)
    return data[lo] + (data[hi] - data[lo]) * (k - lo)


def stability(records):
    """Par image et champ : part des répétitions égales à la valeur majoritaire."""
    by_item = collections.defaultdict(list)
    for r in records:
        if r["attributes"]:
            by_item[r["article_id"]].append(r["attributes"])
    field_agreement, identical = [], 0
    for answers in by_item.values():
        if len(answers) < 2:
            continue
        for field in DIMENSIONS:
            counts = collections.Counter(a[field] for a in answers)
            field_agreement.append(counts.most_common(1)[0][1] / len(answers))
        identical += all(a == answers[0] for a in answers)
    return {
        "items_compared": sum(1 for a in by_item.values() if len(a) >= 2),
        "mean_field_agreement": statistics.mean(field_agreement) if field_agreement else None,
        "items_fully_identical": identical,
    }


def summarize(warm):
    n = len(warm)
    ok_lat = [r["wall_s"] for r in warm if r["error"] is None]
    vram = [r["vram_peak_mib"] for r in warm if r["vram_peak_mib"] is not None]
    ram = [r["ram_min_available_mib"] for r in warm if r["ram_min_available_mib"] is not None]
    shares = [r["gpu_share"] for r in warm if r["gpu_share"] is not None]
    tok = [r["eval_count"] / (r["eval_duration"] / 1e9) for r in warm
           if r.get("eval_count") and r.get("eval_duration")]
    summary = {
        "calls": n,
        "errors": collections.Counter(r["error"] for r in warm if r["error"]),
        "json_parsed_rate": sum(r["json_parsed"] for r in warm) / n if n else None,
        "schema_valid_rate": sum(r["schema_valid"] for r in warm) / n if n else None,
        "done_stop_rate": sum(r["done_reason"] == "stop" for r in warm) / n if n else None,
        "thinking_present_calls": sum(r["thinking_present"] for r in warm),
        "latency_p50_s": percentile(ok_lat, 0.5), "latency_p95_s": percentile(ok_lat, 0.95),
        "latency_max_s": max(ok_lat) if ok_lat else None,
        "eval_tokens_per_s_median": statistics.median(tok) if tok else None,
        "vram_peak_mib": max(vram) if vram else None,
        "ram_min_available_mib": min(ram) if ram else None,
        "gpu_share_min": min(shares) if shares else None,
        "stability": stability(warm),
    }
    summary["errors"] = dict(summary["errors"])
    return summary


def acceptance(summary, criteria=ACCEPTANCE):
    def le(value, bound):
        return value is not None and value <= bound

    def ge(value, bound):
        return value is not None and value >= bound

    checks = {
        "schema_valid": ge(summary["schema_valid_rate"], criteria["valid_schema_min_rate"]),
        "done_stop": ge(summary["done_stop_rate"], criteria["done_stop_min_rate"]),
        "latency_p50": le(summary["latency_p50_s"], criteria["latency_p50_max_s"]),
        "latency_p95": le(summary["latency_p95_s"], criteria["latency_p95_max_s"]),
        "ram": ge(summary["ram_min_available_mib"], criteria["ram_available_min_mib"]),
        "vram": le(summary["vram_peak_mib"], criteria["vram_max_mib"]),
        "stability": ge(summary["stability"]["mean_field_agreement"], criteria["stability_min_field_agreement"]),
    }
    return {"checks": checks, "go_for_e2b": all(checks.values())}


def run(client, model, items, repeats, seed, images_root=DATA_HM_DIR, monitor_factory=ResourceMonitor,
        options=None):
    """Arrête toute nouvelle inférence dès qu'un appel a fait descendre la RAM
    disponible sous RAM_STOP_MIN_MIB, ou si le modèle s'est chargé surtout sur
    le CPU (part GPU < MIN_GPU_SHARE après l'appel à froid)."""
    ensure_model_present(client, model)
    cold = run_call(client, model, items[0], "cold", -1, images_root, monitor_factory, options=options)
    low_gpu = low_gpu_share(cold)
    warm, stopped = [], low_ram(cold)
    for rep, item in ([] if stopped or low_gpu else call_plan(items, repeats, seed)):
        warm.append(run_call(client, model, item, "warm", rep, images_root, monitor_factory, options=options))
        if low_ram(warm[-1]):
            stopped = True
            break
    summary = summarize(warm)
    summary["stopped_low_ram"] = stopped
    summary["stopped_low_gpu_share"] = low_gpu
    return cold, warm, summary, acceptance(summary)


def low_gpu_share(record, minimum=MIN_GPU_SHARE):
    share = record.get("gpu_share")
    return share is not None and share < minimum


def write_outputs(output_dir, client, model, items, cold, warm, summary, verdict, seed, repeats, options=None):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "results.jsonl").open("w", encoding="utf-8") as handle:
        for record in [cold] + warm:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    tag = next((m for m in client.tags() if m.get("name") == model or m.get("model") == model), {})
    metadata = {
        "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "model": model, "model_digest": tag.get("digest"), "model_size": tag.get("size"),
        "ollama_version": client.version(), "options": OPTIONS if options is None else options, "think": False, "repeats": repeats, "seed": seed,
        "taxonomy_version": TAXONOMY_VERSION, "taxonomy_sha256": taxonomy_fingerprint(),
        "prompt_sha256": prompt_fingerprint(), "selection_sha256": sha256_file(SELECTION_CSV),
        "images": {i["article_id"]: i["image_sha256"] for i in items},
        "python": platform.python_version(), "acceptance_criteria": ACCEPTANCE,
        "note": "Faisabilité uniquement : aucune exactitude n'est mesurée.",
    }
    (output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    (output_dir / "summary.json").write_text(json.dumps({"cold": {k: cold.get(k) for k in ("wall_s", "load_duration",
                                                                                              "error", "gpu_share")},
                                                         "warm": summary, "acceptance": verdict},
                                                        indent=2, ensure_ascii=False), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="qwen3-vl:2b")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--seed", type=int, default=20261016)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--host", default="http://localhost:11434")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--num-predict", type=int, default=None, help=f"défaut : {OPTIONS['num_predict']}")
    parser.add_argument("--num-ctx", type=int, default=None, help=f"défaut : {OPTIONS['num_ctx']}")
    args = parser.parse_args()
    try:
        options = build_options(args.num_predict, args.num_ctx)
        ensure_output_free(args.output_dir, "results.jsonl")
    except (ValueError, OutputExists) as error:
        sys.exit(str(error))
    client = OllamaClient(args.host, args.timeout)
    items = load_selection()
    check = ram_preflight(sample_ram_available_mib(), model_loaded(client.ps(), args.model)[0])
    if not check["ok"]:
        sys.exit(f"RAM insuffisante : {check['available_mib']:.0f} Mio < {check['required_mib']:.0f} Mio ; aucun appel")
    try:
        cold, warm, summary, verdict = run(client, args.model, items, args.repeats, args.seed, options=options)
    except ModelMissing as error:
        sys.exit(str(error))
    write_outputs(args.output_dir, client, args.model, items, cold, warm, summary, verdict, args.seed, args.repeats,
                  options)
    print(json.dumps({"warm": summary, "acceptance": verdict}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
