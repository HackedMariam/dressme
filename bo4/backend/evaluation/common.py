"""Éléments partagés par les scripts d'évaluation (lecture seule des données H&M)."""

import csv
import hashlib
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_HM_DIR = BACKEND_DIR.parent / "data" / "hm"
CATALOG_CSV = DATA_HM_DIR / "catalog_products.csv"
ARTICLES_CSV = DATA_HM_DIR / "articles.csv"
OUTPUT_DIR = Path(__file__).resolve().parent / "data"

# Segment du pilote : vêtements femme. Les autres groupes sont exclus.
SEGMENT_NAME = "femme"
SEGMENT_INDEX_GROUPS = {"Ladieswear", "Divided"}
EXCLUDED_INDEX_GROUPS = {
    "Menswear": "homme",
    "Baby/Children": "bébé/enfant",
    "Sport": "sport (genre non garanti)",
}

DEFAULT_SEED = 20261015

# Fichiers dont dépend le moteur évalué (empreintes enregistrées dans le manifeste).
ENGINE_FILES = {
    "outfit_engine.py": BACKEND_DIR / "outfit_engine.py",
    "garment_attributes.py": BACKEND_DIR / "garment_attributes.py",
    "wardrobe_db_adapter.py": BACKEND_DIR / "wardrobe_db_adapter.py",
    "catalog_products.csv": CATALOG_CSV,
}


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def engine_fingerprints():
    return {name: sha256_file(path) for name, path in ENGINE_FILES.items()}


def read_csv(path):
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, rows, fieldnames):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


class RowsConnection:
    """Connexion minimale en mémoire pour réutiliser load_user_wardrobe tel quel
    (mêmes normalisations et même extraction d'attributs que l'API)."""

    def __init__(self, rows):
        self._rows = rows

    def cursor(self, row_factory=None):
        rows = self._rows

        class _Cursor:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def execute(self, query, params=None):
                pass

            def fetchall(self):
                return list(rows)

        return _Cursor()
