-- Wardrobe Gaps (BO3): who the suggestions are for.
-- Both columns are optional. NULL means "not said": BO3 then keeps its previous behaviour (suggestions for everyone).
-- Existing rows, policies (own row only) and the other columns are untouched.
--
-- Already applied to the DressMe project (version 20261103213806). Kept here so the schema stays reproducible.

alter table public.profiles
  add column if not exists gender text
    check (gender is null or gender in ('female', 'male', 'non_binary', 'prefer_not_to_say'));

alter table public.style_profiles
  add column if not exists shopping_for text
    check (shopping_for is null or shopping_for in ('women', 'men', 'both'));

comment on column public.profiles.gender is
  'Optional, set by the user. female | male | non_binary | prefer_not_to_say. Personal data: read only through the owner policy or the service role.';
comment on column public.style_profiles.shopping_for is
  'Optional. Which wardrobe the user wants suggestions for: women | men | both. When NULL, Wardrobe Gaps derives it from profiles.gender (female -> women, male -> men, otherwise both).';
