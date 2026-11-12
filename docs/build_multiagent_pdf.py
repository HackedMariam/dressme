"""Builds docs/DressMe_MultiAgent_A2A.pdf : l'architecture multi-agents, l'orchestrateur et le protocole A2A.

    python docs/build_multiagent_pdf.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.units import mm  # noqa: E402
from reportlab.platypus import BaseDocTemplate, Frame, PageBreak, PageTemplate, Paragraph, Spacer  # noqa: E402

from build_architecture_pdf import (  # noqa: E402
    BODY, CODE, CODEST, DATA, EXT, GREY, H1, H2, LINE, LLM, OLIVE, SMALL, STD_LEGEND, Diagram, P, bullets, table)

OUT = Path(__file__).with_name("DressMe_MultiAgent_A2A.pdf")


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(GREY)
    canvas.drawString(20 * mm, 10 * mm, "DressMe - architecture multi-agents, orchestrateur et A2A")
    canvas.drawRightString(190 * mm, 10 * mm, f"page {doc.page}")
    canvas.setStrokeColor(LINE)
    canvas.line(20 * mm, 14 * mm, 190 * mm, 14 * mm)
    canvas.restoreState()


def diagram_system():
    g = Diagram(170, 112)
    g.box(35, 100, 100, 9, "Interface React : une page par fonction + le chat de l'orchestrateur", DATA, 7.4, True)
    g.box(55, 78, 60, 15, "Orchestrateur (LangGraph)\nroute -> un agent -> respond\nmémoire par utilisateur et par fil", LLM, 7.4)
    g.arrow(85, 100, 85, 93)
    agents = [(2, "AI Stylist", "dans BO1 :8000"), (36, "Wardrobe Agent", "dans BO1 :8000"),
              (70, "Outfit Builder", "dans BO1 :8000"), (104, "Trip Agent", "Help Me Pack :8020"),
              (138, "Gap Agent", "BO3 :8001")]
    for x, name, where in agents:
        g.box(x, 42, 30, 14, name + "\n" + where, CODE, 7)
    for x, _, _ in agents[:3]:
        g.arrow(85, 78, x + 15, 56, GREY, True)
    g.arrow(95, 78, 119, 56)
    g.arrow(105, 78, 153, 56)
    g.label(28, 72, "appels directs (même processus)", 6.8, GREY)
    g.label(150, 72, "A2A (HTTP, JSON-RPC)", 6.8, OLIVE, bold=True)
    g.box(2, 14, 48, 14, "OpenAI GPT-4o\nrouteur, agents, extraction", LLM, 7)
    g.box(61, 14, 48, 14, "Open-Meteo\nmétéo, sans clé", EXT, 7)
    g.box(120, 14, 48, 14, "Supabase\nauth, garde-robe, historique", DATA, 7)
    g.arrow(119, 42, 85, 28, GREY, True)
    g.arrow(153, 42, 145, 28, GREY, True)
    g.label(85, 4, "Le jeton Supabase de l'utilisateur traverse tous les appels : chaque agent agit pour lui, jamais pour un autre.", 6.8, GREY)
    g.legend(STD_LEGEND, y=0)
    return g.d


def diagram_a2a():
    g = Diagram(170, 70)
    g.box(2, 40, 42, 22, "Client A2A\n(orchestrateur, Trip Agent,\nscript de découverte)", LLM, 7)
    g.box(126, 40, 42, 22, "Agent A2A\n(Trip, Gap, Wardrobe,\nStylist, Outfit, Similar)", CODE, 7)
    g.arrow(44, 58, 126, 58)
    g.label(85, 60.5, "1. GET /.well-known/agent-card.json (public)", 6.8, INK_)
    g.arrow(126, 53, 44, 53, GREY, True)
    g.label(85, 49.5, "carte : nom, compétences, authentification", 6.6, GREY)
    g.arrow(44, 46, 126, 46)
    g.label(85, 42.5, "2. POST message/send + Bearer (JSON-RPC 2.0)", 6.8, INK_)
    g.arrow(126, 41, 44, 41, GREY, True)
    g.label(85, 37.5, "tâche : completed | input-required | failed", 6.6, GREY)
    g.label(85, 28, "3. si input-required : même contextId + la réponse de l'utilisateur", 7, OLIVE, bold=True)
    g.label(85, 20, "4. tasks/get pour relire une tâche, tasks/cancel pour l'annuler", 7, INK_)
    g.legend(STD_LEGEND, y=1)
    return g.d


INK_ = __import__("reportlab.lib.colors", fromlist=["HexColor"]).HexColor("#1C1C1C")


def build():
    doc = BaseDocTemplate(str(OUT), pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm,
                          bottomMargin=20 * mm, title="DressMe - multi-agents, orchestrateur et A2A", author="DressMe")
    doc.addPageTemplates([PageTemplate(id="p", frames=[Frame(20 * mm, 20 * mm, 170 * mm, 257 * mm, id="f")], onPage=footer)])
    s = []

    # ------------------------------------------------------------------ 1
    s += [P("Architecture multi-agents de DressMe", H1),
          P("L'orchestrateur et le protocole A2A", H2),
          P("DressMe n'est pas un seul assistant : c'est une équipe d'agents spécialisés. Chaque agent sait faire une chose "
            "(conseiller une tenue, lire la garde-robe, planifier une valise, trouver ce qui manque). Deux mécanismes les "
            "font travailler ensemble : un <b>orchestrateur</b> qui choisit le bon agent pour chaque demande, et le "
            "protocole <b>A2A</b> (Agent2Agent) qui permet à un agent d'en appeler un autre à travers le réseau."),
          P("Principe commun : <b>le LLM décide et rédige, le code déterministe vérifie et calcule</b>. Aucun agent ne peut "
            "citer une pièce absente de la garde-robe, inventer la météo ou inventer une source."),
          Spacer(1, 4), diagram_system(),
          P("Figure 1 - vue d'ensemble : l'orchestrateur reçoit la demande, un agent répond.", SMALL),
          H2_("Pourquoi plusieurs agents plutôt qu'un seul ?"),
          *bullets(["<b>Spécialisation</b> : chaque agent a ses outils et son prompt courts, donc moins d'erreurs qu'un seul "
                    "agent à tout faire.",
                    "<b>Indépendance</b> : le Trip Agent (Help Me Pack) et le Gap Agent sont des services séparés, avec leur "
                    "propre port, leurs propres tests et leur propre équipe ; on peut en redémarrer un sans toucher aux autres.",
                    "<b>Réutilisation</b> : le Trip Agent demande la garde-robe au Wardrobe Agent au lieu de relire la base "
                    "lui-même ; une seule règle d'accès aux données.",
                    "<b>Sécurité</b> : chaque appel porte le jeton de l'utilisateur ; chaque agent ne voit que ses données."]),
          PageBreak()]

    # ------------------------------------------------------------------ 2
    s += [P("Les agents", H1),
          table([["Agent", "Où", "Rôle", "Joint par"],
                 ["AI Stylist", "BO1 :8000", "Conseils de tenue avec météo et livres de mode (RAG)", "appel direct, A2A"],
                 ["Wardrobe Agent", "BO1 :8000", "Chercher, compter, comparer, corriger une pièce (une correction demande une confirmation)", "appel direct, A2A"],
                 ["Outfit Builder", "BO1 :8000", "Trois tenues complètes pour une occasion et une saison (LangGraph)", "appel direct, A2A"],
                 ["Similar Agent", "BO1 :8000", "Quelles pièces possédées ressemblent à celles d'une photo", "A2A"],
                 ["Trip Agent", "Help Me Pack :8020", "Météo, plus petit ensemble de vêtements qui habille chaque jour (OR-Tools CP-SAT), checklist", "A2A"],
                 ["Gap Agent", "BO3 :8001", "Classe les pièces qui manquent pour un objectif (XGBoost)", "A2A"]],
                [30, 30, 80, 30]),
          Spacer(1, 6),
          P("Les trois premiers vivent dans le même processus que l'orchestrateur de BO1 : il les appelle directement. "
            "Le Trip Agent et le Gap Agent sont d'autres services : il les appelle en A2A, exactement comme n'importe "
            "quel autre client A2A le ferait. Chaque agent A2A publie le même type de carte et répond au même format.", BODY),
          H2_("L'orchestrateur (BO1, LangGraph)"),
          P("Un seul point d'entrée de conversation (<font face='Courier'>POST /api/assistant/chat</font>). Le graphe a un "
            "nœud de routage, un nœud par agent, puis un nœud qui répond."),
          table([["Nœud", "Ce qu'il fait"],
                 ["route", "choisit l'agent : le LLM répond en JSON et n'a le droit de citer que les agents de la liste ; "
                           "des règles FR/EN (valise, voyage, manque, tenue...) servent de filet quand le LLM est absent ou se trompe"],
                 ["stylist, wardrobe, outfit", "appel direct dans le même processus"],
                 ["trip, gap", "appel A2A avec le jeton de l'utilisateur ; si le service est arrêté, message clair et pas d'erreur 500"],
                 ["redirect", "« Should I buy » et « Find Similar » ont besoin d'une photo : la réponse ouvre la bonne page"],
                 ["clarify", "la demande est trop vague ou c'est une salutation : demande ce que l'utilisateur veut"],
                 ["respond", "écrit le tour dans l'historique (8 derniers échanges)"]],
                [38, 132]),
          H2_("La mémoire d'une conversation"),
          P("Le graphe est compilé avec un point de reprise (checkpointer) : un fil par utilisateur et par conversation, "
            "deux utilisateurs ne partagent jamais un fil. Exemple :"),
          P("Utilisateur : « Prépare ma valise pour Paris »  ->  Trip Agent : tâche <i>input-required</i>, « quelles dates ? »<br/>"
            "Utilisateur : « du 3 au 7 juin, 8 kg »  ->  aucun mot-clé de voyage, mais la question est restée ouverte : "
            "la réponse repart au Trip Agent avec le même <i>contextId</i>.", CODEST),
          *bullets(["Une correction proposée par le Wardrobe Agent n'est continuée que par un oui ou un non ; toute autre phrase "
                    "est une nouvelle demande.",
                    "L'interface indique l'agent qui a répondu et ouvre la page voulue par un bouton (par exemple Help Me Pack, "
                    "sur la même session de voyage)."]),
          PageBreak()]

    # ------------------------------------------------------------------ 3
    s += [P("Le protocole A2A (Agent2Agent)", H1),
          P("A2A est un protocole ouvert qui permet à des agents de se découvrir et de se confier des tâches, sans connaître "
            "le code les uns des autres. DressMe implémente la version 0.3 au-dessus de HTTP et JSON-RPC 2.0 (dossier "
            "<font face='Courier'>a2a_protocol/</font>) : un serveur (<font face='Courier'>server.py</font>) et un client "
            "(<font face='Courier'>client.py</font>)."),
          Spacer(1, 4), diagram_a2a(),
          P("Figure 2 - un échange A2A, de la découverte à la réponse.", SMALL),
          H2_("Les quatre notions à retenir"),
          table([["Notion", "Définition", "Dans DressMe"],
                 ["Agent Card", "La carte d'identité de l'agent, publique : nom, version, compétences, mode d'authentification",
                  "<font face='Courier'>/.well-known/agent-card.json</font> sous chaque agent"],
                 ["Skill", "Une compétence annoncée sur la carte, avec exemples",
                  "<i>plan-trip-packing</i>, <i>wardrobe-gaps</i>, <i>wardrobe-search</i>, <i>duplicate-check</i>..."],
                 ["Task", "Une demande en cours, avec un état : completed, input-required, failed, canceled",
                  "<i>input-required</i> = l'agent pose une question (dates manquantes, confirmation)"],
                 ["contextId", "Identifiant de la conversation : le rappeler continue la même tâche",
                  "le Trip Agent y met l'identifiant de sa session de voyage"]],
                [26, 80, 64]),
          H2_("Les méthodes"),
          table([["Méthode JSON-RPC", "Rôle"],
                 ["<font face='Courier'>message/send</font>", "envoie du texte et/ou des données structurées, reçoit la tâche et son résultat"],
                 ["<font face='Courier'>tasks/get</font>", "relit une tâche (chaque tâche appartient à celui qui l'a créée)"],
                 ["<font face='Courier'>tasks/cancel</font>", "annule une tâche"]],
                [50, 120]),
          P("Non implémentés, et déclarés comme tels sur la carte : le streaming et les notifications push.", SMALL),
          H2_("Qui parle à qui, par A2A"),
          table([["Appelant", "Appelé", "Pour quoi faire"],
                 ["Orchestrateur", "Trip Agent (8020, /a2a/trip)", "planifier une valise"],
                 ["Orchestrateur", "Gap Agent (8001, /a2a/gap)", "ce qui manque dans la garde-robe"],
                 ["Trip Agent", "Wardrobe Agent (8000, /a2a/wardrobe)", "lire la garde-robe de l'utilisateur (repli sur la route BO1 si A2A échoue)"],
                 ["Trip Agent", "Gap Agent (8001)", "bouton « Gap analysis » de Help Me Pack"],
                 ["Gap Agent", "Wardrobe Agent", "lire la garde-robe (repli sur Supabase)"]],
                [35, 60, 75]),
          P("Pour voir les cartes de tous les agents : <font face='Courier'>python scripts/a2a_discover.py</font>, et avec "
            "un jeton <font face='Courier'>A2A_TOKEN=... python scripts/a2a_discover.py --ask</font> pour envoyer une tâche à chacun.", BODY)]

    # ------------------------------------------------------------------ 4
    s += [P("Sécurité, pannes et limites", H1),
          H2_("Authentification"),
          *bullets(["Chaque appel A2A porte l'en-tête <font face='Courier'>Authorization: Bearer</font> avec le jeton Supabase "
                    "de l'utilisateur ; le serveur de l'agent le vérifie. Sans jeton valide : « Please sign in again ».",
                    "Seule la carte est publique. Une tâche n'est relisible que par son propriétaire.",
                    "Le jeton circule dans la configuration du tour, jamais dans l'état du graphe ni dans les traces."]),
          H2_("Quand un agent est en panne"),
          *bullets(["Le client A2A a un délai maximum par appel (30 s pour la garde-robe, 90 s pour le Gap Agent, 120 s depuis "
                    "l'orchestrateur).",
                    "Orchestrateur : « The Trip Agent is not reachable right now... », jamais une erreur 500.",
                    "Trip Agent : si la garde-robe n'est pas joignable en A2A, il retombe sur la route normale de BO1."]),
          H2_("Ce qu'il faut dire clairement"),
          *bullets(["Chaque saut A2A ajoute un appel réseau, et souvent un appel LLM : plus précis, mais plus lent et plus cher "
                    "qu'un filtrage direct.",
                    "Le routage de l'orchestrateur repose sur le LLM, avec des règles FR/EN en secours : une demande ambiguë "
                    "peut tomber sur « clarify ».",
                    "Les tâches A2A sont gardées en mémoire (bornées) : elles disparaissent au redémarrage du service.",
                    "Le streaming n'est pas géré : l'utilisateur attend la réponse complète.",
                    "Il existe aussi une pile séparée de l'équipe, non branchée à l'interface React : le Stylist BO4 (Ollama, "
                    ":8061) et son propre orchestrateur (:8070, routage par services.yaml vers stylist, garde-robe, achat, RAG). "
                    "Il ne parle pas A2A : il appelle ces services par leurs routes HTTP."]),
          H2_("Fichiers à connaître"),
          table([["Sujet", "Fichier"],
                 ["Orchestrateur de l'application", "backend/app/orchestrator_agent.py"],
                 ["Serveur et client A2A", "a2a_protocol/server.py, a2a_protocol/client.py"],
                 ["Agents A2A de BO1", "backend/app/a2a_agents.py, backend/app/wardrobe_a2a.py"],
                 ["Trip Agent en A2A", "backend/main.py (handle_trip, /a2a/trip)"],
                 ["Gap Agent en A2A", "DressMe UI Blueprint/backend/a2a_gap.py"],
                 ["Découverte des agents", "scripts/a2a_discover.py"]],
                [60, 110])]

    doc.build(s)
    print("written", OUT)


def H2_(text):
    return Paragraph(text, H2)


if __name__ == "__main__":
    build()
