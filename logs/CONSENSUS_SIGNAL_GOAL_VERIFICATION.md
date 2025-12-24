# consensusSignal 목표 달성 여부 점검

## 목표 요약

consensusSignal은 다음 목표를 달성해야 합니다:

1. **txn_events 테이블의 현재 행에서 원본 정보 찾기**:
   - `source = 'consensus'` (또는 `'evt_consensus'`)
   - `source_id = evt_consensus.id` (예: `c34c18f6-0314-42d3-9ba0-5c907aecdca0`)
   - → `evt_consensus` 테이블에서 `id = source_id`인 행을 찾음

2. **같은 애널리스트의 과거 값 찾기**:
   - 찾은 행의 `ticker`, `analyst_name`, `analyst_company`를 기준으로
   - 같은 값들을 가진 행들 중에서
   - `event_date`로 내림차순 정렬했을 때
   - 현재 행보다 과거의 값(prev)을 찾음

3. **변화 계산**:
   - `price_target`의 변화: `current - prev`
   - `price_when_posted`의 변화: `current - prev`
   - 같은 회사 소속 애널리스트의 변화만 비교 (analyst_name, analyst_company가 다르면 비교 불가)

## 현재 구현 분석

### ✅ 올바르게 구현된 부분

#### 1. evt_consensus Phase 2 계산 (`source_data_service.py:256-298`)

**구현 내용**:
```python
# partition별로 (ticker, analyst_name, analyst_company)로 그룹화
for partition in target_partitions:
    ticker, analyst_name, analyst_company = partition
    
    # 같은 partition의 모든 이벤트를 event_date DESC로 정렬
    events = await consensus.select_partition_events(pool, ticker, analyst_name, analyst_company)
    
    # 각 행에 대해 이전 행(prev)을 찾아서 계산
    for i, event in enumerate(events):
        if i < len(events) - 1:
            prev_event = events[i + 1]  # DESC 정렬이므로 다음 인덱스가 과거
            price_target_prev = prev_event['price_target']
            price_when_posted_prev = prev_event['price_when_posted']
            direction = 'up' if event['price_target'] > price_target_prev else 'down'
```

**목표 달성 여부**: ✅ **완벽히 일치**
- 같은 `ticker`, `analyst_name`, `analyst_company`로 partition 생성
- `event_date DESC`로 정렬하여 현재 행보다 과거의 값을 찾음
- 같은 애널리스트의 변화만 비교

### ❌ 문제가 있는 부분

#### 1. consensusSignal 생성 시 source_id 미사용 (`valuation_service.py:575-677`)

**현재 구현**:
```python
async def calculate_qualitative_metrics(
    pool,
    ticker: str,
    event_date,
    source: str  # source_id를 받지 않음!
) -> Dict[str, Any]:
    # ...
    consensus_data = await metrics.select_consensus_data(pool, ticker, event_date)
    # source_id를 사용하지 않음!
```

**문제점**:
- `source_id` 파라미터를 받지 않음
- `select_consensus_data()`가 `ticker`와 `event_date`만으로 조회
- 같은 `ticker`와 `event_date`에 여러 analyst가 있을 수 있는데, `LIMIT 1`로 하나만 가져옴
- **잘못된 행을 선택할 수 있음**

**지침 요구사항 확인** (`1_guideline(function).ini:815-819`):
```
- [table.events] 매칭 키(이벤트 행)
    - ticker = evt_consensus.ticker
    - source = 'evt_consensus'
    - source_id = evt_consensus.id  ← 명시적으로 source_id 사용 요구
    - event_date = evt_consensus.event_date
```

#### 2. select_consensus_data() 함수 (`metrics.py:169-204`)

**현재 구현**:
```python
async def select_consensus_data(
    pool: asyncpg.Pool,
    ticker: str,
    event_date
    # source_id를 받지 않음!
) -> Dict[str, Any]:
    row = await conn.fetchrow(
        """
        SELECT ticker, event_date, analyst_name, analyst_company,
               price_target, price_when_posted,
               price_target_prev, price_when_posted_prev,
               direction, response_key
        FROM evt_consensus
        WHERE ticker = $1
          AND event_date = $2
        ORDER BY event_date DESC
        LIMIT 1  ← 문제: 여러 행이 있을 수 있음
        """,
        ticker,
        event_date
    )
```

**문제점**:
- `source_id`를 사용하지 않아서 정확한 행을 찾을 수 없음
- 같은 `ticker`와 `event_date`에 여러 analyst가 있으면 어떤 것을 선택할지 불명확

## 수정 방안

### 1. select_consensus_data() 함수 수정

**수정 전**:
```python
async def select_consensus_data(
    pool: asyncpg.Pool,
    ticker: str,
    event_date
) -> Dict[str, Any]:
```

**수정 후**:
```python
async def select_consensus_data(
    pool: asyncpg.Pool,
    ticker: str,
    event_date,
    source_id: str  # 추가
) -> Dict[str, Any]:
    """
    Select consensus data for qualitative calculation.
    
    Uses source_id to find the exact row in evt_consensus table.
    This ensures we get the correct analyst's data when multiple
    analysts have events on the same date.
    
    Args:
        pool: Database connection pool
        ticker: Ticker symbol
        event_date: Event date
        source_id: evt_consensus.id (UUID string)
    
    Returns:
        Consensus data dictionary or None
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, ticker, event_date, analyst_name, analyst_company,
                   price_target, price_when_posted,
                   price_target_prev, price_when_posted_prev,
                   direction, response_key
            FROM evt_consensus
            WHERE id = $1
              AND ticker = $2
              AND event_date = $3
            """,
            source_id,  # 정확한 행을 찾기 위해 id 사용
            ticker,
            event_date
        )
        
        return dict(row) if row else None
```

### 2. calculate_qualitative_metrics() 함수 수정

**수정 전**:
```python
async def calculate_qualitative_metrics(
    pool,
    ticker: str,
    event_date,
    source: str
) -> Dict[str, Any]:
    # ...
    consensus_data = await metrics.select_consensus_data(pool, ticker, event_date)
```

**수정 후**:
```python
async def calculate_qualitative_metrics(
    pool,
    ticker: str,
    event_date,
    source: str,
    source_id: str  # 추가
) -> Dict[str, Any]:
    """
    Calculate qualitative metrics (consensusSignal).
    
    Uses source_id to find the exact evt_consensus row,
    ensuring we compare the same analyst's previous values.
    
    Args:
        pool: Database connection pool
        ticker: Ticker symbol
        event_date: Event date
        source: Source table name ('consensus' or 'evt_consensus')
        source_id: evt_consensus.id (UUID string)
    
    Returns:
        Dict with status, value (jsonb), currentPrice, message
    """
    try:
        # Only calculate for consensus events
        if source not in ('consensus', 'evt_consensus'):
            return {
                'status': 'skipped',
                'value': None,
                'currentPrice': None,
                'message': 'Not a consensus event'
            }
        
        # Fetch consensus data using source_id for exact row match
        consensus_data = await metrics.select_consensus_data(
            pool, ticker, event_date, source_id
        )
        
        if not consensus_data:
            return {
                'status': 'failed',
                'value': None,
                'currentPrice': None,
                'message': f'Consensus data not found for source_id={source_id}'
            }
        
        # ... 나머지 로직은 동일
```

### 3. calculate_valuations() 함수에서 호출 부분 수정

**수정 전** (`valuation_service.py:191`):
```python
qual_result = await calculate_qualitative_metrics(
    pool, ticker, event_date, source
)
```

**수정 후**:
```python
qual_result = await calculate_qualitative_metrics(
    pool, ticker, event_date, source, source_id  # source_id 추가
)
```

## 검증

### 수정 후 동작 흐름

1. **txn_events 행 처리**:
   ```
   ticker = 'AAPL'
   event_date = '2025-12-08'
   source = 'consensus'
   source_id = 'c34c18f6-0314-42d3-9ba0-5c907aecdca0'
   ```

2. **evt_consensus에서 정확한 행 찾기**:
   ```sql
   SELECT * FROM evt_consensus
   WHERE id = 'c34c18f6-0314-42d3-9ba0-5c907aecdca0'
     AND ticker = 'AAPL'
     AND event_date = '2025-12-08'
   ```
   → 정확한 analyst의 행을 찾음 (예: analyst_name='John Doe', analyst_company='ABC Securities')

3. **Phase 2에서 이미 계산된 prev 값 사용**:
   - `price_target_prev`: 같은 partition(ticker, analyst_name, analyst_company)의 이전 행에서 계산됨
   - `price_when_posted_prev`: 같은 partition의 이전 행에서 계산됨
   - `direction`: 'up' 또는 'down' 또는 null

4. **consensusSignal 생성**:
   - `last`: 현재 행의 값
   - `prev`: Phase 2에서 계산된 prev 값 (같은 애널리스트의 과거 값)
   - `delta`: `last - prev`
   - `deltaPct`: `delta / prev * 100`

## 결론

### 현재 상태
- ❌ **목표를 완전히 달성하지 못함**
- 문제: `source_id`를 사용하지 않아서 같은 날짜에 여러 analyst가 있으면 잘못된 행을 선택할 수 있음

### 수정 후
- ✅ **목표를 완전히 달성 가능**
- `source_id`로 정확한 행을 찾음
- 그 행의 `analyst_name`, `analyst_company`를 기준으로 Phase 2에서 이미 계산된 prev 값을 사용
- 같은 애널리스트의 변화만 비교

### 지침 준수 여부
- ✅ evt_consensus Phase 2 계산: 지침 완벽 준수
- ❌ consensusSignal 생성: `source_id` 사용 누락으로 지침 미준수
- 수정 후: 지침 완벽 준수


