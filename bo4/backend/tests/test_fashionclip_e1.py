"""Tests de l'expérience E1 (FashionCLIP zéro-shot, hors moteur BO4).

- Partie pure (numpy, fichiers temporaires) : toujours exécutée.
- Partie modèle : FashionCLIP réel chargé hors ligne ; ignorée si les poids ne
  sont pas en cache. Aucune annotation humaine n'est créée ni simulée ici :
  les fonctions d'accord sont testées sur des listes de libellés de manuel.
"""

import csv
import json
import os
import re
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from evaluation.common import OUTPUT_DIR as EVALUATION_OUTPUT_DIR, sha256_file
from experiments.fashionclip_e1 import agreement, annotation_form, attributes, run_e1
from experiments.fashionclip_e1.zero_shot import class_embeddings, l2_normalize, predict, prepare_image

E1_DIR = Path(run_e1.__file__).resolve().parent
HF_CACHE = Path.home() / ".cache" / "huggingface" / "hub" / "models--patrickjohncyh--fashion-clip"


# ---------------------------------------------------------------------------
# Schéma
# ---------------------------------------------------------------------------

def test_schema_is_explicit_and_stable():
    assert set(attributes.ATTRIBUTES) == {"motif", "formalite", "registre", "epaisseur"}
    for spec in attributes.ATTRIBUTES.values():
        assert len(spec["classes"]) >= 2
        for cls, info in spec["classes"].items():
            assert cls not in attributes.HUMAN_EXTRA_OPTIONS
            assert info["label_fr"] and len(info["prompts"]) >= 2
            assert all(p.strip() and p.isascii() for p in info["prompts"])
    assert attributes.schema_fingerprint() == attributes.schema_fingerprint()
    assert 0 < attributes.AMBIGUITY_MARGIN < 0.1


# ---------------------------------------------------------------------------
# Calculs purs
# ---------------------------------------------------------------------------

def test_predict_picks_highest_similarity_with_margin_and_ambiguity():
    classes, matrix = class_embeddings({
        "a": np.array([[1.0, 0.0, 0.0]]),
        "b": np.array([[0.0, 1.0, 0.0], [0.0, 2.0, 0.0]]),   # moyenne de formulations normalisées
        "c": np.array([[0.0, 0.0, 1.0]]),
    })
    images = np.array([[0.9, 0.1, 0.0], [0.5, 0.5, 0.01]])
    clear, tight = predict(images, classes, matrix, margin=0.05)
    assert clear["prediction"] == "a" and clear["second"] == "b" and not clear["ambiguous"]
    assert clear["margin"] == pytest.approx(clear["similarities"]["a"] - clear["similarities"]["b"])
    assert tight["ambiguous"] and tight["margin"] < 0.05
    for result in (clear, tight):
        assert all(-1.0 <= v <= 1.0 for v in result["similarities"].values())


def test_predict_is_deterministic_on_exact_ties():
    classes, matrix = class_embeddings({"x": np.array([[1.0, 0.0]]), "y": np.array([[0.0, 1.0]])})
    result = predict(np.array([[1.0, 1.0]]), classes, matrix)[0]
    assert result["prediction"] == "x" and result["margin"] == 0.0 and result["ambiguous"]


def test_invalid_inputs_raise():
    with pytest.raises(ValueError):
        l2_normalize(np.zeros((1, 3)))
    classes, matrix = class_embeddings({"only": np.array([[1.0, 0.0]])})
    with pytest.raises(ValueError):
        predict(np.array([[1.0, 0.0]]), classes, matrix)


def test_prepare_image_pad_keeps_whole_garment():
    tall = Image.new("RGB", (40, 100), (10, 20, 30))
    padded = prepare_image(tall, "pad")
    assert padded.size == (100, 100)
    assert padded.getpixel((0, 0)) == (255, 255, 255)
    assert padded.getpixel((50, 50)) == (10, 20, 30)
    assert prepare_image(tall, "crop").size == (40, 100)
    with pytest.raises(ValueError):
        prepare_image(tall, "stretch")


# ---------------------------------------------------------------------------
# Images absentes ou corrompues
# ---------------------------------------------------------------------------

def test_load_items_reports_missing_and_corrupt_images(tmp_path):
    images = tmp_path / "hm"
    (images / "images/010").mkdir(parents=True)
    Image.new("RGB", (8, 12), "white").save(images / "images/010/ok.jpg", "JPEG")
    (images / "images/010/corrupt.jpg").write_bytes(b"not a jpeg")
    pool = tmp_path / "pool.csv"
    with pool.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["article_id", "image_path"])
        writer.writeheader()
        writer.writerows([{"article_id": "1", "image_path": "images/010/ok.jpg"},
                          {"article_id": "2", "image_path": "images/010/missing.jpg"},
                          {"article_id": "3", "image_path": "images/010/corrupt.jpg"}])
    valid, rejected = run_e1.load_items(pool, images)
    assert [v["article_id"] for v in valid] == ["1"]
    problems = {r["article_id"]: r["image_problem"] for r in rejected}
    assert problems["2"] == "fichier absent"
    assert problems["3"].startswith("illisible")


# ---------------------------------------------------------------------------
# Formulaire humain : aucune prédiction exposée
# ---------------------------------------------------------------------------

FORBIDDEN = re.compile(r"predict|prédi|margin|marge|similar|cosin|fashion.?clip|ambig|score|prompt", re.I)


def test_annotation_form_exposes_only_questions_and_images():
    items, _ = run_e1.load_items()
    payload = annotation_form.form_payload(items)
    assert {i["id"] for i in payload["items"]} == {i["article_id"] for i in items}
    for item in payload["items"]:
        assert set(item) == annotation_form.ITEM_KEYS
    for question in payload["questions"]:
        assert set(question) == annotation_form.QUESTION_KEYS
        values = [o["value"] for o in question["options"]]
        assert "incertain" in values and "non_visible" in values
    html = annotation_form.render(payload)
    visible = re.sub(r"data:image/jpeg;base64,[A-Za-z0-9+/=]+", "", html)
    visible = re.sub(r"<style>[\s\S]*?</style>|style=\"[^\"]*\"", "", visible)  # le CSS « margin » n'est pas une fuite
    assert not FORBIDDEN.search(visible)
    for item in items:                                     # ni nom ni type produit (comme le modèle)
        assert item["prod_name"] not in visible
    assert "http://" not in visible and "https://" not in visible


# ---------------------------------------------------------------------------
# Accord (préparé, testé sur des exemples de manuel)
# ---------------------------------------------------------------------------

def test_cohen_kappa_textbook_values():
    a = ["oui"] * 20 + ["oui"] * 5 + ["non"] * 10 + ["non"] * 15
    b = ["oui"] * 20 + ["non"] * 5 + ["oui"] * 10 + ["non"] * 15
    assert agreement.cohen_kappa(a, b, ["oui", "non"]) == pytest.approx(0.4)   # po=0.7, pe=0.5
    assert agreement.cohen_kappa(["x", "y"], ["x", "y"], ["x", "y"]) == pytest.approx(1.0)
    assert agreement.cohen_kappa(["x", "x"], ["x", "x"], ["x", "y"]) is None
    assert agreement.cohen_kappa([], [], ["x"]) is None


def test_analysis_excludes_uncertain_and_uses_consensus_only():
    a = {"1": {"motif": "uni"}, "2": {"motif": "raye"}, "3": {"motif": "incertain"}, "4": {"motif": "uni"}}
    b = {"1": {"motif": "uni"}, "2": {"motif": "uni"}, "3": {"motif": "uni"}, "4": {"motif": "uni"}}
    model = {"1": {"motif": "uni"}, "2": {"motif": "uni"}, "3": {"motif": "raye"}, "4": {"motif": "raye"}}
    report = agreement.analyse_attribute("motif", a, b, model)
    assert report["items_both_labelled"] == 3
    assert report["items_excluded_uncertain_or_not_visible"] == 1
    assert report["consensus_items"] == 2                      # articles 1 et 4
    assert report["model_accuracy_on_consensus"] == pytest.approx(0.5)
    assert report["confusion_consensus_vs_model"]["uni"]["raye"] == 1


# ---------------------------------------------------------------------------
# Isolation : pas de base de données, BO4 / ISSUE-08 inchangés
# ---------------------------------------------------------------------------

def test_experiment_code_never_touches_the_database():
    for path in E1_DIR.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert not re.search(r"psycopg|get_connection|import main\b|load_user_wardrobe|INSERT|UPDATE|DELETE", source), path


def test_bo4_and_issue08_files_match_recorded_fingerprints():
    manifest = list(csv.DictReader(open(EVALUATION_OUTPUT_DIR / "manifeste_pilote.csv", encoding="utf-8")))
    backend = E1_DIR.parent.parent
    assert manifest[0]["sha256_outfit_engine"] == sha256_file(backend / "outfit_engine.py")
    assert manifest[0]["sha256_garment_attributes"] == sha256_file(backend / "garment_attributes.py")
    assert manifest[0]["sha256_wardrobe_db_adapter"] == sha256_file(backend / "wardrobe_db_adapter.py")
    metadata_path = E1_DIR / "output" / "metadata.json"
    if metadata_path.is_file():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        assert metadata["protected_files_sha256"] == run_e1.protected_hashes()
        assert metadata["pool_csv_sha256"] == sha256_file(EVALUATION_OUTPUT_DIR / "pool_femme.csv")


# ---------------------------------------------------------------------------
# Modèle réel (hors ligne, CPU)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def model():
    if not HF_CACHE.is_dir():
        pytest.skip("poids FashionCLIP absents du cache local")
    for key in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_DATASETS_OFFLINE"):
        os.environ[key] = "1"
    return run_e1.load_model()


@pytest.fixture(scope="module")
def full_run(model, tmp_path_factory):
    items, rejected = run_e1.load_items()
    embeddings, results = run_e1.run_predictions(model, items, "pad")
    out = tmp_path_factory.mktemp("e1")
    rows = run_e1.write_outputs(out, items, rejected, embeddings, results, "pad", model)
    return {"items": items, "embeddings": embeddings, "results": results, "rows": rows, "out": out}


@pytest.mark.hm_images
def test_model_outputs_are_finite_and_well_formed(full_run):
    assert full_run["embeddings"].shape == (36, 512)
    assert np.isfinite(full_run["embeddings"]).all()
    for attribute, results in full_run["results"].items():
        classes = set(attributes.ATTRIBUTES[attribute]["classes"])
        assert len(results) == 36
        for r in results:
            assert r["prediction"] in classes and r["second"] in classes and r["prediction"] != r["second"]
            assert r["margin"] >= 0 and np.isfinite(r["margin"])
            assert all(-1 <= v <= 1 for v in r["similarities"].values())
    with (full_run["out"] / "predictions.csv").open(encoding="utf-8") as handle:
        assert len(list(csv.DictReader(handle))) == 36
    metadata = json.loads((full_run["out"] / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["offline"]["HF_HUB_OFFLINE"] == "1" and metadata["schema_sha256"] == attributes.schema_fingerprint()


@pytest.mark.hm_images
def test_predictions_are_reproducible(model, full_run):
    subset = full_run["items"][:3]
    again, results = run_e1.run_predictions(model, subset, "pad")
    np.testing.assert_allclose(again, full_run["embeddings"][:3], rtol=0, atol=1e-6)
    for attribute in attributes.ATTRIBUTES:
        assert [r["prediction"] for r in results[attribute]] == \
               [r["prediction"] for r in full_run["results"][attribute][:3]]


@pytest.mark.hm_images
def test_committed_predictions_match_a_fresh_run(full_run):
    committed = E1_DIR / "output" / "predictions.csv"
    if not committed.is_file():
        pytest.skip("aucune sortie E1 enregistrée")
    saved = {r["article_id"]: r for r in csv.DictReader(open(committed, encoding="utf-8"))}
    for row in full_run["rows"]:
        for attribute in attributes.ATTRIBUTES:
            assert saved[row["article_id"]][f"{attribute}_prediction"] == row[f"{attribute}_prediction"]
            assert float(saved[row["article_id"]][f"{attribute}_margin"]) == pytest.approx(
                row[f"{attribute}_margin"], abs=1e-5)


@pytest.mark.hm_images
def test_inference_opens_no_database_connection(model, monkeypatch):
    import psycopg

    def forbidden(*args, **kwargs):
        raise AssertionError("connexion PostgreSQL interdite pendant E1")

    monkeypatch.setattr(psycopg, "connect", forbidden)
    items, _ = run_e1.load_items()
    run_e1.run_predictions(model, items[:2], "pad")
