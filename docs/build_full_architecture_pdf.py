"""Builds docs/DressMe_Architecture_Complete_Agents.pdf : tous les agents, leurs liens, et le rôle exact de l'orchestrateur.

    python docs/build_full_architecture_pdf.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.units import mm  # noqa: E402
from reportlab.platypus import BaseDocTemplate, Frame, PageBreak, PageTemplate, Paragraph, Spacer  # noqa: E402

from build_architecture_pdf import (  # noqa: E402
    BODY, CODEST, DATA, EXT, GREY, H1, H2, LINE, LLM, OLIVE, SMALL, STD_LEGEND, CODE, Diagram, P, bullets, table)

OUT = Path(__file__).with_name("DressMe_Architecture_Complete_Agents.pdf")
INK = __import__("reportlab.lib.colors", fromlist=["HexColor"]).HexColor("#1C1C1C")


def H2_(text):
    return Paragraph(text, H2)


def mono(text):
    return f"<font face='Courier'>{text}</font>"


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(GREY)
    canvas.drawString(20 * mm, 10 * mm, "DressMe - architecture complète des agents")
    canvas.drawRightString(190 * mm, 10 * mm, f"page {doc.page}")
    canvas.setStrokeColor(LINE)
    canvas.line(20 * mm, 14 * mm, 190 * mm, 14 * mm)
    canvas.restoreState()


def diagram_global():
    g = Diagram(170, 132)
    g.label(85, 126, "INTERFACE REACT : une page par fonction", 7.4, OLIVE, bold=True)
    pages = [(1, "AI Stylist\n(chat)"), (35, "Wardrobe\n(recherche, Live scan)"), (69, "Outfit Builder\nFind Similar"),
             (103, "Should I buy"), (137, "Help Me Pack\nWardrobe Gaps")]
    for x, label in pages:
        g.box(x, 104, 32, 16, label, DATA, 6.6)
    # orchestrator, fed only by the chat page
    g.box(1, 66, 32, 22, "ORCHESTRATEUR\n(LangGraph)\n7 routes", LLM, 6.8, True)
    g.arrow(17, 104, 17, 88, INK)
    g.label(19, 95, "seule page qui passe par lui", 6, GREY, anchor="start")
    # BO1
    g.box(40, 62, 128, 32, "", CODE, 6.6)
    g.label(104, 87, "BO1 :8000 (un seul processus)", 6.8, INK, bold=True)
    inner = [(43, "AI Stylist"), (67, "Wardrobe\nAgent"), (91, "Outfit\nBuilder"), (115, "Similar\nAgent"), (139, "Agent d'achat\n(Qwen)")]
    for x, label in inner:
        g.box(x, 66, 23, 16, label, DATA, 6.4)
    g.arrow(33, 77, 43, 77, INK)
    g.label(38, 70, "direct", 6, GREY)
    # other pages call BO1 agents directly
    g.arrow(51, 104, 78, 94, GREY, True)
    g.arrow(85, 104, 102, 94, GREY, True)
    g.arrow(119, 104, 150, 94, GREY, True)
    # separate services
    g.box(1, 28, 40, 18, "Trip Agent\nHelp Me Pack :8020\nOR-Tools CP-SAT", CODE, 6.6)
    g.box(52, 28, 40, 18, "Gap Agent (BO3) :8001\nXGBoost + GPT-4o-mini", CODE, 6.6)
    g.box(130, 28, 38, 18, "RAG :8010\n38 PDF, pgvector", EXT, 6.6)
    # orchestrator A2A to Trip and Gap
    g.arrow(10, 66, 10, 46, OLIVE)
    g.arrow(25, 66, 62, 46, OLIVE)
    g.label(8, 55, "A2A", 6.4, OLIVE, bold=True, anchor="end")
    # Trip and Gap read the wardrobe via the Wardrobe Agent (A2A)
    g.arrow(30, 46, 72, 62, OLIVE)
    g.arrow(80, 46, 80, 62, OLIVE)
    g.label(112, 54, "Trip et Gap lisent la garde-robe", 6.4, OLIVE, bold=True)
    g.label(112, 49, "par le Wardrobe Agent (A2A)", 6.4, OLIVE, bold=True)
    g.arrow(148, 62, 148, 46, GREY, True)
    g.label(148, 20, "BO1 consulte le RAG", 6.2, GREY)
    g.label(85, 10, "Vert : A2A. Gris pointillé : appel direct d'une page. Help Me Pack appelle le Trip Agent, Wardrobe Gaps le Gap Agent.", 6.4, GREY)
    g.legend(STD_LEGEND, y=0)
    return g.d


def build():
    doc = BaseDocTemplate(str(OUT), pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm,
                          bottomMargin=20 * mm, title="DressMe - architecture complète des agents", author="DressMe")
    doc.addPageTemplates([PageTemplate(id="p", frames=[Frame(20 * mm, 20 * mm, 170 * mm, 257 * mm, id="f")], onPage=footer)])
    s = []

    # ---------------------------------------------------------------- 1
    s += [P("Architecture complète des agents de DressMe", H1),
          P("Qui est qui, qui parle à qui, et où intervient l'orchestrateur", H2),
          P("<b>Réponse à la question clé.</b> L'orchestrateur n'intervient <b>que dans le chat de la page AI Stylist</b> : "
            "c'est la seule page qui appelle " + mono("/api/assistant/chat") + ". Toutes les autres pages appellent leur "
            "agent directement. Ce n'est donc pas un passage obligé du système : c'est une entrée de conversation en plus."),
          Spacer(1, 3), diagram_global(),
          P("Figure 1 - tous les agents, les pages qui les appellent, et les liens A2A.", SMALL),
          PageBreak()]

    # ---------------------------------------------------------------- 2
    s += [P("1. Les agents, un par un", H1),
          table([["Agent", "Où", "Technique", "Outils ou nœuds", "Sa mission"],
                 ["AI Stylist", "BO1 :8000", "boucle d'outils GPT-4o, 8 tours",
                  "ask_wardrobe_agent, get_weather, fashion_advice", "conseiller une tenue avec la vraie météo et les livres de mode"],
                 ["Wardrobe Agent", "BO1 :8000", "LangGraph : gate, apply, cancel, assist",
                  "search_wardrobe, find_similar, wardrobe_stats, update_item (propose)", "propriétaire de la garde-robe ; corrige seulement après un oui"],
                 ["Agent anti-doublon", "BO1 :8000 (dans le Wardrobe Agent)", "boucle d'outils, 4 tours", "search_wardrobe",
                  "dire si une pièce scannée existe déjà"],
                 ["Outfit Builder", "BO1 :8000", "LangGraph 5 nœuds",
                  "weather, closet, knowledge, compose, validate", "3 tenues complètes validées par le code"],
                 ["Similar Agent", "BO1 :8000", "LangGraph : ask, judge, check", "interroge le Wardrobe Agent",
                  "pour chaque pièce d'une photo : owned, close ou missing"],
                 ["Agent d'achat", "BO1 (dossier smart_purchasing)", "Qwen2.5-3B LoRA, 6 tours",
                  "analyze_item, find_similar_items, check_outfit_compatibility, analyze_wardrobe_gaps, predict_purchase_ml, calculate_purchase_value",
                  "« Should I buy this ? » : BUY, CONSIDER ou SKIP ; sans HF_TOKEN, repli déterministe"],
                 ["Trip Agent", "Help Me Pack :8020", "GPT-4o + 2 graphes LangGraph + CP-SAT", "10 outils (trip, météo, garde-robe, optimiseur, checklist...)",
                  "valise du plus petit nombre de pièces qui habille chaque jour"],
                 ["Gap Agent (BO3)", "BO3 :8001", "boucle d'outils GPT-4o-mini, 6 étapes + XGBoost", "5 outils",
                  "ce qui manque dans la garde-robe pour un objectif"],
                 ["Orchestrateur", "BO1 :8000", "LangGraph : route, un nœud par agent, respond", "7 routes", "choisir l'agent du chat AI Stylist"]],
                [24, 26, 36, 46, 38]),
          Spacer(1, 4),
          H2_("Ce qui n'est pas un agent"),
          *bullets(["<b>Catalogage vision</b> : YOLO11m-seg puis GPT-4o (JSON strict). Pipeline fixe, le LLM ne choisit pas ses outils.",
                    "<b>RAG</b> (:8010) : recherche hybride puis réponse avec sources numérotées [S#]. Appelé comme un outil par "
                    "l'AI Stylist, l'Outfit Builder, le Wardrobe-fashion et l'orchestrateur de l'équipe.",
                    "<b>Contrôle qualité et doublon visuel du Live scan</b> : du code (histogramme et forme), sans LLM."]),
          H2_("Une pile séparée de l'équipe, non branchée à l'interface React"),
          P("Le Stylist BO4 (LangGraph à 9 nœuds, Ollama qwen2.5:3b, :8061) et son orchestrateur (:8070, routes stylist, garde-robe, achat, "
            "RAG, et modules externes déclarés dans " + mono("services.yaml") + ") ont leur propre page web. Ils ne parlent pas A2A : "
            "ils appellent les services par leurs routes HTTP. À ne pas confondre avec l'orchestrateur de l'application décrit plus bas."),
          PageBreak()]

    # ---------------------------------------------------------------- 3
    s += [P("2. Page par page : qui appelle quoi", H1),
          P("C'est le tableau qui montre où l'orchestrateur intervient : une seule ligne."),
          table([["Page", "Route appelée", "Agent qui répond", "Orchestrateur ?"],
                 ["<b>AI Stylist (chat)</b>", mono("POST /api/assistant/chat"), "celui que l'orchestrateur choisit", "<b>OUI</b>"],
                 ["Wardrobe : recherche IA, corrections", mono("POST /api/wardrobe/agent"), "Wardrobe Agent", "non"],
                 ["Wardrobe : Live scan", mono("quick-detect, analyze, reclassify, check-duplicate"),
                  "détecteur YOLO, puis agent anti-doublon", "non"],
                 ["Wardrobe : recherche par photo", mono("POST /api/search/photo"), "YOLO, sans LLM", "non"],
                 ["Outfit Builder", mono("POST /api/outfits/agent"), "Outfit Builder", "non"],
                 ["Find Similar", mono("POST /api/similar/agent"), "Similar Agent (puis boutiques BO3)", "non"],
                 ["Should I buy this", mono("POST /api/shopping-assistant/evaluate"), "agent d'achat (Qwen)", "non"],
                 ["Help Me Pack", mono("POST :8020/api/trips"), "Trip Agent", "non"],
                 ["Help Me Pack : Gap analysis", mono("POST :8020/api/trips/{id}/gap-analysis"), "Trip Agent puis Gap Agent (A2A)", "non"],
                 ["Wardrobe Gaps et carte du tableau de bord", mono("GET /api/bo3/gaps"), "Gap Agent (proxy Vite vers :8001)", "non"]],
                [40, 56, 50, 24]),
          P("La route " + mono("/api/agent/search") + " (AI Stylist en question libre) existe côté serveur, mais aucune page ne l'appelle "
            "aujourd'hui : le chat de l'AI Stylist passe par l'orchestrateur.", SMALL),
          H2_("Ce que fait l'orchestrateur dans le chat"),
          table([["Route choisie", "Quand", "Comment il l'appelle"],
                 ["stylist", "que porter, couleurs, tissus", "appel direct (même processus)"],
                 ["wardrobe", "ce que je possède, compter, corriger", "appel direct (même processus)"],
                 ["outfit", "tenues pour une occasion", "appel direct (même processus)"],
                 ["trip", "valise, voyage", "<b>A2A</b> vers :8020 avec le jeton de l'utilisateur"],
                 ["gap", "ce qui manque, quoi acheter", "<b>A2A</b> vers :8001 avec le jeton de l'utilisateur"],
                 ["redirect", "« Should I buy » et « Find Similar » : il faut une photo", "aucun agent : la réponse ouvre la bonne page"],
                 ["clarify", "demande vague ou salutation", "aucun agent : pose une question"]],
                [28, 70, 72]),
          *bullets(["<b>Choix de la route</b> : le LLM répond en JSON et ne peut citer que les agents de la liste ; des règles FR/EN "
                    "(valise, manque, tenue...) servent de filet quand il est absent ou se trompe.",
                    "<b>Mémoire</b> : un fil par utilisateur et par conversation (checkpointer). Une question laissée ouverte par le "
                    "Trip Agent (<i>input-required</i>) ou une correction qui attend un oui repart au <b>même agent</b> au message suivant, "
                    "quels que soient les mots."]),
          PageBreak()]

    # ---------------------------------------------------------------- 4
    s += [P("3. Comment les agents communiquent", H1),
          P("Trois mécanismes seulement, du plus simple au plus ouvert."),
          table([["Mécanisme", "Utilisé pour", "Pourquoi"],
                 ["<b>1. Appel Python direct</b>", "orchestrateur vers AI Stylist, Wardrobe Agent, Outfit Builder (même processus BO1)",
                  "le plus rapide, aucun réseau"],
                 ["<b>2. A2A</b> (JSON-RPC sur HTTP)", "dès qu'un agent en appelle un autre en dehors de son processus, et pour lire la garde-robe",
                  "carte publique, jeton de l'utilisateur, tâche avec un état, reprise de conversation par contextId"],
                 ["<b>3. HTTP simple</b> (REST)", "page vers services ; BO1 vers RAG (:8010) ; agents vers Open-Meteo",
                  "données et services qui ne sont pas des agents"]],
                [40, 80, 50]),
          H2_("Tous les liens A2A"),
          table([["Appelant", "Appelé", "Pour quoi", "Si l'appel échoue"],
                 ["Orchestrateur", "Trip Agent (:8020 /a2a/trip)", "planifier une valise", "message « not reachable », jamais une erreur 500"],
                 ["Orchestrateur", "Gap Agent (:8001 /a2a/gap)", "ce qui manque", "même message clair"],
                 ["Trip Agent", "Wardrobe Agent (:8000 /a2a/wardrobe)", "lire la garde-robe (" + mono("list") + ")", "repli sur la route BO1 " + mono("/api/items")],
                 ["Trip Agent", "Gap Agent (:8001)", "bouton « Gap analysis »", "erreur affichée dans la page"],
                 ["Gap Agent", "Wardrobe Agent", "lire la garde-robe", "repli sur Supabase"],
                 ["AI Stylist", "Wardrobe Agent", mono("ask") + " : chercher en mots simples", "repli sur sa propre recherche"],
                 ["Similar Agent", "Wardrobe Agent", "interroger la garde-robe pour chaque pièce", "décision par le classement de similarité"],
                 ["Outfit Builder, routes /api/*", "Wardrobe Agent", "lire la garde-robe (" + mono("list") + ")", "lecture directe de la base"]],
                [32, 44, 50, 44]),
          P("Le Wardrobe Agent est ainsi le <b>point central des données</b> : tout le monde lit la garde-robe par lui. "
            "Aucun autre agent n'a de droit d'écriture sur les vêtements.", BODY),
          H2_("Ce qui voyage dans chaque appel"),
          *bullets(["<b>Le jeton Supabase de l'utilisateur</b> (en-tête " + mono("Authorization: Bearer") + ") : chaque agent agit pour lui et "
                    "ne voit que ses pièces. Il passe dans la configuration du tour, jamais dans l'état du graphe ni dans les traces.",
                    "<b>contextId</b> : identifie la conversation ; le rappeler reprend la même tâche (valise en cours, correction en attente).",
                    "<b>Un état de tâche</b> : completed, input-required (l'agent pose une question) ou failed."]),
          H2_("Protocole A2A en bref"),
          P("Version 0.3, JSON-RPC 2.0 : " + mono("message/send") + ", " + mono("tasks/get") + ", " + mono("tasks/cancel") + ". Chaque agent publie sa "
            "carte à " + mono("/.well-known/agent-card.json") + " (nom, compétences, authentification). Le streaming et les notifications "
            "push ne sont pas gérés. Voir le PDF « multi-agents et A2A » pour le détail.", BODY),
          PageBreak()]

    # ---------------------------------------------------------------- 5
    s += [P("4. Trois parcours de bout en bout", H1),
          H2_("A. « Prépare ma valise pour Paris » dans le chat AI Stylist"),
          P("1. La page envoie le message à " + mono("/api/assistant/chat") + " avec le jeton.<br/>"
            "2. L'orchestrateur choisit <b>trip</b> (LLM + règles).<br/>"
            "3. Il envoie une tâche A2A au Trip Agent. Les dates manquent : tâche <i>input-required</i>, « quelles dates ? ».<br/>"
            "4. Tu réponds « du 3 au 7 juin, 8 kg » : aucun mot-clé, mais la question est restée ouverte, donc le message repart au "
            "Trip Agent avec le même contextId.<br/>"
            "5. Le Trip Agent lit la garde-robe auprès du Wardrobe Agent (A2A), calcule la météo, optimise (CP-SAT) et répond.<br/>"
            "6. La réponse porte un bouton « Open Help Me Pack » sur la même session de voyage.", CODEST),
          H2_("B. Page Help Me Pack, sans orchestrateur"),
          P("1. La page appelle directement " + mono(":8020/api/trips") + " avec le jeton.<br/>"
            "2. Le Trip Agent lit la garde-robe en A2A (Wardrobe Agent), puis planifie.<br/>"
            "3. Le bouton « Gap analysis » appelle le Trip Agent, qui interroge le Gap Agent en A2A.", CODEST),
          H2_("C. Live scan, sans orchestrateur"),
          P("1. La page envoie une image toutes les 600 ms à " + mono("quick-detect") + " (YOLO seul).<br/>"
            "2. L'objet immobile 1,4 s : " + mono("analyze?fast=true") + " contrôle la qualité et le doublon visuel, puis sauvegarde.<br/>"
            "3. La page appelle l'agent anti-doublon et " + mono("reclassify") + " (GPT-4o) en arrière-plan.", CODEST),
          H2_("Garde-fous communs à tous les agents"),
          *bullets(["Le LLM propose et rédige ; le code vérifie, calcule et écrit. Aucun agent ne peut citer une pièce absente de la "
                    "garde-robe, inventer la météo ou une source.",
                    "Une seule voie d'écriture sur les vêtements, validée par le code, et seulement après un oui de l'utilisateur.",
                    "Chaque appel A2A a un délai maximum ; un service arrêté donne un message clair.",
                    "Boucles d'outils bornées (4 à 8 tours) dans une brique commune, " + mono("agent_kit/tool_loop.py") + "."]),
          H2_("Limites à connaître"),
          *bullets(["Le routage de l'orchestrateur repose sur un LLM : une demande ambiguë peut finir en « clarify ».",
                    "Chaque saut A2A ajoute un appel réseau et souvent un appel LLM : plus précis, mais plus lent et plus cher.",
                    "Les tâches A2A et les propositions de correction sont gardées en mémoire du processus : un redémarrage les efface.",
                    "L'agent d'achat dépend de Hugging Face (HF_TOKEN) ; sans lui, il n'est pas un agent mais une évaluation déterministe."])]

    doc.build(s)
    print("written", OUT)


if __name__ == "__main__":
    build()
