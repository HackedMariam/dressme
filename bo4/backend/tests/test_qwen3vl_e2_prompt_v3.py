"""Tests du prompt e2-prompt/3 et de la comparaison v2/v3 (aucun appel Ollama).

Résultats et annotations SYNTHÉTIQUES (fichiers temporaires).
"""

import csv
import json
import re

import pytest
from PIL import Image

from experiments.qwen3vl_e2 import compare_prompts, prompt, prompt_v2, prompt_v3, run_optim
from experiments.qwen3vl_e2.taxonomy import DIMENSIONS, RULES, taxonomy_fingerprint, values

V1_PROMPT_SHA = "1ce78ff8826e1a587832fb794945386339bb3a7a7b19cc0520a1de0f7d748dc2"
V2_PROMPT_SHA = "0194256848d884caef72ef62beb0f7665dc4ea2b6cc73e59882165b05258945d"
TAXONOMY_SHA = "a324e53304b3aaa9a1a18fb190464e57ecd730287477c4f4ba6209f467da972c"
VALID = {"category": "cardigan", "primary_color": "multicolor", "pattern": "other_pattern",
         "material_appearance": "jersey_fine_knit", "fit": "regular", "style": "casual_basic", "formality": "casual",
         "thickness": "medium", "certainty": "medium"}


def test_previous_prompts_and_taxonomy_are_unchanged():
    assert prompt.prompt_fingerprint() == V1_PROMPT_SHA and prompt_v2.prompt_fingerprint() == V2_PROMPT_SHA
    assert taxonomy_fingerprint() == TAXONOMY_SHA
    assert prompt_v3.PROMPT_VERSION == "e2-prompt/3" and prompt_v3.prompt_fingerprint() not in (V1_PROMPT_SHA,
                                                                                               V2_PROMPT_SHA)


def test_v3_keeps_fields_values_rules_and_v2_pattern_guide():
    text = prompt_v3.system_prompt()
    for name, spec in DIMENSIONS.items():
        line = next(l for l in text.splitlines() if l.startswith(f"- {name}:"))
        assert line.endswith("Allowed: " + ", ".join(spec["values"]) + ".")
    assert all(rule in text for rule in RULES)
    assert all(rule in text for rule in prompt_v2.PATTERN_GUIDE)
    assert '"properties"' not in text and prompt_v3.USER_PROMPT == prompt_v2.USER_PROMPT


def test_v3_adds_primary_colour_decision_rule():
    text = prompt_v3.system_prompt()
    assert "clearly covers most of the garment, choose that colour" in text
    assert "none clearly dominates" in text and "choose multicolor" in text
    assert "Ignore small details" in text and "do not compare areas again" in text


def test_v3_category_guide_uses_only_taxonomy_categories():
    guide = " ".join(prompt_v3.CATEGORY_GUIDE)
    labels = [m for rule in prompt_v3.CATEGORY_GUIDE for m in re.findall(r"(?:^|\. )([a-z_]+):", rule)]
    assert labels == ["cardigan", "jacket", "blazer", "hoodie", "coat"]
    named = set(labels)
    assert named <= set(values("category"))
    assert "knitted means cardigan, otherwise jacket" in guide
    v2_rule = next(r for r in prompt_v2.DECISION_RULES if r.startswith("For category"))
    assert v2_rule not in prompt_v3.system_prompt()                     # remplacée, pas dupliquée
    assert sum(r.startswith("For category") for r in prompt_v3.DECISION_RULES) == 1
    assert all(r in prompt_v3.DECISION_RULES for r in prompt_v2.DECISION_RULES if not r.startswith("For category"))


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
        self.loaded = True
        self.systems.append(messages[0]["content"])
        return {"message": {"content": json.dumps(VALID), "thinking": "t"}, "done_reason": "stop", "load_duration": 9e9,
                "prompt_eval_count": 2100, "prompt_eval_duration": 2e9, "eval_count": 400, "eval_duration": 12e9}


class Monitor:
    vram_peak_mib, ram_min_available_mib = 2943, 1500.0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_prompt_v3_experiment_sends_v3_with_unchanged_settings(tmp_path):
    items = []
    for article_id in (run_optim.WARMUP, "0793493001"):
        Image.new("RGB", (1166, 1750), "white").save(tmp_path / f"{article_id}.jpg", "JPEG")
        items.append({"article_id": article_id, "image_path": f"{article_id}.jpg"})
    exp = run_optim.confirm_experiment(("0793493001",), "v3")
    assert exp["name"] == "R1U-P3" and run_optim.PROMPT_V3_DIR.name == "output_prompt_v3"
    client = Client()
    records, stop, _ = run_optim.run_experiment(
        client, "qwen3-vl:2b", exp, items, run_optim.options_for(exp, {}), images_root=tmp_path,
        monitor_factory=Monitor, ram_sampler=lambda: 2500.0,
        memory_sampler=lambda: {"llama_server_mib": 1268.0, "ollama_total_mib": 1300.0},
        unloader=lambda c, m: c.unload(m))
    assert stop is None and len(client.systems) == 2 and client.systems[0] == prompt_v3.system_prompt()
    assert records[1]["options"] == {"temperature": 0, "seed": 0, "num_ctx": 6144, "num_predict": 2048}
    assert records[1]["image"]["height"] == 896 and records[1]["prompt_version"] == "e2-prompt/3"


# ---------------------------------------------------------------------------
# Comparaison v2 / v3
# ---------------------------------------------------------------------------

def _record(article_id, done="stop", eval_count=500, wall=30.0, attrs=None):
    valid = done == "stop"
    return {"article_id": article_id, "phase": "cold_measured", "error": None, "done_reason": done,
            "schema_valid": valid, "eval_count": eval_count, "wall_s": wall, "wall_minus_load_s": wall - 8,
            "ram_min_available_mib": 1100.0, "vram_peak_mib": 2943, "prompt_eval_count": 2100,
            "attributes": (attrs or VALID) if valid else None}


def _write(path, records):
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def base(tmp_path):
    human = tmp_path / "human"
    human.mkdir()
    with (human / "comparaison_T1.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["article_id", "attribute", "human"])
        writer.writeheader()
        for attr in compare_prompts.SCORED:
            writer.writerow({"article_id": "0783144006", "attribute": attr, "human": VALID[attr]})
    selection = tmp_path / "sel.csv"
    selection.write_text("article_id,product_type_name,colour_group_name\n0793493001,Cardigan,Black\n",
                         encoding="utf-8")
    v2 = _write(tmp_path / "v2.jsonl", [_record("0783144006"), _record("0680192004"),
                                        _record("0793493001", done="length", eval_count=2048, wall=86)])
    return tmp_path, human, selection, v2


def test_v3_promising_when_both_cardigans_finish_and_costs_are_kept(base):
    tmp_path, human, selection, v2 = base
    v3 = _write(tmp_path / "v3.jsonl", [_record("0783144006", eval_count=550), _record("0680192004"),
                                        _record("0793493001", eval_count=600)])
    result = compare_prompts.compare_v2_v3(v2, v3, human, selection)
    assert result["verdict"]["promising"] is True and result["verdict"]["target_10_of_10"] is False
    watched = result["watched"]["0793493001"]
    assert watched["primary_color"] == {"v2": None, "v3": "multicolor"}
    assert watched["hm_metadata_signal_not_proof"] == {"product_type": "Cardigan", "colour_group": "Black"}


def test_v3_fails_when_tokens_rise_more_than_20_percent(base):
    tmp_path, human, selection, v2 = base
    v3 = _write(tmp_path / "v3.jsonl", [_record("0783144006", eval_count=900), _record("0680192004", eval_count=900),
                                        _record("0793493001", eval_count=900)])
    checks = compare_prompts.compare_v2_v3(v2, v3, human, selection)["verdict"]["checks"]
    assert checks["multicolour_cardigan_fixed"] and checks["white_cardigan_still_fixed"]
    assert checks["tokens_and_latency_kept"] is False


def test_v3_fails_when_white_cardigan_blocks_again(base):
    tmp_path, human, selection, v2 = base
    v3 = _write(tmp_path / "v3.jsonl", [_record("0783144006"), _record("0680192004", done="length", eval_count=2048),
                                        _record("0793493001")])
    result = compare_prompts.compare_v2_v3(v2, v3, human, selection)
    assert result["verdict"]["checks"]["white_cardigan_still_fixed"] is False
    assert result["verdict"]["promising"] is False
    assert result["attribute_changes"]["0680192004"].startswith("comparaison impossible")
