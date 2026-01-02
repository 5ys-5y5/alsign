-- I-41: Add priceQuantitative metric to config_lv2_metric
-- This metric implements the original design requirement from 1_guideline(function).ini:892-897
-- It replaces the temporary calcFairValue parameter approach (I-36, I-38, I-40)
--
-- Design Decision:
-- - Incorporates the peer-based sector-average fair value calculation logic
-- - Uses fmp-stock-peers API to get peer tickers (implicit, handled in code)
-- - Calculates: sector_avg_PER × (price / current_PER) OR sector_avg_PBR × (price / current_PBR)
-- - Falls back to NULL when peer tickers don't exist (small-cap, special sectors)
--
-- This deprecates:
-- - I-36: calcFairValue parameter-based approach
-- - I-38: calcFairValue default value change
-- - I-40: Null handling for missing peer tickers

-- Step 1: Update CHECK CONSTRAINT to allow source='custom'
ALTER TABLE config_lv2_metric
DROP CONSTRAINT IF EXISTS config_lv2_metric_source_consistency_check;

ALTER TABLE config_lv2_metric
ADD CONSTRAINT config_lv2_metric_source_consistency_check
CHECK (
    ((source = 'api_field'::metric_source) AND (api_list_id IS NOT NULL) AND (response_key IS NOT NULL)) OR
    ((source = 'aggregation'::metric_source) AND (aggregation_kind IS NOT NULL)) OR
    ((source = 'expression'::metric_source) AND (expression IS NOT NULL)) OR
    (source = 'custom'::metric_source)
);

-- Step 2: Insert  metric
INSERT INTO config_lv2_metric (
    id,
    description,
    source,
    api_list_id,
    base_metric_id,
    aggregation_kind,
    aggregation_params,
    expression,
    domain,
    response_path,
    response_key
)
VALUES (
    'priceQuantitative',
    'Fair value price based on sector-average valuation multiples. Calculated as: sector_avg_PER × EPS (or sector_avg_PBR × BPS if PER unavailable). Uses fmp-stock-peers API to determine peer group. Returns NULL if no peer tickers available.',
    'custom',
    NULL,
    NULL,
    NULL,
    '{
        "calculation_method": "sector_average_fair_value",
        "peer_api": "fmp-stock-peers",
        "valuation_metrics": ["PER", "PBR"],
        "max_peers": 10,
        "outlier_removal": "iqr_1.5"
    }'::jsonb,
    NULL,
    'quantitative-valuation',
    NULL,
    NULL
)
ON CONFLICT (id) DO UPDATE SET
    description = EXCLUDED.description,
    source = EXCLUDED.source,
    api_list_id = EXCLUDED.api_list_id,
    base_metric_id = EXCLUDED.base_metric_id,
    aggregation_kind = EXCLUDED.aggregation_kind,
    aggregation_params = EXCLUDED.aggregation_params,
    expression = EXCLUDED.expression,
    domain = EXCLUDED.domain,
    response_path = EXCLUDED.response_path,
    response_key = EXCLUDED.response_key;

-- Verify the insert
SELECT id, domain, source, description, aggregation_params
FROM config_lv2_metric
WHERE id = 'priceQuantitative';

-- Note: The actual calculation logic remains in backend/src/services/valuation_service.py
-- Functions: get_peer_tickers(), calculate_sector_average_metrics(), calculate_fair_value_from_sector()
-- The metric engine will detect source='custom' and delegate to the valuation service.
