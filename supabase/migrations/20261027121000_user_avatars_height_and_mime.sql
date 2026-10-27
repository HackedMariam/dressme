-- Fix avatar persistence failures:
-- 1. The generated payload includes height_cm, which was missing from the table.
-- 2. The private avatars bucket rejected the JSON metadata fallback (415).

begin;

alter table public.user_avatars
  add column if not exists height_cm double precision;

update storage.buckets
set allowed_mime_types = array[
  'model/gltf-binary',
  'application/octet-stream',
  'application/json'
]
where id = 'avatars';

commit;
