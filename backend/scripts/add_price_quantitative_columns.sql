-- Migration: Add price_quantitative and peer_quantitative columns to txn_events
-- Purpose: Extract priceQuantitative from JSONB for easier querying and verification
-- Issue: I-42 - Database persistence verification

-- Add price_quantitative column (extracted from value_quantitative JSONB)
ALTER TABLE txn_events
ADD COLUMN IF NOT EXISTS price_quantitative NUMERIC;

-- Add peer_quantitative column (store peer information for verification)
ALTER TABLE txn_events
ADD COLUMN IF NOT EXISTS peer_quantitative JSONB;

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_txn_events_price_quantitative
ON txn_events(price_quantitative)
WHERE price_quantitative IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_txn_events_ticker_price
ON txn_events(ticker, price_quantitative)
WHERE price_quantitative IS NOT NULL;

-- Backfill price_quantitative from existing value_quantitative data
UPDATE txn_events
SET price_quantitative = (value_quantitative->'valuation'->>'priceQuantitative')::numeric
WHERE value_quantitative IS NOT NULL
  AND value_quantitative->'valuation' IS NOT NULL
  AND value_quantitative->'valuation'->>'priceQuantitative' IS NOT NULL
  AND price_quantitative IS NULL;

-- Backfill peer_quantitative from existing value_quantitative data
-- Store peer count and sector averages for reference
UPDATE txn_events
SET peer_quantitative = jsonb_build_object(
    'peerCount', (value_quantitative->'valuation'->'_meta'->>'peerCount')::int,
    'sectorAvg', value_quantitative->'valuation'->'_meta'->'sectorAvg'
)
WHERE value_quantitative IS NOT NULL
  AND value_quantitative->'valuation'->'_meta' IS NOT NULL
  AND value_quantitative->'valuation'->'_meta'->>'peerCount' IS NOT NULL
  AND peer_quantitative IS NULL;

-- Add comments for documentation
COMMENT ON COLUMN txn_events.price_quantitative IS
'I-42: Extracted priceQuantitative from value_quantitative->valuation for easier querying.
Represents the fair value price estimate from peer comparison analysis.';

COMMENT ON COLUMN txn_events.peer_quantitative IS
'I-42: Peer analysis metadata including peer count and sector averages.
Extracted from value_quantitative->valuation->_meta for verification purposes.';

-- Verification query
SELECT
    ticker,
    event_date::date as event_date,
    price_quantitative,
    peer_quantitative->>'peerCount' as peer_count,
    position_quantitative,
    disparity_quantitative,
    -- Compare with JSONB source
    (value_quantitative->'valuation'->>'priceQuantitative')::numeric as jsonb_price,
    CASE
        WHEN price_quantitative = (value_quantitative->'valuation'->>'priceQuantitative')::numeric
        THEN 'MATCH ✓'
        ELSE 'MISMATCH ✗'
    END as validation
FROM txn_events
WHERE ticker = 'RGTI'
  AND event_date >= '2025-12-17'::timestamptz
  AND event_date < '2025-12-18'::timestamptz
  AND source = 'consensus'
ORDER BY event_date DESC
LIMIT 5;
