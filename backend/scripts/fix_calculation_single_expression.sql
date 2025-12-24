-- I-12: calculation 코드를 single expression으로 재작성
-- 작성일: 2025-12-24
-- 이유: eval()은 single expression만 지원, multiple statements는 syntax 에러 발생

-- avgFromQuarter: 분기 시계열 평균
UPDATE config_lv2_metric_transform
SET calculation = 'None if not quarterly_values else sum(quarterly_values[:params.get("window", 4)]) / len(quarterly_values[:params.get("window", 4)])'
WHERE id = 'avgFromQuarter';

-- ttmFromQuarterSumOrScaled: TTM 합산
UPDATE config_lv2_metric_transform
SET calculation = 'None if not quarterly_values or len(quarterly_values[:params.get("window", 4)]) < params.get("min_points", 1) else (lambda recent: sum(recent) if len(recent) >= params.get("scale_to", 4) else (sum(recent) / len(recent)) * params.get("scale_to", 4))(quarterly_values[:params.get("window", 4)])'
WHERE id = 'ttmFromQuarterSumOrScaled';

-- lastFromQuarter: 최신 값 반환
UPDATE config_lv2_metric_transform
SET calculation = 'None if not quarterly_values else quarterly_values[0]'
WHERE id = 'lastFromQuarter';

-- qoqFromQuarter: 전분기 대비 증감률
UPDATE config_lv2_metric_transform
SET calculation = 'None if len(quarterly_values) < 2 or quarterly_values[1] == 0 else (quarterly_values[0] - quarterly_values[1]) / quarterly_values[1]'
WHERE id = 'qoqFromQuarter';

-- yoyFromQuarter: 전년동기 대비 증감률
UPDATE config_lv2_metric_transform
SET calculation = 'None if len(quarterly_values) < 5 or quarterly_values[4] == 0 else (quarterly_values[0] - quarterly_values[4]) / quarterly_values[4]'
WHERE id = 'yoyFromQuarter';

-- 검증: 업데이트된 calculation 확인
SELECT 
    id,
    LEFT(calculation, 100) as calculation_preview,
    LENGTH(calculation) as calc_length
FROM config_lv2_metric_transform
WHERE id IN ('avgFromQuarter', 'ttmFromQuarterSumOrScaled', 'lastFromQuarter', 'qoqFromQuarter', 'yoyFromQuarter')
ORDER BY id;

