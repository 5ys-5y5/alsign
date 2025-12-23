-- 항목 2: consensusSignal - 누락된 의존성 해결
-- 옵션 A: expression을 제거하고 설명만 남김 (현재 하드코딩된 방식 유지)

UPDATE config_lv2_metric
SET
  expression = NULL,
  description = 'Consensus signal (calculated from evt_consensus table in calculate_qualitative_metrics)'
WHERE id = 'consensusSignal';

-- 확인
SELECT id, source, expression, description
FROM config_lv2_metric
WHERE id = 'consensusSignal';
