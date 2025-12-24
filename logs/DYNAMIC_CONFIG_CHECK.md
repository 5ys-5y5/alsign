# 동적 설정 항목 점검 결과

본 문서는 `1_guideline(function).ini` 지침에서 요구하는 하드 코딩 없이 동적으로 DB에서 값을 읽어 사용해야 하는 항목들을 endpoint별로 정리하고, 각 항목의 지침 위치와 현재 구현 상태를 기록합니다.

---

## 1. GET /sourceData

### 1.1 API 설정 동적 사용 ✅

**지침 위치**: `1_guideline(function).ini` line 403-433

**지침 내용**:
- line 404-405: "config_lv1_api_list 테이블에서 호출되는 모든 API는 호출 전에 호출을 최소화할 수 있는지 반드시 검토할 것"
- line 425-428: "config_lv1_api_list 테이블에서 호출되는 모든 API는 분당 최대 호출량을 사용할 것. Rate Limit 기준: config_lv1_api_list.api_service → config_lv1_api_service.usagePerMin"

**요구사항**:
- API URL, 스키마 매핑은 `config_lv1_api_list` 테이블에서 동적으로 읽어야 함
- API 키, Rate Limit은 `config_lv1_api_service` 테이블에서 동적으로 읽어야 함
- 모든 API 호출은 DB 설정 기반으로 동작해야 함

**현재 구현 상태**: ✅ **반영됨**

**구현 위치**:
- `backend/src/services/external_api.py` - FMPAPIClient.call_api()
- `backend/src/database/queries/api_config.py` - get_api_config_by_id(), get_api_service_config()

**흐름**:
1. `FMPAPIClient.call_api(api_id)` 호출 시
2. `api_config.get_api_config_by_id(pool, api_id)`로 `config_lv1_api_list`에서 API 설정 조회
3. `api_config.get_api_service_config(pool, service_name)`로 `config_lv1_api_service`에서 API 키, rate limit 조회
4. DB에서 읽은 설정으로 API URL 구성 및 호출

---

## 2. POST /backfillEventsTable

### 2.1 quantitative/qualitative 메트릭 정의 동적 사용 ✅

**지침 위치**: `1_guideline(function).ini` line 760, 799

**지침 내용**:
- line 760: "value_quantitative: [table.metric] 테이블의 domain 컬럼이 quantitative로 시작하는 경우에 대해 값을 계산하여..."
- line 799: "value_qualitative: [table.metric] 테이블의 domain 컬럼이 qualitative로 시작하는 경우에 대해 값을 계산하여..."

**요구사항**:
- `config_lv2_metric` 테이블에서 `domain LIKE 'quantitative-%'` 또는 `domain LIKE 'qualitative-%'` 메트릭 정의를 동적으로 읽어야 함
- formula, expression, aggregation 규칙을 DB에서 읽어 동적으로 계산해야 함
- 계산 로직을 하드코딩하지 않고 DB 정의를 해석하여 수행해야 함

**현재 구현 상태**: ✅ **반영됨**

**구현 위치**:
- `backend/src/database/queries/metrics.py` - select_metric_definitions()
- `backend/src/services/metric_engine.py` - MetricCalculationEngine
- `backend/src/services/valuation_service.py` - calculate_valuations()

**흐름**:
1. `metrics.select_metric_definitions(pool)` 호출
2. `config_lv2_metric` 테이블에서 `domain LIKE 'quantitative-%' OR domain LIKE 'qualitative-%'` 조회
3. MetricCalculationEngine에 전달하여 의존성 그래프 구성
4. DB에서 읽은 formula/expression/aggregation 규칙에 따라 계산 수행

---

### 2.2 fillPriceTrend_dateRange 정책 동적 사용 ✅

**지침 위치**: `1_guideline(function).ini` line 935-937

**지침 내용**:
- line 935: "config_lv0_policy.function 값이 fillPriceTrend_dateRange인 행의 policy 컬럼에 있는 countStart 값과 countEnd 값을 각각 event_date에 더한 값이 수집 대상 범위 기간이 됨"
- line 936: "event_date=2025-12-09, countStart=-14, countEnd=14일때 수집 기간 범위는 2025-11-19~2025-12-29"
- line 937: "countStart와 countEnd는 거래일을 의미함"

**요구사항**:
- priceTrend 생성 시 dayOffset 범위는 `config_lv0_policy` 테이블의 `function='fillPriceTrend_dateRange'` 정책에서 동적으로 읽어야 함
- `policy` JSONB에서 `countStart`, `countEnd` 값을 추출하여 사용해야 함

**현재 구현 상태**: ✅ **반영됨**

**구현 위치**:
- `backend/src/database/queries/policies.py` - get_price_trend_range_policy()
- `backend/src/services/valuation_service.py` - generate_price_trends() (line 745-755)

**흐름**:
1. `policies.get_price_trend_range_policy(pool)` 호출
2. `config_lv0_policy` 테이블에서 `function='fillPriceTrend_dateRange'` 조회
3. `policy` JSONB에서 `countStart`, `countEnd` 추출
4. priceTrend 생성 시 dayOffset 범위로 사용

---

### 2.3 priceEodOHLC_dateRange 정책 동적 사용 ⚠️ **미반영**

**지침 위치**: `1_guideline(function).ini` line 984-991

**지침 내용**:
- line 984-985: "조회 기간 산출 (policy 기반; 강제) - config_lv0_policy.function 값이 priceEodOHLC_dateRange 인 행의 policy 컬럼에 있는 countStart 값과 countEnd 값을 unique ticker가 가진 event_date 범위(min/max)에 적용하여 OHLC 수집 기간(from/to)을 결정한다."
- line 986-987: "fromDate = (min_event_date + countStart), toDate = (max_event_date + countEnd)"
- line 988: "countStart와 countEnd는 달력일(day) 기준 오프셋을 의미한다."

**요구사항**:
- OHLC API 호출 시 날짜 범위는 `config_lv0_policy` 테이블의 `function='priceEodOHLC_dateRange'` 정책에서 동적으로 읽어야 함
- `fillPriceTrend_dateRange` 정책과는 별개의 정책을 사용해야 함
- unique ticker의 event_date 범위(min/max)에 정책의 countStart/countEnd를 적용하여 fromDate/toDate 계산

**현재 구현 상태**: ❌ **미반영**

**문제점**:
- `fillPriceTrend_dateRange` 정책의 countStart/countEnd를 재사용 중
- `priceEodOHLC_dateRange` 정책을 별도로 조회하지 않음
- 두 정책의 목적이 다름:
  - `fillPriceTrend_dateRange`: priceTrend 배열의 dayOffset 범위 (거래일 기준)
  - `priceEodOHLC_dateRange`: OHLC API 호출 기간 (달력일 기준)

**현재 구현 위치**:
- `backend/src/services/valuation_service.py` line 787-801
- 하드코딩된 대략적 계산: `fetch_start = min_date + timedelta(days=count_start * 2)`

**수정 필요**:
- `policies.get_ohlc_fetch_policy()` 또는 새로운 함수 `get_ohlc_date_range_policy()` 구현
- `priceEodOHLC_dateRange` 정책을 별도로 조회하여 countStart/countEnd 사용
- line 985의 지침대로 fromDate/toDate 계산 로직 적용

---

## 3. POST /fillAnalyst

### 3.1 fillPriceTrend_dateRange 정책 동적 사용 ✅

**지침 위치**: `1_guideline(function).ini` line 1084-1085, 1144-1145

**지침 내용**:
- line 1084: "정책 존재 여부 - `config_lv0_policy.function = fillPriceTrend_dateRange` 인 정책이 존재해야 함"
- line 1144-1145: "performance 컬럼 스키마 생성/점검 - `config_lv0_policy.function = fillPriceTrend_dateRange` 인 행의 `policy.countStart`, `policy.countEnd`를 성과 집계 범위(dayOffset)로 사용"

**요구사항**:
- fillAnalyst 실행 전/중에 `config_lv0_policy.function='fillPriceTrend_dateRange'` 정책 존재 여부 검증
- `policy.countStart`, `policy.countEnd`를 성과 집계 범위(dayOffset)로 사용

**현재 구현 상태**: ✅ **반영됨**

**구현 위치**:
- `backend/src/database/queries/policies.py` - get_price_trend_range_policy()
- `backend/src/services/analyst_service.py` - aggregate_analyst_performance() (line 44-62)

**흐름**:
1. `policies.get_price_trend_range_policy(pool)` 호출
2. 정책 미존재 시 `POLICY_NOT_FOUND` 에러 반환
3. `countStart`, `countEnd` 추출하여 priceTrend 범위 검증 및 성과 집계 범위로 사용

---

### 3.2 internal(qual) 메트릭 정의 동적 사용 ⚠️ **미반영**

**지침 위치**: `1_guideline(function).ini` line 1118-1120, 1161-1184

**지침 내용**:
- line 1118-1120: "분석 메트릭 정의 존재 여부 - `[table.metric].domain = internal(qual)` 에 성과 계산에 필요한 메트릭 정의가 존재해야 함. 미존재 시 에러: `METRIC_NOT_FOUND`"
- line 1161-1164: "internal(qual) 메트릭 규칙에 따라 통계 계산 및 performance 채움 (DB 정의 권위; 강제) - 계산 로직 하드코딩 금지: Mean/Median/p25/p75/stddev/CI/proficiency 등을 코드에 직접 구현하지 않는다. 반드시 `public.[table.metric]` 정의를 해석하여 산출한다."
- line 1165-1166: "적용 대상(강제): `public.[table.metric].domain = 'internal(qual)'`"
- line 1169-1170: "메트릭 선택 규칙(강제): `base_metric_id = 'priceTrendReturnSeries'` 인 메트릭만 사용"
- line 1171-1178: "performance 필드 매핑(강제): Mean ← returnMeanByDayOffset, Median ← returnMedianByDayOffset, 1stQuartile ← returnFirstQuartileByDayOffset, 3rdQuartile ← returnThirdQuartileByDayOffset, InterquartileRange ← returnIQRByDayOffset, standardDeviation ← returnStdDevByDayOffset, count ← returnCountByDayOffset"

**요구사항**:
- `config_lv2_metric` 테이블에서 `domain='internal(qual)'` 및 `base_metric_id='priceTrendReturnSeries'`인 메트릭 정의를 동적으로 읽어야 함
- Mean, Median, p25, p75, stddev, CI, proficiency 등의 통계 계산 로직을 하드코딩하지 않고 DB 정의를 해석하여 수행해야 함
- performance 필드 매핑은 지침 line 1171-1178에 정의된 대로 DB 메트릭 정의에 따라 동적으로 수행해야 함

**현재 구현 상태**: ❌ **미반영**

**문제점**:
- 하드코딩된 `calculate_statistics()` 함수 사용
- DB에서 internal(qual) 메트릭 정의를 읽지 않음
- 통계 계산 로직이 코드에 직접 구현되어 있음

**현재 구현 위치**:
- `backend/src/services/analyst_service.py` line 186-191: `stats = analyst.calculate_statistics(returns)`
- `backend/src/database/queries/analyst.py` line 134-190: 하드코딩된 통계 계산 함수

**수정 필요**:
- `config_lv2_metric`에서 `domain='internal(qual)'` 및 `base_metric_id='priceTrendReturnSeries'` 메트릭 조회
- MetricCalculationEngine 또는 별도 엔진으로 DB 정의 기반 통계 계산 수행
- line 1171-1178의 필드 매핑 규칙 적용
- `calculate_statistics()` 함수를 제거하거나, DB 메트릭 정의가 없을 때만 fallback으로 사용

---

## 4. POST /setEventsTable

**동적 설정 요구사항**: 없음

이 endpoint는 DB 메타데이터를 사용하여 `evt_%` 테이블을 자동 탐색하고, `config_lv3_targets` 테이블의 sector/industry 값을 참조하지만, 이는 동적 설정이라기보다는 데이터 조회의 범주입니다.

---

## 5. 요약 표

| Endpoint | 동적 설정 항목 | 지침 위치 | 현재 상태 | 비고 |
|----------|---------------|-----------|----------|------|
| GET /sourceData | API 설정 (config_lv1_api_list, config_lv1_api_service) | line 404-405, 425-428 | ✅ 반영됨 | external_api.py |
| POST /backfillEventsTable | quantitative/qualitative 메트릭 정의 (config_lv2_metric) | line 760, 799 | ✅ 반영됨 | metric_engine.py |
| POST /backfillEventsTable | fillPriceTrend_dateRange 정책 (config_lv0_policy) | line 935-937 | ✅ 반영됨 | policies.py |
| POST /backfillEventsTable | priceEodOHLC_dateRange 정책 (config_lv0_policy) | line 984-991 | ❌ **미반영** | fillPriceTrend_dateRange 재사용 중 |
| POST /fillAnalyst | fillPriceTrend_dateRange 정책 (config_lv0_policy) | line 1084-1085, 1144-1145 | ✅ 반영됨 | policies.py |
| POST /fillAnalyst | internal(qual) 메트릭 정의 (config_lv2_metric) | line 1118-1120, 1161-1184 | ❌ **미반영** | 하드코딩된 calculate_statistics 사용 |

---

## 6. 미반영 항목 상세 개선 방안

### 6.1 priceEodOHLC_dateRange 정책 미사용 (POST /backfillEventsTable)

**수정 위치**: `backend/src/services/valuation_service.py`

**수정 내용**:
1. `backend/src/database/queries/policies.py`에 `get_ohlc_date_range_policy()` 함수 추가
   ```python
   async def get_ohlc_date_range_policy(pool: asyncpg.Pool) -> Dict[str, int]:
       """
       Get OHLC API fetch date range policy (countStart, countEnd).
       Uses priceEodOHLC_dateRange policy, separate from fillPriceTrend_dateRange.
       """
       policy = await select_policy(pool, 'priceEodOHLC_dateRange')
       if not policy:
           raise ValueError("Policy 'priceEodOHLC_dateRange' not found in config_lv0_policy")
       policy_config = policy['policy']
       if 'countStart' not in policy_config or 'countEnd' not in policy_config:
           raise ValueError("Policy 'priceEodOHLC_dateRange' missing countStart or countEnd")
       return {
           'countStart': int(policy_config['countStart']),
           'countEnd': int(policy_config['countEnd'])
       }
   ```

2. `generate_price_trends()` 함수에서 별도 정책 사용
   ```python
   # line 745 부근
   ohlc_policy = await policies.get_ohlc_date_range_policy(pool)
   ohlc_count_start = ohlc_policy['countStart']
   ohlc_count_end = ohlc_policy['countEnd']
   
   # line 787-801 부근
   # 지침 line 986-987 적용
   fetch_start = min_date + timedelta(days=ohlc_count_start)
   fetch_end = max_date + timedelta(days=ohlc_count_end)
   ```

**지침 준수**: `1_guideline(function).ini` line 984-991

---

### 6.2 internal(qual) 메트릭 동적 사용 미구현 (POST /fillAnalyst)

**수정 위치**: `backend/src/services/analyst_service.py`

**수정 내용**:
1. internal(qual) 메트릭 정의 조회
   ```python
   # aggregate_analyst_performance() 함수 내부
   # line 64 부근 (정책 로드 이후)
   internal_metrics = await metrics.select_internal_qual_metrics(pool)
   if not internal_metrics:
       return {
           'error': 'METRIC_NOT_FOUND',
           'errorCode': 'METRIC_NOT_FOUND',
           # ...
       }
   ```

2. `backend/src/database/queries/metrics.py`에 조회 함수 추가
   ```python
   async def select_internal_qual_metrics(pool: asyncpg.Pool) -> List[Dict[str, Any]]:
       """Select internal(qual) metrics for analyst performance calculation."""
       async with pool.acquire() as conn:
           rows = await conn.fetch("""
               SELECT id, domain, expression, description,
                      source, base_metric_id, aggregation_kind, 
                      aggregation_params, response_key
               FROM config_lv2_metric
               WHERE domain = 'internal(qual)'
                 AND base_metric_id = 'priceTrendReturnSeries'
               ORDER BY id
           """)
           return [dict(row) for row in rows]
   ```

3. DB 정의 기반 통계 계산 엔진 구현
   - MetricCalculationEngine 확장 또는 별도 엔진 사용
   - line 1171-1178의 필드 매핑 규칙 적용
   - Mean, Median, quartile, stddev 등을 DB 정의 기반으로 계산

4. 하드코딩된 함수 제거
   - `analyst.calculate_statistics()` 함수 제거 또는 fallback으로만 사용
   - DB 메트릭 정의가 없을 때만 경고와 함께 사용

**지침 준수**: `1_guideline(function).ini` line 1118-1120, 1161-1184
