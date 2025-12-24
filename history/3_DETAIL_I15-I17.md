# AlSign 상세 구현 문서 (I-15 ~ I-17)

> 이 문서는 I-15, I-16, I-17 이슈의 상세 구현 내용을 기록합니다.
> 
> **작성**: 2025-12-25
> **세션**: POST /backfillEventsTable 실행 로그 분석 및 개선

---

## I-15: event_date_obj 변수 순서 오류

### I-15-A: 문제 발견 및 수정

**에러 로그**:
```
[calculate_quantitative_metrics] Failed to fetch fmp-historical-price-eod-full: 
local variable 'event_date_obj' referenced before assignment
```

**원인 분석**:
```python
# 잘못된 순서 (backend/src/services/valuation_service.py)

# 431-456라인: API 호출 루프
for api_id in required_apis:
    params = {'ticker': ticker}
    if 'historical-price' in api_id or 'eod' in api_id:
        params['toDate'] = event_date_obj.strftime('%Y-%m-%d')  # ❌ 444라인: 정의 전 사용
    result = await fmp_client.call_api(api_id, params)

# 471-475라인: event_date_obj 정의
if isinstance(event_date, str):
    event_date_obj = datetime.fromisoformat(...).date()  # ❌ 471라인: 늦은 정의
```

**적용된 수정**:
```python
# 올바른 순서

# 430-438라인: event_date_obj를 먼저 변환 (MUST be done before API calls)
from datetime import datetime
if isinstance(event_date, str):
    event_date_obj = datetime.fromisoformat(event_date.replace('Z', '+00:00')).date()
elif hasattr(event_date, 'date'):
    event_date_obj = event_date.date()
else:
    event_date_obj = event_date

# 440-456라인: API 호출 루프 (이제 안전하게 사용 가능)
for api_id in required_apis:
    params = {'ticker': ticker}
    if 'historical-price' in api_id or 'eod' in api_id:
        params['fromDate'] = '2000-01-01'
        params['toDate'] = event_date_obj.strftime('%Y-%m-%d')  # ✅ 정의 후 사용
    result = await fmp_client.call_api(api_id, params)
```

**파일**: `backend/src/services/valuation_service.py:425-456`

**테스트 결과**:
- ✅ `event_date_obj` 에러 해결
- ✅ `fmp-historical-price-eod-full` API 정상 호출
- ✅ `fromDate`, `toDate` 파라미터 정상 전달

---

## I-16: 메트릭 실패 디버깅 로그 부재

### I-16-A: 실패 이유 추적 시스템 구현

**기존 로그** (이유 없음):
```
[MetricEngine] ✗ priceEodOHLC = None (source: api_field)
[MetricEngine] ✗ apicYoY = None (source: aggregation)
[MetricEngine] ✗ revenueQoQ = None (source: aggregation)
[MetricEngine] ✗ sharesYoY = None (source: aggregation)
```

**개선된 로그** (이유 포함):
```
[MetricEngine] ✗ priceEodOHLC = None (source: api_field) | reason: No data from API 'fmp-historical-price-eod-full'
[MetricEngine] ✗ apicYoY = None (source: aggregation) | reason: Base metric 'additionalPaidInCapital' is None
[MetricEngine] ✗ revenueQoQ = None (source: aggregation) | reason: Transform 'qoqFromQuarter' returned None
[MetricEngine] ✗ sharesYoY = None (source: aggregation) | reason: Missing dependencies: weightedAverageShsOut
```

**구현 코드** (`backend/src/services/metric_engine.py`):

```python
# 241-268라인: 메트릭 계산 루프에서 이유 추적
for metric_name in self.calculation_order:
    metric = self.metrics_by_name[metric_name]
    
    try:
        value, failure_reason = self._calculate_metric_with_reason(metric, api_data, calculated_values)
        calculated_values[metric_name] = value
        if value is not None:
            logger.info(f"[MetricEngine] ✓ {metric_name} = {str(value)[:50]} (source: {metric.get('source')})")
        else:
            # Include failure reason for debugging
            reason_str = f" | reason: {failure_reason}" if failure_reason else ""
            logger.info(f"[MetricEngine] ✗ {metric_name} = None (source: {metric.get('source')}){reason_str}")
    except Exception as e:
        logger.error(f"[MetricEngine] Failed to calculate {metric_name}: {e}")
        calculated_values[metric_name] = None

# 272-326라인: 실패 이유 분류 로직
def _calculate_metric_with_reason(
    self,
    metric: Dict[str, Any],
    api_data: Dict[str, List[Dict[str, Any]]],
    calculated_values: Dict[str, Any]
) -> tuple:
    """Calculate a single metric with failure reason tracking."""
    source = metric.get('source')
    metric_name = metric.get('name')

    if source == 'api_field':
        value = self._calculate_api_field(metric, api_data)
        if value is None:
            api_list_id = metric.get('api_list_id')
            if not api_list_id:
                return None, "Missing api_list_id"
            elif api_list_id not in api_data or not api_data.get(api_list_id):
                return None, f"No data from API '{api_list_id}'"
            else:
                return None, f"Field extraction failed from '{api_list_id}'"
        return value, None
        
    elif source == 'aggregation':
        value = self._calculate_aggregation(metric, api_data, calculated_values)
        if value is None:
            base_metric = metric.get('base_metric')
            transform_id = metric.get('transform')
            if not base_metric:
                return None, "Missing base_metric"
            elif base_metric not in calculated_values:
                return None, f"Base metric '{base_metric}' not calculated"
            elif calculated_values.get(base_metric) is None:
                return None, f"Base metric '{base_metric}' is None"
            else:
                return None, f"Transform '{transform_id}' returned None"
        return value, None
        
    elif source == 'expression':
        value = self._calculate_expression(metric, calculated_values)
        if value is None:
            dependencies = metric.get('dependencies', [])
            missing = [d for d in dependencies if d not in calculated_values or calculated_values.get(d) is None]
            if missing:
                return None, f"Missing dependencies: {', '.join(missing)}"
            else:
                return None, "Expression evaluation returned None"
        return value, None
        
    else:
        return None, f"Unknown source type '{source}'"
```

**실패 이유 분류표**:

| Source | 실패 이유 | 설명 |
|--------|----------|------|
| **api_field** | Missing api_list_id | config에 api_list_id 없음 |
| | No data from API 'xxx' | API 호출 실패 또는 빈 응답 |
| | Field extraction failed | response_key 필드 매핑 실패 |
| **aggregation** | Missing base_metric | config에 base_metric 없음 |
| | Base metric 'xxx' not calculated | 의존 메트릭 계산 안됨 |
| | Base metric 'xxx' is None | 의존 메트릭이 NULL |
| | Transform 'xxx' returned None | aggregation 함수가 NULL 반환 |
| **expression** | Missing dependencies: xxx | 의존 메트릭 누락 또는 NULL |
| | Expression evaluation returned None | 수식 계산 결과 NULL |

**경제적 디버깅**:
```bash
# 실패한 메트릭만 확인
grep "✗" backend_logs.txt

# 특정 메트릭 이유 확인
grep "priceEodOHLC.*reason" backend_logs.txt

# API 데이터 문제 확인
grep "reason: No data from API" backend_logs.txt

# 의존성 문제 확인
grep "reason: Missing dependencies" backend_logs.txt
```

---

## I-17: 로그 형식 N/A 과다 출력

### I-17-A: 조건부 로그 포맷 구현

**문제 상황**:
```
[N/A | N/A] | elapsed=0ms | progress=N/A | eta=0ms | rate=N/A | batch=N/A | counters=N/A | warn=[] | [API Response] fmp-aftermarket-trade -> HTTP 200
[N/A | N/A] | elapsed=0ms | progress=N/A | eta=0ms | rate=N/A | batch=N/A | counters=N/A | warn=[] | [API Parse] fmp-aftermarket-trade -> Type: list, Length: 1
[N/A | N/A] | elapsed=0ms | progress=N/A | eta=0ms | rate=N/A | batch=N/A | counters=N/A | warn=[] | [Schema Mapping] fmp-aftermarket-trade -> Mapped 1 items
```

**원인**:
- `external_api.py`, `metric_engine.py` 등에서 `logger.info(f"[API Call] ...")` 형식으로 단순 문자열만 출력
- `extra` 파라미터 없음 → StructuredFormatter가 모든 필드를 N/A로 채움
- 1_guideline(function).ini 지침: "주요 단계만 구조화된 로그, 세부는 단순 포맷"

**적용된 수정** (`backend/src/services/utils/logging_utils.py:15-91`):

```python
def format(self, record: logging.LogRecord) -> str:
    """Format log record into structured 1-line format."""
    # Check if this log has structured data
    has_structured_data = hasattr(record, 'endpoint') and record.endpoint != 'N/A'
    
    # If no structured data, use simple format (for debug/detail logs)
    if not has_structured_data:
        message = record.getMessage()
        # Add to request context for detailed logs
        add_detailed_log(message)
        return message  # ✅ N/A 없이 깔끔하게 출력
    
    # Extract custom attributes with defaults (구조화된 로그용)
    endpoint = getattr(record, 'endpoint', 'N/A')
    phase = getattr(record, 'phase', 'N/A')
    elapsed_ms = getattr(record, 'elapsed_ms', 0)
    progress = getattr(record, 'progress', {})
    eta_ms = getattr(record, 'eta_ms', 0)
    rate = getattr(record, 'rate', {})
    batch = getattr(record, 'batch', {})
    counters = getattr(record, 'counters', {})
    warn = getattr(record, 'warn', [])
    
    # ... 나머지 구조화된 포맷 처리
```

**개선된 출력**:

**단순 로그** (세부 정보 - N/A 없음):
```
[API Call] fmp-aftermarket-trade -> https://...
[API Response] fmp-aftermarket-trade -> HTTP 200
[API Parse] fmp-aftermarket-trade -> Type: list, Length: 1
[Schema Mapping] fmp-aftermarket-trade -> Mapped 1 items
[calculate_quantitative_metrics] Fetched fmp-aftermarket-trade: 1 records
[MetricEngine] ✓ marketCap = 8029534478.0 (source: api_field)
[MetricEngine] ✗ priceEodOHLC = None (source: api_field) | reason: No data from API 'fmp-historical-price-eod-full'
```

**구조화된 로그** (주요 단계 - 진행률/성능 추적):
```
[POST /backfillEventsTable | start] elapsed=0ms | progress=N/A | eta=0ms | rate=N/A | batch=N/A | counters=N/A | warn=[] | START - Processing valuations
[POST /backfillEventsTable | load_metrics] elapsed=50ms | progress=N/A | eta=0ms | rate=N/A | batch=N/A | counters=N/A | warn=[] | Loading metric definitions
[POST /backfillEventsTable | load_events] elapsed=2070ms | progress=N/A | eta=0ms | rate=N/A | batch=N/A | counters=N/A | warn=[] | Loading events for valuation
[POST /backfillEventsTable | process_events] elapsed=2100ms | progress=0/30(0%) | eta=0ms | rate=N/A | batch=N/A | counters=N/A | warn=[] | Processing 30 events
```

### I-17-B: 로깅 가이드 문서

**파일**: `backend/LOGGING_GUIDE.md`

**주요 내용**:

```markdown
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

### 2. 단순 로그 (Simple Logs)
**사용 시기**: 디버깅, 세부 정보, API 호출 상세

```python
logger.info(f"[API Call] {api_id} -> {url}")
logger.info(f"[MetricEngine] ✓ {metric_name} = {value}")
logger.debug(f"[calculate_quantitative_metrics] Fetched {api_id}: {len(result)} records")
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
```

**설계 철학**:
- ✅ 1_guideline(function).ini 지침 준수
- ✅ 세부 로그는 단순 포맷으로 가독성 확보
- ✅ 주요 단계만 구조화된 로그로 진행률/성능 추적
- ✅ 경제적 로깅: API 호출 상세는 단순 로그로 빠르게 출력

**현재 상태**:
- ✅ `logging_utils.py`: 구조화된 로그 없는 경우 단순 포맷 사용
- ✅ `valuation_service.py`: 일부 구조화된 로그 적용됨
- ⚠️ `external_api.py`: 모두 단순 로그 (의도된 설계)
- ⚠️ `metric_engine.py`: 모두 단순 로그 (의도된 설계)

---

*작성: 2025-12-25*  
*최종 업데이트: 2025-12-25*

