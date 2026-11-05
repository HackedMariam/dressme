"""One picture of the whole DressMe architecture: interface, orchestrator, A2A, agents, engines, shared services.

    python docs/build_architecture_image.py      ->  docs/DressMe_Architecture.png (and .pdf)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pypdfium2 as pdfium
from reportlab.graphics import renderPDF
from reportlab.graphics.shapes import Rect, String
from reportlab.lib import colors
from reportlab.lib.units import mm

from build_architecture_pdf import CODE, DATA, EXT, GREY, INK, LLM, OLIVE, Diagram

OUT = Path(__file__).with_name("DressMe_Architecture")
AMBER = colors.HexColor("#FFF1C9")
PANEL = colors.HexColor("#F7F6F1")
LEGEND = [("LLM / agent", LLM), ("code deterministe", CODE), ("donnees", DATA), ("service externe", EXT)]


class Canvas(Diagram):
    def panel(self, x, y, w, h, title):
        self.d.add(Rect(x * mm, y * mm, w * mm, h * mm, rx=4, ry=4, fillColor=PANEL, strokeColor=GREY, strokeWidth=0.8))
        self.label(x + 2.5, y + h - 4.6, title, 8, OLIVE, "start", True)

    def dashed_box(self, x, y, w, h, text, fill=AMBER, size=7.0):
        before = len(self.d.contents)
        self.box(x, y, w, h, text, fill, size)
        self.d.contents[before].strokeDashArray = [3, 2]


def build() -> None:
    g = Canvas(320, 214)
    g.label(160, 207.5, "DressMe : architecture des agents", 14, INK, "middle", True)

    # --- interface and orchestrator
    g.box(5, 186, 241, 17, "Interface React 19 (Vite, Tailwind)\nDashboard | Wardrobe (recherche, voix, Live scan, 3D) | Find Similar | Should I buy | "
          "AI Stylist (voix) | Outfit Builder | Help Me Pack | Gaps / Shop Smart | Avatar", DATA, 7.0)
    g.dashed_box(250, 186, 65, 17, "Orchestrateur (cible)\nclient A2A : lit les cartes,\ndelegue. Existant non branche :\norchestrator/ :8070")
    g.arrow(246, 194.5, 250, 194.5, GREY, True)

    # --- three services with their agents
    g.panel(5, 100, 155, 80, "BO1 :8000 (FastAPI)")
    g.panel(164, 100, 68, 80, "Help Me Pack :8020")
    g.panel(236, 100, 79, 80, "BO3 :8001")
    for x in (82, 198, 240):
        g.arrow(x, 186, x, 180)
    g.label(120, 182.2, "appels REST directs depuis l'interface", 6.2, GREY)

    g.box(8, 124, 47, 49, "Outfit Builder\nLangGraph 5 noeuds\nweather > closet\n> knowledge (RAG)\n> compose (LLM)\n> validate (code)\n3 tenues valides", LLM, 6.4)
    g.box(58, 124, 47, 49, "AI Stylist\nGPT-4o, JSON\nboucle llm / tools\n+ rappel unique\nsearch_wardrobe\nget_weather\nfashion_advice (RAG)", LLM, 6.4)
    g.box(108, 124, 48, 49, "Wardrobe Agent\ngate > apply | cancel\n| assist (outils)\nsearch_wardrobe\nfind_similar\nwardrobe_stats\nupdate_item = propose", LLM, 6.4)
    g.box(167, 124, 62, 49, "Trip Agent\nGPT-4o, 10 outils\n2 graphes LangGraph\nweather > wardrobe >\nrequirements > optimize\n> finish\nchecklist, alternatives", LLM, 6.4)
    g.box(240, 124, 71, 49, "Gap Agent\ngpt-4o-mini, 5 outils\nboucle llm / tools\ncompute_coverage\nrank_gaps (XGBoost)\nmemoire des analyses\nretours = reentrainement", LLM, 6.4)

    # communication between agents
    g.arrow(105, 148, 108, 148, INK)
    g.arrow(167, 150, 156, 150, OLIVE)
    g.label(161.5, 153.5, "A2A", 6.2, OLIVE, "middle", True)
    g.arrow(229, 138, 240, 138, OLIVE)
    g.label(234.5, 141.5, "A2A", 6.2, OLIVE, "middle", True)
    g.label(82, 121, "Outfit Builder et AI Stylist lisent le placard par le Wardrobe Agent", 6.0, GREY)
    g.label(198, 121, "lit le placard (A2A), demande les lacunes (A2A)", 5.8, GREY)
    g.label(275, 121, "alimente Outfits to buy", 6.2, GREY)

    # engines inside each service
    g.box(8, 104, 47, 13, "YOLO + catalogage\nGPT-4o vision", CODE, 6.2)
    g.box(58, 104, 47, 13, "Should I buy : detecteur\n+ LLM + XGBoost", CODE, 6.2)
    g.box(108, 104, 48, 13, "Avatar et try-on\nWaveSpeed / fal.ai", EXT, 6.2)
    g.box(167, 104, 62, 13, "OR-Tools CP-SAT\n(valise optimale)", CODE, 6.2)
    g.box(240, 104, 71, 13, "XGBoost ranker\n+ photos boutiques TN", CODE, 6.2)

    # --- A2A bus
    g.d.add(Rect(5 * mm, 80 * mm, 310 * mm, 11 * mm, rx=3, ry=3, fillColor=OLIVE, strokeColor=INK, strokeWidth=0.8))
    g.d.add(String(160 * mm, 85.3 * mm, "Protocole A2A (Agent2Agent 0.3) : cartes d'agent /.well-known/agent-card.json  |  JSON-RPC message/send, tasks/get  |  jeton Supabase",
                   fontName="Helvetica-Bold", fontSize=7.4, fillColor=colors.white, textAnchor="middle"))
    for x in (82, 198, 275):
        g.arrow(x, 100, x, 91, OLIVE)
    g.polyline([(283, 186), (283, 183), (318, 183), (318, 85.5), (315, 85.5)], GREY, True)

    # --- shared services
    g.panel(5, 6, 310, 68, "Briques partagees")
    g.box(9, 38, 72, 25, "agent_kit/tool_loop.py\nLangGraph : llm > tools > llm\n+ rappel (nudge) + fin\nutilisee par tous les agents", DATA, 6.8)
    g.box(86, 38, 52, 25, "OpenAI GPT-4o\nraisonnement, redaction,\nvision (catalogage)", LLM, 6.8)
    g.box(143, 38, 50, 25, "Open-Meteo\nmeteo + geocodage\n(sans cle, cache 30 min)", EXT, 6.8)
    g.box(198, 38, 62, 25, "RAG :8010\n38 PDF, pgvector, hybride\nreponses citees [S#]", EXT, 6.8)
    g.box(265, 38, 46, 25, "Supabase\nauth, base items,\nstorage, pgvector", DATA, 6.8)
    g.label(160, 28, "Chaque agent : le LLM decide et redige, le code valide et calcule. Les ecritures exigent la confirmation de l'utilisateur.", 7, INK, "middle", True)
    g.label(160, 22, "Lecture du placard : tous passent par le Wardrobe Agent (Trip Agent par A2A, avec repli BO1 ; le Gap Agent lit encore Supabase seul).", 6.6, GREY)
    g.label(160, 16.5, "Trait plein : appel direct | pointille : cible ou non branche | vert : appel A2A entre agents", 6.6, GREY)
    x = 9
    for text, fill in LEGEND:
        g.d.add(Rect(x * mm, 9 * mm, 4 * mm, 3 * mm, fillColor=fill, strokeColor=INK, strokeWidth=0.5))
        g.label(x + 5.5, 9.6, text, 6.8, INK, "start")
        x += 8 + len(text) * 1.9

    pdf_path = OUT.with_suffix(".pdf")
    renderPDF.drawToFile(g.d, str(pdf_path))
    page = pdfium.PdfDocument(str(pdf_path))[0]
    page.render(scale=3.2).to_pil().save(OUT.with_suffix(".png"))
    print("written", OUT.with_suffix(".png"))


if __name__ == "__main__":
    build()
