"""Builds docs/DressMe_Architecture_Agents.pdf (architecture of every agent, graphs, prompts, RAG).

    python docs/build_architecture_pdf.py
"""
from pathlib import Path

from reportlab.graphics.shapes import Drawing, Line, Polygon, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, Frame, KeepTogether, PageBreak, PageTemplate, Paragraph, Spacer,
                                Table, TableStyle)

OUT = Path(__file__).with_name("DressMe_Architecture_Agents.pdf")

OLIVE = colors.HexColor("#556B2F")
OLIVE_LIGHT = colors.HexColor("#E8EDE0")
INK = colors.HexColor("#1C1C1C")
GREY = colors.HexColor("#8C8A82")
SAND = colors.HexColor("#F0EFEA")
LINE = colors.HexColor("#CFCDC4")
LLM = colors.HexColor("#FCE8C8")      # orange-ish: LLM node
CODE = colors.HexColor("#DDE8F5")     # blue-ish: deterministic code
DATA = colors.HexColor("#E8EDE0")     # green: data / store
EXT = colors.HexColor("#EDE3F3")      # purple: external service

W = 170 * mm   # text width

base = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=base["Heading1"], fontName="Helvetica-Bold", fontSize=18, textColor=INK, spaceBefore=4, spaceAfter=8)
H2 = ParagraphStyle("H2", parent=base["Heading2"], keepWithNext=1, fontName="Helvetica-Bold", fontSize=12.5, textColor=OLIVE, spaceBefore=10, spaceAfter=5)
BODY = ParagraphStyle("B", parent=base["BodyText"], fontName="Helvetica", fontSize=9.4, leading=13.2, textColor=INK, spaceAfter=4)
SMALL = ParagraphStyle("S", parent=BODY, fontSize=8.2, leading=11, textColor=GREY)
BUL = ParagraphStyle("BUL", parent=BODY, leftIndent=11, bulletIndent=1, spaceAfter=2)
CELL = ParagraphStyle("C", parent=BODY, fontSize=8.2, leading=10.6, spaceAfter=0)
CELLB = ParagraphStyle("CB", parent=CELL, fontName="Helvetica-Bold")
CAP = ParagraphStyle("CAP", parent=SMALL, alignment=TA_CENTER, spaceBefore=2, spaceAfter=8)
CODEST = ParagraphStyle("CODE", parent=BODY, fontName="Courier", fontSize=7.8, leading=10.2, backColor=SAND, borderPadding=5,
                        leftIndent=4, rightIndent=4, spaceBefore=3, spaceAfter=8)


def P(text, style=BODY):
    return Paragraph(text, style)


def bullets(items):
    return [Paragraph(text, BUL, bulletText="•") for text in items]


def table(rows, widths, header=True):
    data = [[Paragraph(str(cell), CELLB if header and r == 0 else CELL) for cell in row] for r, row in enumerate(rows)]
    t = Table(data, colWidths=[w * mm for w in widths], repeatRows=1 if header else 0)
    style = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("GRID", (0, 0), (-1, -1), 0.4, LINE),
             ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
             ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), OLIVE_LIGHT)]
    t.setStyle(TableStyle(style))
    return t


# ----------------------------------------------------------------------------------------- diagram helpers
class Diagram:
    def __init__(self, width_mm=170, height_mm=80):
        self.w, self.h = width_mm * mm, height_mm * mm
        self.d = Drawing(self.w, self.h)

    def box(self, x, y, w, h, text, fill=CODE, size=7.6, bold=False):
        """x, y, w, h in mm from the bottom-left corner."""
        self.d.add(Rect(x * mm, y * mm, w * mm, h * mm, rx=3, ry=3, fillColor=fill, strokeColor=INK, strokeWidth=0.7))
        lines = text.split("\n")
        lead = size + 1.8
        top = y * mm + h * mm / 2 + (len(lines) - 1) * lead / 2 - size * 0.32
        for i, line in enumerate(lines):
            self.d.add(String((x + w / 2) * mm, top - i * lead, line, fontName="Helvetica-Bold" if bold or i == 0 and len(lines) > 1 else "Helvetica",
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
        size = 2.6 * mm
        left = (c - size * math.cos(angle - 0.4), d - size * math.sin(angle - 0.4))
        right = (c - size * math.cos(angle + 0.4), d - size * math.sin(angle + 0.4))
        self.d.add(Polygon([c, d, left[0], left[1], right[0], right[1]], fillColor=color, strokeColor=color, strokeWidth=0.3))

    def polyline(self, points, color=INK, dashed=False):
        for (x1, y1), (x2, y2) in zip(points, points[1:-1] + [points[-1]]):
            pass
        for i in range(len(points) - 2):
            line = Line(points[i][0] * mm, points[i][1] * mm, points[i + 1][0] * mm, points[i + 1][1] * mm, strokeColor=color, strokeWidth=0.9)
            if dashed:
                line.strokeDashArray = [3, 2]
            self.d.add(line)
        self.arrow(points[-2][0], points[-2][1], points[-1][0], points[-1][1], color, dashed)

    def legend(self, items, y=1.5):
        x = 2
        for text, fill in items:
            self.d.add(Rect(x * mm, y * mm, 4 * mm, 3 * mm, fillColor=fill, strokeColor=INK, strokeWidth=0.5))
            self.label(x + 5.5, y + 0.6, text, size=6.8, color=INK, anchor="start")
            x += 8 + len(text) * 1.9


STD_LEGEND = [("LLM", LLM), ("code deterministe", CODE), ("donnees / stockage", DATA), ("service externe", EXT)]


def diagram_overview():
    g = Diagram(170, 118)
    g.box(35, 104, 100, 10, "Interface React 19 (Vite, Tailwind)\nAI Stylist | Outfit Builder | Help Me Pack | Wardrobe | Should I buy | Dashboard", DATA, 7, True)
    cols = [(2, "BO1  :8000", "garde-robe, detecteur YOLO\nAI Stylist, Outfit Agent\nShould I buy, anti-doublon"),
            (44, "BO3  :8001", "Gap Agent\nlacunes de garde-robe\nboutiques tunisiennes"),
            (86, "Help Me Pack  :8020", "Trip Agent (LangGraph)\nsolveur OR-Tools CP-SAT"),
            (128, "RAG  :8010", "connaissance mode\n38 PDF, pgvector\nreponses citees [S#]")]
    for x, title, body in cols:
        g.box(x, 62, 40, 28, title + "\n" + body, CODE, 7)
        g.arrow(85, 104, x + 20, 90)
    g.box(2, 22, 48, 14, "OpenAI GPT-4o\n(gpt-4o-mini : Gap Agent)", LLM, 7.2)
    g.box(61, 22, 48, 14, "Open-Meteo\nmeteo et geocodage, sans cle", EXT, 7.2)
    g.box(120, 22, 48, 14, "Supabase\nauth, base items, storage, pgvector", DATA, 7.2)
    for x, _, _ in cols:
        g.arrow(x + 20, 62, 26, 36, GREY, True)
        g.arrow(x + 20, 62, 85, 36, GREY, True)
        g.arrow(x + 20, 62, 144, 36, GREY, True)
    g.arrow(148, 62, 144, 36)
    g.label(85, 12, "BO1 appelle le RAG (8010) comme outil ; l'interface appelle les 3 autres services directement.", 7.2, GREY)
    g.legend(STD_LEGEND)
    return g.d


def diagram_stylist():
    g = Diagram(170, 92)
    g.box(2, 70, 34, 14, "Question\n+ ville, pays, unite", DATA, 7.4)
    g.box(52, 66, 44, 22, "AI Stylist (GPT-4o)\ntemperature 0,3\nsortie JSON, 8 tours max", LLM, 7.4)
    g.arrow(36, 77, 52, 77)
    tools = [(116, 70, "search_wardrobe", "filtre le vrai placard", CODE),
             (116, 46, "get_weather", "Open-Meteo, cache 30 min", EXT),
             (116, 22, "fashion_advice", "RAG : livres, sources [S#]", EXT)]
    for x, y, name, desc, fill in tools:
        g.box(x, y, 52, 16, name + "\n" + desc, fill, 7.2)
        g.arrow(96, 77, x, y + 8, GREY)
        g.arrow(x, y + 5, 96, 72, GREY, True)
    g.box(2, 40, 44, 22, "Rappel unique si le modele\nsaute la meteo ou le RAG\n(regex question de style)", CODE, 7)
    g.arrow(52, 70, 46, 56, GREY, True)
    g.box(2, 8, 100, 20, "Reponse : answer | weather | outfit | why | alternatives | tips\nsources citees seulement | pieces retrouvees dans le placard reel", DATA, 7.2)
    g.arrow(74, 66, 62, 28)
    g.legend(STD_LEGEND, y=0.5)
    return g.d


def diagram_outfit():
    g = Diagram(170, 78)
    nodes = [("weather", "prevision de\nla ville", EXT), ("closet", "pieces par role\n+ faits", CODE),
             ("knowledge", "2 questions\nau RAG", EXT), ("compose", "LLM : 3 tenues\n(ids du placard)", LLM),
             ("validate", "controles\ndu code", CODE)]
    x = 2
    pos = []
    for name, body, fill in nodes:
        g.box(x, 38, 28, 22, name + "\n" + body, fill, 7.2)
        pos.append(x)
        x += 33
    g.label(1, 66, "START", 7, INK, "start", True)
    for i in range(len(nodes) - 1):
        g.arrow(pos[i] + 28, 49, pos[i + 1], 49)
    # loop validate -> compose
    g.polyline([(pos[4] + 14, 38), (pos[4] + 14, 30), (pos[3] + 14, 30), (pos[3] + 14, 38)], INK, True)
    g.label((pos[3] + pos[4]) / 2 + 14, 25.5, "erreurs : le LLM corrige (1 fois)", 7, INK)
    g.arrow(pos[4] + 14, 60, pos[4] + 14, 72, INK)
    g.label(pos[4] + 14, 74, "END : tenues valides", 7, INK, bold=True)
    g.box(2, 4, 74, 14, "Etat partage : items, occasion, saison, ville, avoid,\nforecast, closet, advice, sources, draft, problems", DATA, 6.8)
    g.legend(STD_LEGEND, y=0.4)
    return g.d


def diagram_trip():
    g = Diagram(170, 100)
    g.label(2, 94, "Graphe 1 : conversation (LangGraph)", 8, INK, "start", True)
    g.box(2, 74, 32, 14, "intake\nextraction du voyage", LLM, 7)
    g.box(48, 74, 30, 14, "plan\nsi tout est connu", CODE, 7)
    g.arrow(34, 81, 48, 81)
    g.arrow(78, 81, 92, 81)
    g.box(92, 74, 50, 14, "sinon : une question\npuis arret (END)", DATA, 7)
    g.label(2, 66, "Graphe 2 : workflow deterministe (chaque noeud s'arrete si l'etape precedente echoue)", 8, INK, "start", True)
    steps = [("weather", "Open-Meteo", EXT), ("wardrobe", "CSV + pandas", DATA), ("requirements", "regles/jour", CODE),
             ("optimize", "OR-Tools\nCP-SAT", CODE), ("finish", "checklist ou\nalternatives", CODE)]
    x = 2
    pos = []
    for name, body, fill in steps:
        g.box(x, 42, 29, 18, name + "\n" + body, fill, 7)
        pos.append(x)
        x += 34
    for i in range(len(steps) - 1):
        g.arrow(pos[i] + 29, 51, pos[i + 1], 51)
    g.label(2, 33, "Boucle d'outils GPT-4o (temperature 0, 12 iterations max) : 10 outils valides par Pydantic", 8, INK, "start", True)
    names = ["get_trip_details", "get_weather", "get_wardrobe", "get_activity_requirements", "optimize_trip",
             "generate_checklist", "suggest_alternatives", "update_trip", "update_checklist", "check_gaps"]
    for i, name in enumerate(names):
        col, row = i % 5, i // 5
        g.box(2 + col * 34, 14 - row * 11 + 4, 31, 8, name, LLM if i in (0, 7) else CODE, 6.2)
    g.legend(STD_LEGEND, y=0.4)
    return g.d


def diagram_gap():
    g = Diagram(170, 70)
    g.box(2, 44, 34, 18, "Demande\n(objectif : winter_work...)", DATA, 7)
    g.box(48, 40, 44, 26, "Gap Agent BO3\ngpt-4o-mini, temp. 0,2\n6 etapes max", LLM, 7.4)
    g.arrow(36, 53, 48, 53)
    tools = [("get_wardrobe", 104, 52), ("compute_coverage", 104, 40), ("rank_gaps (XGBoost)", 104, 28),
             ("get_past_analyses", 104, 16), ("show_items (photos)", 104, 4)]
    for name, x, y in tools:
        g.box(x, y, 62, 9, name, CODE, 7)
        g.arrow(92, 53, x, y + 4.5, GREY)
    g.box(2, 8, 80, 22, "Regles deterministes : une lacune n'existe que si la\ncouverture la signale. XGBoost ne fait qu'ordonner.\nSortie : lacunes classees + pieces deja couvertes", DATA, 7)
    g.legend(STD_LEGEND, y=0.4)
    return g.d


def diagram_rag():
    g = Diagram(170, 120)
    g.label(2, 114, "A. Ingestion (hors ligne)", 8, INK, "start", True)
    ing = ["38 PDF", "PyMuPDF\n+ OCR Tesseract", "controle qualite\n+ chunking", "embeddings\nMiniLM 384 d", "Supabase\npgvector (HNSW)"]
    x = 2
    pos = []
    for i, text in enumerate(ing):
        g.box(x, 94, 28, 15, text, DATA if i in (0, 4) else CODE, 7)
        pos.append(x)
        x += 34
    for i in range(len(ing) - 1):
        g.arrow(pos[i] + 28, 101.5, pos[i + 1], 101.5)
    g.label(2, 86, "B. Question (en ligne)", 8, INK, "start", True)
    q = [("question\n(FR ou EN)", DATA), ("traduction FR vers EN\n+ glossaire", CODE), ("recherche hybride\nvecteur + texte", CODE),
         ("fusion RRF\ntop 5 passages", CODE), ("LLM : repond avec\nsources [S#] seulement", LLM)]
    x = 2
    pos = []
    for text, fill in q:
        g.box(x, 62, 28, 18, text, fill, 6.8)
        pos.append(x)
        x += 34
    for i in range(len(q) - 1):
        g.arrow(pos[i] + 28, 71, pos[i + 1], 71)
    g.polyline([(pos[4] + 14, 62), (pos[4] + 14, 52), (pos[2] + 14, 52), (pos[2] + 14, 62)], GREY, True)
    g.label(pos[3] + 4, 54.5, "lit knowledge_chunks_v2", 6.8, GREY)
    g.box(2, 22, 78, 20, "POST /ask  ->  {answer, citations[{marker, title, page}], grounded}\nrien trouve : reponse fixe \"I don't know\"\nplus de citation : la reponse est ecartee par le client", DATA, 7)
    g.box(92, 22, 76, 20, "rag_client.advise(question)  (BO1)\nrenvoie {answer, sources, grounded} ou None\nles agents gardent les marqueurs [S1]...", CODE, 7)
    g.arrow(80, 32, 92, 32)
    g.legend(STD_LEGEND, y=8)
    return g.d


def diagram_buy():
    g = Diagram(170, 62)
    steps = [("photo de\nl'article", DATA), ("detecteur YOLO\n+ LLM vision", LLM), ("moteur d'achat :\nredondance, lacune,\ntenues possibles", CODE),
             ("XGBoost + regles\nBUY/CONSIDER/SKIP", CODE), ("LLM : 3 sections\nverdict, why, tip", LLM)]
    x = 2
    pos = []
    for text, fill in steps:
        g.box(x, 24, 29, 22, text, fill, 6.8)
        pos.append(x)
        x += 34
    for i in range(len(steps) - 1):
        g.arrow(pos[i] + 29, 35, pos[i + 1], 35)
    g.box(2, 4, 80, 12, "Garde-robe reelle de l'utilisateur (Supabase) : sert au moteur d'achat", DATA, 7)
    g.arrow(42, 16, pos[2] + 14, 24, GREY, True)
    g.box(92, 4, 76, 12, "L'application ecrit les titres ; le LLM ne donne que le texte", CODE, 7)
    g.arrow(pos[4] + 14, 24, 130, 16, GREY, True)
    g.legend(STD_LEGEND, y=-1)
    return g.d


def diagram_catalog():
    g = Diagram(170, 46)
    steps = [("photo\nvetement", DATA), ("YOLO\nsegmentation", CODE), ("couleurs mesurees\nsur les pixels", CODE),
             ("GPT-4o vision\nJSON strict", LLM), ("fiche : categorie,\ncouleur, matiere,\nsaison, occasion", DATA)]
    x = 2
    pos = []
    for text, fill in steps:
        g.box(x, 14, 29, 22, text, fill, 6.8)
        pos.append(x)
        x += 34
    for i in range(len(steps) - 1):
        g.arrow(pos[i] + 29, 25, pos[i + 1], 25)
    g.label(85, 5, "Sans cle API ou en cas d'erreur : regles de secours (fallback_enrich)", 7.2, GREY)
    return g.d



def flow(steps, notes=None, height=44, per_row=5, box_h=20, size=6.8):
    """A left-to-right chain of boxes (text, fill) with optional notes under the chain."""
    g = Diagram(170, height)
    x = 2
    pos = []
    y = height - box_h - 4
    for text, fill in steps:
        g.box(x, y, 29, box_h, text, fill, size)
        pos.append(x)
        x += 34
    for i in range(len(steps) - 1):
        g.arrow(pos[i] + 29, y + box_h / 2, pos[i + 1], y + box_h / 2)
    for i, note in enumerate(notes or []):
        g.label(2, y - 6 - i * 4.6, note, 7, GREY, "start")
    return g.d


def diagram_voice():
    return flow([("microphone\n(navigateur)", DATA), ("Web Speech API\nChrome / Edge /\nSafari", EXT), ("texte dicte\n(en direct)", CODE),
                 ("POST\n/api/agent/search", CODE), ("Agent de recherche\n(agent 1b)\nchoisit les filtres", LLM)],
                ["Transcription faite par le navigateur (Chrome et Edge utilisent leur service en ligne) : seul le texte arrive a nos serveurs.",
                 "Voix ou texte : meme chemin. Le LLM choisit les filtres, le code filtre la garde-robe, la page affiche le resultat."],
                height=40)


def diagram_live():
    return flow([("camera du\nnavigateur\n(https)", DATA), ("/api/items/\nquick-detect\ncadres en direct", CODE), ("capture\n/api/items/analyze\n(fast, regles)", CODE),
                 ("item enregistre\n(Supabase)", DATA), ("agent\nanti-doublon\n(agent 5)", LLM)],
                ["Pendant la camera : YOLO dessine les cadres et signale une photo floue ou un vetement coupe (module quality).",
                 "Apres chaque capture, l'agent decide avec search_wardrobe s'il s'agit du meme vetement scanne deux fois."],
                height=42)


def diagram_similar():
    return flow([("photo d'une\ntenue", DATA), ("/api/items/analyze\nall_items, sans\nsauvegarde", CODE), ("pieces detectees\nvs garde-robe\n(score local)", CODE),
                 ("owned / close /\nmissing", DATA), ("manquant : photos\nde boutiques TN\n(BO3) + try-on", EXT)],
                ["Aucun LLM : detecteur YOLO + comparaison par categorie, couleur, matiere et style cote interface.",
                 "Une piece manquante renvoie vers BO3 (/api/bo3/plan/photos) et vers l'essayage virtuel sur l'avatar."],
                height=40)


def diagram_dashboard():
    g = Diagram(170, 66)
    g.box(55, 52, 60, 10, "Dashboard (DashboardPage.tsx)", DATA, 7.4, True)
    boxes = [(2, "Garde-robe\n/api/items\n/api/stats/accuracy", CODE), (45, "Today's outfit\nconstructeur a regles\n(local, sans LLM)", CODE),
             (88, "Outfits to buy\n+ notifications\nBO3 /api/bo3/gaps", EXT), (131, "Gaps card, Getting\nstarted, Insights\n(statistiques)", CODE)]
    for x, text, fill in boxes:
        g.box(x, 24, 37, 20, text, fill, 6.8)
        g.arrow(85, 52, x + 18, 44)
    g.box(88, 4, 37, 12, "Gap Agent (agent 4)", LLM, 7)
    g.arrow(106, 24, 106, 16)
    g.label(2, 10, "Le dashboard appelle des services, sans agent propre.", 7, GREY, "start")
    g.label(2, 5, "Produits : boutiques tunisiennes (ddgs), sans prix.", 7, GREY, "start")
    return g.d


def diagram_features():
    """Every page, the route it calls and the agent or engine behind it."""
    g = Diagram(170, 150)
    g.label(2, 144, "Page de l'interface", 7.8, INK, "start", True)
    g.label(70, 144, "Route", 7.8, INK, "start", True)
    g.label(118, 144, "Agent / moteur", 7.8, INK, "start", True)
    rows = [("AI Stylist + voix (conseil)", "/api/agent/search", "AI Stylist (agent 1)", LLM),
            ("Wardrobe : recherche texte + voix", "/api/agent/search", "Agent de recherche (1b)", LLM),
            ("Outfit Builder", "/api/outfits/agent", "Outfit Agent LangGraph (2)", LLM),
            ("Help Me Pack", ":8020 /api/trips", "Trip Agent (3) + CP-SAT", LLM),
            ("Wardrobe Gaps / Shop Smart", ":8001 /api/bo3/*", "Gap Agent (4) + XGBoost", LLM),
            ("Live scan", "/api/items/quick-detect + /api/agent/check-duplicate", "YOLO + agent anti-doublon (5)", LLM),
            ("Should I buy this?", "/api/shopping-assistant/evaluate", "detecteur + LLM + moteur d'achat", CODE),
            ("Find Similar", "/api/items/analyze (all_items)", "YOLO + comparaison locale", CODE),
            ("Ajout / Wardrobe / 3D", "/api/items/analyze, /api/items", "YOLO + catalogage vision", CODE),
            ("Dashboard", "/api/items + :8001 gaps", "Gap Agent + regles locales", CODE),
            ("Avatar + essayage", "/api/avatar/*, tryon-outfit", "WaveSpeed / fal.ai (Bria, Hunyuan3D)", EXT)]
    y = 130
    for page, route, agent, fill in rows:
        g.box(2, y, 56, 9.5, page, DATA, 7)
        g.box(64, y, 48, 9.5, route, CODE, 5.6)
        g.box(118, y, 50, 9.5, agent, fill, 6.4)
        g.arrow(58, y + 4.7, 64, y + 4.7)
        g.arrow(112, y + 4.7, 118, y + 4.7)
        y -= 11.4
    g.legend(STD_LEGEND, y=0.5)
    return g.d

# ----------------------------------------------------------------------------------------- the document
def page_frame(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(GREY)
    canvas.drawString(20 * mm, 10 * mm, "DressMe : architecture des agents - dossier de validation technique")
    canvas.drawRightString(190 * mm, 10 * mm, f"Page {doc.page}")
    canvas.setStrokeColor(LINE)
    canvas.line(20 * mm, 14 * mm, 190 * mm, 14 * mm)
    canvas.restoreState()


def cover_page(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(OLIVE)
    canvas.rect(0, 0, A4[0], A4[1], stroke=0, fill=1)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 38)
    canvas.drawString(22 * mm, 190 * mm, "DressMe")
    canvas.setFont("Helvetica", 18)
    canvas.drawString(22 * mm, 176 * mm, "Architecture des agents IA")
    canvas.setFont("Helvetica", 11)
    for i, line in enumerate(["Dossier de validation technique",
                               "6 agents, 3 pipelines LLM, 1 RAG, 4 services, 11 ecrans",
                               "Graphes, prompts, outils, integration, garde-fous et limites"]):
        canvas.drawString(22 * mm, (160 - i * 7) * mm, line)
    canvas.setFont("Helvetica", 9)
    canvas.drawString(22 * mm, 30 * mm, "Projet de fin d'etudes - application DressMe (React, FastAPI, LangGraph, OpenAI, Supabase)")
    canvas.restoreState()


def build():
    doc = BaseDocTemplate(str(OUT), pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm, bottomMargin=20 * mm,
                          title="DressMe - Architecture des agents", author="DressMe")
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="f")
    doc.addPageTemplates([PageTemplate(id="cover", frames=[Frame(0, 0, 1, 1)], onPage=cover_page),
                          PageTemplate(id="body", frames=[frame], onPage=page_frame)])
    s = []
    from reportlab.platypus import NextPageTemplate
    s += [NextPageTemplate("body"), PageBreak()]

    # ---- 1
    s += [P("1. Vue d'ensemble", H1),
          P("DressMe est une application React 19 qui parle a <b>quatre services FastAPI</b> (BO1, BO3, Help Me Pack, RAG). "
            "Supabase fournit l'authentification, la base de donnees (garde-robe) et le stockage des images. "
            "OpenAI fournit le LLM, Open-Meteo la meteo reelle."),
          diagram_overview(), P("Figure 1 : architecture globale, services et dependances externes.", CAP),
          P("<b>Principe commun a tous les agents :</b> le LLM decide et redige, le code deterministe verifie et calcule. "
            "Aucun agent ne peut citer une piece absente de la garde-robe, inventer la meteo ou inventer une source."),
          H2_("Ports et lancement"),
          table([["Service", "Port", "Role", "Lancement"],
                 ["BO1 (backend/app)", "8000", "garde-robe, detecteur, AI Stylist, Outfit Agent, Should I buy, avatar", "start_bo1.ps1"],
                 ["BO3 (DressMe UI Blueprint/backend)", "8001", "Gap Agent, produits de boutiques tunisiennes", "start_bo3.ps1"],
                 ["Help Me Pack (backend/main.py)", "8020", "Trip Agent et solveur CP-SAT", "start_packing.ps1"],
                 ["RAG (rag_backend)", "8010", "connaissance de mode citee", "start_rag.ps1"],
                 ["Interface (Vite)", "8443", "application React (https de developpement)", "pnpm dev"]],
                [48, 14, 80, 28]),
          PageBreak()]

    # ---- 2 integration of every feature
    s += [P("2. Integration de toutes les fonctionnalites", H1),
          P("Chaque page de l'interface appelle une route ; la route appelle soit un <b>agent</b> (le LLM choisit des outils ou suit un graphe), "
            "soit un <b>moteur</b> (detecteur, moteur d'achat, comparaison locale). Le schema relie les 11 ecrans aux 6 agents et aux moteurs."),
          diagram_features(), P("Figure 2 : de chaque page a l'agent ou au moteur qui la sert.", CAP),
          P("2.1 Recherche vocale", H2), diagram_voice(), P("Figure 3 : recherche intelligente par la voix ou par le texte (agent 1b).", CAP),
          *bullets(["<b>C'est bien un agent.</b> Le texte (ecrit ou dicte) est envoye au LLM, qui choisit lui-meme les parametres de recherche "
                    "(categorie, couleur, saison, occasion, style, chaleur, texte libre), appelle l'outil <font face='Courier'>search_wardrobe</font>, "
                    "<b>regarde le resultat</b> et recommence avec d'autres filtres si c'est vide ou trop large, puis redige sa reponse.",
                    "Voix : hook <font face='Courier'>useSpeech</font> (Web Speech API du navigateur, transcription en direct) ; a la fin de la phrase le texte part comme une question ecrite.",
                    "Page Wardrobe : la grille est filtree sur les pieces trouvees et les <b>filtres choisis par le LLM</b> s'affichent en pastilles (\"jacket, warmth 4+\"). Navigateur sans l'API vocale : le bouton micro est masque.",
                    "<b>Meme code, deux usages</b> : la fonction <font face='Courier'>agent.chat</font> sert la recherche de la page Wardrobe (agent 1b : reponse courte + filtres + pieces) "
                    "et la page AI Stylist (agent 1 : conseil complet avec meteo, tenue, raisons et sources). Le prompt distingue les deux : une simple recherche recoit une phrase, sans conseil ni sections."]),
          P("2.2 Live scan", H2), diagram_live(), P("Figure 4 : scan en direct avec controle qualite et anti-doublon.", CAP),
          *bullets(["La camera exige une origine securisee (https ou localhost) : le serveur de dev peut tourner en https avec un certificat local.",
                    "<font face='Courier'>/api/items/quick-detect</font> renvoie les cadres, la couleur principale et un eventuel probleme (flou, coupe, trop petit).",
                    "La capture passe par <font face='Courier'>/api/items/analyze?fast=true</font> (classification par regles, quelques centaines de ms), puis l'agent anti-doublon decide s'il faut avertir."]),
          P("2.3 Find Similar", H2), diagram_similar(), P("Figure 5 : de la photo d'une tenue aux pieces manquantes.", CAP),
          *bullets(["Une photo de tenue est decoupee en pieces par le detecteur ; chaque piece est comparee a la garde-robe (meme categorie, couleur, matiere, style) et classee <b>You own it</b>, <b>Close match</b> ou <b>Missing</b>.",
                    "Pour une piece manquante, BO3 renvoie des photos de boutiques tunisiennes et l'utilisateur peut l'essayer sur son avatar avant d'acheter.",
                    "Difference avec Should I buy : Find Similar part d'une tenue vue ailleurs ; Should I buy part d'un seul article et rend un verdict."]),
          PageBreak(),
          P("2.4 Dashboard", H2), diagram_dashboard(), P("Figure 6 : composition du tableau de bord.", CAP),
          *bullets(["<b>Outfits to buy</b> et les notifications viennent du Gap Agent (BO3) ; le panneau memorise l'objectif choisi pour prevenir quand des lacunes changent.",
                    "<b>Today's outfit</b> utilise le constructeur a regles local (une tenue pour la saison courante) ; le Outfit Builder Agent est sur sa propre page.",
                    "Les statistiques (nombre de pieces, repartition, precision du catalogage) viennent de <font face='Courier'>/api/items</font> et <font face='Courier'>/api/stats/accuracy</font>."]),
          P("2.5 Essayage virtuel et avatar", H2),
          *bullets(["Avatar : photo en pied, puis modele 3D (Hunyuan3D v3) ; fournisseur configurable (WaveSpeed par defaut ou fal.ai, variable AVATAR_PROVIDER).",
                    "Essayage d'une tenue, d'un vetement de boutique ou d'une tenue de l'Outfit Builder : <font face='Courier'>/api/avatar/tryon-outfit</font> et <font face='Courier'>tryon-garment</font> (Bria virtual try-on), execute en tache d'arriere-plan avec suivi d'etat."]),
          PageBreak()]

    # ---- 2b tools reference
    s += [P("2.6 Services partages par les agents", H1),
          table([["Service", "Utilise par", "Role"],
                 ["Supabase (auth, items, storage)", "tous", "jeton verifie sur chaque route, garde-robe de l'utilisateur, photos et cutouts"],
                 ["OpenAI GPT-4o", "AI Stylist, Outfit Agent, Trip Agent, anti-doublon, catalogage, Should I buy", "raisonnement, redaction, vision"],
                 ["Open-Meteo", "AI Stylist, Outfit Agent, Trip Agent", "geocodage + prevision 16 jours, cache 30 min"],
                 ["RAG (8010)", "AI Stylist, Outfit Agent", "conseils de livres de mode avec sources [S#]"],
                 ["YOLO dressme_best.pt", "Wardrobe, Live scan, Find Similar, Should I buy", "detection et segmentation des vetements"],
                 ["OR-Tools CP-SAT", "Trip Agent", "choix optimal de la valise"],
                 ["XGBoost", "Gap Agent, Should I buy", "classement des lacunes, decision d'achat"],
                 ["WaveSpeed / fal.ai", "Avatar, essayage", "generation 3D et try-on"]],
                [42, 62, 66]),
          PageBreak()]

    # ---- 2
    s += [P("3. Combien d'agents ?", H1),
          P("<b>6 agents</b> (5 moteurs distincts, dont un partage entre 1 et 1b) sont appeles depuis l'interface. <b>3 pipelines</b> utilisent un LLM sans etre des agents (le LLM ne choisit pas ses outils). "
            "Une <b>pile separee de l'equipe</b> (Stylist BO4 et orchestrateur) existe aussi, non branchee a l'interface React."),
          table([["#", "Agent", "Fonctionnalite", "Technique", "Fichier"],
                 ["1", "AI Stylist", "page AI Stylist (texte et voix)", "boucle d'appel d'outils GPT-4o, 3 outils", "backend/app/agent.py"],
                 ["1b", "Agent de recherche intelligente", "recherche texte ou voix de la page Wardrobe", "meme boucle, le LLM choisit les filtres de search_wardrobe", "backend/app/agent.py (chat)"],
                 ["2", "Outfit Builder Agent", "page Outfit Builder", "graphe LangGraph, 5 noeuds", "backend/app/outfit_agent.py"],
                 ["3", "Trip Agent", "Help Me Pack", "GPT-4o, 10 outils, LangGraph (2 graphes), CP-SAT", "packing_backend/trip_agent/"],
                 ["4", "Gap Agent (BO3)", "Wardrobe Gaps, Shop Smart, Outfits to buy", "5 outils, 6 etapes max, XGBoost", "DressMe UI Blueprint/backend/agent/gap_agent.py"],
                 ["5", "Agent anti-doublon", "Live scan (camera)", "1 outil (search_wardrobe)", "backend/app/agent.py (check_duplicate)"]],
                [7, 30, 36, 50, 47]),
          Spacer(1, 8),
          table([["Pipeline LLM", "Role", "Fichier"],
                 ["Catalogage vision", "detecteur YOLO, puis GPT-4o vision (JSON strict) : categorie, couleur, matiere, saison, occasion", "backend/app/enricher.py"],
                 ["Should I buy this?", "detecteur + LLM, moteur d'achat (XGBoost + regles), puis LLM qui redige 3 sections", "smart_purchasing/inference.py"],
                 ["Reponse RAG", "recherche hybride, puis LLM qui repond uniquement avec les sources", "rag_backend/rag/rag_service.py"]],
                [34, 98, 38]),
          Spacer(1, 8),
          table([["Pile separee (non branchee a React)", "Technique"],
                 ["Stylist BO4 (bo4/)", "LangGraph a 9 noeuds, Ollama qwen2.5:3b, moteur de tenues heuristique (couleur 30, style 20, occasion 30, saison 20)"],
                 ["Orchestrateur (orchestrator/, port 8070)", "LangGraph : route_intent (regles puis LLM local) vers stylist, garde-robe, achat, RAG ou clarification"]],
                [60, 110]),
          P("LangGraph est utilise par l'Outfit Builder Agent, le Trip Agent, le Stylist BO4 et l'orchestrateur. "
            "L'AI Stylist, le Gap Agent et l'agent anti-doublon utilisent la boucle d'appel d'outils native d'OpenAI, ecrite a la main.", BODY),
          PageBreak()]

    # ---- tools by agent
    s += [P("4. Outils de chaque agent", H1),
          P("Un <b>outil</b> est une fonction que le LLM peut demander ; le code l'execute et renvoie le resultat au LLM. "
            "Le LLM ne touche jamais directement aux donnees."),
          P("4.1 AI Stylist et agent de recherche : 3 outils", H2),
          table([["Outil", "Parametres", "Retour", "Garde-fou"],
                 ["search_wardrobe", "category, category_group, color_name, season, occasion, style, pattern, min_warmth (1-5), text (choisis par le LLM, voix ou texte)", "jusqu'a 20 pieces : id, nom, categorie, couleur, matiere, saisons, style, occasions, formalite, chaleur", "valeurs d'enumeration imposees ; seuls les items de l'utilisateur"],
                 ["get_weather", "days_ahead (0 a 15), city (optionnel)", "ville, jour, condition, min/max en C et F, % de pluie, mm, vent, resume", "ville inconnue : premiers mots, puis Tunis, annoncee ; sinon \"non verifiee\""],
                 ["fashion_advice", "question (anglais, un seul sujet)", "answer + sources [{marker, title, page}]", "None si RAG arrete ou sans citation : l'agent le dit"]],
                [27, 50, 52, 41]),
          P("4.2 Outfit Builder Agent : 5 noeuds (pas d'appel d'outils)", H2),
          table([["Noeud", "Entree", "Sortie", "Type"],
                 ["weather", "ville, pays", "forecast (ou None)", "code, Open-Meteo"],
                 ["closet", "items", "closet : pieces par role avec 13 champs", "code"],
                 ["knowledge", "occasion, saison, forecast", "advice[] + sources", "RAG, 2 questions"],
                 ["compose", "brief : occasion, meteo, conseils, tenues deja vues, placard", "outfits[] {title, items[ids], weather_note, why[]}, missing[]", "GPT-4o JSON, temp. 0,6"],
                 ["validate", "outfits[] + placard", "tenues valides ou liste d'erreurs (retour a compose une fois)", "code"]],
                [22, 52, 66, 30]),
          P("4.3 Trip Agent : 10 outils (valides par Pydantic)", H2),
          table([["Outil", "Role", "Ressource"],
                 ["get_trip_details", "extrait, fusionne et valide les champs du voyage ; signale ceux qui manquent", "GPT-4o JSON + regex de secours"],
                 ["get_weather", "prevision jour par jour pour la destination et les dates (force_refresh, allow_network)", "Open-Meteo, repli synthetique etiquete"],
                 ["get_wardrobe", "charge la garde-robe (filtres category, style, limit) et la couverture des roles", "CSV + compatibilite (pandas)"],
                 ["get_activity_requirements", "traduit activites, meteo et formalite en exigences quotidiennes du solveur", "regles deterministes"],
                 ["optimize_trip", "choisit la valise : moins de pieces, plus combinables, poids minimal", "OR-Tools CP-SAT"],
                 ["generate_checklist", "cree la checklist (tout non emballe) depuis la capsule", "modeles Pydantic"],
                 ["suggest_alternatives", "diagnostique INFEASIBLE et propose des options sans relacher les contraintes", "CP-SAT + analyse des roles"],
                 ["update_trip", "modifie dates, destination, activites, tenue ou poids ; invalide l'etat obsolete ; re-optimise au choix", "etat de l'agent"],
                 ["update_checklist", "coche ou decoche une piece sans relancer le solveur", "etat de l'agent"],
                 ["check_gaps", "crochet optionnel vers le Gap Agent (peut repondre indisponible)", "fonction injectee"]],
                [36, 90, 44]),
          P("4.4 Gap Agent BO3 : 5 outils", H2),
          table([["Outil", "Parametres", "Role"],
                 ["get_wardrobe", "aucun", "profil de style + resume de chaque piece possedee"],
                 ["compute_coverage", "goal (enum des objectifs)", "exigences couvertes ou manquantes ; les regles decident si une lacune existe"],
                 ["rank_gaps", "goal", "score chaque exigence manquante (deficit, frequence d'usage, saison, gain de tenues, preference, redondance FashionCLIP) puis classe avec XGBoost ; sauvegarde l'analyse"],
                 ["get_past_analyses", "aucun", "memoire a long terme : analyses precedentes de l'utilisateur"],
                 ["show_items", "item_ids (8 max)", "affiche les pieces citees comme cartes photo a cote de la reponse"]],
                [32, 36, 102]),
          P("Le Gap Agent a une vraie <b>memoire</b> (analyses passees) et un <b>apprentissage</b> : les retours de l'utilisateur sur les suggestions reentrainent le classeur (/api/bo3/retrain).", BODY),
          P("4.5 Agent anti-doublon : 1 outil", H2),
          table([["Outil", "Parametres", "Role"],
                 ["search_wardrobe", "memes filtres que l'AI Stylist", "cherche un quasi-doublon du vetement capture ; reponse finale JSON {duplicate, similar_item_id, note}"]],
                [32, 52, 86]),
          PageBreak()]

    # ---- 3 AI Stylist
    s += [P("5. AI Stylist", H1),
          P("<b>Entree :</b> <font face='Courier'>POST /api/agent/search</font> avec message, city, country, unit. La ville du profil est utilisee, "
            "sinon <b>Tunis, Tunisie</b>. <b>Modele :</b> GPT-4o, temperature 0,3, sortie JSON, 8 tours maximum."),
          diagram_stylist(), P("Figure 2 : boucle d'outils de l'AI Stylist.", CAP),
          H2_("Outils"),
          table([["Outil", "Ce qu'il fait", "Source"],
                 ["search_wardrobe", "filtre la vraie garde-robe (categorie, couleur, saison, occasion, style, chaleur, texte)", "table items (Supabase)"],
                 ["get_weather", "prevision du jour voulu (aujourd'hui, demain, \"vendredi\"), en C ou F, 30 min de cache", "Open-Meteo"],
                 ["fashion_advice", "une question de style par sujet (jusqu'a 3), reponse avec [S#]", "RAG (8010)"]],
                [34, 96, 40]),
          H2_("Prompt systeme (regles)"),
          *bullets(["Toujours appeler <b>search_wardrobe</b> avant de repondre ; ne parler que de pieces possedees ; si rien ne convient, le dire.",
                    "<b>Meteo</b> : pour toute question \"que porter / quelle tenue\", appeler get_weather pour le jour voulu et citer les chiffres reels.",
                    "<b>Livres</b> : pour toute question de style, appeler fashion_advice une fois par sujet (code vestimentaire, couleurs, tissus du climat).",
                    "Ne jamais presenter un conseil de livre comme venant du placard ; ne jamais inventer de source.",
                    "Position claire et convaincante : \"My pick: ...\" seulement pour une demande de conseil."]),
          H2_("Format de reponse final (JSON, sans markdown ni emoji)"),
          table([["Cle", "Contenu"],
                 ["answer", "2 phrases : le choix puis la meilleure raison"],
                 ["weather", "1 a 2 phrases : prevision chiffree et ce qu'elle impose"],
                 ["outfit", "0 a 3 tenues, noms exacts des pieces reliees par \" + \""],
                 ["why", "4 a 6 raisons : meteo, occasion, couleurs, matieres, role des pieces ; chacune appuyee sur un fait reel et un [S#]"],
                 ["alternatives", "0 a 3 lignes : ce qui a ete envisage et pourquoi ecarte"],
                 ["tips", "2 a 3 conseils pratiques, avec [S#] quand ils viennent des livres"]],
                [28, 142]),
          H2_("Garde-fous"),
          *bullets(["Rappel unique si le modele saute la meteo ou le RAG sur une question qui les demande (detection par expression reguliere FR/EN).",
                    "Seules les sources reellement citees dans le texte sont renvoyees ; les pieces de la tenue sont retrouvees par leur nom dans le placard.",
                    "Ville inconnue du service meteo : essai sur les premiers mots du nom, sinon meteo de Tunis annoncee comme telle.",
                    "RAG ou meteo en panne : l'agent repond sans eux et le dit."]),
          PageBreak()]

    # ---- 4 Outfit
    s += [P("6. Outfit Builder Agent (LangGraph)", H1),
          P("Route <font face='Courier'>POST /api/outfits/agent</font> (occasion, saison, ville, tenues deja montrees). "
            "Un graphe d'etat partage ou chaque noeud a un seul travail ; le LLM n'intervient que ou le jugement est necessaire."),
          diagram_outfit(), P("Figure 3 : graphe LangGraph de l'Outfit Builder.", CAP),
          table([["Noeud", "Role", "LLM"],
                 ["weather", "prevision reelle de la ville (Tunis par defaut)", "non"],
                 ["closet", "pieces classees par role : hauts, bas, robes, vestes, chaussures, avec couleur, matiere, saison, chaleur, formalite", "non"],
                 ["knowledge", "2 questions au RAG : code vestimentaire de l'occasion ; couleurs et tissus pour le climat du jour", "RAG"],
                 ["compose", "construit 3 tenues avec les identifiants du placard, donne un titre, une note meteo chiffree et 3 a 5 raisons", "GPT-4o, JSON"],
                 ["validate", "ids reels ; robe seule ou haut + bas ; chaussures ; pas deux pieces du meme role ; veste s'il fait froid ou pluvieux", "non"]],
                [24, 128, 18]),
          H2_("Boucle de correction"),
          P("Si une tenue est invalide, le LLM est renvoye <b>une seule fois</b> avec la liste exacte des erreurs (\"Outfit 2: it has no shoes\"). "
            "Seules les tenues valides sont retournees. Le bouton Shuffle envoie les tenues deja vues (<font face='Courier'>avoid</font>) pour en obtenir d'autres."),
          H2_("Interface et repli"),
          *bullets(["Bandeau meteo, titre de chaque look, phrase \"Weather\", liste \"Why this outfit\", bouton essayage virtuel, livres cites.",
                    "Si l'agent est indisponible, l'ancien constructeur a regles (<font face='Courier'>outfitBuilder.ts</font>) prend le relais : la page affiche toujours quelque chose.",
                    "Les pieces manquantes (\"a rain jacket\") ne sont signalees que si les conditions le justifient."]),
          PageBreak()]

    # ---- 5 Trip
    s += [P("7. Trip Agent : Help Me Pack", H1),
          P("<b>Modele :</b> GPT-4o, temperature 0, appel d'outils natif, 12 iterations maximum. Le LLM choisit l'outil suivant ; "
            "le code valide les arguments (Pydantic), impose les dependances et calcule la valise avec <b>OR-Tools CP-SAT</b>."),
          diagram_trip(), P("Figure 4 : deux graphes LangGraph et les 10 outils du Trip Agent.", CAP),
          H2_("Memoire"),
          table([["Type", "Contenu", "Duree"],
                 ["Travail", "AgentState : voyage valide, meteo, placard, exigences, resultat du solveur, capsule, checklist, erreurs", "une session"],
                 ["Conversation", "16 derniers messages injectes dans le prompt", "une session"],
                 ["Session", "instance de l'agent par session_id, protegee par un verrou", "jusqu'au redemarrage"],
                 ["Client", "session_id dans le localStorage pour reprendre apres un rafraichissement", "navigateur"]],
                [28, 112, 30]),
          H2_("Regles du prompt (10)"),
          *bullets(["Ne jamais inventer destination, dates, duree, activites, limite de bagage, meteo, pieces ni resultat du solveur.",
                    "Voyage nouveau : get_trip_details d'abord ; s'il manque un champ, poser UNE question concise et s'arreter.",
                    "Ordre : get_weather, get_wardrobe (une fois), get_activity_requirements, optimize_trip, puis generate_checklist.",
                    "INFEASIBLE : suggest_alternatives ; ne jamais relacher silencieusement une contrainte dure.",
                    "update_trip seulement pour modifier un voyage ; update_checklist pour cocher sans relancer le solveur.",
                    "Une erreur d'outil se corrige ou s'explique, jamais un succes fabrique."]),
          PageBreak()]

    # ---- 6 Gap
    s += [P("8. Gap Agent BO3 et boutiques tunisiennes", H1),
          P("<b>Modele :</b> gpt-4o-mini par defaut, temperature 0,2, 6 etapes maximum. Il repond a \"que manque-t-il dans ma garde-robe pour tel objectif ?\" "
            "uniquement a partir des resultats d'outils."),
          diagram_gap(), P("Figure 5 : Gap Agent et ses 5 outils.", CAP),
          *bullets(["<b>Couverture</b> : regles deterministes par objectif et saison. Une lacune n'est reelle que si ces regles la signalent.",
                    "<b>XGBoost</b> ordonne les lacunes ; son score n'est pas une probabilite, et il est entraine sur des donnees synthetiques tant qu'il n'y a pas de retours reels (le prompt le fait dire).",
                    "<b>Departement</b> (femme, homme) : jamais de piece d'un autre departement ; jamais de genre devine.",
                    "<b>Aval</b> : les lacunes alimentent \"Outfits to buy\" du tableau de bord, avec des produits de boutiques tunisiennes (recherche d'images ddgs) et l'essayage virtuel.",
                    "Reponse dans la langue de l'utilisateur (anglais, francais, arabe tunisien)."]),
          H2_("Agent anti-doublon (Live scan)"),
          P("Apres chaque capture camera, GPT-4o (temperature 0,1, 250 tokens) appelle <font face='Courier'>search_wardrobe</font> pour decider s'il s'agit du <b>meme</b> vetement "
            "scanne deux fois, et non d'\"un autre t-shirt marine\". Reponse JSON : duplicate, similar_item_id, note."),
          PageBreak()]

    # ---- 7 pipelines
    s += [P("9. Pipelines assistes par LLM", H1),
          H2_("9.1 Catalogage d'un vetement"),
          diagram_catalog(), P("Figure 6 : de la photo a la fiche vetement.", CAP),
          P("GPT-4o ne change la categorie du detecteur que si l'image le montre clairement ; la couleur est choisie dans la palette la plus proche de la mesure sur les pixels ; "
            "les scores de confiance doivent etre honnetes (bas si l'image est ambigue)."),
          H2_("9.2 Should I buy this?"),
          diagram_buy(), P("Figure 7 : de la photo a la reponse en trois zones.", CAP),
          *bullets(["L'article est reconnu par le <b>meme</b> detecteur + LLM que le placard : pas de second moteur de vision.",
                    "Le moteur d'achat calcule redondance, lacune comblee, tenues possibles avec les pieces possedees et prix par tenue.",
                    "Le LLM (temperature 0,5) ne redige que trois sections : <b>verdict</b> (\"Yes, buy it:\", \"Think twice:\", \"Skip it:\" + raison), "
                    "<b>why_it_works</b> (3 phrases avec un fait : nombre de tenues, nom d'une piece possedee, prix) et <b>final_advice</b>.",
                    "Le prompt interdit le jargon (XGBoost, score, redondance), les emojis, le markdown et les symboles monetaires ; l'application ecrit les titres en gras."]),
          PageBreak()]

    # ---- 8 RAG
    s += [P("10. Le RAG : connaissance de mode citee", H1),
          diagram_rag(), P("Figure 8 : ingestion et interrogation du RAG.", CAP),
          table([["Element", "Detail"],
                 ["Corpus", "38 PDF (couleurs, tissus, codes vestimentaires, capsules, accessoires...), OCR Tesseract pour les livres scannes"],
                 ["Index", "table knowledge_chunks_v2 (Supabase Postgres + pgvector, HNSW, cosinus), 384 dimensions, all-MiniLM-L6-v2"],
                 ["Recherche", "hybride : vecteurs + recherche plein texte Postgres, fusion RRF, top 5 passages"],
                 ["Question", "francais traduit en anglais (glossaire), anglais inchange"],
                 ["Generation", "repond UNIQUEMENT avec les sources numerotees ; chaque puce finit par [S#] ; sinon la reponse fixe \"I don't know\""],
                 ["API", "POST /ask, /ask/stream (SSE), cle d'API, limitation de debit, historique de conversation"]],
                [28, 142]),
          H2_("Integration dans les agents"),
          *bullets(["<font face='Courier'>rag_client.advise(question)</font> appelle /ask et renvoie {answer, sources:[{marker, title, page}], grounded}, ou None si le service est arrete, vide ou sans citation.",
                    "L'AI Stylist l'expose comme outil <b>fashion_advice</b> ; l'Outfit Agent l'appelle dans le noeud <b>knowledge</b>.",
                    "Les agents gardent les marqueurs [S#] dans leurs phrases ; l'interface les affiche en badges (survol : livre et page) et liste les livres sous \"From fashion books\".",
                    "Le RAG ne connait pas le placard : c'est l'agent qui fait le lien entre la regle du livre et les pieces reelles."]),
          PageBreak()]

    # ---- 9 matrix
    s += [P("11. Qui utilise quoi", H1),
          table([["Fonctionnalite", "Agent / pipeline", "Meteo", "RAG", "Placard", "Solveur / ML"],
                 ["AI Stylist", "AI Stylist", "oui", "oui", "oui", "non"],
                 ["Outfit Builder", "Outfit Builder Agent", "oui", "oui", "oui", "non"],
                 ["Help Me Pack", "Trip Agent", "oui", "hook prevu", "oui", "OR-Tools CP-SAT"],
                 ["Wardrobe Gaps, Shop Smart, Outfits to buy", "Gap Agent", "non", "non", "oui", "regles + XGBoost"],
                 ["Should I buy this?", "pipeline detecteur + LLM + moteur d'achat", "non", "non", "oui", "XGBoost"],
                 ["Live scan", "detecteur + agent anti-doublon", "non", "non", "oui", "YOLO"],
                 ["Ajout d'un vetement", "detecteur + catalogage vision", "non", "non", "non", "YOLO"]],
                [42, 46, 14, 16, 16, 36]),
          H2_("Prompts : parametres LLM par composant"),
          table([["Composant", "Modele", "Temperature", "Sortie", "Limite"],
                 ["AI Stylist", "GPT-4o", "0,3", "JSON", "8 tours, 1800 tokens"],
                 ["Outfit Agent (compose)", "GPT-4o", "0,6", "JSON", "2 passes max, 2200 tokens"],
                 ["Trip Agent", "GPT-4o", "0", "outils + JSON", "12 iterations"],
                 ["Gap Agent", "gpt-4o-mini", "0,2", "Markdown", "6 etapes"],
                 ["Anti-doublon", "GPT-4o", "0,1", "JSON", "250 tokens"],
                 ["Should I buy (rédaction)", "GPT-4o", "0,5", "JSON 3 sections", "-"],
                 ["Catalogage vision", "GPT-4o", "-", "schema JSON strict", "-"]],
                [46, 26, 24, 36, 38]),
          Spacer(1, 6),
          H2_("Cycle d'une requete (exemple : \"Que mettre demain pour un diner ?\")"),
          *bullets(["1. React envoie message + ville + unite du profil a BO1.",
                    "2. L'AI Stylist appelle get_weather (demain), search_wardrobe (saison, occasion) puis fashion_advice (code vestimentaire, couleurs).",
                    "3. GPT-4o redige le JSON : choix, meteo chiffree, tenue, 4 a 6 raisons, alternatives, conseils.",
                    "4. BO1 filtre les sources citees, retrouve les pieces dans le placard et renvoie la reponse + la prevision.",
                    "5. React affiche les zones Weather, Outfit idea (photos), Why I chose this, What else I considered, Tips, From fashion books."]),
          PageBreak()]

    # ---- 10 guardrails
    s += [P("12. Garde-fous, securite et tests", H1),
          table([["Theme", "Mesure"],
                 ["Ancrage", "identifiants du placard seulement ; outils en lecture ; sources numerotees ; meteo reelle ; \"never invent\" dans chaque prompt"],
                 ["Validation par du code", "Outfit Agent (regles de composition), Trip Agent (Pydantic + solveur), AI Stylist (filtrage des sources citees)"],
                 ["Degradation douce", "RAG, meteo ou LLM indisponibles : reponse partielle ou repli par regles, jamais une page cassee"],
                 ["Securite", "jeton Supabase verifie sur chaque route ; chaque utilisateur ne voit que son placard ; cles API cote serveur uniquement ; limitation de debit du RAG"],
                 ["Honnetete", "le prompt du Gap Agent dit que le classeur est entraine sur des donnees synthetiques ; le RAG repond \"I don't know\" plutot que d'inventer"],
                 ["Tests", "85 tests backend (faux LLM, faux RAG, faux service meteo), 30 tests frontend, tests du moteur d'achat et du Trip Agent ; essais reels de bout en bout avec GPT-4o, le RAG et Open-Meteo"]],
                [34, 136]),
          H2_("Limites assumees"),
          *bullets(["Le RAG ne connait pas le placard de l'utilisateur ; il ne contient que des livres de mode.",
                    "Le classeur XGBoost du Gap Agent est entraine sur des donnees synthetiques jusqu'a l'arrivee de retours reels.",
                    "L'AI Stylist n'a pas de memoire entre deux messages ; la memoire du Trip Agent est en memoire serveur (perdue au redemarrage).",
                    "Le Stylist BO4 et l'orchestrateur LangGraph ne sont pas encore relies a l'interface React.",
                    "La meteo est celle d'un jour (jusqu'a 15 jours) pour une seule ville.",
                    "Pistes : memoire de preferences par utilisateur, journal de ce qui est porte, protocole A2A entre agents, migration de l'AI Stylist vers LangGraph."])]

    doc.build(s)
    print("written", OUT)


def H2_(text):
    return Paragraph(text, H2)


if __name__ == "__main__":
    build()
