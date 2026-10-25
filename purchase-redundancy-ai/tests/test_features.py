"""Every one of the 31 features runs through the /feature endpoint with realistic inputs"""

import json

import pytest

ITEM = {"name": "Navy Wool Blazer", "category": "outerwear", "color": "navy", "style": "business",
        "material": "wool", "price": 180, "brand": "Ralph Lauren", "season": "fall",
        "durability_score": 0.9, "sustainability_rating": 0.7, "size_range": ["S", "M", "L"]}


def feature_inputs(wardrobe):
    emb_a = [1.0] + [0.0] * 511
    emb_b = [0.8, 0.6] + [0.0] * 510
    return {
        1: {"embedding1": emb_a, "embedding2": emb_b},
        2: {"visual_sim": 0.8, "color_match": True, "style_match": False, "material_match": True},
        3: {"item1": wardrobe[0], "item2": wardrobe[1]},
        4: {"new_item_embedding": emb_a, "wardrobe_items": [{"id": "a", "name": "A", "embedding": emb_b}]},
        5: {"visual_redundancy": 80, "functional_redundancy": 70, "category_saturation": 40, "outfit_contribution": 30},
        6: {"image_base64": None},  # replaced below with a real image
        7: {"screenshot_data": "", "page_text": "Zara navy wool blazer - $129.99"},
        8: {"wardrobe_items": wardrobe, "new_item": ITEM, "similar_items": []},
        9: {"wardrobe_items": wardrobe, "new_item_category": "shirts"},
        10: {"item_id": "x", "feedback_type": "helpful", "rating": 5},
        11: {"redundancy_score": 85, "similar_items": [{"name": "Navy Oxford Shirt"}], "recommendation": "skip"},
        12: {"item_name": "Navy shirt", "redundancy_score": 70, "similar_items": [{"name": "Navy Oxford Shirt", "similarity": 0.8}], "recommendation": "skip"},
        13: {"new_item": ITEM, "similar_items": [{"name": "Navy Oxford Shirt", "similarity": 0.8}]},
        14: {"wardrobe": wardrobe},
        15: {"wardrobes": [wardrobe, wardrobe[:2]]},
        16: {"wardrobe": wardrobe, "season": "winter"},
        17: {"colors": ["navy", "red", "green"]},
        18: {"wardrobe": wardrobe},
        19: {"budget": 500, "wardrobe": wardrobe},
        20: {"item": ITEM},
        21: {"wardrobe": wardrobe, "event_type": "interview"},
        22: {"wardrobe": wardrobe},
        23: {"item": ITEM},
        24: {"item": ITEM},
        25: {"item": ITEM},
        26: {"wardrobe": wardrobe},
        27: {"items": wardrobe},
        28: {"item": ITEM, "user_size": "M", "fit_preference": "oversized"},
        29: {"item": ITEM},
        30: {"wardrobe": wardrobe},
        31: {"item": ITEM},
    }


@pytest.mark.parametrize("feature_id", range(1, 32))
def test_feature(client, wardrobe, feature_id):
    from test_api import _png_base64

    args = feature_inputs(wardrobe)[feature_id]
    if feature_id == 6:
        args = {"image_base64": _png_base64()}

    r = client.post(f"/feature/{feature_id}", json=args)
    assert r.status_code == 200, r.text
    result = r.json()["result"]
    assert result is not None
    json.dumps(result)  # serializable


def test_feature_values(client, wardrobe):
    run = lambda fid, args: client.post(f"/feature/{fid}", json=args).json()["result"]
    assert run(5, {"visual_redundancy": 100, "functional_redundancy": 100, "category_saturation": 100, "outfit_contribution": 0}) == 100
    extracted = run(7, {"screenshot_data": "", "page_text": "Zara navy wool blazer - $129.99"})["attributes_extracted"]
    assert {k: extracted[k] for k in ("price", "color", "material")} == {"price": 129.99, "color": "navy", "material": "wool"}
    assert run(17, {"colors": ["black", "white", "navy"]})["harmony_score"] == 1.0
    assert run(25, {"item": {"price": None}})["estimated_resale"] == 0.0  # used to crash
    capsule = run(26, {"wardrobe": wardrobe})
    assert capsule["size"] == 4  # catalog categories are plural ("shirts") - used to return []
    assert run(28, {"item": ITEM, "user_size": "M", "fit_preference": "oversized"})["recommended_size"] == "L"


def test_unknown_attributes_are_neutral():
    from features import FeatureSet

    # Real products often miss the material: unknown must not count as a mismatch
    known_mismatch = FeatureSet.feature_2_similarity_score(0.6, True, True, False)
    unknown = FeatureSet.feature_2_similarity_score(0.6, True, True, False, material_known=False)
    known_match = FeatureSet.feature_2_similarity_score(0.6, True, True, True)
    assert known_mismatch < unknown < known_match
    attrs = FeatureSet.feature_3_attribute_comparison({"color": "black", "material": None}, {"color": "black", "material": "cotton"})
    assert attrs["color_known"] and not attrs["material_known"]


def test_image_scale_is_calibrated_on_the_catalog():
    import numpy as np

    from engine import RedundancyEngine

    rng = np.random.default_rng(0)
    base = {c: rng.normal(size=512) for c in ("shirts", "shoes", "pants")}
    catalog, rows = [], []
    for k in range(90):
        category = ("shirts", "shoes", "pants")[k % 3]
        catalog.append({"id": str(k), "category": category, "subcategory": category, "primary_color": "black" if k % 2 else "white"})
        v = base[category] + rng.normal(scale=1.2, size=512)
        rows.append(v / np.linalg.norm(v))
    engine = RedundancyEngine.__new__(RedundancyEngine)
    engine.catalog, engine.catalog_image_embeddings = catalog, np.asarray(rows, dtype=np.float32)
    engine.image_floor, engine.image_ceiling = 0.75, 1.0
    floor, ceiling = engine._calibrate_image_scale()
    unrelated = float(np.median([rows[0] @ rows[1], rows[0] @ rows[2]]))
    assert floor < ceiling and abs(floor - unrelated) < 0.15   # floor sits at the cross-category level
    assert engine._rescale(floor, floor, ceiling) == 0.0 and engine._rescale(ceiling, floor, ceiling) == 1.0
