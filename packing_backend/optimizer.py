
from itertools import product
from pathlib import Path
import random
import re

import pandas as pd
from ortools.sat.python import cp_model


DATA = Path(__file__).parent / "data"

ROLES = [
    "top", "bottom", "shoes", "onepiece",
    "outerwear", "rain", "warm", "sun",
]


# --------------------------------------------------
# 1. LOAD DATA
# --------------------------------------------------

def load_data():
    wardrobe = pd.read_csv(DATA / "wardrobe.csv")
    trips = pd.read_csv(DATA / "trip_requirements.csv")
    compatibility = pd.read_csv(DATA / "compatibility.csv")

    required_wardrobe = {
        "item_id", "category", "item_type", "weight_g",
        "versatility", "style", "warmth_level",
        "water_resistance", "clean_items_available",
    }
    required_trips = {
        "trip_id", "day_number", "activity", "weather",
        "temperature_c", "precipitation_mm", "required_style",
        "needs_outerwear", "needs_warm_layer",
        "needs_rain_protection", "needs_sun_protection",
    }
    required_compatibility = {
        "item_id_a", "item_id_b", "compatibility_score"
    }

    for name, df, columns in [
        ("wardrobe", wardrobe, required_wardrobe),
        ("trips", trips, required_trips),
        ("compatibility", compatibility, required_compatibility),
    ]:
        missing = columns - set(df.columns)
        if missing:
            raise ValueError(f"{name}.csv missing columns: {missing}")

    if wardrobe["item_id"].duplicated().any():
        raise ValueError("wardrobe.csv contains duplicate item_id values")

    wardrobe["weight_g"] = pd.to_numeric(
        wardrobe["weight_g"], errors="raise"
    )
    wardrobe["versatility"] = pd.to_numeric(
        wardrobe["versatility"], errors="coerce"
    ).fillna(1)

    if (wardrobe["weight_g"] < 0).any():
        raise ValueError("Garment weights cannot be negative")

    return wardrobe, trips, compatibility


def truth(value):
    if pd.isna(value):
        return False
    return str(value).strip().lower() in {
        "true", "1", "yes", "y"
    }


# --------------------------------------------------
# 2. CLASSIFY WARDROBE ITEMS
# --------------------------------------------------

def roles_of(item):
    """Retourne tous les rôles utiles d'un vêtement.

    Un article peut cumuler plusieurs rôles : un imperméable est à la
    fois 'outerwear' et 'rain', un sweat à capuche 'top' et 'warm'.
    """
    text = " ".join(
        str(item.get(column, ""))
        for column in ["name", "category", "item_type", "description"]
        if item.get(column) is not None
    ).lower()

    category = str(item.get("category", "")).strip().lower()
    item_type = str(item.get("item_type", "")).strip().lower()

    roles = set()

    # Catégories principales (les champs structurés sont plus fiables).
    if category == "top" or re.search(
        r"\b(top|shirt|t-shirt|blouse|chemise|tee)\b", text
    ):
        roles.add("top")
    if category == "bottom" or re.search(
        r"\b(bottom|trousers|pants|jeans|skirt|shorts|jupe)\b", text
    ):
        roles.add("bottom")
    if category == "shoes" or re.search(
        r"\b(shoes|sneakers|boots|sandals|trainers|chaussures)\b", text
    ):
        roles.add("shoes")
    if (
        category == "dress"
        or item_type.endswith("-dress")
        or re.search(r"\b(dress|robe|jumpsuit)\b", text)
    ):
        roles.add("onepiece")

    # Fonctions additionnelles : les champs structurés (category, item_type)
    # priment sur les mots du nom pour éviter les faux positifs
    # (ex. un chapeau imperméable n'est pas un imperméable de pluie).
    try:
        water_resistance = float(item.get("water_resistance", 0) or 0)
    except (ValueError, TypeError):
        water_resistance = 0.0

    # Seuls les vêtements adaptés peuvent assurer la protection pluie.
    rainwear_types = {"raincoat"}
    outerwear_types = {"coat", "jacket", "raincoat", "parka", "cardigan"}

    if category == "outerwear" or item_type in outerwear_types:
        roles.add("outerwear")
    if item_type in rainwear_types:
        roles.add("rain")
    elif (
        category == "outerwear"
        and water_resistance >= 4
        and item_type in {"coat", "jacket", "parka"}
    ):
        roles.add("rain")
    if item_type in {"hoodie", "sweater", "jumper", "cardigan", "fleece"}:
        roles.add("warm")
    if category == "accessory" and item_type in {"hat", "sunglasses"}:
        roles.add("sun")

    return roles


def build_item_roles(wardrobe):
    return {
        str(row["item_id"]): roles_of(row)
        for _, row in wardrobe.iterrows()
    }


def required_roles_for_day(day):
    """Rôles obligatoires d'une journée (météo + température)."""
    required = set()

    if truth(day.get("needs_outerwear")):
        required.add("outerwear")
    if truth(day.get("needs_warm_layer")):
        required.add("warm")
    if truth(day.get("needs_rain_protection")):
        required.add("rain")
    if truth(day.get("needs_sun_protection")):
        required.add("sun")

    weather = str(day.get("weather", "")).lower()
    if "rain" in weather:
        required.add("rain")

    try:
        temperature = float(day.get("temperature_c"))
    except (TypeError, ValueError):
        temperature = 99.0
    if temperature <= 10:
        required.add("warm")

    return required


def outfit_covers_weather(item_ids, day, item_roles):
    required = required_roles_for_day(day)
    covered = set()
    for item_id in item_ids:
        covered.update(item_roles.get(str(item_id), set()))
    return required.issubset(covered)


# --------------------------------------------------
# 3. COMPATIBILITY LOOKUP
# --------------------------------------------------

def build_compatibility_map(df):
    """Paires normalisées (triées) -> score de compatibilité 0-1."""
    result = {}

    for _, row in df.iterrows():
        a, b = sorted(
            (str(row["item_id_a"]), str(row["item_id_b"]))
        )
        result[(a, b)] = float(row["compatibility_score"])

    return result


def compatibility_score(item_ids, compatibility_lookup):
    """Moyenne des compatibilités connues d'une tenue, sur 0-1.

    Les paires absentes de compatibility.csv sont ignorées : une tenue
    non évaluée ne reçoit pas de bonne note par défaut.
    """
    scores = []

    for i in range(len(item_ids)):
        for j in range(i + 1, len(item_ids)):
            a, b = sorted((str(item_ids[i]), str(item_ids[j])))
            score = compatibility_lookup.get((a, b))
            if score is not None:
                scores.append(float(score))

    return sum(scores) / len(scores) if scores else 0.0


# --------------------------------------------------
# 4. ACTIVITY / STYLE APPROPRIATENESS
# --------------------------------------------------

def is_outfit_appropriate(item_ids, trip, garment_map):
    """Rejette les contradictions fortes entre tenue et contexte.

    Ces règles sont des contraintes dures : une tenue qui les viole n'est
    jamais proposée comme candidate, même si sa compatibilité est élevée.
    """
    activity = str(trip.get("activity", "")).strip().lower()
    style = str(trip.get("required_style", "")).strip().lower()

    types = {
        str(garment_map[item_id].get("item_type", "")).strip().lower()
        for item_id in item_ids
    }

    # Une robe explicitement formelle n'est pas une tenue sportive, même si
    # son champ `style` indique `sporty` (donnée synthétique incohérente).
    if style == "sporty" or activity in {"sport", "sports", "workout"}:
        if "formal-dress" in types:
            return False

    # Une tenue de réunion formelle ne doit pas être dominée par des pièces
    # clairement décontractées.
    if activity == "business-meeting" and style == "formal":
        if types.intersection({"shorts", "t-shirt", "hoodie"}):
            return False

    # Sous pluie significative, des sandales non résistantes à l'eau ne sont
    # pas considérées comme adaptées.
    rain_required = truth(trip.get("needs_rain_protection"))
    try:
        precipitation = float(trip.get("precipitation_mm", 0) or 0)
    except (TypeError, ValueError):
        precipitation = 0

    if rain_required and precipitation >= 2:
        for item_id in item_ids:
            item = garment_map[item_id]
            item_type = str(item.get("item_type", "")).lower()
            category = str(item.get("category", "")).lower()
            try:
                resistance = float(item.get("water_resistance", 0) or 0)
            except (TypeError, ValueError):
                resistance = 0
            if category == "shoes" and item_type == "sandals":
                if resistance < 4:
                    return False

    # Par grand froid, les sandales ne sont pas appropriées.
    try:
        temperature = float(trip.get("temperature_c", 99))
    except (TypeError, ValueError):
        temperature = 99

    if temperature <= 5 and "sandals" in types:
        return False

    return True


def outfit_style_score(item_ids, trip, garment_map):
    """Score souple d'adéquation au contexte ; les valeurs élevées sont meilleures.

    Contrairement à is_outfit_appropriate(), cette fonction ne rejette
    aucune tenue : elle départage les candidates d'une même journée qui
    respectent déjà les contraintes dures.
    """
    activity = str(trip.get("activity", "")).strip().lower()
    required_style = str(trip.get("required_style", "")).strip().lower()
    weather = str(trip.get("weather", "")).strip().lower()

    score = 0.0

    for item_id in item_ids:
        item = garment_map[item_id]
        style = str(item.get("style", "")).strip().lower()
        item_type = str(item.get("item_type", "")).strip().lower()
        category = str(item.get("category", "")).strip().lower()

        # 1. Correspondance de style : signal principal mais souple, car le
        #    style du dataset est parfois incohérent avec item_type.
        if required_style and required_style not in {"", "nan"}:
            if style == required_style:
                score += 2.0
            elif required_style in style or style in required_style:
                score += 1.0

        try:
            formality = float(item.get("formality_level", 0) or 0)
        except (TypeError, ValueError):
            formality = 0.0

        # 2. Formalité : les contextes formels valorisent la formalité ; les
        #    contextes décontractés/sportifs pénalisent les pièces trop habillées.
        if required_style == "formal" or activity == "business-meeting":
            score += 0.5 * formality
        elif required_style in {"casual", "sporty"}:
            score -= 0.3 * max(0.0, formality - 3)

        # 3. Confort : les activités de marche privilégient des chaussures
        #    adaptées (sandales, baskets) plutôt que des chaussures habillées.
        if activity in {"sightseeing", "walking", "shopping", "hiking"}:
            if category == "shoes" and item_type in {
                "sandals", "sneakers", "trainers"
            }:
                score += 1.0

        # 4. Protection : sous la pluie, une meilleure résistance à l'eau est
        #    préférable pour les chaussures et les couches extérieures.
        if "rain" in weather and category in {"shoes", "outerwear"}:
            try:
                resistance = float(item.get("water_resistance", 0) or 0)
            except (TypeError, ValueError):
                resistance = 0.0
            score += 0.5 * resistance

    return score


# --------------------------------------------------
# 5. GENERATE DAILY OUTFIT CANDIDATES
# --------------------------------------------------

def generate_outfits(wardrobe, trip, compatibility, item_roles,
                     max_candidates=500, rng=None):
    items = wardrobe.to_dict("records")

    garment_map = {
        str(item["item_id"]): item
        for item in items
    }

    pools = {
        role: [
            i for i in items
            if role in item_roles[str(i["item_id"])]
        ]
        for role in ROLES
    }

    required = required_roles_for_day(trip)

    # Un rôle obligatoire sans article disponible rend la journée
    # infaisable : on le signale au lieu de produire une tenue inadéquate.
    if any(not pools.get(role) for role in required):
        return []

    # Tenue de base complète : haut + bas + chaussures, ou combinaison.
    bases = []

    for top, bottom, shoes in product(
        pools["top"], pools["bottom"], pools["shoes"]
    ):
        bases.append([top, bottom, shoes])

    for onepiece, shoes in product(
        pools["onepiece"], pools["shoes"]
    ):
        bases.append([onepiece, shoes])

    if not bases:
        return []

    required_style = str(trip["required_style"]).lower()
    activity = str(trip["activity"]).lower()
    weather = str(trip["weather"]).lower()
    temperature = trip["temperature_c"]
    try:
        temperature = float(temperature)
    except (TypeError, ValueError):
        temperature = 99.0

    candidates = {}

    for base in bases:
        base_ids = {str(i["item_id"]) for i in base}
        base_roles = set()
        for item in base:
            base_roles.update(item_roles[str(item["item_id"])])

        # Ne compléter que les rôles non déjà couverts par la base
        # (ex. un sweat à capuche en haut couvre déjà 'warm').
        remaining = sorted(required - base_roles)
        role_pools = [pools[role] for role in remaining]

        for additions in (
            product(*role_pools) if role_pools else [()]
        ):
            seen = set(base_ids)
            outfit = list(base)

            for item in additions:
                item_id = str(item["item_id"])
                if item_id in seen:
                    continue
                seen.add(item_id)
                outfit.append(item)

            ids = [str(i["item_id"]) for i in outfit]

            # Pas d'article en double dans une tenue.
            if len(set(ids)) != len(ids):
                continue

            # Couverture météo obligatoire (contrainte, pas bonus).
            if not outfit_covers_weather(ids, trip, item_roles):
                continue

            # Cohérence activité / style (contrainte dure).
            if not is_outfit_appropriate(ids, trip, garment_map):
                continue

            # Températures basses : exiger une vraie couche chaude (et pas un
            # simple article dont le warmth_level est élevé, ex. un chapeau).
            if temperature <= 5 and not any(
                "warm" in item_roles[str(i["item_id"])]
                and float(i.get("warmth_level", 0) or 0) >= 3
                for i in outfit
            ):
                continue

            signature = tuple(sorted(ids))

            if signature in candidates:
                continue

            compat = compatibility_score(ids, compatibility)

            style_matches = sum(
                required_style in str(i.get("style", "")).lower()
                for i in outfit
                if required_style and required_style != "nan"
            )

            versatility = sum(
                float(i.get("versatility", 1) or 1)
                for i in outfit
            )

            style_fit = outfit_style_score(ids, trip, garment_map)

            # Score entier pour CP-SAT (compatibilité 0-1 -> 0-100).
            quality = round(
                100 * compat
                + 3 * style_matches
                + 2 * versatility
                + style_fit
            )

            candidates[signature] = {
                "item_ids": list(signature),
                "signature": signature,
                "quality": quality,
                "compatibility": round(compat, 4),
                "style_fit": style_fit,
                "activity": activity,
                "required_style": required_style,
                "weather": weather,
                "day_number": int(trip["day_number"]),
                "required_roles": sorted(required),
            }

    # Échantillonnage aléatoire pour éviter le biais des premiers items
    # du fichier lorsque le plafond de candidats est atteint.
    if len(candidates) > max_candidates and rng is not None:
        keys = rng.sample(sorted(candidates), max_candidates)
        candidates = {key: candidates[key] for key in keys}

    return list(candidates.values())


# --------------------------------------------------
# 6. GLOBAL PACKING OPTIMIZATION
# --------------------------------------------------

def optimize_packing(wardrobe, trips, compatibility_df,
                     max_weight_g, max_candidates_per_day=500,
                     time_limit_seconds=30, random_seed=42,
                     allow_outfit_repeats=False):

    compatibility = build_compatibility_map(compatibility_df)
    item_roles = build_item_roles(wardrobe)
    rng = random.Random(random_seed)

    # Create candidates for every day.
    daily_candidates = {}

    for day_idx, (_, trip) in enumerate(trips.iterrows()):
        candidates = generate_outfits(
            wardrobe, trip, compatibility, item_roles,
            max_candidates=max_candidates_per_day, rng=rng,
        )

        if not candidates:
            required = required_roles_for_day(trip)
            return {
                "status": "INFEASIBLE",
                "reason": (
                    f"No feasible outfit for day_number="
                    f"{int(trip['day_number'])}; required roles "
                    f"{sorted(required)} cannot all be covered."
                ),
                "selected_items": [],
                "daily_outfits": [],
                "total_weight_g": None,
                "number_of_items": 0,
                "number_of_outfits": 0,
            }

        daily_candidates[day_idx] = candidates

    model = cp_model.CpModel()
    garment_ids = wardrobe["item_id"].astype(str).tolist()
    garment_map = {
        str(row["item_id"]): row
        for _, row in wardrobe.iterrows()
    }

    x = {
        gid: model.new_bool_var(f"pack_{gid}")
        for gid in garment_ids
    }

    y = {}
    signature_groups = {}

    for day_idx, candidates in daily_candidates.items():
        for outfit_idx, outfit in enumerate(candidates):
            var = model.new_bool_var(
                f"day_{day_idx}_outfit_{outfit_idx}"
            )
            y[(day_idx, outfit_idx)] = var
            signature_groups.setdefault(
                outfit["signature"], []
            ).append(var)

        # Exactly one outfit per day.
        model.add(
            sum(
                y[(day_idx, outfit_idx)]
                for outfit_idx in range(len(candidates))
            ) == 1
        )

        # All clothes in a selected outfit must be packed.
        for outfit_idx, outfit in enumerate(candidates):
            for gid in outfit["item_ids"]:
                model.add(
                    x[gid] >= y[(day_idx, outfit_idx)]
                )

    # Diversité : interdire la même tenue (même signature) sur deux jours.
    if not allow_outfit_repeats:
        for signature, vars_ in signature_groups.items():
            if len(vars_) > 1:
                model.add(sum(vars_) <= 1)

    # Strict luggage weight constraint.
    model.add(
        sum(
            int(garment_map[gid]["weight_g"]) * x[gid]
            for gid in garment_ids
        ) <= int(max_weight_g)
    )

    # Primary objective: minimize the number of packed items.
    # Secondary objective: maximize outfit quality.
    #
    # The penalty is larger than the maximum possible
    # total quality difference across the trip, so one
    # fewer item takes priority over quality.
    max_quality = max(
        outfit["quality"]
        for candidates in daily_candidates.values()
        for outfit in candidates
    )
    item_penalty = len(trips) * max_quality + 1

    quality_term = sum(
        daily_candidates[day_idx][outfit_idx]["quality"]
        * y[(day_idx, outfit_idx)]
        for day_idx, candidates in daily_candidates.items()
        for outfit_idx in range(len(candidates))
    )

    model.maximize(
        quality_term - item_penalty * sum(x.values())
    )

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_seconds

    status = solver.solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {
            "status": solver.status_name(status),
            "selected_items": [],
            "daily_outfits": [],
            "total_weight_g": None,
            "number_of_items": 0,
            "number_of_outfits": 0,
        }

    selected_ids = [
        gid for gid in garment_ids if solver.value(x[gid])
    ]

    selected_items = [
        garment_map[gid].to_dict() for gid in selected_ids
    ]

    daily_outfits = []

    for day_idx, candidates in daily_candidates.items():
        selected_outfit = next(
            outfit
            for outfit_idx, outfit in enumerate(candidates)
            if solver.value(y[(day_idx, outfit_idx)])
        )

        daily_outfits.append(selected_outfit)

    return {
        "status": solver.status_name(status),
        "selected_items": selected_items,
        "daily_outfits": daily_outfits,
        "total_weight_g": sum(
            int(garment_map[gid]["weight_g"])
            for gid in selected_ids
        ),
        "number_of_items": len(selected_ids),
        "number_of_outfits": len(daily_outfits),
    }


# --------------------------------------------------
# 7. VERIFY THE RESULT
# --------------------------------------------------

def report(result, trips, item_roles, garment_map=None):
    print("Status:", result["status"])

    if result["status"] == "INFEASIBLE":
        print("Reason:", result.get("reason"))
        return

    print("Items packed:", result["number_of_items"])
    print("Total weight:", result["total_weight_g"], "g")
    print("Days / outfits:", result["number_of_outfits"])

    signatures = [
        outfit["signature"] for outfit in result["daily_outfits"]
    ]
    print("Distinct outfits:", len(set(signatures)))

    print("\nSelected items:")
    for item in result["selected_items"]:
        print("-", item["item_id"], item["name"])

    print("\nDaily outfits & coverage:")
    for outfit, (_, trip) in zip(
        result["daily_outfits"], trips.iterrows()
    ):
        required = required_roles_for_day(trip)
        covered = set()
        for item_id in outfit["item_ids"]:
            covered.update(item_roles.get(item_id, set()))

        style_ok = None
        if garment_map is not None:
            style_ok = is_outfit_appropriate(
                outfit["item_ids"], trip, garment_map
            )

        print(
            f"Day {outfit['day_number']} "
            f"[{outfit['activity']}/{outfit['required_style']}] "
            f"required={sorted(required)} "
            f"covered={sorted(covered)} "
            f"ok={required.issubset(covered)} "
            f"style_ok={style_ok} "
            f"compat={outfit.get('compatibility')} "
            f"-> {outfit['item_ids']}"
        )

    print("\nReused items:")
    counts = {}
    for outfit in result["daily_outfits"]:
        for item_id in outfit["item_ids"]:
            counts[item_id] = counts.get(item_id, 0) + 1

    for item_id, count in sorted(
        counts.items(), key=lambda kv: -kv[1]
    ):
        if count > 1:
            print(f"- {item_id}: {count} days")


# --------------------------------------------------
# 8. RUN
# --------------------------------------------------

if __name__ == "__main__":
    wardrobe, trips, compatibility = load_data()
    item_roles = build_item_roles(wardrobe)
    garment_map = {
        str(row["item_id"]): row.to_dict()
        for _, row in wardrobe.iterrows()
    }

    # Change this to your actual trip ID.
    available_trip_ids = trips["trip_id"].dropna().unique()
    if len(available_trip_ids) == 0:
        raise ValueError("No trip_id values found.")

    trip_id = available_trip_ids[0]
    selected_trip = trips[
        trips["trip_id"] == trip_id
    ].sort_values("day_number")

    result = optimize_packing(
        wardrobe=wardrobe,
        trips=selected_trip,
        compatibility_df=compatibility,
        max_weight_g=8000,  # Example: 8 kg
    )

    report(result, selected_trip, item_roles, garment_map)
