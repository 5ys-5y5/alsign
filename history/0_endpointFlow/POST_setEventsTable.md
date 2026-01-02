# POST /setEventsTable 엔드포인트 흐름

> **목적**: evt_* 소스 테이블들의 이벤트를 txn_events 테이블로 통합
> 
> **최종 업데이트**: 2025-12-27

---

## 1. 엔드포인트 개요

| 항목 | 값 |
|------|-----|
| **경로** | `POST /setEventsTable` |
| **라우터 파일** | `backend/src/routers/events.py` |
| **서비스 파일** | `backend/src/services/events_service.py` |
| **DB 쿼리 파일** | `backend/src/database/queries/events.py` |

---

## 2. 호출 흐름도

```
[Client]
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ routers/events.py:23-102                                        │
│ @router.post("/setEventsTable")                                │
│ async def set_events_table(...)                                │
│   └─► events_service.consolidate_events(...)                   │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ services/events_service.py                                      │
│ async def consolidate_events(...)                              │
│   ├─► Phase 1: Discover evt_* tables in schema                 │
│   ├─► Phase 2: For each table, extract events                  │
│   ├─► Phase 3: Insert into txn_events                          │
│   └─► Phase 4: Enrich with sector/industry                     │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. 상세 흐름 설명

### Phase 1: Discover evt_* Tables
```
consolidate_events(overwrite, dry_run, schema, table_filter)
    │
    └─► events.discover_event_tables(pool, schema)
          ├─► SQL: SELECT table_name FROM information_schema.tables 
          │        WHERE table_schema = $1 AND table_name LIKE 'evt_%'
          └─► 반환: List[str] ['evt_consensus', 'evt_earning', ...]
```

### Phase 2: Extract Events from Each Table
```
consolidate_events()
    │
    └─► For each table in evt_tables:
          │
          └─► events.extract_events_from_table(pool, table, schema)
                ├─► SQL: SELECT ticker, event_date, 'consensus' as source, id as source_id
                │        FROM evt_consensus
                └─► 반환: List[Dict] (이벤트 목록)
```

### Phase 3: Insert into txn_events
```
consolidate_events()
    │
    └─► events.insert_events_batch(pool, events, overwrite)
          ├─► SQL (overwrite=False): 
          │     INSERT INTO txn_events (ticker, event_date, source, source_id)
          │     VALUES (...) ON CONFLICT DO NOTHING
          │
          └─► SQL (overwrite=True):
                INSERT INTO txn_events (ticker, event_date, source, source_id)
                VALUES (...) 
                ON CONFLICT (ticker, event_date, source, source_id) 
                DO UPDATE SET updated_at = now()
```

### Phase 4: Enrich with Sector/Industry
```
consolidate_events()
    │
    └─► events.enrich_events_with_company_info(pool)
          └─► SQL: UPDATE txn_events e
                   SET sector = t.sector, industry = t.industry
                   FROM config_lv3_targets t
                   WHERE e.ticker = t.ticker AND e.sector IS NULL
```

---

## 4. 데이터 흐름

### 입력 데이터
```
[Request Parameters]
    ├─► overwrite: bool (기존 값 덮어쓰기 여부)
    ├─► dryRun: bool (실제 저장 없이 미리보기)
    ├─► schema: str (default: 'public')
    └─► table: Optional[str] (특정 테이블만 처리, 쉼표 구분)

[DB 소스 테이블]
    ├─► evt_consensus: 애널리스트 컨센서스 이벤트
    └─► evt_earning: 실적 발표 이벤트
```

### 출력 데이터
```
[txn_events 테이블에 삽입]
    ├─► ticker: VARCHAR
    ├─► event_date: TIMESTAMPTZ
    ├─► source: VARCHAR ('consensus' | 'earning')
    ├─► source_id: VARCHAR (원본 테이블의 id)
    ├─► sector: VARCHAR (config_lv3_targets에서 enrichment)
    └─► industry: VARCHAR (config_lv3_targets에서 enrichment)
```

---

## 5. 응답 예시

```json
{
  "reqId": "abc123",
  "endpoint": "POST /setEventsTable",
  "dryRun": false,
  "summary": {
    "totalTablesProcessed": 2,
    "totalEventsInserted": 15000,
    "totalEventsSkipped": 500,
    "elapsedMs": 3500
  },
  "tables": [
    {
      "table": "evt_consensus",
      "eventsFound": 12000,
      "eventsInserted": 11500,
      "eventsSkipped": 500
    },
    {
      "table": "evt_earning",
      "eventsFound": 3500,
      "eventsInserted": 3500,
      "eventsSkipped": 0
    }
  ]
}
```

---

*최종 업데이트: 2025-12-27 KST*

