-- DressMe v1: shared application schema for BO1 through BO7.
-- Apply once to a new Supabase project. Existing application tables are not replaced.
begin;

create schema if not exists extensions;
create extension if not exists vector with schema extensions;
create schema if not exists dressme_private;
revoke all on schema dressme_private from public;

create table public.business_objectives (
  id text primary key check (id ~ '^BO[1-7]$'),
  name text not null,
  description text not null
);

create table public.model_versions (
  id uuid primary key default gen_random_uuid(),
  bo_id text not null references public.business_objectives(id),
  name text not null,
  version text not null,
  artifact_uri text,
  embedding_dimensions integer check (embedding_dimensions > 0),
  metadata jsonb not null default '{}' check (jsonb_typeof(metadata) = 'object'),
  created_at timestamptz not null default now(),
  unique (name, version)
);

create table public.clothing_categories (
  code text primary key,
  label text not null
);

-- Shared catalogs contain licensed/public or synthetic data, never private user photos.
create table public.datasets (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  version text not null,
  source_url text,
  license text not null,
  purpose text not null check (purpose in ('training', 'evaluation', 'integration')),
  created_at timestamptz not null default now(),
  unique (name, version)
);

create table public.garments (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  category text not null references public.clothing_categories(code),
  subcategory text,
  colors text[] not null default '{}',
  materials text[] not null default '{}',
  seasons text[] not null default '{}' check (seasons <@ array['spring','summer','autumn','winter']::text[]),
  occasion_tags text[] not null default '{}',
  style_tags text[] not null default '{}',
  fit text check (fit in ('fitted','regular','relaxed')),
  pattern text,
  brand text,
  weight_g integer check (weight_g >= 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.catalog_images (
  id uuid primary key default gen_random_uuid(),
  garment_id uuid not null references public.garments(id) on delete cascade,
  storage_path text not null unique,
  source_url text,
  license text not null,
  created_at timestamptz not null default now()
);

create table public.dataset_samples (
  id uuid primary key default gen_random_uuid(),
  dataset_id uuid not null references public.datasets(id) on delete cascade,
  garment_id uuid not null references public.garments(id),
  split text not null check (split in ('train','validation','test','integration')),
  annotations jsonb not null default '{}' check (jsonb_typeof(annotations) = 'object'),
  unique (dataset_id, garment_id)
);

create table public.garment_pair_labels (
  id uuid primary key default gen_random_uuid(),
  dataset_id uuid not null references public.datasets(id) on delete cascade,
  garment_a_id uuid not null references public.garments(id),
  garment_b_id uuid not null references public.garments(id),
  intended_use text not null default '',
  relationship text not null check (relationship in ('redundant','similar','complementary','different')),
  source text not null,
  check (garment_a_id < garment_b_id),
  unique (dataset_id, garment_a_id, garment_b_id, intended_use)
);

create table public.catalog_outfits (
  id uuid primary key default gen_random_uuid(),
  dataset_id uuid not null references public.datasets(id) on delete cascade,
  name text not null,
  split text not null check (split in ('train','validation','test','integration')),
  occasion text,
  compatibility_label boolean,
  annotations jsonb not null default '{}' check (jsonb_typeof(annotations) = 'object')
);

create table public.catalog_outfit_items (
  outfit_id uuid not null references public.catalog_outfits(id) on delete cascade,
  garment_id uuid not null references public.garments(id),
  primary key (outfit_id, garment_id)
);

-- Supabase Auth owns login credentials; profiles.id is the canonical user_id.
create table public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  display_name text not null default '',
  default_currency text not null default 'EUR' check (default_currency ~ '^[A-Z]{3}$'),
  timezone text not null default 'UTC',
  location jsonb check (location is null or jsonb_typeof(location) = 'object'),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.style_profiles (
  user_id uuid primary key references public.profiles(id) on delete cascade,
  preferred_styles text[] not null default '{}',
  preferred_colors text[] not null default '{}',
  avoided_colors text[] not null default '{}',
  preferred_fit text check (preferred_fit in ('fitted','regular','relaxed')),
  clothing_sizes jsonb not null default '[]' check (jsonb_typeof(clothing_sizes) = 'array'),
  updated_at timestamptz not null default now()
);

create table public.wardrobe_items (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  catalog_garment_id uuid references public.garments(id),
  name text not null,
  category text not null references public.clothing_categories(code),
  subcategory text,
  colors text[] not null default '{}',
  materials text[] not null default '{}',
  seasons text[] not null default '{}' check (seasons <@ array['spring','summer','autumn','winter']::text[]),
  occasion_tags text[] not null default '{}',
  style_tags text[] not null default '{}',
  fit text check (fit in ('fitted','regular','relaxed')),
  pattern text,
  brand text,
  size_label text,
  size_system text,
  weight_g integer check (weight_g >= 0),
  availability text not null default 'available' check (availability in ('available','laundry','unavailable')),
  purchase_amount_minor bigint check (purchase_amount_minor >= 0),
  purchase_currency text check (purchase_currency ~ '^[A-Z]{3}$'),
  purchased_on date,
  attribute_source text not null default 'user' check (attribute_source in ('user','model','import')),
  validated_at timestamptz,
  archived_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (id, user_id),
  check ((purchase_amount_minor is null) = (purchase_currency is null))
);

create table public.item_images (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  wardrobe_item_id uuid,
  storage_path text not null unique,
  mime_type text not null check (mime_type in ('image/jpeg','image/png','image/webp')),
  width_px integer check (width_px > 0),
  height_px integer check (height_px > 0),
  created_at timestamptz not null default now(),
  unique (id, user_id),
  foreign key (wardrobe_item_id, user_id) references public.wardrobe_items(id, user_id),
  check (split_part(storage_path, '/', 1) = user_id::text)
);

create table public.image_analyses (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  image_id uuid not null,
  model_id uuid not null references public.model_versions(id),
  detected_garments jsonb not null check (jsonb_typeof(detected_garments) = 'array'),
  created_at timestamptz not null default now(),
  foreign key (image_id, user_id) references public.item_images(id, user_id) on delete cascade
);

create table public.garment_embeddings (
  garment_id uuid not null references public.garments(id) on delete cascade,
  model_id uuid not null references public.model_versions(id),
  embedding extensions.vector not null,
  created_at timestamptz not null default now(),
  primary key (garment_id, model_id)
);

create table public.wardrobe_embeddings (
  wardrobe_item_id uuid not null,
  user_id uuid not null references public.profiles(id) on delete cascade,
  model_id uuid not null references public.model_versions(id),
  embedding extensions.vector not null,
  created_at timestamptz not null default now(),
  primary key (wardrobe_item_id, model_id),
  foreign key (wardrobe_item_id, user_id) references public.wardrobe_items(id, user_id) on delete cascade
);

create table public.conversations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  title text not null default 'New conversation',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (id, user_id)
);

create table public.messages (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  conversation_id uuid not null,
  role text not null check (role in ('user','assistant','tool','system')),
  content text not null,
  structured_content jsonb not null default '{}' check (jsonb_typeof(structured_content) = 'object'),
  created_at timestamptz not null default now(),
  foreign key (conversation_id, user_id) references public.conversations(id, user_id) on delete cascade
);

create table public.workflow_runs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  conversation_id uuid,
  schema_version text not null default '1.0',
  request_text text not null,
  request_context jsonb not null default '{}' check (jsonb_typeof(request_context) = 'object'),
  status text not null default 'pending' check (status in ('pending','running','needs_input','completed','failed')),
  response jsonb,
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  unique (id, user_id),
  foreign key (conversation_id, user_id) references public.conversations(id, user_id),
  check (finished_at is null or finished_at >= started_at)
);

create table public.bo_executions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  run_id uuid not null,
  bo_id text not null references public.business_objectives(id),
  model_id uuid references public.model_versions(id),
  operation text not null,
  status text not null check (status in ('running','ok','needs_input','error')),
  input_snapshot jsonb not null default '{}' check (jsonb_typeof(input_snapshot) = 'object'),
  result jsonb,
  warnings jsonb not null default '[]' check (jsonb_typeof(warnings) = 'array'),
  error jsonb,
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  unique (id, user_id),
  unique (id, run_id, user_id),
  foreign key (run_id, user_id) references public.workflow_runs(id, user_id) on delete cascade,
  check (finished_at is null or finished_at >= started_at)
);

create table public.redundancy_assessments (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  execution_id uuid not null,
  candidate jsonb not null check (jsonb_typeof(candidate) = 'object'),
  intended_use text,
  redundancy_score numeric check (redundancy_score between 0 and 1),
  closest_items jsonb not null default '[]' check (jsonb_typeof(closest_items) = 'array'),
  reasons text[] not null default '{}',
  created_at timestamptz not null default now(),
  foreign key (execution_id, user_id) references public.bo_executions(id, user_id) on delete cascade
);

create table public.gap_analyses (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  execution_id uuid not null,
  goal text not null,
  coverage jsonb not null default '{}' check (jsonb_typeof(coverage) = 'object'),
  created_at timestamptz not null default now(),
  unique (id, user_id),
  foreign key (execution_id, user_id) references public.bo_executions(id, user_id) on delete cascade
);

create table public.wardrobe_gaps (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  analysis_id uuid not null,
  category text not null references public.clothing_categories(code),
  desired_attributes jsonb not null default '{}' check (jsonb_typeof(desired_attributes) = 'object'),
  priority text not null check (priority in ('low','medium','high')),
  estimated_outfit_gain integer check (estimated_outfit_gain >= 0),
  reason text not null,
  foreign key (analysis_id, user_id) references public.gap_analyses(id, user_id) on delete cascade
);

create table public.outfits (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  execution_id uuid,
  name text not null,
  occasion text,
  compatibility_score numeric check (compatibility_score between 0 and 100),
  weather_suitable boolean,
  explanation text,
  saved_at timestamptz,
  created_at timestamptz not null default now(),
  unique (id, user_id),
  foreign key (execution_id, user_id) references public.bo_executions(id, user_id)
);

create table public.outfit_items (
  outfit_id uuid not null,
  wardrobe_item_id uuid not null,
  user_id uuid not null references public.profiles(id) on delete cascade,
  position integer not null default 0 check (position >= 0),
  primary key (outfit_id, wardrobe_item_id),
  foreign key (outfit_id, user_id) references public.outfits(id, user_id) on delete cascade,
  foreign key (wardrobe_item_id, user_id) references public.wardrobe_items(id, user_id)
);

create table public.inspiration_matches (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  execution_id uuid not null,
  source_image_id uuid,
  query_text text,
  retrieved_garment_ids uuid[] not null default '{}',
  reconstructed_outfit_id uuid,
  explanation text,
  foreign key (execution_id, user_id) references public.bo_executions(id, user_id) on delete cascade,
  foreign key (source_image_id, user_id) references public.item_images(id, user_id),
  foreign key (reconstructed_outfit_id, user_id) references public.outfits(id, user_id),
  check (source_image_id is not null or query_text is not null)
);

-- BO5 is trust and transparency; trace events alone do not fulfil this objective.
create table public.explanations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  execution_id uuid not null,
  method text not null check (method in ('shap','counterfactual','grad_cam','rules','grounded_summary')),
  summary text not null,
  evidence jsonb not null default '[]' check (jsonb_typeof(evidence) = 'array'),
  counterfactuals jsonb not null default '[]' check (jsonb_typeof(counterfactuals) = 'array'),
  limitations text[] not null default '{}',
  confidence numeric check (confidence between 0 and 1),
  heatmap_storage_path text,
  created_at timestamptz not null default now(),
  unique (id, user_id),
  foreign key (execution_id, user_id) references public.bo_executions(id, user_id) on delete cascade,
  check (heatmap_storage_path is null or split_part(heatmap_storage_path, '/', 1) = user_id::text)
);

create table public.explanation_factors (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  explanation_id uuid not null,
  feature_name text not null,
  feature_value jsonb,
  contribution double precision not null,
  contribution_unit text not null,
  foreign key (explanation_id, user_id) references public.explanations(id, user_id) on delete cascade
);

create table public.products (
  id uuid primary key default gen_random_uuid(),
  garment_id uuid not null references public.garments(id),
  retailer text not null,
  retailer_product_id text not null,
  product_url text not null,
  amount_minor bigint check (amount_minor >= 0),
  currency text check (currency ~ '^[A-Z]{3}$'),
  available boolean not null default true,
  price_checked_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (retailer, retailer_product_id),
  check ((amount_minor is null) = (currency is null))
);

-- BO6 stores purchase decisions, outfit benefits and redundancy, as well as cost.
create table public.purchase_plans (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  execution_id uuid not null,
  budget_minor bigint not null check (budget_minor >= 0),
  currency text not null check (currency ~ '^[A-Z]{3}$'),
  total_minor bigint not null check (total_minor >= 0),
  assessment text not null check (assessment in ('within_budget','over_budget','incomplete')),
  expected_benefits jsonb not null default '{}' check (jsonb_typeof(expected_benefits) = 'object'),
  created_at timestamptz not null default now(),
  unique (id, user_id),
  foreign key (execution_id, user_id) references public.bo_executions(id, user_id) on delete cascade,
  check (assessment <> 'within_budget' or total_minor <= budget_minor)
);

create table public.purchase_plan_items (
  plan_id uuid not null,
  user_id uuid not null references public.profiles(id) on delete cascade,
  product_id uuid not null references public.products(id),
  quantity integer not null default 1 check (quantity > 0),
  quoted_unit_amount_minor bigint not null check (quoted_unit_amount_minor >= 0),
  additive_benefit_score double precision not null,
  redundancy_score numeric check (redundancy_score between 0 and 1),
  estimated_outfit_gain integer check (estimated_outfit_gain >= 0),
  reasons text[] not null default '{}',
  primary key (plan_id, product_id),
  foreign key (plan_id, user_id) references public.purchase_plans(id, user_id) on delete cascade
);

create table public.trips (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  name text not null,
  destinations jsonb not null check (jsonb_typeof(destinations) = 'array'),
  start_date date not null,
  end_date date not null,
  max_weight_g integer check (max_weight_g >= 0),
  max_item_count integer check (max_item_count > 0),
  laundry_available boolean,
  weather_snapshot jsonb not null default '{}' check (jsonb_typeof(weather_snapshot) = 'object'),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (id, user_id),
  check (end_date >= start_date)
);

create table public.trip_activities (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  trip_id uuid not null,
  activity_date date,
  occasion text not null,
  notes text,
  foreign key (trip_id, user_id) references public.trips(id, user_id) on delete cascade
);

create table public.packing_plans (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  trip_id uuid not null,
  execution_id uuid not null,
  known_total_weight_g integer not null default 0 check (known_total_weight_g >= 0),
  weight_assessment text not null check (weight_assessment in ('within_limit','over_limit','unknown')),
  missing_pieces jsonb not null default '[]' check (jsonb_typeof(missing_pieces) = 'array'),
  warnings text[] not null default '{}',
  created_at timestamptz not null default now(),
  unique (id, user_id),
  foreign key (trip_id, user_id) references public.trips(id, user_id) on delete cascade,
  foreign key (execution_id, user_id) references public.bo_executions(id, user_id)
);

create table public.packing_items (
  plan_id uuid not null,
  user_id uuid not null references public.profiles(id) on delete cascade,
  wardrobe_item_id uuid not null,
  weight_g_snapshot integer check (weight_g_snapshot >= 0),
  reason text not null,
  packed boolean not null default false,
  primary key (plan_id, wardrobe_item_id),
  foreign key (plan_id, user_id) references public.packing_plans(id, user_id) on delete cascade,
  foreign key (wardrobe_item_id, user_id) references public.wardrobe_items(id, user_id)
);

create table public.trip_outfits (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  plan_id uuid not null,
  outfit_id uuid not null,
  outfit_date date not null,
  occasion text not null,
  foreign key (plan_id, user_id) references public.packing_plans(id, user_id) on delete cascade,
  foreign key (outfit_id, user_id) references public.outfits(id, user_id)
);

create table public.recommendation_feedback (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  execution_id uuid not null,
  rating smallint check (rating between 1 and 5),
  comment text,
  created_at timestamptz not null default now(),
  foreign key (execution_id, user_id) references public.bo_executions(id, user_id) on delete cascade,
  check (rating is not null or comment is not null)
);

create table public.trace_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  run_id uuid not null,
  execution_id uuid,
  component text not null,
  operation text not null,
  status text not null check (status in ('started','succeeded','failed')),
  duration_ms integer check (duration_ms >= 0),
  error_code text,
  created_at timestamptz not null default now(),
  foreign key (run_id, user_id) references public.workflow_runs(id, user_id) on delete cascade,
  foreign key (execution_id, run_id, user_id) references public.bo_executions(id, run_id, user_id)
);

create function dressme_private.touch_updated_at()
returns trigger language plpgsql set search_path = '' as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create function dressme_private.create_user_profile()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
  insert into public.profiles (id, display_name)
  values (new.id, coalesce(new.raw_user_meta_data ->> 'display_name', ''));
  insert into public.style_profiles (user_id) values (new.id);
  return new;
end;
$$;
revoke all on function dressme_private.create_user_profile() from public, anon, authenticated, service_role;

create trigger dressme_create_profile after insert on auth.users
for each row execute function dressme_private.create_user_profile();

-- Also support projects that already have Auth users.
insert into public.profiles (id, display_name)
select id, coalesce(raw_user_meta_data ->> 'display_name', '') from auth.users
on conflict (id) do nothing;
insert into public.style_profiles (user_id)
select id from public.profiles on conflict (user_id) do nothing;

create function dressme_private.validate_embedding_dimensions()
returns trigger language plpgsql set search_path = '' as $$
declare expected integer;
begin
  select embedding_dimensions into expected from public.model_versions where id = new.model_id;
  if expected is null or extensions.vector_dims(new.embedding) <> expected then
    raise exception 'Embedding dimensions must match the registered model';
  end if;
  return new;
end;
$$;

create trigger garment_embedding_dimensions before insert or update on public.garment_embeddings
for each row execute function dressme_private.validate_embedding_dimensions();
create trigger wardrobe_embedding_dimensions before insert or update on public.wardrobe_embeddings
for each row execute function dressme_private.validate_embedding_dimensions();

-- Owner policies plus composite foreign keys prevent cross-user associations.
-- Computed outputs are readable by their owner but written by the trusted backend.
do $$
declare table_name text;
begin
  foreach table_name in array array[
    'profiles','style_profiles','wardrobe_items','item_images','image_analyses',
    'wardrobe_embeddings','conversations','messages','workflow_runs','bo_executions',
    'redundancy_assessments','gap_analyses','wardrobe_gaps','outfits','outfit_items',
    'inspiration_matches','explanations','explanation_factors','purchase_plans',
    'purchase_plan_items','trips','trip_activities','packing_plans','packing_items',
    'trip_outfits','recommendation_feedback','trace_events'
  ] loop
    execute format('alter table public.%I enable row level security', table_name);
    execute format('revoke all on public.%I from public, anon, authenticated', table_name);
    execute format('grant select on public.%I to authenticated', table_name);
    execute format('grant all on public.%I to service_role', table_name);
    execute format('create policy owner_read on public.%I for select to authenticated using ((select auth.uid()) = %I)',
      table_name, case when table_name = 'profiles' then 'id' else 'user_id' end);
    if table_name <> 'profiles' then
      execute format('create index %I on public.%I (user_id)', table_name || '_user_idx', table_name);
    end if;
  end loop;

  foreach table_name in array array[
    'style_profiles','wardrobe_items','item_images','conversations','trips',
    'trip_activities','recommendation_feedback'
  ] loop
    execute format('grant insert, update, delete on public.%I to authenticated', table_name);
    execute format('create policy owner_write on public.%I for all to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id)', table_name);
  end loop;

  grant update (display_name, default_currency, timezone, location) on public.profiles to authenticated;
  create policy profile_update on public.profiles for update to authenticated
    using ((select auth.uid()) = id) with check ((select auth.uid()) = id);

  foreach table_name in array array[
    'business_objectives','model_versions','clothing_categories','datasets','garments',
    'catalog_images','dataset_samples','garment_pair_labels','catalog_outfits',
    'catalog_outfit_items','garment_embeddings','products'
  ] loop
    execute format('alter table public.%I enable row level security', table_name);
    execute format('revoke all on public.%I from public, anon, authenticated', table_name);
    execute format('grant select on public.%I to authenticated', table_name);
    execute format('grant all on public.%I to service_role', table_name);
    execute format('create policy catalog_read on public.%I for select to authenticated using (true)', table_name);
  end loop;

  foreach table_name in array array['profiles','style_profiles','wardrobe_items','conversations','trips','garments','products'] loop
    execute format('create trigger touch_updated_at before update on public.%I for each row execute function dressme_private.touch_updated_at()', table_name);
  end loop;
end;
$$;

create index wardrobe_category_idx on public.wardrobe_items(user_id, category);
create index messages_conversation_idx on public.messages(conversation_id, created_at);
create index bo_executions_run_idx on public.bo_executions(run_id);
create index trace_events_run_idx on public.trace_events(run_id, created_at);
create index dataset_samples_split_idx on public.dataset_samples(dataset_id, split);
create index products_garment_idx on public.products(garment_id);
create index catalog_images_garment_idx on public.catalog_images(garment_id);
create index dataset_samples_garment_idx on public.dataset_samples(garment_id);
create index pair_labels_garment_a_idx on public.garment_pair_labels(garment_a_id);
create index pair_labels_garment_b_idx on public.garment_pair_labels(garment_b_id);
create index catalog_outfit_items_garment_idx on public.catalog_outfit_items(garment_id);
create index wardrobe_items_catalog_idx on public.wardrobe_items(catalog_garment_id);
create index item_images_item_idx on public.item_images(wardrobe_item_id, user_id);
create index image_analyses_image_idx on public.image_analyses(image_id, user_id);
create index workflow_runs_conversation_idx on public.workflow_runs(conversation_id, user_id);
create index redundancy_execution_idx on public.redundancy_assessments(execution_id, user_id);
create index gap_analyses_execution_idx on public.gap_analyses(execution_id, user_id);
create index wardrobe_gaps_analysis_idx on public.wardrobe_gaps(analysis_id, user_id);
create index outfits_execution_idx on public.outfits(execution_id, user_id);
create index outfit_items_item_idx on public.outfit_items(wardrobe_item_id, user_id);
create index inspiration_execution_idx on public.inspiration_matches(execution_id, user_id);
create index explanations_execution_idx on public.explanations(execution_id, user_id);
create index explanation_factors_parent_idx on public.explanation_factors(explanation_id, user_id);
create index purchase_plans_execution_idx on public.purchase_plans(execution_id, user_id);
create index purchase_plan_items_product_idx on public.purchase_plan_items(product_id);
create index trip_activities_trip_idx on public.trip_activities(trip_id, user_id);
create index packing_plans_trip_idx on public.packing_plans(trip_id, user_id);
create index packing_plans_execution_idx on public.packing_plans(execution_id, user_id);
create index packing_items_item_idx on public.packing_items(wardrobe_item_id, user_id);
create index trip_outfits_plan_idx on public.trip_outfits(plan_id, user_id);
create index trip_outfits_outfit_idx on public.trip_outfits(outfit_id, user_id);
create index feedback_execution_idx on public.recommendation_feedback(execution_id, user_id);
create index trace_events_execution_idx on public.trace_events(execution_id, run_id, user_id);

insert into public.business_objectives (id, name, description) values
  ('BO1','Digital wardrobe','Garment detection, attributes, colors and user validation.'),
  ('BO2','Do I already own this?','Embedding similarity and functional redundancy.'),
  ('BO3','Wardrobe gaps','Coverage and counterfactual outfit gains.'),
  ('BO4','Outfit recommendation, chat and inspiration','Compatibility, retrieval and grounded chat.'),
  ('BO5','Trust and transparency','Feature contributions, counterfactual explanations and heatmaps.'),
  ('BO6','Smart purchasing','Gap coverage, redundancy, outfit benefits and budget optimization.'),
  ('BO7','Packing assistance','Trip outfit coverage and luggage constraints.');

insert into public.clothing_categories (code, label) values
  ('top','Tops'), ('bottom','Bottoms'), ('dress','Dresses'),
  ('outerwear','Outerwear'), ('shoes','Shoes'), ('accessory','Accessories'),
  ('underwear','Underwear'), ('other','Other');

-- Storage object writes happen through the Storage API, not direct SQL.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types) values
  ('wardrobe-images','wardrobe-images',false,10485760,array['image/jpeg','image/png','image/webp']),
  ('explanation-assets','explanation-assets',false,10485760,array['image/jpeg','image/png','image/webp']),
  ('catalog-images','catalog-images',false,10485760,array['image/jpeg','image/png','image/webp'])
on conflict (id) do nothing;

create policy dressme_storage_owner_read on storage.objects for select to authenticated
using (bucket_id in ('wardrobe-images','explanation-assets') and (storage.foldername(name))[1] = (select auth.uid())::text);
create policy dressme_storage_wardrobe_insert on storage.objects for insert to authenticated
with check (bucket_id = 'wardrobe-images' and (storage.foldername(name))[1] = (select auth.uid())::text);
create policy dressme_storage_wardrobe_update on storage.objects for update to authenticated
using (bucket_id = 'wardrobe-images' and (storage.foldername(name))[1] = (select auth.uid())::text)
with check (bucket_id = 'wardrobe-images' and (storage.foldername(name))[1] = (select auth.uid())::text);
create policy dressme_storage_wardrobe_delete on storage.objects for delete to authenticated
using (bucket_id = 'wardrobe-images' and (storage.foldername(name))[1] = (select auth.uid())::text);
create policy dressme_storage_catalog_read on storage.objects for select to authenticated
using (bucket_id = 'catalog-images');

commit;
