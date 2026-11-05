begin;

create table if not exists public.avatar_profiles (
  user_id uuid primary key references public.profiles(id) on delete cascade,
  targets jsonb not null default '{}'::jsonb,
  details jsonb not null default '{}'::jsonb,
  appearance jsonb not null default '{}'::jsonb,
  wardrobe jsonb not null default '[]'::jsonb,
  height_cm double precision not null default 170,
  source text not null default 'manual',
  confidence double precision not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.avatar_profiles enable row level security;
revoke all on public.avatar_profiles from anon;
grant select, insert, update, delete on public.avatar_profiles to authenticated;

drop policy if exists avatar_profiles_own on public.avatar_profiles;
create policy avatar_profiles_own
  on public.avatar_profiles
  for all
  to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);

commit;
