-- Knowledge base for DressMe RAG.
-- Mirrors the schema already live on the Supabase project (idempotent).

create extension if not exists vector with schema extensions;

create table if not exists public.knowledge_chunks (
    id bigserial primary key,
    chunk_id text not null,
    content text not null,
    source text,
    page integer,
    embedding extensions.vector(384) not null
);

create index if not exists knowledge_chunks_embedding_idx
    on public.knowledge_chunks
    using hnsw (embedding extensions.vector_cosine_ops);

-- Top-k cosine similarity search used by rag/retriever.py.
create or replace function public.match_knowledge_chunks(
    query_embedding extensions.vector(384),
    match_count integer default 5
)
returns table (
    chunk_id text,
    content text,
    source text,
    page integer,
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
        1 - (k.embedding <=> query_embedding) as similarity
    from public.knowledge_chunks k
    order by k.embedding <=> query_embedding
    limit match_count;
$$;
