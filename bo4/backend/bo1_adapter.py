import json
from pathlib import Path


def load_wardrobe_from_bo1(json_path):
    path = Path(json_path)

    if not path.is_file():
        raise FileNotFoundError(f"Fichier introuvable : {path}")

    with path.open("r", encoding="utf-8") as f:
        records = json.load(f)

    if not isinstance(records, list):
        raise ValueError("Le JSON doit contenir une liste de vêtements.")

    wardrobe = []

    for record in records:
        if record.get("quality_status") != "accepted":
            continue

        metadata = record.get("metadata") or {}
        fusion = record.get("fusion") or {}
        color_fusion = record.get("color_fusion") or {}

        item = {
            "id": str(record["item_id"]),
            "category": fusion.get("subcategory")
                        or metadata.get("subcategory")
                        or "unknown",
            "color": color_fusion.get("primary_color")
                     or metadata.get("primary_color")
                     or "unknown",
            "style": "unknown",
            "image_path": record.get("crop_path"),
            "review_status": record.get("review_status"),
        }

        wardrobe.append(item)

    return wardrobe


if __name__ == "__main__":
    json_path = "../bo1/outputs/test_14/metadata.json"
    wardrobe = load_wardrobe_from_bo1(json_path)

    print("\n=== BO4 : GARDE-ROBE IMPORTÉE DE BO1 ===")
    print(json.dumps(wardrobe, indent=2, ensure_ascii=False))
    print(f"\nNombre de vêtements importés : {len(wardrobe)}")
