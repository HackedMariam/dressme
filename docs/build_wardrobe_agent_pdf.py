"""Builds docs/DressMe_Wardrobe_Agent.pdf : fiche technique complète du Wardrobe Agent.

    python docs/build_wardrobe_agent_pdf.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from reportlab.lib import colors  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle  # noqa: E402
from reportlab.lib.units import mm  # noqa: E402
from reportlab.platypus import BaseDocTemplate, Frame, PageBreak, PageTemplate, Paragraph, Spacer  # noqa: E402

from build_architecture_pdf import (  # noqa: E402
    BODY, CODE, CODEST, DATA, EXT, GREY, H1, H2, LINE, LLM, SMALL, STD_LEGEND, Diagram, P, bullets, table)

OUT = Path(__file__).with_name("DressMe_Wardrobe_Agent.pdf")
INK = colors.HexColor("#1C1C1C")
OLIVE = colors.HexColor("#556B2F")
PROMPT = ParagraphStyle("PROMPT", parent=CODEST, fontSize=7.2, leading=9.4)


def H2_(text):
    return Paragraph(text, H2)


def mono(text):
    return f"<font face='Courier'>{text}</font>"


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(GREY)
    canvas.drawString(20 * mm, 10 * mm, "DressMe - Wardrobe Agent : fiche technique")
    canvas.drawRightString(190 * mm, 10 * mm, f"page {doc.page}")
    canvas.setStrokeColor(LINE)
    canvas.line(20 * mm, 14 * mm, 190 * mm, 14 * mm)
    canvas.restoreState()


def diagram():
    g = Diagram(170, 100)
    g.box(2, 78, 44, 18, "Page Wardrobe\n(recherche IA, corrections)", DATA, 6.8)
    g.box(63, 78, 44, 18, "Autres agents (A2A)\nTrip, Gap, Stylist, Similar", DATA, 6.8)
    g.box(124, 78, 44, 18, "Live scan\ncheck-duplicate", DATA, 6.8)
    g.label(85, 69, "Entrées : /api/wardrobe/agent    /a2a/wardrobe    /api/agent/check-duplicate", 6.6, GREY)
    g.arrow(24, 78, 70, 62)
    g.arrow(85, 78, 85, 62)
    g.arrow(146, 78, 100, 62)
    g.box(2, 38, 36, 22, "gate\n(code)\nune proposition\nattend-elle ?", CODE, 6.6)
    g.box(48, 38, 36, 22, "assist\n(LLM + 4 outils)\n6 tours maximum", LLM, 6.6)
    g.box(94, 38, 36, 22, "apply\n(code)\nécrit après un oui", CODE, 6.6)
    g.box(134, 38, 34, 22, "cancel\n(code)\nannule après un non", CODE, 6.6)
    g.arrow(38, 49, 48, 49)
    g.arrow(84, 49, 94, 49)
    g.arrow(130, 49, 134, 49)
    g.label(43, 33, "autre message", 6.2, GREY)
    g.label(89, 33, "oui", 6.2, GREY)
    g.box(2, 4, 50, 18, "Garde-robe (Supabase)\nlecture : tous les agents\nécriture : un seul chemin validé", DATA, 6.6)
    g.box(60, 4, 50, 18, "_validate_patch / _apply_patch\n(main.py) : le même chemin que\nle bouton de la page", CODE, 6.6)
    g.box(118, 4, 50, 18, "PendingStore\npropositions en attente\n(15 min, par utilisateur)", DATA, 6.6)
    g.arrow(112, 38, 85, 22, GREY, True)
    g.arrow(26, 38, 26, 22, GREY, True)
    g.arrow(148, 38, 143, 22, GREY, True)
    return g.d


def build():
    doc = BaseDocTemplate(str(OUT), pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm,
                          bottomMargin=20 * mm, title="DressMe - Wardrobe Agent", author="DressMe")
    doc.addPageTemplates([PageTemplate(id="p", frames=[Frame(20 * mm, 20 * mm, 170 * mm, 257 * mm, id="f")], onPage=footer)])
    s = []

    # ------------------------------------------------------------ 1
    s += [P("Wardrobe Agent", H1),
          P("Fiche technique : ce qu'il fait, ce qu'il utilise, ses prompts, ses paramètres et ses fichiers", H2),
          P("Le Wardrobe Agent est <b>le propriétaire de la garde-robe</b> de l'utilisateur. Il cherche, compte, compare et "
            "corrige des vêtements. C'est aussi le seul point par lequel les autres agents lisent la garde-robe."),
          H2_("Carte d'identité"),
          table([["Question", "Réponse"],
                 ["Utilise-t-il un LLM ?", "<b>Oui, mais pas partout.</b> Texte libre, ask et check-duplicate : oui. list, search, "
                                           "calculs, validation, écriture : non (voir la partie 2)."],
                 ["Quel LLM ?", "OpenAI <b>gpt-4o</b> (défaut de " + mono("LLM_MODEL") + "), appelé par l'API Chat Completions avec appel d'outils"],
                 ["Température", "<b>0,2</b> pour répondre (" + mono("node_assist") + "), <b>0,1</b> pour la détection de doublon"],
                 ["Technique", "graphe LangGraph à 4 nœuds + boucle d'outils partagée " + mono("agent_kit/tool_loop.py")],
                 ["Outils", "4 : " + mono("search_wardrobe") + ", " + mono("find_similar") + ", " + mono("wardrobe_stats") + ", " + mono("update_item")],
                 ["Peut-il écrire ?", "<b>Non, jamais seul.</b> Il propose ; le code écrit après un « oui » de l'utilisateur"],
                 ["Où ?", "BO1, port 8000, fichier " + mono("backend/app/wardrobe_agent.py") + " (491 lignes)"],
                 ["Interfaces", mono("POST /api/wardrobe/agent") + ", A2A " + mono("/a2a/wardrobe") + ", " + mono("POST /api/agent/check-duplicate")],
                 ["Mémoire", "aucune conversation longue ; seulement les propositions de correction en attente (15 minutes)"]],
                [38, 132]),
          Spacer(1, 4), diagram(),
          P("Figure 1 - les entrées, le graphe et ce qu'il touche.", SMALL),
          PageBreak()]

    # ------------------------------------------------------------ 2
    s += [H2_("1. Les tâches qu'il fait"),
          table([["Tâche", "Exemple", "Comment"],
                 ["Chercher", "« Montre-moi une veste chaude pour le travail »", "le LLM choisit les filtres, le code filtre (search_wardrobe)"],
                 ["Compter et résumer", "« Combien de hauts ai-je ? »", "wardrobe_stats : calculé par le code"],
                 ["Comparer", "« Ai-je déjà quelque chose comme mon blazer marine ? »", "find_similar : score calculé par le code"],
                 ["Corriger une pièce", "« Change la couleur de ma jupe grise en bleu marine »",
                  "update_item <b>propose</b> ; le code écrit après un oui"],
                 ["Détecter un doublon", "pièce qu'on vient de scanner", "agent à part (prompt dédié), 4 tours, JSON strict"],
                 ["Servir les autres agents", "Trip Agent : toute la garde-robe ; AI Stylist : « une veste pour le travail »",
                  "list, search, ask via A2A"]],
                [34, 62, 74]),
          P("Ce qu'il ne fait <b>pas</b> : conseiller une tenue, consulter la météo ou les livres de mode, construire des tenues. "
            "Son prompt lui interdit et le renvoie à l'AI Stylist et à l'Outfit Builder."),
          H2_("2. Où il utilise un LLM, et où non"),
          table([["Opération", "LLM ?", "Qui décide"],
                 [mono("data.action = list"), "non", "le code renvoie toute la garde-robe"],
                 [mono("data.action = search"), "non", "le code applique les filtres exacts reçus"],
                 [mono("data.action = ask"), "<b>oui</b>, lecture seule", "le LLM choisit les filtres ; le code filtre"],
                 ["texte libre (page Wardrobe, orchestrateur)", "<b>oui</b>", "le LLM choisit les outils ; le code exécute"],
                 [mono("check-duplicate"), "<b>oui</b>", "le LLM juge « même pièce vue deux fois ? » ; sans clé OpenAI : « pas de doublon »"],
                 ["recherche : filtres, comparaison, 20 résultats max", "non", "code"],
                 ["wardrobe_stats, find_similar (score)", "non", "code"],
                 ["validation d'une correction (_validate_patch)", "non", "code"],
                 ["confirmation oui / non (regex FR et EN)", "non", "code"],
                 ["écriture en base (_apply_patch)", "non", "code"]],
                [74, 30, 66]),
          P("Sans clé OpenAI : les actions list, search et check-duplicate répondent quand même (check-duplicate dit « pas de doublon ») ; "
            "le texte libre répond « needs an OPENAI_API_KEY » et ask renvoie une réponse vide.", BODY),
          H2_("3. Les 4 outils du LLM"),
          table([["Outil", "Paramètres", "Effet"],
                 [mono("search_wardrobe"), "category, category_group, color_name, season, occasion, style, pattern, min_warmth (1 à 5), text",
                  "filtre ET ; 20 résultats maximum ; valeurs prises dans des listes fermées (taxonomy.py)"],
                 [mono("find_similar"), "item_id, ou category, color_name, material, style",
                  "pièces proches, score : même type +3, même couleur +2, matière +1, style +1 ; seuil 3 ; 6 meilleures"],
                 [mono("wardrobe_stats"), "aucun", "total, par groupe, catégorie, famille de couleur, saison, occasion, à vérifier, sans photo"],
                 [mono("update_item"), "item_id, fields", "<b>propose</b> une correction ; rien n'est sauvegardé"]],
                [30, 70, 70]),
          P("Champs modifiables par l'agent : " + mono("name, category, color_name, pattern, material, style, seasons, occasions, "
            "formality, warmth") + ". Les autres sont retirés avant validation.", SMALL),
          PageBreak()]

    # ------------------------------------------------------------ 3
    s += [H2_("4. Le flux d'une correction"),
          P("1. Toi : « Change la couleur de ma jupe grise en bleu marine ».<br/>"
            "2. gate : aucune proposition en attente, donc assist. Le LLM cherche la jupe, puis appelle update_item.<br/>"
            "3. Le code vérifie la pièce et le champ, la mémorise dans PendingStore (15 minutes). Rien n'est sauvegardé.<br/>"
            "4. Réponse : « Je propose : couleur gris -> bleu marine. Tu confirmes ? » (tâche input-required).<br/>"
            "5. Toi : « oui » (ou confirm=true) : gate envoie vers apply, qui écrit par le chemin validé.<br/>"
            "6. Toute autre phrase supprime la proposition et devient une nouvelle demande ; « non » l'annule.", CODEST),
          H2_("5. Les prompts"),
          P("<b>Prompt système principal</b> (" + mono("SYSTEM") + ", wardrobe_agent.py) :"),
          P("You are the Wardrobe Agent of DressMe: you look after the user's wardrobe. Reply in the language the user wrote in, "
            "in one to three plain sentences, no markdown, no emojis. Never invent a piece: always call search_wardrobe (or "
            "find_similar / wardrobe_stats) before talking about what the user owns, and call search_wardrobe again with other "
            "filters when a search comes back empty or too broad. To correct a piece, find it first, then call update_item: it "
            "only PROPOSES the change, so tell the user precisely what would change (piece, field, old value, new value) and ask "
            "them to confirm. Never say a change was made. You do not give styling advice or build outfits: say that the AI "
            "Stylist and the Outfit Builder do that.", PROMPT),
          P("<b>Ajout quand un autre agent l'appelle (ask, lecture seule)</b> :"),
          P("This request comes from another agent: it is read-only, never propose a change, and answer in one short sentence "
            "listing what you found. Be generous: when the request is about what to wear for an occasion, a season or the "
            "weather, search each role separately (tops, bottoms, dresses, outerwear, shoes) and use occasion or season filters "
            "only when they still return pieces, otherwise search without them: the other agent chooses among your results. "
            "(L'outil update_item est aussi retiré de la liste des outils.)", PROMPT),
          P("<b>Prompt du contrôle de doublon</b> (" + mono("DUPLICATE_SYSTEM") + ") :"),
          P("You help catalogue a wardrobe that's being scanned live from a camera. An item was just detected and saved. "
            "Decide whether the wardrobe already contains a near-duplicate of it - call search_wardrobe (at least once) to "
            "check, looking at category, colour and whatever else you're told. Only call it a duplicate if you're genuinely "
            "confident it's the same physical garment seen twice (e.g. the user scanned it by accident, or it's a second photo "
            "of the same jacket) - NOT just 'another navy t-shirt' or 'another pair of jeans', which are normal to own more "
            "than one of. When you're done, reply with ONLY a compact JSON object, no other text: {\"duplicate\": true or "
            "false, \"similar_item_id\": \"&lt;id or null&gt;\", \"note\": \"&lt;one short sentence for the user if duplicate, "
            "else empty&gt;\"}.", PROMPT),
          P("Les descriptions des 4 outils (texte vu par le LLM) sont dans les constantes " + mono("SEARCH_TOOL") + ", "
            + mono("FIND_SIMILAR_TOOL") + ", " + mono("STATS_TOOL") + " et " + mono("UPDATE_TOOL") + " du même fichier. "
            "Exemple : update_item dit « PROPOSE a correction ... Nothing is saved: the user must confirm in their next message »."),
          PageBreak()]

    # ------------------------------------------------------------ 4
    s += [H2_("6. Les paramètres et où les changer"),
          table([["Paramètre", "Valeur", "Où"],
                 ["Modèle LLM", "gpt-4o (variable " + mono("LLM_MODEL") + ")", "backend/app/config.py ; surchargé par le .env de la racine"],
                 ["Clé API", mono("OPENAI_API_KEY") + " ou " + mono("LLM_API_KEY"), "backend/app/config.py (lue dans le .env)"],
                 ["Température, réponses", "<b>0,2</b>", "wardrobe_agent.py, " + mono("node_assist") + " (create(... temperature=0.2 ...))"],
                 ["Tokens de sortie, réponses", "700 (" + mono("max_completion_tokens") + ")", "wardrobe_agent.py, " + mono("node_assist")],
                 ["Température, doublon", "<b>0,1</b>", "wardrobe_agent.py, " + mono("check_duplicate")],
                 ["Tokens de sortie, doublon", "250", "wardrobe_agent.py, " + mono("check_duplicate")],
                 ["Format de sortie, doublon", "JSON strict (" + mono("response_format=json_object") + ")", "wardrobe_agent.py, " + mono("check_duplicate")],
                 ["Tours d'outils maximum", "6 (réponses) ; 4 (doublon)", mono("MAX_ROUNDS") + " et l'argument " + mono("max_rounds")],
                 ["Résultats par recherche", "20", mono("MAX_RESULTS_PER_CALL") + " dans wardrobe_agent.py"],
                 ["Durée d'une proposition", "15 minutes", mono("PENDING_TTL") + " dans wardrobe_agent.py"],
                 ["Délai du LLM, essais", "45 s, 2 relances", mono("LLM_TIMEOUT") + " (config.py) et " + mono("max_retries=2")],
                 ["Longueur d'un message", "1 000 caractères", "wardrobe_agent.py (" + mono("text[:1000]") + ") et main.py"],
                 ["Délai A2A", "30 s (list) ; 60 s (ask)", "backend/app/wardrobe_a2a.py"],
                 ["Champs modifiables", "10 champs", mono("EDITABLE") + " dans wardrobe_agent.py"],
                 ["Mots du oui et du non", "regex FR et EN", mono("YES") + " et " + mono("NO") + " dans wardrobe_agent.py"],
                 ["Valeurs autorisées (catégories, couleurs...)", "listes fermées", "backend/app/taxonomy.py"]],
                [48, 50, 72]),
          P("Pour changer la température ou le nombre de tours, il faut éditer wardrobe_agent.py : ces deux valeurs ne sont pas dans le .env. "
            "Le modèle et la clé se changent dans le .env.", SMALL),
          H2_("7. Les fichiers liés"),
          table([["Fichier", "Rôle pour le Wardrobe Agent"],
                 ["backend/app/wardrobe_agent.py", "l'agent : outils, prompts, graphe, PendingStore, check_duplicate"],
                 ["backend/app/wardrobe_a2a.py", "client A2A que les autres agents utilisent pour lui parler (list, ask), avec repli en direct"],
                 ["backend/app/a2a_agents.py", "serveur A2A : handle_wardrobe, carte d'agent et 6 compétences"],
                 ["backend/app/main.py", "routes /api/wardrobe/agent et /api/agent/check-duplicate ; _validate_patch, _apply_patch ; wardrobe_agent.bind(...)"],
                 ["backend/app/taxonomy.py", "listes fermées : catégories, groupes, couleurs, saisons, occasions, styles, motifs"],
                 ["backend/app/config.py", "modèle, clé, délai du LLM"],
                 ["backend/app/storage.py", "accès Supabase (lecture et écriture des pièces)"],
                 ["agent_kit/tool_loop.py", "boucle d'outils LangGraph partagée par tous les agents"],
                 ["a2a_protocol/server.py, client.py", "protocole A2A (carte, message/send, tâches)"],
                 ["DressMe UI Blueprint/src/lib/api.ts", "wardrobeAgent() et checkDuplicate() côté page"],
                 ["DressMe UI Blueprint/src/features/wardrobe/WardrobePage.tsx", "zone de recherche IA, boutons Confirm / Cancel"],
                 ["backend/tests/test_wardrobe_agent.py, test_wardrobe_a2a.py", "10 + 6 tests"]],
                [70, 100]),
          PageBreak()]

    # ------------------------------------------------------------ 5
    s += [H2_("8. Interface A2A (/a2a/wardrobe)"),
          table([["data.action", "LLM ?", "Résultat"],
                 [mono("list"), "non", "text « N piece(s) », data.items = toute la garde-robe"],
                 [mono("search"), "non", "data.items trimmés selon data.filters"],
                 [mono("ask"), "oui, lecture seule", "data.reply, data.items, data.filters"],
                 [mono("check-duplicate"), "oui", "data = {duplicate, similar_item_id, note}"],
                 ["(texte libre)", "oui", "state completed ou input-required ; data.pending si une correction attend"]],
                [40, 40, 90]),
          P("Compétences publiées sur sa carte : wardrobe-search, wardrobe-read, wardrobe-correct, wardrobe-stats, wardrobe-similar, "
            "duplicate-check. Le jeton Supabase est exigé ; l'agent ne voit que les pièces de l'appelant."),
          H2_("9. Garde-fous"),
          *bullets(["<b>Pas d'outil d'écriture pour le LLM.</b> update_item ne fait que proposer.",
                    "<b>Même chemin d'écriture que la page</b> : _validate_patch (listes fermées, entiers de 1 à 5, nom non vide) puis _apply_patch ; "
                    "chaque correction est aussi enregistrée pour mesurer la précision du modèle de détection.",
                    "<b>Isolation</b> : une proposition est liée à (utilisateur, conversation) ; un autre utilisateur ou une autre conversation ne peut pas la confirmer.",
                    "<b>Réponses honnêtes</b> : si le LLM échoue, « The wardrobe agent is having trouble right now » ; si 6 tours ne suffisent pas, "
                    "« That took more digging than usual » ; si l'écriture est refusée, la raison est donnée.",
                    "<b>Jamais d'invention</b> : le prompt impose search_wardrobe avant de parler de ce que l'utilisateur possède, et seules les pièces "
                    "réellement renvoyées par les outils sont affichées."]),
          H2_("10. Limites"),
          *bullets(["Les filtres sont exacts : « bleu marine » ne trouve pas « bleu ».",
                    "Les propositions et les tâches A2A sont en mémoire du processus : un redémarrage de BO1 les efface.",
                    "Le texte libre dépend d'OpenAI ; sans clé, seules les actions structurées (list, search) fonctionnent.",
                    "Les autres agents lisent toute la garde-robe à chaque demande : correct pour quelques centaines de pièces, à surveiller au-delà.",
                    "L'agent suit les étiquettes de la garde-robe (catégorie, couleur...) : si une pièce est mal classée, il se trompe avec elle."]),
          H2_("11. Tests (16, tous verts)"),
          table([["Affirmation", "Test"],
                 ["Une correction n'est que proposée", "a_correction_is_only_proposed_and_nothing_is_saved_before_the_user_confirms"],
                 ["Écriture seulement après un oui dans la même conversation", "the_change_is_written_only_after_a_yes_in_the_same_conversation"],
                 ["Un non, une autre demande ou un autre utilisateur n'écrit jamais", "no_or_a_different_request_or_another_user_never_writes"],
                 ["Pièce inconnue, champ interdit, valeur invalide refusés", "an_unknown_piece_a_forbidden_field_or_an_invalid_value_is_refused_to_the_llm"],
                 ["Recherche : pièces et filtres renvoyés", "a_search_request_returns_the_pieces_the_llm_found_and_the_filters_it_chose"],
                 ["Statistiques et similarité calculées par le code", "stats_and_similar_pieces_are_computed_by_code"],
                 ["Contrôle de doublon : outil de recherche et JSON", "the_duplicate_check_of_the_live_scan_uses_the_search_tool_and_answers_in_json"],
                 ["Demande vide et LLM en panne", "an_empty_request_asks_what_to_do_and_a_failing_llm_is_reported"],
                 ["Boucle d'outils : tours, rappel, abandon propre", "the_tool_loop_runs_tools_nudges_once_and_reports_how_it_ended, ..._gives_up_cleanly"],
                 ["A2A : lecture avec le jeton, repli en direct, ask", "6 tests de test_wardrobe_a2a.py"]],
                [78, 92])]

    doc.build(s)
    print("written", OUT)


if __name__ == "__main__":
    build()
