# Orchestrateur DressMe

Un seul point d'entrée de conversation qui envoie chaque demande au bon service de l'équipe, sans modifier leur
code : tenues (BO4 Stylist), garde-robe (BO1 Wardrobe), avis d'achat (Purchase Redundancy) et conseils de style
(BO5 RAG). Graphe LangGraph, page web au style DressMe, port **8070**.

## Graphe

```
START → route_intent ─┬─ stylist   (BO4 Stylist POST /api/chat)                        ─┐
                      ├─ wardrobe  (BO1 Wardrobe GET /api/items)                       │
                      ├─ purchase  (BO1 Wardrobe + Purchase Redundancy POST /analyze)  ├─→ respond → END
                      ├─ knowledge (traduction Ollama + BO5 RAG POST /ask)             │
                      └─ clarify   (question à l'utilisateur)                          ─┘
```

| Node | Rôle |
|---|---|
| `route_intent` | **règles FR/EN d'abord** (« que porter », « tenue » → stylist ; « est-ce que j'ai », « mes vêtements » → wardrobe ; « acheter », « should I buy », « doublon » → purchase ; « comment porter », « conseil », « pourquoi » → knowledge). Si aucune règle ou plusieurs règles s'appliquent : **qwen2.5:3b** (Ollama, JSON contraint). **Garde-fou** : route hors liste refusée ; quand les règles ont trouvé des indices, le LLM doit choisir parmi eux. Sinon : `clarify`. Salutation seule → `clarify` ; « une autre », « j'aime la 2 » après une tenue → `stylist`. |
| `stylist` | transmet le message au Stylist avec le **même jeton** et le **même thread_id** (le Stylist garde sa propre mémoire). |
| `wardrobe` | répond par des **faits** calculés sur `GET /api/items` : total, répartition, filtre catégorie / couleur (« Jupes (noir) : 1 — … »), vêtements « à vérifier ». `/api/agent/search` n'est pas utilisé : il exige une `OPENAI_API_KEY` côté BO1. |
| `purchase` | repère l'article dans le message (type, couleur, prix), lit la garde-robe BO1 de l'utilisateur, la convertit au format de Purchase Redundancy (`shirts`, `pants`, `dresses`, `shoes`, `outerwear`, `accessories`) et appelle `POST /analyze` avec `wardrobe_items` : l'analyse porte sur **la vraie garde-robe**, pas sur la base « invité » de Purchase Redundancy. Sans BO1, aucun appel. |
| `knowledge` | traduit la question en **anglais** avec qwen (puis glossaire : « col roulé » → turtleneck…), appelle `POST /ask`, affiche la réponse telle quelle, **seulement les sources citées**, et **masque** les titres contenant « z-library », « .indb » ou « Slide 1 » (voir `docs/rag_verification.md`). |
| `clarify` | propose 4 choix ; la réponse « 1 » à « 4 » relance la question d'origine sur la route choisie. |
| `respond` | réponse finale et historique. |

- **Mémoire** : checkpointer LangGraph par `<user_id>:<thread_id>` ; deux utilisateurs ne partagent jamais un fil.
- **Jeton** : transmis dans la configuration du tour (clé `__bo1_token`, objet `RequestToken` au contenu masqué),
  jamais dans l'état ni dans la trace ; un test le vérifie. Il est envoyé à BO1 et au Stylist, pas à Purchase
  Redundancy (qui a sa propre authentification) ni à BO5.
- **Pannes** : chaque appel a un délai maximum (`services.yaml`) ; un service arrêté donne un message clair
  (« … ne répond pas (URL) … Réessaie quand le service est démarré. »), jamais une erreur 500.
- **Trace** : une ligne par node et par appel (`purchase -> purchase POST /analyze : HTTP 200 en 120 ms`).

## Lancement

Python 3.11, dans un venv propre à l'orchestrateur (ou celui du Stylist, qui contient déjà LangGraph et FastAPI) :

```powershell
cd orchestrator
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py                    # port 8070, jeton facultatif
.\.venv\Scripts\python.exe app.py --require-auth     # jeton Supabase obligatoire
.\.venv\Scripts\python.exe app.py --no-llm           # règles seules, sans Ollama
.\.venv\Scripts\python.exe app.py --services autre.yaml
```

Puis ouvrir http://127.0.0.1:8070. Services attendus (`services.yaml`, plan des ports d'`INTEGRATION.md`) :

| Service | URL | Lancement |
|---|---|---|
| BO1 | http://localhost:8000 | `cd backend` puis `uvicorn app.main:app --port 8000` |
| Stylist | http://127.0.0.1:8061 | `cd bo4\backend` puis `python stylist_web.py --port 8061 --bo1-url http://localhost:8000` |
| Purchase Redundancy | http://127.0.0.1:8040 | `cd purchase-redundancy-ai\backend` puis `$env:API_PORT="8040"; $env:CLIP_ENABLED="False"; python main.py` |
| BO5 | http://127.0.0.1:8010 | branche `rag/try1` : `cd rag_backend` puis `uvicorn app:app --port 8010` |
| Ollama | http://localhost:11434 | modèle `qwen2.5:3b` |

API : `POST /api/chat` `{message, thread_id}` (+ `Authorization: Bearer <jeton>`), `GET /api/graph?visited=…`
(SVG, nodes visités en olive), `GET /` (page).

Tests (services simulés, aucun réseau) :

```powershell
cd orchestrator
.\.venv\Scripts\python.exe -m pytest tests -q        # 57 tests
```

## Limites

- **Routage par mots-clés** : une demande sans indice dépend de qwen2.5:3b ; une demande à plusieurs indices est
  tranchée par qwen parmi ces indices, sinon l'utilisateur doit préciser.
- **Article à acheter repéré par règles** (type, couleur, prix) : un article décrit autrement (« ce truc ») n'est pas
  reconnu, et l'orchestrateur le demande. Pas de photo pour l'instant (Purchase Redundancy accepte `image_base64`).
- **Purchase Redundancy** : appelé sans LLM (`use_llm: false`), explication par règles ; ses catégories sont plus
  grossières que celles de BO1 (jupe et pantalon → `pants`).
- **BO5** : qualité mesurée faible pour des garde-robes féminines et réponses en anglais (voir
  `docs/rag_verification.md`) ; `rag/try1` n'est pas encore fusionnée dans `integration`.
- **Garde-robe** : réponses factuelles seulement (pas de recherche sémantique sans clé OpenAI côté BO1).
- **Page web** : pas d'écran de connexion ; en `--require-auth`, le jeton doit venir du front de l'équipe (ou être
  collé dans le champ « Jeton », gardé en mémoire de la page seulement).
