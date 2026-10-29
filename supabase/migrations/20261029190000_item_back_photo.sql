begin;

alter table public.items
  add column if not exists back_photo_url text;

commit;
