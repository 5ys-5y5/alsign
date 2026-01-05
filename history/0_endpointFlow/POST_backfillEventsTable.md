# POST /backfillEventsTable 엔드포인트 흐름

> **목적**: txn_events 테이블의 이벤트들에 대해 valuation metrics를 계산하고 저장
>
> **최종 업데이트**: 2026-01-05 (I-43 설계 - txn_price_trend 테이블 분리, price_trend JSONB → 별도 테이블)
> **이전 업데이트**: 2026-01-02 (I-41 Part 1+2+3 - priceQuantitative 메트릭 + 선택적 메트릭 업데이트 + API 단순화)

---

## 1. 엔드포인트 개요

| 항목 | 값 |
|------|-----|
| **경로** | `POST /backfillEventsTable` |
| **라우터 파일** | `backend/src/routers/events.py` |
| **서비스 파일** | `backend/src/services/valuation_service.py` |
| **DB 쿼리 파일** | `backend/src/database/queries/metrics.py` |
| **엔진 파일** | `backend/src/services/metric_engine.py` |

### 쿼리 파라미터

| 파라미터 | 타입 | 기본값 | 설명 |
|---------|------|--------|------|
| `overwrite` | boolean | false | NULL만 채우기(false) vs 덮어쓰기(true). metrics 지정 시 해당 메트릭에만 적용, 미지정 시 전체 필드에 적용 (I-41 Part 3) |
| `from` | date | null | 이벤트 시작 날짜 필터 (YYYY-MM-DD) |
| `to` | date | null | 이벤트 종료 날짜 필터 (YYYY-MM-DD) |
| `tickers` | string | null | 티커 필터 (쉼표 구분, 예: "AAPL,MSFT") |
| `calcFairValue` | boolean | true | [DEPRECATED - I-41] 업종 평균 적정가 계산 여부 → metrics=priceQuantitative 사용 권장 |
| **`metrics`** | **string** | **null** | **업데이트할 메트릭 ID 리스트 (쉼표 구분, 예: "priceQuantitative,PER,PBR") (I-41 Part 2)** |

**사용법 예시**:
```bash
# 1. 기본: 모든 메트릭 계산 (NULL 값만 채우기)
POST /backfillEventsTable

# 2. 특정 메트릭만 NULL 값 채우기 (I-41)
POST /backfillEventsTable?metrics=priceQuantitative

# 3. 특정 메트릭 강제 재계산 (I-41 Part 3)
POST /backfillEventsTable?metrics=priceQuantitative&overwrite=true

# 4. 여러 메트릭 동시 업데이트 (I-41)
POST /backfillEventsTable?metrics=priceQuantitative,PER,PBR&overwrite=false

# 5. 날짜 범위 + 티커 + 선택적 메트릭 (I-41)
POST /backfillEventsTable?from=2024-01-01&to=2024-12-31&tickers=AAPL&metrics=priceQuantitative&overwrite=true
```

---

## 2. 호출 흐름도

```
[Client]
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ routers/events.py:105-191                                       │
│ @router.post("/backfillEventsTable")                           │
│ async def backfill_events_table(...)                           │
│   └─► valuation_service.calculate_valuations(...)              │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ services/valuation_service.py:406-808                          │
│ async def calculate_valuations(...)                            │
│   ├─► Phase 1: Load metric definitions                         │
│   ├─► Phase 2: Load events from DB                             │
│   ├─► Phase 3: Group events by ticker                          │
│   ├─► Phase 4: Process tickers in parallel                     │
│   │     └─► process_ticker_batch() × N tickers                 │
│   └─► Phase 5: Generate price trends                           │
│         └─► generate_price_trends()                            │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ services/valuation_service.py:39-403                           │
│ async def process_ticker_batch(...)                            │
│   ├─► Fetch API data ONCE for ticker                           │
│   │     ├─► FMPAPIClient.call_api() × required_apis            │
│   │     └─► fmp-price-target-consensus (consensus 캐시)         │
│   ├─► For each event in ticker:                                │
│   │     ├─► calculate_quantitative_metrics_fast()              │
│   │     ├─► calculate_qualitative_metrics_fast()               │
│   │     └─► calculate_position_disparity()                     │
│   └─► Batch update DB                                          │
│         └─► metrics.batch_update_event_valuations()            │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. 상세 흐름 설명

### Phase 1: Load Metric Definitions
**위치**: `valuation_service.py:450-471`

```
calculate_valuations()
    │
    ├─► db_pool.get_pool()
    │     DB 연결 풀 획득
    │
    └─► metrics.select_metric_definitions(pool)
          ├─► 파일: database/queries/metrics.py:15-89
          ├─► SQL: SELECT * FROM config_lv2_metric WHERE ...
          └─► 반환: Dict[str, List[Dict]] (domain별 메트릭 정의)
               예: {'valuation': [PER, PBR, PSR...], 'profitability': [...]}
```

### Phase 2: Load Events from DB
**위치**: `valuation_service.py:488-530`

```
calculate_valuations()
    │
    └─► metrics.select_events_for_valuation(pool, from_date, to_date, tickers)
          ├─► 파일: database/queries/metrics.py:91-145
          ├─► SQL: SELECT ticker, event_date, source, source_id FROM txn_events WHERE ...
          └─► 반환: List[Dict] (처리할 이벤트 목록)
               예: [{'ticker': 'AAPL', 'event_date': '2024-01-15', 'source': 'consensus', ...}]
```

### Phase 3: Group Events by Ticker
**위치**: `valuation_service.py:554-556`

```
calculate_valuations()
    │
    └─► group_events_by_ticker(events)
          ├─► 파일: valuation_service.py:21-36
          ├─► 로직: defaultdict(list)로 ticker별 그룹화
          └─► 반환: Dict[str, List[Dict]]
               예: {'AAPL': [event1, event2], 'GOOGL': [event3, event4]}
```

### Phase 4: Process Tickers in Parallel
**위치**: `valuation_service.py:576-688`

```
calculate_valuations()
    │
    ├─► asyncio.Semaphore(TICKER_CONCURRENCY=10)
    │     동시 처리 제한 (10개 티커)
    │
    ├─► For each ticker in ticker_groups:
    │     └─► process_ticker_with_semaphore(ticker, events)
    │           └─► process_ticker_batch(pool, ticker, events, ...)
    │
    └─► asyncio.gather(*tasks)
          모든 티커 병렬 처리 완료 대기
```

#### process_ticker_batch() 상세
**위치**: `valuation_service.py:39-403`

```
process_ticker_batch(pool, ticker, ticker_events, metrics_by_domain, ...)
    │
    ├─► [1] Transform 정의 로드
    │     └─► metrics.select_metric_transforms(pool)
    │           ├─► SQL: SELECT * FROM config_lv2_metric_transform
    │           └─► 반환: Dict (aggregation 함수 정의)
    │
    ├─► [2] MetricCalculationEngine 초기화
    │     └─► MetricCalculationEngine(metrics_by_domain, transforms)
    │           └─► engine.get_required_apis()
    │                 반환: Set[str] {'fmp-income-statement', 'fmp-balance-sheet', ...}
    │
    ├─► [3] API 데이터 ONCE 호출
    │     └─► FMPAPIClient.call_api() × len(required_apis)
    │           │
    │           ├─► fmp-income-statement (limit=100, period=quarter)
    │           ├─► fmp-balance-sheet-statement (limit=100, period=quarter)
    │           ├─► fmp-cash-flow-statement (limit=100, period=quarter)
    │           ├─► fmp-historical-price-eod-full (fromDate=2000-01-01, toDate=now)
    │           └─► fmp-quote (현재 시점 스냅샷) ⚠️ I-25 이슈
    │
    │     └─► ticker_api_cache에 저장
    │
    ├─► [4] Consensus 데이터 ONCE 호출
    │     └─► FMPAPIClient.call_api('fmp-price-target-consensus', {'ticker': ticker})
    │           └─► consensus_summary_cache에 저장 ⚠️ I-26 이슈
    │
    ├─► [5] 각 이벤트 처리
    │     └─► For each event in ticker_events:
    │           │
    │           ├─► calculate_quantitative_metrics_fast(ticker, event_date, api_cache, engine, ...)
    │           │     ├─► event_date 기준 API 데이터 필터링
    │           │     ├─► engine.calculate_all(filtered_data, target_domains)
    │           │     └─► 반환: {'status': 'success', 'value': {...}}
    │           │
    │           ├─► calculate_qualitative_metrics_fast(pool, ticker, event_date, source, source_id)
   │           │     ├─► metrics.select_consensus_data(pool, ticker, event_date, source_id)
   │           │     │     └─► target_summary 컬럼 포함 (I-31)
   │           │     ├─► consensusSignal 구성 (evt_consensus에서 추출)
   │           │     ├─► targetMedian, targetSummary 추가 (evt_consensus.target_summary에서 읽기)
   │           │     └─► 반환: {'status': 'success', 'value': {...}, 'currentPrice': ...}
    │           │
    │           └─► calculate_position_disparity(quant_value, current_price)
    │                 └─► 반환: (position, disparity)
    │
    └─► [6] DB 배치 업데이트
          └─► metrics.batch_update_event_valuations(pool, batch_updates, overwrite)
                ├─► SQL: UPDATE txn_events SET ... FROM UNNEST(...) WHERE ...
                └─► 반환: updated_count
```

### Phase 5: Generate Price Trends
**위치**: `valuation_service.py:741-785, 1468-1786`

```
calculate_valuations()
    │
    └─► generate_price_trends(from_date, to_date, tickers)
          │
          ├─► [1] 정책 로드
          │     ├─► policies.get_price_trend_range_policy(pool)
          │     │     └─► fillPriceTrend_dateRange: countStart=-14, countEnd=+14
          │     └─► policies.get_ohlc_date_range_policy(pool)
          │           └─► priceEodOHLC_dateRange: 별도 정책
          │
          ├─► [2] OHLC 날짜 범위 계산
          │     └─► For each ticker:
          │           fromDate = min(event_dates) + countStart*2 (calendar days)
          │           toDate = max(event_dates) + countEnd (calendar days)
          │
          ├─► [3] OHLC 데이터 티커별 1회 호출 ✅
          │     └─► For each ticker:
          │           └─► FMPAPIClient.get_historical_price_eod(ticker, fromDate, toDate)
          │                 └─► ohlc_cache[ticker] = {date: {open, high, low, close}, ...}
          │
          ├─► [4] 거래일 캐싱 (최적화)
          │     └─► get_trading_days_in_range(start, end, 'NASDAQ', pool)
          │           └─► trading_days_set에 저장
          │
          ├─► [5] 이벤트별 price_trend 생성
          │     └─► For each event:
          │           ├─► calculate_dayOffset_dates_cached(event_date, countStart, countEnd, trading_days_set)
          │           └─► For each (dayOffset, targetDate):
          │                 └─► ohlc_cache[ticker][targetDate] 조회 (O(1))
          │
          └─► [6] 배치 DB 업데이트
                └─► UPDATE txn_events SET price_trend = ... FROM UNNEST(...)
```

---

## 4. MetricCalculationEngine 상세

### 초기화 및 의존성 해결
**위치**: `metric_engine.py:25-192`

```
MetricCalculationEngine(metrics_by_domain, transforms)
    │
    ├─► _flatten_metrics()
    │     모든 도메인의 메트릭을 단일 리스트로
    │
    ├─► build_dependency_graph()
    │     │
    │     └─► For each metric:
    │           └─► _extract_dependencies(metric)
    │                 ├─► source='api_field' → 의존성 없음
    │                 ├─► source='aggregation' → base_metric_id가 의존성
    │                 └─► source='expression' → formula 파싱하여 의존성 추출
    │
    └─► topological_sort()
          Kahn's algorithm으로 계산 순서 결정
          결과: [api_field 메트릭들, aggregation 메트릭들, expression 메트릭들]
```

### 계산 실행
**위치**: `metric_engine.py:195-350`

```
engine.calculate_all(api_data, target_domains)
    │
    ├─► [1] 의존성 그래프 구축
    │     └─► build_dependency_graph()
    │
    ├─► [2] 위상 정렬
    │     └─► topological_sort()
    │
    └─► [3] 순서대로 메트릭 계산
          └─► For each metric in sorted_order:
                │
                ├─► _calculate_metric_with_reason(metric, api_data, calculated_values)
                │     │
                │     ├─► source='api_field':
                │     │     └─► _calculate_api_field(metric, api_data)
                │     │           ├─► api_list_id로 API 응답 조회
                │     │           ├─► response_key로 필드 추출
                │     │           └─► 값 반환 또는 None
                │     │
                │     ├─► source='aggregation':
                │     │     └─► _calculate_aggregation(metric, calculated_values)
                │     │           ├─► base_metric_id로 기본 값 조회
                │     │           ├─► aggregation_kind로 변환 함수 선택
                │     │           │     ├─► ttmFromQuarterSumOrScaled
                │     │           │     ├─► lastFromQuarter
                │     │           │     ├─► avgFromQuarter
                │     │           │     ├─► yoyFromQuarter
                │     │           │     └─► qoqFromQuarter
                │     │           └─► 값 반환 또는 None
                │     │
                │     └─► source='expression':
                │           └─► _calculate_expression(metric, calculated_values)
                │                 ├─► formula 파싱
                │                 ├─► 의존성 값들 치환
                │                 ├─► eval() 실행
                │                 └─► 값 반환 또는 None
                │
                └─► calculated_values[metric_name] = value
```

---

## 5. 데이터 흐름

### 입력 데이터
```
[Request Parameters]
    ├─► overwrite: bool (기존 값 덮어쓰기 여부)
    ├─► from_date: Optional[date] (이벤트 시작 날짜)
    ├─► to_date: Optional[date] (이벤트 종료 날짜)
    └─► tickers: Optional[str] (티커 필터, 쉼표 구분)

[DB에서 로드]
    ├─► config_lv2_metric: 메트릭 정의 (formula, source, api_list_id 등)
    ├─► config_lv2_metric_transform: aggregation 함수 정의
    ├─► txn_events: 처리할 이벤트 목록
    └─► evt_consensus: qualitative 데이터 (source='consensus' 이벤트용)

[FMP API에서 로드]
    ├─► fmp-income-statement: 분기별 손익계산서 (limit=100)
    ├─► fmp-balance-sheet-statement: 분기별 재무상태표 (limit=100)
    ├─► fmp-cash-flow-statement: 분기별 현금흐름표 (limit=100)
    ├─► fmp-historical-price-eod-full: 과거 OHLC 데이터
    ├─► fmp-quote: 현재 시점 시세 (marketCap 등) ⚠️ 시간적 유효성 없음
    └─► fmp-price-target-consensus: 현재 시점 애널리스트 컨센서스 ⚠️ 시간적 유효성 없음
```

### 출력 데이터
```
[txn_events 테이블 업데이트]
    ├─► value_quantitative: JSONB
    │     {
    │       "valuation": {"PER": 25.3, "PBR": 3.2, ...},
    │       "profitability": {"grossMarginTTM": 0.45, ...},
    │       "momentum": {"revenueYoY": 0.15, ...},
    │       "risk": {"debtToEquity": 0.8, ...},
    │       "dilution": {"sharesYoY": 0.02, ...}
    │     }
    │
    ├─► value_qualitative: JSONB
    │     {
    │       "targetMedian": 150.0,
    │       "consensusSummary": {"targetHigh": 180, "targetLow": 120, ...},
    │       "consensusSignal": {"direction": "up", "last": {...}, "prev": {...}, "delta": 5.0}
    │     }
    │
    ├─► position_quantitative: enum ('long' | 'short' | 'neutral' | NULL)
    ├─► position_qualitative: enum ('long' | 'short' | 'neutral' | NULL)
    ├─► disparity_quantitative: float (target/current - 1)
    ├─► disparity_qualitative: float (target/current - 1)
    └─► price_trend: JSONB
          [
            {"dayOffset": -14, "targetDate": "2024-01-01", "open": 150.0, "high": 152.0, "low": 149.0, "close": 151.0},
            {"dayOffset": -13, "targetDate": "2024-01-02", ...},
            ...
            {"dayOffset": +14, "targetDate": "2024-01-29", ...}
          ]
```

---

## 6. 알려진 이슈

| 이슈 ID | 설명 | 상태 |
|---------|------|------|
| I-25 | marketCap 시간적 유효성 → `fmp-historical-market-capitalization` API로 해결 | ✅ 완료 |
| I-26 | fmp-price-target-consensus가 event_date 무시 → 과거 이벤트 NULL 처리 | ✅ 완료 |
| I-27 | priceTrend 티커별 1회 호출 확인 | ✅ 정상 |
| I-28 | 재무제표 TTM 계산 시간적 유효성 확인 | ✅ 정상 |
| I-29 | price_when_posted_prev 변수 누락 → consensusSignal.prev 항상 null | ✅ 완료 |
| I-30 | _meta.date_range 필드 개선 → sources로 이름 변경 및 값 채움 | ✅ 완료 |
| I-31 | targetSummary 계산 (consensusSummary 대체) | ✅ 완료 |
| I-36 | Quantitative Position/Disparity → calcFairValue 파라미터 | 🔄 DEPRECATED (→ I-41) |
| I-38 | calcFairValue 기본값 | 🔄 DEPRECATED (→ I-41) |
| I-40 | Peer tickers 미존재 로깅 | 🔄 DEPRECATED (→ I-41 제한사항) |
| I-41 | priceQuantitative 메트릭 구현 (원본 설계 준수) | ✅ 완료 |
| I-37 | targetMedian → 실제 Median 계산 (PERCENTILE_CONT) | ✅ 완료 |

### I-25 해결 완료 (2025-12-27)
- **문제**: `fmp-quote` API가 현재 시점 marketCap만 반환
- **해결**: `fmp-historical-market-capitalization` API 사용
  - 엔드포인트: `/stable/historical-market-capitalization?symbol={ticker}&from={fromDate}&to={toDate}`
  - **핵심**: `from`/`to` 파라미터로 날짜 범위 특정 가능
  - 응답에 `date` 필드 포함 → event_date 기준 필터링 가능
  - 시계열 응답에서 가장 최근 값(첫 번째) 자동 선택
- **구현 완료 사항**:
  - ✅ DB: `config_lv1_api_list`에 API 추가 (사용자 직접 반영)
  - ✅ DB: `config_lv2_metric.marketCap`의 `api_list_id` 변경 (사용자 직접 반영)
  - ✅ Python: `valuation_service.py`에서 from/to 파라미터 처리 (2곳)
  - ✅ Python: `metric_engine.py`에서 시계열 marketCap 첫 번째 값 선택

### I-28 확인 완료 (2025-12-27)
- **점검 내용**: 재무제표 TTM 계산이 event_date 기준으로 올바르게 수행되는지 확인
- **결과**: ✅ 정상 작동
  - `valuation_service.py:847-850`: 날짜 필터링 (`date <= event_date`)
  - `metric_engine.py:689-722`: TTM 합산 (최근 4분기)
  - 예: event_date=2024-12-22 → 2024-12-28 분기 제외됨 (정상)

### I-26 해결 완료 (2025-12-27)
- **문제**: FMP `fmp-price-target-consensus` API가 현재 시점 consensus만 반환
- **해결**: 과거 이벤트(7일 이전)에는 consensus 값을 NULL로 처리
- **구현 사항**:
  - ✅ `calculate_qualitative_metrics_fast()` 함수 수정
  - ✅ 과거 이벤트 판단: `event_date < today - 7days`
  - ✅ 과거 이벤트: `targetMedian=NULL`, `consensusSummary=NULL`
  - ✅ `_meta` 필드에 `dataAvailable`, `reason`, `fetchDate` 정보 추가
- **출력 예시**:
  ```json
  // 과거 이벤트 (7일+ 전)
  {
    "targetMedian": null,
    "consensusSummary": null,
    "consensusSignal": {...},
    "_meta": {
      "dataAvailable": false,
      "reason": "Historical event - FMP API only provides current consensus",
      "event_date": "2021-01-31",
      "threshold_days": 7
    }
  }
  
  // 최근 이벤트 (7일 이내)
  {
    "targetMedian": 150.0,
    "consensusSummary": {...},
    "consensusSignal": {...},
    "_meta": {
      "dataAvailable": true,
      "fetchDate": "2025-12-27"
    }
  }
  ```

### I-29 해결됨 (2025-12-30) ✅
- **문제**: evt_consensus 테이블의 `price_target_prev`, `price_when_posted_prev`, `direction`이 모두 NULL
- **원인**: GET /sourceData?mode=consensus의 2단계 계산이 실행되지 않음
- **해결**: `calc_mode=calculation` 모드 추가 (API 호출 없이 2단계 계산만 수행)
- **사용법**: 
  ```bash
  GET /sourceData?mode=consensus&calc_mode=calculation&calc_scope=all
  ```
- **수정 파일**: `backend/src/services/source_data_service.py:177-260`

### I-30 해결됨 (2025-12-31) ✅
- **문제**: 계산된 메트릭이 어떤 날짜의 원천 데이터를 기반으로 하는지 알 수 없음
- **현상**: PER = marketCap / netIncomeTTM 계산 시, marketCap이 어떤 날짜 값인지, netIncomeTTM이 어떤 분기들의 합인지 기록되지 않음
- **해결**: MetricCalculationEngine에서 메트릭별 소스 정보 추적
- **구현 사항**:
  - ✅ `metric_sources` 딕셔너리 추가
  - ✅ `_calculate_api_field_with_source()`: API 응답에서 날짜 추출
  - ✅ `_calculate_aggregation_with_source()`: 기본 메트릭 소스 상속
  - ✅ `_calculate_expression_with_source()`: 의존성 소스 수집
  - ✅ `_group_by_domain()`: `_meta.sources`에 메트릭별 상세 소스 포함
- **예시 출력**:
  ```json
  {
    "valuation": {
      "_meta": {
        "calcType": "TTM_fullQuarter",
        "count": 4,
        "dateRange": "2024-09-28 ~ 2025-08-13",
        "sources": {
          "PER": {
            "type": "expression",
            "formula": "marketCap / netIncomeTTM",
            "dependencies": ["marketCap", "netIncomeTTM"],
            "sources": {
              "marketCap": {"api": "fmp-historical-market-capitalization", "date": "2025-08-13"},
              "netIncomeTTM": {"api": "fmp-income-statement", "dates": ["2024-09-28", ...]}
            }
          }
        }
      },
      "PER": -31.19,
      "PBR": 9.29
    }
  }
  ```
- **수정 파일**: `backend/src/services/metric_engine.py`

### I-31 해결됨 (2025-12-31) ✅
- **문제**: value_qualitative.consensusSummary가 과거 이벤트에서 항상 NULL
- **원인**: FMP API가 현재 시점 consensus만 반환
- **해결**: evt_consensus 테이블에 target_summary 사전 계산 후 저장
- **구현 흐름**:
  1. GET /sourceData?mode=consensus에서 Phase 3로 target_summary 계산
  2. evt_consensus.target_summary에 JSONB로 저장
  3. POST /backfillEventsTable에서 저장된 값 읽기
- **예시 출력**:
  ```json
  {
    "value_qualitative": {
      "targetMedian": 25.5,
      "targetSummary": {
        "lastMonth": {"avg": 28.0, "low": 25.0, "high": 32.0, "count": 3},
        "allTime": {"avg": 25.5, "publishers": ["Williams Trading", "Needham"]}
      },
      "consensusSignal": {...},
      "_meta": {"dataAvailable": true, "source": "evt_consensus (pre-calculated)"}
    }
  }
  ```
- **수정 파일**: 
  - `backend/src/database/queries/consensus.py`
  - `backend/src/services/source_data_service.py`
  - `backend/src/services/valuation_service.py`

### I-36 해결됨 (2025-12-31) → 🔄 DEPRECATED (2026-01-02)
⚠️ **이 이슈는 I-41로 대체되었습니다**

- **문제**: `position_quantitative`, `disparity_quantitative`가 항상 NULL
- **임시 해결**: 업종 평균 PER × EPS로 적정가 계산 (파라미터 기반)
- **폐기 이유**: 원본 설계는 `priceQuantitative` 메트릭 요구, 파라미터 방식은 아키텍처 불일치
- **마이그레이션**: → I-41 priceQuantitative 메트릭 (메트릭 시스템 통합)
- ~~**사용법**: `POST /backfillEventsTable?calcFairValue=true&tickers=AAPL`~~ (deprecated)
- **참조**: `history/3_DETAIL.md#I-36`, `history/3_DETAIL.md#I-41`

### I-41 Part 1+2+3 구현됨 (2026-01-02) ✅

**Part 1: priceQuantitative 메트릭 구현**
- **문제**: 원본 설계 불일치 - `priceQuantitative` 메트릭 미구현
- **해결**: `config_lv2_metric` 테이블에 priceQuantitative 메트릭 추가 (source='custom')
- **구현 내용**:
  - SQL: `backend/scripts/add_priceQuantitative_metric.sql`
  - 설계 문서: `backend/DESIGN_priceQuantitative_metric.md`
  - I-36의 계산 로직 재사용 (get_peer_tickers, calculate_sector_average_metrics 등)
  - `MetricEngine`: custom_values 파라미터 지원 추가
  - `calculate_price_quantitative_metric()`: 기존 로직 래핑
  - Event 처리 루프에서 priceQuantitative 계산 후 custom_values로 전달

**Part 2: 선택적 메트릭 업데이트 (Selective Metric Update)**
- **문제**: 특정 메트릭만 효율적으로 업데이트 필요
- **해결**: `metrics` 파라미터 추가
- **구현 내용**:
  - **API 파라미터**: `metrics` (업데이트할 메트릭 ID 리스트, 쉼표 구분)
  - **데이터베이스**: JSONB `||` 연산자로 선택적 병합
  - **파라미터 전달**: router → calculate_valuations → process_ticker_batch → batch_update_event_valuations

**Part 3: API 단순화 (overwriteMetrics 제거)**
- **문제**: `overwrite` + `overwriteMetrics` 파라미터로 인한 UX 혼란
- **사용자 제안**: "overwriteMetrics는 이미 모든 엔드포인트에 overwrite 파라미터가 있어 이것을 사용하면 되는 것 아닌가요?"
- **해결**: `overwriteMetrics` 제거, `overwrite` 파라미터 의미 확장
- **구현 내용**:
  - `overwriteMetrics` 파라미터 완전 제거
  - `overwrite` 파라미터 문맥적 의미 부여:
    - `metrics` 지정 시: 해당 메트릭에만 적용
    - `metrics` 미지정 시: 전체 필드에 적용
  - 백엔드 4개 파일, 프론트엔드 2개 파일 수정

**단순화된 동작 매트릭스**:
```
metrics          | overwrite | 동작
-----------------|-----------|---------------------
None             | false     | 전체 필드 NULL만 채우기
None             | true      | 전체 필드 강제 덮어쓰기
'priceQuant'     | false     | priceQuantitative만 NULL 채우기
'priceQuant'     | true      | priceQuantitative만 강제 덮어쓰기
'PER,PBR'        | false     | PER,PBR만 NULL 채우기
'PER,PBR'        | true      | PER,PBR만 강제 덮어쓰기
```

**사용법**:
```bash
# priceQuantitative만 NULL 값 채우기 (기본 동작)
POST /backfillEventsTable?metrics=priceQuantitative

# priceQuantitative 강제 재계산 (덮어쓰기)
POST /backfillEventsTable?metrics=priceQuantitative&overwrite=true

# 여러 메트릭 동시 업데이트 (NULL만)
POST /backfillEventsTable?metrics=priceQuantitative,PER,PBR&overwrite=false

# 특정 티커의 여러 메트릭 강제 재계산
POST /backfillEventsTable?tickers=AAPL,MSFT&metrics=PER,PBR,PSR&overwrite=true
```

**폐기된 이슈**:
- I-36 (calcFairValue 파라미터), I-38 (기본값), I-40 (peer tickers)

**수정된 파일**:
- `backend/src/models/request_models.py`: metrics 파라미터, overwrite 의미 확장
- `backend/src/routers/events.py`: 파라미터 파싱 (overwriteMetrics 제거)
- `backend/src/services/valuation_service.py`: priceQuantitative 계산 (overwriteMetrics 제거)
- `backend/src/services/metric_engine.py`: custom_values 지원
- `backend/src/database/queries/metrics.py`: 선택적 JSONB 업데이트 (SQL 단순화)
- `frontend/src/pages/RequestsPage.jsx`: metrics, calcFairValue 파라미터 추가
- `frontend/src/pages/SetRequestsPage.jsx`: endpoint flow 파라미터 업데이트

**참조**: `history/3_DETAIL.md#I-41`, `history/ISSUE_priceQuantitative_MISSING.md`

### I-37 해결됨 (2025-12-31) ✅
- **문제**: 변수명 `targetMedian`인데 실제 값은 `AVG(price_target)` (평균값)
- **해결**: PostgreSQL `PERCENTILE_CONT(0.5)` 함수로 실제 Median 계산
- **구현 내용**:
  - `calculate_target_summary()` SQL에 Median, Min, Max 추가
  - 반환 구조에 `allTimeMedianPriceTarget`, `allTimeMinPriceTarget`, `allTimeMaxPriceTarget` 추가
  - `valuation_service.py`에서 `allTimeMedianPriceTarget` 사용
- **데이터 재계산**: `GET /sourceData?mode=consensus&overwrite=true`
- **참조**: `history/3_DETAIL.md#I-37`

---

## 7. 성능 특성

| 항목 | 값 | 비고 |
|------|-----|------|
| 티커 동시 처리 | 10개 | TICKER_CONCURRENCY |
| API 호출 (티커당) | ~6회 | 재무제표 3개 + OHLC + historical-market-cap + consensus |
| DB 업데이트 방식 | 배치 | UNNEST 사용 |
| 거래일 조회 | 1회 | 전체 기간 캐싱 |

---

## 8. I-43: txn_price_trend 테이블 분리 (2026-01-05) 🔄

**목적**: Dashboard Events 표 로딩 성능 개선 (85-92% 응답 속도 향상)

### 변경 사항

#### Phase 5 수정: generate_price_trends()

**현재 구현**:
```python
# txn_events.price_trend JSONB 컬럼에 저장
UPDATE txn_events SET price_trend = $1 WHERE id = $2
```

**I-43 개선 후**:
```python
# txn_price_trend 테이블에 UPSERT
INSERT INTO txn_price_trend (
    ticker, event_date,
    d_neg14, d_neg13, ..., d_0, ..., d_pos14,
    wts_long, wts_short
) VALUES (...)
ON CONFLICT (ticker, event_date) DO UPDATE
SET d_neg14 = EXCLUDED.d_neg14, ...
```

#### 새로운 테이블: txn_price_trend

```sql
CREATE TABLE txn_price_trend (
    ticker VARCHAR(20) NOT NULL,
    event_date DATE NOT NULL,

    -- 29개 dayOffset 컬럼 (D-14 ~ D14, D0 포함)
    d_neg14 JSONB,
    ...
    d_0 JSONB,
    ...
    d_pos14 JSONB,

    -- WTS 미리 계산
    wts_long INT,
    wts_short INT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (ticker, event_date)
);
```

**JSONB 구조**:
```json
{
  "price_trend": {"low": 25.29, "high": 26.53, "open": 26.37, "close": 25.57},
  "dayOffset0": {"close": 28.57},
  "performance": {"close": -0.0018796992}
}
```

### 로직 변경

1. **ticker + event_date 그룹화**: 중복 제거
2. **D0 close 조회**: base_close로 사용
3. **각 dayOffset 계산**: D-14 ~ D14 (0 포함)
   - `performance = (close - dayOffset0.close) / dayOffset0.close`
4. **WTS 계산**:
   - `wts_long`: long position 최대 수익 dayOffset
   - `wts_short`: short position 최대 수익 dayOffset
5. **UPSERT**: txn_price_trend 테이블

### 기능 유지 사항

- ✅ ticker별 1회 호출 (OHLC API)
- ✅ 날짜 범위 필터 (from, to)
- ✅ ticker 필터
- ✅ overwrite 파라미터
- ✅ 거래일 캐싱 (I-24)
- ✅ 배치 업데이트

### null 값 처리 및 WTS 업데이트

**시나리오**: 미래 날짜 데이터가 아직 없는 경우
```python
# 초기 backfill (2024-12-25 이벤트, 현재 2024-12-28)
# D1, D2, D3은 데이터 있음, D4~D14는 미래라 null
{
  "d_pos1": {"price_trend": {...}, "performance": {...}},
  "d_pos2": {"price_trend": {...}, "performance": {...}},
  "d_pos3": {"price_trend": {...}, "performance": {...}},
  "d_pos4": null,  # 미래 날짜
  ...
  "d_pos14": null,
  "wts_long": 2,  # 현재까지 데이터로 계산된 WTS
  "wts_short": -1
}

# 나중에 재실행 (2025-01-10, 모든 데이터 available)
# null → 값 채워짐
# WTS 재계산 (wts_long: 2 → 7로 업데이트)
```

### 구현 체크리스트

- [ ] DDL 스크립트: `backend/scripts/create_txn_price_trend.sql`
- [ ] 마이그레이션: `backend/scripts/migrate_price_trend_to_table.py`
- [ ] valuation_service.py 수정: generate_price_trends() 함수
- [ ] 성능 테스트 스크립트
- [ ] 문서 업데이트

### 예상 성능

| 작업 | 개선 효과 |
|------|----------|
| GET /dashboard/events | 2-5초 → 0.2-0.4초 (85-92% 개선) |
| POST /backfillEventsTable | 영향 없음 (ticker당 1회 호출 유지) |

### 참조

- **설계 문서**: `history/I-43_FLOW.md`
- **체크리스트**: `history/1_CHECKLIST.md#I-43`
- **엔드포인트**: `history/0_endpointFlow/GET_dashboard_events.md`

---

*최종 업데이트: 2026-01-05 KST (I-43 설계 추가 - txn_price_trend 테이블 분리)*
*이전 업데이트: 2026-01-02 KST (I-41 추가, I-36/I-38/I-40 deprecated)*

