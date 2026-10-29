"""Échantillon pilote de 20 couples tenue-contexte et manifeste reproductible.

Les tenues sont générées par le moteur BO4 actuel (inchangé) à partir du pool
femme. Le score moteur sert uniquement à STRATIFIER l'échantillon et à
l'analyse future ; il n'est jamais une vérité terrain et n'est jamais montré
aux annotateurs.

Plan (fixe, documenté) :
- 16 tirages stratifiés : 4 saisons x 4 structures (haut+bas, haut+bas+veste,
  robe, robe+veste) ; tercile de score (haut / milieu / bas) en rotation
  (indice saison + indice structure) mod 3, occasion « university » ;
- 4 tirages aléatoires (1 par saison) parmi toutes les tenues de la saison,
  avec une occasion différente par saison (work, evening, casual, university)
  pour tester le critère d'occasion du guide.
Une tenue déjà retenue n'est pas reprise tant qu'une alternative existe dans
la strate ; un couple tenue-contexte n'est jamais dupliqué.

Usage (depuis backend/) :
    .\\.venv\\Scripts\\python.exe -m evaluation.sample_outfits --seed 20261015
"""

import argparse
import hashlib
import json
import random
from pathlib import Path

from evaluation.common import (
    CATALOG_CSV,
    DEFAULT_SEED,
    OUTPUT_DIR,
    RowsConnection,
    engine_fingerprints,
    read_csv,
    write_csv,
)
from outfit_engine import SEASONS, garment_role, recommend_outfits
from wardrobe_db_adapter import load_user_wardrobe

PILOT_SIZE = 20
STRATIFIED_OCCASION = "university"
RANDOM_OCCASIONS = ("work", "evening", "casual", "university")  # une par saison
STRUCTURES = ("haut+bas", "haut+bas+veste", "robe", "robe+veste")
TERCILES = ("haut", "milieu", "bas")
ALL = 10 ** 6

MANIFEST_FIELDS = [
    "sample_id", "slot", "season", "occasion", "structure", "selection_method", "stratum",
    "score_tercile", "pool_size", "rank_in_pool", "n_items", "article_ids", "categories",
    "product_types", "names", "image_paths", "engine_score", "color_score", "style_score",
    "occasion_score", "season_score", "engine_explanations", "seed", "segment",
    "sha256_outfit_engine", "sha256_garment_attributes", "sha256_wardrobe_db_adapter",
    "sha256_catalog_products",
]

STRUCTURE_BY_ROLES = {
    ("top", "bottom"): "haut+bas",
    ("top", "bottom", "outerwear"): "haut+bas+veste",
    ("dress",): "robe",
    ("dress", "outerwear"): "robe+veste",
}


def structure_of(outfit):
    return STRUCTURE_BY_ROLES[tuple(garment_role(i) for i in outfit["items"])]


def outfit_ids(outfit):
    return tuple(i["id"] for i in outfit["items"])


def load_pool_wardrobe(pool_rows, catalog_rows):
    """Vêtements du pool au format moteur, via l'adaptateur réel (lecture seule)."""
    catalog = {r["article_id"]: r for r in catalog_rows}
    rows = []
    for item in pool_rows:
        product = catalog[item["article_id"]]
        rows.append((
            item["article_id"], 0, item["article_id"], product["image_path"], product["prod_name"],
            product["product_type_name"], product["colour_group_name"], product["detail_desc"],
        ))
    return load_user_wardrobe(RowsConnection(rows), 0)


def tercile_of(position, size):
    """Tercile positionnel dans l'ordre moteur (score décroissant, départage ISSUE-06)."""
    if position < size / 3:
        return "haut"
    if position < 2 * size / 3:
        return "milieu"
    return "bas"


def sample_id(seed, season, occasion, ids):
    digest = hashlib.sha256(f"{seed}|{season}|{occasion}|{'-'.join(ids)}".encode()).hexdigest()
    return f"T{digest[:8]}"


def build_plan():
    plan = []
    for s_index, season in enumerate(SEASONS):
        for t_index, structure in enumerate(STRUCTURES):
            plan.append({"season": season, "occasion": STRATIFIED_OCCASION, "method": "stratifié",
                         "structure": structure, "tercile": TERCILES[(s_index + t_index) % 3]})
        plan.append({"season": season, "occasion": RANDOM_OCCASIONS[s_index], "method": "aléatoire",
                     "structure": None, "tercile": None})
    assert len(plan) == PILOT_SIZE
    return plan


def draw_sample(wardrobe, seed):
    """Applique le plan ; renvoie la liste des tirages et les pénuries éventuelles."""
    ranked_cache = {}

    def ranked(season, occasion):
        if (season, occasion) not in ranked_cache:
            ranked_cache[(season, occasion)] = recommend_outfits(
                wardrobe, occasion, season, top_k=ALL, diversify=False)
        return ranked_cache[(season, occasion)]

    chosen_outfits, chosen_pairs, draws, shortages = set(), set(), [], []
    for slot, step in enumerate(build_plan(), start=1):
        rng = random.Random(f"{seed}:{slot}:{step['season']}:{step['occasion']}")
        everything = ranked(step["season"], step["occasion"])
        if step["method"] == "stratifié":
            stratum = [r for r in everything if structure_of(r) == step["structure"]]
            positions = {outfit_ids(r): n for n, r in enumerate(stratum)}
            candidates = [r for r in stratum
                          if tercile_of(positions[outfit_ids(r)], len(stratum)) == step["tercile"]]
            pool_size = len(stratum)
        else:
            candidates = list(everything)
            positions = {outfit_ids(r): n for n, r in enumerate(everything)}
            pool_size = len(everything)

        context = (step["season"], step["occasion"])
        fresh = [r for r in candidates if outfit_ids(r) not in chosen_outfits]
        allowed = fresh or [r for r in candidates if (outfit_ids(r), context) not in chosen_pairs]
        if not fresh:
            shortages.append(f"slot {slot} ({step['season']}, {step['structure'] or 'aléatoire'}, "
                             f"{step['tercile'] or '-'}) : tenue déjà utilisée dans un autre contexte")
        if not allowed:
            shortages.append(f"slot {slot} : aucune tenue disponible")
            continue

        outfit = allowed[rng.randrange(len(allowed))]
        chosen_outfits.add(outfit_ids(outfit))
        chosen_pairs.add((outfit_ids(outfit), context))
        position = positions[outfit_ids(outfit)]
        draws.append({
            "slot": slot,
            "step": step,
            "outfit": outfit,
            "pool_size": pool_size,
            "rank_in_pool": position + 1,
            "tercile": step["tercile"] or tercile_of(position, pool_size),
        })
    return draws, shortages


def manifest_rows(draws, seed, fingerprints):
    rows = []
    for draw in draws:
        step, outfit = draw["step"], draw["outfit"]
        items = outfit["items"]
        structure = structure_of(outfit)
        ids = [i["id"] for i in items]
        rows.append({
            "sample_id": sample_id(seed, step["season"], step["occasion"], ids),
            "slot": draw["slot"],
            "season": step["season"],
            "occasion": step["occasion"],
            "structure": structure,
            "selection_method": step["method"],
            "stratum": (f"{step['season']}|{structure}|tercile={draw['tercile']}"
                        if step["method"] == "stratifié" else f"{step['season']}|toutes structures"),
            "score_tercile": draw["tercile"],
            "pool_size": draw["pool_size"],
            "rank_in_pool": draw["rank_in_pool"],
            "n_items": len(items),
            "article_ids": "|".join(ids),
            "categories": "|".join(i["category"] for i in items),
            "product_types": "|".join(i.get("product_type_name", "") for i in items),
            "names": "|".join(i["name"] for i in items),
            "image_paths": "|".join(i["image_path"] for i in items),
            "engine_score": outfit["score"],
            "color_score": outfit["color_score"],
            "style_score": outfit["style_score"],
            "occasion_score": outfit["occasion_score"],
            "season_score": outfit["season_score"],
            "engine_explanations": json.dumps(outfit["explanations"], ensure_ascii=False),
            "seed": seed,
            "segment": "femme",
            "sha256_outfit_engine": fingerprints["outfit_engine.py"],
            "sha256_garment_attributes": fingerprints["garment_attributes.py"],
            "sha256_wardrobe_db_adapter": fingerprints["wardrobe_db_adapter.py"],
            "sha256_catalog_products": fingerprints["catalog_products.csv"],
        })
    return rows


def run(pool_csv, seed):
    pool_rows = read_csv(pool_csv)
    catalog_rows = read_csv(CATALOG_CSV)
    wardrobe = load_pool_wardrobe(pool_rows, catalog_rows)
    types = {r["article_id"]: r["product_type_name"] for r in pool_rows}
    for item in wardrobe:
        item["product_type_name"] = types[item["id"]]
    draws, shortages = draw_sample(wardrobe, seed)
    return manifest_rows(draws, seed, engine_fingerprints()), shortages


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--pool", type=Path, default=OUTPUT_DIR / "pool_femme.csv")
    parser.add_argument("--output", type=Path, default=OUTPUT_DIR / "manifeste_pilote.csv")
    args = parser.parse_args()

    rows, shortages = run(args.pool, args.seed)
    write_csv(args.output, rows, MANIFEST_FIELDS)
    print(f"Manifeste : {args.output} ({len(rows)} couples tenue-contexte, graine {args.seed})")
    for note in shortages:
        print("  NOTE :", note)


if __name__ == "__main__":
    main()
