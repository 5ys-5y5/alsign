-- Config 수정 이슈 문서 반영 SQL 스크립트
-- 작성일: 2025-12-24
-- 목적: config_lv2_metric 테이블과 실제 구현 간의 불일치 해결

-- ============================================
-- 항목 1: consensusSignal aggregation 방식으로 변경
-- ============================================

-- 1-1. consensusSignal을 aggregation 타입으로 변경
-- expression을 NULL로 설정하여 buildConsensusSignal(consensusWithPrev) 의존성 제거
-- 참고: base_metric_id는 NULL로 설정 (consensusRaw 메트릭이 아직 생성되지 않음)
--       leadPairFromList aggregation 구현 후 base_metric_id 추가 필요
UPDATE config_lv2_metric
SET
  source = 'aggregation',
  expression = NULL,
  base_metric_id = NULL,
  aggregation_kind = 'leadPairFromList',
  aggregation_params = '{
    "partitionBy": ["ticker", "analyst_name", "analyst_company"],
    "orderBy": [{"event_date": "desc"}],
    "leadFields": [
      {"field": "price_target", "as": "price_target_prev"},
      {"field": "price_when_posted", "as": "price_when_posted_prev"}
    ],
    "emitPrevRow": true
  }'::jsonb,
  description = 'Consensus signal built from evt_consensus using aggregation. Uses leadPairFromList to find previous record for same ticker/analyst combination. Includes direction, last, prev, delta, deltaPct. NOTE: Currently hardcoded in calculate_qualitative_metrics() until leadPairFromList aggregation is implemented.'
WHERE id = 'consensusSignal';

-- 1-2. base_metric으로 사용할 consensusRaw 메트릭 추가 (보류)
-- 이유: db_field source 타입이 아직 구현되지 않음
-- 필요한 작업:
--   1. MetricCalculationEngine에 db_field source 타입 추가
--   2. evt_consensus 테이블에서 데이터를 가져오는 로직 구현
--   3. 아래 메트릭 추가
--
-- INSERT INTO config_lv2_metric (id, source, api_list_id, response_key, domain, description)
-- VALUES (
--   'consensusRaw',
--   'db_field',
--   NULL,
--   '{"price_target": "price_target", "price_when_posted": "price_when_posted", "direction": "direction", "analyst_name": "analyst_name", "analyst_company": "analyst_company", "ticker": "ticker", "event_date": "event_date"}'::jsonb,
--   'internal',
--   'Raw consensus data from evt_consensus table'
-- )
-- ON CONFLICT (id) DO UPDATE SET
--   source = EXCLUDED.source,
--   response_key = EXCLUDED.response_key,
--   description = EXCLUDED.description;
--
-- 현재 상태: consensusSignal의 base_metric_id는 NULL로 유지

-- ============================================
-- 항목 2: priceEodOHLC
-- ============================================
-- 조치 없음 (정상)

-- ============================================
-- 항목 3: targetMedian & consensusSummary
-- ============================================
-- SQL 수정 불필요 (consensusSummary가 이미 올바르게 설정됨)
-- Python 코드에서 consensusSummary dict에서 targetMedian 추출

-- ============================================
-- 항목 4: 짧은 이름 메트릭
-- ============================================
-- 조치 없음 (현재 상태 유지)

-- ============================================
-- 항목 5: consensus 메트릭 추가
-- ============================================

-- fmp-price-target API를 활용한 consensus 메트릭 추가
INSERT INTO config_lv2_metric (id, source, api_list_id, response_key, domain, description)
VALUES (
  'consensus',
  'api_field',
  'fmp-price-target',
  '{"ticker": "symbol", "newsURL": "newsURL", "newsTitle": "newsTitle", "event_date": "publishedDate", "analystName": "analystName", "newsBaseURL": "newsBaseURL", "priceTarget": "priceTarget", "newsPublisher": "newsPublisher", "publishedDate": "publishedDate", "adjPriceTarget": "adjPriceTarget", "analystCompany": "analystCompany", "priceWhenPosted": "priceWhenPosted"}'::jsonb,
  'qualatative-consensus',
  'Consensus data from fmp-price-target API. Includes analyst info, news details, and price targets.'
)
ON CONFLICT (id) DO UPDATE SET
  source = EXCLUDED.source,
  api_list_id = EXCLUDED.api_list_id,
  response_key = EXCLUDED.response_key,
  domain = EXCLUDED.domain,
  description = EXCLUDED.description;

-- ============================================
-- 항목 6: consensusWithPrev
-- ============================================
-- 조치 불필요 (항목 1의 개선안 적용으로 해결됨)
-- consensusSignal의 expression이 NULL이 되어 consensusWithPrev 의존성 제거됨

-- ============================================
-- 검증 쿼리
-- ============================================

-- 변경된 메트릭 확인
SELECT 
  id, 
  source, 
  expression, 
  base_metric_id, 
  aggregation_kind,
  domain,
  description
FROM config_lv2_metric
WHERE id IN ('consensusSignal', 'consensusSummary', 'consensus')
ORDER BY id;

