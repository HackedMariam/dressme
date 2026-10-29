begin;
-- Remove optional prototype tables; RESTRICT protects dependencies outside this set.
drop table public.catalog_outfit_items, public.catalog_outfits, public.garment_pair_labels, public.dataset_samples, public.datasets, public.recommendation_feedback, public.trace_events, public.explanation_factors, public.inspiration_matches restrict;
commit;
