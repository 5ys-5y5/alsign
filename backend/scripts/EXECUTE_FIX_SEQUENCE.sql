-- ============================================================================
-- EXECUTION SEQUENCE for I-18: priceEodOHLC Field Mapping Issue
-- ============================================================================
-- 
-- Issue: Schema stored as array [{}] instead of object {}
-- Impact: AttributeError: 'list' object has no attribute 'items'
-- 
-- Execute in this order:
-- ============================================================================

-- Step 1: Verify the problem
\echo '===== Step 1: Verify Problem ====='
SELECT 
    'BEFORE FIX' as stage,
    api,
    jsonb_typeof(schema) as schema_type,
    CASE 
        WHEN jsonb_typeof(schema) = 'array' THEN 'ERROR: Schema is array'
        WHEN jsonb_typeof(schema) = 'object' THEN 'OK'
        ELSE 'UNKNOWN'
    END as status
FROM config_lv1_api_list
WHERE api = 'https://financialmodelingprep.com/stable/historical-price-eod/full?symbol={ticker}&from={fromDate}&to={toDate}&apikey={apiKey}';

-- Step 2: Fix the schema (array -> object)
\echo ''
\echo '===== Step 2: Apply Fix ====='
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

-- Step 3: Verify the fix
\echo ''
\echo '===== Step 3: Verify Fix ====='
SELECT 
    'AFTER FIX' as stage,
    api,
    jsonb_typeof(schema) as schema_type,
    CASE 
        WHEN jsonb_typeof(schema) = 'object' THEN 'OK: Fixed!'
        ELSE 'ERROR: Still broken'
    END as status,
    schema::text as schema_content
FROM config_lv1_api_list
WHERE api = 'https://financialmodelingprep.com/stable/historical-price-eod/full?symbol={ticker}&from={fromDate}&to={toDate}&apikey={apiKey}';

-- Step 4: Verify no other APIs have array schemas
\echo ''
\echo '===== Step 4: Check All APIs ====='
SELECT 
    COUNT(*) FILTER (WHERE jsonb_typeof(schema) = 'array') as array_count,
    COUNT(*) FILTER (WHERE jsonb_typeof(schema) = 'object') as object_count,
    COUNT(*) as total_count
FROM config_lv1_api_list;

-- Expected output:
-- array_count | object_count | total_count
-- ------------+--------------+-------------
--           0 |           19 |          19

\echo ''
\echo '===== Fix Complete! ====='
\echo 'Next steps:'
\echo '1. Restart backend to clear cache'
\echo '2. Re-run POST /backfillEventsTable'
\echo '3. Verify priceEodOHLC extraction succeeds'

