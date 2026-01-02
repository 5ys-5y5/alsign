-- =====================================================
-- I-25 해결: historical-market-capitalization API 추가
-- 
-- 문제: fmp-quote API가 현재 시점 marketCap만 반환하여
--       과거 event_date에 잘못된 시가총액이 적용됨
--
-- 해결: fmp-historical-market-capitalization API 사용
--       - from/to 파라미터로 날짜 범위 지정 가능
--       - 응답에 date 필드 포함
--       - event_date 기준 필터링 가능
--
-- API 예시:
--   /stable/historical-market-capitalization?symbol=AAPL&from=2023-10-07&to=2023-10-11
--   응답: [{"symbol":"AAPL","date":"2023-10-11","marketCap":2788655387400}, ...]
--
-- 주의: 주말/휴장일에는 데이터가 없으므로 날짜 범위 조회 후 가장 가까운 날짜 선택 필요
--
-- 참조: https://financialmodelingprep.com/stable/historical-market-capitalization
-- 
-- 작성일: 2025-12-27
-- =====================================================

-- =====================================================
-- 1. API 설정 추가
-- =====================================================
-- 테이블 구조: id, api_service, api, schema, endpoint, function2, created_at
-- URL에 from/to 파라미터 추가 (priceEodOHLC와 동일한 패턴)
INSERT INTO config_lv1_api_list (id, api_service, api, schema, endpoint)
VALUES (
  'fmp-historical-market-capitalization',
  'financialmodelingprep',
  'https://financialmodelingprep.com/stable/historical-market-capitalization?symbol={ticker}&from={fromDate}&to={toDate}&apikey={apiKey}',
  '{
    "symbol": "ticker",
    "date": "date",
    "marketCap": "float"
  }'::jsonb,
  '/stable/historical-market-capitalization'
)
ON CONFLICT (id) DO UPDATE SET
  api_service = EXCLUDED.api_service,
  api = EXCLUDED.api,
  schema = EXCLUDED.schema,
  endpoint = EXCLUDED.endpoint;

-- =====================================================
-- 2. marketCap 메트릭의 api_list_id 변경
-- =====================================================
-- 기존: fmp-quote (현재 시점만)
-- 변경: fmp-historical-market-capitalization (과거 데이터 포함, 날짜 범위 지정)
UPDATE config_lv2_metric
SET 
  api_list_id = 'fmp-historical-market-capitalization',
  response_key = 'marketCap'
WHERE id = 'marketCap';

-- =====================================================
-- 3. 확인 쿼리
-- =====================================================

-- API 추가 확인
SELECT id, api, api_service, endpoint
FROM config_lv1_api_list
WHERE id = 'fmp-historical-market-capitalization';

-- marketCap 메트릭 변경 확인
SELECT id, source, api_list_id, response_key, domain
FROM config_lv2_metric
WHERE id = 'marketCap';

-- marketCap 의존 메트릭 확인 (영향 범위)
SELECT id, expression, domain
FROM config_lv2_metric
WHERE expression LIKE '%marketCap%'
ORDER BY domain, id;

-- fillPriceTrend_dateRange 정책 확인 (날짜 범위 참고용)
SELECT function, policy
FROM config_lv0_policy
WHERE function = 'fillPriceTrend_dateRange';

-- =====================================================
-- 예상 결과:
-- - PER: marketCap / netIncomeTTM (valuation)
-- - PBR: marketCap / equityLatest (valuation)
-- - PSR: marketCap / revenueTTM (valuation)
-- - evEBITDA: (marketCap + netDebtLast) / ebitdaTTM (valuation)
-- =====================================================

-- =====================================================
-- Python 구현 참고:
-- 1. event_date 기준 ±14일 범위로 API 호출
-- 2. 응답에서 event_date 이하의 가장 가까운 날짜 선택
-- 3. 데이터 없으면 NULL 처리
-- 
-- 예시:
--   event_date = 2023-10-09
--   API 호출: from=2023-09-25, to=2023-10-09
--   응답: [2023-10-09, 2023-10-06, 2023-10-05, ...]
--   선택: 2023-10-09 (event_date와 일치)
--
--   event_date = 2023-10-08 (일요일, 데이터 없음)
--   선택: 2023-10-06 (가장 가까운 이전 거래일)
-- =====================================================
