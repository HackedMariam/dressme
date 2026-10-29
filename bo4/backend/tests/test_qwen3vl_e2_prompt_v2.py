"""Tests du prompt e2-prompt/2 et de la comparaison v1/v2 (aucun appel Ollama).

Les résultats et annotations utilisés ici sont SYNTHÉTIQUES (fichiers temporaires).
"""

import csv
import json

import pytest
from PIL import Image

from experiments.qwen3vl_e2 import compare_prompts, prompt, prompt_v2, run_optim
from experiments.qwen3vl_e2.schema import ollama_format_schema
from experiments.qwen3vl_e2.taxonomy import DIMENSIONS, RULES, taxonomy_fingerprint

V1_PROMPT_SHA = "1ce78ff8826e1a587832fb794945386339bb3a7a7b19cc0520a1de0f7d748dc2"
TAXONOMY_SHA = "a324e53304b3aaa9a1a18fb190464e57ecd730287477c4f4ba6209f467da972c"
VALID = {"category": "cardigan", "primary_color": "white", "pattern": "solid", "material_appearance": "jersey_fine_knit",
         "fit": "regular", "style": "casual_basic", "formality": "casual", "thickness": "medium", "certainty": "medium"}


def test_v1_prompt_and_taxonomy_are_unchanged():
    assert prompt.PROMPT_VERSION == "e2-prompt/1" and prompt.prompt_fingerprint() == V1_PROMPT_SHA
    assert taxonomy_fingerprint() == TAXONOMY_SHA


def test_v2_keeps_every_field_value_and_rule():
    text = prompt_v2.system_prompt()
    assert prompt_v2.PROMPT_VERSION == "e2-prompt/2" and prompt_v2.prompt_fingerprint() != V1_PROMPT_SHA
    for name, spec in DIMENSIONS.items():
        line = next(l for l in text.splitlines() if l.startswith(f"- {name}:"))
        assert line.endswith("Allowed: " + ", ".join(spec["values"]) + ".")
    assert all(rule in text for rule in RULES)


def test_v2_adds_the_anti_loop_guidance():
    text = prompt_v2.system_prompt()
    assert "Small contrasting areas" in text and "patch" in text and "keep pattern=solid" in text
    assert "Colour blocking" in text and "graphic_print" in text and "dotted" in text and "striped" in text
    assert "Decide each field ONCE" in text and "Do not re-check" in text
    assert "Never invent details" in text and "multipack" in text


def test_v2_no_longer_copies_the_schema_text_but_format_still_enforces_it():
    assert '"properties"' in prompt.system_prompt() and '"properties"' not in prompt_v2.system_prompt()
    assert len(prompt_v2.system_prompt()) < len(prompt.system_prompt())
    messages = prompt_v2.build_messages("abc")
    assert messages[0]["content"] == prompt_v2.system_prompt() and messages[1]["images"] == ["abc"]


class Client:
    def __init__(self):
        self.loaded, self.systems = False, []

    def tags(self):
        return [{"name": "qwen3-vl:2b", "model": "qwen3-vl:2b"}]

    def ps(self):
        return [{"name": "qwen3-vl:2b", "size": 2548, "size_vram": 1875}] if self.loaded else []

    def unload(self, model):
        self.loaded = False

    def chat(self, model, messages, format_schema, options, think=False, keep_alive="10m"):
        assert format_schema == ollama_format_schema()
        self.loaded = True
        self.systems.append(messages[0]["content"])
        return {"message": {"content": json.dumps(VALID), "thinking": "t"}, "done_reason": "stop", "load_duration": 9e9,
                "prompt_eval_count": 1800, "prompt_eval_duration": 2e9, "eval_count": 300, "eval_duration": 10e9}


class Monitor:
    vram_peak_mib, ram_min_available_mib = 2943, 1500.0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_prompt_v2_experiment_sends_v2_with_same_technical_settings(tmp_path):
    ids = (run_optim.WARMUP, "0680192004")
    items = []
    for article_id in ids:
        Image.new("RGB", (1166, 1750), "white").save(tmp_path / f"{article_id}.jpg", "JPEG")
        items.append({"article_id": article_id, "image_path": f"{article_id}.jpg"})
    exp = run_optim.confirm_experiment(("0680192004",), "v2")
    assert exp["name"] == "R1U-P2" and exp["max_side"] == 896 and exp["unload_between"] is True
    client = Client()
    records, stop, _ = run_optim.run_experiment(
        client, "qwen3-vl:2b", exp, items, run_optim.options_for(exp, {}), images_root=tmp_path,
        monitor_factory=Monitor, ram_sampler=lambda: 2500.0,
        memory_sampler=lambda: {"llama_server_mib": 1268.0, "ollama_total_mib": 1300.0},
        unloader=lambda c, m: c.unload(m))
    assert stop is None and client.systems == [prompt_v2.system_prompt()] * 2
    assert all(r["prompt_version"] == "e2-prompt/2" for r in records)
    assert records[0]["options"] == {"temperature": 0, "seed": 0, "num_ctx": 6144, "num_predict": 2048}
    assert run_optim.confirm_experiment(("x",))["prompt"] == "v1"
    assert run_optim.PROMPT_V2_DIR.name == "output_prompt_v2"


# ---------------------------------------------------------------------------
# Comparaison v1 / v2 (fichiers synthétiques)
# ---------------------------------------------------------------------------

def _record(article_id, done="stop", eval_count=800, wall=30.0, attrs=None, phase="cold_measured"):
    valid = done == "stop"
    return {"article_id": article_id, "phase": phase, "error": None, "done_reason": done, "schema_valid": valid,
            "eval_count": eval_count, "wall_s": wall, "wall_minus_load_s": wall - 7, "ram_min_available_mib": 1000.0,
            "vram_peak_mib": 2943, "prompt_eval_count": 2207, "attributes": (attrs or VALID) if valid else None}


def _write(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def files(tmp_path):
    human_dir = tmp_path / "human"
    human_dir.mkdir()
    with (human_dir / "comparaison_T1.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["article_id", "attribute", "human"])
        writer.writeheader()
        for attr in compare_prompts.SCORED:
            writer.writerow({"article_id": "a", "attribute": attr, "human": VALID[attr]})
    v1 = _write(tmp_path / "v1.jsonl", [_record("w", phase="warmup"), _record("a", eval_count=1000, wall=40),
                                        _record("0680192004", done="length", eval_count=2048, wall=75)])
    return tmp_path, human_dir, v1


def test_compare_promising_when_all_criteria_hold(files):
    tmp_path, human_dir, v1 = files
    v2 = _write(tmp_path / "v2.jsonl", [_record("a", eval_count=500, wall=20), _record("0680192004", eval_count=600)])
    result = compare_prompts.compare(v1, v2, human_dir)
    assert result["verdict"]["promising"] is True
    assert result["v1"]["blocked_length"] == ["0680192004"] and result["v2"]["blocked_length"] == []
    assert result["v1"]["schema_valid"] == 1 and result["v2"]["schema_valid"] == 2
    assert result["attribute_changes"]["0680192004"].startswith("comparaison impossible")


def test_compare_flags_unfixed_block_and_degradation(files):
    tmp_path, human_dir, v1 = files
    worse = {**VALID, "category": "jacket", "fit": "loose_oversized"}
    v2 = _write(tmp_path / "v2.jsonl", [_record("a", eval_count=500, attrs=worse),
                                        _record("0680192004", done="length", eval_count=2048)])
    result = compare_prompts.compare(v1, v2, human_dir)
    checks = result["verdict"]["checks"]
    assert checks["blocked_item_fixed"] is False and checks["no_manifest_degradation_exploratory"] is False
    assert result["human_exploratory"]["v1"]["total"] == 8 and result["human_exploratory"]["v2"]["total"] == 6
    assert result["attribute_changes"]["a"] == {"category": {"v1": "cardigan", "v2": "jacket"},
                                                "fit": {"v1": "regular", "v2": "loose_oversized"}}


def test_compare_refuses_different_image_sets(files):
    tmp_path, human_dir, v1 = files
    v2 = _write(tmp_path / "v2.jsonl", [_record("a")])
    with pytest.raises(ValueError, match="images différentes"):
        compare_prompts.compare(v1, v2, human_dir)
