-- Per-item 3D assets.
-- Each wardrobe item can own a generated GLB (2.5D extrusion of its cutout) so
-- the 3D wardrobe and the item drawer can render the actual item instead of a
-- flat image plane. The avatar try-on still textures body-fitted shells with
-- the item cutout; the mesh is used for previews and future fitting.

begin;

alter table public.items
  add column if not exists mesh_url     text,
  add column if not exists mesh_status  text not null default 'none',
  add column if not exists mesh_source  text,
  add column if not exists mesh_version integer not null default 0,
  add column if not exists mesh_meta    jsonb,
  add column if not exists mesh_error   text;

do $$
begin
  if not exists (
    select 1 from pg_constraint where conname = 'items_mesh_status_check'
  ) then
    alter table public.items
      add constraint items_mesh_status_check
      check (mesh_status in ('none', 'queued', 'building', 'ready', 'failed'));
  end if;
end $$;

commit;
