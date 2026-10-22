# DressMe

**Your smart wardrobe, your personal fashion assistant.**

DressMe is a smart wardrobe ecosystem designed primarily for the **Tunisian market**. The idea is simple: most people own more clothes than they wear, forget what they already own, and end up buying duplicates. DressMe turns a physical wardrobe into a structured, queryable digital one, then uses that understanding to help with everyday decisions — what to wear, what to pack, what to buy, and what to let go.

> **Project status — please read first.**
> This repository contains the **UI / Figma prototype** of DressMe and one implemented vertical slice: the **Help Me Pack (BO7) Trip Agent**, backed by a deterministic CP-SAT optimizer and a FastAPI service. The remaining business objectives, the full eight-agent architecture, and the production data model are still under discussion and are **not implemented**. See [Implemented: Help Me Pack (BO7)](#implemented-help-me-pack-bo7) and [Current Status](#current-status).

---

## Table of Contents

- [GitHub Rules for the Team](#github-rules-for-the-team)
- [Project Overview](#project-overview)
- [Business Objectives](#business-objectives)
- [AI & Multi-Agent Architecture](#ai--multi-agent-architecture)
- [Prototype](#prototype)
- [Implemented: Help Me Pack (BO7)](#implemented-help-me-pack-bo7)
- [Screens](#screens)
- [Current Status](#current-status)
- [Roadmap](#roadmap)
- [Repository Structure](#repository-structure)
- [Disclaimer / Project Status](#disclaimer--project-status)

---

## GitHub Rules for the Team

These rules are not suggestions. They exist so that five people can work on DressMe at the same time without stepping on each other.

### 1. Never work on `main`

`main` is the integration branch. It must always stay runnable.

```bash
git checkout main
git pull
```

### 2. One branch per feature — always create a branch

Never commit a feature directly to `main`. Before writing any code:

```bash
git checkout main
git pull
git checkout -b feature/helpmepack-form
```

**Branch naming:** `feature/<feature-folder>` — the branch name always matches the folder you are building.

| Type | Format | Example |
| --- | --- | --- |
| Feature | `feature/<name>` | `feature/helpmepack-form` |
| Fix | `fix/<name>` | `fix/wardrobe-search-empty-state` |
| Refactor / chore | `chore/<name>` | `chore/split-app-into-features` |

Rules: lowercase, hyphens instead of spaces, one branch = one feature.

### 3. Clear folders — one folder per feature

Every feature gets its own folder, named in lowercase with no spaces. Sub-parts of a feature go in a child folder.

```text
src/
└── features/
    ├── helpmepack/
    │   ├── form/          # the trip input form
    │   ├── packlist/      # the generated pack list
    │   └── looks/         # daily looks for the trip
    ├── wardrobe/
    │   ├── grid/
    │   └── additem/
    ├── outfits/
    │   └── canvas/
    ├── weather/
    ├── shouldibuy/
    │   └── analysis/
    ├── stylist/
    └── profile/
```

**The convention, precisely:**

- Feature folder = the feature name, lowercase, no spaces: `helpmepack`, `shouldibuy`, `wardrobe`.
- Sub-feature = `<feature>/<part>`: `helpmepack/form` is the input data form of the Help Me Pack feature.
- One folder = one screen or one self-contained piece of UI. If a folder gets confusing, split it further rather than growing one giant file.
- Shared code goes in `src/components`, `src/lib`, `src/hooks` — never duplicated inside a feature folder.

> The prototype is currently one large `App.tsx`. As you touch each feature, split that section into its own folder under `src/features/`. Do not rewrite the whole app in one branch.

### 4. Commit early, commit small

Use [Conventional Commits](https://www.conventionalcommits.org/) — the repo already follows this format:

```text
feat: add trip input form for help me pack
fix: pack list ignores optional items
style: align wardrobe grid spacing
refactor: extract weather card component
chore: add pnpm lockfile
```

Types: `feat`, `fix`, `style`, `refactor`, `docs`, `chore`.

### 5. Open a pull request — no direct pushes to `main`

```bash
git push -u origin feature/helpmepack-form
```

Then open a PR on GitHub. A PR must:

- Target `main`, and be linked to its folder (`helpmepack/form`).
- Explain **what** changed and **why** in two or three lines.
- Include a screenshot or screen recording for anything visual.
- Keep to one feature. Do not mix a refactor with a new feature in the same PR.
- Pass CI and get **one approval** before merge.

Use **Squash and merge** so `main` history stays readable.

### 6. Keep your branch current

```bash
git fetch origin
git rebase origin/main
git push --force-with-lease
```

Rebase often — daily if several people are active. Never force-push to `main`.

### 7. Don't commit junk

- Never commit `node_modules`, `.env`, API keys, or local settings. `.gitignore` already covers most of this.
- Commit generated files (like `pnpm-lock.yaml`) but never build output (`dist/`, `.vite/`).
- Keep `README.md` and this rules section up to date when you change the structure or the BOs.

### 8. Ownership

Check open PRs before starting a feature. If someone already has a branch for it, coordinate instead of forking the same work twice.

---

## Project Overview

DressMe aims to combine four capability areas into a single personalized wardrobe ecosystem:

| Pillar | Role |
| --- | --- |
| **Computer Vision** | Understand a photo of a garment: detect it, segment it, remove the background, classify it, and extract attributes (category, color, pattern, material, season). |
| **Recommendation** | Match and rank items into outfits, packing lists, and purchase decisions based on compatibility rather than generic popularity. |
| **Contextual data** | Weather, destination, occasion, season, luggage constraints, budget, and the user's own style profile. |
| **AI agents** | Conversational and task-oriented agents that combine all of the above and explain their reasoning to the user. |

The end goal is an assistant that *understands* the user's wardrobe and preferences rather than just browsing a catalog. It should be able to answer questions like "what do I wear to a dinner party?" or "what am I missing from my wardrobe?" using only what the user actually owns.

The target context is the Tunisian market: local climate ranges, a retail landscape that differs from Europe/North America, purchasing power constraints, and a fashion reality that is practical rather than trend-driven. Those constraints are a product requirement, not an afterthought.

**What this repository is:** the Figma-derived UI prototype that will serve as the reference implementation of the future frontend, plus one implemented backend vertical — Help Me Pack — that the prototype already calls. The remaining screens are still sample-data mockups.

---

## Business Objectives

Seven business objectives (BOs) structure the product. Each one is written as a **pain the user already feels**, followed by the capability that answers it. Each BO is a distinct capability area, not a UI screen.

### BO1 — Wardrobe Visibility

> *I forget what I own.*

Make the wardrobe legible and structured. A user photographs their clothes; the system removes the background, detects the category, extracts attributes (color, material, pattern, season, style tags), and stores the item. Automatic extraction is never trusted blindly — the user can correct any field. The result is a wardrobe that can be searched, filtered, and sorted, plus a wear log that records what gets used and how often.

### BO2 — Purchase Redundancy

> *I buy the same clothes again.*

Stop the cycle of duplicate purchases. For every item the user considers buying — and for every item already in the wardrobe — DressMe quantifies **how close it is to something they already own**. A second white t-shirt with the same cut is flagged as redundant even if it is not the exact same piece. The output is an honest redundancy score with the evidence behind it: which existing items it duplicates, how similar they are, and how often those are actually worn. The goal is to make the user pause before the purchase, not to forbid it.

### BO3 — Wardrobe Gaps

> *Key pieces are missing.*

Tell the user what their wardrobe is structurally unable to do. DressMap analyses category coverage, colour distribution, and season/occasion representativeness to identify missing key pieces — no versatile layer, no warm outerwear, nothing wearable in heat, no formal option. A gap is only real if it blocks an outfit the user would actually want, so gaps are framed against the user's style profile and their lifestyle, not a generic ideal wardrobe. Output is a prioritised list, not a shopping list.

### BO4 — Contextual Recommendation

> *Weather, occasion and plans never meet.*

Recommend outfits built **only from what the user already owns**, conditioned on the real situation rather than on taste in the abstract. Context inputs: current weather and forecast, occasion and dress code, season, time of day, and the user's declared style. The engine ranks combinations by compatibility of the pieces with each other (silhouette, colour harmony, formality level, layering logic) and by fitness for the context. The target is fewer unused items and no outfit that is technically valid but wrong for the day.

### BO5 — Trust & Transparency

> *I do not trust advice I do not understand.*

A recommendation the user cannot interpret is worthless. Every suggestion ships with its reasoning: which items were used and why, which were rejected and on what grounds, which signal carried the most weight, and what the system is uncertain about. Confidence is shown honestly, including "I am not sure" and "I need more data on your wardrobe." Where an automatic attribute extraction may be wrong, the interface says so and invites correction. Trust is earned by being legibly fallible, not by being authoritative.

### BO6 — Smart Purchasing

> *I buy without thinking about my closet.*

Act as a second opinion **before** the money is spent. Given a screenshot, link, or description of an item, DressMe evaluates it against the existing wardrobe: does it fit the user's style profile, does it work with what they own, is it a near-duplicate of something already owned (BO2), does it fill a real gap (BO3), is the price reasonable relative to the user's spending pattern and budget, and what does it do to the wardrobe's cost-per-wear and composition. The output is a verdict with a purchase score and the reasoning behind it — buy, wait, or skip.

### BO7 — Help Me Pack

> *I have a limited amount of choice of outfits.*

Turn a trip into a small number of **maximally combinable** outfits. The system takes destination, dates, planned activities, dress code, and luggage constraints, then combines them with the user's wardrobe and the destination's weather forecast. It optimises for mix-and-match potential — fewest items, most combinations — so a short trip does not collapse into one worn outfit per day. Each packed item is labelled **own / buy / optional**, redundant pieces are flagged, and a pre-departure gap list appears if something essential is missing. The result is a decision the user can defend: here is why these seven items cover nine days.

---

## AI & Multi-Agent Architecture

DressMe is planned to evolve toward a **multi-agent architecture**: a set of specialised agents, each responsible for a bounded task and aligned to a business objective, collaborating through an orchestration layer.

| Agent | Responsibility | Serves |
| --- | --- | --- |
| **Wardrobe Analysis / Computer Vision Agent** | Garment detection, segmentation, background removal, classification, attribute extraction | BO1 |
| **Redundancy Agent** | Similarity and near-duplicate detection between candidate purchases and owned items | BO2 |
| **Wardrobe Gap Agent** | Category / colour / season / occasion coverage analysis, prioritised gap ranking | BO3 |
| **Contextual Recommendation Agent** | Assembles and scores outfits from the existing wardrobe given weather, occasion, and season | BO4 |
| **Transparency / Explanation Agent** | Produces and audits the reasoning attached to every recommendation | BO5 |
| **Shopping / Purchase Assistant Agent** | Evaluates a prospective purchase against wardrobe composition, style, and budget | BO6 |
| **Packing Agent** | Builds and optimises trip pack lists against weather, activities, and luggage limits | BO7 |
| **Conversational / Orchestrator Agent** | Natural-language entry point; routes requests to the right agent and synthesises responses | All |

The intent is **collaboration, not a monolithic model**. A single system asked to do vision, ranking, reasoning, and conversation at once tends to be weaker and harder to evaluate than specialised components with clear boundaries. Separating them also lets each capability be improved, measured, and replaced independently. Having each agent map to exactly one BO keeps the product honest: if an agent cannot be traced to a business objective, it does not ship.

Concepts and technologies under consideration include:

- **Computer Vision** — garment detection, classification, instance segmentation, background removal, attribute (colour / material / pattern) extraction
- **Recommendation systems** — content-based and hybrid ranking over wardrobe embeddings; compatibility and compatibility scoring
- **LLM-based agents** — reasoning, explanation, and conversational interaction over wardrobe data
- **RAG** — retrieval over contextual fashion and wardrobe knowledge where it adds value
- **Weather and context APIs** — current conditions and forecasts as recommendation inputs
- **User preference and wardrobe history** — style profile, wear logs, cost-per-wear, saved outfits as the personal signal
- **Agent orchestration** — routing, tool access, shared memory, and fallback behaviour between agents

> **This architecture is not finalized.** The agent boundaries, model choices, orchestration framework, data stores, and evaluation strategy are all still being evaluated. The table above describes a direction of travel, not a committed design.

---

## Prototype

This repository contains the DressMe **UI / Figma prototype**, built as a React + Vite + Tailwind application from the Figma Make design. It exists to make the product tangible and testable before the technical implementation is decided.

The prototype is used to:

- **Validate the user experience** — test whether the flows are understandable and worth building.
- **Visualise the features** — show what each of the 7 business objectives looks like as an interface.
- **Define navigation and application flows** — settle the information architecture before a backend constrains it.
- **Demonstrate the 7 BOs** — give concrete form to each objective.
- **Provide a foundation for the technical implementation** — act as the visual and UX reference the real frontend is built against.

The prototype is interactive. Most screens are still **not connected to a backend, AI model, or data source** — scores, weather, wardrobe items, recommendations, and chat replies are hard-coded sample data for illustration. The exception is **Help Me Pack**, which is wired to the FastAPI Trip Agent described in [Implemented: Help Me Pack (BO7)](#implemented-help-me-pack-bo7). The prototype will keep evolving as product and technical decisions are refined.

### Prototype screens

Each screen maps to the BOs it is meant to demonstrate:

| Section | Purpose | Related BO |
| --- | --- | --- |
| **Dashboard** | Daily AI recommendation, compatibility score, wardrobe stats, gap and duplicate analysis | BO1, BO2, BO3, BO4 |
| **My Wardrobe** | Item grid with search, category filters, sort by recency / wear / cost-per-wear, add-item flow | BO1, BO3 |
| **Outfit Studio** | Drag-and-drop outfit canvas with live style synergy scoring and suggested additions | BO4, BO5 |
| **Help Me Pack** | Trip form → generated pack list with own / buy / optional states and daily looks | BO7 |
| **Weather & Style** | 7-day forecast with per-day styling guidance from the user's own wardrobe | BO4 |
| **Should I Buy?** | Retail screenshot / URL analysis with purchase score, redundancy risk, and verdict | BO2, BO6 |
| **Find Similar** | Image reference → similar items with match percentages | BO2, BO6 |
| **AI Stylist** | Conversational interface with an active-context panel (weather, occasion, style, wardrobe size) | BO4, BO5 |
| **Style Profile** | Aesthetic affinities, colour palette, preferred occasions, size profile | BO1, BO4 |
| **Settings** | Account, regional preferences (currency, units, size system), AI and notification toggles | — |

---

## Implemented: Help Me Pack (BO7)

Help Me Pack is the only feature implemented end to end. The prototype screen is wired to a real backend:

| Layer | Location |
| --- | --- |
| UI | `DressMe UI Blueprint/src/features/helpmepack/HelpMePack.tsx` — manual trip form and natural-language "AI description" mode |
| API client | `DressMe UI Blueprint/src/api/tripAgent.ts` |
| Service | `backend/main.py` — FastAPI app, in-memory sessions and REST endpoints |
| Agent | `packing_backend/trip_agent/` — agent loop, tools, extraction, weather, requirements and optimizer adapter |
| Optimizer | `packing_backend/optimizer.py` — OR-Tools CP-SAT packing optimizer |

What the agent does:

1. Extracts trip details from free text or a structured form; asks one clarification question instead of inventing missing fields.
2. Fetches daily weather from Open-Meteo, with an explicitly labeled synthetic fallback.
3. Converts weather, activities, occasions and dress code into optimizer requirements.
4. Solves the packing problem with CP-SAT, producing a minimal, maximally combinable capsule.
5. Returns daily outfits and a packing checklist (`packed: false` initially).
6. Diagnoses `INFEASIBLE` results and suggests alternatives without silently relaxing hard constraints.
7. Supports trip updates/reoptimization and checklist updates without rerunning the optimizer.

Technical shape:

- **LLM** — GPT-4o via native function calling at `temperature=0`, with a deterministic regex/dependency-completion fallback when the LLM or network is unavailable.
- **Tools** — 10 validated tools: `get_trip_details`, `get_weather`, `get_wardrobe`, `get_activity_requirements`, `optimize_trip`, `generate_checklist`, `suggest_alternatives`, `update_trip`, `update_checklist`, `check_gaps`.
- **Optimization** — OR-Tools CP-SAT; the LLM never computes or fabricates the packing result.
- **Persistence** — sessions are in memory and are lost on backend restart; there is no authentication or persistent user profile yet.
- **Data** — the wardrobe, compatibility data and preferences are synthetic.
- **Tests** — offline agent tests plus API integration tests: `python -m pytest backend packing_backend/trip_agent/tests -q`.

Endpoints, the session model and the full architecture are documented in [`packing_backend/trip_agent/README.md`](packing_backend/trip_agent/README.md) and [`docs/agent-description.md`](docs/agent-description.md). The pipeline diagram is in [`docs/agent-pipeline.png`](docs/agent-pipeline.png).

### RAG knowledge layer

A separate retrieval layer was built over 38 fashion PDFs (about 6,600 pages, ~10.7M characters): chunking, category/topic tagging, `all-MiniLM-L6-v2` embeddings, query rewriting, top-5 retrieval and grounded answer generation. Reported evaluation on 12 questions: **Hit@5 = 0.9167, MRR = 0.8542, context precision = 0.7167**.

The RAG layer is **not wired into the Trip Agent** and is not part of the running Help Me Pack flow. Its source modules are not present in this working tree — only generated artifacts under `rag_backend/data/` remain; the implementation lives on the `rag/try1` branch. Treat it as an evaluated prototype, not a shipped service.

---

## Screens

### Dashboard

![DressMe Dashboard](dashboard.png)

*Daily AI recommendation with compatibility score, wardrobe statistics, wardrobe gap analysis, and potential duplicate detection.*

### My Wardrobe

![DressMe Wardrobe](wardrobe.png)

*Structured wardrobe grid with search, category filtering, wear counts, and cost-per-wear per item.*

### Help Me Pack

![DressMe Help Me Pack](helpmepack.png)

*Trip intake and generated pack list, distinguishing items already owned, recommended purchases, and optional additions.*

---

## Current Status

**Implemented**

- Product ideation completed around the 7 business objectives.
- UI/UX prototype built from the Figma design, with the main flows navigable.
- **Help Me Pack (BO7)** implemented end to end: Trip Agent, 10 tools, CP-SAT optimizer, Open-Meteo weather with fallback, FastAPI service, React UI and offline/API tests.
- A RAG knowledge layer was built and evaluated (retrieval metrics, generated artifacts), but its source is not on this branch and it is not wired into the agent.

**Still open**

- BO1–BO6 and the computer-vision pipeline are not implemented.
- The production architecture, data model, authentication and persistent storage are not defined.
- The multi-agent approach is planned but not finalized — only the Trip Agent is realized; agent boundaries, models and orchestration are unresolved.
- Sessions are in memory, the wardrobe data is synthetic, and there is no user profile or wear history.
- Screens other than Help Me Pack remain hard-coded prototype mockups.
- No production deployment, monitoring or CI pipeline exists yet.

**This is not a finished or production-ready product.**

---

## Roadmap

Indicative only — the order and content may change as decisions are made.

1. **UI / Figma prototype** — *(current)*
2. **UX validation and refinement** — user testing, flow fixes, design system consolidation
3. **Frontend implementation** — production app, real routing, state management, API layer, split into the feature folders described in the GitHub rules *(partial: Help Me Pack only)*
4. **Backend and data architecture** — wardrobe/item schema, user accounts, wear logs, storage for images *(partial: in-memory Help Me Pack API only)*
5. **Wardrobe computer vision pipeline** — detection, segmentation, background removal, classification, attribute extraction (BO1) *(not started)*
6. **Recommendation and contextual intelligence** — compatibility scoring, occasion/weather conditioning, ranking (BO4), gap and redundancy analysis (BO2, BO3) *(partial: Help Me Pack requirements and CP-SAT optimization only)*
7. **Multi-agent architecture integration** — agent definitions, orchestration, shared memory, RAG, explanation layer (BO5) *(partial: Trip Agent implemented; RAG standalone)*
8. **Testing and evaluation** — CV accuracy, recommendation quality, agent task evaluation, user studies *(partial: Help Me Pack offline/API tests and RAG retrieval metrics)*
9. **Iterative refinement** — feedback-driven improvement across the pipeline

---

## Repository Structure

The structure below reflects what is actually in the repository. Production folders (`frontend/`, a vision pipeline, persistent storage) are still to be created.

```text
DressMe/
├── DressMe UI Blueprint/       # React + Vite + Tailwind prototype
│   └── src/
│       ├── App.tsx             # Prototype screens and navigation
│       ├── api/tripAgent.ts    # Help Me Pack API client
│       └── features/
│           └── helpmepack/HelpMePack.tsx
├── backend/                    # FastAPI service (Trip Agent API, in-memory sessions)
│   ├── main.py
│   └── test_api.py
├── packing_backend/            # CP-SAT optimizer + Trip Agent
│   ├── optimizer.py
│   ├── data/                   # Synthetic wardrobe, compatibility and trip data
│   └── trip_agent/             # Agent loop, tools, extraction, weather, requirements
│       └── tests/
├── rag_backend/                # RAG knowledge layer (generated artifacts only on this branch)
├── docs/                       # Agent description and pipeline diagram
├── scripts/                    # dev-all launcher
├── supabase/                   # Linked project metadata (no migrations tracked)
├── requirements.txt
├── package.json
└── README.md
```

### Documentation

| Document | Contents |
| --- | --- |
| [`docs/agent-description.md`](docs/agent-description.md) | Trip Agent: LLM choice, memory, actions, tools, pipeline, techniques, limitations |
| [`docs/agent-pipeline.png`](docs/agent-pipeline.png) | Rendered end-to-end pipeline diagram |
| [`docs/agent-pipeline.mmd`](docs/agent-pipeline.mmd) | Editable Mermaid source for the diagram |
| [`packing_backend/trip_agent/README.md`](packing_backend/trip_agent/README.md) | Trip Agent setup, CLI, endpoints, session model and safety notes |
| `http://127.0.0.1:8000/docs` | Interactive OpenAPI reference (when the backend is running) |

### Running the prototype

```bash
cd "DressMe UI Blueprint"
pnpm install
pnpm dev
```

Requires Node.js and pnpm (versions pinned in `.mise.toml`).

### Running the full HelpMePack app (Trip Agent + frontend)

One-time setup from the repository root:

```bash
python -m pip install -r requirements.txt
pnpm --dir "DressMe UI Blueprint" install
```

Copy the example files and fill in the values you need:

```bash
cp .env.example .env
cp "DressMe UI Blueprint/.env.example" "DressMe UI Blueprint/.env"
```

| Variable | File | Purpose | Default |
| --- | --- | --- | --- |
| `OPENAI_API_KEY` | root `.env` | OpenAI key for extraction, tool calling and explanations | none — the deterministic fallback is used |
| `LLM_MODEL` | root `.env` | Chat model used by the Trip Agent | `gpt-4o` |
| `TRIP_AGENT_USE_LLM` | root `.env` | Set to `0` to force the no-LLM fallback | `1` |
| `TRIP_AGENT_ALLOW_WEATHER` | root `.env` | Set to `0` to disable live weather calls | `1` |
| `CORS_ORIGINS` | root `.env` | Extra comma-separated origins allowed by the API | `localhost:8443`, `localhost:5173` |
| `BACKEND_HOST` / `BACKEND_PORT` | root `.env` | FastAPI bind address | `127.0.0.1` / `8000` |
| `VITE_API_URL` | `DressMe UI Blueprint/.env` | Backend base URL used by the frontend | `http://localhost:8000` (the launcher uses `127.0.0.1`) |
| `FRONTEND_PORT`, `PYTHON`, `FRONTEND_PM` | shell | Overrides for `scripts/dev-all.mjs` | `8443`, `python`/`python3`, `pnpm` |

Start the FastAPI backend and the existing Vite frontend together:

```bash
npm run dev:all
```

- HelpMePack UI: `http://localhost:8443`
- API docs: `http://127.0.0.1:8000/docs`
- Health check: `http://127.0.0.1:8000/api/health`

The launcher reuses ports that are already running and stops both services when
you press `Ctrl+C`.

Backend tests, frontend typecheck, and production build:

```bash
npm run test:backend
npm run typecheck:frontend
npm run build:frontend
```

The HelpMePack page supports both the existing manual form and a new natural
language "AI description" mode. See
`packing_backend/trip_agent/README.md` for the API endpoints, session model, and
Trip Agent architecture.

---

## Disclaimer / Project Status

DressMe is **under active development**. The prototype, architecture, AI components, and feature scope may change as the project progresses. The seven business objectives and the multi-agent direction described above represent the current understanding of the product and are subject to revision. Only the Help Me Pack (BO7) flow described in [Implemented: Help Me Pack (BO7)](#implemented-help-me-pack-bo7) is implemented end to end; everything else is design intent, not evidence of shipped functionality.
