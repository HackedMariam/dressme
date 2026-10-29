# BO4 · Recommandation de tenues et Stylist Agent

BO4 est la partie **recommandation** de DressMe : à partir de la garde-robe détectée par BO1, il propose des
tenues adaptées à l'occasion, à la saison et à la météo, et les explique. Il comprend :

- **le moteur de recommandation** (`backend/outfit_engine.py`) : il combine les vêtements (haut + bas, robe, avec ou
  sans veste) et calcule un score **heuristique** sur 100 (ce n'est pas une probabilité) :
  0,30 couleur + 0,20 style + 0,30 occasion + 0,20 saison, avec des explications pour chaque tenue ;
- **le Stylist Agent** (`backend/stylist_agent.py`) : un agent conversationnel LangGraph qui comprend une demande en
  français ou en anglais, lit la garde-robe dans BO1, applique les contraintes, appelle le moteur et répond ;
- **une interface web** (`backend/stylist_web.py`) au style du template DressMe de l'équipe ;
- **des évaluations** : extraction d'intention (I79), protocole d'évaluation humaine (ISSUE-08), FashionCLIP (E1),
  Qwen3-VL (E2).

## Le Stylist Agent : graphe LangGraph à 9 nodes

```
START → extract_intent ─┬─ occasion manquante ──→ clarify ──────────────────→ END
                        ├─ retour 👍 / 👎 ──────→ record_feedback ─┬─ merci ──→ END
                        │                                          └─ rejet ───┐
                        └─ occasion connue ──→ get_weather ←───────────────────┘
                                               → fetch_wardrobe ── BO1 indisponible ──┐
                                               → apply_constraints                    │
                                               → recommend                            │
                                               → style_advice → respond ←─────────────┘ → END
```

| Node | Rôle |
|---|---|
| `extract_intent` | occasion, saison, dress code, contraintes, retour sur une tenue ; **règles + LLM local** (Ollama `qwen2.5:3b`) avec un garde-fou qui rejette les contraintes que le LLM invente |
| `clarify` | demande l'occasion quand elle manque |
| `record_feedback` | enregistre un 👍 / 👎 (fichier JSON local) et met à jour le profil de style |
| `get_weather` | prévision Open-Meteo (ville par défaut : Tunis) pour déduire la saison |
| `fetch_wardrobe` | lit la garde-robe dans BO1 : `GET /api/items` |
| `apply_constraints` | retire les vêtements refusés (« sans veste », « pas de noir », « évite les jupes »…) |
| `recommend` | appelle `outfit_engine.recommend_outfits`, applique le dress code, le profil et la diversité ; en business ou formal : pas de short ni de pièce « mini », et veste structurée exigée si l'utilisateur en possède une |
| `style_advice` | conseil de style BO5 (RAG), **désactivé par défaut** |
| `respond` | réponse construite uniquement à partir des tenues classées par le moteur |

L'agent **n'invente jamais de vêtement** : toutes les pièces proposées viennent de la garde-robe lue dans BO1.
La mémoire de conversation (occasion, contraintes, tenues déjà montrées) est gérée par LangGraph, par fil de discussion.

## Dépendance au vrai BO1

Le Stylist Agent lit la garde-robe dans **BO1 (branche `wardrobe` de ce dépôt)**, par `GET /api/items` sur le
**port 8000**, en mode local (utilisateur `local`, sans Supabase ni clé). L'adaptateur `backend/bo1_api_adapter.py`
convertit les vêtements BO1 (catégories, couleurs, styles, chaleur) au format du moteur BO4.

Sans BO1, l'agent peut utiliser une garde-robe d'exemple au même format : `backend/tests/fixtures/bo1_items_sample.json`
(option `--fallback`).

> `bo1_adapter.py` est un ancien adaptateur pour mon essai de BO1 (FashionCLIP), conservé uniquement parce que
> l'expérience E1 vérifie son empreinte ; le Stylist Agent utilise `bo1_api_adapter.py`, qui lit le vrai BO1
> (branche `wardrobe`) par `GET /api/items`.

## État actuel de la démo et de Supabase

- **La démo utilise BO1 en mode local**, avec **10 photos H&M** envoyées à `POST /api/items/analyze` : BO1 tourne
  sans `.env` ni clé Supabase, stocke tout dans `local_data/db.json` sous l'utilisateur unique `local`, et le Stylist
  Agent lit cette garde-robe par `GET /api/items`. Le dataset H&M ne sert qu'aux tests et aux démonstrations ; le
  code du Stylist Agent ne le lit jamais directement.
- **Le branchement sur le Supabase partagé attend une décision d'équipe sur la table des vêtements** : BO1 (branche
  `wardrobe`) écrit dans sa propre table `items` (`supabase/schema.sql`), alors que le schéma partagé
  (`supabase/migrations/`, branche `rag/try1`) définit `wardrobe_items`, `item_images` et `image_analyses`.
  `bo1_api_adapter.py` correspond aujourd'hui aux champs de `items` ; il faudra l'adapter si `wardrobe_items` est retenue.

## Multi-utilisateur (jeton Supabase)

Le Stylist Agent sait servir plusieurs utilisateurs, chacun avec sa garde-robe, ses conversations et son profil :

- **Jeton** : `/api/chat`, `/api/feedback`, `/api/profile` et `/api/wardrobe` lisent `Authorization: Bearer <jeton
  Supabase>`. Le jeton est transmis à BO1 (`GET /api/items`) pour lire la garde-robe **de cet utilisateur**.
- **Identité** : l'identifiant vient de `GET /api/me` de BO1 avec ce jeton (pas de décodage local du JWT) ; un jeton
  refusé par BO1 donne une erreur 401.
- **Jeton jamais conservé** : il passe par la configuration du tour LangGraph (clé `__bo1_token`, objet au contenu
  masqué), jamais par l'état que le checkpointer garde en mémoire ; un test le vérifie.
- **Conversations isolées** : la clé du fil est `<user_id>:<thread_id>` ; un utilisateur ne peut pas reprendre la
  conversation d'un autre, même avec le même `thread_id`.
- **Profils 👍 / 👎 séparés** : chaque retour est enregistré sous l'identifiant réel de l'utilisateur.
- **Mode développement inchangé** : sans jeton et sans `--require-auth`, l'utilisateur est `local` (ou celui de
  `BO1_TOKEN`), comme avant.
- **Mode production** : `--require-auth` renvoie 401 sans jeton, refuse un BO1 resté en mode local (503) et refuse
  `--fallback` au démarrage, pour qu'une panne de BO1 ne bascule jamais en silence sur une garde-robe d'exemple.

Limite : la page de `stylist_web.py` n'a pas d'écran de connexion. En mode `--require-auth`, le jeton doit venir du
front de l'équipe (connexion Supabase, comme `frontend/src/api.js` de BO1 avec `supabase.auth.getSession()`).

## Installation

Python 3.11 (64 bits), depuis `bo4/backend` :

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install fastapi==0.143.0 "uvicorn[standard]==0.54.0" langgraph==1.2.16 `
    pydantic==2.14.0 requests==2.34.2 httpx==0.28.1 pillow==12.3.0 psutil==7.2.2 numpy==2.4.6 `
    "psycopg[binary]==3.3.6" pytest==8.4.2 websockets==16.1.1
# Uniquement pour l'expérience E1 (FashionCLIP, CPU) :
.\.venv\Scripts\python.exe -m pip install fashion-clip==0.2.2 transformers==4.44.2 torch==2.14.1
```

Optionnel :
- **Ollama** avec le modèle `qwen2.5:3b` (`ollama pull qwen2.5:3b`) pour la compréhension des demandes ; sans LLM,
  l'agent fonctionne avec ses règles (`--no-llm`).
- **BO1** : voir la branche `wardrobe` (`backend/`, `uvicorn app.main:app --port 8000`).
- **PostgreSQL** (`dressme_db`) uniquement pour l'ancienne API `backend/main.py` ; le mot de passe est lu dans
  `POSTGRES_PASSWORD` ou demandé au lancement, jamais écrit dans le code.

## Données H&M (non fournies)

Le dataset H&M n'est pas dans le dépôt. Pour les tests et démos qui en ont besoin, placez-le ainsi :

```
bo4/data/hm/catalog_products.csv
bo4/data/hm/articles.csv
bo4/data/hm/images/<3 premiers chiffres>/<article_id>.jpg
```

(`bo4/data/` est ignoré par git.) **18 tests** en ont besoin et échouent sans lui ; tous les autres passent :

| Fichier de test | Tests | Pourquoi |
|---|---|---|
| `tests/test_api_contract.py` | 12 | `main.py` monte le dossier `data/hm/images` au démarrage |
| `tests/test_fashionclip_e1.py` | 4 | images réelles d'E1 (et poids FashionCLIP en cache local) |
| `tests/test_qwen3vl_e2.py` | 1 | vérifie les images réelles de la sélection E2 |
| `tests/test_qwen3vl_e2_human_eval.py` | 1 | vérifie les 4 images réelles de l'évaluation humaine |

`backend/demo_bo4_web.py` (démo visuelle du moteur seul) a aussi besoin du dataset H&M non fourni.

Extraits du dataset H&M (Kaggle) à usage académique ; à retirer si le dépôt devient public.
(Les CSV de protocole contiennent quelques identifiants, noms et couleurs d'articles H&M, sans image.)

## Commandes

Depuis `bo4/backend` :

```powershell
# Tous les tests (dataset H&M en place : 1095 réussis, 25 ignorés)
.\.venv\Scripts\python.exe -m pytest -q
# Moteur BO4 (301 tests)
.\.venv\Scripts\python.exe -m pytest tests/test_outfit_engine.py tests/test_layers_and_conflicts.py tests/test_ranking_determinism.py -q
# Stylist Agent (5 fichiers, 289 tests)
.\.venv\Scripts\python.exe -m pytest tests/test_stylist_agent.py tests/test_stylist_web.py tests/test_stylist_feedback.py tests/test_bo1_api_adapter.py tests/test_bo5_client.py -q
```

### Interface web du Stylist Agent

```powershell
# Avec le vrai BO1, le LLM et la météo
.\.venv\Scripts\python.exe stylist_web.py --port 8061 --bo1-url http://localhost:8000
# Plan B, sans BO1 : garde-robe d'exemple
.\.venv\Scripts\python.exe stylist_web.py --port 8060 --fallback tests\fixtures\bo1_items_sample.json
```

| Option | Effet |
|---|---|
| `--port` | port de la page (8060 par défaut) |
| `--bo1-url` | URL de BO1 (défaut : `$BO1_API_URL`, sinon `http://localhost:8000`) |
| `--fallback <fichier.json>` | garde-robe d'exemple au format `/api/items` si BO1 est injoignable |
| `--no-llm` | extraction d'intention par règles uniquement (sans Ollama) |
| `--no-weather` | saison déduite de la date, sans Open-Meteo |
| `--city` | ville par défaut pour la météo (Tunis) |
| `--feedback-file` | fichier des 👍 / 👎 (`stylist_feedback.json`, ignoré par git) |
| `--bo5-url` | active le conseil de style BO5 (RAG, `POST /ask`) ; clé facultative dans `BO5_API_KEY` |
| `--require-auth` | mode production : jeton Supabase obligatoire (voir « Multi-utilisateur ») ; incompatible avec `--fallback` |

Variables d'environnement utiles : `BO1_API_URL`, `BO5_API_URL`, `BO5_API_KEY`, `OLLAMA_URL`, `STYLIST_LLM_MODEL`,
`STYLIST_CITY`. La même logique existe en ligne de commande : `stylist_agent.py --trace` (mêmes options, sans
`--port` ; `--graph` affiche le graphe au format Mermaid).

### Script de démo `start_demo.ps1`

`bo4/start_demo.ps1` démarre BO1 (port 8000) s'il ne répond pas, préchauffe le LLM, vide le profil de style, lance
le Stylist (port 8061) et ouvre la page. **Chemins à adapter** à votre machine, en haut du script :

| Variable | Valeur actuelle | À adapter |
|---|---|---|
| `$Bo1Dir` | `C:\Users\Win11\DressMe-team\backend` | dossier `backend` de votre copie de la branche `wardrobe` |
| `$Bo1Python` | `$Bo1Dir\.venv-bo1\Scripts\python.exe` | Python de l'environnement de BO1 |
| `$Python` | `bo4\backend\.venv\Scripts\python.exe` (relatif au script) | si votre venv est ailleurs |
| `$LlmModel` | `qwen2.5:3b` | si vous utilisez un autre modèle Ollama |

```powershell
cd bo4
powershell -ExecutionPolicy Bypass -File .\start_demo.ps1
```

Le script ne télécharge jamais de modèle : si `qwen2.5:3b` est absent, il le signale et l'agent utilise ses règles.

## Résultats

- **Tests** : 1095 réussis, 25 ignorés (tests PostgreSQL d'intégration sans base) ; 301 tests du moteur ;
  289 tests du Stylist Agent (dont 67 pour l'adaptateur BO1 et 11 pour le multi-utilisateur).
- **Extraction d'intention (I79)**, `backend/evaluation/intent/report.md` : système complet (règles + LLM + garde-fou)
  - 50 phrases : 39/50 demandes entièrement correctes avant corrections, 46/50 après (chiffre **optimiste**,
    corrections faites en regardant ces phrases) ;
  - **jeu mis de côté** (15 phrases écrites avant les corrections) : **8/15 → 14/15** (chiffre honnête) ;
  - le LLM seul invente 117 contraintes sur 50 phrases ; le garde-fou les rejette toutes.
- **E1 (FashionCLIP zero-shot)** : pas meilleur que la réponse majoritaire, non retenu pour BO4.
- **E2 (Qwen3-VL 2B local)** : prompt v2 retenu (9/10 JSON valides, environ 30 s par vêtement) ; utilisable seulement
  hors ligne ; exactitude à mesurer sur un jeu plus grand (E2-b).

## Limites

- Score **heuristique**, pondérations choisies à la main, non apprises ; pas de chaussures ni d'accessoires.
- Avec les données BO1 réelles, la qualité dépend de la détection YOLO (par exemple une robe détectée comme pull).
- Petit LLM local : environ 3 s par demande ; certaines paraphrases sans mot-clé restent mal comprises
  (« TD à l'amphi », « pique-nique »).
- Évaluations sur peu de phrases et un seul annotateur ; latence mesurée sur un PC portable (RTX 2050, 8 Go de RAM).
- Le profil de style est un fichier JSON local, sans authentification (démo mono-utilisateur).
- **Dress code business / formal par mots-clés** : les shorts et les pièces « mini » sont repérés par la catégorie,
  le nom et la sous-catégorie BO1 (`mini`, `minijupe`, `shorts`, `hot pants`). Une pièce courte nommée autrement
  passe ; une coupe peu adaptée sans mot-clé (par exemple un pull épaules dénudées classé « elegant » par BO1) aussi,
  faute d'attribut de coupe ou d'encolure dans BO1.
- **Veste structurée** : blazer, ou veste de formalité BO1 ≥ 4. Elle est exigée en business ou formal seulement si
  l'utilisateur en possède une ; les manteaux ne comptent pas. Le moteur BO4 lui-même ne valorise pas la veste
  (ajouter une veste ne fait presque jamais monter le score) : c'est la règle de dress code qui l'impose.
- **Doublons à corriger côté BO1** : une même photo envoyée deux fois crée deux vêtements identiques (même photo
  d'origine, même découpe). Le Stylist ne propose plus deux tenues qui ne diffèrent que par ce doublon, mais il
  reste dans la garde-robe : BO1 devrait refuser une photo déjà analysée (même empreinte d'image).

## Données personnelles et fichiers non publiés

- Les annotateurs humains sont **pseudonymisés** (A, B).
- `backend/experiments/qwen3vl_e2/output_human_eval/annotation_e2_humaine.html` n'est pas publié (il contient des
  images H&M). Pour le régénérer, dataset H&M en place, dans un dossier séparé (le manifeste publié n'est pas écrasé) :

```powershell
.\.venv\Scripts\python.exe -c "from experiments.qwen3vl_e2 import human_eval; human_eval.build('formulaire_e2')"
```
