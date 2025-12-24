# consensusSignal 전체 흐름 분석

## 1. 개요

`consensusSignal`은 애널리스트의 목표가(Price Target) 변화를 추적하는 정성적 메트릭입니다.

**핵심 목표**:
- **같은 애널리스트의 이전 목표가와 비교**하여 변화 방향(up/down)과 변화량(delta, deltaPct)을 계산
- `value_qualitative.consensusSignal` 필드에 JSON 형태로 저장

**지침 요구사항** (1_guideline(function).ini:801-803, 851-890):
```
value_qualitative = {
  "targetMedian": 0,  // 단일 값
  "consensusSummary": {
    "targetLow": ...,
    "targetHigh": ...,
    "targetMedian": ...,
    "targetConsensus": ...
  },
  "consensusSignal": {
    "source": "evt_consensus",
    "source_id": "c34c18f6-...",
    "event_date": "2025-12-08",
    "direction": "up",
    "last": {
      "price_target": 250,
      "price_when_posted": 225
    },
    "prev": {
      "price_target": 240,
      "price_when_posted": 220
    },
    "delta": 10,
    "deltaPct": 4.17,
    "meta": {
      "analyst_name": "John Doe",
      "analyst_company": "ABC Securities"
    }
  }
}
```

---

## 2. 데이터 흐름

### Phase 1: 원천 API 데이터 수집 (fmp-price-target)

**위치**: `POST /backfillSourceData`

**API 호출**:
```
GET https://financialmodelingprep.com/api/v3/price-target?symbol={ticker}
```

**응답 예시**:
```json
[
  {
    "symbol": "AAPL",
    "publishedDate": "2025-12-08T10:30:00",
    "newsURL": "https://...",
    "newsTitle": "Analyst Raises Price Target",
    "analystName": "John Doe",
    "analystCompany": "ABC Securities",
    "priceTarget": 250,
    "adjPriceTarget": 250,
    "priceWhenPosted": 225,
    "newsPublisher": "Bloomberg",
    "newsBaseURL": "https://..."
  }
]
```

**저장 위치**: `evt_consensus` 테이블 (Phase 1 필드만)

**Phase 1 필드**:
```sql
CREATE TABLE evt_consensus (
  id UUID PRIMARY KEY,
  ticker VARCHAR(10),
  event_date DATE,
  analyst_name TEXT,
  analyst_company TEXT,
  price_target DECIMAL(15, 2),
  price_when_posted DECIMAL(15, 2),
  news_url TEXT,
  news_title TEXT,
  news_publisher TEXT,
  response_key JSONB,  -- 원본 API 응답 전체

  -- Phase 2 필드 (아직 NULL)
  price_target_prev DECIMAL(15, 2),
  price_when_posted_prev DECIMAL(15, 2),
  direction VARCHAR(10),
  response_key_prev JSONB,

  created_at TIMESTAMP,
  updated_at TIMESTAMP
);
```

---

### Phase 2: 파티션별 이전 값 계산

**위치**: `source_data_service.py:256-298`

**목표**: 같은 (ticker, analyst_name, analyst_company) 파티션 내에서 이전 이벤트 찾기

**처리 로직**:
```python
# 1. 파티션별로 그룹화
for partition in target_partitions:
    ticker, analyst_name, analyst_company = partition

    # 2. 파티션의 모든 이벤트를 event_date DESC로 정렬
    events = await consensus.select_partition_events(
        pool, ticker, analyst_name, analyst_company
    )
    # events = [
    #   {id: 'uuid1', event_date: '2025-12-08', price_target: 250, ...},  # 최신
    #   {id: 'uuid2', event_date: '2025-11-15', price_target: 240, ...},  # 이전
    #   {id: 'uuid3', event_date: '2025-10-20', price_target: 235, ...},  # 더 이전
    # ]

    # 3. 각 이벤트에 대해 이전 이벤트 찾기
    for i, event in enumerate(events):
        if i < len(events) - 1:
            # 이전 이벤트가 있음
            prev_event = events[i + 1]  # DESC 정렬이므로 다음 인덱스가 과거

            price_target_prev = prev_event['price_target']
            price_when_posted_prev = prev_event['price_when_posted']

            # 방향 계산
            if event['price_target'] > price_target_prev:
                direction = 'up'
            elif event['price_target'] < price_target_prev:
                direction = 'down'
            else:
                direction = None

            response_key_prev = {
                'price_target': price_target_prev,
                'price_when_posted': price_when_posted_prev,
                'event_date': prev_event['event_date'].isoformat()
            }
        else:
            # 이전 이벤트가 없음 (파티션의 첫 번째 이벤트)
            price_target_prev = None
            price_when_posted_prev = None
            direction = None
            response_key_prev = None

        # 4. Phase 2 필드 업데이트
        await update_phase2(
            id=event['id'],
            price_target_prev=price_target_prev,
            price_when_posted_prev=price_when_posted_prev,
            direction=direction,
            response_key_prev=response_key_prev
        )
```

**Phase 2 완료 후 evt_consensus 테이블**:
```
| id    | ticker | event_date | analyst_name | analyst_company | price_target | price_target_prev | direction |
|-------|--------|------------|--------------|-----------------|--------------|-------------------|-----------|
| uuid1 | AAPL   | 2025-12-08 | John Doe     | ABC Securities  | 250          | 240               | up        |
| uuid2 | AAPL   | 2025-11-15 | John Doe     | ABC Securities  | 240          | 235               | up        |
| uuid3 | AAPL   | 2025-10-20 | John Doe     | ABC Securities  | 235          | NULL              | NULL      |
```

---

### Phase 3: txn_events 테이블에 이벤트 기록

**위치**: `POST /backfillEventsTable`

**목표**: evt_consensus의 각 행을 txn_events에 기록

**txn_events 구조**:
```sql
CREATE TABLE txn_events (
  ticker VARCHAR(10),
  event_date DATE,
  source VARCHAR(50),     -- 'consensus'
  source_id VARCHAR(255), -- evt_consensus.id (UUID)
  value_quantitative JSONB,
  value_qualitative JSONB,
  PRIMARY KEY (ticker, event_date, source, source_id)
);
```

**Phase 3 처리**:
```python
# evt_consensus의 각 행에 대해
for consensus_row in evt_consensus_rows:
    # txn_events에 삽입
    await insert_txn_events(
        ticker=consensus_row['ticker'],
        event_date=consensus_row['event_date'],
        source='consensus',
        source_id=consensus_row['id'],  # UUID
        value_quantitative=None,  # consensus는 정성적 데이터만
        value_qualitative=None     # 다음 단계에서 계산
    )
```

---

### Phase 4: consensusSignal 계산 및 value_qualitative 업데이트

**위치**: `valuation_service.py:578-684` (`calculate_qualitative_metrics()`)

**입력**:
- `ticker`: 'AAPL'
- `event_date`: '2025-12-08'
- `source`: 'consensus'
- `source_id`: 'uuid1' (evt_consensus.id)

**처리 로직**:
```python
async def calculate_qualitative_metrics(
    pool, ticker, event_date, source, source_id
):
    # 1. source_id로 evt_consensus에서 정확한 행 찾기
    consensus_data = await metrics.select_consensus_data(
        pool, ticker, event_date, source_id
    )
    # SQL: SELECT * FROM evt_consensus WHERE id = $1 AND ticker = $2 AND event_date = $3

    # 2. Phase 2에서 이미 계산된 값 추출
    price_target = consensus_data['price_target']           # 250
    price_when_posted = consensus_data['price_when_posted'] # 225
    price_target_prev = consensus_data['price_target_prev'] # 240 (Phase 2에서 계산됨)
    price_when_posted_prev = consensus_data['price_when_posted_prev'] # 220
    direction = consensus_data['direction']                 # 'up' (Phase 2에서 계산됨)

    # 3. consensusSignal 구조 생성
    consensus_signal = {
        'direction': direction,
        'last': {
            'price_target': float(price_target),
            'price_when_posted': float(price_when_posted)
        }
    }

    # 4. prev와 delta 추가 (prev가 있는 경우만)
    if price_target_prev is not None:
        consensus_signal['prev'] = {
            'price_target': float(price_target_prev),
            'price_when_posted': float(price_when_posted_prev)
        }

        # delta 계산
        delta = float(price_target) - float(price_target_prev)
        delta_pct = (delta / float(price_target_prev)) * 100

        consensus_signal['delta'] = delta
        consensus_signal['deltaPct'] = delta_pct
    else:
        consensus_signal['prev'] = None
        consensus_signal['delta'] = None
        consensus_signal['deltaPct'] = None

    # 5. value_qualitative 생성
    value_qualitative = {
        'consensusSignal': consensus_signal
    }

    return {
        'status': 'success',
        'value': value_qualitative,
        'currentPrice': float(price_when_posted),
        'message': 'Qualitative metrics calculated'
    }
```

**최종 결과** (txn_events.value_qualitative):
```json
{
  "consensusSignal": {
    "direction": "up",
    "last": {
      "price_target": 250,
      "price_when_posted": 225
    },
    "prev": {
      "price_target": 240,
      "price_when_posted": 220
    },
    "delta": 10,
    "deltaPct": 4.17
  }
}
```

---

## 3. config_lv2_metric 테이블의 consensusSignal 정의

**현재 상태**:
```sql
SELECT id, source, expression, domain, description
FROM config_lv2_metric
WHERE id = 'consensusSignal';
```

**결과**:
```
id: consensusSignal
source: expression
expression: buildConsensusSignal(consensusWithPrev)
domain: qualatative-consensusSignal
description: consensusWithPrev(lead 기능을 하드코딩)에서 최신 last/prev를 추출하고
             direction/delta/deltaPct 및 meta를 생성하여
             value_qualitative.consensusSignal 형태 데이터(JSON)를 생성한다.
```

**문제점**:
1. `consensusWithPrev` 메트릭이 존재하지 않음
2. `buildConsensusSignal()` 함수가 MetricCalculationEngine에 구현되지 않음
3. 실제로는 `calculate_qualitative_metrics()` 함수에서 하드코딩되어 처리됨

**즉, config_lv2_metric의 정의는 사용되지 않음!**

---

## 4. 흐름 요약

```
┌─────────────────────────────────────────────────────────────────────────┐
│ Phase 1: 원천 API 데이터 수집 (POST /backfillSourceData)               │
├─────────────────────────────────────────────────────────────────────────┤
│ FMP API → evt_consensus 테이블 (Phase 1 필드만)                        │
│   - ticker, event_date, analyst_name, analyst_company                   │
│   - price_target, price_when_posted                                     │
│   - Phase 2 필드는 NULL                                                 │
└─────────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────────┐
│ Phase 2: 파티션별 이전 값 계산 (source_data_service.py)                │
├─────────────────────────────────────────────────────────────────────────┤
│ 같은 (ticker, analyst_name, analyst_company) 파티션 내에서:            │
│   1. event_date DESC로 정렬                                             │
│   2. 각 행의 이전 행에서 prev 값 추출                                   │
│   3. direction 계산 (up/down/null)                                      │
│   4. evt_consensus 테이블 업데이트 (Phase 2 필드)                       │
│      - price_target_prev, price_when_posted_prev                        │
│      - direction, response_key_prev                                     │
└─────────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────────┐
│ Phase 3: txn_events 테이블에 이벤트 기록 (POST /backfillEventsTable)   │
├─────────────────────────────────────────────────────────────────────────┤
│ evt_consensus의 각 행을 txn_events에 기록:                              │
│   - ticker, event_date, source='consensus', source_id=evt_consensus.id  │
│   - value_qualitative는 아직 NULL                                       │
└─────────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────────┐
│ Phase 4: consensusSignal 계산 (calculate_qualitative_metrics)           │
├─────────────────────────────────────────────────────────────────────────┤
│ txn_events의 각 행에 대해:                                              │
│   1. source_id로 evt_consensus에서 정확한 행 찾기                       │
│   2. Phase 2에서 계산된 prev 값과 direction 사용                        │
│   3. delta, deltaPct 계산                                               │
│   4. consensusSignal 구조 생성                                          │
│   5. txn_events.value_qualitative 업데이트                              │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 5. 핵심 원칙

### ✅ 올바른 접근 (현재 구현)

1. **evt_consensus 테이블의 2단계 계산 사용**
   - Phase 2에서 같은 애널리스트의 이전 값을 미리 계산
   - `price_target_prev`, `direction` 등이 이미 계산되어 있음

2. **source_id로 정확한 행 찾기**
   - `txn_events.source_id = evt_consensus.id`
   - 같은 날짜에 여러 애널리스트가 있어도 정확한 행을 찾을 수 있음

3. **같은 애널리스트만 비교**
   - (ticker, analyst_name, analyst_company) 파티션 내에서만 비교
   - 다른 애널리스트의 목표가와 섞이지 않음

### ❌ 잘못된 접근 (하지 말아야 할 것)

1. **원천 API를 직접 참조하지 않음**
   - FMP API의 `publishedDate`나 `date` 필드를 직접 사용하지 않음
   - 반드시 표준화된 `event_date`를 사용

2. **consensusWithPrev 같은 aggregation 사용하지 않음**
   - `leadPairFromList` 같은 복잡한 aggregation은 불필요
   - evt_consensus Phase 2에서 이미 계산되어 있음

3. **config_lv2_metric에서 동적으로 계산하지 않음**
   - 현재는 하드코딩이 올바른 접근
   - 향후 MetricCalculationEngine 확장 시에만 고려

---

## 6. 현재 문제 및 해결 방안

### 문제 1: config_lv2_metric의 정의가 실제 구현과 불일치

**현재 상태**:
- config_lv2_metric에 `consensusSignal` 정의가 있음
- expression: `buildConsensusSignal(consensusWithPrev)`
- 하지만 `consensusWithPrev`는 존재하지 않음
- 실제로는 `calculate_qualitative_metrics()`에서 하드코딩으로 처리

**문제점**:
- 설정과 구현이 불일치
- `buildConsensusSignal()` 함수가 구현되지 않음
- MetricCalculationEngine이 이를 처리할 수 없음

### 해결 방안

#### 옵션 A: config_lv2_metric에서 expression 제거 (권장)

**이유**:
- 현재 하드코딩 방식이 올바르고 효율적
- evt_consensus Phase 2 계산을 재사용하는 것이 맞음
- 불필요한 복잡성을 추가하지 않음

**수정**:
```sql
UPDATE config_lv2_metric
SET
  expression = NULL,
  description = 'Consensus signal calculated from evt_consensus table (Phase 2 data) in calculate_qualitative_metrics(). Uses source_id to find exact analyst row and extracts prev/direction values.'
WHERE id = 'consensusSignal';
```

#### 옵션 B: MetricCalculationEngine 확장하여 동적 계산 (향후)

**필요한 작업**:
1. `buildConsensusSignal()` 특수 함수 구현
2. evt_consensus 테이블 조회 기능 추가
3. expression 파서 확장

**장점**:
- 모든 메트릭을 config_lv2_metric에서 관리
- 일관성 있는 아키텍처

**단점**:
- 복잡도 증가
- 현재로서는 불필요 (하드코딩이 더 명확함)

**권장**: 현재는 옵션 A, 향후 필요 시 옵션 B 검토

---

## 7. 결론

### 현재 구현 상태: ✅ 올바름

1. **Phase 1-2**: evt_consensus에 데이터 저장 및 prev 값 계산 - **정상**
2. **Phase 3**: txn_events에 이벤트 기록 - **정상**
3. **Phase 4**: calculate_qualitative_metrics()에서 consensusSignal 생성 - **정상**

### 수정 필요 사항: config_lv2_metric 정의만

- expression 제거 또는 명확한 설명으로 변경
- 하드코딩 방식을 명시

### 권장 조치

```sql
-- consensusSignal의 expression을 NULL로 설정하고 설명을 명확히 함
UPDATE config_lv2_metric
SET
  expression = NULL,
  description = 'Consensus signal from evt_consensus Phase 2 data. Calculated in calculate_qualitative_metrics() using source_id to find exact analyst row. Includes direction, last, prev, delta, deltaPct.'
WHERE id = 'consensusSignal';
```

이렇게 하면:
- 설정과 구현이 일치
- 하드코딩 방식이 명확히 문서화됨
- 향후 변경 시에도 혼란이 없음
