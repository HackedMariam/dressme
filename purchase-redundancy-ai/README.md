# 👕 Purchase Redundancy AI — « Ai-je déjà ça ? »

Assistant d'achat vestimentaire qui vous dit, **avant de payer**, si un vêtement fait doublon avec ce que vous possédez déjà.

Prenez une photo (caméra ou fichier) ou décrivez l'article. Le système le compare visuellement à votre garde-robe avec **CLIP**, calcule un score de redondance de 0 à 100 et rend un verdict : **Acheter**, **À réfléchir** ou **Inutile**. Un **styliste IA agentique** (GPT-4.1 ou Claude) analyse la garde-robe, calcule des scores de synergie et de similarité, compose et **enregistre** des tenues, et **prépare des actions** (retirer un doublon, ajouter un achat) que vous validez d'un clic.

Interface au design **DressMe** (Playfair Display + Inter, barre latérale anthracite, accents olive), d'après la maquette « DressMe UI Blueprint ».

| | |
|---|---|
| **Backend** | FastAPI · SQLAlchemy (SQLite ou **PostgreSQL**) · cache **Redis** optionnel · CLIP `openai/clip-vit-base-patch32` |
| **IA générative** | OpenAI **GPT-4.1** (par défaut) ou Anthropic **Claude Opus 5.5**, avec repli local sans clé |
| **Frontend** | React 18 · Vite 5 · français, responsive, thème clair/sombre, caméra, mises à jour en direct (WebSocket) |
| **Comptes** | Inscription et connexion (JWT) ; garde-robe et historique privés par compte ; mode invité |
| **Exploitation** | Logs JSON avec rotation · métriques Prometheus · tableau de bord · limitation de débit · validation stricte |
| **Données** | **761 vrais produits avec vraies photos** issus de 4 sources ouvertes |
| **Tests** | **146 tests** pytest, validés sur SQLite **et** sur PostgreSQL + Redis |
| **Démo** | 4 comptes (2 femmes, 2 hommes) avec 49 à 52 vraies pièces chacun, profil complet et analyses |

---

## Sommaire

1. [Fonctionnalités](#1-fonctionnalités)
2. [Démarrage rapide](#2-démarrage-rapide)
3. [Configuration (.env)](#3-configuration-env)
4. [Architecture](#4-architecture)
5. [Comment le score est calculé](#5-comment-le-score-est-calculé)
6. [L'agent IA autonome](#6-lagent-ia-autonome)
7. [Comptes et confidentialité](#7-comptes-et-confidentialité)
8. [PostgreSQL, Redis et passage à l'échelle](#8-postgresql-redis-et-passage-à-léchelle)
9. [Monitoring et analytics](#9-monitoring-et-analytics)
10. [Le catalogue de données réelles](#10-le-catalogue-de-données-réelles)
11. [Référence de l'API](#11-référence-de-lapi)
12. [Les 31 fonctions](#12-les-31-fonctions)
13. [Tests](#13-tests)
14. [Dépannage](#14-dépannage)
15. [Sécurité](#15-sécurité)
16. [Limites connues et choix techniques](#16-limites-connues-et-choix-techniques)

---

## 1. Fonctionnalités

L'interface est disponible sur `http://localhost:3000`.

| Écran | Ce que l'utilisateur peut faire |
|---|---|
| **Tableau de bord** (page d'accueil) | Salutation, **tenue IA du jour** (composée avec vos pièces, adaptée à la saison, avec son score de synergie) ; **actions en attente de votre accord** ; **santé de la garde-robe** (score 0-100 et 4 sous-scores) ; **conseils priorisés** ; **composition** comparée à l'idéal pour votre sexe ; **palette** ; **doublons regroupés** avec « Retirer » ; pièces stars et orphelines ; **activité** (verdicts par jour, économies). |
| **Studio de tenues** | **Composer** : choisir des pièces (recherche, filtre par catégorie) ; le **score de synergie** 0-100 se recalcule à chaque ajout (couleurs, complétude, cohérence de style, saison, rôles en double), avec conseils et pièces pour compléter ; **enregistrer** la tenue (nom, occasion) et retrouver « Mes tenues ». **Comparer** : la similarité CLIP de deux pièces, avec le verdict « doublon probable » ou non. |
| **Dois-je l'acheter ?** | Photographier un article avec la **caméra**, ou importer une photo. La couleur, la catégorie, le style et la matière sont détectés automatiquement et restent modifiables. On obtient ensuite le score, le verdict, les pièces similaires déjà possédées, une explication rédigée par GPT/Claude et des alternatives du catalogue. |
| **Styliste IA** | Une conversation avec mémoire. Raccourcis : **Diagnostic**, **Que porter ?**, **Quoi acheter ?**, **Trier & revendre**, **Dois-je l'acheter ?**, **Noter & enregistrer**, **Comparer deux pièces** — ou une question libre, avec photo si besoin. Le raisonnement (outils utilisés) se déplie ; les réponses sont illustrées par des cartes : tenues, score de synergie, similarité, tenue enregistrée, **propositions à valider**, doublons, produits, verdict. Une colonne affiche le contexte de l'agent (garde-robe, profil, saison, mémoire) et les actions en attente. |
| **Garde-robe** | Ajouter une pièce (photo ou formulaire), la **modifier** en cliquant dessus, la supprimer, filtrer par catégorie, rechercher, voir la valeur totale. **Garde-robe de départ** : 40+ vraies pièces adaptées (femme ≈ 50, homme ≈ 47, mixte) en un clic, sans rien supprimer. Sous 40 pièces, une suggestion propose de la compléter. Après une analyse, « Ajouter à ma garde-robe » y range l'article. |
| **Trouver similaire** | **Chercher par photo** (les 24 produits visuellement les plus proches, avec le % de similarité) ou parcourir les 761 produits, faire une **recherche sémantique CLIP** (en anglais : « black leather boots »…), filtrer par catégorie, source ou « avec prix », **trier** par pertinence, prix ou nom. Chaque fiche produit propose le bouton **« Ai-je déjà ça ? »** et indique la source et la licence de l'image. |
| **Profil de style** | Esthétique de la garde-robe (part de chaque style, cohérence), palette, couleurs préférées, **archétype** déduit de vos pièces (minimaliste intemporel, coloriste, classique raffiné…), tailles et chiffres clés. |

Fonctions transversales :
- **Compte** (« Se connecter » en bas de la barre latérale) : garde-robe et historique privés et synchronisés entre appareils. Le formulaire d'inscription a trois parties :
  1. **Mon compte** : nom, e-mail, mot de passe.
  2. **Mon profil** : je suis femme / homme / non précisé, taille de vêtements (XS à XXL), pointure (35 à 48), jusqu'à 5 styles et 8 couleurs préférés.
  3. **Ma garde-robe** : garde-robe de départ adaptée, avec l'aperçu de sa composition, et transfert facultatif de la garde-robe invitée.

  Le profil se modifie ensuite en cliquant sur son nom.
- **Le profil adapte** :
  - la garde-robe de départ : robes, talons, ballerines, sacs et bijoux pour une femme ; chemises, chaussures de ville, ceintures et montres pour un homme ;
  - les tailles des pièces (taille de vêtements, pointure pour les chaussures, aucune taille pour les accessoires) ;
  - le choix des pièces selon les styles et couleurs préférés ;
  - le filtre « Pour femme / homme » du catalogue, présélectionné.
- **Temps réel** : une analyse faite sur le téléphone met à jour le tableau de bord ouvert sur l'ordinateur, avec une notification.
- **Veille automatique** : quand une pièce ajoutée fait doublon avec une pièce existante, l'agent crée une alerte « Retirer la nouvelle pièce / Garder » sans qu'on lui demande rien.
- **Thème** clair, sombre ou celui du système. Les animations sont réduites si le système le demande.
- Les produits déjà possédés ne sont jamais proposés comme alternatives.

---

## 2. Démarrage rapide

### Prérequis

- Python **3.10+** (testé avec 3.13)
- Node.js **18+** (testé avec 24)
- Environ 2 Go d'espace disque (PyTorch et le modèle CLIP, ~600 Mo, téléchargé au premier lancement)
- *(Optionnel)* une clé OpenAI ou Anthropic. Sans clé, l'application fonctionne avec des explications à base de règles et un agent local.
- *(Optionnel)* Docker, pour PostgreSQL et Redis (voir [section 8](#8-postgresql-redis-et-passage-à-léchelle)).

### Installation automatique

```powershell
# Windows PowerShell
powershell -ExecutionPolicy Bypass -File setup.ps1        # -NoClip pour une installation légère sans torch
```

```bash
# Linux / macOS / Git Bash
bash setup.sh                                             # --no-clip pour une installation légère
```

Le script :
- crée `backend/venv` et installe les dépendances Python et npm ;
- initialise la base SQLite ;
- crée `.env` à partir de `.env.example`, **uniquement s'il n'existe pas**.

### Installation manuelle

```bash
cd backend
python -m venv venv
venv/Scripts/pip install -r requirements.txt -r requirements-ml.txt   # Windows  (venv/bin/pip sous Linux/macOS)
venv/Scripts/pip install -r requirements-dev.txt                      # pour les tests
cd ../frontend
npm install
cp ../.env.example ../.env    # puis éditez .env
```

### Lancement

Ouvrez deux terminaux.

```powershell
# Terminal 1 — backend  →  http://localhost:8000   (documentation interactive : /docs)
cd backend
.\venv\Scripts\python main.py

# Terminal 2 — frontend →  http://localhost:3000
cd frontend
npm run dev
```

**Si le port 8000 est déjà pris**, le backend refuse de démarrer et l'indique. Lancez-le sur un autre port et pointez le frontend dessus :

```powershell
cd backend;  $env:API_PORT="8001"; .\venv\Scripts\python main.py
cd frontend; $env:BACKEND_URL="http://127.0.0.1:8001"; npm run dev
```

Le frontend appelle l'API via le proxy Vite (`/api` → `BACKEND_URL`, WebSocket compris). Il n'y a donc pas de problème de CORS en développement.

### Comptes de démonstration (hommes et femmes)

```bash
cd backend
venv/Scripts/python seed_demo_users.py           # crée les comptes manquants
venv/Scripts/python seed_demo_users.py --reset   # reconstruit leurs garde-robes et historiques
```

| Compte | Profil | Garde-robe |
|---|---|---|
| `sofia.martin@example.com` | femme, S / 38, classique, couleurs neutres | 52 pièces |
| `emma.laurent@example.com` | femme, M / 39, décontractée, couleurs vives | 52 pièces |
| `karim.benali@example.com` | homme, L / 43, habillé, bleu marine / gris | 49 pièces |
| `yassine.haddad@example.com` | homme, M / 42, sport / décontracté | 49 pièces |

Mot de passe : `Doublon-Demo2026` (modifiable via `DEMO_PASSWORD`).
- Les garde-robes viennent du catalogue réel, filtré par genre. Chacune contient quelques quasi-doublons, comme une vraie garde-robe, ce qui est utile pour tester l'audit.
- Chaque compte a 6 achats envisagés, analysés par le vrai moteur CLIP.
- Aucun prix n'est inventé.
- Le script ne touche qu'à ces 4 comptes.

### Vérifier que tout fonctionne

```bash
curl http://localhost:8000/health       # base, cache, CLIP, LLM
curl http://localhost:8000/llm/status   # fournisseur LLM actif (openai / claude) et modèle
```

---

## 3. Configuration (`.env`)

Le fichier `.env` se trouve à la racine du projet. Toutes les variables sont documentées dans [.env.example](.env.example).

**IA**

| Variable | Défaut | Rôle |
|---|---|---|
| `LLM_PROVIDER` | `auto` | `openai`, `claude` ou `auto` (OpenAI si `OPENAI_API_KEY` est défini, sinon Claude) |
| `OPENAI_API_KEY` / `OPENAI_MODEL` | — / `gpt-4.1` | Clé et modèle OpenAI |
| `CLAUDE_API_KEY` / `LLM_MODEL` | — / `claude-opus-5-5` | Clé et modèle Anthropic |
| `LLM_ENABLED` | `True` | `False` = aucun appel LLM (règles et agent local uniquement) |
| `CLIP_ENABLED` | `True` | `False` = pas de CLIP (embeddings simulés, démarrage rapide) |
| `USE_CUDA` | `False` | Utiliser le GPU pour CLIP |
| `CLIP_QUANTIZE` | `False` | Quantification int8 : plus rapide mais moins précise, déconseillée (voir [section 16](#16-limites-connues-et-choix-techniques)) |

**Données et infrastructure**

| Variable | Défaut | Rôle |
|---|---|---|
| `CATALOG` | `real` | `real` (photos réelles) ou `illustrated` (catalogue illustré généré) |
| `DATABASE_URL` | SQLite `data/redundancy.db` | Toute URL SQLAlchemy, par ex. `postgresql://user:mdp@hôte:5433/base` |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | `5` / `10` | Pool de connexions PostgreSQL |
| `REDIS_URL` | — | Cache et compteurs partagés. S'il est vide ou injoignable, un cache en mémoire est utilisé. |
| `CACHE_TTL` | `300` | Durée de vie du cache (secondes) |

**Comptes, sécurité, exploitation**

| Variable | Défaut | Rôle |
|---|---|---|
| `SECRET_KEY` | générée | Clé de signature des jetons. Si elle est vide, une clé est créée une fois dans `data/.secret_key`. **À définir en production.** |
| `JWT_EXPIRE_HOURS` | `168` | Durée d'une session (7 jours) |
| `AUTH_REQUIRED` | `False` | `True` : compte obligatoire. `False` : les visiteurs sans compte partagent la garde-robe invitée. |
| `RATE_LIMIT_ENABLED` | `True` | Limitation de débit par IP |
| `RATE_LIMIT_DEFAULT` / `_HEAVY` / `_AUTH` | `300` / `30` / `10` | Requêtes par minute : général / analyses, agent, photos / connexion |
| `LOG_LEVEL` / `LOG_FORMAT` | `INFO` / `text` | `json` = une ligne JSON par événement (Loki, ELK, Datadog) |
| `API_HOST` / `API_PORT` | `0.0.0.0` / `8000` | Adresse d'écoute du backend |
| `CORS_ORIGINS` | `*` | Origines autorisées (séparées par des virgules) |
| `VITE_CDN_URL` | — | (frontend) Sert les images du catalogue depuis un CDN |

> Si le LLM échoue (clé invalide, quota épuisé, crédit nul, réseau), l'application **ne plante pas**. Elle bascule sur les explications à base de règles et sur l'agent local, et affiche un avertissement.

---

## 4. Architecture

```
purchase-redundancy-ai/
├── backend/
│   ├── main.py              # API FastAPI : routes, middlewares, WebSocket, fichiers statiques
│   ├── config.py            # Lecture du .env et paramètres
│   ├── engine.py            # RedundancyEngine : embeddings (cache), recherche catalogue, comparaison, analyse
│   ├── clip_integration.py  # CLIP : embeddings texte/image, zero-shot, couleurs HSV, quantification optionnelle
│   ├── features.py          # Les 31 fonctions (FeatureSet) + registre
│   ├── agent.py             # Conseiller : 6 missions, routage d'intention, mode LLM ou local, streaming
│   ├── agent_tools.py       # Outils partagés GPT / Claude (diagnostic, tenues, achats, tri, doublons…)
│   ├── wardrobe_insights.py # Diagnostic : santé, composition, doublons, palette, polyvalence, conseils
│   ├── openai_client.py     # Client GPT (explications, boucle d'outils, vision) + choix du fournisseur
│   ├── llm_client.py        # Client Claude (SDK anthropic, Tool Runner)
│   ├── prompts.py           # Prompts système et gabarits
│   ├── models.py            # Modèles SQLAlchemy, migration automatique (colonnes + index), requêtes
│   ├── auth.py              # Mots de passe PBKDF2, jetons JWT, utilisateur courant
│   ├── validators.py        # Modèles de requête avec validation stricte
│   ├── pagination.py        # Enveloppe de pagination commune
│   ├── cache.py             # Cache Redis ou mémoire (même API), décorateur, compteurs
│   ├── rate_limiter.py      # Limitation de débit (middleware ASGI)
│   ├── monitoring.py        # Métriques par route, format Prometheus, ID de requête, limite de taille
│   ├── logger.py            # Logs texte/JSON avec rotation, ID de requête sur chaque ligne
│   ├── live.py              # Hub WebSocket (événements par utilisateur)
│   ├── migrate_db.py        # Copie SQLite → PostgreSQL
│   ├── seed_demo_users.py   # Comptes de démonstration (hommes et femmes)
│   ├── wardrobe_builder.py  # Garde-robes de départ (plans femme / homme / mixte, 40+ pièces)
│   └── requirements*.txt    # base / ML (torch, transformers) / dev (pytest, couverture)
├── frontend/src/
│   ├── App.jsx              # Navigation, compte, thème, connexion temps réel
│   ├── api.js               # axios + jeton, streaming de l'agent, WebSocket avec reconnexion, CDN
│   ├── utils/analytics.js   # Suivi d'usage (lots, sans données personnelles, respecte Do Not Track)
│   ├── components/          # AccountModal, CameraModal, Icon, ui
│   └── pages/               # Home, Scan, Wardrobe, Dashboard, Agent (conseiller), Catalog
├── database/                # Collecte du catalogue réel, catalogue illustré, images (/images)
├── data/                    # Base SQLite, photos importées, caches, clé de signature (créé automatiquement)
├── tests/                   # 146 tests : API, fonctions, agent, actions, plateforme, LLM hors ligne
├── docker-compose.yml       # PostgreSQL 16 + Redis 7 (optionnels)
└── setup.ps1 / setup.sh / QUICKSTART.md
```

### Chaîne de traitement d'une requête

```
navigateur ─► Vite (/api, WebSocket, X-Forwarded-For)
           ─► ID de requête + log d'accès + métriques ─► CORS ─► limite de débit ─► taille max (15 Mo) ─► gzip
           ─► route FastAPI : validation stricte ─► utilisateur courant (JWT ou invité) ─► logique
```

### Flux d'une analyse

```
Photo / formulaire ──► /camera-capture : détection couleur, catégorie, style, matière (CLIP zero-shot)
                    └► /analyze
                          ├─ embeddings texte CLIP (cache Redis/mémoire) + embedding image (si photo)
                          ├─ comparaison avec chaque pièce de VOTRE garde-robe (60 % image, 40 % texte)
                          ├─ saturation de la catégorie, contribution aux tenues → score 0-100 → verdict
                          ├─ alternatives du catalogue (hors pièces possédées)
                          ├─ explication rédigée par GPT/Claude (ou par des règles)
                          ├─ enregistrement dans votre historique
                          └─ événement « analysis.created » envoyé à vos autres onglets
```

---

## 5. Comment le score est calculé

**Similarité avec chaque pièce possédée :**
- La similarité visuelle combine la similarité **image** CLIP (60 %) et **texte** CLIP (40 %). Sans photo, seule la similarité texte est utilisée.
- On la combine ensuite avec la correspondance de couleur, de style et de matière.
- Une pièce est retenue comme « similaire » si elle est de la même catégorie avec au moins 50 % de similarité, ou si elle atteint au moins 80 % quelle que soit sa catégorie.
- **Calibrage automatique** : au démarrage, l'échelle de similarité image est mesurée sur le catalogue chargé.
  - Le plancher est la médiane des paires de catégories différentes (0,672 sur le catalogue réel).
  - Le plafond est le 90ᵉ centile des paires de même type et même couleur (0,941).
  - L'ancien seuil fixe de 0,75 venait du catalogue illustré. Sur les vraies photos, il comptait un quart des quasi-doublons comme visuellement sans rapport.
  - Sur les paires du catalogue : quasi-doublons repérés 57 % → 80 %, fausses alertes 2,8 % → 10,1 % (paires de même catégorie mais de type différent, par exemple jean et pantalon).
- **Attribut inconnu = neutre** : une matière ou une couleur absente (fréquent sur les vrais produits) ne compte plus comme une différence.

**Score de redondance (fonction 5)** :

```
score = 0,4 × redondance visuelle
      + 0,3 × redondance fonctionnelle      (même usage / même style qu'une pièce possédée)
      + 0,2 × saturation de la catégorie    (nombre de pièces de la catégorie / limite de 5)
      + 0,1 × (100 − contribution aux nouvelles tenues)
```

| Score | Verdict |
|---|---|
| 0 – 34 | 🟢 **Acheter**. Si aucune pièce similaire n'est trouvée, le score est plafonné à 34. |
| 35 – 59 | 🟠 **À réfléchir** |
| 60 – 100 | 🔴 **Inutile** (doublon) |

---

## 6. Le conseiller IA (agent autonome)

Endpoint : `POST /agent/run`. La réponse est un flux NDJSON d'événements `start`, `step`, `notice`, `final` et `error`, non compressé pour que chaque étape arrive immédiatement.

| Mission | Ce que fait l'agent |
|---|---|
| `audit` | Diagnostic : santé 0-100, doublons regroupés, équilibre, couleurs, polyvalence, conseils, achats utiles |
| `outfits` | Comprend l'occasion (mariage, entretien, bureau, soirée, rendez-vous, sport, randonnée, plage) et la saison, puis compose jusqu'à 3 tenues différentes avec **vos** pièces, avec une veste quand il fait froid et un accessoire. Le **code vestimentaire** est respecté : pas de jean, de baskets ni de cargo à un mariage. |
| `shopping` | Vrais manques pour votre sexe, catégories à ne **pas** racheter, répartition du budget, produits réels (« j'ai 150 $ » est compris) |
| `declutter` | Quoi revendre ou donner : pièces en trop dans chaque groupe de doublons, pièces qui ne s'associent à rien |
| `purchase` | Dois-je l'acheter ? (photo et/ou texte) : doublons, associations, marché, qualité, verdict |
| `ask` | Question libre. Le LLM choisit ses outils ; en mode local, un routeur d'intention choisit la mission. |

| Mode | Fonctionnement |
|---|---|
| **LLM** (GPT-4.1 ou Claude) | Le prompt système contient le **profil** (sexe, tailles, styles, couleurs ; le sexe n'est jamais deviné). Les **10 derniers tours** de la conversation sont transmis (mémoire). <br><br>Outils d'analyse partagés par GPT et Claude : `get_wardrobe_insights`, `analyze_redundancy`, `suggest_outfits`, `plan_shopping`, `plan_declutter`, `search_catalog` (filtré par sexe), `get_wardrobe`, **`score_outfit`** (synergie 0-100), **`compare_items`** (similarité CLIP de deux pièces), `run_feature`, `list_features`. <br><br>**Outils d'action** : `save_outfit` enregistre une tenue directement (non destructif) ; `propose_remove_items` et `propose_add_items` créent une **proposition** (`pending`) que l'utilisateur approuve ou refuse : l'agent ne modifie jamais la garde-robe seul et ne propose de retirer que des pièces signalées par un outil. <br><br>**Ancrage** : le premier tour doit appeler un outil (`tool_choice` required / any), donc l'agent ne répond jamais sans avoir regardé vos données. <br><br>Règles du prompt : chaque fait vient d'un outil, rien d'inventé, vouvoiement, conclusion d'abord, moins de 150 mots. Les outils renvoient aussi des **cartes** (tenues, produits, doublons, santé) affichées sous la réponse. |
| **Local** (sans clé, ou si le LLM échoue) | Planificateurs déterministes pour chaque mission, en français. |

En mode `auto`, si le LLM échoue, l'agent passe en mode local et le signale par un événement `notice`. L'agent travaille toujours sur la garde-robe de l'utilisateur connecté.

```bash
curl -N -X POST http://localhost:8000/agent/run -H "Content-Type: application/json" \
  -d '{"mission":"ask","message":"Que porter pour un entretien cet hiver ?","history":[]}'
```

**Diagnostic** (`GET /insights`) :
- **Doublons** : même catégorie et même couleur, ou similarité d'au moins 90 % ; les groupes sont formés par **lien complet** (chaque pièce ressemble à toutes les autres du groupe, pas de chaînes « A ressemble à B, B ressemble à C »).
- **Composition** : comparée au plan femme / homme / mixte, rapporté à la taille de la garde-robe.
- **Couleurs** : 50 % pour la part de neutres, 50 % pour l'harmonie des 3 couleurs principales.
- **Polyvalence** : tenues haut + bas (+ chaussures) ou robe (+ chaussures) jugées harmonieuses.
- **Articles pour enfant** : ils restent dans le catalogue, mais n'entrent jamais dans une garde-robe adulte ni dans les suggestions.

---|---|
| **LLM** (GPT-4.1 ou Claude) | Le modèle reçoit la mission, éventuellement la photo, et décide lui-même quels outils appeler : `analyze_redundancy`, `search_catalog`, `get_wardrobe`, `list_features`, `run_feature`. Chaque appel d'outil devient une étape lisible en français. Le rapport final est complété par le verdict calculé par le moteur. |
| **Local** (sans clé, ou si le LLM échoue) | Un planificateur déterministe exécute la mission. Il comprend le texte libre en français (couleurs, catégories, matières, prix). « Achat » se déroule en 8 étapes, « Audit » en 7 (doublons internes, saturation, harmonie des couleurs, capsule…). |

En mode `auto`, si le LLM échoue, l'agent passe en mode local et le signale par un événement `notice`. L'agent travaille toujours sur la garde-robe de l'utilisateur connecté.

```bash
curl -N -X POST http://localhost:8000/agent/run -H "Content-Type: application/json" \
  -d '{"mission":"purchase","message":"Je pense acheter un manteau en laine gris à 220 $"}'
```

---

## 7. Comptes et confidentialité

| | |
|---|---|
| **Inscription** | `POST /auth/register` avec e-mail, mot de passe (8 caractères minimum, lettres et chiffres) et profil facultatif : `gender`, `clothing_size`, `shoe_size`, `style_preferences`, `favorite_colors`. `starter_wardrobe: true` crée la garde-robe de départ, `import_guest_data: true` transfère la garde-robe invitée. |
| **Connexion** | `POST /auth/login` renvoie un jeton `Bearer` valable 7 jours. Le frontend le garde dans `localStorage` et l'ajoute à chaque requête, au streaming de l'agent et au WebSocket. |
| **Mots de passe** | PBKDF2-HMAC-SHA256 (bibliothèque standard Python), sel aléatoire, 600 000 itérations (recommandation OWASP), comparaison en temps constant. |
| **Isolation** | Garde-robe, historique, avis, statistiques et événements temps réel sont filtrés par utilisateur. Une pièce ou une analyse d'un autre compte renvoie 404. |
| **Mode invité** | Sans jeton, les requêtes utilisent la garde-robe « invité » (comportement d'origine, pratique en usage personnel). `AUTH_REQUIRED=True` rend le compte obligatoire. Le catalogue reste public. |
| **Anti-énumération** | Un e-mail inconnu et un mauvais mot de passe donnent exactement la même réponse, avec le même temps de calcul. |

---

## 8. PostgreSQL, Redis et passage à l'échelle

SQLite et le cache en mémoire suffisent pour un usage personnel. Pour plusieurs utilisateurs ou plusieurs processus API :

```bash
# 1. Démarrer PostgreSQL 16 (port 5433) et Redis 7 (port 6379)
POSTGRES_PASSWORD=un-mot-de-passe-solide docker compose up -d

# 2. Copier les données existantes (la base SQLite source n'est jamais modifiée)
cd backend
venv/Scripts/python migrate_db.py --target postgresql://redundancy:un-mot-de-passe-solide@localhost:5433/purchase_redundancy

# 3. Dans .env
DATABASE_URL=postgresql://redundancy:un-mot-de-passe-solide@localhost:5433/purchase_redundancy
REDIS_URL=redis://localhost:6379/0
```

### Héberger la base sur Supabase

Supabase est un PostgreSQL hébergé : le projet s'y branche sans changer de code. La base de démonstration tourne sur le projet Supabase « DressMe » (région eu-west-1).

Les tables de l'application vivent dans un **schéma dédié, `dressme_ai`**, avec un **rôle dédié** :
- le schéma `public` du projet contient déjà d'autres tables (dont `products` et `wardrobe_items`) : un schéma séparé évite toute collision ;
- Supabase expose `public` par son API REST ; `dressme_ai` ne l'est pas, donc la table `users` n'est pas lisible depuis internet ;
- le rôle de l'application n'a des droits que sur son schéma.

1. Dans Supabase, **SQL Editor** :

   ```sql
   create role dressme_ai with login password 'un-mot-de-passe-solide';
   grant dressme_ai to postgres;
   create schema dressme_ai authorization dressme_ai;
   alter role dressme_ai set search_path = dressme_ai;
   ```

2. **Connect → Session pooler** donne l'hôte (`aws-0-<région>.pooler.supabase.com`). Utilisez le port **5432** (mode session : le `search_path` du rôle est appliqué), et l'utilisateur `dressme_ai.<id du projet>`.
3. Copier les données locales, puis mettre la même adresse dans `.env` :

   ```bash
   cd backend
   venv/Scripts/python migrate_db.py --target "postgresql://dressme_ai.<id du projet>:<mot de passe>@aws-0-<région>.pooler.supabase.com:5432/postgres?sslmode=require"
   ```

   ```
   DATABASE_URL=postgresql://dressme_ai.<id du projet>:<mot de passe>@aws-0-<région>.pooler.supabase.com:5432/postgres?sslmode=require
   ```

4. Redémarrer l'API : `/health` indique `"database": "postgresql"`. Les tables apparaissent dans **Table Editor**, schéma `dressme_ai`.

Les clés d'API Supabase (`sb_publishable_…`, `sb_secret_…`) ne servent pas ici : le backend parle directement à PostgreSQL. Les tests restent sur une base temporaire, même quand `.env` pointe vers Supabase. Pour revenir à SQLite, commentez `DATABASE_URL`.

### Notes

- **Migration du schéma** : au démarrage, les tables, colonnes et index manquants sont créés automatiquement, sur SQLite comme sur PostgreSQL.
- **Redis** partage entre les processus API :
  - les embeddings texte CLIP (24 h) ;
  - les résultats de recherche sémantique ;
  - les compteurs de limitation de débit.

  Si Redis tombe, l'API continue avec le cache en mémoire.
- **Images** : `/images` est servi avec `Cache-Control: immutable` (7 jours). Un CDN peut donc le mettre en cache tel quel (`VITE_CDN_URL`). Les réponses JSON de plus de 1 Ko sont compressées en gzip.
- **Derrière un reverse proxy** : uvicorn lit `X-Forwarded-For` uniquement pour les proxys listés dans `FORWARDED_ALLOW_IPS` (127.0.0.1 par défaut). Ainsi, la limitation de débit s'applique à chaque client et non au proxy.

---

## 9. Monitoring et analytics

| Endpoint | Contenu |
|---|---|
| `GET /health` | État de la base (ping réel), backend de cache, CLIP, LLM |
| `GET /metrics` | Format **Prometheus** : requêtes par route et par résultat, latences p50/p95/p99, cache, rejets 429, connexions temps réel |
| `GET /analytics/system` | Les mêmes métriques en JSON (utilisées par la page Statistiques) |
| `GET /analytics/summary?days=30` | Vos analyses par jour et par verdict, catégories, argent économisé, source des explications, temps d'analyse, pages vues, avis, composition de la garde-robe |
| `POST /analytics/events` | Événements d'usage envoyés par le frontend, par lots (pages vues, analyse faite, caméra, recherche, connexion) |

- **Logs** : `logs/app.log`, rotation à 10 Mo (5 fichiers), au format `LOG_FORMAT=text` ou `json`.
  - Chaque ligne porte l'**ID de requête**, renvoyé aussi dans l'en-tête `X-Request-ID`. Pour suivre une erreur signalée par un utilisateur, il suffit de chercher cet ID dans les logs.
- **Métriques** : elles sont en mémoire et repartent à zéro au redémarrage. Les analytics métier, elles, sont stockées en base.
- **Confidentialité** : les événements d'usage ne contiennent ni nom, ni e-mail, ni photo, ni texte libre. La validation les limite à des valeurs simples. « Do Not Track » est respecté.

---

## 10. Le catalogue de données réelles

Le catalogue contient **761 produits avec de vraies photos**. Ils ont été collectés par [database/scrape_real_catalog.py](database/scrape_real_catalog.py) dans des jeux de données ouverts et sous licence. Aucune boutique n'a été scrapée : leurs conditions d'utilisation l'interdisent.

| Source | Licence | Produits |
|---|---|---|
| [Marqo/KAGL](https://huggingface.co/datasets/Marqo/KAGL) (Hugging Face) | MIT | 530 |
| [Marqo/fashion200k](https://huggingface.co/datasets/Marqo/fashion200k) (Hugging Face) | Apache-2.0 | 169 |
| [DummyJSON](https://dummyjson.com) | API publique | 48 |
| [FakeStore API](https://fakestoreapi.com) | API publique | 14 |

Répartition : hauts 184, chaussures 150, accessoires 141, pantalons 133, vestes et manteaux 88, robes 65.

Le collecteur corrige les erreurs des sources à partir du nom du produit :
- DummyJSON classe 5 robes dans « tops » ;
- FakeStore ne fournit aucun genre ;
- un sac à dos était rangé dans les hauts.

- **Prix** : seuls DummyJSON et FakeStore publient des prix, soit **62 produits**. Pour les autres, le prix est laissé vide plutôt qu'inventé.
- **Traçabilité** : chaque produit garde sa source, sa licence et un lien vers l'origine, affichés sur sa fiche.

Pour régénérer le catalogue :

```bash
cd backend
venv/Scripts/pip install pyarrow          # nécessaire au script de collecte uniquement
venv/Scripts/python ../database/scrape_real_catalog.py
```

Le script télécharge les fichiers parquet dans `database/.scrape_cache/` (environ 1,5 Go, supprimable ensuite). Il écrit `database/products_real.json` et `database/images/real/*.jpg`. Au démarrage suivant, le backend synchronise la base. `CATALOG=illustrated` utilise à la place le catalogue illustré (700 produits).

---

## 11. Référence de l'API

La documentation interactive complète (Swagger) est disponible sur **`/docs`**. 🔒 = utilise le compte connecté (ou la garde-robe invitée sans jeton).

| Méthode | Route | Description |
|---|---|---|
| GET | `/` · `/health` | Informations · état de la base, du cache, de CLIP et du LLM |
| POST | `/auth/register` · `/auth/login` | Créer un compte · se connecter (renvoie un jeton) |
| GET · PATCH | `/auth/me` 🔒 | Compte courant · modifier le profil (sexe, tailles, styles, couleurs, nom) |
| POST | `/analyze` 🔒 | Analyse complète. Paramètres : `new_item`, `wardrobe_items` (facultatif), `image_base64`, `product_id`, `language` |
| GET | `/analyses?limit=&offset=` 🔒 | Historique paginé |
| GET | `/analysis/{id}` 🔒 | Détail d'une de vos analyses |
| GET / POST / DELETE | `/wardrobe` 🔒 | Lister (pagination facultative), ajouter (`product_id`, formulaire ou photo), vider |
| PATCH / DELETE | `/wardrobe/{id}` 🔒 | Modifier · supprimer une pièce |
| POST | `/wardrobe/sample?gender=` 🔒 | Garde-robe de départ : 40+ pièces adaptées (`Women`, `Men`, `Unspecified`). Rien n'est supprimé sauf avec `replace=true`. |
| GET | `/wardrobe/starter-plan?gender=` | Composition prévue (pièces par catégorie) |
| POST | `/agent/run` 🔒 | Conseiller (flux NDJSON) : `mission` = `ask`, `audit`, `outfits`, `shopping`, `declutter`, `purchase` ; `history` (12 tours max) |
| POST | `/outfits/score` 🔒 | Score de synergie d'une tenue (`item_ids`, 1 à 10) : score, verdict, détail, conseils, pièces pour compléter |
| GET · POST · DELETE | `/outfits` · `/outfits/{id}` 🔒 | Tenues enregistrées : lister · enregistrer (`name`, `item_ids` 2-10, `occasion`) · supprimer |
| GET | `/outfits/daily` 🔒 | Tenue du jour (stable sur la journée, adaptée à la saison) |
| POST | `/wardrobe/compare` 🔒 | Similarité de deux pièces (`item_a`, `item_b`) |
| GET | `/agent/actions?status=` 🔒 | Propositions de l'agent et alertes de la veille (`pending`, `done`, `rejected`) |
| POST | `/agent/actions/{id}/approve` · `/reject` 🔒 | Valider (exécute le retrait ou l'ajout) · refuser ; 409 si déjà décidée |
| GET | `/insights?budget=` 🔒 | Diagnostic de la garde-robe (tableau de bord), mis en cache jusqu'au prochain changement |
| POST | `/agent` | Question directe au LLM (503 sans clé) |
| GET | `/llm/status` | Fournisseur, modèle, disponibilité |
| POST | `/upload-image` · `/camera-capture` | Analyse d'une image (multipart · base64 ; `top_k` 1-24 produits proches) |
| GET | `/products` | Catalogue : `category`, `brand`, `source`, `color`, `gender`, `min_price`, `max_price`, `priced`, `q` (recherche sémantique), `sort` (`relevance`, `price_asc`, `price_desc`, `name`), `facets`, `limit` (1-200), `offset` |
| GET | `/stats` 🔒 | Catalogue + vos chiffres (analyses, économies, garde-robe) |
| POST | `/feedback` 🔒 | Avis sur une analyse (note de 0 à 5) |
| POST | `/analytics/events` 🔒 · GET `/analytics/summary` 🔒 | Suivi d'usage · vos statistiques |
| GET | `/analytics/system` · `/metrics` | Monitoring JSON · Prometheus |
| WS | `/ws/live?token=` | Événements temps réel `analysis.created`, `wardrobe.changed`, `agent.action` |
| POST | `/feature/{id}` · GET `/features` · `/prompts` | Les 31 fonctions · liste · prompts |

**Pagination** : toutes les listes renvoient `total`, `limit`, `offset`, `has_more` et `next_offset`. La liste elle-même garde sa clé historique (`products`, `items`).

**En-têtes** : `X-Request-ID` sur chaque réponse ; `X-RateLimit-Limit` et `X-RateLimit-Remaining` ; `Retry-After` en cas de 429.

**Codes d'erreur** :

| Code | Signification |
|---|---|
| 401 | Jeton absent, invalide ou expiré |
| 404 | Ressource introuvable ou appartenant à un autre compte |
| 409 | E-mail déjà utilisé · proposition déjà décidée |
| 413 | Corps de requête supérieur à 15 Mo |
| 415 | Type d'image refusé |
| 422 | Validation (le détail précise le champ) |
| 429 | Trop de requêtes |

Exemple :

```bash
TOKEN=$(curl -s -X POST localhost:8000/auth/login -H "Content-Type: application/json" \
  -d '{"email":"moi@example.com","password":"MonMotDePasse1"}' | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
curl -X POST localhost:8000/analyze -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"new_item":{"name":"Chemise oxford bleue","category":"shirts","color":"blue","price":59},"language":"fr"}'
```

---

## 12. Les 31 fonctions

Toutes ces fonctions sont exécutables via `POST /feature/{id}`. Elles sont toutes testées.

**Fonctions principales (1 à 13)**

| # | Fonction | # | Fonction |
|---|---|---|---|
| 1 | Similarité visuelle | 8 | Contribution aux tenues |
| 2 | Score de similarité | 9 | Saturation de la catégorie |
| 3 | Comparaison d'attributs | 10 | Avis utilisateur |
| 4 | Recherche de pièces similaires | 11 | Alerte doublon (fr/en) |
| 5 | Score de redondance | 12 | Explication (fr/en) |
| 6 | Scan caméra | 13 | Alternatives (fr/en) |
| 7 | Analyse de capture d'écran ou de texte de page produit | | |

**Fonctions avancées (14 à 31)**

| # | Fonction | # | Fonction | # | Fonction |
|---|---|---|---|---|---|
| 14 | Recommandations | 20 | Tendances | 26 | Garde-robe capsule |
| 15 | Analyse multi-garde-robes | 21 | Tenue pour un événement | 27 | Association de tenues |
| 16 | Rotation saisonnière | 22 | Image personnelle | 28 | Conseil de taille |
| 17 | Harmonie des couleurs | 23 | Qualité | 29 | Entretien |
| 18 | Cohérence de style | 24 | Durabilité | 30 | Score mode |
| 19 | Optimisation du budget | 25 | Valeur de revente | 31 | Veille marché |

---

## 13. Tests

```bash
cd backend
venv/Scripts/python -m pytest ../tests -q                         # 146 tests, ~15 s
venv/Scripts/python -m pytest ../tests --cov=. --cov-report=term  # couverture
```

| Fichier | Ce qui est testé |
|---|---|
| `test_api.py` | Analyse, doublons, historique, images, caméra, avis, erreurs |
| `test_features.py` | Les 31 fonctions, avec des valeurs attendues |
| `test_agent.py` | Missions achat et audit, compréhension du français, catalogue, garde-robe |
| `test_platform.py` | Comptes, jetons expirés ou falsifiés, isolation entre comptes, pagination, filtres et tri, validation, taille max, limitation de débit, cache, logs, analytics, Prometheus, gzip, WebSocket, migration |
| `test_advisor.py` | Diagnostic (doublons groupés, couleurs, genre, enfants), missions, routage, codes vestimentaires, mémoire de conversation, boucle Claude avec faux client |
| `test_agent_actions.py` | Score de synergie, tenues enregistrées et du jour, comparaison, veille sur ajout, approbation / refus / 409, confidentialité, outils d'action GPT avec faux client |
| `test_llm_offline.py` | Boucle d'outils GPT, vision, explications, erreurs d'API, repli de l'agent. Utilise un faux client OpenAI : aucun appel réseau, aucun coût. |

- Les tests utilisent une base, un dossier de photos et des logs temporaires (`DATA_DIR` et `LOG_DIR`), sans CLIP ni LLM. Ils ne touchent jamais vos données.
- **Sur PostgreSQL et Redis** : lancez `docker compose up -d`, puis exécutez les tests avec ces variables :

  ```bash
  TEST_DATABASE_URL=postgresql://redundancy:<mot de passe>@127.0.0.1:5433/purchase_redundancy \
  TEST_REDIS_URL=redis://127.0.0.1:6379/0 venv/Scripts/python -m pytest ../tests -q
  ```

- **Couverture** : 78 % au total, et plus de 87 % sur `main.py`, les modèles, l'authentification, la validation, le monitoring et la limitation de débit. Les parties les moins couvertes sont le client Claude et le chargement réel de CLIP, qui demandent le réseau ou le modèle.

---

## 14. Dépannage

| Problème | Solution |
|---|---|
| `Port 8000 already in use` | Lancez le backend avec `API_PORT=8001` et le frontend avec `BACKEND_URL=http://127.0.0.1:8001`. |
| L'interface affiche « hors ligne » | Vérifiez que le backend tourne et que `BACKEND_URL` pointe sur le bon port. |
| « Synchronisation hors ligne » | Le WebSocket se reconnecte tout seul (de 1 à 30 s). Derrière un proxy, autorisez l'upgrade WebSocket sur `/ws/`. |
| `429 Trop de requêtes` | Attendez le délai indiqué (`Retry-After`), ou augmentez `RATE_LIMIT_*`. |
| « Session expirée » | Le jeton a plus de 7 jours ou `SECRET_KEY` a changé : reconnectez-vous. |
| « CLIP non disponible » | Installez `requirements-ml.txt`, ou mettez `CLIP_ENABLED=False`. |
| Premier démarrage lent | Téléchargement de CLIP et calcul des embeddings du catalogue. Les démarrages suivants utilisent le cache. |
| Le LLM ne répond pas | Consultez `/llm/status`. L'application bascule automatiquement sur les règles et l'agent local. |
| La caméra ne s'ouvre pas | Le navigateur exige `localhost` ou HTTPS, et l'autorisation d'accès à la caméra. |
| Redis ou PostgreSQL injoignable | Redis : repli automatique sur la mémoire. PostgreSQL : `/health` affiche `degraded`. Vérifiez `docker compose ps`. |
| Repartir d'une base vide | Arrêtez le backend et supprimez `data/redundancy.db` : la base est recréée au démarrage. |

---

## 15. Sécurité

- **Ne publiez jamais `.env` ni `data/.secret_key`.** Le `.gitignore` les exclut, ainsi que la base, les photos et les logs. Seul `.env.example` doit être partagé.
- **Si une clé a été exposée** (chat, commit, capture d'écran), révoquez-la immédiatement et générez-en une nouvelle sur [platform.openai.com](https://platform.openai.com/api-keys) ou [console.anthropic.com](https://console.anthropic.com).
- **Validation stricte** sur toutes les routes :
  - chaînes nettoyées et bornées ;
  - catégories limitées à une liste fermée ;
  - prix compris entre 0 et 100 000 ;
  - identifiants contrôlés par motif (ce qui bloque les injections) ;
  - langue en liste blanche ;
  - champs inconnus refusés sur les routes de compte et d'analytics.
- **Images et requêtes** : 10 Mo par image, types JPEG, PNG et WebP uniquement, 15 Mo maximum par requête (réponse 413).
- **Limitation de débit** par IP : la connexion est limitée à 10 essais par minute (contre la force brute), et les analyses et l'agent à 30 par minute.
- **Base de données** : requêtes paramétrées via l'ORM SQLAlchemy.
- **Photos** : vider une garde-robe ne supprime que les photos de ce compte.
- **En production** :
  - définissez `SECRET_KEY` ;
  - activez `AUTH_REQUIRED=True` si le service est public ;
  - restreignez `CORS_ORIGINS` ;
  - servez le site en HTTPS ;
  - protégez `/metrics` et `/analytics/system` au niveau du reverse proxy.

---

## 16. Limites connues et choix techniques

**Ce qui a été fait différemment de la feuille de route initiale, et pourquoi :**

| Demande | Choix retenu | Raison |
|---|---|---|
| Elasticsearch | Recherche sémantique CLIP + filtres, tri et facettes en mémoire | 761 produits : un index séparé n'apporterait rien, et CLIP comprend « veste chaude pour l'hiver », ce que la recherche plein texte ne fait pas. |
| Fine-tuning de CLIP | Non fait | Il faudrait des milliers de paires annotées « doublon / pas doublon » qui n'existent pas encore, et un GPU. Les avis utilisateurs (`/feedback`) sont collectés pour pouvoir le faire plus tard. |
| Quantification de CLIP | Disponible (`CLIP_QUANTIZE`), **désactivée** | Mesurée sur le vrai modèle : texte 1,8× et images 1,5× plus rapides, mais la similarité cosinus texte avec la version normale tombe à 0,82 et seuls 57,5 % des 5 premiers résultats de recherche restent identiques. Les seuils calibrés ne tiennent plus. |
| Recommandations ML collaboratives | Non fait | Le filtrage collaboratif exige beaucoup d'utilisateurs actifs. Avec peu de comptes, il recommanderait au hasard. |
| Amazon / Shopify, liens affiliés | Non fait | Nécessite des comptes partenaires approuvés et des clés. Leurs conditions interdisent le scraping. |
| Abonnement premium, notifications e-mail/SMS | Non fait | Nécessite Stripe et un fournisseur e-mail/SMS. Les notifications **dans l'application** existent via le WebSocket. |
| Application mobile React Native | Non fait | L'interface web est responsive (testée à 390 px) avec caméra et thème sombre. Une application native serait un projet séparé. |
| Vision temps réel (vidéo) | Non fait | La capture photo par caméra existe déjà. L'analyse image par image en continu serait coûteuse sur CPU. |

**Limites actuelles :**
- **Prix** : seuls 62 produits du catalogue réel ont un prix. Les filtres de prix s'appliquent donc à ce sous-ensemble.
- **Recherche sémantique** : elle est meilleure en anglais, car CLIP a été entraîné principalement sur des textes anglais.
- **Métriques techniques** : elles sont propres à chaque processus et repartent à zéro au redémarrage. En multi-processus, agrégez-les avec Prometheus.
- **Photos importées** : elles sont servies à des adresses non devinables (identifiants aléatoires de 48 bits), mais sans contrôle d'accès.
- **Comptes** : il n'y a pas encore de réinitialisation de mot de passe par e-mail (il faudrait un service d'envoi).
- **Licence** : aucun fichier de licence n'est inclus dans le projet. Les images du catalogue restent soumises aux licences de leurs sources.
