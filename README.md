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

## Disclaimer / Project Status

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
