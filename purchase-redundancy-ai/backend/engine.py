"""
Redundancy Engine - the analysis pipeline shared by the REST API and the agents.
Catalog text AND image embeddings are computed once at startup (image embeddings are cached
on disk); each analysis only embeds the new item and the user's wardrobe.
"""

import hashlib
import logging
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
from PIL import Image

from cache import make_key
from clip_integration import CLIPEmbedding
from features import FeatureSet

logger = logging.getLogger(__name__)


class RedundancyEngine:
    """Feature 1-13 pipeline: similarity -> scores -> warning -> explanation -> alternatives"""

    def __init__(self, clip: CLIPEmbedding, catalog: List[Dict], saturation_limit: int = 5,
                 image_root: Optional[Path] = None, cache_dir: Optional[Path] = None, cache=None):
        self.clip = clip
        self.cache = cache
        self.catalog = catalog
        self.saturation_limit = saturation_limit
        self.catalog_index = {p["id"]: i for i, p in enumerate(catalog)}

        # CLIP cosine ranges differ by modality - rescale so 0 = unrelated, 1 = identical.
        # Text: 0.6 = 90th percentile of cross-category pairs on the real catalog.
        # Image: calibrated on the loaded catalog (see _calibrate_image_scale) - illustrations and real
        # photos have very different ranges (median same-subcategory+color cosine 0.97 vs 0.84).
        # Photo->catalog cosines are lower, so catalog search by photo uses 0.5.
        self.text_floor = 0.6 if clip.clip_available else 0.0
        self.image_floor, self.image_ceiling = (0.75, 1.0) if clip.clip_available else (0.0, 1.0)
        self.photo_search_floor = 0.5 if clip.clip_available else 0.0

        logger.info(f"Embedding {len(catalog)} catalog products ({clip.mode})...")
        self.catalog_embeddings = clip.get_text_embeddings([self.describe(p) for p in catalog])
        self.catalog_image_embeddings = self._catalog_image_embeddings(image_root, cache_dir)
        if self.catalog_image_embeddings is not None:
            self.image_floor, self.image_ceiling = self._calibrate_image_scale()
        logger.info("✅ Catalog embeddings ready")

    # ------------------------------------------------------------------
    # Embeddings & similarity
    # ------------------------------------------------------------------

    @staticmethod
    def describe(item: Dict) -> str:
        """Text used for the CLIP embedding of an item"""
        parts = [
            item.get("color") or item.get("primary_color"),
            item.get("material"),
            item.get("style"),
            item.get("subcategory"),
            item.get("name"),
        ]
        seen, words = set(), []
        for part in parts:
            for word in str(part or "").split():
                if word.lower() not in seen:
                    seen.add(word.lower())
                    words.append(word)
        return " ".join(words) or "clothing item"

    def _catalog_image_embeddings(self, image_root: Optional[Path], cache_dir: Optional[Path]) -> Optional[np.ndarray]:
        """CLIP embeddings of the catalog images (cached in cache_dir, keyed by ids + model)"""
        if not self.clip.clip_available or image_root is None:
            return None

        paths = [image_root / str(p.get("image_url") or "").lstrip("/") for p in self.catalog]
        key = hashlib.sha1(("|".join(p["id"] for p in self.catalog) + self.clip.model_name
                            + ("-int8" if self.clip.quantized else "")).encode()).hexdigest()[:16]
        cache_file = cache_dir / f"catalog_image_embeddings_{key}.npy" if cache_dir else None
        if cache_file and cache_file.exists():
            embeddings = np.load(cache_file)
            if embeddings.shape == (len(self.catalog), 512):
                logger.info(f"Loaded catalog image embeddings from cache ({cache_file.name})")
                return embeddings

        available = [i for i, path in enumerate(paths) if path.is_file()]
        if not available:
            logger.warning("No catalog images found - run database/generate_product_images.py")
            return None

        logger.info(f"Embedding {len(available)} catalog images with CLIP (first start only)...")
        embeddings = np.zeros((len(self.catalog), 512), dtype=np.float32)
        embeddings[available] = self.clip.get_image_embeddings([Image.open(paths[i]) for i in available])
        if cache_file:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            for old in cache_file.parent.glob("catalog_image_embeddings_*.npy"):
                old.unlink()
            np.save(cache_file, embeddings)
        return embeddings

    def _calibrate_image_scale(self, sample: int = 40) -> tuple:
        """Image cosine -> similarity scale measured on the catalog itself:
        floor   = median cosine of cross-category pairs        (unrelated items -> 0)
        ceiling = 90th percentile of same subcategory + color  (near-duplicates -> 1)
        On the real photo catalog this gives ~0.67 / ~0.94; a fixed 0.75 floor scored a quarter
        of the real near-duplicates as visually unrelated."""
        emb = self.catalog_image_embeddings
        valid = np.flatnonzero(np.abs(emb).sum(axis=1) > 0)
        if len(valid) < 50:
            return self.image_floor, self.image_ceiling
        rng = np.random.default_rng(0)
        cats = np.array([self.catalog[i]["category"] for i in valid])
        keys = np.array([f"{self.catalog[i].get('subcategory')}|{self.catalog[i].get('primary_color')}" for i in valid])
        unrelated, twins = [], []
        for pos, i in enumerate(valid):
            others = rng.choice(len(valid), size=min(sample, len(valid)), replace=False)
            sims = emb[valid[others]] @ emb[i]
            unrelated.extend(sims[cats[others] != cats[pos]])
            same = np.flatnonzero((keys == keys[pos]) & (np.arange(len(valid)) != pos))
            if len(same):
                twins.extend(emb[valid[same]] @ emb[i])
        if not unrelated or not twins:
            return self.image_floor, self.image_ceiling
        floor, ceiling = float(np.median(unrelated)), float(np.percentile(twins, 90))
        if ceiling - floor < 0.1:  # degenerate catalog (e.g. near-identical illustrations)
            return self.image_floor, self.image_ceiling
        logger.info(f"Image similarity calibrated on the catalog: floor {floor:.3f}, ceiling {ceiling:.3f}")
        return round(floor, 4), round(ceiling, 4)

    def _rescale(self, cosine: float, floor: Optional[float] = None, ceiling: float = 1.0) -> float:
        floor = self.text_floor if floor is None else floor
        return float(np.clip((cosine - floor) / (ceiling - floor), 0.0, 1.0))

    def text_embeddings(self, texts: List[str]) -> np.ndarray:
        """CLIP text embeddings, through the shared cache (Redis or memory) when one is attached"""
        if self.cache is None or not texts:
            return self.clip.get_text_embeddings(texts)
        keys = [make_key(f"emb:{self.clip.mode}", text) for text in texts]
        found = [self.cache.get(k) for k in keys]
        missing = [i for i, value in enumerate(found) if value is None]
        if missing:
            computed = self.clip.get_text_embeddings([texts[i] for i in missing])
            for i, emb in zip(missing, computed):
                found[i] = emb
                self.cache.set(keys[i], emb, ttl=86400)
        return np.asarray(found, dtype=np.float32)

    def embed(self, item: Dict) -> np.ndarray:
        return self.text_embeddings([self.describe(item)])[0]

    def image_embedding_for(self, item: Dict) -> Optional[np.ndarray]:
        """Stored photo embedding, or the catalog image embedding for items added from the catalog"""
        if item.get("image_embedding"):
            return np.asarray(item["image_embedding"], dtype=np.float32)
        idx = self.catalog_index.get(item.get("product_id") or "")
        if idx is not None and self.catalog_image_embeddings is not None:
            return self.catalog_image_embeddings[idx]
        return None

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def _product_result(self, idx: int, similarity: float) -> Dict:
        product = self.catalog[idx]
        return {
            "id": product.get("id"),
            "name": product.get("name"),
            "brand": product.get("brand"),
            "category": product.get("category"),
            "subcategory": product.get("subcategory"),
            "color": product.get("primary_color"),
            "style": product.get("style"),
            "material": product.get("material"),
            "price": product.get("price"),
            "image_url": product.get("image_url"),
            "similarity": round(similarity, 4),
        }

    def _rank(self, scores: np.ndarray, category: str, top_k: int, floor: float,
              max_price: Optional[float] = None) -> List[Dict]:
        results = []
        for idx in np.argsort(-scores):
            product = self.catalog[int(idx)]
            if category and str(product.get("category", "")).lower() != category:
                continue
            if max_price is not None and not (product.get("price") and product["price"] <= max_price):
                continue  # a price ceiling only makes sense for products whose price is known
            results.append(self._product_result(int(idx), self._rescale(float(scores[idx]), floor)))
            if len(results) >= top_k:
                break
        return results

    def search_catalog(self, item: Dict, top_k: int = 5, same_category: bool = True,
                       embedding: Optional[np.ndarray] = None, max_price: Optional[float] = None) -> List[Dict]:
        """Most similar catalog products by text embedding"""
        if not self.catalog:
            return []
        query = embedding if embedding is not None else self.embed(item)
        category = str(item.get("category") or "").lower() if same_category else ""
        return self._rank(self.catalog_embeddings @ query, category, top_k, self.text_floor, max_price)

    def search_catalog_by_image(self, image_embedding: np.ndarray, category: str = "", top_k: int = 5) -> List[Dict]:
        """Most similar catalog products by image (image->image when catalog images exist, else image->text)"""
        if not self.catalog:
            return []
        if self.catalog_image_embeddings is not None:
            scores, floor = self.catalog_image_embeddings @ image_embedding, self.photo_search_floor
        else:
            scores, floor = self.catalog_embeddings @ image_embedding, 0.15  # image->text cosines are low
        return self._rank(scores, (category or "").lower(), top_k, floor)

    def compare_wardrobe(self, new_item: Dict, wardrobe: List[Dict],
                         embedding: Optional[np.ndarray] = None,
                         image_embedding: Optional[np.ndarray] = None) -> List[Dict]:
        """Score every owned item against the candidate; return the similar ones.
        When both items have a photo, visual similarity mixes image (60%) and text (40%) CLIP scores."""
        if not wardrobe:
            return []
        query = embedding if embedding is not None else self.embed(new_item)
        wardrobe_embeddings = self.text_embeddings([self.describe(i) for i in wardrobe])

        matches = []
        for item, emb in zip(wardrobe, wardrobe_embeddings):
            text_sim = self._rescale(float(np.dot(query, emb)))
            image_sim = None
            item_image = self.image_embedding_for(item)
            if image_embedding is not None and item_image is not None:
                image_sim = self._rescale(float(np.dot(image_embedding, item_image)), self.image_floor, self.image_ceiling)
            visual = text_sim if image_sim is None else 0.6 * image_sim + 0.4 * text_sim

            attrs = FeatureSet.feature_3_attribute_comparison(new_item, item)
            score = FeatureSet.feature_2_similarity_score(visual, attrs["color_match"], attrs["style_match"], attrs["material_match"],
                                                          color_known=attrs["color_known"], material_known=attrs["material_known"])
            similarity = score / 100

            if (attrs["category_match"] and similarity >= 0.5) or similarity >= 0.8:
                matches.append({
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "brand": item.get("brand"),
                    "category": item.get("category"),
                    "color": item.get("color"),
                    "style": item.get("style"),
                    "material": item.get("material"),
                    "price": item.get("price"),
                    "image_url": item.get("image_url"),
                    "similarity": round(similarity, 4),
                    "visual_similarity": round(visual, 4),
                    "image_similarity": round(image_sim, 4) if image_sim is not None else None,
                    "attribute_match": attrs,
                })

        matches.sort(key=lambda m: m["similarity"], reverse=True)
        return matches

    def find_internal_duplicates(self, wardrobe: List[Dict], threshold: float = 0.75,
                                 other_color_threshold: float = 0.9) -> List[Dict]:
        """Pairs of owned items that duplicate each other (used by the wardrobe audit).
        Same category, and same color - a silver and a gold watch, or a black and a green bag, are not
        duplicates - unless the pieces are almost identical (>= other_color_threshold)."""
        pairs = []
        for i, item in enumerate(wardrobe):
            others = wardrobe[i + 1:]
            for match in self.compare_wardrobe(item, others, image_embedding=self.image_embedding_for(item)):
                attrs = match["attribute_match"]
                same_color = attrs["color_match"] or not attrs.get("color_known", True)
                needed = threshold if same_color else other_color_threshold
                if match["similarity"] >= needed and attrs["category_match"]:
                    pairs.append({"item_a": item.get("name"), "item_a_id": item.get("id"),
                                  "item_a_image": item.get("image_url"),
                                  "item_b": match["name"], "item_b_id": match["id"],
                                  "item_b_image": match.get("image_url"), "similarity": match["similarity"]})
        return sorted(pairs, key=lambda p: p["similarity"], reverse=True)

    # ------------------------------------------------------------------
    # Full analysis
    # ------------------------------------------------------------------

    @staticmethod
    def recommendation_for(score: int) -> str:
        return "buy" if score < 35 else "consider" if score < 60 else "skip"

    def analyze(self, new_item: Dict, wardrobe: List[Dict], image_embedding: Optional[np.ndarray] = None,
                lang: str = "en") -> Dict:
        embedding = self.embed(new_item)

        # Feature 1-4: similarity against the user's wardrobe (+ market context from the catalog)
        similar_items = self.compare_wardrobe(new_item, wardrobe, embedding, image_embedding)
        if image_embedding is not None:
            catalog_matches = self.search_catalog_by_image(image_embedding, new_item.get("category", ""), top_k=12)
        else:
            catalog_matches = self.search_catalog(new_item, top_k=12, embedding=embedding)
        # never suggest a product the shopper already owns
        owned_ids = {w.get("product_id") for w in wardrobe if w.get("product_id")}
        catalog_matches = [m for m in catalog_matches if m["id"] not in owned_ids][:6]

        same_category = [m for m in similar_items if m["attribute_match"]["category_match"]]
        visual_similarity = max((m["visual_similarity"] for m in same_category), default=0.0)

        # Functional redundancy: does an owned item already cover the same use?
        functional = 0.0
        for m in same_category:
            a = m["attribute_match"]
            value = 100 if a["use_case_match"] else 70 if a["style_match"] else 40
            functional = max(functional, value * m["similarity"])

        # Feature 8-9
        outfit_contribution = FeatureSet.feature_8_outfit_contribution(wardrobe, new_item, similar_items)
        category_saturation = FeatureSet.feature_9_category_saturation(wardrobe, new_item.get("category", ""), self.saturation_limit)

        # Feature 5
        redundancy_score = FeatureSet.feature_5_redundancy_score(
            visual_similarity * 100, functional, category_saturation, outfit_contribution
        )
        if not similar_items:
            redundancy_score = min(redundancy_score, 34)  # nothing owned covers it -> never "skip"

        recommendation = self.recommendation_for(redundancy_score)

        # Feature 11-13
        warning = FeatureSet.feature_11_duplicate_warning(redundancy_score, similar_items, recommendation, lang)
        explanation = FeatureSet.feature_12_explain_redundancy(new_item.get("name", "This item"), redundancy_score,
                                                               similar_items, recommendation, lang)
        alternatives = FeatureSet.feature_13_alternatives(new_item, similar_items, lang)

        confidence = 0.85 if self.clip.clip_available else 0.65
        if image_embedding is not None and any(m.get("image_similarity") is not None for m in similar_items):
            confidence += 0.03
        if len(wardrobe) >= 3:
            confidence += 0.04
        if similar_items and similar_items[0]["similarity"] >= 0.8:
            confidence += 0.04

        return {
            "similar_items": similar_items[:5],
            "catalog_matches": catalog_matches,
            "visual_similarity": round(visual_similarity, 4),
            "functional_similarity": round(functional, 2),
            "category_saturation": round(category_saturation, 2),
            "outfit_contribution": round(outfit_contribution, 2),
            "redundancy_score": redundancy_score,
            "recommendation": recommendation,
            "warning": warning,
            "explanation": explanation,
            "explanation_source": "rules",
            "alternatives": alternatives,
            "confidence": round(min(confidence, 0.99), 2),
            "embedding_mode": self.clip.mode,
        }
