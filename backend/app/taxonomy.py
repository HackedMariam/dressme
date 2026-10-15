"""Fixed vocabularies shared by the detector, the LLM and the frontend."""

# The 20 classes your YOLO11m-seg model was trained on (index -> name).
MODEL_CLASSES = [
    "top", "sweater", "jacket", "vest", "pants", "shorts", "skirt", "dress",
    "glasses", "hat", "headband", "scarf", "glove", "watch", "belt", "sock",
    "tights", "shoe", "bag", "umbrella",
]

# Model class -> wardrobe group (the filter chips in the UI, and the 3D zone).
CLASS_TO_GROUP = {
    "top": "Tops", "sweater": "Tops", "vest": "Tops",
    "jacket": "Outerwear",
    "pants": "Bottoms", "shorts": "Bottoms", "skirt": "Bottoms",
    "dress": "Dresses",
    "shoe": "Shoes",
    "bag": "Bags",
    "glasses": "Accessories", "hat": "Accessories", "headband": "Accessories",
    "scarf": "Accessories", "glove": "Accessories", "watch": "Accessories",
    "belt": "Accessories", "sock": "Accessories", "tights": "Accessories",
    "umbrella": "Accessories",
}

GROUPS = ["Tops", "Bottoms", "Dresses", "Outerwear", "Shoes", "Bags", "Accessories"]

# Where an item goes in the 3D wardrobe.
GROUP_TO_ZONE = {
    "Tops": "rail", "Outerwear": "rail", "Dresses": "rail", "Bottoms": "rail",
    "Bags": "shelf", "Accessories": "shelf", "Shoes": "floor",
}

PATTERNS = ["solid", "striped", "checked", "floral", "polka dot", "animal print",
            "graphic", "printed", "denim", "knit texture", "colorblock", "other"]
SEASONS = ["spring", "summer", "autumn", "winter"]
STYLES = ["casual", "elegant", "formal", "business", "sporty", "streetwear",
          "bohemian", "minimalist", "classic", "romantic"]
OCCASIONS = ["everyday", "work", "party", "date night", "wedding", "ceremony",
             "sport", "travel", "beach", "lounge", "outdoor"]

# Colour classification: a fixed name (same palette as colors.py, so filters stay
# consistent) plus a family used to match outfits.
COLOR_FAMILIES = ["neutral", "earth", "warm", "cool", "pastel", "bright", "metallic", "multicolor"]
