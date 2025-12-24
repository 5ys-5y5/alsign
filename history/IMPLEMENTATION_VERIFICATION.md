# 가이드라인 vs 구현 상태 점검 보고서

> 작성일: 2025-12-24  
> 목적: `/prompt` 폴더의 가이드라인과 현재 구현 상태 비교

---

## 🔍 점검 방법

1. `/prompt/1_guideline(function).ini` - 기능 요구사항
2. `/prompt/1_guideline(tableSetting).ini` - DB 스키마 요구사항  
3. `/history` 폴더의 수정 방안 고려
4. 실제 구현 코드 검증

---

## ✅ 구현 완료 항목

### 1. 엔드포인트 구현 상태

| 엔드포인트 | 가이드라인 요구 | 구현 상태 | 파일 |
|-----------|--------------|---------|------|
| GET /sourceData | getHolidays, getTargets, getConsensus, getEarning | ✅ 구현됨 | source_data_service.py |
| POST /backfillEventsTable | valuation 메트릭 계산 및 저장 | ✅ 구현됨 | valuation_service.py |
| POST /setEventsTable | price_trend 채우기 | ✅ 구현됨 | events_service.py |
| POST /fillAnalyst | analyst 성과 분석 | ✅ 구현됨 | analyst_service.py |

### 2. evt_consensus 2단계 처리

**가이드라인 요구사항**:
- Phase 1: Raw Upsert (원천 데이터 보존)
- Phase 2: prev/direction 계산

**구현 상태**: ✅ 완료
- `source_data_service.py` 라인 183-349
- `process_get_consensus()` 함수에서 Phase 1, Phase 2 명확히 분리
- `determine_phase2_partitions()`, `calculate_partition_changes()` 구현

### 3. MetricCalculationEngine 동적 메트릭 계산

**가이드라인 요구사항**:
- config_lv2_metric 테이블 기반 동적 계산
- api_field, aggregation, expression 세 가지 source 타입 지원
- Topological Sort로 의존성 해결

**구현 상태**: ✅ 완료
- `metric_engine.py` - MetricCalculationEngine 클래스
- `build_dependency_graph()`, `topological_sort()` 구현
- `calculate_all()` - 동적 메트릭 계산

### 4. internal(qual) 메트릭 동적 처리 (I-11)

**가이드라인 요구사항** (라인 1161-1185):
```
5) internal(qual) 메트릭 규칙에 따라 통계 계산 및 performance 채움 (DB 정의 권위; 강제)
    - 계산 로직 하드코딩 금지
    - 반드시 public.[table.metric] 정의를 해석하여 산출
    - domain = 'internal(qual)'
    - base_metric_id = 'priceTrendReturnSeries'
```

**구현 상태**: ✅ 완료
- `select_internal_qual_metrics()` 함수 (metrics.py:334-378)
- `calculate_statistics_from_db_metrics()` 함수 (analyst_service.py:15-114)
- DB에 7개 internal(qual) 메트릭 존재
- 하드코딩 없이 DB 정의 기반 계산

### 5. leadPairFromList aggregation (I-01)

**가이드라인 요구사항**:
- consensusSignal은 aggregation 타입
- aggregation_kind = 'leadPairFromList'
- 파티션별로 정렬하여 이전 레코드 값 첨부

**구현 상태**: ✅ 완료
- DB: consensusSignal 메트릭 aggregation 설정 완료
- Python: `_lead_pair_from_list()` 메서드 구현 (metric_engine.py:893-1023)
- 테스트 통과 확인

### 6. priceEodOHLC_dateRange 정책 (I-10)

**가이드라인 요구사항** (라인 984-990):
```
조회 기간 산출 (policy 기반; 강제)
- config_lv0_policy.function 값이 priceEodOHLC_dateRange
- countStart, countEnd는 달력일(day) 기준 오프셋
```

**구현 상태**: ✅ 완료
- DB: `priceEodOHLC_dateRange` 정책 존재
- Python: `get_ohlc_date_range_policy()` 함수 구현
- `valuation_service.py`에서 정책 사용

### 7. 시간/날짜 처리 및 정규화

**가이드라인 요구사항** (라인 22-37):
- 입력 정규화: datetime 객체(UTC) 변환
- 저장 포맷: timestamptz (UTC)
- jsonb 내부 날짜: UTC ISO8601 (+00:00)

**구현 상태**: ✅ 구현됨
- `datetime_utils.py`: `parse_to_utc()`, `parse_date_only_to_utc()` 함수

### 8. price_trend 생성 로직

**가이드라인 요구사항** (라인 908-1003):
- fillPriceTrend_dateRange 정책 기반
- dayOffset 기준 거래일 OHLC 수집
- Progressive Null-Filling (미래는 null)
- 주말 및 NASDAQ 휴장일 자동 스킵

**구현 상태**: ✅ 구현됨
- `events_service.py`: `fill_price_trend()` 함수
- 거래일 계산 로직 포함
- holiday 테이블 참조

---

## ⚠️ 발견된 이슈 (검토 필요)

### I-NEW-01: consensusSignal 하드코딩 문제

**위치**: `valuation_service.py` 라인 638-667

**문제**:
```python
# 현재 코드 (라인 638-667)
consensus_signal = {
    'direction': direction,
    'last': {
        'price_target': float(price_target) if price_target else None,
        'price_when_posted': float(price_when_posted) if price_when_posted else None
    }
}
# ... 하드코딩된 로직으로 consensusSignal 생성
```

**가이드라인 요구사항** (라인 800-891):
- consensusSignal은 DB 메트릭 정의(leadPairFromList aggregation)를 사용해야 함
- MetricCalculationEngine으로 동적 계산해야 함

**상태**: ❌ 가이드라인 불일치
- DB 설정: consensusSignal 메트릭이 aggregation 타입으로 설정됨
- Python 코드: 여전히 하드코딩된 로직 사용 중
- leadPairFromList 구현은 완료되었으나 실제로 사용되지 않음

**해결 방안**:
1. `calculate_qualitative_metrics()` 함수에서 MetricCalculationEngine 사용
2. consensusSignal 메트릭 정의 로드
3. `_lead_pair_from_list()` aggregation으로 동적 계산
4. 하드코딩된 로직 제거

---

### I-NEW-02: consensusSignal 출력 스키마 불일치

**가이드라인 요구사항** (라인 851-891):
```json
{
  "targetMedian": 0,
  "consensusSummary": { ... },
  "consensusSignal": {
    "source": "evt_consensus",
    "source_id": "7f5b7a2a-...",
    "event_date": "2025-12-08T00:00:00Z",
    "direction": "up",
    "last": { ... },
    "prev": { ... },
    "delta": { ... },
    "deltaPct": { ... },
    "meta": {
      "analyst_name": "John Doe",
      "analyst_company": "ABC Securities",
      "news_url": "https://...",
      "news_title": "....",
      "news_publisher": "....",
      "source_api": "fmp-price-target"
    }
  }
}
```

**현재 출력** (`valuation_service.py` 라인 724-727):
```python
value_qualitative = {
    'targetMedian': target_median,
    'consensusSummary': consensus_summary,
    'consensusSignal': consensus_signal  # source, source_id, event_date, meta 누락
}
```

**누락된 필드**:
- `source`: "evt_consensus"
- `source_id`: UUID
- `event_date`: ISO 8601 timestamp
- `meta.news_url`, `meta.news_title`, `meta.news_publisher`, `meta.source_api`

**상태**: ⚠️ 부분 불일치
- 핵심 필드는 존재 (direction, last, prev, delta, deltaPct)
- 메타 정보 일부 누락

---

### I-NEW-03: Upsert 전략 명시 누락

**가이드라인 요구사항** (라인 37-39):
```
적재 전략 명시(Upsert vs Insert-only)
- Insert-only(기존 레코드 변경 금지): evt_earning (중복 시 DO NOTHING)
- Upsert(갱신 허용): config_lv3_market_holidays, config_lv3_targets, evt_consensus, config_lv3_analyst, [table.events]
```

**점검 필요**:
1. `evt_earning`: DO NOTHING 전략 확인
2. 각 테이블의 upsert 로직이 가이드라인과 일치하는지 검증

---

### I-NEW-04: dayOffset 기준 명확화

**가이드라인** (라인 947-949):
```
dayOffset 정의
- dayOffset는 countStart부터 countEnd까지 0 포함하여 생성한다.
- event_date가 비거래일인 경우 dayOffset=0의 targetDate는 직후 첫 거래일로 매핑한다.
```

**점검 필요**:
- `events_service.py`의 `fill_price_trend()` 함수에서 이 규칙이 정확히 구현되었는지 확인
- 비거래일 처리 로직 검증

---

## 📊 요약

| 항목 | 상태 | 비고 |
|------|------|------|
| 엔드포인트 구현 | ✅ | 모든 주요 엔드포인트 구현 완료 |
| evt_consensus 2단계 | ✅ | Phase 1, Phase 2 분리 구현 |
| MetricCalculationEngine | ✅ | 동적 메트릭 계산 완료 |
| internal(qual) 메트릭 | ✅ | DB 기반 동적 계산 완료 (I-11) |
| leadPairFromList aggregation | ✅ | 구현 완료 (I-01) |
| priceEodOHLC_dateRange | ✅ | 정책 및 함수 구현 완료 (I-10) |
| **consensusSignal 하드코딩** | ❌ | **I-NEW-01: 수정 필요** |
| consensusSignal 스키마 | ⚠️ | I-NEW-02: 메타 정보 보완 권장 |
| Upsert 전략 | ⚠️ | I-NEW-03: 검증 필요 |
| dayOffset 처리 | ⚠️ | I-NEW-04: 검증 필요 |

---

## 🎯 다음 조치

### 🔴 필수 (즉시)
1. **I-NEW-01**: consensusSignal 하드코딩 제거
   - MetricCalculationEngine으로 동적 계산 전환
   - leadPairFromList aggregation 실제 사용

### 🟡 권장 (단기)
2. **I-NEW-02**: consensusSignal 출력 스키마 보완
   - source, source_id, event_date, meta 필드 추가

### ⚪ 검증 (선택)
3. **I-NEW-03**: Upsert 전략 검증
4. **I-NEW-04**: dayOffset 처리 로직 검증

---

*작성일: 2025-12-24*  
*작성자: AI Assistant*

