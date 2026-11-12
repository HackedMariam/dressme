"""Builds docs/DressMe_Similar_Agent.pdf : explication technique du Similar Agent.

    python docs/build_similar_agent_pdf.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.units import mm  # noqa: E402
from reportlab.platypus import BaseDocTemplate, Frame, PageBreak, PageTemplate, Paragraph, Spacer  # noqa: E402

from build_architecture_pdf import (  # noqa: E402
    BODY, CODE, CODEST, DATA, EXT, GREY, H1, H2, LINE, LLM, SMALL, STD_LEGEND, Diagram, P, bullets, table)

OUT = Path(__file__).with_name("DressMe_Similar_Agent.pdf")


def H2_(text):
    return Paragraph(text, H2)


def mono(text):
    return f"<font face='Courier'>{text}</font>"


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(GREY)
    canvas.drawString(20 * mm, 10 * mm, "DressMe - Similar Agent : explication technique")
    canvas.drawRightString(190 * mm, 10 * mm, f"page {doc.page}")
    canvas.setStrokeColor(LINE)
    canvas.line(20 * mm, 14 * mm, 190 * mm, 14 * mm)
    canvas.restoreState()


def diagram():
    g = Diagram(170, 86)
    g.box(2, 62, 36, 18, "Page Find Similar\nphoto d'un look", DATA, 7)
    g.box(48, 62, 38, 18, "analyze (YOLO)\ntoutes les pièces\nrien n'est sauvegardé", CODE, 7)
    g.box(96, 62, 34, 18, "POST\n/api/similar/agent\n8 pièces maximum", CODE, 7)
    g.box(140, 62, 28, 18, "Wardrobe Agent\nlit la garde-robe\n(A2A list)", CODE, 7)
    g.arrow(38, 71, 48, 71)
    g.arrow(86, 71, 96, 71)
    g.arrow(130, 71, 140, 71)
    g.label(85, 56, "Graphe LangGraph du Similar Agent (le Wardrobe Agent est interrogé pendant ask)", 7, INK_, bold=True)
    g.box(2, 22, 70, 26, "ask   (LLM + 1 outil)\nGPT-4o, 10 tours maximum\nask_wardrobe_agent, une fois par pièce", LLM, 7)
    g.box(98, 22, 70, 26, "check   (code seul)\nvalide statuts, index, identifiants\nrègles de secours pour le reste", CODE, 7)
    g.arrow(72, 35, 98, 35)
    g.label(85, 38, "JSON du LLM", 6.4, GREY)
    g.box(2, 2, 70, 12, "Wardrobe Agent (A2A ask, lecture seule)", CODE, 6.8)
    g.arrow(37, 22, 37, 14, OLIVE_)
    g.box(98, 2, 70, 12, "Sortie : owned | close | missing + raison + score", DATA, 6.8)
    g.arrow(133, 22, 133, 14)
    return g.d


INK_ = __import__("reportlab.lib.colors", fromlist=["HexColor"]).HexColor("#1C1C1C")
OLIVE_ = __import__("reportlab.lib.colors", fromlist=["HexColor"]).HexColor("#556B2F")


def build():
    doc = BaseDocTemplate(str(OUT), pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm,
                          bottomMargin=20 * mm, title="DressMe - Similar Agent", author="DressMe")
    doc.addPageTemplates([PageTemplate(id="p", frames=[Frame(20 * mm, 20 * mm, 170 * mm, 257 * mm, id="f")], onPage=footer)])
    s = []

    s += [P("Similar Agent", H1),
          P("Explication technique", H2),
          P("<b>Question à laquelle il répond :</b> « Je montre la photo d'une tenue. Est-ce que je possède déjà ses pièces ? ». "
            "Fichier " + mono("backend/app/similar_agent.py") + ". Route " + mono("POST /api/similar/agent") + ", interface A2A "
            + mono("/a2a/similar") + "."),
          P("Principe : <b>le LLM juge, le code vérifie et décide quand le LLM ne peut pas</b>. L'agent ne lit jamais la base : "
            "tout ce qu'il sait de la garde-robe vient du Wardrobe Agent."),
          Spacer(1, 4), diagram(),
          P("Figure 1 - de la photo au verdict, pièce par pièce.", SMALL),
          H2_("1. Où il intervient"),
          *bullets(["La page " + mono("FindSimilarPage.tsx") + " envoie la photo à " + mono("analyze") + " avec " + mono("allItems") + ", "
                    + mono("save=false") + " et " + mono("fast=true") + " : YOLO détecte <b>toutes</b> les pièces, rien n'est sauvegardé.",
                    "Elle envoie ces pièces (8 champs : nom, catégorie, groupe, couleur, famille de couleur, matière, style, motif) à l'agent.",
                    "L'agent renvoie un statut par pièce : <b>owned</b> (la même pièce, dans la même couleur, est déjà possédée), "
                    "<b>close</b> (même type mais autre couleur, matière ou style) ou <b>missing</b> (rien de semblable).",
                    "Si l'agent échoue, la page calcule elle-même un statut avec une règle locale (similarité d'au moins 45)."]),
          H2_("2. Le graphe LangGraph"),
          P("START -> ask -> check -> END", CODEST),
          table([["Nœud", "Type", "Ce qu'il fait"],
                 [mono("ask"), "LLM + outil",
                  "Boucle d'outils GPT-4o (température 0,1, 10 tours maximum) avec <b>un seul outil</b>, " + mono("ask_wardrobe_agent")
                  + ". Pour chaque pièce, le LLM demande en mots simples ce que l'utilisateur possède (« navy wool blazers »), "
                    "puis rend un JSON : un statut, une pièce proche et une raison par pièce, plus une phrase de résumé."],
                 [mono("check"), "code seul", "valide et corrige la réponse du LLM ; c'est lui qui garantit le résultat"]],
                [20, 28, 122]),
          P("Le commentaire en tête du fichier annonce trois nœuds (ask, judge, check) ; dans le code il n'y en a que deux : le "
            "jugement est fait dans " + mono("ask") + " par le LLM.", SMALL),
          PageBreak()]

    s += [H2_("3. L'agent ne lit jamais la base"),
          P("L'outil " + mono("ask_wardrobe_agent") + " envoie une tâche A2A " + mono("ask") + " au Wardrobe Agent "
            "(" + mono("/a2a/wardrobe") + "), en <b>lecture seule</b>, avec le jeton de l'utilisateur. Le Wardrobe Agent répond par une phrase "
            "et la liste des pièces qu'il a trouvées. Si le jeton manque, l'appel est fait directement dans le même processus. "
            "Une seule règle d'accès aux données pour tous les agents."),
          H2_("4. Le nœud check : le LLM propose, le code vérifie"),
          table([["Contrôle", "Si le contrôle échoue"],
                 ["Le statut vaut owned, close ou missing", "l'entrée est ignorée, la pièce est décidée par les règles"],
                 ["L'index de la pièce existe dans la photo", "l'entrée est ignorée"],
                 ["Le " + mono("closest_item_id") + " existe dans la vraie garde-robe", "il est remplacé par null (jamais d'identifiant inventé)"],
                 ["Un statut owned ou close a une vraie pièce proche", "sinon l'entrée est rejetée et décidée par les règles"],
                 ["Le LLM n'a oublié aucune pièce", "toute pièce oubliée est décidée par les règles"],
                 ["La réponse est un JSON lisible", "sinon, toutes les pièces sont décidées par les règles"],
                 ["Taille des textes", "raison limitée à 240 caractères, résumé à 300"]],
                [78, 92]),
          P("Chaque pièce porte un champ " + mono("by") + " : <i>agent</i> si le LLM a décidé, <i>rules</i> si ce sont les règles."),
          H2_("5. Les règles de secours : similar() du Wardrobe Agent"),
          P("Le score est calculé par le code, sans LLM. Seules les pièces à <b>3 points ou plus</b> sont gardées ; les 6 meilleures sont renvoyées."),
          table([["Critère", "Points"],
                 ["même catégorie", "+3"],
                 ["sinon même groupe de catégories", "+1"],
                 ["même couleur", "+2"],
                 ["sinon même famille de couleur", "+1"],
                 ["même matière", "+1"],
                 ["même style", "+1"],
                 ["chaque occasion en commun", "+0,5"],
                 ["chaque saison en commun", "+0,25"]],
                [100, 70]),
          P("Décision de secours : <b>similarité &gt;= 5 : owned</b> ; entre 3 et 5 : <b>close</b> ; aucune pièce : <b>missing</b>. "
            "Score affiché = similarité x 12, plafonné à 100.", BODY),
          P("Quand le LLM décide, le score vaut 90 (owned), 60 (close) ou 0 (missing), sauf s'il choisit la même pièce que les règles : "
            "c'est alors le score des règles qui est gardé.", BODY),
          H2_("6. Sortie"),
          P('{"pieces": [{"index": 0, "status": "owned", "closest_item_id": "...", "reason": "...", "score": 90, "by": "agent"}],<br/>'
            ' "summary": "You can already recreate most of this look."}', CODEST),
          H2_("7. Garde-fous et limites"),
          *bullets(["<b>8 pièces maximum</b> par photo ; chaque pièce de plus ajoute un appel au Wardrobe Agent.",
                    "<b>Sans clé OpenAI</b> (ou si le LLM est en panne) : les règles décident seules, la page reste utilisable.",
                    "<b>Précision</b> : les règles comparent des étiquettes (catégorie, couleur, matière, style), pas l'apparence. "
                    "Un « owned » dépend de la qualité du classement des pièces de la garde-robe.",
                    "<b>Un look sur photo</b> : les pièces cachées ou coupées ne sont pas détectées, donc pas jugées."]),
          H2_("8. Tests (4, tous verts)"),
          table([["Affirmation", "Test"],
                 ["L'agent interroge le Wardrobe Agent puis juge chaque pièce", "the_agent_asks_the_wardrobe_agent_then_judges_every_piece"],
                 ["Une pièce inventée ou oubliée est décidée par les règles", "an_invented_piece_or_a_forgotten_one_is_decided_by_the_wardrobe_rules"],
                 ["Sans LLM, le classement du Wardrobe Agent répond", "without_the_llm_the_wardrobe_agents_ranking_answers"],
                 ["Le sous-appel au Wardrobe Agent est en lecture seule", "the_sub_call_to_the_wardrobe_agent_is_read_only"]],
                [80, 90])]

    doc.build(s)
    print("written", OUT)


if __name__ == "__main__":
    build()
