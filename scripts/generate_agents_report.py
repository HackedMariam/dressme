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
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
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
) -> None:
    x0, y0, x1, y1 = box
    rounded_box(draw, box, WHITE, LINE)
    draw.rounded_rectangle((x0 + 15, y0 + 15, x0 + 51, y0 + 51), radius=10, fill=number_fill)
    nf = font(ARIAL_BOLD, 20)
    draw.text((x0 + 25, y0 + 20), f"{number:02d}", font=nf, fill=WHITE)
    tf = font(GEORGIA_BOLD, 23)
    draw.text((x0 + 64, y0 + 15), title, font=tf, fill=INK)
    bf = font(ARIAL, 18)
    lines = wrap(draw, body, bf, x1 - x0 - 44)
    y = y0 + 64
    for line in lines[:4]:
        draw.text((x0 + 22, y), line, font=bf, fill=MUTED)
        y += 23
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
        "From two photos to a body-shaped try-on",
        "Local pose and silhouette first; optional GPT-4o Vision second opinion; Blender/MPFB2 geometry.",
        "Implemented | avatar/try1 + working tree",
    )

    steps = [
        ("Photo pair", "Front + side photos + height, or the local questionnaire fallback.", GREEN),
        ("Pose + silhouette", "MediaPipe landmarks and selfie segmentation; photos stay in browser.", TERRA),
        ("Measurements", "Height-scaled widths, depths, inseam, mass and BMI.", TERRA),
        ("Optional vision", "Consent-gated GPT-4o relative observations and bounded detail hints.", TERRA),
        ("Silhouette fit", "Optional SciPy Powell search over 15 controls; IoU + profile fit.", GREEN),
        ("MPFB + API", "Macros + details; whitelist, bounds, slot rules, job lock.", GREEN),
        ("Blender / MPFB2", "Shape body, apply details, leg post-process, bake keys.", TERRA),
        ("Garments + GLB", "Body-derived shells, materials, one dressed GLB.", GREEN),
        ("Validate + serve", "Check glTF magic bytes, move to public folder, return URL.", GREEN),
        ("Preview + correct", "Three.js viewer, metrics, compare, one closed-loop regen.", GREEN),
    ]

    w, h, gap, left, top = 300, 170, 55, 100, 290
    boxes = []
    for i in range(5):
        boxes.append((left + i * (w + gap), top, left + i * (w + gap) + w, top + h))
    for i in range(5):
        boxes.append((left + (4 - i) * (w + gap), top + 430, left + (4 - i) * (w + gap) + w, top + 430 + h))

    for i, (title, body, accent) in enumerate(steps):
        step_box(draw, i + 1, title, body, boxes[i], accent, GREEN if accent == GREEN else TERRA)

    for i in range(4):
        arrow(draw, (boxes[i][2] + 6, top + h // 2), (boxes[i + 1][0] - 6, top + h // 2), TAN)
    arrow(draw, (boxes[4][0] + w // 2, top + h + 8), (boxes[5][0] + w // 2, top + 430 - 8), TAN)
    for i in range(5, 9):
        arrow(draw, (boxes[i][0] - 6, top + 430 + h // 2), (boxes[i + 1][2] + 6, top + 430 + h // 2), TAN)

    note_card(draw, (100, 900, 660, 1002), "Tools", "MediaPipe | SciPy | GPT-4V optional | Blender | Three.js", GREEN)
    note_card(draw, (700, 900, 1260, 1002), "Memory", "Photos in browser | 24 saved looks | 24 h GLB TTL", TERRA)
    note_card(draw, (1300, 900, 1820, 1002), "Privacy boundary", "No default upload | consent-gated | no profile", GREEN)
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


def add_footer(slide, label: str, page: int, total: int = 27) -> None:
    add_rule(slide, 0.55, 7.04, 12.23)
    add_text(slide, "DressMe  /  Agent implementation report", 0.55, 7.12, 7.0, 0.22, size=8.5, color=P_MUTED)
    add_text(slide, f"{label}   {page:02d} / {total:02d}", 8.7, 7.12, 4.08, 0.22, size=8.5, color=P_MUTED, align=PP_ALIGN.RIGHT)


def new_slide(prs, page: int, label: str):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = P_BG
    add_rect(slide, 0, 0, 13.333, 0.06, P_GREEN, None, radius=0.0)
    add_footer(slide, label, page)
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


def section_divider(prs, page: int, number: str, title: str, subtitle: str, branch: str, metrics: list[tuple[str, str]]):
    slide = new_slide(prs, page, f"SECTION {number}")
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


def build_deck() -> None:
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    total = 27

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
        ("03", "Avatar & Try-On", "Pose, silhouette, Blender/MPFB2, optional GPT-4V"),
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
        ("03", "Avatar & Try-On", "Constructs and fits", "LLM: optional GPT-4o Vision", "Technique: vision + SciPy + geometry", "Output: body-shaped GLB", P_GREEN),
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
        ["Avatar & Try-On", "avatar/try1", "22eebcb", "Blender/MPFB2, MediaPipe, Three.js, GLB, optional GPT-4V"],
        ["Two-photo capture", "working tree", "uncommitted", "Local pose + silhouette, SciPy fitting, 128 detail targets"],
    ]
    add_table(slide, rows, 0.62, 2.05, 12.05, [2.25, 2.35, 1.65, 5.8], 0.62, font_size=10.5)
    add_card(slide, 0.62, 5.62, 12.05, 0.9, P_GREEN_SOFT, P_GREEN, P_GREEN)
    add_text(slide, "Current branch: avatar/try1. The two-photo capture and optional GPT-4V work is explicitly labelled as current, uncommitted prototype work.", 0.86, 5.82, 11.5, 0.45, size=10.5, color=P_GREEN, bold=True)
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
        "Local two-photo capture, optional GPT-4o Vision and SciPy fitting, and procedural garment fitting.",
        "avatar/try1  @  22eebcb  + current working tree",
        [("2", "photos for capture"), ("15", "controls fitted by SciPy"), ("36", "max evaluations")],
    )

    # 20 - Avatar LLM
    slide = new_slide(prs, 20, "03 / AVATAR")
    content_header(slide, "03 / Avatar & Try-On", "The LLM is a second opinion, not the ruler", "Local pose and silhouette measurements are primary; optional GPT-4o Vision adds relative observations.", "LLM: OPTIONAL")
    add_text(slide, "Local first. Optional VLM second.", 0.62, 2.05, 11.8, 0.75, font="Georgia", size=36, color=P_INK, bold=True)
    cards = [
        ("Primary: local CV", "MediaPipe pose + silhouette, height-scaled. Photos stay in the browser.", P_GREEN),
        ("Optional: GPT-4o Vision", "Consent-gated front/side analysis. Relative observations and bounded detail hints.", P_TERRA),
        ("Hard boundary", "No centimetres and no replacement measurements. The local path works without an API key.", P_GREEN),
    ]
    for index, (title, body, accent) in enumerate(cards):
        x = 0.62 + index * 4.08
        add_card(slide, x, 3.05, 3.86, 2.55, P_WHITE, P_LINE, accent)
        add_label(slide, title, x + 0.24, 3.25, accent, 8.5, 3.3)
        add_text(slide, body, x + 0.24, 3.68, 3.35, 1.65, size=11.5, color=P_INK)
    add_text(slide, "No fine-tuning. A separate SciPy optimizer fits silhouettes; the geometry path never depends on an LLM.", 0.62, 6.0, 11.9, 0.3, size=10.5, color=P_TERRA, italic=True)
    speaker_notes(slide, "This is the key nuance: the current worktree includes an optional GPT-4 Vision second opinion, but the measurements and geometry remain deterministic.")

    # 21 - Avatar memory
    slide = new_slide(prs, 21, "03 / AVATAR")
    content_header(slide, "03 / Avatar & Try-On", "Memory is local, temporary, and explicit", "No account, no durable body profile, no hidden personalization.", "MEMORY")
    mem = [
        ("UI state", "React state", "Photos, analysis, measurements, sliders, job result."),
        ("Saved looks", "localStorage", "Up to 24 looks with garment and wardrobe IDs."),
        ("Backend job", "Temp + lock", "One active Blender job, params/details JSON, temp GLB."),
        ("Generated assets", "24 h TTL", "avatar_<jobId>.glb in public/models/generated."),
        ("Photo pair", "Browser only", "Front/side object URLs; optional upload only after consent."),
        ("Optimizer job", "In-memory", "Async /api/avatar/optimize job, progress, fitted targets."),
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
    add_text(slide, "Photos stay in the browser by default. 128 MPFB detail targets are whitelisted in the manifest; no durable body profile.", 0.62, 6.3, 11.9, 0.3, size=9.5, color=P_MUTED, italic=True)
    speaker_notes(slide, "The absence of a durable profile is deliberate. The local photo path never uploads images.")

    # 22 - Avatar actions
    slide = new_slide(prs, 22, "03 / AVATAR")
    content_header(slide, "03 / Avatar & Try-On", "What the visual agent accomplishes", "From a photo pair to an optimized, body-shaped, dressed GLB.", "ACTIONS")
    actions = [
        ("Capture", "Front + side photos or the local questionnaire."),
        ("Local pose", "MediaPipe landmarks with view-specific checks."),
        ("Silhouette", "Segment the body and scale widths by height."),
        ("Measure", "Widths, depths, inseam, mass, BMI."),
        ("Optional VLM", "GPT-4V relative observations and detail hints."),
        ("SciPy fit", "Powell search over 15 controls; IoU + profile fit."),
        ("Map", "MPFB macros plus up to 128 detail targets."),
        ("Generate", "Blender + MPFB2 shapes the body."),
        ("Dress + GLB", "Garment shells and one dressed GLB."),
        ("Preview + correct", "Three.js viewer, metrics, one closed-loop regen."),
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
    speaker_notes(slide, "The agent is a deterministic visual pipeline; SciPy fitting is optional and the VLM only nudges detail sliders.")

    # 23 - Avatar tools
    slide = new_slide(prs, 23, "03 / AVATAR")
    content_header(slide, "03 / Avatar & Try-On", "The tool stack, with actual output", "Local vision, SciPy fitting, an optional VLM, Blender, and a 3D viewer.", "TOOLS")
    tools = [
        ("MediaPipe Pose", "Landmarks + view checks"),
        ("MediaPipe Segmenter", "Body silhouette mask"),
        ("OpenAI Vision", "Optional relative opinion"),
        ("SciPy Powell", "15-control silhouette fit"),
        ("NumPy + Pillow", "Masks, IoU, profiles"),
        ("FastAPI", "Validation + job control"),
        ("Blender 5.4", "Headless generation"),
        ("MPFB2", "Macros + 128 detail targets"),
        ("bpy / bmesh", "Garment geometry"),
        ("Three.js / R3F", "3D preview + controls"),
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
    add_text(slide, "Photos stay in the browser; only the consent-gated vision route sends them to OpenAI.", 0.62, 6.45, 11.9, 0.3, size=9.5, color=P_MUTED, italic=True)
    speaker_notes(slide, "The render on the right is an actual output from the current prototype, not a mockup.")

    # 24 — Avatar pipeline
    slide = new_slide(prs, 24, "03 / AVATAR")
    content_header(slide, "03 / Avatar & Try-On", "The complete two-photo pipeline", "Capture, local pose and silhouette, optional GPT-4V, SciPy fitting, Blender, garments, viewer.", "PIPELINE")
    add_picture(slide, ASSETS / "avatar-agent-pipeline-flow.png", 0.55, 1.95, 12.23, 4.87)
    speaker_notes(slide, "The default pipeline is local. The optional GPT-4 Vision call is a second opinion, not a measurement step.")

    # 25 - Avatar AI techniques
    slide = new_slide(prs, 25, "03 / AVATAR")
    content_header(slide, "03 / Avatar & Try-On", "AI techniques in the prototype", "Local vision and geometry first; optional VLM and optimization second.", "AI TECHNIQUES")
    tech = [
        ("Pose estimation", "MediaPipe landmarks with visibility and view-specific checks."),
        ("Silhouette segmentation", "Selfie segmenter extracts the body mask for width/depth."),
        ("Height-scaled measurements", "Pixel widths become centimetres using the entered height."),
        ("Optional VLM opinion", "GPT-4o Vision returns relative observations and detail hints."),
        ("SciPy silhouette fitting", "Powell search minimizes IoU loss + width-profile error."),
        ("Garments + correction", "Body-derived shells; achieved ratios nudge controls."),
    ]
    for index, (name, desc) in enumerate(tech):
        col = index % 3
        row = index // 3
        x = 0.62 + col * 4.05
        y = 2.0 + row * 1.9
        add_card(slide, x, y, 3.82, 1.65, P_WHITE, P_LINE, P_GREEN if index % 2 == 0 else P_TERRA)
        add_text(slide, name, x + 0.22, y + 0.18, 3.3, 0.3, font="Georgia", size=14.5, color=P_INK, bold=True)
        add_text(slide, desc, x + 0.22, y + 0.65, 3.3, 0.75, size=9.6, color=P_MUTED)
    add_text(slide, "Not used for geometry: fine-tuning, skeletal skinning, morph targets, cloth simulation, persistent profiles.", 0.62, 6.28, 11.9, 0.35, size=9.5, color=P_TERRA, italic=True)
    speaker_notes(slide, "The AI is local pose/silhouette, optional GPT-4 Vision, and SciPy fitting. Geometry remains procedural.")

    # 26 — Comparison
    slide = new_slide(prs, 26, "COMPARISON")
    content_header(slide, "Cross-agent comparison", "Shared discipline, different intelligence", "The architecture uses each tool where it is strongest.", "COMPARISON")
    rows = [
        ["Dimension", "RAG AI Stylist", "Trip Agent", "Avatar & Try-On"],
        ["Primary intelligence", "Retrieval + grounded generation", "LLM orchestration + CP-SAT", "Vision + geometry + optimization"],
        ["LLM", "GPT-4o (configurable)", "GPT-4o (configurable)", "Optional GPT-4o Vision"],
        ["Memory", "SQLite + pgvector + localStorage", "AgentState + in-memory sessions", "React + localStorage + file cache"],
        ["External services", "OpenAI, Supabase", "OpenAI, Open-Meteo", "MediaPipe, OpenAI (optional), Blender"],
        ["Key technique", "Hybrid RAG with citations", "Tool calling + neuro-symbolic optimization", "Pose + silhouette + SciPy fitting"],
        ["Output", "Cited answer + sources", "Trip capsule + checklist", "Body-shaped GLB + 3D try-on"],
        ["Status", "Implemented", "Implemented", "Implemented; capture work uncommitted"],
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
        ("Avatar", "Real visual try-on", "Local pose + silhouette, optional GPT-4V, SciPy fitting, Blender/MPFB2, GLB.", P_GREEN),
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
    # Fix total in footers (pages were created with default total 27)
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


