# 📋 AlSign 이슈 체크리스트

> 이 문서는 서비스의 모든 이슈들의 반영 상태를 한눈에 파악할 수 있도록 정리한 체크리스트입니다.
> 
> **범례**: ✅ 반영완료 | 🔄 부분반영 | ❌ 미반영 | ⏸️ 보류
> 
> **문서 연결**: 체크리스트 항목 → `2_FLOW.md` (흐름도) → `3_DETAIL.md` (상세도)
> 
> **최종 DB 검증**: 2025-12-24 - `backend/scripts/verify_checklist_items.py` 실행 완료

---

## 1. Config & 메트릭 설정 이슈

### I-01: consensusSignal 설정 불일치
	- ✅ expression을 NULL로 변경 (DB 반영완료)
	- ✅ aggregation 방식으로 변경 (DB 반영완료)
	- ✅ aggregation_kind = 'leadPairFromList' (DB 반영완료)
	- ✅ leadPairFromList aggregation 구현 (MetricCalculationEngine 코드 완료)
	- ✅ _lead_pair_from_list() 메서드 추가 (metric_engine.py)
	- ✅ 테스트 완료 (test_lead_pair_from_list.py 통과)
	- ⏸️ db_field source 타입 구현 (선택사항, 현재 불필요)
	- ⏸️ consensusRaw 메트릭 추가 (선택사항, 현재 불필요)

### I-02: priceEodOHLC dict response_key
	- ✅ dict response_key 지원 확인 (이미 구현됨)
	- ✅ 조치 불필요 확인 (정상 작동)

### I-03: targetMedian & consensusSummary 구현
	- ✅ Python 코드 수정 완료 (calculate_qualitative_metrics)
	- ✅ MetricCalculationEngine 사용하여 fmp-price-target-consensus API 호출
	- ✅ value_qualitative에 targetMedian, consensusSummary, consensusSignal 포함

### I-04: 짧은 이름 메트릭 (rnd, totalEquity, otherNCL)
	- ⏸️ 조치 보류 (현재 긴 이름으로 정상 작동)

### I-05: consensus 메트릭 추가
	- ✅ SQL 스크립트 작성 및 실행완료 (DB 반영완료)
	- ✅ fmp-price-target API 설정 (DB 반영완료)
	- ✅ response_key 12개 필드 매핑 (DB 반영완료)

### I-06: consensusWithPrev
	- ✅ 조치 불필요 (I-01의 개선안으로 해결)

---

## 2. 코드 품질 이슈

### I-07: source_id 파라미터 누락
	- ✅ calculate_qualitative_metrics()에 source_id 파라미터 추가
	- ✅ select_consensus_data()에 source_id 파라미터 추가
	- ✅ 정확한 evt_consensus 행 조회 가능

### I-08: 시간적 유효성 (Temporal Validity)
	- ✅ limit=100으로 충분한 과거 데이터 조회
	- ✅ event_date 기준 필터링 구현
	- ✅ _meta.date_range, calcType, count 기록
	- ✅ no_valid_data 에러 처리

### I-09: Topological Sort 순서 오류
	- ✅ in-degree 계산 로직 수정
	- ✅ 역방향 그래프 구축 로직 추가
	- ✅ api_field 메트릭 먼저 계산되도록 수정

---

## 3. 동적 설정 항목

### (동적 설정 - 반영완료)
	- ✅ GET /sourceData - config_lv1_api_list, config_lv1_api_service 동적 사용
	- ✅ POST /backfillEventsTable - quantitative/qualitative 메트릭 동적 처리
	- ✅ POST /backfillEventsTable - fillPriceTrend_dateRange 정책 동적 로드

### I-10: priceEodOHLC_dateRange 정책 미사용
	- ✅ 별도 정책 추가 완료 (DB 반영완료)
	- ✅ get_ohlc_date_range_policy() 함수 구현 완료
	- ✅ valuation_service.py에서 정책 호출 완료

### I-11: internal(qual) 메트릭 동적 사용 미구현
	- ✅ select_internal_qual_metrics() 함수 구현 완료
	- ✅ calculate_statistics_from_db_metrics() 함수 구현 완료
	- ✅ DB 메트릭 로드 및 동적 통계 계산 구현 완료
	- ✅ DB에 7개 internal(qual) 메트릭 존재 (returnIQRByDayOffset 포함)

---

## 4. 데이터베이스 설정

### (DB 설정 - 반영완료)
	- ✅ Supabase 연결: DATABASE_URL, SSL, Connection Pool 설정
	- ✅ 스키마 설정: setup_supabase.sql 실행완료 (11개 테이블)
	- ✅ config_lv2_metric: 81개 메트릭 정의됨
	- ✅ config_lv0_policy: 2개 정책 존재 (fillPriceTrend_dateRange, sourceData_dateRange)
	- ✅ qualatative 도메인: 4개 메트릭 (consensus, consensusSignal, consensusSummary, priceQualitative)

---

## 요약 테이블

| ID | 이슈 | 상태 | DB 반영 | 흐름도 | 상세도 |
|----|------|------|---------|--------|--------|
| I-01 | consensusSignal 설정 불일치 | ✅ | ✅ 완료 | 2_FLOW.md#I-01 | 3_DETAIL.md#I-01 |
| I-02 | priceEodOHLC dict response_key | ✅ | N/A | 2_FLOW.md#I-02 | 3_DETAIL.md#I-02 |
| I-03 | targetMedian & consensusSummary | ✅ | N/A | 2_FLOW.md#I-03 | 3_DETAIL.md#I-03 |
| I-04 | 짧은 이름 메트릭 | ⏸️ | N/A | 2_FLOW.md#I-04 | - |
| I-05 | consensus 메트릭 추가 | ✅ | ✅ 완료 | 2_FLOW.md#I-05 | 3_DETAIL.md#I-05 |
| I-06 | consensusWithPrev | ✅ | N/A | 2_FLOW.md#I-06 | - |
| I-07 | source_id 파라미터 | ✅ | N/A | 2_FLOW.md#I-07 | 3_DETAIL.md#I-07 |
| I-08 | 시간적 유효성 | ✅ | N/A | 2_FLOW.md#I-08 | 3_DETAIL.md#I-08 |
| I-09 | Topological Sort | ✅ | N/A | 2_FLOW.md#I-09 | 3_DETAIL.md#I-09 |
| I-10 | priceEodOHLC_dateRange 정책 | ✅ | ✅ 완료 | 2_FLOW.md#I-10 | 3_DETAIL.md#I-10 |
| I-11 | internal(qual) 메트릭 | ✅ | ✅ 완료 | 2_FLOW.md#I-11 | 3_DETAIL.md#I-11 |

---

## DB 검증 결과 (2025-12-24)

### ✅ 성공적으로 반영됨
- **I-01**: consensusSignal 설정
  - source = 'aggregation' ✅
  - expression = NULL ✅
  - aggregation_kind = 'leadPairFromList' ✅

- **I-05**: consensus 메트릭
  - source = 'api_field' ✅
  - api_list_id = 'fmp-price-target' ✅
  - response_key: 12개 필드 매핑 ✅

### ✅ 완료된 항목
- **I-10**: priceEodOHLC_dateRange 정책 추가 (DB + Python) ✅
- **I-11**: internal(qual) 메트릭 동적 처리 (Python 코드) ✅

### ✅ 모든 권장 작업 완료!
- **I-01**: leadPairFromList aggregation 로직 ✅
- **I-10**: priceEodOHLC_dateRange 정책 추가 ✅
- **I-11**: internal(qual) 메트릭 동적 처리 ✅

---

## 다음 조치 필요 항목

### 🟢 완료됨
	1. ✅ I-10: priceEodOHLC_dateRange 정책 분리 구현
		- ✅ DB: config_lv0_policy에 정책 추가
		- ✅ Python: get_ohlc_date_range_policy() 함수 구현
	2. ✅ I-11: internal(qual) 메트릭 동적 처리 구현
		- ✅ Python: select_internal_qual_metrics() 함수 구현
		- ✅ Python: calculate_statistics_from_db_metrics() 함수 구현
		- ✅ DB: 7개 internal(qual) 메트릭 존재

### ⚪ 선택 (장기 - 현재 불필요)
	1. I-01: db_field source 타입 구현
		- Python: MetricCalculationEngine 확장
		- 현재 aggregation 방식으로 충분히 동작
	2. I-01: consensusRaw 메트릭 추가
		- DB: consensusRaw 메트릭 정의
		- 현재 evt_consensus 테이블로 충분히 동작

---

## 5. 런타임 이슈 (2025-12-24 발견)

### I-12: 동적 계산 코드 실행 실패
	- ✅ calculation 코드를 single expression으로 재작성 완료
	- ✅ avgFromQuarter, ttmFromQuarterSumOrScaled, lastFromQuarter 수정
	- ✅ qoqFromQuarter, yoyFromQuarter 수정
	- ✅ SQL 스크립트: `backend/scripts/fix_calculation_single_expression.sql`

### I-13: priceEodOHLC 데이터 추출 실패 ⚠️
	- ✅ 원인 규명: API 호출 시 `fromDate`, `toDate` 파라미터 누락
	- ✅ valuation_service.py 수정 완료 (파라미터 추가)
	- ✅ FMP API 실제 응답 검증: 필드명 `low`, `high`, `open`, `close` 정확함
	- ✅ 전체 서비스 API 호출 방식 점검 완료 (11개 위치)
	- ✅ config_lv1_api_list 사용 원칙 준수 확인

### I-14: fmp-aftermarket-trade API 401 오류
	- ⏸️ FMP 서비스의 일시적 문제로 판단
	- ⏸️ 조치 불필요 (priceAfter 메트릭만 영향)
	- ⏸️ 다른 메트릭들은 정상 작동

### I-15: event_date_obj 변수 순서 오류 ⚠️
	- ❌ API 호출 시 event_date_obj 사용 (444라인)
	- ❌ 실제 정의는 471라인 (순서 오류)
	- ❌ 에러: `local variable 'event_date_obj' referenced before assignment`
	- ✅ event_date_obj 변환 로직을 API 호출 전으로 이동
	- ✅ valuation_service.py:425-438 수정 완료

### I-16: 메트릭 실패 디버깅 로그 부재
	- ❌ ✗ 표시만 있고 실패 이유 알 수 없음
	- ✅ _calculate_metric_with_reason() 메서드 추가
	- ✅ 실패 이유 분류 (api_field, aggregation, expression)
	- ✅ 로그 출력 형식: `✗ metricName = None | reason: ...`
	- ✅ metric_engine.py:241-326 수정 완료

### I-17: 로그 형식 N/A 과다 출력
	- ❌ 세부 로그에 불필요한 `[N/A | N/A] | ... | counters=N/A` 출력
	- ✅ logging_utils.py: 구조화된 데이터 없으면 단순 포맷 사용
	- ✅ API 호출/메트릭 계산 등 세부 로그는 단순 포맷
	- ✅ 엔드포인트 주요 단계만 구조화된 로그
	- ✅ LOGGING_GUIDE.md 문서 작성

### I-18: priceEodOHLC Schema Array Type 문제 ⚠️
	- ❌ 에러: `unhashable type: 'list'` 발생
	- ❌ 원인: `config_lv1_api_list.schema`가 `[{}]` (array)로 저장됨
	- ✅ SQL 스크립트: `backend/scripts/diagnose_priceEodOHLC_issue.sql` (진단)
	- ✅ SQL 스크립트: `backend/scripts/fix_priceEodOHLC_array_types.sql` (수정)
	- ✅ schema를 `{}` (object) 타입으로 변경
	- ✅ verify_all_api_schemas.sql로 전체 API 검증

### I-19: 메트릭 로그 Truncation 문제
	- ❌ priceEodOHLC 값이 50자로 잘림 (close 필드 미출력)
	- ❌ 원인: `str(value)[:50]` 하드코딩
	- ✅ 스마트 포맷팅 구현: 리스트는 첫 항목 + 개수 표시
	- ✅ 안전장치: 150자 제한 (이전 50자 → 150자)
	- ✅ 불필요한 디버그 로그 제거 (priceEodOHLC 전용 로그들)
	- ✅ metric_engine.py:258-271 수정 완료

---

## 요약 테이블 (업데이트)

| ID | 이슈 | 상태 | DB 반영 | 흐름도 | 상세도 |
|----|------|------|---------|--------|--------|
| I-01 | consensusSignal 설정 불일치 | ✅ | ✅ 완료 | 2_FLOW.md#I-01 | 3_DETAIL.md#I-01 |
| I-02 | priceEodOHLC dict response_key | ✅ | N/A | 2_FLOW.md#I-02 | 3_DETAIL.md#I-02 |
| I-03 | targetMedian & consensusSummary | ✅ | N/A | 2_FLOW.md#I-03 | 3_DETAIL.md#I-03 |
| I-04 | 짧은 이름 메트릭 | ⏸️ | N/A | 2_FLOW.md#I-04 | - |
| I-05 | consensus 메트릭 추가 | ✅ | ✅ 완료 | 2_FLOW.md#I-05 | 3_DETAIL.md#I-05 |
| I-06 | consensusWithPrev | ✅ | N/A | 2_FLOW.md#I-06 | - |
| I-07 | source_id 파라미터 | ✅ | N/A | 2_FLOW.md#I-07 | 3_DETAIL.md#I-07 |
| I-08 | 시간적 유효성 | ✅ | N/A | 2_FLOW.md#I-08 | 3_DETAIL.md#I-08 |
| I-09 | Topological Sort | ✅ | N/A | 2_FLOW.md#I-09 | 3_DETAIL.md#I-09 |
| I-10 | priceEodOHLC_dateRange 정책 | ✅ | ✅ 완료 | 2_FLOW.md#I-10 | 3_DETAIL.md#I-10 |
| I-11 | internal(qual) 메트릭 | ✅ | ✅ 완료 | 2_FLOW.md#I-11 | 3_DETAIL.md#I-11 |
| **I-12** | **동적 계산 코드 실행 실패** | **✅** | **✅ 완료** | **2_FLOW.md#I-12** | **3_DETAIL.md#I-12** |
| **I-13** | **priceEodOHLC 데이터 추출 실패** | **✅** | **✅ 완료** | **2_FLOW.md#I-13** | **3_DETAIL.md#I-13** |
| **I-14** | **aftermarket API 401 오류** | **⏸️** | **N/A** | **2_FLOW.md#I-14** | **3_DETAIL.md#I-14** |
| **I-15** | **event_date_obj 변수 순서 오류** | **✅** | **✅ 완료** | **2_FLOW.md#I-15** | **3_DETAIL.md#I-15** |
| **I-16** | **메트릭 실패 디버깅 로그 부재** | **✅** | **✅ 완료** | **2_FLOW.md#I-16** | **3_DETAIL.md#I-16** |
| **I-17** | **로그 형식 N/A 과다 출력** | **✅** | **✅ 완료** | **2_FLOW.md#I-17** | **3_DETAIL.md#I-17** |

---

*최종 업데이트: 2025-12-24 (런타임 이슈 추가)*
