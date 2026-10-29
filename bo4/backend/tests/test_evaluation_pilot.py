"""Tests du protocole d'évaluation pilote (ISSUE-08, phase 1).

- Partie hermétique : données synthétiques (CSV et images créés à la volée).
- Partie données réelles : ignorée si les fichiers H&M sont absents. Toutes les
  sorties sont écrites dans un dossier temporaire.
Aucune annotation n'est créée ni simulée.
"""

import collections
import json
import re

import pytest
from PIL import Image

from evaluation import annotation_pack, build_pools, sample_outfits
from evaluation.common import (
    ARTICLES_CSV,
    CATALOG_CSV,
    DATA_HM_DIR,
    DEFAULT_SEED,
    engine_fingerprints,
    read_csv,
    write_csv,
)
from outfit_engine import OCCASION_STYLES, SEASONS, garment_role, recommend_outfits

VALID_STRUCTURES = {"haut+bas", "haut+bas+veste", "robe", "robe+veste"}
FORBIDDEN_FOR_ANNOTATORS = re.compile(
    r"score|tercile|strat|rank|explanation|explication|engine|moteur|selection|aléatoire|stratifié",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Partie hermétique : build_pool
# ---------------------------------------------------------------------------

def _jpeg(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 12), "white").save(path, "JPEG")


@pytest.fixture
def synthetic(tmp_path):
    images = tmp_path / "hm"
    rows, articles = [], {}

    def add(article_id, ptype, group, image="ok"):
        path = f"images/{article_id[:3]}/{article_id}.jpg" if image else ""
        if image == "ok":
            _jpeg(images / path)
        elif image == "corrupt":
            (images / path).parent.mkdir(parents=True, exist_ok=True)
            (images / path).write_bytes(b"not an image")
        rows.append({"article_id": article_id, "prod_name": f"name {article_id}", "product_type_name": ptype,
                     "colour_group_name": "Black", "image_path": path, "detail_desc": ""})
        articles[article_id] = {"index_group_name": group, "graphical_appearance_name": "Solid"}

    add("0100000001", "Shirt", "Ladieswear")
    add("0100000002", "Trousers", "Divided")
    add("0100000003", "Dress", "Ladieswear")
    add("0100000004", "Shirt", "Menswear")
    add("0100000005", "Shirt", "Baby/Children")
    add("0100000006", "Shirt", "Sport")
    add("0100000007", "Socks", "Ladieswear")                 # pas de rôle BO4
    add("0100000008", "Skirt", "Ladieswear", image="")       # pas d'image dans le catalogue
    add("0100000009", "Blouse", "Ladieswear", image="missing")
    add("0100000010", "Coat", "Ladieswear", image="corrupt")
    return rows, articles, images


def test_pool_keeps_only_segment_items_with_role_and_valid_image(synthetic):
    rows, articles, images = synthetic
    pool, report = build_pools.build_pool(rows, articles, images)
    assert [p["article_id"] for p in pool] == ["0100000001", "0100000002", "0100000003"]
    assert {p["index_group_name"] for p in pool} <= {"Ladieswear", "Divided"}
    assert report["roles"] == {"top": 1, "bottom": 1, "dress": 1}


def test_pool_reports_every_exclusion(synthetic):
    rows, articles, images = synthetic
    _, report = build_pools.build_pool(rows, articles, images)
    excluded = report["excluded"]
    assert excluded["segment : homme"] == 1
    assert excluded["segment : bébé/enfant"] == 1
    assert excluded["segment : sport (genre non garanti)"] == 1
    assert excluded["catégorie sans rôle BO4"] == 1
    assert excluded["sans image dans le catalogue"] == 1
    assert excluded["image : fichier absent"] == 1
    assert any(k.startswith("image : illisible") for k in excluded)
    assert {a for a, _, _ in report["missing_images"]} == {"0100000009", "0100000010"}
    text = build_pools.render_report([], report)
    assert "0100000009" in text and "0100000010" in text


# ---------------------------------------------------------------------------
# Partie données réelles
# ---------------------------------------------------------------------------

real_data = pytest.mark.skipif(
    not (CATALOG_CSV.is_file() and ARTICLES_CSV.is_file()), reason="données H&M absentes")


@pytest.fixture(scope="module")
def pilot(tmp_path_factory):
    if not (CATALOG_CSV.is_file() and ARTICLES_CSV.is_file()):
        pytest.skip("données H&M absentes")
    out = tmp_path_factory.mktemp("pilot")
    catalog = read_csv(CATALOG_CSV)
    articles = {r["article_id"]: r for r in read_csv(ARTICLES_CSV)}
    pool, report = build_pools.build_pool(catalog, articles, DATA_HM_DIR)
    pool_csv = out / "pool.csv"
    write_csv(pool_csv, pool, build_pools.POOL_FIELDS)
    manifest, shortages = sample_outfits.run(pool_csv, DEFAULT_SEED)
    return {"catalog": catalog, "articles": articles, "pool": pool, "report": report,
            "pool_csv": pool_csv, "manifest": manifest, "shortages": shortages}


@real_data
def test_real_pool_is_segment_only_with_existing_images(pilot):
    assert pilot["pool"], "pool vide"
    for item in pilot["pool"]:
        assert pilot["articles"][item["article_id"]]["index_group_name"] in {"Ladieswear", "Divided"}
        assert garment_role({"category": item["category"]}) == item["role"]
        assert (DATA_HM_DIR / item["image_path"]).is_file()
    assert pilot["report"]["missing_images"] == []


@real_data
def test_sampling_is_reproducible(pilot):
    again, _ = sample_outfits.run(pilot["pool_csv"], DEFAULT_SEED)
    assert again == pilot["manifest"]
    other, _ = sample_outfits.run(pilot["pool_csv"], DEFAULT_SEED + 1)
    assert [r["sample_id"] for r in other] != [r["sample_id"] for r in pilot["manifest"]]


@real_data
def test_manifest_composition(pilot):
    rows = pilot["manifest"]
    assert len(rows) == sample_outfits.PILOT_SIZE
    assert {r["season"] for r in rows} == set(SEASONS)
    assert {r["structure"] for r in rows} == VALID_STRUCTURES
    assert {r["selection_method"] for r in rows} == {"stratifié", "aléatoire"}
    assert all(r["occasion"] in OCCASION_STYLES for r in rows)
    pairs = [(r["article_ids"], r["season"], r["occasion"]) for r in rows]
    assert len(pairs) == len(set(pairs))                                  # pas de doublon tenue-contexte
    assert len({r["sample_id"] for r in rows}) == len(rows)
    plan = sample_outfits.build_plan()
    for row in rows:
        step = plan[int(row["slot"]) - 1]
        assert (row["season"], row["occasion"]) == (step["season"], step["occasion"])
        if step["method"] == "stratifié":
            assert row["structure"] == step["structure"]
            assert row["score_tercile"] == step["tercile"]


@real_data
def test_manifest_items_are_valid_structures_from_the_pool(pilot):
    pool = {p["article_id"]: p for p in pilot["pool"]}
    allowed = {("top", "bottom"), ("top", "bottom", "outerwear"), ("dress",), ("dress", "outerwear")}
    for row in pilot["manifest"]:
        ids = row["article_ids"].split("|")
        assert all(i in pool for i in ids)
        assert int(row["n_items"]) == len(ids) == len(row["image_paths"].split("|"))
        assert tuple(pool[i]["role"] for i in ids) in allowed
        assert all((DATA_HM_DIR / p).is_file() for p in row["image_paths"].split("|"))


@real_data
def test_manifest_scores_and_fingerprints_are_consistent(pilot):
    fingerprints = engine_fingerprints()
    wardrobe = sample_outfits.load_pool_wardrobe(pilot["pool"], pilot["catalog"])
    cache = {}
    for row in pilot["manifest"]:
        assert row["seed"] == DEFAULT_SEED
        assert row["sha256_outfit_engine"] == fingerprints["outfit_engine.py"]
        assert row["sha256_garment_attributes"] == fingerprints["garment_attributes.py"]
        assert row["sha256_wardrobe_db_adapter"] == fingerprints["wardrobe_db_adapter.py"]
        assert row["sha256_catalog_products"] == fingerprints["catalog_products.csv"]
        context = (row["season"], row["occasion"])
        if context not in cache:
            ranked = recommend_outfits(wardrobe, row["occasion"], row["season"], top_k=10 ** 6, diversify=False)
            cache[context] = {tuple(i["id"] for i in r["items"]): r for r in ranked}
        outfit = cache[context][tuple(row["article_ids"].split("|"))]
        assert row["engine_score"] == outfit["score"]
        assert row["season_score"] == outfit["season_score"]
        assert json.loads(row["engine_explanations"]) == outfit["explanations"]


@real_data
def test_reuse_of_outfits_is_reported(pilot):
    used = collections.Counter(r["article_ids"] for r in pilot["manifest"])
    reused = sum(n - 1 for n in used.values() if n > 1)
    assert reused == len(pilot["shortages"])


# ---------------------------------------------------------------------------
# Données exposées à l'annotateur
# ---------------------------------------------------------------------------

@real_data
def test_annotator_payload_has_no_engine_information(pilot):
    samples = annotation_pack.annotator_payload(pilot["manifest"], pilot["catalog"])
    assert {s["id"] for s in samples} == {r["sample_id"] for r in pilot["manifest"]}
    engine_values = {str(r[k]) for r in pilot["manifest"]
                     for k in ("engine_score", "color_score", "season_score", "rank_in_pool")}
    for sample in samples:
        assert set(sample) == annotation_pack.SAMPLE_KEYS
        for item in sample["items"]:
            assert set(item) == annotation_pack.ITEM_KEYS
        text = json.dumps(sample, ensure_ascii=False)
        assert not FORBIDDEN_FOR_ANNOTATORS.search(json.dumps(
            {k: v for k, v in sample.items() if k != "items"}, ensure_ascii=False))
        for value in engine_values:
            assert f'"{value}"' not in text


@real_data
def test_generated_html_hides_engine_information_and_embeds_valid_images(pilot):
    samples = annotation_pack.annotator_payload(pilot["manifest"], pilot["catalog"])
    images = annotation_pack.embed_images(pilot["manifest"], DATA_HM_DIR)
    sizes = annotation_pack.verify_embedded_images(images)
    expected = {i for r in pilot["manifest"] for i in r["article_ids"].split("|")}
    assert set(sizes) == expected
    html = annotation_pack.render_html(samples, images, "test")
    visible = re.sub(r"data:image/jpeg;base64,[A-Za-z0-9+/=]+", "", html)
    assert not FORBIDDEN_FOR_ANNOTATORS.search(visible)
    assert "http://" not in visible and "https://" not in visible       # aucune ressource distante
    for row in pilot["manifest"]:
        assert row["sample_id"] in html
