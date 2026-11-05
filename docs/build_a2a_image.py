"""One picture of the A2A layer: which agents publish a card and who calls whom.

    python docs/build_a2a_image.py      ->  docs/DressMe_A2A.png (and .pdf)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pypdfium2 as pdfium
from reportlab.graphics import renderPDF

from build_architecture_image import Canvas, ORCH
from build_architecture_pdf import DATA, GREY, INK, LLM, OLIVE

OUT = Path(__file__).with_name("DressMe_A2A")


def build() -> None:
    g = Canvas(320, 212)
    g.label(160, 204, "DressMe : les agents A2A", 14, INK, "middle", True)

    # --- how it works
    g.box(5, 176, 310, 22, "A2A en 3 temps\n1. la carte : GET /a2a/<agent>/.well-known/agent-card.json (qui est l'agent, que sait-il faire)     "
          "2. la tache : POST /a2a/<agent> {message/send} + le jeton de l'utilisateur\n"
          "3. le resultat : completed | input-required (l'agent pose une question) | failed, avec un texte et des donnees", DATA, 6.8)

    # --- clients and servers
    g.box(105, 140, 110, 28, "Orchestrateur (client)\nchoisit l'agent, delegue\npage AI Stylist : POST /api/assistant/chat", ORCH, 6.8)
    g.box(8, 94, 92, 36, "Trip Agent  :8020\ncarte /a2a/trip\nvalise, checklist\n(serveur ET client)", LLM, 6.8)
    g.box(220, 94, 92, 36, "Gap Agent  :8001\ncarte /a2a/gap\nlacunes de garde-robe\n(serveur ET client)", LLM, 6.8)

    g.panel(5, 8, 310, 76, "BO1 :8000 : 4 agents, chacun avec sa carte A2A")
    g.box(10, 14, 62, 44, "Similar Agent\n/a2a/similar\nowned | close | missing", LLM, 6.8)
    g.box(78, 14, 62, 44, "Outfit Builder\n/a2a/outfit\ntenues validees", LLM, 6.8)
    g.box(146, 14, 90, 44, "Wardrobe Agent\n/a2a/wardrobe\nlist | ask | search\ncorrection avec ton oui", LLM, 6.8)
    g.box(242, 14, 66, 44, "AI Stylist\n/a2a/stylist\nconseil de style", LLM, 6.8)

    # --- A2A calls
    g.arrow(120, 140, 75, 130, OLIVE)                       # orchestrator -> trip
    g.label(86, 138.5, "A2A", 6.4, OLIVE, "middle", True)
    g.arrow(200, 140, 245, 130, OLIVE)                      # orchestrator -> gap
    g.label(234, 138.5, "A2A", 6.4, OLIVE, "middle", True)
    g.arrow(100, 112, 220, 112, OLIVE)                      # trip -> gap
    g.label(130, 115, "A2A : check_gaps", 6.4, OLIVE, "middle", True)
    g.arrow(160, 140, 160, 84, GREY, True)                  # orchestrator -> BO1 agents (direct)
    g.label(172, 126, "appel direct", 6.2, GREY, "middle")
    g.polyline([(70, 94), (70, 76), (182, 76), (182, 58)], OLIVE)       # trip -> wardrobe
    g.label(126, 77.6, "A2A : list", 6.4, OLIVE, "middle", True)
    g.polyline([(262, 94), (262, 76), (198, 76), (198, 58)], OLIVE)     # gap -> wardrobe
    g.label(236, 77.6, "A2A : list", 6.4, OLIVE, "middle", True)
    g.polyline([(41, 58), (41, 64), (150, 64), (150, 58)], OLIVE)       # similar -> wardrobe (A2A inside BO1)
    g.polyline([(109, 58), (109, 69), (165, 69), (165, 58)], OLIVE)     # outfit -> wardrobe
    g.polyline([(275, 58), (275, 64), (215, 64), (215, 58)], OLIVE)     # stylist -> wardrobe
    g.label(78, 71.5, "A2A : list / ask (meme dans BO1)", 6.2, OLIVE, "middle", True)

    # --- notes
    g.label(160, 3.6, "Chaque appel emporte le jeton Supabase de l'utilisateur : l'agent qui recoit le verifie et ne repond que pour lui. "
            "Pas de streaming ni de notifications push.", 6.4, GREY)

    pdf_path = OUT.with_suffix(".pdf")
    renderPDF.drawToFile(g.d, str(pdf_path))
    page = pdfium.PdfDocument(str(pdf_path))[0]
    page.render(scale=3.2).to_pil().save(OUT.with_suffix(".png"))
    print("written", OUT.with_suffix(".png"))


if __name__ == "__main__":
    build()
