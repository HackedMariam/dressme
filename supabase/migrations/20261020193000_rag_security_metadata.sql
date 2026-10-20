-- DressMe RAG hardening:
--   * enriched chunk metadata + embedding versioning
--   * idempotent upsert key on chunk_id
--   * hybrid retrieval RPCs (vector + full-text)
--   * read-only RLS and restricted RPC execution

-- ---------------------------------------------------------------------------
-- Metadata columns
-- ---------------------------------------------------------------------------
alter table public.knowledge_chunks
    add column if not exists document_id text,
    add column if not exists title text,
    add column if not exists author text,
    add column if not exists section text,
    add column if not exists category text,
    add column if not exists topics text[] not null default '{}',
    add column if not exists content_hash text,
    add column if not exists chunk_index integer,
    add column if not exists embedding_model text,
    add column if not exists embedding_version text,
    add column if not exists ocr boolean not null default false,
    add column if not exists updated_at timestamptz not null default now();

-- Remove duplicate chunk_ids before enforcing the upsert key. Keep the
-- newest row (highest id) so re-indexing wins.
delete from public.knowledge_chunks older
using public.knowledge_chunks newer
where older.chunk_id = newer.chunk_id
  and older.id < newer.id;

create unique index if not exists knowledge_chunks_chunk_id_key
    on public.knowledge_chunks (chunk_id);

create index if not exists knowledge_chunks_source_idx
    on public.knowledge_chunks (source);

create index if not exists knowledge_chunks_document_id_idx
    on public.knowledge_chunks (document_id);

create index if not exists knowledge_chunks_category_idx
    on public.knowledge_chunks (category);

create index if not exists knowledge_chunks_embedding_version_idx
    on public.knowledge_chunks (embedding_version);

create index if not exists knowledge_chunks_topics_idx
    on public.knowledge_chunks using gin (topics);

create index if not exists knowledge_chunks_content_fts_idx
    on public.knowledge_chunks
    using gin (to_tsvector('english', coalesce(content, '')));

-- ---------------------------------------------------------------------------
-- Vector search with a similarity floor and enriched return shape
-- ---------------------------------------------------------------------------
drop function if exists public.match_knowledge_chunks(
    extensions.vector, integer
);

create or replace function public.match_knowledge_chunks(
    query_embedding extensions.vector(384),
    match_count integer default 5,
    min_similarity double precision default 0.0
)
returns table (
    chunk_id text,
    content text,
    source text,
    page integer,
    title text,
    section text,
    category text,
    topics text[],
    document_id text,
    similarity double precision
)
language sql
stable
as $$
    select
        k.chunk_id,
        k.content,
        k.source,
        k.page,
        k.title,
        k.section,
        k.category,
        k.topics,
        k.document_id,
        1 - (k.embedding <=> query_embedding) as similarity
    from public.knowledge_chunks k
    where 1 - (k.embedding <=> query_embedding) >= min_similarity
    order by k.embedding <=> query_embedding
    limit match_count;
$$;

-- ---------------------------------------------------------------------------
-- Keyword (full-text) search for hybrid retrieval
-- ---------------------------------------------------------------------------
create or replace function public.search_knowledge_chunks(
    query_text text,
    match_count integer default 5
)
returns table (
    chunk_id text,
    content text,
    source text,
    page integer,
    title text,
    section text,
    category text,
    topics text[],
    document_id text,
    similarity double precision
)
language sql
stable
as $$
    with parsed as (
        select websearch_to_tsquery('english', query_text) as ts_query
    )
    select
        k.chunk_id,
        k.content,
        k.source,
        k.page,
        k.title,
        k.section,
        k.category,
        k.topics,
        k.document_id,
        ts_rank(
            to_tsvector('english', coalesce(k.content, '')),
            parsed.ts_query
        )::double precision as similarity
    from public.knowledge_chunks k, parsed
    where parsed.ts_query is not null
      and to_tsvector('english', coalesce(k.content, '')) @@ parsed.ts_query
    order by similarity desc
    limit match_count;
$$;

-- ---------------------------------------------------------------------------
-- RLS: public read-only knowledge base; writes only via service role
-- ---------------------------------------------------------------------------
alter table public.knowledge_chunks enable row level security;

drop policy if exists knowledge_chunks_read on public.knowledge_chunks;
create policy knowledge_chunks_read
    on public.knowledge_chunks
    for select
    to anon, authenticated
    using (true);

revoke insert, update, delete, truncate
    on public.knowledge_chunks
    from anon, authenticated;

grant select on public.knowledge_chunks to anon, authenticated;

-- RPCs are for the backend (service role) only. The UI should call /ask,
-- never query the knowledge base directly.
revoke execute on function public.match_knowledge_chunks(
    extensions.vector, integer, double precision
) from public, anon, authenticated;

revoke execute on function public.search_knowledge_chunks(
    text, integer
) from public, anon, authenticated;

grant execute on function public.match_knowledge_chunks(
    extensions.vector, integer, double precision
) to service_role;

grant execute on function public.search_knowledge_chunks(
    text, integer
) to service_role;

comment on table public.knowledge_chunks is
    'DressMe fashion knowledge chunks. Read-only for anon/authenticated; '
    'indexed and searched by the RAG backend using service_role.';

-- Make the new RPC signatures visible to PostgREST immediately.
notify pgrst, 'reload schema';
