# 로그 구조 최종 개선 완료

## 요청 사항 해결

### 1. ✅ RGTI API가 30번 반복 호출되지 않음 확인
**테스트 결과:**
- RGTI API: **9회만** 호출 (30회 아님)
- Peer ticker API: 9개 × 6-7회 = 54-63회
- **총 63회 API 호출**

**검증:**
```
RGTI      :   9 calls (8 unique APIs)
BILI      :   6 calls (6 unique APIs)
CACI      :   6 calls (6 unique APIs)
...
```

### 2. ✅ 모든 로그에 Row ID 추가
**이전:**
```
[API Call] fmp-balance-sheet-statement -> ...
[API Response] fmp-balance-sheet-statement -> HTTP 200
```

**개선 후:**
```
[table: txn_events | id: ticker-cache:RGTI] | [API Call] fmp-balance-sheet-statement -> ...
[table: txn_events | id: ticker-cache:RGTI] | [API Response] fmp-balance-sheet-statement -> HTTP 200
```

### 3. ✅ 명확한 로그 섹션 구분

## 새로운 로그 구조

### 1단계: TICKER-LEVEL API CACHING (일괄 호출)

```
[table: txn_events | id: ticker-cache:RGTI] | ========== TICKER-LEVEL API CACHING START ==========
[table: txn_events | id: ticker-cache:RGTI] | Fetching 7 APIs for RGTI (ONCE for all 30 events)

[table: txn_events | id: ticker-cache:RGTI] | [API Call] fmp-historical-market-capitalization -> ...
[table: txn_events | id: ticker-cache:RGTI] | [API Response] fmp-historical-market-capitalization -> HTTP 200
[table: txn_events | id: ticker-cache:RGTI] | [API Parse] fmp-historical-market-capitalization -> Type: list, Length: 1181
[table: txn_events | id: ticker-cache:RGTI] | [Schema Mapping] fmp-historical-market-capitalization -> Mapped 1181 items

[table: txn_events | id: ticker-cache:RGTI] | [API Call] fmp-quote -> ...
[table: txn_events | id: ticker-cache:RGTI] | [API Response] fmp-quote -> HTTP 200
...

[table: txn_events | id: ticker-cache:RGTI] | API cache ready: 8 APIs cached
[table: txn_events | id: ticker-cache:RGTI] | ========== TICKER-LEVEL API CACHING END ==========
```

**의미:**
- `ticker-cache:RGTI` = RGTI 자체 데이터를 30개 이벤트 전체를 위해 **한 번만** 가져옴
- 각 API는 1회만 호출되고 결과가 캐시됨

---

### 2단계: PEER TICKER DATA CACHING (Sector Average 계산용)

```
[table: txn_events | id: ticker-cache:RGTI] | ========== PEER TICKER DATA CACHING START ==========
[table: txn_events | id: ticker-cache:RGTI] | Found 9 peer tickers: ['BILI', 'CACI', 'DUOL', ...]

[table: txn_events | id: ticker-cache:RGTI:peer-BILI] | [API Call] fmp-balance-sheet-statement -> ...symbol=BILI...
[table: txn_events | id: ticker-cache:RGTI:peer-BILI] | [API Response] fmp-balance-sheet-statement -> HTTP 200
[table: txn_events | id: ticker-cache:RGTI:peer-BILI] | [API Parse] fmp-balance-sheet-statement -> Type: list, Length: 35

[table: txn_events | id: ticker-cache:RGTI:peer-ZBRA] | [API Call] fmp-income-statement -> ...symbol=ZBRA...
[table: txn_events | id: ticker-cache:RGTI:peer-ZBRA] | [API Response] fmp-income-statement -> HTTP 200
...

[table: txn_events | id: ticker-cache:RGTI] | Peer data cached: 9 peers, sector averages=['PER', 'PBR']
[table: txn_events | id: ticker-cache:RGTI] | ========== PEER TICKER DATA CACHING END ==========
```

**의미:**
- `ticker-cache:RGTI:peer-BILI` = RGTI의 sector average 계산을 위한 BILI 데이터
- Peer ticker 데이터는 priceQuantitative (적정가) 계산에 필수
- 9개 peer ticker × 6-7 API = 54-63회 호출

---

### 3단계: EVENT PROCESSING (캐시된 데이터 사용)

```
[table: txn_events | id: ticker-cache:RGTI] | ========== EVENT PROCESSING START ==========
[table: txn_events | id: ticker-cache:RGTI] | Processing 30 events using CACHED API data (no new API calls)

[table: txn_events | id: 4d102390-73fe-4a1e-9b3b-71369b3d9e02] | ---------- Event 1/30 | source=earning ----------
[table: txn_events | id: 4d102390-73fe-4a1e-9b3b-71369b3d9e02] | DEBUG | current_price=9.79, has_temp_value=True
[table: txn_events | id: 4d102390-73fe-4a1e-9b3b-71369b3d9e02] | DEBUG | priceQuantitative=45.84 (CACHED sector_avg)
[table: txn_events | id: 4d102390-73fe-4a1e-9b3b-71369b3d9e02] | Event 1/30 completed | quant=OK, qual=FAIL

[table: txn_events | id: 4740ea81-e913-4a38-aa46-f682460723de] | ---------- Event 2/30 | source=earning ----------
[table: txn_events | id: 4740ea81-e913-4a38-aa46-f682460723de] | DEBUG | current_price=10.23, has_temp_value=True
[table: txn_events | id: 4740ea81-e913-4a38-aa46-f682460723de] | Event 2/30 completed | quant=OK, qual=OK

...

[table: txn_events | id: ticker-cache:RGTI] | ========== EVENT PROCESSING END ==========
[table: txn_events | id: ticker-cache:RGTI] | Processed 30 events | quant_success=30, qual_success=10
```

**의미:**
- 각 이벤트는 **새로운 API 호출 없이** 1, 2단계에서 캐시된 데이터만 사용
- 각 이벤트마다 고유한 `txn_events.id` 표시
- 이벤트 처리 시작/완료 로그 포함

---

## Row ID 형식 정리

### 1. Ticker-level 캐싱
```
[table: txn_events | id: ticker-cache:RGTI]
```
**의미:** RGTI 전체 이벤트를 위한 일괄 API 호출

### 2. Peer ticker 캐싱
```
[table: txn_events | id: ticker-cache:RGTI:peer-BILI]
```
**의미:** RGTI의 sector average 계산을 위한 BILI 데이터 수집

### 3. 개별 이벤트 처리
```
[table: txn_events | id: 4d102390-73fe-4a1e-9b3b-71369b3d9e02]
```
**의미:** txn_events 테이블의 특정 행(이벤트) 처리

### 4. Context 없음
```
[no event context]
```
**의미:** 특정 이벤트/티커와 무관한 API 호출 (거의 발생하지 않음)

---

## API 호출 횟수 요약

**RGTI 30개 이벤트 처리 시:**

| 단계 | API 호출 대상 | 호출 횟수 | 비고 |
|------|--------------|----------|------|
| 1단계 | RGTI 자체 | 9회 | 8개 unique API + consensus |
| 2단계 | 9개 Peer ticker | 54-63회 | 각 peer × 6-7 API |
| 3단계 | 30개 이벤트 처리 | **0회** | 캐시 사용, 새 API 호출 없음 |
| **합계** | - | **63-72회** | 30개 이벤트를 위해 총 63-72회만 호출 |

**결론:**
- ✅ RGTI API는 **9회만** 호출 (30회 ✗)
- ✅ 각 이벤트 처리 시 **새로운 API 호출 없음**
- ✅ Ticker-level caching이 정상 작동

---

## 변경 사항

### backend/src/services/valuation_service.py

**Line 94-95:** Ticker-level caching 시작 로그
```python
logger.info(f"[table: txn_events | id: {ticker_context_id}] | ========== TICKER-LEVEL API CACHING START ==========")
logger.info(f"[table: txn_events | id: {ticker_context_id}] | Fetching {len(required_apis)} APIs for {ticker} (ONCE for all {len(ticker_events)} events)")
```

**Line 135-136:** Ticker-level caching 종료 로그
```python
logger.info(f"[table: txn_events | id: {ticker_context_id}] | API cache ready: {len(ticker_api_cache) + 1} APIs cached")
logger.info(f"[table: txn_events | id: {ticker_context_id}] | ========== TICKER-LEVEL API CACHING END ==========")
```

**Line 155:** Peer ticker caching 시작 로그
```python
logger.info(f"[table: txn_events | id: {ticker_context_id}] | ========== PEER TICKER DATA CACHING START ==========")
```

**Line 162:** Peer ticker 목록 로그
```python
logger.info(f"[table: txn_events | id: {ticker_context_id}] | Found {peer_count} peer tickers: {peer_tickers}")
```

**Line 169-173:** Peer ticker caching 종료 로그
```python
logger.info(f"[table: txn_events | id: {ticker_context_id}] | Peer data cached: {peer_count} peers, sector averages={list(sector_averages.keys())}")
logger.info(f"[table: txn_events | id: {ticker_context_id}] | ========== PEER TICKER DATA CACHING END ==========")
```

**Line 214-215:** 이벤트 처리 시작 로그
```python
logger.info(f"[table: txn_events | id: ticker-cache:{ticker}] | ========== EVENT PROCESSING START ==========")
logger.info(f"[table: txn_events | id: ticker-cache:{ticker}] | Processing {total_events} events using CACHED API data (no new API calls)")
```

**Line 227:** 각 이벤트 시작 로그
```python
logger.info(f"{row_context} | ---------- Event {idx}/{total_events} | source={source} ----------")
```

**Line 450:** 각 이벤트 완료 로그
```python
logger.info(f"{row_context} | Event {idx}/{total_events} completed | quant={'OK' if quant_result['status']=='success' else 'FAIL'}, qual={'OK' if qual_result['status']=='success' else 'FAIL'}")
```

**Line 571-572:** 이벤트 처리 종료 로그
```python
logger.info(f"[table: txn_events | id: ticker-cache:{ticker}] | ========== EVENT PROCESSING END ==========")
logger.info(f"[table: txn_events | id: ticker-cache:{ticker}] | Processed {total_events} events | quant_success={quant_success}, qual_success={qual_success}")
```

**Line 2124:** Peer ticker context 생성
```python
peer_context = f"{event_id}:peer-{peer_ticker}" if event_id else f"peer-{peer_ticker}"
```

---

## 검증 방법

```bash
cd backend
python test_rgti_backfill_logs.py 2>&1 | grep -E "====|----------|\[API "
```

**예상 결과:**
- 명확한 섹션 구분선 (`==========`)
- 모든 API 호출에 row ID 포함
- Peer ticker API 호출에 `:peer-TICKER` suffix
- 각 이벤트 시작/완료 로그 (`----------`)

---

## 결론

✅ **30번 호출 의심 해결:** RGTI API는 9회만 호출, ticker-level caching 정상 작동
✅ **Row ID 누락 해결:** 모든 로그에 `[table: txn_events | id: ...]` 형식 적용
✅ **로그 구조 개선:** 일괄 호출과 개별 이벤트 처리를 명확히 구분
✅ **Peer ticker 구분:** `:peer-TICKER` suffix로 peer 데이터 수집 목적 명확화

**핵심 개선:**
- 사용자는 이제 로그만 봐도 어떤 단계에서 어떤 API가 몇 번 호출되는지 명확히 파악 가능
- 각 이벤트 처리 시 새로운 API 호출이 없다는 것이 로그에서 명확히 드러남
- Row ID를 통해 모든 작업의 추적이 가능
