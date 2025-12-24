# I-01: consensusSignal leadPairFromList Aggregation - 완료 보고서

## 📋 작업 요약

**이슈**: consensusSignal 메트릭이 존재하지 않는 consensusWithPrev에 의존  
**목표**: leadPairFromList aggregation 구현으로 동적 consensusSignal 계산  
**상태**: ✅ **완료** (2025-12-24)

---

## ✅ 완료된 작업

### 1. DB 설정 (이미 완료됨)

#### 📊 config_lv2_metric 테이블

**consensusSignal 메트릭 설정**:
```sql
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
  }'::jsonb
WHERE id = 'consensusSignal';
```

**확인 결과**: ✅ DB에 이미 반영되어 있음

---

### 2. Python 코드 구현 (신규 완료)

#### 📁 `backend/src/services/metric_engine.py`

**1) Aggregation 라우팅 추가** (라인 520-521):
```python
elif aggregation_kind == 'leadPairFromList':
    return self._lead_pair_from_list(base_values, aggregation_params)
```

**2) `_lead_pair_from_list()` 메서드 구현** (라인 893-1023):
```python
def _lead_pair_from_list(
    self,
    base_values: List[Dict[str, Any]],
    params: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """
    Find previous record for the same partition and attach lead (previous) values.

    This aggregation is used for consensusSignal to track analyst's previous predictions.

    Workflow:
    1. Partition records by (ticker, analyst_name, analyst_company)
    2. Sort each partition by event_date (desc)
    3. For the most recent record, find the previous record
    4. Attach prev values from previous record

    Args:
        base_values: List of consensus records from evt_consensus
        params: {
            "partitionBy": ["ticker", "analyst_name", "analyst_company"],
            "orderBy": [{"event_date": "desc"}],
            "leadFields": [
                {"field": "price_target", "as": "price_target_prev"},
                {"field": "price_when_posted", "as": "price_when_posted_prev"}
            ],
            "emitPrevRow": true
        }

    Returns:
        Dict with current record + prev field values, or None if no records
    """
```

**기능**:
- 파티션 키로 레코드 그룹화 (ticker, analyst_name, analyst_company)
- 각 파티션을 event_date 기준 내림차순 정렬
- 가장 최근 레코드에 이전 레코드의 값 첨부
- price_target_prev, price_when_posted_prev 필드 생성

---

### 3. 테스트 및 검증 (완료)

#### 📁 `backend/scripts/test_lead_pair_from_list.py`

**테스트 케이스**:
1. **정상 케이스**: 3개의 레코드에서 가장 최근 레코드 + 이전 값 추출
2. **단일 레코드**: 이전 레코드 없을 때 prev 필드 = None
3. **빈 리스트**: None 반환

**실행 결과**:
```
================================================================================
🧪 Testing leadPairFromList Aggregation
================================================================================

📊 Input Data:
  1. 2024-03-15: price_target=180.0, price_when_posted=170.0
  2. 2024-02-10: price_target=175.0, price_when_posted=165.0
  3. 2024-01-05: price_target=170.0, price_when_posted=160.0

✅ Result:
  Current Record:
    - event_date: 2024-03-15
    - price_target: 180.0
    - price_when_posted: 170.0

  Previous Values (Lead Fields):
    - price_target_prev: 175.0
    - price_when_posted_prev: 165.0

  Previous Record (_prev):
    - event_date: 2024-02-10
    - price_target: 175.0
    - price_when_posted: 165.0

✅ All assertions passed!

📈 Direction: up
   (price_target 180.0 vs prev 175.0)

🎉 All tests passed successfully!
```

---

## 🔍 구현 세부사항

### Partition & Sort 로직

```python
# 1. Group records by partition key
from collections import defaultdict
partitions = defaultdict(list)

for record in base_values:
    partition_key = tuple(record.get(field) for field in partition_by)
    partitions[partition_key].append(record)

# 2. Sort each partition
for partition_key, records in partitions.items():
    sort_config = order_by[0]
    sort_field = list(sort_config.keys())[0]
    sort_direction = sort_config[sort_field]  # 'asc' or 'desc'

    records.sort(
        key=lambda r: r.get(sort_field, ''),
        reverse=(sort_direction == 'desc')
    )
```

### Lead Fields Attachment

```python
# 3. Get most recent record
current_record = sorted_records[0].copy()

# 4. Attach prev values
if len(sorted_records) > 1:
    prev_record = sorted_records[1]

    for lead_config in lead_fields:
        source_field = lead_config.get('field')
        target_field = lead_config.get('as', f"{source_field}_prev")
        current_record[target_field] = prev_record.get(source_field)
```

---

## 📊 사용 예시

### consensusSignal 계산 흐름

```
1. evt_consensus 테이블에서 consensus 이벤트 조회
   → ticker, analyst_name, analyst_company, event_date, price_target, price_when_posted

2. MetricCalculationEngine.calculate_all() 호출
   → consensusSignal 메트릭 정의 로드

3. _lead_pair_from_list() 실행
   → partitionBy: [ticker, analyst_name, analyst_company]
   → orderBy: [{event_date: desc}]
   → 가장 최근 레코드 + price_target_prev, price_when_posted_prev 첨부

4. consensusSignal 구성
   {
     "direction": "up",  // price_target > price_target_prev
     "last": {
       "price_target": 180.0,
       "price_when_posted": 170.0
     },
     "prev": {
       "price_target": 175.0,
       "price_when_posted": 165.0
     },
     "delta": 5.0,
     "deltaPct": 2.86
   }
```

---

## ✅ 완료 확인 항목

- [x] DB: consensusSignal 메트릭 aggregation 타입으로 변경
- [x] DB: aggregation_kind = 'leadPairFromList' 설정
- [x] Python: _lead_pair_from_list() 메서드 구현
- [x] Python: aggregation 라우팅에 leadPairFromList 추가
- [x] 테스트: test_lead_pair_from_list.py 작성 및 통과
- [x] 테스트: 정상 케이스, 단일 레코드, 빈 리스트 검증
- [x] 문서: 1_CHECKLIST.md, 2_FLOW.md 업데이트

---

## 🎯 결론

**I-01: consensusSignal leadPairFromList Aggregation**은 **✅ 완료**되었습니다!

- DB 설정: 이미 완료되어 있었음 ✅
- Python 코드: _lead_pair_from_list() 메서드 구현 완료 ✅
- 테스트: 모든 테스트 케이스 통과 ✅
- 문서: 업데이트 완료 ✅

이제 consensusSignal이 **동적으로 계산**됩니다:
- evt_consensus 테이블에서 데이터 조회
- 파티션별로 정렬하여 가장 최근 레코드 선택
- 이전 레코드의 값을 prev 필드로 첨부
- direction, delta, deltaPct 자동 계산

---

## 🚀 다음 단계 (선택사항)

현재 모든 **권장 작업이 완료**되었습니다:
- ✅ I-01: leadPairFromList aggregation 구현
- ✅ I-10: priceEodOHLC_dateRange 정책 분리
- ✅ I-11: internal(qual) 메트릭 동적 처리

**선택 사항 (현재 불필요)**:
- ⚪ db_field source 타입 구현 (현재 aggregation으로 충분)
- ⚪ consensusRaw 메트릭 추가 (현재 evt_consensus로 충분)

---

*작성일: 2025-12-24*  
*작성자: AI Assistant*  
*검증 완료: ✅*

