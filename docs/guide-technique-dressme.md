# DressMe — guide technique et démarrage complet

Date de référence : 5 novembre 2026

Ce document décrit l'architecture réellement présente dans le dépôt, les
fonctionnalités, les flux de données, les agents LangGraph et les commandes
Windows pour lancer l'ensemble de la plateforme.

## 1. Vue rapide

DressMe est une plateforme de garde-robe intelligente composée de plusieurs
services Python et d'une interface React/Vite.

Le chemin recommandé est :

```text
Navigateur
   ↓
DressMe UI Blueprint (Vite :8443)
   ↓ proxy /api
BO1 FastAPI (:8000)
   ├── stockage garde-robe / Supabase ou local
   ├── détection YOLO + classification GPT
   ├── AI Stylist
   ├── Outfit Builder LangGraph
   ├── Wardrobe Agent LangGraph
   ├── Similar Agent LangGraph
   └── Orchestrateur BO1 LangGraph

Services complémentaires :
BO3 (:8001)       → Wardrobe Gaps
RAG (:8010)       → connaissances mode et sources
HelpMePack (:8020)→ valise et optimisation OR-Tools
Purchase (:8040)  → analyse achat / redondance
Stylist BO4 (:8061)→ stylist LangGraph séparé avec Ollama
Orchestrator (:8070)→ orchestrateur multi-services séparé
```

Le script `start_all.ps1` lance les services backend, mais pas le frontend
Vite. Le frontend canonique doit être lancé dans un terminal séparé.

## 2. Dépôt et responsabilités

| Dossier | Responsabilité |
|---|---|
| `backend/` | BO1 : API principale, garde-robe, vision, agents principaux |
| `DressMe UI Blueprint/` | frontend React canonique |
| `DressMe UI Blueprint/backend/` | BO3 Wardrobe Gaps |
| `rag_backend/` | API RAG de connaissances mode |
| `packing_backend/` | Trip Agent et optimisation de valise |
| `purchase-redundancy-ai/` | analyse d'achat et diagnostic de redondance |
| `bo4/` | Stylist LangGraph historique/expérimental avec Ollama |
| `orchestrator/` | orchestrateur multi-services indépendant |
| `agent_kit/` | boucle commune d'appel d'outils |
| `a2a_protocol/` | communication Agent-to-Agent entre services |
| `docs/` | documentation et schémas |

Le frontend canonique est `DressMe UI Blueprint`. Les dossiers `frontend/` et
`purchase-redundancy-ai/frontend/` sont des applications secondaires ou de
migration et ne constituent pas le chemin principal.

## 3. Architecture des données

### Mode local

- BO1 utilise `backend/local_data/`.
- L'utilisateur est généralement `local`.
- L'authentification Supabase est désactivée.
- Les services peuvent fonctionner sans compte utilisateur.

### Mode production

- Supabase Auth fournit le JWT.
- Supabase Postgres stocke les vêtements et corrections.
- Supabase Storage stocke les images.
- Chaque requête est limitée au `user_id`.
- La clé `SUPABASE_SERVICE_ROLE_KEY` reste côté serveur uniquement.
- Le frontend ne reçoit que `SUPABASE_ANON_KEY`.

### Mémoire conversationnelle

L'orchestrateur BO1 persiste les checkpoints LangGraph dans :

```text
backend/data/orchestrator_checkpoints.sqlite
```

Variable de configuration :

```text
ORCHESTRATOR_CHECKPOINT_DB
```

La clé de thread est construite comme :

```text
<user_id>:<thread_id>
```

Le token d'autorisation n'est pas stocké dans l'état checkpointé. Il est
transmis au graphe via la configuration runtime LangGraph.

Attention : HelpMePack conserve actuellement ses sessions en mémoire du
processus. Un redémarrage du service efface ses sessions de voyage.

## 4. Fonctionnalités utilisateur

### 4.1 Ajouter un vêtement

Flux :

```text
photo
  → YOLO11 segmentation
  → masque du vêtement
  → couleurs mesurées sur les pixels
  → GPT-4 / modèle configuré
  → validation des champs
  → stockage image + vêtement
```

Le vêtement contient notamment :

- catégorie ;
- groupe de catégorie ;
- couleur et famille de couleur ;
- matière ;
- motif ;
- saison ;
- occasion ;
- style ;
- formalité ;
- chaleur ;
- confiance ;
- indicateur `needs_review`.

Si le LLM échoue, BO1 utilise un enrichissement de secours basé sur les règles.

### 4.2 Ma garde-robe

La page utilise BO1 pour :

- lister les vêtements ;
- filtrer ;
- corriger ;
- supprimer ;
- afficher les statistiques ;
- afficher les éléments à vérifier ;
- afficher la garde-robe 3D.

Les modifications sensibles passent par une validation serveur.

### 4.3 AI Stylist BO1

Endpoint principal :

```text
POST /api/agent/search
```

L'agent utilise une boucle d'appels d'outils, pas un graphe LangGraph complet.

Outils principaux :

- recherche dans la garde-robe ;
- météo ;
- conseils RAG ;
- récupération de pièces réelles.

Règle importante : l'agent doit consulter la garde-robe avant de citer un
vêtement. Les réponses affichent les sources RAG réellement utilisées.

### 4.4 Outfit Builder

Endpoint :

```text
POST /api/outfits/agent
```

Graphe :

```text
START
 → weather
 → closet
 → knowledge
 → compose
 → validate
       ├── erreurs et tentative restante → compose
       └── valide → END
```

Le LLM propose les tenues, mais du code vérifie :

- les identifiants réels ;
- la présence d'un haut et d'un bas, ou d'une robe ;
- les chaussures ;
- l'absence de doublons de rôle ;
- l'outerwear par temps froid ou pluvieux.

Une erreur LLM est maintenant exposée explicitement au frontend avec HTTP 503.

### 4.5 Wardrobe Agent

Endpoint :

```text
POST /api/wardrobe/agent
```

Graphe :

```text
START → gate
          ├── apply
          ├── cancel
          └── assist
```

Une correction suit toujours ce protocole :

```text
recherche → proposition → confirmation explicite → écriture
```

Le LLM ne possède pas d'outil d'écriture directe. Une réponse « oui » est
nécessaire pour appliquer la modification.

### 4.6 Find Similar

Endpoint :

```text
POST /api/similar/agent
```

Le système compare les pièces détectées dans une image à la vraie garde-robe.
Chaque pièce reçoit l'un des statuts :

- `owned` ;
- `close` ;
- `missing`.

Le contrôle final est déterministe et vérifie que l'identifiant cité existe.

### 4.7 Live Scan et doublons

Le scan caméra :

```text
détection → sauvegarde → recherche de similarité → décision de doublon
```

L'agent anti-doublon ne lit pas directement la base. Il passe par le service
Wardrobe Agent.

### 4.8 Wardrobe Gaps BO3

Service :

```text
http://127.0.0.1:8001
```

Fonctions :

- objectifs de garde-robe ;
- couverture ;
- pièces manquantes ;
- classement des gaps ;
- plan d'achat ;
- photos de boutiques ;
- feedback et apprentissage.

Le BO3 possède ses propres routes `/api/bo3/...` et sa propre logique d'agent.

### 4.9 Help Me Pack

Service :

```text
http://127.0.0.1:8020
```

Le Trip Agent combine :

- extraction de détails ;
- météo ;
- garde-robe ;
- exigences d'activités ;
- optimisation OR-Tools CP-SAT ;
- checklist ;
- alternatives en cas d'infaisabilité.

Les contraintes ne sont pas silencieusement relâchées. Si aucune solution
n'existe, l'agent retourne un état `infeasible` et propose des alternatives.

### 4.10 Purchase Redundancy

Service :

```text
http://127.0.0.1:8040
```

Fonctions principales :

- analyse d'un achat ;
- comparaison avec la garde-robe ;
- redondance ;
- budget ;
- score ;
- diagnostic global ;
- actions approuvables.

Ce service possède son propre backend et éventuellement son propre frontend.
Il n'est pas le frontend canonique DressMe.

## 5. LangGraph et agents

### 5.1 Boucle commune

[agent_kit/tool_loop.py](../agent_kit/tool_loop.py) fournit :

```text
llm → tools → llm
          ↘ nudge → llm
          ↘ finish → END
```

La boucle limite le nombre de tours et distingue :

- `answer` ;
- `error` ;
- `exhausted`.

### 5.2 Orchestrateur BO1

Le graphe route une demande vers :

- `stylist` ;
- `wardrobe` ;
- `outfit` ;
- `trip` ;
- `gap` ;
- `redirect` ;
- `clarify`.

Chaque branche revient vers `respond`, qui ajoute le tour à l'historique.
Les checkpoints SQLite permettent de continuer une conversation après un
redémarrage.

### 5.3 Orchestrateur indépendant

`orchestrator/graph.py` est une seconde implémentation plus générique avec :

- services déclarés dans `services.yaml` ;
- modules externes ;
- routage `route_intent` ;
- trace ;
- historique Supabase ;
- SQLite checkpoints.

Il faut éviter de mélanger les deux orchestrateurs dans une même démonstration.
Le chemin BO1 utilise `backend/app/orchestrator_agent.py`; le service séparé
utilise le port 8070.

## 6. Commandes d'installation Windows

Ouvrir PowerShell à la racine du dépôt :

```powershell
cd "C:\Users\maria\Desktop\5eme esprit\Dressme"
```

### 6.1 Préparer les environnements Python

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

BO1 :

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
cd ..
```

BO4 :

```powershell
cd bo4
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
cd ..
```

Orchestrateur séparé :

```powershell
cd orchestrator
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
cd ..
```

Purchase Redundancy :

```powershell
cd purchase-redundancy-ai\backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
cd ..\..
```

### 6.2 Préparer les frontends

Frontend canonique :

```powershell
corepack enable
pnpm --dir "DressMe UI Blueprint" install
```

Frontend historique, uniquement si nécessaire :

```powershell
pnpm --dir frontend install
```

Frontend Purchase Redundancy, optionnel :

```powershell
pnpm --dir "purchase-redundancy-ai\frontend" install
```

### 6.3 Préparer Ollama

Installer Ollama pour Windows, puis :

```powershell
ollama pull qwen2.5:3b
ollama serve
```

Laisser cette fenêtre ouverte si `start_all.ps1` ne trouve pas Ollama.

### 6.4 Préparer l'environnement

```powershell
Copy-Item .env.example .env
notepad .env
```

À renseigner selon le mode :

- `OPENAI_API_KEY` pour les agents GPT ;
- `SUPABASE_URL` ;
- `SUPABASE_SERVICE_ROLE_KEY` uniquement côté serveur ;
- `SUPABASE_ANON_KEY` pour le frontend ;
- `RAG_API_KEY` si l'API RAG est protégée ;
- `FAL_KEY` ou `WAVESPEED_API_KEY` pour l'avatar.

Ne jamais mettre `SUPABASE_SERVICE_ROLE_KEY`, `OPENAI_API_KEY` ou une clé RAG
secrète dans un fichier frontend.

## 7. Démarrage recommandé complet

### Terminal 1 — tous les backends

```powershell
cd "C:\Users\maria\Desktop\5eme esprit\Dressme"
.\start_all.ps1
```

Ce script démarre et vérifie :

| Service | Port | Santé |
|---|---:|---|
| BO1 | 8000 | `/api/health` |
| BO3 | 8001 | `/api/health` |
| RAG | 8010 | `/health` |
| HelpMePack | 8020 | `/api/health` |
| Purchase | 8040 | `/health` |
| Stylist BO4 | 8061 | `/api/graph` |
| Orchestrateur séparé | 8070 | `/api/config` |
| Ollama | 11434 | `/api/version` |

### Terminal 2 — frontend canonique

```powershell
cd "C:\Users\maria\Desktop\5eme esprit\Dressme"
$env:BACKEND_URL = "http://127.0.0.1:8000"
pnpm --dir "DressMe UI Blueprint" dev --host 127.0.0.1 --port 8443
```

Ouvrir :

```text
http://127.0.0.1:8443
```

### Arrêt

Dans le terminal de `start_all.ps1` :

```powershell
.\start_all.ps1 -Stop
```

Arrêter le frontend avec `Ctrl+C`.

## 8. Démarrage séparé pour le développement

BO1 uniquement :

```powershell
.\start_bo1.ps1
```

BO3 uniquement :

```powershell
.\start_bo3.ps1
```

RAG uniquement :

```powershell
.\start_rag.ps1
```

HelpMePack uniquement :

```powershell
.\start_packing.ps1
```

Stylist BO4 :

```powershell
cd bo4\backend
.\.venv\Scripts\python.exe stylist_web.py --port 8061 --require-auth --bo1-url http://127.0.0.1:8000
```

Orchestrateur indépendant :

```powershell
cd orchestrator
.\.venv\Scripts\python.exe app.py --port 8070
```

Purchase Redundancy :

```powershell
cd purchase-redundancy-ai\backend
$env:API_PORT = "8040"
$env:API_HOST = "127.0.0.1"
.\.venv\Scripts\python.exe main.py
```

## 9. Vérifications rapides

```powershell
Invoke-WebRequest http://127.0.0.1:8000/api/health
Invoke-WebRequest http://127.0.0.1:8001/api/health
Invoke-WebRequest http://127.0.0.1:8010/health
Invoke-WebRequest http://127.0.0.1:8020/api/health
Invoke-WebRequest http://127.0.0.1:8040/health
Invoke-WebRequest http://127.0.0.1:8061/api/graph
Invoke-WebRequest http://127.0.0.1:8070/api/config
```

Documentation OpenAPI :

```text
http://127.0.0.1:8000/docs
http://127.0.0.1:8020/docs
http://127.0.0.1:8040/docs
http://127.0.0.1:8001/docs
```

## 10. Tests et qualité

Tests BO1 :

```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend\tests -q
```

Tests Trip :

```powershell
.\.venv\Scripts\python.exe -m pytest packing_backend\trip_agent\tests -q
```

Tests Stylist BO4 :

```powershell
.\bo4\.venv\Scripts\python.exe -m pytest bo4\backend\tests -q
```

Tests orchestrateur indépendant :

```powershell
.\orchestrator\.venv\Scripts\python.exe -m pytest orchestrator\tests -q
```

Frontend canonique :

```powershell
pnpm --dir "DressMe UI Blueprint" typecheck
pnpm --dir "DressMe UI Blueprint" test
pnpm --dir "DressMe UI Blueprint" build
```

## 11. Points techniques à retenir

1. `start_all.ps1` ne lance pas Vite : il faut un deuxième terminal.
2. BO1 est le service principal du frontend canonique.
3. Le port 8000 est réservé à BO1.
4. Le port 8020 est HelpMePack, pas BO1.
5. BO5 RAG dans `orchestrator/services.yaml` est désactivé pour l'orchestrateur
   indépendant, même si `rag_backend` peut être lancé séparément.
6. Les tokens ne doivent pas être placés dans les états LangGraph persistants.
7. Les checkpoints SQLite doivent être sur un volume persistant en production.
8. HelpMePack perd ses sessions en mémoire après redémarrage.
9. BO4 Stylist et l'AI Stylist BO1 sont deux implémentations différentes.
10. Le frontend canonique est `DressMe UI Blueprint`, pas `frontend/`.
11. Les réponses générées par un LLM doivent être validées par du code avant
    d'être utilisées comme données métier.
12. Les logs et fichiers de checkpoint locaux ne doivent pas être commités.

## 12. Flux de démonstration conseillé

1. Lancer `start_all.ps1`.
2. Lancer le frontend canonique sur `8443`.
3. Ouvrir la page et vérifier l'authentification ou le mode local.
4. Ajouter une photo d'un vêtement.
5. Vérifier la détection et les attributs.
6. Tester AI Stylist.
7. Tester Outfit Builder.
8. Tester une correction via Wardrobe Agent et confirmer avec « oui ».
9. Tester HelpMePack avec un voyage.
10. Tester l'orchestrateur `8070` séparément si nécessaire.
11. Redémarrer BO1 et vérifier que le thread de l'orchestrateur BO1 est repris
    grâce au checkpoint SQLite.
