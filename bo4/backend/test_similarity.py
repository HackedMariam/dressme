
import argparse
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from fashion_clip.fashion_clip import FashionCLIP


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image1", required=True)
    parser.add_argument("--image2", required=True)
    args = parser.parse_args()

    path1 = Path(args.image1)
    path2 = Path(args.image2)

    for path in (path1, path2):
        if not path.is_file():
            raise FileNotFoundError(f"Image introuvable : {path}")

    # Vérifier les images
    for path in (path1, path2):
        with Image.open(path) as img:
            img.verify()

    print("Chargement de FashionCLIP...")
    model = FashionCLIP("fashion-clip")

    print("Extraction des embeddings...")
    embeddings = model.encode_images(
        [str(path1), str(path2)],
        batch_size=2
    )

    embeddings = np.asarray(embeddings, dtype=np.float32)

    # Normalisation L2
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    embeddings = embeddings / np.maximum(norms, 1e-12)

    # Similarité cosinus
    similarity = float(np.dot(embeddings[0], embeddings[1]))

    print("\n=== RESULTAT BO4 ===")
    print(f"Image 1 : {path1.name}")
    print(f"Image 2 : {path2.name}")
    print(f"Dimensions embeddings : {embeddings.shape}")
    print(f"Similarité cosinus : {similarity:.4f}")
    print(f"Similarité en pourcentage indicatif : {similarity * 100:.2f}%")
    print("\nNote : ce score mesure la similarité visuelle,")
    print("pas la compatibilité d'une tenue.")


if __name__ == "__main__":
    main()
