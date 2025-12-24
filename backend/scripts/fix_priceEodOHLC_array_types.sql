-- ============================================================================
-- FIX: priceEodOHLC Array Type Issues
-- ============================================================================
--
-- Issue: api_list_id or response_key stored as array instead of proper type
-- Error: unhashable type: 'list' when trying to add to set()
--
-- ============================================================================

-- Fix 1: If api_list_id is stored as array, convert to string
UPDATE config_lv2_metric
SET api_list_id = 'fmp-historical-price-eod-full'
WHERE id = 'priceEodOHLC'
  AND (api_list_id IS NULL OR api_list_id = '' OR api_list_id::text LIKE '[%');

-- Fix 2: If response_key is stored as array, convert to object
UPDATE config_lv2_metric
SET response_key = '{
  "low": "low",
  "high": "high",
  "open": "open",
  "close": "close"
}'::jsonb
WHERE id = 'priceEodOHLC'
  AND jsonb_typeof(response_key) = 'array';

-- Fix 3: Ensure config_lv1_api_list schema is object (not array)
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
WHERE api = 'https://financialmodelingprep.com/stable/historical-price-eod/full?symbol={ticker}&from={fromDate}&to={toDate}&apikey={apiKey}'
  AND jsonb_typeof(schema) = 'array';

-- Verification
\echo ''
\echo '===== Verification ====='
SELECT 
    'priceEodOHLC config' as check_name,
    id,
    api_list_id,
    CASE 
        WHEN api_list_id IS NULL OR api_list_id = '' THEN 'ERROR: NULL or empty'
        WHEN api_list_id::text LIKE '[%' THEN 'ERROR: Still array'
        ELSE 'OK'
    END as api_list_id_status,
    jsonb_typeof(response_key) as response_key_type,
    CASE 
        WHEN jsonb_typeof(response_key) = 'object' THEN 'OK'
        ELSE 'ERROR: Not object'
    END as response_key_status
FROM config_lv2_metric
WHERE id = 'priceEodOHLC';

\echo ''
SELECT 
    'fmp-historical-price schema' as check_name,
    jsonb_typeof(schema) as schema_type,
    CASE 
        WHEN jsonb_typeof(schema) = 'object' THEN 'OK'
        ELSE 'ERROR: Not object'
    END as schema_status
FROM config_lv1_api_list
WHERE api = 'https://financialmodelingprep.com/stable/historical-price-eod/full?symbol={ticker}&from={fromDate}&to={toDate}&apikey={apiKey}';

