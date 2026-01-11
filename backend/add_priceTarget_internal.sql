-- Add priceTarget as internal metric (custom source)
-- Data is fetched from evt_consensus table and passed via custom_values
-- This is the first step, consensus will use this as base_metric_id

INSERT INTO config_lv2_metric (
    id,
    domain,
    source,
    api_list_id,
    response_key,
    description,
    created_at
) VALUES (
    'priceTarget',
    'internal',
    'custom',  -- Custom source: data provided via custom_values from evt_consensus
    NULL,  -- No direct API access
    NULL,  -- No response_key needed
    'Raw price target data from evt_consensus table. Used as intermediate data for consensus calculation.',
    NOW()
)
ON CONFLICT (id) DO UPDATE SET
    domain = EXCLUDED.domain,
    source = EXCLUDED.source,
    api_list_id = EXCLUDED.api_list_id,
    response_key = EXCLUDED.response_key,
    description = EXCLUDED.description;

-- Verify
SELECT id, domain, source, api_list_id, response_key, description
FROM config_lv2_metric
WHERE id = 'priceTarget';
