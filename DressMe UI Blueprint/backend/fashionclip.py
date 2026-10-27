"""Image and text embeddings from the locally downloaded FashionCLIP model."""

from pathlib import Path

import torch
from PIL import Image
from transformers import CLIPModel, CLIPProcessor

MODEL_DIR = Path(__file__).resolve().parent / "models" / "fashionclip"


class FashionCLIPEncoder:
    def __init__(self, device: str = "cpu") -> None:
        if not (MODEL_DIR / "model.safetensors").is_file():
            raise FileNotFoundError("Run python backend/download_fashionclip.py first.")
        self.device = torch.device(device)
        self.processor = CLIPProcessor.from_pretrained(MODEL_DIR, local_files_only=True)
        self.model = CLIPModel.from_pretrained(
            MODEL_DIR, local_files_only=True, use_safetensors=True
        ).to(self.device).eval()

    @torch.inference_mode()
    def encode_text(self, texts: list[str]) -> torch.Tensor:
        if not texts:
            raise ValueError("Provide at least one text.")
        inputs = self.processor(
            text=texts, return_tensors="pt", padding=True, truncation=True
        ).to(self.device)
        features = self.model.get_text_features(**inputs)
        return torch.nn.functional.normalize(features, dim=-1).cpu()

    @torch.inference_mode()
    def encode_images(self, paths: list[str | Path]) -> torch.Tensor:
        if not paths:
            raise ValueError("Provide at least one image path.")
        images = []
        for path in paths:
            with Image.open(path) as image:
                images.append(image.convert("RGB"))
        inputs = self.processor(images=images, return_tensors="pt").to(self.device)
        features = self.model.get_image_features(**inputs)
        return torch.nn.functional.normalize(features, dim=-1).cpu()
