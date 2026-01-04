-- Backfill price_quantitative from value_quantitative JSONB
UPDATE txn_events
SET price_quantitative = (value_quantitative->'valuation'->>'priceQuantitative')::numeric
WHERE value_quantitative IS NOT NULL
  AND value_quantitative->'valuation' IS NOT NULL
  AND value_quantitative->'valuation'->>'priceQuantitative' IS NOT NULL
  AND price_quantitative IS NULL;

-- Backfill peer_quantitative with peer count and sector averages
UPDATE txn_events
SET peer_quantitative = jsonb_build_object(
    'peerCount', (value_quantitative->'valuation'->'_meta'->>'peerCount')::int,
    'sectorAvg', value_quantitative->'valuation'->'_meta'->'sectorAvg'
)
WHERE value_quantitative IS NOT NULL
  AND value_quantitative->'valuation'->'_meta' IS NOT NULL
  AND value_quantitative->'valuation'->'_meta'->>'peerCount' IS NOT NULL
  AND peer_quantitative IS NULL;
