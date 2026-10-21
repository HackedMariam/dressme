"""
REAL CLIP Integration - OpenAI CLIP Embeddings
Production-ready for real image and text embeddings
"""

import base64
import colorsys
import hashlib
import io
import re
from datetime import datetime
from typing import List, Dict, Optional, Sequence

import numpy as np
from PIL import Image
import logging

logger = logging.getLogger(__name__)

# Zero-shot labels used to extract attributes from an image with CLIP
CATEGORY_LABELS = ["shirts", "pants", "dresses", "shoes", "outerwear", "accessories"]
CATEGORY_PROMPTS = {
    "shirts": "a photo of a shirt, t-shirt, sweater or top",
    "pants": "a photo of pants, jeans, shorts or leggings",
    "dresses": "a photo of a dress",
    "shoes": "a photo of shoes, sneakers or boots",
    "outerwear": "a photo of a jacket, coat or blazer",
    "accessories": "a photo of a bag, hat, scarf, belt, watch or jewelry",
}
STYLE_LABELS = ["casual", "formal", "sporty", "vintage", "streetwear", "business", "bohemian", "minimalist"]
MATERIAL_LABELS = ["cotton", "denim", "leather", "wool", "silk", "linen", "polyester", "knit"]

# ============================================================================
# CLIP MODEL
# ============================================================================

class CLIPEmbedding:
    """
    Real CLIP Integration using OpenAI's CLIP model
    Generates actual image and text embeddings for similarity detection.
    Falls back to a deterministic token-hashing embedding when torch/transformers
    are missing or the model cannot be downloaded.
    """

    def __init__(self, model_name: str = "openai/clip-vit-base-patch32", use_cuda: bool = False, enabled: bool = True,
                 quantize: bool = False):
        """Initialize CLIP model (quantize=True: int8 dynamic quantization of the Linear layers, CPU only)"""
        self.model_name = model_name
        self.quantized = False
        self.device = "cpu"
        self.model = None
        self.processor = None
        self.clip_available = False
        self.load_error: Optional[str] = None

        if not enabled:
            self.load_error = "CLIP disabled by configuration (CLIP_ENABLED=False)"
            logger.warning(f"⚠️ {self.load_error}")
            return

        try:
            import torch
            from transformers import CLIPProcessor, CLIPModel

            if use_cuda and torch.cuda.is_available():
                self.device = "cuda"

            logger.info(f"Loading OpenAI CLIP model ({model_name}) on {self.device}...")
            self.model = CLIPModel.from_pretrained(model_name).to(self.device)
            self.model.eval()
            if quantize and self.device == "cpu":
                self.model = torch.quantization.quantize_dynamic(self.model, {torch.nn.Linear}, dtype=torch.qint8)
                self.quantized = True
                logger.info("CLIP quantized to int8 (dynamic, Linear layers)")
            self.processor = CLIPProcessor.from_pretrained(model_name)

            self.clip_available = True
            logger.info(f"✅ CLIP model loaded successfully on {self.device}")

        except ImportError as e:
            self.load_error = f"CLIP libraries not available: {e}"
            logger.warning(f"⚠️ {self.load_error}")
            logger.warning("   Install with: pip install -r requirements-ml.txt")
        except Exception as e:  # network error, corrupted cache, out of memory...
            self.load_error = f"CLIP model could not be loaded: {e}"
            logger.warning(f"⚠️ {self.load_error}")

    @property
    def mode(self) -> str:
        if not self.clip_available:
            return "simulated"
        return "clip-int8" if self.quantized else "clip"

    # ------------------------------------------------------------------
    # Embeddings
    # ------------------------------------------------------------------

    def get_image_embedding(self, image_input) -> np.ndarray:
        """
        Generate embedding for an image

        Args:
            image_input: File path (str), PIL Image, raw bytes or base64 string

        Returns:
            512-dimensional normalized embedding vector
        """
        try:
            image = load_image(image_input)
        except Exception as e:
            logger.error(f"Could not load image: {e}")
            return self._simulate_embedding("invalid-image")

        if not self.clip_available:
            return self._simulate_image_embedding(image)

        try:
            import torch

            inputs = self.processor(images=image, return_tensors="pt").to(self.device)
            with torch.no_grad():
                image_features = self._as_tensor(self.model.get_image_features(**inputs))

            return self._normalize(image_features[0].cpu().numpy())

        except Exception as e:
            logger.error(f"Error processing image with CLIP: {e}")
            return self._simulate_image_embedding(image)

    def get_image_embeddings(self, images: Sequence[Image.Image], batch_size: int = 32) -> np.ndarray:
        """Batch image embeddings - shape (len(images), 512)"""
        if not images:
            return np.zeros((0, 512), dtype=np.float32)
        if not self.clip_available:
            return np.stack([self._simulate_image_embedding(img) for img in images])

        import torch

        chunks = []
        for start in range(0, len(images), batch_size):
            batch = [img.convert("RGB") for img in images[start:start + batch_size]]
            inputs = self.processor(images=batch, return_tensors="pt").to(self.device)
            with torch.no_grad():
                features = self._as_tensor(self.model.get_image_features(**inputs))
            chunks.append(features.cpu().numpy())
        embeddings = np.concatenate(chunks, axis=0)
        embeddings = embeddings / (np.linalg.norm(embeddings, axis=1, keepdims=True) + 1e-8)
        return embeddings.astype(np.float32)

    def get_text_embedding(self, text: str) -> np.ndarray:
        """Generate a 512-dim normalized embedding for a text description"""
        return self.get_text_embeddings([text])[0]

    def get_text_embeddings(self, texts: Sequence[str], batch_size: int = 64) -> np.ndarray:
        """Batch text embeddings - shape (len(texts), 512)"""
        if not texts:
            return np.zeros((0, 512), dtype=np.float32)

        if not self.clip_available:
            return np.stack([self._simulate_embedding(t) for t in texts])

        try:
            import torch

            chunks = []
            for start in range(0, len(texts), batch_size):
                batch = list(texts[start:start + batch_size])
                inputs = self.processor(text=batch, return_tensors="pt", padding=True, truncation=True).to(self.device)
                with torch.no_grad():
                    features = self._as_tensor(self.model.get_text_features(**inputs))
                chunks.append(features.cpu().numpy())

            embeddings = np.concatenate(chunks, axis=0)
            embeddings = embeddings / (np.linalg.norm(embeddings, axis=1, keepdims=True) + 1e-8)
            return embeddings.astype(np.float32)

        except Exception as e:
            logger.error(f"Error processing text with CLIP: {e}")
            return np.stack([self._simulate_embedding(t) for t in texts])

    def similarity(self, embedding1: np.ndarray, embedding2: np.ndarray) -> float:
        """
        Cosine similarity between two normalized embeddings, clipped to 0-1
        (negative similarity = unrelated = 0)
        """
        dot_product = float(np.dot(np.asarray(embedding1), np.asarray(embedding2)))
        return float(np.clip(dot_product, 0.0, 1.0))

    def zero_shot(self, image_embedding: np.ndarray, labels: List[str], prompts: Optional[Dict[str, str]] = None) -> Dict:
        """
        Zero-shot classification of an image embedding against text labels.
        Returns {"label": best_label, "confidence": prob, "scores": {...}}
        """
        if not self.clip_available:
            return {"label": None, "confidence": 0.0, "scores": {}}

        texts = [prompts[label] if prompts else f"a photo of {label} clothing" for label in labels]
        text_embeddings = self.get_text_embeddings(texts)
        logits = 100.0 * text_embeddings @ np.asarray(image_embedding)
        probs = np.exp(logits - logits.max())
        probs = probs / probs.sum()
        best = int(np.argmax(probs))
        return {
            "label": labels[best],
            "confidence": round(float(probs[best]), 3),
            "scores": {label: round(float(p), 3) for label, p in zip(labels, probs)},
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _as_tensor(output):
        """transformers >= 5 may return a ModelOutput instead of a tensor"""
        if hasattr(output, "pooler_output") and not hasattr(output, "cpu"):
            return output.pooler_output
        return output

    @staticmethod
    def _normalize(vector: np.ndarray) -> np.ndarray:
        vector = np.asarray(vector, dtype=np.float32)
        return (vector / (np.linalg.norm(vector) + 1e-8)).astype(np.float32)

    def _decode_base64_image(self, base64_string: str) -> Image.Image:
        """Decode base64 image to PIL Image"""
        return load_image(base64_string)

    def _simulate_embedding(self, input_data: str) -> np.ndarray:
        """
        Deterministic fallback embedding (feature hashing of word tokens and bigrams).
        Texts sharing words get similar vectors, so similarity stays meaningful
        even without the CLIP model.
        """
        vector = np.zeros(512, dtype=np.float32)
        tokens = re.findall(r"[a-z0-9]+", str(input_data).lower())
        features = tokens + [f"{a}_{b}" for a, b in zip(tokens, tokens[1:])]

        for feature in features:
            digest = hashlib.md5(feature.encode()).digest()
            index = int.from_bytes(digest[:4], "little") % 512
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign

        if not features:
            vector[0] = 1.0

        return self._normalize(vector)

    def _simulate_image_embedding(self, image: Image.Image) -> np.ndarray:
        """Fallback image embedding: downscaled pixels projected to 512 dims"""
        small = np.asarray(image.convert("RGB").resize((16, 16)), dtype=np.float32).flatten() / 255.0
        rng = np.random.default_rng(42)  # fixed projection -> deterministic
        projection = rng.standard_normal((512, small.size)).astype(np.float32)
        return self._normalize(projection @ (small - small.mean()))


def load_image(image_input) -> Image.Image:
    """Load a PIL RGB image from a path, bytes, base64 string or PIL image"""
    if isinstance(image_input, Image.Image):
        return image_input.convert("RGB")
    if isinstance(image_input, (bytes, bytearray)):
        return Image.open(io.BytesIO(image_input)).convert("RGB")
    if isinstance(image_input, str):
        data = image_input.strip()
        if data.startswith("data:image"):
            data = data.split(",", 1)[1]
            return Image.open(io.BytesIO(base64.b64decode(data))).convert("RGB")
        if len(data) > 260:  # too long for a file path -> raw base64
            return Image.open(io.BytesIO(base64.b64decode(data))).convert("RGB")
        return Image.open(data).convert("RGB")
    raise ValueError(f"Unsupported image input type: {type(image_input).__name__}")

# ============================================================================
# IMAGE PROCESSOR
# ============================================================================

class ImageProcessor:
    """Process images and extract attributes"""

    def __init__(self, clip_embedding: CLIPEmbedding):
        self.clip = clip_embedding

    def process_image(self, image_input) -> Dict:
        """
        Process image and extract attributes

        Returns:
            {
                'status': 'success'|'error',
                'embedding': list (first 50 dims),
                'attributes': {...},
                'colors': [...],
                'confidence': float
            }
        """
        try:
            image = load_image(image_input)
            embedding = self.clip.get_image_embedding(image)
            colors = self._extract_colors(image)
            attributes = self._analyze_attributes(embedding, image, colors)

            return {
                "status": "success",
                "embedding_mode": self.clip.mode,
                "embedding": embedding.tolist()[:50],  # First 50 dims for display
                "embedding_full": embedding.tolist(),
                "attributes": attributes,
                "colors": colors,
                "dimensions": {"width": image.width, "height": image.height},
                "confidence": attributes.get("category_confidence", 0.5),
            }

        except Exception as e:
            logger.error(f"Image processing error: {e}")
            return {
                "status": "error",
                "error": str(e),
                "attributes": self._default_attributes()
            }

    def _extract_colors(self, image: Image.Image) -> List[str]:
        """Extract the 3 dominant color names (center crop to limit background)"""
        try:
            w, h = image.size
            crop = image.crop((int(w * 0.15), int(h * 0.15), int(w * 0.85), int(h * 0.85)))
            pixels = np.asarray(crop.resize((50, 50)), dtype=np.int32).reshape(-1, 3)

            color_map: Dict[str, int] = {}
            for r, g, b in pixels:
                name = self._rgb_to_color_name(int(r), int(g), int(b))
                color_map[name] = color_map.get(name, 0) + 1

            sorted_colors = sorted(color_map.items(), key=lambda x: x[1], reverse=True)
            return [color for color, _ in sorted_colors[:3]]

        except Exception as e:
            logger.error(f"Color extraction error: {e}")
            return ["unknown"]

    @staticmethod
    def _rgb_to_color_name(r: int, g: int, b: int) -> str:
        """Convert RGB to a color name using HSV"""
        h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
        hue = h * 360

        if v < 0.18:
            return "black"
        if s < 0.15:
            if v > 0.85:
                return "white"
            return "gray"
        if s < 0.35 and v > 0.6 and 20 <= hue < 60:
            return "beige"
        if hue < 15 or hue >= 345:
            return "red" if v > 0.5 else "burgundy"
        if hue < 40:
            return "orange" if v > 0.6 else "brown"
        if hue < 70:
            return "yellow" if v > 0.6 else "olive"
        if hue < 165:
            return "green" if v > 0.4 else "olive"
        if hue < 200:
            return "teal"
        if hue < 255:
            return "blue" if v > 0.45 else "navy"
        if hue < 290:
            return "purple"
        return "pink"

    def _analyze_attributes(self, embedding: np.ndarray, image: Image.Image, colors: List[str]) -> Dict:
        """Extract clothing attributes - CLIP zero-shot when available"""
        brightness = float(np.asarray(image.convert("L"), dtype=np.float32).mean() / 255.0)
        attributes = {
            "primary_color": colors[0] if colors else "unknown",
            "estimated_brightness": "dark" if brightness < 0.35 else "light" if brightness > 0.65 else "medium",
            "condition": "good",
        }

        if self.clip.clip_available:
            category = self.clip.zero_shot(embedding, CATEGORY_LABELS, CATEGORY_PROMPTS)
            style = self.clip.zero_shot(embedding, STYLE_LABELS, {s: f"a photo of {s} style clothing" for s in STYLE_LABELS})
            material = self.clip.zero_shot(embedding, MATERIAL_LABELS, {m: f"a photo of clothing made of {m}" for m in MATERIAL_LABELS})
            attributes.update({
                "category": category["label"],
                "category_confidence": category["confidence"],
                "category_scores": category["scores"],
                "style": style["label"],
                "style_confidence": style["confidence"],
                "material_appearance": material["label"],
                "material_confidence": material["confidence"],
                "method": "clip_zero_shot",
            })
        else:
            attributes.update({
                "category": "unknown",
                "category_confidence": 0.0,
                "style": "unknown",
                "material_appearance": "unknown",
                "method": "color_analysis_only (CLIP unavailable)",
            })

        return attributes

    def _default_attributes(self) -> Dict:
        """Default attributes if processing fails"""
        return {
            "primary_color": "unknown",
            "style": "unknown",
            "category": "unknown",
            "material_appearance": "unknown",
            "condition": "unknown"
        }

# ============================================================================
# CAMERA CAPTURE
# ============================================================================

class CameraCapture:
    """Handle camera and gallery image capture"""

    def __init__(self, clip_embedding: CLIPEmbedding):
        self.processor = ImageProcessor(clip_embedding)

    def capture_and_analyze(self, image_source) -> Dict:
        """
        Capture image and analyze it

        Args:
            image_source: File path, bytes, Base64, or PIL Image
        """
        result = self.processor.process_image(image_source)
        if result.get("status") != "success":
            return {
                "status": "error",
                "error": result.get("error"),
                "message": "Failed to capture/analyze image"
            }

        return {
            "status": "success",
            "source": "camera_or_gallery",
            "analysis": result,
            "timestamp": datetime.now().isoformat()
        }

# ============================================================================
# INITIALIZATION
# ============================================================================

if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO)
    print("\n" + "="*70)
    print("CLIP INTEGRATION - Real OpenAI CLIP Embeddings")
    print("="*70)

    clip = CLIPEmbedding()
    print(f"\n✅ System initialized - mode: {clip.mode}")

    text1 = "Blue casual cotton shirt"
    text2 = "Navy cotton t-shirt"
    text3 = "Red formal leather shoes"

    emb1, emb2, emb3 = clip.get_text_embeddings([text1, text2, text3])

    print(f"\n   Similarity: '{text1}' vs '{text2}': {clip.similarity(emb1, emb2):.2%}")
    print(f"   Similarity: '{text1}' vs '{text3}': {clip.similarity(emb1, emb3):.2%}")
    print("\n✅ CLIP integration ready!")
