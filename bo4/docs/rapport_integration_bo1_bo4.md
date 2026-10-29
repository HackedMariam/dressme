# Rapport d'intégration BO1 → BO4 → Stylist Agent (LangGraph)

Analyse en lecture seule, réalisée le 2026-10-22.

- **BO1** (vrai BO1, branche `wardrobe`) : `C:\Users\Win11\DressMe-team\backend\app\`. La branche active a été vérifiée avec `git branch` : `* wardrobe`.
- **BO4** : `C:\Users\Win11\DressMe\backend\`

Conventions : les chemins BO1 sont relatifs à `DressMe-team/`, les chemins BO4 à `DressMe/`. « L12-30 » signifie lignes 12 à 30.

---

## PARTIE 1 — BO1 : contrat d'API

### 1. Lancement de BO1

**Commande** (`README.md` L55-63) :

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate                  # macOS/Linux : source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --port 8000
```

La documentation interactive est servie sur `http://localhost:8000/docs` (`README.md` L63).

**Port** : 8000. La valeur vient de la commande README L61 et du défaut `PUBLIC_API_URL` dans `backend/app/config.py` L57. Le CORS par défaut n'autorise que `http://localhost:5173` (`config.py` L56).

**Fichiers `.env` lus** (`config.py` L9-11) : `backend/.env`, puis `DressMe-team/.env` à la racine. **Aucun des deux n'existe** (vérifié avec `ls`). Seul `.env.example` est présent.

**Variables d'environnement** (`config.py` L27-58, `.env.example` L1-24) :

| Variable | Défaut (config.py) | Rôle |
|---|---|---|
| `MODEL_PATH` | `backend/models/dressme_best.pt` (L27-29) | Modèle YOLO11m-seg, 20 classes. Le fichier est présent dans le dépôt. |
| `DETECT_CONF` | 0.25 (L30) | Confiance minimale de détection |
| `REVIEW_THRESHOLD` | 0.60 (L31) | Seuil du badge « Needs review » |
| `IMG_SIZE` | 640 (L32) | |
| `OPENAI_API_KEY` | `""` (L35) | Sans clé : enrichissement par règles, et l'agent répond par un message d'erreur |
| `LLM_MODEL` | `gpt-4o` (L36) | |
| `LLM_SEND_IMAGE` | true (L37) | |
| `LLM_IMAGE_DETAIL` | `low` (L38) | |
| `LLM_TIMEOUT` | 45 (L39) | |
| `SUPABASE_URL` | `""` (L42). `.env.example` L12 la pré-remplit avec `https://gxmvxegwlntqpcardrjq.supabase.co`. | |
| `SUPABASE_SERVICE_ROLE_KEY` | `""` (L43) | |
| `SUPABASE_BUCKET` | `wardrobe` (L44) | |
| `LOCAL_DATA_DIR` | `backend/local_data` (L53) | Stockage local en mode dev |
| `CORS_ORIGINS` | `http://localhost:5173` (L56) | |
| `PUBLIC_API_URL` | `http://localhost:8000` (L57) | Préfixe des URL d'images en mode local |
| `MAX_UPLOAD_MB` | 15 (L58) | |

**Dépendances** (`backend/requirements.txt`) : `ultralytics>=8.3.0, torch, torchvision, fastapi>=0.110, uvicorn[standard], python-multipart, pillow, pillow-heif, numpy, scikit-learn, openai>=1.60, supabase>=2.4, python-dotenv`. `requirements-dev.txt` ajoute `pytest` et `httpx`.

> ⚠️ Lancer BO1 provoque des écritures disque : `get_store()` est appelé à l'import (`main.py` L72), et `LocalStore.__init__` crée `backend/local_data/files/` et `db.json` (`storage.py` L117-123). Au démarrage, le lifespan charge aussi le modèle YOLO, ce qui demande torch et ultralytics (`main.py` L39-48). Ce lancement n'a **pas** été fait ici.

### 2. Authentification (`backend/app/auth.py`)

```python
# auth.py L37-45
def current_user(authorization: str | None = Header(None)) -> User:
    if not config.AUTH_ENABLED:
        return User(id=config.LOCAL_USER_ID)

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Not signed in")
    token = authorization.split(" ", 1)[1].strip()
    ...
    res = _supabase().auth.get_user(token)          # L53
```

- **Token exigé ?** Les routes `GET /api/items` (`main.py` L230) et `GET /api/me` (`main.py` L103) dépendent toutes deux de `Depends(current_user)`. Le token n'est exigé **que si `AUTH_ENABLED`**, c'est-à-dire si `SUPABASE_URL` **et** `SUPABASE_SERVICE_ROLE_KEY` sont remplis (`config.py` L45, L49).
- **Header exact** : `Authorization: Bearer <JWT Supabase Auth>` (`auth.py` L41-43, `README.md` L73). Le JWT est vérifié auprès de Supabase via `auth.get_user(token)`, puis mis en cache 300 s (`auth.py` L16, L47-65).
- **Comment l'obtenir** : par un compte Supabase Auth (email + mot de passe), créé côté frontend avec `VITE_SUPABASE_ANON_KEY` (`README.md` L38, L46, L53). La procédure exacte de récupération du token hors frontend (script, curl) est **NON TROUVÉE** dans le backend.
- **Mode sans authentification / utilisateur de dev** : oui. Si `SUPABASE_SERVICE_ROLE_KEY` est vide, `current_user` renvoie `User(id="local")` sans aucun header (`auth.py` L38-39, `config.py` L47-50). Le README le documente L33-39 : « un seul [utilisateur], pas de connexion ». C'est le cas avec le `.env.example` actuel, où l'URL est remplie mais la clé est vide.

### 3. Handlers (verbatim, `backend/app/main.py`)

**GET /api/taxonomy** (L95-99)

```python
@app.get("/api/taxonomy")
def taxonomy() -> dict:
    return {"classes": MODEL_CLASSES, "class_to_group": CLASS_TO_GROUP, "groups": GROUPS,
            "patterns": PATTERNS, "seasons": SEASONS, "styles": STYLES, "occasions": OCCASIONS,
            "colors": COLOR_NAMES, "color_families": COLOR_FAMILIES}
```

Cette route n'exige pas d'authentification (aucun `Depends(current_user)`).

**GET /api/me** (L102-104)

```python
@app.get("/api/me")
def me(user: User = Depends(current_user)) -> dict:
    return {"id": user.id, "email": user.email}
```

**GET /api/items** (L229-231)

```python
@app.get("/api/items")
def list_items(user: User = Depends(current_user)) -> list[dict]:
    return store.list_items(user.id)
```

**GET /api/items/{item_id}** (L344-346), avec le helper `_get_or_404` (L337-341)

```python
def _get_or_404(user: User, item_id: str) -> dict:
    item = store.get_item(user.id, item_id)
    if not item:
        raise HTTPException(404, "Item not found")
    return item
```

```python
@app.get("/api/items/{item_id}")
def get_item(item_id: str, user: User = Depends(current_user)) -> dict:
    return _get_or_404(user, item_id)
```

**POST /api/agent/search** (L310-318)

```python
class AgentRequest(BaseModel):
    message: str


@app.post("/api/agent/search")
async def agent_search(body: AgentRequest, user: User = Depends(current_user)) -> dict[str, Any]:
    """Ask the AI stylist a free-form question; it searches the real wardrobe before answering."""
    items = store.list_items(user.id)
    return await run_in_threadpool(agent.chat, items, body.message)
```

### 4. Format JSON de GET /api/items

`GET /api/items` renvoie une **liste JSON d'objets vêtement**, du plus récent au plus ancien. En Supabase, le tri vient de `.order("created_at", desc=True)` (`storage.py` L75-76). En local, il vient de l'insertion en tête de liste (`storage.py` L153).

**Filtrage par utilisateur : oui.**
- Supabase : `.eq("user_id", user_id)` (`storage.py` L75).
- Local : `i.get("user_id") == user_id` (`storage.py` L158).
- En mode local, `user_id` vaut toujours `"local"`.

Un objet est construit par `analyze` : `{"id", "user_id", **classify_fields(...)}` (`main.py` L209-210), puis `image_url` et `cutout_url` (L213-214), plus `created_at` à l'insertion (`storage.py` L151-152). Les champs de `classify_fields` sont définis `main.py` L122-151. En Supabase, la ligne contient en plus `position_3d` (`supabase/schema.sql` L50).

| Champ | Type | Source (fichier:ligne) | Valeurs |
|---|---|---|---|
| `id` | str (UUID4) | main.py L209 | |
| `user_id` | str | main.py L210 | `"local"` en dev, UUID Supabase en prod |
| `created_at` | str ISO 8601 | storage.py L152 / schema.sql L12 | |
| `name` | str | main.py L123 | Libre, ex. « Navy Jacket » |
| `category` | str | main.py L124 | `MODEL_CLASSES` (20 classes, §6) |
| `category_group` | str | main.py L125 | `GROUPS` |
| `subcategory` | str \| null | main.py L126 | **Texte libre** (ex. « crew-neck t-shirt »), défaut = category (enricher.py L181, L248) |
| `color_name` | str | main.py L127 | Palette de 33 noms **avec espaces** (colors.py L8-20) |
| `color_hex` | str | main.py L128 | `#rrggbb` mesuré |
| `color_family` | str | main.py L129 | `COLOR_FAMILIES` |
| `colors` | list[{name, hex, share}] | main.py L130 | |
| `pattern` | str | main.py L131 | `PATTERNS` |
| `material` | str | main.py L132 | Libre |
| `seasons` | list[str] | main.py L133 | `SEASONS` |
| `style` | str | main.py L134 | `STYLES` (une seule valeur) |
| `occasions` | list[str] | main.py L135 | `OCCASIONS` |
| `formality` | int 1-5 | main.py L136 | |
| `warmth` | **int 1-5** | main.py L137 | 1 = très léger … 5 = très chaud (enricher.py L55) |
| `description` | str | main.py L138 | |
| `styling_tips` | list[str] | main.py L139 | |
| `tags` | list[str] | main.py L140 | |
| `confidence` | float | main.py L141 | |
| `field_confidence` | dict | main.py L142-144 | |
| `needs_review` | bool | main.py L145 | |
| `status` | str | main.py L146 | `auto` \| `review` \| `confirmed` |
| `zone` | str | main.py L147 | `rail` \| `shelf` \| `floor` |
| `detection` | dict {category, group, confidence, box, area_ratio, colors, alternatives} | main.py L148, detector.py L35-41 | |
| `enrichment_source` | str | main.py L149 | `llm:<model>` ou `rules (...)` |
| `predicted` | dict | main.py L151 | |
| `image_url` | str (URL absolue) | main.py L213 | Local : `{PUBLIC_API_URL}/files/{user}/{id}/original.jpg` (storage.py L143) ; Supabase : URL publique du bucket (storage.py L65) |
| `cutout_url` | str (URL absolue, PNG détouré) | main.py L214 | Même règle, `cutout.png` |

**Exemple déduit du code** : valeurs **illustratives**. Ce n'est pas une donnée réelle (aucune donnée n'a été trouvée, voir §5). L'exemple simule le chemin sans clé OpenAI, donc l'enrichissement par règles `_fallback` (`enricher.py` L203, L239-257).

```json
[
  {
    "id": "3f1c2a9e-7b1d-4e0a-9c1e-2d5b8a6f0c11",
    "created_at": "2026-10-22T15:00:00+00:00",
    "user_id": "local",
    "name": "Navy Jacket",
    "category": "jacket",
    "category_group": "Outerwear",
    "subcategory": "jacket",
    "color_name": "navy",
    "color_hex": "#202b4c",
    "color_family": "neutral",
    "colors": [{"name": "navy", "hex": "#202b4c", "share": 0.81}],
    "pattern": "solid",
    "material": "cotton blend",
    "seasons": ["spring", "autumn"],
    "style": "classic",
    "occasions": ["everyday", "work"],
    "formality": 3,
    "warmth": 3,
    "description": "A navy jacket from your wardrobe.",
    "styling_tips": ["Pair with neutral basics.", "Add one accent accessory."],
    "tags": ["jacket", "navy", "outerwear"],
    "confidence": 0.91,
    "field_confidence": {"category": 0.91, "color": 0.8, "pattern": 0.5, "season": 0.5,
                         "style": 0.5, "occasion": 0.5, "material": 0.3},
    "needs_review": false,
    "status": "auto",
    "zone": "rail",
    "detection": {"category": "jacket", "group": "Outerwear", "confidence": 0.91,
                  "box": [12.0, 30.5, 410.2, 600.0], "area_ratio": 0.42,
                  "colors": [{"name": "navy", "hex": "#202b4c", "share": 0.81}],
                  "alternatives": []},
    "enrichment_source": "rules (no OPENAI_API_KEY set)",
    "predicted": {"category": "jacket", "color_name": "navy", "pattern": "solid",
                  "seasons": ["spring", "autumn"], "style": "classic",
                  "occasions": ["everyday", "work"], "material": "cotton blend"},
    "image_url": "http://localhost:8000/files/local/3f1c2a9e-7b1d-4e0a-9c1e-2d5b8a6f0c11/original.jpg",
    "cutout_url": "http://localhost:8000/files/local/3f1c2a9e-7b1d-4e0a-9c1e-2d5b8a6f0c11/cutout.png"
  }
]
```

### 5. Stockage (`backend/app/storage.py`)

Il existe deux backends, choisis dans `get_store()` (L204-208) :
- **Supabase** (PostgreSQL + Storage) si `USE_SUPABASE`. Table `public.items`, schéma dans `supabase/schema.sql` L9-56 ; images dans le bucket `wardrobe`.
- **Local** : un **fichier JSON** `backend/local_data/db.json` (L120) et les images dans `backend/local_data/files/` (L119), servies sous `/files` (`main.py` L73-74).

Pas de SQLite.

**Fonctions de lecture (verbatim)**

```python
# storage.py L23-27
def _fill_defaults(row: dict) -> dict:
    """Values that can be derived when an older database doesn't store them."""
    if row and not row.get("color_family") and row.get("color_name"):
        row["color_family"] = color_family_of(row["color_name"])
    return row
```

```python
# storage.py L74-82 (SupabaseStore)
    def list_items(self, user_id: str) -> list[dict]:
        rows = (self.db.table("items").select("*").eq("user_id", user_id)
                .order("created_at", desc=True).execute().data)
        return [_fill_defaults(r) for r in rows]

    def get_item(self, user_id: str, item_id: str) -> dict | None:
        rows = (self.db.table("items").select("*").eq("id", item_id).eq("user_id", user_id)
                .limit(1).execute().data)
        return _fill_defaults(rows[0]) if rows else None
```

```python
# storage.py L125-126, L145-146, L157-161 (LocalStore)
    def _load(self) -> dict:
        return json.loads(self.db_path.read_text(encoding="utf-8"))

    def download(self, path: str) -> bytes:
        return self._file(path).read_bytes()

    def list_items(self, user_id: str) -> list[dict]:
        return [i for i in self._load()["items"] if i.get("user_id") == user_id]

    def get_item(self, user_id: str, item_id: str) -> dict | None:
        return next((i for i in self.list_items(user_id) if i["id"] == item_id), None)
```

**Fichier de données existant : NON TROUVÉ.**
- `backend/local_data/` n'existe pas.
- Aucun `db.json` n'a été trouvé, ni dans `DressMe-team`, ni dans `DressMe`.
- Les données Supabase ne sont pas lisibles sans `SUPABASE_SERVICE_ROLE_KEY`.

Il n'y a donc **aucun vêtement réel à montrer**.

### 6. Taxonomie (verbatim, `backend/app/taxonomy.py` L1-42)

```python
"""Fixed vocabularies shared by the detector, the LLM and the frontend."""

# The 20 classes your YOLO11m-seg model was trained on (index -> name).
MODEL_CLASSES = [
    "top", "sweater", "jacket", "vest", "pants", "shorts", "skirt", "dress",
    "glasses", "hat", "headband", "scarf", "glove", "watch", "belt", "sock",
    "tights", "shoe", "bag", "umbrella",
]

# Model class -> wardrobe group (the filter chips in the UI, and the 3D zone).
CLASS_TO_GROUP = {
    "top": "Tops", "sweater": "Tops", "vest": "Tops",
    "jacket": "Outerwear",
    "pants": "Bottoms", "shorts": "Bottoms", "skirt": "Bottoms",
    "dress": "Dresses",
    "shoe": "Shoes",
    "bag": "Bags",
    "glasses": "Accessories", "hat": "Accessories", "headband": "Accessories",
    "scarf": "Accessories", "glove": "Accessories", "watch": "Accessories",
    "belt": "Accessories", "sock": "Accessories", "tights": "Accessories",
    "umbrella": "Accessories",
}

GROUPS = ["Tops", "Bottoms", "Dresses", "Outerwear", "Shoes", "Bags", "Accessories"]

# Where an item goes in the 3D wardrobe.
GROUP_TO_ZONE = {
    "Tops": "rail", "Outerwear": "rail", "Dresses": "rail", "Bottoms": "rail",
    "Bags": "shelf", "Accessories": "shelf", "Shoes": "floor",
}

PATTERNS = ["solid", "striped", "checked", "floral", "polka dot", "animal print",
            "graphic", "printed", "denim", "knit texture", "colorblock", "other"]
SEASONS = ["spring", "summer", "autumn", "winter"]
STYLES = ["casual", "elegant", "formal", "business", "sporty", "streetwear",
          "bohemian", "minimalist", "classic", "romantic"]
OCCASIONS = ["everyday", "work", "party", "date night", "wedding", "ceremony",
             "sport", "travel", "beach", "lounge", "outdoor"]

# Colour classification: a fixed name (same palette as colors.py, so filters stay
# consistent) plus a family used to match outfits.
COLOR_FAMILIES = ["neutral", "earth", "warm", "cool", "pastel", "bright", "metallic", "multicolor"]
```

**Sous-catégories** : aucune liste fermée. `subcategory` est du texte libre produit par GPT-4 (`enricher.py` L43, L181).

**Couleurs** (palette fermée, `backend/app/colors.py` L8-20, exposée par `COLOR_NAMES` L46) :

```python
PALETTE = [
    ("black", "#1c1c1c"), ("charcoal", "#3d3d3d"), ("grey", "#8a8a8a"),
    ("light grey", "#c8c8c8"), ("white", "#f5f5f2"), ("cream", "#efe6d2"),
    ("beige", "#d6bf98"), ("camel", "#b58a57"), ("tan", "#c9a27a"),
    ("brown", "#7a4a2a"), ("chocolate", "#4a2c1d"), ("khaki", "#b5a77a"),
    ("olive", "#6b6b2f"), ("green", "#3f8a4a"), ("forest green", "#24452c"),
    ("mint", "#a8dcc2"), ("teal", "#1f7a7a"), ("navy", "#1f2a4d"),
    ("blue", "#3666b0"), ("denim blue", "#4a6890"), ("light blue", "#9cc3e6"),
    ("purple", "#6a3d8f"), ("lavender", "#bfa8dc"), ("burgundy", "#6e1f2e"),
    ("red", "#c0282d"), ("coral", "#ef7f6a"), ("pink", "#e8a0b4"),
    ("hot pink", "#d63c84"), ("orange", "#e0772a"), ("mustard", "#d1a12c"),
    ("yellow", "#f0d43a"), ("gold", "#c9a94b"), ("silver", "#b8b8bc"),
]
```

**Familles de couleurs** (`backend/app/enricher.py` L216-224). `multicolor` figure dans `COLOR_FAMILIES` mais n'apparaît dans aucune famille de ce mapping.

```python
_FAMILY = {
    "neutral": {"black", "charcoal", "grey", "light grey", "white", "cream", "beige", "navy"},
    "earth": {"camel", "tan", "brown", "chocolate", "khaki", "olive", "forest green"},
    "pastel": {"mint", "light blue", "lavender", "pink"},
    "warm": {"burgundy", "red", "coral", "orange", "mustard", "yellow"},
    "cool": {"green", "teal", "blue", "denim blue", "purple"},
    "bright": {"hot pink"},
    "metallic": {"gold", "silver"},
}
```

**Autres attributs** : `formality` et `warmth` sont des entiers de 1 à 5 (`enricher.py` L54-55, bornés L189-190 ; `schema.sql` L32-33).

### 7. Agent BO1 (`backend/app/agent.py`)

Résumé :
1. **LLM** : OpenAI, modèle `config.LLM_MODEL` (défaut `gpt-4o`), via `client.chat.completions.create` (L102-113). Il n'y a **ni Ollama ni LangChain**.
2. **Entrées** : la liste complète des vêtements de l'utilisateur (`store.list_items`) et un message texte (`main.py` L317-318).
3. L'agent fait du **function calling** avec un unique outil, `search_wardrobe` (L25-53). Ses filtres sont `category`, `category_group`, `color_name`, `season`, `occasion`, `style`, `pattern`, `min_warmth` et `text`.
4. Le filtrage est déterministe et fait en Python (`_matches`, L65-87). Il renvoie au plus 20 résultats par appel (L21, L90-91).
5. La boucle compte au plus 4 tours (L20, L109). Le LLM peut relancer la recherche avec d'autres filtres.
6. Seuls les champs `RESULT_FIELDS` sont renvoyés au LLM (L22-23), donc pas les images.
7. **Sortie** : `{"reply": str, "items": [ {id, name, category, category_group, color_name, pattern, material, seasons, style, occasions, formality, warmth} ]}` (L95, L121).
8. Sans `OPENAI_API_KEY`, l'agent renvoie un message d'erreur et aucune recherche (L99-100).
9. `check_duplicate` (L153-198) réutilise le même outil pour détecter un doublon après un scan caméra. Il renvoie `{"duplicate", "similar_item_id", "note"}`.
10. **Aucune recommandation de tenue** : l'agent ne fait que chercher et décrire des articles existants.

Signatures publiques :

```python
def chat(items: list[dict], message: str) -> dict:                 # L94
def check_duplicate(items: list[dict], candidate: dict) -> dict:   # L153
```

Les helpers privés sont `_matches(item: dict, args: dict) -> bool` (L65) et `_run_search(items: list[dict], args: dict) -> list[dict]` (L90). Les constantes publiques sont `TOOLS` (L25), `SYSTEM` (L55) et `DUPLICATE_SYSTEM` (L140).

---

## PARTIE 2 — BO4 : ce que le moteur attend

### 8. `backend/outfit_engine.py`

**Signatures (verbatim)**

```python
def garment_role(item):                                                                   # L159
def evaluate_outfit(items, occasion, season):                                             # L413
def recommend_outfits(wardrobe, occasion="university", season="autumn", top_k=5, diversify=True):  # L555
```

**Paramètres de `recommend_outfits`** :
- `occasion` ∈ {`university`, `work`, `evening`, `casual`} (L37-42). Toute autre valeur lève `ValueError` (L561-562).
- `season` ∈ {`spring`, `summer`, `autumn`, `winter`} (L44). Toute autre valeur lève `ValueError` (L563-564).

**Sortie** : une liste de dicts `{items, occasion, season, score, color_score, style_score, occasion_score, season_score, explanations}` (L590-595, L457-464). Tous les scores sont sur 100.

**Normalisation appliquée par le moteur** : `normalize(v) = str(v or "unknown").lower().strip()`, avec espaces et `-` remplacés par `_` (L133-134). Une valeur absente devient donc `"unknown"`.

**Champs d'un vêtement lus par le moteur (exhaustif)**

| Champ | Où (outfit_engine.py) | Valeurs acceptées / effet |
|---|---|---|
| `category` | `garment_role` L160, `item_warmth` L243, `season_score` L363, `_label` L301, tie-break L470 | **Rôle** : TOPS `shirt, tshirt, t_shirt, blouse, sweater, hoodie, top` (L7) ; BOTTOMS `trousers, pants, jeans, shorts, skirt` (L8) ; OUTERWEAR `blazer, jacket, coat, cardigan` (L9) ; DRESSES `dress` (L13). Toute autre catégorie a le rôle `None` et le vêtement est **ignoré** (L566-569). La chaleur par catégorie vient de `CATEGORY_WARMTH` (L59-77). `shorts` est traité comme jambes découvertes (L96). |
| `color` | `evaluate_outfit` L414, L433 → `color_score` L172-187 | Chaîne libre en snake_case. Les **neutres** sont définis L15-21 (`black, white, grey, gray, beige, cream, navy_blue, navy, light_grey, dark_grey` + bases) ; les **familles** L23-31 ; les modificateurs `light/dark/other/off` et le suffixe `-ish` L35, L137-142. Une valeur absente ou `unknown` donne un score de 0.60. |
| `style` | `style_score` L191, `occasion_score` L205 | Seules valeurs utiles : `casual`, `smart_casual`, `formal` (L37-42, L198). `unknown` donne 0.60. Toute autre valeur fait baisser les scores style (0.50) et occasion. |
| `id` | Anti-doublon L584-586, tri L483-492, diversité L512 | str ou int. Les identifiants numériques passent avant les textuels (L487-490). |
| `name` | `_label` L301 (explications), tie-break L470 | Libre |
| `warmth` | `item_warmth` L240-242 | **Chaîne** `light` \| `medium` \| `heavy` (L54). Toute autre valeur fait basculer sur l'estimation par catégorie. |
| `warmth_source` | L244-253 | Seules `text_contradictory`, `text_conflict` et `text_partial` ont un effet. Facultatif. |
| `text_warmth_levels` | L245 | Liste ⊂ {light, medium, heavy}. Facultatif. |
| `sleeve_length` | `item_sleeve` L260-261 | `sleeveless` \| `short` \| `three_quarter` \| `long`. Toute autre valeur donne `unknown` (facteur neutre 1.0). |
| `article_id`, `image_path` | Tie-break uniquement, L470, L491 | Facultatifs, aucun effet sur le score |

Le moteur **ne lit pas** `seasons`, `occasions`, `formality`, `pattern`, `material` ni `color_hex`.

### 9. `backend/demo_bo4_web.py`

Les 10 vêtements ne sont **pas écrits en dur**. Ce sont 10 `article_id` H&M, lus dans `data/hm/catalog_products.csv` puis transformés (L24-55) :

```python
# Sélection variée (couleurs, chaleur, manches) pour que la saison change visiblement le classement.
ARTICLE_IDS = (
    "0108775044", "0702784001", "0674310002",   # hauts : débardeur blanc, pull gris, blouse bordeaux
    "0719952001", "0547522002", "0399201042",   # bas : short noir, jupe vert foncé, pantalon gris
    "0635510002", "0633226002",                 # vestes : doudoune noire, blazer gris
    "0801843006", "0713783002",                 # robes : rose sans manches, rouge manches longues
)
...
def build_wardrobe():
    """Même transformation que load_user_wardrobe, à partir du CSV du catalogue."""
    catalog = {r["article_id"]: r for r in read_csv(CATALOG_CSV)}
    wardrobe = []
    for index, article_id in enumerate(ARTICLE_IDS, 1):
        row = catalog[article_id]
        category = normalize_category(row["product_type_name"])
        attributes = extract_attributes(row["prod_name"], row["detail_desc"], category)
        item = {
            "id": str(index), "article_id": article_id, "name": row["prod_name"],
            "category": category, "color": normalize_color(row["colour_group_name"]), "style": "unknown",
            "image_path": row["image_path"],
            "warmth": attributes.warmth, "warmth_source": attributes.warmth_source,
            "warmth_evidence": list(attributes.warmth_evidence),
            "text_warmth_levels": list(attributes.text_warmth_levels),
            "sleeve_length": attributes.sleeve_length, "sleeve_source": attributes.sleeve_source,
        }
        if garment_role(item) is not None and (DATA_HM_DIR / item["image_path"]).is_file():
            wardrobe.append(item)
    return wardrobe


WARDROBE = build_wardrobe()
```

**Appels à `recommend_outfits`** (L89-90) :

```python
    ranked = recommend_outfits(WARDROBE, occasion=occasion, season=season, top_k=1000, diversify=False)
    top3 = recommend_outfits(WARDROBE, occasion=occasion, season=season, top_k=3)
```

**Valeurs effectives** : résultat de `WARDROBE`, obtenu en important le module en lecture seule (`python -B`, sans lancer le serveur). Champs principaux :

| id | article_id | name | category | color | style | warmth (source) | sleeve_length |
|---|---|---|---|---|---|---|---|
| 1 | 0108775044 | Strap top | top | white | unknown | unknown (none) | sleeveless |
| 2 | 0702784001 | American Beauty intarsia | sweater | grey | unknown | unknown (none) | long |
| 3 | 0674310002 | ED Liddy blouse | blouse | dark_red | unknown | unknown (none) | long |
| 4 | 0719952001 | Joaquin shorts | shorts | black | unknown | light (text) | unknown |
| 5 | 0547522002 | Angelina Skirt | skirt | dark_green | unknown | light (text) | unknown |
| 6 | 0399201042 | Shaping Skinny H.W | trousers | dark_grey | unknown | unknown (none) | unknown |
| 7 | 0635510002 | Huffel puffer jacket | jacket | black | unknown | heavy (text) | long |
| 8 | 0633226002 | Zion slim | blazer | dark_grey | unknown | medium (text_and_category) | unknown |
| 9 | 0801843006 | Elva Dress | dress | light_pink | unknown | light (text) | sleeveless |
| 10 | 0713783002 | Mara off shoulder dress | dress | red | unknown | unknown (none) | long |

`image_path` est de la forme `images/010/0108775044.jpg`, relative à `data/hm/`. Les images sont servies par `/img/{article_id}` (L64-69). Le style est **toujours `unknown`**, si bien que le critère occasion est inactif (L101-104).

### 10. Ton essai de BO1 dans `C:\Users\Win11\DressMe`

| Fichier | Rôle |
|---|---|
| `bo1/bo1_pipeline.py` | Détection et segmentation YOLO **DeepFashion2 `models/deepfashion2_yolov8s-seg.pt`** (L17-19), contrôle qualité masque/confiance (L36-100), statut `quality_status` (`accepted`, `suspected_false_detection`, `needs_mask_review`, L410-420), découpe des crops. Script CLI (`argparse`, L449-483). |
| `bo1/enrich_metadata.py` | **FashionCLIP zero-shot** (L7, L668) sur 5 attributs (L27-80) : `subcategory` (16 labels, dont `t_shirt`, `trousers`, `jeans`, `blazer`, `coat`, `cardigan`, `trench_coat`, `wide_leg_trousers`, `vest`… L28-45), `primary_color` (12 labels en snake_case, dont `navy_blue`, `light_blue`, `gray`, L47-60), `sleeve_length` (L62-66), `neckline`, `closure_type`. Il produit aussi une fusion couleur OpenCV (`fuse_color`, L267). |
| `bo1/outputs/<test>/metadata.json` | Sortie : liste d'objets `{item_id, yolo_category, quality_status, crop_path, metadata{subcategory, primary_color, sleeve_length, neckline, closure_type, category}, fusion, color_fusion, review_status, …}`. Exemple : `outputs/test_14/metadata.json`, 3 articles (chemise `light_blue`, etc.). |
| `bo1/*_backup.py`, `*_baseline.py`, `*_experimental.py`, `*_integrated.py`, `evaluate_*.py`, `test_*.py`, `inspect_*.py` | Variantes, évaluations et scripts de test de l'essai |
| `backend/bo1_adapter.py` | `load_wardrobe_from_bo1(json_path)` (L5-42) : lit `metadata.json`, garde `quality_status == "accepted"` et produit `{id, category, color, style:"unknown", image_path, review_status}` pour BO4 |

**Différences avec le vrai BO1**

| Aspect | Ton essai | Vrai BO1 (DressMe-team) |
|---|---|---|
| Détecteur | YOLOv8s-seg DeepFashion2 (classes `long_sleeved_shirt`, `trousers`, `sling_dress`…) | YOLO11m-seg custom `dressme_best.pt`, 20 classes (`top`, `pants`… + accessoires) |
| Attributs | FashionCLIP zero-shot, 5 attributs | GPT-4o, sortie JSON stricte : style, occasions, saisons, warmth, formality, pattern, material… |
| Sous-catégorie | Vocabulaire fermé, **compatible BO4** (`t_shirt`, `jeans`, `blazer`…) | Texte libre |
| Couleur | `primary_color` snake_case (12 labels) | `color_name` avec espaces (33 labels) + `color_hex` + `color_family` |
| Style / saison / chaleur | Absents | Présents |
| Manches | `sleeve_length` présent (long/short/sleeveless) | **Absent** |
| Exposition | Scripts et fichier JSON, sans API | API FastAPI, multi-utilisateur, Supabase ou JSON local |
| Images | Chemin absolu local (`crop_path`) | URL HTTP (`image_url`, `cutout_url`) |

---

## PARTIE 3 — Correspondance

### 11. Tableau de correspondance

| Champ BO4 attendu | Champ BO1 équivalent | Conversion nécessaire | Manquant ? |
|---|---|---|---|
| `id` | `id` (UUID str) | Aucune. Le moteur accepte les ids textuels (outfit_engine L489-490). | Non |
| `name` | `name` | Aucune | Non |
| `category` | `category` (+ `subcategory` libre) | `top`→`top`, `sweater`→`sweater`, `jacket`→`jacket`, `pants`→`pants`, `shorts`, `skirt`, `dress` reconnus tels quels (vérifié par appel de `garment_role`). `vest` donne `None` et le vêtement est **perdu**. Les 12 classes accessoires, chaussures et sacs donnent `None` et sont ignorées. Option : déduire `shirt`, `tshirt`, `blouse`, `jeans`, `blazer`, `coat`, `cardigan`, `hoodie` depuis `subcategory` ou `tags` par mots-clés. | Partiel (granularité) |
| `color` | `color_name` | Renommer le champ. `normalize` gère déjà les espaces (`light grey`→`light_grey`). Mappings utiles : `navy`→OK neutre ; **`charcoal`** n'est pas reconnu comme neutre (→ `dark_grey`) ; `chocolate`→`brown` ; `forest green`→`dark_green` ; `mint`→`light_green` ; `hot pink`→`pink` ; `coral`, `orange`, `teal`, `gold`, `silver` restent seuls dans leur famille. Alternative : utiliser `color_family` de BO1. | Non (conversion) |
| `style` | `style` | Mapping vers {`casual`, `smart_casual`, `formal`} : proposition `casual, sporty, streetwear, bohemian`→`casual` ; `classic, minimalist, elegant, business, romantic`→`smart_casual` ou `formal` (à décider). **Proposition à valider, pas dans le code.** | Non (conversion) |
| `warmth` | `warmth` (int 1-5) | Proposition : 1-2→`light`, 3→`medium`, 4-5→`heavy`. **À valider.** Sinon la valeur est ignorée (L240-243) et le moteur estime d'après la catégorie. | Non (conversion) |
| `warmth_source` | — | Ne pas fournir (facultatif) | Oui (sans effet) |
| `text_warmth_levels` | — | Ne pas fournir (facultatif) | Oui (sans effet) |
| `sleeve_length` | — | Éventuellement depuis `subcategory`, `description` ou `tags` (`extract_attributes` de BO4 sur `name` + `description` ?) | **Oui** |
| `image_path` | `image_url` / `cutout_url` | URL absolue au lieu d'un chemin relatif à `data/hm`. Utilisé seulement pour le tie-break ; l'UI de démo devra afficher l'URL directement. | Non (format différent) |
| `article_id` | — | Aucun équivalent (catalogue H&M) | Oui (sans effet sur le score) |
| Occasion de la requête (`university/work/evening/casual`) | `occasions` (par article : `everyday, work, party…`) | Le moteur ne lit pas les occasions des articles. L'occasion est un paramètre de requête : l'agent doit la mapper vers les 4 valeurs BO4. | — |
| Saison de la requête | `seasons` (par article) | Le moteur ne lit pas `seasons` des articles. Le paramètre de requête utilise les mêmes 4 valeurs que BO1. | — |
| (non lu) | `formality`, `pattern`, `material`, `color_hex`, `color_family`, `needs_review`, `status` | Non utilisés par BO4. `needs_review` et `status` pourraient filtrer. | — |

### 12. Incompatibilités

1. **Nom du champ couleur** : BO4 lit `color` (L414), BO1 fournit `color_name`. Sans renommage, toutes les couleurs valent `unknown` et le score couleur tombe à 0.60.
2. **Format des couleurs** : BO1 utilise du texte avec espaces (33 noms, `colors.py` L8-20), BO4 du snake_case. Les espaces sont gérés par `normalize`, mais :
   - `charcoal` n'est **pas neutre** dans BO4 (neutre dans BO1, `enricher.py` L217) ;
   - `forest green`, `hot pink`, `mint`, `teal`, `coral`, `orange`, `chocolate`, `gold` et `silver` sont hors des familles BO4 (vérifié par appel de `is_neutral` et `color_family`).

   Le code hexadécimal (`color_hex`) n'est pas utilisé par BO4.
3. **Catégories** :
   - BO1 a 20 classes grossières, dont 12 accessoires que BO4 ignore.
   - `vest` est inconnu de BO4 et l'article est éliminé.
   - BO1 n'a pas `shirt`, `tshirt`, `jeans`, `blazer`, `coat`, `cardigan` : tout est `top`, `pants` ou `jacket`. La chaleur par catégorie de BO4 en devient moins précise (`jacket` = 3 niveaux, L75).
4. **Style** : vocabulaires disjoints, sauf `casual` et `formal`. BO1 a `elegant, business, sporty, streetwear, bohemian, minimalist, classic, romantic` ; BO4 attend `smart_casual`. Sans mapping, les scores style et occasion sont pénalisés (L198-200, L211-217).
5. **Chaleur** : entier 1-5 dans BO1, chaîne `light/medium/heavy` dans BO4. Sans conversion, elle est silencieusement ignorée.
6. **Saisons et occasions** : BO4 ne lit pas les listes `seasons` et `occasions` des articles. Les occasions de requête diffèrent : BO4 a `university/work/evening/casual`, BO1 a 11 valeurs (`everyday, work, party, date night…`).
7. **Manches** : `sleeve_length` est absent de BO1 (présent dans ton essai FashionCLIP).
8. **Images** : URL HTTP absolue côté BO1 (`/files/...` en local, Supabase public en prod) au lieu de `image_path` relatif à `data/hm/`. La démo `demo_bo4_web.py` sert les images par `article_id` (L59, L64-69), qui n'existe pas dans BO1.
9. **Identifiants** : UUID textuels contre ids numériques. C'est compatible, mais l'ordre de départage sera alphabétique.
10. **Authentification** : en prod, le JWT Supabase est obligatoire. En dev, l'utilisateur est fixe (`"local"`) et le `user_id` n'est pas un entier comme dans `wardrobe_db_adapter.load_user_wardrobe` (L167, `int(input(...))`).
11. **LLM** : l'agent BO1 est lié à OpenAI (`openai`, `gpt-4o`, `agent.py` L102-113) ; l'environnement BO4 dispose d'Ollama local (§13). Il n'y a ni LangChain ni LangGraph dans BO1.
12. **Environnements Python séparés** : BO1 requiert `ultralytics`, `openai`, `supabase`, `scikit-learn`, `pillow-heif`, `python-multipart`, absents du venv BO4 (§13). BO1 doit donc tourner dans son propre venv et être appelé en HTTP.
13. **Port** : BO1 et `backend/main.py` de BO4 (lancé par uvicorn, port non précisé ici, défaut 8000) peuvent entrer en conflit. `demo_bo4_web` utilise 8050 (L10).

---

## PARTIE 4 — Environnement

### 13. Sorties des commandes

**`ollama list`**

```
NAME           ID              SIZE      MODIFIED
qwen3-vl:2b    0635d9d857d4    1.9 GB    6 days ago
qwen2.5:3b     357c53fb659c    1.9 GB    7 weeks ago
```

**`C:\Users\Win11\DressMe\backend\.venv\Scripts\python.exe --version`**

```
Python 3.11.8
```

**`... -m pip list`** (sortie complète)

```
Package                 Version
----------------------- -----------
aiohappyeyeballs        2.7.1
aiohttp                 3.14.5
aiosignal               1.4.0
annotated-doc           0.0.5
annotated-types         0.8.0
annoy                   1.17.3
anyio                   4.15.1
appdirs                 1.4.4
asttokens               3.0.2
attrs                   26.1.0
boto3                   1.43.111
botocore                1.43.111
certifi                 2026.7.22
charset-normalizer      3.5.2
click                   8.5.0
colorama                0.4.6
contourpy               1.3.3
cycler                  0.12.1
datasets                2.21.0
dill                    0.3.8
executing               2.3.0
fashion-clip            0.2.2
fastapi                 0.143.0
filelock                4.1.1
fonttools               4.66.1
frozenlist              1.8.0
fsspec                  2024.6.1
h11                     0.16.0
hf-xet                  1.7.0
httpcore2               2.13.1
httptools               0.9.0
httpx2                  2.13.1
huggingface-hub         0.25.2
idna                    3.20
iniconfig               2.3.1
ipyplot                 1.1.2
ipython                 9.17.1
ipython_pygments_lexers 1.1.1
jedi                    0.20.0
Jinja2                  3.1.6
jmespath                1.1.0
kiwisolver              1.5.1
markdown-it-py          4.2.0
MarkupSafe              3.0.4
matplotlib              3.11.2
matplotlib-inline       0.2.2
mdurl                   0.1.2
mpmath                  1.3.0
multidict               7.1.0
multiprocess            0.70.16
networkx                3.6.1
numpy                   2.4.6
opencv-python           5.0.0.93
opentelemetry-api       1.45.1
packaging               26.3
pandas                  3.0.6
parso                   0.8.7
pillow                  12.3.0
pip                     26.2.1
pluggy                  1.6.0
prompt_toolkit          3.0.53
propcache               0.5.4
psutil                  7.2.2
psycopg                 3.3.6
psycopg-binary          3.3.6
pure_eval               0.2.4
pyarrow                 26.0.0
pydantic                2.14.0
pydantic_core           2.50.0
Pygments                2.21.0
pyparsing               3.3.3
pytest                  8.4.2
python-dateutil         2.9.0.post0
python-dotenv           1.2.4
PyYAML                  6.0.3
regex                   2026.9.29
requests                2.34.2
rich                    15.0.0
s3transfer              0.19.2
safetensors             0.8.0
setuptools              84.0.0
shellingham             1.5.4
shortuuid               1.0.13
six                     1.17.0
stack-data              0.6.3
starlette               1.7.0
sympy                   1.14.0
tokenizers              0.19.1
torch                   2.14.1
torchvision             0.29.1
tqdm                    4.70.1
traitlets               5.16.1
transformers            4.44.2
truststore              0.10.4
typer                   0.27.3
typing_extensions       4.16.0
typing-inspection       0.4.4
tzdata                  2026.5
urllib3                 2.8.0
uvicorn                 0.54.0
validators              0.36.0
watchfiles              1.3.0
wcwidth                 0.9.2
websockets              17.2
xxhash                  4.0.1
yarl                    1.25.1
```

**Paquets signalés**

| Paquet | Statut |
|---|---|
| `langgraph` | **ABSENT** |
| `langchain` | **ABSENT** |
| `langchain-ollama` | **ABSENT** |
| `fastapi` | Présent : 0.143.0 (+ `uvicorn` 0.54.0, `starlette` 1.7.0, `pydantic` 2.14.0) |
| `httpx` | **ABSENT sous ce nom**. Ce sont `httpx2` 2.13.1 et `httpcore2` 2.13.1 qui sont installés, un nom de paquet inhabituel dont la provenance est à vérifier. Le `TestClient` FastAPI et le client `ollama` attendent `httpx`. |
| `requests` | Présent : 2.34.2 |
| (info) `ollama` (client Python) | **ABSENT** |
| (info) `openai`, `supabase`, `ultralytics` | **ABSENTS** (nécessaires à BO1 uniquement) |

---

## Points bloquants

1. **Aucune donnée BO1 réelle disponible.** Il n'y a ni `backend/local_data/db.json` ni `.env`, et Supabase est inaccessible sans `SUPABASE_SERVICE_ROLE_KEY`. Il faut soit obtenir la clé ou un JWT de ta collègue, soit lancer BO1 en mode local et ajouter des vêtements (ce qui écrit sur disque et nécessite le venv BO1 avec torch et ultralytics).
2. **Stack LangGraph non installée** dans le venv BO4 : `langgraph`, `langchain` et `langchain-ollama` sont absents, ainsi que le client `ollama`. Le `httpx` standard est absent lui aussi : seul `httpx2` est présent.
3. **Contrat de champs incompatible** : `color_name`→`color`, `warmth` int→str, `style` hors vocabulaire. Sans couche d'adaptation, BO4 renvoie des scores dégradés **sans erreur** (valeurs `unknown` silencieuses). Un adaptateur `bo1_api_adapter` est à écrire ; l'actuel `bo1_adapter.py` vise ton essai FashionCLIP, pas l'API réelle.
4. **Décisions de mapping à prendre**, absentes du code :
   - styles BO1 (10 valeurs) vers les 3 styles BO4 ;
   - `warmth` 1-5 vers light/medium/heavy ;
   - sort de `vest` ;
   - déduction de `shirt`/`jeans`/`blazer`/`coat` depuis `subcategory` ;
   - couleurs hors familles BO4 (`charcoal`, `forest green`, etc.) ;
   - occasion utilisateur vers `university/work/evening/casual`.
5. **Granularité catégorielle** : BO1 n'a que `top`, `pants` et `jacket` là où BO4 distingue chemise, t-shirt, jean, blazer, manteau. La chaleur est estimée plus grossièrement, et `sleeve_length` manque.
6. **Authentification** : en prod, chaque appel BO4→BO1 doit porter `Authorization: Bearer <JWT Supabase>`. La procédure d'obtention du JWT côté backend est NON TROUVÉE. En dev, il n'y a qu'un utilisateur `"local"`.
7. **LLM divergent** : l'agent BO1 dépend d'OpenAI (`gpt-4o`, clé requise) alors que la cible est Ollama local. Les modèles disponibles sont `qwen2.5:3b` (texte) et `qwen3-vl:2b` (vision), tous deux petits (1.9 GB). La fiabilité du tool calling de ces modèles n'a pas été testée ici.
8. **Deux environnements Python** : BO1 (torch, ultralytics, openai, supabase) et BO4 ne partagent pas de venv. L'intégration doit passer par HTTP (BO1 sur le port 8000) et les ports doivent être coordonnés.
