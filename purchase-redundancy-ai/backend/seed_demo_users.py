"""
Demo accounts - women and men with complete profiles and realistic starter wardrobes (40+ real catalog
photos each: tops, bottoms, dresses, shoes, bags, watches, belts...), plus purchase candidates analyzed
by the real engine (CLIP image + text comparison).

    cd backend
    venv/Scripts/python seed_demo_users.py            # create the accounts that do not exist yet
    venv/Scripts/python seed_demo_users.py --reset    # rebuild the demo accounts' profiles, wardrobes and histories
    venv/Scripts/python seed_demo_users.py --llm      # also let GPT/Claude write the explanations (paid API calls)

Only accounts listed in PROFILES are touched. Prices are never invented: wardrobe items keep the catalog
price (often unknown), and purchase candidates are preferably products whose source publishes a price.
"""

import argparse
import os
import random
import sys
from collections import Counter
from typing import Dict, List

from wardrobe_builder import build_starter_wardrobe, fits

DEMO_PASSWORD = os.getenv("DEMO_PASSWORD", "Doublon-Demo2026")

# Same attributes as the sign-up form
PROFILES = [
    {"email": "sofia.martin@example.com", "display_name": "Sofia Martin", "gender": "Women", "seed": 11,
     "clothing_size": "S", "shoe_size": "38", "style_preferences": ["formal", "classic"],
     "favorite_colors": ["black", "white", "beige", "navy", "gray"]},
    {"email": "emma.laurent@example.com", "display_name": "Emma Laurent", "gender": "Women", "seed": 23,
     "clothing_size": "M", "shoe_size": "39", "style_preferences": ["casual"],
     "favorite_colors": ["pink", "red", "blue", "white", "green", "yellow"]},
    {"email": "karim.benali@example.com", "display_name": "Karim Benali", "gender": "Men", "seed": 37,
     "clothing_size": "L", "shoe_size": "43", "style_preferences": ["formal", "classic"],
     "favorite_colors": ["navy", "white", "gray", "black", "blue", "brown"]},
    {"email": "yassine.haddad@example.com", "display_name": "Yassine Haddad", "gender": "Men", "seed": 41,
     "clothing_size": "M", "shoe_size": "42", "style_preferences": ["sporty", "casual"],
     "favorite_colors": ["black", "white", "red", "green", "blue", "gray"]},
]
PROFILE_KEYS = ("display_name", "gender", "clothing_size", "shoe_size", "style_preferences", "favorite_colors")
NEAR_DUPLICATES = 2   # real wardrobes contain a couple of almost identical pieces (great for the audit)
CANDIDATES = 6        # purchases each person considers -> analyses in their history


def size_for(product: Dict, profile: Dict):
    if product["category"] == "shoes":
        return profile["shoe_size"]
    return None if product["category"] == "accessories" else profile["clothing_size"]


def pick_candidates(catalog: List[Dict], wardrobe: List[Dict], profile: Dict, rng: random.Random) -> List[Dict]:
    """Half look like something already owned (should be flagged), half fill a gap"""
    owned = {p["id"] for p in wardrobe}
    available = [p for p in catalog if p["id"] not in owned and fits(p, profile["gender"])]
    priced_first = lambda items: sorted(items, key=lambda p: (not p.get("price"), rng.random()))

    lookalikes = []
    for base in rng.sample(wardrobe, k=len(wardrobe)):
        twins = [p for p in available if p.get("subcategory") == base.get("subcategory")
                 and p.get("primary_color") == base.get("primary_color") and p not in lookalikes]
        if twins:
            lookalikes.append(priced_first(twins)[0])
        if len(lookalikes) == CANDIDATES // 2:
            break

    counts = Counter(p["category"] for p in wardrobe)
    rare = sorted(counts, key=lambda c: counts[c])[:3]
    fillers = priced_first([p for p in available if p["category"] in rare and p not in lookalikes])
    return lookalikes + fillers[:CANDIDATES - len(lookalikes)]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reset", action="store_true", help="rebuild the demo accounts' wardrobes and histories")
    parser.add_argument("--llm", action="store_true", help="let the LLM write explanations (paid API calls)")
    args = parser.parse_args(argv)

    os.environ["RATE_LIMIT_ENABLED"] = "False"   # in-process seeding, no HTTP clients to protect from
    if not args.llm:
        os.environ["LLM_ENABLED"] = "False"
    from fastapi.testclient import TestClient
    import main as api
    from models import SimilarityAnalysis

    rows = []
    with TestClient(api.app) as client:
        catalog, db, by_id = api.state["catalog"], api.state["db"], api.state["catalog_by_id"]
        for profile in PROFILES:
            rng = random.Random(profile["seed"])
            attributes = {k: profile[k] for k in PROFILE_KEYS}
            r = client.post("/auth/register", json={"email": profile["email"], "password": DEMO_PASSWORD, **attributes})
            if r.status_code == 409:
                r = client.post("/auth/login", json={"email": profile["email"], "password": DEMO_PASSWORD})
            if r.status_code not in (200, 201):
                print(f"✗ {profile['email']}: {r.json().get('detail')}")
                continue
            headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
            user_id = r.json()["user"]["id"]
            client.patch("/auth/me", json=attributes, headers=headers)  # existing accounts get the current profile

            if args.reset:
                client.delete("/wardrobe", headers=headers)
                with db.get_session() as session:
                    session.query(SimilarityAnalysis).filter(SimilarityAnalysis.user_id == user_id).delete()
                    session.commit()

            existing = client.get("/wardrobe", headers=headers).json()["items"]
            if not existing:
                wardrobe = build_starter_wardrobe(catalog, profile["gender"], profile["style_preferences"],
                                                  profile["favorite_colors"], seed=profile["seed"],
                                                  near_duplicates=NEAR_DUPLICATES)
                for product in wardrobe:
                    client.post("/wardrobe", json={"product_id": product["id"], "size": size_for(product, profile)},
                                headers=headers)
            else:
                wardrobe = [by_id[i["product_id"]] for i in existing if i.get("product_id") in by_id]

            verdicts = Counter()
            if db.count_analyses(user_id) == 0:
                for product in pick_candidates(catalog, wardrobe, profile, rng):
                    item = {"name": product["name"][:160], "category": product["category"],
                            "color": product.get("primary_color"), "style": product.get("style") or "casual",
                            "material": product.get("material"), "price": product.get("price")}
                    result = client.post("/analyze", headers=headers, json={
                        "new_item": {k: v for k, v in item.items() if v is not None}, "product_id": product["id"],
                        "language": "fr", "use_llm": args.llm}).json()
                    verdicts[result["recommendation"]] += 1

            stats = client.get("/stats", headers=headers).json()
            pieces = Counter(i["category"] for i in client.get("/wardrobe", headers=headers).json()["items"])
            rows.append((profile["display_name"], "femme" if profile["gender"] == "Women" else "homme", profile["email"],
                         stats["wardrobe_items"], stats["analyses_run"], stats["duplicates_avoided"], pieces))

    print(f"\n{'Nom':16} {'':6} {'E-mail':28} {'pièces':>6} {'analyses':>8} {'doublons':>8}  détail")
    for name, gender, email, items, analyses, dupes, pieces in rows:
        detail = ", ".join(f"{k} {v}" for k, v in sorted(pieces.items()))
        print(f"{name:16} {gender:6} {email:28} {items:>6} {analyses:>8} {dupes:>8}  {detail}")
    print(f"\nMot de passe des comptes de démonstration : {DEMO_PASSWORD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
