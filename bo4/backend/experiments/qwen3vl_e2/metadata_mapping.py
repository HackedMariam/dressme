"""Correspondance A PRIORI des métadonnées H&M vers la taxonomie E2 (pour E2-b).

Fixée avant de voir toute sortie du modèle. Les métadonnées H&M sont un SYSTÈME
comparé, pas une vérité terrain. `None` = pas de correspondance sûre (ne pas
deviner). H&M mélange motif et matière dans `graphical_appearance_name` : une
même valeur peut alimenter les deux dimensions.
"""

# graphical_appearance_name -> (pattern, material_appearance)
GRAPHICAL_APPEARANCE = {
    "Solid": ("solid", None),
    "Stripe": ("striped", None),
    "Check": ("checked", None),
    "Dot": ("dotted", None),
    "All over pattern": ("other_pattern", None),
    "Front print": ("graphic_print", None),
    "Placement print": ("graphic_print", None),
    "Denim": (None, "denim"),
    "Lace": (None, "lace"),
    "Mesh": (None, "mesh_sheer"),
    "Glittering/Metallic": (None, "sequin_metallic"),
    "Sequin": (None, "sequin_metallic"),
    "Melange": (None, None),
    "Slub": (None, None),
    "Treatment": (None, None),
    "Application/3D": (None, None),
    "Jacquard": (None, None),
    "Other structure": (None, None),
    "Other pattern": ("other_pattern", None),
}

# colour_group_name normalisé (couleur principale)
COLOUR_GROUP = {
    "Black": "black", "White": "white", "Off White": "white", "Grey": "grey", "Dark Grey": "grey",
    "Light Grey": "grey", "Beige": "beige", "Light Beige": "beige", "Dark Beige": "beige",
    "Greyish Beige": "beige", "Yellowish Brown": "brown", "Dark Blue": "navy", "Blue": "blue",
    "Light Blue": "light_blue", "Red": "red", "Dark Red": "burgundy", "Pink": "pink", "Light Pink": "pink",
    "Dark Pink": "pink", "Purple": "purple", "Light Purple": "purple", "Green": "green",
    "Dark Green": "green", "Light Green": "green", "Greenish Khaki": "khaki", "Yellow": "yellow",
    "Light Yellow": "yellow", "Dark Yellow": "yellow", "Orange": "orange", "Light Orange": "orange",
    "Dark Orange": "orange",
}

# product_type_name -> category
PRODUCT_TYPE = {
    "Vest top": "top", "Top": "top", "Shirt": "shirt_blouse", "Blouse": "shirt_blouse", "T-shirt": "tshirt",
    "Sweater": "sweater_knit", "Hoodie": "hoodie", "Dress": "dress", "Skirt": "skirt", "Trousers": "trousers",
    "Shorts": "shorts", "Jacket": "jacket", "Coat": "coat", "Blazer": "blazer", "Cardigan": "cardigan",
}


def map_article(article):
    """Valeurs déduites des métadonnées (None si aucune correspondance sûre)."""
    pattern, material = GRAPHICAL_APPEARANCE.get(article.get("graphical_appearance_name", ""), (None, None))
    return {
        "category": PRODUCT_TYPE.get(article.get("product_type_name", "")),
        "primary_color": COLOUR_GROUP.get(article.get("colour_group_name", "")),
        "pattern": pattern,
        "material_appearance": material,
    }
