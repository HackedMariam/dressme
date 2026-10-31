# DressMe UI Blueprint

Canonical frontend for DressMe. It keeps the existing Supabase auth, onboarding, style profile and
settings, and adds live wardrobe, dashboard, stylist, purchase analysis and wardrobe search pages
from the main backend.

Full consolidation notes: [`../docs/frontend-consolidation.md`](../docs/frontend-consolidation.md).

## Run

```powershell
# Terminal 1 - main backend
cd ..\backend
.venv\Scripts\activate
uvicorn app.main:app --port 8000

# Terminal 2 - this frontend
pnpm install
pnpm dev
```

The dev server proxies `/api` to `http://127.0.0.1:8000`. Override the target with `BACKEND_URL`:

```powershell
$env:BACKEND_URL="http://127.0.0.1:8001"; pnpm dev
```

## Environment

Vite reads the single `.env` at the repository root (copy the root `.env.example`): `SUPABASE_URL`,
`SUPABASE_ANON_KEY` and the `VITE_*` values. A `.env` in this folder, if present, wins for those two Supabase
values. Leave `VITE_API_URL` empty when using the Vite proxy. Set it to the backend origin when the app is
served without a proxy.

Never put `SUPABASE_SERVICE_ROLE_KEY` or an LLM/RAG key in this file: it is compiled into the
browser bundle.

## Page status

| Page | Status | Source |
|---|---|---|
| Dashboard | Live | `GET /api/items`, `GET /api/stats/accuracy` |
| My Wardrobe | Live | `GET/POST/PATCH/DELETE /api/items*` |
| 3D wardrobe | Live (lazy-loaded) | `three`, existing items |
| Live scan | Live | `POST /api/items/quick-detect`, `POST /api/items/analyze?fast=true` |
| Should I Buy? | Live (photo analysis) | `POST /api/items/analyze?save=false`, `POST /api/agent/check-duplicate` |
| Find Similar | Live (in-wardrobe search) | `POST /api/search/photo`, `POST /api/agent/search` |
| AI Stylist | Live (wardrobe-grounded chat) | `POST /api/agent/search` |
| Style Profile | Live | Supabase `profiles`, `style_profiles` |
| Settings | Live | Supabase |
| Outfit Studio | Design preview | not wired yet |
| Help Me Pack | Design preview | not wired yet |
| Weather | Design preview | not wired yet |

## Verify

```powershell
pnpm typecheck
pnpm build
pnpm test
```
