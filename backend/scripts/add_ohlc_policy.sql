-- ============================================================================
-- Add priceEodOHLC_dateRange policy to config_lv0_policy
-- ============================================================================
--
-- Issue: I-10
-- This policy defines the date range for OHLC API fetch operations.
-- Separate from fillPriceTrend_dateRange policy.
--
-- Usage:
-- 1. Open Supabase Dashboard SQL Editor
-- 2. Copy and paste this script
-- 3. Click "Run" to execute
-- ============================================================================

-- Insert priceEodOHLC_dateRange policy
INSERT INTO config_lv0_policy (
    endpoint,
    function,
    description,
    policy
)
VALUES (
    'priceEodOHLC',
    'priceEodOHLC_dateRange',
    'OHLC API fetch date range (calendar days offset from event dates)',
    '{
        "countStart": -30,
        "countEnd": 7
    }'::jsonb
)
ON CONFLICT (function) DO UPDATE SET
    endpoint = EXCLUDED.endpoint,
    description = EXCLUDED.description,
    policy = EXCLUDED.policy;

-- Verify the insert
SELECT function, policy, description
FROM config_lv0_policy
WHERE function = 'priceEodOHLC_dateRange';

