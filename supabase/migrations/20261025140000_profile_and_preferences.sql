-- DressMe user profile, onboarding and style preferences.
--
-- The project already has public.profiles and public.style_profiles. This
-- migration extends those tables instead of creating a parallel system.
--
-- Safe to run more than once.

begin;

-- ---------------------------------------------------------------------------
-- Profile columns
-- ---------------------------------------------------------------------------

alter table public.profiles
  add column if not exists preferred_language text,
  add column if not exists avatar_url text,
  add column if not exists onboarding_completed boolean not null default false,
  add column if not exists onboarding_step smallint not null default 0,
  add column if not exists temperature_unit text not null default 'Celsius',
  add column if not exists size_system text not null default 'EU',
  add column if not exists notifications_enabled boolean not null default true,
  add column if not exists weather_sync_enabled boolean not null default true,
  add column if not exists ai_style_tips_enabled boolean not null default false;

do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conrelid = 'public.profiles'::regclass
      and conname = 'profiles_onboarding_step_check'
  ) then
    alter table public.profiles
      add constraint profiles_onboarding_step_check
      check (onboarding_step >= 0 and onboarding_step <= 10);
  end if;

  if not exists (
    select 1 from pg_constraint
    where conrelid = 'public.profiles'::regclass
      and conname = 'profiles_temperature_unit_check'
  ) then
    alter table public.profiles
      add constraint profiles_temperature_unit_check
      check (temperature_unit in ('Celsius', 'Fahrenheit'));
  end if;

  if not exists (
    select 1 from pg_constraint
    where conrelid = 'public.profiles'::regclass
      and conname = 'profiles_size_system_check'
  ) then
    alter table public.profiles
      add constraint profiles_size_system_check
      check (size_system in ('EU', 'US', 'UK'));
  end if;

  if not exists (
    select 1 from pg_constraint
    where conrelid = 'public.profiles'::regclass
      and conname = 'profiles_preferred_language_check'
  ) then
    alter table public.profiles
      add constraint profiles_preferred_language_check
      check (preferred_language is null or preferred_language in ('en', 'fr', 'ar'));
  end if;
end
$$;

-- ---------------------------------------------------------------------------
-- Style preference columns
-- ---------------------------------------------------------------------------

alter table public.style_profiles
  add column if not exists preferred_occasions text[] not null default '{}'::text[],
  add column if not exists preferred_categories text[] not null default '{}'::text[];

-- The existing table constrains clothing_sizes to a JSON array. Keep that
-- shape and store one entry per size, e.g.
-- [{"key":"top","value":"S"},{"key":"shoes","value":"EU 38"}].
alter table public.style_profiles
  alter column clothing_sizes set default '[]'::jsonb;

do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conrelid = 'public.style_profiles'::regclass
      and conname = 'style_profiles_preferred_fit_check'
  ) then
    alter table public.style_profiles
      add constraint style_profiles_preferred_fit_check
      check (
        preferred_fit is null
        or preferred_fit in ('fitted', 'regular', 'relaxed')
      );
  end if;
end
$$;

-- ---------------------------------------------------------------------------
-- Row Level Security
-- ---------------------------------------------------------------------------

alter table public.profiles enable row level security;
alter table public.style_profiles enable row level security;

-- Only authenticated users receive table privileges. Anonymous users must not
-- be able to read private profile data.
revoke all on public.profiles from anon;
revoke all on public.style_profiles from anon;
grant select, insert, update on public.profiles to authenticated;
grant select, insert, update on public.style_profiles to authenticated;

drop policy if exists "profiles_select_own" on public.profiles;
create policy "profiles_select_own"
  on public.profiles
  for select
  to authenticated
  using ((select auth.uid()) = id);

drop policy if exists "profiles_insert_own" on public.profiles;
create policy "profiles_insert_own"
  on public.profiles
  for insert
  to authenticated
  with check ((select auth.uid()) = id);

drop policy if exists "profiles_update_own" on public.profiles;
create policy "profiles_update_own"
  on public.profiles
  for update
  to authenticated
  using ((select auth.uid()) = id)
  with check ((select auth.uid()) = id);

drop policy if exists "style_profiles_select_own" on public.style_profiles;
create policy "style_profiles_select_own"
  on public.style_profiles
  for select
  to authenticated
  using ((select auth.uid()) = user_id);

drop policy if exists "style_profiles_insert_own" on public.style_profiles;
create policy "style_profiles_insert_own"
  on public.style_profiles
  for insert
  to authenticated
  with check ((select auth.uid()) = user_id);

drop policy if exists "style_profiles_update_own" on public.style_profiles;
create policy "style_profiles_update_own"
  on public.style_profiles
  for update
  to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);

-- ---------------------------------------------------------------------------
-- Idempotent profile initialisation
-- ---------------------------------------------------------------------------
--
-- The project already creates a profile and style_profiles row when a user
-- signs up. This function is still useful for old accounts or if that trigger
-- is ever removed: it only ever creates rows for auth.uid(), never for an
-- arbitrary user id.

create or replace function public.ensure_user_profile()
returns public.profiles
language plpgsql
security definer
set search_path = public
as $$
declare
  current_user_id uuid := auth.uid();
  result public.profiles%rowtype;
  metadata_name text;
begin
  if current_user_id is null then
    raise exception 'Authentication required' using errcode = '28000';
  end if;

  select nullif(trim(raw_user_meta_data ->> 'full_name'), '')
    into metadata_name
    from auth.users
    where id = current_user_id;

  insert into public.profiles (id, display_name)
  values (current_user_id, coalesce(metadata_name, ''))
  on conflict (id) do nothing;

  insert into public.style_profiles (user_id)
  values (current_user_id)
  on conflict (user_id) do nothing;

  select *
    into result
    from public.profiles
    where id = current_user_id;

  return result;
end;
$$;

revoke all on function public.ensure_user_profile() from public;
revoke all on function public.ensure_user_profile() from anon;
grant execute on function public.ensure_user_profile() to authenticated;

comment on function public.ensure_user_profile() is
  'Creates the authenticated user''s profile/preferences rows when missing and returns the profile.';

commit;
