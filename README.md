# DressMe

**Your smart wardrobe, your personal fashion assistant.**

DressMe is a smart wardrobe ecosystem designed primarily for the **Tunisian market**. The idea is simple: most people own more clothes than they wear, forget what they already own, and end up buying duplicates. DressMe turns a physical wardrobe into a structured, queryable digital one, then uses that understanding to help with everyday decisions — what to wear, what to pack, what to buy, and what to let go.

> **Project status — please read first.**
> This repository currently contains the **UI / Figma prototype** of DressMe. It is the visual and UX reference for the future application, not the application itself. Product, architectural, and AI decisions are still under discussion and are **not finalized**. Nothing described in the roadmap or AI sections below is implemented yet.

---

## Table of Contents

- [GitHub Rules for the Team](#github-rules-for-the-team)
- [Project Overview](#project-overview)
- [Business Objectives](#business-objectives)
- [AI & Multi-Agent Architecture](#ai--multi-agent-architecture)
- [RAG System](#rag-system)
- [Running the RAG API](#running-the-rag-api)
- [RAG Configuration](#rag-configuration)
- [RAG Evaluation](#rag-evaluation)
- [Troubleshooting](#troubleshooting)
- [Prototype](#prototype)
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

**What this repository is:** the Figma-derived UI prototype that will serve as the reference implementation of the future frontend. The interface is already navigable and covers the main flows described below.

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

## RAG System

The AI Stylist is backed by a Retrieval-Augmented Generation service in `rag_backend/`. It retrieves passages from a curated corpus of fashion books, grounds the answer in those passages, and returns inline citations.

> **Scope.** This is a fashion-knowledge RAG, not a wardrobe retriever. It does not yet retrieve the user's clothes, wear log, style profile, weather, or purchase history. Those data sources remain future work.

Full technical reference: [`docs/rag.md`](docs/rag.md).

### Architecture

```text
PDF corpus
   -> PyMuPDF extraction -> OCR fallback -> quality checks
   -> character chunking -> embeddings -> Supabase pgvector
Question
   -> optional LLM query rewrite -> vector + full-text search
   -> Reciprocal Rank Fusion -> top passages as [S1]...[Sn]
   -> LLM answer with inline citations -> FastAPI -> AI Stylist UI
```

### Corpus and index

| Metric | Current value |
|---|---:|
| PDFs | 38 |
| Pages extracted | 6,600 |
| Extracted characters | 10,729,040 |
| OCR pages | 1,281 |
| Empty pages | 675 |
| Extraction errors | 0 |
| Indexed chunks | 14,574 |
| Embedding model | `sentence-transformers/all-MiniLM-L6-v2` |
| Embedding dimension | 384 |
| Embedding version | `sentence-transformers/all-MiniLM-L6-v2-v1` |
| Vector store | Supabase Postgres + pgvector |
| Vector index | HNSW, cosine distance |

OCR was run on five scanned or low-text books: `clothing_for_women_1916.pdf`, `Color Harmony Workbook.pdf`, `J.J. Pizzutos Fabric Science...pdf`, `scarves.pdf`, and `Textilepedia...pdf`.

> **Corpus reproducibility.** The current local corpus has 38 PDFs, but 19 of them are currently untracked in git. A fresh clone may index only the committed PDFs until those files are added or fetched.

### Ingestion and chunking

| Parameter | Value |
|---|---|
| PDF input folder | `rag_backend/ingestion/pdfs/` |
| Extraction | PyMuPDF text layer |
| OCR fallback | Tesseract, triggered below 24 characters, 200 DPI, `eng` |
| Chunk unit | Characters, not tokens |
| Chunk size | 1,000 characters |
| Chunk overlap | 150 characters |
| Minimum chunk | 40 characters |
| Boundary handling | Split at the last space after the first half of the chunk |
| Cross-page chunks | No; each page is chunked independently |
| Chunk ID | `{slug(source)}-p{page}-c{chunk_index}` |
| Embedding batch | 32 |
| Index batch | 250 |

Each chunk stores the source, page, title, author, section, category, topics, document ID, chunk index, content hash, embedding model/version, and OCR flag. Topic tags are produced by deterministic keyword matching.

The extractor caches every PDF by file SHA-256 plus OCR settings in `rag_backend/data/extraction_cache/`. Runs are resumable: checkpoints are written every 25 pages, so stopping mid-run loses at most about 25 pages of OCR work.

### Storage

| Artifact | Location |
|---|---|
| Source PDFs | `rag_backend/ingestion/pdfs/` |
| Extracted pages | `rag_backend/data/extracted_pages.json` |
| Chunks | `rag_backend/data/chunks.jsonl` |
| Embedded chunks | `rag_backend/data/embedded_chunks.jsonl` |
| Extraction cache | `rag_backend/data/extraction_cache/` |
| Quality report | `rag_backend/data/quality_report.json` |
| Evaluation results | `rag_backend/data/evaluation_results.json` |
| Conversations | `rag_backend/data/conversations.sqlite3` |
| Knowledge index | Supabase `public.knowledge_chunks` |
| Vector + keyword RPCs | Supabase `match_knowledge_chunks`, `search_knowledge_chunks` |

`rag_backend/data/` is gitignored. Docker persists `/data` and the Hugging Face cache as volumes.

### Retrieval and answering

1. Optionally rewrite the question with the LLM (last four history messages, max 80 tokens).
2. Embed the query with the same 384-dimension model.
3. Run cosine vector search and English full-text search, each with 30 candidates.
4. Fuse the lists with Reciprocal Rank Fusion:

```text
score(chunk) = sum over lists of 1 / (60 + rank_in_list)
```

5. Keep the top `top_k` passages, filter weak matches, and build a context capped at 12,000 characters.
6. Ask the LLM to answer using `[S1]`, `[S2]`, ... citations.
7. Return the answer, deduplicated sources, citations, rewritten query, and `grounded` flag.

| Setting | Default |
|---|---:|
| `RAG_TOP_K` | 5 |
| `RAG_CANDIDATE_K` | 30 |
| `RAG_MIN_SIMILARITY` | 0.25 |
| `RAG_HYBRID_ENABLED` | true |
| `RAG_RRF_CONSTANT` | 60 |
| `RAG_MAX_CONTEXT_CHARS` | 12,000 |
| `QUERY_REWRITE_ENABLED` | true |

`grounded` is currently a heuristic: true when the answer contains at least one valid citation. It does not prove that the cited text supports the claim.

### API

| Endpoint | Method | Purpose |
|---|---|---|
| `/` | GET | Service metadata |
| `/health` | GET | Supabase and LLM health |
| `/ask` | POST | Grounded answer |
| `/ask/stream` | POST | SSE streamed answer |
| `/conversations` | POST | Create conversation |
| `/conversations/{id}` | GET | Read history |
| `/conversations/{id}` | DELETE | Delete conversation |

Authentication is optional and controlled by `RAG_API_KEY`. Clients send `X-API-Key: <key>` or `Authorization: Bearer <key>`. The UI uses `VITE_RAG_API_KEY`.

The default rate limit is 30 requests per minute per IP and path. It is in-memory and assumes a single API instance.

---

## Running the RAG API

Prerequisites:

- Python 3.12.
- A Supabase project with the migrations applied.
- An OpenAI-compatible API key.
- Tesseract OCR for scanned PDFs.
- Node.js and pnpm for the UI.

Configure the backend by copying `.env.example` to `.env` and filling in:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `OPENAI_API_KEY` or `LLM_API_KEY`
- `LLM_MODEL`
- `RAG_API_KEY` (recommended outside local development)

Start the API:

```powershell
cd rag_backend
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

Or run it with Docker:

```powershell
docker compose up -d --build rag-api
```

Configure the UI in `DressMe UI Blueprint/.env`:

```text
VITE_API_URL=http://localhost:8000
VITE_RAG_API_KEY=<same value as RAG_API_KEY>
```

Then start the UI:

```powershell
cd "DressMe UI Blueprint"
pnpm dev
```

The Vite server runs on `http://localhost:8443` by default. Restart the API and Vite after changing environment variables.

### Adding or updating PDFs

1. Put the PDFs in `rag_backend/ingestion/pdfs/`.
2. Run the pipeline from `rag_backend`.

Full run:

```powershell
python pipeline.py
```

OCR only the scanned books:

```powershell
python pipeline.py --ocr-only Color,Textilepedia,Fabric,clothing_for_women,scarves
```

Useful options:

| Option | Effect |
|---|---|
| `--ocr-only <substrings>` | OCR only PDFs whose filename matches one of the comma-separated substrings |
| `--refresh` | Re-extract every PDF and overwrite cache entries |
| `--no-cache` | Ignore the extraction cache |
| `--prune` | Delete chunks for PDFs no longer present |
| `--no-ocr` | Disable OCR entirely |
| `--skip-extract` | Reuse `extracted_pages.json` |
| `--skip-embed` | Reuse `embedded_chunks.jsonl` |
| `--skip-index` | Stop before writing to Supabase |

Stopping and resuming is safe: rerun the same command. Completed PDFs are reused from the cache, and the interrupted PDF resumes from its last page checkpoint.

Verify the index:

```powershell
python verify_setup.py
```

This checks the table, metadata columns, vector RPC with `min_similarity`, keyword RPC, and embedding version.

---

## RAG Configuration

| Variable | Default | Purpose |
|---|---|---|
| `SUPABASE_URL` | required | Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | required | Server-side Supabase key |
| `OPENAI_API_KEY` / `LLM_API_KEY` | required | LLM provider key |
| `LLM_MODEL` | required | Answer and rewrite model |
| `LLM_BASE_URL` | empty | Optional OpenAI-compatible endpoint |
| `EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | Embedding model |
| `EMBEDDING_VERSION` | model name + `-v1` | Index version marker |
| `EMBEDDING_BATCH_SIZE` | 32 | Embedding batch size |
| `CHUNK_SIZE` | 1000 | Chunk size in characters |
| `CHUNK_OVERLAP` | 150 | Chunk overlap in characters |
| `RAG_TOP_K` | 5 | Final passages returned |
| `RAG_CANDIDATE_K` | 30 | Candidates per retrieval method |
| `RAG_MIN_SIMILARITY` | 0.25 | Vector similarity floor |
| `RAG_HYBRID_ENABLED` | true | Enable vector + keyword fusion |
| `RAG_RRF_CONSTANT` | 60 | RRF constant |
| `RAG_MAX_CONTEXT_CHARS` | 12000 | Context budget |
| `QUERY_REWRITE_ENABLED` | true | LLM query rewriting |
| `OCR_ENABLED` | true | Enable OCR fallback |
| `OCR_MIN_CHARS` | 24 | OCR trigger threshold |
| `OCR_DPI` | 200 | OCR render DPI |
| `OCR_LANGUAGE` | eng | Tesseract language |
| `TESSERACT_CMD` | auto-detected | Explicit `tesseract.exe` path |
| `RAG_EXTRACTION_CACHE_DIR` | `data/extraction_cache` | Per-PDF cache directory |
| `RAG_API_KEY` | empty | Shared API secret; empty disables auth |
| `RAG_API_KEY_HEADER` | `X-API-Key` | API key header name |
| `RAG_RATE_LIMIT_PER_MINUTE` | 30 | Requests per minute per IP/path |
| `CORS_ORIGINS` | localhost 5173 + 8443 | Allowed UI origins |
| `VITE_API_URL` | `http://localhost:8000` | UI API base URL |
| `VITE_RAG_API_KEY` | empty | UI API key |

Security note: `VITE_*` values are embedded in the browser bundle. The UI key is demo-level gating, not real secrecy. Production should use a server-side proxy.

---

## RAG Evaluation

The golden set contains 12 fashion questions in `rag_backend/evaluation/golden_qa.jsonl`.

```powershell
cd rag_backend
python -m evaluation.evaluate --top-k 5
python -m evaluation.evaluate --top-k 5 --judge
```

Current retrieval results:

| Metric | Value |
|---|---:|
| questions | 12 |
| hit@k | 91.67% |
| MRR@k | 85.42% |
| context precision | 71.67% |

`--judge` adds LLM-based faithfulness, answer relevance, and citation accuracy. The saved `evaluation_results.json` currently contains retrieval metrics only. The default evaluation calls `retrieve()` directly, so it does not exercise production query rewriting.

Known weak spots: `color-harmony` still misses the expected source, and `work-clothes` ranks its relevant source low. Fabric and wool questions improved after OCR and now hit.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Tesseract OCR binary not found` | Install Tesseract or set `TESSERACT_CMD`; verify with `tesseract --version` |
| `401` from `/ask` | Send `X-API-Key` or Bearer token; restart the API after changing `.env` |
| `503` from `/ask` | Check `/health`; run `python verify_setup.py` |
| Embedding version mismatch | Re-run the pipeline and restart the API |
| Scanned PDFs index as empty | Enable OCR for the file with `--ocr-only`; inspect `quality_report.json` |
| OCR is slow | Use `--ocr-only`; reruns reuse the cache and resume checkpoints |
| UI cannot reach the API | Check `VITE_API_URL` and `CORS_ORIGINS`; restart Vite after env changes |
| API key visible in browser | Use a server-side proxy for production |

For the full technical reference, see [`docs/rag.md`](docs/rag.md).

---

## Prototype

This repository contains the DressMe **UI / Figma prototype**, built as a React + Vite + Tailwind application from the Figma Make design. It exists to make the product tangible and testable before the technical implementation is decided.

The prototype is used to:

- **Validate the user experience** — test whether the flows are understandable and worth building.
- **Visualise the features** — show what each of the 7 business objectives looks like as an interface.
- **Define navigation and application flows** — settle the information architecture before a backend constrains it.
- **Demonstrate the 7 BOs** — give concrete form to each objective.
- **Provide a foundation for the technical implementation** — act as the visual and UX reference the real frontend is built against.

Most prototype screens still use hard-coded sample data. The **AI Stylist** screen is the exception: it is connected to the RAG API in `rag_backend/` and returns grounded answers with sources. Wardrobe items, weather, scores, and the other feature screens remain illustrative placeholders. The prototype will keep evolving as product and technical decisions are refined.

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

**Done / in progress**

- Product ideation completed around the 7 business objectives.
- UI/UX prototype under development from the Figma design.
- Core navigation and the main feature flows implemented as interactive prototype screens.
- RAG backend implemented: PDF ingestion, OCR, chunking, embeddings, hybrid retrieval, grounded answers, citations, and streaming.
- Supabase knowledge index populated with 38 PDFs and 14,574 chunks.
- AI Stylist connected to the RAG API.
- Extraction cache and resumable OCR pipeline in place.
- Golden-set evaluation and RAG CI (Ruff + pytest) in place.

**Still open**

- The full technical architecture is not finalized.
- The multi-agent approach is planned but not finalized — agent boundaries, models, and orchestration are unresolved.
- Wardrobe CV, personal wardrobe retrieval, and the wardrobe data model are not implemented.
- RAG is not yet multilingual (English corpus and English full-text search).
- Production hardening is incomplete: server-side API proxy, shared rate limiting, multi-instance conversation storage, and observability.
- Answer faithfulness/relevance evaluation (`--judge`) is not part of CI yet.

**This is not a finished or production-ready product.**

---

## Roadmap

Indicative only — the order and content may change as decisions are made.

1. **UI / Figma prototype** — *(current)*
2. **UX validation and refinement** — user testing, flow fixes, design system consolidation
3. **Frontend implementation** — production app, real routing, state management, API layer, split into the feature folders described in the GitHub rules
4. **Backend and data architecture** — wardrobe/item schema, user accounts, wear logs, storage for images
5. **Wardrobe computer vision pipeline** — detection, segmentation, background removal, classification, attribute extraction (BO1)
6. **Recommendation and contextual intelligence** — compatibility scoring, occasion/weather conditioning, ranking (BO4), gap and redundancy analysis (BO2, BO3)
7. **Multi-agent architecture integration** — agent definitions, orchestration, shared memory, explanation layer (BO5); the grounded RAG knowledge layer is already implemented
8. **Testing and evaluation** — CV accuracy, recommendation quality, RAG faithfulness, agent task evaluation, user studies
9. **Iterative refinement** — feedback-driven improvement across the pipeline

---

## Repository Structure

The structure below is **indicative and will change** as the prototype transitions into the full application:

```text
DressMe/
├── DressMe UI Blueprint/  # React + Vite + Tailwind prototype
│   └── src/
│       ├── main.tsx
│       ├── App.tsx        # Prototype screens and AI Stylist integration
│       ├── index.css
│       └── features/      # Created as features are split out
├── rag_backend/           # RAG API, ingestion, retrieval, evaluation
│   ├── app.py             # FastAPI application
│   ├── pipeline.py        # extract -> chunk -> embed -> index
│   ├── ingestion/
│   │   ├── pdfs/          # Source PDF corpus
│   │   ├── pdf_extractor.py
│   │   ├── chunker.py
│   │   ├── embedder.py
│   │   ├── indexer.py
│   │   └── quality.py
│   ├── rag/               # retriever, query rewrite, LLM, Supabase
│   ├── evaluation/        # golden QA set and metrics
│   ├── tests/
│   └── data/              # Generated artifacts; gitignored
├── supabase/
│   └── migrations/        # knowledge_chunks, RPCs, RLS, indexes
├── docs/
│   └── rag.md             # Full RAG technical reference
├── .github/workflows/
│   └── rag-ci.yml         # Ruff + pytest for rag_backend
├── docker-compose.yml     # rag-api service
├── .env.example
├── dashboard.png
├── wardrobe.png
├── helpmepack.png
└── README.md
```

The generated RAG artifacts in `rag_backend/data/` (extracted pages, chunks, embeddings, extraction cache, quality report, evaluation results, and conversations) are gitignored and recreated by the pipeline.

### Running the prototype

```bash
cd "DressMe UI Blueprint"
pnpm install
pnpm dev
```

Requires Node.js and pnpm (versions pinned in `.mise.toml`). The AI Stylist screen also requires the RAG API to be running; see [Running the RAG API](#running-the-rag-api).

---

## Disclaimer / Project Status

DressMe is **under active development**. The prototype, architecture, AI components, and feature scope may change as the project progresses. The seven business objectives and the multi-agent direction described above represent the current understanding of the product and are subject to revision.

The RAG service is implemented and usable, but it is not production-hardened: it is not yet wardrobe-aware, multilingual, or fully evaluated for answer faithfulness, and the demo API key is exposed to the browser. Everything else in this README should not be read as evidence of implemented functionality.
