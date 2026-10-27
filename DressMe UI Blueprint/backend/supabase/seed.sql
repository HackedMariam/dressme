-- Optional synthetic integration fixtures. Run after the initial migration.
-- These are fictional examples, not Fashionpedia/Polyvore data or real offers.
begin;

insert into public.garments
  (id, name, category, subcategory, colors, materials, seasons, occasion_tags, style_tags, weight_g)
values
  ('20000000-0000-4000-8000-000000000001','White cotton T-shirt','top','t-shirt',array['white'],array['cotton'],array['spring','summer','autumn','winter'],array['casual'],array['minimal'],160),
  ('20000000-0000-4000-8000-000000000002','White crew-neck T-shirt','top','t-shirt',array['white'],array['cotton'],array['spring','summer','autumn','winter'],array['casual'],array['minimal'],170),
  ('20000000-0000-4000-8000-000000000003','Navy straight jeans','bottom','jeans',array['navy'],array['denim'],array['spring','summer','autumn','winter'],array['casual'],array['minimal'],620),
  ('20000000-0000-4000-8000-000000000004','White sneakers','shoes','sneakers',array['white'],array['leather'],array['spring','summer','autumn'],array['casual'],array['minimal'],700),
  ('20000000-0000-4000-8000-000000000005','Camel blazer','outerwear','blazer',array['camel'],array['wool'],array['spring','autumn'],array['work','smart_casual'],array['classic'],650),
  ('20000000-0000-4000-8000-000000000006','Black trousers','bottom','trousers',array['black'],array['cotton'],array['spring','summer','autumn','winter'],array['work','smart_casual'],array['classic'],420),
  ('20000000-0000-4000-8000-000000000007','Waterproof rain jacket','outerwear','rain_jacket',array['olive'],array['polyester'],array['spring','autumn','winter'],array['outdoor'],array['practical'],450),
  ('20000000-0000-4000-8000-000000000008','Ivory wool sweater','top','sweater',array['ivory'],array['wool'],array['autumn','winter'],array['casual'],array['classic'],380),
  ('20000000-0000-4000-8000-000000000009','Black ankle boots','shoes','boots',array['black'],array['leather'],array['autumn','winter'],array['work','smart_casual'],array['classic'],950),
  ('20000000-0000-4000-8000-000000000010','Navy scarf','accessory','scarf',array['navy'],array['wool'],array['autumn','winter'],array['casual','work'],array['classic'],130)
on conflict (id) do nothing;

-- No fabricated accounts, model predictions, embeddings, photos or retailer prices.
commit;

