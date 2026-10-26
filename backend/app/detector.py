"""YOLO11m-seg wrapper: detect garment, cut it out (background removal), read its colour."""
from __future__ import annotations

import io
import threading
from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps

from . import config
from .colors import dominant_colors
from .taxonomy import CLASS_TO_GROUP

Image.MAX_IMAGE_PIXELS = 60_000_000  # refuse decompression bombs
try:  # iPhone photos (HEIC) when pillow-heif is installed
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:
    pass


@dataclass
class Detection:
    category: str                 # model class, e.g. "dress"
    group: str                    # UI group, e.g. "Dresses"
    confidence: float             # 0..1
    box: list[float]              # x1, y1, x2, y2 (original pixels)
    area_ratio: float             # mask area / image area
    colors: list[dict] = field(default_factory=list)
    cutout_png: bytes | None = None   # RGBA PNG, background removed, cropped
    alternatives: list[dict] = field(default_factory=list)  # overlapping detections of other classes

    def to_dict(self) -> dict:
        return {
            "category": self.category, "group": self.group,
            "confidence": round(self.confidence, 4), "box": [round(v, 1) for v in self.box],
            "area_ratio": round(self.area_ratio, 4), "colors": self.colors,
            "alternatives": self.alternatives,
        }


def _iou(a, b) -> float:
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


class GarmentDetector:
    _instance: "GarmentDetector | None" = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        from ultralytics import YOLO  # heavy import, done once

        self.model = YOLO(str(config.MODEL_PATH))
        self.names = self.model.names  # {0: 'top', ...}
        self._infer_lock = threading.Lock()

    @classmethod
    def get(cls) -> "GarmentDetector":
        with cls._lock:
            if cls._instance is None:
                cls._instance = GarmentDetector()
            return cls._instance

    # ------------------------------------------------------------------
    @staticmethod
    def load_image(data: bytes) -> Image.Image:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img)  # respect phone orientation
        return img.convert("RGB")

    def detect(self, img: Image.Image, all_items: bool = False) -> list[Detection]:
        """Return detections sorted best-first. If all_items is False only the main garment."""
        with self._infer_lock:
            res = self.model.predict(img, imgsz=config.IMG_SIZE, conf=config.DETECT_CONF,
                                     retina_masks=False, verbose=False)[0]
            if res.boxes is None or len(res.boxes) == 0:
                # second chance with a lower threshold — better a low-confidence guess flagged for review
                res = self.model.predict(img, imgsz=config.IMG_SIZE, conf=0.05,
                                         retina_masks=False, verbose=False)[0]
        if res.boxes is None or len(res.boxes) == 0:
            return []

        W, H = img.size
        raw = []
        polys = res.masks.xy if res.masks is not None else [None] * len(res.boxes)
        for i in range(len(res.boxes)):
            cls_name = self.names[int(res.boxes.cls[i])]
            conf = float(res.boxes.conf[i])
            box = res.boxes.xyxy[i].tolist()
            poly = polys[i]
            mask = Image.new("L", (W, H), 0)
            if poly is not None and len(poly) >= 3:
                ImageDraw.Draw(mask).polygon([tuple(p) for p in poly], fill=255)
            else:  # no mask -> use the box
                ImageDraw.Draw(mask).rectangle(box, fill=255)
            area = np.count_nonzero(np.asarray(mask)) / (W * H)
            raw.append({"cls": cls_name, "conf": conf, "box": box, "mask": mask, "area": area})

        # Main garment = confident AND big (a photo of one item usually fills the frame)
        raw.sort(key=lambda r: r["conf"] * np.sqrt(max(r["area"], 1e-4)), reverse=True)

        detections: list[Detection] = []
        used: list[list[float]] = []
        for r in raw:
            # skip duplicates of an item already kept (same garment, other class guess)
            if any(_iou(r["box"], u) > 0.6 for u in used):
                continue
            alts = [
                {"category": o["cls"], "confidence": round(o["conf"], 4)}
                for o in raw if o is not r and o["cls"] != r["cls"] and _iou(r["box"], o["box"]) > 0.5
            ]
            det = Detection(
                category=r["cls"], group=CLASS_TO_GROUP.get(r["cls"], "Accessories"),
                confidence=r["conf"], box=r["box"], area_ratio=r["area"], alternatives=alts,
            )
            self._finish(img, r["mask"], det)
            detections.append(det)
            used.append(r["box"])
            if not all_items:
                break
        return detections

    # ------------------------------------------------------------------
    @staticmethod
    def _finish(img: Image.Image, mask: Image.Image, det: Detection) -> None:
        # Colour: sample from an eroded mask so edges / background bleed don't count.
        eroded = mask.filter(ImageFilter.MinFilter(9))
        m = np.asarray(eroded) > 127
        if m.sum() < 200:
            m = np.asarray(mask) > 127
        pixels = np.asarray(img)[m]
        det.colors = dominant_colors(pixels)

        # Cut-out: soft alpha edge, crop to box with padding, cap size.
        soft = mask.filter(ImageFilter.GaussianBlur(1.5))
        rgba = img.copy()
        rgba.putalpha(soft)
        x1, y1, x2, y2 = det.box
        pad = 0.04 * max(x2 - x1, y2 - y1)
        W, H = img.size
        crop = rgba.crop((max(0, int(x1 - pad)), max(0, int(y1 - pad)),
                          min(W, int(x2 + pad)), min(H, int(y2 + pad))))
        crop.thumbnail((1024, 1024))
        buf = io.BytesIO()
        crop.save(buf, format="PNG", optimize=True)
        det.cutout_png = buf.getvalue()
