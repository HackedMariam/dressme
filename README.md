# Dress Me — AI Style Intelligence

> **Frontend consolidation in progress.** `DressMe UI Blueprint` is the canonical frontend. The
> `frontend/` and `purchase-redundancy-ai/frontend/` apps are migration sources and will be retired
> after feature parity. See [`docs/frontend-consolidation.md`](docs/frontend-consolidation.md) for
> the decision log, feature matrix and remaining work.

Smart wardrobe:
photo → **YOLO11m-seg model** (`backend/models/dressme_best.pt`: category + cut-out) →
**color measured on the pixels** → **GPT-4 (OpenAI)** which classifies the item by **occasion, style,
color**, season, pattern, material → **per-user storage** → **3D wardrobe**.

```
 ┌──────────┐   photo   ┌──────────────────────── backend (FastAPI) ─────────────────────────┐
 │ Frontend │ ────────▶ │ 1. dressme_best.pt (YOLO11m-seg) → category + mask + confidence │
 │  React   │  + JWT    │ 2. mask → background removed (PNG) + k-means colors (Lab)         │
 │  + 3D    │ ◀──────── │ 3. GPT-4 (sees model output + cut-out, strict JSON)              │
 │ three.js │   item    │    → occasions, style, color + family, seasons, pattern, material │
 └──────────┘           │ 4. Supabase Storage + `items` table (filtered by user_id)         │
                        │ 5. corrections → `corrections` table → real accuracy              │
                        └────────────────────────────────────────────────────────────────────┘
```

## What each component does

| Step | Who | Result |
|---|---|---|
| Detection | `dressme_best.pt` (20 classes: top, sweater, jacket, vest, pants, shorts, skirt, dress, glasses, hat, headband, scarf, glove, watch, belt, sock, tights, shoe, bag, umbrella) | category + confidence + mask |
| Background removal | segmentation mask | transparent PNG (cards + 3D texture) |
| Measured color | k-means in Lab space on the **garment pixels only** | dominant color + palette |
| Classification | **GPT-4** (`gpt-4o` by default), strict JSON output (structured outputs), then re-validated on the server | occasions, style, color (fixed palette) + color family, seasons, pattern, material, formality, warmth, description, styling tips, tags, **confidence per field** |
| Review | detector confidence < 60%, GPT-4 disagrees with the model, or GPT-4 is unsure about occasion/style/season | **Needs review** badge |
| Corrections | "Save correction" / "Looks right" | `corrections` table → real accuracy per field (Dashboard) |

If the GPT-4 call fails (missing key, timeout, refusal), the item is still saved using
category rules and can be reclassified later ("Re-run AI").

## Two modes

| | Local (dev) | Production |
|---|---|---|
| Enabled when | `SUPABASE_SERVICE_ROLE_KEY` is empty | `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` are filled |
| Users | one user, no sign-in | Supabase Auth accounts (email + password), each user sees only their own wardrobe |
| Data | `backend/local_data/` | Supabase Postgres + Storage |

## Installation

### 1. Keys
```bash
cp .env.example .env                    # OPENAI_API_KEY (+ Supabase in production)
cp frontend/.env.example frontend/.env  # VITE_SUPABASE_ANON_KEY in production
```

### 2. Supabase (production)
1. Dashboard → **SQL Editor** → paste `supabase/schema.sql` → **Run**
   (tables `items`, `corrections`, RLS policies, bucket `wardrobe`). The script can be run again safely.
2. **Project Settings → API**: `service_role` key → `.env`; `anon public` key → `frontend/.env`.
3. **Authentication → Providers → Email** enabled. **URL Configuration**: add the frontend URL.

### 3. Backend
```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate                  # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --port 8000
```

Interactive docs: http://localhost:8000/docs — Tests: `pip install -r requirements-dev.txt && pytest`

### 4. Frontend (canonical)
```bash
cd "DressMe UI Blueprint"
pnpm install
pnpm dev           # dev server, proxies /api to http://127.0.0.1:8000
pnpm build         # production build in "DressMe UI Blueprint/dist"
```

The legacy `frontend/` app is kept only as a migration reference until the canonical frontend
reaches parity. See [`docs/frontend-consolidation.md`](docs/frontend-consolidation.md) for the
status matrix.

## Smart Purchasing AI Agent (BO6)

### Running the Smart Purchasing AI Agent (Inference)

The autonomous shopping assistant evaluates candidate clothes against the user's digital wardrobe using YOLO segmentation (`dressme_best.pt`), XGBoost decision classification, and fine-tuned Qwen reasoning. Runs on **any computer locally (GPU or CPU)** without memory overloads.

#### ⚡ Step 1: Install Dependencies (Required Before Running)
Before running `inference.py`, you must install all project dependencies:
```bash
cd smart_purchasing
pip install -r requirements.txt
```
*(Optionally, copy `.env.example` to `.env` and add your free Hugging Face token `HF_TOKEN=hf_...` to enable cloud Qwen reasoning).*

#### 🚀 Step 2: Run Inference

**The 4 Inputs:**
1. **`--image`**: Garment image (Web URL or local path). *Optional: defaults to `data/sample_camel_blazer.jpg` if omitted.*
2. **`--price`**: Candidate item price (e.g. `45.0`).
3. **`--budget`**: User's budget (e.g. `60.0`).
4. **`--prompt`**: Natural language question (e.g. `"Can I wear this to work?"`).

```bash
# Option A: From an Internet Image URL
python inference.py --image "https://images.unsplash.com/photo-1596755094514-f87e34085b2c?w=500" --price 45.0 --budget 60.0 --prompt "Can I wear this to a wedding?"

# Option B: From a Local Image File
python inference.py --image "data/sample_camel_blazer.jpg" --price 80.0 --budget 100.0 --prompt "Is this suitable for office meetings?"

# Option C: Quick Test with Default Fallback Image (no --image needed)
python inference.py --price 35.0 --budget 50.0 --prompt "Should I buy this for casual wear?"

# Option D: Instant Deterministic Test (Vision + XGBoost, skips Qwen load)
python inference.py --skip-llm
```


---

---

## Help Me Pack (BO7)

The Help Me Pack screen and orchestrator use the packing API in `backend/main.py`
on port **8020**. It verifies the caller through BO1 on port **8000**, loads that
user's wardrobe, and runs the packing workflow through LangGraph and the CP-SAT
optimizer. The service refreshes the wardrobe before trip continuations and edits;
sessions and checklists are in memory and are lost on restart. BO1 must enable
Supabase authentication for signed-in users; its local mode is single-user only.

Garment weights and compatibility are explicitly labelled estimates; BO1 does not
currently store weights, water resistance or pairwise compatibility. Live packing
requires an Open-Meteo forecast for every trip day and reports an error if unavailable.
The Gap Agent is unavailable unless a real integration is configured.
If the wardrobe cannot meet the trip requirements, Help Me Pack suggests missing
items and can retry after wardrobe updates. When repeating a complete outfit can
resolve the trip, it offers that as an explicit user choice.

Install `python -m pip install -r requirements.txt` at the root and the BO1 and
frontend dependencies. Start BO1 and then run `npm run dev:all`, or use
`start_all.ps1` to start the services. Configure `BO1_URL` if BO1 is not at
`http://127.0.0.1:8000`, and `VITE_TRIP_API_URL` if the packing API is not at
`http://localhost:8020`. Configure Supabase in the frontend and BO1. Packing tests:
`python -m pytest backend/test_api.py backend/test_packing_integration.py packing_backend/trip_agent/tests -q`.

## API (all `/api/items*` and `/api/stats*` routes require `Authorization: Bearer <Supabase JWT>` in production)

| Method | Route | Purpose |
|---|---|---|
| POST | `/api/items/analyze?all_items=false` | photo → detection → GPT-4 → save. `all_items=true`: one item per detected garment |
| GET | `/api/items` | list the user's items |
| PATCH | `/api/items/{id}` | `{fields:{...}, confirm:true}` correct / confirm (validated values), logs corrections |
| POST | `/api/items/{id}/reclassify` | run GPT-4 again on an existing item |
| DELETE | `/api/items/{id}` | delete the item and its images |
| GET | `/api/stats/accuracy` | real accuracy per field |
| GET | `/api/health`, `/api/taxonomy`, `/api/me` | status, vocabularies, current user |

## 3D wardrobe (`frontend/src/components/Wardrobe3D.jsx`)
- three.js wardrobe with animated doors. **Hanging rail**: jackets → tops → dresses → bottoms, each section ordered from light to dark, using the real cut-out photo as texture. **Shelves**: bags and accessories. **Bottom**: shoes.
- "Highlight what fits": filter by season, **occasion, style, color** — the other items dim.

## Deployment
- Backend: any Python host (VM, Render, Railway, Fly…) with at least 2 GB of RAM (torch + model). Set `CORS_ORIGINS` and `PUBLIC_API_URL` to the real URLs.
- Frontend: `npm run build`, then host `frontend/dist` (Vercel, Netlify, Supabase hosting…), with `VITE_API_URL` pointing to the backend.
- The `wardrobe` bucket is public for reading (paths contain non-guessable UUIDs) so the 3D view can load textures.

## Tips
- Photos of a single garment, flat or on a hanger, on a plain background: best detection and best cut-out. HEIC (iPhone) is accepted.
- `LLM_MODEL=gpt-4o` (default), `gpt-4.1`, or `gpt-4o-mini` to reduce costs. `LLM_IMAGE_DETAIL=high` helps on fine patterns.
- The `corrections` table is a ready-to-use dataset for retraining YOLO on its mistakes.
- License: Ultralytics/YOLO11 is AGPL-3.0 — take this into account if the app becomes commercial.

## Lancer DressMe

Tout DressMe en local, depuis la racine du dépôt (Windows PowerShell) :

```powershell
.\start_all.ps1          # démarre, vérifie la santé, précharge qwen2.5:3b
.\start_all.ps1 -Stop    # arrête ce que le script a lancé
```

| Service | Port | Lancement par le script |
|---|---|---|
| BO1 Wardrobe (`backend/`) | 8000 | `uvicorn app.main:app` |
| HelpMePack (`packing_backend/`) | 8020 | `uvicorn backend.main:app --port 8020` |
| Purchase Redundancy (`purchase-redundancy-ai/backend/`) | 8040 | `API_PORT=8040 python main.py` (son port par défaut, 8000, est celui de BO1) |
| Ollama `qwen2.5:3b` | 11434 | `ollama serve` avec `OLLAMA_KEEP_ALIVE=30m` |
| BO4 Stylist (`bo4/backend/`) | 8061 | `stylist_web.py --require-auth --bo1-url http://localhost:8000` |
| Orchestrateur (`orchestrator/`) | 8070 | `app.py` : page de conversation sur http://127.0.0.1:8070/ |

Chaque service utilise le Python de son dossier (`.venv`, `venv` ou `.venv-*`) ; sinon, indiquer le chemin de
`python.exe` dans `DRESSME_PY_BO1`, `DRESSME_PY_PURCHASE`, `DRESSME_PY_STYLIST` ou `DRESSME_PY_ORCHESTRATOR`.
Journaux : `%TEMP%\dressme-run`.

Fichiers `.env` (ignorés par git ; ne jamais les commiter). Seuls les **noms** des variables sont donnés ici :

| Fichier | Variables |
|---|---|
| `.env` ou `backend/.env` (BO1) | `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `OPENAI_API_KEY` ; facultatif : `LLM_MODEL`, `CORS_ORIGINS`, `PUBLIC_API_URL` |
| `orchestrator/.env` | `SUPABASE_URL`, `SUPABASE_ANON_KEY` (connexion des utilisateurs sur la page) |
| `purchase-redundancy-ai/.env` | voir `purchase-redundancy-ai/.env.example` (`SECRET_KEY`, `AUTH_REQUIRED`, `CLIP_ENABLED`, `DB_TYPE`…) ; `API_PORT` est fixé par le script |
| `frontend/.env` | `VITE_API_URL`, `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` |

Le Stylist n'a pas de `.env` : avec `--require-auth`, il vérifie le jeton de l'utilisateur auprès de BO1.
