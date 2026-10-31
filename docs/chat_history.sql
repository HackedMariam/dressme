-- ===========================================================================
-- DressMe : historique de conversation de l'orchestrateur (chat_threads, chat_messages)
-- NE PAS EXÉCUTER sans accord : script à part, à coller dans le SQL Editor de Supabase.
-- Lu et écrit par l'orchestrateur avec le JETON de l'utilisatrice et la clé anon (jamais service_role) :
-- la RLS limite chaque utilisatrice à ses propres lignes. Script rejouable (if not exists / drop policy).
-- ===========================================================================
begin;

-- 1. Conversations
create table if not exists public.chat_threads (
    id          uuid primary key default gen_random_uuid(),
    user_id     uuid not null default auth.uid() references auth.users (id) on delete cascade,
    title       text not null default 'Nouvelle conversation' check (char_length(title) between 1 and 200),
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now(),
    -- cible de la clé étrangère composite des messages : un message ne peut viser que le fil de sa propriétaire
    unique (id, user_id)
);

-- 2. Messages (un par tour : question de l'utilisatrice, réponse de l'assistant)
create table if not exists public.chat_messages (
    id          uuid primary key default gen_random_uuid(),
    thread_id   uuid not null,
    user_id     uuid not null default auth.uid() references auth.users (id) on delete cascade,
    role        text not null check (role in ('user', 'assistant')),
    content     text not null check (char_length(content) between 1 and 20000),
    route       text check (route is null or char_length(route) <= 60),
    created_at  timestamptz not null default now(),
    foreign key (thread_id, user_id) references public.chat_threads (id, user_id) on delete cascade
);

-- 3. Index : liste des conversations (plus récente d'abord) et messages d'un fil dans l'ordre
create index if not exists chat_threads_user_updated_idx on public.chat_threads (user_id, updated_at desc);
create index if not exists chat_messages_thread_created_idx on public.chat_messages (thread_id, created_at);
create index if not exists chat_messages_user_idx on public.chat_messages (user_id);

-- 4. updated_at du fil : mis à jour à chaque message et à chaque modification du fil
create or replace function public.chat_touch_thread()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $fn$
begin
    update public.chat_threads set updated_at = now() where id = new.thread_id and user_id = new.user_id;
    return new;
end;
$fn$;

create or replace function public.chat_set_updated_at()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $fn$
begin
    new.updated_at = now();
    return new;
end;
$fn$;

drop trigger if exists chat_messages_touch_thread on public.chat_messages;
create trigger chat_messages_touch_thread
    after insert on public.chat_messages
    for each row execute function public.chat_touch_thread();

drop trigger if exists chat_threads_set_updated_at on public.chat_threads;
create trigger chat_threads_set_updated_at
    before update on public.chat_threads
    for each row execute function public.chat_set_updated_at();

-- 5. RLS : chaque utilisatrice lit, écrit et supprime seulement ses lignes
alter table public.chat_threads enable row level security;
alter table public.chat_messages enable row level security;

drop policy if exists chat_threads_select_own on public.chat_threads;
create policy chat_threads_select_own on public.chat_threads
    for select to authenticated using ((select auth.uid()) = user_id);
drop policy if exists chat_threads_insert_own on public.chat_threads;
create policy chat_threads_insert_own on public.chat_threads
    for insert to authenticated with check ((select auth.uid()) = user_id);
drop policy if exists chat_threads_update_own on public.chat_threads;
create policy chat_threads_update_own on public.chat_threads
    for update to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
drop policy if exists chat_threads_delete_own on public.chat_threads;
create policy chat_threads_delete_own on public.chat_threads
    for delete to authenticated using ((select auth.uid()) = user_id);

drop policy if exists chat_messages_select_own on public.chat_messages;
create policy chat_messages_select_own on public.chat_messages
    for select to authenticated using ((select auth.uid()) = user_id);
drop policy if exists chat_messages_insert_own on public.chat_messages;
create policy chat_messages_insert_own on public.chat_messages
    for insert to authenticated with check ((select auth.uid()) = user_id);
drop policy if exists chat_messages_delete_own on public.chat_messages;
create policy chat_messages_delete_own on public.chat_messages
    for delete to authenticated using ((select auth.uid()) = user_id);
-- pas de politique update sur chat_messages : un message enregistré ne se modifie pas

-- 6. Droits : rien pour anon (sans jeton) ; authenticated limité par la RLS ci-dessus
revoke all on public.chat_threads from anon;
revoke all on public.chat_messages from anon;
grant select, insert, update, delete on public.chat_threads to authenticated;
grant select, insert, delete on public.chat_messages to authenticated;
revoke execute on function public.chat_touch_thread() from public, anon;
revoke execute on function public.chat_set_updated_at() from public, anon;

-- 7. Contrôle : tables créées et RLS activée
select c.relname as table_name, c.relrowsecurity as rls_enabled,
       (select count(*) from pg_policies p where p.schemaname = 'public' and p.tablename = c.relname) as policies
from pg_class c join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public' and c.relname in ('chat_threads', 'chat_messages')
order by c.relname;
-- attendu : chat_messages true 3 ; chat_threads true 4

commit;
