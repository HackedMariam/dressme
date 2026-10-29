"""Tests de l'évaluation humaine E2-h (formulaire en aveugle et comparaison).

Les annotations utilisées ici sont SYNTHÉTIQUES (fixtures de test) : elles ne
sont ni des annotations humaines réelles ni écrites dans output_human_eval/.
"""

import csv
import json
from pathlib import Path

import pytest
from PIL import Image

from experiments.qwen3vl_e2 import human_eval
from experiments.qwen3vl_e2.taxonomy import DIMENSIONS

PRED = {  # prédictions synthétiques, conformes à la taxonomie
    "0840606004": {"category": "trousers", "primary_color": "pink", "pattern": "striped",
                   "material_appearance": "jersey_fine_knit", "fit": "regular", "style": "casual_basic",
                   "formality": "casual", "thickness": "medium", "certainty": "high"},
    "0781758009": {"category": "shirt_blouse", "primary_color": "burgundy", "pattern": "dotted",
                   "material_appearance": "smooth_woven", "fit": "regular", "style": "casual_basic",
                   "formality": "smart_casual", "thickness": "light", "certainty": "high"},
    "0783144006": {"category": "blazer", "primary_color": "burgundy", "pattern": "solid",
                   "material_appearance": "smooth_woven", "fit": "fitted", "style": "classic_tailored",
                   "formality": "formal", "thickness": "medium", "certainty": "medium"},
    "0801843006": {"category": "dress", "primary_color": "pink", "pattern": "floral",
                   "material_appearance": "jersey_fine_knit", "fit": "flared", "style": "romantic_boho",
                   "formality": "casual", "thickness": "light", "certainty": "low"},
}


@pytest.fixture
def setup(tmp_path):
    """Racine E2 factice : images, prédictions enregistrées, dossier de sortie."""
    images, items, shas = tmp_path / "hm", [], {}
    for n, article_id in enumerate(human_eval.ARTICLES):
        path = images / f"{article_id}.jpg"
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (8, 12), (n * 40, 10, 10)).save(path, "JPEG")
        shas[article_id] = human_eval.sha256_file(path)
        items.append({"article_id": article_id, "image_path": f"{article_id}.jpg", "image_sha256": shas[article_id],
                      "file": path})
    root = tmp_path / "e2"
    single = root / "output_single_check" / "single_check.json"
    single.parent.mkdir(parents=True)
    single.write_text(json.dumps({"article_id": "0840606004", "metadata": {"image_sha256": shas["0840606004"]},
                                  "result": {"article_id": "0840606004", "schema_valid": True,
                                             "attributes": PRED["0840606004"]}}), encoding="utf-8")
    mini = root / "output_mini3_v4"
    mini.mkdir()
    others = [a for a in human_eval.ARTICLES if a != "0840606004"]
    (mini / "results.jsonl").write_text("\n".join(json.dumps({"article_id": a, "schema_valid": True,
                                                              "attributes": PRED[a]}) for a in others) + "\n",
                                        encoding="utf-8")
    (mini / "metadata.json").write_text(json.dumps({"images": {a: shas[a] for a in others}}), encoding="utf-8")
    out = tmp_path / "human"
    manifest = human_eval.build(out, items, root)
    return root, out, manifest


def write_annotations(path, manifest, overrides=None, exposed=None, drop=None):
    """CSV au format exporté par le formulaire (annotateur synthétique « T1 »)."""
    fields = (["annotateur", "article_id", "ordre_presentation", *DIMENSIONS]
              + [f"alt_{d}" for d in human_eval.WITH_ALTERNATIVE]
              + ["deja_vu_predictions", "commentaire", "horodatage", "version_formulaire"])
    with Path(path).open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for i, article_id in enumerate(human_eval.ARTICLES):
            if article_id == drop:
                continue
            row = {"annotateur": "T1", "article_id": article_id, "ordre_presentation": i + 1,
                   **PRED[article_id], "deja_vu_predictions": "oui" if article_id in (exposed or ()) else "non",
                   "version_formulaire": manifest["form_version"], "horodatage": "2026-10-16T10:00:00Z"}
            row.update((overrides or {}).get(article_id, {}))
            writer.writerow(row)
    return path


# ---------------------------------------------------------------------------
# Formulaire en aveugle
# ---------------------------------------------------------------------------

def test_form_payload_contains_only_images_and_taxonomy(setup):
    _, out, _ = setup
    html = (out / human_eval.FORM_FILE).read_text(encoding="utf-8")
    payload = json.loads(html.split('id="data">', 1)[1].split("</script>", 1)[0].replace("<\\/", "</"))
    assert set(payload) == {"version", "taxonomy_version", "rules", "questions", "items"}
    assert all(set(item) == {"id", "image"} for item in payload["items"])
    assert [q["id"] for q in payload["questions"]] == list(DIMENSIONS)
    for q in payload["questions"]:
        assert [o["value"] for o in q["options"]] == list(DIMENSIONS[q["id"]]["values"])
        assert q["alternative"] is (q["id"] != "certainty")
    for leak in ("schema_valid", "thinking", "attributes", "single_check", "mini3", "Trousers", "qwen"):
        assert leak not in html


def test_manifest_records_prediction_hashes_not_values(setup):
    _, _, manifest = setup
    text = json.dumps(manifest)
    assert set(manifest["prediction_files_sha256"]) == {"output_single_check/single_check.json",
                                                        "output_mini3_v4/results.jsonl"}
    assert "striped" not in text and "attributes" not in text


def test_build_never_overwrites(setup):
    root, out, _ = setup
    with pytest.raises(human_eval.HumanEvalError):
        human_eval.build(out, [], root)


@pytest.mark.hm_images
def test_real_images_are_the_exact_selection_files():
    items = human_eval.annotation_items()
    assert [i["article_id"] for i in items] == sorted(["0840606004", "0781758009", "0783144006", "0801843006"])
    assert all(len(i["image_sha256"]) == 64 for i in items)


def test_certainty_is_defined_as_annotator_confidence_and_never_scored():
    assert "certainty" not in human_eval.SCORED and len(human_eval.SCORED) == 8
    assert "VOTRE certitude" in human_eval.HELP_FR["certainty"]


# ---------------------------------------------------------------------------
# Comparaison (annotations synthétiques)
# ---------------------------------------------------------------------------

def test_compare_scores_strict_lenient_and_ordinal(setup, tmp_path):
    root, out, manifest = setup
    overrides = {
        "0781758009": {"primary_color": "red", "alt_primary_color": "burgundy", "certainty": "low"},
        "0783144006": {"formality": "casual"},
        "0801843006": {"pattern": "other_pattern", "style": "casual_basic", "commentaire": "motif ambigu"},
    }
    csv_path = write_annotations(tmp_path / "a.csv", manifest, overrides, exposed={"0840606004"})
    result = human_eval.run_compare(csv_path, out, root)
    by = result["scores"]["by_attribute"]
    assert by["primary_color"] == {**by["primary_color"], "n": 4, "strict": 3, "lenient": 4}
    assert by["formality"]["ordinal_distances"] == [0, 2, 0, 0]      # ordre des identifiants : blazer 2e
    assert by["pattern"]["differences"] == [{"article_id": "0801843006", "human": "other_pattern",
                                             "human_alternative": None, "qwen": "floral"}]
    assert result["scores"]["overall"] == {"n": 32, "strict": 28, "lenient": 29}
    assert result["scores"]["overall_without_style"]["n"] == 28
    assert result["scores"]["overall_blind_items_only"]["n"] == 24
    assert result["exposed_items"] == ["0840606004"]
    assert "certainty" not in by
    cert = {c["article_id"]: c for c in result["certainty"]}
    assert cert["0781758009"] == {"article_id": "0781758009", "human_certainty": "low", "qwen_certainty": "high",
                                  "qwen_strict_matches": 7, "n_attributes": 8}
    assert result["comments"] == {"0801843006": "motif ambigu"}
    assert (out / "comparaison_T1.json").exists() and (out / "comparaison_T1.csv").exists()
    with pytest.raises(human_eval.HumanEvalError):           # jamais d'écrasement
        human_eval.run_compare(csv_path, out, root)


@pytest.mark.parametrize("kwargs, message", [
    ({"overrides": {"0781758009": {"pattern": "stripes"}}}, "hors taxonomie"),
    ({"overrides": {"0781758009": {"fit": ""}}}, "hors taxonomie"),
    ({"overrides": {"0781758009": {"alt_fit": "regular"}}}, "alt_fit"),
    ({"overrides": {"0781758009": {"deja_vu_predictions": ""}}}, "deja_vu_predictions"),
    ({"overrides": {"0781758009": {"version_formulaire": "autre"}}}, "version du formulaire"),
    ({"drop": "0783144006"}, "non annotées"),
])
def test_invalid_annotations_are_rejected_not_completed(setup, tmp_path, kwargs, message):
    root, out, manifest = setup
    csv_path = write_annotations(tmp_path / "a.csv", manifest, **kwargs)
    with pytest.raises(human_eval.HumanEvalError, match=message):
        human_eval.run_compare(csv_path, out, root)
    assert not (out / "comparaison_T1.json").exists()


def test_compare_refuses_modified_prediction_files(setup, tmp_path):
    root, out, manifest = setup
    path = root / "output_mini3_v4" / "results.jsonl"
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(human_eval.HumanEvalError, match="modifié"):
        human_eval.run_compare(write_annotations(tmp_path / "a.csv", manifest), out, root)


def test_compare_refuses_prediction_for_another_image(setup, tmp_path):
    root, out, manifest = setup
    meta = root / "output_mini3_v4" / "metadata.json"
    data = json.loads(meta.read_text(encoding="utf-8"))
    data["images"]["0781758009"] = "0" * 64
    meta.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(human_eval.HumanEvalError, match="pas celle annotée"):
        human_eval.run_compare(write_annotations(tmp_path / "a.csv", manifest), out, root)


def test_human_eval_never_calls_ollama_or_database():
    source = Path(human_eval.__file__).read_text(encoding="utf-8")
    for forbidden in ("OllamaClient", "requests", "psycopg", "/api/chat", "run_call"):
        assert forbidden not in source
