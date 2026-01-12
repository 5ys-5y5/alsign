create or replace view public.txn_events_with_price as
select
  t.id,
  t.ticker,
  t.event_date,
  t.source,
  t.source_id,
  t.position_quantitative,
  t.disparity_quantitative,
  t.position_qualitative,
  t.disparity_qualitative,
  t.price_quantitative,
  hp.price as price
from public.txn_events t
join public.config_lv3_quantitatives c
  on c.ticker = t.ticker
left join lateral (
  select hp_elem as price
  from jsonb_array_elements(c.historical_price) as hp_elem
  where (hp_elem->>'date')::date = t.event_date::date
  limit 1
) hp on true;