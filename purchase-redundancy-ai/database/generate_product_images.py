"""
Generate one product illustration (PNG) per catalog product.

Each image is drawn from the product's own attributes: the garment silhouette comes from the
subcategory, the fill from primary_color, accents (soles, buttons, straps) from secondary_colors,
and a texture from the material (denim stitching, knit, corduroy, quilting, leather sheen...).
The images give the catalog a visual dataset that CLIP can embed for image-to-image search.

Usage:  python generate_product_images.py        (reads products_700.json, writes images/products/<id>.png)
"""

import json
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE / "images" / "products"
W, H = 512, 640          # drawing canvas (2x, downsampled for anti-aliasing)
OUT_SIZE = (256, 320)

COLOR_HEX = {
    "black": "#1f1f24", "white": "#f7f7f5", "gray": "#8a8d93", "navy": "#1f2a5a", "blue": "#2f6fd6",
    "red": "#d23b3b", "pink": "#f2a7c3", "green": "#2f8f4e", "olive": "#6f7436", "khaki": "#c9b47a",
    "beige": "#e3d5b8", "cream": "#f4ecd6", "orange": "#f08a2c", "yellow": "#f4d03f", "purple": "#7d3c98",
    "burgundy": "#7a1f33", "maroon": "#6e1f22", "teal": "#1f8a8a", "turquoise": "#3cc7c0", "coral": "#ff7f61",
    "salmon": "#f59a86", "gold": "#d4af37", "silver": "#c0c4c8", "brown": "#7b4a2d", "tan": "#cfa77a",
    "peach": "#ffc9a8", "lavender": "#c9b8ea", "lime": "#9bd13d", "mint": "#a8e6c9", "forest green": "#235c3a",
    "emerald": "#2fae74", "cobalt": "#1f4fbf", "royal blue": "#3557d4",
}

# ============================================================================
# Color helpers
# ============================================================================

def hex_rgb(value: str):
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def mix(c1, c2, t: float):
    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))


def luminance(c) -> float:
    return (0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]) / 255


def shade(c, amount: float):
    """amount < 0 darkens, > 0 lightens"""
    return mix(c, (0, 0, 0), -amount) if amount < 0 else mix(c, (255, 255, 255), amount)


def color_of(name: str):
    return hex_rgb(COLOR_HEX.get((name or "").lower(), "#8a8d93"))

# ============================================================================
# Silhouettes - each draws the garment shape (fill=255) on a mask and returns
# a "details" callback drawn afterwards in the outline/accent colors.
# ============================================================================

LONG_SLEEVES = [(172, 110), (340, 110), (414, 168), (466, 470), (414, 482), (366, 252), (364, 548),
                (148, 548), (146, 252), (98, 482), (46, 470), (98, 168)]
SHORT_SLEEVES = [(166, 116), (346, 116), (452, 200), (402, 266), (362, 238), (362, 548),
                 (150, 548), (150, 238), (110, 266), (60, 200)]


def neck_cut(m, box=(212, 92, 300, 150)):
    m.ellipse(box, fill=0)


def buttons(d, x, ys, color, r=7):
    for y in ys:
        d.ellipse((x - r, y - r, x + r, y + r), fill=color)


def collar(d, color, accent):
    d.polygon([(206, 110), (256, 160), (226, 186)], fill=accent, outline=color)
    d.polygon([(306, 110), (256, 160), (286, 186)], fill=accent, outline=color)


def tshirt(m):
    m.polygon(SHORT_SLEEVES, fill=255)
    neck_cut(m)
    return lambda d, o, a: d.arc((212, 92, 300, 150), 0, 180, fill=o, width=6)


def polo(m):
    m.polygon(SHORT_SLEEVES, fill=255)
    neck_cut(m, (220, 100, 292, 140))
    def det(d, o, a):
        collar(d, o, a)
        d.line((256, 160, 256, 250), fill=o, width=4)
        buttons(d, 256, (190, 228), o)
    return det


def henley(m):
    m.polygon(LONG_SLEEVES, fill=255)
    neck_cut(m)
    def det(d, o, a):
        d.line((256, 146, 256, 250), fill=o, width=4)
        buttons(d, 256, (172, 205, 238), a)
    return det


def shirt(m):
    m.polygon(LONG_SLEEVES, fill=255)
    def det(d, o, a):
        collar(d, o, a)
        d.line((256, 160, 256, 548), fill=o, width=4)
        buttons(d, 256, range(205, 548, 60), o)
        d.rectangle((292, 230, 340, 280), outline=o, width=4)          # chest pocket
        for x in (98, 414):                                             # cuffs
            d.line((x - 30, 440, x + 30, 452), fill=o, width=5)
    return det


def sweater(m):
    m.polygon(LONG_SLEEVES, fill=255)
    neck_cut(m)
    def det(d, o, a):
        d.arc((212, 92, 300, 150), 0, 180, fill=o, width=10)
        for y in range(520, 548, 8):
            d.line((152, y, 360, y), fill=o, width=2)
    return det


def cardigan(m):
    m.polygon(LONG_SLEEVES, fill=255)
    m.polygon([(222, 110), (290, 110), (256, 230)], fill=0)
    def det(d, o, a):
        d.line((256, 230, 256, 548), fill=o, width=5)
        buttons(d, 270, range(260, 548, 55), a)
        d.rectangle((168, 400, 222, 450), outline=o, width=4)
        d.rectangle((290, 400, 344, 450), outline=o, width=4)
    return det


def hoodie(m):
    m.ellipse((176, 40, 336, 190), fill=255)
    m.polygon(LONG_SLEEVES, fill=255)
    def det(d, o, a):
        d.ellipse((204, 70, 308, 176), outline=o, width=6)
        d.line((236, 176, 230, 260), fill=a, width=5)
        d.line((276, 176, 282, 260), fill=a, width=5)
        d.polygon([(186, 400), (326, 400), (346, 490), (166, 490)], outline=o, width=5)
    return det


def tank_top(m):
    m.polygon([(186, 96), (226, 96), (256, 178), (286, 96), (326, 96), (350, 232), (362, 548),
               (150, 548), (162, 232)], fill=255)
    return lambda d, o, a: None


def long_pants(m):
    m.polygon([(168, 92), (344, 92), (378, 590), (290, 590), (256, 262), (222, 590), (134, 590)], fill=255)
    def det(d, o, a):
        d.line((168, 126, 344, 126), fill=o, width=5)
        d.line((256, 126, 256, 230), fill=o, width=4)
        buttons(d, 256, (110,), a, 8)
    return det


def jeans(m):
    det_base = long_pants(m)
    def det(d, o, a):
        det_base(d, o, a)
        d.arc((150, 100, 230, 200), 0, 90, fill=a, width=5)
        d.arc((282, 100, 362, 200), 90, 180, fill=a, width=5)
        for x0, x1 in ((140, 222), (290, 372)):
            for y in range(140, 590, 18):
                d.line((x0 + 10 + (y - 140) * 0.02, y, x0 + 10 + (y - 140) * 0.02, y + 9), fill=a, width=3)
    return det


def cargo(m):
    det_base = long_pants(m)
    def det(d, o, a):
        det_base(d, o, a)
        d.rectangle((150, 330, 214, 410), outline=o, width=5)
        d.rectangle((298, 330, 362, 410), outline=o, width=5)
    return det


def joggers(m):
    m.polygon([(168, 92), (344, 92), (370, 560), (292, 560), (256, 262), (220, 560), (142, 560)], fill=255)
    m.rectangle((144, 548, 220, 590), fill=255)
    m.rectangle((292, 548, 368, 590), fill=255)
    def det(d, o, a):
        d.rectangle((168, 92, 344, 132), outline=o, width=5)
        d.line((236, 112, 226, 180), fill=a, width=4)
        d.line((276, 112, 286, 180), fill=a, width=4)
        for x0 in (144, 292):
            d.line((x0, 548, x0 + 76, 548), fill=o, width=5)
    return det


def leggings(m):
    m.polygon([(184, 92), (328, 92), (334, 590), (280, 590), (256, 250), (232, 590), (178, 590)], fill=255)
    return lambda d, o, a: d.line((184, 122, 328, 122), fill=o, width=5)


def shorts(m):
    m.polygon([(166, 140), (346, 140), (374, 392), (274, 404), (256, 290), (238, 404), (138, 392)], fill=255)
    def det(d, o, a):
        d.line((166, 174, 346, 174), fill=o, width=5)
        d.line((256, 174, 256, 260), fill=o, width=4)
    return det


def dress(m, hem=560, flare=110, waist=262, sleeves=False, straps=False):
    if straps:
        m.polygon([(206, 140), (306, 140), (320, 180), (310, waist), (256 + flare + 34, hem),
                   (256 - flare - 34, hem), (202, waist), (192, 180)], fill=255)
    else:
        m.polygon([(204, 90), (308, 90), (324, 150), (312, waist), (256 + flare + 34, hem),
                   (256 - flare - 34, hem), (200, waist), (188, 150)], fill=255)
        neck_cut(m, (222, 76, 290, 130))
    if sleeves:
        m.polygon([(204, 92), (150, 150), (176, 200), (196, 168)], fill=255)
        m.polygon([(308, 92), (362, 150), (336, 200), (316, 168)], fill=255)
    def det(d, o, a):
        if straps:
            d.line((210, 140, 222, 70), fill=o, width=6)
            d.line((302, 140, 290, 70), fill=o, width=6)
        d.line((202, waist, 310, waist), fill=a, width=8)
    return det


def bodycon(m):
    m.polygon([(206, 90), (306, 90), (320, 160), (304, 290), (318, 560), (194, 560), (208, 290), (192, 160)], fill=255)
    neck_cut(m, (226, 76, 286, 124))
    return lambda d, o, a: d.line((208, 290, 304, 290), fill=o, width=3)


def shirt_dress(m):
    det_base = dress(m, hem=560, flare=80, waist=280, sleeves=True)
    def det(d, o, a):
        det_base(d, o, a)
        collar(d, o, a)
        d.line((256, 160, 256, 560), fill=o, width=3)
        buttons(d, 256, range(200, 540, 55), o, 6)
    return det


def wrap_dress(m):
    det_base = dress(m, hem=560, flare=100, waist=270, sleeves=True)
    def det(d, o, a):
        det_base(d, o, a)
        d.line((204, 100, 300, 270), fill=o, width=4)
        d.line((300, 270, 240, 560), fill=o, width=4)
    return det


def sneaker(m):
    m.polygon([(70, 420), (110, 340), (190, 326), (250, 344), (330, 372), (420, 392), (446, 430), (446, 460), (70, 460)], fill=255)
    def det(d, o, a):
        d.rounded_rectangle((60, 452, 456, 492), radius=16, fill=a, outline=o, width=4)
        for i in range(4):
            x = 170 + i * 30
            d.line((x, 352 + i * 6, x + 26, 340 + i * 8), fill=o, width=5)
        d.arc((190, 360, 380, 470), 200, 320, fill=a, width=10)
    return det


def boot(m):
    m.polygon([(140, 150), (276, 150), (284, 368), (420, 392), (446, 436), (446, 470), (124, 470), (130, 300)], fill=255)
    def det(d, o, a):
        d.rectangle((116, 462, 456, 500), fill=a, outline=o, width=4)
        d.rectangle((150, 470, 214, 500), fill=shade(a, -0.3))
        d.line((140, 190, 276, 190), fill=o, width=4)
    return det


def heels(m):
    m.polygon([(96, 392), (150, 350), (226, 360), (310, 392), (404, 330), (430, 344), (420, 400),
               (128, 430)], fill=255)
    m.polygon([(392, 392), (420, 396), (404, 520), (388, 520)], fill=255)
    return lambda d, o, a: d.line((96, 430, 404, 400), fill=a, width=8)


def flat_shoe(m, laces=False, strap=False):
    m.polygon([(84, 410), (140, 362), (300, 360), (404, 388), (440, 430), (440, 462), (84, 462)], fill=255)
    def det(d, o, a):
        d.rectangle((78, 456, 446, 476), fill=shade(a, -0.4))
        if laces:
            for i in range(4):
                d.line((200 + i * 22, 372, 214 + i * 22, 392), fill=o, width=4)
        if strap:
            d.rectangle((220, 378, 300, 396), fill=a, outline=o, width=3)
    return det


def sandal(m):
    m.rounded_rectangle((70, 440, 446, 476), radius=18, fill=255)
    def det(d, o, a):
        d.arc((140, 330, 320, 520), 200, 340, fill=a, width=22)
        d.arc((240, 340, 420, 520), 200, 340, fill=a, width=22)
    return det


def jacket(m, length=560, lapels=True):
    m.polygon([(172, 110), (340, 110), (414, 168), (466, 490), (414, 502), (370, 252), (372, length),
               (140, length), (142, 252), (98, 502), (46, 490), (98, 168)], fill=255)
    def det(d, o, a):
        if lapels:
            d.polygon([(206, 110), (256, 300), (226, 300), (190, 170)], fill=shade(a, -0.1), outline=o)
            d.polygon([(306, 110), (256, 300), (286, 300), (322, 170)], fill=shade(a, -0.1), outline=o)
        d.line((256, 300, 256, length), fill=o, width=4)
        buttons(d, 270, range(330, length - 20, 70), o)
        d.line((166, 420, 222, 420), fill=o, width=5)
        d.line((290, 420, 346, 420), fill=o, width=5)
    return det


def coat(m):
    return jacket(m, length=610)


def raincoat(m):
    det_base = jacket(m, length=600)
    return lambda d, o, a: (det_base(d, o, a), d.rectangle((140, 360, 372, 384), fill=a, outline=o, width=3))


def puffer(m):
    m.polygon([(170, 110), (342, 110), (420, 170), (476, 470), (420, 486), (378, 260), (380, 540),
               (132, 540), (134, 260), (92, 486), (36, 470), (92, 170)], fill=255)
    def det(d, o, a):
        for y in range(170, 540, 52):
            d.line((136, y, 376, y), fill=o, width=4)
        for y in range(220, 480, 52):
            d.line((80, y, 120, y - 10), fill=o, width=4)
            d.line((392, y - 10, 432, y), fill=o, width=4)
        d.line((256, 110, 256, 540), fill=a, width=6)
    return det


def vest(m):
    m.polygon([(176, 110), (336, 110), (372, 210), (370, 548), (142, 548), (140, 210)], fill=255)
    m.polygon([(220, 110), (292, 110), (256, 250)], fill=0)
    def det(d, o, a):
        d.line((256, 250, 256, 548), fill=o, width=4)
        buttons(d, 256, range(280, 540, 60), a)
    return det


def bag(m):
    m.rounded_rectangle((120, 250, 392, 530), radius=34, fill=255)
    def det(d, o, a):
        d.arc((170, 120, 342, 330), 180, 360, fill=o, width=16)
        d.line((120, 330, 392, 330), fill=o, width=4)
        d.rounded_rectangle((236, 316, 276, 350), radius=6, fill=a, outline=o, width=3)
    return det


def hat(m):
    m.ellipse((70, 330, 442, 430), fill=255)
    m.rounded_rectangle((150, 180, 362, 380), radius=70, fill=255)
    return lambda d, o, a: d.rectangle((150, 330, 362, 360), fill=a)


def scarf(m):
    m.polygon([(170, 80), (270, 80), (350, 540), (250, 560)], fill=255)
    m.polygon([(170, 80), (350, 80), (350, 160), (170, 160)], fill=255)
    def det(d, o, a):
        for x in range(254, 352, 14):
            d.line((x, 556 - (x - 250) * 0.2, x + 4, 600), fill=o, width=4)
        for y in range(180, 520, 60):
            d.line((190 + (y - 80) * 0.18, y, 290 + (y - 80) * 0.18, y), fill=a, width=8)
    return det


def belt(m):
    m.rounded_rectangle((40, 290, 472, 350), radius=10, fill=255)
    def det(d, o, a):
        d.rectangle((150, 272, 230, 368), outline=a, width=12)
        d.line((190, 290, 190, 350), fill=a, width=8)
        for x in range(280, 440, 36):
            d.ellipse((x - 7, 313, x + 7, 327), fill=o)
    return det


def wallet(m):
    m.rounded_rectangle((120, 230, 392, 430), radius=22, fill=255)
    def det(d, o, a):
        d.polygon([(120, 260), (392, 260), (392, 330), (120, 330)], outline=o, width=4)
        d.ellipse((340, 284, 364, 308), fill=a)
    return det


def gloves(m):
    for ox in (-90, 90):
        m.rounded_rectangle((176 + ox, 300, 336 + ox, 520), radius=40, fill=255)
        for i in range(4):
            m.rounded_rectangle((180 + ox + i * 38, 170 + abs(1.5 - i) * 20, 214 + ox + i * 38, 330), radius=17, fill=255)
    return lambda d, o, a: [d.rectangle((176 + ox, 480, 336 + ox, 520), fill=a) for ox in (-90, 90)]


def sunglasses(m):
    m.ellipse((70, 260, 236, 390), fill=255)
    m.ellipse((276, 260, 442, 390), fill=255)
    def det(d, o, a):
        d.arc((226, 270, 286, 320), 200, 340, fill=o, width=10)
        d.line((70, 300, 30, 280), fill=o, width=10)
        d.line((442, 300, 482, 280), fill=o, width=10)
        d.ellipse((100, 285, 140, 315), fill=(255, 255, 255))
        d.ellipse((306, 285, 346, 315), fill=(255, 255, 255))
    return det


def watch(m):
    m.rounded_rectangle((210, 90, 302, 550), radius=30, fill=255)
    def det(d, o, a):
        d.ellipse((160, 220, 352, 412), fill=a, outline=o, width=12)
        d.ellipse((186, 246, 326, 386), fill=(250, 250, 250))
        d.line((256, 316, 256, 266), fill=o, width=6)
        d.line((256, 316, 296, 316), fill=o, width=6)
    return det


def jewelry(m):
    m.ellipse((236, 400, 276, 440), fill=255)
    m.polygon([(256, 430), (226, 480), (256, 540), (286, 480)], fill=255)
    return lambda d, o, a: d.arc((120, 60, 392, 440), 20, 160, fill=a, width=10)


def tie(m):
    m.polygon([(232, 110), (280, 110), (270, 156), (304, 470), (256, 540), (208, 470), (242, 156)], fill=255)
    def det(d, o, a):
        d.polygon([(232, 110), (280, 110), (270, 156), (242, 156)], fill=shade(a, -0.1), outline=o)
        for y in range(200, 480, 50):
            d.line((230, y, 290, y + 30), fill=a, width=8)
    return det


SILHOUETTES = {
    "t-shirt": tshirt, "polo": polo, "henley": henley, "casual shirt": shirt, "formal shirt": shirt,
    "sweater": sweater, "sweatshirt": sweater, "cardigan": cardigan, "hoodie": hoodie, "tank top": tank_top,
    "jeans": jeans, "chinos": long_pants, "dress pants": long_pants, "corduroys": long_pants,
    "cargo pants": cargo, "joggers": joggers, "sweatpants": joggers, "leggings": leggings,
    "yoga pants": leggings, "shorts": shorts,
    "casual dress": lambda m: dress(m), "formal dress": lambda m: dress(m, hem=610, flare=140),
    "cocktail dress": lambda m: dress(m, hem=470, flare=90, straps=True),
    "maxi dress": lambda m: dress(m, hem=615, flare=150, straps=True),
    "midi dress": lambda m: dress(m, hem=520, flare=100), "shift dress": lambda m: dress(m, hem=500, flare=40),
    "wrap dress": wrap_dress, "sundress": lambda m: dress(m, hem=500, flare=120, straps=True),
    "shirt dress": shirt_dress, "bodycon": bodycon,
    "sneakers": sneaker, "athletic shoes": sneaker, "boots": boot, "heels": heels, "sandals": sandal,
    "loafers": lambda m: flat_shoe(m, strap=True), "oxfords": lambda m: flat_shoe(m, laces=True),
    "dress shoes": lambda m: flat_shoe(m, laces=True), "flats": flat_shoe, "slip-ons": flat_shoe,
    "jacket": jacket, "blazer": jacket, "denim jacket": jacket, "leather jacket": jacket,
    "windbreaker": lambda m: jacket(m, lapels=False), "coat": coat, "raincoat": raincoat,
    "puffer jacket": puffer, "vest": vest,
    "scarf": scarf, "hat": hat, "belt": belt, "bag": bag, "wallet": wallet, "gloves": gloves,
    "sunglasses": sunglasses, "watch": watch, "jewelry": jewelry, "tie": tie,
}

# ============================================================================
# Material textures (drawn inside the garment mask)
# ============================================================================

def texture(material: str, base, size):
    layer = Image.new("RGB", size, base)
    d = ImageDraw.Draw(layer)
    w, h = size
    dark, light = shade(base, -0.12), shade(base, 0.12)
    material = (material or "").lower()

    if material == "denim":
        for x in range(-h, w, 7):
            d.line((x, 0, x + h, h), fill=dark, width=2)
    elif material in ("wool", "fleece", "acrylic"):
        for y in range(0, h, 14):
            for x in range((y // 14 % 2) * 7, w, 14):
                d.ellipse((x, y, x + 4, y + 4), fill=dark)
    elif material in ("jersey", "knit", "spandex"):
        for x in range(0, w, 12):
            d.line((x, 0, x, h), fill=dark, width=2)
    elif material == "linen":
        for y in range(0, h, 6):
            d.line((0, y, w, y), fill=light, width=1)
    elif material in ("leather", "suede", "silk", "nylon", "polyester", "viscose", "rayon"):
        sheen = Image.new("L", size, 0)
        ImageDraw.Draw(sheen).ellipse((w * 0.25, h * 0.1, w * 0.6, h * 0.55), fill=70 if material != "suede" else 30)
        sheen = sheen.filter(ImageFilter.GaussianBlur(40))
        layer = Image.composite(Image.new("RGB", size, shade(base, 0.35)), layer, sheen)
    return layer


def render(product: dict) -> Image.Image:
    base = color_of(product.get("primary_color"))
    secondaries = product.get("secondary_colors") or []
    accent = color_of(secondaries[0]) if secondaries else shade(base, -0.3)
    if abs(luminance(accent) - luminance(base)) < 0.08:
        accent = shade(base, -0.35) if luminance(base) > 0.4 else shade(base, 0.45)

    outline = shade(base, -0.55) if luminance(base) > 0.25 else shade(base, 0.45)
    bg = mix(base, (255, 255, 255), 0.86) if luminance(base) < 0.85 else (233, 236, 242)

    mask = Image.new("L", (W, H), 0)
    draw_shape = SILHOUETTES.get(product.get("subcategory"), tshirt)
    details = draw_shape(ImageDraw.Draw(mask)) or (lambda d, o, a: None)

    canvas = Image.new("RGB", (W, H), bg)
    # soft drop shadow
    shadow = mask.filter(ImageFilter.GaussianBlur(14))
    canvas.paste(shade(bg, -0.18), (8, 14), shadow)
    canvas.paste(texture(product.get("material"), base, (W, H)), (0, 0), mask)

    # outline = dilated mask minus mask
    ring = ImageChops.subtract(mask.filter(ImageFilter.MaxFilter(7)), mask)
    canvas.paste(outline, (0, 0), ring)

    details(ImageDraw.Draw(canvas), outline, accent)
    return canvas.resize(OUT_SIZE, Image.LANCZOS)


def main(products_file: Path = HERE / "products_700.json") -> int:
    products = json.loads(products_file.read_text(encoding="utf-8"))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    keep = set()
    for product in products:
        name = f"{product['id']}.png"
        render(product).save(OUT_DIR / name, optimize=True)
        keep.add(name)
    for stale in OUT_DIR.glob("*.png"):
        if stale.name not in keep:
            stale.unlink()
    return len(keep)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    count = main()
    print(f"✅ Generated {count} product images in {OUT_DIR}")
