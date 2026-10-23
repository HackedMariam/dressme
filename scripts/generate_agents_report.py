"""Generate the DressMe agent report assets and PowerPoint deck.

Run from the repository root:

    python scripts/generate_agents_report.py

The script is deterministic: it draws the pipeline diagrams with Pillow and
builds the 16:9 deck with python-pptx. It does not call any external service.
"""

from __future__ import annotations

import math
import os
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs" / "agents-report-assets"
DECK_PATH = ROOT / "docs" / "agent-report.pptx"

# ---------------------------------------------------------------------------
# Palette and typography
# ---------------------------------------------------------------------------
BG = "#FFFDF9"
INK = "#1A1A1A"
MUTED = "#6F6961"
SOFT = "#F3EEE7"
CARD = "#FAF7F2"
LINE = "#D8C6AE"
TAN = "#C8B49A"
GREEN = "#4F6B45"
GREEN_SOFT = "#E7EDE2"
TERRA = "#B9785E"
TERRA_SOFT = "#F5E5DE"
WHITE = "#FFFFFF"

GEORGIA = r"C:\Windows\Fonts\georgia.ttf"
GEORGIA_BOLD = r"C:\Windows\Fonts\georgiab.ttf"
GEORGIA_ITALIC = r"C:\Windows\Fonts\georgiai.ttf"
ARIAL = r"C:\Windows\Fonts\arial.ttf"
ARIAL_BOLD = r"C:\Windows\Fonts\arialbd.ttf"


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def text_width(draw: ImageDraw.ImageDraw, text: str, fnt: ImageFont.FreeTypeFont) -> int:
    box = draw.textbbox((0, 0), text, font=fnt)
    return box[2] - box[0]


def wrap(draw: ImageDraw.ImageDraw, text: str, fnt: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if text_width(draw, candidate, fnt) <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def draw_tracking(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    fnt: ImageFont.FreeTypeFont,
    fill: str,
    tracking: int = 4,
) -> int:
    x, y = xy
    for char in text:
        draw.text((x, y), char, font=fnt, fill=fill)
        x += text_width(draw, char, fnt) + tracking
    return x


def rounded_box(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    fill: str,
    outline: str,
    radius: int = 18,
    shadow: bool = True,
) -> None:
    x0, y0, x1, y1 = box
    if shadow:
        draw.rounded_rectangle((x0 + 5, y0 + 7, x1 + 5, y1 + 7), radius=radius, fill="#E9E1D5")
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=2)


def arrow(draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int], color: str, width: int = 4) -> None:
    x0, y0 = start
    x1, y1 = end
    draw.line((x0, y0, x1, y1), fill=color, width=width)
    angle = math.atan2(y1 - y0, x1 - x0)
    size = 15
    left = (x1 - size * math.cos(angle - math.pi / 6), y1 - size * math.sin(angle - math.pi / 6))
    right = (x1 - size * math.cos(angle + math.pi / 6), y1 - size * math.sin(angle + math.pi / 6))
    draw.polygon([ (x1, y1), left, right ], fill=color)


def step_box(
    draw: ImageDraw.ImageDraw,
    number: int,
    title: str,
    body: str,
    box: tuple[int, int, int, int],
    accent: str,
    number_fill: str = GREEN,
    title_size: int = 23,
    body_size: int = 18,
    number_size: int = 20,
    max_lines: int = 4,
) -> None:
    x0, y0, x1, y1 = box
    rounded_box(draw, box, WHITE, LINE)
    draw.rounded_rectangle((x0 + 15, y0 + 15, x0 + 51, y0 + 51), radius=10, fill=number_fill)
    nf = font(ARIAL_BOLD, number_size)
    draw.text((x0 + 25, y0 + 20), f"{number:02d}", font=nf, fill=WHITE)
    tf = font(GEORGIA_BOLD, title_size)
    draw.text((x0 + 64, y0 + 15), title, font=tf, fill=INK)
    bf = font(ARIAL, body_size)
    lines = wrap(draw, body, bf, x1 - x0 - 44)
    y = y0 + 64
    for line in lines[:max_lines]:
        draw.text((x0 + 22, y), line, font=bf, fill=MUTED)
        y += body_size + 5
    draw.line((x0 + 22, y1 - 20, x1 - 22, y1 - 20), fill=accent, width=3)


def header(draw: ImageDraw.ImageDraw, eyebrow: str, title: str, subtitle: str, badge: str) -> None:
    draw.rectangle((0, 0, 1920, 1080), fill=BG)
    draw.rectangle((0, 0, 1920, 10), fill=GREEN)
    draw_tracking(draw, (100, 62), eyebrow.upper(), font(ARIAL_BOLD, 18), GREEN, tracking=5)
    draw.text((100, 105), title, font=font(GEORGIA_BOLD, 58), fill=INK)
    draw.text((100, 183), subtitle, font=font(ARIAL, 22), fill=MUTED)
    # badge
    bf = font(ARIAL_BOLD, 17)
    label = badge.upper()
    w = text_width(draw, label, bf) + 52
    draw.rounded_rectangle((1820 - w, 86, 1820, 130), radius=22, fill=GREEN_SOFT, outline=GREEN, width=2)
    draw.text((1820 - w + 26, 99), label, font=bf, fill=GREEN)
    draw.line((100, 235, 1820, 235), fill=LINE, width=2)


def note_card(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], label: str, value: str, accent: str) -> None:
    x0, y0, x1, y1 = box
    rounded_box(draw, box, SOFT, LINE, shadow=False)
    draw.rectangle((x0, y0 + 14, x0 + 7, y1 - 14), fill=accent)
    draw_tracking(draw, (x0 + 24, y0 + 16), label.upper(), font(ARIAL_BOLD, 15), accent, tracking=3)
    bf = font(ARIAL, 18)
    lines = wrap(draw, value, bf, x1 - x0 - 48)
    y = y0 + 46
    for line in lines[:3]:
        draw.text((x0 + 24, y), line, font=bf, fill=INK)
        y += 24


def footer(draw: ImageDraw.ImageDraw, page: str) -> None:
    draw.line((100, 1022, 1820, 1022), fill=LINE, width=2)
    draw.text((100, 1038), "DressMe | Agent implementation report", font=font(ARIAL, 16), fill=MUTED)
    draw.text((1720, 1038), page, font=font(ARIAL_BOLD, 16), fill=MUTED)


def draw_rag(path: Path) -> None:
    img = Image.new("RGB", (1920, 1080), BG)
    draw = ImageDraw.Draw(img)
    header(
        draw,
        "01 / RAG AI Stylist",
        "From a question to a cited answer",
        "Hybrid retrieval over 14,574 fashion-knowledge chunks, grounded generation, inline citations.",
        "Implemented | rag/try1",
    )

    steps = [
        ("User question", "AI Stylist chat or API client sends a fashion question.", GREEN),
        ("FastAPI boundary", "Validation, optional API key, rate limit, conversation lookup.", GREEN),
        ("Query rewrite", "LLM rewrites vague questions using the last 4 messages.", TERRA),
        ("Embed query", "all-MiniLM-L6-v2 produces a normalized 384-d vector.", TERRA),
        ("Hybrid retrieval", "Vector search + English full-text search, 30 candidates each.", GREEN),
        ("RRF fusion", "Reciprocal Rank Fusion, dedupe, keep top_k = 5.", GREEN),
        ("Context assembly", "Passages labelled [S1]...[Sn], capped at 12,000 chars.", TERRA),
        ("Grounded answer", "GPT-4o answers under strict citation rules.", TERRA),
        ("Citations", "Parse [S1] markers, map to sources, set grounded flag.", GREEN),
        ("Stream to UI", "SSE tokens, sources, done event; localStorage history.", GREEN),
    ]

    w, h, gap, left, top = 300, 170, 55, 100, 290
    boxes = []
    for i in range(5):
        boxes.append((left + i * (w + gap), top, left + i * (w + gap) + w, top + h))
    for i in range(5):
        boxes.append((left + (4 - i) * (w + gap), top + 430, left + (4 - i) * (w + gap) + w, top + 430 + h))

    for i, (title, body, accent) in enumerate(steps):
        step_box(draw, i + 1, title, body, boxes[i], accent, GREEN if accent == GREEN else TERRA)

    # row 1 arrows
    for i in range(4):
        arrow(draw, (boxes[i][2] + 6, top + h // 2), (boxes[i + 1][0] - 6, top + h // 2), TAN)
    # down arrow from 05 to 06
    arrow(draw, (boxes[4][0] + w // 2, top + h + 8), (boxes[5][0] + w // 2, top + 430 - 8), TAN)
    # row 2 arrows right-to-left
    for i in range(5, 9):
        arrow(draw, (boxes[i][0] - 6, top + 430 + h // 2), (boxes[i + 1][2] + 6, top + 430 + h // 2), TAN)

    note_card(draw, (100, 900, 660, 1002), "Knowledge memory", "14,574 chunks | 384-d | pgvector HNSW", GREEN)
    note_card(draw, (700, 900, 1260, 1002), "Conversation memory", "SQLite | last 8 answer / last 4 rewrite | localStorage", TERRA)
    note_card(draw, (1300, 900, 1820, 1002), "Measured retrieval", "Hit@5 91.67% | MRR 85.42% | precision 71.67%", GREEN)
    footer(draw, "01 / 03")
    img.save(path, quality=95)


def draw_avatar(path: Path) -> None:
    img = Image.new("RGB", (1920, 1080), BG)
    draw = ImageDraw.Draw(img)
    header(
        draw,
        "03 / Avatar & Try-On",
        "GPT-4o Vision chooses the body",
        "Primary path: GPT-4o Vision selects MPFB targets; MediaPipe and SciPy are optional refinement.",
        "Implemented | avatar/try1 + working tree",
    )

    primary = [
        ("Photo pair", "Front + side photos + height.", GREEN),
        ("Consent + API", "Validate photos, consent, OpenAI call.", GREEN),
        ("GPT-4o Vision", "Reads both photos; returns targets + details.", TERRA),
        ("Targets + details", "8 MPFB macros + 19 detail controls.", TERRA),
        ("Blender / MPFB2", "Shape body, apply details, bake keys.", GREEN),
        ("Garments + GLB", "Body-derived shells, one dressed GLB.", GREEN),
        ("Three.js preview", "Orbit viewer, metrics, compare, save.", GREEN),
    ]
    w, h, gap, left, top = 240, 170, 25, 45, 290
    boxes = []
    for i in range(7):
        x = left + i * (w + gap)
        boxes.append((x, top, x + w, top + h))
    for i, (title, body, accent) in enumerate(primary):
        step_box(draw, i + 1, title, body, boxes[i], accent, GREEN if accent == GREEN else TERRA,
                 title_size=20, body_size=16, number_size=18, max_lines=4)
        if i < 6:
            arrow(draw, (boxes[i][2] + 4, top + h // 2), (boxes[i + 1][0] - 4, top + h // 2), TAN)

    optional = [
        ("MediaPipe", "Pose + silhouette; local measurements.", TERRA),
        ("SciPy fitting", "Powell search; IoU + profile; 36 evals.", TERRA),
        ("Questionnaire", "Eight-answer local fallback.", GREEN),
    ]
    ow, oh, ogap, oleft, otop = 360, 150, 40, 380, 620
    oboxes = []
    for i in range(3):
        x = oleft + i * (ow + ogap)
        oboxes.append((x, otop, x + ow, otop + oh))
    for i, (title, body, accent) in enumerate(optional):
        step_box(draw, i + 8, title, body, oboxes[i], accent, GREEN if accent == GREEN else TERRA,
                 title_size=21, body_size=16, number_size=18, max_lines=3)
        if i < 2:
            arrow(draw, (oboxes[i][2] + 4, otop + oh // 2), (oboxes[i + 1][0] - 4, otop + oh // 2), TAN)
    # Optional branch feeds back into Targets + details (step 04)
    arrow(draw, (960, otop - 4), (960, top + h + 4), TERRA)
    draw.text((975, otop - 62), "optional refinement", font=font(ARIAL_BOLD, 16), fill=TERRA)

    note_card(draw, (100, 900, 660, 1002), "Tools", "GPT-4o Vision | MediaPipe/SciPy optional | Blender", GREEN)
    note_card(draw, (700, 900, 1260, 1002), "Memory", "Photos in browser | 24 looks | 24 h GLB TTL", TERRA)
    note_card(draw, (1300, 900, 1820, 1002), "Privacy", "Consent-gated OpenAI call | no stored photos", GREEN)
    footer(draw, "03 / 03")
    img.save(path, quality=95)


def draw_trip(path: Path) -> None:
    img = Image.new("RGB", (1920, 1080), BG)
    draw = ImageDraw.Draw(img)
    header(
        draw,
        "02 / Trip Agent",
        "From a trip request to a packing capsule",
        "The LLM orchestrates ten tools; Python and CP-SAT compute the packing result.",
        "Implemented | helpmepack/try1",
    )

    steps = [
        ("User input", "Manual form or free text: destination, dates, activities, dress code, luggage.", GREEN),
        ("FastAPI backend", "POST /api/trips, session lock, Pydantic validation, request logging.", GREEN),
        ("Trip Agent", "System prompt + state summary + last 16 messages + 10 tool schemas.", TERRA),
        ("GPT-4o", "temperature 0, native function calling; chooses the next tool and arguments.", TERRA),
        ("Tool loop", "Pydantic validation, dependency checks, structured errors, max 12 iterations.", GREEN),
        ("State + response", "Trip, weather, requirements, capsule, checklist, suggestions, errors.", GREEN),
        ("UI render", "Weather cards, daily outfits, capsule summary, interactive checklist.", TERRA),
        ("Follow-up", "PATCH checklist without re-optimize; PATCH trip and re-optimize.", GREEN),
    ]

    w, h, gap, left, top = 360, 170, 60, 150, 290
    boxes = []
    for i in range(4):
        boxes.append((left + i * (w + gap), top, left + i * (w + gap) + w, top + h))
    for i in range(4):
        boxes.append((left + (3 - i) * (w + gap), top + 410, left + (3 - i) * (w + gap) + w, top + 410 + h))

    for i, (title, body, accent) in enumerate(steps):
        step_box(draw, i + 1, title, body, boxes[i], accent, GREEN if accent == GREEN else TERRA)

    for i in range(3):
        arrow(draw, (boxes[i][2] + 6, top + h // 2), (boxes[i + 1][0] - 6, top + h // 2), TAN)
    arrow(draw, (boxes[3][0] + w // 2, top + h + 8), (boxes[4][0] + w // 2, top + 410 - 8), TAN)
    for i in range(4, 7):
        arrow(draw, (boxes[i][0] - 6, top + 410 + h // 2), (boxes[i + 1][2] + 6, top + 410 + h // 2), TAN)

    note_card(draw, (100, 900, 660, 1002), "Tools", "10 functions: trip, weather, wardrobe, requirements, optimizer, checklist, updates, gap hook", GREEN)
    note_card(draw, (700, 900, 1260, 1002), "Memory", "AgentState + last 16 messages + in-memory SessionStore + localStorage", TERRA)
    note_card(draw, (1300, 900, 1820, 1002), "Guardrails", "regex fallback, labelled synthetic weather, no silent relaxation", GREEN)
    footer(draw, "02 / 03")
    img.save(path, quality=95)


# ---------------------------------------------------------------------------
# PowerPoint deck
# ---------------------------------------------------------------------------
P_BG = RGBColor(0xFF, 0xFD, 0xF9)
P_INK = RGBColor(0x1A, 0x1A, 0x1A)
P_MUTED = RGBColor(0x6F, 0x69, 0x61)
P_SOFT = RGBColor(0xF3, 0xEE, 0xE7)
P_CARD = RGBColor(0xFA, 0xF7, 0xF2)
P_LINE = RGBColor(0xD8, 0xC6, 0xAE)
P_TAN = RGBColor(0xC8, 0xB4, 0x9A)
P_GREEN = RGBColor(0x4F, 0x6B, 0x45)
P_GREEN_SOFT = RGBColor(0xE7, 0xED, 0xE2)
P_TERRA = RGBColor(0xB9, 0x78, 0x5E)
P_TERRA_SOFT = RGBColor(0xF5, 0xE5, 0xDE)
P_WHITE = RGBColor(0xFF, 0xFF, 0xFF)
BULLET = chr(0x2022)
MIDDOT = chr(0x00B7)


def pfont(run, name: str, size: float, color: RGBColor, bold: bool = False, italic: bool = False) -> None:
    run.font.name = name
    run.font.size = Pt(size)
    run.font.color.rgb = color
    run.font.bold = bold
    run.font.italic = italic


def set_spacing(run, hundredths: int) -> None:
    run.font._element.set("spc", str(hundredths))


def textbox(slide, left: float, top: float, width: float, height: float, align=PP_ALIGN.LEFT, valign=MSO_ANCHOR.TOP):
    box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = 0
    tf.margin_right = 0
    tf.margin_top = 0
    tf.margin_bottom = 0
    tf.vertical_anchor = valign
    tf.paragraphs[0].alignment = align
    return box


def add_text(
    slide,
    text: str,
    left: float,
    top: float,
    width: float,
    height: float,
    *,
    font: str = "Arial",
    size: float = 13,
    color: RGBColor = P_INK,
    bold: bool = False,
    italic: bool = False,
    align=PP_ALIGN.LEFT,
    valign=MSO_ANCHOR.TOP,
    spacing: int | None = None,
):
    box = textbox(slide, left, top, width, height, align, valign)
    p = box.text_frame.paragraphs[0]
    p.text = text
    p.alignment = align
    for run in p.runs:
        pfont(run, font, size, color, bold, italic)
        if spacing is not None:
            set_spacing(run, spacing)
    return box


def add_para(
    slide,
    paras: list[dict],
    left: float,
    top: float,
    width: float,
    height: float,
    *,
    valign=MSO_ANCHOR.TOP,
):
    box = textbox(slide, left, top, width, height, valign=valign)
    tf = box.text_frame
    for index, item in enumerate(paras):
        p = tf.paragraphs[0] if index == 0 else tf.add_paragraph()
        p.alignment = item.get("align", PP_ALIGN.LEFT)
        p.space_after = Pt(item.get("space_after", 4))
        p.space_before = Pt(item.get("space_before", 0))
        p.line_spacing = item.get("line_spacing", 1.0)
        p.level = item.get("level", 0)
        p.text = item["text"]
        for run in p.runs:
            pfont(
                run,
                item.get("font", "Arial"),
                item.get("size", 13),
                item.get("color", P_INK),
                item.get("bold", False),
                item.get("italic", False),
            )
    return box


def add_label(slide, text: str, left: float, top: float, color: RGBColor = P_GREEN, size: float = 9, width: float = 4.0):
    return add_text(
        slide,
        text.upper(),
        left,
        top,
        width,
        0.25,
        font="Arial",
        size=size,
        color=color,
        bold=True,
        spacing=240,
    )


def add_rule(slide, left: float, top: float, width: float, color: RGBColor = P_LINE, height: float = 0.012):
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(left), Inches(top), Inches(width), Inches(height))
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    shape.line.fill.background()
    return shape


def add_rect(slide, left: float, top: float, width: float, height: float, fill: RGBColor, line: RGBColor | None = None, radius: float = 0.06):
    shape = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE, Inches(left), Inches(top), Inches(width), Inches(height)
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill
    if line is None:
        shape.line.fill.background()
    else:
        shape.line.color.rgb = line
        shape.line.width = Pt(0.9)
    try:
        shape.adjustments[0] = radius
    except Exception:
        pass
    return shape


def add_card(
    slide,
    left: float,
    top: float,
    width: float,
    height: float,
    fill: RGBColor = P_WHITE,
    line: RGBColor = P_LINE,
    accent: RGBColor | None = None,
):
    add_rect(slide, left, top, width, height, fill, line)
    if accent is not None:
        add_rect(slide, left + 0.02, top + 0.14, 0.055, height - 0.28, accent, None, radius=0.5)


def add_picture(slide, path: Path, left: float, top: float, width: float, height: float):
    picture = slide.shapes.add_picture(str(path), Inches(left), Inches(top), Inches(width), Inches(height))
    picture.line.color.rgb = P_LINE
    picture.line.width = Pt(0.75)
    return picture


def add_runs(slide, runs: list[tuple[str, bool, RGBColor]], left: float, top: float, width: float, height: float, *, size: float = 9.3):
    box = textbox(slide, left, top, width, height)
    p = box.text_frame.paragraphs[0]
    for text, bold, color in runs:
        run = p.add_run()
        run.text = text
        pfont(run, "Arial", size, color, bold)
    return box


def add_arrow(slide, x1: float, y1: float, x2: float, y2: float, color: RGBColor = P_TAN, width: float = 1.1):
    shape = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    shape.line.color.rgb = color
    shape.line.width = Pt(width)
    ln = shape.line._get_or_add_ln()
    tail = ln.makeelement(qn("a:tailEnd"), {"type": "triangle", "w": "sm", "len": "sm"})
    ln.append(tail)
    return shape


def external_header(slide, title: str, subtitle: str):
    add_text(slide, title, 0.55, 0.58, 11.9, 0.62, font="Georgia", size=28, color=P_INK, bold=True)
    add_text(slide, subtitle, 0.55, 1.2, 11.9, 0.4, size=12.5, color=P_MUTED)
    add_rule(slide, 0.55, 1.72, 12.23)


def add_pill(slide, text: str, left: float, top: float, color: RGBColor = P_GREEN, fill: RGBColor = P_GREEN_SOFT, width: float | None = None):
    label = text.upper()
    width = width or max(1.35, 0.095 * len(label) + 0.42)
    shape = add_rect(slide, left, top, width, 0.32, fill, color, radius=0.45)
    tf = shape.text_frame
    tf.word_wrap = False
    tf.margin_left = 0
    tf.margin_right = 0
    tf.margin_top = 0
    tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    p.text = label
    for run in p.runs:
        pfont(run, "Arial", 8.5, color, True)
        set_spacing(run, 160)
    return shape


def add_footer(slide, label: str, page: int, total: int = 37) -> None:
    add_rule(slide, 0.55, 7.04, 12.23)
    add_text(slide, "DressMe  /  Agent implementation report", 0.55, 7.12, 7.0, 0.22, size=8.5, color=P_MUTED)
    add_text(slide, f"{label}   {page:02d} / {total:02d}", 8.7, 7.12, 4.08, 0.22, size=8.5, color=P_MUTED, align=PP_ALIGN.RIGHT)


def new_slide(prs, page: int, label: str, offset: int = 3, total: int = 37, footer: bool = True):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = P_BG
    add_rect(slide, 0, 0, 13.333, 0.06, P_GREEN, None, radius=0.0)
    if footer:
        add_footer(slide, label, page + offset, total)
    else:
        add_text(slide, str(page), 12.2, 7.12, 0.6, 0.22, size=8.5, color=P_MUTED, align=PP_ALIGN.RIGHT)
    return slide


def content_header(slide, eyebrow: str, title: str, subtitle: str, badge: str | None = None):
    add_label(slide, eyebrow, 0.55, 0.36)
    add_text(slide, title, 0.55, 0.66, 10.6, 0.62, font="Georgia", size=28, color=P_INK, bold=True)
    add_text(slide, subtitle, 0.55, 1.28, 10.9, 0.4, size=12.5, color=P_MUTED)
    add_rule(slide, 0.55, 1.8, 12.23)
    if badge:
        add_pill(slide, badge, 11.05, 0.63, P_GREEN, P_GREEN_SOFT, 1.72)


def speaker_notes(slide, text: str) -> None:
    slide.notes_slide.notes_text_frame.text = text


def section_divider(prs, page: int, number: str, title: str, subtitle: str, branch: str, metrics: list[tuple[str, str]], offset: int = 3, total: int = 37):
    slide = new_slide(prs, page, f"SECTION {number}", offset=offset, total=total)
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = P_SOFT
    add_text(slide, number, 8.35, 0.7, 4.3, 2.4, font="Georgia", size=180, color=RGBColor(0xE8, 0xDC, 0xCA), bold=True, align=PP_ALIGN.RIGHT)
    add_rule(slide, 8.05, 1.0, 0.012, P_LINE, 3.2)
    add_label(slide, f"Section {number}", 0.62, 2.15, P_GREEN)
    add_text(slide, title, 0.62, 2.45, 11.8, 0.8, font="Georgia", size=42, color=P_INK, bold=True)
    add_text(slide, subtitle, 0.62, 3.38, 10.8, 0.55, size=15, color=P_MUTED)
    add_pill(slide, branch, 0.62, 4.18, P_GREEN, P_GREEN_SOFT, max(2.1, 0.1 * len(branch)))
    x = 0.62
    for value, label in metrics:
        add_card(slide, x, 5.22, 3.7, 1.05, P_WHITE, P_LINE, P_GREEN if "hit" in label.lower() else P_TERRA)
        add_text(slide, value, x + 0.2, 5.36, 3.25, 0.4, font="Georgia", size=23, color=P_INK, bold=True)
        add_text(slide, label, x + 0.2, 5.84, 3.25, 0.25, size=8.5, color=P_MUTED)
        x += 4.0
    return slide


def add_table(slide, rows: list[list[str]], left: float, top: float, width: float, col_widths: list[float], row_height: float, header: bool = True, font_size: float = 9.5):
    table_shape = slide.shapes.add_table(len(rows), len(rows[0]), Inches(left), Inches(top), Inches(width), Inches(row_height * len(rows)))
    table = table_shape.table
    table.first_row = False
    table.horz_banding = False
    for index, width_in in enumerate(col_widths):
        table.columns[index].width = Inches(width_in)
    for r_index, row in enumerate(rows):
        table.rows[r_index].height = Inches(row_height)
        for c_index, value in enumerate(row):
            cell = table.cell(r_index, c_index)
            cell.margin_left = Inches(0.08)
            cell.margin_right = Inches(0.06)
            cell.margin_top = Inches(0.03)
            cell.margin_bottom = Inches(0.03)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.fill.solid()
            if header and r_index == 0:
                cell.fill.fore_color.rgb = P_GREEN
            else:
                cell.fill.fore_color.rgb = P_WHITE if r_index % 2 == 1 else P_CARD
            tf = cell.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            p.text = value
            p.space_after = Pt(0)
            for run in p.runs:
                pfont(run, "Arial", font_size, P_WHITE if header and r_index == 0 else P_INK, header and r_index == 0)
    return table


def build_llm_agents_slides(prs) -> None:
    # Slide 1 - LLM agents: the model and its memory
    slide = new_slide(prs, 1, "LLM AGENTS", offset=0, footer=False)
    external_header(slide, "LLM agents: the model and its memory", "My part of DressMe: the LLM that powers the agents, and how it remembers")
    add_text(slide, "The LLM: OpenAI GPT-4o", 0.55, 1.95, 5.9, 0.3, font="Georgia", size=15, color=P_INK, bold=True)
    llm_cards = [
        ("Sees images", "judges pattern, material and style", P_TERRA),
        ("Calls tools", "decides when to search the wardrobe", P_GREEN),
        ("Strict JSON", "always answers in a fixed format", P_GREEN),
        ("Easy to switch", "gpt-4o-mini with one variable", P_TAN),
    ]
    positions = [(0.55, 2.4), (3.55, 2.4), (0.55, 3.95), (3.55, 3.95)]
    for (title, body, accent), (x, y) in zip(llm_cards, positions):
        add_card(slide, x, y, 2.85, 1.35, P_WHITE, P_LINE, accent)
        add_text(slide, title, x + 0.22, y + 0.2, 2.45, 0.28, font="Georgia", size=13, color=P_INK, bold=True)
        add_text(slide, body, x + 0.22, y + 0.6, 2.45, 0.55, size=9.5, color=P_MUTED)
    stats = [("2", "agents", P_GREEN), ("1", "tool", P_TERRA), ("4", "max rounds", P_TAN)]
    for index, (number, label, accent) in enumerate(stats):
        x = 0.55 + index * 2.0
        add_card(slide, x, 5.65, 1.85, 1.15, P_WHITE, P_LINE, accent)
        add_text(slide, number, x + 0.2, 5.8, 1.45, 0.4, font="Georgia", size=28, color=accent, bold=True)
        add_text(slide, label, x + 0.2, 6.3, 1.45, 0.25, size=9.5, color=P_MUTED)

    add_text(slide, "Memory: how the agent remembers", 6.95, 1.95, 5.8, 0.3, font="Georgia", size=15, color=P_INK, bold=True)
    memory = [
        ("Feedback", "user corrections, used to measure accuracy", P_TERRA),
        ("Long-term", "the user's wardrobe in Supabase", P_GREEN),
        ("Short-term", "messages of one question (max 4 rounds)", P_TAN),
    ]
    for index, (title, body, accent) in enumerate(memory):
        x = 6.95 + index * 2.0
        add_card(slide, x, 2.4, 1.8, 1.5, P_WHITE, P_LINE, accent)
        add_text(slide, title, x + 0.18, 2.58, 1.45, 0.28, font="Georgia", size=11.5, color=P_INK, bold=True)
        add_text(slide, body, x + 0.18, 2.95, 1.45, 0.8, size=8.5, color=P_MUTED)
        if index < 2:
            add_arrow(slide, x + 1.82, 3.15, x + 1.98, 3.15, P_TAN, 1.0)
    add_text(slide, "No chat history: each question starts fresh from the stored wardrobe.", 6.95, 4.05, 5.8, 0.3, size=9.5, color=P_MUTED, italic=True)
    add_text(slide, "GPT-4o temperature per task (low = stable answers)", 6.95, 4.55, 5.8, 0.3, size=11.5, color=P_INK, bold=True)
    # Small horizontal bar chart
    add_rule(slide, 7.25, 6.12, 4.4, P_LINE, 0.01)
    add_text(slide, "0", 7.2, 6.2, 0.3, 0.2, size=8, color=P_MUTED)
    for i, value in enumerate(["0.1", "0.2", "0.3", "0.4"]):
        add_text(slide, value, 8.3 + i * 1.1, 6.2, 0.4, 0.2, size=8, color=P_MUTED)
    chart = [("3.0", 0.3, 4.9), ("2.0", 0.2, 5.3), ("1.0", 0.1, 5.7)]
    for label, value, y in chart:
        add_text(slide, label, 6.7, y + 0.02, 0.45, 0.2, size=8.5, color=P_MUTED, align=PP_ALIGN.RIGHT)
        width = 4.4 * (value / 0.4)
        add_rect(slide, 7.25, y, width, 0.25, P_TERRA, None, radius=0.04)
        add_text(slide, f"{value:.1f}", 7.25 + width - 0.4, y + 0.035, 0.35, 0.18, size=7.5, color=P_WHITE, bold=True)
    speaker_notes(slide, "This slide introduces the LLM and its memory model: GPT-4o, 2 agents, 1 tool, 4 max rounds.")

    # Slide 2 - Actions and tools: the two agents
    slide = new_slide(prs, 2, "LLM AGENTS", offset=0, footer=False)
    external_header(slide, "Actions and tools: the two agents", "Each agent uses GPT-4o plus one tool, search_wardrobe, on the stored wardrobe")
    top = [
        ("Input", "photo or camera", P_GREEN),
        ("Detect", "YOLO finds the item", P_TERRA),
        ("Colour", "measured from pixels", P_TAN),
        ("GPT-4o", "adds style, season...", P_GREEN),
        ("Wardrobe", "saved per user", P_TERRA),
    ]
    for index, (title, body, accent) in enumerate(top):
        x = 0.55 + index * 2.55
        add_card(slide, x, 1.95, 2.35, 0.95, P_WHITE, P_LINE, accent)
        add_text(slide, title, x + 0.18, 2.07, 1.95, 0.26, font="Georgia", size=11.5, color=P_INK, bold=True)
        add_text(slide, body, x + 0.18, 2.42, 1.95, 0.3, size=8.5, color=P_MUTED)
        if index < 4:
            add_arrow(slide, x + 2.38, 2.42, x + 2.52, 2.42, P_TAN, 1.0)
    add_text(slide, f"Tools used: search_wardrobe (Python)  {MIDDOT}  OpenAI API  {MIDDOT}  Supabase  {MIDDOT}  FastAPI + React", 0.55, 3.08, 12.2, 0.3, size=9, color=P_MUTED, italic=True, align=PP_ALIGN.CENTER)

    # Agent 1 panel
    add_rect(slide, 0.55, 3.55, 6.0, 3.2, P_SOFT, P_LINE)
    add_text(slide, "Agent 1: Stylist", 0.8, 3.72, 5.4, 0.3, font="Georgia", size=15, color=P_TERRA, bold=True)
    add_text(slide, "Answers questions with the user's real clothes", 0.8, 4.02, 5.4, 0.3, size=10.5, color=P_INK)
    for index, (title, body) in enumerate([("Question", "warm jacket?"), ("GPT-4o", "picks filters"), ("Answer", "+ matching items")]):
        x = 0.8 + index * 1.8
        add_card(slide, x, 4.45, 1.55, 0.8, P_WHITE, P_LINE, P_GREEN if index == 1 else P_TAN)
        add_text(slide, title, x + 0.14, 4.57, 1.25, 0.24, font="Georgia", size=10.5, color=P_INK, bold=True)
        add_text(slide, body, x + 0.14, 4.87, 1.25, 0.25, size=8.2, color=P_MUTED)
        if index < 2:
            add_arrow(slide, x + 1.57, 4.85, x + 1.73, 4.85, P_TAN, 1.0)
    add_card(slide, 2.6, 5.65, 1.55, 0.8, P_WHITE, P_LINE, P_GREEN)
    add_text(slide, "search_wardrobe", 2.73, 5.75, 1.3, 0.24, font="Georgia", size=9.8, color=P_INK, bold=True)
    add_text(slide, "finds items", 2.73, 6.03, 1.3, 0.22, size=8.2, color=P_MUTED)
    add_arrow(slide, 3.12, 5.27, 3.12, 5.63, P_TERRA, 1.0)
    add_arrow(slide, 3.58, 5.63, 3.58, 5.27, P_GREEN, 1.0)
    add_text(slide, "filters", 2.55, 5.35, 0.55, 0.2, size=8, color=P_MUTED)
    add_text(slide, "results", 3.7, 5.35, 0.6, 0.2, size=8, color=P_MUTED)
    add_text(slide, "Searches again if needed (max 4 times)", 0.8, 5.45, 1.6, 0.7, size=9.3, color=P_MUTED)
    add_text(slide, "Stops when it has a good answer", 4.4, 5.45, 1.6, 0.7, size=9.3, color=P_MUTED)

    # Agent 2 panel
    add_rect(slide, 6.78, 3.55, 6.0, 3.2, P_SOFT, P_LINE)
    add_text(slide, "Agent 2: Duplicate guard", 7.03, 3.72, 5.4, 0.3, font="Georgia", size=15, color=P_GREEN, bold=True)
    add_text(slide, "Stops the same item from being saved twice", 7.03, 4.02, 5.4, 0.3, size=10.5, color=P_INK)
    for index, (title, body) in enumerate([("Live scan", "camera + YOLO"), ("Stable?", "held 1.4 s"), ("Already owned?", "GPT-4o + search")]):
        x = 7.0 + index * 1.8
        add_card(slide, x, 4.45, 1.55, 0.8, P_WHITE, P_LINE, P_TERRA if index == 2 else P_TAN)
        add_text(slide, title, x + 0.14, 4.57, 1.25, 0.24, font="Georgia", size=10, color=P_INK, bold=True)
        add_text(slide, body, x + 0.14, 4.87, 1.25, 0.25, size=8.2, color=P_MUTED)
        if index < 2:
            add_arrow(slide, x + 1.57, 4.85, x + 1.73, 4.85, P_TAN, 1.0)
    add_card(slide, 8.8, 5.65, 1.55, 0.8, P_WHITE, P_LINE, P_TERRA)
    add_text(slide, "Not added", 8.94, 5.75, 1.25, 0.24, font="Georgia", size=10.5, color=P_INK, bold=True)
    add_text(slide, "duplicate", 8.94, 6.03, 1.25, 0.22, size=8.2, color=P_MUTED)
    add_card(slide, 10.6, 5.65, 1.55, 0.8, P_WHITE, P_LINE, P_GREEN)
    add_text(slide, "Saved", 10.74, 5.75, 1.25, 0.24, font="Georgia", size=10.5, color=P_INK, bold=True)
    add_text(slide, "new item", 10.74, 6.03, 1.25, 0.22, size=8.2, color=P_MUTED)
    add_arrow(slide, 11.3, 5.27, 9.6, 5.63, P_TERRA, 1.0)
    add_arrow(slide, 11.45, 5.27, 11.45, 5.63, P_GREEN, 1.0)
    add_text(slide, "yes", 9.85, 5.33, 0.4, 0.2, size=8, color=P_MUTED)
    add_text(slide, "no", 11.55, 5.33, 0.4, 0.2, size=8, color=P_MUTED)
    add_text(slide, "Checks before saving. A similar item is still allowed.", 7.03, 5.38, 1.6, 0.8, size=9.3, color=P_MUTED)
    speaker_notes(slide, "Two agents share the same GPT-4o plus search_wardrobe tool: the Stylist and the Duplicate guard.")

    # Slide 3 - AI techniques and safeguards
    slide = new_slide(prs, 3, "LLM AGENTS", offset=0, footer=False)
    external_header(slide, "AI techniques and safeguards", "What makes the agents smart, and what keeps them safe")
    center = (4.1, 4.35)
    techniques = [
        ("Fine-tuned vision", "YOLO trained on 20 clothing classes", 0.58, 2.12, P_TERRA),
        ("Agentic RAG", "searches real data, then answers", 4.98, 2.12, P_GREEN),
        ("Tool-using agents", "plan, search, check, adjust", 0.48, 3.82, P_TAN),
        ("Smart prompting", "clear rules and fixed word lists", 5.08, 3.82, P_TERRA),
        ("Structured outputs", "JSON checked before saving", 0.58, 5.52, P_TERRA),
        ("Human in the loop", "users can fix mistakes", 4.98, 5.52, P_GREEN),
    ]
    for title, body, x, y, accent in techniques:
        add_arrow(slide, center[0], center[1], x + 1.325, y + 0.525, P_LINE, 0.9)
    for title, body, x, y, accent in techniques:
        add_card(slide, x, y, 2.65, 1.05, P_WHITE, P_LINE, accent)
        add_text(slide, title, x + 0.2, y + 0.16, 2.25, 0.26, font="Georgia", size=11.5, color=P_INK, bold=True)
        add_text(slide, body, x + 0.2, y + 0.5, 2.25, 0.45, size=8.8, color=P_MUTED)
    circle = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(3.25), Inches(3.5), Inches(1.7), Inches(1.7))
    circle.fill.solid()
    circle.fill.fore_color.rgb = P_GREEN
    circle.line.fill.background()
    tf = circle.text_frame
    tf.word_wrap = True
    tf.margin_left = 0
    tf.margin_right = 0
    tf.margin_top = 0
    tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    p.text = "LLM"
    for run in p.runs:
        pfont(run, "Georgia", 15, P_WHITE, True)
    p2 = tf.add_paragraph()
    p2.alignment = PP_ALIGN.CENTER
    p2.text = "agents"
    for run in p2.runs:
        pfont(run, "Arial", 10, P_WHITE, False)

    add_text(slide, "Safeguards", 8.15, 1.95, 4.6, 0.3, font="Georgia", size=15, color=P_INK, bold=True)
    safeguards = [
        ("Limited loops: ", "max 4 tool rounds, no runaway cost"),
        ("Real answers only: ", "uses the user's own items"),
        ("Checked data: ", "invalid values are rejected"),
        ("Safe fallback: ", "simple rules if GPT-4o fails"),
        ("Private data: ", "each user sees only their items"),
        ("No duplicates: ", "checked before saving"),
    ]
    for index, (label, detail) in enumerate(safeguards):
        y = 2.42 + index * 0.72
        add_rect(slide, 8.15, y, 4.6, 0.6, P_SOFT, P_LINE)
        check = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(8.28), Inches(y + 0.14), Inches(0.3), Inches(0.3))
        check.fill.solid()
        check.fill.fore_color.rgb = P_GREEN
        check.line.fill.background()
        ctf = check.text_frame
        ctf.margin_left = 0
        ctf.margin_right = 0
        ctf.margin_top = 0
        ctf.margin_bottom = 0
        ctf.vertical_anchor = MSO_ANCHOR.MIDDLE
        cp = ctf.paragraphs[0]
        cp.alignment = PP_ALIGN.CENTER
        cp.text = chr(0x2713)
        for run in cp.runs:
            pfont(run, "Arial", 9.5, P_WHITE, True)
        add_runs(slide, [(label, True, P_INK), (detail, False, P_MUTED)], 8.7, y + 0.11, 3.9, 0.4, size=9.2)
    speaker_notes(slide, "Six techniques around the LLM, and six safeguards that bound cost, accuracy, and privacy.")

def build_purchasing_slides(prs) -> None:
    # Divider - page 31
    section_divider(
        prs, 1, "04", "Smart Purchasing Assistant",
        "Should I buy this? Qwen 2.5 3B, YOLOv8, CIEDE2000, and XGBoost arbitration.",
        "Appendix  /  DressMe_Fashion_Assistant_Presentation.docx",
        [("3B", "Qwen 2.5 parameters"), ("9", "agent actions"), ("7", "tools + engines")],
        offset=30, total=37,
    )

    # LLM - page 32
    slide = new_slide(prs, 2, "SMART PURCHASING", offset=30, total=37)
    content_header(slide, "04 / SMART PURCHASING", "The LLM: Qwen 2.5 3B Instruct", "Fine-tuned with 4-bit QLoRA and hosted in Hugging Face.", "LLM USED")
    add_text(slide, "Why this model", 0.62, 2.0, 5.8, 0.3, font="Georgia", size=16, color=P_INK, bold=True)
    add_para(slide, [
        {"text": f"{BULLET}  Exceptional instruction and strict JSON compliance.", "size": 11.2, "space_after": 8},
        {"text": f"{BULLET}  4-bit NF4: ~2.1 GB VRAM, efficient on edge and GPU.", "size": 11.2, "space_after": 8},
        {"text": f"{BULLET}  3B capacity for fashion knowledge, trade-off reasoning, and hard constraints.", "size": 11.2, "space_after": 8},
        {"text": f"{BULLET}  Fine-tuned on 1,200 curated fashion deliberation scenarios.", "size": 11.2, "space_after": 8},
        {"text": f"{BULLET}  Hosted in Hugging Face; no catastrophic forgetting in the setup.", "size": 11.2, "space_after": 8},
    ], 0.62, 2.42, 6.0, 2.8)
    add_card(slide, 7.05, 1.98, 5.5, 3.55, P_WHITE, P_LINE, P_TERRA)
    add_label(slide, "Model card", 7.32, 2.16, P_TERRA, 8.5)
    rows = [
        ["Field", "Value"],
        ["Model", "Qwen/Qwen2.5-3B-Instruct"],
        ["Method", "4-bit QLoRA"],
        ["Precision", "4-bit NF4"],
        ["VRAM", "~2.1 GB"],
        ["Hosting", "Hugging Face"],
        ["Training", "PEFT + TRL, 1,200 scenarios"],
        ["Role", "Purchase verdict reasoning"],
    ]
    add_table(slide, rows, 7.32, 2.48, 4.95, [1.35, 3.6], 0.37, font_size=8.5)
    add_card(slide, 0.62, 5.72, 11.93, 0.92, P_GREEN_SOFT, P_GREEN, P_GREEN)
    add_text(slide, "The 3B model is the reasoning layer; YOLOv8, CIEDE2000, and XGBoost provide grounded observations.", 0.86, 5.9, 11.5, 0.55, size=10.5, color=P_INK)
    speaker_notes(slide, "Qwen 2.5 3B is fine-tuned with 4-bit QLoRA and hosted in Hugging Face; it is the reasoning layer.")

    # Memory - page 33
    slide = new_slide(prs, 3, "SMART PURCHASING", offset=30, total=37)
    content_header(slide, "04 / SMART PURCHASING", "Three tiers of memory", "Scratchpad state, session checkpoints, and the authoritative wardrobe.", "MEMORY")
    tiers = [
        ("Tier 1", "Working in-context memory", "Scratchpad", "Ephemeral active evaluation turn: candidate image features, user budget, and every executed tool result (redundancy, gaps, outfits, ML predictions).", P_GREEN),
        ("Tier 2", "Episodic session memory", "Checkpoints", "JSON session checkpoints in data/checkpoints/ (e.g. sess_0082e4a2.json); tracks recent shopping history across a browsing session.", P_TERRA),
        ("Tier 3", "Long-term wardrobe knowledge", "50 real items", "The user's wardrobe: item_id, category, item_type, color, style, season, warmth, versatility, formality, cleanliness.", P_GREEN),
    ]
    for index, (tier, title, big, body, accent) in enumerate(tiers):
        x = 0.55 + index * 3.95
        add_card(slide, x, 1.98, 3.75, 3.55, P_WHITE, P_LINE, accent)
        add_label(slide, tier, x + 0.22, 2.16, accent, 8.5, 2.5)
        add_text(slide, title, x + 0.22, 2.55, 3.3, 0.62, font="Georgia", size=13.5, color=P_INK, bold=True)
        add_text(slide, big, x + 0.22, 3.2, 3.3, 0.3, size=10.5, color=accent, bold=True)
        add_text(slide, body, x + 0.22, 3.56, 3.3, 1.8, size=9.3, color=P_MUTED)
    add_text(slide, "Tier 3 is the authoritative knowledge base for every duplicate and outfit calculation.", 0.62, 5.85, 11.9, 0.3, size=10.2, color=P_INK, italic=True)
    speaker_notes(slide, "Memory combines an in-context scratchpad, JSON session checkpoints, and the 50-item wardrobe knowledge base.")

    # Actions - page 34
    slide = new_slide(prs, 4, "SMART PURCHASING", offset=30, total=37)
    content_header(slide, "04 / SMART PURCHASING", "Nine autonomous actions", "From image ingestion to multi-model deliberation.", "ACTIONS")
    actions = [
        ("Multi-modal ingestion & URL fetching", "Downloads garment images from URLs or local paths."),
        ("Zero-shot NLP intent & occasion parsing", "Extracts occasion and style preferences from prompts."),
        ("Foreground segmentation & colour extraction", "YOLOv8 polygon masks; background-free median RGB."),
        ("Perceptual colour physics normalization", "RGB -> CIELAB D65; CIEDE2000 against textile shades."),
        ("Wardrobe duplicate & redundancy auditing", "Finds similar items; functional + perceptual redundancy."),
        ("Combinatorial outfit assembly", "Builds valid outfits with owned item IDs."),
        ("Closet gap & underrepresentation analysis", "Scores missing categories and colour diversification."),
        ("Dynamic financial overage penalization", "Penalty when price exceeds the declared budget."),
        ("Multi-model decision deliberation", "Arbitrates XGBoost, deterministic score, and LLM."),
    ]
    for index, (title, body) in enumerate(actions):
        col = index % 3
        row = index // 3
        x = 0.55 + col * 3.95
        y = 1.95 + row * 1.5
        add_card(slide, x, y, 3.75, 1.35, P_WHITE, P_LINE, P_GREEN if index % 2 == 0 else P_TERRA)
        add_text(slide, f"{index + 1:02d}", x + 0.18, y + 0.12, 0.4, 0.25, size=9, color=P_TAN, bold=True)
        add_text(slide, title, x + 0.55, y + 0.1, 3.0, 0.52, font="Georgia", size=10.2, color=P_INK, bold=True)
        add_text(slide, body, x + 0.55, y + 0.66, 3.0, 0.55, size=8.3, color=P_MUTED)
    add_text(slide, "The nine actions feed the same validated downstream JSON contract.", 0.62, 6.45, 11.9, 0.3, size=9.5, color=P_MUTED, italic=True)
    speaker_notes(slide, "Nine discrete actions cover ingestion, language, vision, colour science, wardrobe retrieval, combinatorics, gaps, budget, and deliberation.")

    # Tools - page 35
    slide = new_slide(prs, 5, "SMART PURCHASING", offset=30, total=37)
    content_header(slide, "04 / SMART PURCHASING", "Tools, APIs, and internal engines", "Five specialized domain tools plus two internal ML/CV engines.", "TOOLS")
    rows = [
        ["Tool / Resource", "Implementation", "Role & function"],
        ["analyze_item (YOLOv8)", "vision_model.py / dressme_best.pt", "Instance segmentation across 20 clothing classes; polygon masks remove background."],
        ["Color Similarity Engine", "color_similarity.py / data/colors.json", "sRGB -> CIEXYZ -> CIELAB D65; CIEDE2000 vs 30+ colors; Delta E -> similarity."],
        ["find_similar_items", "tools.py / wardrobe.csv", "RAG over wardrobe; category, color, subtype; redundancy % + duplicate flags."],
        ["check_outfit_compatibility", "tools.py / wardrobe.csv", "Builds outfits with owned tops, bottoms, footwear; returns item IDs."],
        ["analyze_wardrobe_gaps", "tools.py / wardrobe.csv", "Essential gap 90; color diversification 75; redundant duplicate 10."],
        ["predict_purchase_ml (XGBoost)", "ml_model.py / xgb_purchase_model.json", "6D feature vector -> BUY / CONSIDER / SKIP probabilities."],
        ["calculate_purchase_value", "tools.py / deterministic formula", "S = 0.30*O + 0.20*G + 0.20*V + 0.15*P + 0.15*(100-R) - penalty; R >= 85% caps <=40 and forces SKIP."],
    ]
    add_table(slide, rows, 0.62, 1.92, 12.05, [2.45, 3.2, 6.4], 0.56, font_size=7.7)
    add_text(slide, "The LLM never invents these observations; it deliberates over their validated outputs.", 0.62, 6.58, 11.9, 0.25, size=9.3, color=P_MUTED, italic=True)
    speaker_notes(slide, "Seven tools and engines produce the grounded observations used by the LLM and the deterministic formula.")

    # Pipeline - page 36
    slide = new_slide(prs, 6, "SMART PURCHASING", offset=30, total=37)
    content_header(slide, "04 / SMART PURCHASING", "The complete agent pipeline", "Five sequential stages from input to validated downstream JSON.", "PIPELINE")
    stages = [
        ("Ingestion & intent extraction", "image_path, price, budget, user_prompt; auto-downloader -> NLP intent parser infers occasion."),
        ("Computer vision & colour physics", "YOLOv8 category + polygon mask; img_np[mask > 0.5] -> CIELAB D65 -> CIEDE2000."),
        ("Wardrobe retrieval & combinatorics", "find_similar_items + check_outfit_compatibility + analyze_wardrobe_gaps; budget penalty min(25, (price-budget)/budget*20)."),
        ("Statistical & deterministic arbitration", "XGBoost BUY / CONSIDER / SKIP probabilities + weighted 0-100 score + duplicate cap."),
        ("Reasoning & JSON generation", "Fine-tuned Qwen 2.5 3B deliberates over observations; emits validated downstream JSON."),
    ]
    for index, (title, body) in enumerate(stages):
        y = 1.95 + index * 0.98
        add_card(slide, 0.62, y, 12.05, 0.82, P_WHITE, P_LINE, P_GREEN if index % 2 == 0 else P_TERRA)
        circle = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(0.78), Inches(y + 0.18), Inches(0.4), Inches(0.4))
        circle.fill.solid()
        circle.fill.fore_color.rgb = P_GREEN if index % 2 == 0 else P_TERRA
        circle.line.fill.background()
        ctf = circle.text_frame
        ctf.margin_left = 0
        ctf.margin_right = 0
        ctf.margin_top = 0
        ctf.margin_bottom = 0
        ctf.vertical_anchor = MSO_ANCHOR.MIDDLE
        cp = ctf.paragraphs[0]
        cp.alignment = PP_ALIGN.CENTER
        cp.text = str(index + 1)
        for run in cp.runs:
            pfont(run, "Arial", 9, P_WHITE, True)
        add_text(slide, title, 1.35, y + 0.12, 3.2, 0.28, font="Georgia", size=11.5, color=P_INK, bold=True)
        add_text(slide, body, 4.65, y + 0.14, 7.75, 0.55, size=8.6, color=P_MUTED)
        if index < 4:
            add_arrow(slide, 0.98, y + 0.82, 0.98, y + 0.96, P_TAN, 1.0)
    speaker_notes(slide, "The five stages mirror the source pipeline: ingestion, vision and colour, retrieval and combinatorics, arbitration, then reasoning and JSON.")

    # AI techniques - page 37
    slide = new_slide(prs, 7, "SMART PURCHASING", offset=30, total=37)
    content_header(slide, "04 / SMART PURCHASING", "AI techniques and guardrails", "Five techniques turn observations into an auditable purchase verdict.", "AI TECHNIQUES")
    top = [
        ("4-bit QLoRA", "Qwen 2.5 3B on Kaggle GPUs; 1,200 scenarios; PEFT/TRL; r=16, alpha=32; q/k/v/o/gate/up/down; NF4."),
        ("YOLOv8 segmentation", "dressme_best.pt; pixel-accurate polygon masks; filters background and skin."),
        ("CIEDE2000 colour science", "RGB -> CIELAB; Sharma-Wu-Dalal; White/Ivory 89%; White/Camel 31%."),
        ("XGBoost classifier", "xgb_purchase_model.json; BUY / CONSIDER / SKIP probabilities."),
    ]
    for index, (title, body) in enumerate(top):
        col = index % 2
        row = index // 2
        x = 0.62 + col * 6.1
        y = 1.95 + row * 1.55
        add_card(slide, x, y, 5.9, 1.35, P_WHITE, P_LINE, P_GREEN if index % 2 == 0 else P_TERRA)
        add_text(slide, title, x + 0.22, y + 0.15, 5.4, 0.28, font="Georgia", size=12.5, color=P_INK, bold=True)
        add_text(slide, body, x + 0.22, y + 0.55, 5.4, 0.7, size=8.7, color=P_MUTED)
    add_card(slide, 0.62, 5.12, 12.05, 1.2, P_GREEN_SOFT, P_GREEN, P_GREEN)
    add_text(slide, "Advanced prompting + guardrails", 0.86, 5.28, 4.2, 0.28, font="Georgia", size=12.5, color=P_INK, bold=True)
    add_text(slide, "Role conditioning, structured observation injection, and hard constraints: redundancy >= 85% caps the score at <=40 and forces SKIP regardless of LLM sentiment.", 0.86, 5.65, 11.5, 0.5, size=8.8, color=P_INK)
    add_text(slide, "Five techniques, one auditable decision pipeline.", 0.62, 6.55, 11.9, 0.25, size=9.3, color=P_MUTED, italic=True)
    speaker_notes(slide, "QLoRA, YOLOv8, CIEDE2000, XGBoost, and hard-constrained prompting form the purchasing prototype.")

def build_deck() -> None:
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    total = 37

    build_llm_agents_slides(prs)

    # 01 — Cover
    slide = new_slide(prs, 1, "COVER")
    add_label(slide, "Advanced Data Science Project", 0.62, 0.72, P_GREEN, 9)
    add_text(slide, "DressMe", 0.6, 1.15, 8.0, 1.0, font="Georgia", size=58, color=P_INK, bold=True)
    add_text(slide, "Three implemented agents.\nThree different kinds of intelligence.", 0.62, 2.2, 7.4, 1.0, font="Georgia", size=25, color=P_INK)
    add_text(slide, "A technical report on the RAG AI Stylist, the Help Me Pack Trip Agent,\nand the Avatar & Try-On pipeline.", 0.62, 3.62, 7.2, 0.8, size=13.5, color=P_MUTED)
    add_pill(slide, "Supervisor: Jihene Jebri", 0.62, 4.72, P_GREEN, P_GREEN_SOFT, 2.4)
    add_text(slide, "October 2026", 0.62, 5.2, 3.0, 0.3, size=10, color=P_MUTED)
    # right index
    add_rule(slide, 8.55, 1.25, 0.012, P_LINE, 5.3)
    for i, (num, title, sub) in enumerate([
        ("01", "RAG AI Stylist", "Grounded fashion knowledge"),
        ("02", "Trip Agent", "Help Me Pack planning"),
        ("03", "Avatar & Try-On", "Body-aware visual try-on"),
    ]):
        y = 1.45 + i * 1.55
        add_text(slide, num, 8.9, y, 0.8, 0.4, font="Georgia", size=18, color=P_TAN, bold=True)
        add_text(slide, title, 9.55, y - 0.02, 3.25, 0.35, font="Georgia", size=16, color=P_INK, bold=True)
        add_text(slide, sub, 9.55, y + 0.32, 3.25, 0.3, size=10, color=P_MUTED)
    add_text(slide, "Branches: rag/try1 · helpmepack/try1 · avatar/try1 + current working tree", 0.62, 6.55, 8.0, 0.3, size=8.5, color=P_MUTED)
    speaker_notes(slide, "Three prototypes, three intelligence strategies: retrieval, tool-using optimization, and deterministic vision/geometry.")

    # 02 — Agenda
    slide = new_slide(prs, 2, "AGENDA")
    content_header(slide, "What this deck covers", "The same six questions, for three agents", "Each section covers LLM, memory, actions, tools, pipeline, and AI techniques.")
    items = [
        ("01", "RAG AI Stylist", "Hybrid retrieval, grounded answers, citations"),
        ("02", "Trip Agent / Help Me Pack", "Tool calling, weather, CP-SAT, checklist"),
        ("03", "Avatar & Try-On", "GPT-4o Vision, Blender/MPFB2, try-on"),
        ("04", "Cross-agent comparison", "What is shared and what is deliberately different"),
        ("05", "Prototype evidence", "Branches, files, metrics, and reproduction"),
        ("06", "Conclusion", "What is real, what is next"),
    ]
    for index, (num, title, sub) in enumerate(items):
        col = index // 3
        row = index % 3
        x = 0.62 + col * 6.15
        y = 2.05 + row * 1.55
        add_text(slide, num, x, y, 0.62, 0.55, font="Georgia", size=18, color=P_TAN, bold=True)
        add_text(slide, title, x + 0.68, y - 0.02, 4.8, 0.38, font="Georgia", size=17, color=P_INK, bold=True)
        add_text(slide, sub, x + 0.68, y + 0.4, 4.9, 0.4, size=10.5, color=P_MUTED)
        add_rule(slide, x, y + 0.92, 5.35, P_LINE, 0.008)
    speaker_notes(slide, "The deck is deliberately symmetric: every agent gets the same six-slide treatment.")

    # 03 — At a glance
    slide = new_slide(prs, 3, "OVERVIEW")
    content_header(slide, "Three agents at a glance", "Different problems need different intelligence", "One retrieves knowledge, one computes a plan, one builds a body.")
    cards = [
        ("01", "RAG AI Stylist", "Knows and cites", "LLM: GPT-4o", "Technique: hybrid RAG", "Output: answer + sources", P_GREEN),
        ("02", "Trip Agent", "Decides and computes", "LLM: GPT-4o", "Technique: tool calling + CP-SAT", "Output: capsule + checklist", P_TERRA),
        ("03", "Avatar & Try-On", "Constructs and fits", "LLM: GPT-4o Vision", "Technique: VLM + geometry", "Output: body-shaped GLB", P_GREEN),
    ]
    for index, (num, title, role, llm, tech, output, accent) in enumerate(cards):
        x = 0.6 + index * 4.14
        add_card(slide, x, 2.0, 3.86, 3.95, P_WHITE, P_LINE, accent)
        add_text(slide, num, x + 0.24, 2.2, 0.5, 0.35, font="Georgia", size=16, color=accent, bold=True)
        add_text(slide, title, x + 0.24, 2.62, 3.35, 0.55, font="Georgia", size=19, color=P_INK, bold=True)
        add_text(slide, role, x + 0.24, 3.18, 3.35, 0.3, size=10.5, color=accent, bold=True)
        rows = [(llm, P_INK), (tech, P_INK), (output, P_INK)]
        for r, (line, color) in enumerate(rows):
            add_text(slide, line, x + 0.24, 3.65 + r * 0.42, 3.35, 0.3, size=10.5, color=color)
        add_rule(slide, x + 0.24, 5.54, 3.25, accent, 0.025)
        add_text(slide, "Implemented", x + 0.24, 5.65, 3.3, 0.25, size=8.5, color=P_MUTED)
    add_text(slide, "The shared design rule: use the model for language, and deterministic tools for correctness.", 0.62, 6.35, 11.9, 0.3, size=11, color=P_MUTED, italic=True)
    speaker_notes(slide, "This comparison frames the rest of the deck: the three agents are intentionally different.")

    # 04 — Evidence map
    slide = new_slide(prs, 4, "EVIDENCE")
    content_header(slide, "Prototype evidence", "Every section maps to a branch and to running code", "No architecture-only claims: each agent has implementation artifacts.")
    rows = [
        ["Idea", "Branch", "Commit", "What is real"],
        ["RAG AI Stylist", "rag/try1", "5f7f6b4", "FastAPI, hybrid retrieval, citations, eval set"],
        ["Trip Agent", "helpmepack/try1", "8d90269", "10 tools, CP-SAT, weather, checklist, UI"],
        ["Avatar & Try-On", "avatar/try1", "22eebcb", "Blender/MPFB2, GPT-4o Vision, Three.js, GLB"],
        ["GPT-4V capture", "working tree", "uncommitted", "GPT-4o Vision targets, 19 detail controls, optional SciPy"],
    ]
    add_table(slide, rows, 0.62, 2.05, 12.05, [2.25, 2.35, 1.65, 5.8], 0.62, font_size=10.5)
    add_card(slide, 0.62, 5.62, 12.05, 0.9, P_GREEN_SOFT, P_GREEN, P_GREEN)
    add_text(slide, "Current branch: avatar/try1. The GPT-4V capture and optional MediaPipe/SciPy work is explicitly labelled as current, uncommitted prototype work.", 0.86, 5.82, 11.5, 0.45, size=10.5, color=P_GREEN, bold=True)
    speaker_notes(slide, "Use this slide to ground the report: every claim is tied to a branch and a source path.")

    # 05 — Section 01
    section_divider(
        prs, 5, "01", "RAG AI Stylist",
        "Grounded fashion knowledge with hybrid retrieval and inline citations.",
        "rag/try1  @  5f7f6b4",
        [("14,574", "indexed chunks"), ("384-d", "embeddings"), ("91.67%", "Hit@5 on 12 questions")],
    )

    # 06 — RAG LLM
    slide = new_slide(prs, 6, "01 / RAG")
    content_header(slide, "01 / RAG AI Stylist", "The LLM is used twice", "Query rewriting and grounded answer generation. The embedding model is separate.", "LLM USED")
    add_text(slide, "Model choice", 0.62, 2.02, 4.0, 0.3, font="Georgia", size=17, color=P_INK, bold=True)
    add_para(slide, [
        {"text": f"{BULLET}  OpenAI-compatible Chat Completions; model selected by LLM_MODEL.", "size": 12, "space_after": 8},
        {"text": f"{BULLET}  Repository .env sets gpt-4o; tracked .env.example uses gpt-4o-mini.", "size": 12, "space_after": 8},
        {"text": f"{BULLET}  Answer temperature 0.2; query rewrite temperature 0.0.", "size": 12, "space_after": 8},
        {"text": f"{BULLET}  Max 900 answer tokens; 45 s timeout; 2 retries.", "size": 12, "space_after": 8},
        {"text": f"{BULLET}  No fine-tuning. Grounding comes from retrieval, not weights.", "size": 12, "space_after": 8},
    ], 0.62, 2.45, 6.45, 2.7)
    add_card(slide, 7.35, 2.0, 5.2, 3.35, P_WHITE, P_LINE, P_GREEN)
    add_label(slide, "Model card", 7.62, 2.18, P_GREEN, 8.5)
    rows = [
        ["Field", "Value"],
        ["Model", "gpt-4o (configurable)"],
        ["Answer role", "Grounded answer + citations"],
        ["Rewrite role", "Retrieval-friendly query"],
        ["Embeddings", "all-MiniLM-L6-v2"],
        ["Dimensions", "384"],
        ["Fine-tuning", "None"],
    ]
    add_table(slide, rows, 7.62, 2.5, 4.65, [1.45, 3.2], 0.39, font_size=8.8)
    add_card(slide, 0.62, 5.7, 11.93, 0.96, P_TERRA_SOFT, P_TERRA, P_TERRA)
    add_text(slide, "Why this model: it follows negative constraints, keeps citations stable at low temperature,\nand handles multilingual user questions. The provider stays replaceable through LLM_MODEL.", 0.88, 5.86, 11.5, 0.62, size=10.5, color=P_INK)
    speaker_notes(slide, "The same model does rewrite and answer, but with different temperature and token budgets. Embeddings are not done by the LLM.")

    # 07 — RAG Memory
    slide = new_slide(prs, 7, "01 / RAG")
    content_header(slide, "01 / RAG AI Stylist", "Four memory layers, one boundary", "Conversation state is separate from the fashion knowledge base.", "MEMORY")
    mem = [
        ("Conversation", "SQLite WAL", "Messages, sources, citations, rewritten query.", P_GREEN),
        ("Prompt window", "8 + 4 messages", "Last 8 for answering; last 4 for query rewriting.", P_TERRA),
        ("Knowledge", "14,574 chunks", "384-d embeddings stored in Supabase pgvector.", P_GREEN),
        ("Client", "localStorage", "Conversation ID and rendered chat state.", P_TERRA),
    ]
    for index, (title, big, body, accent) in enumerate(mem):
        x = 0.6 + index * 3.08
        add_card(slide, x, 2.05, 2.88, 3.5, P_WHITE, P_LINE, accent)
        add_label(slide, title, x + 0.22, 2.25, accent, 8.5, 2.5)
        add_text(slide, big, x + 0.22, 2.64, 2.45, 0.45, font="Georgia", size=18, color=P_INK, bold=True)
        add_text(slide, body, x + 0.22, 3.2, 2.45, 0.95, size=10.3, color=P_MUTED)
    add_card(slide, 0.62, 5.82, 11.93, 0.8, P_SOFT, P_LINE)
    add_text(slide, "Boundary: the RAG does not yet retrieve the user's wardrobe, wear log, profile, weather, or purchase history.", 0.88, 6.02, 11.4, 0.4, size=10.5, color=P_INK, bold=True)
    speaker_notes(slide, "The knowledge base is persistent; the conversation store is per-assistant chat. Personal wardrobe memory is still future work.")

    # 08 — RAG Actions
    slide = new_slide(prs, 8, "01 / RAG")
    content_header(slide, "01 / RAG AI Stylist", "What the agent actually does", "A retrieval-and-citation pipeline, not a general chatbot.", "ACTIONS")
    steps = [
        ("Rewrite", "Turn a vague question into a search query."),
        ("Embed", "Produce a normalized 384-d query vector."),
        ("Retrieve", "Run vector search and English full-text search."),
        ("Fuse", "Combine both ranked lists with RRF."),
        ("Assemble", "Label passages [S1]...[Sn], cap at 12,000 chars."),
        ("Answer", "Generate a grounded answer with GPT-4o."),
        ("Cite", "Parse markers and map them to source metadata."),
        ("Stream or refuse", "SSE tokens, or a fixed refusal when evidence is missing."),
    ]
    for index, (title, body) in enumerate(steps):
        y = 2.0 + index * 0.56
        add_text(slide, f"{index + 1:02d}", 0.68, y + 0.02, 0.35, 0.28, font="Arial", size=9, color=P_WHITE, bold=True, align=PP_ALIGN.CENTER)
        add_rect(slide, 0.65, y, 0.42, 0.32, P_GREEN if index % 2 == 0 else P_TERRA, None, 0.35)
        add_text(slide, f"{index + 1:02d}", 0.65, y + 0.04, 0.42, 0.22, size=9, color=P_WHITE, bold=True, align=PP_ALIGN.CENTER)
        add_text(slide, title, 1.2, y - 0.01, 2.2, 0.28, font="Georgia", size=13.5, color=P_INK, bold=True)
        add_text(slide, body, 3.25, y, 4.1, 0.3, size=10, color=P_MUTED)
    add_card(slide, 7.85, 2.0, 4.7, 3.45, P_WHITE, P_LINE, P_GREEN)
    add_label(slide, "Response contract", 8.1, 2.18, P_GREEN, 8.5)
    add_para(slide, [
        {"text": "answer", "font": "Arial", "size": 10.5, "bold": True, "space_after": 4},
        {"text": "sources, citations, grounded", "size": 10, "color": P_MUTED, "space_after": 9},
        {"text": "conversation_id, rewritten_query", "size": 10, "color": P_MUTED, "space_after": 9},
        {"text": "usage", "size": 10, "color": P_MUTED, "space_after": 9},
        {"text": "If retrieval is empty: fixed refusal, grounded = false.", "size": 10, "color": P_TERRA, "bold": True},
    ], 8.1, 2.62, 4.1, 2.3)
    speaker_notes(slide, "The refusal path is a feature, not an error: it prevents unsupported answers.")

    # 09 — RAG Tools
    slide = new_slide(prs, 9, "01 / RAG")
    content_header(slide, "01 / RAG AI Stylist", "The tool stack", "A FastAPI service around OpenAI, Supabase, OCR, and a React client.", "TOOLS")
    tools = [
        ("FastAPI", "Ask, stream, conversations, health"),
        ("OpenAI SDK", "Rewrite + grounded answer"),
        ("Supabase", "Postgres + pgvector + RPCs"),
        ("MiniLM", "384-d query and chunk embeddings"),
        ("PyMuPDF", "Native PDF text extraction"),
        ("Tesseract", "OCR fallback for scanned pages"),
        ("SQLite", "Conversation and message store"),
        ("SSE", "Token streaming to the UI"),
        ("React / Vite", "AI Stylist chat and sources"),
    ]
    for index, (name, desc) in enumerate(tools):
        col = index % 3
        row = index // 3
        x = 0.62 + col * 4.05
        y = 2.02 + row * 1.38
        add_card(slide, x, y, 3.82, 1.18, P_WHITE, P_LINE, P_GREEN if index % 2 == 0 else P_TERRA)
        add_text(slide, name, x + 0.22, y + 0.16, 3.3, 0.3, font="Georgia", size=14, color=P_INK, bold=True)
        add_text(slide, desc, x + 0.22, y + 0.56, 3.3, 0.4, size=9.5, color=P_MUTED)
    add_text(slide, "Ingestion also includes: extraction cache, quality report, chunker, embedder, indexer, verify_setup.py, and a 12-question evaluation harness.", 0.62, 6.42, 11.9, 0.3, size=9.5, color=P_MUTED, italic=True)
    speaker_notes(slide, "The stack is intentionally boring and observable: every ingestion stage has a separate module.")

    # 10 — RAG Pipeline
    slide = new_slide(prs, 10, "01 / RAG")
    content_header(slide, "01 / RAG AI Stylist", "The complete pipeline", "From a question to a cited answer, with all processing steps visible.", "PIPELINE")
    add_picture(slide, ASSETS / "rag-agent-pipeline-flow.png", 0.55, 1.95, 12.23, 4.87)
    speaker_notes(slide, "This is the full production path, not a conceptual sketch. The diagram is generated from the implementation.")

    # 11 — RAG AI techniques
    slide = new_slide(prs, 11, "01 / RAG")
    content_header(slide, "01 / RAG AI Stylist", "AI techniques in the prototype", "Retrieval quality is measured, not assumed.", "AI TECHNIQUES")
    tech = [
        ("RAG", "Answers are grounded in retrieved book passages."),
        ("Hybrid retrieval", "Vector search + English full-text search."),
        ("RRF", "Reciprocal Rank Fusion with k = 60."),
        ("Query rewriting", "LLM rewrite with the last four messages."),
        ("Citation grounding", "Only markers in the answer become citations."),
        ("OCR + evaluation", "Tesseract for scanned books; Hit@5, MRR, precision."),
    ]
    for index, (name, desc) in enumerate(tech):
        col = index % 3
        row = index // 3
        x = 0.62 + col * 4.05
        y = 2.0 + row * 1.9
        add_card(slide, x, y, 3.82, 1.65, P_WHITE, P_LINE, P_GREEN if index % 2 == 0 else P_TERRA)
        add_text(slide, name, x + 0.22, y + 0.18, 3.3, 0.3, font="Georgia", size=15, color=P_INK, bold=True)
        add_text(slide, desc, x + 0.22, y + 0.65, 3.3, 0.75, size=9.8, color=P_MUTED)
    add_text(slide, "Not used: fine-tuning, cross-encoder reranker, query-time metadata filters, multilingual retrieval, personal-wardrobe retrieval.", 0.62, 6.28, 11.9, 0.35, size=9.5, color=P_TERRA, italic=True)
    speaker_notes(slide, "The evaluation numbers are the evidence: 91.67% Hit@5, 85.42% MRR, 71.67% context precision on 12 questions.")

    # 12 — Section 02
    section_divider(
        prs, 12, "02", "Trip Agent",
        "Help Me Pack: a tool-using planner with a deterministic optimizer.",
        "helpmepack/try1  @  8d90269",
        [("10", "native tools"), ("12", "max agent iterations"), ("CP-SAT", "packing optimizer")],
    )

    # 13 — Trip LLM
    slide = new_slide(prs, 13, "02 / TRIP")
    content_header(slide, "02 / Trip Agent", "GPT-4o chooses tools, not packing", "The LLM orchestrates; Python validates; CP-SAT solves the constraint problem.", "LLM USED")
    add_text(slide, "Model choice", 0.62, 2.02, 4.0, 0.3, font="Georgia", size=17, color=P_INK, bold=True)
    add_para(slide, [
        {"text": f"{BULLET}  Default model: gpt-4o; override with LLM_MODEL.", "size": 12, "space_after": 8},
        {"text": f"{BULLET}  Native function calling, tool_choice = auto.", "size": 12, "space_after": 8},
        {"text": f"{BULLET}  Temperature 0; structured JSON extraction.", "size": 12, "space_after": 8},
        {"text": f"{BULLET}  45 s timeout; one retry; bounded to 12 loop iterations.", "size": 12, "space_after": 8},
        {"text": f"{BULLET}  Fallback: deterministic regex parser + dependency loop.", "size": 12, "space_after": 8},
    ], 0.62, 2.45, 6.45, 2.7)
    add_card(slide, 7.35, 2.0, 5.2, 3.35, P_WHITE, P_LINE, P_TERRA)
    add_label(slide, "Model card", 7.62, 2.18, P_TERRA, 8.5)
    rows = [
        ["Field", "Value"],
        ["Model", "gpt-4o (configurable)"],
        ["Interaction", "Native tool calling"],
        ["Extraction", "JSON object + Pydantic"],
        ["Temperature", "0"],
        ["Loop limit", "12 iterations"],
        ["Fallback", "Regex + dependency loop"],
    ]
    add_table(slide, rows, 7.62, 2.5, 4.65, [1.45, 3.2], 0.39, font_size=8.8)
    add_card(slide, 0.62, 5.7, 11.93, 0.96, P_GREEN_SOFT, P_GREEN, P_GREEN)
    add_text(slide, "Why GPT-4o: reliable native tool calls, strict JSON, and good instruction following under negative constraints.\nThe model never computes the packing result; it only chooses and explains.", 0.88, 5.86, 11.5, 0.62, size=10.5, color=P_INK)
    speaker_notes(slide, "This is a neuro-symbolic split: language on the LLM side, correctness on the Python/CP-SAT side.")

    # 14 — Trip memory
    slide = new_slide(prs, 14, "02 / TRIP")
    content_header(slide, "02 / Trip Agent", "Memory is a session, not a profile", "Working state, transcript, session store, and a small client cache.", "MEMORY")
    mem = [
        ("Working", "AgentState", "Trip, weather, requirements, capsule, checklist, errors."),
        ("Conversation", "Last 16 messages", "Injected into each LLM turn with a state summary."),
        ("Session", "SessionStore", "TripAgent keyed by session_id, protected by a lock."),
        ("Client", "localStorage", "Current session_id so a refresh can resume."),
    ]
    for index, (title, big, body) in enumerate(mem):
        x = 0.6 + index * 3.08
        add_card(slide, x, 2.05, 2.88, 3.05, P_WHITE, P_LINE, P_GREEN if index % 2 == 0 else P_TERRA)
        add_label(slide, title, x + 0.22, 2.25, P_GREEN if index % 2 == 0 else P_TERRA, 8.5, 2.5)
        add_text(slide, big, x + 0.22, 2.64, 2.45, 0.45, font="Georgia", size=17, color=P_INK, bold=True)
        add_text(slide, body, x + 0.22, 3.2, 2.45, 1.1, size=10, color=P_MUTED)
    # state machine strip
    add_card(slide, 0.62, 5.38, 11.93, 1.15, P_SOFT, P_LINE)
    add_label(slide, "State machine", 0.86, 5.52, P_GREEN, 8)
    states = ["collecting_details", "needs_clarification", "ready", "optimizing", "optimized / infeasible"]
    x = 0.9
    for index, state in enumerate(states):
        add_pill(slide, state, x, 5.9, P_GREEN, P_WHITE, 2.1)
        if index < len(states) - 1:
            add_text(slide, "->", x + 2.12, 5.95, 0.35, 0.2, size=10, color=P_TAN, bold=True)
        x += 2.32
    add_text(slide, "No long-term user profile, wear history, or cross-session learning yet.", 0.62, 6.68, 11.9, 0.25, size=9.5, color=P_TERRA, italic=True)
    speaker_notes(slide, "The in-memory session store is the main limitation: a backend restart loses the trip.")

    # 15 — Trip actions
    slide = new_slide(prs, 15, "02 / TRIP")
    content_header(slide, "02 / Trip Agent", "What the agent accomplishes", "From a messy trip request to a validated checklist.", "ACTIONS")
    actions = [
        ("Understand", "Parse destination, dates, duration, activities, dress code, luggage."),
        ("Clarify", "Ask one concise question instead of inventing missing fields."),
        ("Retrieve context", "Fetch daily weather and load the wardrobe snapshot."),
        ("Translate", "Convert weather and activities into daily requirements."),
        ("Optimize", "Run CP-SAT to minimize items under the weight constraint."),
        ("Build capsule", "Produce daily outfits, selected items, total weight, status."),
        ("Checklist", "Create packed:false items and track packing updates."),
        ("Diagnose", "Explain INFEASIBLE; propose options; never relax silently."),
    ]
    for index, (title, body) in enumerate(actions):
        col = index % 2
        row = index // 2
        x = 0.62 + col * 6.1
        y = 2.02 + row * 1.12
        add_text(slide, f"{index + 1:02d}", x, y, 0.4, 0.3, font="Georgia", size=14, color=P_TAN, bold=True)
        add_text(slide, title, x + 0.52, y - 0.02, 2.4, 0.3, font="Georgia", size=14, color=P_INK, bold=True)
        add_text(slide, body, x + 0.52, y + 0.34, 4.9, 0.55, size=9.8, color=P_MUTED)
        add_rule(slide, x, y + 0.92, 5.4, P_LINE, 0.008)
    add_text(slide, "Not in scope: computer vision, purchase evaluation, non-trip outfit generation, persistent profiling.", 0.62, 6.68, 11.9, 0.25, size=9.5, color=P_TERRA, italic=True)
    speaker_notes(slide, "The important action is clarification: the agent is designed to ask rather than hallucinate trip fields.")

    # 16 — Trip tools
    slide = new_slide(prs, 16, "02 / TRIP")
    content_header(slide, "02 / Trip Agent", "Ten native tools, one deterministic core", "Every tool has a schema, a Python implementation, and a backing resource.", "TOOLS")
    left_tools = [
        ("get_trip_details", "GPT-4o JSON + regex fallback"),
        ("get_weather", "Open-Meteo + labelled fallback"),
        ("get_wardrobe", "wardrobe.csv + compatibility.csv"),
        ("get_activity_requirements", "Deterministic rules"),
        ("optimize_trip", "OR-Tools CP-SAT"),
    ]
    right_tools = [
        ("generate_checklist", "Pydantic capsule -> checklist"),
        ("suggest_alternatives", "Diagnostic CP-SAT solve"),
        ("update_trip", "Invalidate stale state, re-optimize"),
        ("update_checklist", "No optimizer rerun"),
        ("check_gaps", "Optional Gap Agent hook"),
    ]
    for col, tools in enumerate([left_tools, right_tools]):
        x = 0.62 + col * 6.1
        for index, (name, backing) in enumerate(tools):
            y = 2.02 + index * 0.72
            add_card(slide, x, y, 5.72, 0.58, P_WHITE, P_LINE, P_GREEN if col == 0 else P_TERRA)
            add_text(slide, name, x + 0.2, y + 0.1, 2.45, 0.28, font="Arial", size=9.5, color=P_INK, bold=True)
            add_text(slide, backing, x + 2.65, y + 0.12, 2.9, 0.25, size=8.8, color=P_MUTED)
    add_text(slide, "External services: OpenAI · Open-Meteo · OR-Tools CP-SAT · pandas/CSV · FastAPI · Pydantic · React/Vite.", 0.62, 6.3, 11.9, 0.3, size=9.5, color=P_MUTED, italic=True)
    speaker_notes(slide, "Tool arguments are validated with Pydantic and dependencies are enforced in Python, not left to the model.")

    # 17 — Trip pipeline
    slide = new_slide(prs, 17, "02 / TRIP")
    content_header(slide, "02 / Trip Agent", "The complete pipeline", "Input, API, agent loop, LLM, tools, state, UI, and follow-up actions.", "PIPELINE")
    add_picture(slide, ASSETS / "trip-agent-pipeline-compact-flow.png", 0.55, 1.95, 12.23, 4.87)
    speaker_notes(slide, "The compact diagram mirrors the original HelpMePack pipeline; the full detailed version is in the report assets.")

    # 18 — Trip AI techniques
    slide = new_slide(prs, 18, "02 / TRIP")
    content_header(slide, "02 / Trip Agent", "AI techniques in the prototype", "Agentic orchestration around a deterministic solver.", "AI TECHNIQUES")
    tech = [
        ("Tool calling", "GPT-4o selects among ten tools; Python executes."),
        ("Prompt engineering", "Ten system rules enforce order, clarification, and grounding."),
        ("Structured output", "JSON extraction plus Pydantic validation."),
        ("Neuro-symbolic", "LLM language + CP-SAT combinatorial optimization."),
        ("Guardrails", "Regex fallback, labelled synthetic weather, no silent relaxation."),
        ("RAG (separate)", "The fashion knowledge layer is documented in section 01."),
    ]
    for index, (name, desc) in enumerate(tech):
        col = index % 3
        row = index // 3
        x = 0.62 + col * 4.05
        y = 2.0 + row * 1.9
        add_card(slide, x, y, 3.82, 1.65, P_WHITE, P_LINE, P_GREEN if index % 2 == 0 else P_TERRA)
        add_text(slide, name, x + 0.22, y + 0.18, 3.3, 0.3, font="Georgia", size=15, color=P_INK, bold=True)
        add_text(slide, desc, x + 0.22, y + 0.65, 3.3, 0.75, size=9.8, color=P_MUTED)
    add_text(slide, "Not used: fine-tuning, RLHF, autonomous multi-agent orchestration, real computer vision.", 0.62, 6.28, 11.9, 0.35, size=9.5, color=P_TERRA, italic=True)
    speaker_notes(slide, "The core evaluation is offline tool/optimizer testing, not only answer quality.")

    # 19 — Section 03
    section_divider(
        prs, 19, "03", "Avatar & Try-On",
        "GPT-4o Vision parameter selection, optional MediaPipe/SciPy refinement, and procedural garment fitting.",
        "avatar/try1  @  22eebcb  + current working tree",
        [("2", "photos for capture"), ("8", "MPFB macro targets"), ("19", "detail controls")],
    )

    # 20 - Avatar LLM
    slide = new_slide(prs, 20, "03 / AVATAR")
    content_header(slide, "03 / Avatar & Try-On", "GPT-4o Vision chooses the body", "Front + side photos + height; the model returns MPFB targets and detail values after consent.", "LLM: PRIMARY")
    add_text(slide, "One vision call. Eight targets. Nineteen details.", 0.62, 2.05, 11.8, 0.6, font="Georgia", size=32, color=P_INK, bold=True)
    cards = [
        ("What it sees", "Front + side photos and the declared height. Explicit consent is required.", P_GREEN),
        ("What it returns", "Body shape, confidence, 8 MPFB macro targets, and 19 detail controls.", P_TERRA),
        ("What we do with it", "Clamp values, apply the sliders, and generate in Blender. MediaPipe/SciPy remain optional.", P_GREEN),
    ]
    for index, (title, body, accent) in enumerate(cards):
        x = 0.62 + index * 4.08
        add_card(slide, x, 2.9, 3.86, 2.7, P_WHITE, P_LINE, accent)
        add_label(slide, title, x + 0.24, 3.1, accent, 8.5, 3.3)
        add_text(slide, body, x + 0.24, 3.55, 3.35, 1.75, size=11.2, color=P_INK)
    add_text(slide, "No fine-tuning. The LLM chooses parameters; Blender builds the body.", 0.62, 6.0, 11.9, 0.3, size=10.5, color=P_TERRA, italic=True)
    speaker_notes(slide, "GPT-4o Vision is the primary avatar-estimation path. Local MediaPipe and SciPy are optional refinement tools.")

    # 21 - Avatar memory
    slide = new_slide(prs, 21, "03 / AVATAR")
    content_header(slide, "03 / Avatar & Try-On", "Memory is local, temporary, and explicit", "No account, no durable body profile, no hidden personalization.", "MEMORY")
    mem = [
        ("UI state", "React state", "Photos, vision result, targets, detail sliders, job result."),
        ("Saved looks", "localStorage", "Up to 24 looks with garment and wardrobe IDs."),
        ("Photo pair", "Consent-gated", "Front/side object URLs; sent to OpenAI only after consent."),
        ("Vision result", "React state", "Body shape, confidence, 8 targets, 19 detail values."),
        ("Backend job", "Temp + lock", "One active Blender job, params/details JSON, temp GLB."),
        ("Generated assets", "24 h TTL", "avatar_<jobId>.glb in public/models/generated."),
    ]
    for index, (title, big, body) in enumerate(mem):
        col = index % 3
        row = index // 3
        x = 0.62 + col * 4.05
        y = 2.0 + row * 1.95
        add_card(slide, x, y, 3.82, 1.68, P_WHITE, P_LINE, P_GREEN if index % 2 == 0 else P_TERRA)
        add_label(slide, title, x + 0.22, y + 0.16, P_GREEN if index % 2 == 0 else P_TERRA, 8)
        add_text(slide, big, x + 0.22, y + 0.52, 3.35, 0.3, font="Georgia", size=14.5, color=P_INK, bold=True)
        add_text(slide, body, x + 0.22, y + 0.9, 3.35, 0.6, size=9.3, color=P_MUTED)
    add_text(slide, "Optional SciPy jobs are in-memory; 128 detail targets are whitelisted; no durable body profile.", 0.62, 6.3, 11.9, 0.3, size=9.5, color=P_MUTED, italic=True)
    speaker_notes(slide, "The primary vision flow sends photos to OpenAI only after consent; the app stores no durable body profile.")

    # 22 - Avatar actions
    slide = new_slide(prs, 22, "03 / AVATAR")
    content_header(slide, "03 / Avatar & Try-On", "What the visual agent accomplishes", "GPT-4o Vision chooses the body; Blender builds and dresses it.", "ACTIONS")
    actions = [
        ("Capture", "Front + side photos + height."),
        ("Consent", "Explicit OpenAI consent."),
        ("GPT-4o Vision", "Reads both photos; chooses body parameters."),
        ("Targets + details", "8 MPFB macros + 19 detail controls."),
        ("Generate", "Validate and run Blender/MPFB2."),
        ("Garments + GLB", "Body-derived shells, one dressed GLB."),
        ("Preview", "Three.js viewer, metrics, compare, save."),
        ("MediaPipe", "Optional pose + silhouette measurements."),
        ("SciPy fit", "Optional Powell search; IoU + profile; 36 evals."),
        ("Questionnaire", "Eight-answer local fallback."),
    ]
    for index, (title, body) in enumerate(actions):
        col = index % 2
        row = index // 2
        x = 0.62 + col * 6.1
        y = 2.02 + row * 0.9
        add_text(slide, f"{index + 1:02d}", x, y, 0.4, 0.3, font="Georgia", size=13.5, color=P_TAN, bold=True)
        add_text(slide, title, x + 0.52, y - 0.02, 2.4, 0.3, font="Georgia", size=13.5, color=P_INK, bold=True)
        add_text(slide, body, x + 0.52, y + 0.3, 4.9, 0.44, size=9.3, color=P_MUTED)
        add_rule(slide, x, y + 0.78, 5.4, P_LINE, 0.008)
    add_text(slide, "Slot rule: one item per slot; a dress replaces top + bottom; outerwear layers over a top.", 0.62, 6.68, 11.9, 0.25, size=9.5, color=P_TERRA, italic=True)
    speaker_notes(slide, "The primary flow is GPT-4o Vision -> targets/details -> Blender. MediaPipe, SciPy, and the questionnaire are optional paths.")

    # 23 - Avatar tools
    slide = new_slide(prs, 23, "03 / AVATAR")
    content_header(slide, "03 / Avatar & Try-On", "The tool stack, with actual output", "GPT-4o Vision for parameters, local fallback tools, Blender, and a 3D viewer.", "TOOLS")
    tools = [
        ("GPT-4o Vision", "Primary parameter chooser"),
        ("FastAPI", "Validation + job control"),
        ("Blender 5.4", "Headless generation"),
        ("MPFB2", "Macros + 128 detail targets"),
        ("bpy / bmesh", "Garment geometry"),
        ("Three.js / R3F", "3D preview + controls"),
        ("MediaPipe Pose", "Optional local analysis"),
        ("MediaPipe Segmenter", "Optional silhouette"),
        ("SciPy Powell", "Optional silhouette fit"),
        ("NumPy + Pillow", "Masks, IoU, profiles"),
    ]
    for index, (name, desc) in enumerate(tools):
        col = index % 2
        row = index // 2
        x = 0.62 + col * 3.15
        y = 2.0 + row * 0.86
        add_card(slide, x, y, 2.95, 0.74, P_WHITE, P_LINE, P_GREEN if index % 2 == 0 else P_TERRA)
        add_text(slide, name, x + 0.16, y + 0.08, 2.55, 0.24, font="Georgia", size=11.5, color=P_INK, bold=True)
        add_text(slide, desc, x + 0.16, y + 0.38, 2.55, 0.3, size=8.2, color=P_MUTED)
    add_card(slide, 7.35, 1.98, 5.2, 4.55, P_SOFT, P_LINE)
    add_picture(slide, ASSETS / "avatar-dressed_threeq.png", 7.72, 2.12, 2.55, 3.82)
    add_text(slide, "Actual Blender render", 10.4, 2.45, 1.95, 0.3, font="Georgia", size=12, color=P_INK, bold=True)
    add_text(slide, "public/models/dressed_avatar.glb\nrendered with backend/blender/\nrender_preview.py", 10.4, 2.85, 1.95, 1.0, size=8.5, color=P_MUTED)
    add_text(slide, "10 garments / 5 slots", 10.4, 4.05, 1.95, 0.3, size=9.5, color=P_GREEN, bold=True)
    add_text(slide, "Photos go to OpenAI only after consent; the MediaPipe and SciPy paths stay local.", 0.62, 6.45, 11.9, 0.3, size=9.5, color=P_MUTED, italic=True)
    speaker_notes(slide, "The render on the right is an actual output from the current prototype, not a mockup.")

    # 24 — Avatar pipeline
    slide = new_slide(prs, 24, "03 / AVATAR")
    content_header(slide, "03 / Avatar & Try-On", "The complete two-photo pipeline", "Photo pair + consent, GPT-4o Vision targets, Blender/MPFB2, garments, viewer; MediaPipe/SciPy optional.", "PIPELINE")
    add_picture(slide, ASSETS / "avatar-agent-pipeline-flow.png", 0.55, 1.95, 12.23, 4.87)
    speaker_notes(slide, "GPT-4o Vision is the primary parameter chooser; MediaPipe and SciPy are optional refinement paths.")

    # 25 - Avatar AI techniques
    slide = new_slide(prs, 25, "03 / AVATAR")
    content_header(slide, "03 / Avatar & Try-On", "AI techniques in the prototype", "Vision-language parameter selection first; local refinement is optional.", "AI TECHNIQUES")
    tech = [
        ("GPT-4o parameter selection", "Front + side photos -> 8 macro targets + 19 details."),
        ("Structured output", "JSON checked, clamped, and bounded before use."),
        ("Optional pose + silhouette", "MediaPipe measurements and side-depth hints."),
        ("Optional SciPy fitting", "Powell search minimizes IoU + width-profile error."),
        ("Procedural garments", "Body-derived shells, offset and solidified."),
        ("Closed-loop + guardrails", "Achieved ratios nudge controls; invalid input rejected."),
    ]
    for index, (name, desc) in enumerate(tech):
        col = index % 3
        row = index // 3
        x = 0.62 + col * 4.05
        y = 2.0 + row * 1.9
        add_card(slide, x, y, 3.82, 1.65, P_WHITE, P_LINE, P_GREEN if index % 2 == 0 else P_TERRA)
        add_text(slide, name, x + 0.22, y + 0.18, 3.3, 0.3, font="Georgia", size=14.2, color=P_INK, bold=True)
        add_text(slide, desc, x + 0.22, y + 0.65, 3.3, 0.75, size=9.6, color=P_MUTED)
    add_text(slide, "Not used for geometry: fine-tuning, skeletal skinning, morph targets, cloth simulation, persistent profiles.", 0.62, 6.28, 11.9, 0.35, size=9.5, color=P_TERRA, italic=True)
    speaker_notes(slide, "The primary AI is GPT-4o Vision parameter selection. MediaPipe and SciPy are optional refinement tools.")

    # 26 — Comparison
    slide = new_slide(prs, 26, "COMPARISON")
    content_header(slide, "Cross-agent comparison", "Shared discipline, different intelligence", "The architecture uses each tool where it is strongest.", "COMPARISON")
    rows = [
        ["Dimension", "RAG AI Stylist", "Trip Agent", "Avatar & Try-On"],
        ["Primary intelligence", "Retrieval + grounded generation", "LLM orchestration + CP-SAT", "Vision-language + geometry"],
        ["LLM", "GPT-4o (configurable)", "GPT-4o (configurable)", "GPT-4o Vision (primary)"],
        ["Memory", "SQLite + pgvector + localStorage", "AgentState + in-memory sessions", "React + localStorage + file cache"],
        ["External services", "OpenAI, Supabase", "OpenAI, Open-Meteo", "OpenAI, Blender (+ MediaPipe optional)"],
        ["Key technique", "Hybrid RAG with citations", "Tool calling + neuro-symbolic optimization", "VLM parameter selection + garments"],
        ["Output", "Cited answer + sources", "Trip capsule + checklist", "Body-shaped GLB + 3D try-on"],
        ["Status", "Implemented", "Implemented", "Implemented; GPT-4V flow uncommitted"],
    ]
    add_table(slide, rows, 0.62, 1.98, 12.05, [2.1, 3.3, 3.3, 3.35], 0.55, font_size=9.2)
    add_text(slide, "Use the LLM for language and relative visual judgment, solvers for fitting and constraints, and geometry for bodies.", 0.62, 6.62, 11.9, 0.3, size=10.5, color=P_GREEN, bold=True)
    speaker_notes(slide, "This is the architectural takeaway of the report.")

    # 27 — Conclusion
    slide = new_slide(prs, 27, "CONCLUSION")
    content_header(slide, "Conclusion", "Three working prototypes, three clear boundaries", "What is real today, and what comes next.", "CLOSING")
    cards = [
        ("RAG", "Real grounded answers", "14,574 chunks, hybrid retrieval, citations, measured Hit@5.", P_GREEN),
        ("Trip Agent", "Real planning", "10 tools, weather, CP-SAT, capsule, checklist, fallbacks.", P_TERRA),
        ("Avatar", "Real visual try-on", "GPT-4o Vision parameter selection, optional MediaPipe/SciPy, Blender/MPFB2, GLB.", P_GREEN),
    ]
    for index, (title, big, body, accent) in enumerate(cards):
        x = 0.62 + index * 4.08
        add_card(slide, x, 2.0, 3.86, 2.2, P_WHITE, P_LINE, accent)
        add_label(slide, title, x + 0.24, 2.2, accent, 8.5)
        add_text(slide, big, x + 0.24, 2.58, 3.35, 0.4, font="Georgia", size=16.5, color=P_INK, bold=True)
        add_text(slide, body, x + 0.24, 3.12, 3.35, 0.85, size=9.8, color=P_MUTED)
    add_text(slide, "Next steps", 0.62, 4.62, 3.0, 0.3, font="Georgia", size=15, color=P_INK, bold=True)
    add_para(slide, [
        {"text": f"{BULLET}  Connect the RAG layer to personal wardrobe and wear-history data.", "size": 10.5, "space_after": 4},
        {"text": f"{BULLET}  Expose RAG as a Trip Agent tool and connect the Gap Agent.", "size": 10.5, "space_after": 4},
        {"text": f"{BULLET}  Replace synthetic wardrobe data with real user data.", "size": 10.5, "space_after": 4},
        {"text": f"{BULLET}  Add persistent profiles, authentication, and production hardening.", "size": 10.5, "space_after": 4},
    ], 0.62, 5.0, 11.5, 1.2)
    add_text(slide, "See your wardrobe differently.", 0.62, 6.45, 8.0, 0.45, font="Georgia", size=22, color=P_GREEN, bold=True, italic=True)
    speaker_notes(slide, "Close on the architectural lesson and the concrete next steps.")
    build_purchasing_slides(prs)
    prs.save(DECK_PATH)
    print("Wrote deck to", DECK_PATH)


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    draw_rag(ASSETS / "rag-agent-pipeline.png")
    draw_trip(ASSETS / "trip-agent-pipeline-compact.png")
    draw_avatar(ASSETS / "avatar-agent-pipeline.png")
    for name in ["rag-agent-pipeline", "trip-agent-pipeline-compact", "avatar-agent-pipeline"]:
        source = ASSETS / f"{name}.png"
        image = Image.open(source)
        image.crop((0, 250, image.width, 1015)).save(ASSETS / f"{name}-flow.png")
    print("Wrote pipeline diagrams to", ASSETS)
    build_deck()


if __name__ == "__main__":
    main()


