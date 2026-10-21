# DressMe Trip Agent

A custom, stateful LLM trip-planning agent built on top of the existing
deterministic OR-Tools packing optimizer. No agent orchestration framework is
used: the agent loop, tool registry, validation, and state transitions are plain
Python.

## What it does

1. Extracts and validates a trip request (free text or structured input).
2. Asks for missing mandatory information instead of inventing it.
3. Selects and calls tools based on the current state.
4. Retrieves daily weather from Open-Meteo, with an explicitly labeled synthetic
   fallback when forecasts are unavailable.
5. Converts activities, weather, and occasions into optimizer-compatible daily
   requirements.
6. Runs the existing CP-SAT optimizer unchanged through an adapter.
7. Returns a trip capsule and a packing checklist (`packed: false` initially).
8. Suggests concrete recovery options for `INFEASIBLE` results without silently
   relaxing hard constraints.
9. Supports trip updates/reoptimization and checklist updates without rerunning
   the optimizer.
10. Exposes an optional `check_gaps` interface for a future Gap Agent.

## Architecture

```text
User text / structured request
        |
        v
TripAgent (agent.py)  <--- native OpenAI function calling
        |
        v
TripTools (tools.py) ---> extraction.py
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
| `wardrobe.py` | Provider interface and CSV-backed synthetic wardrobe/compatibility |
| `requirements.py` | Activity assignment and optimizer-compatible daily requirements |
| `optimizer_adapter.py` | Calls `optimize_packing`; builds capsule and compact results |
| `tools.py` | Tool schemas, argument validation, execution, state invalidation |
| `agent.py` | Custom LLM tool-calling loop + deterministic dependency-completion fallback |
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

The agent also works without an LLM or network: it uses the deterministic parser,
synthetic weather fallback, and the same Python tools. Set
`TRIP_AGENT_USE_LLM=0` (or pass `--no-llm`) to force that mode.

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
python -m pytest packing_backend/trip_agent/tests -q
```

Coverage includes:

- free-text extraction and missing dates
- weather retrieval/synthetic fallback
- dynamic daily requirement generation
- successful optimization and capsule creation
- infeasible optimization with recovery suggestions
- updating a trip and reoptimizing
- checklist state updates without optimizer reruns
- tool argument validation, weather caching, and the Gap Agent placeholder

## LLM behavior and safety

- The LLM decides which tools to call and in what order.
- Python validates every tool argument with Pydantic and enforces dependencies
  (for example, requirements cannot be generated before weather).
- Tool failures are returned as structured errors; the agent never fabricates
  optimizer output, wardrobe items, or weather.
- The loop is bounded by `MAX_AGENT_ITERATIONS`.
- If the LLM is unavailable, the same tools run through a deterministic
  fallback/dependency-completion path.
- `update_trip` invalidates stale downstream state and can reoptimize on request.
- `suggest_alternatives` diagnoses missing wardrobe roles and tight weight limits
  with a separate diagnostic solve; it reports suggestions and never applies a
  silent constraint relaxation.

## Notes and limitations

- Wardrobe, compatibility, and missing preferences remain synthetic.
- No frontend integration is included.
- Open-Meteo forecasts are limited to roughly the next 15 days; other dates use
  the labeled synthetic fallback.
- `check_gaps` is an interface only: inject a `gap_checker` callable into
  `TripAgent` to connect a teammate's Gap Agent.
- Weather/LLM calls have timeouts and all tool executions are logged as structured
  key/value events.
