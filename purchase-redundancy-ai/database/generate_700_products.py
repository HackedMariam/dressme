"""
Generate 700+ Product Seed Data
Rich, diverse product database with real brands and attributes
"""

import json
import random
import hashlib
from pathlib import Path
from typing import List, Dict

class ProductGenerator:
    """Generate diverse product catalog"""

    BRANDS = [
        "H&M", "Zara", "Gap", "ASOS", "Uniqlo", "Nike",
        "Adidas", "Puma", "Tommy Hilfiger", "Ralph Lauren", "Calvin Klein", "Gucci",
        "Prada", "Chanel", "Louis Vuitton", "Dior", "Versace", "Dolce & Gabbana",
        "Armani", "Burberry", "Levi's", "Wrangler", "Lee", "Dockers",
        "Dickies", "Timberland", "Dr. Martens", "UGG", "Converse", "Vans",
        "New Balance", "Asics", "Reebok", "Saucony", "Salomon", "Columbia",
        "North Face", "Patagonia", "REI", "Carhartt", "Banana Republic", "Brooks Brothers",
        "J.Crew", "Bonobos", "Everlane", "Warby Parker", "Outdoor Voices", "Glossier",
        "Lululemon", "Athleta", "Allbirds", "Toms", "Rothys", "Reformation",
        "Madewell", "J Brand", "Frame", "Agolde", "Rag & Bone", "AllSaints",
        "Topshop", "Urban Outfitters", "Free People", "Anthropologie", "Sundance", "LL Bean",
        "Eddie Bauer", "Orvis", "Lands End", "Duluth", "Mizuno", "Oakley",
        "Arc'teryx", "Mammut", "Black Diamond", "Salewa", "La Sportiva", "Scarpa",
        "Five Ten", "Vibram", "Merrell", "Keen", "Teva", "Birkenstock",
        "CROCS", "Clarks", "Skechers", "Minnetonka", "Keds", "Cole Haan",
        "Rockport", "Johnston Murphy", "Allen Edmonds", "Ferragamo", "Louboutin", "Manolo Blahnik",
        "Jimmy Choo", "Stuart Weitzman", "Badgley Mischka", "Diane Von Furstenberg", "Michael Kors", "Coach",
        "Dooney & Bourke", "Fossil",
    ]

    CATEGORIES = {
        "shirts": ["casual shirt", "formal shirt", "t-shirt", "polo", "henley", "sweater", "cardigan", "hoodie", "sweatshirt", "tank top"],
        "pants": ["jeans", "chinos", "dress pants", "joggers", "leggings", "shorts", "cargo pants", "corduroys", "sweatpants", "yoga pants"],
        "dresses": ["casual dress", "formal dress", "cocktail dress", "maxi dress", "midi dress", "shift dress", "wrap dress", "sundress", "shirt dress", "bodycon"],
        "shoes": ["sneakers", "dress shoes", "boots", "sandals", "loafers", "heels", "flats", "oxfords", "athletic shoes", "slip-ons"],
        "outerwear": ["jacket", "coat", "blazer", "cardigan", "vest", "windbreaker", "raincoat", "puffer jacket", "leather jacket", "denim jacket"],
        "accessories": ["scarf", "hat", "belt", "bag", "wallet", "gloves", "sunglasses", "watch", "jewelry", "tie"],
    }

    COLORS = [
        "black", "white", "gray", "navy", "blue", "red", "pink", "green",
        "olive", "khaki", "beige", "cream", "orange", "yellow", "purple",
        "burgundy", "maroon", "teal", "turquoise", "coral", "salmon",
        "gold", "silver", "brown", "tan", "peach", "lavender", "lime",
        "mint", "forest green", "emerald", "cobalt", "royal blue",
    ]

    MATERIALS = [
        "cotton", "polyester", "wool", "silk", "linen", "denim",
        "leather", "suede", "rayon", "nylon", "spandex", "acrylic",
        "viscose", "bamboo", "hemp", "blend", "fleece", "jersey",
    ]

    STYLES = [
        "casual", "formal", "sporty", "bohemian", "minimalist",
        "vintage", "trendy", "classic", "edgy", "romantic",
        "preppy", "athletic", "business", "streetwear", "luxury",
    ]

    # Plausible materials per garment type (a jean is denim, a sneaker is leather/nylon...)
    MATERIALS_BY_SUBCATEGORY = {
        "casual shirt": ["cotton", "linen", "cotton", "polyester"], "formal shirt": ["cotton", "silk", "polyester"],
        "t-shirt": ["cotton", "jersey", "cotton", "bamboo"], "polo": ["cotton", "jersey"], "henley": ["cotton", "jersey"],
        "sweater": ["wool", "cotton", "acrylic", "blend"], "cardigan": ["wool", "cotton", "acrylic"],
        "hoodie": ["cotton", "fleece", "blend"], "sweatshirt": ["cotton", "fleece", "blend"], "tank top": ["cotton", "jersey"],
        "jeans": ["denim"], "chinos": ["cotton", "linen"], "dress pants": ["wool", "polyester", "blend"],
        "joggers": ["cotton", "fleece", "jersey"], "sweatpants": ["cotton", "fleece"], "leggings": ["spandex", "nylon"],
        "yoga pants": ["spandex", "nylon", "polyester"], "shorts": ["cotton", "denim", "linen"],
        "cargo pants": ["cotton", "nylon"], "corduroys": ["cotton"],
        "casual dress": ["cotton", "linen", "jersey", "viscose"], "formal dress": ["silk", "polyester", "viscose"],
        "cocktail dress": ["silk", "polyester", "viscose"], "maxi dress": ["cotton", "viscose", "linen", "rayon"],
        "midi dress": ["cotton", "viscose", "silk"], "shift dress": ["cotton", "polyester", "wool"],
        "wrap dress": ["jersey", "viscose", "silk"], "sundress": ["cotton", "linen"], "shirt dress": ["cotton", "linen"],
        "bodycon": ["spandex", "jersey", "polyester"],
        "sneakers": ["leather", "suede", "nylon", "polyester"], "athletic shoes": ["nylon", "polyester"],
        "boots": ["leather", "suede"], "heels": ["leather", "suede"], "flats": ["leather", "suede"],
        "loafers": ["leather", "suede"], "oxfords": ["leather"], "dress shoes": ["leather"],
        "sandals": ["leather"], "slip-ons": ["cotton", "leather", "suede"],
        "jacket": ["cotton", "nylon", "polyester"], "coat": ["wool", "wool", "blend", "polyester"],
        "blazer": ["wool", "linen", "cotton"], "vest": ["wool", "nylon", "fleece"], "windbreaker": ["nylon", "polyester"],
        "raincoat": ["nylon", "polyester"], "puffer jacket": ["nylon", "polyester"], "leather jacket": ["leather"],
        "denim jacket": ["denim"],
        "scarf": ["wool", "silk", "cotton"], "hat": ["wool", "cotton", "polyester"], "belt": ["leather", "suede"],
        "bag": ["leather", "nylon", "suede"], "wallet": ["leather"], "gloves": ["leather", "wool"],
        "sunglasses": ["blend"], "watch": ["leather", "blend"], "jewelry": ["blend"], "tie": ["silk", "wool"],
    }
    NEUTRALS = ["black", "white", "gray", "navy", "beige", "brown", "khaki", "cream", "tan"]
    COLORS_BY_SUBCATEGORY = {
        "jeans": ["blue", "blue", "navy", "black", "gray", "white"], "denim jacket": ["blue", "navy", "black"],
        "leather jacket": ["black", "brown", "tan"], "dress shoes": ["black", "brown"], "oxfords": ["black", "brown", "tan"],
        "chinos": ["beige", "khaki", "navy", "olive", "tan", "gray"], "belt": ["black", "brown", "tan"],
        "wallet": ["black", "brown", "tan"],
    }

    @staticmethod
    def pick_color(subcategory: str) -> str:
        """Neutrals are 3x more frequent than fashion colors (as in real catalogs)"""
        if subcategory in ProductGenerator.COLORS_BY_SUBCATEGORY:
            return random.choice(ProductGenerator.COLORS_BY_SUBCATEGORY[subcategory])
        if random.random() < 0.55:
            return random.choice(ProductGenerator.NEUTRALS)
        return random.choice(ProductGenerator.COLORS)

    SEASONS = ["spring", "summer", "fall", "winter", "all-season"]

    USE_CASES = [
        "casual", "office", "workout", "party", "dinner",
        "weekend", "travel", "beach", "hiking", "date night",
        "work from home", "gym", "yoga", "running", "everyday",
    ]

    @staticmethod
    def generate_product_id(name: str, brand: str) -> str:
        """Generate unique product ID"""
        content = f"{name}{brand}{random.getrandbits(64)}"
        return hashlib.md5(content.encode()).hexdigest()[:12]

    @staticmethod
    def generate_price() -> float:
        """Generate realistic product price"""
        return round(random.choice([29.99, 39.99, 49.99, 59.99, 69.99, 79.99, 89.99, 99.99, 129.99, 149.99, 199.99, 249.99, 299.99]), 2)

    @staticmethod
    def generate_products(count: int = 700) -> List[Dict]:
        """Generate products catalog"""
        products = []
        seen_ids = set()

        while len(products) < count:
            category = random.choice(list(ProductGenerator.CATEGORIES.keys()))
            subcategory = random.choice(ProductGenerator.CATEGORIES[category])
            brand = random.choice(ProductGenerator.BRANDS)
            color = ProductGenerator.pick_color(subcategory)
            secondary_colors = random.sample(ProductGenerator.COLORS, k=random.randint(1, 2))
            material = random.choice(ProductGenerator.MATERIALS_BY_SUBCATEGORY.get(subcategory, ProductGenerator.MATERIALS))
            style = random.choice(ProductGenerator.STYLES)
            season = random.choice(ProductGenerator.SEASONS)
            use_case = random.choice(ProductGenerator.USE_CASES)

            # Create product name
            adjective = color.title() if random.random() > 0.5 else ""
            # avoid "Casual Casual Shirt" / "Athletic Athletic Shoes"
            style_word = "" if style.lower() in subcategory.lower() else style.title()
            product_name = " ".join(part for part in (adjective, style_word, subcategory.title()) if part)

            product = {
                "id": ProductGenerator.generate_product_id(product_name, brand),
                "name": product_name,
                "brand": brand,
                "category": category,
                "subcategory": subcategory,
                "primary_color": color,
                "secondary_colors": secondary_colors,
                "color_hex": ProductGenerator.get_color_hex(color),
                "material": material,
                "style": style,
                "season": season,
                "use_case": use_case,
                "price": ProductGenerator.generate_price(),
                "currency": "USD",
                "durability_score": round(random.uniform(0.5, 1.0), 2),
                "sustainability_rating": round(random.uniform(0.3, 1.0), 2),
                "resale_value_estimate": round(ProductGenerator.generate_price() * random.uniform(0.2, 0.6), 2),
                "description": f"A stylish {color} {subcategory} made from {material}. Perfect for {use_case} occasions.",
                "care_instructions": ProductGenerator.get_care_instructions(material),
                "image_url": None,  # set below: /images/products/<id>.png
                "tags": [category, style, season, use_case, color, brand.lower()],
                "size_range": ["XS", "S", "M", "L", "XL", "XXL"] if category != "shoes" else ["5", "6", "7", "8", "9", "10", "11", "12", "13"],
            }

            if product["id"] in seen_ids:
                continue
            product["image_url"] = f"/images/products/{product['id']}.png"
            seen_ids.add(product["id"])
            products.append(product)

        return products

    @staticmethod
    def get_color_hex(color: str) -> str:
        """Get hex code for color"""
        color_map = {
            "black": "#000000", "white": "#FFFFFF", "gray": "#808080",
            "navy": "#000080", "blue": "#0000FF", "red": "#FF0000",
            "pink": "#FFC0CB", "green": "#008000", "olive": "#808000",
            "khaki": "#F0E68C", "beige": "#F5F5DC", "cream": "#FFFDD0",
            "orange": "#FFA500", "yellow": "#FFFF00", "purple": "#800080",
            "burgundy": "#800020", "maroon": "#800000", "teal": "#008080",
            "turquoise": "#40E0D0", "coral": "#FF7F50", "salmon": "#FA8072",
            "gold": "#FFD700", "silver": "#C0C0C0", "brown": "#A52A2A",
            "tan": "#D2B48C", "peach": "#FFCCCB", "lavender": "#E6E6FA",
            "lime": "#00FF00", "mint": "#98FF98", "forest green": "#228B22",
            "emerald": "#50C878", "cobalt": "#0047AB", "royal blue": "#4169E1",
        }
        return color_map.get(color.lower(), "#808080")

    @staticmethod
    def get_care_instructions(material: str) -> str:
        """Get care instructions based on material"""
        instructions = {
            "silk": "Hand wash with silk detergent in cool water. Air dry flat.",
            "wool": "Dry clean or hand wash in cold water. Lay flat to dry.",
            "leather": "Clean with leather cleaner. Condition regularly.",
            "cotton": "Machine wash warm. Tumble dry low.",
            "linen": "Hand wash or gentle machine wash. Hang dry.",
            "polyester": "Machine wash warm. Tumble dry low.",
            "nylon": "Machine wash cool. Air dry recommended.",
            "suede": "Spot clean only. Professional cleaning recommended.",
        }
        return instructions.get(material.lower(), "Machine wash and tumble dry.")

# ============================================================================
# MAIN EXECUTION
# ============================================================================

if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("Generating 700+ products...")

    random.seed(42)  # reproducible catalog -> stable product IDs across runs
    products = ProductGenerator.generate_products(700)

    # Save next to this script, whatever the current directory is
    output = Path(__file__).resolve().parent / "products_700.json"
    with open(output, "w", encoding="utf-8") as f:
        json.dump(products, f, indent=2)

    print(f"✅ Generated {len(products)} products")
    print(f"   Categories: {len(set(p['category'] for p in products))}")
    print(f"   Brands: {len(set(p['brand'] for p in products))}")
    print(f"   Saved to: {output}")

    from generate_product_images import main as generate_images
    print(f"🖼️  Generated {generate_images(output)} product images in database/images/products/")

    # Show sample
    print("\n📦 Sample products:")
    for product in products[:3]:
        print(f"   {product['name']} by {product['brand']} - ${product['price']}")
