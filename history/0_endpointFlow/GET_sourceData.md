# GET /sourceData 엔드포인트 흐름

> **목적**: 외부 FMP API에서 금융 데이터를 수집하여 DB에 저장
> 
> **최종 업데이트**: 2025-12-31

---

## 1. 엔드포인트 개요

| 항목 | 값 |
|------|-----|
| **경로** | `GET /sourceData` |
| **라우터 파일** | `backend/src/routers/source_data.py` |
| **서비스 파일** | `backend/src/services/source_data_service.py` |
| **외부 API** | `backend/src/services/external_api.py` |

---

## 2. 지원 모드

| 모드 | 설명 | DB 테이블 |
|------|------|-----------|
| `holiday` | 시장 휴장일 수집 | `config_lv3_market_holidays` |
| `target` | 분석 대상 종목 수집 | `config_lv3_targets` |
| `consensus` | 애널리스트 컨센서스 수집 | `evt_consensus` |
| `earning` | 실적 발표 수집 | `evt_earning` |

---

## 3. 호출 흐름도

```
[Client]
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ routers/source_data.py:18-191                                   │
│ @router.get("/sourceData")                                     │
│ async def get_source_data(...)                                 │
│   └─► For each mode in mode_list:                              │
│         ├─► source_data_service.get_holidays()                 │
│         ├─► source_data_service.get_targets()                  │
│         ├─► source_data_service.get_consensus()                │
│         └─► source_data_service.get_earning()                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. 각 모드별 상세 흐름

### mode=holiday
```
get_holidays(overwrite)
    │
    ├─► FMPAPIClient.call_api('fmp-is-the-market-open', {'exchange': 'NASDAQ'})
    │     FMP API에서 거래소 휴장일 조회
    │
    ├─► For each holiday:
    │     └─► holidays.insert_holiday(pool, exchange, date, is_fully_closed)
    │
    └─► 반환: {'counters': {'success': N, 'fail': M}}
```

### mode=target
```
get_targets(overwrite)
    │
    ├─► policies.get_target_source_policy(pool)
    │     config_lv1_policy에서 target 소스 URL 조회
    │
    ├─► HTTP GET (external source)
    │     분석 대상 종목 리스트 조회
    │
    ├─► For each ticker:
    │     └─► targets.upsert_target(pool, ticker, sector, industry, ...)
    │
    └─► 반환: {'counters': {'success': N, 'fail': M}}
```

### mode=consensus (3-Phase 처리)
```
get_consensus(overwrite, calc_mode, calc_scope, tickers_param, from_date, to_date, partitions_param)
    │
    ├─► [Phase 1] FMP API에서 raw consensus 수집
    │     │
    │     ├─► targets.select_all_tickers(pool)
    │     │     분석 대상 종목 목록 조회
    │     │
    │     └─► For each ticker:
    │           └─► FMPAPIClient.call_api('fmp-price-target', {'ticker': ticker})
    │                 └─► consensus.insert_consensus_raw(pool, ...)
    │
    ├─► [Phase 2] prev 값 계산 및 direction 설정
    │     │
    │     ├─► consensus.calculate_prev_values(pool, ticker, analyst_name, analyst_company)
    │     │     │
    │     │     └─► SQL: UPDATE evt_consensus SET
    │     │              price_target_prev = ..., price_when_posted_prev = ...
    │     │              WHERE id = $id
    │     │
    │     └─► consensus.set_direction(pool, id, price_target, price_target_prev)
    │           └─► direction = 'up' | 'down' | null
    │
    └─► [Phase 3] targetSummary 계산 (I-31)
          │
          ├─► consensus.get_events_for_target_summary(pool, overwrite, calc_scope, ...)
          │     overwrite=true: 모든 행 재계산
          │     overwrite=false: target_summary IS NULL인 행만
          │
          └─► For each event:
                ├─► consensus.calculate_target_summary(pool, ticker, event_date)
                │     lastMonth/lastQuarter/lastYear/allTime 통계 계산
                │
                └─► consensus.update_target_summary_batch(pool, updates)
                      evt_consensus.target_summary에 저장
```

**calc_mode 옵션:**
- `calc_mode=calculation`: Phase 1 스킵 (API 호출 없음), Phase 2+3만 실행
- `calc_mode=maintenance`: Phase 1+2+3 모두 실행 (사용자 지정 scope)

### mode=earning
```
get_earning(overwrite, past)
    │
    ├─► FMPAPIClient.call_api('fmp-earning-calendar', {'from': from_date, 'to': to_date})
    │     FMP API에서 실적 발표 일정 조회
    │
    ├─► For each earning:
    │     └─► earning.upsert_earning(pool, ticker, event_date, eps, revenue, ...)
    │
    └─► 반환: {'counters': {'success': N, 'fail': M}}
```

---

## 5. 데이터 흐름

### 입력 파라미터
```
[Request Parameters]
    ├─► mode: str (쉼표 구분, 기본값: 'holiday,target,consensus,earning')
    ├─► overwrite: bool (기존 값 덮어쓰기 여부)
    ├─► calc_mode: str (consensus Phase 2: 'full' | 'incremental')
    ├─► calc_scope: str (consensus 범위: 'all' | 'ticker')
    ├─► tickers: Optional[str] (특정 티커만 처리)
    ├─► from_date: Optional[date] (날짜 범위 시작)
    ├─► to_date: Optional[date] (날짜 범위 끝)
    ├─► partitions: Optional[str] (analyst 파티션 필터)
    └─► past: bool (earning - 과거 포함 여부)
```

### 출력 테이블
```
[mode=holiday]
    config_lv3_market_holidays
    ├─► exchange: VARCHAR
    ├─► date: DATE
    └─► is_fully_closed: BOOLEAN

[mode=target]
    config_lv3_targets
    ├─► ticker: VARCHAR (PK)
    ├─► company_name: VARCHAR
    ├─► sector: VARCHAR
    ├─► industry: VARCHAR
    └─► is_active: BOOLEAN

[mode=consensus]
    evt_consensus
    ├─► id: UUID (PK)
    ├─► ticker: VARCHAR
    ├─► event_date: TIMESTAMPTZ
    ├─► analyst_name: VARCHAR
    ├─► analyst_company: VARCHAR
    ├─► price_target: DECIMAL
    ├─► price_when_posted: DECIMAL
    ├─► price_target_prev: DECIMAL (Phase 2)
    ├─► price_when_posted_prev: DECIMAL (Phase 2)
    ├─► direction: VARCHAR ('up'|'down'|'maintain', Phase 2)
    └─► target_summary: JSONB (Phase 3, I-31)

[mode=earning]
    evt_earning
    ├─► id: UUID (PK)
    ├─► ticker: VARCHAR
    ├─► event_date: TIMESTAMPTZ
    ├─► eps: DECIMAL
    ├─► eps_estimated: DECIMAL
    ├─► revenue: DECIMAL
    └─► revenue_estimated: DECIMAL
```

---

## 6. 응답 예시

```json
{
  "reqId": "def456",
  "endpoint": "GET /sourceData",
  "summary": {
    "totalElapsedMs": 45000,
    "totalSuccess": 15000,
    "totalFail": 5
  },
  "results": {
    "holiday": {
      "executed": true,
      "elapsedMs": 500,
      "counters": { "success": 50, "fail": 0 }
    },
    "target": {
      "executed": true,
      "elapsedMs": 2000,
      "counters": { "success": 500, "fail": 0 }
    },
    "consensus": {
      "executed": true,
      "elapsedMs": 40000,
      "counters": { "success": 14400, "fail": 5 }
    },
    "earning": {
      "executed": true,
      "elapsedMs": 2500,
      "counters": { "success": 50, "fail": 0 }
    }
  }
}
```

---

## 7. 관련 이슈

### I-29 해결됨 (2025-12-31) ✅
- **문제**: evt_consensus 테이블의 `price_target_prev`, `price_when_posted_prev`, `direction`이 모두 NULL
- **원인**: GET /sourceData?mode=consensus의 Phase 2 계산이 실행되지 않음
- **해결**: `calc_mode=calculation` 모드 추가 (API 호출 없이 Phase 2+3 계산만 수행)
- **사용법**: 
  ```bash
  GET /sourceData?mode=consensus&calc_mode=calculation&calc_scope=all
  GET /sourceData?mode=consensus&calc_mode=calculation&calc_scope=ticker&tickers=RGTI
  ```
- **수정 파일**: `backend/src/services/source_data_service.py`

### I-31 해결됨 (2025-12-31) ✅
- **문제**: POST /backfillEventsTable에서 value_qualitative.consensusSummary가 과거 이벤트에서 항상 NULL
- **원인**: FMP API가 현재 시점 consensus만 반환, 과거 데이터 없음
- **해결**: GET /sourceData?mode=consensus에 Phase 3 추가하여 target_summary 사전 계산
- **구현 사항**:
  - ✅ evt_consensus 테이블에 `target_summary` JSONB 컬럼 추가
  - ✅ `consensus.calculate_target_summary()`: 과거 데이터 기반 집계 계산
  - ✅ `consensus.update_consensus_phase3()`: target_summary 저장
  - ✅ overwrite 옵션 지원 (재계산 가능)
- **수정 파일**: 
  - `backend/src/database/queries/consensus.py`
  - `backend/src/services/source_data_service.py`

---

*최종 업데이트: 2025-12-31 KST*

