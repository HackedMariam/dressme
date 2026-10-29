"""Sélection déterministe des 10 images du microbenchmark E2 (hors E1, développement).

- Exclut STRICTEMENT les 36 vêtements d'E1 (pool ISSUE-08 et prédictions E1).
- Priorité aux vêtements adultes (homme, sport), puis enfant.
- Vise au moins 6 motifs H&M différents et au moins 4 rôles BO4 ; si ce n'est
  pas possible, le signale sans rien inventer.
- Écrit data/microbench_e2.csv et data/splits.json (registre de séparation).
Ces 10 images servent à la FAISABILITÉ : elles ne feront jamais partie du jeu
de test de qualité (E2-b).

Usage (depuis backend/) :
    .\\.venv\\Scripts\\python.exe -m experiments.qwen3vl_e2.select_images --seed 20261016
"""

import argparse
import csv
import json
import random
from pathlib import Path

from evaluation.build_pools import check_image
from evaluation.common import ARTICLES_CSV, CATALOG_CSV, DATA_HM_DIR, OUTPUT_DIR as EVALUATION_DIR, read_csv, sha256_file
from outfit_engine import garment_role
from wardrobe_db_adapter import normalize_category

E2_DIR = Path(__file__).resolve().parent
DATA_DIR = E2_DIR / "data"
E1_PREDICTIONS = E2_DIR.parent / "fashionclip_e1" / "output" / "predictions.csv"
DEFAULT_SEED = 20261016
SIZE = 10
MIN_PATTERNS = 6
MIN_ROLES = 4
MAX_PATTERN_PASS = 7
# Motifs H&M exigés s'ils existent (rayures : échec observé en E1-b).
REQUIRED_PATTERNS = ("Stripe", "Dot", "Front print")
# Plafond de vêtements d'extérieur (levé seulement s'il n'y a pas d'autre candidat).
MAX_OUTERWEAR = 3
GROUP_RANK = {"Menswear": 0, "Sport": 1, "Baby/Children": 2}
FIELDS = ["article_id", "image_path", "image_sha256", "product_type_name", "role", "index_group_name",
          "graphical_appearance_name", "colour_group_name", "split", "selection_reason"]


def e1_article_ids(pool_csv=EVALUATION_DIR / "pool_femme.csv", predictions_csv=E1_PREDICTIONS):
    ids = {r["article_id"] for r in read_csv(pool_csv)}
    if Path(predictions_csv).is_file():
        ids |= {r["article_id"] for r in read_csv(predictions_csv)}
    return ids


def candidates(catalog_rows, articles, excluded, images_root=DATA_HM_DIR, checker=check_image):
    """Vêtements hors E1, avec rôle BO4 et image valide ; (retenus, rejetés pour image)."""
    kept, bad_images = [], []
    for row in catalog_rows:
        if not row["image_path"] or row["article_id"] in excluded:
            continue
        role = garment_role({"category": normalize_category(row["product_type_name"])})
        if role is None:
            continue
        article = articles.get(row["article_id"], {})
        group = article.get("index_group_name", "")
        if group not in GROUP_RANK:          # femme = E1 ; autres groupes hors périmètre
            continue
        ok, reason, _, _ = checker(Path(images_root) / row["image_path"])
        if not ok:
            bad_images.append((row["article_id"], reason))
            continue
        kept.append({"article_id": row["article_id"], "image_path": row["image_path"],
                     "product_type_name": row["product_type_name"], "role": role, "index_group_name": group,
                     "graphical_appearance_name": article.get("graphical_appearance_name", ""),
                     "colour_group_name": row["colour_group_name"]})
    return kept, bad_images


def select(pool, seed=DEFAULT_SEED, size=SIZE):
    """Glouton déterministe : motifs requis, motifs variés, rôles manquants, puis
    complément adulte, avec au plus MAX_OUTERWEAR vêtements d'extérieur."""
    rng = random.Random(seed)
    ordered = sorted(pool, key=lambda r: r["article_id"])
    rng.shuffle(ordered)
    ordered.sort(key=lambda r: GROUP_RANK[r["index_group_name"]])   # tri stable : adultes d'abord
    chosen, reasons = [], {}

    def take(item, reason):
        chosen.append(item)
        reasons[item["article_id"]] = reason

    def outerwear_room(item):
        return item["role"] != "outerwear" or sum(c["role"] == "outerwear" for c in chosen) < MAX_OUTERWEAR

    problems = []
    for pattern in REQUIRED_PATTERNS:                               # 0. motifs requis
        if len(chosen) >= size:
            break
        item = next((i for i in ordered if i["graphical_appearance_name"] == pattern
                     and i not in chosen and outerwear_room(i)), None)
        if item:
            take(item, f"motif requis {pattern}")
        else:
            problems.append(f"motif requis {pattern} indisponible")
    for item in ordered:                                            # 1. motifs H&M distincts
        if len(chosen) >= min(size, MAX_PATTERN_PASS):
            break
        if (item not in chosen and outerwear_room(item)
                and item["graphical_appearance_name"] not in {c["graphical_appearance_name"] for c in chosen}):
            take(item, "motif H&M nouveau")
    for role in ("top", "bottom", "outerwear", "dress"):           # 2. rôles manquants
        if len(chosen) >= size or role in {c["role"] for c in chosen}:
            continue
        item = next((i for i in ordered if i["role"] == role and i not in chosen), None)
        if item:
            take(item, f"rôle {role} manquant")
    for item in ordered:                                            # 3. complément sous plafond
        if len(chosen) >= size:
            break
        if item not in chosen and outerwear_room(item):
            take(item, "complément (ordre de priorité)")
    for item in ordered:                                            # 4. plafond levé si nécessaire
        if len(chosen) >= size:
            break
        if item not in chosen:
            take(item, "complément (plafond de vestes levé)")
            problems.append("plafond de vêtements d'extérieur dépassé faute d'autres candidats")

    patterns = {c["graphical_appearance_name"] for c in chosen}
    roles = {c["role"] for c in chosen}
    if len(chosen) < size:
        problems.append(f"seulement {len(chosen)} images disponibles (cible {size})")
    if len(patterns) < MIN_PATTERNS:
        problems.append(f"diversité de motifs insuffisante : {len(patterns)} < {MIN_PATTERNS}")
    if len(roles) < MIN_ROLES:
        problems.append(f"diversité de rôles insuffisante : {len(roles)} < {MIN_ROLES}")
    return chosen, reasons, problems


def write_outputs(chosen, reasons, e1_ids, seed, data_dir=DATA_DIR, images_root=DATA_HM_DIR):
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    rows = [{**item, "image_sha256": sha256_file(Path(images_root) / item["image_path"]),
             "split": "e2_microbench_dev", "selection_reason": reasons[item["article_id"]]} for item in chosen]
    with (data_dir / "microbench_e2.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    splits = {
        "seed": seed,
        "e1_test_sealed": sorted(e1_ids),
        "e2_microbench_dev": sorted(r["article_id"] for r in rows),
        "rule": "Tout futur jeu de test de qualité (E2-b) doit exclure les deux listes ci-dessus.",
    }
    (data_dir / "splits.json").write_text(json.dumps(splits, indent=2, ensure_ascii=False), encoding="utf-8")
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args()
    e1_ids = e1_article_ids()
    articles = {r["article_id"]: r for r in read_csv(ARTICLES_CSV)}
    pool, bad = candidates(read_csv(CATALOG_CSV), articles, e1_ids)
    chosen, reasons, problems = select(pool, args.seed)
    assert not ({c["article_id"] for c in chosen} & e1_ids), "image E1 sélectionnée"
    rows = write_outputs(chosen, reasons, e1_ids, args.seed)
    print(f"E1 exclus : {len(e1_ids)} | candidats hors E1 : {len(pool)} | images invalides : {len(bad)}")
    for r in rows:
        print(f"  {r['article_id']} {r['product_type_name']:10} {r['role']:9} {r['index_group_name']:13} "
              f"{r['graphical_appearance_name']:18} ({r['selection_reason']})")
    print("PROBLÈMES :" if problems else "Diversité atteinte.", *problems, sep="\n  ")


if __name__ == "__main__":
    main()
