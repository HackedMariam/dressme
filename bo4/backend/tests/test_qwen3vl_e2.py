"""Tests E2 (Qwen3-VL 2B) sans Ollama ni base de données.

Un faux client remplace le serveur Ollama : aucun appel réseau, aucun modèle
chargé. Ces tests ne mesurent aucune qualité.
"""

import csv
import json
import re
from pathlib import Path

import pytest
import requests
from PIL import Image

from evaluation.common import OUTPUT_DIR as EVALUATION_DIR, sha256_file
from experiments.qwen3vl_e2 import (metadata_mapping, prompt, run_microbench, run_mini_bench, run_single_check,
                                    select_images)
from experiments.qwen3vl_e2.monitor import ResourceMonitor
from experiments.qwen3vl_e2.ollama_client import OllamaClient
from experiments.qwen3vl_e2.schema import GarmentAttributes, ollama_format_schema, validate_response
from experiments.qwen3vl_e2.taxonomy import DIMENSIONS, EXPLORATORY, ORDINAL, RULES, values

E2_DIR = Path(run_microbench.__file__).resolve().parent
VALID = {"category": "dress", "primary_color": "burgundy", "pattern": "floral", "material_appearance": "lace",
         "fit": "fitted", "style": "romantic_boho", "formality": "smart_casual", "thickness": "light",
         "certainty": "medium"}


# ---------------------------------------------------------------------------
# Taxonomie et schéma
# ---------------------------------------------------------------------------

def test_taxonomy_values_are_unique_and_documented():
    for name, spec in DIMENSIONS.items():
        ids = list(spec["values"])
        assert len(ids) == len(set(ids)) >= 3
        assert all(re.fullmatch(r"[a-z_]+", v) for v in ids)
        assert spec["label_fr"] and spec["question"]
    for dim, order in ORDINAL.items():
        assert set(order) <= set(values(dim))
    assert EXPLORATORY == {"style"}


def test_rules_state_independence_and_no_formality_from_category():
    text = " ".join(RULES)
    assert "pattern=floral AND material_appearance=lace" in text
    assert "Never infer formality from the category" in text


def test_schema_is_strict():
    schema = ollama_format_schema()
    assert set(schema["required"]) == set(DIMENSIONS)
    assert schema.get("additionalProperties") is False
    for name in DIMENSIONS:
        assert set(schema["properties"][name]["enum"]) == set(values(name))


def test_validator_accepts_independent_pattern_and_material():
    parsed, valid, attributes, error = validate_response(json.dumps(VALID))
    assert (parsed, valid, error) == (True, True, None)
    assert attributes["pattern"] == "floral" and attributes["material_appearance"] == "lace"


@pytest.mark.parametrize("payload, parsed_expected", [
    ({k: v for k, v in VALID.items() if k != "fit"}, True),          # champ manquant
    ({**VALID, "comment": "x"}, True),                                # champ en trop
    ({**VALID, "pattern": "lace"}, True),                             # valeur hors énumération
    ({**VALID, "formality": "habille"}, True),                        # ancien libellé E1 refusé
])
def test_validator_rejects_non_conforming(payload, parsed_expected):
    parsed, valid, attributes, error = validate_response(json.dumps(payload))
    assert parsed is parsed_expected and valid is False and attributes is None and error


@pytest.mark.parametrize("text", ["", "{", '{"category": "dress"', "not json", None])
def test_validator_rejects_invalid_json(text):
    parsed, valid, attributes, error = validate_response(text)
    assert (parsed, valid, attributes) == (False, False, None) and error


def test_prompt_contains_schema_rules_and_is_stable():
    system = prompt.system_prompt()
    assert json.dumps(ollama_format_schema(), sort_keys=True) in system
    assert all(rule in system for rule in RULES)
    assert prompt.prompt_fingerprint() == prompt.prompt_fingerprint()
    messages = prompt.build_messages("AAAA")
    assert messages[1]["images"] == ["AAAA"]


# ---------------------------------------------------------------------------
# Sélection des images
# ---------------------------------------------------------------------------

def _pool(n_groups=("Menswear", "Baby/Children")):
    patterns = ["Solid", "Stripe", "Check", "Dot", "Denim", "Melange", "Front print", "Slub"]
    roles = ["top", "bottom", "outerwear", "dress"]
    pool = []
    for i in range(24):
        pool.append({"article_id": f"09{i:08d}", "image_path": f"images/090/09{i:08d}.jpg",
                     "product_type_name": "X", "role": roles[i % 4], "index_group_name": n_groups[i % len(n_groups)],
                     "graphical_appearance_name": patterns[i % len(patterns)], "colour_group_name": "Black"})
    return pool


def test_selection_is_deterministic_and_diverse():
    a, _, problems_a = select_images.select(_pool(), seed=1)
    b, _, _ = select_images.select(_pool(), seed=1)
    assert [x["article_id"] for x in a] == [x["article_id"] for x in b]
    assert len(a) == 10 and problems_a == []
    assert len({x["graphical_appearance_name"] for x in a}) >= select_images.MIN_PATTERNS
    assert len({x["role"] for x in a}) >= select_images.MIN_ROLES


def test_selection_includes_required_patterns_and_caps_outerwear():
    chosen, reasons, problems = select_images.select(_pool(), seed=1)
    patterns = {x["graphical_appearance_name"] for x in chosen}
    assert set(select_images.REQUIRED_PATTERNS) <= patterns
    assert sum(x["role"] == "outerwear" for x in chosen) <= select_images.MAX_OUTERWEAR
    assert problems == []


def test_missing_required_pattern_is_reported_not_invented():
    pool = [item for item in _pool() if item["graphical_appearance_name"] != "Dot"]
    chosen, _, problems = select_images.select(pool, seed=1)
    assert "Dot" not in {x["graphical_appearance_name"] for x in chosen}
    assert "motif requis Dot indisponible" in problems


def test_outerwear_cap_lifted_only_when_nothing_else_remains():
    pool = [{**item, "role": "outerwear"} for item in _pool()[:4]] + \
           [{**item, "role": "top"} for item in _pool()[4:6]]
    chosen, _, problems = select_images.select(pool, seed=1, size=6)
    assert len(chosen) == 6
    assert any("plafond" in p for p in problems)


def test_selection_prefers_adults():
    chosen, _, _ = select_images.select(_pool(), seed=3)
    adults = sum(x["index_group_name"] == "Menswear" for x in chosen)
    assert adults >= 7


def test_selection_reports_insufficient_diversity_without_inventing():
    pool = [{**item, "graphical_appearance_name": "Solid", "role": "top"} for item in _pool()[:5]]
    chosen, _, problems = select_images.select(pool, seed=1)
    assert len(chosen) == 5
    assert any("seulement 5" in p for p in problems)
    assert any("motifs" in p for p in problems) and any("rôles" in p for p in problems)


def test_candidates_exclude_e1_and_other_segments(tmp_path):
    images = tmp_path / "hm"
    (images / "images/090").mkdir(parents=True)
    for name in ("0900000001", "0900000002", "0900000003", "0900000004"):
        Image.new("RGB", (8, 12), "white").save(images / f"images/090/{name}.jpg", "JPEG")
    rows = [{"article_id": a, "image_path": f"images/090/{a}.jpg", "product_type_name": "Shirt",
             "colour_group_name": "Black"} for a in ("0900000001", "0900000002", "0900000003", "0900000004")]
    articles = {"0900000001": {"index_group_name": "Menswear"}, "0900000002": {"index_group_name": "Menswear"},
                "0900000003": {"index_group_name": "Ladieswear"}, "0900000004": {"index_group_name": "Baby/Children"}}
    kept, bad = select_images.candidates(rows, articles, excluded={"0900000002"}, images_root=images)
    assert [k["article_id"] for k in kept] == ["0900000001", "0900000004"]   # E1 exclu, femme exclue
    assert bad == []


def test_real_selection_excludes_every_e1_image():
    selection = E2_DIR / "data" / "microbench_e2.csv"
    if not selection.is_file():
        pytest.skip("sélection non générée")
    rows = list(csv.DictReader(open(selection, encoding="utf-8")))
    e1 = select_images.e1_article_ids()
    assert len(e1) == 36
    assert not ({r["article_id"] for r in rows} & e1)
    assert all(r["split"] == "e2_microbench_dev" for r in rows)
    splits = json.loads((E2_DIR / "data" / "splits.json").read_text(encoding="utf-8"))
    assert set(splits["e1_test_sealed"]) == e1
    assert not (set(splits["e1_test_sealed"]) & set(splits["e2_microbench_dev"]))
    for r in rows:
        image = select_images.DATA_HM_DIR / r["image_path"]
        assert image.is_file() and sha256_file(image) == r["image_sha256"]


# ---------------------------------------------------------------------------
# Correspondance des métadonnées H&M
# ---------------------------------------------------------------------------

def test_metadata_mapping_uses_taxonomy_values_only():
    for pattern, material in metadata_mapping.GRAPHICAL_APPEARANCE.values():
        assert pattern is None or pattern in values("pattern")
        assert material is None or material in values("material_appearance")
    assert set(metadata_mapping.COLOUR_GROUP.values()) <= set(values("primary_color"))
    assert set(metadata_mapping.PRODUCT_TYPE.values()) <= set(values("category"))
    assert metadata_mapping.map_article({"graphical_appearance_name": "Melange"})["pattern"] is None


# ---------------------------------------------------------------------------
# Exécution avec un faux client Ollama
# ---------------------------------------------------------------------------

class FakeMonitor:
    def __init__(self, vram=2500, ram=900.0):
        self.vram_peak_mib, self.ram_min_available_mib = vram, ram

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeClient:
    """Réponses scriptées ; ne fait aucun appel réseau."""

    def __init__(self, behaviours, models=("qwen3-vl:2b",), loaded=True):
        self.behaviours = list(behaviours)
        self.models = models
        self.loaded = loaded
        self.chat_calls = 0
        self.options_seen = []

    def tags(self):
        return [{"name": m, "model": m, "digest": "sha256:fake", "size": 1} for m in self.models]

    def version(self):
        return "fake"

    def ps(self):
        return [{"name": "qwen3-vl:2b", "size": 2400, "size_vram": 1944}] if self.loaded else []

    def show(self, model):
        return {"capabilities": ["completion", "vision", "thinking"], "template": "{{ if .Think }}x{{ end }}",
                "details": {"parameter_size": "2B"}, "model_info": {"qwen3vl.context_length": 262144}}

    def chat(self, model, messages, format_schema, options, think=False, keep_alive="10m"):
        assert options["temperature"] == 0 and think is False and format_schema == ollama_format_schema()
        self.options_seen.append(dict(options))
        behaviour = self.behaviours[self.chat_calls % len(self.behaviours)]
        self.chat_calls += 1
        if isinstance(behaviour, Exception):
            raise behaviour
        return behaviour


def _response(content, done="stop", thinking=""):
    return {"message": {"content": content, "thinking": thinking}, "done_reason": done,
            "total_duration": 5e9, "load_duration": 1e8, "prompt_eval_count": 900, "prompt_eval_duration": 2e9,
            "eval_count": 80, "eval_duration": 2e9}


@pytest.fixture
def items(tmp_path):
    root = tmp_path / "hm"
    (root / "images/090").mkdir(parents=True)
    out = []
    for i in range(3):
        path = f"images/090/090000000{i}.jpg"
        Image.new("RGB", (8, 12), "white").save(root / path, "JPEG")
        out.append({"article_id": f"090000000{i}", "image_path": path, "image_sha256": "x"})
    return root, out


def test_run_counts_errors_without_stopping(items):
    root, selection = items
    behaviours = [
        _response(json.dumps(VALID)),                                   # cold
        _response(json.dumps(VALID)),
        _response(json.dumps(VALID), thinking="hidden reasoning"),      # thinking ignoré mais compté
        _response('{"category": "dress"', done="length"),               # tronqué
        requests.Timeout(),
        requests.ConnectionError(),
        _response(json.dumps({**VALID, "extra": 1})),                   # non conforme
    ]
    client = FakeClient(behaviours)
    cold, warm, summary, verdict = run_microbench.run(client, "qwen3-vl:2b", selection, repeats=2, seed=0,
                                                      images_root=root, monitor_factory=FakeMonitor)
    assert len(warm) == 6 and summary["calls"] == 6
    assert summary["errors"] == {"timeout": 1, "http: ConnectionError": 1}
    assert summary["thinking_present_calls"] == 1
    assert summary["schema_valid_rate"] == pytest.approx(2 / 6)
    assert summary["json_parsed_rate"] == pytest.approx(3 / 6)
    assert verdict["checks"]["schema_valid"] is False and verdict["go_for_e2b"] is False
    assert all(r["gpu_share"] == pytest.approx(1944 / 2400) for r in warm)


def test_run_all_valid_passes_feasibility_checks(items):
    root, selection = items
    client = FakeClient([_response(json.dumps(VALID))])
    cold, warm, summary, verdict = run_microbench.run(client, "qwen3-vl:2b", selection, repeats=3, seed=0,
                                                      images_root=root, monitor_factory=FakeMonitor)
    assert summary["schema_valid_rate"] == 1.0 and summary["done_stop_rate"] == 1.0
    assert summary["stability"]["mean_field_agreement"] == 1.0
    assert summary["stability"]["items_fully_identical"] == 3
    assert verdict["checks"]["schema_valid"] and verdict["checks"]["stability"] and verdict["checks"]["vram"]


def test_missing_model_aborts_without_download(items):
    root, selection = items
    client = FakeClient([_response(json.dumps(VALID))], models=("qwen2.5:3b",))
    with pytest.raises(run_microbench.ModelMissing):
        run_microbench.run(client, "qwen3-vl:2b", selection, 1, 0, images_root=root, monitor_factory=FakeMonitor)
    assert client.chat_calls == 0


def test_client_refuses_non_local_host_and_has_no_pull():
    with pytest.raises(ValueError):
        OllamaClient("https://ollama.example.com")
    assert not hasattr(OllamaClient, "pull")
    source = Path(run_microbench.__file__).with_name("ollama_client.py").read_text(encoding="utf-8")
    assert '"/api/pull"' not in source and "'/api/pull'" not in source     # jamais utilisé comme URL


def test_metrics_helpers():
    assert run_microbench.percentile([1, 2, 3, 4], 0.5) == pytest.approx(2.5)
    assert run_microbench.percentile([5.0], 0.95) == 5.0
    assert run_microbench.percentile([], 0.5) is None
    records = [{"article_id": "a", "attributes": VALID}, {"article_id": "a", "attributes": {**VALID, "fit": "regular"}},
               {"article_id": "a", "attributes": VALID}]
    result = run_microbench.stability(records)
    assert result["items_compared"] == 1 and result["items_fully_identical"] == 0
    assert result["mean_field_agreement"] == pytest.approx((8 + 2 / 3) / 9)
    plan = run_microbench.call_plan(["x", "y", "z"], 2, 0)
    assert len(plan) == 6 and sorted(i for r, i in plan if r == 0) == ["x", "y", "z"]


# ---------------------------------------------------------------------------
# Diagnostic : options, extraits, garde-fous mémoire, test sur une image
# ---------------------------------------------------------------------------

def test_default_options_are_the_initial_benchmark_ones():
    assert run_microbench.build_options() == {"temperature": 0, "seed": 0, "num_ctx": 4096, "num_predict": 256}
    assert run_microbench.build_options(2048, 6144) == {"temperature": 0, "seed": 0, "num_ctx": 6144,
                                                         "num_predict": 2048}
    assert run_microbench.OPTIONS["num_predict"] == 256          # constante initiale inchangée


def test_context_too_small_for_input_plus_output_is_refused():
    with pytest.raises(ValueError):
        run_microbench.build_options(2048)                       # 3107 + 2048 > 4096
    with pytest.raises(ValueError):
        run_microbench.build_options(2048, 5000)


def test_run_call_passes_options_and_records_previews(items):
    root, selection = items
    thinking = "a" * 150 + "b" * 300
    client = FakeClient([_response(json.dumps(VALID), thinking=thinking)])
    options = run_microbench.build_options(2048, 6144)
    record = run_microbench.run_call(client, "qwen3-vl:2b", selection[0], "single_check", 0, root, FakeMonitor,
                                     options=options)
    assert client.options_seen == [options]
    assert record["thinking_chars"] == 450 and record["thinking_head"] == "a" * 150 + "b" * 50
    assert record["thinking_tail"] == "b" * 200
    content = json.dumps(VALID)                                  # 219 caractères > 200
    assert record["content_chars"] == len(content) and record["content_tail"] == content[-200:]
    assert record["schema_valid"] is True


def test_previews_never_store_full_long_text():
    p = run_microbench.previews("x" * 1000)
    assert p["chars"] == 1000 and len(p["head"]) == len(p["tail"]) == run_microbench.PREVIEW_CHARS
    assert run_microbench.previews("") == {"chars": 0, "head": "", "tail": ""}


def test_ram_preflight_accounts_for_model_load():
    assert run_microbench.ram_preflight(1600, loaded=True)["ok"] is True
    unloaded = run_microbench.ram_preflight(1600, loaded=False)
    assert unloaded["ok"] is False and unloaded["required_mib"] == pytest.approx(1500 + 418)
    assert run_microbench.ram_preflight(1499, loaded=True)["ok"] is False
    assert run_microbench.ram_preflight(None, loaded=True)["ok"] is False
    loaded, model_ram = run_microbench.model_loaded([{"name": "m", "size": 3 * 2**20, "size_vram": 2**20}], "m")
    assert loaded and model_ram == pytest.approx(2.0)
    assert run_microbench.model_loaded([], "m") == (False, None)


def test_run_stops_new_inference_when_ram_drops_below_300(items):
    root, selection = items
    rams = iter([900.0, 900.0, 250.0, 900.0, 900.0])
    client = FakeClient([_response(json.dumps(VALID))])
    cold, warm, summary, verdict = run_microbench.run(client, "qwen3-vl:2b", selection, repeats=2, seed=0,
                                                      images_root=root,
                                                      monitor_factory=lambda: FakeMonitor(ram=next(rams)))
    assert client.chat_calls == 3 and len(warm) == 2 and summary["stopped_low_ram"] is True
    assert verdict["go_for_e2b"] is False


def test_low_ram_cold_call_prevents_warm_calls(items):
    root, selection = items
    client = FakeClient([_response(json.dumps(VALID))])
    _, warm, summary, _ = run_microbench.run(client, "qwen3-vl:2b", selection, 1, 0, images_root=root,
                                             monitor_factory=lambda: FakeMonitor(ram=100.0))
    assert client.chat_calls == 1 and warm == [] and summary["stopped_low_ram"] is True


def test_existing_results_are_never_overwritten(tmp_path):
    run_microbench.ensure_output_free(tmp_path, "results.jsonl")
    (tmp_path / "results.jsonl").write_text("{}", encoding="utf-8")
    with pytest.raises(run_microbench.OutputExists):
        run_microbench.ensure_output_free(tmp_path, "results.jsonl")
    run_microbench.ensure_output_free(run_microbench.OUTPUT_DIR, "absent.json")
    with pytest.raises(run_microbench.OutputExists):            # le benchmark initial est protégé
        run_microbench.ensure_output_free(run_microbench.OUTPUT_DIR, "results.jsonl")


def test_single_check_skips_inference_when_ram_insufficient(items):
    root, selection = items
    client = FakeClient([_response(json.dumps(VALID))], loaded=False)
    report = run_single_check.single_check(client, "qwen3-vl:2b", selection[0],
                                           run_microbench.build_options(2048, 6144), root, FakeMonitor,
                                           ram_sampler=lambda: 1700.0)          # < 1500 + 418
    assert report["inference_done"] is False and client.chat_calls == 0
    assert report["show"]["capabilities"] == ["completion", "vision", "thinking"]
    assert report["show"]["template_mentions_think"] is True and "template" not in report["show"]


def test_single_check_makes_exactly_one_call(items):
    root, selection = items
    client = FakeClient([_response("", done="length", thinking="t" * 900)])
    options = run_microbench.build_options(2048, 6144)
    report = run_single_check.single_check(client, "qwen3-vl:2b", selection[0], options, root,
                                           lambda: FakeMonitor(ram=250.0), ram_sampler=lambda: 2000.0)
    assert client.chat_calls == 1 and report["inference_done"] is True
    assert report["result"]["done_reason"] == "length" and report["result"]["json_parsed"] is False
    assert report["stop_further_inference"] is True and report["eval_count_hit_limit"] is False
    assert report["preflight"]["model_loaded"] is True


def test_refused_preflight_does_not_block_a_later_check():
    meta = {"created_utc": "2026-10-15T17:20:02+00:00"}
    assert run_single_check.result_filename({"inference_done": True, "metadata": meta}) == "single_check.json"
    refused = run_single_check.result_filename({"inference_done": False, "metadata": meta})
    assert refused == "preflight_refused_2026-10-15T172002Z.json"


def test_single_check_output_dir_is_separate_from_initial_benchmark():
    assert run_single_check.SINGLE_OUTPUT_DIR != run_microbench.OUTPUT_DIR
    assert run_single_check.SINGLE_OUTPUT_DIR.name == "output_single_check"


def test_monitor_samples_once_per_second_by_default():
    assert ResourceMonitor().interval == 1.0


def test_client_show_posts_without_inference():
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"capabilities": []}

    class Session:
        def post(self, url, json, timeout):
            self.url, self.payload = url, json
            return Response()

    session = Session()
    assert OllamaClient(session=session).show("qwen3-vl:2b") == {"capabilities": []}
    assert session.url.endswith("/api/show") and session.payload == {"model": "qwen3-vl:2b"}


# ---------------------------------------------------------------------------
# Mini-benchmark : 3 images, un appel chacune
# ---------------------------------------------------------------------------

def test_mini_default_images_are_three_new_roles_of_the_selection():
    items = run_mini_bench.pick_items(run_microbench.load_selection(), list(run_mini_bench.DEFAULT_ARTICLES))
    assert len(items) == 3 and "0840606004" not in run_mini_bench.DEFAULT_ARTICLES
    assert {i["role"] for i in items} == {"top", "outerwear", "dress"}
    assert len({i["graphical_appearance_name"] for i in items}) == 3


@pytest.mark.parametrize("ids", [["0781758009", "0781758009"], [], ["a", "b", "c", "d"], ["0000000000"]])
def test_mini_pick_items_rejects_bad_requests(ids):
    with pytest.raises(ValueError):
        run_mini_bench.pick_items(run_microbench.load_selection(), ids)


def test_mini_bench_makes_one_call_per_image_with_wide_options(items):
    root, selection = items
    client = FakeClient([_response(json.dumps(VALID))])
    options = run_microbench.build_options(2048, 6144)
    preflights, records, stop = run_mini_bench.mini_bench(client, "qwen3-vl:2b", selection, options, root,
                                                          FakeMonitor, ram_sampler=lambda: 2000.0)
    assert client.chat_calls == 3 and len(preflights) == 3 and stop is None
    assert client.options_seen == [options] * 3
    assert [r["article_id"] for r in records] == [i["article_id"] for i in selection]
    summary = run_mini_bench.summarize_mini(records, options, 3)
    assert summary["done_stop"] == summary["schema_valid"] == 3 and summary["eval_count_hit_limit"] == 0
    assert summary["wall_minus_load_s"] == pytest.approx([r["wall_s"] - 0.1 for r in records])
    assert summary["eval_tokens_per_s"] == pytest.approx([40.0] * 3)


def test_mini_bench_stops_when_a_preflight_fails(items):
    root, selection = items
    rams = iter([2500.0, 1000.0, 2500.0])
    client = FakeClient([_response(json.dumps(VALID))])
    preflights, records, stop = run_mini_bench.mini_bench(client, "qwen3-vl:2b", selection,
                                                          run_microbench.build_options(2048, 6144), root,
                                                          FakeMonitor, ram_sampler=lambda: next(rams))
    assert client.chat_calls == 1 and len(preflights) == 2 and preflights[1]["ok"] is False
    assert stop.startswith("contrôle RAM échoué")


def test_mini_bench_requires_extra_margin_when_model_not_loaded(items):
    root, selection = items
    client = FakeClient([_response(json.dumps(VALID))], loaded=False)
    preflights, records, stop = run_mini_bench.mini_bench(client, "qwen3-vl:2b", selection,
                                                          run_microbench.build_options(2048, 6144), root,
                                                          FakeMonitor, ram_sampler=lambda: 1700.0)
    assert client.chat_calls == 0 and records == [] and preflights[0]["required_mib"] == pytest.approx(1918)


def test_mini_bench_stops_after_a_call_below_300_mib(items):
    root, selection = items
    client = FakeClient([_response("", done="length", thinking="t" * 50)])
    options = run_microbench.build_options(2048, 6144)
    preflights, records, stop = run_mini_bench.mini_bench(client, "qwen3-vl:2b", selection, options, root,
                                                          lambda: FakeMonitor(ram=250.0), ram_sampler=lambda: 2000.0)
    assert client.chat_calls == 1 and stop.startswith("RAM sous 300 Mio")
    summary = run_mini_bench.summarize_mini(records, options, 3)
    assert summary["calls"] == 1 and summary["planned_calls"] == 3 and summary["schema_valid"] == 0
    assert summary["indicative_vs_acceptance"]["ram_ok"] is False


def test_run_stops_after_cold_call_when_model_mostly_on_cpu(items):
    root, selection = items

    class CpuHeavyClient(FakeClient):
        def ps(self):
            return [{"name": "qwen3-vl:2b", "size": 2548, "size_vram": 1010}]      # 0,396 observé

    client = CpuHeavyClient([_response(json.dumps(VALID))])
    cold, warm, summary, verdict = run_microbench.run(client, "qwen3-vl:2b", selection, 3, 0, images_root=root,
                                                      monitor_factory=FakeMonitor)
    assert client.chat_calls == 1 and warm == []
    assert summary["stopped_low_gpu_share"] is True and verdict["go_for_e2b"] is False


def test_write_outputs_survives_a_failed_cold_call(items, tmp_path):
    root, selection = items
    client = FakeClient([requests.Timeout(), _response(json.dumps(VALID))])
    cold, warm, summary, verdict = run_microbench.run(client, "qwen3-vl:2b", selection, 1, 0, images_root=root,
                                                      monitor_factory=FakeMonitor)
    assert cold["error"] == "timeout" and "load_duration" not in cold
    run_microbench.write_outputs(tmp_path / "out", client, "qwen3-vl:2b", selection, cold, warm, summary, verdict,
                                 0, 1, run_microbench.build_options(2048, 6144))
    saved = json.loads((tmp_path / "out" / "summary.json").read_text(encoding="utf-8"))
    assert saved["cold"]["error"] == "timeout" and saved["cold"]["load_duration"] is None


def test_mini_output_dir_is_new_and_separate():
    reserved = {run_microbench.OUTPUT_DIR, run_single_check.SINGLE_OUTPUT_DIR}
    assert run_mini_bench.MINI_OUTPUT_DIR not in reserved
    assert run_mini_bench.MINI_OUTPUT_DIR.name == "output_mini3"


# ---------------------------------------------------------------------------
# Isolation
# ---------------------------------------------------------------------------

def test_e2_code_never_touches_database_or_downloads():
    for path in E2_DIR.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert not re.search(r"psycopg|get_connection|import main\b|load_user_wardrobe|api/pull\"|\.pull\(", source), path


def test_bo4_files_match_issue08_fingerprints():
    manifest = list(csv.DictReader(open(EVALUATION_DIR / "manifeste_pilote.csv", encoding="utf-8")))[0]
    backend = E2_DIR.parent.parent
    assert manifest["sha256_outfit_engine"] == sha256_file(backend / "outfit_engine.py")
    assert manifest["sha256_garment_attributes"] == sha256_file(backend / "garment_attributes.py")
    assert manifest["sha256_wardrobe_db_adapter"] == sha256_file(backend / "wardrobe_db_adapter.py")
