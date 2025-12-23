-- 항목 1: priceEodOHLC - dict response_key 문제 해결
-- 옵션 A: response_key를 단일 필드로 변경 (close 가격만 사용)

UPDATE config_lv2_metric
SET
  response_key = '"close"',
  description = 'EOD Close Price'
WHERE id = 'priceEodOHLC';

-- 확인
SELECT id, source, api_list_id, response_key, description
FROM config_lv2_metric
WHERE id = 'priceEodOHLC';
