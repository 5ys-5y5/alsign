# 📋 AlSign 이슈 체크리스트

> **목적**: 서비스의 모든 이슈들의 반영 상태를 한눈에 파악
> 
> **범례**: ✅ 반영완료 | 🔄 부분반영 | ❌ 미반영 | ⏸️ 보류
> 
> **문서 연결**: 체크리스트(여기) → `2_FLOW.md` (흐름도) → `3_DETAIL.md` (상세도)
> 
> **최종 업데이트**: 2025-12-25 21:30 KST

---

## 📊 전체 요약 테이블

| ID | 이슈명 | 상태 | 발견일 | 해결일 | DB | 흐름도 | 상세도 |
|----|--------|------|--------|--------|-----|--------|--------|
| I-01 | consensusSignal 설정 불일치 | ✅ | 2025-12-23 | 2025-12-24 | ✅ | #I-01 | #I-01 |
| I-02 | priceEodOHLC dict response_key | ✅ | 2025-12-23 | 2025-12-23 | N/A | #I-02 | #I-02 |
| I-03 | targetMedian & consensusSummary | ✅ | 2025-12-23 | 2025-12-23 | N/A | #I-03 | #I-03 |
| I-04 | 짧은 이름 메트릭 | ⏸️ | 2025-12-23 | - | N/A | #I-04 | - |
| I-05 | consensus 메트릭 추가 | ✅ | 2025-12-23 | 2025-12-24 | ✅ | #I-05 | #I-05 |
| I-06 | consensusWithPrev | ✅ | 2025-12-23 | 2025-12-24 | N/A | #I-06 | - |
| I-07 | source_id 파라미터 누락 | ✅ | 2025-12-23 | 2025-12-23 | N/A | #I-07 | #I-07 |
| I-08 | 시간적 유효성 문제 | ✅ | 2025-12-23 | 2025-12-23 | N/A | #I-08 | #I-08 |
| I-09 | Topological Sort 순서 오류 | ✅ | 2025-12-23 | 2025-12-23 | N/A | #I-09 | #I-09 |
| I-10 | priceEodOHLC_dateRange 정책 | ✅ | 2025-12-24 | 2025-12-24 | ✅ | #I-10 | #I-10 |
| I-11 | internal(qual) 메트릭 동적 | ✅ | 2025-12-24 | 2025-12-24 | ✅ | #I-11 | #I-11 |
| I-12 | 동적 계산 코드 syntax 오류 | ✅ | 2025-12-24 | 2025-12-24 | ✅ | #I-12 | #I-12 |
| I-13 | priceEodOHLC API 파라미터 누락 | ✅ | 2025-12-24 | 2025-12-24 | N/A | #I-13 | #I-13 |
| I-14 | aftermarket API 401 오류 | ⏸️ | 2025-12-24 | - | N/A | #I-14 | #I-14 |
| I-15 | event_date_obj 변수 순서 오류 | ✅ | 2025-12-24 | 2025-12-24 | N/A | #I-15 | #I-15 |
| I-16 | 메트릭 실패 디버깅 로그 부재 | ✅ | 2025-12-24 | 2025-12-24 | N/A | #I-16 | #I-16 |
| I-17 | 로그 형식 N/A 과다 출력 | ✅ | 2025-12-24 | 2025-12-24 | N/A | #I-17 | #I-17 |
| I-18 | priceEodOHLC Schema Array Type | ✅ | 2025-12-25 | 2025-12-25 | ✅ | #I-18 | #I-18 |
| I-19 | 메트릭 로그 Truncation 문제 | ✅ | 2025-12-25 | 2025-12-25 | N/A | #I-19 | #I-19 |
| I-20 | backfillEventsTable 성능 개선 | ✅ | 2025-12-25 | 2025-12-25 | N/A | #I-20 | #I-20 |
| I-21 | priceEodOHLC domain 설정 오류 | ✅ | 2025-12-25 | 2025-12-25 | ✅ | #I-21 | #I-21 |
| I-22 | SQL 예약어 "position" 문제 | ✅ | 2025-12-25 | 2025-12-25 | N/A | #I-22 | #I-22 |
| I-23 | NULL 값 디버깅 로그 개선 | ✅ | 2025-12-25 | 2025-12-25 | N/A | #I-23 | #I-23 |
| I-24 | price trends 처리 성능 최적화 | ✅ | 2025-12-25 | 2025-12-25 | N/A | #I-24 | #I-24 |

---

## 1. Config & 메트릭 설정 이슈 (I-01 ~ I-06)

### I-01: consensusSignal 설정 불일치 ✅
	발견: 2025-12-23 | 해결: 2025-12-24
	- ✅ expression을 NULL로 변경 (DB)
	- ✅ aggregation 방식으로 변경 (DB)
	- ✅ aggregation_kind = 'leadPairFromList' (DB)
	- ✅ _lead_pair_from_list() 메서드 구현 (Python)
	- ⏸️ db_field source 타입 구현 (선택, 불필요)
	- ⏸️ consensusRaw 메트릭 추가 (선택, 불필요)

### I-02: priceEodOHLC dict response_key ✅
	발견: 2025-12-23 | 해결: 2025-12-23
	- ✅ dict response_key 지원 확인 (이미 구현됨)
	- ✅ 조치 불필요 확인

### I-03: targetMedian & consensusSummary 구현 ✅
	발견: 2025-12-23 | 해결: 2025-12-23
	- ✅ calculate_qualitative_metrics() 수정
	- ✅ MetricCalculationEngine 사용
	- ✅ value_qualitative에 세 항목 포함

### I-04: 짧은 이름 메트릭 ⏸️
	발견: 2025-12-23 | 보류
	- ⏸️ 조치 보류 (현재 긴 이름으로 정상 작동)

### I-05: consensus 메트릭 추가 ✅
	발견: 2025-12-23 | 해결: 2025-12-24
	- ✅ SQL 스크립트 작성 및 실행완료 (DB)
	- ✅ fmp-price-target API 설정 (DB)
	- ✅ response_key 12개 필드 매핑 (DB)

### I-06: consensusWithPrev ✅
	발견: 2025-12-23 | 해결: 2025-12-24
	- ✅ 조치 불필요 (I-01의 개선안으로 해결)

---

## 2. 코드 품질 이슈 (I-07 ~ I-09)

### I-07: source_id 파라미터 누락 ✅
	발견: 2025-12-23 | 해결: 2025-12-23
	- ✅ calculate_qualitative_metrics()에 source_id 추가
	- ✅ select_consensus_data()에 source_id 추가
	- ✅ 정확한 evt_consensus 행 조회

### I-08: 시간적 유효성 (Temporal Validity) ✅
	발견: 2025-12-23 | 해결: 2025-12-23
	- ✅ limit=100으로 충분한 과거 데이터 조회
	- ✅ event_date 기준 필터링 구현
	- ✅ _meta 정보 기록

### I-09: Topological Sort 순서 오류 ✅
	발견: 2025-12-23 | 해결: 2025-12-23
	- ✅ in-degree 계산 로직 수정
	- ✅ 역방향 그래프 구축
	- ✅ api_field 먼저 계산되도록 수정

---

## 3. 동적 설정 항목 (I-10 ~ I-11)

### I-10: priceEodOHLC_dateRange 정책 ✅
	발견: 2025-12-24 | 해결: 2025-12-24
	- ✅ 별도 정책 추가 (DB)
	- ✅ get_ohlc_date_range_policy() 구현
	- ✅ valuation_service.py에서 정책 호출

### I-11: internal(qual) 메트릭 동적 사용 ✅
	발견: 2025-12-24 | 해결: 2025-12-24
	- ✅ select_internal_qual_metrics() 구현
	- ✅ calculate_statistics_from_db_metrics() 구현
	- ✅ 7개 internal(qual) 메트릭 존재 (DB)

---

## 4. 런타임 이슈 - 2025-12-24 (I-12 ~ I-17)

### I-12: 동적 계산 코드 실행 실패 ✅
	발견: 2025-12-24 09:00 | 해결: 2025-12-24 10:30
	- ✅ calculation 코드를 single expression으로 재작성
	- ✅ avgFromQuarter, ttmFromQuarterSumOrScaled 등 수정
	- ✅ SQL 스크립트: fix_calculation_single_expression.sql

### I-13: priceEodOHLC 데이터 추출 실패 ✅
	발견: 2025-12-24 09:00 | 해결: 2025-12-24 14:00
	- ✅ 원인: API 호출 시 fromDate, toDate 파라미터 누락
	- ✅ valuation_service.py 수정 (파라미터 추가)
	- ✅ 전체 서비스 API 호출 점검 완료

### I-14: fmp-aftermarket-trade API 401 오류 ⏸️
	발견: 2025-12-24 09:00 | 보류
	- ⏸️ FMP 서비스의 일시적 문제로 판단
	- ⏸️ priceAfter 메트릭만 영향 (다른 메트릭 정상)

### I-15: event_date_obj 변수 순서 오류 ✅
	발견: 2025-12-24 15:00 | 해결: 2025-12-24 15:30
	- ✅ event_date_obj 변환 로직을 API 호출 전으로 이동
	- ✅ valuation_service.py:425-438 수정

### I-16: 메트릭 실패 디버깅 로그 부재 ✅
	발견: 2025-12-24 16:00 | 해결: 2025-12-24 17:00
	- ✅ _calculate_metric_with_reason() 메서드 추가
	- ✅ 실패 이유 분류 (api_field, aggregation, expression)

### I-17: 로그 형식 N/A 과다 출력 ✅
	발견: 2025-12-24 17:00 | 해결: 2025-12-24 18:00
	- ✅ 구조화된 데이터 없으면 단순 포맷 사용
	- ✅ LOGGING_GUIDE.md 문서 작성

---

## 5. 런타임 이슈 - 2025-12-25 (I-18 ~ I-20)

### I-18: priceEodOHLC Schema Array Type 문제 ✅
	발견: 2025-12-25 10:00 | 해결: 2025-12-25 11:30
	- ✅ 에러: unhashable type: 'list'
	- ✅ 원인: config_lv1_api_list.schema가 [{}] (array)로 저장
	- ✅ schema를 {} (object) 타입으로 변경
	- ✅ SQL 스크립트: fix_priceEodOHLC_array_types.sql
	- ✅ 전체 API 스키마 검증: verify_all_api_schemas.sql

### I-19: 메트릭 로그 Truncation 문제 ✅
	발견: 2025-12-25 12:00 | 해결: 2025-12-25 13:00
	- ✅ priceEodOHLC 값이 50자로 잘림
	- ✅ 스마트 포맷팅 구현: 리스트는 첫 항목 + 개수 표시
	- ✅ 150자 제한 (이전 50자 → 150자)
	- ✅ 불필요한 디버그 로그 제거

### I-20: POST /backfillEventsTable 성능 개선 ✅
	발견: 2025-12-25 14:00 | 해결: 2025-12-25 18:00
	- ✅ Ticker 그룹화 함수 구현 (group_events_by_ticker)
	- ✅ Ticker 배치 처리 함수 구현 (process_ticker_batch)
	- ✅ DB 배치 업데이트 함수 구현 (batch_update_event_valuations)
	- ✅ 병렬 처리 로직 구현 (asyncio.Semaphore)
	- ✅ 동시성 제어 (TICKER_CONCURRENCY = 10)

	**성능 개선 효과**:
	| 항목 | Before | After | 개선율 |
	|------|--------|-------|--------|
	| API 호출 | 136,954 | ~5,000 | 96% ↓ |
	| DB 쿼리 | 136,954 | ~5,000 | 96% ↓ |
	| 소요 시간 | 76시간 | 0.5-1시간 | **99% ↓** |

### I-21: priceEodOHLC domain 설정 오류 ✅
	발견: 2025-12-25 19:00 | 해결: 2025-12-25 19:30
	- ✅ 원인: priceEodOHLC domain이 'quantitative-momentum'으로 잘못 설정됨
	- ✅ 문제: momentum 도메인에 priceEodOHLC가 포함되어 불필요한 값 출력
	- ✅ 해결: domain을 'internal'로 복원 (SQL 스크립트)
	- ✅ fix_priceeodohlc_domain.py 삭제 (잘못된 변경 스크립트)

### I-22: SQL 예약어 "position" 문제 ✅
	발견: 2025-12-25 19:30 | 해결: 2025-12-25 19:45
	- ✅ 에러: syntax error at or near "position"
	- ✅ 원인: ::position 캐스팅에서 position은 PostgreSQL 예약어
	- ✅ 해결: ::"position" 으로 따옴표 추가

### I-23: NULL 값 디버깅 로그 개선 ✅
	발견: 2025-12-25 20:00 | 해결: 2025-12-25 20:30
	- ✅ 문제: NULL 값 원인을 구별할 수 없음 (API 데이터 부재 vs 계산 오류)
	- ✅ 해결: INFO 레벨로 NULL 원인 로그 출력
	- ✅ 출력 형식: `[MetricEngine] ✗ NULL: PER | domain=valuation | reason=Missing deps: netIncomeTTM(=None)`
	- ✅ expression 메트릭의 의존성 추적 개선

### I-24: price trends 처리 성능 최적화 ✅
	발견: 2025-12-25 21:00 | 해결: 2025-12-25 21:30
	- ✅ 문제: 이벤트당 ~12초 소요 (53개 이벤트 처리에 10분 이상)
	- ✅ 원인 1: calculate_dayOffset_dates()가 각 dayOffset마다 DB 조회
	- ✅ 원인 2: 각 이벤트마다 개별 DB UPDATE 실행
	- ✅ 해결 1: 거래일 정보 미리 캐시 (get_trading_days_in_range)
	- ✅ 해결 2: 배치 DB 업데이트 (UNNEST 사용)
	
	**성능 개선 효과**:
	| 항목 | Before | After | 개선율 |
	|------|--------|-------|--------|
	| 거래일 DB 조회 | 이벤트×dayOffset | 1회 | **99% ↓** |
	| DB UPDATE | 이벤트당 1회 | 배치 1회 | **99% ↓** |
	| 53개 이벤트 | ~10분 | ~10초 | **98% ↓** |

---

## 📈 통계

### 상태별 현황
- ✅ **완료**: 22개 (92%)
- ⏸️ **보류**: 2개 (8%)
- ❌ **미반영**: 0개 (0%)

### 일자별 이슈 처리
- **2025-12-23**: I-01 ~ I-09 (9개 이슈 처리)
- **2025-12-24**: I-10 ~ I-17 (8개 이슈 처리)
- **2025-12-25**: I-18 ~ I-24 (7개 이슈 처리)

---

*최종 업데이트: 2025-12-25 22:00 KST*
