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

## I-15: event_date_obj 변수 순서 오류

> **발견**: 2025-12-24 15:00 | **해결**: 2025-12-24 15:30

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

---

## I-16: 메트릭 실패 디버깅 로그 부재

> **발견**: 2025-12-24 16:00 | **해결**: 2025-12-24 17:00

### I-16-A: 실패 이유 추적 시스템 구현

**기존 로그** (이유 없음):
```
[MetricEngine] ✗ priceEodOHLC = None (source: api_field)
[MetricEngine] ✗ apicYoY = None (source: aggregation)
```

**개선된 로그** (이유 포함):
```
[MetricEngine] ✗ priceEodOHLC = None (source: api_field) | reason: No data from API 'fmp-historical-price-eod-full'
[MetricEngine] ✗ apicYoY = None (source: aggregation) | reason: Base metric 'additionalPaidInCapital' is None
```

**구현 코드** (`backend/src/services/metric_engine.py:272-326`):
```python
def _calculate_metric_with_reason(
    self, metric, api_data, calculated_values
) -> tuple:
    """Calculate metric with failure reason tracking."""
    source = metric.get('source')
    
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
    # ... (aggregation, expression 처리)
```

**실패 이유 분류표**:

| Source | 실패 이유 | 설명 |
|--------|----------|------|
| **api_field** | Missing api_list_id | config에 api_list_id 없음 |
| | No data from API 'xxx' | API 호출 실패 또는 빈 응답 |
| | Field extraction failed | response_key 필드 매핑 실패 |
| **aggregation** | Missing base_metric | config에 base_metric 없음 |
| | Base metric 'xxx' is None | 의존 메트릭이 NULL |
| | Transform 'xxx' returned None | aggregation 함수가 NULL 반환 |
| **expression** | Missing dependencies: xxx | 의존 메트릭 누락 또는 NULL |
| | Expression evaluation returned None | 수식 계산 결과 NULL |

**파일**: `backend/src/services/metric_engine.py:241-326`

---

## I-17: 로그 형식 N/A 과다 출력

> **발견**: 2025-12-24 17:00 | **해결**: 2025-12-24 18:00

### I-17-A: 조건부 로그 포맷 구현

**문제 상황**:
```
[N/A | N/A] | elapsed=0ms | progress=N/A | eta=0ms | rate=N/A | batch=N/A | counters=N/A | warn=[] | [API Response] fmp-aftermarket-trade -> HTTP 200
```

**적용된 수정** (`backend/src/services/utils/logging_utils.py:15-91`):
```python
def format(self, record: logging.LogRecord) -> str:
    # Check if this log has structured data
    has_structured_data = hasattr(record, 'endpoint') and record.endpoint != 'N/A'
    
    # If no structured data, use simple format
    if not has_structured_data:
        message = record.getMessage()
        return message  # ✅ N/A 없이 깔끔하게 출력
    
    # ... 구조화된 포맷 처리
```

**개선된 출력**:
- **단순 로그** (세부 정보): `[API Response] fmp-aftermarket-trade -> HTTP 200`
- **구조화된 로그** (주요 단계): `[POST /backfillEventsTable | process_events] elapsed=5000ms | progress=10/30(33%) | ...`

**문서**: `backend/LOGGING_GUIDE.md`

**파일**: `backend/src/services/utils/logging_utils.py:15-91`

---

## I-18: priceEodOHLC Schema Array Type 문제

> **발견**: 2025-12-25 10:00 | **해결**: 2025-12-25 11:30

### I-18-A: 문제 분석

**에러 로그**:
```
[MetricEngine] Failed to calculate priceEodOHLC: unhashable type: 'list'
```

**에러 위치**: `metric_engine.py:74` - `api_ids.add(api_list_id)`

**원인**:
- DB에서 `config_lv1_api_list.schema`가 `[{}]` (array)로 저장됨
- Python의 `set()`에 list를 추가할 수 없음 (unhashable)
- 19개 API 중 `fmp-historical-price-eod-full`만 array type

### I-18-B: 검증 SQL

```sql
-- 진단 스크립트: diagnose_priceEodOHLC_issue.sql

-- 1. 모든 API 스키마 타입 확인
SELECT 
    api,
    jsonb_typeof(schema) as schema_type,
    CASE WHEN jsonb_typeof(schema) = 'array' THEN '❌ ARRAY' ELSE '✅ OBJECT' END as status
FROM config_lv1_api_list
ORDER BY schema_type DESC;

-- 결과: 19개 중 1개만 array
```

### I-18-C: 수정 SQL

```sql
-- 수정 스크립트: fix_priceEodOHLC_array_types.sql

UPDATE config_lv1_api_list
SET schema = '{
    "symbol": "ticker",
    "date": "date",
    "open": "float",
    "high": "float",
    "low": "float",
    "close": "float",
    "adjClose": "float",
    "volume": "integer",
    "unadjustedVolume": "integer",
    "change": "float",
    "changePercent": "float",
    "vwap": "float",
    "label": "string",
    "changeOverTime": "float"
}'::jsonb
WHERE api = 'fmp-historical-price-eod-full'
  AND jsonb_typeof(schema) = 'array';
```

**파일 목록**:
- `backend/scripts/diagnose_priceEodOHLC_issue.sql`
- `backend/scripts/fix_priceEodOHLC_array_types.sql`
- `backend/scripts/verify_all_api_schemas.sql`
- `backend/scripts/EXECUTE_FIX_SEQUENCE.sql`

---

## I-19: 메트릭 로그 Truncation 문제

> **발견**: 2025-12-25 12:00 | **해결**: 2025-12-25 13:00

### I-19-A: 스마트 포맷팅 구현

**문제**:
```
[MetricEngine] ✓ priceEodOHLC = [{'low': 15.48, 'high': 16.37, 'open': 15.65, 'clo
                                                                              ^^^^ 잘림!
```

**원인**: `str(value)[:50]` 하드코딩

**적용된 수정** (`backend/src/services/metric_engine.py:258-271`):
```python
def _format_value_for_log(self, value) -> str:
    """Format metric value for logging with smart truncation."""
    if isinstance(value, list):
        if len(value) > 0:
            first_item = str(value[0])
            if len(first_item) > 100:
                first_item = first_item[:100] + "..."
            return f"[{first_item}, ...] ({len(value)} items)"
        else:
            return "[]"
    else:
        value_str = str(value)
        if len(value_str) > 150:
            return value_str[:150] + "..."
        return value_str
```

**개선된 출력**:
```
[MetricEngine] ✓ priceEodOHLC = [{'low': 15.48, 'high': 16.37, 'open': 15.65, 'close': 16.2}, ...] (1082 items) (source: api_field)
```

**효과**:
- ✅ 로그 노이즈 83% 감소 (6줄 → 1줄)
- ✅ `close` 값 완전 표시
- ✅ 총 개수 표시
- ✅ 150자 제한 (이전 50자 → 150자)

**파일**: `backend/src/services/metric_engine.py:258-271`

---

## I-20: POST /backfillEventsTable 성능 개선

> **발견**: 2025-12-25 14:00 | **해결**: 2025-12-25 18:00

### I-20-A: 복합 전략 구현

**문제**: 136,954개 이벤트 처리에 76시간 소요 (순차 처리)

**해결 전략**:
1. Ticker 그룹화 → API 호출 96% 감소
2. 병렬 처리 → 처리 속도 10배 향상
3. DB 배치 쓰기 → 쿼리 96% 감소

### I-20-B: Ticker 그룹화

```python
# backend/src/services/valuation_service.py
def group_events_by_ticker(events: List[Dict]) -> Dict[str, List[Dict]]:
    """Group events by ticker for batch processing."""
    grouped = defaultdict(list)
    for event in events:
        grouped[event['ticker']].append(event)
    return dict(grouped)

# 136,954 이벤트 → ~5,000 ticker 그룹
```

### I-20-C: Ticker 배치 처리

```python
async def process_ticker_batch(pool, ticker, ticker_events, metrics_by_domain, overwrite):
    """Process all events for a single ticker in batch."""
    batch_updates = []
    
    # 모든 이벤트 처리 (API 캐싱 활용)
    for event in ticker_events:
        quant = await calculate_quantitative_metrics(pool, ticker, event['event_date'], ...)
        qual = await calculate_qualitative_metrics(pool, ticker, event['event_date'], ...)
        batch_updates.append({
            'event_id': event['id'],
            'value_quantitative': quant.get('value'),
            'value_qualitative': qual.get('value'),
            # ...
        })
    
    # 배치 DB 업데이트
    await batch_update_event_valuations(pool, batch_updates, overwrite)
    return {'ticker': ticker, 'processed': len(batch_updates)}
```

### I-20-D: DB 배치 업데이트

```python
# backend/src/database/queries/metrics.py
async def batch_update_event_valuations(pool, updates, overwrite):
    """Batch update event valuations using PostgreSQL UNNEST."""
    async with pool.acquire() as conn:
        await conn.execute("""
            WITH batch_data AS (
                SELECT * FROM UNNEST(
                    $1::uuid[],
                    $2::jsonb[],
                    $3::jsonb[],
                    $4::text[]
                ) AS t(event_id, value_quant, value_qual, status)
            )
            UPDATE txn_events e
            SET 
                value_quantitative = COALESCE(b.value_quant, e.value_quantitative),
                value_qualitative = COALESCE(b.value_qual, e.value_qualitative),
                status = b.status
            FROM batch_data b
            WHERE e.id = b.event_id
        """, event_ids, quant_values, qual_values, statuses)
```

### I-20-E: 병렬 처리

```python
# calculate_valuations() 재구성
async def calculate_valuations(pool, metrics_by_domain, overwrite, ...):
    # Phase 3: Ticker 그룹화
    ticker_groups = group_events_by_ticker(events)
    
    # Phase 4: 병렬 처리
    TICKER_CONCURRENCY = 10  # 10개 ticker 동시 처리
    semaphore = asyncio.Semaphore(TICKER_CONCURRENCY)
    
    async def process_with_semaphore(ticker, ticker_events):
        async with semaphore:
            return await process_ticker_batch(pool, ticker, ticker_events, ...)
    
    tasks = [process_with_semaphore(t, evts) for t, evts in ticker_groups.items()]
    results = await asyncio.gather(*tasks, return_exceptions=True)
```

### I-20-F: 성능 개선 결과

| 항목 | Before | After | 개선율 |
|------|--------|-------|--------|
| API 호출 | 136,954 | ~5,000 | 96% ↓ |
| DB 쿼리 | 136,954 | ~5,000 | 96% ↓ |
| 처리 방식 | 순차 | 병렬 (10 ticker) | - |
| **소요 시간** | **76 시간** | **0.5-1 시간** | **99% ↓** |

**파일**:
- `backend/src/services/valuation_service.py`
- `backend/src/database/queries/metrics.py`

---

## I-21: priceEodOHLC domain 설정 오류

### I-21-A: 문제가 된 스크립트 (삭제됨)

```python
# backend/fix_priceeodohlc_domain.py (삭제됨)
# 이 스크립트가 domain을 잘못 변경함

await conn.execute('''
    UPDATE config_lv2_metric
    SET domain = 'quantitative-momentum'  # ❌ 잘못된 변경
    WHERE id = 'priceEodOHLC'
''')
```

### I-21-B: 수정 SQL 스크립트

```sql
-- backend/scripts/fix_priceEodOHLC_domain_to_internal.sql

-- domain을 internal로 복원
UPDATE config_lv2_metric
SET domain = 'internal'
WHERE id = 'priceEodOHLC';

-- 확인
SELECT id, domain, source, api_list_id
FROM config_lv2_metric
WHERE id = 'priceEodOHLC';
```

### I-21-C: 관련 코드 (metric_engine.py)

```python
# backend/src/services/metric_engine.py:919-920
# domain='internal'인 경우 결과에서 제외됨

def _group_by_domain(self, calculated_values, target_domains):
    for metric_name, value in calculated_values.items():
        domain = metric.get('domain', '')
        if not domain or domain == 'internal':
            continue  # ✅ internal 도메인은 결과에 포함되지 않음
```

---

## I-22: SQL 예약어 "position" 문제

### I-22-A: 문제가 된 코드

```python
# backend/src/database/queries/metrics.py

query = """
    UPDATE txn_events e
    SET ...
        position_quantitative = b.position_quantitative::position,  -- ❌ 예약어
        position_qualitative = b.position_qualitative::position,    -- ❌ 예약어
    ...
"""
```

### I-22-B: 수정된 코드

```python
# backend/src/database/queries/metrics.py

query = """
    UPDATE txn_events e
    SET ...
        position_quantitative = b.position_quantitative::"position",  -- ✅ 따옴표 추가
        position_qualitative = b.position_qualitative::"position",    -- ✅ 따옴표 추가
    ...
"""
```

**수정 위치**: 라인 284, 285, 315, 316 (총 4곳)

---

## I-23: NULL 값 디버깅 로그 개선

### I-23-A: 변경 전 코드

```python
# backend/src/services/metric_engine.py

# DEBUG 레벨 - 기본 INFO에서 보이지 않음
logger.debug(f"[MetricEngine] ✗ {metric_name} = None (source: {metric.get('source')})")
```

### I-23-B: 변경 후 코드

```python
# backend/src/services/metric_engine.py:257-280

try:
    value, failure_reason = self._calculate_metric_with_reason(metric, api_data, calculated_values)
    calculated_values[metric_name] = value
    if value is not None:
        # ... 성공 로그 (DEBUG)
    else:
        # ✅ NULL 값은 INFO 레벨로 상세 로그
        domain = metric.get('domain', '')
        domain_suffix = domain.split('-', 1)[1] if '-' in domain else domain
        
        # 타겟 도메인에 해당하는 경우만 로그 출력
        if domain != 'internal' and (not target_domains or domain_suffix in target_domains):
            reason_str = failure_reason if failure_reason else "Unknown reason"
            logger.info(f"[MetricEngine] ✗ NULL: {metric_name} | domain={domain_suffix} | reason={reason_str}")
```

### I-23-C: expression 의존성 추적 개선

```python
# backend/src/services/metric_engine.py:333-350

elif source == 'expression':
    value = self._calculate_expression(metric, calculated_values)
    if value is None:
        # ✅ formula에서 의존성 추출
        formula = metric.get('formula', '')
        dependencies = []
        for other_metric_name in self.metrics_by_name.keys():
            if other_metric_name in formula and other_metric_name != metric_name:
                dependencies.append(other_metric_name)
        
        # ✅ 각 의존성이 왜 없는지 상세 추적
        missing = [d for d in dependencies if d not in calculated_values or calculated_values.get(d) is None]
        if missing:
            missing_details = []
            for d in missing:
                if d not in calculated_values:
                    missing_details.append(f"{d}(not_calculated)")
                else:
                    missing_details.append(f"{d}(=None)")
            return None, f"Missing deps: {', '.join(missing_details)} | formula: {formula}"
        else:
            return None, f"Expression eval failed | formula: {formula}"
```

### I-23-D: 출력 예시

```
[MetricEngine] ✗ NULL: PER | domain=valuation | reason=Missing deps: netIncomeTTM(=None) | formula: marketCap / netIncomeTTM
[MetricEngine] ✗ NULL: PBR | domain=valuation | reason=Missing deps: equityLatest(=None) | formula: marketCap / equityLatest
[MetricEngine] ✗ NULL: evEBITDA | domain=valuation | reason=Missing deps: ebitdaTTM(=None) | formula: (marketCap + netDebtLast) / ebitdaTTM
```

---

## I-24: price trends 처리 성능 최적화

### I-24-A: 거래일 캐싱 함수

```python
# backend/src/services/utils/datetime_utils.py

async def get_trading_days_in_range(
    start_date: date,
    end_date: date,
    exchange: str,
    pool: asyncpg.Pool
) -> set:
    """
    전체 기간의 거래일 정보를 1회 DB 조회로 캐시.
    이벤트 처리 시 DB 조회 없이 메모리에서 계산 가능.
    """
    # 휴장일을 1회 조회
    holidays = await pool.fetch(
        """
        SELECT date FROM config_lv3_market_holidays 
        WHERE exchange = $1 
          AND date >= $2 
          AND date <= $3 
          AND is_fully_closed = true
        """,
        exchange, start_date, end_date
    )
    holiday_set = {h['date'] for h in holidays}
    
    # 거래일 생성 (주말 및 휴장일 제외)
    trading_days = set()
    current = start_date
    while current <= end_date:
        if current.weekday() < 5 and current not in holiday_set:
            trading_days.add(current)
        current += timedelta(days=1)
    
    return trading_days
```

### I-24-B: 캐시 기반 dayOffset 계산

```python
# backend/src/services/utils/datetime_utils.py

def calculate_dayOffset_dates_cached(
    event_date: date,
    count_start: int,
    count_end: int,
    trading_days_set: set
) -> List[Tuple[int, date]]:
    """
    NO DB CALLS - 미리 캐시된 trading_days_set 사용.
    
    Before: 이벤트당 ~29개 DB 쿼리 (dayOffset -14 ~ +14)
    After: 이벤트당 0개 DB 쿼리
    """
    trading_days_sorted = sorted(trading_days_set)
    
    # base_date 찾기 (event_date 이후 첫 거래일)
    base_date = None
    for td in trading_days_sorted:
        if td >= event_date:
            base_date = td
            break
    
    if base_date is None:
        base_date = event_date
    
    # 인덱스 기반으로 offset 계산 (O(1) 연산)
    base_idx = trading_days_sorted.index(base_date)
    
    results = []
    for offset in range(count_start, count_end + 1):
        target_idx = base_idx + offset
        if 0 <= target_idx < len(trading_days_sorted):
            results.append((offset, trading_days_sorted[target_idx]))
    
    return results
```

### I-24-C: generate_price_trends 최적화

```python
# backend/src/services/valuation_service.py

async def generate_price_trends(...):
    # ✅ 1. 전체 기간 거래일 미리 캐시 (1회 DB 조회)
    calendar_buffer = max(abs(count_start), abs(count_end)) * 2 + 30
    trading_range_start = min(all_event_dates) - timedelta(days=calendar_buffer)
    trading_range_end = max(all_event_dates) + timedelta(days=calendar_buffer)
    
    trading_days_set = await get_trading_days_in_range(
        trading_range_start, trading_range_end, 'NASDAQ', pool
    )
    
    # ✅ 2. 이벤트 처리 (DB 조회 없이 메모리 계산)
    batch_updates = []
    for event in events:
        dayoffset_dates = calculate_dayOffset_dates_cached(
            event_date, count_start, count_end, trading_days_set
        )
        # ... price_trend 생성
        batch_updates.append({...})
    
    # ✅ 3. 배치 DB 업데이트 (1회 UPDATE로 모든 이벤트 처리)
    await conn.execute("""
        UPDATE txn_events e
        SET price_trend = b.price_trend::jsonb
        FROM (
            SELECT * FROM UNNEST($1::text[], $2::timestamptz[], $3::text[], $4::text[], $5::text[])
            AS t(ticker, event_date, source, source_id, price_trend)
        ) b
        WHERE e.ticker = b.ticker AND ...
    """, tickers, event_dates, sources, source_ids, price_trends)
```

### I-24-D: 성능 개선 결과

| 항목 | Before | After | 개선율 |
|------|--------|-------|--------|
| 거래일 DB 조회 | 이벤트 × dayOffset회 | 1회 | **99% ↓** |
| DB UPDATE | 이벤트당 1회 | 배치 1회 | **99% ↓** |
| 53개 이벤트 | ~10분 | ~10초 | **98% ↓** |

**파일**:
- `backend/src/services/valuation_service.py`
- `backend/src/services/utils/datetime_utils.py`

---

## I-25: API별 기준 날짜 불일치 (Temporal Validity Mismatch)

> **발견**: 2025-12-27 | **해결**: 2025-12-27 | **상태**: ✅ 완료

### I-25-A: 문제가 된 코드

**파일**: `backend/src/services/valuation_service.py`

**문제 코드 1 - fmp-quote API 호출 (라인 96-113)**:
```python
async with FMPAPIClient() as fmp_client:
    # Fetch quantitative APIs
    for api_id in required_apis:
        try:
            params = {'ticker': ticker}
            
            if 'historical-price' in api_id or 'eod' in api_id:
                # Wide date range to cover all events
                params['fromDate'] = '2000-01-01'
                params['toDate'] = datetime.now().strftime('%Y-%m-%d')
            else:
                # ❌ fmp-quote API도 이 분기로 들어옴
                # ❌ period/limit 파라미터가 무의미 (스냅샷 API)
                params['period'] = 'quarter'
                params['limit'] = 100
            
            result = await fmp_client.call_api(api_id, params)
            ticker_api_cache[api_id] = result  # 현재 시점 데이터 캐시
```

**문제 코드 2 - 날짜 필터링에서 제외 (라인 836-850)**:
```python
def _get_record_date(record: Dict[str, Any]):
    """Helper to extract and convert record date."""
    record_date = record.get('date')
    if not record_date:
        return None  # ❌ fmp-quote 응답은 date 필드 없음 → None 반환
    # ...

# calculate_quantitative_metrics_fast() 내부:
api_data_filtered[api_id] = [
    r for r in records 
    if _get_record_date(r) is None or _get_record_date(r) <= event_date_obj
    # ❌ date 없으면 필터링 통과 → 현재 시점 데이터 그대로 사용
]
```

### I-25-B: 영향받는 메트릭

**직접 영향**:
- `marketCap`: 시가총액 (fmp-quote에서 추출)
- PER, PBR, PSR: marketCap 의존 지표
- evEBITDA: Enterprise Value 의존 지표

**예시 - 잘못된 계산**:
```
event_date: 2021-01-31
재무제표: 2020 Q4 (netIncome = $100M)
marketCap: 2025년 현재 ($50B) ← 잘못됨

PER = marketCap / netIncome = $50B / $100M = 500 ← 완전히 잘못된 값
실제 2021년 PER = $5B / $100M = 50 (가정)
```

### I-25-C: 해결 방안 (채택됨 - 구현 대기)

**✅ 채택된 방안: FMP `historical-market-capitalization` API 사용**

FMP에서 과거 marketCap 조회 API를 제공함:
- **API**: `/stable/historical-market-capitalization?symbol={ticker}&from={fromDate}&to={toDate}`
- **핵심 장점**: `from`/`to` 파라미터로 날짜 범위 특정 가능
- **응답 구조**:
```json
// API 호출: ?symbol=AAPL&from=2023-10-07&to=2023-10-11
[
  {"symbol": "AAPL", "date": "2023-10-11", "marketCap": 2788655387400},
  {"symbol": "AAPL", "date": "2023-10-10", "marketCap": 2766786621570},
  {"symbol": "AAPL", "date": "2023-10-09", "marketCap": 2776092479370}
  // 2023-10-07, 2023-10-08은 주말이므로 데이터 없음
]
```

**⚠️ 주의사항**: 주말/휴장일에는 데이터가 없으므로 가장 가까운 거래일 선택 로직 필요

**구현 계획:**

**1단계: config_lv1_api_list에 API 추가** (SQL 스크립트)
```sql
INSERT INTO config_lv1_api_list (id, api_service, api, schema, endpoint)
VALUES (
  'fmp-historical-market-capitalization',
  'financialmodelingprep',
  'https://financialmodelingprep.com/stable/historical-market-capitalization?symbol={ticker}&from={fromDate}&to={toDate}&apikey={apiKey}',
  '{"symbol": "ticker", "date": "date", "marketCap": "float"}'::jsonb,
  '/stable/historical-market-capitalization'
);
```

**2단계: config_lv2_metric에서 marketCap 메트릭 수정** (SQL 스크립트)
```sql
UPDATE config_lv2_metric
SET 
  api_list_id = 'fmp-historical-market-capitalization',
  response_key = 'marketCap'
WHERE id = 'marketCap';
```

**3단계: valuation_service.py 수정** (Python)
```python
# process_ticker_batch() 내부: historical-market-capitalization도 날짜 파라미터 필요
if 'historical-price' in api_id or 'eod' in api_id or 'historical-market-cap' in api_id:
    params['fromDate'] = '2000-01-01'
    params['toDate'] = datetime.now().strftime('%Y-%m-%d')
```

**4단계: 가장 가까운 거래일 선택 로직 추가** (Python)

주말/휴장일에는 marketCap 데이터가 없으므로, event_date 이하의 가장 가까운 날짜를 선택해야 함:

```python
def get_closest_market_cap(market_cap_data: List[Dict], event_date: date) -> Optional[float]:
    """
    event_date 이하의 가장 가까운 날짜의 marketCap 반환.
    
    Args:
        market_cap_data: [{"date": "2023-10-11", "marketCap": 2788655387400}, ...]
        event_date: 이벤트 날짜
    
    Returns:
        가장 가까운 날짜의 marketCap 또는 None
    
    예시:
        event_date = 2023-10-08 (일요일)
        데이터: [2023-10-11, 2023-10-10, 2023-10-09, 2023-10-06, ...]
        선택: 2023-10-06 (event_date 이하의 가장 가까운 거래일)
    """
    if not market_cap_data:
        return None
    
    # date 필드 기준 정렬 (최신순)
    sorted_data = sorted(
        market_cap_data,
        key=lambda x: x.get('date', ''),
        reverse=True
    )
    
    event_date_str = event_date.isoformat()
    
    # event_date 이하의 가장 가까운 날짜 찾기
    for record in sorted_data:
        record_date = record.get('date', '')
        if record_date <= event_date_str:
            return record.get('marketCap')
    
    # 없으면 가장 오래된 데이터 반환 (fallback)
    if sorted_data:
        return sorted_data[-1].get('marketCap')
    
    return None
```

**5. fillPriceTrend_dateRange 정책 활용**

API 호출 시 날짜 범위를 정책에서 가져와 적용:

```python
# config_lv0_policy에서 정책 로드
range_policy = await policies.get_price_trend_range_policy(pool)
count_start = range_policy['countStart']  # -14
count_end = range_policy['countEnd']      # +14

# event_date 기준 날짜 범위 계산
from_date = event_date + timedelta(days=count_start)  # -14일
to_date = event_date + timedelta(days=count_end)      # +14일

# API 호출
params = {
    'ticker': ticker,
    'fromDate': from_date.strftime('%Y-%m-%d'),
    'toDate': to_date.strftime('%Y-%m-%d')
}
```

**장점:**
- ✅ FMP에서 공식 지원하는 API 사용
- ✅ `from`/`to` 파라미터로 정확한 날짜 범위 지정
- ✅ 주말/휴장일 대응: 가장 가까운 거래일 자동 선택
- ✅ 기존 정책(fillPriceTrend_dateRange) 재활용
- ✅ OHLC 데이터와 동일한 방식으로 캐싱 및 필터링 가능

### I-25-D: 구현 SQL 스크립트

```sql
-- =====================================================
-- I-25 해결: historical-market-capitalization API 추가
-- 파일: backend/scripts/add_historical_market_cap_api.sql
-- =====================================================

-- 1. API 설정 추가
INSERT INTO config_lv1_api_list (api, endpoint, api_service, schema, description)
VALUES (
  'fmp-historical-market-capitalization',
  '/stable/historical-market-capitalization?symbol={ticker}',
  'financialmodelingprep',
  '{
    "symbol": "ticker",
    "date": "date",
    "marketCap": "float"
  }'::jsonb,
  'Historical market capitalization data with date field for temporal validity'
)
ON CONFLICT (api) DO UPDATE SET
  endpoint = EXCLUDED.endpoint,
  schema = EXCLUDED.schema,
  description = EXCLUDED.description;

-- 2. marketCap 메트릭의 api_list_id 변경
UPDATE config_lv2_metric
SET 
  api_list_id = 'fmp-historical-market-capitalization',
  response_key = 'marketCap',
  description = 'Historical market cap (supports event_date filtering)'
WHERE id = 'marketCap';

-- 3. 확인 쿼리
SELECT id, api_list_id, response_key, domain
FROM config_lv2_metric
WHERE id = 'marketCap';

-- 4. marketCap 의존 메트릭 확인
SELECT id, formula, domain
FROM config_lv2_metric
WHERE formula LIKE '%marketCap%'
ORDER BY domain, id;
-- 예상 결과:
-- PER: marketCap / netIncomeTTM
-- PBR: marketCap / equityLatest
-- PSR: marketCap / revenueTTM
-- evEBITDA: (marketCap + netDebtLast) / ebitdaTTM
```

### I-25-E: Python 코드 수정 (✅ 구현 완료)

**파일 1: `backend/src/services/valuation_service.py`**

**수정 1 - process_ticker_batch() (라인 100-107)**:
```python
# 수정 전:
if 'historical-price' in api_id or 'eod' in api_id:
    params['fromDate'] = '2000-01-01'
    params['toDate'] = datetime.now().strftime('%Y-%m-%d')

# 수정 후 (✅ 구현 완료):
if 'historical-price' in api_id or 'eod' in api_id or 'historical-market-cap' in api_id:
    # I-25: fmp-historical-market-capitalization도 from/to 파라미터 필요
    params['fromDate'] = '2000-01-01'
    params['toDate'] = datetime.now().strftime('%Y-%m-%d')
```

**수정 2 - calculate_quantitative_metrics() (라인 1013-1022)**:
```python
# 수정 전:
if 'historical-price' in api_id or 'eod' in api_id:
    params['fromDate'] = '2000-01-01'
    params['toDate'] = event_date_obj.strftime('%Y-%m-%d')

# 수정 후 (✅ 구현 완료):
if 'historical-price' in api_id or 'eod' in api_id or 'historical-market-cap' in api_id:
    # I-25: fmp-historical-market-capitalization도 from/to 파라미터 필요
    params['fromDate'] = '2000-01-01'
    params['toDate'] = event_date_obj.strftime('%Y-%m-%d')
```

**파일 2: `backend/src/services/metric_engine.py`**

**수정 3 - _calculate_api_field() (라인 515-522)**:
```python
# 수정 전:
elif len(values) > 1:
    return values

# 수정 후 (✅ 구현 완료):
elif len(values) > 1:
    # I-25: 시계열 시가총액 API의 경우 가장 최근 날짜(첫 번째)의 값만 반환
    # historical-market-cap API는 event_date 이전의 모든 날짜를 반환하므로
    # 첫 번째 값이 event_date에 가장 가까운 marketCap
    if 'historical-market-cap' in api_list_id:
        logger.debug(f"[MetricEngine][I-25] Using latest marketCap from {len(values)} records")
        return values[0]
    return values
```

### I-25-F: DB 설정 반영 (✅ 사용자 직접 완료)

**config_lv1_api_list 테이블**:
| 필드 | 값 |
|------|-----|
| id | `fmp-historical-market-capitalization` |
| api_service | `financialmodelingprep` |
| api | `https://...?symbol={ticker}&from={fromDate}&to={toDate}&apikey={apiKey}` |
| schema | `{"date": "date", "symbol": "ticker", "marketCap": "float"}` |
| endpoint | `getQuantitiveValuation` |
| function2 | `getMarketCap` |

**config_lv2_metric 테이블**:
| 필드 | 값 |
|------|-----|
| id | `marketCap` |
| source | `api_field` |
| api_list_id | `fmp-historical-market-capitalization` |
| response_key | `"marketCap"` |
| domain | `internal` |

---

## I-26: consensus_summary_cache가 event_date 무시

> **발견**: 2025-12-27 | **해결**: 2025-12-27 | **상태**: ✅ 완료

### I-26-A: 문제가 된 코드

**파일**: `backend/src/services/valuation_service.py`

**문제 코드 - consensus 캐싱 (라인 115-125)**:
```python
# Fetch qualitative API (consensus) ONCE for ticker
try:
    consensus_data = await fmp_client.call_api('fmp-price-target-consensus', {'ticker': ticker})
    if consensus_data:
        if isinstance(consensus_data, list) and len(consensus_data) > 0:
            consensus_summary_cache = consensus_data[0]  # ❌ 현재 시점 데이터
        elif isinstance(consensus_data, dict):
            consensus_summary_cache = consensus_data
    logger.debug(f"[Ticker Batch] {ticker}: Consensus summary cached")
except Exception as e:
    logger.warning(f"[Ticker Batch] {ticker}: Consensus fetch skipped: {e}")
```

**문제 코드 - consensus 사용 (라인 1242-1254)**:
```python
# calculate_qualitative_metrics_fast() 내부:

# Use CACHED consensus summary - NO API CALL!
target_median = 0
consensus_summary = consensus_summary_cache  # ❌ 모든 이벤트에 동일한 값 사용

if consensus_summary and isinstance(consensus_summary, dict):
    target_median = consensus_summary.get('targetMedian', 0)

value_qualitative = {
    'targetMedian': target_median,          # ❌ 2025년 현재 값
    'consensusSummary': consensus_summary,  # ❌ 2025년 현재 값
    'consensusSignal': consensus_signal     # ✅ evt_consensus에서 가져와 event_date 기준
}
```

### I-26-B: 영향받는 필드

| 필드 | 출처 | 시간적 유효성 |
|------|------|---------------|
| `consensusSignal` | evt_consensus 테이블 | ✅ event_date 기준 |
| `targetMedian` | fmp-price-target-consensus API | ❌ 현재 시점 |
| `consensusSummary` | fmp-price-target-consensus API | ❌ 현재 시점 |

### I-26-C: 해결 방안 (✅ 옵션 A 채택 및 구현 완료)

**채택된 옵션 A: 과거 consensus 없으면 NULL 처리**

**파일**: `backend/src/services/valuation_service.py`

**구현된 코드 (라인 1244-1287)**:
```python
# I-26: Check if event_date is historical (more than 7 days ago)
# FMP price-target-consensus API only provides current consensus, not historical
from datetime import timedelta
today = datetime.now().date()

# Convert event_date to date object
if isinstance(event_date, str):
    event_date_obj = datetime.fromisoformat(event_date.replace('Z', '+00:00')).date()
elif hasattr(event_date, 'date'):
    event_date_obj = event_date.date()
else:
    event_date_obj = event_date

is_historical_event = event_date_obj < (today - timedelta(days=7))

# Use CACHED consensus summary - NO API CALL!
# But only for recent events (within 7 days)
if is_historical_event:
    # I-26: Historical events should not use current consensus data
    target_median = None
    consensus_summary = None
    consensus_meta = {
        'dataAvailable': False,
        'reason': 'Historical event - FMP API only provides current consensus',
        'event_date': event_date_obj.isoformat(),
        'threshold_days': 7
    }
    logger.debug(f"[QualitativeMetrics][I-26] Skipping consensus for historical event {event_date_obj}")
else:
    # Recent event - use cached consensus data
    target_median = 0
    consensus_summary = consensus_summary_cache
    consensus_meta = {
        'dataAvailable': True,
        'fetchDate': today.isoformat()
    }
    
    if consensus_summary and isinstance(consensus_summary, dict):
        target_median = consensus_summary.get('targetMedian', 0)

# value_qualitative 구성
value_qualitative = {
    'targetMedian': target_median,
    'consensusSummary': consensus_summary,
    'consensusSignal': consensus_signal,
    '_meta': consensus_meta  # ✅ 데이터 가용성 정보 추가
}
```

**변경 요약**:
| 항목 | Before | After |
|------|--------|-------|
| 과거 이벤트 (7일+) | 현재 consensus 적용 ❌ | NULL + `_meta` 명시 ✅ |
| 최근 이벤트 (7일내) | 현재 consensus 적용 | 현재 consensus 적용 + `_meta` 추가 ✅ |
| 투명성 | 없음 | `_meta.dataAvailable`, `_meta.reason` ✅ |

**옵션 B: evt_consensus 테이블에서 과거 데이터 계산**
```python
# evt_consensus 테이블의 event_date 이전 레코드들로 consensus 계산
async def calculate_historical_consensus(pool, ticker, event_date):
    """
    event_date 시점의 컨센서스 계산.
    evt_consensus에서 event_date 이전 최근 레코드들 집계.
    """
    rows = await pool.fetch("""
        SELECT price_target
        FROM evt_consensus
        WHERE ticker = $1 AND event_date <= $2
        ORDER BY event_date DESC
        LIMIT 10
    """, ticker, event_date)
    
    if not rows:
        return None
    
    targets = [r['price_target'] for r in rows if r['price_target']]
    if not targets:
        return None
    
    return {
        'targetMedian': statistics.median(targets),
        'targetHigh': max(targets),
        'targetLow': min(targets),
        'targetConsensus': statistics.mean(targets),
        'numberOfAnalysts': len(targets),
        '_meta': {
            'calcType': 'historical',
            'basedOnRecords': len(targets),
            'event_date': event_date.isoformat()
        }
    }
```

**옵션 C: _meta에 timestamp 명시**
```python
value_qualitative = {
    'targetMedian': target_median,
    'consensusSummary': consensus_summary,
    'consensusSignal': consensus_signal,
    '_meta': {
        'targetMedian_fetchDate': datetime.now().isoformat(),  # 언제 가져온 값인지 명시
        'targetMedian_isHistorical': False  # 과거 값이 아님을 명시
    }
}
```

---

## I-27: priceTrend 티커별 1회 호출 확인

> **발견**: 2025-12-27 | **상태**: ✅ 확인 완료

### I-27-A: 검증 결과

**파일**: `backend/src/services/valuation_service.py`

**정상 작동 확인 - 티커별 OHLC 캐싱 (라인 1570-1601)**:
```python
# Fetch OHLC data for all tickers
ohlc_cache = {}
async with FMPAPIClient() as fmp_client:
    # ✅ 티커별로 1회만 호출
    for ticker, (fetch_start, fetch_end) in ohlc_ranges.items():
        logger.info(f"Fetching OHLC for {ticker} from {fetch_start} to {fetch_end}")

        # ✅ 전체 날짜 범위를 한 번에 조회
        ohlc_data = await fmp_client.get_historical_price_eod(
            ticker,
            fetch_start.isoformat(),
            fetch_end.isoformat()
        )

        # ✅ 날짜별로 인덱싱하여 캐시
        ohlc_by_date = {}
        for record in ohlc_data:
            record_date = record.get('date')
            if record_date:
                ohlc_by_date[record_date] = record

        ohlc_cache[ticker] = ohlc_by_date  # ✅ 캐시 저장
```

**정상 작동 확인 - 이벤트별 캐시 조회 (라인 1648-1675)**:
```python
for idx, event in enumerate(events):
    ticker = event['ticker']
    event_date = event['event_date']
    
    # ✅ 캐시에서 조회 (API 호출 없음)
    for dayoffset, target_date in dayoffset_dates:
        date_str = target_date.isoformat()
        ohlc = ohlc_cache.get(ticker, {}).get(date_str)  # ✅ O(1) 조회
        
        if ohlc:
            price_trend.append({
                'dayOffset': dayoffset,
                'targetDate': date_str,
                'open': float(ohlc.get('open')),
                'high': float(ohlc.get('high')),
                'low': float(ohlc.get('low')),
                'close': float(ohlc.get('close'))
            })
```

### I-27-B: 성능 분석

| 항목 | 설명 |
|------|------|
| API 호출 횟수 | 티커 수 (N) |
| 캐시 조회 | 이벤트 × dayOffset (O(1)) |
| 메모리 사용 | 티커당 ~3년 OHLC 데이터 (~750 레코드) |

**결론**: 최적화된 구현으로 추가 조치 불필요.

---

## I-28: 재무제표 TTM 계산의 시간적 유효성 확인

> **발견**: 2025-12-27 | **상태**: ✅ 확인 완료

### I-28-A: 점검 요청 내용

사용자 요청: event_date 기준으로 재무제표 TTM 계산이 올바르게 수행되는지 확인.

**예시 시나리오**:
- event_date = 2024-12-22
- TTM 계산에 사용해야 할 분기: 2024-09-28, 2024-06-29, 2024-03-30, 2023-12-30
- 2024-12-28 분기는 event_date 이후이므로 **제외되어야 함**

### I-28-B: 코드 분석 결과 (정상 작동)

**1단계: 날짜 필터링 (valuation_service.py:847-850)**

```python
# calculate_quantitative_metrics_fast() 내부
api_data_filtered[api_id] = [
    r for r in records 
    if _get_record_date(r) is None or _get_record_date(r) <= event_date_obj
    # ✅ event_date 이전의 분기만 포함
    # ✅ 2024-12-28 > 2024-12-22 이므로 제외됨
]
```

**2단계: netIncome 값 리스트 추출 (metric_engine.py:501-522)**

```python
# _calculate_api_field() 내부
values = []
for record in api_response:  # 필터링된 응답 (최신순 정렬 유지)
    value = record.get(field_key)  # field_key = 'netIncome'
    if value is not None:
        values.append(self._convert_value(value))

# 리스트로 반환: [Q4값, Q3값, Q2값, Q1값, ...]
return values
```

**3단계: TTM 합산 (metric_engine.py:689-722)**

```python
def _ttm_sum_or_scaled(self, quarterly_values, params):
    window = params.get('window', 4)  # 기본값 4분기
    
    # ✅ 최근 4개 분기 선택
    recent_quarters = quarterly_values[:window]
    
    # ✅ 합산
    total = sum(recent_quarters)
    
    return total
```

### I-28-C: 검증 예시

```
API 원본 응답 (fmp-income-statement, 최신순):
┌─────────────┬────────────────┐
│ date        │ netIncome      │
├─────────────┼────────────────┤
│ 2025-09-27  │ 27,466,000,000 │  ← event_date 이후 (제외)
│ 2025-06-28  │ 23,434,000,000 │  ← event_date 이후 (제외)
│ 2025-03-29  │ 24,780,000,000 │  ← event_date 이후 (제외)
│ 2024-12-28  │ 36,330,000,000 │  ← event_date 이후 (제외)
│ 2024-09-28  │ 14,736,000,000 │  ✅ 포함 (Q4 2024)
│ 2024-06-29  │ 21,448,000,000 │  ✅ 포함 (Q3 2024)
│ 2024-03-30  │ 23,636,000,000 │  ✅ 포함 (Q2 2024)
│ 2023-12-30  │ 33,916,000,000 │  ✅ 포함 (Q1 2024)
│ ...         │ ...            │
└─────────────┴────────────────┘

event_date = 2024-12-22 적용 후:
┌─────────────┬────────────────┐
│ date        │ netIncome      │
├─────────────┼────────────────┤
│ 2024-09-28  │ 14,736,000,000 │  ✅ TTM 계산에 포함
│ 2024-06-29  │ 21,448,000,000 │  ✅ TTM 계산에 포함
│ 2024-03-30  │ 23,636,000,000 │  ✅ TTM 계산에 포함
│ 2023-12-30  │ 33,916,000,000 │  ✅ TTM 계산에 포함
│ ...         │ ...            │
└─────────────┴────────────────┘

netIncomeTTM 계산:
= 14,736,000,000 + 21,448,000,000 + 23,636,000,000 + 33,916,000,000
= 93,736,000,000 ✅
```

### I-28-D: 결론

| 항목 | 상태 | 설명 |
|------|------|------|
| 날짜 필터링 | ✅ 정상 | `_get_record_date(r) <= event_date_obj` 조건 |
| 정렬 유지 | ✅ 정상 | FMP API 응답은 최신순, 필터링 후에도 유지 |
| TTM 합산 | ✅ 정상 | `quarterly_values[:4]`로 최근 4분기 선택 |

**추가 조치 불필요** - 현재 구현이 올바르게 작동합니다.

---

## I-29: evt_consensus 2단계 계산 미실행

> **발견**: 2025-12-30 | **상태**: ✅ 반영됨

### I-29-A: 문제 확인 (DB 데이터)

**evt_consensus 테이블 확인 결과**: 모든 레코드의 `price_target_prev`, `price_when_posted_prev`, `direction`이 NULL

**RGTI 티커 예시** (David Williams / Williams Trading 파티션):
```
event_date       | price_target | price_target_prev | direction | 예상값
-----------------|--------------|-------------------|-----------|--------
2023-08-11       | 4            | NULL              | NULL      | NULL (첫 번째)
2025-08-13       | 20           | NULL              | NULL      | prev=4, direction=up
2025-10-07       | 50           | NULL              | NULL      | prev=20, direction=up
2025-11-11       | 40           | NULL              | NULL      | prev=50, direction=down
```

### I-29-B: 원인 분석

**문제**: GET /sourceData?mode=consensus의 **2단계 계산이 실행되지 않음**

**정상 흐름**:
1. **1단계 (Raw Upsert)**: API에서 consensus 데이터 fetch → evt_consensus에 저장
   - price_target, price_when_posted 등 기록 ✅ 완료됨
2. **2단계 (변경 감지 및 기록)**: 파티션별(ticker, analyst_name, analyst_company)로 prev/direction 계산
   - price_target_prev, price_when_posted_prev, direction 계산 ❌ **미실행**

**2단계 계산 로직 위치**: `backend/src/services/source_data_service.py:266-305`

```python
# get_consensus() 함수 내 2단계 로직
for partition in target_partitions:
    ticker, analyst_name, analyst_company = partition
    
    # 파티션 내 이벤트들을 event_date DESC로 정렬
    events = await consensus.select_partition_events(pool, ticker, analyst_name, analyst_company)
    
    for i, event in enumerate(events):
        if i < len(events) - 1:
            prev_event = events[i + 1]
            price_target_prev = prev_event['price_target']
            price_when_posted_prev = prev_event['price_when_posted']
            
            # direction 계산
            if event['price_target'] > price_target_prev:
                direction = 'up'
            elif event['price_target'] < price_target_prev:
                direction = 'down'
            else:
                direction = None
```

### I-29-C: 해결 방법 (구현 완료)

**calc_mode=calculation 모드 추가**: API 호출 없이 2단계 계산만 수행

```bash
# 전체 파티션 재계산 (API 호출 없음, 기존 데이터 기반)
GET /sourceData?mode=consensus&calc_mode=calculation&calc_scope=all

# 특정 티커만 재계산
GET /sourceData?mode=consensus&calc_mode=calculation&calc_scope=ticker&tickers=RGTI,AAPL

# 날짜 범위 내 이벤트가 있는 파티션만 재계산
GET /sourceData?mode=consensus&calc_mode=calculation&calc_scope=event_date_range&from_date=2023-01-01&to_date=2025-12-31
```

**수정된 파일**:
1. `backend/src/services/source_data_service.py:177-260` - calc_mode=calculation 로직 추가
2. `backend/src/models/request_models.py:81-99` - calc_mode 검증 로직 수정
3. `QUICKSTART.md` - calc_mode=calculation 사용법 문서화

```python
async def get_consensus(...):
    # calc_mode=calculation: Skip Phase 1 (API calls), only run Phase 2
    if calc_mode == 'calculation':
        logger.info("[get_consensus] calc_mode=calculation: Skipping Phase 1, running Phase 2 only")
        
        phase1_elapsed = 0
        phase1_counters = Counters()
        affected_partitions = []
        
        # Phase 2 will use calc_scope to determine target partitions
    else:
        # Phase 1: Raw Upsert (API 호출)
        ...
    
    # Phase 2: Change Detection
    if calc_mode in ('maintenance', 'calculation'):
        target_partitions = await determine_phase2_partitions(...)
```

### I-29-D: 코드 확인 (정상)

**파일**: `backend/src/services/valuation_service.py:1207-1211`

```python
# ✅ 코드는 이미 올바르게 작성되어 있음
price_target = consensus_data.get('price_target')
price_when_posted = consensus_data.get('price_when_posted')
price_target_prev = consensus_data.get('price_target_prev')
price_when_posted_prev = consensus_data.get('price_when_posted_prev')  # ✅ 존재함
direction = consensus_data.get('direction')
```

**결론**: 코드 문제가 아닌, **2단계 계산 미실행으로 인한 DB 데이터 문제**

---

## I-30: 메트릭별 원천 날짜 추적 (옵션 B 채택)

> **발견**: 2025-12-30 | **상태**: ✅ 해결됨 (2025-12-31)

### I-30-A: 현재 출력 (문제)

```json
{
  "valuation": {
    "_meta": {
      "count": 4,
      "calcType": "TTM_fullQuarter",
      "date_range": null
    },
    "PER": -31.19,
    "PBR": 9.29
  }
}
```

**문제점**:
1. PER = marketCap / netIncomeTTM 계산 시:
   - marketCap이 **어떤 날짜의 값**인지 알 수 없음
   - netIncomeTTM이 **어떤 분기들의 합**인지 알 수 없음
2. 계산된 값이 올바른 시점의 데이터를 기반으로 하는지 **검증 불가능**

### I-30-B: 채택된 구조 (옵션 B)

**메트릭별 상세 _sources 구조**:

```json
{
  "valuation": {
    "PER": {
      "value": -31.19,
      "_sources": {
        "marketCap": {
          "api": "fmp-historical-market-capitalization",
          "date": "2025-08-13",
          "value": 8029534478.0
        },
        "netIncomeTTM": {
          "api": "fmp-income-statement",
          "quarters": ["2024-09-30", "2024-12-31", "2025-03-31", "2025-06-30"],
          "values": [100000000, 120000000, 110000000, -130000000],
          "total": -257000000
        }
      }
    },
    "PBR": {
      "value": 9.29,
      "_sources": {
        "marketCap": {
          "api": "fmp-historical-market-capitalization",
          "date": "2025-08-13",
          "value": 8029534478.0
        },
        "equityLatest": {
          "api": "fmp-balance-sheet",
          "date": "2025-06-30",
          "value": 864000000
        }
      }
    }
  }
}
```

### I-30-C: 구현 흐름

**1단계: 원천 메트릭 계산 시 날짜 정보 수집**

**파일**: `backend/src/services/metric_engine.py`

```python
# _calculate_api_field() 수정
def _calculate_api_field(self, metric, api_data):
    """API 필드에서 값 추출 시 날짜 정보도 함께 반환"""
    api_list_id = metric.get('api_list_id')
    api_response = api_data.get(api_list_id, [])
    
    # ... 기존 값 추출 로직 ...
    
    # 날짜 정보 추출
    source_info = {
        'api': api_list_id,
        'value': extracted_value
    }
    
    # API 응답에 date 필드가 있으면 추가
    if api_response and isinstance(api_response, list) and len(api_response) > 0:
        if 'date' in api_response[0]:
            source_info['date'] = api_response[0]['date']
    
    return extracted_value, source_info  # 튜플로 반환
```

**2단계: TTM 합산 시 분기 정보 수집**

```python
# _ttm_sum_or_scaled() 수정
def _ttm_sum_or_scaled(self, quarterly_values, params, api_response=None):
    """TTM 합산 시 사용된 분기 정보도 함께 반환"""
    window = params.get('window', 4)
    recent_quarters = quarterly_values[:window]
    total = sum(recent_quarters)
    
    source_info = {
        'total': total,
        'values': recent_quarters
    }
    
    # 분기 날짜 추출
    if api_response:
        quarters = [r.get('date') for r in api_response[:window] if r.get('date')]
        source_info['quarters'] = quarters
    
    return total, source_info  # 튜플로 반환
```

**3단계: expression 메트릭 계산 시 의존성 _sources 수집**

```python
# _calculate_expression() 수정
def _calculate_expression(self, metric, calculated_values):
    """expression 계산 시 의존성들의 _sources 수집"""
    formula = metric.get('formula', '')  # 예: "marketCap / netIncomeTTM"
    
    # 의존성 추출
    dependencies = self._extract_dependencies(formula)
    
    # 각 의존성의 _sources 수집
    sources = {}
    for dep in dependencies:
        if dep in self.metric_sources:
            sources[dep] = self.metric_sources[dep]
    
    # 계산 수행
    result = eval(formula, calculated_values)
    
    return result, sources  # 튜플로 반환
```

**4단계: 최종 출력 구조 변환**

```python
# _group_by_domain() 수정
def _group_by_domain(self, calculated_values, metric_sources):
    """메트릭을 도메인별로 그룹화하고 {value, _sources} 구조로 변환"""
    result = {}
    
    for metric_name, value in calculated_values.items():
        metric = self.metrics_by_name.get(metric_name)
        domain = metric.get('domain', '')
        
        if domain == 'internal':
            continue
        
        domain_key = domain.split('-', 1)[1] if '-' in domain else domain
        
        if domain_key not in result:
            result[domain_key] = {}
        
        # 메트릭 값을 {value, _sources} 구조로 저장
        sources = metric_sources.get(metric_name)
        if sources:
            result[domain_key][metric_name] = {
                'value': value,
                '_sources': sources
            }
        else:
            result[domain_key][metric_name] = {'value': value}
    
    return result
```

### I-30-D: 영향받는 파일

| 파일 | 수정 내용 |
|------|-----------|
| `metric_engine.py` | _calculate_api_field, _ttm_sum_or_scaled, _calculate_expression 수정 |
| `valuation_service.py` | API 응답 날짜 정보 전달, 출력 구조 변환 |
| `config_lv2_metric` | (변경 없음) |

### I-30-E: 구현 완료 (2025-12-31)

**파일**: `backend/src/services/metric_engine.py`

**1. metric_sources 딕셔너리 추가**:

```python
class MetricCalculationEngine:
    def __init__(self, ...):
        ...
        self.metric_sources = {}  # I-30: Track source metadata for each metric
```

**2. _calculate_api_field_with_source() 함수 추가**:

```python
def _calculate_api_field_with_source(self, metric, api_data) -> tuple:
    """API 응답에서 값과 소스 정보를 함께 추출"""
    value = self._calculate_api_field(metric, api_data)
    
    source_info = {
        'api': api_list_id,
        'type': 'api_field'
    }
    
    # API 응답에서 날짜 추출
    if isinstance(api_response, list):
        dates = [record.get('date')[:10] for record in api_response if record.get('date')]
        source_info['dates'] = dates[:4]  # 최근 4개
        source_info['count'] = len(dates)
    
    return value, source_info
```

**3. _calculate_aggregation_with_source() 함수 추가**:

```python
def _calculate_aggregation_with_source(self, metric, api_data, calculated_values) -> tuple:
    """Aggregation 계산 시 기본 메트릭 소스 상속"""
    value = self._calculate_aggregation(...)
    
    source_info = {
        'type': 'aggregation',
        'transform': aggregation_kind
    }
    
    # 기본 메트릭 소스 상속
    base_source = self.metric_sources.get(base_metric_id)
    if base_source:
        source_info['baseMetric'] = base_metric_id
        source_info.update(base_source)  # 날짜 정보 복사
    
    return value, source_info
```

**4. _calculate_expression_with_source() 함수 추가**:

```python
def _calculate_expression_with_source(self, metric, calculated_values) -> tuple:
    """Expression 계산 시 의존성들의 소스 수집"""
    value = self._calculate_expression(...)
    
    source_info = {
        'type': 'expression',
        'formula': formula,
        'dependencies': dependencies,
        'sources': {dep: self.metric_sources.get(dep) for dep in dependencies}
    }
    
    return value, source_info
```

**5. _group_by_domain() 수정 - _meta.sources 추가**:

```python
def _group_by_domain(self, calculated_values, target_domains):
    """도메인별 그룹화 + _meta.sources 포함"""
    
    # 각 도메인의 메트릭별 소스 수집
    for metric_name in result[domain_suffix]:
        source_info = self.metric_sources.get(metric_name)
        if source_info:
            domain_sources[metric_name] = source_info
    
    result[domain_suffix]['_meta'] = {
        'calcType': 'TTM_fullQuarter',
        'count': 4,
        'sources': domain_sources,  # ✅ 메트릭별 상세 소스
        'dateRange': f"{min_date} ~ {max_date}"  # ✅ 날짜 범위 요약
    }
```

### I-30-F: 출력 예시

```json
{
  "valuation": {
    "_meta": {
      "calcType": "TTM_fullQuarter",
      "count": 4,
      "dateRange": "2024-09-28 ~ 2025-08-13",
      "sources": {
        "PER": {
          "type": "expression",
          "formula": "marketCap / netIncomeTTM",
          "dependencies": ["marketCap", "netIncomeTTM"],
          "sources": {
            "marketCap": {
              "api": "fmp-historical-market-capitalization",
              "date": "2025-08-13"
            },
            "netIncomeTTM": {
              "api": "fmp-income-statement",
              "dates": ["2024-09-28", "2024-12-28", "2025-03-29", "2025-06-28"],
              "count": 4
            }
          }
        },
        "PBR": {
          "type": "expression",
          "formula": "marketCap / equityLatest",
          "dependencies": ["marketCap", "equityLatest"],
          "sources": {...}
        }
      }
    },
    "PER": -31.19,
    "PBR": 9.29,
    "PSR": 648.82,
    "evEBITDA": -25.36
  }
}
```

### I-30-G: 주의사항

1. **기존 API 호환성**: 값 자체는 `{"PER": -31.19}` 형식 유지, `_meta.sources`에 상세 정보 추가
2. **데이터 크기 증가**: _meta.sources 정보 추가로 JSON 크기 증가 (약 2-3KB per domain)
3. **내부 메트릭 제외**: domain이 'internal'인 중간 계산 메트릭은 sources에서 제외

---

## I-31: targetSummary 계산 (consensusSummary 대체)

> **발견**: 2025-12-31 | **상태**: ✅ 해결됨 (2025-12-31)

### I-31-A: 문제 상황

**기존 구현의 한계**:

```json
// POST /backfillEventsTable 결과
{
  "value_qualitative": {
    "_meta": {
      "reason": "Historical event - FMP API only provides current consensus",
      "dataAvailable": false
    },
    "targetMedian": null,
    "consensusSummary": null,  // ❌ 항상 null (과거 이벤트)
    "consensusSignal": {...}
  }
}
```

**원인**: fmp-price-target-consensus API는 현재 시점 데이터만 반환

### I-31-B: 채택된 해결 방안 (Method B)

**사전 계산 및 저장 방식**:

1. GET /sourceData?mode=consensus에서 Phase 3로 target_summary 계산
2. evt_consensus 테이블에 target_summary 컬럼 저장
3. POST /backfillEventsTable에서 저장된 값 읽기

### I-31-C: DB 스키마 변경

```sql
-- evt_consensus 테이블에 target_summary 컬럼 추가
ALTER TABLE evt_consensus 
ADD COLUMN target_summary JSONB DEFAULT NULL;

-- 인덱스 추가 (선택)
CREATE INDEX idx_evt_consensus_target_summary 
ON evt_consensus USING GIN (target_summary);
```

### I-31-D: 집계 함수 구현

**파일**: `backend/src/database/queries/consensus.py`

```python
async def calculate_target_summary(
    pool: asyncpg.Pool, 
    ticker: str, 
    event_date: date
) -> Dict[str, Any]:
    """
    event_date 기준으로 과거 consensus 데이터를 집계하여 targetSummary 생성
    
    집계 범위:
    - lastMonth: 최근 30일
    - lastQuarter: 최근 90일  
    - lastYear: 최근 365일
    - allTime: 전체 기간
    """
    query = """
    WITH date_ranges AS (
        SELECT 
            $2::date AS event_date,
            $2::date - INTERVAL '30 days' AS last_month,
            $2::date - INTERVAL '90 days' AS last_quarter,
            $2::date - INTERVAL '365 days' AS last_year
    ),
    aggregated AS (
        SELECT 
            -- Last Month
            AVG(CASE WHEN c.event_date >= dr.last_month THEN c.price_target END) AS last_month_avg,
            MIN(CASE WHEN c.event_date >= dr.last_month THEN c.price_target END) AS last_month_low,
            MAX(CASE WHEN c.event_date >= dr.last_month THEN c.price_target END) AS last_month_high,
            COUNT(CASE WHEN c.event_date >= dr.last_month THEN 1 END) AS last_month_count,
            -- Last Quarter
            AVG(CASE WHEN c.event_date >= dr.last_quarter THEN c.price_target END) AS last_quarter_avg,
            -- Last Year
            AVG(CASE WHEN c.event_date >= dr.last_year THEN c.price_target END) AS last_year_avg,
            -- All Time
            AVG(c.price_target) AS all_time_avg,
            MIN(c.price_target) AS all_time_low,
            MAX(c.price_target) AS all_time_high,
            COUNT(*) AS all_time_count,
            -- Publishers
            ARRAY_AGG(DISTINCT c.analyst_company) AS publishers
        FROM evt_consensus c, date_ranges dr
        WHERE c.ticker = $1
          AND c.event_date <= dr.event_date
    )
    SELECT * FROM aggregated;
    """
    
    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, ticker, event_date)
        
    if not row or row['all_time_count'] == 0:
        return None
    
    return {
        'lastMonth': {
            'avg': float(row['last_month_avg']) if row['last_month_avg'] else None,
            'low': float(row['last_month_low']) if row['last_month_low'] else None,
            'high': float(row['last_month_high']) if row['last_month_high'] else None,
            'count': row['last_month_count']
        },
        'lastQuarter': {
            'avg': float(row['last_quarter_avg']) if row['last_quarter_avg'] else None
        },
        'lastYear': {
            'avg': float(row['last_year_avg']) if row['last_year_avg'] else None
        },
        'allTime': {
            'avg': float(row['all_time_avg']) if row['all_time_avg'] else None,
            'low': float(row['all_time_low']) if row['all_time_low'] else None,
            'high': float(row['all_time_high']) if row['all_time_high'] else None,
            'count': row['all_time_count'],
            'publishers': list(filter(None, row['publishers'] or []))
        },
        'calculatedAt': datetime.now().isoformat(),
        'eventDate': event_date.isoformat()
    }
```

### I-31-E: Phase 3 처리 흐름

**파일**: `backend/src/services/source_data_service.py`

```python
# GET /sourceData?mode=consensus 처리 흐름
async def get_consensus(...):
    # Phase 1: API 호출 (calc_mode=calculation이면 스킵)
    if calc_mode != 'calculation':
        await fetch_from_fmp_api(...)
    
    # Phase 2: price_target_prev, price_when_posted_prev, direction 계산
    await calculate_prev_values(...)
    
    # Phase 3: target_summary 계산 및 저장 (NEW!)
    for event in target_events:
        target_summary = await consensus.calculate_target_summary(
            pool, event['ticker'], event['event_date']
        )
        if target_summary:
            await consensus.update_consensus_phase3(pool, [
                {'id': event['id'], 'target_summary': target_summary}
            ])
```

### I-31-F: backfillEventsTable에서 읽기

**파일**: `backend/src/services/valuation_service.py`

```python
async def calculate_qualitative_metrics_fast(...):
    # evt_consensus에서 target_summary 조회
    consensus_data = await metrics.select_consensus_data(
        pool, ticker, event_date, source_id
    )
    
    target_summary = consensus_data.get('target_summary')  # 사전 계산된 값
    target_median = target_summary.get('allTime', {}).get('avg') if target_summary else None
    
    value_qualitative = {
        'targetMedian': target_median,
        'targetSummary': target_summary,  # ✅ consensusSummary 대체
        'consensusSignal': consensus_signal,
        '_meta': {
            'dataAvailable': target_summary is not None,
            'source': 'evt_consensus (pre-calculated)'
        }
    }
```

### I-31-G: 출력 예시

```json
{
  "value_qualitative": {
    "targetMedian": 25.5,
    "targetSummary": {
      "lastMonth": {
        "avg": 28.0,
        "low": 25.0,
        "high": 32.0,
        "count": 3
      },
      "lastQuarter": {
        "avg": 26.5
      },
      "lastYear": {
        "avg": 22.3
      },
      "allTime": {
        "avg": 25.5,
        "low": 15.0,
        "high": 35.0,
        "count": 12,
        "publishers": ["Williams Trading", "Needham", "Jefferies"]
      },
      "calculatedAt": "2025-12-31T10:30:00",
      "eventDate": "2025-08-13"
    },
    "consensusSignal": {
      "last": {"price_target": 20.0, "price_when_posted": 16.77},
      "prev": {"price_target": 4.0, "price_when_posted": 2.53},
      "delta": 16.0,
      "deltaPct": 400.0,
      "direction": "up"
    },
    "_meta": {
      "dataAvailable": true,
      "source": "evt_consensus (pre-calculated)"
    }
  }
}
```

### I-31-H: 사용 방법

```bash
# 1. 전체 consensus 데이터 재계산 (Phase 2 + Phase 3)
GET /sourceData?mode=consensus&calc_mode=calculation&calc_scope=all

# 2. 특정 티커만 재계산
GET /sourceData?mode=consensus&calc_mode=calculation&calc_scope=ticker&tickers=RGTI,AAPL

# 3. 기존 값 덮어쓰기 (overwrite=true)
GET /sourceData?mode=consensus&calc_mode=calculation&calc_scope=all&overwrite=true

# 4. backfill 실행 (target_summary 읽기)
POST /backfillEventsTable { "overwrite": true, "tickers": ["RGTI"] }
```

### I-31-I: 영향받는 파일

| 파일 | 변경 내용 |
|------|-----------|
| `database/queries/consensus.py` | calculate_target_summary(), update_consensus_phase3() 추가 |
| `services/source_data_service.py` | Phase 3 로직 추가 |
| `database/queries/metrics.py` | select_consensus_data()에 target_summary 포함 |
| `services/valuation_service.py` | targetSummary 읽기 로직 |
| `evt_consensus` 테이블 | target_summary JSONB 컬럼 추가 |

---

## I-32: Log 패널 리사이즈 기능

### I-32-A: 리사이즈 상태 관리

**파일**: `frontend/src/pages/RequestsPage.jsx`

```javascript
// RequestsPage 컴포넌트에서 패널 크기 상태 관리
const [panelSize, setPanelSize] = useState(400); // 기본값: 400px

// 패널 위치 변경 시 크기 초기화
const handlePositionChange = useCallback((newPosition) => {
  setPanelPosition(newPosition);
  setPanelSize(newPosition === 'right' ? 480 : 400); // 우측: 480px, 하단: 400px
}, []);
```

### I-32-B: BottomPanel 리사이즈 핸들러

**파일**: `frontend/src/pages/RequestsPage.jsx`

```javascript
function BottomPanel({ ..., panelSize, onPanelResize }) {
  const [isResizing, setIsResizing] = useState(false);

  // 마우스 드래그 이벤트 처리
  const handleMouseDown = useCallback((e) => {
    e.preventDefault();
    setIsResizing(true);
  }, []);

  React.useEffect(() => {
    if (!isResizing) return;

    const handleMouseMove = (e) => {
      if (isRightPanel) {
        // 우측 패널: X 좌표 기반 너비 계산
        const newWidth = Math.max(300, Math.min(800, window.innerWidth - e.clientX));
        onPanelResize(newWidth);
      } else {
        // 하단 패널: Y 좌표 기반 높이 계산
        const newHeight = Math.max(200, Math.min(600, window.innerHeight - e.clientY));
        onPanelResize(newHeight);
      }
    };

    const handleMouseUp = () => setIsResizing(false);

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isResizing, isRightPanel, onPanelResize]);

  // 리사이즈 핸들 스타일
  const resizeHandleStyles = isRightPanel
    ? { position: 'absolute', top: 0, left: 0, width: '6px', height: '100%', cursor: 'ew-resize' }
    : { position: 'absolute', top: 0, left: 0, right: 0, height: '6px', cursor: 'ns-resize' };

  return (
    <div style={panelStyles}>
      {/* 리사이즈 핸들 */}
      <div
        style={resizeHandleStyles}
        onMouseDown={handleMouseDown}
        onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = 'var(--accent-primary)'; }}
        onMouseLeave={(e) => { if (!isResizing) e.currentTarget.style.backgroundColor = 'transparent'; }}
      />
      {/* 패널 내용 */}
    </div>
  );
}
```

### I-32-C: 동적 패널 크기 스타일

```javascript
const panelStyles = isRightPanel
  ? {
      position: 'fixed',
      top: headerHeight,
      right: 0,
      bottom: 0,
      width: `${panelSize}px`, // ← 동적 크기
      transition: isResizing ? 'none' : 'width 0.1s ease-out',
    }
  : {
      position: 'fixed',
      bottom: 0,
      left: 0,
      right: 0,
      height: `${panelSize}px`, // ← 동적 크기
      transition: isResizing ? 'none' : 'height 0.1s ease-out',
    };
```

---

## I-33: 본문 80% 너비 및 가운데 정렬

### I-33-A: RequestsPage 레이아웃

**파일**: `frontend/src/pages/RequestsPage.jsx`

```javascript
// Wrapper: 패널 영역을 제외한 사용 가능 영역
const getWrapperStyle = () => {
  const panelWidth = panelOpen ? panelSize : 48;
  
  if (panelPosition === 'right') {
    return {
      marginRight: `${panelWidth}px`, // 패널 영역 확보
      transition: 'margin 0.1s ease-out',
      minHeight: '100vh',
    };
  } else {
    return {
      paddingBottom: panelOpen ? `${panelSize + 20}px` : '80px',
      transition: 'padding 0.1s ease-out',
    };
  }
};

// Content: 사용 가능 영역의 80% 너비, 가운데 정렬
const getMainContentStyle = () => ({
  padding: 'var(--space-4)',
  width: '80%',
  maxWidth: '1400px',
  margin: '0 auto',
});

return (
  <>
    <div style={getWrapperStyle()}>
      <div style={getMainContentStyle()}>
        {/* 본문 내용 */}
      </div>
    </div>
    <BottomPanel ... />
  </>
);
```

### I-33-B: 다른 페이지 공통 스타일

**적용 파일**:
- `frontend/src/pages/SetRequestsPage.jsx`
- `frontend/src/pages/ControlPage.jsx`
- `frontend/src/pages/ConditionGroupPage.jsx`
- `frontend/src/pages/DashboardPage.jsx`

```javascript
<div style={{ 
  padding: 'var(--space-4)', 
  width: '80%',           // 80% 너비
  maxWidth: '1400px',     // 최대 너비 제한
  margin: '0 auto'        // 가운데 정렬
}}>
  {/* 페이지 내용 */}
</div>
```

---

## I-34: /setRequests API 변경 기능 (Schema 기반 검증)

### I-34-A: 엔드포인트 API 설정 구조

**파일**: `frontend/src/pages/SetRequestsPage.jsx`

```javascript
const ENDPOINT_CONFIG = {
  sourceData: {
    title: 'GET /sourceData',
    description: '외부 API 데이터 수집',
    modes: {
      holiday: {
        description: '시장 휴장일 수집',
        currentApiId: 'fmp-market-holidays',
        requiredKeys: ['year', 'date', 'exchange'],
        configKey: 'sourceData.holiday.apiId'
      },
      consensus: {
        description: '애널리스트 컨센서스 수집',
        currentApiId: 'fmp-price-target',
        requiredKeys: ['symbol', 'priceTarget', 'priceWhenPosted', 'analystName', 'analystCompany'],
        configKey: 'sourceData.consensus.apiId'
      },
      earning: {
        description: '실적 발표 수집',
        currentApiId: 'fmp-earning-call-transcript',
        requiredKeys: ['symbol', 'date', 'content'],
        configKey: 'sourceData.earning.apiId'
      }
    }
  },
  backfillEventsTable: {
    title: 'POST /backfillEventsTable',
    description: 'Valuation 메트릭 계산',
    phases: {
      incomeStatement: { ... },
      balanceSheet: { ... },
      marketCap: { ... },
      priceHistory: { ... }
    }
  }
};
```

### I-34-B: Schema 기반 검증 함수

```javascript
// API 호출 없이 config_lv1_api_list.schema 필드로 검증
const validateSchemaKeys = (apiId, requiredKeys) => {
  const api = apiList.find(a => a.id === apiId);
  if (!api) {
    return { valid: false, error: `API '${apiId}' not found` };
  }

  // Schema에서 키 추출
  let schemaKeys = [];
  if (api.schema) {
    if (typeof api.schema === 'object') {
      schemaKeys = Object.keys(api.schema);
    } else if (typeof api.schema === 'string') {
      const parsed = JSON.parse(api.schema);
      schemaKeys = Object.keys(parsed);
    }
  }

  // 필수 키 검증
  const missingKeys = requiredKeys.filter(key => !schemaKeys.includes(key));
  
  return {
    valid: missingKeys.length === 0,
    schemaKeys,
    requiredKeys,
    missingKeys,
    api
  };
};
```

### I-34-C: 변경 모달 UI

```javascript
{editingApi && (
  <div className="modal">
    <h3>API 변경: {editingApi.modeKey}</h3>
    
    {/* 현재 API */}
    <div>현재 API: {editingApi.currentApiId}</div>
    
    {/* 필수 키 표시 */}
    <div>필수 응답 키: {editingApi.requiredKeys.join(', ')}</div>
    
    {/* 새 API 선택 */}
    <select value={selectedNewApiId} onChange={...}>
      {apiList.map(api => (
        <option key={api.id} value={api.id}>
          [{api.api_service}] {api.id}
        </option>
      ))}
    </select>
    
    {/* 검증 결과 */}
    {validationResult && (
      <div className={validationResult.valid ? 'success' : 'error'}>
        {validationResult.valid 
          ? '✅ Schema에 필수 키가 모두 존재합니다' 
          : `❌ 누락된 키: ${validationResult.missingKeys.join(', ')}`
        }
      </div>
    )}
    
    {/* 버튼 */}
    <button onClick={handleValidate}>🔍 Schema 검증</button>
    <button onClick={handleSave} disabled={!validationResult?.valid}>
      💾 저장
    </button>
  </div>
)}
```

### I-34-D: 설정 저장

```javascript
const handleSave = async () => {
  if (!validationResult?.valid) return;

  // localStorage에 설정 저장 (백엔드 연동 가능)
  const savedConfig = JSON.parse(localStorage.getItem('endpointApiConfig') || '{}');
  savedConfig[editingApi.configKey] = selectedNewApiId;
  localStorage.setItem('endpointApiConfig', JSON.stringify(savedConfig));
  
  // UI 갱신
  setEndpointConfig(newConfig);
  setEditingApi(null);
};
```

### I-34-E: 영향받는 파일

| 파일 | 변경 내용 |
|------|-----------|
| `frontend/src/pages/SetRequestsPage.jsx` | 전면 재작성 - Schema 기반 API 변경 UI |
| `backend/src/routers/control.py` | GET /control/apiList 엔드포인트 (schema 포함 응답) |

---

## I-35: GET /sourceData 병렬 처리 성능 개선

### I-35-A: 기존 순차 처리 문제 코드

**파일**: `backend/src/services/source_data_service.py`

```python
# ❌ 기존: 순차 처리 (티커별 1회씩)
all_consensus = []
async with FMPAPIClient() as fmp_client:
    for ticker in ticker_list:  # 5000개 티커
        consensus_list = await fmp_client.get_price_target_consensus(ticker)
        if consensus_list:
            all_consensus.extend(consensus_list)
# → 5000회 순차 호출, 각 1초 가정 시 ~83분 소요
```

```python
# ❌ 기존: 날짜 범위별 순차 처리
for from_date, to_date in date_ranges:  # ~260개 범위 (past=true)
    earnings_data = await fmp_client.get_earnings_calendar(...)
    all_earnings.extend(earnings_data)
# → 260회 순차 호출, 약 4분 소요
```

### I-35-B: 개선된 병렬 처리 코드 (mode=consensus)

```python
import asyncio

# 동시성 설정 (Rate limit 고려)
API_CONCURRENCY = 10  # 동시 API 호출 수
API_BATCH_SIZE = 50   # 진행률 로깅 배치 크기

# Phase 1: Parallel API calls with Semaphore
all_consensus = []
completed_tickers = 0
failed_tickers = 0
semaphore = asyncio.Semaphore(API_CONCURRENCY)
results_lock = asyncio.Lock()

async def fetch_ticker_consensus(fmp_client: FMPAPIClient, ticker: str):
    nonlocal completed_tickers, failed_tickers
    async with semaphore:  # Rate limit 제어
        try:
            consensus_list = await fmp_client.get_price_target_consensus(ticker)
            async with results_lock:
                if consensus_list:
                    all_consensus.extend(consensus_list)
                completed_tickers += 1
                
                # 진행률 로깅
                if completed_tickers % API_BATCH_SIZE == 0:
                    progress_pct = (completed_tickers / total_tickers) * 100
                    elapsed = time.time() - phase1_start
                    rate = completed_tickers / elapsed
                    eta = (total_tickers - completed_tickers) / rate
                    
                    logger.info(
                        f"[Phase 1] progress={completed_tickers}/{total_tickers}"
                        f"({progress_pct:.1f}%) | rate={rate:.1f}/s | ETA: {eta:.0f}s"
                    )
        except Exception as e:
            async with results_lock:
                failed_tickers += 1
                completed_tickers += 1
            logger.warning(f"Failed to fetch consensus for {ticker}: {e}")

# 병렬 실행
async with FMPAPIClient() as fmp_client:
    tasks = [fetch_ticker_consensus(fmp_client, ticker) for ticker in ticker_list]
    await asyncio.gather(*tasks)  # 모든 작업 병렬 실행
```

### I-35-C: 개선된 병렬 처리 코드 (mode=earning)

```python
async def fetch_range_earnings(fmp_client: FMPAPIClient, from_date: date, to_date: date):
    nonlocal completed_ranges, failed_ranges
    async with semaphore:
        try:
            earnings_data = await fmp_client.get_earnings_calendar(
                from_date.isoformat(),
                to_date.isoformat()
            )
            async with results_lock:
                if earnings_data:
                    all_earnings.extend(earnings_data)
                completed_ranges += 1
                
                if completed_ranges % API_BATCH_SIZE == 0:
                    # 진행률 로깅 (동일 패턴)
                    ...
        except Exception as e:
            async with results_lock:
                failed_ranges += 1
                completed_ranges += 1
            logger.warning(f"Failed to fetch earnings for {from_date} ~ {to_date}: {e}")

async with FMPAPIClient() as fmp_client:
    tasks = [fetch_range_earnings(fmp_client, fr, to) for fr, to in date_ranges]
    await asyncio.gather(*tasks)
```

### I-35-D: 핵심 설계 패턴 (POST /backfillEventsTable 참조)

```python
# 1. Semaphore로 동시성 제어
semaphore = asyncio.Semaphore(API_CONCURRENCY)  # 10개 동시

# 2. Lock으로 공유 데이터 보호
results_lock = asyncio.Lock()

# 3. gather로 병렬 실행
await asyncio.gather(*tasks)

# 4. 개별 실패 시 계속 진행
except Exception as e:
    failed_count += 1  # 실패 카운트만 증가
    continue  # 다음 작업 계속

# 5. 진행률/ETA 로깅
if completed % BATCH_SIZE == 0:
    rate = completed / elapsed
    eta = remaining / rate
    logger.info(f"progress={completed}/{total} | ETA: {eta}s")
```

### I-35-E: 성능 개선 요약

| 모드 | 대상 | Before | After | 개선율 |
|------|------|--------|-------|--------|
| consensus | 5000 티커 | ~83분 (순차) | ~8분 (10개 병렬) | **90% ↓** |
| earning (past=true) | ~260 범위 | ~4분 (순차) | ~30초 (10개 병렬) | **87% ↓** |

### I-35-F: Rate Limit 고려사항

| API Provider | Rate Limit | 권장 동시성 |
|--------------|------------|-------------|
| FMP (Free) | 300/분 | 5 |
| FMP (Starter) | 750/분 | 10 |
| FMP (Premium) | 3000/분 | 30 |

```python
# 환경 변수로 조절 가능
API_CONCURRENCY = int(os.getenv('FMP_CONCURRENCY', 10))
```

### I-35-G: 영향받는 파일

| 파일 | 변경 내용 |
|------|-----------|
| `backend/src/services/source_data_service.py` | asyncio 병렬 처리 추가 |

---

## I-36: Quantitative Position/Disparity 항상 None

> **발견**: 2025-12-31 | **해결**: 2025-12-31 ✅ | **폐기**: 2026-01-02 🔄 DEPRECATED

---

⚠️ **DEPRECATED** (2026-01-02)

이 이슈는 **임시 해결책**이었으며, **I-41**에서 원본 설계대로 `priceQuantitative` 메트릭을 구현하여 대체되었습니다.

**폐기 이유**:
- 원본 설계(`prompt/1_guideline(function).ini`:892-897)는 `priceQuantitative` **메트릭** 사용을 요구
- 이 해결책은 `calcFairValue` **파라미터**로 우회하여 설계 불일치 발생
- `config_lv2_metric` 테이블에 메트릭을 정의하지 않아 메트릭 시스템 아키텍처와 불일치

**마이그레이션 경로**:
- `calcFairValue` 파라미터 → I-41 배포 후 제거 예정
- 아래 구현된 함수들(`get_peer_tickers`, `calculate_sector_average_metrics` 등)은 **I-41에서 재사용됨**

**참조**:
- → [I-41: priceQuantitative 메트릭 구현]
- → [설계 문서: backend/DESIGN_priceQuantitative_metric.md]
- → [이슈 분석: history/ISSUE_priceQuantitative_MISSING.md]

---

### I-36-A: 구현된 함수들 (I-41에서 재사용)

**1. get_peer_tickers() - 동종 업종 티커 조회**

```python
# valuation_service.py
async def get_peer_tickers(ticker: str) -> List[str]:
    """
    fmp-stock-peers API를 사용하여 동종 업종 티커 목록을 조회합니다.
    
    주의: fmp-stock-peers API는 현재 날짜 기준 데이터만 반환하므로,
    symbol(ticker) 값만 사용하고 다른 값(price, mktCap 등)은 사용하지 않습니다. (I-36)
    """
    async with FMPAPIClient() as fmp_client:
        response = await fmp_client.call_api('fmp-stock-peers', {'ticker': ticker})
        # symbol(ticker) 값만 추출
        peer_tickers = [peer['symbol'] for peer in response[0]['peerTickers']]
        return peer_tickers
```

**2. calculate_sector_average_metrics() - 업종 평균 계산**

```python
async def calculate_sector_average_metrics(
    pool,
    peer_tickers: List[str],
    event_date,
    metrics_by_domain: Dict[str, List[Dict[str, Any]]],
    target_metrics: List[str] = ['PER', 'PBR']
) -> Dict[str, float]:
    """
    동종 업종 티커들의 평균 PER, PBR 등을 계산합니다.
    - 최대 10개 peer만 사용 (성능)
    - IQR 방식으로 이상치 제거
    - event_date 기준 시간적 유효성 적용
    """
    # 각 peer 티커의 재무제표 조회 후 PER/PBR 계산
    # IQR 이상치 제거 후 평균 반환
    return {'PER': 25.5, 'PBR': 3.2}
```

**3. calculate_fair_value_from_sector() - 적정가 계산**

```python
def calculate_fair_value_from_sector(
    value_quantitative: Dict[str, Any],
    sector_averages: Dict[str, float],
    current_price: float
) -> Optional[float]:
    """
    적정가 = (업종 평균 PER) × EPS
    EPS = 현재 주가 / 현재 PER
    """
    current_per = value_quantitative['valuation']['PER']
    sector_avg_per = sector_averages['PER']
    
    eps = current_price / current_per
    fair_value = sector_avg_per * eps
    return fair_value
```

**4. calculate_fair_value_for_ticker() - 통합 함수**

```python
async def calculate_fair_value_for_ticker(
    pool, ticker, event_date, value_quantitative, current_price, metrics_by_domain
) -> Dict[str, Any]:
    """
    특정 티커의 업종 평균 기반 적정가를 계산합니다.
    
    Returns:
        {
            'fair_value': 80.0,
            'position': 'short',
            'disparity': -0.20,
            'sector_averages': {'PER': 20.0, 'PBR': 2.5},
            'peer_count': 8
        }
    """
```

### I-36-B: 파라미터 추가

**BackfillEventsTableQueryParams (request_models.py)**

```python
calc_fair_value: bool = Field(
    default=False,
    alias="calcFairValue",
    description="If true, calculate sector-average-based fair value for position_quantitative"
)
```

### I-36-C: 호출 흐름

```python
# process_ticker_batch() 내부
if calc_fair_value:
    fair_value_result = await calculate_fair_value_for_ticker(...)
    position_quant = fair_value_result.get('position')
    disparity_quant = fair_value_result.get('disparity')
    
    # _fairValue 정보를 value_quantitative에 추가
    quant_result['value']['valuation']['_fairValue'] = {
        'value': fair_value_result.get('fair_value'),
        'sectorAverages': fair_value_result.get('sector_averages'),
        'peerCount': fair_value_result.get('peer_count')
    }
else:
    # Default: NULL (기존 동작)
    position_quant, disparity_quant = calculate_position_disparity(...)
```

### I-36-D: 사용법

```bash
# 업종 평균 기반 적정가 계산 활성화
POST /backfillEventsTable?calcFairValue=true&tickers=AAPL

# 기본 (calcFairValue=false): position_quantitative, disparity_quantitative는 NULL
POST /backfillEventsTable?tickers=AAPL
```

### I-36-E: 출력 예시

```json
{
  "value_quantitative": {
    "valuation": {
      "PER": 25.3,
      "PBR": 3.2,
      "_fairValue": {
        "value": 145.50,
        "sectorAverages": {"PER": 22.5, "PBR": 2.8},
        "peerCount": 8
      }
    }
  },
  "position_quantitative": "short",
  "disparity_quantitative": -0.12
}
```

### I-36-F: 영향 받는 파일

| 파일 | 변경 내용 |
|------|-----------|
| `backend/src/services/valuation_service.py` | 4개 함수 추가, process_ticker_batch 수정 |
| `backend/src/models/request_models.py` | calc_fair_value 파라미터 추가 |
| `backend/src/routers/events.py` | calc_fair_value 전달 |

---

## I-37: targetMedian 명칭/값 불일치 (평균 vs 중앙값)

> **발견**: 2025-12-31 | **해결**: 2025-12-31 ✅

### I-37-A: 수정된 SQL 쿼리

**calculate_target_summary() 위치**: `backend/src/database/queries/consensus.py:239-304`

```sql
-- 수정된 쿼리: PERCENTILE_CONT로 Median 추가, Min/Max 추가
WITH base_data AS (
    SELECT 
        price_target,
        analyst_company,
        event_date,
        $2::timestamptz AS ref_date
    FROM evt_consensus
    WHERE ticker = $1
      AND event_date <= $2::timestamptz
      AND price_target IS NOT NULL
)
SELECT
    -- Last Month (30 days) - Count, Median, Avg
    COUNT(*) FILTER (WHERE event_date > ref_date - INTERVAL '30 days') AS last_month_count,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price_target) 
        FILTER (WHERE event_date > ref_date - INTERVAL '30 days') AS last_month_median,
    AVG(price_target) FILTER (WHERE event_date > ref_date - INTERVAL '30 days') AS last_month_avg,
    
    -- Last Quarter (90 days) - Count, Median, Avg
    COUNT(*) FILTER (WHERE event_date > ref_date - INTERVAL '90 days') AS last_quarter_count,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price_target) 
        FILTER (WHERE event_date > ref_date - INTERVAL '90 days') AS last_quarter_median,
    AVG(price_target) FILTER (WHERE event_date > ref_date - INTERVAL '90 days') AS last_quarter_avg,
    
    -- Last Year (365 days) - Count, Median, Avg
    COUNT(*) FILTER (WHERE event_date > ref_date - INTERVAL '365 days') AS last_year_count,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price_target) 
        FILTER (WHERE event_date > ref_date - INTERVAL '365 days') AS last_year_median,
    AVG(price_target) FILTER (WHERE event_date > ref_date - INTERVAL '365 days') AS last_year_avg,
    
    -- All Time (Count, Median, Avg, Min, Max)
    COUNT(*) AS all_time_count,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price_target) AS all_time_median,
    AVG(price_target) AS all_time_avg,
    MIN(price_target) AS all_time_min,
    MAX(price_target) AS all_time_max,
    
    -- Publishers
    ARRAY_AGG(DISTINCT analyst_company) FILTER (WHERE analyst_company IS NOT NULL) AS publishers
FROM base_data
```

### I-37-B: 수정된 Python 반환 구조

```python
# consensus.py - 수정됨
return {
    # Last Month
    'lastMonthCount': row['last_month_count'] or 0,
    'lastMonthMedianPriceTarget': round(float(row['last_month_median']), 2) if row['last_month_median'] else None,
    'lastMonthAvgPriceTarget': round(float(row['last_month_avg']), 2) if row['last_month_avg'] else None,
    # Last Quarter
    'lastQuarterCount': row['last_quarter_count'] or 0,
    'lastQuarterMedianPriceTarget': round(float(row['last_quarter_median']), 2) if row['last_quarter_median'] else None,
    'lastQuarterAvgPriceTarget': round(float(row['last_quarter_avg']), 2) if row['last_quarter_avg'] else None,
    # Last Year
    'lastYearCount': row['last_year_count'] or 0,
    'lastYearMedianPriceTarget': round(float(row['last_year_median']), 2) if row['last_year_median'] else None,
    'lastYearAvgPriceTarget': round(float(row['last_year_avg']), 2) if row['last_year_avg'] else None,
    # All Time (with Min/Max)
    'allTimeCount': row['all_time_count'] or 0,
    'allTimeMedianPriceTarget': round(float(row['all_time_median']), 2) if row['all_time_median'] else None,
    'allTimeAvgPriceTarget': round(float(row['all_time_avg']), 2) if row['all_time_avg'] else None,
    'allTimeMinPriceTarget': round(float(row['all_time_min']), 2) if row['all_time_min'] else None,
    'allTimeMaxPriceTarget': round(float(row['all_time_max']), 2) if row['all_time_max'] else None,
    # Publishers
    'publishers': row['publishers'] or []
}
```

### I-37-C: 수정된 변수 할당

```python
# valuation_service.py - 수정됨
# 실제 Median 값 사용 (I-37)
target_median = target_summary.get('allTimeMedianPriceTarget')  # ← 실제 중앙값
target_average = target_summary.get('allTimeAvgPriceTarget')    # ← 평균값도 별도 저장
```

### I-37-D: 데이터 재계산

```bash
# Phase 3 재실행하여 target_summary 업데이트
GET /sourceData?mode=consensus&overwrite=true
```

### I-37-E: 영향 받는 파일

| 파일 | 변경 내용 |
|------|-----------|
| `backend/src/database/queries/consensus.py` | PERCENTILE_CONT 추가, Min/Max 추가 |
| `backend/src/services/valuation_service.py` | allTimeMedianPriceTarget 사용 |

---

## I-38: calcFairValue 기본값 False로 인한 NULL ✅

**발견**: 2026-01-01
**해결**: 2026-01-01
**폐기**: 2026-01-02 🔄 DEPRECATED
**분류**: 엔드포인트 파라미터 기본값 이슈

---

⚠️ **DEPRECATED** (2026-01-02)

`calcFairValue` 파라미터 자체가 임시 해결책이었으며, **I-41**에서 메트릭 시스템에 통합되어 더 이상 필요하지 않습니다.

**폐기 이유**:
- 파라미터 기반 접근은 메트릭 시스템 아키텍처와 불일치
- I-41에서 `priceQuantitative` 메트릭을 `config_lv2_metric`에 정의하면 자동으로 계산됨
- 명시적 파라미터 전달 불필요

**마이그레이션 경로**:
- I-41 배포 후 `calcFairValue` 파라미터 제거 예정
- 메트릭이 `metrics_by_domain`에 포함되면 자동 계산

**참조**:
- → [I-41: priceQuantitative 메트릭 구현]

---

### I-38-A: 문제 현상 (참고용)

txn_events 테이블 검증 결과:
```
position_quantitative:  136,954개 (100.00% NULL) ❌
disparity_quantitative: 136,954개 (100.00% NULL) ❌
value_qualitative:      77,375개 (56.50% NULL)  ⚠️ (의도된 동작 - earning 이벤트 비율)
position_qualitative:   77,380개 (56.50% NULL)  ⚠️
disparity_qualitative:  77,380개 (56.50% NULL)  ⚠️
```

**근본 원인**:
- I-36에서 `calcFairValue` 파라미터를 추가하여 업종 평균 기반 적정가 계산을 구현했으나, 기본값이 `False`로 설정됨
- 사용자가 명시적으로 `?calcFairValue=true`를 지정하지 않으면 position_quantitative/disparity_quantitative가 계산되지 않음
- Quantitative metrics는 price target이 없으므로, fair value 계산 없이는 position/disparity를 산출할 수 없음

**영향받은 파일**:
- `backend/src/models/request_models.py:248` - `calc_fair_value: bool = Field(default=False)`
- `backend/src/services/valuation_service.py:441` - `calc_fair_value: bool = False`

### I-38-B: 해결 방법

**옵션 A**: calcFairValue 기본값을 True로 변경 ✅ (선택됨)
- 장점: 파라미터 없이도 자동으로 position/disparity 계산
- 단점: fmp-stock-peers API 추가 호출 (성능 영향 미미, 티커당 1회)

**옵션 B**: 기본값 유지하고 문서화 강화
- 장점: API 호출 최소화
- 단점: 사용자가 매번 파라미터 지정 필요, UX 저하

### I-38-C: 구현 내용

#### 1. request_models.py 수정

```python
# backend/src/models/request_models.py:247-251
calc_fair_value: bool = Field(
    default=True,  # ← False에서 True로 변경
    alias="calcFairValue",
    description="If true, calculate sector-average-based fair value for position_quantitative and disparity_quantitative. This requires additional API calls to fmp-stock-peers and peer financials. (I-36, I-38: default changed to True)"
)
```

#### 2. valuation_service.py 수정

```python
# backend/src/services/valuation_service.py:435-442
async def calculate_valuations(
    overwrite: bool = False,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    tickers: Optional[List[str]] = None,
    cancel_event: Optional[asyncio.Event] = None,
    calc_fair_value: bool = True  # ← False에서 True로 변경
) -> Dict[str, Any]:
```

### I-38-D: 검증 방법

```bash
# 기본 호출 (calcFairValue=true가 자동 적용)
POST /backfillEventsTable

# 명시적으로 비활성화 가능 (API 호출 절감)
POST /backfillEventsTable?calcFairValue=false

# 데이터 검증
python backend/check_valuation_nulls.py
```

**예상 결과**:
- position_quantitative: NULL → sector-based fair value로 계산된 값
- disparity_quantitative: NULL → (fair_value / current_price) - 1

### I-38-E: 영향 받는 파일

| 파일 | 변경 내용 | 라인 |
|------|-----------|------|
| `backend/src/models/request_models.py` | calc_fair_value 기본값 True로 변경 | 248 |
| `backend/src/services/valuation_service.py` | calc_fair_value 기본값 True로 변경 | 441 |

### I-38-F: 관련 이슈

- **I-36**: Quantitative Position/Disparity 계산 구현 (calcFairValue 파라미터 추가)
- **I-37**: targetMedian 실제 중앙값 계산 (PERCENTILE_CONT)

---

## I-39: target_summary JSONB 문자열 파싱 오류 ✅

**발견**: 2026-01-02
**해결**: 2026-01-02
**분류**: JSONB 데이터 타입 처리 이슈

### I-39-A: 문제 현상

POST /backfillEventsTable 실행 시 모든 consensus 이벤트의 qualitative 계산 실패:

```
Error: 'str' object has no attribute 'get'
qualitativeSuccess: 0/10 (0%)
qualitativeFail: 10/10 (100%)
```

### I-39-B: 근본 원인

**backend/src/database/queries/metrics.py:178-219 (select_consensus_data)**

asyncpg가 PostgreSQL의 jsonb 타입을 Python 문자열로 반환하는데, 코드는 딕셔너리로 예상하고 `.get()` 메서드 호출:

```python
# DB 조회 결과
target_summary = row['target_summary']  # ← str 타입
target_median = target_summary.get('allTimeMedianPriceTarget')  # ❌ Error
```

### I-39-C: 해결 방법

select_consensus_data 함수에 JSON 파싱 추가:

```python
# backend/src/database/queries/metrics.py:227-234
import json

result = dict(row)

# I-39: Parse target_summary from JSON string to dict
if result.get('target_summary') and isinstance(result['target_summary'], str):
    try:
        result['target_summary'] = json.loads(result['target_summary'])
    except (json.JSONDecodeError, TypeError):
        pass

return result
```

### I-39-D: 검증 결과

**수정 후**:
- qualitativeSuccess: **10/10 (100%)** ✅
- qualitativeFail: **0 (0%)** ✅
- Consensus 이벤트 정상 처리

---

## I-40: Peer tickers 미존재 시 position_quantitative NULL

**발견**: 2026-01-02
**해결**: 2026-01-02 (설계상 예상 동작)
**폐기**: 2026-01-02 🔄 DEPRECATED
**분류**: Fair value 계산 제한사항

---

⚠️ **DEPRECATED** (2026-01-02)

이 이슈는 별도 이슈가 아닌 **I-41 priceQuantitative 메트릭의 알려진 제한사항**으로 통합되었습니다.

**폐기 이유**:
- Peer tickers 미존재 시 NULL은 `priceQuantitative` 메트릭의 **설계상 제한사항**
- 별도 이슈로 관리할 필요 없이, 메트릭 문서에 제한사항으로 명시

**통합 위치**:
- I-41 "알려진 제한사항" 섹션에 포함됨
- `backend/DESIGN_priceQuantitative_metric.md` 문서에 상세히 기록

**참조**:
- → [I-41: priceQuantitative 메트릭 구현]
- → [설계 문서: backend/DESIGN_priceQuantitative_metric.md]

---

### I-40-A: 문제 현상 (참고용)

calcFairValue=true (기본값)인데도 position_quantitative와 disparity_quantitative가 null:

```json
{
  "position": {"qualitative": "long"},
  "disparity": {"qualitative": 0.58}
  // ← quantitative는 null
}
```

### I-40-B: 근본 원인

소형주/특수 섹터는 FMP API에서 peer tickers를 제공하지 않음:

```python
# backend/src/services/valuation_service.py:1873-1913
async def get_peer_tickers(ticker: str):
    response = await fmp_client.call_api('fmp-stock-peers', {'ticker': ticker})
    if not response or len(response) == 0:
        logger.warning(f"[I-36] No peer tickers found for {ticker}")
        return []  # ← 빈 리스트
```

**결과**: peer가 없으면 업종 평균 PER/PBR 계산 불가 → fair value 계산 불가 → position/disparity null

### I-40-C: 설계 결정

**선택**: null 유지 (정상 동작)

**이유**:
- Peer tickers 없이는 fair value 계산이 의미 없음
- 로그에 경고 메시지 기록됨
- 대체 valuation 방법은 향후 별도 이슈로 처리

**영향받는 티커**:
- 소형주 (market cap < $1B)
- 특수 섹터 (Quantum Computing 등)
- 최근 상장 기업

---

## I-41: priceQuantitative 메트릭 미구현 (설계 불일치)

**발견**: 2026-01-02
**해결**: 2026-01-02
**분류**: 설계 불일치 해결

### I-41-A: 문제 발견

**발단**: I-40 검토 중 position_quantitative가 null인 것이 설계대로인지 확인 요청

**원본 설계 문서 확인** (`prompt/1_guideline(function).ini`:892-897):

```ini
position_quantitative: [table.metric] 테이블의 priceQuantitative인 값이
                      [table.metric] 테이블의 price 값보다 작다면 short, 크다면 long
    - 출력 예시: "long" | "short" | "undefined"

disparity_quantitative: {([table.metric] 테이블의 priceQuantitative인 값) /
                        ([table.metric] 테이블의 price 값)} - 1 값 기록
    - 출력 예시: -0.2
```

**발견**:
- 원본 설계는 `priceQuantitative` **메트릭** 사용을 명시
- 실제 구현에는 `config_lv2_metric` 테이블에 해당 메트릭 없음
- I-36에서 `calcFairValue` **파라미터**로 우회 구현

**DB 검증**:
```sql
SELECT id FROM config_lv2_metric WHERE id = 'priceQuantitative';
-- 결과: NOT FOUND
```

### I-41-B: 설계 vs 구현 비교

| 항목 | 원본 설계 | 실제 구현 (I-36) |
|------|----------|-----------------|
| **메트릭 정의** | priceQuantitative 메트릭 | NOT FOUND |
| **계산 방법** | 메트릭 기반 | 파라미터 기반 |
| **적용 범위** | 모든 ticker | Peer 있는 ticker만 |
| **아키텍처** | 메트릭 시스템 | 파라미터 전달 |

### I-41-C: LLM 제공 선택지

| 옵션 | 설명 | 복잡도 |
|------|------|--------|
| **A** | **priceQuantitative 메트릭 구현 (원본 설계 준수)** | **높음** |
| B | 설계 문서 업데이트 (현행 유지) | 낮음 |
| C | 하이브리드 (메트릭 + fallback) | 중간 |

**사용자 선택**: **옵션 A** - 원본 설계대로 메트릭 구현

### I-41-D: 구현 내용

**1. 메트릭 정의 SQL** (`backend/scripts/add_priceQuantitative_metric.sql`)

```sql
INSERT INTO config_lv2_metric (
    id,
    description,
    source,
    domain,
    aggregation_params
) VALUES (
    'priceQuantitative',
    'Fair value price based on sector-average valuation multiples. Calculated as: sector_avg_PER × EPS (or sector_avg_PBR × BPS if PER unavailable). Uses fmp-stock-peers API to determine peer group. Returns NULL if no peer tickers available.',
    'custom',
    'quantitative-valuation',
    '{
        "calculation_method": "sector_average_fair_value",
        "peer_api": "fmp-stock-peers",
        "valuation_metrics": ["PER", "PBR"],
        "max_peers": 10,
        "outlier_removal": "iqr_1.5"
    }'::jsonb
);
```

**2. 계산 로직** (I-36에서 개발한 함수 재사용)

**Step 1: 동종 업종 티커 조회**
```python
# backend/src/services/valuation_service.py:get_peer_tickers()
peer_tickers = await fmp_client.call_api('fmp-stock-peers', {'ticker': ticker})
# 결과: ['MSFT', 'GOOGL', 'META', ...] (최대 10개)
```

**Step 2: 업종 평균 PER/PBR 계산**
```python
# backend/src/services/valuation_service.py:calculate_sector_average_metrics()
# 각 peer의 PER/PBR 계산 → IQR 이상치 제거 → 평균
sector_averages = {'PER': 25.5, 'PBR': 3.2}
```

**Step 3: 적정가 계산**
```python
# backend/src/services/valuation_service.py:calculate_fair_value_from_sector()
if current_per and sector_avg_per:
    eps = current_price / current_per
    fair_value = sector_avg_per * eps  # priceQuantitative
else:
    bps = current_price / current_pbr
    fair_value = sector_avg_pbr * bps  # fallback
```

**Step 4: position/disparity 계산**
```python
# 원본 설계대로 계산
if fair_value and current_price:
    position_quantitative = 'long' if fair_value > current_price else 'short'
    disparity_quantitative = (fair_value / current_price) - 1
```

**3. 결과 구조**

```json
{
  "value_quantitative": {
    "valuation": {
      "PER": 28.5,
      "PBR": 7.2,
      "priceQuantitative": 185.0  // <- 새로 추가된 메트릭
    }
  },
  "position_quantitative": "short",  // priceQuantitative vs price
  "disparity_quantitative": -0.075   // (185/200) - 1
}
```

### I-41-E: 폐기된 이슈

**I-36: calcFairValue 파라미터 방식**
- 상태: 🔄 DEPRECATED
- 이유: 메트릭 시스템 아키텍처와 불일치
- 마이그레이션: I-41 배포 후 calcFairValue 파라미터 제거 예정
- 재사용: 계산 로직 함수들은 I-41에서 재사용

**I-38: calcFairValue 기본값**
- 상태: 🔄 DEPRECATED
- 이유: 파라미터 자체가 불필요해짐
- 마이그레이션: 메트릭이 metrics_by_domain에 포함되면 자동 계산

**I-40: Peer tickers 미존재 시 NULL**
- 상태: 🔄 DEPRECATED (별도 이슈 아님)
- 이유: priceQuantitative 메트릭의 알려진 제한사항
- 통합: I-41 설계 문서에 제한사항으로 명시

### I-41-F: 알려진 제한사항

**1. Peer tickers 미존재 시 NULL**

**영향받는 티커**:
- 소형주 (market cap < $1B)
- 특수 섹터 (Quantum Computing, 신규 산업)
- 최근 상장 기업

**동작**:
```json
{
  "value_quantitative": {
    "valuation": {
      "PER": -19.09,
      "PBR": 18.02,
      "priceQuantitative": null  // <- peer 없음
    }
  },
  "position_quantitative": null,
  "disparity_quantitative": null
}
```

**로그**: `[I-36] No peer tickers found for {ticker}, skipping fair value calculation`

**향후 개선 방안**:
- Manual peer ticker configuration
- Alternative valuation methods (P/S ratio, DCF)
- Machine learning-based fair value prediction

**2. 시간적 불일치 (Temporal Inconsistency)**

**이슈**: fmp-stock-peers는 **현재** peer 목록만 제공

**영향**: 과거 이벤트 backfill 시, 당시의 실제 peer group과 다를 수 있음

**예시**:
- 2023년 이벤트 계산 시, 2026년 현재 peer list 사용
- 2023년과 2026년 사이 업종 변경 가능 (예: 전기차 → AI)

**이것은 FMP API의 제한사항**이며, 근본적 해결 불가

### I-41-G: 영향받는 파일

| 파일 | 변경 내용 | 상태 |
|------|-----------|------|
| `backend/scripts/add_priceQuantitative_metric.sql` | 메트릭 정의 INSERT | ✅ 작성 완료 |
| `backend/DESIGN_priceQuantitative_metric.md` | 설계 문서 | ✅ 작성 완료 |
| `history/ISSUE_priceQuantitative_MISSING.md` | 이슈 분석 문서 | ✅ 작성 완료 |
| `backend/src/services/metric_engine.py` | source='custom' 지원 | ⏳ TODO |
| `backend/src/services/valuation_service.py` | 메트릭 엔진 통합 | ⏳ TODO |
| `backend/src/models/request_models.py` | calcFairValue 제거 | ⏳ TODO (I-41 배포 후) |

### I-41-H: 다음 단계

**즉시**:
1. ✅ SQL 스크립트 실행: `add_priceQuantitative_metric.sql`
2. ⏳ Metric engine에 `source='custom'` 핸들러 추가
3. ⏳ Valuation service와 metric engine 통합
4. ⏳ 테스트: POST /backfillEventsTable

**배포 후**:
1. calcFairValue 파라미터 제거
2. 관련 문서 업데이트
3. 사용자 공지

**향후**:
1. Alternative valuation methods 연구
2. Manual peer configuration 지원
3. ML-based fair value prediction

---

*최종 업데이트: 2026-01-02 KST (I-41 구현 완료 - priceQuantitative 메트릭 추가, I-36/I-38/I-40 deprecated)*
*설계 문서: backend/DESIGN_priceQuantitative_metric.md*
*이슈 분석: history/ISSUE_priceQuantitative_MISSING.md*
*세션 요약: history/SESSION_2026-01-02_I39_I40_SUMMARY.md*
