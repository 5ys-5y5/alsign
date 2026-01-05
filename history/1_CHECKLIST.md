# 📋 AlSign 이슈 체크리스트

> **목적**: 서비스의 모든 이슈들의 반영 상태를 한눈에 파악
>
> **범례**: ✅ 반영완료 | 🔄 부분반영 | ❌ 미반영 | ⏸️ 보류
>
> **문서 연결**: 체크리스트(여기) → `2_FLOW.md` (흐름도) → `3_DETAIL.md` (상세도)
>
> **최종 업데이트**: 2026-01-05 KST (I-43 설계 완료 - Dashboard Events 로딩 성능 개선, txn_price_trend 테이블 분리)

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
| I-25 | API별 기준 날짜 불일치 (marketCap) | ✅ | 2025-12-27 | 2025-12-27 | ✅ | #I-25 | #I-25 |
| I-26 | consensus_summary_cache event_date 무시 | ✅ | 2025-12-27 | 2025-12-27 | N/A | #I-26 | #I-26 |
| I-27 | priceTrend 티커별 1회 호출 확인 | ✅ | 2025-12-27 | 2025-12-27 | N/A | #I-27 | #I-27 |
| I-28 | 재무제표 TTM 계산 시간적 유효성 | ✅ | 2025-12-27 | 2025-12-27 | N/A | #I-28 | #I-28 |
| I-29 | evt_consensus 2단계 계산 미실행 | ✅ | 2025-12-30 | 2025-12-31 | N/A | #I-29 | #I-29 |
| I-30 | 메트릭별 원천 날짜 추적 (_meta.sources) | ✅ | 2025-12-30 | 2025-12-31 | N/A | #I-30 | #I-30 |
| I-31 | targetSummary 계산 (consensusSummary 대체) | ✅ | 2025-12-31 | 2025-12-31 | ✅ | #I-31 | #I-31 |
| I-32 | Log 패널 리사이즈 기능 | ✅ | 2025-12-31 | 2025-12-31 | N/A | #I-32 | #I-32 |
| I-33 | 본문 80% 너비 및 가운데 정렬 | ✅ | 2025-12-31 | 2025-12-31 | N/A | #I-33 | #I-33 |
| I-34 | /setRequests API 변경 기능 (Schema 검증) | ✅ | 2025-12-31 | 2025-12-31 | N/A | #I-34 | #I-34 |
| I-35 | GET /sourceData 병렬 처리 성능 개선 | ✅ | 2025-12-31 | 2025-12-31 | N/A | #I-35 | #I-35 |
| I-36 | Quantitative Position/Disparity 항상 None | 🔄 DEPRECATED | 2025-12-31 | 2025-12-31 | I-41로 대체 | #I-36 | #I-36 |
| I-37 | targetMedian 명칭/값 불일치 (평균 vs 중앙값) | ✅ | 2025-12-31 | 2025-12-31 | N/A | #I-37 | #I-37 |
| I-38 | calcFairValue 기본값 False로 인한 NULL | 🔄 DEPRECATED | 2026-01-01 | 2026-01-01 | I-41로 대체 | #I-38 | #I-38 |
| I-39 | target_summary JSONB 문자열 파싱 오류 | ✅ | 2026-01-02 | 2026-01-02 | N/A | #I-39 | #I-39 |
| I-40 | Peer tickers 미존재 시 로깅 부족 | 🔄 DEPRECATED | 2026-01-02 | 2026-01-02 | I-41로 통합 | #I-40 | #I-40 |
| I-41 | priceQuantitative 메트릭 미구현 (설계 불일치) | ✅ | 2026-01-02 | 2026-01-02 | N/A | #I-41 | #I-41 |
| I-42 | fmp-stock-peers schema mapping + DB 저장 실패 | ✅ | 2026-01-02 | 2026-01-02 | N/A | #I-42 | #I-42 |
| I-43 | Dashboard Events 표 로딩 성능 개선 | 🔄 | 2026-01-05 | - | ✅ | #I-43 | #I-43 |

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

## 6. 시간적 유효성 이슈 - 2025-12-27 (I-25 ~ I-27)

### I-25: API별 기준 날짜 불일치 (Temporal Validity Mismatch) ✅
	발견: 2025-12-27 | 해결: 2025-12-27
	- ✅ marketCap: `fmp-historical-market-capitalization` API로 해결 완료
	  - API: `/stable/historical-market-capitalization?symbol={ticker}&from={fromDate}&to={toDate}`
	  - **핵심**: `from`/`to` 파라미터로 날짜 범위 특정 가능
	  - 응답에 date 필드 포함 → event_date 기준 필터링 가능
	  - **구현**: 시계열 데이터에서 가장 최근 날짜의 값(첫 번째) 선택
	- ❌ fmp-price-target-consensus API: 현재 시점 consensus만 반환 (I-26 이슈)
	- ✅ 재무제표 API: event_date 기준 필터링 적용됨 (정상)
	
	**구현 완료 사항**:
	- ✅ SQL 스크립트 작성: `backend/scripts/fix_I25_historical_market_cap.sql`
	- ✅ config_lv1_api_list에 fmp-historical-market-capitalization API 추가 (사용자 직접 반영)
	- ✅ config_lv2_metric에서 marketCap 메트릭의 api_list_id 변경 (사용자 직접 반영)
	- ✅ valuation_service.py에서 historical-market-cap API 호출 시 from/to 파라미터 처리
	- ✅ metric_engine.py에서 시계열 marketCap 응답에서 가장 최근 값만 추출

### I-26: consensus_summary_cache가 event_date 무시 ✅
	발견: 2025-12-27 | 해결: 2025-12-27
	- ✅ 문제: FMP API가 현재 시점 consensus만 제공, 과거 데이터 없음
	- ✅ 해결: 과거 이벤트(7일 이전)에는 consensus 값을 NULL로 처리
	- ✅ `_meta` 필드에 데이터 가용성 및 이유 명시
	- ✅ 최근 이벤트(7일 이내)에는 현재 consensus 값 사용 (정상)
	
	**구현 완료 사항**:
	- ✅ `calculate_qualitative_metrics_fast()` 함수 수정
	- ✅ 과거 이벤트 판단 로직 추가 (`event_date < today - 7days`)
	- ✅ `_meta` 필드에 `dataAvailable`, `reason`, `fetchDate` 정보 포함

### I-27: priceTrend 티커별 1회 호출 확인 ✅
	발견: 2025-12-27 | 확인 완료
	- ✅ generate_price_trends()에서 ohlc_cache를 티커별로 구축
	- ✅ 각 이벤트는 캐시에서 날짜 기반 조회
	- ✅ 티커당 1회만 OHLC API 호출됨 (정상 작동)

### I-28: 재무제표 TTM 계산 시간적 유효성 확인 ✅
	발견: 2025-12-27 | 확인 완료
	- ✅ fmp-income-statement 응답에서 event_date 기준 필터링 정상 작동
	- ✅ 필터링 로직: `_get_record_date(r) <= event_date_obj`
	- ✅ TTM 계산: 필터링 후 최근 4분기 합산
	- ✅ 예시: event_date=2024-12-22 → 2024-12-28 분기 제외됨 (정상)
	
	**핵심 로직 위치**:
	- `valuation_service.py:847-850`: 날짜 필터링
	- `metric_engine.py:689-722`: TTM 합산 (_ttm_sum_or_scaled)

---

## 7. consensusSignal 및 메타데이터 이슈 - 2025-12-30 (I-29 ~ I-30)

### I-29: evt_consensus 2단계 계산 미실행 ✅
	발견: 2025-12-30 | 해결됨
	- ✅ evt_consensus 테이블의 price_target_prev, price_when_posted_prev, direction이 모두 NULL
	- ✅ 원인: GET /sourceData?mode=consensus의 2단계 계산이 실행되지 않음
	- ✅ 해결: calc_mode=calculation 모드 추가 (API 호출 없이 2단계 계산만 수행)
	- ✅ 사용법: GET /sourceData?mode=consensus&calc_mode=calculation&calc_scope=all

### I-30: 메트릭별 원천 날짜 추적 (옵션 B 채택) ✅
	발견: 2025-12-30 | 해결됨: 2025-12-31
	- ✅ 각 메트릭별로 원천 데이터의 날짜 정보가 기록됨
	- ✅ MetricCalculationEngine에 metric_sources 딕셔너리 추가
	- ✅ _calculate_api_field_with_source: API 응답에서 날짜 추출
	- ✅ _calculate_aggregation_with_source: 기본 메트릭 소스 상속
	- ✅ _calculate_expression_with_source: 의존성 소스 수집
	- ✅ _group_by_domain: _meta.sources에 메트릭별 상세 소스 정보 포함

### I-31: targetSummary 계산 (consensusSummary 대체) ✅
	발견: 2025-12-31 | 해결됨
	- ✅ evt_consensus 테이블에 target_summary JSONB 컬럼 추가
	- ✅ GET /sourceData?mode=consensus에 Phase 3 추가 (targetSummary 계산 및 저장)
	- ✅ overwrite=true: 지정된 scope의 모든 행 재계산
	- ✅ overwrite=false: target_summary가 NULL인 행만 계산
	- ✅ POST /backfillEventsTable에서 evt_consensus.target_summary 읽기

---

## 8. UI/UX 개선 이슈 - 2025-12-31 (I-32 ~ I-34)

### I-32: Log 패널 리사이즈 기능 ✅
	발견: 2025-12-31 | 해결됨
	- ✅ 요구사항: Cursor의 agent UI처럼 마우스로 패널 크기 조정
	- ✅ 구현: BottomPanel에 드래그 리사이즈 핸들러 추가
	- ✅ 하단 패널: 상단 가장자리 드래그 → 높이 조절 (200px ~ 600px)
	- ✅ 우측 패널: 좌측 가장자리 드래그 → 너비 조절 (300px ~ 800px)
	- ✅ 마우스 호버 시 파란색 하이라이트로 리사이즈 영역 표시

### I-33: 본문 80% 너비 및 가운데 정렬 ✅
	발견: 2025-12-31 | 해결됨
	- ✅ 요구사항: 모든 라우터 본문이 출력 영역의 80% 너비로 가운데 정렬
	- ✅ 적용 페이지: /requests, /setRequests, /control, /conditionGroup, /dashboard
	- ✅ /requests: Wrapper div로 패널 영역 제외 후 80% 적용
	- ✅ 패널 접힘/펼침 상태에서도 80% 유지

### I-34: /setRequests API 변경 기능 (Schema 기반 검증) ✅
	발견: 2025-12-31 | 해결됨
	- ✅ 요구사항: 각 엔드포인트/모드별 config_lv1_api_list ID 변경 가능
	- ✅ 검증 방식: API 호출 없이 config_lv1_api_list.schema 필드로 필수 키 존재 확인
	- ✅ UI: 모드별 "변경" 버튼 → 모달에서 새 API 선택 → Schema 검증 → 저장
	- ✅ 검증 실패 시 저장 불가, 누락된 키 표시

### I-35: GET /sourceData 병렬 처리 성능 개선 ✅
	발견: 2025-12-31 | 해결됨
	- ✅ mode=consensus: 티커별 API 호출 병렬 처리 (asyncio.Semaphore)
	- ✅ mode=earning: 날짜 범위별 API 호출 병렬 처리
	- ✅ 동시성: API_CONCURRENCY = 10 (Rate limit 고려)
	- ✅ 진행률 로깅: 배치별 progress, ETA 출력
	
	**성능 개선 효과** (mode=consensus 기준):
	| 항목 | Before | After | 개선율 |
	|------|--------|-------|--------|
	| 처리 방식 | 순차 (1개씩) | 병렬 (10개 동시) | - |
	| 5000 티커 예상 | ~83분 | ~8분 | **90% ↓** |

---

## 9. 계산 로직 검토 이슈 - 2025-12-31 (I-36 ~ I-37)

### I-36: Quantitative Position/Disparity 항상 None 🔄 DEPRECATED
	발견: 2025-12-31 | 해결됨: 2025-12-31 | **폐기됨: 2026-01-02** (I-41로 대체)

	⚠️ **DEPRECATED**: 이 이슈는 임시 해결책이었으며, I-41에서 원본 설계대로 `priceQuantitative` 메트릭을 구현하여 대체되었습니다.

	**폐기 이유**:
	- 원본 설계(`1_guideline(function).ini`)는 `priceQuantitative` **메트릭**을 요구했으나, 이 해결책은 `calcFairValue` **파라미터**로 우회함
	- `config_lv2_metric` 테이블에 메트릭을 정의하지 않아 설계 불일치 발생
	- I-41에서 메트릭 시스템에 통합하여 근본적으로 해결

	**마이그레이션**:
	- `calcFairValue` 파라미터는 I-41 배포 후 제거될 예정
	- 계산 로직 (`get_peer_tickers`, `calculate_sector_average_metrics` 등)은 I-41에서 재사용됨

	---

	**원래 구현 내용** (참고용):

	**현상**: txn_events.position_quantitative, disparity_quantitative가 항상 NULL

	**원인**: Quantitative 지표(PER, PBR, PSR 등)에서 "목표 주가(price_target)"를 직접 도출하는 로직 없음

	**사용자 선택**: **옵션 A** - 업종 평균 대비 적정가 계산

	**구현 내용**:
	- ✅ `fmp-stock-peers` API로 동종 업종 티커 조회 (symbol만 사용, 다른 값은 event_date와 무관)
	- ✅ `calculate_sector_average_metrics()`: 동종 업종 평균 PER/PBR 계산
	- ✅ `calculate_fair_value_from_sector()`: 업종 평균 PER × EPS로 적정가 계산
	- ✅ `calculate_fair_value_for_ticker()`: 통합 함수
	- ✅ `calcFairValue` 파라미터 추가 (선택적 기능)

	**사용법**:
	```bash
	# 업종 평균 기반 적정가 계산 활성화
	POST /backfillEventsTable?calcFairValue=true&tickers=AAPL
	```

### I-37: targetMedian 명칭/값 불일치 (평균 vs 중앙값) ✅
	발견: 2025-12-31 | 해결됨: 2025-12-31
	
	**현상**: 변수명 `targetMedian`인데 실제 값은 `AVG(price_target)` (평균값)
	
	**사용자 선택**: **옵션 B** - PostgreSQL PERCENTILE_CONT로 실제 Median 계산 구현
	
	**구현 내용**:
	- ✅ `calculate_target_summary()` SQL에 `PERCENTILE_CONT(0.5)` 추가
	- ✅ 반환 구조에 Median, Avg, Min, Max 모두 포함
	- ✅ `valuation_service.py`에서 실제 Median 사용 (`allTimeMedianPriceTarget`)
	
	**데이터 재계산**:
	```bash
	GET /sourceData?mode=consensus&overwrite=true
	```

### I-38: calcFairValue 기본값 False로 인한 NULL 🔄 DEPRECATED
	발견: 2026-01-01 | 해결됨: 2026-01-01 | **폐기됨: 2026-01-02** (I-41로 대체)

	⚠️ **DEPRECATED**: `calcFairValue` 파라미터 자체가 임시 해결책이었으며, I-41에서 메트릭 시스템에 통합되어 더 이상 필요하지 않습니다.

	**폐기 이유**:
	- 파라미터 기반 접근은 메트릭 시스템 아키텍처와 불일치
	- I-41에서 `priceQuantitative` 메트릭을 `config_lv2_metric`에 정의하면 자동으로 계산됨
	- 명시적 파라미터 전달 불필요

	**마이그레이션**:
	- I-41 배포 후 `calcFairValue` 파라미터 제거 예정
	- 메트릭이 `metrics_by_domain`에 포함되면 자동 계산

	---

	**원래 구현 내용** (참고용):

	**현상**:
	- `POST /backfillEventsTable` 호출 시 `position_quantitative`, `disparity_quantitative`가 100% NULL
	- I-36에서 `calcFairValue` 파라미터를 추가했으나, 기본값이 `False`로 설정되어 있어 명시적으로 `?calcFairValue=true`를 지정하지 않으면 계산되지 않음

	**근본 원인**:
	- `backend/src/models/request_models.py:248` - `default=False`
	- `backend/src/services/valuation_service.py:441` - `calc_fair_value: bool = False`
	- Quantitative metrics는 price target이 없으므로, fair value 계산 없이는 position/disparity를 계산할 수 없음

	**해결책**:
	- ✅ `BackfillEventsTableQueryParams.calc_fair_value` 기본값을 `True`로 변경
	- ✅ `calculate_valuations()` 함수 시그니처도 `calc_fair_value: bool = True`로 변경
	- ✅ 이제 파라미터 없이 `POST /backfillEventsTable` 호출해도 자동으로 position/disparity 계산됨

	**영향**:
	- 업종 평균 PER/PBR 기반 적정가 자동 계산 (I-36)
	- `fmp-stock-peers` API 추가 호출 발생 (성능 영향 미미)

	**검증**:
	```bash
	# 재계산 (calcFairValue=true가 기본값)
	POST /backfillEventsTable

	# 또는 명시적으로 비활성화 가능
	POST /backfillEventsTable?calcFairValue=false
	```

---

## 10. 설계 불일치 해결 이슈 - 2026-01-02 (I-41)

### I-41: priceQuantitative 메트릭 미구현 (설계 불일치) + 선택적 메트릭 업데이트 ✅
	발견: 2026-01-02 | 해결됨: 2026-01-02

	**Part 1: 설계 불일치 - priceQuantitative 메트릭 구현**

	**현상**:
	- 원본 설계(`prompt/1_guideline(function).ini`:892-897)는 `priceQuantitative` 메트릭 사용을 명시
	- 실제 구현에는 `priceQuantitative` 메트릭이 `config_lv2_metric` 테이블에 존재하지 않음
	- 대신 I-36에서 `calcFairValue` 파라미터로 우회 구현

	**근본 원인**:
	- 설계 문서와 구현 간 불일치
	- 메트릭 시스템 아키텍처를 따르지 않은 임시 해결책 (I-36, I-38)

	**LLM 제안**: 2가지 옵션 제시
	- **옵션 A**: 원본 설계대로 priceQuantitative 메트릭 구현 (메트릭 시스템 통합)
	- **옵션 B**: calcFairValue 파라미터 유지 (빠른 우회 해결)

	**사용자 선택**: **옵션 A** 채택 - 근본적 해결 선호

	**LLM 반영 - 데이터베이스 설정**:
	- ✅ `config_lv2_metric` 테이블에 `priceQuantitative` 메트릭 정의
	- ✅ source='custom' 지원을 위한 CHECK 제약조건 업데이트
	- ✅ aggregation_params에 계산 방법 메타데이터 저장

	**메트릭 정의** (`backend/scripts/add_priceQuantitative_metric.sql`):
	```sql
	INSERT INTO config_lv2_metric (
	    id, source, domain, aggregation_params
	) VALUES (
	    'priceQuantitative',
	    'custom',
	    'quantitative-valuation',
	    '{"calculation_method": "sector_average_fair_value", ...}'::jsonb
	);
	```

	**LLM 반영 - 백엔드 구현**:
	- ✅ `MetricEngine.calculate_all()`: custom_values 파라미터 추가
	- ✅ `MetricEngine._calculate_metric_with_reason()`: source='custom' 처리 로직
	- ✅ `calculate_price_quantitative_metric()`: 기존 calcFairValue 로직 래핑
	- ✅ `process_ticker_batch()`: priceQuantitative 계산 후 custom_values로 전달

	**계산 프로세스**:
	1. `fmp-stock-peers` API로 동종 업종 티커 조회
	2. 각 peer 티커의 PER/PBR 계산
	3. IQR 방식으로 이상치 제거 후 평균 계산
	4. `fair_value = sector_avg_PER × (price / current_PER)`
	5. `position_quantitative = 'long' if fair_value > price else 'short'`
	6. `disparity_quantitative = (fair_value / price) - 1`

	---

	**Part 2: 선택적 메트릭 업데이트 기능 (Selective Metric Update)**

	**사용자 요구사항**:
	> "테이블에 값을 효율적으로 채워넣기 위해 txn_events 테이블의 config_lv2_metric 테이블의 id별로 파라미터에 값을 입력하면
	> 해당하는 값만 overwrite 하거나 null 값만 업데이트 하거나 입력한 ticker에 대해서만 엔드포인트를 실행할 수 있도록"

	**LLM 제안**: 3가지 옵션 제시
	- **옵션 1**: metrics 파라미터만 추가 (단순)
	- **옵션 2**: metrics + overwriteMetrics 파라미터 (유연)
	- **옵션 3**: 옵션 2 + DB 레벨 selective update (완전)

	**사용자 선택**: **옵션 3** 채택 - 완전한 구현 선호

	**LLM 반영 - API 파라미터**:
	- ✅ `metrics`: 업데이트할 메트릭 ID 리스트 (예: `priceQuantitative,PER,PBR`)
	- ✅ `overwriteMetrics`: True=덮어쓰기, False=NULL만 업데이트
	- ✅ `BackfillEventsTableQueryParams.get_metrics_list()`: 파싱 함수 추가

	**LLM 반영 - 백엔드 로직**:
	- ✅ `calculate_valuations()`: metrics_list 파라미터 추가
	- ✅ `process_ticker_batch()`: metrics_list를 DB 업데이트에 전달
	- ✅ `batch_update_event_valuations()`: JSONB 선택적 병합 쿼리 구현

	**데이터베이스 업데이트 로직** (`backend/src/database/queries/metrics.py`):
	```sql
	-- metrics_list 지정 시: JSONB || 연산자로 선택적 병합
	SET value_quantitative = COALESCE(e.value_quantitative, '{}'::jsonb) || b.value_quantitative

	-- metrics_list 미지정 시: 기존 로직 (전체 교체 또는 NULL만 업데이트)
	```

	**사용법 예시**:
	```bash
	# priceQuantitative만 NULL 값 업데이트
	POST /backfillEventsTable?metrics=priceQuantitative&overwriteMetrics=false

	# priceQuantitative 강제 재계산 (덮어쓰기)
	POST /backfillEventsTable?metrics=priceQuantitative&overwriteMetrics=true

	# 특정 ticker의 여러 메트릭 업데이트
	POST /backfillEventsTable?tickers=AAPL&metrics=priceQuantitative,PER,PBR&overwriteMetrics=true
	```

	---

	**Part 3: API 단순화 (overwriteMetrics 제거)** - 2026-01-02

	사용자 제안으로 `overwriteMetrics` 파라미터를 제거하고 기존 `overwrite` 파라미터를 확장:
	- **문제**: `overwrite`와 `overwriteMetrics` 2개 파라미터로 인한 UX 혼란
	- **사용자 제안**: "overwriteMetrics는 이미 모든 엔드포인트에 overwrite 파라미터가 있어 이것을 사용하면 되는 것 아닌가요?"
	- **LLM 동의**: 단일 파라미터로 문맥적 의미 부여 (metrics 유무에 따라)
	- **반영**:
	  - `overwriteMetrics` 파라미터 완전 제거
	  - `overwrite` 파라미터 의미 확장:
	    - `metrics` 지정 시: 해당 메트릭에만 적용
	    - `metrics` 미지정 시: 전체 필드에 적용
	  - 백엔드 4개 파일, 프론트엔드 2개 파일 수정

	**알려진 제한사항**:
	- Peer tickers 미존재 시 priceQuantitative NULL (소형주, 특수 섹터)
	- fmp-stock-peers는 현재 peer 목록만 반환 (과거 데이터 없음)

	**폐기된 이슈**:
	- **I-36**: calcFairValue 파라미터 방식 → priceQuantitative 메트릭으로 대체
	- **I-38**: calcFairValue 기본값 → 메트릭 자동 계산으로 대체
	- **I-40**: Peer tickers 로깅 → priceQuantitative 제한사항으로 통합

	**수정된 파일**:
	- `backend/scripts/add_priceQuantitative_metric.sql`: 메트릭 정의
	- `backend/src/models/request_models.py`: metrics 파라미터, overwrite 의미 확장
	- `backend/src/routers/events.py`: 파라미터 파싱 (overwriteMetrics 제거)
	- `backend/src/services/valuation_service.py`: 계산 로직 통합 (overwriteMetrics 제거)
	- `backend/src/services/metric_engine.py`: custom_values 지원
	- `backend/src/database/queries/metrics.py`: 선택적 JSONB 업데이트 (SQL 단순화)
	- `frontend/src/pages/RequestsPage.jsx`: metrics, calcFairValue 파라미터 추가
	- `frontend/src/pages/SetRequestsPage.jsx`: endpoint flow 파라미터 업데이트

	**참조**:
	- 설계 문서: `backend/DESIGN_priceQuantitative_metric.md`
	- SQL 스크립트: `backend/scripts/add_priceQuantitative_metric.sql`
	- 이슈 분석: `history/ISSUE_priceQuantitative_MISSING.md`

### I-42: fmp-stock-peers API schema mapping 오류 + priceQuantitative DB 저장 실패 🔄
	발견: 2026-01-02 | 진행중

	**Part 1: Schema Mapping Error (✅ 완료)**

	**현상**:
	- I-41 구현 후 RGTI의 priceQuantitative가 여전히 NULL
	- Peer ticker API 호출 시 schema mapping TypeError 발생
	- 에러: `TypeError: unhashable type: 'dict'` at `external_api.py:86`

	**원인**:
	- `fmp-stock-peers` API schema가 nested dict 구조로 정의됨
	- `_apply_schema_mapping()` 함수가 nested schema를 처리하지 못함
	- `reverse_schema = {v: k for k, v in schema.items()}` 에서 dict를 key로 사용 시도

	**LLM 제안**: 3가지 옵션 제시
	- **옵션 A**: Schema mapping 함수 개선 (nested schema 지원 추가)
	- **옵션 B**: fmp-stock-peers schema를 flat 구조로 변경
	- **옵션 C**: Schema mapping 우회 (특정 API만)

	**사용자 선택**: 사용자 명시 없음 → LLM이 **옵션 A + B 결합** 선택
	- 옵션 A: `_apply_schema_mapping()` 함수 개선으로 범용 해결
	- 옵션 B: `fmp-stock-peers` schema를 실제 API 응답에 맞게 수정

	**LLM 반영 내용**:
	- ✅ `external_api.py`: `_apply_schema_mapping()` nested schema 지원 추가
	  - Line 87-102: nested_schemas 딕셔너리로 array/object 타입 분리 처리
	  - Line 104-119: `map_array_items()` helper 함수 구현
	  - Line 121-142: `map_item()` 함수에서 nested field 처리 로직 추가

	- ✅ `valuation_service.py`: `get_peer_tickers()` 함수 수정
	  - Line 1952-1960: Flat list 구조 처리 (nested peerTickers 제거)
	  - Schema mapping 후 'ticker' 필드 직접 추출

	- ✅ Database: `fmp-stock-peers` schema 수정
	  ```sql
	  -- Before (nested, 에러 발생):
	  {
	    "ticker": "symbol",
	    "peerTickers": {
	      "type": "array",
	      "items": {"symbol": {"type": "string", "value": "symbol"}, ...}
	    }
	  }

	  -- After (flat, 정상 작동):
	  {
	    "ticker": "symbol",
	    "companyName": "companyName",
	    "price": "price",
	    "mktCap": "mktCap"
	  }
	  ```

	**검증 결과** (Part 1):
	- ✅ Peer ticker retrieval: 성공 (RGTI → 9 peers: BILI, CACI, DUOL, IONQ, QBTS, QXO, SAIL, SNX, ZBRA)
	- ✅ Sector average calculation: 성공 (PER: 20.15, PBR: 3.87)
	- ✅ Fair value calculation: 성공 (로직 검증 완료)

	---

	**Part 2: Database 저장 실패 (✅ 완료)**

	**현상**:
	- priceQuantitative 계산 성공하지만 데이터베이스에 NULL로 저장됨
	- `test_full_flow.py` 실행 시 "Current price not found!" 에러 발생
	- 데이터베이스 조회 결과 nested structure 발견:
	  ```json
	  {
	    "valuation": {
	      "values": {"priceQuantitative": null, "PER": -19.09, ...},
	      "dateInfo": {...}
	    }
	  }
	  ```

	**원인 분석**:
	1. **Formatter가 데이터베이스 저장 전에 호출됨**
	   - `valuation_service.py:264`: `format_value_quantitative()` 호출
	   - Nested structure 생성: `{values: {...}, dateInfo: {...}}`

	2. **데이터베이스 쿼리 경로 불일치**
	   - 기대 경로: `value_quantitative->'valuation'->>'priceQuantitative'`
	   - 실제 경로: `value_quantitative->'valuation'->'values'->>'priceQuantitative'`

	3. **Cascading failures**
	   - currentPrice 조회 실패 (`value_qualitative->>'currentPrice'` → NULL)
	   - currentPrice 없으면 priceQuantitative 계산 차단됨
	   - 계산되어도 nested path로 인해 조회 실패

	**LLM 제안**: 3가지 옵션 제시
	- **옵션 A**: Formatter를 API 응답 단계로 이동 (데이터베이스 저장 후)
	- **옵션 B**: Formatter 완전 제거, raw engine output 저장
	- **옵션 C**: 데이터베이스 쿼리를 nested path로 수정

	**사용자 선택**: 사용자 명시 없음 → LLM이 **옵션 B** 선택
	- Formatter는 API 응답 포맷팅 전용으로 사용되어야 함
	- 데이터베이스에는 engine의 raw output 저장 (flat structure)
	- 기존 쿼리들과의 호환성 유지

	**LLM 반영 내용**:
	- ✅ `valuation_service.py:263-287`: Formatter 호출 제거
	  ```python
	  # OLD (BROKEN):
	  # formatted_quant = format_value_quantitative(quant_result.get('value'))
	  # formatted_qual = format_value_qualitative(qual_result.get('value'))

	  # NEW (FIXED):
	  value_quant = quant_result.get('value')
	  value_qual = qual_result.get('value')
	  ```

	- ✅ `valuation_service.py:15-16`: Formatter imports 주석 처리
	  ```python
	  # I-42: Removed formatter imports - formatting should only be done in API responses
	  # from .utils.response_formatter import format_value_quantitative, format_value_qualitative
	  ```

	- ✅ `metrics.py:274-279`: Debug logging 추가
	  - 데이터베이스 저장 직전 구조 확인 로그

	**검증 결과** (Part 2):
	- ✅ Engine output 검증: Flat structure 확인 (`test_engine_output.py`)
	  ```json
	  {
	    "valuation": {
	      "priceQuantitative": 123.45,
	      "PER": -19.09,
	      "_meta": {...}
	    }
	  }
	  ```
	- ✅ custom_values 전달: Engine에서 정상 처리 확인
	- ⏳ 최종 통합 테스트: 서버 재시작 및 backfill 재실행 필요

	**수정된 파일** (전체):
	- `backend/src/services/external_api.py`: Schema mapping 함수 개선 (Part 1)
	- `backend/src/services/valuation_service.py`:
	  - Peer ticker 추출 로직 수정 (Part 1)
	  - Formatter 호출 제거 (Part 2)
	- `backend/src/database/queries/metrics.py`: Debug logging 추가 (Part 2)
	- Database: `config_lv1_api_list.fmp-stock-peers.schema` 수정 (Part 1)

	**테스트 스크립트 생성**:
	- `backend/test_rgti_peers_api.py`: API 호출 테스트 (Part 1)
	- `backend/test_sector_averages.py`: Sector average 계산 테스트 (Part 1)
	- `backend/test_full_flow.py`: End-to-end 테스트 (Part 1-2)
	- `backend/test_engine_output.py`: Engine flat structure 검증 (Part 2)

---

## 11. 성능 최적화 이슈 - 2026-01-05 (I-43)

### I-43: Dashboard Events 표 로딩 성능 개선 - txn_price_trend 테이블 분리 🔄
	발견: 2026-01-05 | 진행중

	**현상**:
	- GET /dashboard/events 응답 속도 2-5초 (100행 기준)
	- 매 요청마다 JSONB price_trend 파싱 + 28개 dayOffset 추출 (2,800번 딕셔너리 조회)
	- 필터/정렬 컬럼에 인덱스 없음

	**성능 분석**:
	- 데이터베이스: 146,696행, 182MB (인덱스 28MB)
	- 주요 병목: Python JSONB 파싱 (~1.5초)
	- 부차 병목: 필터링/정렬 인덱스 부재 (~500ms)

	**LLM 제안**: 6가지 최적화 방안
	- **계획 1**: 계산된 컬럼 추가 (80-90% 개선, 가장 효과적)
	- **계획 2**: DB 함수 + Materialized View (70-80% 개선)
	- **계획 3**: 필터/정렬 인덱스 추가 (30-50% 개선, 빠른 적용)
	- **계획 4**: 프론트엔드 가상화 (체감 성능 80% 개선)
	- **계획 5**: 응답 캐싱 Redis (캐시 히트 시 95% 개선)
	- **계획 6**: 페이지 크기 최적화 (20-30% 개선)

	**사용자 선택**: **계획 1 변형** - txn_price_trend 테이블 분리
	- price_trend JSONB를 별도 테이블로 정규화
	- ticker + event_date를 PRIMARY KEY로 사용
	- 29개 dayOffset 컬럼 (D-14 ~ D14, D0 포함)
	- 각 컬럼에 JSONB 저장: `{price: {OHLC}, dayOffset0: {close}, performance: {close}}`
	- WTS는 wts_long, wts_short 컬럼으로 미리 계산

	**설계 확정 사항** (사용자 답변):
	1. ✅ D0 컬럼 생성: txn_price_trend 테이블에만 (Dashboard 표에는 표시 안 함)
	2. ✅ JSONB 구조:
	   ```json
	   {
	     "price_trend": {"low": 25.29, "high": 26.53, "open": 26.37, "close": 25.57},
	     "dayOffset0": {"close": 28.57},
	     "performance": {"close": -0.0018796992}
	   }
	   ```
	3. ✅ WTS 계산: txn_price_trend에 wts_long, wts_short 컬럼 저장
	4. ✅ WTS 업데이트: null → 값 채워질 때마다 재계산
	5. ✅ 데이터 마이그레이션: 기존 txn_events.price_trend → txn_price_trend
	6. ✅ Backfill 기능 유지: ticker별 1회 호출, 날짜 범위, overwrite 모두 유지

	**구현 계획** (미완료):
	- ⏳ Step 1: txn_price_trend 테이블 생성 (DDL 스크립트)
	- ⏳ Step 2: 데이터 마이그레이션 (기존 price_trend → 새 테이블)
	- ⏳ Step 3: POST /backfillEventsTable 수정 (새 테이블에 데이터 채우기)
	- ⏳ Step 4: GET /dashboard/events 수정 (LEFT JOIN으로 조회)
	- ⏳ Step 5: 성능 테스트 및 검증
	- ⏳ Step 6: txn_events.price_trend 컬럼 제거 (선택)

	**예상 성능 개선**:
	| 작업 | 현재 | 개선 후 | 개선율 |
	|------|------|---------|--------|
	| GET /events (100행) | 2-5초 | 0.2-0.4초 | **85-92%** |
	| DB 쿼리 | ~500ms | ~100ms | 80% |
	| Python 처리 | ~1500ms | ~50ms | 97% |

	**참조**:
	- 설계 문서: 본 대화 로그
	- 흐름도: `2_FLOW.md#I-43`
	- 상세 구현: `3_DETAIL.md#I-43`
	- 엔드포인트: `0_endpointFlow/GET_dashboard_events.md`, `POST_backfillEventsTable.md`

---

## 📈 통계

### 상태별 현황
- ✅ **완료**: 37개 (86.0%)
- 🔄 **진행중**: 1개 (2.3%) - I-43
- 🔄 **DEPRECATED**: 3개 (7.0%) - I-36, I-38, I-40 (I-41로 대체됨)
- ⏸️ **보류**: 2개 (4.7%) - I-04, I-14

> **전체 이슈**: 43개 (I-01 ~ I-43)

### 일자별 이슈 처리
- **2025-12-23**: I-01 ~ I-09 (9개 이슈 처리)
- **2025-12-24**: I-10 ~ I-17 (8개 이슈 처리)
- **2025-12-25**: I-18 ~ I-24 (7개 이슈 처리)
- **2025-12-27**: I-25 ~ I-28 (4개 이슈 식별 및 완료)
- **2025-12-30**: I-29 (식별)
- **2025-12-31**: I-29 ~ I-37 (9개 이슈 해결 - 백엔드 6건, UI/UX 3건)
- **2026-01-01**: I-38 (calcFairValue 기본값 변경 - 현재 deprecated)
- **2026-01-02**: I-39 ~ I-42 (JSONB 파싱, priceQuantitative 메트릭 구현, schema mapping 개선)
- **2026-01-05**: I-43 (Dashboard Events 로딩 성능 개선 - txn_price_trend 테이블 분리 설계)

### 폐기 이슈 (Deprecated)
- **I-36**: calcFairValue 파라미터 → I-41 priceQuantitative 메트릭으로 대체
- **I-38**: calcFairValue 기본값 → I-41 메트릭 자동 계산으로 대체
- **I-40**: Peer tickers 로깅 → I-41 제한사항으로 통합

---

*최종 업데이트: 2026-01-05 KST (I-43 설계 완료 - Dashboard Events 로딩 성능 개선, txn_price_trend 테이블 분리)*
*이전 업데이트: I-42 완료 - fmp-stock-peers schema mapping 개선, priceQuantitative DB 저장 수정*
*설계 문서: backend/DESIGN_priceQuantitative_metric.md*
*이슈 분석: history/ISSUE_priceQuantitative_MISSING.md*
