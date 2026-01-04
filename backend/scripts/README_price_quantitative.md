# Price Quantitative Column Migration

## Overview
I-42 해결의 일환으로 `txn_events` 테이블에 `price_quantitative`와 `peer_quantitative` 컬럼을 추가하여 JSONB에서 값을 쉽게 조회할 수 있도록 합니다.

## Migration Steps

### 1. 컬럼 추가 및 인덱스 생성
```sql
-- 실행: psql 또는 pgAdmin에서 실행
\i backend/scripts/add_price_quantitative_columns.sql
```

또는 Python을 사용:
```bash
cd backend
python -c "
import asyncio
import asyncpg
import os

async def add_columns():
    # Load DB URL from .env
    env_vars = {}
    with open('.env') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, val = line.split('=', 1)
                env_vars[key] = val.strip('\"')

    conn = await asyncpg.connect(env_vars['DATABASE_URL'], statement_cache_size=0)

    # Add columns
    await conn.execute('ALTER TABLE txn_events ADD COLUMN IF NOT EXISTS price_quantitative NUMERIC')
    await conn.execute('ALTER TABLE txn_events ADD COLUMN IF NOT EXISTS peer_quantitative JSONB')

    # Add indexes
    await conn.execute('CREATE INDEX IF NOT EXISTS idx_txn_events_price_quantitative ON txn_events(price_quantitative) WHERE price_quantitative IS NOT NULL')
    await conn.execute('CREATE INDEX IF NOT EXISTS idx_txn_events_ticker_price ON txn_events(ticker, price_quantitative) WHERE price_quantitative IS NOT NULL')

    print('Columns and indexes created successfully!')
    await conn.close()

asyncio.run(add_columns())
"
```

### 2. 기존 데이터 백필
```bash
cd backend
python -c "
import asyncio
import asyncpg
import os

async def backfill():
    env_vars = {}
    with open('.env') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, val = line.split('=', 1)
                env_vars[key] = val.strip('\"')

    conn = await asyncpg.connect(env_vars['DATABASE_URL'], statement_cache_size=0)

    with open('scripts/backfill_price_quantitative.sql', 'r', encoding='utf-8') as f:
        sql_content = f.read()

    statements = [s.strip() for s in sql_content.split(';') if s.strip()]

    for stmt in statements:
        if stmt:
            result = await conn.execute(stmt)
            print(f'Executed: {result}')

    await conn.close()

asyncio.run(backfill())
"
```

## Usage Examples

### 간단한 조회
```sql
-- priceQuantitative 값으로 이벤트 조회
SELECT
    ticker,
    event_date::date,
    price_quantitative,
    position_quantitative,
    disparity_quantitative
FROM txn_events
WHERE price_quantitative IS NOT NULL
ORDER BY event_date DESC
LIMIT 10;
```

### JSONB와 비교 검증
```sql
-- 추출된 컬럼과 JSONB 원본 비교
SELECT
    ticker,
    event_date::date,
    price_quantitative,
    (value_quantitative->'valuation'->>'priceQuantitative')::numeric as jsonb_price,
    CASE
        WHEN price_quantitative = (value_quantitative->'valuation'->>'priceQuantitative')::numeric
        THEN 'MATCH ✓'
        ELSE 'MISMATCH ✗'
    END as validation
FROM txn_events
WHERE ticker = 'RGTI'
  AND event_date >= '2025-12-17'
  AND source = 'consensus';
```

### 특정 가격 범위 필터링
```sql
-- 저평가된 종목 찾기 (negative price → undervalued)
SELECT
    ticker,
    event_date::date,
    price_quantitative as fair_value,
    position_quantitative,
    disparity_quantitative
FROM txn_events
WHERE price_quantitative < 0
  AND position_quantitative = 'short'
ORDER BY disparity_quantitative ASC
LIMIT 20;
```

### Ticker별 평균 Fair Value
```sql
SELECT
    ticker,
    COUNT(*) as event_count,
    AVG(price_quantitative) as avg_fair_value,
    MIN(price_quantitative) as min_fair_value,
    MAX(price_quantitative) as max_fair_value,
    STDDEV(price_quantitative) as stddev_fair_value
FROM txn_events
WHERE price_quantitative IS NOT NULL
  AND event_date >= NOW() - INTERVAL '30 days'
GROUP BY ticker
ORDER BY avg_fair_value ASC;
```

## Automatic Updates

향후 backfill 시 자동으로 `price_quantitative`를 업데이트하려면 `valuation_service.py`를 수정:

```python
# backend/src/services/valuation_service.py
# batch_updates.append() 부분에 추가:

batch_updates.append({
    'value_quantitative': value_quant,
    'value_qualitative': value_qual,
    'position_quantitative': position_quant,
    'position_qualitative': position_qual,
    'disparity_quantitative': disparity_quant,
    'disparity_qualitative': disparity_qual,
    # I-42: Extract priceQuantitative to dedicated column
    'price_quantitative': value_quant.get('valuation', {}).get('priceQuantitative') if value_quant else None,
    'peer_quantitative': {
        'peerCount': value_quant.get('valuation', {}).get('_meta', {}).get('peerCount'),
        'sectorAvg': value_quant.get('valuation', {}).get('_meta', {}).get('sectorAvg')
    } if value_quant and value_quant.get('valuation', {}).get('_meta') else None,
    # ... other fields
})
```

그리고 `metrics.py`의 UPDATE 쿼리 수정:
```python
# backend/src/database/queries/metrics.py
# batch_update_event_valuations() 함수의 UPDATE 쿼리에 추가:

query = """
    WITH batch_data AS (
        SELECT * FROM UNNEST($1::text[], $2::timestamptz[], $3::text[], $4::text[],
                           $5::jsonb[], $6::jsonb[], $7::text[], $8::text[],
                           $9::numeric[], $10::numeric[],
                           $11::numeric[], $12::jsonb[])  -- 추가!
        AS t(ticker, event_date, source, source_id,
             value_quantitative, value_qualitative,
             position_quantitative, position_qualitative,
             disparity_quantitative, disparity_qualitative,
             price_quantitative, peer_quantitative)  -- 추가!
    )
    UPDATE txn_events e
    SET value_quantitative = b.value_quantitative,
        value_qualitative = b.value_qualitative,
        position_quantitative = b.position_quantitative::"position",
        position_qualitative = b.position_qualitative::"position",
        disparity_quantitative = b.disparity_quantitative,
        disparity_qualitative = b.disparity_qualitative,
        price_quantitative = b.price_quantitative,  -- 추가!
        peer_quantitative = b.peer_quantitative     -- 추가!
    FROM batch_data b
    WHERE e.ticker = b.ticker ...
"""
```

## Verification

현재 상태 확인:
```bash
cd backend
python -c "
import asyncio
import asyncpg
import os

async def verify():
    env_vars = {}
    with open('.env') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, val = line.split('=', 1)
                env_vars[key] = val.strip('\"')

    conn = await asyncpg.connect(env_vars['DATABASE_URL'], statement_cache_size=0)

    row = await conn.fetchrow('''
        SELECT
            ticker,
            event_date,
            price_quantitative,
            position_quantitative,
            disparity_quantitative,
            (value_quantitative->''valuation''->>>''priceQuantitative'')::numeric as jsonb_price
        FROM txn_events
        WHERE ticker = \$1
          AND event_date >= ''2025-12-17''::timestamptz
          AND event_date < ''2025-12-18''::timestamptz
          AND source = \$2
        LIMIT 1
    ''', 'RGTI', 'consensus')

    if row:
        print(f'Ticker: {row[0]}')
        print(f'Date: {row[1]}')
        print(f'price_quantitative (column): {row[2]}')
        print(f'JSONB source: {row[5]}')
        print(f'Match: {row[2] == row[5]}')

    await conn.close()

asyncio.run(verify())
"
```

## Benefits

1. **쿼리 성능 향상**: JSONB 추출 없이 바로 numeric 값 사용
2. **인덱스 활용**: price_quantitative에 인덱스가 있어 빠른 필터링/정렬
3. **간단한 SQL**: 복잡한 JSONB 경로 대신 단순 컬럼명 사용
4. **타입 안정성**: NUMERIC 타입으로 명확한 타입 보장

## Rollback

필요시 컬럼 제거:
```sql
DROP INDEX IF EXISTS idx_txn_events_price_quantitative;
DROP INDEX IF EXISTS idx_txn_events_ticker_price;
ALTER TABLE txn_events DROP COLUMN IF EXISTS price_quantitative;
ALTER TABLE txn_events DROP COLUMN IF EXISTS peer_quantitative;
```
