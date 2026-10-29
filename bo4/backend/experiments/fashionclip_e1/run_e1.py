"""E1 : prédictions zéro-shot FashionCLIP sur les 36 vêtements du pool femme.

- Poids chargés HORS LIGNE depuis le cache Hugging Face local (aucun téléchargement).
- CPU uniquement, aucun entraînement, aucun appel externe, aucune base de données.
- Entrée : evaluation/data/pool_femme.csv (lecture seule, ISSUE-08 inchangé).
- Sorties (output/) : predictions.csv, similarities.csv, embeddings.npz, metadata.json.

Usage (depuis backend/) :
    .\\.venv\\Scripts\\python.exe -m experiments.fashionclip_e1.run_e1
"""

import os

# Hors ligne strict, AVANT tout import de transformers / datasets.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_DATASETS_OFFLINE", "1")

import argparse  # noqa: E402
import csv  # noqa: E402
import datetime  # noqa: E402
import json  # noqa: E402
import platform  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from evaluation.build_pools import check_image  # noqa: E402  (réutilisé tel quel)
from evaluation.common import DATA_HM_DIR, OUTPUT_DIR as EVALUATION_OUTPUT_DIR, sha256_file  # noqa: E402
from experiments.fashionclip_e1.attributes import (  # noqa: E402
    AMBIGUITY_MARGIN,
    ATTRIBUTES,
    SCHEMA_VERSION,
    schema_fingerprint,
)
from experiments.fashionclip_e1.zero_shot import class_embeddings, predict, prepare_image  # noqa: E402

E1_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = E1_DIR / "output"
POOL_CSV = EVALUATION_OUTPUT_DIR / "pool_femme.csv"
MODEL_NAME = "fashion-clip"
BACKEND_DIR = E1_DIR.parent.parent
PROTECTED_FILES = [
    "outfit_engine.py", "garment_attributes.py", "wardrobe_db_adapter.py", "main.py", "bo1_adapter.py",
]


def load_items(pool_csv=POOL_CSV, images_root=DATA_HM_DIR, checker=check_image):
    """Vêtements du pool + contrôle d'image. Renvoie (valides, rejetés)."""
    with Path(pool_csv).open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    valid, rejected = [], []
    for row in rows:
        path = Path(images_root) / row["image_path"]
        ok, reason, _, _ = checker(path)
        (valid if ok else rejected).append({**row, "image_file": str(path), "image_problem": reason})
    return valid, rejected


def load_model():
    """FashionCLIP réel, poids lus dans le cache local (échoue si absents)."""
    from fashion_clip.fashion_clip import FashionCLIP
    return FashionCLIP(MODEL_NAME)


def encode_images(model, items, image_mode):
    images = []
    for item in items:
        with Image.open(item["image_file"]) as image:
            images.append(prepare_image(image, image_mode))
    return np.asarray(model.encode_images(images, batch_size=8), dtype=np.float64)


def encode_texts(model, texts):
    """Embeddings texte avec le modèle et le préprocesseur de FashionCLIP.

    Mêmes paramètres que `FashionCLIP.encode_text` (max_length=77, padding
    "max_length", troncature, get_text_features), mais sans `datasets.map` :
    l'empreinte que calcule `datasets` sérialise le modèle et peut bloquer
    (constaté sous pytest). Équivalence vérifiée par test.
    """
    import torch

    inputs = model.preprocess(text=list(texts), return_tensors="pt", max_length=77,
                              padding="max_length", truncation=True)
    inputs = {k: v.to(model.device) for k, v in inputs.items()}
    with torch.no_grad():
        return model.model.get_text_features(**inputs).detach().cpu().numpy().astype(np.float64)


def encode_prompts(model):
    """{attribut: {classe: embeddings des formulations}}."""
    out = {}
    for attribute, spec in ATTRIBUTES.items():
        out[attribute] = {cls: encode_texts(model, info["prompts"]) for cls, info in spec["classes"].items()}
    return out


def run_predictions(model, items, image_mode="pad"):
    """Prédictions par vêtement et par attribut (sans écriture)."""
    image_embeddings = encode_images(model, items, image_mode)
    prompt_embeddings = encode_prompts(model)
    results = {}
    for attribute, by_class in prompt_embeddings.items():
        classes, matrix = class_embeddings(by_class)
        results[attribute] = predict(image_embeddings, classes, matrix)
    return image_embeddings, results


def protected_hashes():
    return {name: sha256_file(BACKEND_DIR / name) for name in PROTECTED_FILES}


def write_outputs(output_dir, items, rejected, image_embeddings, results, image_mode, model):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    prediction_rows, similarity_rows = [], []
    for index, item in enumerate(items):
        row = {"article_id": item["article_id"], "product_type_name": item["product_type_name"],
               "role": item["role"], "prod_name": item["prod_name"]}
        for attribute in ATTRIBUTES:
            result = results[attribute][index]
            row[f"{attribute}_prediction"] = result["prediction"]
            row[f"{attribute}_second"] = result["second"]
            row[f"{attribute}_margin"] = round(result["margin"], 6)
            row[f"{attribute}_ambiguous"] = int(result["ambiguous"])
            for cls, value in result["similarities"].items():
                similarity_rows.append({"article_id": item["article_id"], "attribute": attribute,
                                        "class": cls, "cosine": round(value, 8)})
        prediction_rows.append(row)

    with (output_dir / "predictions.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(prediction_rows[0]))
        writer.writeheader()
        writer.writerows(prediction_rows)
    with (output_dir / "similarities.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["article_id", "attribute", "class", "cosine"])
        writer.writeheader()
        writer.writerows(similarity_rows)
    np.savez(output_dir / "embeddings.npz", article_ids=np.array([i["article_id"] for i in items]),
             image_embeddings=image_embeddings)

    import torch
    import transformers
    metadata = {
        "experiment": "E1 FashionCLIP zero-shot attributes",
        "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "model_name": MODEL_NAME,
        "model_hash": getattr(model, "model_hash", None),
        "device": str(getattr(model, "device", "")),
        "image_mode": image_mode,
        "schema_version": SCHEMA_VERSION,
        "schema_sha256": schema_fingerprint(),
        "ambiguity_margin": AMBIGUITY_MARGIN,
        "offline": {k: os.environ.get(k) for k in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_DATASETS_OFFLINE")},
        "versions": {"python": platform.python_version(), "torch": torch.__version__,
                     "transformers": transformers.__version__, "numpy": np.__version__},
        "pool_csv_sha256": sha256_file(POOL_CSV),
        "images": {i["article_id"]: sha256_file(i["image_file"]) for i in items},
        "rejected_images": [{"article_id": r["article_id"], "image_path": r["image_path"],
                             "problem": r["image_problem"]} for r in rejected],
        "protected_files_sha256": protected_hashes(),
        "note": "Similarités cosinus non calibrées ; aucune précision calculée sans annotations humaines.",
    }
    (output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    return prediction_rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image-mode", choices=["pad", "crop"], default="pad")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()

    items, rejected = load_items()
    print(f"Vêtements : {len(items)} valides, {len(rejected)} rejetés")
    for r in rejected:
        print(f"  REJET {r['article_id']} : {r['image_problem']}")
    model = load_model()
    image_embeddings, results = run_predictions(model, items, args.image_mode)
    rows = write_outputs(args.output_dir, items, rejected, image_embeddings, results, args.image_mode, model)
    ambiguous = {a: sum(r[f"{a}_ambiguous"] for r in rows) for a in ATTRIBUTES}
    print(f"Prédictions écrites dans {args.output_dir} ; ambiguës par attribut : {ambiguous}")


if __name__ == "__main__":
    main()
