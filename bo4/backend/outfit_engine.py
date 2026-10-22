
from itertools import product
import argparse
import collections
import json

TOPS = {"shirt", "tshirt", "t_shirt", "blouse", "sweater", "hoodie", "top"}
BOTTOMS = {"trousers", "pants", "jeans", "shorts", "skirt"}
OUTERWEAR = {"blazer", "jacket", "coat", "cardigan"}
# Pièce unique couvrant le buste et les jambes (ISSUE-05). Seule la catégorie
# H&M "Dress" est prise en charge : combinaisons, salopettes, sous-robes et
# pyjamas restent exclus.
DRESSES = {"dress"}

NEUTRAL = {
    "black", "white", "grey", "gray", "beige",
    "cream", "navy_blue", "navy", "light_grey",
    "dark_grey"
}

NEUTRAL_BASES = {"black", "white", "grey", "gray", "beige", "cream"}

COLOR_FAMILIES = {
    "blue": {"blue", "light_blue", "dark_blue", "navy_blue", "denim_blue"},
    "green": {"green", "olive", "dark_green", "light_green", "khaki"},
    "red": {"red", "burgundy", "maroon"},
    "brown": {"brown", "camel", "tan"},
    "yellow": {"yellow", "mustard"},
    "pink": {"pink", "light_pink"},
    "purple": {"purple", "lavender", "lilac"},
}

# Modificateurs de nuance des couleurs H&M ("Light Beige", "Off White",
# "Other Pink") ; les suffixes en "ish" ("Yellowish Brown") sont traités à part.
COLOR_MODIFIERS = {"light", "dark", "other", "off"}

OCCASION_STYLES = {
    "university": {"casual", "smart_casual"},
    "work": {"formal", "smart_casual"},
    "evening": {"formal", "smart_casual"},
    "casual": {"casual", "smart_casual"},
}

SEASONS = ("spring", "summer", "autumn", "winter")

# ---------------------------------------------------------------------------
# Chaleur des vêtements et saisons
#
# Toutes les valeurs ci-dessous sont des HEURISTIQUES non calibrées : elles
# encodent un raisonnement vestimentaire courant, pas une mesure. Elles devront
# être ajustées sur un jeu de tenues annoté avant toute affirmation de qualité.
# ---------------------------------------------------------------------------

WARMTH_LEVELS = ("light", "medium", "heavy")

# Niveaux de chaleur PLAUSIBLES par catégorie (estimation, pas observation).
# Une catégorie peu informative garde les trois niveaux : on ne suppose jamais
# "medium" par défaut. Les catégories absentes sont aussi traitées ainsi.
CATEGORY_WARMTH = {
    "tshirt": ("light",),
    "t_shirt": ("light",),
    "shorts": ("light",),
    "top": ("light", "medium"),
    "shirt": ("light", "medium"),
    "blouse": ("light", "medium"),
    "blazer": ("light", "medium"),
    "trousers": ("light", "medium"),
    "pants": ("light", "medium"),
    "jeans": ("light", "medium"),
    "skirt": ("light", "medium"),
    "dress": ("light", "medium"),  # hypothèse incertaine ; le texte reste prioritaire
    "sweater": ("medium", "heavy"),
    "hoodie": ("medium", "heavy"),
    "coat": ("medium", "heavy"),
    "jacket": WARMTH_LEVELS,    # de la veste en lin à la doudoune
    "cardigan": WARMTH_LEVELS,  # de la maille fine à la grosse maille
}

# Adéquation (0-1) de la couche la plus chaude du buste (haut + veste) à la saison.
TORSO_SUITABILITY = {
    "summer": {"light": 1.0, "medium": 0.6, "heavy": 0.1},
    "spring": {"light": 0.8, "medium": 1.0, "heavy": 0.5},
    "autumn": {"light": 0.6, "medium": 1.0, "heavy": 0.8},
    "winter": {"light": 0.2, "medium": 0.7, "heavy": 1.0},
}

# Les jambes tolèrent mieux les écarts de chaleur que le buste.
BOTTOM_SUITABILITY = {
    "summer": {"light": 1.0, "medium": 0.8, "heavy": 0.4},
    "spring": {"light": 0.9, "medium": 1.0, "heavy": 0.6},
    "autumn": {"light": 0.8, "medium": 1.0, "heavy": 0.9},
    "winter": {"light": 0.5, "medium": 0.9, "heavy": 1.0},
}

# Jambes découvertes : la couverture, et non la chaleur du tissu, est en cause.
EXPOSED_LEGS = {"shorts"}
EXPOSED_LEGS_SUITABILITY = {"summer": 1.0, "spring": 0.8, "autumn": 0.5, "winter": 0.2}

TORSO_WEIGHT = 0.65  # le buste porte l'essentiel de l'adaptation thermique

# Couche intérieure : adéquation du haut seul, si la veste est retirée
# (à l'intérieur). Plus tolérante que TORSO_SUITABILITY en saison froide.
INNER_SUITABILITY = {
    "summer": {"light": 1.0, "medium": 0.6, "heavy": 0.1},
    "spring": {"light": 0.9, "medium": 1.0, "heavy": 0.6},
    "autumn": {"light": 0.7, "medium": 1.0, "heavy": 0.8},
    "winter": {"light": 0.6, "medium": 1.0, "heavy": 0.9},
}
# Part de la couche intérieure dans le buste quand une veste est portée. Elle
# ne peut que baisser le score (jamais compenser une veste trop chaude).
INNER_LAYER_WEIGHT = 0.3

# Longueur des manches : facteur de couverture des bras, distinct de la chaleur
# du tissu. "unknown" est neutre (1.0) : on ne pénalise pas l'absence d'info.
SLEEVE_LENGTHS = ("sleeveless", "short", "three_quarter", "long")
SLEEVE_FACTOR = {
    "summer": {"sleeveless": 1.0, "short": 1.0, "three_quarter": 0.95, "long": 0.9},
    "spring": {"sleeveless": 0.9, "short": 1.0, "three_quarter": 1.0, "long": 1.0},
    "autumn": {"sleeveless": 0.8, "short": 0.9, "three_quarter": 1.0, "long": 1.0},
    "winter": {"sleeveless": 0.7, "short": 0.8, "three_quarter": 0.95, "long": 1.0},
}

WARMTH_ORIGIN_LABELS = {
    "attribute": "attribut",
    "category": "estimation par catégorie",
    "text_partial": "description partielle",
    "conflict": "description et catégorie divergentes",
    "contradictory": "description contradictoire",
    "unknown": "chaleur inconnue",
}


def normalize(value):
    return str(value or "unknown").lower().strip().replace(" ", "_").replace("-", "_")


def base_color(color):
    """Teinte de base : "light_beige" -> "beige", "yellowish_brown" -> "brown"."""
    parts = normalize(color).split("_")
    while len(parts) > 1 and (parts[0] in COLOR_MODIFIERS or parts[0].endswith("ish")):
        parts = parts[1:]
    return "_".join(parts)


def is_neutral(color):
    color = normalize(color)
    return color in NEUTRAL or base_color(color) in NEUTRAL_BASES


def color_family(color):
    color = normalize(color)
    base = base_color(color)
    for family, members in COLOR_FAMILIES.items():
        if color in members or base in members:
            return family
    return base


def garment_role(item):
    category = normalize(item.get("category"))
    if category in TOPS:
        return "top"
    if category in BOTTOMS:
        return "bottom"
    if category in OUTERWEAR:
        return "outerwear"
    if category in DRESSES:
        return "dress"
    return None


def color_score(a, b):
    a, b = normalize(a), normalize(b)

    if "unknown" in (a, b):
        return 0.60, "Couleur non renseignée"
    if is_neutral(a) and is_neutral(b):
        if a == b:
            return 0.95, "Ensemble monochrome neutre"
        return 0.95, "Association de couleurs neutres"
    if a == b:
        return 0.75, "Ensemble monochrome"
    if is_neutral(a) or is_neutral(b):
        return 0.90, "Une couleur neutre équilibre la tenue"
    if color_family(a) == color_family(b):
        return 0.85, "Couleurs de la même famille"
    return 0.55, "Association de couleurs à vérifier"


def style_score(items):
    styles = [normalize(i.get("style")) for i in items]
    known = [s for s in styles if s != "unknown"]

    if not known:
        return 0.60, "Styles non renseignés"
    if len(set(known)) == 1:
        return 1.0, "Styles cohérents"
    if set(known) <= {"casual", "smart_casual", "formal"}:
        return 0.75, "Mélange de styles potentiellement compatible"
    return 0.50, "Mélange de styles à vérifier"


def occasion_score(items, occasion):
    preferred = OCCASION_STYLES[occasion]
    styles = [normalize(i.get("style")) for i in items]

    known = [s for s in styles if s != "unknown"]
    if not known:
        return 0.60, "Adéquation à l'occasion incertaine"

    matches = sum(s in preferred for s in known)
    score = matches / len(known)

    if score == 1:
        return 1.0, f"Styles adaptés à l'occasion : {occasion}"

    return max(0.20, score), f"Certains vêtements sont moins adaptés à : {occasion}"


def _ordered(levels):
    return tuple(level for level in WARMTH_LEVELS if level in levels)


def item_warmth(item):
    """Niveaux de chaleur plausibles d'un vêtement et origine de l'information.

    Renvoie (niveaux, source) avec source :
    - "attribute"     : attribut `warmth` fourni (light / medium / heavy) ;
    - "contradictory" : description aux indices incompatibles : les trois
                        niveaux restent possibles (incertitude explicite) ;
    - "conflict"      : description et catégorie divergent : union exacte de
                        leurs niveaux, sans ajouter de niveau intermédiaire ;
    - "text_partial"  : plage de la catégorie restreinte par la description ;
    - "category"      : plage estimée d'après une catégorie informative ;
    - "unknown"       : aucune information, les trois niveaux restent possibles.

    `warmth_source` et `text_warmth_levels` (garment_attributes) sont facultatifs :
    sans eux, seuls l'attribut et la catégorie sont utilisés.
    """
    declared = normalize(item.get("warmth"))
    if declared in WARMTH_LEVELS:
        return (declared,), "attribute"
    category_levels = CATEGORY_WARMTH.get(normalize(item.get("category")), WARMTH_LEVELS)
    source = item.get("warmth_source")
    text_levels = {normalize(level) for level in item.get("text_warmth_levels") or ()} & set(WARMTH_LEVELS)
    if source == "text_contradictory":
        return WARMTH_LEVELS, "contradictory"
    if source == "text_conflict" and text_levels:
        return _ordered(text_levels | set(category_levels)), "conflict"
    if source == "text_partial" and text_levels:
        narrowed = _ordered(text_levels & set(category_levels))
        if narrowed:
            return narrowed, "text_partial"
    if len(category_levels) < len(WARMTH_LEVELS):
        return category_levels, "category"
    return WARMTH_LEVELS, "unknown"


def item_sleeve(item):
    sleeve = normalize(item.get("sleeve_length"))
    return sleeve if sleeve in SLEEVE_LENGTHS else "unknown"


def sleeve_coverage(items):
    """Couverture des bras d'une superposition : la manche la plus couvrante.

    Inconnue si une pièce n'est pas renseignée et qu'aucune pièce connue n'a de
    manches longues (la pièce inconnue pourrait couvrir davantage).
    """
    sleeves = [item_sleeve(i) for i in items]
    known = [s for s in sleeves if s != "unknown"]
    if not known:
        return "unknown"
    best = max(known, key=SLEEVE_LENGTHS.index)
    if best != "long" and len(known) < len(sleeves):
        return "unknown"
    return best


def _sleeve_factor(coverage, season):
    return SLEEVE_FACTOR[season].get(coverage, 1.0)


SLEEVE_LABELS = {
    "sleeveless": "sans manches",
    "short": "manches courtes",
    "three_quarter": "manches 3/4",
    "long": "manches longues",
}


def _expected_suitability(level_sets, table):
    """Espérance de l'adéquation de la couche la plus chaude, chaque vêtement
    prenant uniformément l'un de ses niveaux plausibles."""
    combinations = list(product(*level_sets))
    total = sum(table[max(c, key=WARMTH_LEVELS.index)] for c in combinations)
    return total / len(combinations)


def _label(item):
    return item.get("name") or normalize(item.get("category"))


def season_score(items, season):
    """Adéquation thermique de la tenue complète à la saison (0-1).

    Le buste est évalué par sa couche la plus chaude (haut ou veste) : un haut
    léger sous une veste chaude convient en hiver, une veste chaude rend la
    tenue trop chaude en été. Ajouter une pièce n'apporte donc aucun bonus en
    soi : cela ne change le score que si cela change la chaleur de la tenue.

    Une robe compte à la fois comme haut (buste, couche intérieure, manches) et
    comme bas (jambes), avec les mêmes règles et les mêmes poids.

    Deux ajustements, tous deux sans bonus possible :
    - la couverture des bras (manches) multiplie le score du buste ;
    - avec une veste, la couche intérieure (haut seul, veste retirée) peut
      baisser le score du buste, jamais l'augmenter :
      buste = min(W, (1 - a) * W + a * I).
    """
    torso = [i for i in items if garment_role(i) in ("top", "dress", "outerwear")]
    tops = [i for i in torso if garment_role(i) in ("top", "dress")]
    outerwear = [i for i in torso if garment_role(i) == "outerwear"]
    bottoms = [i for i in items if garment_role(i) in ("bottom", "dress")]
    # Chaque vêtement une seule fois (une robe est à la fois buste et bas).
    worn = list({id(i): i for i in torso + bottoms}.values())
    warmth = {id(i): item_warmth(i) for i in worn}
    reasons = []

    components = []
    torso_score = None
    if torso:
        coverage = sleeve_coverage(torso)
        arms = _sleeve_factor(coverage, season)
        torso_score = arms * _expected_suitability(
            [warmth[id(i)][0] for i in torso], TORSO_SUITABILITY[season]
        )
        if arms <= 0.9:
            if season == "summer":
                reasons.append(f"Bras couverts ({SLEEVE_LABELS[coverage]}) : un peu chaud pour l'été")
            else:
                reasons.append(f"Bras peu couverts ({SLEEVE_LABELS[coverage]}) pour la saison : {season}")

        if tops and outerwear:
            inner = _sleeve_factor(sleeve_coverage(tops), season) * _expected_suitability(
                [warmth[id(i)][0] for i in tops], INNER_SUITABILITY[season]
            )
            layered = min(
                torso_score,
                (1 - INNER_LAYER_WEIGHT) * torso_score + INNER_LAYER_WEIGHT * inner,
            )
            if torso_score - layered >= 0.03:
                names = ", ".join(_label(t) for t in tops)
                reasons.append(
                    f"Couche intérieure ({names}) légère ou peu couvrante : prévoir une couche "
                    f"intermédiaire si la veste est retirée"
                )
            torso_score = layered

        components.append((TORSO_WEIGHT, torso_score))

    for bottom in bottoms:
        category = normalize(bottom.get("category"))
        if category in EXPOSED_LEGS:
            value = EXPOSED_LEGS_SUITABILITY[season]
            if value < 0.6:
                reasons.append(f"{category} peu adapté à la saison {season}")
        else:
            value = _expected_suitability([warmth[id(bottom)][0]], BOTTOM_SUITABILITY[season])
        components.append(((1 - TORSO_WEIGHT) / len(bottoms), value))

    if not components:
        return 0.60, ["Adéquation saisonnière non évaluable"]

    score = sum(w * v for w, v in components) / sum(w for w, _ in components)

    if season == "summer":
        # En été, chaque pièce trop chaude pose problème, quelle que soit la couche.
        for item in torso:
            levels, source = warmth[id(item)]
            if _expected_suitability([levels], TORSO_SUITABILITY[season]) < 0.5:
                reasons.append(f"{_label(item)} trop chaud pour l'été ({WARMTH_ORIGIN_LABELS[source]})")
    elif torso_score is not None and torso_score < 0.5:
        reasons.append(f"Couches insuffisamment chaudes pour la saison : {season}")

    for item in worn:
        origin = warmth[id(item)][1]
        if origin == "unknown":
            reasons.append(f"Chaleur de {_label(item)} non renseignée : estimation incertaine")
        elif origin == "conflict":
            reasons.append(
                f"Chaleur de {_label(item)} : description et catégorie divergent, "
                f"plusieurs niveaux retenus"
            )
        elif origin == "contradictory":
            reasons.append(f"Chaleur de {_label(item)} : description contradictoire, chaleur incertaine")

    negative = ("peu adapté", "trop chaud", "insuffisamment", "peu couverts", "un peu chaud")
    if score >= 0.75 and not any(marker in r for r in reasons for marker in negative):
        reasons.append(f"Tenue globalement adaptée à la saison : {season}")
    elif score < 0.5:
        reasons.append(f"Tenue peu adaptée à la saison : {season}")
    else:
        reasons.append(f"Adéquation à la saison {season} à vérifier")

    return score, reasons


SINGLE_PIECE_COLOR_SCORE = 0.90
JACKET_COLOR_CAP_REASON = "La veste ne compense pas le contraste entre le haut et le bas."


def evaluate_outfit(items, occasion, season):
    colors = [i.get("color", "unknown") for i in items]

    pair_scores = []
    explanations = []

    for i in range(len(colors)):
        for j in range(i + 1, len(colors)):
            score, reason = color_score(colors[i], colors[j])
            pair_scores.append(score)
            if reason not in explanations:
                explanations.append(reason)

    if pair_scores:
        color_avg = sum(pair_scores) / len(pair_scores)
        # ISSUE-04b : haut + bas + veste. La moyenne des 3 paires ne peut pas
        # dépasser l'harmonie haut/bas : une veste peut la dégrader (conflit),
        # pas la compenser. Haut + bas, robe et robe + veste : inchangés.
        base = [i for i in items if garment_role(i) in ("top", "bottom")]
        if len(base) == 2 and len(items) == 3:
            base_score, _ = color_score(base[0].get("color", "unknown"), base[1].get("color", "unknown"))
            if color_avg > base_score:
                color_avg = base_score
                explanations.append(JACKET_COLOR_CAP_REASON)
    else:
        # Pièce unique (robe seule) : aucune paire à comparer. Valeur
        # conventionnelle, heuristique, sans harmonie démontrée.
        color_avg = SINGLE_PIECE_COLOR_SCORE
        explanations.append("Pièce unique : aucune association de couleurs entre pièces n'est évaluée")
    style, style_reason = style_score(items)
    occ, occ_reason = occasion_score(items, occasion)
    sea, sea_reasons = season_score(items, season)

    # Pondérations initiales heuristiques
    total = 100 * (
        0.30 * color_avg +
        0.20 * style +
        0.30 * occ +
        0.20 * sea
    )

    explanations.extend([style_reason, occ_reason])
    explanations.extend(sea_reasons)

    return {
        "score": round(total, 2),
        "color_score": round(color_avg * 100, 2),
        "style_score": round(style * 100, 2),
        "occasion_score": round(occ * 100, 2),
        "season_score": round(sea * 100, 2),
        "explanations": explanations,
    }


# Départage des ex aequo (ISSUE-06) : purement TECHNIQUE. Il rend l'ordre
# indépendant de l'ordre d'entrée de la garde-robe ; il n'exprime aucune
# préférence de pertinence ou de diversité et ne modifie aucun score.
TIE_BREAK_FALLBACK_FIELDS = ("article_id", "name", "category", "color", "style", "image_path")


def _item_sort_key(item):
    """Clé déterministe d'un vêtement : identifiant, puis champs publics.

    - identifiant numérique : ordre naturel ("9" avant "10") ;
    - identifiant textuel   : ordre alphabétique, après les numériques ;
    - identifiant manquant ou vide : en dernier.
    Les champs publics ne départagent que des identifiants dupliqués. Deux
    vêtements identiques sur tous ces champs restent indiscernables : leur ordre
    relatif n'est alors pas garanti, mais ils produisent le même JSON public.
    """
    raw = item.get("id")
    text = "" if raw is None else str(raw).strip()
    if not text:
        id_key = (2, 0, "")
    elif text.isascii() and text.isdigit():
        id_key = (0, int(text), text)
    else:
        id_key = (1, 0, text)
    fallback = tuple(str(item.get(field) or "") for field in TIE_BREAK_FALLBACK_FIELDS)
    return id_key, fallback


def outfit_sort_key(result):
    """Score décroissant, puis vêtements (haut, bas, veste) par clé déterministe.

    À score égal, une tenue sans veste précède sa variante avec veste (préfixe).
    """
    return -result["score"], tuple(_item_sort_key(i) for i in result["items"])


# Diversification du top-k (ISSUE-07) par contrainte de couverture. Valeurs
# HEURISTIQUES non calibrées. Les scores et explications ne sont pas modifiés :
# seule la sélection des tenues renvoyées change.
DIVERSITY_SCORE_WINDOW = 3.0  # écart de score toléré par rapport au meilleur
DIVERSITY_ITEM_CAP = 2        # nombre max de tenues partageant un même vêtement


def _item_identity(item):
    # Même identité que le contrôle de doublons de recommend_outfits.
    return str(item.get("id"))


def select_diverse(ranked, top_k, window=DIVERSITY_SCORE_WINDOW, cap=DIVERSITY_ITEM_CAP):
    """Sélectionne top_k tenues variées parmi `ranked` (trié par outfit_sort_key).

    Étapes, chacune dans l'ordre du classement brut, sans doublon :
    1. fenêtre (score >= meilleur - window) en respectant le plafond `cap` par
       vêtement ; la meilleure tenue est donc toujours retenue ;
    2. si cela ne suffit pas : reste de la fenêtre, plafond relâché (on préfère
       une répétition proche du meilleur score à une tenue nettement moins bonne) ;
    3. si la fenêtre elle-même est trop petite : meilleures tenues hors fenêtre.
       C'est le seul cas où l'écart de `window` points est dépassé.
    Le résultat est trié par outfit_sort_key (score décroissant).
    """
    if top_k <= 0 or top_k >= len(ranked):
        return ranked[:top_k]

    best = ranked[0]["score"]
    in_window = [r for r in ranked if r["score"] >= best - window]
    selected, chosen, uses = [], set(), collections.Counter()

    def take(result):
        selected.append(result)
        chosen.add(id(result))
        uses.update(_item_identity(i) for i in result["items"])

    for result in in_window:
        if len(selected) == top_k:
            break
        if all(uses[_item_identity(i)] < cap for i in result["items"]):
            take(result)

    for candidates in (in_window, ranked):
        for result in candidates:
            if len(selected) == top_k:
                break
            if id(result) not in chosen:
                take(result)

    return sorted(selected, key=outfit_sort_key)


def recommend_outfits(wardrobe, occasion="university", season="autumn", top_k=5, diversify=True):
    """Tenues recommandées, triées par score (départage d'ISSUE-06).

    `diversify=False` renvoie exactement le classement brut (les top_k
    premières tenues) ; par défaut, le top-k est diversifié (select_diverse).
    """
    if occasion not in OCCASION_STYLES:
        raise ValueError(f"Occasion inconnue : {occasion}")
    if season not in SEASONS:
        raise ValueError(f"Saison inconnue : {season}")

    tops = [i for i in wardrobe if garment_role(i) == "top"]
    bottoms = [i for i in wardrobe if garment_role(i) == "bottom"]
    jackets = [i for i in wardrobe if garment_role(i) == "outerwear"]
    dresses = [i for i in wardrobe if garment_role(i) == "dress"]

    # Bases de tenue : haut + bas, ou robe seule (jamais robe + haut ou bas).
    bases = [[top, bottom] for top, bottom in product(tops, bottoms)]
    bases.extend([dress] for dress in dresses)

    results = []

    for base in bases:
        combinations = [base]
        combinations.extend(
            [base + [jacket] for jacket in jackets]
        )

        for items in combinations:
            ids = [str(i.get("id")) for i in items]
            if len(ids) != len(set(ids)):
                continue

            evaluation = evaluate_outfit(items, occasion, season)

            results.append({
                "items": items,
                "occasion": occasion,
                "season": season,
                **evaluation
            })

    results.sort(key=outfit_sort_key)
    if diversify:
        return select_diverse(results, top_k)
    return results[:top_k]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--occasion",
        choices=list(OCCASION_STYLES),
        default="university"
    )
    parser.add_argument(
        "--season",
        choices=list(SEASONS),
        default="autumn"
    )
    args = parser.parse_args()

    # Données de démonstration, pas encore PostgreSQL
    wardrobe = [
        {"id": "1", "category": "shirt", "color": "light_blue", "style": "formal"},
        {"id": "2", "category": "trousers", "color": "beige", "style": "formal"},
        {"id": "3", "category": "blazer", "color": "navy_blue", "style": "formal"},
        {"id": "4", "category": "jeans", "color": "black", "style": "casual"},
        {"id": "5", "category": "tshirt", "color": "white", "style": "casual"},
    ]

    results = recommend_outfits(
        wardrobe,
        occasion=args.occasion,
        season=args.season,
        top_k=5
    )

    print("\n=== BO4 : RECOMMANDATIONS CONTEXTUELLES ===")
    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
