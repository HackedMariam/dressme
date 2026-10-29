"""Tests du protocole d'optimisation E2 (faux client Ollama, aucun réseau)."""

import json
from types import SimpleNamespace

import pytest
from PIL import Image

from experiments.qwen3vl_e2 import run_optim
from experiments.qwen3vl_e2.ollama_client import OllamaClient
from experiments.qwen3vl_e2.schema import ollama_format_schema
from experiments.qwen3vl_e2.taxonomy import DIMENSIONS

VALID = {"category": "dress", "primary_color": "pink", "pattern": "floral", "material_appearance": "lace",
         "fit": "fitted", "style": "romantic_boho", "formality": "smart_casual", "thickness": "light",
         "certainty": "medium"}
IDS = (run_optim.WARMUP, *run_optim.MEASURED)


class Monitor:
    def __init__(self, ram=1500.0):
        self.vram_peak_mib, self.ram_min_available_mib = 2977, ram

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class OptimClient:
    """Simule le chargement à la première inférence et le déchargement."""

    def __init__(self, prompt_tokens=3107, size_vram=1875, eval_count=700):
        self.loaded, self.unloads, self.chats = False, 0, []
        self.prompt_tokens, self.size_vram, self.eval_count = prompt_tokens, size_vram, eval_count

    def tags(self):
        return [{"name": "qwen3-vl:2b", "model": "qwen3-vl:2b", "digest": "sha256:fake"}]

    def version(self):
        return "fake"

    def ps(self):
        return [{"name": "qwen3-vl:2b", "size": 2548, "size_vram": self.size_vram}] if self.loaded else []

    def unload(self, model):
        self.loaded = False
        self.unloads += 1
        return {}

    def chat(self, model, messages, format_schema, options, think=False, keep_alive="10m"):
        assert format_schema == ollama_format_schema() and think is False
        was_loaded, self.loaded = self.loaded, True
        self.chats.append({"options": dict(options), "image_b64_len": len(messages[-1]["images"][0])})
        return {"message": {"content": json.dumps(VALID), "thinking": "t" * 2000}, "done_reason": "stop",
                "load_duration": 0 if was_loaded else 9e9, "prompt_eval_count": self.prompt_tokens,
                "prompt_eval_duration": 3e9, "eval_count": self.eval_count, "eval_duration": 28e9,
                "total_duration": 40e9}


def no_sleep_unloader(client, model):
    run_optim.unload_and_wait(client, model, sleep=lambda s: None)


@pytest.fixture
def setup(tmp_path):
    root = tmp_path / "hm"
    root.mkdir()
    items = []
    for article_id in IDS:
        Image.new("RGB", (1166, 1750), "white").save(root / f"{article_id}.jpg", "JPEG")
        items.append({"article_id": article_id, "image_path": f"{article_id}.jpg", "image_sha256": "x"})
    return root, items


def kwargs(root, ram=2500.0, monitor_ram=1500.0, memory=None):
    return {"images_root": root, "monitor_factory": lambda: Monitor(monitor_ram), "ram_sampler": lambda: ram,
            "memory_sampler": memory or (lambda: {"llama_server_mib": 1800.0, "ollama_total_mib": 1900.0}),
            "unloader": no_sleep_unloader}


def test_prepare_image_resizes_in_memory_only(setup):
    root, _ = setup
    path = root / f"{run_optim.WARMUP}.jpg"
    before = path.read_bytes()
    data, info = run_optim.prepare_image(path, 896)
    assert info["resized"] and (info["width"], info["height"]) == (597, 896)
    with Image.open(__import__("io").BytesIO(data)) as image:
        assert image.size == (597, 896)
    assert path.read_bytes() == before                                     # source intacte
    original, info0 = run_optim.prepare_image(path, None)
    assert original == before and not info0["resized"] and info0["height"] == 1750
    assert run_optim.prepare_image(path, 640)[1]["height"] == 640


def test_ollama_memory_counts_llama_server_and_ollama():
    procs = [SimpleNamespace(info={"name": "llama-server.exe", "memory_info": SimpleNamespace(rss=1024 * 2**20)}),
             SimpleNamespace(info={"name": "ollama.exe", "memory_info": SimpleNamespace(rss=100 * 2**20)}),
             SimpleNamespace(info={"name": "Code.exe", "memory_info": SimpleNamespace(rss=900 * 2**20)})]
    assert run_optim.ollama_memory_mib(lambda attrs: procs) == {"llama_server_mib": 1024.0, "ollama_total_mib": 1124.0}
    assert run_optim.ollama_memory_mib(lambda attrs: [])["llama_server_mib"] is None


def test_a0_runs_warmup_then_five_warm_calls(setup):
    root, items = setup
    client = OptimClient()
    exp = run_optim.EXPERIMENTS[0]
    options = run_optim.options_for(exp, {})
    records, stop, _ = run_optim.run_experiment(client, "qwen3-vl:2b", exp, items, options, **kwargs(root))
    assert stop is None and client.unloads == 1 and len(client.chats) == 6
    assert [r["phase"] for r in records] == ["warmup"] + ["warm"] * 5
    assert [r["article_id"] for r in records] == list(IDS)
    assert all(c["options"] == {"temperature": 0, "seed": 0, "num_ctx": 6144, "num_predict": 2048}
               for c in client.chats)
    assert records[0]["preflight"]["required_mib"] == pytest.approx(1918)    # chargement
    assert records[1]["preflight"]["required_mib"] == pytest.approx(300)     # modèle chargé
    assert records[1]["memory_before"]["llama_server_mib"] == 1800.0 and records[1]["cache_hit"] is False
    summary = run_optim.summarize_experiment(records, 100.0)
    assert summary["measured_calls"] == 5 and summary["schema_valid"] == 5 and summary["done_stop"] == 5
    assert summary["eval_tokens_per_s_median"] == pytest.approx(700 / 28)


def test_a1_unloads_before_every_image_and_labels_calls_cold(setup):
    root, items = setup
    client = OptimClient()
    exp = run_optim.EXPERIMENTS[1]
    records, stop, _ = run_optim.run_experiment(client, "qwen3-vl:2b", exp, items, run_optim.options_for(exp, {}),
                                                **kwargs(root))
    assert stop is None and client.unloads == 6
    assert [r["phase"] for r in records] == ["warmup"] + ["cold_measured"] * 5
    assert all(r["load_duration"] == 9e9 for r in records)
    assert all(r["wall_minus_load_s"] < r["wall_s"] for r in records)


def test_resized_experiment_sends_smaller_images(setup):
    root, items = setup
    sizes = {}
    for exp in run_optim.EXPERIMENTS[:4]:
        client = OptimClient()
        records, _, _ = run_optim.run_experiment(client, "qwen3-vl:2b", exp, items, run_optim.options_for(exp, {}),
                                                 **kwargs(root))
        sizes[exp["name"]] = client.chats[1]["image_b64_len"]
        assert records[1]["image"]["height"] == (exp["max_side"] or 1750)
    assert sizes["A0"] == sizes["A1"] and sizes["R2"] < sizes["R1"]


@pytest.mark.parametrize("args, calls, reason", [
    ({"ram": 1700.0}, 0, "contrôle avant"),          # < 1500 + 418 pour charger
    ({"monitor_ram": 250.0}, 1, "RAM sous 300"),
])
def test_safety_stops_without_workaround(setup, args, calls, reason):
    root, items = setup
    client = OptimClient()
    exp = run_optim.EXPERIMENTS[0]
    records, stop, _ = run_optim.run_experiment(client, "qwen3-vl:2b", exp, items, run_optim.options_for(exp, {}),
                                                **kwargs(root, **args))
    assert len(client.chats) == calls and reason in stop


def test_low_gpu_share_stops(setup):
    root, items = setup
    client = OptimClient(size_vram=1010)                                     # 0,396
    exp = run_optim.EXPERIMENTS[0]
    records, stop, _ = run_optim.run_experiment(client, "qwen3-vl:2b", exp, items, run_optim.options_for(exp, {}),
                                                **kwargs(root))
    assert len(client.chats) == 1 and "part GPU" in stop


def test_run_all_stops_entire_benchmark_on_safety_failure(setup, tmp_path):
    root, items = setup
    client = OptimClient()
    results, _, stop = run_optim.run_all(client, "qwen3-vl:2b", items, tmp_path / "out",
                                         **kwargs(root, monitor_ram=250.0))
    assert list(results) == ["A0"] and "RAM" in stop and len(client.chats) == 1
    assert (tmp_path / "out" / "A0" / "results.jsonl").exists() and not (tmp_path / "out" / "A1").exists()


def test_c1_uses_prompt_tokens_measured_in_r1(setup, tmp_path):
    root, items = setup
    client = OptimClient(prompt_tokens=1600)
    results, comparison, stop = run_optim.run_all(client, "qwen3-vl:2b", items, tmp_path / "out", **kwargs(root))
    assert stop is None and list(results) == ["A0", "A1", "R1", "R2", "C1"]
    assert len(client.chats) == 30
    assert results["C1"]["summary"]["options"]["num_ctx"] == 4096
    assert comparison["R1"]["identical_fields"] == comparison["R1"]["compared_fields"] == 5 * len(DIMENSIONS)
    saved = json.loads((tmp_path / "out" / "comparison.json").read_text(encoding="utf-8"))
    assert "dress" not in json.dumps(saved["vs_A0"])                         # noms de champs, pas de valeurs


def test_c1_is_skipped_when_measured_input_does_not_fit(setup, tmp_path):
    root, items = setup
    client = OptimClient(prompt_tokens=3107)
    results, _, stop = run_optim.run_all(client, "qwen3-vl:2b", items, tmp_path / "out", **kwargs(root))
    assert "skipped" in results["C1"] and len(client.chats) == 24 and stop is None


def test_compare_reports_field_names_only():
    rec = lambda exp, aid, attrs: {"experiment": exp, "article_id": aid, "phase": "warm", "attributes": attrs}
    out = run_optim.compare_to_reference([rec("A0", "x", VALID), rec("R2", "x", {**VALID, "fit": "regular"})])
    assert out["R2"]["by_item"]["x"] == {"identical_fields": 8, "differing_fields": ["fit"]}


def test_client_unload_sends_no_prompt():
    class Session:
        def post(self, url, json, timeout):
            self.url, self.payload = url, json
            return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {})
    session = Session()
    OllamaClient(session=session).unload("qwen3-vl:2b")
    assert session.url.endswith("/api/generate") and session.payload == {"model": "qwen3-vl:2b", "keep_alive": 0}


def test_unload_wait_gives_up_instead_of_looping():
    class Stuck(OptimClient):
        def unload(self, model):
            self.loaded = True
    client = Stuck()
    ticks = iter(range(100))
    with pytest.raises(run_optim.SafetyStop):
        run_optim.unload_and_wait(client, "qwen3-vl:2b", timeout_s=3, sleep=lambda s: None, clock=lambda: next(ticks))


def test_confirm_experiment_unloads_before_each_dev_image(setup):
    root, items = setup
    client = OptimClient(prompt_tokens=2207)
    exp = run_optim.confirm_experiment(IDS)
    records, stop, _ = run_optim.run_experiment(client, "qwen3-vl:2b", exp, items, run_optim.options_for(exp, {}),
                                                **kwargs(root))
    assert stop is None and len(client.chats) == 1 + len(IDS) and client.unloads == 1 + len(IDS)
    assert [r["phase"] for r in records] == ["warmup"] + ["cold_measured"] * len(IDS)
    assert all(r["image"]["height"] == 896 for r in records)
    assert run_optim.CONFIRM_DIR.name == "output_optim_confirm" and run_optim.CONFIRM_DIR != run_optim.OPTIM_DIR


def test_single_check_can_send_a_resized_image_with_a_larger_budget(setup):
    from experiments.qwen3vl_e2 import run_single_check
    from experiments.qwen3vl_e2.run_microbench import build_options
    root, items = setup
    client = OptimClient(prompt_tokens=2207)
    client.show = lambda model: {"capabilities": [], "template": ""}
    data, info = run_optim.prepare_image(root / items[0]["image_path"], 896)
    options = build_options(3584, 6144, prompt_tokens=run_single_check.R1_PROMPT_TOKENS)
    report = run_single_check.single_check(client, "qwen3-vl:2b", items[0], options, root, Monitor,
                                           ram_sampler=lambda: 2500.0, image_bytes=data)
    assert report["inference_done"] and len(client.chats) == 1
    assert client.chats[0]["options"]["num_predict"] == 3584 and info["height"] == 896
    with pytest.raises(ValueError):                       # 3107 + 3584 > 6144 à pleine résolution
        build_options(3584, 6144)
