# 📋 가이드라인 검증 후 발견된 이슈 체크리스트

> 작성일: 2025-12-24  
> 목적: `/prompt` 가이드라인과 현재 구현 비교 후 발견된 불일치 항목

---

## 📊 이슈 요약

| ID | 이슈 | 상태 | 우선순위 | 흐름도 | 상세도 |
|----|------|------|---------|--------|--------|
| I-NEW-01 | consensusSignal 하드코딩 문제 | ❌ 미반영 | 🔴 필수 | NEW_FLOW.md#I-NEW-01 | NEW_DETAIL.md#I-NEW-01 |
| I-NEW-02 | consensusSignal 스키마 불일치 | ⚠️ 부분반영 | 🟡 권장 | NEW_FLOW.md#I-NEW-02 | NEW_DETAIL.md#I-NEW-02 |
| I-NEW-03 | Upsert 전략 검증 필요 | ⚪ 미확인 | ⚪ 검증 | NEW_FLOW.md#I-NEW-03 | - |
| I-NEW-04 | dayOffset 처리 검증 필요 | ⚪ 미확인 | ⚪ 검증 | NEW_FLOW.md#I-NEW-04 | - |

---

## 🔴 필수 (즉시)

### I-NEW-01: consensusSignal 하드코딩 문제
	- ❌ MetricCalculationEngine 미사용 (현재 하드코딩)
	- ❌ leadPairFromList aggregation 실제 사용 안됨
	- ✅ leadPairFromList 구현은 완료됨 (I-01)
	- ❌ calculate_qualitative_metrics()에서 동적 계산 미적용

**문제의 심각성**:
- DB 설정과 Python 코드 불일치
- 가이드라인 (라인 800-891) 직접 위반
- leadPairFromList 구현했지만 사용하지 않음

---

## 🟡 권장 (단기)

### I-NEW-02: consensusSignal 출력 스키마 불일치
	- ✅ 핵심 필드 존재 (direction, last, prev, delta, deltaPct)
	- ❌ source 필드 누락
	- ❌ source_id 필드 누락
	- ❌ event_date 필드 누락
	- ⚠️ meta.news_url, meta.news_title 등 부분 누락

**가이드라인 요구** (라인 851-891):
```json
{
  "consensusSignal": {
    "source": "evt_consensus",
    "source_id": "UUID",
    "event_date": "ISO 8601",
    "direction": "up",
    "last": { ... },
    "prev": { ... },
    "delta": { ... },
    "deltaPct": { ... },
    "meta": {
      "analyst_name": "...",
      "analyst_company": "...",
      "news_url": "...",
      "news_title": "...",
      "news_publisher": "...",
      "source_api": "fmp-price-target"
    }
  }
}
```

---

## ⚪ 검증 필요

### I-NEW-03: Upsert 전략 검증 필요
	- ⚪ evt_earning: DO NOTHING 전략 확인 필요
	- ⚪ evt_consensus: Upsert 전략 확인 완료
	- ⚪ config_lv3_* 테이블: Upsert 전략 확인 필요

### I-NEW-04: dayOffset 처리 검증 필요
	- ⚪ event_date가 비거래일일 때 dayOffset=0 처리 확인 필요
	- ⚪ 직후 첫 거래일 매핑 로직 확인 필요

---

## ✅ 확인된 정상 항목

1. ✅ evt_consensus 2단계 처리 (Phase 1 + Phase 2)
2. ✅ MetricCalculationEngine 동적 메트릭 계산
3. ✅ internal(qual) 메트릭 DB 기반 계산 (I-11)
4. ✅ leadPairFromList aggregation 구현 (I-01)
5. ✅ priceEodOHLC_dateRange 정책 (I-10)
6. ✅ 시간/날짜 UTC 정규화
7. ✅ price_trend 거래일 기반 생성

---

## 📝 조치 필요 항목

### 우선순위 1 (필수)
1. **I-NEW-01 수정**: consensusSignal 동적 계산 전환
   - `valuation_service.py` 수정
   - MetricCalculationEngine 사용
   - 하드코딩 로직 제거

### 우선순위 2 (권장)
2. **I-NEW-02 보완**: consensusSignal 스키마 완성
   - source, source_id, event_date 추가
   - meta 정보 보완

### 우선순위 3 (검증)
3. **I-NEW-03, I-NEW-04 검증**: 코드 리뷰 및 테스트

---

*작성일: 2025-12-24*  
*마지막 업데이트: 2025-12-24*

