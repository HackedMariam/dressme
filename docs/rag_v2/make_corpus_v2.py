"""RAG v2 étape 3 : plan du corpus v2 et script SQL de knowledge_chunks_v2 (à NE PAS exécuter sans feu vert).

Entrée  : inventory.json (inventaire en lecture seule de knowledge_chunks, phase 1).
Sorties : corpus_v2_plan.json (documents retirés, raisons, renommage) et knowledge_chunks_v2.sql.
knowledge_chunks n'est jamais modifiée : la v2 est une COPIE filtrée.
"""
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
INVENTORY = Path(r"C:\Users\Win11\DressMe\docs\rag_v2\inventory.json")

# Documents hors sujet pour conseiller une tenue (théorie, gestion, recherche), hors z-library.
OFF_TOPIC = {
    "Fashion Education": "pédagogie et enseignement de la mode, pas de conseil vestimentaire",
    "Fashion, Design and Events": "organisation d'événements de mode, pas de conseil vestimentaire",
    "Chapter06-SmaouiandGhariani-aout11": "chapitre d'article de recherche, hors sujet",
}
# Doublon : « How to Pack for Any Trip » indexé deux fois ; on garde l'identifiant qui a le plus de passages.
DUPLICATE_TITLE = "How to Pack for Any Trip (Lonely Planet)"
# Renommage d'après le fichier d'origine (Color Harmony Workbook.pdf), le titre extrait étant « Slide 1 ».
RENAME = {"Slide 1": "Color Harmony Workbook"}


def main() -> None:
    docs = json.loads(INVENTORY.read_text(encoding="utf-8"))["documents"]
    total = sum(d["chunks"] for d in docs)
    removed, renamed = [], []
    duplicates = sorted((d for d in docs if d["title"] == DUPLICATE_TITLE), key=lambda d: -d["chunks"])
    for dup in duplicates[1:]:
        removed.append({**{k: dup[k] for k in ("document_id", "title", "chunks")}, "reason": "doublon",
                        "sources": dup["sources"]})
    for d in docs:
        if any(r["document_id"] == d["document_id"] for r in removed):
            continue
        reason = None
        if d["zlibrary_filename"]:
            reason = "fichier issu de z-library (droits douteux)"
        elif d["title"] in OFF_TOPIC:
            reason = f"hors sujet : {OFF_TOPIC[d['title']]}"
        if reason:
            removed.append({**{k: d[k] for k in ("document_id", "title", "chunks")}, "reason": reason,
                            "sources": d["sources"]})
        if d["title"] in RENAME:
            renamed.append({"document_id": d["document_id"], "old_title": d["title"],
                            "new_title": RENAME[d["title"]], "sources": d["sources"]})
    removed_ids = {r["document_id"] for r in removed}
    kept = [d for d in docs if d["document_id"] not in removed_ids]
    plan = {"total_chunks_v1": total, "documents_v1": len(docs),
            "removed_documents": len(removed), "removed_chunks": sum(r["chunks"] for r in removed),
            "kept_documents": len(kept), "kept_chunks": sum(d["chunks"] for d in kept),
            "removed": removed, "renamed": renamed,
            "kept": [{"document_id": d["document_id"], "title": d["title"], "chunks": d["chunks"]} for d in kept]}
    (HERE / "corpus_v2_plan.json").write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
    (HERE / "knowledge_chunks_v2.sql").write_text(sql(plan), encoding="utf-8", newline="\n")
    print(f"retirés : {plan['removed_documents']} documents, {plan['removed_chunks']} passages ; "
          f"gardés : {plan['kept_documents']} documents, {plan['kept_chunks']} passages")


def q(text: str) -> str:
    return "'" + str(text).replace("'", "''") + "'"


def sql(plan: dict) -> str:
    removed_values = ",\n        ".join(f"({q(r['document_id'])}, {q(r['reason'])})  -- {r['title'][:60]}"
                                       for r in plan["removed"])
    renames = "\n".join(f"update public.knowledge_chunks_v2 set title = {q(r['new_title'])}, updated_at = now()\n"
                        f" where document_id = {q(r['document_id'])};  -- était {q(r['old_title'])}"
                        for r in plan["renamed"])
    return f"""-- ===========================================================================
-- RAG v2, étape 3 : knowledge_chunks_v2
-- NE PAS EXÉCUTER sans le feu vert de Nourhene. Script à part, hors supabase/migrations.
-- knowledge_chunks (v1) n'est pas modifiée : la v2 est une copie filtrée, avec ses propres
-- fonctions de recherche ; BO5 continue d'utiliser la v1 tant qu'on ne bascule pas.
-- Généré par docs/rag_v2/make_corpus_v2.py à partir de l'inventaire en lecture seule.
-- v1 : {plan['documents_v1']} documents, {plan['total_chunks_v1']} passages ;
-- v2 : {plan['kept_documents']} documents, {plan['kept_chunks']} passages ({plan['removed_documents']} documents retirés).
-- ===========================================================================
begin;

-- 1. Même schéma que knowledge_chunks (colonnes, contraintes, index), avec sa propre séquence.
create table public.knowledge_chunks_v2
    (like public.knowledge_chunks including defaults including constraints including indexes);
create sequence public.knowledge_chunks_v2_id_seq owned by public.knowledge_chunks_v2.id;
alter table public.knowledge_chunks_v2
    alter column id set default nextval('public.knowledge_chunks_v2_id_seq');

-- 2. Copie des passages, sauf les documents retirés (liste et raisons dans corpus_v2_plan.json).
with removed(document_id, reason) as (
    values
        {removed_values}
)
insert into public.knowledge_chunks_v2
select k.* from public.knowledge_chunks k
where k.document_id is null or k.document_id not in (select document_id from removed);

select setval('public.knowledge_chunks_v2_id_seq', coalesce((select max(id) from public.knowledge_chunks_v2), 1));

-- 3. Titres corrigés d'après le fichier d'origine.
{renames}

-- 4. Sécurité : mêmes règles que la v1 (lecture publique, écriture par la clé service seulement).
alter table public.knowledge_chunks_v2 enable row level security;
create policy knowledge_chunks_v2_read on public.knowledge_chunks_v2
    for select to anon, authenticated using (true);
revoke insert, update, delete, truncate on public.knowledge_chunks_v2 from anon, authenticated;
grant select on public.knowledge_chunks_v2 to anon, authenticated;

-- 5. Fonctions de recherche de la v2 (copies de celles de la v1, autre table).
create or replace function public.match_knowledge_chunks_v2(
    query_embedding extensions.vector(384),
    match_count integer default 5,
    min_similarity double precision default 0.0
)
returns table (chunk_id text, content text, source text, page integer, title text, section text,
               category text, topics text[], document_id text, similarity double precision)
language sql stable
set search_path = public, extensions
as $fn$
    select k.chunk_id, k.content, k.source, k.page, k.title, k.section, k.category, k.topics,
           k.document_id, 1 - (k.embedding <=> query_embedding) as similarity
    from public.knowledge_chunks_v2 k
    where 1 - (k.embedding <=> query_embedding) >= min_similarity
    order by k.embedding <=> query_embedding
    limit match_count;
$fn$;

create or replace function public.search_knowledge_chunks_v2(
    query_text text,
    match_count integer default 5
)
returns table (chunk_id text, content text, source text, page integer, title text, section text,
               category text, topics text[], document_id text, similarity double precision)
language sql stable
set search_path = public, extensions
as $fn$
    with parsed as (select websearch_to_tsquery('english', query_text) as ts_query)
    select k.chunk_id, k.content, k.source, k.page, k.title, k.section, k.category, k.topics, k.document_id,
           ts_rank(to_tsvector('english', coalesce(k.content, '')), parsed.ts_query)::double precision
    from public.knowledge_chunks_v2 k, parsed
    where parsed.ts_query is not null
      and to_tsvector('english', coalesce(k.content, '')) @@ parsed.ts_query
    order by 10 desc
    limit match_count;
$fn$;

revoke execute on function public.match_knowledge_chunks_v2(extensions.vector, integer, double precision)
    from public, anon, authenticated;
revoke execute on function public.search_knowledge_chunks_v2(text, integer) from public, anon, authenticated;
grant execute on function public.match_knowledge_chunks_v2(extensions.vector, integer, double precision)
    to service_role;
grant execute on function public.search_knowledge_chunks_v2(text, integer) to service_role;

-- 6. Contrôles avant de valider : nombre de passages et de documents attendus.
select count(*) as passages, count(distinct document_id) as documents from public.knowledge_chunks_v2;
-- attendu : {plan['kept_chunks']} passages, {plan['kept_documents']} documents

commit;
"""


if __name__ == "__main__":
    main()
