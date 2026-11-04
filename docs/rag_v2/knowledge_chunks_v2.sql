-- ===========================================================================
-- RAG v2, étape 3 : knowledge_chunks_v2
-- NE PAS EXÉCUTER sans le feu vert de Nourhene. Script à part, hors supabase/migrations.
-- knowledge_chunks (v1) n'est pas modifiée : la v2 est une copie filtrée, avec ses propres
-- fonctions de recherche ; BO5 continue d'utiliser la v1 tant qu'on ne bascule pas.
-- Généré par docs/rag_v2/make_corpus_v2.py à partir de l'inventaire en lecture seule.
-- v1 : 38 documents, 14574 passages ;
-- v2 : 17 documents, 2747 passages (21 documents retirés).
-- ===========================================================================
begin;

-- 1. Même schéma que knowledge_chunks (colonnes, contraintes, index). id y est un bigserial : LIKE copierait
--    le défaut nextval('knowledge_chunks_id_seq') de la v1, d'où une séquence bigint propre à la v2.
create table public.knowledge_chunks_v2
    (like public.knowledge_chunks including defaults including constraints including indexes);
create sequence public.knowledge_chunks_v2_id_seq as bigint owned by public.knowledge_chunks_v2.id;
alter table public.knowledge_chunks_v2
    alter column id set default nextval('public.knowledge_chunks_v2_id_seq');

-- 2. Copie des passages, sauf les documents retirés (liste et raisons dans corpus_v2_plan.json).
with removed(document_id, reason) as (
    values
        ('785153fc17609fc960de48a1513a692c09a01d776a7769d587e8bcff68852423', 'doublon'),  -- How to Pack for Any Trip (Lonely Planet)
        ('0e87cfed7e3e6e8eaba421e60830396dbfee360d93838a98d0032d4f69556156', 'fichier issu de z-library (droits douteux)'),  -- The Science of Footwear
        ('a00807d510c441b7f773cace2c73e1094db2578d50e62c5f5e2ed24c8d4e6cb2', 'fichier issu de z-library (droits douteux)'),  -- J.J. Pizzutos Fabric Science, 10th Edition (Allen C. Cohen,
        ('a5fba229a17a0a1a2b9c36cf8ab0280d5a4cbace7e024d8ee9d9ac7a5ffc2a3f', 'fichier issu de z-library (droits douteux)'),  -- Fashion Education
        ('af308dc7d439a4ad60e95e8e3e21bc9b3ea4dc50a0db5d45573071b1c9b54d2b', 'fichier issu de z-library (droits douteux)'),  -- Fashion Media Past and Present (Djurdja Bartlett, Shaun Cole
        ('5cfcf765b5aa2aa5e9ad66c568550dc876ff4a880a0e354317ac5a60b2b62b13', 'fichier issu de z-library (droits douteux)'),  -- Communicating Fashion
        ('d173d7e89ec64f0f93dfe44f83020f79176f708bc90431efd667a7bbb5eed0b2', 'fichier issu de z-library (droits douteux)'),  -- 36916.indb
        ('1b7ed0388cf073451e2a5deaf4c3d15613471feacd05611dcfb89796d6922059', 'hors sujet : organisation d''événements de mode, pas de conseil vestimentaire'),  -- Fashion, Design and Events
        ('8e83ee4f18bf0c3a6e3a263aba1e3163091764230441fe20e0c5c018a4ba95cb', 'fichier issu de z-library (droits douteux)'),  -- Worn: Footwear, Attachment and the Affects of Wear
        ('361c745bd3d348201c69cbdf69280f97dff28f682936afe8d4eae46c609fa868', 'fichier issu de z-library (droits douteux)'),  -- Men's wardrobe
        ('13b9c9e791f69afdb812bd9b6593ebfea951a2975f1afc8c9502b27d61d62b4b', 'fichier issu de z-library (droits douteux)'),  -- Traveling clothes
        ('03576799c376d669708799c7a540bd666e0b07cc13dba14e8fb9bd93c04a8c90', 'fichier issu de z-library (droits douteux)'),  -- Ten Garments Every Man Should Own
        ('e13e21ba09d1721d6f0977147bf437003b4fa46777f78ce703d6aa1edd811cf1', 'fichier issu de z-library (droits douteux)'),  -- Textilepedia (Fashionary International Limited) (z-library.s
        ('75407d0c0ce2c314e87627c7afb37e4c3e863ecb9c2cbc74a32cdfe85c04d9a0', 'fichier issu de z-library (droits douteux)'),  -- Work clothes
        ('3b2b3a8901e4444c3ef9524aa3d838132047af1d894d67cac6ef37fce87c891b', 'fichier issu de z-library (droits douteux)'),  -- Old Money Style: Secrets to Dressing Well for Less (The Gent
        ('dd77d47aa35e3d15ada7da8214137135dbc08907ee53062ee4e3612dafcd4391', 'fichier issu de z-library (droits douteux)'),  -- How to Pack for Any Trip (Lonely Planet)
        ('2eea009171781fc355c1cc23341df51bd9f999481a5cdcc2bcbccaec12395e3c', 'fichier issu de z-library (droits douteux)'),  -- How to Pack: Travel Smart for Any Trip
        ('4b4e81e15e0a03a1afe3411ae1e45dd1474ba95832eeeae794f7684fab06ef58', 'fichier issu de z-library (droits douteux)'),  -- The Capsule Wardrobe
        ('d580d5d489ea12ed1db7ee5adad09a3a0d138a683a30f2c808827d3b29cb0586', 'fichier issu de z-library (droits douteux)'),  -- Shoes (Klaus H. Carl) (z-library.sk, 1lib.sk, z-lib.sk)
        ('68152d63e128c904c5db214dd2e6347c336719b57b856a5d45447aed23624009', 'hors sujet : chapitre d''article de recherche, hors sujet'),  -- Chapter06-SmaouiandGhariani-aout11
        ('24f9f83a81bddd4d6152ebbbce0c83bacfca29bd42fee9fa08d7092dec4ee901', 'fichier issu de z-library (droits douteux)')  -- The French Minimalist Capsule Wardrobe - Winter 2018-2019 Co
)
insert into public.knowledge_chunks_v2
select k.* from public.knowledge_chunks k
where k.document_id is null or k.document_id not in (select document_id from removed);

select setval('public.knowledge_chunks_v2_id_seq', coalesce((select max(id) from public.knowledge_chunks_v2), 0) + 1, false);

-- 3. Titres corrigés d'après le fichier d'origine.
update public.knowledge_chunks_v2 set title = 'Color Harmony Workbook', updated_at = now()
 where document_id = 'debc441d706baccb55a9334573e4c5aeb0556a026023d10fe7a6e7443fb70c91';  -- était 'Slide 1'

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
-- attendu : 2747 passages, 17 documents

commit;
