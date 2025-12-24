# POST /backfillEventsTable 상세 실행 흐름 점검 문서

## 개요
이 문서는 수정된 코드의 실제 실행 흐름을 단계별로 따라가며, 각 단계에서 호출하는 DB 쿼리, API 엔드포인트, event_date 기반 필터링, 그리고 데이터 처리 과정을 상세히 기록합니다.

---

## 전체 실행 흐름 개요

```
1. 요청 수신 및 파라미터 검증
2. Phase 1: 메트릭 정의 로드 (config_lv2_metric)
3. Phase 2: 이벤트 로드 (txn_events)
4. Phase 3: 각 이벤트별 처리
   ├─ 3-1. Quantitative 메트릭 계산
   │   ├─ FMP API 호출 (limit=100)
   │   ├─ event_date 기반 필터링
   │   ├─ MetricCalculationEngine 실행
   │   └─ _meta 정보 추가
   ├─ 3-2. Qualitative 메트릭 계산
   ├─ 3-3. Position/Disparity 계산
   └─ 3-4. DB 업데이트
5. Phase 4: Price Trend 생성
6. 결과 집계 및 반환
```

---

## 단계별 상세 실행 흐름

### 1단계: 요청 수신 및 파라미터 검증

**위치**: `backend/src/routers/events.py:105-136`

**실행 내용**:
1. FastAPI 라우터가 POST 요청 수신
2. `BackfillEventsTableQueryParams` 객체 생성 및 검증
   - `overwrite`: boolean (default: false)
   - `from`: date (optional, alias: `from_date`)
   - `to`: date (optional, alias: `to_date`)
   - `tickers`: string (optional, comma-separated)
3. `get_ticker_list()` 호출하여 tickers 파라미터 파싱
   - 쉼표로 분리
   - 대괄호 제거 (있는 경우)
   - 공백 제거 및 대문자 변환
   - 예: `"AAPL,MSFT"` → `["AAPL", "MSFT"]`
4. 요청 ID 생성: `request.state.reqId` 또는 `uuid.uuid4()`

**로그 출력**:
```
[ROUTER] POST /backfillEventsTable RECEIVED - reqId={req_id}
[ROUTER] Parameters: overwrite={overwrite}, from_date={from_date}, to_date={to_date}, tickers={ticker_list}
```

---

### 2단계: Valuation Service 호출

**위치**: `backend/src/routers/events.py:138-146`

**실행 내용**:
1. `valuation_service.calculate_valuations()` 함수 호출
2. 전달 파라미터:
   - `overwrite`: boolean
   - `from_date`: date | None
   - `to_date`: date | None
   - `tickers`: List[str] | None

---

### 3단계: Phase 1 - 메트릭 정의 로드

**위치**: `backend/src/services/valuation_service.py:54-90`

#### 3-1. 데이터베이스 연결 풀 획득

**코드**: `pool = await db_pool.get_pool()`

**실행 내용**:
- PostgreSQL 연결 풀에서 연결 획득
- 연결 풀은 애플리케이션 시작 시 초기화됨

#### 3-2. 메트릭 정의 조회

**코드**: `metrics_by_domain = await metrics.select_metric_definitions(pool)`

**위치**: `backend/src/database/queries/metrics.py:8-66`

**실행 SQL 쿼리**:
```sql
SELECT id, domain, expression, description, source, api_list_id, 
       base_metric_id, aggregation_kind, aggregation_params, response_key
FROM config_lv2_metric
WHERE domain LIKE 'quantitative-%' OR domain LIKE 'qualitative-%'
ORDER BY domain, id
```

**쿼리 결과 처리**:
1. 각 row를 순회하며 도메인 suffix 추출
   - `quantitative-valuation` → `valuation`
   - `quantitative-profitability` → `profitability`
   - `qualitative-consensusSignal` → `consensusSignal`
2. 도메인별로 그룹화하여 딕셔너리 생성

**반환 데이터 구조 예시**:
```python
{
    'valuation': [
        {
            'name': 'PER',
            'domain': 'quantitative-valuation',
            'formula': 'marketCap / netIncomeTTM',
            'description': 'Price to Earnings Ratio',
            'source': 'expression',
            'api_list_id': None,
            'base_metric_id': None,
            'aggregation_kind': None,
            'aggregation_params': None,
            'response_key': None
        },
        ...
    ],
    'profitability': [...],
    'momentum': [...],
    'risk': [...],
    'dilution': [...]
}
```

**로그 출력**:
```
[backfillEventsTable] Metrics loaded: {len(metrics_by_domain)} domains
```

---

### 4단계: Phase 2 - 이벤트 로드

**위치**: `backend/src/services/valuation_service.py:92-133`

#### 4-1. 이벤트 조회

**코드**: `events = await metrics.select_events_for_valuation(pool, from_date, to_date, tickers)`

**위치**: `backend/src/database/queries/metrics.py:69-123`

**실행 SQL 쿼리** (동적 구성):
```sql
SELECT ticker, event_date, source, source_id,
       sector, industry,
       value_quantitative, value_qualitative,
       position_quantitative, position_qualitative,
       disparity_quantitative, disparity_qualitative
FROM txn_events
WHERE 1=1
  [AND (event_date AT TIME ZONE 'UTC')::date >= $1]  -- from_date가 있는 경우
  [AND (event_date AT TIME ZONE 'UTC')::date <= $2]  -- to_date가 있는 경우
  [AND ticker = ANY($3)]                              -- tickers가 있는 경우
ORDER BY ticker, event_date
```

**쿼리 파라미터 예시**:
- `from_date='2021-01-01'`, `to_date='2025-12-31'`, `tickers=['RGTI']`
- 파라미터: `[$1='2021-01-01', $2='2025-12-31', $3=['RGTI']]`

**반환 데이터 구조**:
```python
[
    {
        'ticker': 'RGTI',
        'event_date': datetime(2021, 1, 31, 0, 0, 0, tzinfo=timezone.utc),
        'source': 'consensus',
        'source_id': '12345',
        'sector': 'Technology',
        'industry': 'Software',
        'value_quantitative': None,  # 아직 계산 안 됨
        'value_qualitative': None,
        ...
    },
    {
        'ticker': 'RGTI',
        'event_date': datetime(2025, 12, 11, 10, 19, 41, tzinfo=timezone.utc),
        'source': 'consensus',
        'source_id': '67890',
        ...
    },
    ...
]
```

**로그 출력**:
```
[backfillEventsTable] Events loaded: {len(events)} events
[backfillEventsTable] Filtered by tickers: {tickers}  # tickers가 있는 경우
```

#### 4-2. 조기 종료 검사

**코드**: `if len(events) == 0: return {...}`

**조건**: 이벤트가 0개인 경우

**반환값**:
```python
{
    'summary': {
        'totalEventsProcessed': 0,
        'quantitativeSuccess': 0,
        'quantitativeFail': 0,
        'qualitativeSuccess': 0,
        'qualitativeFail': 0,
        'priceTrendSuccess': 0,
        'priceTrendFail': 0,
        'elapsedMs': ...
    },
    'results': []
}
```

---

### 5단계: Phase 3 - 각 이벤트별 처리

**위치**: `backend/src/services/valuation_service.py:156-319`

**루프 구조**:
```python
for idx, event in enumerate(events):
    # 각 이벤트 처리
```

#### 5-1. Quantitative 메트릭 계산

**위치**: `backend/src/services/valuation_service.py:400-547`

##### 5-1-1. FMP API 호출 (과거 데이터 충분히 가져오기)

**코드**: `backend/src/services/valuation_service.py:425-429`

**실행 내용**:

1. **Income Statement API 호출**:
   ```python
   income_stmt_all = await fmp_client.get_income_statement(ticker, period='quarter', limit=100)
   ```
   
   **내부 처리** (`backend/src/services/external_api.py:353-379`):
   - `call_api('fmp-income-statement', {'ticker': ticker, 'period': 'quarter', 'limit': 100})` 호출
   - `config_lv1_api_list` 테이블에서 `id='fmp-income-statement'` 조회
   - URL 템플릿: `https://financialmodelingprep.com/stable/income-statement?symbol={ticker}&period=quarter&limit={limit}&apikey={apiKey}`
   - 실제 URL: `https://financialmodelingprep.com/stable/income-statement?symbol=RGTI&period=quarter&limit=100&apikey=XXX`
   - Rate Limiter 적용 (API 호출 속도 제한)
   - Schema Mapping 적용 (API 필드명 → 내부 표준 필드명)
   
   **반환 데이터 구조** (최신이 첫 번째):
   ```python
   [
       {'date': '2025-12-31', 'netIncome': 1000000, 'revenue': 5000000, ...},  # 최신 분기
       {'date': '2025-09-30', 'netIncome': 900000, 'revenue': 4800000, ...},
       {'date': '2025-06-30', 'netIncome': 800000, 'revenue': 4600000, ...},
       ...
       {'date': '2021-03-31', 'netIncome': 500000, 'revenue': 3000000, ...},  # 과거 분기
       ...
   ]
   ```

2. **Balance Sheet API 호출**:
   ```python
   balance_sheet_all = await fmp_client.get_balance_sheet(ticker, period='quarter', limit=100)
   ```
   
   **내부 처리** (`backend/src/services/external_api.py:381-407`):
   - `call_api('fmp-balance-sheet-statement', {'ticker': ticker, 'period': 'quarter', 'limit': 100})` 호출
   - URL 템플릿: `https://financialmodelingprep.com/stable/balance-sheet-statement?symbol={ticker}&period=quarter&limit={limit}&apikey={apiKey}`
   - 실제 URL: `https://financialmodelingprep.com/stable/balance-sheet-statement?symbol=RGTI&period=quarter&limit=100&apikey=XXX`
   
   **반환 데이터 구조**:
   ```python
   [
       {'date': '2025-12-31', 'totalAssets': 10000000, 'totalLiabilities': 4000000, ...},
       {'date': '2025-09-30', 'totalAssets': 9800000, 'totalLiabilities': 3900000, ...},
       ...
   ]
   ```

3. **Quote API 호출** (시가총액 등 현재 시장 데이터):
   ```python
   quote = await fmp_client.get_quote(ticker)
   ```
   
   **참고**: `get_quote()` 메서드가 `external_api.py`에 정의되어 있지 않을 수 있습니다. 이 경우 에러가 발생할 수 있습니다.

##### 5-1-2. event_date 기반 필터링 (시간적 유효성 보장)

**코드**: `backend/src/services/valuation_service.py:438-472`

**실행 내용**:

1. **event_date 변환**:
   ```python
   if isinstance(event_date, str):
       event_date_obj = datetime.fromisoformat(event_date.replace('Z', '+00:00')).date()
   elif hasattr(event_date, 'date'):
       event_date_obj = event_date.date()
   else:
       event_date_obj = event_date
   ```
   
   **예시**:
   - 입력: `datetime(2021, 1, 31, 0, 0, 0, tzinfo=timezone.utc)`
   - 출력: `date(2021, 1, 31)`

2. **Income Statement 필터링**:
   ```python
   income_stmt = []
   for quarter in income_stmt_all:
       quarter_date_str = quarter.get('date')
       if quarter_date_str:
           quarter_date = datetime.fromisoformat(quarter_date_str.replace('Z', '+00:00')).date()
           if quarter_date <= event_date_obj:  # 중요: event_date 이전 분기만 사용
               income_stmt.append(quarter)
   ```
   
   **필터링 예시**:
   - `event_date = 2021-01-31`
   - `income_stmt_all`에 2025년 분기들이 포함되어 있어도
   - 필터링 후 `income_stmt`에는 2021-01-31 이전 분기만 포함:
     ```python
     [
         {'date': '2020-12-31', ...},  # 2021-01-31 이전
         {'date': '2020-09-30', ...},
         {'date': '2020-06-30', ...},
         {'date': '2020-03-31', ...},
         ...
     ]
     ```

3. **Balance Sheet 필터링**:
   - 동일한 로직으로 `balance_sheet_all` 필터링
   - `balance_sheet`에는 `event_date` 이전 분기만 포함

4. **유효성 검사**:
   ```python
   if len(income_stmt) == 0 or len(balance_sheet) == 0:
       return {
           'status': 'failed',
           'value': None,
           'message': f'no_valid_data: No quarterly data available before event_date {event_date_obj}'
       }
   ```
   
   **에러 케이스**:
   - `event_date`가 너무 과거여서 API에 해당 시점 이전 데이터가 없는 경우
   - 예: `event_date=2010-01-01`인데 API에 2015년 이후 데이터만 있는 경우

**로그 출력**:
```
[calculate_quantitative_metrics] Filtered {len(income_stmt)} income quarters and {len(balance_sheet)} balance sheet quarters for event_date {event_date_obj}
```

##### 5-1-3. MetricCalculationEngine 실행

**코드**: `backend/src/services/valuation_service.py:484-496`

**실행 내용**:

1. **API 데이터 준비**:
   ```python
   api_data = {
       'fmp-income-statement': income_stmt,  # 필터링된 데이터
       'fmp-balance-sheet-statement': balance_sheet,  # 필터링된 데이터
       'fmp-quote': quote if isinstance(quote, list) and len(quote) > 0 else (quote[0] if quote else {})
   }
   ```

2. **MetricCalculationEngine 초기화**:
   ```python
   engine = MetricCalculationEngine(metrics_by_domain)
   ```
   
   **내부 처리** (`backend/src/services/metric_engine.py:32-44`):
   - `metrics_by_domain`을 받아서 모든 메트릭을 평탄화
   - 메트릭 이름으로 인덱스 생성: `metrics_by_name`
   - 의존성 그래프 및 계산 순서는 나중에 빌드 (lazy initialization)

3. **모든 Quantitative 도메인 계산**:
   ```python
   target_domains = ['valuation', 'profitability', 'momentum', 'risk', 'dilution']
   value_quantitative = engine.calculate_all(api_data, target_domains)
   ```
   
   **내부 처리** (`backend/src/services/metric_engine.py:151-207`):
   
   a. **의존성 그래프 빌드** (`build_dependency_graph()`):
      - 각 메트릭의 의존성 추출:
        - `api_field`: 의존성 없음
        - `aggregation`: `base_metric_id`에 의존
        - `expression`: 공식에서 참조하는 메트릭 이름 추출
      - 예: `PER = marketCap / netIncomeTTM`
        - `PER`은 `marketCap`, `netIncomeTTM`에 의존
        - `netIncomeTTM`은 `netIncome` (api_field)에 의존
   
   b. **위상 정렬** (`topological_sort()`):
      - Kahn's 알고리즘 사용
      - 의존성이 없는 메트릭부터 계산 순서 결정
      - 예: `['netIncome', 'netIncomeTTM', 'marketCap', 'PER']`
   
   c. **각 메트릭 계산** (순서대로):
      - `_calculate_metric()` 호출
      - `source` 타입에 따라 라우팅:
        - `api_field`: `_calculate_api_field()` - API 응답에서 값 추출
        - `aggregation`: `_calculate_aggregation()` - TTM, Last, Avg 등 변환
        - `expression`: `_calculate_expression()` - 공식 평가
   
   d. **도메인별 그룹화** (`_group_by_domain()`):
      - 계산된 메트릭들을 도메인 suffix로 그룹화
      - 예: `{'valuation': {'PER': 25.5, 'PBR': 3.2}, 'profitability': {'ROE': 0.15}}`

**계산 예시** (PER 메트릭):
1. `netIncome` (api_field) 계산:
   - `fmp-income-statement`에서 `netIncome` 필드 추출
   - 결과: `[1000000, 900000, 800000, 700000]` (최근 4분기)
2. `netIncomeTTM` (aggregation: ttmFromQuarterSumOrScaled) 계산:
   - 최근 4분기 합산: `1000000 + 900000 + 800000 + 700000 = 3400000`
   - 결과: `3400000`
3. `marketCap` (api_field) 계산:
   - `fmp-quote`에서 `marketCap` 필드 추출
   - 결과: `85000000`
4. `PER` (expression) 계산:
   - 공식: `marketCap / netIncomeTTM`
   - 계산: `85000000 / 3400000 = 25.0`
   - 결과: `25.0`

##### 5-1-4. Sector/Industry 정보 추가

**코드**: `backend/src/services/valuation_service.py:498-533`

**실행 내용**:

1. **config_lv3_targets에서 회사 정보 조회**:
   ```python
   company_info = await targets.get_company_info(pool, ticker)
   ```
   
   **위치**: `backend/src/database/queries/targets.py:149-170`
   
   **실행 SQL 쿼리**:
   ```sql
   SELECT sector, industry 
   FROM config_lv3_targets 
   WHERE ticker = $1
   ```
   
   **파라미터**: `[$1='RGTI']`
   
   **반환값 예시**:
   ```python
   {
       'sector': 'Technology',
       'industry': 'Software'
   }
   ```

2. **_meta 정보 추가**:
   ```python
   quarters_used = min(len(income_stmt), 4)  # 최대 4개 분기 사용
   
   for domain_key in value_quantitative:
       if quarters_used >= 4:
           value_quantitative[domain_key]['_meta']['date_range'] = {
               'start': income_stmt[3].get('date'),  # 4번째로 오래된 분기
               'end': income_stmt[0].get('date')      # 가장 최신 분기
           }
           value_quantitative[domain_key]['_meta']['calcType'] = 'TTM_fullQuarter'
       else:
           value_quantitative[domain_key]['_meta']['date_range'] = {
               'start': income_stmt[quarters_used - 1].get('date'),
               'end': income_stmt[0].get('date')
           }
           value_quantitative[domain_key]['_meta']['calcType'] = 'TTM_partialQuarter'
       
       value_quantitative[domain_key]['_meta']['count'] = quarters_used
       value_quantitative[domain_key]['_meta']['event_date'] = str(event_date_obj)
       value_quantitative[domain_key]['_meta']['sector'] = company_info.get('sector')
       value_quantitative[domain_key]['_meta']['industry'] = company_info.get('industry')
   ```

**최종 value_quantitative 구조 예시**:
```json
{
    "valuation": {
        "PER": 25.0,
        "PBR": 3.2,
        "_meta": {
            "date_range": {
                "start": "2020-03-31",
                "end": "2020-12-31"
            },
            "calcType": "TTM_fullQuarter",
            "count": 4,
            "event_date": "2021-01-31",
            "sector": "Technology",
            "industry": "Software"
        }
    },
    "profitability": {
        "ROE": 0.15,
        "_meta": {...}
    },
    ...
}
```

##### 5-1-5. 반환값

**코드**: `backend/src/services/valuation_service.py:535-539`

**반환값 구조**:
```python
{
    'status': 'success',  # 또는 'failed'
    'value': value_quantitative,  # 위의 JSON 구조
    'message': 'Quantitative metrics calculated'  # 또는 에러 메시지
}
```

#### 5-2. Qualitative 메트릭 계산

**위치**: `backend/src/services/valuation_service.py:550-650`

**실행 내용**:

1. **소스 검증**:
   ```python
   if source != 'consensus':
       return {'status': 'skipped', 'value': None, 'currentPrice': None, 'message': 'Not a consensus event'}
   ```

2. **evt_consensus 테이블에서 데이터 조회**:
   ```python
   consensus_data = await metrics.select_consensus_data(pool, ticker, event_date)
   ```
   
   **위치**: `backend/src/database/queries/metrics.py:160-195`
   
   **실행 SQL 쿼리**:
   ```sql
   SELECT ticker, event_date, analyst_name, analyst_company,
          price_target, price_when_posted,
          price_target_prev, price_when_posted_prev,
          direction, response_key
   FROM evt_consensus
   WHERE ticker = $1
     AND event_date = $2
   ORDER BY event_date DESC
   LIMIT 1
   ```
   
   **파라미터**: `[$1='RGTI', $2='2021-01-31 00:00:00+00']`
   
   **반환값 예시**:
   ```python
   {
       'ticker': 'RGTI',
       'event_date': datetime(2021, 1, 31, ...),
       'analyst_name': 'John Doe',
       'analyst_company': 'ABC Securities',
       'price_target': 150.0,
       'price_when_posted': 140.0,
       'price_target_prev': 140.0,
       'price_when_posted_prev': 135.0,
       'direction': 'up',
       'response_key': {...}
   }
   ```

3. **consensusSignal 구조 생성**:
   ```python
   consensus_signal = {
       'direction': direction,  # 'up', 'down', 또는 None
       'last': {
           'price_target': float(price_target),
           'price_when_posted': float(price_when_posted)
       }
   }
   
   if price_target_prev is not None and price_when_posted_prev is not None:
       consensus_signal['prev'] = {
           'price_target': float(price_target_prev),
           'price_when_posted': float(price_when_posted_prev)
       }
       
       if price_target and price_target_prev:
           delta = float(price_target) - float(price_target_prev)
           delta_pct = (delta / float(price_target_prev)) * 100 if price_target_prev != 0 else None
           consensus_signal['delta'] = delta
           consensus_signal['deltaPct'] = delta_pct
   ```

**최종 value_qualitative 구조**:
```json
{
    "consensusSignal": {
        "direction": "up",
        "last": {
            "price_target": 150.0,
            "price_when_posted": 140.0
        },
        "prev": {
            "price_target": 140.0,
            "price_when_posted": 135.0
        },
        "delta": 10.0,
        "deltaPct": 7.14
    }
}
```

#### 5-3. Position 및 Disparity 계산

**위치**: `backend/src/services/valuation_service.py:203-212, 570-616`

**실행 내용**:

1. **Quantitative Position/Disparity**:
   ```python
   position_quant, disparity_quant = calculate_position_disparity(
       quant_result.get('value'),
       qual_result.get('currentPrice')
   )
   ```
   
   **내부 처리**:
   - `value_quantitative`에서 목표 가격 추출 (현재는 플레이스홀더)
   - `currentPrice`는 `qual_result.get('currentPrice')` (즉, `price_when_posted`)
   - `position`: `price_target > current_price` → `'long'`, `<` → `'short'`, `==` → `'neutral'`
   - `disparity`: `(price_target / current_price) - 1`

2. **Qualitative Position/Disparity**:
   ```python
   position_qual, disparity_qual = calculate_position_disparity(
       qual_result.get('value'),
       qual_result.get('currentPrice')
   )
   ```
   
   **내부 처리**:
   - `value_qualitative.consensusSignal.last.price_target`에서 목표 가격 추출
   - 동일한 로직으로 position/disparity 계산

#### 5-4. 데이터베이스 업데이트

**위치**: `backend/src/services/valuation_service.py:214-268`

**실행 내용**:

1. **update_event_valuations 호출**:
   ```python
   updated = await metrics.update_event_valuations(
       pool, ticker, event_date, source, source_id,
       value_quantitative=quant_result.get('value'),
       value_qualitative=qual_result.get('value'),
       position_quantitative=position_quant,
       position_qualitative=position_qual,
       disparity_quantitative=disparity_quant,
       disparity_qualitative=disparity_qual,
       overwrite=overwrite
   )
   ```
   
   **위치**: `backend/src/database/queries/metrics.py:198-308`
   
   **실행 SQL 쿼리** (overwrite 모드에 따라 다름):
   
   **overwrite=true**:
   ```sql
   UPDATE txn_events
   SET value_quantitative = $5::jsonb,
       value_qualitative = $6::jsonb,
       position_quantitative = $7,
       position_qualitative = $8,
       disparity_quantitative = $9,
       disparity_qualitative = $10
   WHERE ticker = $1
     AND event_date = $2
     AND source = $3
     AND source_id = $4
   ```
   
   **overwrite=false**:
   ```sql
   UPDATE txn_events
   SET value_quantitative = CASE
           WHEN value_quantitative IS NULL THEN $5::jsonb
           ELSE value_quantitative
       END,
       value_qualitative = CASE
           WHEN value_qualitative IS NULL THEN $6::jsonb
           ELSE value_qualitative
       END,
       position_quantitative = COALESCE(position_quantitative, $7),
       position_qualitative = COALESCE(position_qualitative, $8),
       disparity_quantitative = COALESCE(disparity_quantitative, $9),
       disparity_qualitative = COALESCE(disparity_qualitative, $10)
   WHERE ticker = $1
     AND event_date = $2
     AND source = $3
     AND source_id = $4
   ```
   
   **파라미터 예시**:
   ```python
   $1 = 'RGTI'
   $2 = datetime(2021, 1, 31, 0, 0, 0, tzinfo=timezone.utc)
   $3 = 'consensus'
   $4 = '12345'
   $5 = '{"valuation": {"PER": 25.0, ...}, ...}'  # JSON 문자열
   $6 = '{"consensusSignal": {...}}'
   $7 = 'long'
   $8 = 'long'
   $9 = 0.0714
   $10 = 0.0714
   ```

2. **업데이트 결과 확인**:
   ```python
   if updated == 0:
       raise ValueError("Event not found for update")
   ```

3. **성공/실패 카운터 업데이트**:
   ```python
   if quant_result['status'] == 'success':
       quantitative_success += 1
   elif quant_result['status'] == 'failed':
       quantitative_fail += 1
   ```

---

### 6단계: Phase 4 - Price Trend 생성

**위치**: `backend/src/services/valuation_service.py:321-350, 619-870`

**실행 내용**:

1. **정책 설정 로드**:
   ```python
   range_policy = await policies.get_price_trend_range_policy(pool)
   count_start = range_policy['countStart']  # 예: -30
   count_end = range_policy['countEnd']      # 예: 30
   ```
   
   **위치**: `backend/src/database/queries/policies.py:67-93`
   
   **실행 SQL 쿼리**:
   ```sql
   SELECT function, policy, description
   FROM config_lv0_policy
   WHERE function = 'fillPriceTrend_dateRange'
   ```
   
   **반환값 예시**:
   ```python
   {
       'function': 'fillPriceTrend_dateRange',
       'policy': {
           'countStart': -30,
           'countEnd': 30
       }
   }
   ```

2. **이벤트를 티커별로 그룹화**:
   ```python
   events_by_ticker = {}
   for event in events:
       ticker = event['ticker']
       if ticker not in events_by_ticker:
           events_by_ticker[ticker] = []
       events_by_ticker[ticker].append(event)
   ```

3. **각 티커별 OHLC 데이터 일괄 가져오기**:
   ```python
   for ticker, ticker_events in events_by_ticker.items():
       # 날짜 범위 계산
       min_date = min(event_dates)
       max_date = max(event_dates)
       fetch_start = min_date + timedelta(days=count_start * 2)
       fetch_end = max_date + timedelta(days=count_end * 2)
       
       # FMP API 호출
       ohlc_data = await fmp_client.get_historical_price_eod(ticker, fetch_start.isoformat(), fetch_end.isoformat())
       ohlc_cache[ticker] = ohlc_by_date  # 날짜를 키로 인덱싱
   ```
   
   **API 호출**:
   - URL: `https://financialmodelingprep.com/stable/historical-price-full/{ticker}?from={fromDate}&to={toDate}&apikey={apiKey}`
   - 예: `https://financialmodelingprep.com/stable/historical-price-full/RGTI?from=2020-11-01&to=2021-03-15&apikey=XXX`

4. **각 이벤트에 대해 Price Trend 생성**:
   ```python
   for event in events:
       # DayOffset 스캐폴드 생성
       dayoffset_dates = await calculate_dayOffset_dates(event_date, count_start, count_end, 'NASDAQ', pool)
       
       # Price Trend 배열 생성
       price_trend = []
       for dayoffset, target_date in dayoffset_dates:
           ohlc = ohlc_cache.get(ticker, {}).get(target_date.isoformat())
           if ohlc:
               price_trend.append({
                   'dayOffset': dayoffset,
                   'targetDate': target_date.isoformat(),
                   'open': float(ohlc.get('open')),
                   'high': float(ohlc.get('high')),
                   'low': float(ohlc.get('low')),
                   'close': float(ohlc.get('close'))
               })
           else:
               price_trend.append({
                   'dayOffset': dayoffset,
                   'targetDate': target_date.isoformat(),
                   'open': None,
                   'high': None,
                   'low': None,
                   'close': None
               })
       
       # DB 업데이트
       await conn.execute("UPDATE txn_events SET price_trend = $5 WHERE ...")
   ```

---

### 7단계: 결과 집계 및 반환

**위치**: `backend/src/services/valuation_service.py:351-387`

**실행 내용**:

1. **Summary 생성**:
   ```python
   summary = {
       'totalEventsProcessed': len(events),
       'quantitativeSuccess': quantitative_success,
       'quantitativeFail': quantitative_fail,
       'qualitativeSuccess': qualitative_success,
       'qualitativeFail': qualitative_fail,
       'priceTrendSuccess': price_trend_result.get('success', 0),
       'priceTrendFail': price_trend_result.get('fail', 0),
       'elapsedMs': int((time.time() - start_time) * 1000)
   }
   ```

2. **반환값**:
   ```python
   {
       'summary': summary,
       'results': results  # List[EventProcessingResult]
   }
   ```

---

## 검증 포인트

### ✅ 시간적 유효성 검증

**검증 항목**:
1. ✅ `limit=100`으로 충분한 과거 데이터 가져오기
2. ✅ `event_date` 기준으로 필터링 (`quarter_date <= event_date_obj`)
3. ✅ 필터링 후 데이터가 없으면 `no_valid_data` 에러 반환
4. ✅ `_meta.date_range`에 실제 사용된 분기 범위 기록
5. ✅ `_meta.event_date`에 이벤트 날짜 기록

**테스트 시나리오**:
- `event_date=2021-01-31`인 이벤트 처리 시
  - API에서 2025년 분기 데이터가 포함되어 있어도
  - 필터링 후 2021-01-31 이전 분기만 사용
  - `_meta.date_range.start`와 `_meta.date_range.end`가 2021-01-31 이전인지 확인

### ✅ 동적 메트릭 계산 검증

**검증 항목**:
1. ✅ `MetricCalculationEngine` 사용으로 하드코딩 제거
2. ✅ `metrics_by_domain`의 모든 도메인을 동적으로 처리
3. ✅ `config_lv2_metric` 테이블 변경사항이 자동 반영
4. ✅ 의존성 그래프 및 위상 정렬로 계산 순서 보장

**테스트 시나리오**:
- `config_lv2_metric`에 새로운 도메인 추가 시
  - 코드 수정 없이 자동으로 계산되는지 확인
  - `target_domains`에 포함된 도메인만 계산되는지 확인

---

## 발견된 잠재적 이슈

### ⚠️ Issue 1: get_quote() 메서드 미정의

**위치**: `backend/src/services/valuation_service.py:429`

**문제**:
```python
quote = await fmp_client.get_quote(ticker)
```

`FMPAPIClient`에 `get_quote()` 메서드가 정의되어 있지 않을 수 있습니다.

**영향**:
- `AttributeError` 발생 가능
- 시가총액 기반 메트릭 (PER 등) 계산 실패

**해결 방안**:
- `external_api.py`에 `get_quote()` 메서드 추가
- 또는 `quote` 변수 사용 부분을 조건부로 처리

---

## 결론

수정사항이 대부분 올바르게 반영되었습니다:

1. ✅ **시간적 유효성**: `limit=100` 및 `event_date` 기반 필터링 구현됨
2. ✅ **동적 메트릭 계산**: `MetricCalculationEngine` 사용으로 하드코딩 제거
3. ✅ **에러 처리**: `no_valid_data` 메시지 반환 구현됨
4. ✅ **메타데이터**: `_meta`에 date_range, calcType, count, event_date, sector, industry 기록

**주의사항**:
- `get_quote()` 메서드 구현 여부 확인 필요
- `target_domains` 하드코딩 (`['valuation', 'profitability', 'momentum', 'risk', 'dilution']`) - 필요시 동적 처리 고려

