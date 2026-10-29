"""Construit le pool de vêtements du segment femme (pilote ISSUE-08).

Lecture seule de data/hm (catalogue, articles, images). Produit :
- data/pool_femme.csv            : vêtements retenus ;
- data/couverture_femme.md       : rapport de couverture par catégorie.

Usage (depuis backend/) :
    .\\.venv\\Scripts\\python.exe -m evaluation.build_pools
"""

import argparse
import collections
from pathlib import Path

from PIL import Image

from evaluation.common import (
    ARTICLES_CSV,
    CATALOG_CSV,
    DATA_HM_DIR,
    EXCLUDED_INDEX_GROUPS,
    OUTPUT_DIR,
    SEGMENT_INDEX_GROUPS,
    read_csv,
    write_csv,
)
from outfit_engine import garment_role
from wardrobe_db_adapter import normalize_category, normalize_color

POOL_FIELDS = [
    "article_id", "prod_name", "product_type_name", "category", "role", "colour_group_name",
    "color", "index_group_name", "graphical_appearance_name", "image_path", "image_width",
    "image_height",
]


def check_image(path):
    """(ok, motif, largeur, hauteur) : le fichier existe et se décode comme image."""
    path = Path(path)
    if not path.is_file():
        return False, "fichier absent", 0, 0
    if path.stat().st_size == 0:
        return False, "fichier vide", 0, 0
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            width, height = image.size
    except Exception as error:  # image corrompue ou format inconnu
        return False, f"illisible ({type(error).__name__})", 0, 0
    return True, "", width, height


def build_pool(catalog_rows, articles_by_id, images_root, image_checker=check_image):
    """Sélectionne les vêtements du segment ayant un rôle BO4 et une image valide.

    Renvoie (pool, rapport) ; le rapport compte chaque motif d'exclusion.
    """
    pool = []
    excluded = collections.Counter()
    missing_images = []
    by_type = collections.defaultdict(collections.Counter)

    for row in catalog_rows:
        article = articles_by_id.get(row["article_id"], {})
        group = article.get("index_group_name", "")
        category = normalize_category(row["product_type_name"])
        role = garment_role({"category": category})
        ptype = row["product_type_name"]

        if group not in SEGMENT_INDEX_GROUPS:
            reason = EXCLUDED_INDEX_GROUPS.get(group, f"hors segment ({group or 'inconnu'})")
            excluded[f"segment : {reason}"] += 1
            continue
        if role is None:
            excluded["catégorie sans rôle BO4"] += 1
            continue
        by_type[ptype]["segment"] += 1
        if not row["image_path"]:
            by_type[ptype]["sans image"] += 1
            excluded["sans image dans le catalogue"] += 1
            continue
        ok, reason, width, height = image_checker(Path(images_root) / row["image_path"])
        if not ok:
            by_type[ptype]["image invalide"] += 1
            excluded[f"image : {reason}"] += 1
            missing_images.append((row["article_id"], row["image_path"], reason))
            continue
        by_type[ptype]["retenus"] += 1
        pool.append({
            "article_id": row["article_id"],
            "prod_name": row["prod_name"],
            "product_type_name": ptype,
            "category": category,
            "role": role,
            "colour_group_name": row["colour_group_name"],
            "color": normalize_color(row["colour_group_name"]),
            "index_group_name": group,
            "graphical_appearance_name": article.get("graphical_appearance_name", ""),
            "image_path": row["image_path"],
            "image_width": width,
            "image_height": height,
        })

    pool.sort(key=lambda r: r["article_id"])
    report = {
        "excluded": excluded,
        "missing_images": missing_images,
        "by_type": by_type,
        "roles": collections.Counter(r["role"] for r in pool),
        "groups": collections.Counter(r["index_group_name"] for r in pool),
    }
    return pool, report


def render_report(pool, report):
    roles = report["roles"]
    tops, bottoms, outer, dresses = roles["top"], roles["bottom"], roles["outerwear"], roles["dress"]
    lines = [
        "# Couverture du pool « femme » (pilote ISSUE-08)",
        "",
        "Segment : `index_group_name` ∈ {Ladieswear, Divided}. Exclus : homme, bébé/enfant, sport.",
        "",
        f"**Vêtements retenus : {len(pool)}** — hauts {tops}, bas {bottoms}, vestes {outer}, robes {dresses}.",
        "",
        f"Tenues possibles : haut+bas {tops * bottoms}, haut+bas+veste {tops * bottoms * outer}, "
        f"robe {dresses}, robe+veste {dresses * outer} (total {tops * bottoms * (outer + 1) + dresses * (outer + 1)}).",
        "",
        "Groupes retenus : " + ", ".join(f"{g} {n}" for g, n in sorted(report["groups"].items())),
        "",
        "## Par type de produit (segment, catégories avec rôle BO4)",
        "",
        "| Type H&M | Dans le segment | Sans image | Image invalide | Retenus |",
        "|---|---|---|---|---|",
    ]
    for ptype, counts in sorted(report["by_type"].items(), key=lambda kv: -kv[1]["segment"]):
        lines.append(f"| {ptype} | {counts['segment']} | {counts['sans image']} | "
                     f"{counts['image invalide']} | {counts['retenus']} |")
    lines += ["", "## Exclusions", "", "| Motif | Nombre |", "|---|---|"]
    for reason, count in sorted(report["excluded"].items(), key=lambda kv: -kv[1]):
        lines.append(f"| {reason} | {count} |")
    lines += ["", "## Images référencées mais absentes ou illisibles", ""]
    if report["missing_images"]:
        lines += ["| article_id | image_path | motif |", "|---|---|---|"]
        lines += [f"| {a} | {p} | {r} |" for a, p, r in report["missing_images"]]
    else:
        lines.append("Aucune : toutes les images référencées du segment existent et se décodent.")
    lines += [
        "",
        "## Limites",
        "",
        "- Seuls les articles dont l'image a été téléchargée sont utilisables (501 images pour 105 542 articles).",
        f"- Robes : {dresses} seulement ; les conclusions sur les robes resteront fragiles.",
        "",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()

    articles = {r["article_id"]: r for r in read_csv(ARTICLES_CSV)}
    pool, report = build_pool(read_csv(CATALOG_CSV), articles, DATA_HM_DIR)
    write_csv(args.output_dir / "pool_femme.csv", pool, POOL_FIELDS)
    (args.output_dir / "couverture_femme.md").write_text(render_report(pool, report), encoding="utf-8")
    print(f"Pool femme : {len(pool)} vêtements {dict(report['roles'])}")
    print(f"Images absentes ou illisibles : {len(report['missing_images'])}")
    print(f"Écrit : {args.output_dir / 'pool_femme.csv'} ; {args.output_dir / 'couverture_femme.md'}")


if __name__ == "__main__":
    main()
