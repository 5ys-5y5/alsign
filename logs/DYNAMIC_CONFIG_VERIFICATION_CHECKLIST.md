# 동적 설정 항목 검증 체크리스트

본 체크리스트는 `DYNAMIC_CONFIG_CHECK.md`에 명시된 각 항목이 실제 코드에 올바르게 반영되었는지 검증하기 위한 체크리스트입니다.

각 항목을 검증할 때는 해당 파일을 열어 실제 코드를 확인하고, 아래 체크리스트를 순서대로 검증하세요.

---

## 1. GET /sourceData

### 1.1 API 설정 동적 사용 ✅

**검증 대상 파일**:
- `backend/src/services/external_api.py`
- `backend/src/database/queries/api_config.py`

**지침 위치**: `1_guideline(function).ini` line 404-405, 425-428

#### 체크리스트

- [ ] **1.1.1** `external_api.py`의 `FMPAPIClient.call_api()` 함수에서 `api_config.get_api_config_by_id()`를 호출하여 API 설정을 DB에서 읽는지 확인
- [ ] **1.1.2** `external_api.py`의 `FMPAPIClient._get_api_key()` 함수에서 `api_config.get_api_service_config()`를 호출하여 API 키를 DB에서 읽는지 확인
- [ ] **1.1.3** `api_config.py`의 `get_api_config_by_id()` 함수가 `config_lv1_api_list` 테이블에서 데이터를 조회하는지 확인
- [ ] **1.1.4** `api_config.py`의 `get_api_service_config()` 함수가 `config_lv1_api_service` 테이블에서 데이터를 조회하는지 확인
- [ ] **1.1.5** Rate Limit이 `config_lv1_api_service.usagePerMin`에서 동적으로 읽혀서 사용되는지 확인 (RateLimiter 초기화 부분)
- [ ] **1.1.6** API URL이 `config_lv1_api_list.api` 컬럼 값으로 동적으로 구성되는지 확인
- [ ] **1.1.7** 스키마 매핑이 `config_lv1_api_list.schema` 컬럼 값으로 동적으로 수행되는지 확인

**검증 방법**: 
1. `external_api.py` line 148-163 부근 코드 확인
2. `api_config.py` 전체 코드 확인
3. 하드코딩된 API URL, API 키, rate limit이 없는지 확인

---

## 2. GET /sourceData/stream

**동적 설정 요구사항**: GET /sourceData와 동일 (동일 서비스 사용)

**검증**: GET /sourceData (1.1) 체크리스트와 동일

---

## 3. POST /sourceData/cancel/{req_id}

**동적 설정 요구사항**: 없음

**검증**: 스트림 취소 기능이므로 동적 설정 검증 불필요

---

## 4. POST /test-post

**동적 설정 요구사항**: 없음

**검증**: 테스트용 엔드포인트이므로 동적 설정 검증 불필요

---

## 5. POST /setEventsTable

**동적 설정 요구사항**: 없음

**검증 대상 파일**:
- `backend/src/services/events_service.py`
- `backend/src/routers/events.py`

#### 체크리스트

- [ ] **5.1** 이 엔드포인트는 DB 메타데이터를 사용하여 `evt_%` 테이블을 자동 탐색하지만, 이는 동적 설정이 아닌 데이터 조회임을 확인
- [ ] **5.2** `config_lv3_targets` 테이블에서 sector/industry 값을 참조하지만, 이는 데이터 조회이지 설정 조회가 아님을 확인
- [ ] **5.3** 하드코딩된 설정 값이 없는지 확인

**검증 방법**: 
1. `events_service.py` 코드 확인
2. 하드코딩된 설정 값이 없는지 확인

---

## 6. POST /backfillEventsTable

### 6.1 quantitative/qualitative 메트릭 정의 동적 사용 ✅

**검증 대상 파일**:
- `backend/src/database/queries/metrics.py`
- `backend/src/services/metric_engine.py`
- `backend/src/services/valuation_service.py`

**지침 위치**: `1_guideline(function).ini` line 760, 799

#### 체크리스트

- [ ] **6.1.1** `valuation_service.py`의 `calculate_valuations()` 함수에서 `metrics.select_metric_definitions(pool)`을 호출하는지 확인
- [ ] **6.1.2** `metrics.py`의 `select_metric_definitions()` 함수가 `config_lv2_metric` 테이블을 조회하는지 확인
- [ ] **6.1.3** `select_metric_definitions()` 함수의 WHERE 절에 `domain LIKE 'quantitative-%' OR domain LIKE 'qualitative-%'` 조건이 있는지 확인
- [ ] **6.1.4** `metric_engine.py`의 `MetricCalculationEngine`이 DB에서 읽은 메트릭 정의를 사용하여 계산을 수행하는지 확인
- [ ] **6.1.5** `MetricCalculationEngine`이 formula, expression, aggregation을 하드코딩하지 않고 DB 정의에서 읽어 사용하는지 확인
- [ ] **6.1.6** 메트릭 계산 로직에 하드코딩된 공식(formula)이 없는지 확인 (모든 계산이 DB 정의 기반인지)

**검증 방법**:
1. `valuation_service.py` line 71 부근에서 `select_metric_definitions()` 호출 확인
2. `metrics.py` line 26-36 부근 SQL 쿼리 확인
3. `metric_engine.py`의 계산 로직이 DB 메트릭 정의를 참조하는지 확인

---

### 6.2 fillPriceTrend_dateRange 정책 동적 사용 ✅

**검증 대상 파일**:
- `backend/src/database/queries/policies.py`
- `backend/src/services/valuation_service.py`

**지침 위치**: `1_guideline(function).ini` line 935-937

#### 체크리스트

- [ ] **6.2.1** `valuation_service.py`의 `generate_price_trends()` 함수에서 `policies.get_price_trend_range_policy(pool)`을 호출하는지 확인
- [ ] **6.2.2** `policies.py`의 `get_price_trend_range_policy()` 함수가 `config_lv0_policy` 테이블을 조회하는지 확인
- [ ] **6.2.3** `get_price_trend_range_policy()` 함수의 WHERE 절에 `function = 'fillPriceTrend_dateRange'` 조건이 있는지 확인
- [ ] **6.2.4** `get_price_trend_range_policy()` 함수가 `policy` JSONB에서 `countStart`, `countEnd`를 추출하는지 확인
- [ ] **6.2.5** `generate_price_trends()` 함수에서 추출한 `countStart`, `countEnd` 값을 dayOffset 범위 계산에 사용하는지 확인
- [ ] **6.2.6** 하드코딩된 countStart/countEnd 값이 없는지 확인 (모든 값이 DB에서 읽히는지)

**검증 방법**:
1. `valuation_service.py` line 745-755 부근 코드 확인
2. `policies.py` line 67-93 부근 코드 확인
3. 하드코딩된 -14, 14 같은 값이 없는지 확인

---

### 6.3 priceEodOHLC_dateRange 정책 동적 사용 ❌ **미반영**

**검증 대상 파일**:
- `backend/src/database/queries/policies.py`
- `backend/src/services/valuation_service.py`

**지침 위치**: `1_guideline(function).ini` line 984-991

#### 체크리스트 (미반영 상태이므로 개선 후 검증)

- [ ] **6.3.1** `policies.py`에 `get_ohlc_date_range_policy()` 함수가 추가되었는지 확인
- [ ] **6.3.2** `get_ohlc_date_range_policy()` 함수가 `function = 'priceEodOHLC_dateRange'`로 조회하는지 확인
- [ ] **6.3.3** `get_ohlc_date_range_policy()` 함수가 `fillPriceTrend_dateRange`와 별개로 동작하는지 확인
- [ ] **6.3.4** `valuation_service.py`의 `generate_price_trends()` 함수에서 `get_price_trend_range_policy()`와 별도로 `get_ohlc_date_range_policy()`를 호출하는지 확인
- [ ] **6.3.5** OHLC API 호출 시 날짜 범위 계산에 `priceEodOHLC_dateRange` 정책의 countStart/countEnd를 사용하는지 확인
- [ ] **6.3.6** fromDate/toDate 계산이 지침 line 986-987에 따라 `fromDate = (min_event_date + countStart)`, `toDate = (max_event_date + countEnd)`로 수행되는지 확인
- [ ] **6.3.7** `fillPriceTrend_dateRange` 정책을 OHLC API 호출에 재사용하지 않는지 확인

**현재 상태**: ❌ **미반영** - `valuation_service.py` line 787-801에서 `fillPriceTrend_dateRange` 정책을 재사용 중

**검증 방법**:
1. `policies.py`에 `get_ohlc_date_range_policy()` 함수 존재 여부 확인
2. `valuation_service.py` line 787-801 부근 코드에서 별도 정책 사용 확인
3. `timedelta(days=count_start * 2)` 같은 하드코딩된 계산이 제거되었는지 확인

---

## 7. POST /setEventsTable/cancel/{req_id}

**동적 설정 요구사항**: 없음

**검증**: 스트림 취소 기능이므로 동적 설정 검증 불필요

---

## 8. POST /backfillEventsTable/cancel/{req_id}

**동적 설정 요구사항**: 없음

**검증**: 스트림 취소 기능이므로 동적 설정 검증 불필요

---

## 9. GET /dashboard/kpis

**동적 설정 요구사항**: 없음

**검증 대상 파일**:
- `backend/src/routers/dashboard.py`

#### 체크리스트

- [ ] **9.1** 이 엔드포인트는 `config_lv3_targets`, `config_lv3_market_holidays` 테이블에서 데이터를 조회하지만, 동적 설정을 사용하지 않음을 확인
- [ ] **9.2** 하드코딩된 설정 값이 없는지 확인

**검증 방법**: `dashboard.py` line 70-123 부근 코드 확인

---

## 10. GET /dashboard/performanceSummary

**동적 설정 요구사항**: 없음

**검증 대상 파일**:
- `backend/src/routers/dashboard.py`

#### 체크리스트

- [ ] **10.1** 이 엔드포인트는 `txn_events` 테이블에서 데이터를 조회하지만, 동적 설정을 사용하지 않음을 확인
- [ ] **10.2** 하드코딩된 설정 값이 없는지 확인

**검증 방법**: `dashboard.py` line 126-305 부근 코드 확인

---

## 11. GET /dashboard/dayOffsetMetrics

**동적 설정 요구사항**: 없음

**검증 대상 파일**:
- `backend/src/routers/dashboard.py`

#### 체크리스트

- [ ] **11.1** 이 엔드포인트는 `txn_events` 테이블에서 데이터를 조회하지만, 동적 설정을 사용하지 않음을 확인
- [ ] **11.2** 하드코딩된 설정 값이 없는지 확인

**검증 방법**: `dashboard.py` line 308-425 부근 코드 확인

---

## 12. GET /control/apiServices

**동적 설정 요구사항**: 없음 (조회 전용 엔드포인트)

**검증 대상 파일**:
- `backend/src/routers/control.py`

#### 체크리스트

- [ ] **12.1** 이 엔드포인트는 `config_lv1_api_service` 테이블에서 데이터를 조회하는 전용 엔드포인트임을 확인
- [ ] **12.2** 하드코딩된 설정 값이 없는지 확인

**검증 방법**: `control.py` line 90-129 부근 코드 확인

---

## 13. PUT /control/apiServices/{service}

**동적 설정 요구사항**: 없음 (설정 업데이트 엔드포인트)

**검증 대상 파일**:
- `backend/src/routers/control.py`

#### 체크리스트

- [ ] **13.1** 이 엔드포인트는 `config_lv1_api_service` 테이블의 설정을 업데이트하는 엔드포인트임을 확인
- [ ] **13.2** 하드코딩된 설정 값이 없는지 확인

**검증 방법**: `control.py` line 132-193 부근 코드 확인

---

## 14. GET /control/runtime

**동적 설정 요구사항**: 없음

**검증 대상 파일**:
- `backend/src/routers/control.py`

#### 체크리스트

- [ ] **14.1** 이 엔드포인트는 런타임 정보를 조회하는 전용 엔드포인트임을 확인
- [ ] **14.2** 하드코딩된 설정 값이 없는지 확인

**검증 방법**: `control.py` line 195-216 부근 코드 확인

---

## 15. GET /control/apiList

**동적 설정 요구사항**: 없음 (조회 전용 엔드포인트)

**검증 대상 파일**:
- `backend/src/routers/control.py`

#### 체크리스트

- [ ] **15.1** 이 엔드포인트는 `config_lv1_api_list` 테이블에서 데이터를 조회하는 전용 엔드포인트임을 확인
- [ ] **15.2** 하드코딩된 설정 값이 없는지 확인

**검증 방법**: `control.py` line 219-269 부근 코드 확인

---

## 16. GET /control/metrics

**동적 설정 요구사항**: 없음 (조회 전용 엔드포인트)

**검증 대상 파일**:
- `backend/src/routers/control.py`

#### 체크리스트

- [ ] **16.1** 이 엔드포인트는 `config_lv2_metric` 테이블에서 데이터를 조회하는 전용 엔드포인트임을 확인
- [ ] **16.2** 하드코딩된 설정 값이 없는지 확인

**검증 방법**: `control.py` line 272-338 부근 코드 확인

---

## 17. GET /control/metricTransforms

**동적 설정 요구사항**: 없음 (조회 전용 엔드포인트)

**검증 대상 파일**:
- `backend/src/routers/control.py`

#### 체크리스트

- [ ] **17.1** 이 엔드포인트는 메트릭 변환 정보를 조회하는 전용 엔드포인트임을 확인
- [ ] **17.2** 하드코딩된 설정 값이 없는지 확인

**검증 방법**: `control.py` line 339 이후 코드 확인

---

## 18. POST /fillAnalyst

### 18.1 fillPriceTrend_dateRange 정책 동적 사용 ✅

**검증 대상 파일**:
- `backend/src/database/queries/policies.py`
- `backend/src/services/analyst_service.py`

**지침 위치**: `1_guideline(function).ini` line 1084-1085, 1144-1145

#### 체크리스트

- [ ] **18.1.1** `analyst_service.py`의 `aggregate_analyst_performance()` 함수에서 `policies.get_price_trend_range_policy(pool)`을 호출하는지 확인
- [ ] **18.1.2** 정책 미존재 시 `POLICY_NOT_FOUND` 에러를 반환하는지 확인
- [ ] **18.1.3** 추출한 `countStart`, `countEnd` 값을 priceTrend 범위 검증에 사용하는지 확인
- [ ] **18.1.4** 추출한 `countStart`, `countEnd` 값을 성과 집계 범위(dayOffset)로 사용하는지 확인
- [ ] **18.1.5** `validate_price_trend()` 함수에서 정책 기반 범위 검증을 수행하는지 확인

**검증 방법**:
1. `analyst_service.py` line 44-62 부근 코드 확인
2. `analyst_service.py` line 157 부근에서 `validate_price_trend()` 호출 확인
3. `analyst_service.py` line 188 부근에서 dayOffset 범위가 정책 기반인지 확인

---

### 18.2 internal(qual) 메트릭 정의 동적 사용 ❌ **미반영**

**검증 대상 파일**:
- `backend/src/database/queries/metrics.py`
- `backend/src/services/analyst_service.py`
- `backend/src/database/queries/analyst.py`

**지침 위치**: `1_guideline(function).ini` line 1118-1120, 1161-1184

#### 체크리스트 (미반영 상태이므로 개선 후 검증)

- [ ] **18.2.1** `metrics.py`에 `select_internal_qual_metrics()` 함수가 추가되었는지 확인
- [ ] **18.2.2** `select_internal_qual_metrics()` 함수가 `domain = 'internal(qual)'` 및 `base_metric_id = 'priceTrendReturnSeries'` 조건으로 조회하는지 확인
- [ ] **18.2.3** `analyst_service.py`의 `aggregate_analyst_performance()` 함수에서 `select_internal_qual_metrics()`를 호출하는지 확인
- [ ] **18.2.4** 메트릭 정의 미존재 시 `METRIC_NOT_FOUND` 에러를 반환하는지 확인
- [ ] **18.2.5** 통계 계산이 DB 메트릭 정의를 기반으로 수행되는지 확인 (하드코딩된 `calculate_statistics()` 사용 안 함)
- [ ] **18.2.6** Mean, Median, quartile, stddev 등이 DB 정의 기반으로 계산되는지 확인
- [ ] **18.2.7** performance 필드 매핑이 지침 line 1171-1178에 따라 수행되는지 확인:
  - Mean ← returnMeanByDayOffset
  - Median ← returnMedianByDayOffset
  - 1stQuartile ← returnFirstQuartileByDayOffset
  - 3rdQuartile ← returnThirdQuartileByDayOffset
  - InterquartileRange ← returnIQRByDayOffset
  - standardDeviation ← returnStdDevByDayOffset
  - count ← returnCountByDayOffset
- [ ] **18.2.8** `analyst.py`의 `calculate_statistics()` 함수가 제거되었거나 fallback으로만 사용되는지 확인
- [ ] **18.2.9** 하드코딩된 통계 계산 로직이 없는지 확인

**현재 상태**: ❌ **미반영** - `analyst_service.py` line 186-191에서 하드코딩된 `calculate_statistics()` 사용

**검증 방법**:
1. `metrics.py`에 `select_internal_qual_metrics()` 함수 존재 여부 확인
2. `analyst_service.py` line 186-191 부근에서 DB 메트릭 정의 기반 계산 확인
3. `analyst.py`의 `calculate_statistics()` 함수 사용 여부 확인
4. statistics 모듈을 직접 import하여 사용하는 부분이 있는지 확인

---

## 19. GET /conditionGroups/columns

**동적 설정 요구사항**: 없음

**검증 대상 파일**:
- `backend/src/routers/condition_group.py`

#### 체크리스트

- [ ] **19.1** 이 엔드포인트는 하드코딩된 컬럼 목록을 반환하는 전용 엔드포인트임을 확인
- [ ] **19.2** 지침에서 동적 설정 요구사항이 없는지 확인

**검증 방법**: `condition_group.py` line 50-58 부근 코드 확인

---

## 20. GET /conditionGroups/values

**동적 설정 요구사항**: 없음

**검증 대상 파일**:
- `backend/src/routers/condition_group.py`

#### 체크리스트

- [ ] **20.1** 이 엔드포인트는 `txn_events` 테이블에서 데이터를 조회하지만, 동적 설정을 사용하지 않음을 확인
- [ ] **20.2** 하드코딩된 설정 값이 없는지 확인

**검증 방법**: `condition_group.py` line 61-105 부근 코드 확인

---

## 21. GET /conditionGroups

**동적 설정 요구사항**: 없음

**검증 대상 파일**:
- `backend/src/routers/condition_group.py`

#### 체크리스트

- [ ] **21.1** 이 엔드포인트는 `txn_events` 테이블에서 데이터를 조회하지만, 동적 설정을 사용하지 않음을 확인
- [ ] **21.2** 하드코딩된 설정 값이 없는지 확인

**검증 방법**: `condition_group.py` line 108-170 부근 코드 확인

---

## 22. POST /conditionGroups

**동적 설정 요구사항**: 없음

**검증 대상 파일**:
- `backend/src/routers/condition_group.py`

#### 체크리스트

- [ ] **22.1** 이 엔드포인트는 `txn_events` 테이블을 업데이트하는 엔드포인트이지만, 동적 설정을 사용하지 않음을 확인
- [ ] **22.2** 하드코딩된 설정 값이 없는지 확인

**검증 방법**: `condition_group.py` line 173-253 부근 코드 확인

---

## 23. DELETE /conditionGroups/{name}

**동적 설정 요구사항**: 없음

**검증 대상 파일**:
- `backend/src/routers/condition_group.py`

#### 체크리스트

- [ ] **23.1** 이 엔드포인트는 `txn_events` 테이블을 업데이트하는 엔드포인트이지만, 동적 설정을 사용하지 않음을 확인
- [ ] **23.2** 하드코딩된 설정 값이 없는지 확인

**검증 방법**: `condition_group.py` line 256-326 부근 코드 확인

---

## 전체 검증 요약

### 동적 설정이 필요한 엔드포인트 (6개 항목)

#### 반영된 항목 (4개)
- ✅ GET /sourceData - API 설정 동적 사용
- ✅ POST /backfillEventsTable - quantitative/qualitative 메트릭 정의
- ✅ POST /backfillEventsTable - fillPriceTrend_dateRange 정책
- ✅ POST /fillAnalyst - fillPriceTrend_dateRange 정책

#### 미반영 항목 (2개)
- ❌ POST /backfillEventsTable - priceEodOHLC_dateRange 정책
- ❌ POST /fillAnalyst - internal(qual) 메트릭 정의

### 동적 설정이 불필요한 엔드포인트 (17개)
- GET /sourceData/stream
- POST /sourceData/cancel/{req_id}
- POST /test-post
- POST /setEventsTable
- POST /setEventsTable/cancel/{req_id}
- POST /backfillEventsTable/cancel/{req_id}
- GET /dashboard/kpis
- GET /dashboard/performanceSummary
- GET /dashboard/dayOffsetMetrics
- GET /control/apiServices
- PUT /control/apiServices/{service}
- GET /control/runtime
- GET /control/apiList
- GET /control/metrics
- GET /control/metricTransforms
- GET /conditionGroups/columns
- GET /conditionGroups/values
- GET /conditionGroups
- POST /conditionGroups
- DELETE /conditionGroups/{name}

---

## 검증 실행 순서

1. **반영된 항목 검증** (체크리스트 1.1, 6.1, 6.2, 18.1)
   - 각 항목의 체크리스트를 순서대로 검증
   - 모든 체크박스가 체크되면 해당 항목은 정상적으로 반영된 것으로 확인

2. **미반영 항목 개선 후 검증** (체크리스트 6.3, 18.2)
   - 먼저 개선 방안에 따라 코드 수정
   - 수정 후 체크리스트 6.3, 18.2를 검증
   - 모든 체크박스가 체크되면 해당 항목은 정상적으로 반영된 것으로 확인

3. **동적 설정 불필요 엔드포인트 확인** (체크리스트 2-5, 7-8, 9-17, 19-23)
   - 각 엔드포인트가 실제로 동적 설정을 사용하지 않음을 확인
   - 하드코딩된 설정 값이 없는지 확인

4. **최종 확인**
   - 모든 체크리스트 항목이 체크되었는지 확인
   - `DYNAMIC_CONFIG_CHECK.md`의 상태 표시 업데이트

---

## 검증 시 주의사항

1. **하드코딩 값 확인**: 각 파일에서 하드코딩된 값(예: -14, 14, API URL, API 키 등)이 없는지 주의 깊게 확인
2. **DB 쿼리 확인**: 모든 설정이 실제로 DB 테이블에서 조회되는지 SQL 쿼리 확인
3. **함수 호출 확인**: 지침에서 요구하는 함수가 실제로 호출되는지 호출 흐름 추적
4. **에러 처리 확인**: 정책/메트릭 미존재 시 적절한 에러를 반환하는지 확인
5. **별도 정책 확인**: priceEodOHLC_dateRange와 fillPriceTrend_dateRange가 별도로 관리되는지 확인
6. **조회 전용 엔드포인트**: `/control/*`, `/dashboard/*` 등은 조회 전용이므로 동적 설정 검증 불필요
