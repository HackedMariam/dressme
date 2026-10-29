
import pandas as pd
import json
from pathlib import Path

DATA_DIR = Path("data")

wardrobe = pd.read_csv(DATA_DIR / "wardrobe.csv")
requirements = pd.read_csv(DATA_DIR / "trip_requirements.csv")
compatibility = pd.read_csv(DATA_DIR / "compatibility.csv")

with open(DATA_DIR / "trips.json", encoding="utf-8") as f:
    trips = json.load(f)

print("Wardrobe:", wardrobe.shape)
print("Trips:", len(trips))
print("Daily requirements:", requirements.shape)
print("Compatibility:", compatibility.shape)

print("\nWardrobe preview:")
print(wardrobe.head())

print("\nTrip example:")
print(json.dumps(trips[0], indent=2, ensure_ascii=False))
