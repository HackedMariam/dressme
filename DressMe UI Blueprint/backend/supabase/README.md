# DressMe Supabase database

Shared schema for all seven confirmed business objectives, applied to the
[DressMe project](https://supabase.com/dashboard/project/gxmvxegwlntqpcardrjq)
on 11 October 2026. Project region: Ireland (`eu-west-1`), as created in the dashboard.
API URL: `https://gxmvxegwlntqpcardrjq.supabase.co`.

All 30 application tables have RLS. Three private image buckets and synthetic
integration fixtures are installed. No app users have been created; Supabase
dashboard accounts are separate from application Auth users.

## Apply to a new project

1. Create or select the DressMe Supabase project.
2. Apply `migrations/20261011152406_dressme_initial_schema.sql`, then
   `migrations/20261011152606_dressme_indexes_and_policies.sql` as migrations.
   It can also be run in the project's SQL Editor. Run it once; it uses a
   transaction and aborts on application-table name conflicts.
3. Optionally run `seed.sql` in development. It is repeatable and adds ten
   fictional garments.
4. Sign up a real test account through Supabase Auth. The signup trigger creates
   its `profiles` and `style_profiles` records with the Auth user ID.
5. Upload images using the Supabase Storage API; SQL creates buckets and metadata,
   not the image files themselves.

No real training dataset is downloaded or imported. Fashionpedia, Polyvore,
FashionCLIP weights, and retailer catalogs require their own sources, licenses,
and import procedures. The seed is integration data, not training evidence.

## Tables by responsibility

| Area | Tables |
| --- | --- |
| Accounts | `profiles`, `style_profiles`; credentials remain in Supabase `auth.users` |
| Shared data/model registry | `business_objectives`, `clothing_categories`, `model_versions` |
| Shared clothing catalog | `garments`, `catalog_images`, `garment_embeddings` |
| BO1 Digital wardrobe | `wardrobe_items`, `item_images`, `image_analyses`, `wardrobe_embeddings` |
| BO2 Redundancy | `redundancy_assessments` |
| BO3 Gaps | `gap_analyses`, `wardrobe_gaps` |
| BO4 Outfits/chat/inspiration | `outfits`, `outfit_items`, `conversations`, `messages` |
| BO5 Trust and transparency | `explanations` |
| BO6 Smart purchasing | `products`, `purchase_plans`, `purchase_plan_items` |
| BO7 Packing | `trips`, `trip_activities`, `packing_plans`, `packing_items`, `trip_outfits` |
| Orchestration/observability | `workflow_runs`, `bo_executions` |

There is no Critic Agent table. BO5 records actual explanations, supporting
evidence, counterfactuals and heatmap paths. BO6 records purchase benefit and
redundancy assessments as well as prices and budgets.

## Shared conventions

- `id` is the record ID; `user_id` always references `profiles.id = auth.users.id`.
- Timestamps are `timestamptz`; exchange them as UTC ISO timestamps.
- Amounts use integer currency minor units. Prices within a purchase plan must
  be converted by the backend into that plan's currency before inclusion.
- Weight is grams. Missing weight, price, confidence or scores remain NULL.
- Redundancy/confidence scores use 0–1; outfit compatibility uses 0–100.
- Each wardrobe row represents one physical garment, so packing entries cannot
  duplicate that item. A wardrobe item's price means its actual purchase price.
- Shared catalogs contain licensed/public or synthetic records. Private user
  images and attributes remain in user-owned tables.
- Register the actual model name, version and embedding dimensions before saving
  embeddings. Dimension checks reject inconsistent vectors. No vector index is
  created until the team fixes the model/dimension; index each model's vectors
  separately. Do not compare embeddings from different model versions.

## Access and backend responsibilities

All application tables enable RLS. Anonymous users have no table access.
Authenticated users read their own records and the shared catalog. They can edit
profile preferences, their wardrobe, images, trips, conversation titles and
feedback. Computed recommendations, traces, explanations, embeddings and shared
catalog changes are written by the trusted backend.

Supabase secret/service-role credentials bypass RLS and must stay server-side.
The backend must verify the caller's identity, scope every operation by user ID,
and validate all nested IDs in JSON and arrays. Relational associations use
composite foreign keys to prevent cross-user links. Explanation evidence and
retrieval-result JSON still require backend validation.

Buckets are private: `wardrobe-images`, `explanation-assets`, `catalog-images`.
User-owned object paths start with `<user_id>/`. Users upload wardrobe images;
the backend writes explanation heatmaps and shared catalog images. Ten MB is an
application-selected per-image limit. Use signed URLs when showing private assets.

The backend must compute purchase totals, check quote freshness/currency, validate
trip activity dates, handle unknown garment weights, and validate packed outfits
against selected items. JSON stores model-dependent details; each BO's adapter
must validate its agreed request/response schema before inserting them.

LangGraph can install its own checkpoint tables using its chosen persistence
adapter later. `workflow_runs` is the application record, not a replacement for
that adapter's checkpoint format. Model hosting, agents, training pipelines and
frontend API wiring are subsequent implementation steps.

## Verification before integration

Database checks passed on the hosted project: Auth-row insertion creates both
profile records; owner reads/writes succeed; cross-user reads, writes and owner
reassignment are blocked; cross-user outfit associations fail foreign-key checks;
incorrect embedding dimensions are rejected; anonymous roles cannot read private
tables; users cannot write model outputs or shared catalog records. Temporary
test identities and records were rolled back. This tests database rules, not the
frontend signup flow or an actual image upload.

Seed data was applied twice and remained ten garments, ten samples, two pair
labels and two outfits. Security advisors returned no findings. Performance
advisors returned only [unused-index information](https://supabase.com/docs/guides/database/database-linter?lint=0005_unused_index),
expected before application workloads use the new tables. Missing foreign-key
indexes and overlapping owner policies were resolved in the second migration.

Before connecting the UI:

Confirm signup creates the profile; authenticate two different test users and
check that they cannot read or link each other's wardrobe, trips and results.
Check image storage access under both identities. Register one real embedding
model and check that mismatched dimensions are rejected. Apply seed twice and
confirm it does not duplicate catalog fixtures.

## Prototype simplification

Removed nine optional tables on 11 October 2026: datasets, dataset_samples,
garment_pair_labels, catalog_outfits, catalog_outfit_items, recommendation_feedback,
trace_events, explanation_factors, and inspiration_matches. Existing fixture rows
in those tables were deleted. The ten garment fixtures remain. All 30 remaining
public tables retain RLS. Historical migrations retain the original schema; apply
all migrations in order. Training datasets stay outside the application database
initially, explanation details use explanations, and detailed traces use backend logs.

