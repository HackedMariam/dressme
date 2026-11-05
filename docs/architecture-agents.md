# DressMe : architecture des agents (dossier de validation technique)

## 1. Vue d'ensemble

DressMe est une application React 19 (Vite, Tailwind) qui parle à **quatre services FastAPI** et à **un service RAG**.
Supabase fournit l'authentification, la base de données (garde-robe) et le stockage des images.

```
                          React (DressMe UI Blueprint)
   ┌─────────────┬────────────────┬──────────────────┬─────────────────────┐
   │ BO1  :8000  │ BO3  :8001     │ Help Me Pack :8020│ RAG  :8010          │
   │ garde-robe  │ Gap Agent      │ Trip Agent        │ connaissance mode   │
   │ AI Stylist  │ boutiques TN   │ (OR-Tools CP-SAT) │ (38 PDF, pgvector)  │
   │ Outfit Agent│                │                   │                     │
   │ Should I buy│                │                   │                     │
   └──────┬──────┴───────┬────────┴─────────┬─────────┴──────────┬──────────┘
          │              │                  │                    │
          └── OpenAI GPT-4o (gpt-4o-mini pour le Gap Agent) ──────┘
          └── Open-Meteo (météo, sans clé)      └── Supabase (auth, DB, storage, pgvector)
```

Principe commun à tous les agents : **le LLM décide et rédige, le code déterministe vérifie et calcule**. Aucun agent
ne peut citer une pièce qui n'existe pas dans la garde-robe, ni inventer la météo, ni inventer une source.

## 2. Combien d'agents ?

**5 agents dans l'application** (appelés depuis l'interface React) :

| # | Agent | Fonctionnalité | Service | Type | Fichier |
|---|---|---|---|---|---|
| 1 | **AI Stylist** | page AI Stylist (et recherche de la garde-robe) | BO1 | boucle d'appel d'outils GPT-4o, 3 outils | `backend/app/agent.py` |
| 2 | **Outfit Builder Agent** | page Outfit Builder | BO1 | **graphe LangGraph** à 5 nœuds | `backend/app/outfit_agent.py` |
| 3 | **Trip Agent** | Help Me Pack | 8020 | GPT-4o à 10 outils + **LangGraph** (2 graphes) + solveur CP-SAT | `packing_backend/trip_agent/` |
| 4 | **Gap Agent (BO3)** | Wardrobe Gaps, Shop Smart | BO3 | boucle d'appel d'outils, 5 outils, 6 étapes max | `DressMe UI Blueprint/backend/agent/gap_agent.py` |
| 5 | **Agent anti-doublon** | Live scan (caméra) | BO1 | boucle d'appel d'outils, 1 outil | `backend/app/agent.py` (`check_duplicate`) |

**Pipelines assistés par LLM, qui ne sont pas des agents** (le LLM ne choisit pas ses outils) :

| Composant | Rôle | Fichier |
|---|---|---|
| Catalogage vision | détecteur YOLO `dressme_best.pt` puis GPT-4o (vision, JSON strict) : catégorie, couleur, matière, saison, occasion | `backend/app/enricher.py` |
| Should I buy this? | détecteur + LLM, moteur d'achat (XGBoost + règles), puis LLM qui rédige 3 sections | `smart_purchasing/inference.py` |
| Réponse RAG | recherche hybride puis LLM qui répond uniquement avec les sources | `rag_backend/rag/rag_service.py` |

**Pile séparée de l'équipe, non branchée à l'interface React** : le *Stylist BO4* (LangGraph à 9 nœuds, Ollama
`qwen2.5:3b`, `bo4/`) et l'*orchestrateur* (LangGraph, port 8070, route vers stylist, garde-robe, achat, RAG ;
`orchestrator/`). Ils ont leur propre page web et sont lancés par `start_all.ps1`.

LangGraph est utilisé par l'Outfit Builder Agent, par le Trip Agent, par le Stylist BO4 et par l'orchestrateur.
L'AI Stylist, le Gap Agent et l'agent anti-doublon utilisent une boucle d'appel d'outils native OpenAI, écrite à la main.

## 3. Chaque agent en détail

### 3.1 AI Stylist (`backend/app/agent.py`)

- **Entrée** : `POST /api/agent/search` avec `message`, `city`, `country`, `unit`. La ville du profil est utilisée,
  sinon **Tunis, Tunisie**.
- **Boucle** : GPT-4o, `temperature=0.3`, `response_format=json_object`, jusqu'à 8 tours.
- **Outils** :
  - `search_wardrobe` : filtre la vraie garde-robe (catégorie, couleur, saison, occasion, chaleur...).
  - `get_weather` : prévision Open-Meteo du jour demandé (aujourd'hui, demain, « vendredi »), en °C ou °F, cache 30 min.
  - `fashion_advice` : appelle le RAG (une question par sujet, jusqu'à 3 : code vestimentaire, couleurs, tissus).
- **Prompt système** (extraits) : toujours appeler `search_wardrobe` avant de répondre ; météo obligatoire pour toute
  question « que porter » ; RAG obligatoire pour toute question de style ; ne jamais inventer de pièce ni de source ;
  réponse finale en JSON : `answer`, `weather`, `outfit`, `why` (4 à 6 raisons précises), `alternatives`, `tips`.
- **Garde-fous** : un rappel unique si le modèle saute le RAG ou la météo ; seules les sources réellement citées
  (`[S1]`...) sont renvoyées ; les pièces de la tenue sont retrouvées par leur nom dans le placard réel ; si le RAG
  ou la météo sont en panne, l'agent répond sans eux et le dit.
- **Sortie** : `reply`, `items`, `sections`, `sources`, `weather`, affichés en zones (Weather, Outfit idea avec
  photos, Why I chose this, What else I considered, Tips, From fashion books).

### 3.2 Outfit Builder Agent (`backend/app/outfit_agent.py`, LangGraph)

```
START → weather → closet → knowledge → compose → validate ──(erreurs, 1re fois)──→ compose
                                                      └──────────────────────────→ END
```

| Nœud | Rôle | LLM ? |
|---|---|---|
| `weather` | prévision réelle de la ville | non |
| `closet` | pièces classées par rôle (hauts, bas, robes, vestes, chaussures) avec leurs faits | non |
| `knowledge` | 2 questions au RAG : code vestimentaire de l'occasion, couleurs et tissus du climat | RAG |
| `compose` | construit 3 tenues avec les **identifiants** du placard et explique chaque choix | oui (GPT-4o, JSON) |
| `validate` | contrôle : ids réels, robe seule ou haut + bas, chaussures, pas deux pièces du même rôle, veste s'il fait froid | non |

Si une tenue est invalide, le LLM est renvoyé **une fois** avec la liste précise des erreurs. Seules les tenues valides
sortent. Si l'agent est indisponible, la page retombe sur l'ancien constructeur à règles (`outfitBuilder.ts`).
Route : `POST /api/outfits/agent`. Le bouton Shuffle envoie les tenues déjà montrées (`avoid`).

### 3.3 Trip Agent, Help Me Pack (`packing_backend/trip_agent/`)

- **LLM** : GPT-4o, `temperature=0`, appel d'outils natif, 12 itérations maximum.
- **10 outils** validés par Pydantic : `get_trip_details`, `get_weather`, `get_wardrobe`, `get_activity_requirements`,
  `optimize_trip`, `generate_checklist`, `suggest_alternatives`, `update_trip`, `update_checklist`, `check_gaps`.
- **LangGraph** : un graphe `intake → plan` et un graphe déterministe
  `weather → wardrobe → requirements → optimize → finish`, chaque nœud s'arrêtant si l'étape précédente échoue.
- **Calcul** : la valise est choisie par **OR-Tools CP-SAT** (pas par le LLM) : pièces les plus combinables, poids
  minimal, tenues quotidiennes. En cas d'`INFEASIBLE`, l'agent diagnostique et propose des alternatives sans relâcher
  silencieusement les contraintes.
- **Mémoire** : état de travail (`AgentState`), 16 derniers messages, session en mémoire côté serveur, `session_id`
  dans le `localStorage` du navigateur.
- **Prompt** : 10 règles (ne jamais inventer destination, dates, météo, pièces ni résultat du solveur ; poser une
  seule question quand il manque une information ; ne jamais fabriquer un succès).

### 3.4 Gap Agent BO3 (`DressMe UI Blueprint/backend/agent/gap_agent.py`)

- **LLM** : `gpt-4o-mini` par défaut, `temperature=0.2`, 6 étapes maximum.
- **5 outils** : `get_wardrobe`, `compute_coverage`, `rank_gaps`, `get_past_analyses`, `show_items`.
- **Calcul** : la couverture est une règle déterministe ; un classeur **XGBoost** ne fait qu'ordonner les lacunes
  (son score n'est pas une probabilité, et il est entraîné sur des données synthétiques tant qu'il n'y a pas de
  retours réels : le prompt le fait dire).
- **Prompt** : « utilise uniquement les résultats d'outils », une lacune n'existe que si les règles l'ont signalée,
  respecter le département (femme/homme), réponse dans la langue de l'utilisateur.
- **Aval** : les lacunes alimentent « Outfits to buy » sur le tableau de bord, avec des produits de boutiques
  tunisiennes (recherche d'images `ddgs`) et l'essayage virtuel.

### 3.5 Agent anti-doublon (`check_duplicate`, Live scan)

Après chaque capture caméra, GPT-4o (`temperature=0.1`, 250 tokens) appelle `search_wardrobe` pour décider s'il s'agit
du même vêtement scanné deux fois, pas simplement d'« un autre t-shirt marine ». Réponse JSON compacte :
`duplicate`, `similar_item_id`, `note`.

## 4. Les pipelines assistés par LLM

**Catalogage (BO1)** : YOLO segmente et mesure les couleurs sur les pixels ; GPT-4o (vision, schéma JSON strict)
corrige la catégorie seulement si l'image le montre, choisit la couleur, la matière, les saisons, les occasions, avec
un score de confiance honnête. Sans clé API ou en cas d'erreur : règles de secours (`fallback_enrich`).

**Should I buy this?** : l'article est reconnu par le même détecteur + LLM que le placard (pas de second moteur de
vision), puis le moteur d'achat calcule redondance, lacune comblée, tenues possibles avec les pièces possédées et
décision XGBoost + règles. Le LLM ne fait que rédiger trois sections (`verdict`, `why_it_works`, `final_advice`) ;
l'application écrit les titres en gras. Le prompt interdit le jargon (« XGBoost », « score »), demande une position
claire appuyée sur un fait (nombre ou nom de pièce) et des prix sans symbole monétaire.

## 5. Le RAG (`rag_backend/`, port 8010)

| Étape | Détail |
|---|---|
| Corpus | 38 PDF de mode (couleurs, tissus, codes vestimentaires, capsules...) ; OCR Tesseract pour les livres scannés |
| Index | `knowledge_chunks_v2` (Supabase Postgres + pgvector, HNSW cosinus), embeddings `all-MiniLM-L6-v2` (384 dim.) |
| Question | une question en français est traduite en anglais (glossaire), une question anglaise reste telle quelle |
| Recherche | **hybride** : vecteurs + recherche plein texte Postgres, fusion **RRF**, top 5 passages |
| Génération | prompt strict : répondre **uniquement** avec les sources numérotées, chaque puce finit par `[S#]`, réponse fixe « I don't know » si rien ne répond |
| API | `POST /ask` (réponse + citations), `/ask/stream` (SSE), clé d'API, limitation de débit |

Intégration dans les agents (`backend/app/rag_client.py`) : `advise(question)` appelle `/ask` et renvoie
`{answer, sources:[{marker, title, page}], grounded}`, ou `None` si le service est arrêté, vide ou sans citation.
Les agents gardent les marqueurs `[S#]` dans leurs phrases ; l'interface les affiche en badges (le survol donne le
livre et la page) et liste les livres sous « From fashion books ».

## 6. Qui utilise quoi

| Fonctionnalité | Agent / pipeline | Météo | RAG | Placard | Solveur / ML |
|---|---|---|---|---|---|
| AI Stylist | AI Stylist | oui | oui | oui | non |
| Outfit Builder | Outfit Builder Agent | oui | oui | oui | non |
| Help Me Pack | Trip Agent | oui | non (hook prévu) | oui | OR-Tools CP-SAT |
| Wardrobe Gaps, Shop Smart, Outfits to buy | Gap Agent | non | non | oui | règles + XGBoost |
| Should I buy this? | pipeline (détecteur + LLM + moteur d'achat) | non | non | oui | XGBoost |
| Live scan | détecteur + agent anti-doublon | non | non | oui | YOLO |
| Ajout d'un vêtement | détecteur + catalogage vision | non | non | non | YOLO |

## 7. Garde-fous communs

- **Ancrage** : identifiants du placard seulement ; outils de lecture ; sources numérotées ; météo réelle.
- **Validation par du code** après le LLM (Outfit Builder, Trip Agent avec Pydantic et solveur, Stylist avec filtrage
  des sources citées).
- **Dégradation douce** : RAG, météo ou LLM indisponibles ne cassent jamais la page (réponse partielle ou repli par règles).
- **Sécurité** : jeton Supabase vérifié sur chaque route, chaque utilisateur ne voit que son placard, clés API côté
  serveur uniquement, limitation de débit sur le RAG.
- **Tests** : 85 tests backend (agents avec faux LLM, faux RAG, faux service météo), 30 tests frontend, tests du moteur
  d'achat et du Trip Agent ; essais réels bout en bout avec GPT-4o, le RAG et Open-Meteo.

## 8. Limites assumées

- Le RAG ne connaît pas le placard de l'utilisateur ; c'est l'agent qui fait le lien.
- Le classeur XGBoost du Gap Agent est entraîné sur des données synthétiques jusqu'à l'arrivée de retours réels.
- La mémoire de conversation du Trip Agent est en mémoire serveur (perdue au redémarrage) ; l'AI Stylist n'a pas
  de mémoire entre deux messages.
- Le Stylist BO4 et l'orchestrateur LangGraph ne sont pas encore reliés à l'interface React.
- La météo est celle du jour (ou d'un jour proche, jusqu'à 15 jours) pour une seule ville.
