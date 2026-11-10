# Evaluator Agent

Un agent qui **évalue tous les autres agents de DressMe** en les appelant par leurs endpoints et contrats existants
(A2A `message/send`, REST). Il ne modifie ni n'importe le code d'aucun autre agent.

Principe commun à DressMe : *le LLM rédige, le code vérifie*. L'évaluateur l'applique à lui-même : les contrôles
du **code** décident, le **LLM-juge** (Ollama `qwen2.5:3b`, température 0, JSON) ne note que la pertinence et l'utilité
(1 à 5, justification courte) et **ne peut pas contredire un échec détecté par le code**.

## Agents évalués

| Nom (`--agents`) | Agent | Endpoint | Contrat |
|---|---|---|---|
| `orchestrator_bo1` | Orchestrateur BO1 | `POST :8000/api/assistant/chat` | REST, route choisie |
| `stylist` | AI Stylist | `POST :8000/a2a/stylist` | A2A |
| `wardrobe` | Wardrobe Agent | `POST :8000/a2a/wardrobe` | A2A (`input-required` = modification en attente) |
| `similar` | Similar Agent | `POST :8000/a2a/similar` | A2A |
| `outfit` | Outfit Builder | `POST :8000/a2a/outfit` | A2A |
| `trip` | Trip Agent (Help Me Pack) | `POST :8020/a2a/trip` | A2A |
| `gap` | Gap Agent (BO3) | `POST :8001/a2a/gap` | A2A |
| `purchase` | Purchase Redundancy | via l'orchestrateur `POST :8070/api/chat` (route `purchase`) | REST |
| `bo4` | Stylist BO4 | `POST :8061/api/chat` | REST |
| `orchestrator` | Orchestrateur + RAG | `POST :8070/api/chat` | REST |
| `rag` | RAG BO5 | `POST :8010/ask` (en-tête `X-API-Key`) | REST |

États : `completed`, `input-required`, `failed` (A2A natifs ; déduits de la réponse pour les agents REST).

## Contrôles du code

| Critère | Ce qui est vérifié |
|---|---|
| `contract` | état valide et attendu, réponse non vide, champs obligatoires présents |
| `grounding` | chaque pièce citée existe dans **la** garde-robe de l'utilisatrice (aucun vêtement inventé ni d'une autre utilisatrice) |
| `rules` | tenue = haut + bas ou robe, chaussures, couche en plus s'il fait froid ou s'il pleut ; pas de minijupe ni d'épaules dénudées en business ; Wardrobe : aucune modification sans confirmation (et remise en état après un cas confirmé) ; Trip : pas de contrainte relâchée en silence ; RAG : refus sans source |
| `citations` | chaque `[S#]` correspond à une source réellement renvoyée |
| `routing` | la route de l'orchestrateur est la route attendue |
| `robustness` | un service arrêté donne `failed` proprement, sans HTTP 5xx ni trace d'erreur |
| `performance` | latence de l'appel (90 s pour les agents à LLM, 15 s sinon, réglable par cas) |

Chaque pas de test finit **PASS** (tout passe), **WARN** (le code passe mais le juge note < 3) ou **FAIL** (un contrôle du
code échoue). Taux de réussite = PASS / pas de test.

## Jeu de test

`evaluator/cases/<agent>.yaml` : 5 à 10 cas par agent, en français et en anglais, chacun avec son résultat attendu
(route, état, règles) et un cas « service arrêté » (l'appel part vers un port fermé). Scénarios : entretien, mariage
black tie, pluie, recherche « jupe noire », correction de couleur avec confirmation, voyage, gaps « winter work », achat
d'un blazer, tendances (doit refuser). Format : voir l'en-tête de `evaluator/cases.py`.

## Lancer

Prérequis : les services à évaluer démarrés (`start_all.ps1`), `orchestrator/.env.test` (`TEST_EMAIL`, `TEST_PASSWORD`),
`SUPABASE_URL` et `SUPABASE_ANON_KEY` dans `orchestrator/.env` (ou `--env-file`). Aucun secret n'est affiché ni écrit.

```
python -m evaluator.run --agents all
python -m evaluator.run --agents stylist,outfit
python -m evaluator.run --agents all --no-judge     # contrôles du code seulement
python -m evaluator.run --agents all --seed-shoes   # ajoute 3 paires de chaussures au compte de test, puis les retire
python -m evaluator.run --list
```

La garde-robe e2e du compte de test n'a pas de chaussures : sans `--seed-shoes`, la règle « chaussures » n'est exigée que si
la garde-robe en contient. Rapports : `evaluator/reports/eval-<date>.json` et `.md` (score par agent et par critère,
taux de réussite, latence médiane, liste des échecs avec la raison).

Service HTTP facultatif (port 8090, sans toucher aux autres services) :

```
python -m uvicorn evaluator.api:app --host 127.0.0.1 --port 8090
POST /api/evaluator/run   {"agents": ["stylist", "outfit"], "judge": true}     # Authorization: Bearer <jeton> (sinon : compte de test)
```

## Graphe

`load_cases → call_agents → code_checks → llm_judge → aggregate → report` (LangGraph, `evaluator/evaluator_agent.py`).
L'agent suit le contrat commun : `completed` (rapport produit), `input-required` (agent inconnu, configuration ou service de
référence manquant : il dit quoi fournir), `failed` (erreur interne, sans trace technique).

## Tests

```
python -m pytest evaluator/tests -q
```

Des faux agents prouvent que : un `item_id` inventé échoue, une tenue sans chaussures échoue, une citation `[S9]` absente des
sources échoue, une modification sans confirmation échoue, et que le juge ne peut pas sauver un cas que le code a refusé.
