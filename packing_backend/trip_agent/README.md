# DressMe Trip Agent

A stateful trip-planning agent using LangGraph and the deterministic OR-Tools
packing optimizer. The integrated API authenticates through BO1 and uses its
real wardrobe; the standalone CLI retains synthetic demo data.

## What it does

1. Extracts and validates a trip request (free text or structured input).
2. Asks for missing mandatory information instead of inventing it.
3. Selects and calls tools based on the current state.
4. Retrieves daily weather from Open-Meteo. The integrated API requires a real
   forecast for every trip day; the standalone demo can use synthetic weather.
5. Converts activities, weather, and occasions into optimizer-compatible daily
   requirements.
6. Runs the existing CP-SAT optimizer unchanged through an adapter.
7. Returns a trip capsule and a packing checklist (`packed: false` initially).
8. Suggests concrete recovery options for `INFEASIBLE` results without silently
   relaxing hard constraints: missing wardrobe items, or an explicit option to
   repeat a full outfit when a diagnostic proves that can solve the trip.
9. Supports trip updates/reoptimization and checklist updates without rerunning
   the optimizer.
10. Exposes an optional `check_gaps` interface for a future Gap Agent.

## Architecture

```text
User text / structured request
        |
        v
TripAgent (agent.py)  <--- optional OpenAI trip extraction
        |
        v
LangGraph workflow ---> TripTools (tools.py) ---> extraction.py
        |                 weather.py
        |                 wardrobe.py
        |                 requirements.py
        |                 optimizer_adapter.py ---> ../optimizer.py (unchanged)
        v
AgentState (schemas.py) -> AgentResponse (capsule + checklist + status)
```

| File | Responsibility |
|---|---|
| `schemas.py` | Pydantic trip/weather/requirements/capsule/checklist/state models |
| `llm.py` | Native chat-completions + tool-call wrapper; structured JSON extraction |
| `extraction.py` | LLM extraction, deterministic fallback parser, date/activity parsing |
| `weather.py` | Open-Meteo geocoding/forecast + labeled synthetic fallback |
| `wardrobe.py` | BO1 provider with estimated weight/compatibility; synthetic CLI provider |
| `requirements.py` | Activity assignment and optimizer-compatible daily requirements |
| `optimizer_adapter.py` | Calls `optimize_packing`; builds capsule and compact results |
| `tools.py` | Tool schemas, argument validation, execution, state invalidation |
| `agent.py` | LangGraph packing workflow and standalone demo tool-calling loop |
| `cli.py` | Runnable CLI, end-to-end demo, interactive mode |
| `tests/test_trip_agent.py` | Offline tests for all requested scenarios |

The optimizer contract is preserved: generated requirements include
`temperature_c`, `precipitation_mm`, `required_style`, `needs_outerwear`,
`needs_warm_layer`, `needs_rain_protection`, and `needs_sun_protection` exactly
as `packing_backend/optimizer.py` expects.

## Setup

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Set the LLM configuration in the existing root `.env`:

```dotenv
OPENAI_API_KEY=your_key_here
LLM_MODEL=gpt-4o
```

The standalone CLI works without an LLM or network using synthetic demo data.
Set `TRIP_AGENT_USE_LLM=0` (or pass `--no-llm`) to use the deterministic parser.
The integrated API requires BO1 and a real weather forecast.

## Run

Full demonstration (missing dates -> clarification -> optimize -> infeasible
recovery -> update/reoptimize -> checklist update):

```powershell
python -m packing_backend.trip_agent --demo
```

One-shot free-text request with dates:

```powershell
python -m packing_backend.trip_agent --request "I'm going to Paris for 5 days for sightseeing, shopping, and a formal dinner. My clothing luggage limit is 8 kg." --dates "June 3-7, 2027"
```

Offline/no-LLM demonstration:

```powershell
python -m packing_backend.trip_agent --demo --no-llm --no-weather-network
```

Structured input:

```powershell
python -m packing_backend.trip_agent --structured '{"destination":"Rome","start_date":"2027-05-10","end_date":"2027-05-12","activities":["sightseeing","shopping"],"max_luggage_weight_kg":8}'
```

Interactive mode:

```powershell
python -m packing_backend.trip_agent --interactive
```

Interactive commands: `/update {"max_luggage_weight_kg": 10}`, `/pack ITEM001`,
`/unpack ITEM001`, `/json`, `/quit`.

Use `--json` for machine-readable responses. Use `--no-weather-network` to force
the labeled synthetic weather fallback.

## Tests

```powershell
python -m pytest backend packing_backend/trip_agent/tests -q
npm run typecheck:frontend
npm run build:frontend
```

API integration tests live in `backend/test_api.py` and cover text/structured
trip creation, clarification continuation, weather/requirements, capsule and
checklist retrieval, checklist updates without optimizer reruns, trip editing,
infeasible recovery, and the mock Gap Agent.

Coverage includes:

- free-text extraction and missing dates
- weather retrieval/synthetic fallback
- dynamic daily requirement generation
- successful optimization and capsule creation
- infeasible optimization with recovery suggestions
- updating a trip and reoptimizing
- checklist state updates without optimizer reruns
- tool argument validation, weather caching, and the Gap Agent placeholder

## API + HelpMePack frontend

The agent is exposed by `backend/main.py` (FastAPI) and consumed by the existing
HelpMePack page in `DressMe UI Blueprint/src/features/helpmepack/HelpMePack.tsx`.
Sessions are kept in memory per backend process; the frontend stores the current
`session_id` in `localStorage` so it can resume after a page refresh.

### One-command startup

From the repository root:

```powershell
npm run dev:all
```

Start BO1 separately on port 8000 first. This starts:

- Packing FastAPI backend on `http://127.0.0.1:8020`
- Existing Vite HelpMePack frontend on `http://localhost:8443`

The launcher is `scripts/dev-all.mjs`. It reuses ports that are already open,
prints clear readiness logs, and stops both child processes together on
`Ctrl+C`. For manual backend debugging use `npm run dev:backend`; for the
frontend only use `npm run dev:frontend`.

### Environment

Root `.env`:

```dotenv
OPENAI_API_KEY=your_key_here
LLM_MODEL=gpt-4o
CORS_ORIGINS=http://localhost:8443,http://localhost:5173
```

Frontend `.env` in `DressMe UI Blueprint/`:

```dotenv
VITE_TRIP_API_URL=http://localhost:8020
```

Useful overrides for the launcher: `BACKEND_PORT`, `FRONTEND_PORT`,
`VITE_TRIP_API_URL`, `BO1_URL`, `PYTHON`, `FRONTEND_PM`.

### Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/health` | API/LLM/weather/session health |
| `POST` | `/api/trips` | Create from `{mode:"text", text:...}` or `{mode:"structured", trip:{...}}` |
| `POST` | `/api/trips/{session_id}/messages` | Continue a clarification conversation |
| `GET` | `/api/trips/{session_id}` | Retrieve full session state |
| `PATCH` | `/api/trips/{session_id}` | Update trip details and optionally reoptimize |
| `DELETE` | `/api/trips/{session_id}` | Drop an in-memory session |
| `POST` | `/api/trips/{session_id}/weather` | Retrieve/refresh weather |
| `POST` | `/api/trips/{session_id}/requirements` | Retrieve/generate daily requirements |
| `POST` | `/api/trips/{session_id}/optimize` | Run CP-SAT and return the result |
| `POST` | `/api/trips/{session_id}/suggest-alternatives` | Diagnose infeasibility |
| `GET` | `/api/trips/{session_id}/capsule` | Retrieve the optimized capsule |
| `GET` | `/api/trips/{session_id}/checklist` | Retrieve the packing checklist |
| `PATCH` | `/api/trips/{session_id}/checklist/{item_id}` | Mark packed/unpacked (no optimizer rerun) |
| `POST` | `/api/trips/{session_id}/gap-analysis` | Invoke the optional configured Gap Agent |

Interactive OpenAPI docs are available at `http://127.0.0.1:8020/docs`.

### Frontend flow

The HelpMePack page preserves the existing manual form and adds an "AI
description" tab. Both modes call the same backend:

1. Manual form -> structured trip payload.
2. AI text -> `mode:"text"` and LLM extraction.
3. Missing details -> the agent's clarification question is shown inline; the
   answer continues the same session.
4. Successful optimization -> weather cards, extracted details, daily outfits,
   capsule summary, and an interactive checklist.
5. Checklist updates call the checklist endpoint only.
6. Edit trip -> `PATCH /api/trips/{id}` with `reoptimize: true`.
7. Infeasible results -> explanations and recovery suggestions without silent
   constraint relaxation. Add or correct the suggested items in My Wardrobe, then
   use **Retry this trip**. If shown, **Allow outfit repeats & retry** explicitly
   permits repeating a complete outfit while retaining weather and weight limits.
8. Gap analysis -> unavailable unless a real integration is configured.

## LLM behavior and safety

- LangGraph controls the integrated packing workflow; the LLM can extract trip details.
- Python validates every tool argument with Pydantic and enforces dependencies
  (for example, requirements cannot be generated before weather).
- Tool failures are returned as structured errors; the agent never fabricates
  optimizer output, wardrobe items, or weather.
- The standalone demo's LLM tool loop is bounded by `MAX_AGENT_ITERATIONS`.
- If the LLM is unavailable, the same tools run through a deterministic
  fallback/dependency-completion path.
- `update_trip` invalidates stale downstream state and can reoptimize on request.
- `suggest_alternatives` diagnoses missing wardrobe roles and tight weight limits
  with a separate diagnostic solve; it reports suggestions and never applies a
  silent constraint relaxation.

## Notes and limitations

- The integrated API uses BO1 wardrobe items; weights and compatibility are estimates.
- Open-Meteo forecasts are limited to roughly the next 15 days. The integrated API
  reports unavailable forecasts instead of planning with synthetic weather.
- Destination geocoding is confidence-checked. Fuzzy/fictional names are
  refused instead of silently using an unrelated real town; the agent asks for a
  valid destination. Country requests use a representative city where available
  (for example `France` → `Paris`) or a clearly labelled country-centroid
  forecast.
- `check_gaps` is unavailable by default. Inject a `gap_checker` callable to connect it.
- Weather/LLM calls have timeouts and all tool executions are logged as structured
  key/value events.
