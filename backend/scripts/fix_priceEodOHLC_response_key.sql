-- Fix priceEodOHLC response_key to match schema-mapped field names
-- Issue: config_lv1_api_list schema maps 'open' -> 'priceEodOpen', etc.
-- But config_lv2_metric.response_key still references unmapped names

-- Current (incorrect):
-- {"low": "low", "high": "high", "open": "open", "close": "close"}

-- Should be (correct):
-- {"low": "priceEodLow", "high": "priceEodHigh", "open": "priceEodOpen", "close": "priceEodClose"}

UPDATE config_lv2_metric
SET response_key = '{
  "low": "priceEodLow",
  "high": "priceEodHigh",
  "open": "priceEodOpen",
  "close": "priceEodClose"
}'::jsonb
WHERE id = 'priceEodOHLC';

-- Verification
SELECT 
    id,
    api_list_id,
    response_key::text as response_key
FROM config_lv2_metric
WHERE id = 'priceEodOHLC';

-- Expected output:
-- id            | api_list_id                   | response_key
-- --------------+-------------------------------+--------------------------------------------------
-- priceEodOHLC  | fmp-historical-price-eod-full | {"low": "priceEodLow", "high": "priceEodHigh", "open": "priceEodOpen", "close": "priceEodClose"}

