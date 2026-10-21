# DressMe RAG — Technical Reference

This document describes the Retrieval-Augmented Generation (RAG) system used by the DressMe AI Stylist. It covers the corpus, ingestion, chunking, embeddings, storage, retrieval, answer generation, API, evaluation, operations, and known limitations.

> **Scope.** The RAG currently retrieves from a curated corpus of fashion books. It does **not** retrieve the user's wardrobe, wear log, profile, weather, or purchase history. Personal wardrobe retrieval is a separate future capability.

---

## 1. Role in DressMe

The RAG is the grounded fashion-knowledge layer behind the AI Stylist. It:

- Answers style, fabric, occasion, travel, wardrobe, footwear, and sustainability questions.
- Grounds answers in retrieved book passages instead of relying only on the LLM.
- Returns inline citations (`[S1]`, `[S2]`, ...) and source metadata.
- Supports the trust-and-transparency objective by exposing evidence.
- Acts as an external knowledge source for recommendation and packing features.

It supports the conversational and recommendation goals of DressMe, but it is not yet connected to the user's personal wardrobe data.

---

## 2. Architecture

```text
PDF corpus
   |
   v
PyMuPDF text extraction
   |
   v (low-text pages)
Tesseract OCR fallback
   |
   v
Quality checks and repeated-line removal
   |
   v
Character-based chunking + metadata
   |
   v
SentenceTransformer embeddings (384 dimensions)
   |
   v
Supabase Postgres + pgvector (`knowledge_chunks`)
   |
   v
User question
   |
   v
Optional LLM query rewrite
   |
   v
Vector search + Postgres full-text search
   |
   v
Reciprocal Rank Fusion (RRF)
   |
   v
Top passages formatted as [S1]...[Sn]
   |
   v
LLM answer with inline citations
   |
   v
FastAPI `/ask` or SSE `/ask/stream`
   |
   v
AI Stylist UI
```

| Component | File |
|---|---|
| API | `rag_backend/app.py` |
| Configuration | `rag_backend/config.py` |
| PDF extraction / OCR | `rag_backend/ingestion/pdf_extractor.py` |
| Chunking | `rag_backend/ingestion/chunker.py` |
| Embeddings | `rag_backend/ingestion/embedder.py` |
| Quality and metadata helpers | `rag_backend/ingestion/quality.py` |
| Supabase indexing | `rag_backend/ingestion/indexer.py` |
| Retrieval | `rag_backend/rag/retriever.py` |
| Query rewrite | `rag_backend/rag/query_rewrite.py` |
| Grounded answers and citations | `rag_backend/rag/rag_service.py` |
| LLM client | `rag_backend/rag/llm_client.py` |
| Supabase client | `rag_backend/rag/supabase_client.py` |
| Conversation store | `rag_backend/conversations.py` |
| Rate limiter | `rag_backend/rate_limit.py` |
| Pipeline orchestration | `rag_backend/pipeline.py` |
| Evaluation | `rag_backend/evaluation/` |
| Database migrations | `supabase/migrations/` |
| UI integration | `DressMe UI Blueprint/src/App.tsx` |

---

## 3. Current corpus and index

| Metric | Value |
|---|---:|
| PDFs | 38 |
| Pages extracted | 6,600 |
| Extracted characters | 10,729,040 |
| OCR pages | 1,281 |
| Empty pages | 675 |
| Extraction errors | 0 |
| Indexed chunks | 14,574 |
| Embedding dimension | 384 |
| Embedding model | `sentence-transformers/all-MiniLM-L6-v2` |
| Embedding version | `sentence-transformers/all-MiniLM-L6-v2-v1` |
| Supabase table | `public.knowledge_chunks` |
| Vector index | HNSW, cosine distance |

OCR was applied to five scanned or low-text books:

| Document | Pages | Extracted characters |
|---|---:|---:|
| `clothing_for_women_1916.pdf` | 484 | ~714k |
| `Color Harmony Workbook.pdf` | 97 | ~59k |
| `J.J. Pizzutos Fabric Science...pdf` | 401 | ~1.25M |
| `scarves.pdf` | 104 | ~63k |
| `Textilepedia...pdf` | 249 | ~196k |

Before the OCR/reindex pass the index held 6,565 chunks; it now holds 14,574.

> **Corpus reproducibility.** The current local corpus has 38 PDFs, but 19 of them are currently untracked in git. A fresh clone may index only the committed PDFs until those files are added or fetched.

---

## 4. Ingestion

### 4.1 Input

PDFs are read from:

```text
rag_backend/ingestion/pdfs/
```

The extractor accepts a folder or a single PDF. Every page keeps its 1-based page number.

### 4.2 Extraction and OCR

The extractor uses PyMuPDF:

1. Extract the native text layer with `page.get_text("text")`.
2. If the page has fewer than `OCR_MIN_CHARS` characters (default 24), render it at `OCR_DPI` (default 200) and run Tesseract.
3. OCR language defaults to `eng`.
4. Tesseract is discovered from `TESSERACT_CMD`, `PATH`, or common Windows install locations.
5. A missing Tesseract binary now produces a clear error instead of silently indexing empty pages.

The Docker image installs `tesseract-ocr` automatically.

### 4.3 Extraction cache and resume

Each document is cached by:

- SHA-256 of the PDF bytes.
- OCR options: enabled/disabled, minimum characters, DPI, and language.

Cache location:

```text
rag_backend/data/extraction_cache/
```

Behavior:

- Completed documents are reused on later runs.
- Partial documents resume from the last checkpoint.
- Checkpoints are written every 25 pages using atomic file replacement.
- Interrupting a run loses at most about 25 pages of work for the active document.
- `--refresh` forces re-extraction.
- `--no-cache` disables cache reads and writes.
- `--ocr-only` limits OCR to filenames matching comma-separated substrings.

### 4.4 Quality checks

Before chunking, the pipeline:

- Detects and removes repeated headers and footers.
  - Examines the first and last three lines of each page.
  - A line must appear on at least 30% of non-empty pages and at least 3 pages.
- Detects section headings from the first lines of a page.
- Marks pages below 24 normalized characters as empty.
- Detects byte-identical duplicate PDFs.
- Detects content-identical documents using a normalized full-text SHA-256.

The quality report (`data/quality_report.json`) contains per-document page counts, characters, empty pages, OCR pages, errors, duplicate documents, warnings, skipped duplicates, and cache hits.

### 4.5 Chunking

Implemented in `ingestion/chunker.py`.

| Parameter | Value / behavior |
|---|---|
| Chunk unit | Characters, not tokens |
| Chunk size | 1,000 characters |
| Overlap | 150 characters |
| Minimum chunk | 40 characters; shorter pieces are dropped |
| Boundary handling | If a space exists after the first half of the chunk, split at the last space before 1,000 characters |
| Cross-page chunks | No; each page is chunked independently |
| Chunk ID | `{slug(source)}-p{page}-c{chunk_index}` |
| Example ID | `color-harmony-workbook-pdf-p12-c0` |
| Duplicate chunk IDs | Skipped within a run |
| Text cleanup | NUL removal, whitespace normalization, blank-line compression |

The overlap is nominally 150 characters but can vary slightly when the split is moved back to a word boundary.

Each chunk stores:

| Field | Meaning |
|---|---|
| `chunk_id` | Stable identifier |
| `document_id` | SHA-256 of the source PDF |
| `source` | PDF filename |
| `title` | PDF metadata title, fallback to filename |
| `author` | PDF metadata author |
| `page` | 1-based page number |
| `page_count` | Total pages in the PDF |
| `section` | Best-effort heading |
| `category` | Top keyword-classified category |
| `topics` | Up to five keyword topics |
| `chunk_index` | Index within the page |
| `content_hash` | SHA-256 of normalized chunk text |
| `embedding_model` | Embedding model name |
| `embedding_version` | Embedding index version |
| `ocr` | Whether the page came from OCR |
| `text` | Chunk text used for embedding |

Topic classification is deterministic keyword matching, not an ML classifier. Topics include color, styling, body, seasons, fabrics, occasions, wardrobe, footwear, menswear, travel, sustainability, construction, and care.

### 4.6 Embeddings

Implemented in `ingestion/embedder.py`.

- Model: `sentence-transformers/all-MiniLM-L6-v2`
- Output: 384-dimensional vectors
- Normalization: enabled
- Batch size: 32
- Each vector is stamped with the model name and version.
- The model is loaded lazily and cached in the API process.

Embeddings are stored locally in `data/embedded_chunks.jsonl` and in Supabase in `knowledge_chunks.embedding` as `vector(384)`.

The embedder currently re-embeds the full corpus. It does not skip unchanged chunks using `content_hash`; that is a future optimization.

### 4.7 Indexing

Implemented in `ingestion/indexer.py`.

- Batch size: 250 chunks.
- Upsert key: `chunk_id`.
- Unique index on `chunk_id`.
- Stores content, embedding, page, source, and enriched metadata.
- Deletes stale chunks missing from the current run for the same source.
- `--prune` deletes stale chunks across all sources.
- Detects legacy schemas and can fall back to delete+insert.
- Counts unchanged content hashes but still upserts all rows.
- Shows a chunk indexing progress bar.

---

## 5. Storage

### 5.1 Supabase / Postgres

Main table: `public.knowledge_chunks`.

Base columns:

- `id bigserial primary key`
- `chunk_id text not null unique`
- `content text not null`
- `source text`
- `page integer`
- `embedding vector(384) not null`

Hardening migration adds:

- `document_id`
- `title`
- `author`
- `section`
- `category`
- `topics text[]`
- `content_hash`
- `chunk_index`
- `embedding_model`
- `embedding_version`
- `ocr boolean`
- `updated_at`

Indexes:

- HNSW index on `embedding` using `vector_cosine_ops`
- Unique `chunk_id`
- Source, document, category, and embedding-version indexes
- GIN index on `topics`
- GIN full-text index on `to_tsvector('english', content)`

### 5.2 Local artifacts

| Artifact | Location | Current size |
|---|---|---:|
| PDFs | `rag_backend/ingestion/pdfs/` | 38 PDFs |
| Extracted pages | `rag_backend/data/extracted_pages.json` | 13.1 MB |
| Chunks | `rag_backend/data/chunks.jsonl` | 22 MB |
| Embedded chunks | `rag_backend/data/embedded_chunks.jsonl` | 139.3 MB |
| Extraction cache | `rag_backend/data/extraction_cache/` | 12.7 MB |
| Quality report | `rag_backend/data/quality_report.json` | small |
| Evaluation results | `rag_backend/data/evaluation_results.json` | small |
| Conversations | `rag_backend/data/conversations.sqlite3` | ~0.1 MB |

`rag_backend/data/` is gitignored. Docker mounts `/data` as a persistent volume.

### 5.3 Conversation store

SQLite with WAL mode:

- `conversations(id, created_at, updated_at)`
- `messages(id, conversation_id, role, content, sources, citations, rewritten_query, created_at)`

Behavior:

- Last 8 messages are sent to the answer LLM.
- Last 4 messages are used for query rewriting.
- `GET /conversations/{id}` returns up to 100 messages.
- This is single-instance storage and is not shared across API replicas.

---

## 6. Retrieval

Implemented in `rag/retriever.py`.

### 6.1 Query rewrite

- Controlled by `QUERY_REWRITE_ENABLED` (default true).
- Uses the LLM to rewrite vague questions into retrieval-friendly queries.
- Uses the last four conversation messages.
- Temperature 0, max 80 tokens.
- Falls back to the original question on failure.
- Adds an additional LLM call before retrieval, increasing latency and cost.

### 6.2 Vector search

Supabase RPC:

```sql
match_knowledge_chunks(
  query_embedding vector(384),
  match_count integer,
  min_similarity double precision
)
```

Similarity is cosine similarity:

```text
1 - (embedding <=> query_embedding)
```

Results are ordered by cosine distance and filtered below `min_similarity`. If the three-argument RPC is missing, the retriever falls back to the legacy two-argument RPC.

### 6.3 Keyword search

Supabase RPC:

```sql
search_knowledge_chunks(query_text text, match_count integer)
```

Uses:

- `websearch_to_tsquery('english', query_text)`
- `to_tsvector('english', content)`
- `ts_rank(...)`

This is English-only. French and Arabic keyword search are not supported yet.

### 6.4 Hybrid fusion

When hybrid search is enabled:

- Run vector search with `candidate_k = 30`.
- Run keyword search with `candidate_k = 30`.
- Fuse with Reciprocal Rank Fusion:

```text
score(chunk) = sum over lists of 1 / (60 + rank_in_list)
```

- RRF constant: 60.
- Deduplicate by `chunk_id`.
- Keep the highest-similarity row for duplicate IDs.
- Label results as `vector`, `keyword`, or `hybrid`.
- Return the final `top_k`.

Safety guard: if vector search returns no credible matches, keyword-only results are dropped. This prevents irrelevant keyword matches from bypassing the similarity floor.

### 6.5 Default retrieval parameters

| Setting | Default |
|---|---:|
| `RAG_TOP_K` | 5 |
| `RAG_CANDIDATE_K` | 30 |
| `RAG_MIN_SIMILARITY` | 0.25 |
| `RAG_HYBRID_ENABLED` | true |
| `RAG_RRF_CONSTANT` | 60 |
| `RAG_MAX_CONTEXT_CHARS` | 12,000 |

---

## 7. Answer generation and citations

Implemented in `rag/rag_service.py`.

### 7.1 Context construction

- Retrieves the top passages.
- Formats them as `[S1]`, `[S2]`, and so on.
- Each block includes source filename, page, title, section, and chunk text.
- Stops adding passages at 12,000 characters.

### 7.2 System prompt rules

The LLM is instructed to:

1. Use the supplied context as primary evidence.
2. Cite factual claims with `[S1]`, `[S2]`, and so on.
3. Say when the context is insufficient.
4. Never invent citations, page numbers, authors, or facts.
5. Label general styling advice as "General guidance" and keep it separate from source-backed statements.
6. Respect constraints such as occasion, season, body, budget, color, and destination.

### 7.3 No-information behavior

If retrieval returns no passages, the API returns a fixed "not enough information" answer with `grounded: false`.

### 7.4 Citations

- Markers are parsed with `\[S(\d+)\]`.
- Only markers present in the answer become citations.
- Citations map back to retrieved passage metadata.
- `grounded` is currently heuristic: true when at least one valid citation exists.
- It does not verify that the cited text actually supports the claim.

### 7.5 Streaming

`/ask/stream` emits Server-Sent Events:

- `sources`
- `token`
- `done`
- `error`

The `done` event includes citations, the grounded flag, and the rewritten query. The UI supports streaming and falls back to `/ask` if streaming is unavailable.

---

## 8. API

FastAPI app version 2.0.0.

| Endpoint | Method | Purpose |
|---|---|---|
| `/` | GET | Service metadata |
| `/health` | GET | Supabase and LLM health |
| `/ask` | POST | Grounded answer |
| `/ask/stream` | POST | SSE streamed answer |
| `/conversations` | POST | Create conversation |
| `/conversations/{id}` | GET | Read history |
| `/conversations/{id}` | DELETE | Delete conversation |

`/ask` request:

```json
{
  "question": "What should I wear to a formal dinner?",
  "top_k": 5,
  "conversation_id": "optional",
  "min_similarity": 0.25
}
```

Limits:

- Question: 1-2,000 characters.
- `top_k`: 1-20.
- `min_similarity`: 0-1.

Response fields:

- `answer`
- `sources`
- `citations`
- `conversation_id`
- `rewritten_query`
- `grounded`
- `usage`

Authentication:

- Optional shared secret via `RAG_API_KEY`.
- Header: `X-API-Key: <key>` or `Authorization: Bearer <key>`.
- If empty, authentication is disabled.
- The UI sends `X-API-Key` from `VITE_RAG_API_KEY`.

Rate limiting:

- Sliding window, default 30 requests per minute.
- Key is IP plus path.
- In-memory only; not shared across replicas.

Errors:

- 400 empty question.
- 401 invalid or missing API key.
- 429 rate limit.
- 502 LLM failure.
- 503 retrieval or Supabase failure.
- 500 unexpected error.

CORS:

- Default origins: `http://localhost:5173` and `http://localhost:8443`.
- Credentials enabled.
- Wildcard `*` is rejected.

Health:

- Checks the Supabase table count and embedding versions.
- Makes a live LLM call.
- Returns 503 if either check fails.
- The Docker healthcheck calls it every 30 seconds, which means a paid LLM call every 30 seconds in Docker.

---

## 9. Frontend integration

In `DressMe UI Blueprint/src/App.tsx`:

- `VITE_API_URL` defaults to `http://localhost:8000`.
- `VITE_RAG_API_KEY` is sent as `X-API-Key`.
- The AI Stylist sends the question, `top_k: 5`, and `conversation_id`.
- It uses `/ask/stream`, then falls back to `/ask`.
- It displays returned sources.
- It stores chat state in `localStorage`.
- It does not send wardrobe items, weather, profile, or the active-context panel to the RAG API.

Security note: any `VITE_*` value is embedded in the browser bundle. The API key is therefore demo-level gating, not real secrecy. Production should use a server-side proxy.

---

## 10. Evaluation

Golden set: 12 fashion questions in `evaluation/golden_qa.jsonl`, each with expected source filename substrings, expected topics, and a reference answer.

Metrics:

| Metric | Meaning |
|---|---|
| `hit@k` | At least one retrieved source matches an expected source |
| `MRR@k` | Reciprocal rank of the first relevant result |
| `context_precision` | Fraction of retrieved rows that are relevant |
| `citation_accuracy` | Cited markers map to retrieved rows |
| `groundedness` | Answer has at least one citation |

Current retrieval results after OCR and reindexing:

| Metric | Before | After |
|---|---:|---:|
| hit@k | 83.33% | 91.67% |
| MRR@k | 79.17% | 85.42% |
| context precision | 70.00% | 71.67% |

Remaining weak spots:

- `color-harmony`: 0.0 hit; retrieval prefers capsule and wardrobe guides.
- `work-clothes`: MRR 0.25, precision 0.20; the relevant source appears but ranks low.
- Fabric and wool questions improved after OCR and now hit.

Evaluation limitations:

- The default evaluation calls `retrieve()` directly and therefore does not exercise production query rewriting.
- `--judge` adds LLM-based faithfulness and relevance scoring, but the saved `evaluation_results.json` currently contains only retrieval metrics.
- `--ragas` is optional and requires extra dependencies.
- No CI threshold currently fails the build on metric regression.

---

## 11. Operations

### 11.1 Prerequisites

- Python 3.12.
- A Supabase project with the migrations applied.
- An OpenAI-compatible API key.
- Tesseract OCR for scanned PDFs.
- For the UI: Node.js and pnpm.

### 11.2 Environment

Copy `.env.example` to `.env` and fill in:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `OPENAI_API_KEY` or `LLM_API_KEY`
- `LLM_MODEL`
- `RAG_API_KEY` (recommended outside local development)

Optional OCR settings:

- `TESSERACT_CMD`
- `RAG_EXTRACTION_CACHE_DIR`
- `OCR_DPI`
- `OCR_LANGUAGE`

UI settings live in `DressMe UI Blueprint/.env`:

```text
VITE_API_URL=http://localhost:8000
VITE_RAG_API_KEY=<same value as RAG_API_KEY>
```

### 11.3 Run the API

```powershell
cd rag_backend
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

### 11.4 Run with Docker

```powershell
docker compose up -d --build rag-api
```

The compose file:

- Builds `rag_backend/`.
- Exposes port 8000.
- Persists `/data` and the Hugging Face cache.
- Mounts the PDF folder read-only.
- Restarts unless stopped.

### 11.5 Add or update PDFs

1. Put the PDFs in `rag_backend/ingestion/pdfs/`.
2. Run the pipeline.

Full run:

```powershell
cd rag_backend
python pipeline.py
```

OCR only selected scanned books:

```powershell
python pipeline.py --ocr-only Color,Textilepedia,Fabric,clothing_for_women,scarves
```

Resume after stopping:

- Rerun the same command.
- Completed PDFs are reused from the extraction cache.
- The interrupted PDF resumes from its last checkpoint.

Force re-extraction:

```powershell
python pipeline.py --refresh --ocr-only Color,Textilepedia,Fabric,clothing_for_women,scarves
```

Remove stale chunks for deleted or renamed PDFs:

```powershell
python pipeline.py --prune
```

Skip completed stages:

```powershell
python pipeline.py --skip-extract
python pipeline.py --skip-extract --skip-embed
```

### 11.6 Verify the index

```powershell
cd rag_backend
python verify_setup.py
```

Checks:

- Table exists.
- Metadata columns exist.
- Vector RPC with `min_similarity` exists.
- Keyword RPC exists.
- Embedding version matches the configured model.

### 11.7 Evaluate

```powershell
cd rag_backend
python -m evaluation.evaluate --top-k 5
python -m evaluation.evaluate --top-k 5 --judge
```

`--judge` adds LLM-based faithfulness, answer relevance, and citation accuracy.

---

## 12. Troubleshooting

**Tesseract OCR binary not found**

- Install Tesseract.
- Or set `TESSERACT_CMD` to the full path of `tesseract.exe`.
- Verify with `tesseract --version`.

**401 from `/ask`**

- `RAG_API_KEY` is set on the server but the client did not send it.
- Send `X-API-Key` or `Authorization: Bearer`.
- Restart the API after changing `.env`.

**503 from `/ask`**

- Supabase is unreachable, or the RPCs are missing.
- Check `/health`.
- Run `python verify_setup.py`.

**Embedding version mismatch**

- The model or `EMBEDDING_VERSION` changed.
- Re-run `python pipeline.py` and restart the API.

**Scanned PDFs index as empty**

- Tesseract is missing or OCR was not enabled for that file.
- Use `--ocr-only` with a matching filename substring.
- Inspect `data/quality_report.json` for empty pages.

**OCR is slow**

- OCR is CPU-bound.
- Use `--ocr-only` to avoid OCR on text-layer PDFs.
- Reruns reuse the cache.
- Interrupted documents resume from a checkpoint.

**UI cannot reach the API**

- Check `VITE_API_URL`.
- Check `CORS_ORIGINS`.
- Restart the Vite server after changing `.env`.

**API key is visible in the browser**

- `VITE_*` values are bundled into the client.
- Use a server-side proxy for production.

---

## 13. Security

- Supabase service-role keys are used server-side only.
- RLS allows public `select` on `knowledge_chunks`.
- RPC execution is revoked from `anon` and `authenticated` and granted only to `service_role`.
- The UI should call `/ask`, not query the table directly.
- The API key is optional and currently client-bundled.
- CORS is restricted to local origins by default.
- There is no user-level authentication or per-user data isolation yet.
- Conversations may contain user text; no retention or erasure policy is implemented.

---

## 14. Limitations

1. Not wardrobe-aware: it answers from fashion books, not the user's clothes.
2. English-only corpus and full-text search.
3. Page-scoped character chunking can split semantic units.
4. No cross-encoder reranker.
5. No metadata filters despite storing categories and topics.
6. Full re-embedding on every corpus update.
7. OCR noise in scanned books.
8. No faithfulness evaluation in the saved results.
9. Color Harmony retrieval is weaker than expected.
10. Client-side API key is not production-grade security.
11. In-memory rate limiting and SQLite conversations assume a single instance.
12. Docker healthchecks call the paid LLM every 30 seconds.
13. No tracing, metrics, or dashboards.
14. No multi-agent orchestration yet.

---

## 15. Recommended next steps

- Add a cross-encoder reranker.
- Add multilingual embeddings and multilingual full-text search.
- Use `content_hash` for incremental embedding.
- Add query expansion and color/colour synonyms.
- Add metadata filters for category, topic, and season.
- Run `--judge` and store faithfulness and relevance scores.
- Add CI thresholds for retrieval and answer quality.
- Move API-key handling to a server-side proxy.
- Replace SQLite conversations and in-memory rate limiting for multi-replica deployment.
- Make `/health` cheap and add a separate deep-health endpoint.
- Add tracing, metrics, and index-version monitoring.
- Deduplicate near-identical books before indexing.
