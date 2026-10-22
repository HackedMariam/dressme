# DressMe — Implemented Agent Prototypes

**Advanced Data Science Project · Agent Implementation Report**

This report documents three implemented prototypes in the DressMe repository:

| # | Idea | Branch | Evidence |
|---|---|---|---|
| 01 | RAG AI Stylist | `rag/try1` (`5f7f6b4`) | `rag_backend/`, `supabase/`, AI Stylist UI |
| 02 | Trip Agent / Help Me Pack | `helpmepack/try1` (`8d90269`) | `packing_backend/trip_agent/`, HelpMePack UI |
| 03 | Avatar & Try-On | `avatar/try1` (`22eebcb`) + current working tree | `backend/`, Blender/MPFB2, MediaPipe, Three.js |

The third section also covers the uncommitted two-photo capture, SciPy silhouette-fitting, MPFB detail-target, and optional GPT-4o Vision work currently present in the working tree (`backend/vision.py`, `backend/optimizer.py`, `backend/mpfb_details.py`, `backend/mpfb_targets.json`, `backend/body_scan.py`, `pose.ts`, `bodyPhotos.ts`, `silhouette.ts`, `bodyDetails.ts`, `questionnaire.ts`, and their tests). That work is explicitly labelled as current, uncommitted prototype work.

> **What is real.** Each section is based on code and artifacts that exist in the repository. The report separates implemented behaviour from limitations and future work. No API keys or secrets are included.

**Companion deck:** [`agent-report.pptx`](agent-report.pptx) - 27 slides, 16:9, matching the DressMe design language.  
**Pipeline assets:** [`agents-report-assets/`](agents-report-assets/).

---

## Executive summary

DressMe is a smart-wardrobe ecosystem for the Tunisian market. The repository contains three different kinds of intelligence:

1. **A grounded knowledge agent.** The RAG AI Stylist answers fashion questions from a curated book corpus and returns inline citations. It uses hybrid retrieval over 14,574 chunks.
2. **A task-oriented planning agent.** The Trip Agent interprets a trip request, calls deterministic tools, fetches weather, runs a CP-SAT packing optimizer, and produces a trip capsule and checklist.
3. **A visual body and try-on agent.** The Avatar pipeline estimates body shape from a front/side photo pair or questionnaire, optionally asks GPT-4o Vision for a relative second opinion, can refine the body with a SciPy silhouette-fitting optimizer, regenerates a body-shaped avatar in Blender, and builds garments from the generated body surface for 3D try-on.

The three prototypes deliberately use different intelligence strategies. The RAG agent is language-and-retrieval centric. The Trip Agent is neuro-symbolic: the LLM orchestrates, while Python and OR-Tools compute. The Avatar pipeline is deterministic computer vision and geometry by default, with an optional GPT-4o Vision second opinion that never replaces the measurements.

---

## 1. RAG AI Stylist

**Branch:** `rag/try1`  
**Role in DressMe:** grounded fashion-knowledge layer behind the AI Stylist.  
**Primary entry points:** `rag_backend/app.py`, `rag_backend/rag/rag_service.py`, `rag_backend/rag/retriever.py`.

### 1.1 LLM used

The answer and query-rewrite model is selected through `LLM_MODEL` and called through an OpenAI-compatible Chat Completions client (`rag_backend/rag/llm_client.py`). The repository environment currently sets `LLM_MODEL=gpt-4o`; the tracked `.env.example` uses `gpt-4o-mini` as a cheaper default. The model is therefore configurable rather than hard-coded.

| Aspect | Implementation |
|---|---|
| Provider | OpenAI-compatible API (`LLM_API_KEY` or `OPENAI_API_KEY`, optional `LLM_BASE_URL`) |
| Current repo model | `gpt-4o` |
| Example/default model | `gpt-4o-mini` in `.env.example` |
| Answer temperature | `0.2` (`LLM_TEMPERATURE`) |
| Rewrite temperature | `0.0` |
| Max answer tokens | `900` |
| Timeout / retries | 45 s, 2 retries with exponential backoff |
| Embedding model | `sentence-transformers/all-MiniLM-L6-v2`, 384 dimensions |

**Why this choice.** The agent needs two distinct behaviours from the same model: a cheap, deterministic query rewrite, and a careful grounded answer that respects retrieved evidence. GPT-4o-class models follow negative constraints well (“do not invent citations”, “say when the context is insufficient”), handle multilingual user questions, and support streaming. The low answer temperature keeps citations and advice stable. The embedding model is deliberately separate: retrieval quality is optimized with a small sentence-transformer rather than an LLM embedding.

No fine-tuning is used.

### 1.2 Memory

The RAG agent uses four memory layers:

| Memory layer | What is stored | Where | Lifetime |
|---|---|---|---|
| Conversation memory | User/assistant messages, sources, citations, rewritten query | SQLite in WAL mode (`conversations.py`) | Persistent |
| Prompt context | Last 8 messages for answering, last 4 for query rewriting | `rag_service.py`, `query_rewrite.py` | Per request |
| Knowledge memory | 14,574 embedded chunks from 38 fashion PDFs | Supabase Postgres + pgvector | Persistent |
| Client memory | Conversation ID and rendered chat messages | Browser `localStorage` (`dressme.chat.v1`) | Until cleared |

The SQLite schema stores conversations and messages with source metadata and rewritten queries. The browser restores the conversation after a refresh. The knowledge base is separate from user data: the RAG does **not** retrieve the user's wardrobe, wear log, profile, weather, or purchase history yet.

This is a deliberate boundary: the current agent is a fashion-knowledge assistant, not yet a personal-wardrobe assistant.

### 1.3 Actions

The implemented agent can:

1. Accept a natural-language fashion question (1–2,000 characters).
2. Rewrite vague or context-dependent questions into retrieval-friendly queries.
3. Embed the rewritten query with the same 384-dimensional model used at ingestion.
4. Run vector search and English full-text search in parallel.
5. Fuse both result lists with Reciprocal Rank Fusion.
6. Filter weak matches by a minimum cosine similarity.
7. Build a source-labelled context block (`[S1]`, `[S2]`, ...) capped at 12,000 characters.
8. Generate an answer that cites source-backed claims.
9. Return deduplicated sources, citations, the rewritten query, and a grounded flag.
10. Stream the answer token-by-token over Server-Sent Events.
11. Create, read, and delete conversation histories.
12. Refuse to answer when retrieval has no credible evidence.

The “no information” path is important: if retrieval returns nothing, the service returns a fixed answer with `grounded: false` instead of letting the model improvise.

### 1.4 Tools

| Tool / service | Purpose |
|---|---|
| FastAPI | `/ask`, `/ask/stream`, `/conversations`, `/health` |
| OpenAI Python SDK | Query rewriting and answer generation |
| Supabase Postgres + pgvector | Storage of 14,574 chunks and 384-dimensional embeddings |
| Supabase RPCs | `match_knowledge_chunks`, `search_knowledge_chunks` |
| SentenceTransformers | Query and document embeddings |
| PyMuPDF (`fitz`) | PDF text extraction |
| Tesseract OCR | Fallback for scanned pages (1,281 pages OCR’d) |
| SQLite | Conversation and message persistence |
| Server-Sent Events | Streaming `sources`, `token`, `done`, and `error` events |
| React/Vite AI Stylist | Chat UI, source display, `localStorage` restore |
| Pytest + Ruff + GitHub Actions | Retrieval, API, quality, conversation and metric tests |

The ingestion pipeline is also a set of tools: extraction cache, quality report, chunker, embedder, indexer, and `verify_setup.py`.

### 1.5 Agent pipeline

![RAG AI Stylist pipeline](agents-report-assets/rag-agent-pipeline.png)

*Pipeline diagram generated from the implementation in `rag_backend/`.*

The production path is:

1. **Input.** The user asks a question in the AI Stylist.
2. **API boundary.** FastAPI validates the request, checks the optional `X-API-Key`, applies a 30-requests/minute sliding-window limit, and resolves or creates a conversation.
3. **Query rewrite.** The LLM rewrites the question using the last four messages. Failure falls back to the original question.
4. **Embedding.** The rewritten query is embedded with `all-MiniLM-L6-v2`.
5. **Hybrid retrieval.** Vector search and Postgres full-text search each return up to 30 candidates.
6. **Fusion.** Reciprocal Rank Fusion combines the lists (`1 / (60 + rank)`), deduplicates by `chunk_id`, and keeps the top `top_k` (default 5).
7. **Context assembly.** Passages are labelled `[S1]`...`[Sn]`, with source, page, title and section metadata, capped at 12,000 characters.
8. **Grounded generation.** GPT-4o answers under a six-rule system prompt that requires citations and forbids invented facts or citations.
9. **Citation parsing.** Only markers actually present in the answer become citations. `grounded` is true when at least one valid citation exists.
10. **Response.** The API returns the answer, sources, citations, conversation ID, rewritten query, and usage. The UI renders sources and stores the conversation locally.

The repository includes a retrieval evaluation on a 12-question golden set:

| Metric | Result |
|---|---:|
| Hit@5 | 91.67% |
| MRR@5 | 85.42% |
| Context precision | 71.67% |

Known weak spots are colour-harmony retrieval and low ranking for some work-clothes questions.

### 1.6 AI techniques used

| Technique | How it is used |
|---|---|
| **Retrieval-Augmented Generation (RAG)** | Answers are generated from retrieved book passages rather than model memory alone. |
| **Hybrid retrieval** | Cosine vector search plus Postgres full-text search, so semantic and keyword matches both contribute. |
| **Reciprocal Rank Fusion** | Merges the two ranked lists without needing a learned reranker. |
| **LLM query rewriting** | Converts vague conversational questions into specific search queries using recent context. |
| **Grounding and inline citations** | The prompt requires `[S1]`-style markers; citations are parsed and mapped back to source metadata. |
| **Extractive ingestion with OCR** | PyMuPDF extracts native text; Tesseract recovers low-text scanned pages. |
| **Metadata enrichment** | Each chunk stores source, page, title, author, section, category, topics, OCR flag, content hash, and embedding version. |
| **Offline evaluation** | Hit@k, MRR@k, context precision, citation accuracy, and groundedness on a golden question set. |
| **Graceful refusal** | A similarity floor and empty-retrieval path prevent unsupported answers. |

**Not used:** fine-tuning, a cross-encoder reranker, metadata filters at query time, multilingual retrieval, personal-wardrobe retrieval, and multi-agent orchestration.

### 1.7 Limitations

- The corpus and full-text search are English-only.
- The agent is not wardrobe-aware; it cannot answer “what should I wear from my own closet?”
- Chunking is page-scoped and character-based, so semantic units can split.
- No cross-encoder reranker and no query-time metadata filters.
- `grounded` is heuristic: it checks that a citation exists, not that the cited text supports the claim.
- The API key is client-bundled in the demo UI; production needs a server-side proxy.
- SQLite conversations and in-memory rate limiting assume a single API instance.
- The Docker healthcheck makes a paid LLM call every 30 seconds.

---

## 2. Trip Agent / Help Me Pack

**Branch:** `helpmepack/try1`  
**Role in DressMe:** planning agent for BO7, “Help Me Pack”.  
**Primary entry points:** `packing_backend/trip_agent/agent.py`, `tools.py`, `backend/main.py`, `HelpMePack.tsx`.

### 2.1 LLM used

**OpenAI GPT-4o** is the default model (`DEFAULT_MODEL = "gpt-4o"` in `packing_backend/trip_agent/config.py`), accessed through native Chat Completions function calling.

| Aspect | Implementation |
|---|---|
| Model | `gpt-4o`, override with `LLM_MODEL` |
| Tool use | Native function calling, `tool_choice="auto"` |
| Temperature | `0` |
| Structured extraction | `response_format={"type": "json_object"}`, with one plain retry for compatible providers |
| Timeout / retries | 45 s, one retry |
| Agent loop limit | 12 iterations |
| Fallback | Deterministic regex parser and dependency-completion loop when the LLM is unavailable |

**Why GPT-4o.** The agent must do three things at once: interpret messy multilingual trip descriptions, choose among ten tools with valid JSON arguments, and explain the result without inventing data. GPT-4o handles native tool calling and strict JSON well, and `temperature=0` makes the planning workflow repeatable. The model is configurable, so a compatible provider can replace it.

No fine-tuning is used.

### 2.2 Memory

| Memory type | What is stored | Where | Lifetime |
|---|---|---|---|
| Working memory | Validated trip, weather, wardrobe snapshot, daily requirements, optimizer result, capsule, checklist, tool history, errors, status | `AgentState` Pydantic model | One session |
| Conversation memory | User and assistant transcript; last 16 messages injected into the prompt | `state.messages` | One session |
| Session memory | `TripAgent` instance keyed by `session_id`, protected by a lock | In-memory `SessionStore` in `backend/main.py` | Until backend restart |
| Client memory | Current `session_id` | Browser `localStorage` | Until cleared |
| Separate knowledge memory | Fashion-knowledge chunks and RAG conversations | `rag_backend/` | Persistent, not wired into this agent |

The agent also injects a compact state summary (status, missing fields, weather source, optimization status, checklist counts) into each LLM turn. Stale downstream state is explicitly invalidated when trip details change. There is no long-term user profile or wear-history memory and no cross-session learning.

### 2.3 Actions

The Trip Agent implements the complete packing workflow:

1. Parse free text or a structured form into destination, dates, duration, activities, occasions, dress code, and luggage limit.
2. Ask one concise clarification question when fields are missing, instead of inventing values.
3. Fetch daily weather for the destination and dates.
4. Load the user’s wardrobe and compatibility data.
5. Translate weather, activities, and formality into optimizer-compatible daily requirements.
6. Run the CP-SAT optimizer to select a minimal set of maximally combinable items.
7. Produce a trip capsule with daily outfits, selected items, total clothing weight, and optimization status.
8. Generate a checklist where every item starts `packed: false`.
9. Update trip details and re-optimize when the user changes the plan.
10. Mark items packed or unpacked without re-running the optimizer.
11. Diagnose `INFEASIBLE` results and propose recovery options without silently relaxing hard constraints.
12. Explain the result using tool output: status, item count, weight, weather source, and checklist progress.
13. Optionally call a future Gap Agent hook.

It does not perform computer vision, purchase evaluation, outfit generation outside a trip, or persistent profiling.

### 2.4 Tools

The agent exposes ten native function-calling tools:

| Tool | Function | Backing resource |
|---|---|---|
| `get_trip_details` | Extract, merge, validate trip fields and report missing fields | GPT-4o JSON extraction + regex fallback |
| `get_weather` | Daily forecast | Open-Meteo geocoding + forecast API |
| `get_wardrobe` | Load and filter wardrobe items and role coverage | `wardrobe.csv`, `compatibility.csv` via pandas |
| `get_activity_requirements` | Build daily optimizer requirements | Deterministic rules in `requirements.py` |
| `optimize_trip` | Solve the packing problem | OR-Tools CP-SAT |
| `generate_checklist` | Create the checklist from the capsule | Pydantic models |
| `suggest_alternatives` | Diagnose infeasibility with a diagnostic solve | CP-SAT + wardrobe role analysis |
| `update_trip` | Edit trip details, invalidate stale state, optionally re-optimize | `tools.py` |
| `update_checklist` | Mark packed/unpacked without re-solving | `tools.py` |
| `check_gaps` | Optional Gap Agent interface | Injected checker or mock |

External services and infrastructure: OpenAI API, Open-Meteo, OR-Tools CP-SAT, pandas/CSV, FastAPI, Pydantic, React/Vite, and browser `localStorage`.

### 2.5 Agent pipeline

![Trip Agent pipeline](agents-report-assets/trip-agent-pipeline.png)

*Pipeline screenshot from the Help Me Pack branch (`docs/agent-pipeline.png`).*

The implemented HelpMePack form:

![Help Me Pack UI](agents-report-assets/helpmepack-ui.png)

*Actual Help Me Pack UI: destination, dates, trip type, dress code, luggage limit, and the generate action.*

End-to-end flow:

1. **User input.** Manual form or free text, e.g. “Paris, 5 days, sightseeing and a formal dinner, 8 kg”.
2. **FastAPI.** `POST /api/trips` validates the request, creates or retrieves a session, and locks it while the agent runs.
3. **Trip Agent.** Builds a prompt from the system rules, compact state summary, last 16 messages, and ten tool schemas.
4. **GPT-4o.** Chooses the next tool and produces arguments; it does not compute the packing itself.
5. **Tool loop.** Pydantic validates every argument, Python enforces dependencies, tool failures become structured errors, and the loop is bounded to 12 iterations.
6. **State and response.** The agent returns trip details, weather, daily requirements, capsule, checklist, suggestions, and errors.
7. **UI render.** Weather cards, extracted details, daily outfits, capsule summary, and an interactive checklist.
8. **Follow-up.** Checklist updates call `PATCH /checklist/{item_id}` without re-optimizing; trip edits call `PATCH /trips/{session_id}` and can re-optimize.

Failure branches:

| Branch | Behaviour |
|---|---|
| Missing trip data | Ask one concise question; status becomes `needs_clarification`. |
| LLM unavailable | Deterministic regex parser and dependency-completion loop. |
| Weather unavailable | Explicitly labelled synthetic fallback, never presented as real. |
| Optimizer `INFEASIBLE` | Diagnostic solve, blocking constraints, concrete options; no silent relaxation. |

### 2.6 AI techniques used

| Technique | How it is used |
|---|---|
| **Agentic tool use / function calling** | GPT-4o selects among ten tools; Python validates and executes deterministic operations. The loop is custom-built, not LangChain/LangGraph. |
| **Advanced prompt engineering** | A ten-rule system prompt forbids invented data, enforces tool order, requires clarification, forbids silent constraint relaxation, and requires grounded final answers. |
| **Structured output + schema validation** | Trip extraction returns JSON; Pydantic validates and normalizes dates, activities, limits, and missing fields. |
| **Hybrid neuro-symbolic reasoning** | The LLM handles language and orchestration; CP-SAT handles the combinatorial optimization. The LLM never fabricates the packing result. |
| **Retrieval-Augmented Generation (RAG)** | The separate RAG layer is documented in section 1. It is not yet exposed as a Trip Agent tool. |
| **Graceful degradation / guardrails** | Labelled synthetic weather, regex fallback, bounded loop, structured tool errors, dependency checks, no silent constraint relaxation. |
| **Evaluation** | Offline tests cover extraction, clarification, weather fallback, requirements, optimization, infeasibility, updates, and checklist updates. |

**Not used:** LLM fine-tuning, RLHF, autonomous multi-agent orchestration, and real computer-vision integration.

### 2.7 Limitations

- Wardrobe and compatibility data are synthetic.
- Sessions are in-memory and disappear on backend restart.
- No authentication or persistent user profile.
- The RAG layer is not a wired Trip Agent tool.
- The computer-vision model referenced in `.env` is not wired into this agent.
- The full eight-agent DressMe architecture is still a proposal.

---

## 3. Avatar & Try-On Agent

**Branch:** `avatar/try1` plus current working tree  
**Role in DressMe:** body-aware visual try-on and outfit preview.  
**Primary entry points:** `backend/main.py`, `backend/blender/generate_avatar.py`, `backend/blender/generate_dressed_avatar.py`, `CustomizeAvatar.tsx`, `TryOnStudio.tsx`.

### 3.1 LLM used

The **measurement and geometry path does not use an LLM**. Body measurements come from local MediaPipe pose and silhouette analysis; avatar geometry comes from MPFB2 and Blender. That part is deterministic and runs in the browser plus the local backend.

The current working tree adds one **optional LLM second opinion**: GPT-4o Vision through `backend/vision.py`, exposed as `POST /api/body/vision`. It is consent-gated, sends the front and side photos to the OpenAI Chat Completions API, and returns:

- relative observations (`narrow` / `average` / `broad`, `short` / `average` / `long`),
- confidence values and photo-quality notes,
- bounded detail-target suggestions in `[-1, 1]`.

It is explicitly **not a tape measure**. The prompt forbids centimetres, the response is cleaned and clamped, and its suggestions are merged into the advanced detail sliders rather than replacing the local measurements. The local MediaPipe path continues to work when `OPENAI_API_KEY` is missing; the vision route then returns `503`.

Model selection is `OPENAI_VISION_MODEL`, falling back to `LLM_MODEL`, then `gpt-4o`. The request uses temperature `0.2`, JSON-object output, and a 90 s timeout.

The current working tree also includes an optional **SciPy silhouette-fitting optimizer** (`backend/optimizer.py`). It is not an LLM. It runs a Powell search over 15 controls (4 macro controls and 11 detail pairs), renders front/side body masks in Blender for each evaluation, and minimizes a combination of silhouette IoU loss and width-profile RMSE. The default budget is 36 evaluations, it takes roughly 3-5 minutes, and it returns optimized targets, details, fit metrics, and the best GLB.

| Path | Intelligence | Network |
|---|---|---|
| Front + side photos | MediaPipe Pose + Image Segmenter, height-scaled measurements | None; photos stay in the browser |
| Questionnaire fallback | Deterministic anthropometric estimator in `body_scan.py` | None |
| Optional second opinion | GPT-4o Vision relative observations + detail hints | OpenAI, only after consent |
| Optional silhouette fitting | SciPy Powell search over 15 controls, Blender mask loop | Local backend |
| Avatar generation | Blender 5.4 + MPFB2 macro and detail targets | Local backend |
| Garment generation | Procedural geometry from the actual body mesh | Local backend |

**Why this split.** A vision-language model is useful for relative visual judgments that are hard to encode as a formula, such as ?shoulders look broad? or ?the waist is not very defined.? It is not reliable for centimetres. The architecture therefore keeps precise measurement and mesh construction deterministic, and uses the VLM only as an optional, bounded second opinion. No fine-tuning is used.

### 3.2 Memory

| Memory type | What is stored | Where | Lifetime |
|---|---|---|---|
| UI working memory | Front/side photos, pose and silhouette analysis, measurements, detail sliders, generated URL, history | React state | Page session |
| Photo pair | Front and side images as browser object URLs | Browser memory | Until replaced or page closed |
| Saved looks | Up to 24 looks with label, garment IDs, wardrobe IDs, timestamp | Browser `localStorage` (`dressme.savedLooks.v1`) | Persistent |
| Backend job state | One active Blender job, parameter JSON, details JSON, temp GLB, job lock | `backend/main.py`, `backend/temp/` | Process / job |
| Optimizer job state | Async job, evaluation progress, best score, fitted targets/details | In-memory `_opt_jobs`, `backend/temp/opt_<id>/` | Process / job cleanup |
| Generated assets | `avatar_<jobId>.glb` files | `public/models/generated/` | 24 h TTL |
| Detail manifest | 128 whitelisted MPFB detail targets across torso, legs, arms, hips, stomach, etc. | `backend/mpfb_targets.json` | Versioned in repo |
| Garment catalog | 10 garments, 5 slots, geometry hints | `garments.json` shared by frontend and Blender | Versioned in repo |
| Optional vision result | Body shape, observations, quality, suggested details | Returned to the client; not persisted server-side | Request |

There is no user account, no durable body profile, and no cross-session wear history. The local photo path never uploads images. The optional GPT-4 Vision path sends the two photos to OpenAI only when the user explicitly consents; DressMe does not store them server-side. Generated GLBs are cleaned after 24 hours.

### 3.3 Actions

The avatar/try-on agent can:

1. Accept a front photo, a side photo, and a declared height.
2. Validate photo type and size, then run MediaPipe Pose locally.
3. Reject unreliable captures: missing person, low visibility, frontal photo in the side slot, or sideways photo in the front slot.
4. Run MediaPipe Image Segmenter to extract the body silhouette.
5. Convert silhouette widths to centimetres using the entered height.
6. Estimate shoulder, chest, waist, hip, thigh, calf, inseam, mass, and BMI.
7. Optionally request a consent-gated GPT-4o Vision analysis for relative observations and detail hints.
8. Fall back to the eight-question local estimator when photos are not available.
9. Map measurements to macro controls: `height`, `legLength`, `muscle`, `weight`, `proportions`, `cupsize`.
10. Map advanced controls to up to 128 whitelisted MPFB detail targets (waist, hips, torso depth, belly, thigh, calf, arm length, and others).
11. Submit a validated generation request to FastAPI.
12. Run Blender headless with MPFB2 to shape the body.
13. Apply detail targets after the macro shape, then apply the torso/leg post-process.
14. Build fitted garments from the generated body surface.
15. Export avatar + garments as one GLB and validate its magic bytes and size.
16. Serve the GLB from the Vite public folder.
17. Render the 3D result with rotate and zoom.
18. Compare the previous look, reuse a selection, and save a look.
19. Run one closed-loop correction pass: compare achieved body ratios with the captured target, nudge `muscle`/`legLength`, and regenerate once.

In addition, the current working tree can run an optional **SciPy silhouette-fitting job** (`POST /api/avatar/optimize`): it polls progress, adopts the fitted 15-control target set, and can use the best GLB directly. The fitting step is optional; the normal generate path remains available.

The garment catalogue is slot-based: one item per slot, a dress replaces top + bottom, and outerwear layers over a top.

### 3.4 Tools

| Tool / service | Purpose |
|---|---|
| MediaPipe Pose Landmarker | Pose landmarks, visibility, frontality, quality |
| MediaPipe Image Segmenter | Person silhouette from `selfie_segmenter.tflite` |
| OpenAI Vision (optional) | GPT-4o relative body observations and detail hints |
| FastAPI | `/api/health`, `/api/body/status`, `/api/body/questionnaire`, `/api/body/measurements`, `/api/body/vision`, `/api/avatar/generate`, `/api/avatar/optimize` |
| Pydantic | Request validation and bounds |
| Blender 5.4 headless | Runs the avatar and dressed-avatar scripts |
| MPFB2 | Macro body parameters, detail targets, shape-key baking, GLB export |
| `bpy` / `bmesh` | Mesh manipulation, vertex classification, garment shells |
| Three.js + react-three-fiber + drei | 3D preview, lighting, shadows, orbit controls |
| React + Vite | Customize and Try-On UI |
| `httpx` | OpenAI Vision client with timeout handling |
| SciPy + NumPy + Pillow | Silhouette fitting: Powell search, mask I/O, IoU, width profiles |
| Blender silhouette rendering | Transparent front/side masks for each optimizer evaluation |
| Pytest | Validation, GLB, body-scan, vision, detail-target, and optimizer tests |

The frontend and Blender share `garments.json`, so ids, slots, labels, colours, and geometry hints cannot drift apart. The detail manifest is validated by `mpfb_details.py`, which rejects arbitrary target names and caps details at 128.

### 3.5 Agent pipeline

![Avatar and Try-On pipeline](agents-report-assets/avatar-agent-pipeline.png)

*Pipeline diagram generated from the current implementation in `backend/` and the working tree.*

The complete path is:

1. **Input.** Front + side photos with a declared height, the questionnaire, or manual sliders.
2. **Local pose analysis.** MediaPipe returns landmarks. The app checks visibility and view-specific frontality, so a side photo cannot masquerade as a front photo.
3. **Local silhouette.** MediaPipe Image Segmenter extracts the body mask; row widths become centimetres after height scaling.
4. **Measurements.** The browser derives shoulder, chest, waist, hip, thigh, calf, inseam, mass, and BMI. These are estimates, not tape measurements.
5. **Optional second opinion.** With consent, `POST /api/body/vision` sends both photos to GPT-4o Vision. Its relative observations and bounded detail suggestions are merged into the advanced sliders.
6. **Optional silhouette fitting.** SciPy Powell search adjusts 15 macro/detail controls. Each evaluation runs Blender, renders front/side masks, and scores IoU plus width-profile error. It returns the best targets, details, fit metrics, and GLB.
7. **Mapping.** Measurements and fitted controls become MPFB macro targets and whitelisted detail targets.
8. **API validation.** FastAPI validates both dictionaries, validates the outfit against slot rules, and acquires a single-job lock.
9. **Blender body generation.** `generate_avatar.py` sets MPFB macros, reapplies macro details, loads detail targets, applies `legLength`, bakes shape keys, and exports a GLB.
10. **Dressed generation.** `generate_dressed_avatar.py` reads joint-cube landmarks, classifies skin vertices to anatomical segments, builds garment shells from the body surface, offsets them along normals, solidifies them, assigns materials, and exports one GLB.
11. **Validation and serving.** The backend checks GLB magic bytes and size, moves it into `public/models/generated/`, and returns the URL, applied details, and achieved metrics.
12. **3D preview.** Three.js loads the GLB, normalizes only implausible scales, and shows height in metres.
13. **Closed-loop correction.** The frontend compares desired and achieved ratios and triggers one regeneration if needed.

Actual rendered prototype output:

![Rendered dressed avatar, three-quarter view](agents-report-assets/avatar-dressed_threeq.png)

*Actual Blender render of `public/models/dressed_avatar.glb` using `backend/blender/render_preview.py`.*

### 3.6 AI techniques used

| Technique | How it is used |
|---|---|
| **Pose estimation** | MediaPipe landmarks, visibility and view-specific frontality checks reject bad photos. |
| **Image segmentation** | MediaPipe selfie segmenter extracts the body silhouette used for width/depth measurements. |
| **Height-scaled anthropometry** | Silhouette widths in pixels are converted to centimetres using the user?s height. |
| **Measurement-to-parameter mapping** | Measurements drive macro controls; side-view depth drives torso/hip detail targets. |
| **Vision-language second opinion** | Optional GPT-4o Vision returns relative observations and bounded detail hints, never centimetres. |
| **Silhouette fitting optimization** | Optional SciPy Powell search over 15 controls; each evaluation renders masks and scores IoU + width-profile error. |
| **Procedural garment generation** | Garments are built from the actual body mesh, not imported assets. Vertices are classified to anatomical segments, kept by region, offset along normals, and solidified. |
| **Closed-loop correction** | Achieved body ratios are compared with the capture target; `muscle` and `legLength` are nudged and the avatar is regenerated once. |
| **Guardrails** | Sideways/frontal photo checks, invalid garment combinations, oversized uploads, invalid detail names, and invalid GLBs are rejected. |

**Not used for geometry:** fine-tuning, skeletal skinning, morph targets, cloth simulation, and persistent body profiles. The exported GLB is a static mesh with baked shape keys and shared topology.

### 3.7 Limitations

- A single uncalibrated 2D photo cannot measure a body; photo-derived values are estimates, not tape measurements.
- Silhouette quality depends on clothing, pose, lighting, and background.
- Mass and BMI are inferred from width-to-height ratios unless the user edits them.
- The optional GPT-4 Vision path sends photos to OpenAI and depends on an API key, network, and quota.
- Silhouette fitting runs Blender many times, takes roughly 3-5 minutes, and defaults to 36 evaluations.
- The exported avatar has no skeleton, no morph targets, and no runtime skinning.
- Garments are procedural shells, not production cloth simulation.
- The wardrobe-to-garment mapping uses a small catalogue of 10 garments across 5 slots.
- Generated GLBs are cleaned after 24 hours; there is no durable user avatar profile.
- The backend is local-only (`127.0.0.1`) and has no authentication.

## 4. Cross-agent comparison

| Dimension | RAG AI Stylist | Trip Agent | Avatar / Try-On |
|---|---|---|---|
| Primary intelligence | Retrieval + grounded generation | LLM orchestration + CP-SAT | Computer vision + procedural geometry |
| LLM | GPT-4o (configurable) | GPT-4o (configurable) | Optional GPT-4o Vision second opinion |
| Core memory | SQLite conversations + pgvector corpus | AgentState + in-memory sessions | React state + localStorage + file cache |
| Main external service | Supabase / OpenAI | OpenAI / Open-Meteo | MediaPipe / OpenAI (optional) / Blender |
| Key AI technique | Hybrid RAG with citations | Native tool calling + neuro-symbolic optimization | Pose + silhouette + SciPy fitting |
| Output | Cited answer + sources | Trip capsule + checklist | Body-shaped GLB + 3D try-on |
| Evaluation | Golden-set retrieval metrics | Offline tool/optimizer tests | Validation tests + rendered previews |
| Status | Implemented | Implemented | Implemented; two-photo capture work is uncommitted |

### Why the differences are intentional

The three prototypes answer different questions:

- The RAG agent must **know** something and show its evidence.
- The Trip Agent must **decide and compute** under hard constraints.
- The Avatar pipeline must **construct** something geometrically correct.

Using an LLM for all three would make the system less reliable. The architecture keeps the LLM where language and explanation matter, and uses deterministic tools where correctness matters.

---

## 5. Prototype evidence and reproduction

### 5.1 Evidence map

| Area | Evidence |
|---|---|
| RAG | `rag_backend/app.py`, `rag/rag_service.py`, `rag/retriever.py`, `evaluation/`, `tests/`, Supabase migrations |
| Trip Agent | `packing_backend/trip_agent/`, `packing_backend/optimizer.py`, `backend/main.py`, `HelpMePack.tsx`, `docs/agent-pipeline.png` |
| Avatar | `backend/main.py`, `backend/blender/`, `pose.ts`, `silhouette.ts`, `bodyPhotos.ts`, `avatarApi.ts`, `CustomizeAvatar.tsx`, `TryOnStudio.tsx`, `garments.json` |
| Current uncommitted capture work | `backend/vision.py`, `backend/mpfb_details.py`, `backend/mpfb_targets.json`, `backend/tests/test_vision.py`, `backend/tests/test_mpfb_details.py`, `bodyPhotos.ts`, `silhouette.ts`, `bodyDetails.ts`, `questionnaire.ts` |

### 5.2 How to run

**RAG API**

```powershell
cd rag_backend
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

**Trip Agent**

```powershell
cd backend
uvicorn main:app --host 127.0.0.1 --port 8000
```

Then open the HelpMePack page in the Vite app.

**Avatar backend**

```powershell
cd backend
uvicorn main:app --host 127.0.0.1 --port 8000
```

The avatar generator needs the Blender path and `avatar.blend` configured in `backend/README.md`. The optional GPT-4 Vision route uses `OPENAI_API_KEY` (and optionally `OPENAI_VISION_MODEL`); without it, the local MediaPipe path still works. The optional silhouette fit is `POST /api/avatar/optimize` followed by `GET /api/avatar/optimize/{job_id}`.

**UI**

```powershell
cd "DressMe UI Blueprint"
pnpm dev
```

### 5.3 Verification commands

```powershell
# RAG tests
cd rag_backend
pytest

# Avatar backend tests
cd backend
pytest

# Trip Agent tests
cd packing_backend
pytest trip_agent/tests
```

---

## 6. Conclusion

The repository contains three working prototypes, not three theoretical architectures:

- **RAG** is a real grounded question-answering service with a 14,574-chunk index, hybrid retrieval, citations, streaming, and measured retrieval quality.
- **Trip Agent** is a real tool-using planner with ten tools, weather integration, a CP-SAT optimizer, a capsule, a checklist, and deterministic fallbacks.
- **Avatar / Try-On** is a real body-generation and garment-fitting pipeline, with local two-photo capture, optional GPT-4o Vision second opinions, SciPy silhouette fitting, MPFB macro/detail targets, procedural garments, a 3D viewer, and actual rendered output.

The main lesson is architectural: use the LLM for language and relative visual judgment, use retrieval for evidence, use solvers for constraints, and use geometry for bodies. The next steps are to connect the RAG layer to personal wardrobe data, connect the Trip Agent to the RAG and Gap Agent, replace synthetic wardrobe data with real user data, and add persistent profiles and production hardening.
