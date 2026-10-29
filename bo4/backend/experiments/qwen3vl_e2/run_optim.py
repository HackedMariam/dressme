"""Protocole d'optimisation E2 : 5 configurations x (1 appel de préparation + 5 images).

Un seul changement par configuration par rapport à la référence A0 :
    A0  image d'origine, num_ctx=6144                     (référence)
    A1  idem, modèle DÉCHARGÉ avant chaque image          (cache de prompt, RAM, reproductibilité)
    R1  image réduite à 896 px (grand côté), num_ctx=6144
    R2  image réduite à 640 px, num_ctx=6144
    C1  image 896 px, num_ctx=4096 (seulement si l'entrée mesurée en R1 + 2048 tient dans 4096)

Prompt, taxonomie, schéma et num_predict=2048 inchangés. Les images sources ne
sont jamais modifiées : la réduction se fait en mémoire (empreinte enregistrée).

Sécurité : modèle déchargé avant chaque configuration ; avant chaque inférence,
RAM >= 1 500 Mio (+418 si le modèle n'est pas chargé) pour un chargement, sinon
RAM >= 300 Mio et part GPU >= 70 % ; après chaque appel, arrêt si la RAM est
descendue sous 300 Mio ou si la part GPU est < 70 %. Tout échec arrête le
benchmark entier (aucun contournement). Exécution strictement séquentielle.

Usage (depuis backend/), après autorisation :
    .\\.venv\\Scripts\\python.exe -m experiments.qwen3vl_e2.run_optim
"""

import argparse
import collections
import datetime
import hashlib
import io
import json
import statistics
import sys
import time
from pathlib import Path

import psutil
from PIL import Image

from evaluation.common import DATA_HM_DIR, sha256_file
from experiments.qwen3vl_e2.monitor import ResourceMonitor, sample_ram_available_mib
from experiments.qwen3vl_e2.ollama_client import OllamaClient
from experiments.qwen3vl_e2 import prompt as prompt_v1, prompt_v2, prompt_v3
from experiments.qwen3vl_e2.prompt import prompt_fingerprint
from experiments.qwen3vl_e2.run_microbench import (
    MIN_GPU_SHARE, RAM_STOP_MIN_MIB, SELECTION_CSV, ModelMissing, build_options, ensure_model_present, gpu_share,
    load_selection, low_gpu_share, low_ram, model_loaded, percentile, ram_preflight, run_call)
from experiments.qwen3vl_e2.taxonomy import DIMENSIONS, TAXONOMY_VERSION, taxonomy_fingerprint

E2_DIR = Path(__file__).resolve().parent
OPTIM_DIR = E2_DIR / "output_optim"
NUM_PREDICT = 2048
NEAR_LIMIT = 1800
CACHE_HIT_MAX_S = 0.5
# Images mesurées : robe (raisonnement le plus long), pois, rayures, blazer uni, imprimé.
MEASURED = ("0801843006", "0781758009", "0840606004", "0783144006", "0698425001")
# Préparation (chargement) sur une image distincte, exclue des mesures.
WARMUP = "0706388001"
EXPERIMENTS = (
    {"name": "A0", "max_side": None, "num_ctx": 6144, "unload_between": False},
    {"name": "A1", "max_side": None, "num_ctx": 6144, "unload_between": True},
    {"name": "R1", "max_side": 896, "num_ctx": 6144, "unload_between": False},
    {"name": "R2", "max_side": 640, "num_ctx": 6144, "unload_between": False},
    {"name": "C1", "max_side": 896, "num_ctx": 4096, "unload_between": False, "prompt_tokens_from": "R1"},
)
# Confirmation : R1 + déchargement entre images, sur les 10 images de développement.
CONFIRM_DIR = E2_DIR / "output_optim_confirm"
PROMPT_V2_DIR = E2_DIR / "output_prompt_v2"
PROMPT_V3_DIR = E2_DIR / "output_prompt_v3"
PROMPTS = {"v1": prompt_v1, "v2": prompt_v2, "v3": prompt_v3}


def confirm_experiment(selection_ids, prompt="v1"):
    name = "R1U" if prompt == "v1" else f"R1U-P{prompt[1:]}"
    return {"name": name, "max_side": 896, "num_ctx": 6144, "unload_between": True,
            "measured": tuple(selection_ids), "prompt": prompt}


class SafetyStop(RuntimeError):
    pass


def prepare_image(path, max_side):
    """Octets envoyés au modèle ; réduction en mémoire, jamais sur disque."""
    data = Path(path).read_bytes()
    with Image.open(io.BytesIO(data)) as image:
        width, height = image.size
        if max_side is None or max(width, height) <= max_side:
            return data, {"width": width, "height": height, "resized": False,
                          "sha256": hashlib.sha256(data).hexdigest()}
        scale = max_side / max(width, height)
        size = (round(width * scale), round(height * scale))
        buffer = io.BytesIO()
        image.convert("RGB").resize(size, Image.LANCZOS).save(buffer, "JPEG", quality=95)
    out = buffer.getvalue()
    return out, {"width": size[0], "height": size[1], "resized": True, "sha256": hashlib.sha256(out).hexdigest()}


def ollama_memory_mib(process_iter=psutil.process_iter):
    """Mémoire résidente (working set) des processus Ollama, dont llama-server."""
    llama, total, found = 0, 0, False
    for proc in process_iter(["name", "memory_info"]):
        name = (proc.info.get("name") or "").lower()
        info = proc.info.get("memory_info")
        if info is None or not (name.startswith("llama-server") or name.startswith("ollama")):
            continue
        found = True
        total += info.rss
        if name.startswith("llama-server"):
            llama += info.rss
    if not found:
        return {"llama_server_mib": None, "ollama_total_mib": None}
    return {"llama_server_mib": llama / 2**20, "ollama_total_mib": total / 2**20}


def power_state():
    """Secteur ou batterie : influe sur la vitesse du GPU d'un portable."""
    battery = psutil.sensors_battery()
    return None if battery is None else {"percent": battery.percent, "plugged": battery.power_plugged}


def unload_and_wait(client, model, timeout_s=30.0, sleep=time.sleep, clock=time.monotonic):
    client.unload(model)
    deadline = clock() + timeout_s
    while model_loaded(client.ps(), model)[0]:
        if clock() > deadline:
            raise SafetyStop(f"le modèle {model} ne s'est pas déchargé en {timeout_s:.0f} s")
        sleep(0.5)


def check_before(client, model, ram_sampler):
    """Contrôle avant inférence. Modèle non chargé : marge de chargement ; sinon seuils d'arrêt."""
    ps = client.ps()
    loaded, _ = model_loaded(ps, model)
    ram = ram_sampler()
    if loaded:
        share = gpu_share(ps, model)[0]
        ok_ram = ram is not None and ram >= RAM_STOP_MIN_MIB
        ok_gpu = share is None or share >= MIN_GPU_SHARE
        return {"available_mib": ram, "model_loaded": True, "required_mib": RAM_STOP_MIN_MIB, "gpu_share": share,
                "ok": ok_ram and ok_gpu,
                "reason": None if ok_ram and ok_gpu else ("RAM" if not ok_ram else "part GPU")}
    check = ram_preflight(ram, False)
    return {**check, "gpu_share": None, "reason": None if check["ok"] else "RAM (chargement)"}


def run_experiment(client, model, exp, items, options, images_root=DATA_HM_DIR, monitor_factory=ResourceMonitor,
                   ram_sampler=sample_ram_available_mib, memory_sampler=ollama_memory_mib, unloader=unload_and_wait,
                   clock=time.perf_counter):
    """Renvoie (records, stop_reason, durée). Le modèle est déchargé au départ (configuration indépendante)."""
    by_id = {i["article_id"]: i for i in items}
    measured = exp.get("measured", MEASURED)
    sequence = [("warmup", WARMUP)] + [("cold_measured" if exp["unload_between"] else "warm", a) for a in measured]
    records, start = [], clock()
    unloader(client, model)
    for index, (phase, article_id) in enumerate(sequence):
        if exp["unload_between"] and index > 0:
            unloader(client, model)
        check = check_before(client, model, ram_sampler)
        if not check["ok"]:
            return records, f"{exp['name']} : contrôle avant {article_id} échoué ({check['reason']})", clock() - start
        item = by_id[article_id]
        image_bytes, image_info = prepare_image(Path(images_root) / item["image_path"], exp["max_side"])
        memory_before = memory_sampler()
        prompt = PROMPTS[exp.get("prompt", "v1")]
        record = run_call(client, model, item, phase, 0, images_root, monitor_factory, options=options,
                          image_bytes=image_bytes, messages_builder=prompt.build_messages)
        prompt_s = (record.get("prompt_eval_duration") or 0) / 1e9
        record.update({
            "experiment": exp["name"], "options": options, "prompt_version": prompt.PROMPT_VERSION, "image": image_info, "preflight": check,
            "memory_before": memory_before, "memory_after": memory_sampler(),
            "cache_hit": record.get("prompt_eval_duration") is not None and prompt_s < CACHE_HIT_MAX_S,
            "wall_minus_load_s": record["wall_s"] - (record.get("load_duration") or 0) / 1e9,
        })
        records.append(record)
        if low_ram(record):
            return records, f"{exp['name']} : RAM sous {RAM_STOP_MIN_MIB:.0f} Mio pendant {article_id}", clock() - start
        if low_gpu_share(record):
            return records, f"{exp['name']} : part GPU {record['gpu_share']:.3f} < {MIN_GPU_SHARE}", clock() - start
    return records, None, clock() - start


def summarize_experiment(records, duration_s=None):
    measured = [r for r in records if r["phase"] != "warmup"]
    ok = [r for r in measured if r["error"] is None]
    rates = [r["eval_count"] / (r["eval_duration"] / 1e9) for r in ok if r.get("eval_count") and r.get("eval_duration")]
    walls = [r["wall_s"] for r in ok]
    def values(key, rows=records):
        return [r[key] for r in rows if r.get(key) is not None]
    llama_after = [r["memory_after"]["llama_server_mib"] for r in records
                   if r["memory_after"]["llama_server_mib"] is not None]
    return {
        "measured_calls": len(measured), "warmup_calls": len(records) - len(measured),
        "errors": [r["error"] for r in measured if r["error"]],
        "schema_valid": sum(r["schema_valid"] for r in measured),
        "done_stop": sum(r["done_reason"] == "stop" for r in measured),
        "near_limit": sum((r.get("eval_count") or 0) >= NEAR_LIMIT for r in measured),
        "prompt_eval_count": sorted(set(values("prompt_eval_count", measured))),
        "eval_count": values("eval_count", measured),
        "thinking_chars": values("thinking_chars", measured),
        "latency_p50_s": percentile(walls, 0.5), "latency_p95_s": percentile(walls, 0.95),
        "wall_minus_load_p50_s": percentile(values("wall_minus_load_s", ok), 0.5),
        "load_s": [round((r.get("load_duration") or 0) / 1e9, 2) for r in measured],
        "eval_tokens_per_s_median": statistics.median(rates) if rates else None,
        "ram_min_available_mib": min(values("ram_min_available_mib"), default=None),
        "vram_peak_mib": max(values("vram_peak_mib"), default=None),
        "gpu_share_min": min(values("gpu_share"), default=None),
        "llama_server_mib_first_before": records[0]["memory_before"]["llama_server_mib"] if records else None,
        "llama_server_mib_after": llama_after,
        "cache_hits": sum(r["cache_hit"] for r in measured),
        "total_duration_s": duration_s,
    }


def compare_to_reference(all_records, reference="A0"):
    """Nombre de champs identiques à la référence, par image ; NOMS des champs différents uniquement."""
    attrs = collections.defaultdict(dict)
    for r in all_records:
        if r["phase"] != "warmup" and r.get("attributes"):
            attrs[r["experiment"]][r["article_id"]] = r["attributes"]
    out = {}
    for exp, by_item in attrs.items():
        if exp == reference:
            continue
        rows = {}
        for article_id, values in by_item.items():
            ref = attrs.get(reference, {}).get(article_id)
            if ref is None:
                continue
            diff = [d for d in DIMENSIONS if values[d] != ref[d]]
            rows[article_id] = {"identical_fields": len(DIMENSIONS) - len(diff), "differing_fields": diff}
        total = sum(v["identical_fields"] for v in rows.values())
        out[exp] = {"by_item": rows, "identical_fields": total, "compared_fields": len(rows) * len(DIMENSIONS)}
    return out


def options_for(exp, results):
    """C1 dépend de l'entrée MESURÉE en R1 ; refus explicite si elle ne tient pas."""
    source = exp.get("prompt_tokens_from")
    if source is None:
        return build_options(NUM_PREDICT, exp["num_ctx"])
    measured = [c for c in results.get(source, {}).get("summary", {}).get("prompt_eval_count", []) if c]
    if not measured:
        raise ValueError(f"{exp['name']} : entrée de {source} non mesurée")
    return build_options(NUM_PREDICT, exp["num_ctx"], prompt_tokens=max(measured))


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def run_all(client, model, items, output_dir, experiments=EXPERIMENTS, **kwargs):
    output_dir = Path(output_dir)
    ensure_model_present(client, model)
    results, all_records, stop_reason = {}, [], None
    for exp in experiments:
        try:
            options = options_for(exp, results)
        except ValueError as error:
            results[exp["name"]] = {"skipped": str(error)}
            write_json(output_dir / exp["name"] / "summary.json", results[exp["name"]])
            continue
        records, stop_reason, duration = run_experiment(client, model, exp, items, options, **kwargs)
        all_records += records
        summary = {**summarize_experiment(records, duration), "config": exp, "options": options,
                   "stop_reason": stop_reason}
        results[exp["name"]] = {"summary": summary}
        exp_dir = output_dir / exp["name"]
        exp_dir.mkdir(parents=True, exist_ok=True)
        with (exp_dir / "results.jsonl").open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        write_json(exp_dir / "summary.json", summary)
        if stop_reason:
            break
    comparison = compare_to_reference(all_records)
    write_json(output_dir / "comparison.json", {"stop_reason": stop_reason, "vs_A0": comparison,
                                                "summaries": {k: v.get("summary", v) for k, v in results.items()}})
    return results, comparison, stop_reason


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="qwen3-vl:2b")
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--host", default="http://localhost:11434")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--confirm", action="store_true",
                        help="R1 + déchargement entre images sur les 10 images de développement")
    parser.add_argument("--prompt-v2", action="store_true",
                        help="comme --confirm, avec le prompt e2-prompt/2")
    parser.add_argument("--prompt-v3", action="store_true",
                        help="comme --confirm, avec le prompt e2-prompt/3")
    args = parser.parse_args()
    if args.output_dir is None:
        args.output_dir = (PROMPT_V3_DIR if args.prompt_v3 else PROMPT_V2_DIR if args.prompt_v2
                           else CONFIRM_DIR if args.confirm else OPTIM_DIR)
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        sys.exit(f"{args.output_dir} existe déjà : résultats conservés, rien n'est écrasé")
    selection = {i["article_id"]: i for i in load_selection()}
    if args.prompt_v2 and args.prompt_v3:
        sys.exit("choisir --prompt-v2 OU --prompt-v3")
    if args.prompt_v3:
        experiments = (confirm_experiment(selection, "v3"),)
    elif args.prompt_v2:
        experiments = (confirm_experiment(selection, "v2"),)
    elif args.confirm:
        experiments = (confirm_experiment(selection),)
    else:
        experiments = EXPERIMENTS
    measured_ids = tuple(dict.fromkeys(a for exp in experiments for a in exp.get("measured", MEASURED)))
    items = [selection[a] for a in dict.fromkeys((WARMUP, *measured_ids))]
    client = OllamaClient(args.host, args.timeout)
    tag = next((m for m in client.tags() if m.get("name") == args.model or m.get("model") == args.model), {})
    write_json(args.output_dir / "metadata.json", {
        "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "model": args.model, "model_digest": tag.get("digest"), "ollama_version": client.version(),
        "experiments": experiments, "measured": measured_ids, "warmup": WARMUP, "num_predict": NUM_PREDICT,
        "think": False, "timeout_s": args.timeout, "images": {i["article_id"]: i["image_sha256"] for i in items},
        "taxonomy_version": TAXONOMY_VERSION, "taxonomy_sha256": taxonomy_fingerprint(),
        "prompt_sha256": prompt_fingerprint(),
        "prompts": {e["name"]: {"version": PROMPTS[e.get("prompt", "v1")].PROMPT_VERSION,
                                "sha256": PROMPTS[e.get("prompt", "v1")].prompt_fingerprint()} for e in experiments},
        "selection_sha256": sha256_file(SELECTION_CSV),
        "safety": {"ram_stop_mib": RAM_STOP_MIN_MIB, "min_gpu_share": MIN_GPU_SHARE},
        "power_start": power_state(),
        "note": "Optimisation de faisabilité : aucune exactitude n'est mesurée.",
    })
    try:
        results, comparison, stop_reason = run_all(client, args.model, items, args.output_dir, experiments)
    except (ModelMissing, SafetyStop) as error:
        sys.exit(str(error))
    finally:
        try:
            client.unload(args.model)               # libère la RAM à la fin, même après un arrêt
        except Exception:                           # noqa: BLE001 - le déchargement final est best effort
            pass
    write_json(args.output_dir / "power_end.json", power_state())
    print(json.dumps({"stop_reason": stop_reason,
                      "summaries": {k: v.get("summary", v) for k, v in results.items()}},
                     indent=2, ensure_ascii=False, default=str))
    if stop_reason:
        sys.exit(f"arrêt de sécurité : {stop_reason}")


if __name__ == "__main__":
    main()
