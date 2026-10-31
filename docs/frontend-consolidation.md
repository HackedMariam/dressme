# Frontend consolidation

Status: in progress
Branch: `wardrobe`
Scope: this branch only. Feature branches (`avatar/try1`, `helpmepack/try1`, `rag/try1`,
`shoppingAssistant`, `recommendation/stylist-agent`) are **not** merged here. Their modules will be
ported later, after the core frontend is stable.

## Goal

One frontend for every feature. `DressMe UI Blueprint` is the canonical app. The other two
frontends are migration sources and will be retired after parity:

- `frontend/` (wardrobe, 3D wardrobe, dashboard, live scan, Supabase auth)
- `purchase-redundancy-ai/frontend/` (dashboard, wardrobe, studio, scan, catalog, stylist, profile)

## Decisions

| Decision | Choice |
|---|---|
| Canonical frontend | `DressMe UI Blueprint` (React 19, Vite, TypeScript, Tailwind v4) |
| Identity | Supabase Auth |
| Wardrobe source of truth | Supabase `items` through `backend/app` (the main FastAPI backend) |
| UI language | English |
| V1 scope | auth, onboarding, profile, wardrobe, 3D, live scan, dashboard, purchase analysis, stylist, find similar; outfits pending a real score service |
| API access | One frontend origin. Dev uses the Vite `/api` proxy; production uses a reverse proxy or `VITE_API_URL`. |

## Current inventory

| App | Real features | Mock features | Backend |
|---|---|---|---|
| `DressMe UI Blueprint` | auth, onboarding, style profile, settings, wardrobe (list/edit/add/live scan/3D), dashboard, should I buy, AI stylist, find similar | outfit studio, help me pack, weather | Supabase + `backend/app` |
| `frontend/` | wardrobe list, item editing, live scan, photo/text/agent search, 3D wardrobe, dashboard | none | `backend/app` on `:8000` |
| `purchase-redundancy-ai/frontend/` | dashboard, wardrobe, outfit studio, purchase scan, catalog/search, stylist agent, style profile | none | `purchase-redundancy-ai/backend` via `/api` proxy |

The Blueprint `App.tsx` is a monolith. Its mock pages are defined in `src/App.tsx`:

| Lines | Function | Replacement |
|---|---|---|
| 122 | `Dashboard` | `features/dashboard/DashboardPage.tsx` |
| 237 | `MyWardrobe` | `features/wardrobe/WardrobePage.tsx` |
| 335 | `OutfitStudio` | not wired yet (preview) |
| 467 | `HelpMePack` | not wired yet (preview) |
| 620 | `WeatherPage` | live location forecast with Open-Meteo and MET Norway fallback |
| 703 | `ShouldIBuy` | `features/purchase/ShouldIBuyPage.tsx` |
| 819 | `AIStylist` | `features/stylist/StylistPage.tsx` |
| 944 | `FindSimilar` | `features/purchase/FindSimilarPage.tsx` |

## What this change does

1. Adds a shared API layer:
   - `src/lib/api.ts` – Supabase bearer token, main backend endpoints, errors.
   - `src/lib/types.ts` – `WardrobeItem`, `Health`, `AccuracyRow`, duplicate/search results.
   - `src/lib/taxonomy.ts` – taxonomy, colour palette, labels.
2. Adds `WardrobeProvider`, a single source of wardrobe state for all pages.
3. Replaces the mock **My Wardrobe** page with a real page:
   - list, search, group/colour/season/occasion/style filters, needs-review filter
   - add one or many photos through `POST /api/items/analyze`
   - photo search through `POST /api/search/photo`
   - item drawer with edit/confirm, re-run AI, delete
4. Replaces the mock **Dashboard** with real wardrobe statistics and the accuracy endpoint.
5. Replaces the mock **AI Stylist** with `POST /api/agent/search` (real wardrobe grounding).
6. Replaces the mock **Should I Buy?** with a real photo analysis flow:
   - `POST /api/items/analyze?save=false` for a preview
   - `POST /api/agent/check-duplicate` for the duplication verdict
   - locally matched similar items from the current wardrobe
   - optional save to the wardrobe
7. Replaces the mock **Find Similar** with in-wardrobe photo and text search:
   - `POST /api/search/photo`
   - `POST /api/agent/search`
8. Ports the **live camera scan** (`POST /api/items/quick-detect` + `POST /api/items/analyze?fast=true`
   + background `/reclassify`).
9. Ports the **3D wardrobe** (`Wardrobe3D.jsx`) and lazy-loads `three` so it is only downloaded when
   the 3D view is opened.
10. Adds the Vite `/api` proxy so the Blueprint can call the main backend without CORS.
11. Leaves **Outfit Studio**, **Help Me Pack** and **Weather** as design previews. Each is labelled
    in the UI until a real backend is wired.

## Feature status

| Feature | Status | API |
|---|---|---|
| Sign up / sign in / session | Ready | Supabase Auth |
| Onboarding and style preferences | Ready | Supabase `profiles`, `style_profiles` |
| Wardrobe list and filters | Ready | `GET /api/items` |
| Add clothing photo (single/multi) | Ready | `POST /api/items/analyze` |
| Edit / confirm / delete item | Ready | `PATCH /api/items/{id}`, `DELETE /api/items/{id}` |
| Re-run AI classification | Ready | `POST /api/items/{id}/reclassify` |
| Photo search in wardrobe | Ready | `POST /api/search/photo` |
| Text/agent search in wardrobe | Ready | `POST /api/agent/search` |
| Live camera scan | Ready | `POST /api/items/quick-detect`, `POST /api/items/analyze?fast=true` |
| 3D wardrobe | Ready (lazy-loaded) | existing items only (+ `three`) |
| Dashboard statistics | Ready | `GET /api/items`, `GET /api/stats/accuracy` |
| Should I Buy? | Ready (main backend version) | `POST /api/items/analyze?save=false`, `POST /api/agent/check-duplicate` |
| Find Similar | Ready (in wardrobe) | `POST /api/search/photo`, `POST /api/agent/search` |
| AI Stylist | Ready (main backend version) | `POST /api/agent/search` |
| Outfit Studio / outfit scoring | Real wardrobe + BO4 heuristic scoring | `GET /api/items`, `POST /api/stylist/outfit-score` (BO4, port 8061) |
| Help Me Pack / weather | Preview only | needs the packing service |
| Avatar / try-on | Out of scope on this branch | `avatar/try1` |
| RAG stylist | Out of scope on this branch | `rag/try1` |
| Smart purchasing | Out of scope on this branch | `shoppingAssistant` |

## Target structure

```
DressMe UI Blueprint/
  src/
    app/                 # shell, navigation, route switch
    features/
      auth/ onboarding/ profile/ settings/   # existing
      wardrobe/          # provider, page, item drawer
      dashboard/         # real stats
      stylist/           # wardrobe-grounded chat
      purchase/          # should I buy, find similar
      outfits/           # later
      packing/           # later
      avatar/            # later
    lib/                 # api, types, taxonomy, supabase
```

The current step adds the `lib/` layer and the `wardrobe/`, `dashboard/`, `stylist/` and `purchase/`
feature modules. Moving the remaining mock pages out of `App.tsx` is the next structural step.

## Backend and data constraints

1. **Supabase is the identity and wardrobe source of truth.** PR and feature services must read the
   user's wardrobe through an adapter. They must not introduce a second account system.
2. **One API origin.** Main backend paths already start with `/api`. The dev proxy forwards `/api`
   to `http://127.0.0.1:8000`. Later services get prefixes such as `/api/redundancy`, `/api/trips`,
   `/api/avatar`, `/api/stylist`, `/api/purchase` and separate ports behind the same proxy.
3. **No secrets in the browser.** The RAG key and any service credentials stay in a server-side
   gateway.
4. **No fake data in wired pages.** If a backend capability does not exist, the page is marked as a
   preview instead of inventing numbers.

## Running this branch

Backend (from the repository root):

```powershell
cd backend
.venv\Scripts\activate
uvicorn app.main:app --port 8000
```

Frontend:

```powershell
cd "DressMe UI Blueprint"
pnpm install
pnpm dev
```

Environment:

```env
# Leave empty to use the Vite proxy for /api
VITE_API_URL=

# Public Supabase values (same project as the backend)
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-public-anon-key
```

If the frontend is served without the Vite proxy, set `VITE_API_URL=http://localhost:8000`.

The Vite dev server proxy is configured for `/api` and uses `BACKEND_URL` when set:

```powershell
$env:BACKEND_URL="http://127.0.0.1:8001"; pnpm dev
```

## Next steps on this branch

1. Wire Outfit Studio to a real outfit scoring service. On this branch the only real engine is the
   `purchase-redundancy-ai` backend; it still needs a Supabase JWT adapter and a wardrobe adapter.
2. Move the remaining mock pages out of `App.tsx` into `features/`.
3. Remove the legacy frontends only after the wired pages pass manual smoke tests.
4. Add a server-side gateway if PR, packing, RAG, avatar or smart purchasing are enabled in the
   same deployment.

## Progress log

### Step 1 - real core pages on the branch

Added:

- `DressMe UI Blueprint/src/lib/api.ts`
- `DressMe UI Blueprint/src/lib/types.ts`
- `DressMe UI Blueprint/src/lib/taxonomy.ts`
- `DressMe UI Blueprint/src/features/wardrobe/WardrobeProvider.tsx`
- `DressMe UI Blueprint/src/features/wardrobe/WardrobePage.tsx`
- `DressMe UI Blueprint/src/features/wardrobe/ItemDrawer.tsx`
- `DressMe UI Blueprint/src/features/wardrobe/Wardrobe3D.jsx`
- `DressMe UI Blueprint/src/features/wardrobe/LiveScan.jsx`
- `DressMe UI Blueprint/src/features/dashboard/DashboardPage.tsx`
- `DressMe UI Blueprint/src/features/stylist/StylistPage.tsx`
- `DressMe UI Blueprint/src/features/purchase/ShouldIBuyPage.tsx`
- `DressMe UI Blueprint/src/features/purchase/FindSimilarPage.tsx`

Changed:

- `DressMe UI Blueprint/src/App.tsx`
  - renders the new pages for dashboard, wardrobe, should I buy, AI stylist and find similar
  - wraps the authenticated content in `WardrobeProvider`
  - marks outfit studio, help me pack and weather as design previews
- `DressMe UI Blueprint/vite.config.ts`
  - adds the `/api` development proxy (`BACKEND_URL` or `127.0.0.1:8000`)
- `DressMe UI Blueprint/.env.example`
  - documents the proxy-first `VITE_API_URL` behaviour and removes the browser RAG key
- `DressMe UI Blueprint/package.json` and `pnpm-lock.yaml`
  - add `three@0.186.1` for the 3D wardrobe
- `DressMe UI Blueprint/tsconfig.json`
  - enables `allowJs` for the two ported `.jsx` components

Known temporary state:

- The old mock page functions still exist inside `App.tsx`. They are no longer rendered for the
  replaced pages, but they were not deleted yet to keep this change focused and reviewable. Removing
  them and splitting the remaining preview pages into `features/` is the next structural step.
- `/api/items/analyze` is the only write path for new items. There is no price, URL or retail
  catalogue backend on this branch, so `Should I Buy?` reports detection, duplicate risk and owned
  matches instead of inventing a purchase score.
- `Find Similar` searches the user's wardrobe, not a retailer catalogue.
- Outfit Studio, Help Me Pack and Weather still display mock data and are labelled as previews.

Verified:

- `pnpm typecheck`
- `pnpm build`
- `pnpm test` (16 tests)
- Vite dev server starts and serves `/` and `/src/main.tsx`

## Verification

- `pnpm typecheck`
- `pnpm build`
- `pnpm test`
- Manual smoke test with a running backend:
  - sign in, complete onboarding
  - add a wardrobe photo and verify the item appears
  - use live scan and verify the held item is saved and reclassified
  - open the 3D view and click an item
  - edit and confirm the item, re-run AI, delete it
  - verify the dashboard numbers change
  - ask the stylist a question about an owned item
  - analyse a purchase photo and confirm the duplicate result
  - search by photo and by text
