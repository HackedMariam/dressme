"""Calculs zéro-shot purs (numpy), indépendants du modèle.

Les similarités sont des cosinus entre embeddings normalisés : elles servent
à ORDONNER les classes. Ce ne sont pas des probabilités calibrées.
"""

import numpy as np
from PIL import Image

from experiments.fashionclip_e1.attributes import AMBIGUITY_MARGIN


def l2_normalize(vectors):
    vectors = np.asarray(vectors, dtype=np.float64)
    norms = np.linalg.norm(vectors, axis=-1, keepdims=True)
    if np.any(norms == 0):
        raise ValueError("vecteur nul : impossible de normaliser")
    return vectors / norms


def class_embeddings(prompt_embeddings_by_class):
    """{classe: embeddings des formulations} -> (classes, matrice normalisée).

    Chaque classe = moyenne des formulations normalisées, renormalisée.
    """
    classes = list(prompt_embeddings_by_class)
    rows = [l2_normalize(l2_normalize(prompt_embeddings_by_class[c]).mean(axis=0)) for c in classes]
    return classes, np.vstack(rows)


def predict(image_embeddings, classes, class_matrix, margin=AMBIGUITY_MARGIN):
    """Prédiction par image : classe la plus similaire, deuxième classe, marge.

    Renvoie une liste de dicts ; `ambiguous` vaut True si la marge est
    inférieure au seuil fixé a priori (la prédiction est alors conservée mais
    signalée, jamais présentée comme certaine).
    """
    if len(classes) < 2:
        raise ValueError("au moins deux classes sont nécessaires")
    sims = l2_normalize(image_embeddings) @ class_matrix.T
    results = []
    for row in sims:
        order = np.argsort(-row, kind="stable")
        top1, top2 = int(order[0]), int(order[1])
        gap = float(row[top1] - row[top2])
        results.append({
            "prediction": classes[top1],
            "second": classes[top2],
            "margin": gap,
            "ambiguous": gap < margin,
            "similarities": {c: float(row[i]) for i, c in enumerate(classes)},
        })
    return results


def prepare_image(image, mode="pad"):
    """Image RVB prête pour le préprocesseur CLIP.

    - "pad"  : complète en carré sur fond blanc (le vêtement entier reste
               visible malgré le recadrage central 224 x 224 de CLIP) ;
    - "crop" : image inchangée (recadrage central par le préprocesseur).
    """
    image = image.convert("RGB")
    if mode == "crop":
        return image
    if mode != "pad":
        raise ValueError(f"mode d'image inconnu : {mode}")
    side = max(image.size)
    canvas = Image.new("RGB", (side, side), (255, 255, 255))
    canvas.paste(image, ((side - image.width) // 2, (side - image.height) // 2))
    return canvas
