import pandas as pd
from pathlib import Path

data_dir = Path(__file__).parent / "data"
wardrobe = pd.read_csv(data_dir / "wardrobe.csv")

selected_ids = [
    "ITEM001", "ITEM015", "ITEM022",
    "ITEM023", "ITEM040", "ITEM049"]

columns = [
    "item_id", "name", "category", "item_type",
    "style", "season", "warmth_level",
    "water_resistance", "weight_g",
    "versatility", "formality_level"]

available = [c for c in columns if c in wardrobe.columns]

print(wardrobe.loc[
    wardrobe["item_id"].isin(selected_ids), available].to_string(index=False))
print("\n--- Valeurs présentes dans le dataset ---")
for col in ["category", "item_type", "style", "season"]:
    if col in wardrobe.columns:
        print(f"{col}: {sorted(wardrobe[col].dropna().astype(str).unique())}")
