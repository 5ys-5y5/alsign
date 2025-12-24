# POST /backfillEventsTable 기능 작동 과정 (상세 버전)

## 개요
POST /backfillEventsTable 엔드포인트는 `txn_events` 테이블의 이벤트들에 대해 평가 지표(valuation metrics)를 계산하고 업데이트하는 기능입니다. 이 문서는 각 단계에서 호출하는 API, 사용하는 계산 방식, 그리고 실제 데이터 처리 과정을 상세히 기록합니다.

## 전체 실행 흐름

### 1단계: 요청 수신 및 파라미터 파싱
**위치**: `backend/src/routers/events.py` (105-136줄)

1. FastAPI 라우터가 POST 요청을 수신합니다.
2. `BackfillEventsTableQueryParams`를 통해 쿼리 파라미터를 검증합니다:
   - `overwrite` (optional, boolean, default: false): 전체 갱신 여부
   - `from` (optional, date): 시작 날짜 필터
   - `to` (optional, date): 종료 날짜 필터
   - `tickers` (optional, string): 쉼표로 구분된 티커 심볼 목록
3. `tickers` 파라미터를 파싱하여 리스트로 변환합니다 (`get_ticker_list()`).
4. 요청 ID를 생성하거나 미들웨어에서 전달받은 reqId를 사용합니다.
5. 로그를 기록합니다.

### 2단계: Valuation Service 호출
**위치**: `backend/src/routers/events.py` (138-146줄)

1. `valuation_service.calculate_valuations()` 함수를 호출합니다.
2. 다음 파라미터를 전달합니다:
   - `overwrite`: 전체 갱신 여부
   - `from_date`: 시작 날짜
   - `to_date`: 종료 날짜
   - `tickers`: 티커 리스트

### 3단계: Phase 1 - 메트릭 정의 로드
**위치**: `backend/src/services/valuation_service.py` (53-89줄)

1. 데이터베이스 연결 풀을 획득합니다 (`db_pool.get_pool()`).
2. `metrics.select_metric_definitions()` 함수를 호출하여 `config_lv2_metric` 테이블에서 메트릭 정의를 로드합니다.
3. 메트릭을 도메인별로 그룹화합니다 (valuation, profitability, momentum, risk, dilution 등).
4. 로드된 메트릭 정의를 `metrics_by_domain` 딕셔너리에 저장합니다.

**데이터베이스 쿼리** (`backend/src/database/queries/metrics.py` 8-57줄):
```sql
SELECT id, domain, expression, description
FROM config_lv2_metric
WHERE domain LIKE 'quantitative-%' OR domain LIKE 'qualitative-%'
ORDER BY domain, id
```

**데이터 구조 예시**:
```python
metrics_by_domain = {
    'valuation': [
        {
            'name': 'PER',  # id 컬럼
            'domain': 'quantitative-valuation',
            'formula': 'market_cap / ttm_earnings',  # expression 컬럼
            'description': 'Price to Earnings Ratio'
        },
        ...
    ],
    'profitability': [
        {
            'name': 'ROE',
            'domain': 'quantitative-profitability',
            'formula': 'net_income / shareholders_equity',
            'description': 'Return on Equity'
        },
        ...
    ],
    ...
}
```

**도메인 추출 로직**:
- `domain` 컬럼에서 `-` 이후의 suffix를 추출합니다.
- 예: `quantitative-valuation` → `valuation`
- 예: `qualitative-consensus` → `consensus`

### 4단계: Phase 2 - 이벤트 로드
**위치**: `backend/src/services/valuation_service.py` (91-133줄)

1. `metrics.select_events_for_valuation()` 함수를 호출하여 처리할 이벤트를 로드합니다.
2. 필터 조건을 적용합니다:
   - `from_date`: 이벤트 날짜가 시작 날짜 이후
   - `to_date`: 이벤트 날짜가 종료 날짜 이전
   - `tickers`: 지정된 티커만 선택
3. 로드된 이벤트가 없으면 조기 종료하고 빈 결과를 반환합니다.

**데이터베이스 쿼리** (`backend/src/database/queries/metrics.py` 60-114줄):
```sql
SELECT ticker, event_date, source, source_id,
       sector, industry,
       value_quantitative, value_qualitative,
       position_quantitative, position_qualitative,
       disparity_quantitative, disparity_qualitative
FROM txn_events
WHERE (조건에 따라 필터링)
ORDER BY ticker, event_date
```

### 5단계: Phase 3 - 각 이벤트 처리
**위치**: `backend/src/services/valuation_service.py` (156-319줄)

각 이벤트에 대해 다음 작업을 순차적으로 수행합니다:

#### 5-1. Quantitative 메트릭 계산
**위치**: `backend/src/services/valuation_service.py` (174-186줄, 390-467줄)

1. `calculate_quantitative_metrics()` 함수를 호출합니다.
2. **FMP API 호출** - Financial Modeling Prep API를 통해 분기별 재무 데이터를 가져옵니다:

   **API 엔드포인트 및 파라미터**:
   - **Income Statement**: 
     - API ID: `fmp-income-statement`
     - URL 템플릿: `https://financialmodelingprep.com/stable/income-statement?symbol={ticker}&period=quarter&limit={limit}&apikey={apiKey}`
     - 파라미터: `ticker`, `period='quarter'`, `limit=4`
     - 반환 데이터: 최근 4개 분기의 손익계산서 데이터 (날짜순 정렬, 최신이 첫 번째)
   
   - **Balance Sheet**:
     - API ID: `fmp-balance-sheet-statement`
     - URL 템플릿: `https://financialmodelingprep.com/stable/balance-sheet-statement?symbol={ticker}&period=quarter&limit={limit}&apikey={apiKey}`
     - 파라미터: `ticker`, `period='quarter'`, `limit=4`
     - 반환 데이터: 최근 4개 분기의 재무상태표 데이터
   
   - **Cash Flow**:
     - API ID: `fmp-cash-flow-statement`
     - URL 템플릿: `https://financialmodelingprep.com/stable/cash-flow-statement?symbol={ticker}&period=quarter&limit={limit}&apikey={apiKey}`
     - 파라미터: `ticker`, `period='quarter'`, `limit=4`
     - 반환 데이터: 최근 4개 분기의 현금흐름표 데이터

   **API 호출 방식**:
   - `FMPAPIClient`는 `config_lv1_api_list` 테이블에서 API 설정을 동적으로 로드합니다.
   - `config_lv1_api_service` 테이블에서 API 키를 가져옵니다.
   - Rate Limiter를 사용하여 API 호출 속도를 제한합니다 (기본값: 설정 파일의 `FMP_RATE_LIMIT`).
   - Schema Mapping을 통해 API 응답 필드명을 내부 표준 필드명으로 변환합니다.

3. **TTM(Trailing Twelve Months) 계산**:
   - 최근 4개 분기의 데이터를 합산하여 TTM 값을 계산합니다.
   - 예시: `ttm_earnings = sum([q.get('netIncome', 0) for q in income_stmt[:4]])`
   - 각 분기 데이터는 날짜순으로 정렬되어 있으며, 최신 분기가 첫 번째 인덱스입니다.

4. **도메인별 재무 비율 계산**:
   - `metrics_by_domain`에 정의된 각 메트릭의 `formula`를 파싱하여 계산합니다.
   - 현재 구현은 간소화된 버전이며, 실제 프로덕션에서는 복잡한 공식 파싱 엔진을 사용합니다.
   - 예시 계산 (PER):
     ```python
     # TTM 순이익 계산
     ttm_earnings = sum([q.get('netIncome', 0) for q in income_stmt[:4]])
     
     # 현재 주가와 발행 주식 수를 가져와서 시가총액 계산
     # market_cap = current_price * shares_outstanding
     
     # PER 계산
     # PER = market_cap / (ttm_earnings / shares_outstanding)
     # 또는 PER = (current_price * shares_outstanding) / (ttm_earnings / shares_outstanding)
     #     = current_price / (ttm_earnings / shares_outstanding)
     ```

5. **`value_quantitative` JSONB 구조 생성**:
   ```json
   {
     "valuation": {
       "PER": 25.5,
       "PBR": 3.2,
       "_meta": {
         "date_range": "2024-01-01 to 2024-10-01",
         "calcType": "TTM_fullQuarter",
         "count": 4
       }
     },
     "profitability": {
       "ROE": 0.15,
       "ROA": 0.08,
       "_meta": {
         "date_range": "2024-01-01 to 2024-10-01",
         "calcType": "TTM_fullQuarter",
         "count": 4
       }
     },
     "momentum": { ... },
     "risk": { ... },
     "dilution": { ... }
   }
   ```
   
   **메타데이터 설명**:
   - `date_range`: 사용된 분기 데이터의 날짜 범위 (가장 오래된 분기 ~ 가장 최신 분기)
   - `calcType`: 계산 방식 (`TTM_fullQuarter` = 최근 4개 분기 합산)
   - `count`: 사용된 분기 수 (일반적으로 4)

#### 5-2. Qualitative 메트릭 계산
**위치**: `backend/src/services/valuation_service.py` (188-201줄, 470-567줄)

1. `calculate_qualitative_metrics()` 함수를 호출합니다.
2. **소스 검증**: 소스가 `'consensus'`가 아니면 스킵하고 `status='skipped'`를 반환합니다.
3. **데이터베이스 쿼리** - `metrics.select_consensus_data()`를 호출하여 `evt_consensus` 테이블에서 컨센서스 데이터를 가져옵니다:

   **SQL 쿼리** (`backend/src/database/queries/metrics.py` 160-195줄):
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
   
   - `ticker`와 `event_date`로 정확히 일치하는 레코드를 조회합니다.
   - 여러 레코드가 있을 경우 가장 최신 `event_date`를 가진 레코드를 선택합니다.

4. **Phase 2 데이터 추출**:
   - `price_target`: 현재 목표 주가 (Float)
   - `price_when_posted`: 목표 주가가 게시된 시점의 실제 주가 (Float)
   - `price_target_prev`: 이전 목표 주가 (Float, nullable)
   - `price_when_posted_prev`: 이전 게시 시점 주가 (Float, nullable)
   - `direction`: 방향 (`'up'`, `'down'`, `'neutral'`)

5. **`consensusSignal` 구조 생성**:
   
   **기본 구조**:
   ```json
   {
     "consensusSignal": {
       "direction": "up",
       "last": {
         "price_target": 150.0,
         "price_when_posted": 140.0
       }
     }
   }
   ```
   
   **이전 데이터가 있는 경우 추가**:
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
   
   **Delta 계산 로직** (`backend/src/services/valuation_service.py` 534-547줄):
   ```python
   if price_target and price_target_prev:
       # 절대 변화량
       delta = float(price_target) - float(price_target_prev)
       
       # 백분율 변화량
       delta_pct = (delta / float(price_target_prev)) * 100 if price_target_prev != 0 else None
       
       consensus_signal['delta'] = delta
       consensus_signal['deltaPct'] = delta_pct
   else:
       consensus_signal['delta'] = None
       consensus_signal['deltaPct'] = None
   ```
   
   **현재 주가 반환**: `currentPrice`는 `price_when_posted` 값을 사용합니다.

#### 5-3. Position 및 Disparity 계산
**위치**: `backend/src/services/valuation_service.py` (203-212줄, 570-616줄)

1. `calculate_position_disparity()` 함수를 호출합니다. 이 함수는 Quantitative와 Qualitative 각각에 대해 한 번씩 호출됩니다.

2. **Quantitative용 position/disparity 계산**:
   - **목표 가격 추출**: `value_quantitative` 구조에서 목표 가격을 추출합니다.
     - 현재 구현에서는 `valuation` 도메인에서 목표 가격을 추출하는 로직이 플레이스홀더 상태입니다.
     - 실제 구현에서는 메트릭 정의에 따라 목표 가격을 계산합니다.
   - **현재 가격**: `qualitative_result.get('currentPrice')`를 사용합니다 (consensus의 `price_when_posted`).
   - **Position 결정 로직**:
     ```python
     if price_target > current_price:
         position = 'long'  # 목표가가 현재가보다 높으면 매수 포지션
     elif price_target < current_price:
         position = 'short'  # 목표가가 현재가보다 낮으면 매도 포지션
     else:
         position = 'neutral'  # 같으면 중립
     ```
   - **Disparity 계산**:
     ```python
     disparity = (price_target / current_price) - 1 if current_price != 0 else None
     ```
     - 예시: `price_target=150`, `current_price=140` → `disparity = (150/140) - 1 = 0.0714` (7.14% 상승 여력)

3. **Qualitative용 position/disparity 계산**:
   - **목표 가격 추출**: `value_qualitative.consensusSignal.last.price_target`에서 추출합니다.
     ```python
     if 'consensusSignal' in target_price:
         signal = target_price['consensusSignal']
         if signal and 'last' in signal:
             price_target = signal['last'].get('price_target')
     ```
   - **현재 가격**: `qualitative_result.get('currentPrice')` (즉, `price_when_posted`)를 사용합니다.
   - **Position 및 Disparity 계산**: Quantitative와 동일한 로직을 사용합니다.

4. **반환값**:
   - `position`: `'long'`, `'short'`, `'neutral'`, 또는 `None` (데이터 부족 시)
   - `disparity`: Float 값 (백분율이 아닌 소수점 값, 예: 0.0714 = 7.14%) 또는 `None`

#### 5-4. 데이터베이스 업데이트
**위치**: `backend/src/services/valuation_service.py` (214-268줄)

1. `metrics.update_event_valuations()` 함수를 호출합니다.

2. **`overwrite` 모드에 따른 SQL 쿼리** (`backend/src/database/queries/metrics.py` 198-300줄):

   **overwrite=true (전체 교체 모드)**:
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
   - 모든 필드를 새로운 값으로 완전히 교체합니다.
   - 기존에 값이 있더라도 무조건 덮어씁니다.

   **overwrite=false (부분 업데이트 모드)**:
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
   - JSONB 필드 (`value_quantitative`, `value_qualitative`): `CASE` 문을 사용하여 NULL인 경우에만 업데이트합니다.
   - 단순 타입 필드 (`position_*`, `disparity_*`): `COALESCE`를 사용하여 NULL인 경우에만 업데이트합니다.
   - 기존에 값이 있으면 유지하고, NULL인 경우에만 새 값을 채웁니다.

3. **업데이트할 필드 및 데이터 타입**:
   - `value_quantitative` (jsonb): Quantitative 메트릭 결과
   - `value_qualitative` (jsonb): Qualitative 메트릭 결과
   - `position_quantitative` (text): `'long'`, `'short'`, `'neutral'`, 또는 `NULL`
   - `position_qualitative` (text): `'long'`, `'short'`, `'neutral'`, 또는 `NULL`
   - `disparity_quantitative` (numeric): Float 값 (예: 0.0714)
   - `disparity_qualitative` (numeric): Float 값 (예: 0.0714)

4. **업데이트 결과 확인**:
   - 업데이트된 행 수를 확인합니다 (`UPDATE` 문의 반환값).
   - 0행이 업데이트되면 `ValueError("Event not found for update")`를 발생시킵니다.
   - 1행이 업데이트되면 정상 처리로 간주합니다.
   - 2행 이상이 업데이트되면 중복 레코드 오류로 간주합니다.

5. **성공/실패 카운터 업데이트**:
   ```python
   if quant_result['status'] == 'success':
       quantitative_success += 1
   elif quant_result['status'] == 'failed':
       quantitative_fail += 1
   
   if qual_result['status'] == 'success':
       qualitative_success += 1
   elif qual_result['status'] == 'failed':
       qualitative_fail += 1
   ```

6. **`EventProcessingResult` 객체 생성**:
   ```python
   EventProcessingResult(
       ticker=ticker,
       event_date=event_date.isoformat(),
       source=source,
       source_id=str(source_id),
       status='success' if (quant_result['status'] == 'success' and qual_result['status'] == 'success') else 'partial',
       quantitative={
           'status': quant_result['status'],
           'message': quant_result.get('message')
       },
       qualitative={
           'status': qual_result['status'],
           'message': qual_result.get('message')
       },
       position={
           'quantitative': position_quant,
           'qualitative': position_qual
       } if position_quant or position_qual else None,
       disparity={
           'quantitative': disparity_quant,
           'qualitative': disparity_qual
       } if disparity_quant is not None or disparity_qual is not None else None
   )
   ```
   
   **Status 값**:
   - `'success'`: Quantitative와 Qualitative 모두 성공
   - `'partial'`: 둘 중 하나만 성공 또는 둘 다 부분 성공
   - `'failed'`: 업데이트 실패 또는 예외 발생

**데이터베이스 쿼리** (`backend/src/database/queries/metrics.py` 198-300줄):
- overwrite=true: 전체 UPDATE
- overwrite=false: CASE/COALESCE를 사용한 부분 UPDATE

#### 5-5. 진행 상황 로깅
**위치**: `backend/src/services/valuation_service.py` (298-319줄)

- 10개 이벤트마다 진행 상황을 로그로 기록합니다.

### 6단계: Phase 4 - Price Trend 생성
**위치**: `backend/src/services/valuation_service.py` (321-350줄, 619-870줄)

1. `generate_price_trends()` 함수를 호출합니다.

2. **정책 설정 로드** (`backend/src/database/queries/policies.py` 67-93줄):
   - `policies.get_price_trend_range_policy()`를 호출합니다.
   - `config_lv0_policy` 테이블에서 `function='fillPriceTrend_dateRange'` 정책을 조회합니다.
   - 정책 JSON 구조:
     ```json
     {
       "countStart": -30,  // 음수: 이벤트 날짜 이전 거래일 수
       "countEnd": 30      // 양수: 이벤트 날짜 이후 거래일 수
     }
     ```
   - 예시: `countStart=-14`, `countEnd=14` → 이벤트 날짜 기준으로 과거 14거래일부터 미래 14거래일까지

3. **이벤트 로드 및 그룹화**:
   - `metrics.select_events_for_valuation()`를 호출하여 이벤트를 다시 로드합니다 (Phase 2와 동일한 쿼리).
   - 이벤트를 티커별로 그룹화합니다:
     ```python
     events_by_ticker = {}
     for event in events:
         ticker = event['ticker']
         if ticker not in events_by_ticker:
             events_by_ticker[ticker] = []
         events_by_ticker[ticker].append(event)
     ```

4. **OHLC 데이터 가져올 날짜 범위 계산**:
   - 각 티커별로 이벤트 날짜의 최소값과 최대값을 계산합니다.
   - `countStart`와 `countEnd`를 고려하여 버퍼를 추가합니다:
     ```python
     min_date = min(event_dates)
     max_date = max(event_dates)
     
     # 거래일 기준으로 대략적인 범위 계산 (실제로는 거래일만 카운트)
     from datetime import timedelta
     fetch_start = min_date + timedelta(days=count_start * 2)  # 대략적인 계산
     fetch_end = max_date + timedelta(days=count_end * 2)
     ```

5. **FMP API를 통한 OHLC 데이터 일괄 가져오기**:
   - **API 엔드포인트**:
     - API ID: `fmp-historical-price-eod-full`
     - URL 템플릿: `https://financialmodelingprep.com/stable/historical-price-full/{ticker}?from={fromDate}&to={toDate}&apikey={apiKey}`
     - 파라미터: `ticker`, `fromDate` (YYYY-MM-DD), `toDate` (YYYY-MM-DD)
   
   - **응답 구조**:
     ```json
     {
       "symbol": "AAPL",
       "historical": [
         {
           "date": "2024-01-15",
           "open": 150.0,
           "high": 152.0,
           "low": 149.0,
           "close": 151.0,
           "volume": 50000000
         },
         ...
       ]
     }
     ```
   
   - **캐싱**: 각 티커의 OHLC 데이터를 `ohlc_cache` 딕셔너리에 저장합니다 (날짜를 키로 사용).

6. **각 이벤트에 대한 Price Trend 생성**:

   **6-1. DayOffset 스캐폴드 생성** (`backend/src/services/utils/datetime_utils.py` 160-213줄):
   - `calculate_dayOffset_dates()` 함수를 호출합니다.
   - **거래일 판정 로직**:
     - `is_trading_day()`: 주말(토/일)과 `config_lv3_market_holidays` 테이블의 휴장일을 제외합니다.
     - `next_trading_day()`: 주어진 날짜 이후의 첫 거래일을 찾습니다.
     - `previous_trading_day()`: 주어진 날짜 이전의 첫 거래일을 찾습니다.
   
   - **DayOffset 계산 과정**:
     ```python
     # 1. dayOffset=0을 이벤트 날짜 이후 첫 거래일로 매핑
     base_date = await next_trading_day(event_date, exchange, pool)
     
     # 2. 음수 오프셋 생성 (과거 거래일)
     if count_start < 0:
         current = base_date
         for offset in range(0, count_start, -1):  # 0, -1, -2, ..., count_start
             if offset < 0:
                 current = await previous_trading_day(current - timedelta(days=1), exchange, pool)
             results.append((offset, current))
     
     # 3. dayOffset=0 추가
     results.append((0, base_date))
     
     # 4. 양수 오프셋 생성 (미래 거래일)
     if count_end > 0:
         current = base_date
         for offset in range(1, count_end + 1):  # 1, 2, 3, ..., count_end
             current = await next_trading_day(current + timedelta(days=1), exchange, pool)
             results.append((offset, current))
     ```
   
   - **예시**: `event_date=2024-12-15` (월요일), `countStart=-2`, `countEnd=2`
     - `base_date = 2024-12-15` (월요일이므로 거래일)
     - 결과: `[(-2, 2024-12-11), (-1, 2024-12-12), (0, 2024-12-15), (1, 2024-12-16), (2, 2024-12-17)]`

   **6-2. Price Trend 배열 생성**:
   - 각 `(dayOffset, targetDate)` 쌍에 대해:
     - `ohlc_cache`에서 해당 날짜의 OHLC 데이터를 조회합니다.
     - 데이터가 있으면 실제 값을 사용하고, 없으면 (미래 날짜 또는 데이터 누락) `null`로 채웁니다.
     ```python
     price_trend = []
     for dayoffset, target_date in dayoffset_dates:
         date_str = target_date.isoformat()
         ohlc = ohlc_cache.get(ticker, {}).get(date_str)
         
         if ohlc:
             price_trend.append({
                 'dayOffset': dayoffset,
                 'targetDate': date_str,
                 'open': float(ohlc.get('open')) if ohlc.get('open') else None,
                 'high': float(ohlc.get('high')) if ohlc.get('high') else None,
                 'low': float(ohlc.get('low')) if ohlc.get('low') else None,
                 'close': float(ohlc.get('close')) if ohlc.get('close') else None
             })
         else:
             # Progressive null-filling: 미래 날짜나 누락된 데이터는 null
             price_trend.append({
                 'dayOffset': dayoffset,
                 'targetDate': date_str,
                 'open': None,
                 'high': None,
                 'low': None,
                 'close': None
             })
     ```
   
   **최종 Price Trend 구조**:
   ```json
   [
     {
       "dayOffset": -30,
       "targetDate": "2024-01-15",
       "open": 150.0,
       "high": 152.0,
       "low": 149.0,
       "close": 151.0
     },
     {
       "dayOffset": -29,
       "targetDate": "2024-01-16",
       "open": 151.5,
       "high": 153.0,
       "low": 150.5,
       "close": 152.0
     },
     ...
     {
       "dayOffset": 0,
       "targetDate": "2024-02-15",
       "open": 155.0,
       "high": 156.0,
       "low": 154.0,
       "close": 155.5
     },
     ...
     {
       "dayOffset": 30,
       "targetDate": "2024-03-20",
       "open": null,
       "high": null,
       "low": null,
       "close": null
     }
   ]
   ```

   **6-3. 데이터베이스 업데이트**:
   ```sql
   UPDATE txn_events
   SET price_trend = $5::jsonb
   WHERE ticker = $1
     AND event_date = $2
     AND source = $3
     AND source_id = $4
   ```
   - `price_trend` 필드에 JSONB 배열을 저장합니다.
   - 업데이트된 행 수를 확인하여 성공/실패를 판단합니다.

7. **성공/실패 카운터 집계**:
   - 각 이벤트 처리 후 성공/실패를 카운트합니다.
   - 10개 이벤트마다 진행 상황을 로그로 기록합니다.

### 7단계: 결과 집계 및 반환
**위치**: `backend/src/services/valuation_service.py` (351-387줄)

1. 전체 실행 시간을 계산합니다.
2. Summary 딕셔너리를 생성합니다:
   ```python
   {
     'totalEventsProcessed': len(events),
     'quantitativeSuccess': ...,
     'quantitativeFail': ...,
     'qualitativeSuccess': ...,
     'qualitativeFail': ...,
     'priceTrendSuccess': ...,
     'priceTrendFail': ...,
     'elapsedMs': ...
   }
   ```
3. 결과 딕셔너리를 반환합니다:
   ```python
   {
     'summary': summary,
     'results': results  # List[EventProcessingResult]
   }
   ```

### 8단계: HTTP 응답 생성
**위치**: `backend/src/routers/events.py` (148-168줄)

1. Summary를 확인하여 실패한 이벤트가 있는지 확인합니다.
2. 실패가 있으면 HTTP 상태 코드를 207 (Multi-Status)로 설정합니다.
3. `BackfillEventsTableResponse` 객체를 생성합니다:
   - `reqId`: 요청 ID
   - `endpoint`: "POST /backfillEventsTable"
   - `overwrite`: overwrite 파라미터 값
   - `summary`: 집계 결과
   - `results`: 각 이벤트별 처리 결과 리스트
4. 응답을 반환합니다.

### 9단계: 에러 처리
**위치**: `backend/src/routers/events.py` (170-190줄)

- 예외가 발생하면:
  1. 에러 로그를 기록합니다.
  2. HTTP 500 에러와 함께 예외 메시지를 반환합니다.

## 주요 데이터 흐름

```
요청 파라미터
  ↓
BackfillEventsTableQueryParams 검증
  ↓
valuation_service.calculate_valuations()
  ↓
Phase 1: 메트릭 정의 로드 (config_lv2_metric)
  ↓
Phase 2: 이벤트 로드 (txn_events)
  ↓
Phase 3: 각 이벤트 처리
  ├─ Quantitative 계산 (FMP API → 재무 데이터)
  ├─ Qualitative 계산 (evt_consensus → 컨센서스 데이터)
  ├─ Position/Disparity 계산
  └─ DB 업데이트 (txn_events)
  ↓
Phase 4: Price Trend 생성 (FMP API → OHLC 데이터)
  ↓
결과 집계
  ↓
BackfillEventsTableResponse 반환
```

## 주요 함수 및 파일

- **라우터**: `backend/src/routers/events.py` - `backfill_events_table()`
- **서비스**: `backend/src/services/valuation_service.py` - `calculate_valuations()`
- **데이터베이스 쿼리**: `backend/src/database/queries/metrics.py`
- **요청 모델**: `backend/src/models/request_models.py` - `BackfillEventsTableQueryParams`
- **응답 모델**: `backend/src/models/response_models.py` - `BackfillEventsTableResponse`
- **외부 API**: `backend/src/services/external_api.py` - `FMPAPIClient`

## API 호출 요약

### 외부 API (Financial Modeling Prep)

1. **Income Statement** (각 이벤트당 1회 호출)
   - 엔드포인트: `https://financialmodelingprep.com/stable/income-statement?symbol={ticker}&period=quarter&limit=4&apikey={apiKey}`
   - 용도: 분기별 손익계산서 데이터 (최근 4분기)
   - 반환 데이터: `netIncome`, `revenue`, `operatingIncome` 등

2. **Balance Sheet** (각 이벤트당 1회 호출)
   - 엔드포인트: `https://financialmodelingprep.com/stable/balance-sheet-statement?symbol={ticker}&period=quarter&limit=4&apikey={apiKey}`
   - 용도: 분기별 재무상태표 데이터 (최근 4분기)
   - 반환 데이터: `totalAssets`, `totalLiabilities`, `totalStockholdersEquity` 등

3. **Cash Flow** (각 이벤트당 1회 호출)
   - 엔드포인트: `https://financialmodelingprep.com/stable/cash-flow-statement?symbol={ticker}&period=quarter&limit=4&apikey={apiKey}`
   - 용도: 분기별 현금흐름표 데이터 (최근 4분기)
   - 반환 데이터: `operatingCashFlow`, `freeCashFlow` 등

4. **Historical Price EOD** (티커별 1회 호출, Phase 4에서 사용)
   - 엔드포인트: `https://financialmodelingprep.com/stable/historical-price-full/{ticker}?from={fromDate}&to={toDate}&apikey={apiKey}`
   - 용도: 과거 일별 OHLC 가격 데이터
   - 반환 데이터: 날짜별 `open`, `high`, `low`, `close`, `volume`

### 데이터베이스 쿼리

1. **메트릭 정의 조회**: `config_lv2_metric` 테이블
2. **이벤트 조회**: `txn_events` 테이블 (필터링: 날짜 범위, 티커)
3. **컨센서스 데이터 조회**: `evt_consensus` 테이블
4. **정책 조회**: `config_lv0_policy` 테이블 (price trend 범위)
5. **거래일 판정**: `config_lv3_market_holidays` 테이블
6. **이벤트 업데이트**: `txn_events` 테이블 (valuation 필드들)

## 계산 방식 요약

### Quantitative 메트릭 계산

1. **TTM (Trailing Twelve Months) 계산**:
   - 최근 4개 분기의 데이터를 합산
   - 예: `ttm_earnings = sum([q.get('netIncome', 0) for q in income_stmt[:4]])`

2. **재무 비율 계산**:
   - `config_lv2_metric` 테이블의 `expression` 필드에 정의된 공식을 파싱하여 계산
   - 도메인별로 그룹화하여 저장 (valuation, profitability, momentum, risk, dilution)

### Qualitative 메트릭 계산

1. **Consensus Signal 추출**:
   - `evt_consensus` 테이블의 Phase 2 데이터 사용
   - `direction`, `price_target`, `price_when_posted` 추출

2. **Delta 계산**:
   - 절대 변화량: `delta = price_target - price_target_prev`
   - 백분율 변화량: `deltaPct = (delta / price_target_prev) * 100`

### Position 및 Disparity 계산

1. **Position 결정**:
   - `price_target > current_price` → `'long'`
   - `price_target < current_price` → `'short'`
   - `price_target == current_price` → `'neutral'`

2. **Disparity 계산**:
   - 공식: `disparity = (price_target / current_price) - 1`
   - 결과: 소수점 값 (예: 0.0714 = 7.14% 상승 여력)

### Price Trend 생성

1. **DayOffset 계산**:
   - `dayOffset=0`을 이벤트 날짜 이후 첫 거래일로 매핑
   - 음수 오프셋: 과거 거래일 (주말/휴장일 제외)
   - 양수 오프셋: 미래 거래일 (주말/휴장일 제외)

2. **거래일 판정**:
   - 주말 (토/일) 제외
   - `config_lv3_market_holidays` 테이블의 휴장일 제외

3. **OHLC 데이터 매핑**:
   - 각 `dayOffset`에 해당하는 날짜의 OHLC 데이터를 조회
   - 데이터가 없으면 (미래 날짜 또는 누락) `null`로 채움

## 성능 고려사항

1. **API 호출 최적화**:
   - Phase 4에서 티커별로 OHLC 데이터를 일괄 가져와서 캐싱
   - Rate Limiter를 사용하여 API 호출 속도 제한

2. **데이터베이스 최적화**:
   - Connection Pool 사용
   - 인덱스 활용 (ticker, event_date, source, source_id)

3. **진행 상황 모니터링**:
   - 10개 이벤트마다 진행 상황 로그 기록
   - 각 단계별 경과 시간 추적

