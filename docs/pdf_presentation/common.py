"""Shared styles, tables and document scaffolding for the DressMe presentation PDFs."""
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.graphics.shapes import Drawing, Line, Polygon, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, Frame, KeepTogether, NextPageTemplate, PageBreak, PageTemplate,
                                Paragraph, Spacer, Table, TableStyle)

OLIVE = colors.HexColor("#556B2F")
OLIVE_DARK = colors.HexColor("#3E4F22")
OLIVE_LIGHT = colors.HexColor("#E8EDE0")
INK = colors.HexColor("#1C1C1C")
GREY = colors.HexColor("#8C8A82")
SAND = colors.HexColor("#F0EFEA")
LINE = colors.HexColor("#CFCDC4")
LLM = colors.HexColor("#FCE8C8")
CODE = colors.HexColor("#DDE8F5")
DATA = colors.HexColor("#E8EDE0")
EXT = colors.HexColor("#EDE3F3")
WARN = colors.HexColor("#F7D9D9")

W = 170 * mm

base = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=base["Heading1"], fontName="Helvetica-Bold", fontSize=19, textColor=INK,
                    spaceBefore=2, spaceAfter=9)
H2 = ParagraphStyle("H2", parent=base["Heading2"], keepWithNext=1, fontName="Helvetica-Bold", fontSize=12.5,
                    textColor=OLIVE, spaceBefore=12, spaceAfter=5)
H3 = ParagraphStyle("H3", parent=base["Heading3"], keepWithNext=1, fontName="Helvetica-Bold", fontSize=10.5,
                    textColor=INK, spaceBefore=8, spaceAfter=3)
BODY = ParagraphStyle("B", parent=base["BodyText"], fontName="Helvetica", fontSize=9.4, leading=13.2,
                      textColor=INK, spaceAfter=5)
SMALL = ParagraphStyle("S", parent=BODY, fontSize=8.2, leading=11, textColor=GREY)
BUL = ParagraphStyle("BUL", parent=BODY, leftIndent=11, bulletIndent=1, spaceAfter=2.5)
CELL = ParagraphStyle("C", parent=BODY, fontSize=8, leading=10.4, spaceAfter=0)
CELLB = ParagraphStyle("CB", parent=CELL, fontName="Helvetica-Bold")
CAP = ParagraphStyle("CAP", parent=SMALL, alignment=TA_CENTER, spaceBefore=2, spaceAfter=10)
CODEST = ParagraphStyle("CODE", parent=BODY, fontName="Courier", fontSize=7.5, leading=9.8, backColor=SAND,
                        borderPadding=5, leftIndent=4, rightIndent=4, spaceBefore=3, spaceAfter=8)


_ALIASES = {"H1": H1, "H2": H2, "H3": H3, "BODY": BODY}


def P(text, style=BODY):
    if isinstance(style, str):
        style = _ALIASES.get(style, BODY)
    return Paragraph(text, style)


def H2_(text):
    return Paragraph(text, H2)


def H3_(text):
    return Paragraph(text, H3)


def bullets(items):
    return [Paragraph(text, BUL, bulletText="\u2022") for text in items]


def numbered(items):
    out = []
    for i, text in enumerate(items, 1):
        out.append(Paragraph(text, BUL, bulletText="%d." % i))
    return out


def table(rows, widths, header=True, size=None, fill=OLIVE_LIGHT):
    def cell(value, bold):
        style = CELLB if bold else CELL
        if size:
            style = ParagraphStyle("tmp", parent=style, fontSize=size, leading=size * 1.3)
        return Paragraph(str(value), style)

    data = [[cell(c, header and r == 0) for c in row] for r, row in enumerate(rows)]
    t = Table(data, colWidths=[w * mm for w in widths], repeatRows=1 if header else 0)
    style = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("GRID", (0, 0), (-1, -1), 0.4, LINE),
             ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
             ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
    if header:
        style.append(("BACKGROUND", (0, 0), (-1, 0), fill))
    t.setStyle(TableStyle(style))
    return t


def code(text):
    text = escape(text)
    return Paragraph(text.replace(" ", "&nbsp;").replace("\n", "<br/>"), CODEST)


class Diagram:
    def __init__(self, width_mm=170, height_mm=80):
        self.w, self.h = width_mm * mm, height_mm * mm
        self.d = Drawing(self.w, self.h)

    def box(self, x, y, w, h, text, fill=CODE, size=7.4, bold=False):
        self.d.add(Rect(x * mm, y * mm, w * mm, h * mm, rx=3, ry=3, fillColor=fill, strokeColor=INK, strokeWidth=0.7))
        lines = text.split("\n")
        lead = size + 1.7
        top = y * mm + h * mm / 2 + (len(lines) - 1) * lead / 2 - size * 0.32
        for i, line in enumerate(lines):
            self.d.add(String((x + w / 2) * mm, top - i * lead, line,
                              fontName="Helvetica-Bold" if bold or (i == 0 and len(lines) > 1) else "Helvetica",
                              fontSize=size, fillColor=INK, textAnchor="middle"))

    def label(self, x, y, text, size=7, color=GREY, anchor="middle", bold=False):
        self.d.add(String(x * mm, y * mm, text, fontName="Helvetica-Bold" if bold else "Helvetica", fontSize=size,
                          fillColor=color, textAnchor=anchor))

    def arrow(self, x1, y1, x2, y2, color=INK, dashed=False):
        import math
        a, b, c, d = x1 * mm, y1 * mm, x2 * mm, y2 * mm
        line = Line(a, b, c, d, strokeColor=color, strokeWidth=0.9)
        if dashed:
            line.strokeDashArray = [3, 2]
        self.d.add(line)
        angle = math.atan2(d - b, c - a)
        size = 2.5 * mm
        left = (c - size * math.cos(angle - 0.4), d - size * math.sin(angle - 0.4))
        right = (c - size * math.cos(angle + 0.4), d - size * math.sin(angle + 0.4))
        self.d.add(Polygon([c, d, left[0], left[1], right[0], right[1]], fillColor=color, strokeColor=color,
                           strokeWidth=0.3))

    def polyline(self, points, color=INK, dashed=False):
        for i in range(len(points) - 2):
            line = Line(points[i][0] * mm, points[i][1] * mm, points[i + 1][0] * mm, points[i + 1][1] * mm,
                        strokeColor=color, strokeWidth=0.9)
            if dashed:
                line.strokeDashArray = [3, 2]
            self.d.add(line)
        self.arrow(points[-2][0], points[-2][1], points[-1][0], points[-1][1], color, dashed)

    def legend(self, lang="fr", y=1.5):
        items = (("LLM", LLM), ("code deterministe", CODE), ("donnees / stockage", DATA), ("service externe", EXT)) \
            if lang == "fr" else (("LLM", LLM), ("deterministic code", CODE), ("data / storage", DATA),
                                  ("external service", EXT))
        x = 2
        for text, fill in items:
            self.d.add(Rect(x * mm, y * mm, 4 * mm, 3 * mm, fillColor=fill, strokeColor=INK, strokeWidth=0.5))
            self.label(x + 5.5, y + 0.6, text, size=6.8, color=INK, anchor="start")
            x += 8 + len(text) * 1.85


def chain(steps, height=40, box_h=20, box_w=29, gap=34, size=6.8, notes=None, legend_lang="fr"):
    """A left-to-right chain of boxes with optional captions underneath."""
    g = Diagram(170, height)
    y = height - box_h - 5
    x = 2
    pos = []
    for text, fill in steps:
        g.box(x, y, box_w, box_h, text, fill, size)
        pos.append(x)
        x += gap
    for i in range(len(steps) - 1):
        g.arrow(pos[i] + box_w, y + box_h / 2, pos[i + 1], y + box_h / 2)
    for i, note in enumerate(notes or []):
        g.label(2, y - 6 - i * 4.6, note, 7, GREY, "start")
    return g.d


def page_frame(lang, footer):
    def draw(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(GREY)
        canvas.drawString(20 * mm, 10 * mm, footer)
        canvas.drawRightString(190 * mm, 10 * mm, ("Page %d" % doc.page) if lang == "fr" else ("Page %d" % doc.page))
        canvas.setStrokeColor(LINE)
        canvas.line(20 * mm, 14 * mm, 190 * mm, 14 * mm)
        canvas.restoreState()
    return draw


def cover(lang, title, subtitle, lines, footer):
    def draw(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(OLIVE)
        canvas.rect(0, 0, A4[0], A4[1], stroke=0, fill=1)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 40)
        canvas.drawString(22 * mm, 190 * mm, "DressMe")
        canvas.setFont("Helvetica", 18)
        canvas.drawString(22 * mm, 176 * mm, title)
        canvas.setFont("Helvetica", 10.5)
        for i, line in enumerate(lines):
            canvas.drawString(22 * mm, (158 - i * 7) * mm, line)
        canvas.setStrokeColor(colors.Color(1, 1, 1, 0.35))
        canvas.setLineWidth(0.8)
        canvas.line(22 * mm, 60 * mm, 188 * mm, 60 * mm)
        canvas.setFont("Helvetica-Oblique", 9)
        canvas.drawString(22 * mm, 52 * mm, subtitle)
        canvas.setFont("Helvetica", 8.5)
        canvas.drawString(22 * mm, 24 * mm, footer)
        canvas.restoreState()
    return draw


def build_doc(out, story, lang, title, footer, cover_title, cover_sub, cover_lines, cover_footer):
    out = Path(out)
    doc = BaseDocTemplate(str(out), pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm,
                          bottomMargin=22 * mm, title=title, author="DressMe")
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="f")
    doc.addPageTemplates([
        PageTemplate(id="cover", frames=[Frame(0, 0, 1, 1)], onPage=cover(lang, cover_title, cover_sub, cover_lines,
                                                                           cover_footer)),
        PageTemplate(id="body", frames=[frame], onPage=page_frame(lang, footer)),
    ])
    story = [NextPageTemplate("body"), PageBreak()] + story
    doc.build(story)
    print("written", out)
    return out
