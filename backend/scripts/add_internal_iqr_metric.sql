-- Add missing returnIQRByDayOffset metric to config_lv2_metric
-- This metric calculates the interquartile range (IQR) of return distribution

-- Insert returnIQRByDayOffset metric (expression-based: p75 - p25)
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
    'returnIQRByDayOffset',
    'Interquartile range (IQR) of return distribution by dayOffset (p75 - p25)',
    'expression',
    NULL,
    'priceTrendReturnSeries',
    NULL,
    '{}'::jsonb,
    'returnThirdQuartileByDayOffset - returnFirstQuartileByDayOffset',
    'internal(qual)',
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
SELECT id, domain, source, expression, base_metric_id
FROM config_lv2_metric
WHERE id = 'returnIQRByDayOffset';

-- Show all internal(qual) metrics (should be 7 total)
SELECT id, domain, source, aggregation_kind, expression
FROM config_lv2_metric
WHERE domain = 'internal(qual)'
  AND base_metric_id = 'priceTrendReturnSeries'
ORDER BY id;

