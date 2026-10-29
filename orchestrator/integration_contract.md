# Contrat d'intégration DressMe : `wardrobe_items`

Version 1 · 29/10/2026 · pour les modules appelés par l'orchestrateur (`orchestrator/`, port 8070).

## Principe

1. L'orchestrateur identifie l'utilisateur (jeton Supabase vérifié par BO1 `GET /api/me`).
2. Il lit **sa** garde-robe par BO1 `GET /api/items`, avec son jeton.
3. Il envoie cette garde-robe au module dans le champ **`wardrobe_items`** de la requête.

Le module **ne lit ni Supabase ni BO1** et n'a pas besoin du jeton de l'utilisateur (sauf Avatar, voir plus bas).
Il ne garde pas sa propre copie des vêtements : la garde-robe reçue fait foi pour la requête.

## Format de `wardrobe_items`

Une liste (0 à 500 éléments) de vêtements. Chaque vêtement reprend une ligne de la table BO1 `items`, réduite aux
champs ci-dessous : **ni `user_id`, ni champs internes** (`detection`, `predicted`, `confidence`,
`field_confidence`, `colors`, `zone`, `enrichment_source`). Les champs absents dans BO1 sont envoyés à `null` ;
les listes vides sont `[]`.

| Champ | Type | Peut être null | Valeurs / remarque |
|---|---|---|---|
| `id` | string (UUID) | non | identifiant BO1, stable : à renvoyer dans les réponses pour désigner un vêtement |
| `name` | string | non | ex. « Navy Blazer » |
| `category` | string | non | classe du détecteur BO1 : `top`, `sweater`, `vest`, `jacket`, `pants`, `shorts`, `skirt`, `dress`, `shoe`, `bag`, `belt`, `hat`, `glasses`, `scarf`, `watch`, `glove`, `headband`, `sock`, `tights`, `umbrella` |
| `category_group` | string | non | `Tops`, `Bottoms`, `Dresses`, `Outerwear`, `Shoes`, `Bags`, `Accessories` |
| `subcategory` | string | oui | texte libre, ex. « single-breasted blazer » |
| `color_name` | string | oui | ex. `black`, `navy`, `light blue`, `chocolate` |
| `color_hex` | string | oui | ex. `#1f2a4d` |
| `color_family` | string | oui | `neutral`, `earth`, `warm`, `cool`, `pastel`, `bright`, `metallic`, `multicolor` |
| `pattern` | string | oui | ex. `solid`, `striped`, `plaid` |
| `material` | string | oui | ex. `cotton`, `wool blend` |
| `seasons` | string[] | non (`[]`) | parmi `spring`, `summer`, `autumn`, `winter` |
| `style` | string | oui | un des 10 styles BO1 : `casual`, `sporty`, `streetwear`, `bohemian`, `classic`, `minimalist`, `romantic`, `business`, `elegant`, `formal` |
| `occasions` | string[] | non (`[]`) | ex. `work`, `everyday`, `party`, `ceremony` |
| `formality` | integer 1–5 | oui | 1 très décontracté, 5 très habillé |
| `warmth` | integer 1–5 | oui | 1 très léger, 5 très chaud |
| `description` | string | oui | |
| `tags` | string[] | non (`[]`) | |
| `needs_review` | boolean | non | `true` : détection incertaine, à prendre avec prudence |
| `status` | string | oui | `auto`, `review`, `confirmed` |
| `image_url` | string (URL) | oui | photo d'origine |
| `cutout_url` | string (URL) | oui | vêtement détouré (PNG) |
| `created_at` | string (ISO 8601) | oui | date d'ajout |

### Exemple (3 vêtements)

```json
[
  {"id": "a1000000-0000-4000-8000-000000000002", "name": "Light Blue Shirt", "category": "top",
   "category_group": "Tops", "subcategory": "long-sleeve button-up shirt", "color_name": "light blue",
   "color_hex": "#9cc3e6", "color_family": "pastel", "pattern": "solid", "material": "cotton",
   "seasons": ["spring", "autumn"], "style": "classic", "occasions": ["work", "everyday"], "formality": 3,
   "warmth": 2, "description": "A crisp button-up shirt.", "tags": ["shirt"], "needs_review": false,
   "status": "auto", "image_url": "http://localhost:8000/files/local/a1000000-0000-4000-8000-000000000002/original.jpg",
   "cutout_url": "http://localhost:8000/files/local/a1000000-0000-4000-8000-000000000002/cutout.png",
   "created_at": "2026-10-16T09:05:59+00:00"},
  {"id": "a1000000-0000-4000-8000-000000000004", "name": "Navy Blazer", "category": "jacket",
   "category_group": "Outerwear", "subcategory": "single-breasted blazer", "color_name": "navy",
   "color_hex": "#1f2a4d", "color_family": "neutral", "pattern": "solid", "material": "wool blend",
   "seasons": ["spring", "autumn"], "style": "business", "occasions": ["work", "ceremony"], "formality": 4,
   "warmth": 3, "description": "A tailored navy blazer.", "tags": ["blazer"], "needs_review": false,
   "status": "auto", "image_url": "http://localhost:8000/files/local/a1000000-0000-4000-8000-000000000004/original.jpg",
   "cutout_url": "http://localhost:8000/files/local/a1000000-0000-4000-8000-000000000004/cutout.png",
   "created_at": "2026-10-16T09:06:00+00:00"},
  {"id": "a1000000-0000-4000-8000-000000000008", "name": "Black Skirt", "category": "skirt",
   "category_group": "Bottoms", "subcategory": "a-line midi skirt", "color_name": "black",
   "color_hex": "#1c1c1c", "color_family": "neutral", "pattern": "solid", "material": "polyester",
   "seasons": ["spring", "summer", "autumn"], "style": "elegant", "occasions": ["work", "party"], "formality": 3,
   "warmth": 2, "description": "A flowing midi skirt.", "tags": ["skirt"], "needs_review": false,
   "status": "auto", "image_url": "http://localhost:8000/files/local/a1000000-0000-4000-8000-000000000008/original.jpg",
   "cutout_url": "http://localhost:8000/files/local/a1000000-0000-4000-8000-000000000008/cutout.png",
   "created_at": "2026-10-16T09:05:15+00:00"}
]
```

Vêtements issus de la garde-robe de test de BO4 (`backend/tests/fixtures/bo1_items_sample.json`), passés par la
fonction de l'orchestrateur `contract_item()` ; les dates sont des exemples.

## Règles communes

| Règle | Détail |
|---|---|
| Champs communs de la requête | `wardrobe_items` (liste ci-dessus) et `user_id` (string opaque : identifiant BO1 de l'utilisateur, `local` en mode démo), à utiliser pour la mémoire par utilisateur (retours, sessions) |
| Santé | `GET` sur une route de santé (`/health` ou `/api/health`) qui répond 200 en moins de 3 s ; l'orchestrateur la sonde avant chaque appel |
| Réponse | JSON ; en cas d'erreur, code 4xx/5xx et `{"detail": "message lisible"}` (format FastAPI) |
| Jeton | non transmis par défaut ; un module n'en a pas besoin pour lire la garde-robe |
| Vêtements | désigner un vêtement par son `id` BO1 ; ne pas réécrire la garde-robe |
| Délai | répondre dans le délai de `services.yaml` (30 à 120 s selon le module) |
| Compatibilité | accepter des champs supplémentaires dans `wardrobe_items` sans échouer (le contrat peut s'enrichir) |

## Endpoints attendus par module

Les endpoints partent des fonctions qui existent déjà dans chaque branche ; ce qui manque est signalé.

### Smart Purchasing (`smart_purchasing/`, RemiNOmi) : à créer

Aujourd'hui : ligne de commande (`inference.py`), garde-robe lue dans `wardrobe.csv`. À ajouter : une petite API
FastAPI **à côté** de `inference.py`, qui convertit `wardrobe_items` en objets `Garment` (`schemas.py`), les place
dans `DressMeInferenceEngine.wardrobe` à la place du CSV, puis appelle la méthode existante `evaluate()`.

| | |
|---|---|
| Port | **8050** |
| Santé | `GET /health` |
| Endpoint | `POST /api/purchase/evaluate` |
| Requête | `{"wardrobe_items": [...], "user_id": "…", "prompt": "Should I buy this for work?", "candidate": {"image_url": "https://…/coat.jpg", "price": 80.0, "budget": 60.0}}` (`image_url` obligatoire ; `price` et `budget` peuvent être null) |
| Réponse | le dictionnaire renvoyé aujourd'hui par `evaluate()` : `status`, `user_query`, `candidate_item` {`image_source`, `detected_category`, `detected_color`, `inferred_occasion`, `inferred_style`, `price`, `budget`}, `tool_evidence` {`redundancy_score`, `closest_wardrobe_match`, `compatible_outfits_count`, `matching_wardrobe_item_ids`, `matching_outfits`, `wardrobe_gap_score`, `xgboost_prediction`, `xgboost_confidence`, `deterministic_score`, `budget_penalty`}, `agent_verdict` {`decision`, `score`, `matching_item_ids`, `reasons`, `uncertainties`} ; `matching_*_ids` = `id` BO1 |
| Conversion | `category` BO1 → leur `item_type` (mots-clés de `subcategory`), `style` → liste (`smart_casual` → `["smart_casual", "formal"]`, comme `load_wardrobe_from_csv`), `seasons` vides → les 4 saisons, `formality`, `warmth` repris |

### HelpMePack (`backend/main.py` + `packing_backend/`, Mariam Ben Abdallah) : à étendre

Aujourd'hui : `POST /api/trips` existe ; la garde-robe vient du CSV synthétique (`SyntheticWardrobeProvider`).
`TripAgent(wardrobe_provider=…)` accepte déjà un autre fournisseur : il suffit d'en construire un depuis
`wardrobe_items` (conversion vers `REQUIRED_WARDROBE_COLUMNS` de `trip_agent/wardrobe.py` et matrice de
compatibilité générée, car l'optimiseur ignore les paires absentes).

| | |
|---|---|
| Port | **8020** |
| Santé | `GET /api/health` (existe) |
| Endpoint | `POST /api/trips` (existe) ; suites : `POST /api/trips/{session_id}/messages` (existe, garde-robe de la session conservée) |
| Requête | `CreateTripRequest` actuel + deux champs facultatifs : `{"mode": "text", "text": "3 days in Rome, business", "wardrobe_items": [...], "user_id": "…"}` (le modèle est en `extra="forbid"` : les deux champs doivent y être déclarés) |
| Réponse | inchangée (`_response_payload`) : `message`, `status`, `trip_details`, `weather_summary`, `daily_requirements`, `capsule`, `checklist`, `missing_info`, `suggestions`, `errors`, `session_id`, `weather`, `optimization_status`, `optimization_runs`, `clarification_question` |
| Conversion | `category` → `top`/`bottom`/`dress`/`outerwear`/`shoes`/`accessory` ; `warmth` → `warmth_level`, `formality` → `formality_level` ; `water_resistance`, `weight_g`, `versatility` estimés (BO1 ne les mesure pas) |

### BO3 Wardrobe Gaps (`DressMe UI Blueprint/backend/`, mouhamed mahmoud) : à étendre

Aujourd'hui : `GET /api/bo3/gaps?goal=…` ; la garde-robe vient de Supabase (clé service, `WARDROBE_USER_ID` fixe).
La fonction existante `to_bo3_item(row)` convertit déjà une ligne `items` : elle s'applique telle quelle à chaque
élément de `wardrobe_items`.

| | |
|---|---|
| Port | **8030** |
| Santé | `GET /api/health` (existe) |
| Endpoint | `POST /api/bo3/gaps` (nouveau ; le `GET` reste pour l'interface actuelle) ; facultatif : `POST /api/bo3/chat` avec les mêmes champs en plus |
| Requête | `{"goal": "winter_work", "wardrobe_items": [...], "user_id": "…"}` (`goal` parmi `GET /api/bo3/goals`) |
| Réponse | la sortie actuelle de `GapAgentTools.rank_gaps()` : `goal`, `goal_label`, `season`, `ranker_model`, `ranker_trained_on`, `ranked_gaps` [{`rank`, `candidate_id`, `name`, `priority`, `ranking_score`, `owned_count`, `required_count`, `coverage_deficit`, `matched_items`, …}], `covered` ; ou `{goal, ranked_gaps: [], covered, note}` si rien ne manque |
| Mémoire | `user_id` remplace l'utilisateur fixe `USER_ID = "demo_user"` pour les retours et le réentraînement |

### Avatar / Try-on (`backend/main.py` de la branche `avatar/try1`, Mariam Ben Abdallah) : existe déjà

`POST /api/avatar/generate` accepte déjà `wardrobe_items` (modèle `WardrobeItemInput`). Exception au principe :
il **exige le jeton** (`current_user`), car il enregistre l'avatar dans `user_avatars` ; l'entrée de l'orchestrateur
devra donc avoir `forward_token: true`.

| | |
|---|---|
| Port | **8001** |
| Santé | `GET /api/health` (existe) |
| Endpoint | `POST /api/avatar/generate` (existe) |
| Requête | `{"targets": {…}, "details": {…}, "outfit": [...], "wardrobe_item_ids": ["<id BO1>", …], "wardrobe_items": [WardrobeItemInput…], "height_cm": 168}` ; `WardrobeItemInput` depuis le contrat : `wardrobe_item_id` = `id`, `label` = `name`, `color_hex`, `category`, `category_group`, `subcategory`, `material`, `formality`, `cutout_url` (+ `template`, `slot`, `mesh_url`, `mesh_version` propres à l'avatar) |
| Réponse | `GenerateResponse` : `jobId`, `url`, `params`, `details`, `outfit`, `bytes`, `elapsedSeconds`, `metrics`, `items`, `saved`, `savedAt`, `saveError` |
| Remarque | pas d'entrée dans `services.yaml` pour l'instant : le résultat (modèle 3D) s'affiche dans la page d'essayage, pas dans une conversation |

## Côté orchestrateur

Chaque module a une entrée dans la section `modules` de `orchestrator/services.yaml` (URL, santé, route, modèle de
requête avec `$wardrobe_items`, mots-clés, champs à afficher). Les entrées `smart_purchasing`, `helpmepack` et `bo3`
sont livrées **désactivées** : l'orchestrateur répond « pas encore branché » sans rien appeler. Quand l'endpoint du
module existe, passer `enabled: true` ; s'il ne répond pas, l'orchestrateur le dit sans appeler le module.
