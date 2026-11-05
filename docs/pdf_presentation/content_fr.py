"""French content of the DressMe presentation PDF."""
from reportlab.platypus import PageBreak, Spacer

from .common import CAP, H2, H2_, H3_, P, bullets, code, numbered, table
from .diagrams import (d_a2a, d_bo4, d_data, d_gap, d_langgraph, d_orchestrator, d_outfit, d_purchase, d_rag,
                       d_services, d_similar, d_stylist, d_trip, d_vision, d_wardrobe)


def build_story():
    s = []

    # 1 ------------------------------------------------------------------------------------------------
    s += [P("1. Resume executif", "H1"),
          P("DressMe est une application de garde-robe intelligente. L'utilisateur photographie ses vetements, "
            "l'application les catalogue automatiquement (detecteur YOLO + GPT-4o vision), puis huit agents "
            "LangGraph l'aident a s'habiller, a construire des tenues, a preparer une valise, a reperer les "
            "lacunes de sa garde-robe et a decider d'un achat. Un orchestrateur unique donne un seul point "
            "d'entree conversationnel."),
          P("Le principe d'architecture est constant : <b>le LLM decide et redige, le code deterministe verifie "
            "et calcule</b>. Aucun agent ne peut citer une piece absente du placard, inventer une prevision "
            "meteo ou citer une source qui n'existe pas dans le RAG."),
          table([["Indicateur", "Valeur"],
                 ["Agents LangGraph", "8 (dont 1 orchestrateur) et 2 orchestrateurs alternatifs"],
                 ["Services FastAPI", "BO1 8000, BO3 8001, Help Me Pack 8020, RAG 8010, orchestre 8070"],
                 ["Modeles LLM", "GPT-4o, gpt-4o-mini, Qwen2.5-3B + LoRA, Ollama qwen2.5:3b"],
                 ["Corpus RAG", "38 PDF, 14 574 chunks, all-MiniLM-L6-v2 (384 dimensions)"],
                 ["Qualite RAG", "Hit@5 91,67 %, MRR 85,42 %, precision du contexte 71,67 %"],
                 ["Tests", "101 orchestrateur, 85 backend, 30 frontend, 1 095 BO4 (25 ignores)"],
                 ["Protocole agent a agent", "A2A 0.3.0 sur JSON-RPC 2.0"],
                 ["Categories de vetements", "20 classes detectees et cataloguees"],
                 ["Outils du Trip Agent", "10 outils valides par Pydantic + solveur OR-Tools CP-SAT"]],
                [46, 124]),
          H2_("Ce qui distingue le projet"),
          *bullets(["<b>Ancrage fort</b> : les identifiants de pieces viennent toujours de la vraie garde-robe ; "
                    "la meteo vient d'Open-Meteo ; les conseils de mode viennent de livres, avec des marqueurs [S#].",
                    "<b>Verification par code</b> : une tenue est validee par des regles (robe seule ou haut + bas, "
                    "chaussures obligatoires, pas deux pieces du meme role), un verdict d'achat est valide par du code.",
                    "<b>Degradation douce</b> : RAG, meteo, LLM ou Hugging Face indisponibles entrainent un repli "
                    "deterministe, jamais une page cassee.",
                    "<b>Communication standard</b> : chaque agent publie une carte A2A et accepte des taches JSON-RPC, "
                    "ce qui permet a l'orchestrateur de deleguer sans connaitre les routes internes."]),
          PageBreak()]

    # 2 ------------------------------------------------------------------------------------------------
    s += [P("2. Le produit : onze ecrans, huit agents", "H1"),
          P("Chaque page de l'interface appelle une route ; la route appelle soit un <b>agent</b> (le LLM choisit "
            "des outils ou suit un graphe), soit un <b>moteur</b> (detecteur, moteur d'achat, comparaison locale)."),
          table([["Ecran", "Route", "Agent / moteur", "Entree", "Sortie"],
                 ["AI Stylist + voix", "POST /api/agent/search", "AI Stylist (LangGraph)", "message, ville, pays, unite", "conseil, meteo, tenue, raisons, sources"],
                 ["Wardrobe", "POST /api/wardrobe/agent", "Wardrobe Agent (LangGraph)", "message, action", "pieces, filtres, proposition"],
                 ["Outfit Builder", "POST /api/outfits/agent", "Outfit Builder (LangGraph)", "occasion, saison, ville, avoid", "3 tenues validees + sources"],
                 ["Help Me Pack", "POST :8020/api/trips", "Trip Agent + CP-SAT", "message, session_id", "valise, checklist, alternatives"],
                 ["Wardrobe Gaps", "POST :8001/api/bo3/agent", "Gap Agent + XGBoost", "message, objectif", "lacunes classees, pieces couvertes"],
                 ["Live scan", "/api/items/quick-detect + check-duplicate", "YOLO + Wardrobe Agent", "flux camera", "cadres, qualite, doublon"],
                 ["Should I buy this?", "POST /api/shopping-assistant/evaluate", "Qwen + 6 outils + GPT-4o", "photo de l'article", "verdict BUY / CONSIDER / SKIP"],
                 ["Find Similar", "POST /api/items/analyze (all_items)", "YOLO + comparaison locale", "photo d'une tenue", "owned / close / missing"],
                 ["Ajout, garde-robe, 3D", "/api/items/analyze, /api/items", "YOLO + catalogage vision", "photo", "fiche vetement, modele 3D"],
                 ["Dashboard", "/api/items + :8001 gaps", "Gap Agent + regles locales", "aucune", "statistiques, tenue du jour"],
                 ["Avatar, essayage", "/api/avatar/*, tryon-outfit", "WaveSpeed / fal.ai", "photo, tenue", "image generee, suivi de tache"]],
                [26, 38, 40, 30, 36], size=7.4),
          Spacer(1, 6),
          P("Les agents ne filtrent plus la garde-robe eux-memes : ils la <b>demandent au Wardrobe Agent</b> en "
            "langage naturel, par appel direct dans BO1 ou par A2A pour le Trip Agent. Trois composants LLM ne sont "
            "pas des agents : le catalogage vision, le calcul des preuves d'achat et la generation de reponse du RAG."),
          PageBreak()]

    # 3 ------------------------------------------------------------------------------------------------
    s += [P("3. Architecture globale", "H1"),
          P("Quatre services FastAPI independants sont appeles par l'interface React 19. Supabase fournit "
            "l'authentification, la base de donnees et le stockage. OpenAI fournit les LLM, Open-Meteo la meteo reelle."),
          d_services("fr"), P("Figure 1 : services, ports et dependances externes.", CAP),
          table([["Service", "Port", "Stack", "Role"],
                 ["BO1 (backend/app)", "8000", "FastAPI, LangGraph, YOLO", "garde-robe, detecteur, AI Stylist, Outfit Agent, Similar Agent, Purchase Agent, avatar"],
                 ["BO3 (DressMe UI Blueprint)", "8001", "FastAPI, gpt-4o-mini, XGBoost", "Gap Agent, produits de boutiques tunisiennes"],
                 ["Help Me Pack", "8020", "FastAPI, LangGraph, OR-Tools", "Trip Agent, solveur CP-SAT, checklist"],
                 ["RAG (rag_backend)", "8010", "FastAPI, pgvector, MiniLM", "connaissance de mode citee, reponses [S#]"],
                 ["Orchestrateur autonome", "8070", "FastAPI, LangGraph, Ollama", "ancien orchestrateur, conserve comme alternative locale"],
                 ["Interface (Vite)", "8443", "React 19, Tailwind", "application web, https de developpement"],
                 ["Ollama", "11434", "qwen2.5:3b", "LLM local du Stylist BO4 et du routeur 8070"]],
                [40, 12, 46, 72], size=7.6),
          PageBreak()]

    # 4 ------------------------------------------------------------------------------------------------
    s += [P("4. Donnees, authentification et memoire", "H1"),
          P("Chaque requete est portee par un jeton Supabase. Une dependance FastAPI le verifie et expose un "
            "<b>user_id</b> ; toutes les requetes SQL sont filtrees par cet identifiant. Un utilisateur ne peut donc "
            "jamais lire ou modifier le placard d'un autre, y compris via une tache A2A."),
          d_data("fr"), P("Figure 2 : identite de la requete, stockage et memoires.", CAP),
          H2_("Stockage"),
          table([["Store", "Contenu", "Utilise par"],
                 ["Postgres items", "fiche vetement : categorie, couleur, matiere, saison, occasion, style, chaleur, image", "tous les agents"],
                 ["Postgres profiles", "ville, pays, unite, preferences, departement", "AI Stylist, Outfit, Gap"],
                 ["Storage", "photos originales et cutouts transparents", "interface, essayage, 3D"],
                 ["pgvector knowledge_chunks_v2", "14 574 passages + embeddings 384 d, index HNSW cosinus", "service RAG"],
                 ["Outfits, feedback", "tenues sauvegardees, retours sur les suggestions", "Outfit Builder, Gap Agent"]],
                [40, 86, 44], size=7.6),
          H2_("Memoires des agents"),
          table([["Memoire", "Portee", "Duree"],
                 ["Checkpointer LangGraph", "un fil par utilisateur et par conversation ; 8 derniers echanges", "persistante cote serveur"],
                 ["Wardrobe Agent", "proposition de correction en attente (oui / non)", "15 minutes, liee a l'utilisateur"],
                 ["Trip Agent", "AgentState complet + 16 derniers messages", "session en memoire, verrou par session_id"],
                 ["Gap Agent", "analyses passees et retours utilisateur", "base de donnees"],
                 ["RAG", "historique de conversation", "session du service"]],
                [40, 90, 40], size=7.6),
          PageBreak()]

    # 5 ------------------------------------------------------------------------------------------------
    s += [P("5. Pipeline vision : de la photo a la fiche", "H1"),
          P("Le catalogage est un pipeline en deux temps. Le detecteur local fait le travail geometrique et "
            "colorimetrique ; le LLM vision fait le travail semantique."),
          d_vision("fr"), P("Figure 3 : pipeline de catalogage d'un vetement.", CAP),
          *bullets(["<b>YOLO</b> (<font face='Courier'>dressme_best.pt</font>) detecte et segmente le vetement sur la photo.",
                    "Les <b>couleurs sont mesurees sur les pixels</b> du masque, puis ramenees a la palette la plus proche : "
                    "le LLM ne devine pas la couleur.",
                    "<b>GPT-4o vision</b> recoit l'image et un schema JSON strict : categorie, matiere, saison, occasion, "
                    "style, formalite, niveau de chaleur, confiance. Il ne peut changer la categorie du detecteur que si "
                    "l'image le montre clairement.",
                    "Sans cle API ou en cas d'erreur, <font face='Courier'>fallback_enrich</font> applique des regles et la fiche reste utilisable.",
                    "20 classes : t-shirt, chemise, pull, veste, manteau, blouse, robe, jupe, pantalon, jean, short, "
                    "combinaison, chaussures, bottes, sandales, sac, ceinture, chapeau, echarpe, accessoire."]),
          PageBreak()]

    # 6 ------------------------------------------------------------------------------------------------
    s += [P("6. LLM et modeles utilises", "H1"),
          P("Le choix du modele depend de la tache : GPT-4o pour le raisonnement et la vision, gpt-4o-mini pour une "
            "tache courte et bon marche, Qwen + LoRA pour une decision specialisee, Ollama pour fonctionner sans cle API."),
          table([["Composant", "Modele", "Temp.", "Format", "Limite", "Role"],
                 ["Catalogage vision", "GPT-4o", "-", "JSON strict", "1 appel", "categorie, couleur, matiere, saison, occasion"],
                 ["AI Stylist", "GPT-4o", "0,3", "JSON", "8 tours, 1 800 tokens", "conseil, meteo, RAG, placard"],
                 ["Wardrobe Agent", "GPT-4o", "0,1", "JSON", "6 tours", "recherche, comptage, doublons, correction"],
                 ["Similar Agent", "GPT-4o", "0,1", "JSON", "10 tours", "statuts owned / close / missing"],
                 ["Outfit Builder (compose)", "GPT-4o", "0,6", "JSON", "2 passes, 2 200 tokens", "3 tenues avec identifiants reels"],
                 ["Trip Agent", "GPT-4o", "0", "outils + JSON", "12 iterations", "choix d'outils, valise CP-SAT"],
                 ["Gap Agent", "gpt-4o-mini", "0,2", "Markdown", "6 etapes", "lacunes de garde-robe"],
                 ["Purchase Agent", "Qwen2.5-3B + LoRA", "0,1", "JSON", "6 tours", "verdict BUY / CONSIDER / SKIP"],
                 ["Purchase (redaction)", "GPT-4o", "0,5", "JSON 3 sections", "-", "reformule le verdict, ne decide pas"],
                 ["Purchase Redundancy", "GPT-4.1 / Claude Opus 5.5", "0,2", "JSON", "1 appel", "redondance + CLIP ViT-B/32"],
                 ["Stylist BO4", "Ollama qwen2.5:3b", "0,2", "JSON", "9 noeuds", "tenues locales, heuristique"],
                 ["Orchestrateur 8070", "Ollama qwen2.5:3b", "0", "JSON / regles", "1", "routage d'intention"],
                 ["Recherche RAG", "MiniLM + LLM", "0,1", "texte cite", "top 5", "reponse sourcee [S#]"]],
                [36, 32, 12, 24, 24, 42], size=7.2),
          PageBreak()]

    # 7 ------------------------------------------------------------------------------------------------
    s += [P("7. Entrees et sorties par fonctionnalite", "H1"),
          P("Toutes les routes sont protegees par le jeton Supabase. Les reponses sont du JSON ; l'interface "
            "affiche ensuite des zones dediees (meteo, tenues, raisons, sources, verdict)."),
          table([["Fonction", "Entree", "Sortie principale"],
                 ["AI Stylist", "{message, city, country, unit}", "{answer, weather, outfit[], why[], alternatives[], tips[], sources[], items[]}"],
                 ["Wardrobe", "{message, action?, confirm?}", "{reply, items[], filters, proposal{fields, item_id}}"],
                 ["Similar", "{pieces[]} via A2A", "{pieces[{status: owned|close|missing, match_item, missing_spec}]}"],
                 ["Outfit Builder", "{occasion, season, city, avoid[]}", "{outfits[{title, items[], weather_note, why[]}], missing[], sources[]}"],
                 ["Trip Agent", "{message, session_id}", "{message, state, capsule[], checklist[], alternatives[]}"],
                 ["Gap Agent", "{message, goal}", "{answer, gaps[], covered[], products[]}"],
                 ["Purchase Agent", "{image} ou photo", "{decision, score, reasons[], matching_item_ids[], decision_source}"],
                 ["Avatar", "{photo} / {outfit_id}", "{job_id, status, result_url}"]],
                [28, 58, 84], size=7.4),
          H2_("Exemple de reponse de l'AI Stylist"),
          code('{\n  "answer": "Wear the beige blazer with the white shirt and navy trousers.",\n'
               '  "weather": "27 C and sunny in Tunis; light layers are enough.",\n'
               '  "outfit": ["Beige blazer + White shirt + Navy trousers + Leather loafers"],\n'
               '  "why": ["The blazer keeps the dinner look formal [S2].", "..."],\n'
               '  "alternatives": ["The grey cardigan is too casual for a dinner."],\n'
               '  "tips": ["Choose breathable cotton for a warm evening [S4]."]\n}'),
          PageBreak()]

    # 8 ------------------------------------------------------------------------------------------------
    s += [P("8. LangGraph : comment fonctionne un agent", "H1"),
          P("LangGraph modelise un agent comme une <b>machine a etats</b>. Un etat partage (un TypedDict) traverse "
            "des noeuds ; chaque noeud est une fonction Python qui lit l'etat et renvoie une mise a jour partielle. "
            "Les aretes conditionnelles choisissent le noeud suivant. Un checkpointer conserve l'etat entre deux appels."),
          d_langgraph("fr"), P("Figure 4 : anatomie d'un graphe et boucle d'outils commune.", CAP),
          H2_("Les quatre briques"),
          table([["Brique", "Role dans DressMe"],
                 ["Etat partage", "messages, items, meteo, conseils, brouillon de tenues, erreurs, identifiants de conversation"],
                 ["Noeud", "une fonction pure : appeler un outil, construire le placard, composer, valider, rediger"],
                 ["Arete conditionnelle", "le code decide du chemin (ex. gate -> apply / cancel / assist)"],
                 ["Checkpointer", "memoire par utilisateur et par fil ; reprise d'une conversation apres un InputRequired"]],
                [34, 136], size=7.8),
          H2_("La boucle d'outils partagee"),
          P("Le module <font face='Courier'>agent_kit/tool_loop.py</font> fournit la meme mecanique a tous les agents : "
            "le LLM choisit un outil, le code valide les arguments et execute l'outil, le resultat revient au LLM. "
            "Un noeud <b>nudge</b> envoie un rappel unique si le modele saute un outil obligatoire (meteo, RAG, placard). "
            "Un noeud <b>finish</b> arrete la boucle quand la reponse est exploitable."),
          P("Chaque agent reutilise ce squelette : un noeud <b>llm</b>, un noeud <b>tools</b>, une arete "
            "conditionnelle vers <b>finish</b> et une arete de retour <b>tools -> llm</b>. Seuls le modele, les "
            "outils et les garde-fous changent d'un agent a l'autre."),
          PageBreak()]

    # 9 ------------------------------------------------------------------------------------------------
    s += [P("9. Les graphes, un par un", "H1"),
          P("Chaque agent possede son graphe. Les noeuds sont nommes comme dans le code, ce qui permet de relier "
            "directement ce document aux fichiers sources.")]

    s += [P("9.1 AI Stylist : boucle d'outils", H2),
          P("Modele GPT-4o, temperature 0,3, sortie JSON, 8 tours maximum. Trois outils : "
            "<font face='Courier'>search_wardrobe</font>, <font face='Courier'>get_weather</font>, "
            "<font face='Courier'>fashion_advice</font>."),
          d_stylist("fr"), P("Figure 5 : boucle d'outils de l'AI Stylist.", CAP),
          *bullets(["Le prompt impose d'appeler <b>search_wardrobe</b> avant de repondre et de ne parler que de pieces possedees.",
                    "Toute question de style declenche <b>fashion_advice</b> ; toute question de meteo declenche <b>get_weather</b>.",
                    "Un rappel unique est envoye si le modele oublie la meteo ou le RAG (detection par expression reguliere FR / EN).",
                    "Seules les sources reellement citees sont renvoyees ; les pieces sont retrouvees par leur nom dans le placard."]),
          PageBreak()]

    s += [P("9.2 Wardrobe Agent : graphe de confirmation", H2),
          P("Le Wardrobe Agent possede la garde-robe. Son graphe commence par un noeud <b>gate</b> : si une correction "
            "attend une reponse, un oui mene a <b>apply</b>, un non a <b>cancel</b> ; sinon <b>assist</b> lance la "
            "boucle d'outils. Aucun outil LLM n'ecrit : <font face='Courier'>update_item</font> ne fait que proposer."),
          d_wardrobe("fr"), P("Figure 6 : gates et outils du Wardrobe Agent.", CAP),
          table([["Outil", "Role"],
                 ["search_wardrobe", "filtre la garde-robe (categorie, couleur, saison, occasion, style, chaleur, texte)"],
                 ["find_similar", "pieces proches avec les raisons (meme type, meme couleur, meme matiere)"],
                 ["wardrobe_stats", "total, repartition, pieces a verifier"],
                 ["update_item", "propose une correction, sans ecriture"]],
                [36, 134], size=7.8),
          P("Une correction n'est appliquee que par le noeud <b>apply</b>, apres un oui explicite. La proposition expire "
            "apres 15 minutes et reste liee a l'utilisateur et a la conversation. Le meme agent expose des actions "
            "structurees sans LLM (list, search, check-duplicate) utilisees par les autres agents et le Live scan."),
          PageBreak()]

    s += [P("9.3 Similar Agent : owned, close, missing", H2),
          P("A partir d'une photo de tenue, le detecteur decoupe les pieces ; l'agent demande au Wardrobe Agent "
            "(A2A) les pieces proches, propose un statut par piece, puis le <b>code verifie</b> chaque identifiant cite."),
          d_similar("fr"), P("Figure 7 : chaine Similar Agent.", CAP),
          *bullets(["<b>owned</b> : la piece exacte est dans le placard ; <b>close</b> : meme categorie et couleur proche ; "
                    "<b>missing</b> : rien ne correspond.",
                    "Le code valide les statuts et rejette tout identifiant absent du placard.",
                    "Une piece manquante renvoie vers BO3 (photos de boutiques tunisiennes) et vers l'essayage virtuel."]),
          PageBreak()]

    s += [P("9.4 Outfit Builder : graphe metier a cinq noeuds", H2),
          P("Le LLM n'intervient que dans <b>compose</b>. Les quatre autres noeuds sont du code deterministe, "
            "ce qui garantit que la meteo, le placard et la validation ne dependent pas du modele."),
          d_outfit("fr"), P("Figure 8 : graphe de l'Outfit Builder.", CAP),
          table([["Noeud", "Entree", "Sortie", "Type"],
                 ["weather", "ville, pays", "forecast ou None", "Open-Meteo"],
                 ["closet", "items", "pieces classees par role (13 champs)", "code"],
                 ["knowledge", "occasion, saison, forecast", "advice[] + sources", "RAG, 2 questions"],
                 ["compose", "brief complet", "outfits[] {title, items[], weather_note, why[]}, missing[]", "GPT-4o, JSON, temp. 0,6"],
                 ["validate", "outfits[] + placard", "tenues valides ou erreurs (retour a compose une fois)", "code"]],
                [22, 46, 66, 36], size=7.6),
          P("Regles de validation : identifiants reels ; robe seule ou haut + bas ; chaussures obligatoires ; jamais "
            "deux pieces du meme role ; veste si froid ou pluie. En cas d'echec, le LLM est relance <b>une seule fois</b> "
            "avec la liste exacte des erreurs."),
          PageBreak()]

    s += [P("9.5 Trip Agent : deux graphes et dix outils", H2),
          P("Le Trip Agent combine une conversation (graphe 1) et un workflow deterministe (graphe 2). Le LLM "
            "n'invente ni destination, ni dates, ni meteo, ni resultat du solveur ; il choisit l'outil suivant."),
          d_trip("fr"), P("Figure 9 : les deux graphes du Trip Agent et ses dix outils.", CAP),
          table([["Outil", "Role", "Ressource"],
                 ["get_trip_details", "extrait, fusionne et valide les champs du voyage", "GPT-4o JSON + regex"],
                 ["get_weather", "prevision jour par jour pour la destination", "Open-Meteo"],
                 ["get_wardrobe", "charge la garde-robe et la couverture des roles", "CSV + pandas"],
                 ["get_activity_requirements", "traduit activites et meteo en exigences", "regles"],
                 ["optimize_trip", "choisit la valise (moins de pieces, plus combinables)", "OR-Tools CP-SAT"],
                 ["generate_checklist", "checklist depuis la capsule", "Pydantic"],
                 ["suggest_alternatives", "diagnostique INFEASIBLE sans relacher les contraintes", "CP-SAT"],
                 ["update_trip", "modifie le voyage et invalide l'etat obsolete", "etat de l'agent"],
                 ["update_checklist", "coche une piece sans relancer le solveur", "etat de l'agent"],
                 ["check_gaps", "appelle le Gap Agent par A2A (optionnel)", "fonction injectee"]],
                [46, 90, 34], size=7.4),
          PageBreak()]

    s += [P("9.6 Gap Agent : lacunes et classement XGBoost", H2),
          P("Modele gpt-4o-mini, temperature 0,2, 6 etapes maximum. Les <b>regles deterministes</b> decident si une "
            "lacune existe ; XGBoost ne fait que l'ordonner. Le prompt precise que le classeur est entraine sur des "
            "donnees synthetiques tant qu'il n'y a pas de retours reels."),
          d_gap("fr"), P("Figure 10 : Gap Agent et ses cinq outils.", CAP),
          *bullets(["<b>compute_coverage</b> compare l'objectif choisi aux pieces possedees, par saison et par exigence.",
                    "<b>rank_gaps</b> score chaque manque (deficit, frequence, saison, gain de tenues, preference, "
                    "redondance FashionCLIP) puis ordonne avec XGBoost.",
                    "<b>get_past_analyses</b> donne une memoire a long terme ; les retours alimentent "
                    "<font face='Courier'>/api/bo3/retrain</font>.",
                    "Jamais de piece d'un autre departement ; jamais de genre devine. Reponse dans la langue de l'utilisateur."]),
          PageBreak()]

    s += [P("9.7 Purchase Agent : Qwen decide, GPT redige", H2),
          P("Le decideur est <b>Qwen2.5-3B-Instruct + adaptateur LoRA</b> "
            "(<font face='Courier'>meriemgharbi123/dressme_qwen3b_lora</font>), charge depuis Hugging Face. "
            "Il choisit lui-meme six outils dans une boucle LangGraph ; chaque outil est calcule par du code sur la "
            "vraie garde-robe, et ses resultats font foi."),
          d_purchase("fr"), P("Figure 11 : chaine de decision du Purchase Agent.", CAP),
          table([["Outil", "Ce qu'il calcule"],
                 ["analyze_item", "categorie, couleur et attributs de l'article photographie"],
                 ["find_similar_items", "pieces proches deja possedees"],
                 ["check_outfit_compatibility", "tenues possibles avec l'article"],
                 ["analyze_wardrobe_gaps", "lacune comblee ou non"],
                 ["predict_purchase_ml", "score XGBoost de valeur d'achat"],
                 ["calculate_purchase_value", "rapport cout / usage estime"]],
                [50, 120], size=7.8),
          P("Qwen termine par un verdict JSON {decision, score, matching_item_ids, reasons}. Le code le verifie : "
            "decision connue, score entre 0 et 100, identifiants reellement presents, raisons courtes. GPT-4o recoit "
            "ce JSON et le reecrit en trois sections, sans pouvoir changer la decision. Repli deterministe si "
            "Hugging Face, GPU ou reseau indisponibles ; <font face='Courier'>decision_source</font> indique la source."),
          PageBreak()]

    s += [P("9.8 Stylist BO4 : graphe local a neuf noeuds", H2),
          P("BO4 est une pile separee, non branchee a l'interface React. Elle montre une variante locale, sans cle API : "
            "Ollama qwen2.5:3b et un moteur de tenues heuristique."),
          d_bo4("fr"), P("Figure 12 : graphe du Stylist BO4.", CAP),
          P("Les neuf noeuds : extract_intent, get_weather, fetch_wardrobe, apply_constraints, recommend, "
            "style_advice, respond, clarify, record_feedback. Le score heuristique combine couleur (0,30), "
            "style (0,20), occasion (0,30) et saison (0,20)."),
          PageBreak()]

    # 10 -----------------------------------------------------------------------------------------------
    s += [P("10. Communication entre agents : A2A", "H1"),
          P("Chaque agent expose une <b>carte d'agent</b> (identite, competences, authentification) et un point "
            "d'entree <b>JSON-RPC</b> conforme au protocole Agent2Agent 0.3.0. N'importe quel client peut donc "
            "decouvrir un agent et lui confier une tache par HTTP, sans connaitre ses routes internes."),
          d_a2a("fr"), P("Figure 13 : decouverte par carte, envoi d'une tache, agent vers agent.", CAP),
          table([["Agent", "Carte", "Point d'entree", "Competence"],
                 ["AI Stylist", "/a2a/stylist/.well-known/agent-card.json", "POST /a2a/stylist (8000)", "style-advice, wardrobe-search"],
                 ["Outfit Builder", "/a2a/outfit/.well-known/agent-card.json", "POST /a2a/outfit (8000)", "build-outfits"],
                 ["Wardrobe Agent", "/a2a/wardrobe/.well-known/agent-card.json", "POST /a2a/wardrobe (8000)", "search, list, correction, stats, doublons"],
                 ["Similar Agent", "/a2a/similar/.well-known/agent-card.json", "POST /a2a/similar (8000)", "find-similar"],
                 ["Trip Agent", "/a2a/trip/.well-known/agent-card.json", "POST /a2a/trip (8020)", "plan-trip-packing"],
                 ["Gap Agent", "/a2a/gap/.well-known/agent-card.json", "POST /a2a/gap (8001)", "wardrobe-gaps"]],
                [22, 58, 34, 56], size=6.6),
          H2_("Methodes et etats"),
          *bullets(["<b>message/send</b> (reponse synchrone), <b>tasks/get</b>, <b>tasks/cancel</b>.",
                    "Etats d'une tache : submitted, working, input-required, completed, failed, canceled, rejected.",
                    "Erreurs JSON-RPC : -32700 analyse, -32600 requete, -32601 methode, -32602 parametres, "
                    "-32001 tache inconnue, -32002 non annulable, -32004 operation non supportee.",
                    "La carte est publique ; chaque tache exige le jeton Supabase et ne travaille que sur la garde-robe "
                    "de cet utilisateur. Une tache n'est lisible que par son createur.",
                    "<b>input-required</b> : le Trip Agent demande une precision ; le client repond avec le meme "
                    "<font face='Courier'>contextId</font> (identifiant de session de voyage).",
                    "Non implemente et declare tel quel : streaming (message/stream) et notifications push."]),
          P("Exemple de tache envoyee au Wardrobe Agent :"),
          code('POST /a2a/wardrobe\nAuthorization: Bearer <supabase_jwt>\n\n'
               '{"jsonrpc": "2.0", "id": "42", "method": "message/send",\n'
               ' "params": {"message": {"role": "user", "parts": [{"kind": "text", "text": "list my jackets"}]},\n'
               '            "metadata": {"action": "list"}}}'),
          P("Agent vers agent : l'outil <b>check_gaps</b> du Trip Agent envoie la capsule du voyage au Gap Agent "
            "(A2A, meme jeton). Si le Gap Agent est arrete, l'outil renvoie une erreur propre et le voyage continue. "
            "L'adresse se regle avec <font face='Courier'>GAP_A2A_URL</font>."),
          PageBreak()]

    # 11 -----------------------------------------------------------------------------------------------
    s += [P("11. Orchestrateurs", "H1"),
          P("L'orchestrateur BO1 est le point d'entree conversationnel de l'application : "
            "<font face='Courier'>POST /api/assistant/chat</font>. Il choisit l'agent, lui delegue la demande et "
            "garde le fil. Les autres ecrans continuent d'appeler leur agent directement."),
          d_orchestrator("fr"), P("Figure 14 : orchestrateur BO1 et orchestrateur autonome 8070.", CAP),
          table([["Noeud BO1", "Role"],
                 ["route", "GPT-4o en JSON, liste fermee d'agents ; regles FR / EN si le LLM est indisponible ; si un agent attend une reponse, la suite va au meme agent"],
                 ["stylist / wardrobe / outfit", "appel direct dans BO1"],
                 ["trip / gap", "appel A2A avec le jeton de l'utilisateur (8020 et 8001)"],
                 ["redirect", "Should I buy et Find Similar ont besoin d'une photo : ouvre la bonne page"],
                 ["clarify", "demande une precision si la demande est trop vague"],
                 ["respond", "ajoute le tour a l'historique (8 derniers echanges, un fil par utilisateur)"]],
                [38, 132], size=7.6),
          H2_("Exemple de conversation suivie"),
          *bullets(["\"Prepare ma valise pour Paris\" : routage vers le Trip Agent, tache <b>input-required</b> "
                    "(\"quelles dates ?\").",
                    "\"Du 3 au 7 juin, 8 kg\" : aucun mot-cle d'agent, mais la question est restee ouverte ; la "
                    "reponse repart au Trip Agent avec le meme contextId.",
                    "Une correction du Wardrobe Agent n'est continuee que par un oui ou un non ; toute autre phrase "
                    "est une nouvelle demande.",
                    "Chaque reponse indique l'agent qui a repondu (\"Answered by ...\") ; les tenues s'affichent avec "
                    "leurs photos et un bouton ouvre la page demandee."]),
          H2_("Orchestrateur autonome 8070"),
          P("Le graphe <font face='Courier'>orchestrator/</font> (port 8070) est conserve comme alternative locale : "
            "<b>route_intent</b> (Ollama qwen2.5:3b puis regles), branches stylist, wardrobe, purchase, knowledge, "
            "external, clarify, puis respond. Il n'est pas branche a l'interface React actuelle.")]

    # 12 -----------------------------------------------------------------------------------------------
    s += [Spacer(1, 12), P("12. Le RAG : connaissance de mode citee", "H1"),
          P("Le RAG repond a des questions de style a partir de 38 livres de mode. Il ne connait pas le placard : "
            "c'est l'agent qui fait le lien entre la regle du livre et les pieces reelles."),
          d_rag("fr"), P("Figure 15 : ingestion hors ligne et interrogation en ligne.", CAP),
          table([["Element", "Detail"],
                 ["Corpus", "38 PDF : couleurs, tissus, codes vestimentaires, capsules, accessoires"],
                 ["Ingestion", "PyMuPDF, OCR Tesseract pour les livres scannes, controle qualite, chunking"],
                 ["Index", "knowledge_chunks_v2, Postgres + pgvector, HNSW, cosinus, 384 dimensions"],
                 ["Embeddings", "sentence-transformers all-MiniLM-L6-v2"],
                 ["Recherche", "hybride : vecteurs + plein texte, fusion RRF, top 5 passages"],
                 ["Question", "francais traduit en anglais avec glossaire ; anglais inchange"],
                 ["Generation", "repond uniquement avec les sources numerotees ; sinon \"I don't know\""],
                 ["API", "POST /ask, /ask/stream (SSE), cle d'API, limitation de debit, historique"]],
                [30, 140], size=7.6),
          H2_("Qualite mesuree"),
          table([["Metrique", "Valeur", "Ce qu'elle mesure"],
                 ["Hit@5", "91,67 %", "le bon passage est dans les cinq premiers"],
                 ["MRR", "85,42 %", "rang moyen du premier bon passage"],
                 ["Precision du contexte", "71,67 %", "part des passages recuperes qui sont pertinents"],
                 ["Chunks indexes", "14 574", "taille de l'index pgvector"],
                 ["Documents", "38", "livres de mode traites"]],
                [46, 30, 94], size=7.8),
          P("Integration : <font face='Courier'>rag_client.advise(question)</font> renvoie {answer, sources, grounded} "
            "ou None. L'AI Stylist l'expose comme outil <b>fashion_advice</b> ; l'Outfit Builder l'appelle dans le "
            "noeud <b>knowledge</b>. Les marqueurs [S#] sont conserves puis affiches en badges (livre et page).")]

    # 13 -----------------------------------------------------------------------------------------------
    s += [Spacer(1, 12), P("13. Algorithmes deterministes et apprentissage", "H1"),
          P("Le projet combine plusieurs familles d'algorithmes. Les LLM ne remplacent jamais un calcul exact "
            "quand celui-ci est possible."),
          table([["Algorithme", "Utilise par", "Role"],
                 ["YOLO (dressme_best.pt)", "catalogage, live scan, similar, achat", "detection et segmentation des vetements"],
                 ["OR-Tools CP-SAT", "Trip Agent", "choix optimal de la valise sous contraintes dures"],
                 ["XGBoost", "Gap Agent, Purchase Agent", "classement des lacunes et score d'achat"],
                 ["Heuristique de tenues", "Outfit Builder (repli), BO4", "couleur 0,30 + style 0,20 + occasion 0,30 + saison 0,20"],
                 ["FashionCLIP", "Gap Agent, redondance d'achat", "similarite visuelle entre pieces"],
                 ["CLIP ViT-B/32", "Purchase Redundancy", "redondance semantique d'un article"],
                 ["Recherche hybride + RRF", "RAG", "fusion des classements vecteur et texte"],
                 ["Regles metier", "Wardrobe, Outfit, Trip, Gap", "validation, contraintes, garde-fous"]],
                [42, 46, 82], size=7.6),
          H2_("Le solveur de valise"),
          *bullets(["Variables : une par piece du placard, binaire (prise ou non).",
                    "Contraintes dures : au moins une tenue par jour et par activite, exigences meteo, formalite, "
                    "limite de poids, pas de doublon de role.",
                    "Objectif : minimiser le poids puis le nombre de pieces, en maximisant les combinaisons possibles.",
                    "Si le probleme est <b>INFEASIBLE</b>, <font face='Courier'>suggest_alternatives</font> explique "
                    "la contrainte bloquante sans jamais la relacher silencieusement."]),
          PageBreak()]

    # 14 -----------------------------------------------------------------------------------------------
    s += [P("14. Avatar et essayage virtuel", "H1"),
          P("L'avatar est genere a partir d'une photo en pied ; l'essayage applique ensuite une tenue ou un vetement "
            "sur cet avatar. Le fournisseur est configurable avec <font face='Courier'>AVATAR_PROVIDER</font>."),
          *bullets(["<b>Avatar 3D</b> : Hunyuan3D v3 via WaveSpeed (defaut) ou fal.ai.",
                    "<b>Essayage d'une tenue complete</b> : <font face='Courier'>/api/avatar/tryon-outfit</font> (Bria virtual try-on).",
                    "<b>Essayage d'un vetement de boutique</b> : <font face='Courier'>/api/avatar/tryon-garment</font>.",
                    "Les generations sont des <b>taches d'arriere-plan</b> : la route renvoie un job_id, l'interface "
                    "suit le statut puis affiche le resultat.",
                    "Une piece manquante detectee par Find Similar peut etre essayee avant l'achat.",
                    "Aucune image d'avatar n'est envoyee a un agent LLM : seuls les fournisseurs d'images la voient."]),
          PageBreak()]

    # 15 -----------------------------------------------------------------------------------------------
    s += [P("15. Securite, garde-fous et tests", "H1"),
          table([["Theme", "Mesure"],
                 ["Ancrage", "identifiants du placard uniquement ; outils en lecture ; sources numerotees ; meteo reelle"],
                 ["Validation par code", "Outfit (regles de composition), Trip (Pydantic + solveur), Purchase (verdict), Similar (identifiants)"],
                 ["Degradation douce", "RAG, meteo, LLM, HF indisponibles : reponse partielle ou repli par regles"],
                 ["Cloisonnement", "jeton Supabase verifie sur chaque route ; requetes filtrees par user_id ; taches A2A privees"],
                 ["Secrets", "cles API uniquement cote serveur ; jamais dans le frontend ni dans un prompt"],
                 ["Honnetete", "le Gap Agent dit que XGBoost est entraine sur des donnees synthetiques ; le RAG repond \"I don't know\" plutot que d'inventer"],
                 ["Erreurs A2A", "tache failed avec message neutre, aucun detail interne"],
                 ["Limitation de debit", "service RAG et routes sensibles"]],
                [36, 134], size=7.8),
          H2_("Tests"),
          table([["Suite", "Nombre", "Remarque"],
                 ["Orchestrateur", "101", "routage, memoire, appels A2A simules"],
                 ["Backend BO1", "85", "faux LLM, faux RAG, fausse meteo"],
                 ["Frontend", "30", "composants et parcours"],
                 ["BO4", "1 095 (25 ignores)", "graphe local et heuristiques"],
                 ["Moteur d'achat, Trip Agent", "tests dedies", "outils, solveur, repli deterministe"],
                 ["Bout en bout", "essais reels", "GPT-4o, RAG, Open-Meteo"]],
                [46, 34, 90], size=7.8),
          PageBreak()]

    # 16 -----------------------------------------------------------------------------------------------
    s += [P("16. Limites assumees", "H1"),
          *bullets(["Le RAG ne connait pas le placard ; il ne contient que des livres de mode.",
                    "Le classeur XGBoost du Gap Agent est entraine sur des donnees synthetiques jusqu'a l'arrivee de retours reels.",
                    "L'AI Stylist n'a pas de memoire entre deux messages ; la memoire du Trip Agent est en memoire serveur "
                    "et disparait au redemarrage.",
                    "Le Stylist BO4 et l'orchestrateur 8070 ne sont pas branches a l'interface React.",
                    "Le Purchase Agent depend de Hugging Face : sans HF_TOKEN il n'est pas actif ; Qwen2.5-3B en local "
                    "demande assez de memoire et de GPU.",
                    "La meteo couvre un seul jour a la fois (jusqu'a 15 jours) pour une seule ville.",
                    "A2A est une implementation legere : JSON-RPC et cartes d'agent, sans streaming ni notifications push.",
                    "Pistes : memoire de preferences par utilisateur, journal des tenues portees, orchestrateur 100 % A2A, "
                    "migration de l'AI Stylist vers un graphe explicite."]),
          PageBreak()]

    # 17 -----------------------------------------------------------------------------------------------
    s += [P("17. Lancement et scenario de demonstration", "H1"),
          table([["Etape", "Commande / variable", "Port"],
                 ["BO1", ".\\start_bo1.ps1", "8000"],
                 ["BO3", ".\\start_bo3.ps1", "8001"],
                 ["Help Me Pack", ".\\start_packing.ps1", "8020"],
                 ["RAG", ".\\start_rag.ps1", "8010"],
                 ["Interface", "pnpm dev", "8443"],
                 ["Orchestrateur autonome", "uvicorn orchestrator.main:app --port 8070", "8070"],
                 ["Ollama", "ollama serve", "11434"]],
                [44, 106, 20], size=7.8),
          H2_("Variables d'environnement utiles"),
          table([["Variable", "Role"],
                 ["OPENAI_API_KEY", "GPT-4o, gpt-4o-mini, vision"],
                 ["SUPABASE_URL / SUPABASE_ANON_KEY / SUPABASE_SERVICE_ROLE_KEY", "auth, base, stockage"],
                 ["HF_TOKEN / QWEN_BACKEND / HF_ENDPOINT_URL", "Purchase Agent (local, hf_api, auto, off)"],
                 ["GAP_A2A_URL", "adresse du Gap Agent pour l'outil check_gaps (vide pour desactiver)"],
                 ["RAG_API_URL / RAG_API_KEY", "client RAG des agents"],
                 ["AVATAR_PROVIDER", "wavespeed ou fal"],
                 ["OLLAMA_HOST", "LLM local BO4 et orchestrateur 8070"]],
                [64, 106], size=7.6),
          H2_("Scenario de demonstration (10 minutes)"),
          *numbered(["Ajouter trois vetements par photo : montrer la fiche generee et la couleur mesuree.",
                     "Ouvrir Wardrobe et demander \"montre-moi mes vestes pour le travail\" : le LLM choisit les filtres.",
                     "AI Stylist : \"que mettre demain soir pour un diner a Tunis ?\" : meteo, tenue, raisons, sources.",
                     "Outfit Builder : generer trois tenues, puis Shuffle pour en obtenir d'autres.",
                     "Help Me Pack : \"valise pour Paris du 3 au 7 juin, 8 kg\" : question de precision, puis checklist.",
                     "Wardrobe Gaps : objectif \"winter work\" : lacunes classees et produits de boutiques tunisiennes.",
                     "Should I buy this? : photographier un article et montrer le verdict, les preuves et le repli.",
                     "Dashboard : statistiques, tenue du jour et notifications.",
                     "Terminer par une tache A2A : <font face='Courier'>python scripts/a2a_discover.py --ask</font>."]),
          PageBreak()]

    # 18 -----------------------------------------------------------------------------------------------
    s += [P("18. Carte du depot", "H1"),
          table([["Chemin", "Contenu"],
                 ["backend/app", "BO1 : routes, agents LangGraph, detecteur, catalogage, avatar"],
                 ["DressMe UI Blueprint", "BO3 et frontend React"],
                 ["packing_backend", "Trip Agent, solveur CP-SAT, checklist"],
                 ["rag_backend", "ingestion, index pgvector, service /ask"],
                 ["orchestrator", "orchestrateur autonome 8070 (graphe, services.yaml)"],
                 ["a2a_protocol", "serveur et client A2A, cartes d'agent"],
                 ["agent_kit", "boucle d'outils LangGraph partagee"],
                 ["bo4", "Stylist local a neuf noeuds (Ollama)"],
                 ["smart_purchasing", "Purchase Agent Qwen + LoRA et outils d'achat"],
                 ["purchase-redundancy-ai", "service de redondance GPT-4.1 / Claude + CLIP"],
                 ["scripts", "lancement, decouverte A2A, maintenance"],
                 ["docs", "guides techniques et PDF de presentation"]],
                [46, 124], size=7.8),
          PageBreak()]

    # 19 -----------------------------------------------------------------------------------------------
    s += [P("19. Glossaire", "H1"),
          table([["Terme", "Definition"],
                 ["Agent", "composant qui combine un LLM, des outils et une politique de decision"],
                 ["LangGraph", "bibliotheque de graphes d'etats pour agents, avec noeuds, aretes et checkpointer"],
                 ["A2A", "protocole Agent2Agent : carte d'agent + taches JSON-RPC"],
                 ["RAG", "retrieval-augmented generation : repondre a partir de documents recuperes et cites"],
                 ["Chunk", "passage de texte indexe dans pgvector"],
                 ["RRF", "Reciprocal Rank Fusion, fusion de plusieurs classements"],
                 ["Ancrage (grounding)", "obligation de fonder chaque affirmation sur une donnee reelle"],
                 ["Garde-fou", "regle de code ou de prompt qui empeche une sortie inventee"],
                 ["Checkpointer", "mecanisme qui sauvegarde l'etat d'un graphe entre deux appels"],
                 ["Repli (fallback)", "chemin deterministe quand un service externe est indisponible"],
                 ["CP-SAT", "solveur de programmation par contraintes d'OR-Tools"],
                 ["LoRA", "adaptateur leger qui specialise un modele pre-entraine"]],
                [38, 132], size=7.8)]

    return s
