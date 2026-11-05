"""All diagrams used by the DressMe presentation PDFs."""
from .common import CODE, DATA, EXT, GREY, INK, LLM, Diagram, chain


def T(lang, fr, en):
    return fr if lang == "fr" else en


def d_services(lang="fr"):
    g = Diagram(170, 118)
    ui = T(lang, "Interface React 19 (Vite, Tailwind)\nAI Stylist | Outfit Builder | Help Me Pack | Wardrobe | Should I buy | Dashboard",
            "React 19 interface (Vite, Tailwind)\nAI Stylist | Outfit Builder | Help Me Pack | Wardrobe | Should I buy | Dashboard")
    g.box(25, 104, 120, 10, ui, DATA, 7, True)
    cols = [(2, "BO1  :8000", T(lang, "Wardrobe Agent, YOLO\nAI Stylist, Outfit Agent\nShould I buy, avatar",
                                "Wardrobe Agent, YOLO\nAI Stylist, Outfit Agent\nShould I buy, avatar")),
            (44, "BO3  :8001", T(lang, "Gap Agent\nlacunes de garde-robe\nboutiques tunisiennes",
                                 "Gap Agent\nwardrobe gaps\nTunisian shops")),
            (86, "Help Me Pack  :8020", T(lang, "Trip Agent (LangGraph)\nsolveur OR-Tools CP-SAT",
                                          "Trip Agent (LangGraph)\nOR-Tools CP-SAT solver")),
            (128, "RAG  :8010", T(lang, "connaissance de mode\n38 PDF, pgvector\nreponses citees [S#]",
                                  "fashion knowledge\n38 PDFs, pgvector\ncited answers [S#]"))]
    for x, title, body in cols:
        g.box(x, 62, 40, 28, title + "\n" + body, CODE, 7)
        g.arrow(85, 104, x + 20, 90)
    g.box(2, 22, 48, 14, T(lang, "OpenAI GPT-4o\ngpt-4o-mini pour le Gap Agent",
                           "OpenAI GPT-4o\ngpt-4o-mini for the Gap Agent"), LLM, 7.2)
    g.box(61, 22, 48, 14, "Open-Meteo\n" + T(lang, "meteo et geocodage, sans cle",
                                              "weather and geocoding, no key"), EXT, 7.2)
    g.box(120, 22, 48, 14, "Supabase\n" + T(lang, "auth, base items, storage, pgvector",
                                             "auth, items, storage, pgvector"), DATA, 7.2)
    for x, _, _ in cols:
        g.arrow(x + 20, 62, 26, 36, GREY, True)
        g.arrow(x + 20, 62, 85, 36, GREY, True)
        g.arrow(x + 20, 62, 144, 36, GREY, True)
    g.arrow(148, 62, 144, 36)
    g.label(85, 12, T(lang, "BO1 appelle le RAG (8010) comme outil ; l'interface appelle les 3 autres services directement.",
                      "BO1 calls the RAG (8010) as a tool; the interface calls the other services directly."), 7.2, GREY)
    g.legend(lang)
    return g.d


def d_data(lang="fr"):
    g = Diagram(170, 96)
    g.label(2, 90, "A. " + T(lang, "Authentification et identite de la requete",
                             "Authentication and request identity"), 8, INK, "start", True)
    row = [T(lang, "Utilisateur\nnavigateur", "User / browser"), "Supabase Auth\nJWT token",
           "React 19\nAuthorization: Bearer", T(lang, "Dependance FastAPI\nuser_id verifie",
                                                 "FastAPI dependency\nverified user_id")]
    x = 2
    for text, fill in zip(row, (DATA, EXT, CODE, CODE)):
        g.box(x, 72, 36, 14, text, fill, 6.8)
        x += 44
    for i in range(3):
        g.arrow(2 + i * 44 + 36, 79, 2 + (i + 1) * 44, 79)
    g.label(2, 65, "B. " + T(lang, "Stockage", "Stores"), 8, INK, "start", True)
    stores = [(2, 40, T(lang, "Postgres\nitems, profils, tenues", "Postgres\nitems, profiles, outfits")),
              (48, 40, T(lang, "Stockage\nphotos + detourages", "Storage\nphotos + cutouts")),
              (94, 34, T(lang, "pgvector\nknowledge_chunks_v2", "pgvector\nknowledge_chunks_v2")),
              (134, 34, T(lang, "Service RAG\n:8010", "RAG service\n:8010"))]
    for x, w, text in stores:
        g.box(x, 44, w, 16, text, DATA, 6.8)
    g.label(2, 37, "C. " + T(lang, "Memoire", "Memory"), 8, INK, "start", True)
    mem = [(2, 40, T(lang, "Conversation\ncheckpointer LangGraph\n8 a 16 derniers echanges",
                       "Conversation\nLangGraph checkpointer\nlast 8-16 turns")),
           (48, 40, T(lang, "Proposition\nWardrobe Agent\n15 min, par utilisateur",
                       "Wardrobe proposal\n15-minute TTL\nper user + thread")),
           (94, 34, T(lang, "Session Trip\nAgentState + 16 messages\nverrou en memoire",
                       "Trip session\nAgentState + 16 msgs\nin-process lock")),
           (134, 34, T(lang, "Gap Agent\nanalyses passees\nretours utilisateur",
                        "Gap Agent\npast analyses\nfeedback loop"))]
    for x, w, text in mem:
        g.box(x, 14, w, 18, text, CODE, 6.6)
    g.arrow(60, 44, 20, 32, GREY, True)
    g.arrow(112, 44, 68, 32, GREY, True)
    g.legend(lang, y=1)
    return g.d


def d_vision(lang="fr"):
    steps = [(T(lang, "photo", "photo"), DATA), ("YOLO\nsegmentation", CODE),
             (T(lang, "couleurs mesurees\nsur les pixels", "colours measured\non pixels"), CODE),
             ("GPT-4o vision\n" + T(lang, "JSON strict", "strict JSON"), LLM),
             (T(lang, "fiche vetement\n20 categories", "item record\n20 categories"), DATA)]
    notes = [T(lang, "D'abord le detecteur, ensuite le LLM : le modele affine mais n'invente jamais un vetement absent de la photo.",
                  "Detector first, LLM second: the model refines but never invents a garment that is not in the photo."),
             T(lang, "Sans cle API ou en cas d'erreur du modele : repli deterministe (fallback_enrich), la fiche reste utilisable.",
                  "No API key or model error: deterministic fallback (fallback_enrich) still creates a usable item.")]
    return chain(steps, height=50, notes=notes, legend_lang=lang)


def d_langgraph(lang="fr"):
    g = Diagram(170, 120)
    g.label(2, 114, "A. " + T(lang, "Anatomie d'une machine a etats LangGraph",
                             "Anatomy of a LangGraph state machine"), 8, INK, "start", True)
    g.box(2, 88, 32, 14, "State\nTypedDict", DATA, 6.9)
    g.box(40, 88, 22, 14, "START", CODE, 6.9)
    g.box(70, 88, 32, 14, T(lang, "noeud", "node") + "\n(" + T(lang, "fonction pure", "pure function") + ")", CODE, 6.9)
    g.box(110, 88, 30, 14, T(lang, "arete\nconditionnelle", "conditional\nedge"), LLM, 6.9)
    g.box(148, 88, 20, 14, "END", CODE, 6.9)
    for x1, x2 in ((34, 40), (62, 70), (102, 110), (140, 148)):
        g.arrow(x1, 95, x2, 95)
    g.box(40, 66, 70, 14, T(lang, "checkpointer : un fil par utilisateur et par conversation",
                            "checkpointer: one thread per user and conversation"), CODE, 6.6)
    g.arrow(18, 88, 50, 80, GREY, True)

    g.label(2, 56, "B. " + T(lang, "Boucle d'outils partagee (agent_kit/tool_loop.py)",
                             "Shared tool loop (agent_kit/tool_loop.py)"), 8, INK, "start", True)
    g.box(2, 26, 34, 22, "llm\n" + T(lang, "le modele choisit\nune action",
                                    "the model chooses\nan action"), LLM, 6.8)
    g.box(50, 26, 30, 22, "tools\n" + T(lang, "execution validee\npar Pydantic",
                                       "Pydantic-validated\nexecution"), CODE, 6.8)
    g.box(96, 26, 30, 22, "nudge\n" + T(lang, "rappel unique si\nun outil est saute",
                                       "single reminder\nif it skips a tool"), CODE, 6.8)
    g.box(142, 26, 26, 22, "finish\n" + T(lang, "reponse finale", "final answer"), DATA, 6.8)
    g.arrow(36, 41, 50, 41)
    g.arrow(126, 37, 142, 37)
    g.polyline([(65, 26), (65, 21), (19, 21), (19, 26)], GREY, True)
    g.polyline([(111, 26), (111, 15), (28, 15), (28, 26)], GREY, True)
    g.label(42, 23, T(lang, "resultat d'outil", "tool result"), 6.4, GREY)
    g.label(69, 12, T(lang, "rappel une seule fois", "reminder only once"), 6.4, GREY)
    g.legend(lang, y=1)
    return g.d


def d_stylist(lang="fr"):
    g = Diagram(170, 92)
    g.box(2, 70, 34, 14, T(lang, "Question\n+ ville, pays, unite", "Question\n+ city, country, unit"), DATA, 7.2)
    g.box(52, 66, 44, 22, "AI Stylist (GPT-4o)\ntemperature 0,3\n" + T(lang, "sortie JSON, 8 tours",
                                                                       "JSON output, 8 rounds"), LLM, 7.2)
    g.arrow(36, 77, 52, 77)
    tools = [(116, 70, "search_wardrobe", T(lang, "filtre le vrai placard", "filters the real wardrobe"), CODE),
             (116, 46, "get_weather", T(lang, "Open-Meteo, cache 30 min", "Open-Meteo, 30-min cache"), EXT),
             (116, 22, "fashion_advice", T(lang, "RAG : livres, sources [S#]", "RAG books, [S#] sources"), EXT)]
    for x, y, name, desc, fill in tools:
        g.box(x, y, 52, 16, name + "\n" + desc, fill, 7.0)
        g.arrow(96, 77, x, y + 8, GREY)
        g.arrow(x, y + 5, 96, 72, GREY, True)
    g.box(2, 40, 44, 22, T(lang, "rappel unique si le modele\nsaute la meteo ou le RAG\n(regex question de style)",
                           "single reminder if the model\nskips weather or RAG\n(regex on style questions)"), CODE, 6.8)
    g.arrow(52, 70, 46, 56, GREY, True)
    g.box(2, 8, 100, 20, T(lang, "answer | weather | outfit | why | alternatives | tips\nsources citees seulement | pieces du placard reel",
                           "answer | weather | outfit | why | alternatives | tips\nsources cited only | items found in the real wardrobe"), DATA, 7)
    g.arrow(74, 66, 62, 28)
    g.legend(lang, y=0.5)
    return g.d


def d_wardrobe(lang="fr"):
    g = Diagram(170, 84)
    g.box(2, 60, 34, 16, T(lang, "message / voix\n+ data.action", "message / voice\n+ data.action"), DATA, 6.9)
    g.box(46, 56, 42, 24, "gate\n" + T(lang, "correction en attente ?", "pending correction?"), LLM, 7.2)
    g.arrow(36, 68, 46, 68)
    g.box(98, 66, 32, 14, "apply\n" + T(lang, "oui explicite", "explicit yes"), CODE, 6.9)
    g.box(98, 46, 32, 14, "cancel\n" + T(lang, "non explicite", "explicit no"), CODE, 6.9)
    g.box(140, 56, 28, 24, "assist\n" + T(lang, "boucle d'outils", "tool loop"), LLM, 6.9)
    g.arrow(88, 72, 98, 72)
    g.arrow(88, 64, 98, 53)
    g.arrow(88, 60, 140, 66)
    g.box(46, 10, 62, 22, "search_wardrobe\nfind_similar\nwardrobe_stats\nupdate_item (" +
          T(lang, "proposition seule", "proposal only") + ")", CODE, 6.6)
    g.arrow(154, 56, 108, 32)
    g.box(116, 10, 52, 22, T(lang, "aucun outil LLM n'ecrit :\nle noeud apply ecrit\napres un oui de l'utilisateur",
                             "no LLM write tool:\nthe apply node writes\nonly after the user says yes"), DATA, 6.6)
    g.arrow(108, 21, 116, 21)
    g.legend(lang, y=0.5)
    return g.d


def d_similar(lang="fr"):
    g = Diagram(170, 70)
    steps = [(T(lang, "photo d'une\ntenue", "photo of\nan outfit"), DATA),
             ("analyze\nall_items", CODE),
             (T(lang, "pieces detectees\nvs garde-robe", "pieces detected\nvs wardrobe"), CODE),
             ("ask_wardrobe\nagent (A2A)", LLM),
             (T(lang, "juge\nstatuts", "judge\nstatuses"), LLM),
             (T(lang, "verification\npar le code", "check\nby code"), CODE),
             ("owned | close\n| missing", DATA)]
    x = 2
    w, gap = 22, 24
    pos = []
    for text, fill in steps:
        g.box(x, 38, w, 20, text, fill, 6.0)
        pos.append(x)
        x += gap
    for i in range(len(steps) - 1):
        g.arrow(pos[i] + w, 48, pos[i + 1], 48)
    g.label(85, 29, T(lang, "le LLM propose, le code verifie chaque identifiant cite",
                      "the LLM proposes, the code verifies every cited item id"), 7, GREY)
    g.label(85, 23, T(lang, "les pieces manquantes renvoient vers BO3 et l'essayage virtuel",
                      "missing pieces link to BO3 and virtual try-on"), 7, GREY)
    g.legend(lang, y=1)
    return g.d


def d_outfit(lang="fr"):
    g = Diagram(170, 78)
    nodes = [("weather", T(lang, "prevision reelle\nde la ville", "real forecast\nfor the city"), EXT),
             ("closet", T(lang, "pieces par role\n+ faits", "pieces by role\n+ facts"), CODE),
             ("knowledge", T(lang, "2 questions\nau RAG", "2 questions\nto the RAG"), EXT),
             ("compose", T(lang, "LLM : 3 tenues\n(ids du placard)", "LLM: 3 outfits\n(wardrobe ids)"), LLM),
             ("validate", T(lang, "controles\ndu code", "code checks"), CODE)]
    x = 2
    pos = []
    for name, body, fill in nodes:
        g.box(x, 38, 28, 22, name + "\n" + body, fill, 7.0)
        pos.append(x)
        x += 33
    g.label(1, 66, "START", 7, INK, "start", True)
    for i in range(len(nodes) - 1):
        g.arrow(pos[i] + 28, 49, pos[i + 1], 49)
    g.polyline([(pos[4] + 14, 38), (pos[4] + 14, 30), (pos[3] + 14, 30), (pos[3] + 14, 38)], INK, True)
    g.label((pos[3] + pos[4]) / 2 + 14, 25.5, T(lang, "erreurs : le LLM corrige (1 fois)",
                                                "errors: the LLM fixes once"), 7, INK)
    g.arrow(pos[4] + 14, 60, pos[4] + 14, 72, INK)
    g.label(pos[4] + 14, 74, T(lang, "END : tenues valides", "END: valid outfits"), 7, INK, bold=True)
    g.box(2, 4, 88, 14, T(lang, "Etat partage : items, occasion, saison, ville, avoid,\nforecast, closet, advice, sources, draft, problems",
                          "shared state: items, occasion, season, city, avoid,\nforecast, closet, advice, sources, draft, problems"), DATA, 6.6)
    g.legend(lang, y=0.4)
    return g.d


def d_trip(lang="fr"):
    g = Diagram(170, 100)
    g.label(2, 94, T(lang, "Graphe 1 : conversation (LangGraph)", "Graph 1: conversation (LangGraph)"),
            8, INK, "start", True)
    g.box(2, 74, 32, 14, "intake\n" + T(lang, "extraction du voyage", "trip extraction"), LLM, 7)
    g.box(48, 74, 30, 14, "plan\n" + T(lang, "si tout est connu", "if all is known"), CODE, 7)
    g.arrow(34, 81, 48, 81)
    g.arrow(78, 81, 92, 81)
    g.box(92, 74, 50, 14, T(lang, "sinon : une question\npuis arret (END)",
                           "otherwise: one question\nthen stop (END)"), DATA, 7)
    g.label(2, 66, T(lang, "Graphe 2 : workflow deterministe (chaque noeud s'arrete si l'etape precedente echoue)",
                     "Graph 2: deterministic workflow (each node stops if the previous step fails)"), 8, INK, "start", True)
    steps = [("weather", "Open-Meteo", EXT), ("wardrobe", "CSV + pandas", DATA),
             ("requirements", T(lang, "regles / jour", "rules / day"), CODE),
             ("optimize", "OR-Tools\nCP-SAT", CODE),
             ("finish", T(lang, "checklist ou\nalternatives", "checklist or\nalternatives"), CODE)]
    x = 2
    pos = []
    for name, body, fill in steps:
        g.box(x, 42, 29, 18, name + "\n" + body, fill, 7)
        pos.append(x)
        x += 34
    for i in range(len(steps) - 1):
        g.arrow(pos[i] + 29, 51, pos[i + 1], 51)
    g.label(2, 33, T(lang, "Boucle d'outils GPT-4o (temperature 0, 12 iterations max) : 10 outils valides par Pydantic",
                     "GPT-4o tool loop (temperature 0, 12 iterations max): 10 tools validated by Pydantic"), 8, INK, "start", True)
    names = ["get_trip_details", "get_weather", "get_wardrobe", "get_activity_requirements", "optimize_trip",
             "generate_checklist", "suggest_alternatives", "update_trip", "update_checklist", "check_gaps"]
    for i, name in enumerate(names):
        col, row = i % 5, i // 5
        g.box(2 + col * 34, 14 - row * 11 + 4, 31, 8, name, LLM if i in (0, 7) else CODE, 6.2)
    g.legend(lang, y=0.4)
    return g.d


def d_gap(lang="fr"):
    g = Diagram(170, 72)
    g.box(2, 44, 34, 18, T(lang, "Demande\n(objectif : winter_work...)",
                           "Request\n(goal: winter_work...)"), DATA, 7)
    g.box(48, 40, 44, 26, "Gap Agent BO3\ngpt-4o-mini, temp. 0,2\n" + T(lang, "6 etapes max", "6 steps max"), LLM, 7.2)
    g.arrow(36, 53, 48, 53)
    tools = [("get_wardrobe", 104, 52), ("compute_coverage", 104, 40), ("rank_gaps (XGBoost)", 104, 28),
             ("get_past_analyses", 104, 16), ("show_items (photos)", 104, 4)]
    for name, x, y in tools:
        g.box(x, y, 62, 9, name, CODE, 7)
        g.arrow(92, 53, x, y + 4.5, GREY)
    g.box(2, 8, 80, 22, T(lang, "regles deterministes : une lacune n'existe que si la\ncouverture la signale. XGBoost ne fait qu'ordonner.\nSortie : lacunes classees + pieces deja couvertes",
                           "deterministic rules: a gap exists only if coverage\nflags it. XGBoost only ranks. Output: ranked gaps\n+ already-covered pieces"), DATA, 6.8)
    g.legend(lang, y=0.4)
    return g.d


def d_purchase(lang="fr"):
    g = Diagram(170, 96)
    top = [(2, 24, T(lang, "photo", "photo")),
           (30, 34, T(lang, "detecteur +\nLLM vision", "detector +\nLLM vision")),
           (68, 40, T(lang, "Qwen2.5-3B + LoRA\nboucle d'outils", "Qwen2.5-3B + LoRA\ntool loop agent")),
           (112, 32, T(lang, "verdict JSON\nverifie par le code", "JSON verdict\nchecked by code")),
           (148, 20, "GPT-4o\n" + T(lang, "reecrit", "rewrites"))]
    fills = [DATA, CODE, LLM, CODE, LLM]
    for (x, w, text), fill in zip(top, fills):
        g.box(x, 72, w, 16, text, fill, 6.6)
    for (x1, w, _), (x2, _, _) in zip(top, top[1:]):
        g.arrow(x1 + w, 80, x2, 80)
    names = ["analyze_item", "similar_items", "outfit_compat", "wardrobe_gaps", "predict_ml", "purchase_value"]
    for i, name in enumerate(names):
        g.box(2 + i * 28, 46, 24, 9, name, CODE, 5.9)
    g.arrow(94, 72, 94, 55, GREY, True)
    g.box(2, 14, 78, 22, T(lang, "sans HF_TOKEN / GPU / reseau :\nrepli deterministe (XGBoost + regles)\ndecision_source = deterministic",
                           "without HF_TOKEN / GPU / network:\ndeterministic fallback (XGBoost + rules)\ndecision_source = deterministic"), DATA, 6.6)
    g.box(88, 14, 80, 22, T(lang, "le LLM ne decide jamais seul : les outils calculent\nsur la vraie garde-robe et le code valide le verdict\n(libelle connu, score 0-100, ids reels)",
                            "the LLM never decides alone: tool results are computed\non the real wardrobe and the code validates the verdict\n(known label, score 0-100, real item ids)"), CODE, 6.6)
    g.arrow(60, 46, 41, 36, GREY, True)
    g.legend(lang, y=1)
    return g.d


def d_bo4(lang="fr"):
    g = Diagram(170, 96)
    g.label(2, 90, T(lang, "Stylist BO4 (bo4/, autonome, non branche a React)",
                     "Stylist BO4 (bo4/, standalone, not wired to React)"), 8, INK, "start", True)
    row1 = [("extract_intent", 0), ("get_weather", 1), ("fetch_wardrobe", 2), ("apply_constraints", 3),
            ("recommend", 4)]
    for name, i in row1:
        g.box(2 + i * 33, 66, 29, 14, name, LLM if i in (0, 4) else CODE, 6.3)
    for i in range(4):
        g.arrow(2 + i * 33 + 29, 73, 2 + (i + 1) * 33, 73)
    g.arrow(148, 66, 148, 54)
    row2 = [("style_advice", 134, LLM), ("respond", 101, DATA), ("clarify", 68, DATA),
            ("record_feedback", 35, CODE)]
    for name, x, fill in row2:
        g.box(x, 40, 29, 14, name, fill, 6.3)
    for i in range(len(row2) - 1):
        g.arrow(row2[i][1], 47, row2[i + 1][1] + 29, 47)
    g.box(2, 10, 104, 22, T(lang, "Ollama qwen2.5:3b, local, sans cle API\nscore heuristique : couleur 0,30 + style 0,20 + occasion 0,30 + saison 0,20",
                            "Ollama qwen2.5:3b, local, no API key\nheuristic score: colour 0.30 + style 0.20 + occasion 0.30 + season 0.20"), DATA, 6.4)
    g.box(114, 10, 54, 22, T(lang, "9 noeuds, deterministes\nautour du LLM\ntemperature 0,2",
                             "9 nodes, deterministic\nscoring around the LLM\ntemperature 0.2"), CODE, 6.4)
    g.legend(lang, y=0.5)
    return g.d


def d_orchestrator(lang="fr"):
    g = Diagram(170, 122)
    g.label(2, 116, T(lang, "A. Orchestrateur BO1 : POST /api/assistant/chat",
                      "A. BO1 orchestrator: POST /api/assistant/chat"), 8, INK, "start", True)
    g.box(2, 96, 30, 14, T(lang, "message\n+ user_id", "user message\n+ user_id"), DATA, 6.6)
    g.box(40, 92, 34, 18, "route\nGPT-4o JSON", LLM, 7)
    g.arrow(32, 103, 40, 101)
    branches = ["stylist", "wardrobe", "outfit", "trip (A2A)", "gap (A2A)", "redirect", "clarify"]
    x = 2
    pos = []
    for name in branches:
        g.box(x, 66, 22, 12, name, CODE if "A2A" not in name else EXT, 6.0)
        pos.append(x)
        x += 24
    for px in pos:
        g.arrow(57, 92, px + 11, 78, GREY)
    g.box(46, 42, 60, 14, T(lang, "respond + historique du fil", "respond + thread history"), DATA, 6.8)
    for px in pos:
        g.arrow(px + 11, 66, 76, 56, GREY)
    g.box(2, 42, 38, 14, T(lang, "checkpointer\npar utilisateur + fil",
                           "checkpointer\nper user + thread"), CODE, 6.4)
    g.arrow(40, 49, 46, 49)

    g.label(2, 34, T(lang, "B. Orchestrateur autonome (orchestrator/, port 8070)",
                     "B. Standalone orchestrator (orchestrator/, port 8070)"), 8, INK, "start", True)
    row = ["route_intent", "stylist", "wardrobe", "purchase", "knowledge", "external", "clarify", "respond"]
    for i, name in enumerate(row):
        g.box(2 + i * 21, 10, 18, 14, name, LLM if i == 0 else CODE, 5.6)
    for i in range(len(row) - 1):
        g.arrow(2 + i * 21 + 18, 17, 2 + (i + 1) * 21, 17)
    g.legend(lang, y=0.5)
    return g.d


def d_a2a(lang="fr"):
    g = Diagram(170, 118)
    g.box(45, 104, 80, 10, T(lang, "Agent client (orchestrateur, script, autre agent)",
                             "Client agent (orchestrator, script, another agent)"), DATA, 7, True)
    g.label(85, 99.5, T(lang, "1. GET .well-known/agent-card.json  (public : qui es-tu, que sais-tu faire ?)",
                        "1. GET .well-known/agent-card.json  (public: who are you, what can you do?)"), 6.8, GREY)
    g.label(85, 95.5, T(lang, "2. POST JSON-RPC message/send  + Authorization: Bearer (jeton Supabase)",
                        "2. POST JSON-RPC message/send  + Authorization: Bearer (Supabase token)"), 6.8, GREY)
    cols = [(2, "AI Stylist", "BO1 :8000\n/a2a/stylist\nstyle-advice\nwardrobe-search", LLM),
            (44, "Outfit Builder", "BO1 :8000\n/a2a/outfit\nbuild-outfits", LLM),
            (86, "Trip Agent", "Help Me Pack :8020\n/a2a/trip\nplan-trip-packing", LLM),
            (128, "Gap Agent", "BO3 :8001\n/a2a/gap\nwardrobe-gaps", LLM)]
    for x, title, body, fill in cols:
        g.box(x, 60, 40, 26, title + "\n" + body, fill, 6.9)
        g.arrow(85, 92, x + 20, 86)
    g.polyline([(106, 60), (106, 48), (148, 48), (148, 60)], INK, True)
    g.label(127, 43, T(lang, "Trip Agent -> Gap Agent : outil check_gaps, meme jeton, capsule du voyage en donnees",
                       "Trip Agent -> Gap Agent: check_gaps tool, same token, trip capsule as data"), 6.8, INK)
    g.box(2, 18, 80, 18, T(lang, "Tache A2A : submitted, working, input-required, completed,\nfailed, canceled, rejected. Resultat : message texte +\nartefact JSON (donnees structurees).",
                           "A2A task: submitted, working, input-required, completed,\nfailed, canceled, rejected. Result: text message +\nJSON artifact (structured data)."), DATA, 6.8)
    g.box(90, 18, 78, 18, T(lang, "Erreurs JSON-RPC : -32700 JSON invalide, -32600 requete, -32601\nmethode, -32602 parametres, -32001 tache inconnue,\n-32002 non annulable, -32004 operation non supportee.",
                            "JSON-RPC errors: -32700 parse, -32600 request, -32601 method,\n-32602 params, -32001 unknown task, -32002 not cancelable,\n-32004 unsupported operation."), CODE, 6.8)
    g.legend(lang, y=4)
    return g.d


def d_rag(lang="fr"):
    g = Diagram(170, 120)
    g.label(2, 114, "A. " + T(lang, "Ingestion (hors ligne)", "Ingestion (offline)"), 8, INK, "start", True)
    ing = [T(lang, "38 PDF", "38 PDFs"), "PyMuPDF\n+ Tesseract OCR",
           T(lang, "controle qualite\n+ chunking", "quality control\n+ chunking"),
           "embeddings\nMiniLM 384 d", "Supabase\npgvector (HNSW)"]
    x = 2
    pos = []
    for i, text in enumerate(ing):
        g.box(x, 94, 28, 15, text, DATA if i in (0, 4) else CODE, 7)
        pos.append(x)
        x += 34
    for i in range(len(ing) - 1):
        g.arrow(pos[i] + 28, 101.5, pos[i + 1], 101.5)
    g.label(2, 86, "B. " + T(lang, "Question (en ligne)", "Question (online)"), 8, INK, "start", True)
    q = [(T(lang, "question\n(FR ou EN)", "question\n(FR or EN)"), DATA),
         (T(lang, "traduction FR vers EN\n+ glossaire", "translate FR -> EN\n+ glossary"), CODE),
         (T(lang, "recherche hybride\nvecteur + texte", "hybrid search\nvector + full text"), CODE),
         (T(lang, "fusion RRF\ntop 5 passages", "RRF fusion\ntop 5 passages"), CODE),
         (T(lang, "reponse avec\nles sources [S#]", "LLM answers with\n[S#] sources only"), LLM)]
    x = 2
    pos = []
    for text, fill in q:
        g.box(x, 62, 28, 18, text, fill, 6.8)
        pos.append(x)
        x += 34
    for i in range(len(q) - 1):
        g.arrow(pos[i] + 28, 71, pos[i + 1], 71)
    g.polyline([(pos[4] + 14, 62), (pos[4] + 14, 52), (pos[2] + 14, 52), (pos[2] + 14, 62)], GREY, True)
    g.label(pos[3] + 4, 54.5, T(lang, "lit knowledge_chunks_v2", "reads knowledge_chunks_v2"), 6.8, GREY)
    g.box(2, 22, 78, 20, T(lang, "POST /ask -> {answer, citations[{marker, title, page}], grounded}\nrien trouve : reponse fixe \"I don't know\"\nsans citation : la reponse est ecartee par le client",
                           "POST /ask -> {answer, citations[{marker, title, page}], grounded}\nnothing found: fixed answer \"I don't know\"\nno citation: the answer is rejected by the client"), DATA, 7)
    g.box(92, 22, 76, 20, T(lang, "rag_client.advise(question) (BO1)\nrenvoie {answer, sources, grounded} ou None\nles agents gardent les marqueurs [S1]",
                            "rag_client.advise(question) (BO1)\nreturns {answer, sources, grounded} or None\nthe agents keep the [S1] markers"), CODE, 7)
    g.arrow(80, 32, 92, 32)
    g.legend(lang, y=8)
    return g.d
