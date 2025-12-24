-- Verify all config_lv1_api_list schemas are dict type, not list type
-- Issue: Some schemas might be stored as [{'key': 'value'}] instead of {'key': 'value'}

SELECT 
    api,
    jsonb_typeof(schema) as schema_type,
    CASE 
        WHEN jsonb_typeof(schema) = 'array' THEN 'ERROR: Schema is array, should be object'
        WHEN jsonb_typeof(schema) = 'object' THEN 'OK'
        ELSE 'UNKNOWN'
    END as status,
    schema::text as schema_preview
FROM config_lv1_api_list
ORDER BY 
    CASE WHEN jsonb_typeof(schema) = 'array' THEN 0 ELSE 1 END,  -- Show errors first
    api;

-- Expected output: All should show 'object' type, not 'array'
-- If any show 'array', they need to be fixed!

