
from pathlib import Path

import numpy as np
import torch
from fashion_clip.fashion_clip import FashionCLIP

# Chemin vers notre image H&M
BASE_DIR = Path(__file__).resolve().parent.parent

IMAGE_PATH = (
    BASE_DIR
    / "data"
    / "hm"
    / "images"
    / "010"
    / "0108775015.jpg"
)

print("PyTorch:", torch.__version__)
print("CUDA disponible:", torch.cuda.is_available())
print("Image:", IMAGE_PATH)

if not IMAGE_PATH.exists():
    raise FileNotFoundError(
        f"Image introuvable : {IMAGE_PATH}"
    )

# Charger le modele pre-entraine
print("\nChargement de FashionCLIP...")
model = FashionCLIP("fashion-clip")

# Generer l'embedding de l'image
print("Generation de l'embedding...")
embeddings = model.encode_images(
    [str(IMAGE_PATH)],
    batch_size=1
)

embedding = np.asarray(embeddings[0])

print("\n========== RESULTATS ==========")
print("Article ID:", "0108775015")
print("Dimensions:", embedding.shape)
print("Premieres valeurs:", embedding[:10])
print("Norme:", np.linalg.norm(embedding))
print("================================")
print("Embedding genere avec succes !")
