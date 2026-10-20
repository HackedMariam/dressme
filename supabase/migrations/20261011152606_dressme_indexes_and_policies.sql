-- Preserve owner access while removing duplicated SELECT policies.
begin;
do $$
declare table_name text;
begin
  foreach table_name in array array[
    'style_profiles','wardrobe_items','item_images','conversations',
    'trips','trip_activities','recommendation_feedback'
  ] loop
    execute format('drop policy owner_read on public.%I', table_name);
  end loop;
end;
$$;
-- Cover every remaining foreign-key association, including composite ownership.
create index model_versions_bo_idx on public.model_versions(bo_id);
create index bo_executions_bo_idx on public.bo_executions(bo_id);
create index bo_executions_model_idx on public.bo_executions(model_id);
create index bo_executions_run_owner_idx on public.bo_executions(run_id,user_id);
create index catalog_outfits_dataset_idx on public.catalog_outfits(dataset_id);
create index garment_embeddings_model_idx on public.garment_embeddings(model_id);
create index garments_category_idx on public.garments(category);
create index image_analyses_model_idx on public.image_analyses(model_id);
create index inspiration_outfit_idx on public.inspiration_matches(reconstructed_outfit_id,user_id);
create index inspiration_image_idx on public.inspiration_matches(source_image_id,user_id);
create index messages_conversation_owner_idx on public.messages(conversation_id,user_id);
create index outfit_items_outfit_owner_idx on public.outfit_items(outfit_id,user_id);
create index packing_items_plan_owner_idx on public.packing_items(plan_id,user_id);
create index purchase_items_plan_owner_idx on public.purchase_plan_items(plan_id,user_id);
create index trace_events_run_owner_idx on public.trace_events(run_id,user_id);
create index wardrobe_embeddings_model_idx on public.wardrobe_embeddings(model_id);
create index wardrobe_embeddings_item_owner_idx on public.wardrobe_embeddings(wardrobe_item_id,user_id);
create index wardrobe_gaps_category_idx on public.wardrobe_gaps(category);
create index wardrobe_items_category_idx on public.wardrobe_items(category);
commit;
