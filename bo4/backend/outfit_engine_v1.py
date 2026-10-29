
from itertools import product
import json

TOPS = {"shirt", "tshirt", "t-shirt", "blouse", "sweater", "hoodie", "top"}
BOTTOMS = {"trousers", "pants", "jeans", "shorts", "skirt"}
OUTERWEAR = {"blazer", "jacket", "coat", "cardigan"}

NEUTRAL = {
    "black", "white", "grey", "gray",
    "beige", "cream", "navy_blue", "navy",
    "light_grey", "dark_grey"
}

COLOR_FAMILIES = {
    "blue": {"blue", "light_blue", "dark_blue", "navy_blue", "denim_blue"},
    "green": {"green", "olive", "dark_green", "light_green"},
    "red": {"red", "burgundy", "maroon"},
    "brown": {"brown", "camel", "tan"},
    "yellow": {"yellow", "mustard"},
    "pink": {"pink", "light_pink"},
    "purple": {"purple", "lavender"},
}


def normalize(value):
    return str(value or "unknown").lower().strip().replace(" ", "_").replace("-", "_")


def color_family(color):
    color = normalize(color)
    for family, members in COLOR_FAMILIES.items():
        if color in members:
            return family
    return color


def garment_role(item):
    category = normalize(item.get("category"))
    if category in TOPS:
        return "top"
    if category in BOTTOMS:
        return "bottom"
    if category in OUTERWEAR:
        return "outerwear"
    return None


def color_score(a, b):
    a = normalize(a)
    b = normalize(b)

    if "unknown" in (a, b):
        return 0.6, "Couleur non renseignée"

    if a == b:
        return 0.75, "Couleurs identiques : ensemble monochrome"

    if a in NEUTRAL and b in NEUTRAL:
        return 0.95, "Association de couleurs neutres"

    if a in NEUTRAL or b in NEUTRAL:
        return 0.90, "Une couleur neutre équilibre la tenue"

    if color_family(a) == color_family(b):
        return 0.85, "Couleurs de la même famille"

    return 0.55, "Association de couleurs à vérifier"


def style_score(items):
    styles = [normalize(i.get("style")) for i in items]
    known = [s for s in styles if s != "unknown"]

    if not known:
        return 0.6, "Styles non renseignés"

    if len(set(known)) == 1:
        return 1.0, "Styles cohérents"

    if set(known) <= {"casual", "smart_casual", "formal"}:
        return 0.75, "Mélange de styles potentiellement compatible"

    return 0.50, "Mélange de styles à vérifier"


def evaluate_outfit(items):
    colors = [i.get("color", "unknown") for i in items]

    pair_scores = []
    reasons = []

    for i in range(len(colors)):
        for j in range(i + 1, len(colors)):
            score, reason = color_score(colors[i], colors[j])
            pair_scores.append(score)
            if reason not in reasons:
                reasons.append(reason)

    color_avg = sum(pair_scores) / len(pair_scores)
    style, style_reason = style_score(items)

    # Premier prototype : pondérations heuristiques
    total = 100 * (0.65 * color_avg + 0.35 * style)

    reasons.append(style_reason)

    return {
        "score": round(total, 2),
        "color_score": round(color_avg * 100, 2),
        "style_score": round(style * 100, 2),
        "explanations": reasons,
    }


def recommend_outfits(wardrobe, top_k=5):
    tops = [i for i in wardrobe if garment_role(i) == "top"]
    bottoms = [i for i in wardrobe if garment_role(i) == "bottom"]
    jackets = [i for i in wardrobe if garment_role(i) == "outerwear"]

    if not tops or not bottoms:
        return []

    results = []

    # Deux pièces, puis trois pièces si une veste existe
    for top, bottom in product(tops, bottoms):
        combinations = [[top, bottom]]
        combinations += [[top, bottom, jacket] for jacket in jackets]

        for items in combinations:
            ids = [str(i.get("id")) for i in items]

            if len(ids) != len(set(ids)):
                continue

            evaluation = evaluate_outfit(items)

            results.append({
                "items": items,
                **evaluation
            })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]


if __name__ == "__main__":
    wardrobe = [
        {
            "id": "1",
            "category": "shirt",
            "color": "light_blue",
            "style": "formal"
        },
        {
            "id": "2",
            "category": "trousers",
            "color": "beige",
            "style": "formal"
        },
        {
            "id": "3",
            "category": "blazer",
            "color": "navy_blue",
            "style": "formal"
        },
        {
            "id": "4",
            "category": "jeans",
            "color": "black",
            "style": "casual"
        },
        {
            "id": "5",
            "category": "tshirt",
            "color": "white",
            "style": "casual"
        }
    ]

    recommendations = recommend_outfits(wardrobe, top_k=5)

    print("\n=== BO4 : TOP 5 TENUES ===")
    print(json.dumps(recommendations, indent=2, ensure_ascii=False))
