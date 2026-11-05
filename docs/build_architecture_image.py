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
PANEL = colors.HexColor("#F7F6F1")
ORCH = colors.HexColor("#F9D9A0")
LEGEND = [("LLM / agent", LLM), ("orchestrateur", ORCH), ("code deterministe", CODE), ("donnees", DATA), ("service externe", EXT)]


class Canvas(Diagram):
    def panel(self, x, y, w, h, title):
        self.d.add(Rect(x * mm, y * mm, w * mm, h * mm, rx=4, ry=4, fillColor=PANEL, strokeColor=GREY, strokeWidth=0.8))
        self.label(x + 2.5, y + h - 4.6, title, 8, OLIVE, "start", True)


def build() -> None:
    g = Canvas(320, 226)
    g.label(160, 219.5, "DressMe : architecture des agents", 14, INK, "middle", True)

    # --- interface and orchestrator
    g.box(5, 198, 310, 16, "Interface React 19 (Vite, Tailwind)\nDashboard | Wardrobe (recherche, voix, Live scan, 3D) | Find Similar | Should I buy | "
          "AI Stylist = l'assistant (voix) | Outfit Builder | Help Me Pack | Gaps / Shop Smart | Avatar", DATA, 7.0)
    g.arrow(160, 198, 160, 192)
    g.box(5, 170, 310, 22, "ORCHESTRATEUR (LangGraph, dans BO1) : POST /api/assistant/chat\n"
          "route : GPT-4o (JSON, agents autorises seulement) + regles FR/EN en secours  >  delegue a l'agent  >  respond\n"
          "memoire de la conversation (checkpointer) : une question ouverte (valise, correction a confirmer) est continuee par le meme agent", ORCH, 7.0)

    # --- three services with their agents
    g.panel(5, 98, 203, 68, "BO1 :8000 (FastAPI)")
    g.panel(212, 98, 52, 68, "Help Me Pack :8020")
    g.panel(268, 98, 47, 68, "BO3 :8001")
    g.arrow(105, 170, 105, 166)
    g.arrow(238, 170, 238, 166, OLIVE)
    g.arrow(291, 170, 291, 166, OLIVE)
    g.label(125, 167.2, "appel direct", 6, GREY, "start")
    g.label(246, 167.2, "A2A", 6, OLIVE, "start", True)

    agents = [(8, "Outfit Builder\nLangGraph 5 noeuds\nweather > closet\n> knowledge > compose\n> validate"),
              (48, "AI Stylist\nGPT-4o, JSON\nask_wardrobe_agent\nget_weather\nfashion_advice (RAG)"),
              (88, "Wardrobe Agent\ngate > apply | cancel\n| assist\nsearch, find_similar\nstats, update_item\n(propose, oui requis)"),
              (128, "Similar Agent\nask_wardrobe_agent\npar piece detectee\nowned | close |\nmissing + raison"),
              (168, "Purchase Agent\nQwen2.5-3B + LoRA\n(Hugging Face)\n5 outils d'achat\nverdict JSON")]
    for x, text in agents:
        g.box(x, 118, 37, 40, text, LLM, 5.9)
    g.box(215, 118, 46, 40, "Trip Agent\nGPT-4o, 10 outils\n2 graphes LangGraph\nweather > wardrobe\n> requirements\n> optimize > finish", LLM, 5.9)
    g.box(271, 118, 41, 40, "Gap Agent\ngpt-4o-mini\n5 outils\nrank_gaps (XGBoost)\nmemoire +\napprentissage", LLM, 5.9)

    # agents ask the Wardrobe Agent
    g.arrow(85, 138, 88, 138, INK)
    g.arrow(128, 138, 125, 138, INK)
    g.label(106, 114.2, "AI Stylist et Similar Agent demandent le placard au Wardrobe Agent (agent a agent)", 6.0, GREY)
    g.label(238, 114.2, "lit le placard (A2A)", 5.8, GREY)
    g.arrow(261, 132, 271, 132, OLIVE)
    g.label(266, 135.5, "A2A", 6.0, OLIVE, "middle", True)

    # engines
    g.box(8, 101, 62, 10, "YOLO + catalogage GPT-4o vision", CODE, 6.2)
    g.box(73, 101, 70, 10, "GPT-4o : ecrit le conseil du verdict, ne decide pas", EXT, 6.0)
    g.box(146, 101, 59, 10, "Avatar, try-on : WaveSpeed / fal.ai", EXT, 6.0)
    g.box(215, 101, 46, 10, "OR-Tools CP-SAT", CODE, 6.2)
    g.box(271, 101, 41, 10, "XGBoost + photos TN", CODE, 6.0)

    # --- A2A bus
    g.d.add(Rect(5 * mm, 80 * mm, 310 * mm, 11 * mm, rx=3, ry=3, fillColor=OLIVE, strokeColor=INK, strokeWidth=0.8))
    g.d.add(String(160 * mm, 85.3 * mm, "Protocole A2A (Agent2Agent 0.3) : cartes d'agent /.well-known/agent-card.json  |  JSON-RPC message/send, tasks/get  |  jeton Supabase",
                   fontName="Helvetica-Bold", fontSize=7.4, fillColor=colors.white, textAnchor="middle"))
    for x in (105, 238, 291):
        g.arrow(x, 98, x, 91, OLIVE)

    # --- shared services
    g.panel(5, 6, 310, 68, "Briques partagees")
    g.box(9, 38, 72, 25, "agent_kit/tool_loop.py\nLangGraph : llm > tools > llm\n+ rappel (nudge) + fin\nutilisee par tous les agents", DATA, 6.8)
    g.box(86, 38, 52, 25, "OpenAI GPT-4o\nraisonnement, redaction,\nvision (catalogage)", LLM, 6.8)
    g.box(143, 38, 50, 25, "Open-Meteo\nmeteo + geocodage\n(sans cle, cache 30 min)", EXT, 6.8)
    g.box(198, 38, 62, 25, "RAG :8010\n38 PDF, pgvector, hybride\nreponses citees [S#]", EXT, 6.8)
    g.box(265, 38, 46, 25, "Supabase\nauth, base items,\nstorage, pgvector", DATA, 6.8)
    g.label(160, 28, "Chaque agent : le LLM decide et redige, le code valide et calcule. Les ecritures exigent la confirmation de l'utilisateur.", 7, INK, "middle", True)
    g.label(160, 22, "Les autres ecrans appellent aussi leur agent directement (REST). Qwen : repli deterministe sans HF_TOKEN ou sans modele.", 6.6, GREY)
    g.label(160, 16.5, "Trait noir : appel direct | vert : appel A2A entre services | Trip Agent et Gap Agent lisent le placard par A2A (repli REST / Supabase)", 6.6, GREY)
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
