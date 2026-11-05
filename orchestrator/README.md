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
                      ├─ external  (module de services.yaml + wardrobe_items)          │
                      └─ clarify   (question à l'utilisateur)                          ─┘
```

| Node | Rôle |
|---|---|
| `route_intent` | **règles FR/EN d'abord** (« que porter », « tenue » → stylist ; « est-ce que j'ai », « mes vêtements » → wardrobe ; « acheter », « should I buy », « doublon » → purchase ; « comment porter », « conseil », « pourquoi » → knowledge). Si aucune règle ou plusieurs règles s'appliquent : **qwen2.5:3b** (Ollama, JSON contraint). **Garde-fou** : route hors liste refusée ; quand les règles ont trouvé des indices, le LLM doit choisir parmi eux. Sinon : `clarify`. Salutation seule → `clarify` ; « une autre », « j'aime la 2 » après une tenue → `stylist`. |
| `stylist` | transmet le message au Stylist avec le **même jeton** et le **même thread_id** (le Stylist garde sa propre mémoire). |
| `wardrobe` | répond par des **faits** calculés sur `GET /api/items` : total, répartition, filtre catégorie / couleur (« Jupes (noir) : 1 — … »), vêtements « à vérifier ». `/api/agent/search` n'est pas utilisé : il exige une `OPENAI_API_KEY` côté BO1. |
| `purchase` | repère l'article dans le message (type, couleur, prix), lit la garde-robe BO1 de l'utilisateur, la convertit au format de Purchase Redundancy (`shirts`, `pants`, `dresses`, `shoes`, `outerwear`, `accessories`) et appelle `POST /analyze` avec `wardrobe_items` : l'analyse porte sur **la vraie garde-robe**, pas sur la base « invité » de Purchase Redundancy. Sans BO1, aucun appel. |
| `knowledge` | traduit la question en **anglais** avec qwen (puis glossaire : « col roulé » → turtleneck…), appelle le RAG actif sur `POST /ask`, affiche la réponse telle quelle, **seulement les sources citées**, et **masque** les titres contenant « z-library », « .indb » ou « Slide 1 ». |
| `external` | **module externe générique** (section `modules` de `services.yaml`) : vérifie qu'il est activé puis qu'il répond (`health`), lit la garde-robe BO1 de l'utilisateur, l'envoie au module dans `wardrobe_items` (format : `integration_contract.md`), puis met en forme la réponse (champs, liste, texte). Voir « Modules externes ». |
| `clarify` | propose 4 choix ; la réponse « 1 » à « 4 » relance la question d'origine sur la route choisie. |
| `respond` | réponse finale et historique. |

- **Mémoire** : checkpointer LangGraph par `<user_id>:<thread_id>` ; deux utilisateurs ne partagent jamais un fil.
- **Jeton** : transmis dans la configuration du tour (clé `__bo1_token`, objet `RequestToken` au contenu masqué),
  jamais dans l'état ni dans la trace ; un test le vérifie. Il est envoyé à BO1 et au Stylist, pas à Purchase
  Redundancy (qui a sa propre authentification) ni à BO5.
- **Pannes** : chaque appel a un délai maximum (`services.yaml`) ; un service arrêté donne un message clair
  (« … ne répond pas (URL) … Réessaie quand le service est démarré. »), jamais une erreur 500.
-   Un service de base dont `enabled: false` répond « … n'est pas encore disponible » sans rien appeler.
  Le BO5 RAG est maintenant activé et doit répondre sur `http://127.0.0.1:8010/ask`.
- **Trace** : une ligne par node et par appel (`purchase -> purchase POST /analyze : HTTP 200 en 120 ms`).

## Modules externes

Un module (Smart Purchasing, HelpMePack, BO3…) se branche **sans code** dans l'orchestrateur, par une entrée de la
section `modules` de `services.yaml` :

| Clé | Rôle |
|---|---|
| `enabled` | `false` tant que le module n'expose pas l'endpoint du contrat : la demande reçoit « Le module … n'est pas encore branché » et aucun appel n'est fait |
| `url`, `health`, `method`, `path`, `timeout` | service appelé ; `health` est sondé avant chaque appel (3 s au plus) : s'il ne répond pas, message clair et aucun appel |
| `keywords` | expressions régulières de routage (texte en minuscules, sans accents). Un module désactivé ne prend jamais une demande qu'une autre route sait traiter ; le LLM ne peut choisir qu'un module activé |
| `request` | modèle JSON de la requête ; variables `$wardrobe_items`, `$message`, `$language`, `$user_id`, `$thread_id`, `$first_url`, `$price`, `$budget` |
| `response` | `fields` (étiquette + chemin JSON), `list` (chemin d'une liste + format), `text` (chemins de texte) |
| `forward_token` | `false` par défaut : le module reçoit les données, pas le jeton de l'utilisateur |

`$wardrobe_items` est la garde-robe BO1 de l'utilisateur, lue avec son jeton puis réduite aux champs du contrat
(ni `user_id`, ni champs internes). Si BO1 ne répond pas, le module n'est pas appelé.

`helpmepack` (8020, `POST /api/trips`) et `bo3` (8001, `POST /api/bo3/gaps`) sont branchés. BO3 utilise le
jeton de session transmis par l'orchestrateur et recharge toujours la garde-robe côté serveur. `smart_purchasing`
reste désactivé tant qu'il n'expose pas l'endpoint HTTP du contrat (`8050`, `POST /api/purchase/evaluate`).

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

Puis ouvrir http://127.0.0.1:8070.

**Connexion** : mettre `SUPABASE_URL` et la clé **anon** dans le `.env` de la racine du dépôt (ou dans `orchestrator/.env`, prioritaire ; ignorés par git)
(publique, prévue pour le navigateur ; jamais la clé service_role). La page affiche alors « Se connecter » :
e-mail et mot de passe via supabase-js 2.45.4 (jsDelivr, version figée). Le jeton de session reste en mémoire
de la page (stockage supabase-js en mémoire, `persistSession: false`), est envoyé en `Authorization: Bearer`, et
« Se déconnecter » l'efface. Sans `.env` ou sans connexion : **mode démo** (« Mode démo : garde-robe d'exemple »),
sans jeton.

**Rendu** : les réponses sont affichées en markdown (gras, listes, paragraphes) par `static/markdown.js`, qui
construit le DOM avec `textContent` uniquement : aucun HTML venant d'un service n'est interprété. Pour BO5 RAG,
la réponse reste en anglais (étiquette « Réponse en anglais (base de connaissances anglophone) ») ; les marqueurs
`[S1]`…`[Sn]` et les renvois « FIGURE nn » sont retirés, et les sources citées sont listées sous la réponse.

Services attendus (`services.yaml`, plan des ports d'`INTEGRATION.md`) :

| Service | URL | Lancement |
|---|---|---|
| BO1 | http://127.0.0.1:8000 | `cd backend` puis `uvicorn app.main:app --port 8000` |
| Stylist | http://127.0.0.1:8061 | `cd bo4\backend` puis `python stylist_web.py --port 8061 --bo1-url http://127.0.0.1:8000` |
| Purchase Redundancy | http://127.0.0.1:8040 | `cd purchase-redundancy-ai\backend` puis `$env:API_PORT="8040"; $env:CLIP_ENABLED="False"; python main.py` |
| BO5 | http://127.0.0.1:8010 | `cd rag_backend` puis `uvicorn app:app --port 8010`, et `enabled: true` |
| Ollama | http://127.0.0.1:11434 | modèle `qwen2.5:3b` |

API : `POST /api/chat` `{message, thread_id}` (+ `Authorization: Bearer <jeton>`), `GET /api/graph?visited=…`
(SVG, nodes visités en olive), `GET /` (page).

Tests (services simulés, aucun réseau) :

```powershell
cd orchestrator
.\.venv\Scripts\python.exe -m pytest tests -q        # 101 tests (Node.js requis pour 8 d'entre eux)
```

## Historique des conversations

En mode connecté, chaque tour (question et réponse) est enregistré dans Supabase, tables `chat_threads` et
`chat_messages` (script `docs/chat_history.sql`, à exécuter une fois dans le SQL Editor). L'orchestrateur appelle
Supabase avec la **clé anon et le jeton de l'utilisatrice** : la RLS limite chacune à ses propres lignes ; la clé
`service_role` n'est jamais utilisée. Un échec d'enregistrement ne bloque jamais la réponse (la carte l'indique).

- À la connexion, la page recharge la dernière conversation et liste les conversations passées ; « Nouvelle
  conversation » et « Effacer mon historique » (confirmation dans la page) sont au-dessus du fil.
- À la déconnexion, la page se vide ; rien n'est supprimé en base.
- Le `thread_id` est celui du fil enregistré : il est transmis au Stylist, dont le contexte suit la conversation.
- Mémoire des graphes : `SqliteSaver` dans `orchestrator/data/checkpoints.sqlite` et
  `bo4/data/stylist_checkpoints.sqlite` (ignorés par git ; autres chemins : `ORCHESTRATOR_CHECKPOINT_DB`,
  `STYLIST_CHECKPOINT_DB`), clé `<user_id>:<thread_id>`. Le contexte survit au redémarrage ; le jeton n'y est
  jamais écrit (il passe par la configuration du tour). « Effacer mon historique » efface aussi la mémoire de
  l'orchestrateur pour ces fils.

| Route | Rôle |
|---|---|
| `GET /api/history` | conversations de l'utilisatrice (plus récente d'abord) |
| `GET /api/history/{thread_id}` | messages d'une conversation |
| `DELETE /api/history` | efface toutes ses conversations |

## Tests de bout en bout (compte de test)

`tests_e2e/run_e2e.py` joue des scénarios contre le **vrai** orchestrateur, le vrai Stylist, le vrai BO1 (Supabase) et
le vrai Purchase Redundancy, avec un compte de test dédié, puis la page dans un vrai navigateur (Playwright).

```powershell
.\start_all.ps1                                   # BO1 (8000) et Purchase (8040) doivent répondre
python orchestrator	ests_e2eun_e2e.py --env-file .env      # --no-browser, --unseed, --skip-seed
```

- **Identifiants** : `orchestrator/.env.test` avec `TEST_EMAIL` et `TEST_PASSWORD` (ignoré par git, jamais affiché).
  `SUPABASE_URL` et `SUPABASE_ANON_KEY` viennent de l'environnement, de `--env-file`, de `orchestrator/.env` ou du
  `.env` de la racine. La connexion passe par l'API Auth de Supabase (clé anon) ; le jeton reste en mémoire.
- **Garde-robe de test** (`wardrobe.py`) : BO1 ne crée un vêtement qu'à partir d'une photo détectée, le script écrit donc
  15 pièces sans image dans la table `items` avec le jeton du compte de test (la règle RLS « own items » limite
  l'écriture à ce compte ; aucune clé service_role). Chaque ligne porte le tag `e2e-test` ; `--unseed` les supprime.
- **Piles isolées** : le script démarre ses propres Stylist et orchestrateur (ports 8161/8170, et 8162/8171 pour la pluie),
  sans LLM pour des réponses reproductibles, avec leurs propres fichiers de goûts et de mémoire : vos services et vos
  goûts ne sont pas touchés.
- **Scénarios** : a entretien sans pièce interdite (O3, O4) ; b « j'aime pas » jusqu'à « plus aucune tenue » avec le
  blazer ; c 👎 sur la tenue 2 seulement ; d tenue n° 5 inexistante ; e « top » après une clarification ; f achat puis
  réaction courte ; g historique relu après une nouvelle connexion ; h pluie en météo hors ligne ; i réinitialisation des
  goûts ; n1 à n11 la page (connexion, liste, bouton Effacer éloigné, confirmation cachée, déconnexion, reconnexion,
  course de la réouverture lente). Captures dans `tests_e2e/screenshots/` (ignoré par git, adresse e-mail masquée).
- **À la fin** : conversations et goûts du compte de test remis à zéro.

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
