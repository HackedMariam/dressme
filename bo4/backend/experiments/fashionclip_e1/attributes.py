"""Schéma d'attributs et libellés zéro-shot d'E1 (fixés AVANT toute prédiction).

Chaque classe a plusieurs formulations anglaises neutres ; leurs embeddings
texte sont moyennés (pratique courante en zéro-shot CLIP) pour limiter la
sensibilité à une formulation. Les libellés décrivent ce qui est visible sur
une photo produit ; ils ne reprennent pas les règles du moteur BO4.

Toute modification de ce fichier change `SCHEMA_VERSION` et l'empreinte
enregistrée dans les métadonnées : les résultats ne sont alors plus comparables.
"""

import hashlib
import json

SCHEMA_VERSION = "e1-attributes/1"

# Marge (similarité cosinus top1 - top2) en dessous de laquelle la prédiction
# est signalée ambiguë. Valeur PROVISOIRE fixée a priori, non ajustée sur les
# résultats ; ce n'est pas un seuil de probabilité.
AMBIGUITY_MARGIN = 0.01

# Réponses humaines supplémentaires (jamais produites par le modèle).
HUMAN_EXTRA_OPTIONS = {"incertain": "Incertain", "non_visible": "Non visible"}

ATTRIBUTES = {
    "motif": {
        "label_fr": "Motif",
        "question_fr": "Quel motif voyez-vous sur ce vêtement ?",
        "classes": {
            "uni": {
                "label_fr": "Uni (une seule couleur, sans motif)",
                "prompts": [
                    "a product photo of a plain solid-colour garment",
                    "a garment in a single solid colour with no pattern",
                ],
            },
            "raye": {
                "label_fr": "Rayé",
                "prompts": [
                    "a product photo of a striped garment",
                    "a garment with stripes",
                ],
            },
            "carreaux": {
                "label_fr": "À carreaux",
                "prompts": [
                    "a product photo of a checked or plaid garment",
                    "a garment with a check pattern",
                ],
            },
            "fleuri": {
                "label_fr": "Fleuri",
                "prompts": [
                    "a product photo of a garment with a floral print",
                    "a garment with a flower pattern",
                ],
            },
            "graphique": {
                "label_fr": "Imprimé graphique ou texte",
                "prompts": [
                    "a product photo of a garment with a graphic or text print",
                    "a garment with a printed logo, slogan or picture",
                ],
            },
            "autre_motif": {
                "label_fr": "Autre motif (pois, animal, abstrait…)",
                "prompts": [
                    "a product photo of a garment with an all-over pattern",
                    "a garment with dots, animal print or an abstract pattern",
                ],
            },
        },
    },
    "formalite": {
        "label_fr": "Formalité",
        "question_fr": "Quel est le niveau de formalité de ce vêtement ?",
        "classes": {
            "decontracte": {
                "label_fr": "Décontracté",
                "prompts": [
                    "a casual everyday garment",
                    "a product photo of relaxed casual clothing",
                ],
            },
            "habille_decontracte": {
                "label_fr": "Habillé-décontracté",
                "prompts": [
                    "a smart casual garment",
                    "a product photo of neat smart-casual clothing",
                ],
            },
            "habille": {
                "label_fr": "Habillé / formel",
                "prompts": [
                    "a formal or dressy garment",
                    "a product photo of elegant formal clothing",
                ],
            },
        },
    },
    "registre": {
        "label_fr": "Registre de style",
        "question_fr": "À quel registre de style ce vêtement appartient-il le plus ?",
        "classes": {
            "sport": {
                "label_fr": "Sport / sportswear",
                "prompts": [
                    "sporty athletic clothing",
                    "a product photo of sportswear or athleisure",
                ],
            },
            "classique": {
                "label_fr": "Classique / basique intemporel",
                "prompts": [
                    "classic timeless clothing",
                    "a product photo of a simple wardrobe staple",
                ],
            },
            "romantique": {
                "label_fr": "Romantique / féminin",
                "prompts": [
                    "romantic feminine clothing with delicate details",
                    "a product photo of a soft, feminine garment",
                ],
            },
            "tendance": {
                "label_fr": "Tendance / pièce affirmée",
                "prompts": [
                    "bold trendy fashion clothing",
                    "a product photo of a statement fashion piece",
                ],
            },
        },
    },
    "epaisseur": {
        "label_fr": "Épaisseur apparente",
        "question_fr": "Quelle épaisseur ce vêtement semble-t-il avoir ?",
        "classes": {
            "leger": {
                "label_fr": "Léger / fin",
                "prompts": [
                    "a thin lightweight garment",
                    "a product photo of light, airy clothing",
                ],
            },
            "moyen": {
                "label_fr": "Moyen",
                "prompts": [
                    "a medium-weight garment",
                    "a product photo of mid-weight clothing",
                ],
            },
            "epais": {
                "label_fr": "Épais / chaud",
                "prompts": [
                    "a thick heavy warm garment",
                    "a product photo of padded or chunky warm clothing",
                ],
            },
        },
    },
}


def schema_fingerprint():
    """Empreinte du schéma, des libellés et du seuil d'ambiguïté."""
    payload = json.dumps({"version": SCHEMA_VERSION, "margin": AMBIGUITY_MARGIN, "attributes": ATTRIBUTES},
                         sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
