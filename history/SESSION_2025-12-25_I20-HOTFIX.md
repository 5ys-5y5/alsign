# 🚨 긴급 수정: I-20 API 캐싱 미작동 (2025-12-25)

## 문제 발견

I-20 초기 구현 후 실제 운영 테스트에서 **치명적 결함** 발견:

### 📊 증상
```
300개 대상 처리에 30분 이상 소요
NVDA ticker에 대해 동일 API 반복 호출 확인:
- Line 290-321: NVDA event 1 → API 6회 호출
- Line 397-427: NVDA event 2 → API 6회 재호출!
- Line 503-533: NVDA event 3 → API 6회 재호출!
```

**결과**: API 캐싱이 전혀 작동하지 않음!

---

## 🔍 근본 원인

### 잘못된 구현
```python
# process_ticker_batch() - 기존 코드
for event in ticker_events:
    # ❌ 매 이벤트마다 API 호출!
    quant_result = await calculate_quantitative_metrics(
        pool, ticker, event_date, metrics_by_domain
    )
```

**문제**:
1. `calculate_quantitative_metrics()`는 **내부에서 FMP API를 호출**
2. Ticker 배치를 만들었지만, **실제 캐싱은 구현 안 됨**
3. 매 이벤트마다 동일한 API를 반복 호출

### 예상 vs 실제

| 항목 | 예상 | 실제 |
|------|------|------|
| NVDA 30개 이벤트 | API 6회 (ticker당 1회) | API 180회 (30×6) |
| 성능 | 99% 개선 | **0% 개선** |

---

## ✅ 긴급 수정

### 1. 실제 API 캐싱 구현

**파일**: `backend/src/services/valuation_service.py`

#### A. Ticker 단위로 API 한 번만 호출

```python
async def process_ticker_batch(...):
    # ========================================
    # CRITICAL: Fetch API data ONCE for ticker
    # ========================================
    ticker_api_cache = {}
    async with FMPAPIClient() as fmp_client:
        for api_id in required_apis:
            params = {'ticker': ticker}
            
            if 'historical-price' in api_id:
                params['fromDate'] = '2000-01-01'
                params['toDate'] = datetime.now().strftime('%Y-%m-%d')
            else:
                params['period'] = 'quarter'
                params['limit'] = 100
            
            result = await fmp_client.call_api(api_id, params)
            ticker_api_cache[api_id] = result  # ✅ 캐시에 저장!
    
    logger.info(f"[Ticker Batch] {ticker}: API cache ready ({len(ticker_api_cache)} APIs)")
```

#### B. 캐시 사용 함수 추가

```python
async def calculate_quantitative_metrics_cached(
    pool, ticker, event_date, metrics_by_domain,
    api_cache: Dict[str, List[Dict[str, Any]]]  # ✅ 캐시 전달!
) -> Dict[str, Any]:
    """
    Calculate metrics using pre-fetched API cache.
    NO API CALLS!
    """
    # Use cached API data (NO API CALLS!)
    api_data_raw = api_cache
    
    # Filter by event_date (temporal validity)
    api_data_filtered = {}
    for api_id, records in api_data_raw.items():
        # ... 날짜 필터링 ...
        api_data_filtered[api_id] = filtered
    
    # Calculate metrics
    result = engine.calculate_all(api_data_filtered, target_domains)
    
    return {'status': 'success', 'value': result}
```

#### C. 이벤트 처리에서 캐시 사용

```python
async def process_ticker_batch(...):
    # 1. API 캐시 생성 (한 번만)
    ticker_api_cache = {...}
    
    # 2. 모든 이벤트에 캐시 재사용
    for event in ticker_events:
        # ✅ 캐시된 데이터 사용!
        quant_result = await calculate_quantitative_metrics_cached(
            pool, ticker, event_date, metrics_by_domain,
            ticker_api_cache  # 캐시 전달!
        )
```

### 2. 에러 수정

**에러**:
```
[QualitativeMetrics] Failed: module 'src.database.queries.metrics' has no attribute 'select_metrics_by_domains'
```

**수정**:
```python
# Before
consensus_summary_metrics = await metrics_queries.select_metrics_by_domains(...)  # ❌ 존재하지 않는 함수

# After
async with FMPAPIClient() as fmp_client:
    consensus_target_data = await fmp_client.call_api(
        'fmp-price-target-consensus', {'ticker': ticker}
    )  # ✅ 직접 API 호출로 단순화
```

---

## 📊 예상 성능 개선

### Before (Hotfix 전)
```
NVDA ticker (30 이벤트):
- API 호출: 30 × 6 = 180회
- 소요 시간: ~60초 (이벤트당 2초)
```

### After (Hotfix 후)
```
NVDA ticker (30 이벤트):
- API 호출: 1 × 6 = 6회 (ticker당 1회!)
- 소요 시간: ~6초 + 30초(처리) = 36초
- 개선율: 40% 단축
```

### 전체 (300개 대상)
```
Before: 30분 이상
After: 10-15분 (예상)
개선율: 50-67% 단축
```

---

## 🔑 핵심 차이점

| 항목 | 초기 구현 | Hotfix 후 |
|------|----------|-----------|
| **API 호출** | 매 이벤트마다 | Ticker당 1회 |
| **캐싱** | 없음 (빈 껍데기) | 실제 구현됨 |
| **함수** | `calculate_quantitative_metrics()` | `calculate_quantitative_metrics_cached()` |
| **성능** | 0% 개선 | 50-67% 개선 |

---

## 🎓 교훈

### 1. **"배치 처리" ≠ "캐싱"**
- Ticker 단위로 그룹화 ✅
- 하지만 실제 API 캐싱은 별도 구현 필요 ✅

### 2. **테스트의 중요성**
- 소규모 테스트에서 로그 확인 필수
- 동일 ticker 반복 호출 여부 확인

### 3. **함수 분리**
- `calculate_quantitative_metrics()` (원본, API 호출)
- `calculate_quantitative_metrics_cached()` (캐싱, API 호출 없음)
- 명확한 역할 분리

---

## 📝 코드 변경 사항

**파일**: `backend/src/services/valuation_service.py`

### 추가된 함수
1. `calculate_quantitative_metrics_cached()` (80줄)
   - API 캐시를 받아서 메트릭 계산
   - API 호출 없음

### 수정된 함수
1. `process_ticker_batch()`
   - Ticker당 API 한 번만 호출
   - 모든 이벤트에 캐시 재사용
   
2. `calculate_qualitative_metrics()`
   - `select_metrics_by_domains` 호출 제거
   - 직접 FMP API 호출로 단순화

---

## 🧪 테스트 권장

```http
# 1. 단일 ticker (이벤트 많은 종목)
POST /backfillEventsTable?tickers=NVDA

# 예상: API 6회만 호출, 로그에서 "API cache ready" 확인
```

---

*작성일: 2025-12-25*
*긴급 수정: I-20 API 캐싱 미작동 해결*
*예상 성능: 30분+ → 10-15분 (50-67% 개선)*

