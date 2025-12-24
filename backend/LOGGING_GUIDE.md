# 로깅 가이드

## 로그 형식 정책

### 1. 구조화된 로그 (Structured Logs)
**사용 시기**: 엔드포인트의 주요 단계 (Phase 전환, 진행률 보고)

```python
from .utils.logging_utils import create_log_context

logger.info(
    "Processing events",
    extra=create_log_context(
        endpoint='POST /backfillEventsTable',
        phase='process_events',
        elapsed_ms=int((time.time() - start_time) * 1000),
        progress={'done': 10, 'total': 100, 'pct': 10},
        counters={'ok': 8, 'fail': 2}
    )
)
```

**출력**:
```
[POST /backfillEventsTable | process_events] elapsed=1500ms | progress=10/100(10%) | eta=13500ms | rate=N/A | batch=N/A | ok=8 fail=2 | warn=[] | Processing events
```

### 2. 단순 로그 (Simple Logs)
**사용 시기**: 디버깅, 세부 정보, API 호출 상세

```python
logger.info(f"[API Call] {api_id} -> {url}")
logger.info(f"[MetricEngine] ✓ {metric_name} = {value}")
logger.debug(f"[calculate_quantitative_metrics] Fetched {api_id}: {len(result)} records")
```

**출력**:
```
[API Call] fmp-income-statement -> https://...
[MetricEngine] ✓ marketCap = 8029534478.0 (source: api_field)
```

## 구조화된 로그 필수 사용 위치

### POST /backfillEventsTable
- `phase='start'`: 엔드포인트 시작
- `phase='load_metrics'`: 메트릭 정의 로드
- `phase='load_events'`: 이벤트 로드
- `phase='process_events'`: 이벤트 처리 (10개마다 진행률 업데이트)
- `phase='complete'`: 완료

### GET /sourceData
- `phase='start'`
- `phase='getHolidays'` / `'getTargets'` / `'getConsensus'` / `'getEarning'`
- `phase='complete'`

### POST /fillAnalyst
- `phase='start'`
- `phase='load_events'`
- `phase='process_groups'` (10개마다)
- `phase='complete'`

## 로그 컨텍스트 필드

```python
create_log_context(
    endpoint: str,          # 'POST /backfillEventsTable'
    phase: str,             # 'process_events'
    elapsed_ms: int,        # 누적 경과 시간 (ms)
    progress: dict,         # {'done': 10, 'total': 100, 'pct': 10}
    eta_ms: int,            # 예상 남은 시간 (ms)
    rate: dict,             # {'perMin': 50, 'limitPerMin': 300, 'usagePct': 16}
    batch: dict,            # {'size': 10, 'mode': 'dynamic'}
    counters: dict,         # {'ok': 8, 'fail': 2, 'skip': 1, 'upd': 5, 'ins': 3}
    warn: list              # ['POLICY_CONFLICT_DB_SCHEMA']
)
```

## 현재 상태

- ✅ `logging_utils.py`: 구조화된 로그 없는 경우 단순 포맷 사용
- ✅ `valuation_service.py`: 일부 구조화된 로그 적용됨
- ⚠️ `external_api.py`: 모두 단순 로그 (의도된 설계)
- ⚠️ `metric_engine.py`: 모두 단순 로그 (의도된 설계)

## 권장사항

**현재 구현은 적절합니다:**
- API 호출, 메트릭 계산 등 세부 로그는 단순 포맷으로 가독성 확보
- 엔드포인트 주요 단계만 구조화된 로그로 진행률/성능 추적

**추가 개선이 필요한 경우:**
- `valuation_service.py`의 이벤트 처리 루프에서 10개마다 진행률 업데이트
- Rate limiter에서 `rate` 정보 추가

