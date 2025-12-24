-- ============================================================================
-- DIAGNOSIS: priceEodOHLC "unhashable type: 'list'" Error
-- ============================================================================
--
-- Error: unhashable type: 'list'
-- Location: metric_engine.py line 74: api_ids.add(api_list_id)
-- Cause: api_list_id or response_key stored as array instead of string/object
--
-- ============================================================================

\echo '===== Step 1: Check priceEodOHLC metric configuration ====='
SELECT 
    id,
    api_list_id,
    jsonb_typeof(api_list_id::jsonb) as api_list_id_type,
    response_key,
    jsonb_typeof(response_key) as response_key_type,
    source
FROM config_lv2_metric
WHERE id = 'priceEodOHLC';

-- Expected:
-- api_list_id should be TEXT (not jsonb array)
-- response_key should be 'object' type: {"low": "low", ...}

\echo ''
\echo '===== Step 2: Check fmp-historical-price-eod-full API schema ====='
SELECT 
    id,
    api,
    jsonb_typeof(schema) as schema_type,
    schema::text as schema_content
FROM config_lv1_api_list
WHERE api LIKE '%historical-price-eod%';

-- Expected:
-- schema should be 'object' type: {"symbol": "ticker", ...}

\echo ''
\echo '===== Step 3: Check all metrics with array-type fields ====='
SELECT 
    id,
    api_list_id,
    'api_list_id is array' as issue
FROM config_lv2_metric
WHERE api_list_id::text LIKE '[%'
UNION ALL
SELECT 
    id,
    response_key::text,
    'response_key is array' as issue
FROM config_lv2_metric
WHERE jsonb_typeof(response_key) = 'array';

-- Expected: No results (no arrays)

\echo ''
\echo '===== Diagnosis Complete ====='

