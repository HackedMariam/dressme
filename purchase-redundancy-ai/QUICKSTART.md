# ⚡ Quick Start

## Prerequisites
- Python 3.10+ (tested with 3.13)
- Node.js 18+ (tested with 24)
- An Anthropic API key (optional - the app works without it, with rule-based explanations)

## 1. Install

```bash
# Linux / macOS / Git Bash
bash setup.sh            # add --no-clip for a light install without torch

# Windows PowerShell
powershell -ExecutionPolicy Bypass -File setup.ps1   # add -NoClip for a light install
```

The script creates `backend/venv`, installs the Python and npm packages, seeds the SQLite
database with the 700 products, downloads the CLIP model (~600 MB, first run only) and
creates `.env` from `.env.example` **only if it does not exist**.

## 2. Configure

Edit `.env` - one LLM key is enough:
```env
OPENAI_API_KEY=sk-proj-...     # GPT (default when present), model in OPENAI_MODEL (gpt-4.1)
CLAUDE_API_KEY=sk-ant-...      # or Claude - set LLM_PROVIDER=claude to force it
```
Without any working key the app still runs: rule-based explanations and the local agent planner.

## 3. Run

```bash
# Terminal 1 - backend (http://localhost:8000, docs at /docs)
cd backend
venv/Scripts/python main.py      # Windows
venv/bin/python main.py          # Linux / macOS

# Terminal 2 - frontend (http://localhost:3000)
cd frontend
npm run dev
```

The frontend calls `/api/*`, which Vite proxies to the backend - no CORS setup needed.

## 4. Test

```bash
backend/venv/Scripts/python -m pytest tests     # Windows
backend/venv/bin/python -m pytest tests         # Linux / macOS
```

The tests run offline (simulated embeddings, no Claude calls, temporary database).

## Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/health` | CLIP / Claude / database status |
| GET | `/stats` | Catalog, wardrobe, analyses and feedback statistics |
| POST | `/analyze` | Redundancy analysis (features 1-13) against the saved wardrobe; optional `image_base64` photo |
| POST | `/agent/run` | **Autonomous agent** (streamed NDJSON): `mission` = `purchase` or `audit`, `message`, `image_base64`, `budget` |
| GET/POST/DELETE | `/wardrobe` | Saved wardrobe - add by photo (`image_base64`, attributes auto-detected), catalog `product_id` or fields |
| POST | `/wardrobe/sample` | Replace the wardrobe with 8 coherent catalog items |
| GET | `/products` | Catalog (`?category=shoes`, semantic search `?q=white leather sneakers`) |
| GET | `/images/products/<id>.png` | Product illustrations (700) - `/uploads/<id>.jpg` for wardrobe photos |
| POST | `/camera-capture` | Photo → CLIP zero-shot attributes + similar catalog products |
| POST | `/feature/{id}` | Run any feature 1-31 (body = its keyword arguments) |
| POST | `/feedback` | Persist user feedback |
| GET | `/llm/status` | Claude integration status |

### The agent

`POST /agent/run` plans its steps, executes them with the project's tools (CLIP vision, wardrobe,
redundancy engine, outfit matching, market & quality features) and streams one event per step,
then a final report (verdict, reasons, actions, catalog suggestions).
With a valid Claude key it runs as a Claude tool-use agent; otherwise - or if Claude fails
(no credits, network) - the local planner runs the same tools, so the agent always answers.

```bash
curl -N -X POST http://localhost:8000/agent/run -H "Content-Type: application/json" \
  -d '{"mission": "purchase", "message": "Des baskets blanches en cuir à 120 $"}'
```

### Data

**Real catalog (default)** - `database/products_real.json` + `database/images/real/*.jpg`, built by
`python database/scrape_real_catalog.py` from 4 open sources:

| Source | License | What it brings |
|---|---|---|
| [Marqo/KAGL](https://huggingface.co/datasets/Marqo/KAGL) | MIT | real product photos, category / color / season / usage |
| [Marqo/fashion200k](https://huggingface.co/datasets/Marqo/fashion200k) | Apache-2.0 | descriptions (materials), dresses / jackets / tops |
| [DummyJSON](https://dummyjson.com) | public test API | prices, brands |
| [FakeStore API](https://fakestoreapi.com) | public test API | prices |

Only DummyJSON / FakeStore publish prices: other products keep `price = null` (nothing invented).
The scraper respects Hugging Face rate limits (HTTP 429 → backoff) and caches pages in `database/.scrape_cache/`.

**Illustrated catalog** - `CATALOG=illustrated` uses `database/products_700.json` + generated drawings
(`python database/generate_700_products.py`).

The first backend start embeds the catalog photos with CLIP (~20-60 s, cached in `data/`).

### Example: analysis

```bash
curl -X POST http://localhost:8000/analyze -H "Content-Type: application/json" -d '{
  "new_item": {"name": "Blue Casual Shirt", "category": "shirts", "color": "blue", "style": "casual", "material": "cotton"},
  "wardrobe_items": [
    {"name": "Light Blue Oxford", "category": "shirts", "color": "blue", "style": "casual", "material": "cotton"}
  ]
}'
```

### Example: agent

```bash
curl -X POST http://localhost:8000/agent -H "Content-Type: application/json" -d '{
  "message": "Should I buy a navy wool blazer for $180? Check redundancy and quality.",
  "wardrobe_items": [{"name": "Grey Wool Coat", "category": "outerwear", "color": "gray", "style": "classic", "material": "wool"}]
}'
```

### Example: a backup feature

```bash
curl -X POST http://localhost:8000/feature/17 -H "Content-Type: application/json" -d '{"colors": ["navy", "red", "green"]}'
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `clip_mode: simulated` in `/health` | `pip install -r backend/requirements-ml.txt`, and check internet access for the first model download (`clip_error` tells why) |
| `llm.available: false` | Set `CLAUDE_API_KEY` in `.env` and restart the backend |
| Frontend shows "Backend unreachable" | Start the backend first; it listens on port 8000 |
| Port 3000 already in use | Stop the other process - Vite runs with `strictPort` |
| "Port 8000 is already used" at startup | Another app listens on 8000: set `API_PORT=8001` in `.env` and start the frontend with `BACKEND_URL=http://127.0.0.1:8001` |
| Camera button shows "accès refusé" | Allow the camera in the browser address bar. On a phone, the camera only works over HTTPS or `localhost` |
| Slow first start | The CLIP model loads and embeds the 700 products once (~10-30 s on CPU) |

## Accounts, PostgreSQL, Redis (optional)

- Accounts: click **Se connecter** in the sidebar. Without an account you use the guest wardrobe (as before).
  Set `SECRET_KEY` in `.env` for production and `AUTH_REQUIRED=True` to make accounts mandatory.
- PostgreSQL + Redis:
  ```bash
  POSTGRES_PASSWORD=choose-one docker compose up -d
  cd backend && venv/Scripts/python migrate_db.py --target postgresql://redundancy:choose-one@localhost:5433/purchase_redundancy
  # then in .env: DATABASE_URL=postgresql://redundancy:choose-one@localhost:5433/purchase_redundancy
  #               REDIS_URL=redis://localhost:6379/0
  ```
- Monitoring: the **Statistiques** page, `GET /metrics` (Prometheus), `GET /analytics/system`, logs in `logs/app.log`
  (`LOG_FORMAT=json` for log aggregators).
- Tests: `cd backend && venv/Scripts/python -m pytest ../tests -q` (136 tests).
- Demo accounts (2 women, 2 men, ~50 real pieces each): `cd backend && venv/Scripts/python seed_demo_users.py`
  — e.g. `sofia.martin@example.com` / `karim.benali@example.com`, password `Doublon-Demo2026`.
