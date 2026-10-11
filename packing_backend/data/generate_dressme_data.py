#!/usr/bin/env python3
"""
Synthetic dataset generator for DressMe's Packing Agent.

Creates:
  data/wardrobe.csv
  data/trips.json
  data/trip_requirements.csv
  data/compatibility.csv

Uses only Python's standard library. All records and scores are synthetic.
Run:
  python generate_dressme_data.py
  python generate_dressme_data.py --wardrobe-size 60 --trips 20 --seed 42
"""

import argparse
import csv
import json
import random
from datetime import date, timedelta
from pathlib import Path

CATEGORIES = {
    "top": ["t-shirt", "shirt", "blouse", "sweater", "hoodie"],
    "bottom": ["jeans", "trousers", "skirt", "shorts"],
    "dress": ["casual-dress", "formal-dress"],
    "outerwear": ["jacket", "coat", "raincoat", "cardigan"],
    "shoes": ["sneakers", "boots", "loafers", "sandals"],
    "accessory": ["scarf", "hat", "belt", "bag"],
}
COLORS = ["black", "white", "grey", "navy", "blue", "beige", "brown",
          "green", "burgundy", "pink", "cream"]
STYLES = ["casual", "smart-casual", "formal", "sporty", "minimalist"]
SEASONS = ["spring", "summer", "autumn", "winter", "all-season"]
ACTIVITIES = [
    "sightseeing", "walking", "restaurant", "business-meeting",
    "hiking", "beach", "shopping", "night-out", "museum"
]
DRESS_CODES = ["casual", "smart-casual", "formal", "sporty"]
WEATHER_TYPES = ["sunny", "cloudy", "rainy", "windy", "cold", "hot"]
DESTINATIONS = [
    ("Paris", "France"), ("Tunis", "Tunisia"), ("Rome", "Italy"),
    ("Berlin", "Germany"), ("Barcelona", "Spain"), ("London", "United Kingdom"),
    ("Istanbul", "Türkiye"), ("Amsterdam", "Netherlands"),
    ("Marrakech", "Morocco"), ("Vienna", "Austria")
]
ACTIVITY_WEIGHTS = {
    "sightseeing": 0.22, "walking": 0.18, "restaurant": 0.12,
    "business-meeting": 0.08, "hiking": 0.10, "beach": 0.08,
    "shopping": 0.10, "night-out": 0.07, "museum": 0.05,
}
STYLE_BY_ACTIVITY = {
    "business-meeting": ["formal", "smart-casual"],
    "restaurant": ["smart-casual", "formal", "casual"],
    "night-out": ["smart-casual", "formal", "casual"],
    "hiking": ["sporty", "casual"],
    "beach": ["casual", "sporty"],
    "walking": ["casual", "sporty", "smart-casual"],
    "sightseeing": ["casual", "smart-casual", "sporty"],
    "shopping": ["casual", "smart-casual"],
    "museum": ["casual", "smart-casual", "formal"],
}
SEASON_BY_MONTH = {
    12: "winter", 1: "winter", 2: "winter",
    3: "spring", 4: "spring", 5: "spring",
    6: "summer", 7: "summer", 8: "summer",
    9: "autumn", 10: "autumn", 11: "autumn",
}


def weighted_choice(rng, mapping):
    values = list(mapping)
    weights = [mapping[x] for x in values]
    return rng.choices(values, weights=weights, k=1)[0]


def make_wardrobe(rng, size):
    rows = []
    for i in range(1, size + 1):
        category = weighted_choice(rng, {
            "top": 0.28, "bottom": 0.20, "dress": 0.08,
            "outerwear": 0.15, "shoes": 0.15, "accessory": 0.14
        })
        item_type = rng.choice(CATEGORIES[category])
        color = rng.choice(COLORS)
        style = rng.choice(STYLES)
        season = rng.choice(SEASONS)
        if item_type in ("coat", "sweater", "hoodie", "boots", "scarf"):
            warmth = rng.randint(3, 5)
        elif item_type in ("shorts", "sandals", "t-shirt"):
            warmth = rng.randint(1, 2)
        else:
            warmth = rng.randint(1, 4)

        water_resistance = rng.randint(0, 5)
        if item_type in ("raincoat", "boots"):
            water_resistance = rng.randint(3, 5)
        elif item_type in ("sandals", "formal-dress"):
            water_resistance = rng.randint(0, 1)

        weight_g = {
            "top": rng.randint(120, 450),
            "bottom": rng.randint(250, 700),
            "dress": rng.randint(250, 600),
            "outerwear": rng.randint(300, 1100),
            "shoes": rng.randint(450, 1100),
            "accessory": rng.randint(50, 500),
        }[category]
        versatility = round(rng.uniform(0.35, 1.0), 2)
        formality = {
            "casual": rng.randint(1, 2),
            "smart-casual": rng.randint(2, 4),
            "formal": rng.randint(4, 5),
            "sporty": rng.randint(1, 3),
            "minimalist": rng.randint(2, 4),
        }[style]
        rows.append({
            "item_id": f"ITEM{i:03d}",
            "name": f"{color.title()} {item_type.replace('-', ' ')} {i:03d}",
            "category": category,
            "item_type": item_type,
            "color": color,
            "style": style,
            "season": season,
            "warmth_level": warmth,             # 1 = light, 5 = very warm
            "water_resistance": water_resistance, # 0 = none, 5 = very resistant
            "weight_g": weight_g,
            "versatility": versatility,           # synthetic score in [0, 1]
            "formality_level": formality,         # 1 = casual, 5 = formal
            "clean_items_available": True,
            "image_url": "",                      # fill with real URLs later
            "description": f"Synthetic {style} {item_type.replace('-', ' ')} in {color}",
        })
    return rows


def make_trips(rng, trip_count):
    trips = []
    requirements = []
    start_base = date(2026, 10, 15)
    for t in range(1, trip_count + 1):
        city, country = rng.choice(DESTINATIONS)
        duration = rng.randint(3, 8)
        start = start_base + timedelta(days=(t - 1) * 3)
        season = SEASON_BY_MONTH[start.month]
        activities = rng.sample(ACTIVITIES, k=rng.randint(2, 4))
        dress_code = rng.choice(DRESS_CODES)
        max_weight_kg = rng.choice([5.0, 7.0, 8.0, 10.0])
        trip_id = f"TRIP{t:03d}"
        daily = []
        for d in range(duration):
            day_date = start + timedelta(days=d)
            activity = rng.choice(activities)
            # Keep the synthetic climate plausible enough for testing, not forecasting.
            if season == "winter":
                temp = rng.randint(2, 13)
            elif season == "summer":
                temp = rng.randint(22, 35)
            elif season == "spring":
                temp = rng.randint(10, 23)
            else:
                temp = rng.randint(8, 21)
            weather = rng.choices(
                WEATHER_TYPES,
                weights=[0.32, 0.24, 0.14, 0.10, 0.12, 0.08],
                k=1
            )[0]
            if temp >= 27:
                weather = rng.choice(["sunny", "hot", "cloudy"])
            elif temp <= 7:
                weather = rng.choice(["cold", "windy", "rainy", "cloudy"])
            precipitation = round(rng.uniform(0, 12) if weather == "rainy"
                                  else rng.uniform(0, 3), 1)
            required_style = rng.choice(STYLE_BY_ACTIVITY[activity])
            needs_outerwear = weather in ("rainy", "windy", "cold") or temp < 15
            needs_warm_layer = temp < 12
            daily_row = {
                "trip_id": trip_id,
                "day_number": d + 1,
                "date": day_date.isoformat(),
                "activity": activity,
                "weather": weather,
                "temperature_c": temp,
                "precipitation_mm": precipitation,
                "required_style": required_style,
                "needs_outerwear": needs_outerwear,
                "needs_warm_layer": needs_warm_layer,
                "needs_rain_protection": weather == "rainy",
                "needs_sun_protection": weather in ("sunny", "hot"),
            }
            daily.append(daily_row)
            requirements.append(daily_row)

        trips.append({
            "trip_id": trip_id,
            "destination_city": city,
            "destination_country": country,
            "start_date": start.isoformat(),
            "end_date": (start + timedelta(days=duration - 1)).isoformat(),
            "duration_days": duration,
            "activities": activities,
            "dress_code": dress_code,
            "season": season,
            "max_luggage_weight_kg": max_weight_kg,
            "max_items_target": rng.randint(8, 16),
            "allow_laundry": rng.choice([True, False]),
            "daily_requirements": daily,
            "synthetic_data": True,
        })
    return trips, requirements


def compatibility_score(a, b, rng):
    """Synthetic pair score [0, 1], useful for testing—not a learned prediction."""
    if a["category"] == b["category"]:
        return 0.0
    score = 0.62
    if a["color"] == b["color"]:
        score += 0.08
    neutral = {"black", "white", "grey", "navy", "beige", "brown", "cream"}
    if a["color"] in neutral or b["color"] in neutral:
        score += 0.08
    if a["style"] == b["style"]:
        score += 0.10
    elif {a["style"], b["style"]} <= {"casual", "smart-casual", "minimalist"}:
        score += 0.04
    if abs(a["formality_level"] - b["formality_level"]) <= 1:
        score += 0.05
    score += rng.uniform(-0.12, 0.12)
    return round(max(0.0, min(1.0, score)), 3)


def write_csv(path, rows, fieldnames=None):
    if not rows:
        return
    if fieldnames is None:
        fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic DressMe packing data.")
    parser.add_argument("--wardrobe-size", type=int, default=50,
                        help="Number of synthetic wardrobe items (default: 50)")
    parser.add_argument("--trips", type=int, default=15,
                        help="Number of synthetic trip scenarios (default: 15)")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed for reproducible output (default: 42)")
    parser.add_argument("--output-dir", default="dressme_synthetic_data",
                        help="Output folder (default: dressme_synthetic_data)")
    args = parser.parse_args()

    if args.wardrobe_size < 12:
        parser.error("--wardrobe-size must be at least 12")
    if args.trips < 1:
        parser.error("--trips must be at least 1")

    rng = random.Random(args.seed)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)

    wardrobe = make_wardrobe(rng, args.wardrobe_size)
    trips, requirements = make_trips(rng, args.trips)

    compatibility = []
    for i, a in enumerate(wardrobe):
        for b in wardrobe[i + 1:]:
            compatibility.append({
                "item_id_a": a["item_id"],
                "item_id_b": b["item_id"],
                "compatibility_score": compatibility_score(a, b, rng),
                "score_source": "synthetic_heuristic",
            })

    write_csv(output / "wardrobe.csv", wardrobe)
    write_csv(output / "trip_requirements.csv", requirements)
    write_csv(output / "compatibility.csv", compatibility)
    with (output / "trips.json").open("w", encoding="utf-8") as f:
        json.dump(trips, f, ensure_ascii=False, indent=2)

    summary = {
        "wardrobe_items": len(wardrobe),
        "trips": len(trips),
        "daily_requirements": len(requirements),
        "pairwise_compatibility_scores": len(compatibility),
        "seed": args.seed,
        "warning": "All data and compatibility scores are synthetic; do not treat them as real-world predictions.",
    }
    with (output / "dataset_summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print("DressMe synthetic dataset generated successfully.")
    print(f"Output folder: {output.resolve()}")
    for filename in ("wardrobe.csv", "trips.json", "trip_requirements.csv",
                     "compatibility.csv", "dataset_summary.json"):
        print(f" - {filename}")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
