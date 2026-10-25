-- Last generated avatar per user.
-- One row per user; the GLB is stored in the private `avatars` bucket and
-- overwritten on every successful generation.

begin;

create table if not exists public.user_avatars (
  user_id     uuid primary key references public.profiles(id) on delete cascade,
  targets     jsonb not null default '{}'::jsonb,
  details     jsonb not null default '{}'::jsonb,
  outfit      jsonb not null default '[]'::jsonb,
  metrics     jsonb not null default '{}'::jsonb,
  glb_path    text not null,
  glb_bytes   integer check (glb_bytes is null or glb_bytes >= 0),
  generated_at timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

alter table public.user_avatars enable row level security;

revoke all on public.user_avatars from anon;
grant select on public.user_avatars to authenticated;
grant all on public.user_avatars to service_role;

drop policy if exists user_avatars_select_own on public.user_avatars;
create policy user_avatars_select_own
  on public.user_avatars
  for select
  to authenticated
  using ((select auth.uid()) = user_id);

-- Private bucket: the backend uploads with the service role and returns
-- short-lived signed URLs to the browser.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'avatars',
  'avatars',
  false,
  52428800,
  array['model/gltf-binary', 'application/octet-stream']
)
on conflict (id) do update set
  public = false,
  file_size_limit = excluded.file_size_limit,
  allowed_mime_types = excluded.allowed_mime_types;

commit;
