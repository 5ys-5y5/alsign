# 📝 AlSign 이슈 상세도

> 이 문서는 각 이슈의 문제가 된 코드와 적용할 코드를 상세히 기록합니다.
> 각 항목은 `1_CHECKLIST.md` 및 `2_FLOW.md`와 동일한 `I-##` ID를 사용합니다.
>
> **ID 체계**: 모든 문서에서 동일한 `I-##` ID를 사용합니다.

---

## I-01: consensusSignal 설정 불일치

### I-01-A: SQL 변경 (반영완료 - 실행대기)

	**파일**: `backend/scripts/apply_issue_docs_changes.sql`
	
	**문제가 된 설정**:
	```sql
	-- 기존 config_lv2_metric 테이블의 consensusSignal
	id: consensusSignal
	source: expression
	expression: buildConsensusSignal(consensusWithPrev)  -- ❌ consensusWithPrev 미존재
	domain: qualatative-consensusSignal
	```
	
	**적용할 변경**:
	```sql
	-- consensusSignal을 aggregation 타입으로 변경
	UPDATE config_lv2_metric
	SET
	  source = 'aggregation',
	  expression = NULL,  -- 의존성 제거
	  base_metric_id = NULL,  -- consensusRaw 구현 후 추가 필요
	  aggregation_kind = 'leadPairFromList',
	  aggregation_params = '{
	    "partitionBy": ["ticker", "analyst_name", "analyst_company"],
	    "orderBy": [{"event_date": "desc"}],
	    "leadFields": [
	      {"field": "price_target", "as": "price_target_prev"},
	      {"field": "price_when_posted", "as": "price_when_posted_prev"}
	    ],
	    "emitPrevRow": true
	  }'::jsonb,
	  description = 'Consensus signal built from evt_consensus using aggregation...'
	WHERE id = 'consensusSignal';
	```

### I-01-B: leadPairFromList aggregation 구현 (미반영)

	**필요 파일**: `backend/src/services/metric_engine.py`
	
	**현재 상태**: aggregation 라우팅에 leadPairFromList 없음
	
	```python
	# 현재 코드 (metric_engine.py ~438줄)
	if aggregation_kind == 'ttmFromQuarterSumOrScaled':
	    return self._ttm_sum_or_scaled(base_values, aggregation_params)
	elif aggregation_kind == 'lastFromQuarter':
	    return self._last_from_quarter(base_values, aggregation_params)
	# ... leadPairFromList 없음!
	```
	
	**추가해야 할 코드**:
	```python
	elif aggregation_kind == 'leadPairFromList':
	    return self._lead_pair_from_list(base_values, aggregation_params)
	
	def _lead_pair_from_list(
	    self,
	    base_values: List[Dict[str, Any]],
	    params: Dict[str, Any]
	) -> Optional[Dict[str, Any]]:
	    """
	    Find previous record for same partition and attach lead values.
	    
	    Args:
	        base_values: List of records from base_metric
	        params: {
	            "partitionBy": ["ticker", "analyst_name", "analyst_company"],
	            "orderBy": [{"event_date": "desc"}],
	            "leadFields": [{"field": "price_target", "as": "price_target_prev"}],
	            "emitPrevRow": true
	        }
	    
	    Returns:
	        Dict with current record + prev values
	    """
	    partition_by = params.get('partitionBy', [])
	    order_by = params.get('orderBy', [])
	    lead_fields = params.get('leadFields', [])
	    
	    # Implementation: partition, sort, find prev, attach lead fields
	    # ...
	```

---

## I-02: priceEodOHLC dict response_key

### 검증 결과 (조치 불필요)

	**파일**: `backend/src/services/metric_engine.py`
	
	**확인된 코드** (라인 385-422):
	```python
	def _calculate_api_field(self, metric, api_data):
	    # ...
	    
	    # Handle dict response_key (complex schema mapping)
	    if isinstance(field_key, dict):
	        # ✅ dict 형태 지원 확인됨!
	        if isinstance(api_response, list):
	            result_list = []
	            for record in api_response:
	                record_dict = {}
	                for output_key, api_key in field_key.items():
	                    value = record.get(api_key)
	                    if value is not None:
	                        record_dict[output_key] = self._convert_value(value)
	                if record_dict:
	                    result_list.append(record_dict)
	            
	            if len(result_list) == 1:
	                return result_list[0]
	            elif len(result_list) > 1:
	                return result_list
	            else:
	                return None
	```
	
	**결론**: dict response_key `{"low": "low", "high": "high", "open": "open", "close": "close"}`가 정상 지원됨.

---

## I-03: targetMedian & consensusSummary 구현

### Python 코드 변경 (반영완료)

	**파일**: `backend/src/services/valuation_service.py`
	
	**변경 전** (라인 ~723):
	```python
	value_qualitative = {
	    'consensusSignal': consensus_signal  # ❌ targetMedian, consensusSummary 없음
	}
	```
	
	**변경 후** (라인 678-728):
	```python
	# I-03 적용: targetMedian & consensusSummary 계산
	target_median = 0
	consensus_summary = None
	
	try:
	    # 1. qualatative-consensusSummary 도메인 메트릭 로드
	    consensus_summary_metrics = await metrics.select_metrics_by_domain_prefix(
	        pool, 'qualatative-consensusSummary'
	    )
	    
	    if consensus_summary_metrics:
	        # 2. FMP API 호출하여 consensus summary 데이터 가져오기
	        async with FMPAPIClient() as fmp_client:
	            api_data = {}
	            consensus_target_data = await fmp_client.call_api(
	                'fmp-price-target-consensus',
	                {'ticker': ticker}
	            )
	            if consensus_target_data:
	                api_data['fmp-price-target-consensus'] = (
	                    consensus_target_data if isinstance(consensus_target_data, list) 
	                    else [consensus_target_data]
	                )
	            
	            # 3. MetricCalculationEngine으로 계산
	            engine = MetricCalculationEngine(
	                metrics_by_domain={'consensusSummary': consensus_summary_metrics}
	            )
	            engine.build_dependency_graph()
	            engine.topological_sort()
	            
	            calculated = engine.calculate_all(
	                api_data=api_data,
	                target_domains=['consensusSummary']
	            )
	            
	            # 4. consensusSummary 추출
	            if 'consensusSummary' in calculated:
	                consensus_summary = calculated['consensusSummary'].get('consensusSummary')
	                
	                # 5. targetMedian 추출
	                if isinstance(consensus_summary, dict):
	                    target_median = consensus_summary.get('targetMedian', 0)
	                    
	except Exception as e:
	    logger.warning(f"Failed to calculate consensusSummary/targetMedian: {e}")
	
	# value_qualitative 구성 (세 항목 모두 포함)
	value_qualitative = {
	    'targetMedian': target_median,           # ✅ 추가됨
	    'consensusSummary': consensus_summary,   # ✅ 추가됨
	    'consensusSignal': consensus_signal      # 기존 유지
	}
	```

---

## I-05: consensus 메트릭 추가

### SQL 변경 (반영완료 - 실행대기)

	**파일**: `backend/scripts/apply_issue_docs_changes.sql`
	
	**추가할 메트릭**:
	```sql
	INSERT INTO config_lv2_metric (id, source, api_list_id, response_key, domain, description)
	VALUES (
	  'consensus',
	  'api_field',
	  'fmp-price-target',
	  '{
	    "ticker": "symbol",
	    "newsURL": "newsURL",
	    "newsTitle": "newsTitle",
	    "event_date": "publishedDate",
	    "analystName": "analystName",
	    "newsBaseURL": "newsBaseURL",
	    "priceTarget": "priceTarget",
	    "newsPublisher": "newsPublisher",
	    "publishedDate": "publishedDate",
	    "adjPriceTarget": "adjPriceTarget",
	    "analystCompany": "analystCompany",
	    "priceWhenPosted": "priceWhenPosted"
	  }'::jsonb,
	  'qualatative-consensus',
	  'Consensus data from fmp-price-target API. Includes analyst info, news details, and price targets.'
	)
	ON CONFLICT (id) DO UPDATE SET
	  source = EXCLUDED.source,
	  api_list_id = EXCLUDED.api_list_id,
	  response_key = EXCLUDED.response_key,
	  domain = EXCLUDED.domain,
	  description = EXCLUDED.description;
	```

---

## I-07: source_id 파라미터 추가

### Python 코드 변경 (반영완료)

	**파일**: `backend/src/services/valuation_service.py`
	
	**변경 전**:
	```python
	async def calculate_qualitative_metrics(
	    pool,
	    ticker: str,
	    event_date,
	    source: str  # ❌ source_id 없음!
	) -> Dict[str, Any]:
	    # ...
	    consensus_data = await metrics.select_consensus_data(
	        pool, ticker, event_date  # ❌ source_id 없음!
	    )
	```
	
	**변경 후** (라인 578-621):
	```python
	async def calculate_qualitative_metrics(
	    pool,
	    ticker: str,
	    event_date,
	    source: str,
	    source_id: str  # ✅ 추가됨
	) -> Dict[str, Any]:
	    """
	    Calculate qualitative metrics.
	    
	    Uses source_id to find the exact evt_consensus row,
	    ensuring we compare the same analyst's previous values.
	    """
	    # ...
	    consensus_data = await metrics.select_consensus_data(
	        pool, ticker, event_date, source_id  # ✅ source_id 전달
	    )
	```
	
	**파일**: `backend/src/database/queries/metrics.py`
	
	**변경 후** (select_consensus_data 함수):
	```python
	async def select_consensus_data(
	    pool: asyncpg.Pool,
	    ticker: str,
	    event_date,
	    source_id: str  # ✅ 추가됨
	) -> Dict[str, Any]:
	    async with pool.acquire() as conn:
	        row = await conn.fetchrow(
	            """
	            SELECT id, ticker, event_date, analyst_name, analyst_company,
	                   price_target, price_when_posted,
	                   price_target_prev, price_when_posted_prev,
	                   direction, response_key
	            FROM evt_consensus
	            WHERE id = $1        -- ✅ source_id로 정확한 행 조회
	              AND ticker = $2
	              AND event_date = $3
	            """,
	            source_id,  # ✅ 정확한 행 찾기
	            ticker,
	            event_date
	        )
	        return dict(row) if row else None
	```

---

## I-08: 시간적 유효성 (Temporal Validity)

### Python 코드 변경 (반영완료)

	**파일**: `backend/src/services/valuation_service.py`
	
	**변경 전**:
	```python
	# FMP API 호출
	income_stmt = await fmp_client.get_income_statement(ticker, period='quarter', limit=4)  # ❌ limit=4 고정
	balance_sheet = await fmp_client.get_balance_sheet(ticker, period='quarter', limit=4)
	```
	
	**변경 후** (라인 425-504):
	```python
	# 1. limit=100으로 변경
	income_stmt_all = await fmp_client.get_income_statement(ticker, period='quarter', limit=100)
	balance_sheet_all = await fmp_client.get_balance_sheet(ticker, period='quarter', limit=100)
	
	# 2. event_date 변환
	if isinstance(event_date, str):
	    event_date_obj = datetime.fromisoformat(event_date.replace('Z', '+00:00')).date()
	elif hasattr(event_date, 'date'):
	    event_date_obj = event_date.date()
	else:
	    event_date_obj = event_date
	
	# 3. event_date 기준 필터링
	for api_id, data in api_data_raw.items():
	    if isinstance(data, list):
	        filtered_data = []
	        for record in data:
	            record_date_str = record.get('date')
	            if record_date_str:
	                try:
	                    record_date = datetime.fromisoformat(
	                        record_date_str.replace('Z', '+00:00')
	                    ).date()
	                    if record_date <= event_date_obj:  # ✅ 이전 분기만 사용
	                        filtered_data.append(record)
	                except:
	                    pass
	        api_data[api_id] = filtered_data
	        logger.info(f"Filtered {api_id}: {len(data)} -> {len(filtered_data)} records")
	
	# 4. 데이터 없을 시 에러
	if not has_data:
	    return {
	        'status': 'failed',
	        'value': None,
	        'message': f'no_valid_data: No data available before event_date {event_date_obj}'
	    }
	
	# 5. _meta 정보 기록
	value_quantitative[domain_key]['_meta'] = {
	    'date_range': {
	        'start': quarterly_data[3].get('date'),
	        'end': quarterly_data[0].get('date')
	    },
	    'calcType': 'TTM_fullQuarter' if quarters_used >= 4 else 'TTM_partialQuarter',
	    'count': quarters_used,
	    'event_date': str(event_date_obj),
	    'sector': company_info.get('sector'),
	    'industry': company_info.get('industry')
	}
	```

---

## I-09: Topological Sort 순서 수정

### Python 코드 변경 (반영완료)

	**파일**: `backend/src/services/metric_engine.py`
	
	**변경 전** (라인 121-163):
	```python
	# ❌ 잘못된 로직: 의존성에 대해 in-degree 증가
	for dependency in dependencies:
	    in_degree[dependency] += 1  # ❌ 반대로 됨
	```
	
	**변경 후**:
	```python
	def topological_sort(self):
	    """
	    Topological sort using Kahn's algorithm.
	    Ensures api_field metrics (no dependencies) are calculated first.
	    """
	    # in-degree: 이 메트릭이 의존하는 메트릭 개수
	    in_degree = {m: 0 for m in self.metrics_by_name.keys()}
	    
	    # 역방향 그래프: 각 메트릭에 의존하는 메트릭들
	    reverse_graph = defaultdict(list)
	    
	    # 의존성 분석
	    for metric_name, metric in self.metrics_by_name.items():
	        dependencies = self._get_dependencies(metric)
	        
	        # ✅ 올바른 로직: 메트릭 자체의 in-degree를 의존성 개수로 설정
	        in_degree[metric_name] = len(dependencies)
	        
	        # 역방향 그래프 구축
	        for dep in dependencies:
	            reverse_graph[dep].append(metric_name)
	    
	    # ✅ 의존성이 없는 메트릭(api_field)부터 시작
	    queue = deque([m for m, degree in in_degree.items() if degree == 0])
	    
	    sorted_order = []
	    while queue:
	        metric = queue.popleft()
	        sorted_order.append(metric)
	        
	        # 이 메트릭에 의존하는 메트릭들의 in-degree 감소
	        for dependent in reverse_graph[metric]:
	            in_degree[dependent] -= 1
	            if in_degree[dependent] == 0:
	                queue.append(dependent)
	    
	    self.sorted_metrics = sorted_order
	```

---

## I-10: priceEodOHLC_dateRange 정책 분리 (미반영)

### 필요한 변경

	**파일**: `backend/src/database/queries/policies.py`
	
	**추가해야 할 함수**:
	```python
	async def get_ohlc_date_range_policy(pool: asyncpg.Pool) -> Dict[str, int]:
	    """
	    Get OHLC API fetch date range policy.
	    Uses priceEodOHLC_dateRange policy, separate from fillPriceTrend_dateRange.
	    
	    Returns:
	        Dict with countStart, countEnd (calendar days)
	    """
	    policy = await select_policy(pool, 'priceEodOHLC_dateRange')
	    if not policy:
	        raise ValueError("Policy 'priceEodOHLC_dateRange' not found")
	    
	    policy_config = policy['policy']
	    return {
	        'countStart': int(policy_config['countStart']),
	        'countEnd': int(policy_config['countEnd'])
	    }
	```
	
	**파일**: `backend/src/services/valuation_service.py`
	
	**변경해야 할 코드**:
	```python
	# 현재 (잘못됨)
	fetch_start = min_date + timedelta(days=count_start * 2)  # ❌ fillPriceTrend_dateRange 재사용
	
	# 수정 후 (지침 준수)
	ohlc_policy = await policies.get_ohlc_date_range_policy(pool)
	fetch_start = min_date + timedelta(days=ohlc_policy['countStart'])  # ✅ 별도 정책 사용
	fetch_end = max_date + timedelta(days=ohlc_policy['countEnd'])
	```

---

## I-11: internal(qual) 메트릭 동적 사용 (미반영)

### 필요한 변경

	**파일**: `backend/src/database/queries/metrics.py`
	
	**추가해야 할 함수**:
	```python
	async def select_internal_qual_metrics(pool: asyncpg.Pool) -> List[Dict[str, Any]]:
	    """
	    Select internal(qual) metrics for analyst performance calculation.
	    
	    Filters by:
	        - domain = 'internal(qual)'
	        - base_metric_id = 'priceTrendReturnSeries'
	    """
	    async with pool.acquire() as conn:
	        rows = await conn.fetch("""
	            SELECT id, domain, expression, description,
	                   source, base_metric_id, aggregation_kind, 
	                   aggregation_params, response_key
	            FROM config_lv2_metric
	            WHERE domain = 'internal(qual)'
	              AND base_metric_id = 'priceTrendReturnSeries'
	            ORDER BY id
	        """)
	        return [dict(row) for row in rows]
	```
	
	**파일**: `backend/src/services/analyst_service.py`
	
	**변경해야 할 코드**:
	```python
	# 현재 (하드코딩)
	stats = analyst.calculate_statistics(returns)  # ❌ 하드코딩된 통계 계산
	
	# 수정 후 (DB 정의 기반)
	internal_metrics = await metrics.select_internal_qual_metrics(pool)
	if not internal_metrics:
	    return {'error': 'METRIC_NOT_FOUND', ...}
	
	# DB 메트릭 정의에서 통계 함수 매핑
	# Mean ← returnMeanByDayOffset
	# Median ← returnMedianByDayOffset
	# 1stQuartile ← returnFirstQuartileByDayOffset
	# 3rdQuartile ← returnThirdQuartileByDayOffset
	# InterquartileRange ← returnIQRByDayOffset
	# standardDeviation ← returnStdDevByDayOffset
	# count ← returnCountByDayOffset
	```

---

## SQL 실행 순서

### 1단계: 기본 스키마 설정 (아직 미실행 시)
	```bash
	# Supabase SQL Editor에서 실행
	backend/scripts/setup_supabase.sql
	```

### 2단계: 이슈 반영 SQL
	```bash
	# Supabase SQL Editor에서 실행
	backend/scripts/apply_issue_docs_changes.sql
	```

### 검증 쿼리
	```sql
	-- I-01: consensusSignal 설정 확인
	SELECT id, source, expression, aggregation_kind, domain
	FROM config_lv2_metric
	WHERE id = 'consensusSignal';
	
	-- I-05: consensus 메트릭 추가 확인
	SELECT id, source, api_list_id, domain
	FROM config_lv2_metric
	WHERE id = 'consensus';
	
	-- 전체 qualatative 메트릭 확인
	SELECT id, source, domain
	FROM config_lv2_metric
	WHERE domain LIKE 'qualatative-%'
	ORDER BY id;
	```

---

## I-12: 동적 계산 코드 실행 실패

### I-12-A: 문제 로그 분석

**로그 출력**:
```
[MetricEngine] Dynamic calculation execution failed: invalid syntax (<string>, line 2)
[MetricEngine] Dynamic calculation failed for yoyFromQuarter, falling back to hardcoded: invalid syntax (<string>, line 2)
```

**영향받는 함수들**:
- `yoyFromQuarter`: 전년동기 대비 증감률
- `qoqFromQuarter`: 전분기 대비 증감률  
- `lastFromQuarter`: 최신 1개 값 반환
- `avgFromQuarter`: 분기 평균
- `ttmFromQuarterSumOrScaled`: TTM 합산

**현재 동작**:
```python
# backend/src/services/metric_engine.py:494-508
transform_def = self.transforms.get(aggregation_kind)
if transform_def and transform_def.get('calculation'):
    try:
        return self._execute_dynamic_calculation(
            transform_def['calculation'],
            base_values,
            aggregation_params
        )
    except Exception as e:
        logger.warning(
            f"[MetricEngine] Dynamic calculation failed for {aggregation_kind}, "
            f"falling back to hardcoded: {e}"
        )
        # Fall through to hardcoded functions ✅ 폴백 작동
```

### I-12-B: 원인 분석

**calculation 컬럼 코드 예시** (seed_calculation_codes.sql):
```sql
UPDATE config_lv2_metric_transform
SET calculation = $$
if not quarterly_values:
    return None

current = quarterly_values[0]
previous = quarterly_values[1]

if previous == 0:
    return None

return (current - previous) / previous
$$
WHERE id = 'qoqFromQuarter';
```

**문제점**:
1. `$$` 구분자로 감싼 코드가 DB에 저장될 때 공백이나 개행 문자 포함
2. `eval()` 실행 시 첫 줄 파싱 에러 발생
3. Python의 `eval()`은 single expression만 지원하나, 코드는 multiple statements

### I-12-C: 해결 방안

**옵션 A: exec() 사용으로 변경** (권장)
```python
# backend/src/services/metric_engine.py:526-608
def _execute_dynamic_calculation(
    self,
    calculation_code: str,
    quarterly_values: List[float],
    params: Dict[str, Any]
) -> Any:
    # ... namespace 설정 ...
    
    try:
        # eval() → exec() + return value 추출
        local_vars = {}
        exec(calculation_code, safe_namespace, local_vars)
        return local_vars.get('result')  # 코드가 result 변수 설정 필요
    except Exception as e:
        logger.error(f"[MetricEngine] Dynamic calculation execution failed: {e}")
        logger.debug(f"[MetricEngine] Calculation code: {calculation_code[:200]}...")
        raise
```

**옵션 B: calculation 코드 재작성**
```sql
-- qoqFromQuarter를 single expression으로 변경
UPDATE config_lv2_metric_transform
SET calculation = 'None if len(quarterly_values) < 2 or quarterly_values[1] == 0 else (quarterly_values[0] - quarterly_values[1]) / quarterly_values[1]'
WHERE id = 'qoqFromQuarter';
```

**옵션 C: 하드코딩 유지** (현재 상태)
- 장점: 이미 테스트되고 안정적
- 단점: DB 설정과 불일치

### I-12-D: 검증 SQL

```sql
-- calculation 컬럼 내용 확인
SELECT 
    id, 
    calculation,
    LENGTH(calculation) as code_length,
    LEFT(calculation, 50) as first_50_chars
FROM config_lv2_metric_transform
WHERE calculation IS NOT NULL
ORDER BY id;

-- 문제가 있는 코드 확인
SELECT id, calculation
FROM config_lv2_metric_transform  
WHERE calculation LIKE E'%\n%'  -- 개행 문자 포함
   OR calculation LIKE '  %';    -- 시작 공백 포함
```

### I-12-E: 적용된 해결 방안 (반영완료)

**파일**: `backend/scripts/fix_calculation_single_expression.sql`

**수정 내용**:
```sql
-- avgFromQuarter: 분기 시계열 평균
UPDATE config_lv2_metric_transform
SET calculation = 'None if not quarterly_values else sum(quarterly_values[:params.get("window", 4)]) / len(quarterly_values[:params.get("window", 4)])'
WHERE id = 'avgFromQuarter';

-- ttmFromQuarterSumOrScaled: TTM 합산
UPDATE config_lv2_metric_transform
SET calculation = 'None if not quarterly_values or len(quarterly_values[:params.get("window", 4)]) < params.get("min_points", 1) else (lambda recent: sum(recent) if len(recent) >= params.get("scale_to", 4) else (sum(recent) / len(recent)) * params.get("scale_to", 4))(quarterly_values[:params.get("window", 4)])'
WHERE id = 'ttmFromQuarterSumOrScaled';

-- lastFromQuarter: 최신 값 반환
UPDATE config_lv2_metric_transform
SET calculation = 'None if not quarterly_values else quarterly_values[0]'
WHERE id = 'lastFromQuarter';

-- qoqFromQuarter: 전분기 대비 증감률
UPDATE config_lv2_metric_transform
SET calculation = 'None if len(quarterly_values) < 2 or quarterly_values[1] == 0 else (quarterly_values[0] - quarterly_values[1]) / quarterly_values[1]'
WHERE id = 'qoqFromQuarter';

-- yoyFromQuarter: 전년동기 대비 증감률
UPDATE config_lv2_metric_transform
SET calculation = 'None if len(quarterly_values) < 5 or quarterly_values[4] == 0 else (quarterly_values[0] - quarterly_values[4]) / quarterly_values[4]'
WHERE id = 'yoyFromQuarter';
```

**핵심 변경**:
- multiple statements → single expression
- lambda 함수 활용으로 복잡한 로직 표현
- conditional expression (ternary operator) 사용

---

## I-13: priceEodOHLC 데이터 추출 실패

### I-13-A: 문제 로그 분석

**로그 출력**:
```
[calculate_quantitative_metrics] Fetched fmp-historical-price-eod-full: 1176 records
[calculate_quantitative_metrics] Filtered fmp-historical-price-eod-full: 1176 -> 0 records for event_date 2021-01-31

# 두 번째 이벤트
[calculate_quantitative_metrics] Filtered fmp-historical-price-eod-full: 1176 -> 39 records for event_date 2021-06-16
[priceEodOHLC] Dict response_key processing: field_key={'low': 'low', 'high': 'high', 'open': 'open', 'close': 'close'}, api_response type=<class 'list'>, len=39
[priceEodOHLC] Extracted 0 dicts from 39 records
[priceEodOHLC] Returning None: result_list is empty
```

**문제**:
- API에서 1176개 레코드 받음
- 날짜 필터링으로 39개로 축소됨
- **필드 매핑에서 0개 추출** ← 핵심 문제

### I-13-B: 원인 분석

**현재 설정** (config_lv2_metric):
```json
{
  "id": "priceEodOHLC",
  "api_list_id": "fmp-historical-price-eod-full",
  "response_key": {
    "low": "low",
    "high": "high", 
    "open": "open",
    "close": "close"
  }
}
```

**필드 추출 로직** (metric_engine.py:389-414):
```python
for record in api_response:
    record_dict = {}
    for output_key, api_key in field_key.items():
        value = record.get(api_key)  # ← 여기서 None 반환됨
        if value is not None:
            record_dict[output_key] = self._convert_value(value)
    if record_dict:  # ← record_dict가 비어있어서 추가 안됨
        result_list.append(record_dict)
```

**예상 원인**:
1. FMP API가 `low`, `high`, `open`, `close` 필드명 대신 다른 이름 사용
2. 가능한 실제 필드명: `adjClose`, `adjHigh`, `adjLow`, `adjOpen` (adjusted 값)
3. 또는: `unadjustedClose`, `unadjustedHigh` 등

### I-13-C: 검증 SQL

```sql
-- 1. priceEodOHLC 메트릭 설정 확인
SELECT 
    id,
    api_list_id,
    response_key::text,
    domain,
    source
FROM config_lv2_metric 
WHERE id = 'priceEodOHLC';

-- 2. fmp-historical-price-eod-full API 스키마 확인
SELECT 
    api,
    endpoint,
    schema::text as response_schema
FROM config_lv1_api_list 
WHERE api = 'fmp-historical-price-eod-full';

-- 3. API 스키마에서 실제 필드명 확인
SELECT 
    api,
    jsonb_object_keys(schema) as field_name
FROM config_lv1_api_list 
WHERE api = 'fmp-historical-price-eod-full';
```

### I-13-D: 해결 방안

**옵션 A: response_key 수정** (권장 - 간단)
```sql
-- adjusted 필드 사용
UPDATE config_lv2_metric
SET response_key = '{
    "low": "adjLow",
    "high": "adjHigh",
    "open": "adjOpen",
    "close": "adjClose"
}'::jsonb
WHERE id = 'priceEodOHLC';
```

**옵션 B: 두 가지 필드 모두 지원** (안전)
```python
# metric_engine.py 수정
for output_key, api_key in field_key.items():
    # Try adjusted field first, fallback to unadjusted
    value = record.get(f"adj{api_key.capitalize()}") or record.get(api_key)
    if value is not None:
        record_dict[output_key] = self._convert_value(value)
```

**옵션 C: API 응답 로깅 강화**
```python
# valuation_service.py에 임시 로깅 추가
if api_id == 'fmp-historical-price-eod-full' and data:
    logger.info(f"[DEBUG] OHLC API sample record: {data[0]}")
    logger.info(f"[DEBUG] OHLC API keys: {list(data[0].keys())}")
```

### I-13-E: 테스트 스크립트

```python
# backend/test_ohlc_fields.py
import asyncio
import asyncpg

async def test_ohlc_fields():
    conn = await asyncpg.connect(
        "postgresql://postgres:password@localhost:54322/postgres"
    )
    
    # 1. 현재 response_key 확인
    row = await conn.fetchrow(
        "SELECT response_key FROM config_lv2_metric WHERE id = 'priceEodOHLC'"
    )
    print(f"Current response_key: {row['response_key']}")
    
    # 2. API 스키마 확인
    row = await conn.fetchrow(
        "SELECT schema FROM config_lv1_api_list WHERE api = 'fmp-historical-price-eod-full'"
    )
    print(f"\nAPI schema fields:")
    for key in row['schema'].keys():
        print(f"  - {key}")
    
    await conn.close()

asyncio.run(test_ohlc_fields())
```

### I-13-F: 실제 원인 및 해결 (반영완료)

**실제 원인 발견**:
- FMP API 실제 응답 확인 결과: 필드명은 `low`, `high`, `open`, `close`로 정확함
- 문제는 `calculate_quantitative_metrics()`에서 API 호출 시 **필수 파라미터 누락**
- `fmp-historical-price-eod-full` API는 `{fromDate}`, `{toDate}` 파라미터 필요
- 파라미터 없이 호출하면 URL에 `{fromDate}`, `{toDate}` placeholder가 그대로 남음

**로그 증거**:
```
URL template variable 'fromDate' not provided, keeping placeholder
URL template variable 'toDate' not provided, keeping placeholder
[API Call] fmp-historical-price-eod-full -> https://...?symbol=RGTI&from={fromDate}&to={toDate}&apikey=...
```

**적용한 수정** (`backend/src/services/valuation_service.py:431-456`):
```python
# 수정 전
for api_id in required_apis:
    result = await fmp_client.call_api(api_id, {
        'ticker': ticker,
        'period': 'quarter',
        'limit': 100
    })

# 수정 후
for api_id in required_apis:
    # Prepare API-specific parameters
    params = {'ticker': ticker}
    
    # Add API-specific parameters
    if 'historical-price' in api_id or 'eod' in api_id:
        # Historical price APIs need date range
        params['fromDate'] = '2000-01-01'  # Far past for sufficient data
        params['toDate'] = event_date_obj.strftime('%Y-%m-%d')
    else:
        # Quarterly financial APIs
        params['period'] = 'quarter'
        params['limit'] = 100
    
    result = await fmp_client.call_api(api_id, params)
```

**전체 서비스 점검 결과**:
- 총 11개 `call_api()` 호출 위치 검증
- 모든 위치에서 config_lv1_api_list 사용 확인
- `get_historical_price_eod()` 메서드는 올바르게 파라미터 전달
- 문제는 `calculate_quantitative_metrics()`의 동적 API 호출 부분만 해당

**검증 필요 사항**:
- 다른 API들도 필수 파라미터가 있는지 확인
- `config_lv1_api_list.api` 컬럼의 URL 템플릿 검토

---

## I-14: fmp-aftermarket-trade API 401 오류

### I-14-A: 문제 로그 분석

**로그 출력**:
```
[API Call] fmp-aftermarket-trade -> https://financialmodelingprep.com/stable/aftermarket-trade?symbol=RGTI?apikey=8AP6lUDNsrBwtx5IzVoDliKnG186rBSt
[API Error] fmp-aftermarket-trade -> HTTPStatusError: Client error '401 Unauthorized'
[calculate_quantitative_metrics] Failed to fetch fmp-aftermarket-trade: Client error '401 Unauthorized'
```

**문제점**:
1. **이중 `?` 문자**: `...?symbol=RGTI?apikey=...` ← 잘못된 URL
2. **401 Unauthorized**: API 키가 있지만 권한 거부

### I-14-B: 원인 분석

**URL 구성 로직** (external_api.py):
```python
async def call_api(self, api_id: str, params: Dict[str, str] = None):
    # DB에서 endpoint 템플릿 가져오기
    api_config = self.api_configs.get(api_id)
    url_template = api_config['endpoint']  # 예: "...?symbol={ticker}"
    
    # 파라미터 치환
    url = url_template.format(**params)
    
    # API 키 추가
    if '?' in url:
        url = f"{url}&apikey={api_key}"  # ✅ 올바름
    else:
        url = f"{url}?apikey={api_key}"  # ❌ 이미 ?가 있으면 문제
```

**DB 설정 확인 필요**:
```sql
SELECT api, endpoint
FROM config_lv1_api_list
WHERE api = 'fmp-aftermarket-trade';
```

**예상 DB 값**:
```
endpoint: "/aftermarket-trade?symbol={ticker}?"
                                            ^ 불필요한 ?
```

### I-14-C: 해결 방안

**옵션 A: DB endpoint 수정** (권장)
```sql
UPDATE config_lv1_api_list
SET endpoint = '/aftermarket-trade?symbol={ticker}'
WHERE api = 'fmp-aftermarket-trade';
```

**옵션 B: Python 코드에서 처리**
```python
# external_api.py: call_api 함수 수정
url = url_template.format(**params)

# URL 정규화: 중복 ? 제거
url = url.replace('??', '?').rstrip('?')

# API 키 추가
if '?' in url:
    url = f"{url}&apikey={api_key}"
else:
    url = f"{url}?apikey={api_key}"
```

**옵션 C: 메트릭을 optional로 처리**
```python
# metric_engine.py에서 priceAfter 실패 시 None 반환
if metric.get('name') == 'priceAfter' and api_response is None:
    logger.debug("[MetricEngine] priceAfter API unavailable, skipping")
    return None
```

**옵션 D: API 비활성화**
```sql
-- aftermarket API 비활성화
UPDATE config_lv1_api_list
SET is_active = false
WHERE api = 'fmp-aftermarket-trade';

-- 또는 priceAfter 메트릭 비활성화
UPDATE config_lv2_metric
SET domain = 'disabled'  -- internal에서 제외
WHERE id = 'priceAfter';
```

### I-14-D: 검증 SQL

```sql
-- 1. aftermarket API 설정 확인
SELECT 
    api,
    endpoint,
    api_service,
    is_active
FROM config_lv1_api_list
WHERE api LIKE '%aftermarket%';

-- 2. priceAfter 메트릭 확인  
SELECT 
    id,
    api_list_id,
    domain,
    response_key
FROM config_lv2_metric
WHERE id = 'priceAfter';

-- 3. endpoint에 ? 문자 개수 확인
SELECT 
    api,
    endpoint,
    LENGTH(endpoint) - LENGTH(REPLACE(endpoint, '?', '')) as question_mark_count
FROM config_lv1_api_list
WHERE endpoint LIKE '%?%'
ORDER BY question_mark_count DESC;
```

### I-14-E: FMP API 권한 확인

```bash
# 수동 테스트: aftermarket API 접근 가능 여부 확인
curl "https://financialmodelingprep.com/stable/aftermarket-trade?symbol=AAPL&apikey=YOUR_KEY"

# 예상 응답:
# - 200 OK: API 접근 가능
# - 401 Unauthorized: API 키 문제 또는 플랜 권한 없음
# - 403 Forbidden: 엔드포인트 접근 불가 (플랜 업그레이드 필요)
```

---

## 런타임 이슈 우선순위

| ID | 이슈 | 우선순위 | 영향도 | 해결 난이도 |
|----|------|----------|--------|-------------|
| I-13 | priceEodOHLC 추출 실패 | 🔴 높음 | 높음 (OHLC 데이터 전체) | 낮음 (SQL 수정) |
| I-14 | aftermarket API 401 | ⚠️ 중간 | 낮음 (1개 메트릭) | 낮음 (SQL 수정) |
| I-12 | 동적 계산 코드 실패 | ⚠️ 낮음 | 없음 (폴백 작동) | 중간 (코드 재작성) |

**권장 조치 순서**:
1. ✅ **I-13 우선 해결**: DB 스키마 확인 → response_key 수정
2. ✅ **I-14 간단 수정**: endpoint URL에서 불필요한 `?` 제거
3. ⏸️ **I-12 보류**: 하드코딩 폴백으로 정상 작동 중

---

## 추가 이슈 (I-15 ~ I-17)

> **참조**: `3_DETAIL_I15-I17.md` 문서에 상세 내용 기록

### I-15: event_date_obj 변수 순서 오류
- **상태**: ✅ 해결 완료
- **파일**: `backend/src/services/valuation_service.py:425-456`
- **내용**: event_date_obj 변환 로직을 API 호출 전으로 이동

### I-16: 메트릭 실패 디버깅 로그 부재
- **상태**: ✅ 해결 완료
- **파일**: `backend/src/services/metric_engine.py:241-326`
- **내용**: `_calculate_metric_with_reason()` 메서드 추가, 실패 이유 분류

### I-17: 로그 형식 N/A 과다 출력
- **상태**: ✅ 해결 완료
- **파일**: `backend/src/services/utils/logging_utils.py:15-91`
- **문서**: `backend/LOGGING_GUIDE.md`
- **내용**: 구조화된 데이터 없으면 단순 포맷 사용

---

*마지막 업데이트: 2025-12-25 (I-15~I-17 추가)*
