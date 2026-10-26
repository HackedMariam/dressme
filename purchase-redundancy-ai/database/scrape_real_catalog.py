"""
Build a REAL product catalog (real photos) from several open sources.

Sources (license stored per product in `source_license`):
  - Marqo/KAGL          (Hugging Face, MIT)        fashion products, 1800x2400 photos, structured categories
  - Marqo/fashion200k   (Hugging Face, Apache-2.0)  products with descriptions (materials) - dresses, jackets...
  - DummyJSON           (public test API)           shirts / shoes / dresses / bags / watches with prices & brands
  - FakeStore API       (public test API)           clothing & jewelry with prices

The Hugging Face datasets are read from a few parquet shards, downloaded once from the Hub CDN
(the photos are embedded in the parquet) - no per-row API calls, so no rate limiting.

Output:
  database/products_real.json
  database/images/real/<id>.jpg   (downscaled to 640 px)

Prices: only DummyJSON / FakeStore publish prices - the Hugging Face products keep price = null
(nothing invented).

Usage:
  python scrape_real_catalog.py              # ~750 products
  python scrape_real_catalog.py --scale 0.5  # smaller catalog
"""

import argparse
import io
import json
import random
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
IMAGE_DIR = HERE / "images" / "real"
CACHE_DIR = HERE / ".scrape_cache"
OUTPUT = HERE / "products_real.json"
USER_AGENT = "purchase-redundancy-catalog/1.0 (educational project)"

SHARDS = {
    "kagl": ("https://huggingface.co/datasets/Marqo/KAGL/resolve/main/data/data-00000-of-00035.parquet",
             CACHE_DIR / "kagl-00000.parquet"),
}
# fashion200k is sorted by category: shard 0 = dresses, 3 = jackets, 4 = pants/skirts
F200K_SHARDS = [0, 3, 4]
F200K_URL = "https://huggingface.co/datasets/Marqo/fashion200k/resolve/main/data/data-{:05d}-of-00009.parquet"

# ============================================================================
# Normalisation helpers
# ============================================================================

COLOR_MAP = {
    "navy blue": "navy", "navy": "navy", "blue": "blue", "black": "black", "white": "white", "grey": "gray",
    "gray": "gray", "charcoal": "gray", "grey melange": "gray", "silver": "silver", "red": "red", "maroon": "maroon",
    "burgundy": "burgundy", "pink": "pink", "magenta": "pink", "rose": "pink", "purple": "purple", "mauve": "purple",
    "lavender": "lavender", "green": "green", "olive": "olive", "sea green": "green", "lime green": "lime",
    "fluorescent green": "lime", "teal": "teal", "turquoise blue": "turquoise", "yellow": "yellow",
    "mustard": "yellow", "orange": "orange", "rust": "orange", "peach": "peach", "brown": "brown",
    "coffee brown": "brown", "copper": "brown", "bronze": "brown", "tan": "tan", "khaki": "khaki", "beige": "beige",
    "skin": "beige", "nude": "beige", "cream": "cream", "off white": "cream", "gold": "gold", "metallic": "silver",
    "steel": "silver", "multi": None,
}
COLOR_WORDS = sorted({k for k in COLOR_MAP if COLOR_MAP[k]} | {"denim", "camel", "ivory"}, key=len, reverse=True)
EXTRA_COLOR = {"denim": "blue", "camel": "tan", "ivory": "cream"}

MATERIAL_WORDS = {
    "cotton": "cotton", "linen": "linen", "wool": "wool", "woollen": "wool", "cashmere": "wool", "merino": "wool",
    "silk": "silk", "satin": "silk", "leather": "leather", "suede": "suede", "denim": "denim", "jeans": "denim",
    "polyester": "polyester", "chiffon": "polyester", "nylon": "nylon", "knit": "knit", "knitted": "knit",
    "fleece": "fleece", "jersey": "jersey", "lace": "polyester", "velvet": "polyester", "corduroy": "cotton",
    "canvas": "cotton", "viscose": "viscose", "rayon": "rayon", "spandex": "spandex",
}

USAGE_TO_STYLE = {"casual": "casual", "formal": "formal", "sports": "sporty", "smart casual": "classic",
                  "party": "trendy", "ethnic": "ethnic", "travel": "casual", "home": "casual"}

# KAGL articleType (category3) -> (category, subcategory)
KAGL_TYPES = {
    "Tshirts": ("shirts", "t-shirt"), "Shirts": ("shirts", "casual shirt"), "Tops": ("shirts", "top"),
    "Sweatshirts": ("shirts", "sweatshirt"), "Sweaters": ("shirts", "sweater"), "Tunics": ("shirts", "top"),
    "Jeans": ("pants", "jeans"), "Trousers": ("pants", "trousers"), "Shorts": ("pants", "shorts"),
    "Track Pants": ("pants", "joggers"), "Skirts": ("pants", "skirt"), "Leggings": ("pants", "leggings"),
    "Capris": ("pants", "capris"),
    "Dresses": ("dresses", "dress"), "Jumpsuit": ("dresses", "jumpsuit"),
    "Jackets": ("outerwear", "jacket"), "Blazers": ("outerwear", "blazer"), "Waistcoat": ("outerwear", "vest"),
    "Rain Jacket": ("outerwear", "raincoat"), "Coats": ("outerwear", "coat"),
    "Casual Shoes": ("shoes", "sneakers"), "Sports Shoes": ("shoes", "athletic shoes"),
    "Formal Shoes": ("shoes", "dress shoes"), "Heels": ("shoes", "heels"), "Flats": ("shoes", "flats"),
    "Sandals": ("shoes", "sandals"), "Sports Sandals": ("shoes", "sandals"), "Flip Flops": ("shoes", "sandals"),
    "Boots": ("shoes", "boots"),
    "Watches": ("accessories", "watch"), "Handbags": ("accessories", "bag"), "Backpacks": ("accessories", "bag"),
    "Clutches": ("accessories", "bag"), "Belts": ("accessories", "belt"), "Wallets": ("accessories", "wallet"),
    "Sunglasses": ("accessories", "sunglasses"), "Caps": ("accessories", "hat"), "Hat": ("accessories", "hat"),
    "Ties": ("accessories", "tie"), "Scarves": ("accessories", "scarf"), "Stoles": ("accessories", "scarf"),
    "Earrings": ("accessories", "jewelry"), "Necklace and Chains": ("accessories", "jewelry"),
    "Bracelet": ("accessories", "jewelry"), "Ring": ("accessories", "jewelry"),
}

F200K_TYPES = {"dresses": ("dresses", "dress"), "jackets": ("outerwear", "jacket"), "pants": ("pants", "trousers"),
               "skirts": ("pants", "skirt"), "tops": ("shirts", "top")}
F200K_LIMITS = {"dresses": 60, "jackets": 80, "pants": 40, "skirts": 20, "tops": 25}

DUMMYJSON_TYPES = {
    "mens-shirts": ("shirts", "casual shirt"), "tops": ("shirts", "top"), "womens-dresses": ("dresses", "dress"),
    "mens-shoes": ("shoes", "sneakers"), "womens-shoes": ("shoes", "heels"), "womens-bags": ("accessories", "bag"),
    "mens-watches": ("accessories", "watch"), "womens-watches": ("accessories", "watch"),
    "sunglasses": ("accessories", "sunglasses"), "womens-jewellery": ("accessories", "jewelry"),
}

TARGETS = {"shirts": 190, "pants": 140, "dresses": 100, "shoes": 150, "outerwear": 90, "accessories": 140}


def find_color(text: str):
    low = text.lower()
    for word in COLOR_WORDS:
        if re.search(rf"\b{re.escape(word)}\b", low):
            return EXTRA_COLOR.get(word) or COLOR_MAP.get(word)
    return None


def find_material(text: str, subcategory: str = ""):
    low = text.lower()
    for word, material in MATERIAL_WORDS.items():
        if re.search(rf"\b{word}\b", low):
            return material
    return "denim" if subcategory == "jeans" else None


def http_get(url: str, timeout: int = 60, attempts: int = 4) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except Exception:
            if attempt == attempts - 1:
                raise
            time.sleep(2 * (attempt + 1))
    return b""


def download(url: str, path: Path) -> Path:
    """Stream a large file (parquet shard) to disk once"""
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    print(f"   ⬇️  {url.split('/datasets/')[1]}", flush=True)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response, open(tmp, "wb") as out:
        while chunk := response.read(1 << 20):
            out.write(chunk)
    tmp.replace(path)
    return path


def save_image_bytes(data: bytes, product_id: str) -> bool:
    """Downscale to 640 px and store as JPEG"""
    path = IMAGE_DIR / f"{product_id}.jpg"
    if path.exists():
        return True
    try:
        image = Image.open(io.BytesIO(data))
        if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
            # transparent WebP/PNG (DummyJSON): flatten on white, not black
            rgba = image.convert("RGBA")
            background = Image.new("RGB", rgba.size, (255, 255, 255))
            background.paste(rgba, mask=rgba.split()[-1])
            image = background
        else:
            image = image.convert("RGB")
        image.thumbnail((640, 640))
        image.save(path, "JPEG", quality=86, optimize=True)
        return True
    except Exception as e:
        print(f"   ⚠️ image failed for {product_id}: {e}")
        return False


def save_image_url(url: str, product_id: str) -> bool:
    try:
        return save_image_bytes(http_get(url), product_id)
    except Exception as e:
        print(f"   ⚠️ download failed for {product_id}: {e}")
        return False

# ============================================================================
# Sources
# ============================================================================

def parquet_rows(path: Path, columns, batch_size: int = 256):
    """Iterate rows of a parquet shard without loading it all in memory"""
    import pyarrow.parquet as pq

    for batch in pq.ParquetFile(path).iter_batches(batch_size=batch_size, columns=columns):
        yield from batch.to_pylist()


def scrape_kagl(quota: dict, seen: set):
    """Marqo/KAGL - one parquet shard (~1.3k products with their photos)"""
    path = download(*SHARDS["kagl"])
    products = []
    cols = ["image", "gender", "category3", "baseColour", "season", "usage", "text", "item_ID"]
    for row in parquet_rows(path, cols):
        mapped = KAGL_TYPES.get(row.get("category3"))
        if not mapped or quota.get(mapped[0], 0) <= 0:
            continue
        name = (row.get("text") or "").strip()
        color = COLOR_MAP.get((row.get("baseColour") or "").lower(), find_color(name))
        if not name or not color or name.lower() in seen:
            continue
        category, subcategory = mapped
        pid = f"kagl-{row['item_ID']}"
        if not save_image_bytes((row.get("image") or {}).get("bytes") or b"", pid):
            continue
        usage = (row.get("usage") or "casual").lower()
        products.append({
            "id": pid, "name": name, "brand": name.split()[0], "category": category, "subcategory": subcategory,
            "primary_color": color, "material": find_material(name, subcategory),
            "style": USAGE_TO_STYLE.get(usage, "casual"), "use_case": usage,
            "season": (row.get("season") or "all-season").lower(), "gender": row.get("gender"),
            "price": None, "currency": None, "description": name,
            "data_source": "Marqo/KAGL (Hugging Face)", "source_license": "MIT",
            "source_url": "https://huggingface.co/datasets/Marqo/KAGL",
        })
        seen.add(name.lower())
        quota[category] -= 1
    print(f"   KAGL: {len(products)} products", flush=True)
    return products


def scrape_fashion200k(seen: set, rng: random.Random):
    """Marqo/fashion200k - a few parquet shards (sorted by category); descriptions give materials"""
    candidates = {k: [] for k in F200K_TYPES}
    for shard in F200K_SHARDS:
        path = download(F200K_URL.format(shard), CACHE_DIR / f"f200k-{shard:05d}.parquet")
        for row in parquet_rows(path, ["image", "category1", "category3", "text", "item_ID"]):
            kind = (row.get("category1") or "").lower()
            if kind not in F200K_TYPES or len(candidates[kind]) >= F200K_LIMITS[kind] * 4:
                continue
            candidates[kind].append(row)

    products = []
    for kind, rows in candidates.items():
        rng.shuffle(rows)
        count = 0
        for row in rows:
            if count >= F200K_LIMITS[kind]:
                break
            title = (row.get("category3") or "").strip()
            description = (row.get("text") or "").strip()
            color = find_color(title) or find_color(description)
            if not title or not color or title.lower() in seen:
                continue
            pid = f"f200k-{row['item_ID']}"
            if not save_image_bytes((row.get("image") or {}).get("bytes") or b"", pid):
                continue
            category, subcategory = F200K_TYPES[kind]
            products.append({
                "id": pid, "name": title.capitalize(), "brand": None, "category": category,
                "subcategory": subcategory, "primary_color": color,
                "material": find_material(f"{title} {description}", subcategory), "style": "casual",
                "use_case": "casual", "season": "all-season", "gender": "Women", "price": None, "currency": None,
                "description": description, "data_source": "Marqo/fashion200k (Hugging Face)",
                "source_license": "Apache-2.0", "source_url": "https://huggingface.co/datasets/Marqo/fashion200k",
            })
            seen.add(title.lower())
            count += 1
    print(f"   fashion200k: {len(products)} products", flush=True)
    return products


def scrape_dummyjson(seen: set):
    products = []
    for slug, (category, subcategory) in DUMMYJSON_TYPES.items():
        data = json.loads(http_get(f"https://dummyjson.com/products/category/{slug}?limit=100"))
        for p in data["products"]:
            if p["title"].lower() in seen:
                continue
            text = f"{p['title']} {p.get('description', '')}"
            products.append({
                "id": f"dj-{p['id']}", "name": p["title"], "brand": p.get("brand"), "category": category,
                "subcategory": subcategory, "primary_color": find_color(text) or "multi",
                "material": find_material(text, subcategory), "style": "casual", "use_case": "casual",
                "season": "all-season",
                "gender": "Men" if slug.startswith("mens") else "Women" if slug.startswith("womens") else None,
                "price": p.get("price"), "currency": "USD", "description": p.get("description"),
                "_image_src": (p.get("images") or [p.get("thumbnail")])[0],
                "data_source": "DummyJSON", "source_license": "public test API",
                "source_url": f"https://dummyjson.com/products/{p['id']}",
            })
            seen.add(p["title"].lower())
    print(f"   DummyJSON: {len(products)} products", flush=True)
    return products


def scrape_fakestore(seen: set):
    products = []
    mapping = {"men's clothing": "shirts", "women's clothing": "shirts", "jewelery": "accessories"}
    for p in json.loads(http_get("https://fakestoreapi.com/products")):
        category = mapping.get(p["category"])
        if not category or p["title"].lower() in seen:
            continue
        text = f"{p['title']} {p.get('description', '')}"
        low = text.lower()
        if category == "shirts" and re.search(r"jacket|coat|raincoat", low):
            category, subcategory = "outerwear", "jacket"
        elif category == "shirts":
            subcategory = "t-shirt" if "t-shirt" in low or "tee" in low else "top"
        else:
            subcategory = "jewelry"
        products.append({
            "id": f"fs-{p['id']}", "name": p["title"][:90], "brand": None, "category": category,
            "subcategory": subcategory, "primary_color": find_color(text) or "multi",
            "material": find_material(text, subcategory), "style": "casual", "use_case": "casual",
            "season": "all-season", "gender": None, "price": p.get("price"), "currency": "USD",
            "description": p.get("description"), "_image_src": p["image"],
            "data_source": "FakeStore API", "source_license": "public test API",
            "source_url": f"https://fakestoreapi.com/products/{p['id']}",
        })
        seen.add(p["title"].lower())
    print(f"   FakeStore: {len(products)} products", flush=True)
    return products

# ============================================================================
# Main
# ============================================================================

GENDER_WORDS = [  # checked in order on the product name - the sources' own labels are missing or wrong
    (re.compile(r"\b(women'?s?|womens|ladies|girl'?s?|female)\b", re.I), "Women"),
    (re.compile(r"\b(men'?s?|mens|male|boy'?s?)\b", re.I), "Men"),
]
# Children's clothes (sources label some of them "Women" / "Unisex"): kept in the catalog, never in adult wardrobes
KIDS_WORDS = re.compile(r"\b(kids?|toddlers?|baby|infants?|doodle (girl|boy)|palm tree)\b", re.I)
CATEGORY_WORDS = [
    (re.compile(r"\b(dress|frock|gown)\b", re.I), "dresses", "dress"),
    (re.compile(r"\b(backpack|handbag|bag|tote|purse)\b", re.I), "accessories", "bag"),
]


def refine(product: dict) -> dict:
    """Fix what the API sources get wrong: DummyJSON files dresses under "tops", FakeStore has no gender
    and lists a backpack as clothing. The product name is the most reliable signal."""
    name = product.get("name") or ""
    for pattern, category, subcategory in CATEGORY_WORDS:
        if pattern.search(name) and product.get("category") != category:
            product["category"], product["subcategory"] = category, subcategory
            break
    if KIDS_WORDS.search(name):
        product["gender"] = "Kids"
    elif not product.get("gender"):
        for pattern, gender in GENDER_WORDS:
            if pattern.search(name):
                product["gender"] = gender
                break
        else:
            if product.get("category") == "dresses":
                product["gender"] = "Women"
    product["tags"] = [t for t in (product["category"], product.get("subcategory"), product.get("primary_color"),
                                   product.get("material"), product.get("style")) if t]
    return product


def main(scale: float = 1.0, seed: int = 7) -> int:
    rng = random.Random(seed)
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    seen: set = set()

    print("🌐 Building the real catalog from 4 sources...", flush=True)
    api_products = scrape_dummyjson(seen) + scrape_fakestore(seen)
    print(f"🖼️  Downloading {len(api_products)} API product photos...", flush=True)
    with ThreadPoolExecutor(max_workers=8) as pool:
        ok = list(pool.map(lambda p: save_image_url(p.pop("_image_src"), p["id"]), api_products))
    products = [p for p, good in zip(api_products, ok) if good]

    products += scrape_fashion200k(seen, rng)

    quota = {c: int(t * scale) for c, t in TARGETS.items()}
    for p in products:
        quota[p["category"]] = quota.get(p["category"], 0) - 1
    products += scrape_kagl(quota, seen)

    for p in products:
        p["image_url"] = f"/images/real/{p['id']}.jpg"
        refine(p)

    keep = {f"{p['id']}.jpg" for p in products}
    for stale in IMAGE_DIR.glob("*.jpg"):
        if stale.name not in keep:
            stale.unlink()

    OUTPUT.write_text(json.dumps(products, indent=1, ensure_ascii=False), encoding="utf-8")
    by_cat, by_src = {}, {}
    for p in products:
        by_cat[p["category"]] = by_cat.get(p["category"], 0) + 1
        by_src[p["data_source"]] = by_src.get(p["data_source"], 0) + 1
    print(f"✅ {len(products)} real products saved to {OUTPUT.name}")
    print(f"   by category: {by_cat}")
    print(f"   by source:   {by_src}")
    print(f"   with price:  {sum(1 for p in products if p['price'])}")
    return len(products)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--scale", type=float, default=1.0, help="multiply the per-category targets")
    main(parser.parse_args().scale)
