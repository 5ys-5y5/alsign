-- Fix config_lv1_api_list schema for fmp-historical-price-eod-full
-- Issue: Schema stored as array [{}] instead of object {}
-- FMP API returns: open, high, low, close
-- Solution: Store schema as dict (object) type, not array

-- CRITICAL FIX: Schema must be a dict, not a list!
-- Current (WRONG): [{'low': 'low', ...}]  <- list type causes 'list' object has no attribute 'items'
-- Correct (RIGHT): {'low': 'low', ...}    <- dict type

UPDATE config_lv1_api_list
SET schema = '{
  "symbol": "ticker",
  "date": "date",
  "open": "open",
  "high": "high",
  "low": "low",
  "close": "close",
  "volume": "volume",
  "change": "change",
  "changePercent": "changePercent",
  "vwap": "vwap"
}'::jsonb
WHERE api = 'https://financialmodelingprep.com/stable/historical-price-eod/full?symbol={ticker}&from={fromDate}&to={toDate}&apikey={apiKey}';

-- Verification
SELECT 
    api,
    jsonb_typeof(schema) as schema_type,
    CASE 
        WHEN jsonb_typeof(schema) = 'object' THEN 'OK'
        ELSE 'ERROR'
    END as status,
    schema::text
FROM config_lv1_api_list
WHERE api = 'https://financialmodelingprep.com/stable/historical-price-eod/full?symbol={ticker}&from={fromDate}&to={toDate}&apikey={apiKey}';

-- Expected result:
-- After this change, response_key can use original field names:
-- {"low": "low", "high": "high", "open": "open", "close": "close"}
-- No need to change config_lv2_metric.response_key!

-- Verify config_lv2_metric is correct
SELECT 
    id,
    response_key::text
FROM config_lv2_metric
WHERE id = 'priceEodOHLC';

-- Should show:
-- {"low": "low", "high": "high", "open": "open", "close": "close"}
-- This is correct! No change needed.

