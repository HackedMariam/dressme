-- DressMe wardrobe items used by the virtual try-on.
-- Mirrors the schema from the wardrobe feature branch and is safe to re-run.

begin;

create extension if not exists "pgcrypto";

create table if not exists public.items (
  id                uuid primary key default gen_random_uuid(),
  user_id           uuid references auth.users(id) on delete cascade,
  created_at        timestamptz not null default now(),

  name              text not null,
  category          text not null,
  category_group    text not null,
  subcategory       text,

  color_name        text,
  color_hex         text,
  color_family      text,
  colors            jsonb,

  pattern           text,
  material          text,
  seasons           text[] default '{}',
  style             text,
  occasions         text[] default '{}',
  formality         smallint check (formality between 1 and 5),
  warmth            smallint check (warmth between 1 and 5),
  description       text,
  styling_tips      text[] default '{}',
  tags              text[] default '{}',

  confidence        real,
  field_confidence  jsonb,
  needs_review      boolean not null default false,
  status            text not null default 'auto' check (status in ('auto','review','confirmed')),

  image_url         text,
  cutout_url        text,

  zone              text default 'rail' check (zone in ('rail','shelf','floor')),
  position_3d       jsonb,

  detection         jsonb,
  predicted         jsonb,
  enrichment_source text
);

alter table public.items add column if not exists color_family text;

create index if not exists items_user_idx     on public.items (user_id, created_at desc);
create index if not exists items_group_idx    on public.items (category_group);
create index if not exists items_seasons_idx  on public.items using gin (seasons);
create index if not exists items_occasion_idx on public.items using gin (occasions);

create table if not exists public.corrections (
  id               bigint generated always as identity primary key,
  item_id          uuid not null references public.items(id) on delete cascade,
  field            text not null,
  predicted        jsonb,
  corrected        jsonb,
  model_confidence real,
  created_at       timestamptz not null default now()
);
create index if not exists corrections_item_idx on public.corrections (item_id);

create or replace view public.detection_accuracy as
with reviewed as (
  select id from public.items where status = 'confirmed'
), wrong as (
  select field, count(distinct item_id) as corrected
  from public.corrections where item_id in (select id from reviewed)
  group by field
)
select f.field,
       (select count(*) from reviewed)                         as reviewed,
       coalesce(w.corrected, 0)                                as corrected,
       case when (select count(*) from reviewed) = 0 then null
            else round(1 - coalesce(w.corrected,0)::numeric / (select count(*) from reviewed), 3) end as accuracy
from (values ('category'),('color_name'),('pattern'),('seasons'),('style'),('occasions'),('material')) f(field)
left join wrong w using (field);

alter table public.items       enable row level security;
alter table public.corrections enable row level security;

drop policy if exists "own items" on public.items;
create policy "own items" on public.items
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists "own corrections" on public.corrections;
create policy "own corrections" on public.corrections
  for all using (exists (select 1 from public.items i where i.id = item_id and i.user_id = auth.uid()));

insert into storage.buckets (id, name, public)
values ('wardrobe', 'wardrobe', true)
on conflict (id) do update set public = true;

commit;
