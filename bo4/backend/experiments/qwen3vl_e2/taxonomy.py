"""Taxonomie E2 des attributs vestimentaires (identifiants anglais pour le modèle,
libellés français pour les humains).

Règles (fixées AVANT tout appel au modèle) :
- Une dimension = une question visuelle. Les dimensions sont INDÉPENDANTES :
  une dentelle florale peut avoir pattern=floral ET material_appearance=lace.
- Une texture n'est pas un motif : pattern décrit un dessin de couleurs ; si la
  surface est d'une seule couleur, pattern=solid quelle que soit la texture.
- La coupe (fit) n'est pas un style.
- La formalité ne se déduit jamais de la catégorie (une robe n'est pas
  automatiquement formelle).
- style est EXPLORATOIRE : mesuré, mais jamais utilisé par BO4.
- not_visible quand la photo ne permet pas de décider : ne pas deviner.
- certainty est une auto-évaluation NON calibrée.
"""

import hashlib
import json

TAXONOMY_VERSION = "e2-taxonomy/1"

# Dimensions dont l'échelle est ordinale (pour κ pondéré en E2-b).
ORDINAL = {"formality": ["casual", "smart_casual", "formal"], "thickness": ["light", "medium", "heavy"]}
# Dimensions mesurées mais exclues de toute intégration BO4.
EXPLORATORY = {"style"}

DIMENSIONS = {
    "category": {
        "label_fr": "Catégorie",
        "question": "What type of garment is shown?",
        "values": {
            "top": "Haut (débardeur, top)", "shirt_blouse": "Chemise / blouse", "tshirt": "T-shirt",
            "sweater_knit": "Pull / maille", "hoodie": "Sweat à capuche", "dress": "Robe", "skirt": "Jupe",
            "trousers": "Pantalon", "jeans": "Jean", "shorts": "Short", "jacket": "Veste",
            "coat": "Manteau", "blazer": "Blazer", "cardigan": "Cardigan", "other": "Autre",
        },
    },
    "primary_color": {
        "label_fr": "Couleur principale",
        "question": "Which colour covers the largest area of the garment?",
        "values": {
            "black": "Noir", "white": "Blanc", "grey": "Gris", "beige": "Beige", "brown": "Marron",
            "navy": "Bleu marine", "blue": "Bleu", "light_blue": "Bleu clair", "red": "Rouge",
            "burgundy": "Bordeaux", "pink": "Rose", "purple": "Violet", "green": "Vert", "khaki": "Kaki",
            "yellow": "Jaune", "orange": "Orange", "multicolor": "Multicolore", "other": "Autre",
        },
    },
    "pattern": {
        "label_fr": "Motif (dessin de couleurs)",
        "question": "Which colour pattern is printed or woven on the surface? A texture alone is not a pattern.",
        "values": {
            "solid": "Uni", "striped": "Rayé", "checked": "À carreaux", "floral": "Fleuri", "dotted": "À pois",
            "animal": "Imprimé animal", "graphic_print": "Imprimé graphique / texte / logo",
            "abstract_geometric": "Abstrait / géométrique", "other_pattern": "Autre motif",
            "not_visible": "Non visible",
        },
    },
    "material_appearance": {
        "label_fr": "Matière apparente",
        "question": "What does the fabric look like? Judge appearance only, not fibre composition.",
        "values": {
            "jersey_fine_knit": "Jersey / maille fine", "chunky_knit": "Grosse maille", "denim": "Denim",
            "smooth_woven": "Tissu tissé lisse", "lace": "Dentelle", "satin_shiny": "Satiné / brillant",
            "leather_like": "Aspect cuir", "suede_like": "Aspect suède", "fur_teddy_fleece": "Fourrure / teddy / polaire",
            "corduroy_velvet": "Velours / côtelé", "mesh_sheer": "Résille / transparent",
            "sequin_metallic": "Sequins / métallisé", "quilted_padded": "Matelassé / rembourré",
            "not_visible": "Non visible",
        },
    },
    "fit": {
        "label_fr": "Coupe",
        "question": "What is the silhouette relative to the body? This is not a style.",
        "values": {
            "fitted": "Ajustée / moulante", "regular": "Droite / standard", "loose_oversized": "Ample / oversize",
            "flared": "Évasée", "not_visible": "Non visible",
        },
    },
    "style": {
        "label_fr": "Registre de style (exploratoire)",
        "question": "Which style register dominates?",
        "values": {
            "athletic": "Sport / technique", "casual_basic": "Basique décontracté",
            "classic_tailored": "Classique / tailleur", "dressy_evening": "Habillé / soirée",
            "romantic_boho": "Romantique / bohème", "streetwear_trendy": "Streetwear / tendance",
            "not_visible": "Non visible",
        },
    },
    "formality": {
        "label_fr": "Formalité",
        "question": "What is the most formal plausible context for wearing it? Do not infer it from the category alone.",
        "values": {"casual": "Décontracté", "smart_casual": "Habillé-décontracté", "formal": "Habillé / formel",
                   "not_visible": "Non visible"},
    },
    "thickness": {
        "label_fr": "Épaisseur apparente",
        "question": "How thick does it look (transparency, volume, padding, chunky knit)? Use not_visible if unsure.",
        "values": {"light": "Fin / léger", "medium": "Moyen", "heavy": "Épais / chaud", "not_visible": "Non visible"},
    },
    "certainty": {
        "label_fr": "Certitude déclarée (non calibrée)",
        "question": "How certain are you overall?",
        "values": {"low": "Faible", "medium": "Moyenne", "high": "Élevée"},
    },
}

RULES = [
    "Each field is independent: e.g. a floral lace dress is pattern=floral AND material_appearance=lace.",
    "pattern describes a colour design; a single-colour surface is pattern=solid whatever its texture.",
    "fit describes the silhouette and is never a style.",
    "Never infer formality from the category alone (a dress is not automatically formal).",
    "Answer only from what is visible in the image; use not_visible when it cannot be decided.",
]


def values(dimension):
    return tuple(DIMENSIONS[dimension]["values"])


def taxonomy_fingerprint():
    payload = json.dumps({"version": TAXONOMY_VERSION, "dimensions": DIMENSIONS, "rules": RULES,
                          "ordinal": ORDINAL, "exploratory": sorted(EXPLORATORY)}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
