-- ============================================================================
-- FIX: priceEodOHLC domain을 internal로 복원
-- ============================================================================
-- 
-- 문제: priceEodOHLC가 'quantitative-momentum' domain으로 잘못 설정됨
-- 
-- 지침서에 따르면:
--   1. momentum 도메인에는 grossMarginLast, grossMarginTTM, operatingMarginTTM, 
--      rndIntensityTTM만 포함되어야 함 (지침서 라인 788-793)
--   2. priceEodOHLC는 priceTrend 기능(price_trend 컬럼)을 위해 사용됨 (지침서 라인 982)
--   3. priceEodOHLC는 internal 도메인이어야 함
--
-- 해결: domain을 'internal'로 복원
-- ============================================================================

-- 현재 상태 확인
\echo '===== [BEFORE] priceEodOHLC 상태 ====='
SELECT id, domain, source, api_list_id
FROM config_lv2_metric
WHERE id = 'priceEodOHLC';

-- domain을 internal로 복원
UPDATE config_lv2_metric
SET domain = 'internal'
WHERE id = 'priceEodOHLC';

-- 변경 후 상태 확인
\echo ''
\echo '===== [AFTER] priceEodOHLC 상태 ====='
SELECT id, domain, source, api_list_id
FROM config_lv2_metric
WHERE id = 'priceEodOHLC';

-- momentum 도메인의 메트릭들 확인 (priceEodOHLC가 제외되었는지 확인)
\echo ''
\echo '===== momentum 도메인 메트릭 목록 ====='
SELECT id, domain, source
FROM config_lv2_metric
WHERE domain LIKE '%momentum%'
ORDER BY id;

\echo ''
\echo '===== 수정 완료 ====='
\echo 'priceEodOHLC는 이제 internal 도메인이며, momentum 도메인에 포함되지 않습니다.'
\echo 'priceEodOHLC는 priceTrend 기능(price_trend 컬럼)에서만 사용됩니다.'

