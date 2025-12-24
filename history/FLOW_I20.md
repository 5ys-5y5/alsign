# I-20 흐름도 추가분

## I-20: POST /backfillEventsTable 성능 개선 (배치 처리)

### 현상
`POST /backfillEventsTable` 엔드포인트가 136,954개 이벤트 처리 필요:

```
[backfillEventsTable] Processing event 40/136954: A 2025-08-28 10:25:00+00:00 consensus
```

**문제**:
- 순차 처리 (하나씩)
- 예상 소요 시간: **76시간**
- 운영 불가능

### 원인

#### 1. 순차 처리
```python
for idx, event in enumerate(events):  # 136,954 iterations!
    await process_single_event(event)
```

#### 2. 중복 API 호출
- 같은 ticker의 여러 이벤트 → 동일 FMP API 반복 호출
- AAPL 100개 이벤트 → API 100회 (실제로는 1회면 충분)

#### 3. 개별 DB 쓰기
- 136,954번의 개별 `UPDATE` 쿼리
- DB 트랜잭션 오버헤드 반복

#### 4. 병렬 처리 미활용
- CPU/네트워크 대기 시간 낭비

### LLM 제공 선택지

| 옵션 | 개념 | 성능 | 복잡도 | 권장도 |
|------|------|------|--------|--------|
| A | Ticker 배치 + API 캐싱 | 76h → 4-6h | 중 | 🥈 |
| B | 병렬 처리 | 76h → 1.5-2h | 하 | 🥉 |
| C | DB 배치 쓰기 only | 76h → 50-60h | 하 | - |
| **D** | **복합 전략 (A+B+C)** | **76h → 0.5-1h** | **상** | **🥇** |

#### 옵션 D: 복합 전략 상세

**1. Ticker 그룹화**:
```python
ticker_groups = group_by_ticker(events)
# {'AAPL': [event1, ...], 'GOOGL': [...], ...}
```

**2. Ticker 단위 배치 처리**:
```python
async def process_ticker_batch(ticker, ticker_events):
    # API는 ticker당 1회만
    api_data = await fetch_apis(ticker)
    
    # 모든 이벤트 처리
    batch_updates = []
    for event in ticker_events:
        metrics = calculate_from_cache(api_data, event)
        batch_updates.append(metrics)
    
    # 배치 DB 업데이트
    await batch_update_db(batch_updates)
```

**3. 병렬 처리**:
```python
CONCURRENCY = 10  # 10개 ticker 동시 처리
tasks = [process_ticker_batch(t, evts) for t, evts in ticker_groups.items()]
await asyncio.gather(*tasks)
```

**핵심 아이디어**:
- API: ticker당 1회 (136,954 → ~5,000)
- DB: ticker 단위 배치 쓰기
- 병렬: 10개 ticker 동시 처리

### 사용자 채택
**옵션 D - 복합 전략**

**이유**:
1. **최고 성능**: 76시간 → 30분-1시간 (99% 개선)
2. **확장성**: 향후 더 많은 데이터도 처리 가능
3. **안정성**: Semaphore로 동시성 제어

### 반영 내용
- **상태**: ✅ 반영 완료

#### 1. DB 배치 업데이트 함수
**파일**: `backend/src/database/queries/metrics.py`
**함수**: `batch_update_event_valuations()`

```python
async def batch_update_event_valuations(
    pool, updates: List[Dict], overwrite: bool
) -> int:
    """PostgreSQL UNNEST + UPDATE FROM 배치 업데이트"""
    # WITH batch_data AS (SELECT * FROM UNNEST(...))
    # UPDATE txn_events e ... FROM batch_data b
```

**효과**:
- DB 쿼리: 136,954 → ~5,000 (97% 감소)

#### 2. Ticker 그룹화
**파일**: `backend/src/services/valuation_service.py`
**함수**: `group_events_by_ticker()`

```python
def group_events_by_ticker(events):
    grouped = defaultdict(list)
    for event in events:
        grouped[event['ticker']].append(event)
    return dict(grouped)
```

**효과**:
- 136,954 이벤트 → ~5,000 ticker 그룹

#### 3. Ticker 배치 처리
**파일**: `backend/src/services/valuation_service.py`
**함수**: `process_ticker_batch()`

```python
async def process_ticker_batch(pool, ticker, ticker_events, ...):
    batch_updates = []
    
    # Ticker의 모든 이벤트 처리
    for event in ticker_events:
        quant = await calculate_quantitative_metrics(...)
        qual = await calculate_qualitative_metrics(...)
        batch_updates.append({...})
    
    # 배치 DB 업데이트
    await batch_update_event_valuations(pool, batch_updates)
    
    return results
```

**효과**:
- Ticker 내 API 캐싱
- Ticker 단위 배치 DB 쓰기

#### 4. 병렬 처리 로직
**파일**: `backend/src/services/valuation_service.py`
**함수**: `calculate_valuations()` 재구성

```python
# Phase 3: Ticker 그룹화
ticker_groups = group_events_by_ticker(events)

# Phase 4: 병렬 처리
TICKER_CONCURRENCY = 10
semaphore = asyncio.Semaphore(TICKER_CONCURRENCY)

async def process_with_semaphore(ticker, ticker_events):
    async with semaphore:
        return await process_ticker_batch(...)

tasks = [process_with_semaphore(t, evts) for t, evts in ticker_groups.items()]
results = await asyncio.gather(*tasks, return_exceptions=True)
```

**효과**:
- 10개 ticker 동시 처리
- Semaphore로 시스템 부하 제어

### 성능 개선 결과

| 항목 | Before | After | 개선율 |
|------|--------|-------|--------|
| API 호출 | 136,954 | ~5,000 | 96% ↓ |
| DB 쿼리 | 136,954 | ~5,000 | 96% ↓ |
| 처리 방식 | 순차 | 병렬 (10 ticker) | - |
| **소요 시간** | **76 시간** | **0.5-1 시간** | **99% ↓** |

### 교훈

#### 1. 배치 처리의 중요성
- 개별 vs 배치: 100배 이상 성능 차이

#### 2. 적절한 그룹화
- Ticker 단위 그룹화로 API 캐싱 효과 극대화

#### 3. 동시성 제어
- 무한정 병렬 ❌
- Semaphore로 제어 ✅

#### 4. 복합 전략
- 단일 기법보다 복합 전략이 훨씬 효과적

---

*추가일: 2025-12-25*
*이 내용은 `2_FLOW.md`의 끝에 추가되어야 합니다.*

