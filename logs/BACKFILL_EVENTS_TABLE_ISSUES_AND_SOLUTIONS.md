# POST /backfillEventsTable 구현 문제 및 해결 방안

## 문제 1: 시간적 유효성 문제 (Temporal Validity Issue)

### 문제 상황
현재 `calculate_quantitative_metrics()` 함수는 `limit=4`로 고정하여 항상 최근 4개 분기만 가져옵니다. 이로 인해 과거 `event_date`를 가진 이벤트에 대해 잘못된 데이터를 사용하게 됩니다.

**예시 시나리오**:
- `ticker='RGTI'`, `event_date='2021-01-31'`인 이벤트 처리 시
- 현재 구현: `limit=4`로 호출 → 2025년 최신 4개 분기 데이터 반환
- 문제: 2021년 이벤트에 2025년 데이터를 사용하여 잘못된 계산 수행

**현재 코드 위치**: `backend/src/services/valuation_service.py:424-425`
```python
income_stmt = await fmp_client.get_income_statement(ticker, period='quarter', limit=4)
balance_sheet = await fmp_client.get_balance_sheet(ticker, period='quarter', limit=4)
```

### 해결 방안 명령

**LLM에게 전달할 명령**:

```
calculate_quantitative_metrics() 함수를 수정하라:

1. FMP API 호출 시 limit 파라미터를 충분히 큰 값(예: 100)으로 설정하여 과거 데이터를 충분히 가져온다.

2. event_date를 기준으로 유효한 분기 데이터를 필터링한다:
   - API 응답의 각 분기 데이터에 'date' 필드가 있다고 가정
   - event_date 이전의 분기 데이터만 사용 (event_date >= 분기 종료일)
   - TTM 계산에 필요한 4개 분기를 event_date 기준으로 선택
   - 선택된 분기들이 event_date 이전에 모두 존재하는지 검증

3. 유효한 데이터가 없는 경우:
   - status='failed' 반환
   - message='no_valid_data' 또는 'insufficient_historical_data' 설정
   - value=None 반환

4. _meta 정보에 실제 사용된 분기 범위를 기록:
   - date_range.start: 사용된 가장 오래된 분기 종료일
   - date_range.end: 사용된 가장 최신 분기 종료일
   - calcType: 'TTM_fullQuarter' (4개 분기 모두 있음) 또는 'TTM_partialQuarter' (일부만 있음)
   - count: 실제 사용된 분기 수

5. TTM 계산 로직:
   - 4개 분기가 모두 event_date 이전에 존재하면: Q0 + Q1 + Q2 + Q3
   - 일부 분기만 있으면: (사용 가능한 분기 합계) / (분기 수) × 4
   - 분기가 0개면: status='failed', message='no_valid_data'
```

### 구현 체크리스트

- [ ] `get_income_statement()`, `get_balance_sheet()`, `get_cash_flow()` 호출 시 `limit=100` (또는 충분히 큰 값) 사용
- [ ] API 응답 데이터를 `event_date` 기준으로 필터링하는 로직 추가
- [ ] 필터링된 분기 데이터가 TTM 계산에 충분한지 검증 (최소 1개 분기 이상)
- [ ] 유효하지 않은 경우 `status='failed'`, `message='no_valid_data'` 반환
- [ ] `_meta.date_range`에 실제 사용된 분기 범위 기록
- [ ] `_meta.calcType`에 계산 타입 기록 ('TTM_fullQuarter', 'TTM_partialQuarter', 또는 에러 시 None)
- [ ] `_meta.count`에 실제 사용된 분기 수 기록

---

## 문제 2: 동적 메트릭 계산 미구현 (Dynamic Metric Calculation Missing)

### 문제 상황
현재 `calculate_quantitative_metrics()` 함수는 하드코딩된 도메인만 처리합니다 (`if 'valuation' in metrics_by_domain:`). `config_lv2_metric` 테이블에 새로운 도메인이 추가되거나 변경되어도 반영되지 않습니다.

**현재 코드 위치**: `backend/src/services/valuation_service.py:443-460`
```python
if 'valuation' in metrics_by_domain:
    valuation_metrics = {}
    # ... 하드코딩된 계산
```

**지침 요구사항** (`prompt/1_guideline(function).ini:760`):
- `value_quantitative`: `config_lv2_metric` 테이블의 `domain` 컬럼이 `quantitative-`로 시작하는 모든 메트릭을 계산
- `-` 뒤의 도메인 키워드별로 그룹화하여 JSON 형식으로 기록
- 예: `quantitative-valuation` → `valuation` 키로 그룹화
- 예: `quantitative-profitability` → `profitability` 키로 그룹화

### 해결 방안 명령

**LLM에게 전달할 명령**:

```
calculate_quantitative_metrics() 함수를 완전히 재작성하라:

1. metrics_by_domain 딕셔너리를 순회하여 모든 quantitative-* 도메인을 동적으로 처리한다:
   - metrics_by_domain.keys()를 순회
   - 각 도메인에 대해 해당 도메인의 모든 메트릭 정의를 처리

2. 각 메트릭의 expression(공식)을 파싱하여 계산한다:
   - expression 필드에 정의된 공식을 해석
   - 필요한 재무 데이터(income_stmt, balance_sheet, cash_flow)에서 값 추출
   - 공식에 따라 계산 수행
   - 계산 실패 시 해당 메트릭은 None 또는 에러 메시지 기록

3. 도메인별로 그룹화하여 value_quantitative 구조 생성:
   - 도메인 suffix(예: 'valuation', 'profitability')를 키로 사용
   - 각 도메인 그룹에 계산된 메트릭들을 저장
   - 예: {'valuation': {'PER': 25.5, 'PBR': 3.2}, 'profitability': {'ROE': 0.15}}

4. _meta 정보 추가:
   - _meta.sector: config_lv3_targets 테이블에서 ticker로 조회한 sector 값
   - _meta.industry: config_lv3_targets 테이블에서 ticker로 조회한 industry 값
   - _meta.date_range: 실제 사용된 분기 범위 (문제 1 해결 방안 참조)
   - _meta.calcType: 계산 타입 ('TTM_fullQuarter', 'TTM_partialQuarter' 등)
   - _meta.count: 사용된 분기 수

5. 하드코딩 제거:
   - 'valuation' 도메인만 처리하는 if 문 제거
   - 모든 quantitative-* 도메인을 동적으로 처리하도록 변경
```

### 구현 체크리스트

- [ ] `metrics_by_domain`의 모든 키를 순회하는 루프 추가
- [ ] 각 도메인의 모든 메트릭 정의를 순회하는 루프 추가
- [ ] `expression` 필드를 파싱하여 계산하는 로직 구현 (공식 파싱 엔진 또는 간단한 파서)
- [ ] 계산 실패 시 에러 처리 (해당 메트릭만 None 또는 에러 메시지)
- [ ] 도메인 suffix를 키로 사용하여 그룹화
- [ ] `_meta.sector`, `_meta.industry`를 `config_lv3_targets` 테이블에서 조회하여 추가
- [ ] 하드코딩된 'valuation' 체크 제거
- [ ] 모든 quantitative-* 도메인이 동적으로 처리되는지 검증

---

## 추가 고려사항

### 공식 파싱 엔진
`config_lv2_metric.expression` 필드의 공식을 파싱하는 방법:
- 간단한 파서: 변수 치환 방식 (예: `market_cap / ttm_earnings` → 변수 값으로 치환 후 eval)
- 고급 파서: AST 파싱 또는 수식 파싱 라이브러리 사용
- 초기 구현: 간단한 변수 치환 방식으로 시작, 필요시 고급 파서로 확장

### 에러 메시지 표준화
- `no_valid_data`: event_date 기준으로 유효한 분기 데이터가 없음
- `insufficient_historical_data`: TTM 계산에 필요한 최소 분기 수(예: 1개) 미달
- `metric_calculation_failed`: 특정 메트릭 계산 실패 (메트릭별 상세 메시지 포함)
- `formula_parse_error`: expression 파싱 실패

### 테스트 시나리오
1. **과거 이벤트 테스트**: 2021년 event_date를 가진 이벤트로 TTM 계산이 올바른 분기 데이터를 사용하는지 확인
2. **최신 이벤트 테스트**: 2025년 event_date를 가진 이벤트로 최신 4개 분기를 사용하는지 확인
3. **동적 도메인 테스트**: config_lv2_metric에 새로운 도메인 추가 후 자동 반영되는지 확인
4. **에러 케이스 테스트**: 유효한 데이터가 없는 경우 적절한 에러 메시지 반환 확인

---

## 문제 3: Topological Sort 순서 오류 (해결됨 ✅)

### 문제 상황

메트릭 계산 엔진이 메트릭을 잘못된 순서로 처리하고 있었습니다. `api_field` 메트릭(예: `revenue`, `netIncome`)이 마지막에 계산되어, 이를 의존하는 모든 메트릭이 "not defined" 오류로 실패했습니다.

**증상**:
- `revenueQoQ`, `revenueYoY` 같은 집계 메트릭이 계산 실패
- 의존하는 메트릭들이 정의되지 않았다는 오류 발생
- `api_field` 메트릭이 의존 메트릭보다 나중에 계산됨

**현재 코드 위치**: `backend/src/services/metric_engine.py:121-192`

### 근본 원인

`metric_engine.py`의 topological sort 구현(121-163줄)에서 in-degree 계산이 반대로 되어 있었습니다. 의존성(dependencies)에 대해 in-degree를 증가시켜 의존 메트릭이 나중에 계산되도록 만들었는데, 실제로는 의존받는 메트릭(dependents)이 의존 메트릭을 기다려야 합니다.

### 해결 방안

**수정 내용** (`metric_engine.py:121-192`):

1. **in-degree 의미 수정**: "이 메트릭이 의존하는 메트릭의 개수"로 변경
2. **역방향 그래프 구축**: "각 메트릭에 의존하는 메트릭들" 추적
3. **시작 큐 설정**: in-degree가 0인 메트릭(의존성 없음 = `api_field` 메트릭)부터 시작
4. **처리 순서**: 각 메트릭 처리 시, 이를 의존하는 메트릭들의 in-degree 감소
5. **디버그 로깅 추가**: 계산 순서 확인을 위한 로깅 추가

**핵심 변경사항**:
```python
# 수정 전: 의존성에 대해 in-degree 증가 (잘못된 로직)
for dependency in dependencies:
    in_degree[dependency] += 1  # ❌ 잘못됨

# 수정 후: 메트릭 자체의 in-degree를 의존성 개수로 설정
in_degree[metric_name] = len(dependencies)  # ✅ 올바름
# 역방향 그래프로 의존받는 메트릭 추적
reverse_graph[dependency].append(metric_name)
```

### 결과

**✅ 성공적으로 수정됨**:

1. **Topological sort가 올바르게 작동**:
   - 처음 10개 메트릭이 모두 `api_field` 메트릭 (의존성 없음): `additionalPaidInCapital`, `cashAndCashEquivalents`, `marketCap`, `netIncome`, `revenue` 등
   - 마지막 10개 메트릭이 파생 메트릭 (표현식): `PSR`, `ROE`, `PBR`, `evEBITDA`

2. **API 필드 메트릭이 먼저 계산됨**:
   - ✅ `revenue = [1548000000.0, 1483000000.0...]`
   - ✅ `netIncome = [288000000.0, 222000000.0...]`
   - ✅ `marketCap = 39270477209.0`

3. **이를 사용하는 집계 메트릭이 정상 작동**:
   - ✅ `revenueQoQ = 0.043830074` (성공적으로 계산됨!)
   - ✅ `revenueYoY = 0.140751658` (성공적으로 계산됨!)

4. **계산 순서**:
   - ✅ 22개의 `api_field` 메트릭이 먼저 계산됨
   - ✅ 집계 메트릭(TTM, QoQ, YoY)이 두 번째로 계산됨
   - ✅ 표현식 메트릭(비율, 공식)이 마지막에 계산됨

### 남아있는 이슈

일부 TTM 집계 계산이 여전히 실패하고 있습니다:
- `Failed to calculate ebitdaTTM: 'str' object has no attribute 'get'`
- 이는 topological sort와는 별개의 버그로, 집계 계산 로직의 문제입니다.

### 구현 체크리스트

- [x] in-degree 계산 로직 수정
- [x] 역방향 그래프 구축 로직 추가
- [x] 의존성이 없는 메트릭부터 시작하도록 큐 초기화
- [x] 메트릭 처리 시 의존받는 메트릭의 in-degree 감소 로직 추가
- [x] 디버그 로깅 추가
- [x] `api_field` 메트릭이 먼저 계산되는지 검증
- [x] 집계 메트릭이 정상 작동하는지 검증

---

## 문제 4: 메트릭 계산 실패 원인 분석 및 해결 방안

### 개요

**목표**: 하드코딩 없이 `config_lv2_metric` 테이블 설정만 수정하여 모든 메트릭이 계산되도록 함

**원칙**:
1. 복잡한 dict 형태의 `response_key`를 생략하지 않고, 세분화된 항목들로 나누어 각각을 개별 메트릭으로 구현
2. `1_guideline(function).ini`의 "b. 가치 기록:" 항목 출력 예시를 모두 만족하도록 구현
3. `consensusSignal`은 `evt_consensus` 테이블의 2단계 계산 결과를 직접 사용 (원천 API 직접 참조 금지)

### 문제 상황

POST /backfillEventsTable 호출 시 일부 메트릭이 `None`을 반환하거나 계산에 실패합니다.

**실패 항목 분류**:
1. **api_field 실패**: `consensus`, `priceAfter`, `priceEodOHLC`
2. **aggregation 실패**: `apicYoY`, `consensusWithPrev`, `revenueQoQ`, `revenueYoY`, `sharesYoY`
3. **expression 실패**: `price`, `PER`, `runwayYears`, `grossMarginTTM`, `operatingMarginTTM`, `rndIntensityTTM`, `cashToRevenueTTM`, `PSR`, `debtToEquityAvg`, `othernclToEquityAvg`, `ROE`, `netdebtToEquityAvg`, `evEBITDA`

### 근본 원인 분석

#### 1. 복잡한 response_key (dict 형태) 미지원

**문제**: `consensus` 메트릭이 dict 형태의 `response_key`를 사용하는데, 현재 코드에서 이를 지원하지 않습니다.

**현재 코드 위치**: `backend/src/services/metric_engine.py:370-373`
```python
# Handle dict response_key (complex schema mapping)
if isinstance(field_key, dict):
    logger.warning(f"[MetricEngine] Complex response_key not yet supported for {metric.get('name')}")
    return None
```

**영향받는 메트릭**:
- `consensus` (fmp-price-target) - response_key가 복잡한 dict 형태

**해결 방안**:
- dict 형태의 `response_key`를 파싱하여 여러 필드를 추출하는 로직 구현
- 또는 `response_path`를 사용하여 JSONPath 방식으로 값 추출

#### 2. leadPairFromList aggregation_kind 미구현

**문제**: `consensusWithPrev` 메트릭이 사용하는 `leadPairFromList` aggregation이 구현되지 않았습니다.

**현재 코드 위치**: `backend/src/services/metric_engine.py:438-451`
```python
# Route to appropriate aggregation function
if aggregation_kind == 'ttmFromQuarterSumOrScaled':
    return self._ttm_sum_or_scaled(base_values, aggregation_params)
elif aggregation_kind == 'lastFromQuarter':
    return self._last_from_quarter(base_values, aggregation_params)
# ... leadPairFromList가 없음
```

**영향받는 메트릭**:
- `consensusWithPrev` (consensus의 leadPairFromList)

**해결 방안**:
- `leadPairFromList` aggregation 함수 구현
- 파티션별로 정렬 후 lead 값을 붙이는 로직 추가

#### 3. YoY 계산을 위한 데이터 부족

**문제**: `_yoy_from_quarter` 함수는 최소 5개 분기가 필요한데, 필터링 후 데이터가 부족할 수 있습니다.

**현재 코드 위치**: `backend/src/services/metric_engine.py:547-567`
```python
def _yoy_from_quarter(self, quarterly_values: List[float], params: Dict[str, Any]) -> Optional[float]:
    if len(quarterly_values) < 5:  # Need 5 quarters (current + 4 previous)
        return None
```

**영향받는 메트릭**:
- `apicYoY` (additionalPaidInCapital의 yoyFromQuarter)
- `revenueYoY` (revenue의 yoyFromQuarter)
- `sharesYoY` (weightedAverageShsOut의 yoyFromQuarter)

**해결 방안**:
- 데이터가 부족한 경우에도 가능한 범위에서 계산하도록 로직 개선
- 또는 `min_points` 파라미터를 활용하여 최소 요구사항 조정

#### 4. QoQ 계산 실패

**문제**: `revenueQoQ`가 실패하는데, 이는 `revenue`가 리스트가 아닌 스칼라 값으로 반환되었을 가능성이 있습니다.

**현재 코드 위치**: `backend/src/services/metric_engine.py:525-545`
```python
def _qoq_from_quarter(self, quarterly_values: List[float], params: Dict[str, Any]) -> Optional[float]:
    if len(quarterly_values) < 2:
        return None
```

**영향받는 메트릭**:
- `revenueQoQ` (revenue의 qoqFromQuarter)

**가능한 원인**:
- `revenue`가 단일 값으로 반환되어 리스트가 아닐 수 있음
- `_calculate_aggregation`에서 리스트로 변환하지만 (436줄), 이미 스칼라인 경우 문제 발생 가능

#### 5. TTM 메트릭 실패로 인한 expression 연쇄 실패

**문제**: TTM 메트릭들(`revenueTTM`, `netIncomeTTM`, `ebitdaTTM` 등)이 `None`이면 이를 사용하는 expression 메트릭들도 실패합니다.

**영향받는 메트릭**:
- `PER` (marketCap / netIncomeTTM) - netIncomeTTM이 None
- `PSR` (marketCap / revenueTTM) - revenueTTM이 None
- `evEBITDA` (enterpriseValue / ebitdaTTM) - ebitdaTTM이 None
- `grossMarginTTM` (grossProfitTTM / revenueTTM) - grossProfitTTM 또는 revenueTTM이 None
- `operatingMarginTTM` (operatingIncomeTTM / revenueTTM) - operatingIncomeTTM 또는 revenueTTM이 None
- `rndIntensityTTM` (rndTTM / revenueTTM) - rndTTM 또는 revenueTTM이 None
- `cashToRevenueTTM` (cashAndShortTermInvestmentsLast / revenueTTM) - revenueTTM이 None

**가능한 원인**:
- TTM 계산 시 데이터가 부족하거나
- TTM 계산 로직에서 오류 발생 (예: 'str' object has no attribute 'get')

#### 6. API 데이터 미호출 또는 필터링 후 데이터 부족

**문제**: 일부 API가 호출되지 않았거나, 필터링 후 데이터가 없을 수 있습니다.

**영향받는 메트릭**:
- `priceAfter` (fmp-aftermarket-trade) - API 데이터 없음
- `priceEodOHLC` (fmp-historical-price-eod-full) - API 데이터 없음

**가능한 원인**:
- `get_required_apis()`가 해당 API를 포함하지 않음
- API 호출 실패
- 필터링 후 데이터가 없음

#### 7. avgFromQuarter 메트릭 실패로 인한 expression 연쇄 실패

**문제**: `avgFromQuarter` aggregation 메트릭들이 실패하면 이를 사용하는 expression 메트릭들도 실패합니다.

**영향받는 메트릭**:
- `debtToEquityAvg` (avgTotalDebt / avgTotalEquity) - avgTotalDebt 또는 avgTotalEquity가 None
- `othernclToEquityAvg` (avgOtherNCL / avgTotalEquity) - avgOtherNCL 또는 avgTotalEquity가 None
- `ROE` (netIncomeTTM / avgTotalEquity) - avgTotalEquity가 None
- `netdebtToEquityAvg` (avgNetDebt / avgTotalEquity) - avgNetDebt 또는 avgTotalEquity가 None

**가능한 원인**:
- base 메트릭이 리스트가 아닌 스칼라 값으로 반환됨
- avgFromQuarter 계산 로직 오류

### 해결 방안: config_lv2_metric 테이블 수정 (하드코딩 없이)

**목표**: 코드 수정 없이 `config_lv2_metric` 테이블의 설정만 수정하여 모든 메트릭이 계산되도록 함

#### 1. api_field 실패 항목 해결

##### 1.1 `consensus` 메트릭 수정 - 세분화된 항목으로 분리

**현재 문제 분석**: 

`consensus` 메트릭이 "복잡한 dict 형태"라고 한 이유는 `response_key`에 여러 필드를 매핑하려고 했기 때문입니다:
```sql
response_key = '{"ticker": "symbol", "newsURL": "newsURL", "newsTitle": "newsTitle", 
                 "analystName": "analystName", "priceTarget": "priceTarget", ...}'
```

하지만 실제로는 **복잡하지 않습니다**. 각 필드는 단순한 문자열 매핑일 뿐이며, 현재 코드(`metric_engine.py:370-373`)가 dict 형태의 `response_key`를 지원하지 않아서 문제가 발생한 것입니다.

**해결 방안**: dict 형태를 생략하지 않고, **세분화된 항목들로 나누어 각각을 개별 메트릭으로 구현**

**지침 요구사항 확인** (`1_guideline(function).ini:851-890`):
- `value_qualitative`에는 다음이 모두 포함되어야 함:
  - `targetMedian`: 단일 값
  - `consensusSummary`: `{targetLow, targetHigh, targetMedian, targetConsensus}`
  - `consensusSignal`: `{source, source_id, event_date, direction, last, prev, delta, deltaPct, meta}`

**세분화된 메트릭 추가**:

```sql
-- 1. consensusPriceTarget: 목표가 (단일 값)
INSERT INTO config_lv2_metric (
    id, description, source, api_list_id, base_metric_id,
    aggregation_kind, aggregation_params, expression, domain, response_key
) VALUES (
    'consensusPriceTarget',
    '애널리스트 목표가',
    'api_field',
    'fmp-price-target',
    NULL,
    NULL,
    NULL,
    NULL,
    'internal',
    '"priceTarget"'
) ON CONFLICT (id) DO UPDATE SET
    response_key = '"priceTarget"',
    api_list_id = 'fmp-price-target';

-- 2. consensusAnalystName: 애널리스트 이름
INSERT INTO config_lv2_metric (
    id, description, source, api_list_id, base_metric_id,
    aggregation_kind, aggregation_params, expression, domain, response_key
) VALUES (
    'consensusAnalystName',
    '애널리스트 이름',
    'api_field',
    'fmp-price-target',
    NULL,
    NULL,
    NULL,
    NULL,
    'internal',
    '"analystName"'
) ON CONFLICT (id) DO UPDATE SET
    response_key = '"analystName"',
    api_list_id = 'fmp-price-target';

-- 3. consensusAnalystCompany: 애널리스트 회사
INSERT INTO config_lv2_metric (
    id, description, source, api_list_id, base_metric_id,
    aggregation_kind, aggregation_params, expression, domain, response_key
) VALUES (
    'consensusAnalystCompany',
    '애널리스트 회사',
    'api_field',
    'fmp-price-target',
    NULL,
    NULL,
    NULL,
    NULL,
    'internal',
    '"analystCompany"'
) ON CONFLICT (id) DO UPDATE SET
    response_key = '"analystCompany"',
    api_list_id = 'fmp-price-target';

-- 4. consensusPriceWhenPosted: 게시 시점 주가
INSERT INTO config_lv2_metric (
    id, description, source, api_list_id, base_metric_id,
    aggregation_kind, aggregation_params, expression, domain, response_key
) VALUES (
    'consensusPriceWhenPosted',
    '게시 시점 주가',
    'api_field',
    'fmp-price-target',
    NULL,
    NULL,
    NULL,
    NULL,
    'internal',
    '"priceWhenPosted"'
) ON CONFLICT (id) DO UPDATE SET
    response_key = '"priceWhenPosted"',
    api_list_id = 'fmp-price-target';

-- 5. consensusNewsURL: 뉴스 URL
INSERT INTO config_lv2_metric (
    id, description, source, api_list_id, base_metric_id,
    aggregation_kind, aggregation_params, expression, domain, response_key
) VALUES (
    'consensusNewsURL',
    '뉴스 URL',
    'api_field',
    'fmp-price-target',
    NULL,
    NULL,
    NULL,
    NULL,
    'internal',
    '"newsURL"'
) ON CONFLICT (id) DO UPDATE SET
    response_key = '"newsURL"',
    api_list_id = 'fmp-price-target';

-- 6. consensusNewsTitle: 뉴스 제목
INSERT INTO config_lv2_metric (
    id, description, source, api_list_id, base_metric_id,
    aggregation_kind, aggregation_params, expression, domain, response_key
) VALUES (
    'consensusNewsTitle',
    '뉴스 제목',
    'api_field',
    'fmp-price-target',
    NULL,
    NULL,
    NULL,
    NULL,
    'internal',
    '"newsTitle"'
) ON CONFLICT (id) DO UPDATE SET
    response_key = '"newsTitle"',
    api_list_id = 'fmp-price-target';

-- 7. consensusNewsPublisher: 뉴스 발행자
INSERT INTO config_lv2_metric (
    id, description, source, api_list_id, base_metric_id,
    aggregation_kind, aggregation_params, expression, domain, response_key
) VALUES (
    'consensusNewsPublisher',
    '뉴스 발행자',
    'api_field',
    'fmp-price-target',
    NULL,
    NULL,
    NULL,
    NULL,
    'internal',
    '"newsPublisher"'
) ON CONFLICT (id) DO UPDATE SET
    response_key = '"newsPublisher"',
    api_list_id = 'fmp-price-target';

-- 8. consensusPublishedDate: 게시일
INSERT INTO config_lv2_metric (
    id, description, source, api_list_id, base_metric_id,
    aggregation_kind, aggregation_params, expression, domain, response_key
) VALUES (
    'consensusPublishedDate',
    '게시일',
    'api_field',
    'fmp-price-target',
    NULL,
    NULL,
    NULL,
    NULL,
    'internal',
    '"publishedDate"'
) ON CONFLICT (id) DO UPDATE SET
    response_key = '"publishedDate"',
    api_list_id = 'fmp-price-target';

-- 기존 consensus 메트릭은 리스트 전체를 반환하도록 수정 (또는 제거)
-- consensusSignal 생성 시에는 evt_consensus 테이블을 직접 사용하므로,
-- api_field로 consensus를 가져올 필요는 없을 수 있음
-- 하지만 다른 용도로 사용할 수 있으므로 유지하되, 리스트 전체를 반환하도록 수정
UPDATE config_lv2_metric
SET response_key = NULL,  -- NULL이면 리스트 전체 반환
    description = '애널리스트 목표가 리스트 (전체)'
WHERE id = 'consensus';
```

**참고**: `consensusSignal`은 `evt_consensus` 테이블의 2단계 계산 결과를 직접 사용하므로, 위의 개별 메트릭들은 `consensusSignal` 생성에는 필요하지 않을 수 있습니다. 하지만 `value_qualitative`의 다른 부분(예: `consensusSummary`)에서 사용할 수 있으므로 추가합니다.

**value_qualitative 전체 구조 구현** (`1_guideline(function).ini:851-890`):

지침에 따르면 `value_qualitative`에는 다음이 **모두** 포함되어야 합니다:

1. **targetMedian**: 단일 값 (0 또는 실제 값)
2. **consensusSummary**: `{targetLow, targetHigh, targetMedian, targetConsensus}`
3. **consensusSignal**: `{source, source_id, event_date, direction, last, prev, delta, deltaPct, meta}`

**추가 필요한 메트릭**:

```sql
-- 1. targetMedian: 중간 목표가
INSERT INTO config_lv2_metric (
    id, description, source, api_list_id, base_metric_id,
    aggregation_kind, aggregation_params, expression, domain, response_key
) VALUES (
    'targetMedian',
    '중간 목표가',
    'api_field',
    'fmp-price-target-consensus',  -- consensus summary API
    NULL,
    NULL,
    NULL,
    NULL,
    'qualatative-targetMedian',
    '"targetMedian"'
) ON CONFLICT (id) DO UPDATE SET
    response_key = '"targetMedian"',
    api_list_id = 'fmp-price-target-consensus',
    domain = 'qualatative-targetMedian';

-- 2. consensusSummary: 목표가 요약 (전체 객체)
-- 이는 여러 필드를 포함하므로, 각 필드를 개별 메트릭으로 추가하거나
-- expression으로 조합해야 함
INSERT INTO config_lv2_metric (
    id, description, source, api_list_id, base_metric_id,
    aggregation_kind, aggregation_params, expression, domain, response_key
) VALUES (
    'consensusSummaryTargetLow',
    '목표가 최저값',
    'api_field',
    'fmp-price-target-consensus',
    NULL,
    NULL,
    NULL,
    NULL,
    'internal',
    '"targetLow"'
) ON CONFLICT (id) DO UPDATE SET
    response_key = '"targetLow"',
    api_list_id = 'fmp-price-target-consensus';

INSERT INTO config_lv2_metric (
    id, description, source, api_list_id, base_metric_id,
    aggregation_kind, aggregation_params, expression, domain, response_key
) VALUES (
    'consensusSummaryTargetHigh',
    '목표가 최고값',
    'api_field',
    'fmp-price-target-consensus',
    NULL,
    NULL,
    NULL,
    NULL,
    'internal',
    '"targetHigh"'
) ON CONFLICT (id) DO UPDATE SET
    response_key = '"targetHigh"',
    api_list_id = 'fmp-price-target-consensus';

INSERT INTO config_lv2_metric (
    id, description, source, api_list_id, base_metric_id,
    aggregation_kind, aggregation_params, expression, domain, response_key
) VALUES (
    'consensusSummaryTargetMedian',
    '목표가 중간값',
    'api_field',
    'fmp-price-target-consensus',
    NULL,
    NULL,
    NULL,
    NULL,
    'internal',
    '"targetMedian"'
) ON CONFLICT (id) DO UPDATE SET
    response_key = '"targetMedian"',
    api_list_id = 'fmp-price-target-consensus';

INSERT INTO config_lv2_metric (
    id, description, source, api_list_id, base_metric_id,
    aggregation_kind, aggregation_params, expression, domain, response_key
) VALUES (
    'consensusSummaryTargetConsensus',
    '목표가 컨센서스',
    'api_field',
    'fmp-price-target-consensus',
    NULL,
    NULL,
    NULL,
    NULL,
    'internal',
    '"targetConsensus"'
) ON CONFLICT (id) DO UPDATE SET
    response_key = '"targetConsensus"',
    api_list_id = 'fmp-price-target-consensus';

-- 3. consensusSummary를 expression으로 조합
INSERT INTO config_lv2_metric (
    id, description, source, api_list_id, base_metric_id,
    aggregation_kind, aggregation_params, expression, domain
) VALUES (
    'consensusSummary',
    '목표가 요약 (전체)',
    'expression',
    NULL,
    NULL,
    NULL,
    NULL,
    'buildConsensusSummary(consensusSummaryTargetLow, consensusSummaryTargetHigh, consensusSummaryTargetMedian, consensusSummaryTargetConsensus)',
    'qualatative-consensusSummary'
) ON CONFLICT (id) DO UPDATE SET
    source = 'expression',
    expression = 'buildConsensusSummary(consensusSummaryTargetLow, consensusSummaryTargetHigh, consensusSummaryTargetMedian, consensusSummaryTargetConsensus)',
    domain = 'qualatative-consensusSummary';
```

**참고**: `buildConsensusSummary`와 `buildConsensusSignal`은 특수 함수로, 현재 코드에서는 하드코딩되어 있지만, 향후 `MetricCalculationEngine`이 이를 지원하도록 확장되어야 합니다. 또는 expression 파서가 이러한 특수 함수를 인식하도록 구현해야 합니다.

##### 1.2 `priceAfter` 메트릭 확인 및 수정

**현재 설정 확인 필요**:
```sql
SELECT id, api_list_id, response_key, response_path
FROM config_lv2_metric
WHERE id = 'priceAfter';
```

**가능한 문제**:
- `api_list_id`가 `fmp-aftermarket-trade`로 설정되어 있지만 API가 호출되지 않음
- `response_key`가 잘못 설정됨

**해결 방안**:
1. `api_list_id` 확인: `fmp-aftermarket-trade`가 `config_lv1_api_list`에 존재하는지 확인
2. `response_key` 확인: API 응답의 실제 필드명과 일치하는지 확인
3. 필요시 `response_key` 수정:
```sql
UPDATE config_lv2_metric
SET response_key = '"priceAfter"'  -- 실제 API 응답 필드명으로 수정
WHERE id = 'priceAfter';
```

##### 1.3 `priceEodOHLC` 메트릭 확인 및 수정

**현재 설정 확인 필요**:
```sql
SELECT id, api_list_id, response_key, response_path
FROM config_lv2_metric
WHERE id = 'priceEodOHLC';
```

**가능한 문제**:
- `api_list_id`가 `fmp-historical-price-eod-full`로 설정되어 있지만 API가 호출되지 않음
- `response_key`가 복잡한 dict 형태일 수 있음

**해결 방안**:
1. `api_list_id` 확인 및 수정 필요 시:
```sql
UPDATE config_lv2_metric
SET api_list_id = 'fmp-historical-price-eod-full'
WHERE id = 'priceEodOHLC';
```

2. `response_key`를 단순 필드로 변경:
```sql
-- 현재 response_key가 dict 형태라면, 단일 필드로 변경
-- 예: close 가격만 추출하거나, 리스트 전체를 반환하도록
UPDATE config_lv2_metric
SET response_key = '"close"'  -- 또는 null로 설정하여 리스트 전체 반환
WHERE id = 'priceEodOHLC';
```

#### 2. aggregation 실패 항목 해결

##### 2.1 `apicYoY`, `revenueYoY`, `sharesYoY` 실패

**문제**: YoY 계산은 최소 5개 분기가 필요한데 데이터가 부족할 수 있음

**현재 설정 확인**:
```sql
SELECT id, base_metric_id, aggregation_kind, aggregation_params
FROM config_lv2_metric
WHERE id IN ('apicYoY', 'revenueYoY', 'sharesYoY');
```

**해결 방안**: `aggregation_params`에 `min_points` 파라미터 추가하여 데이터 부족 시에도 처리 가능하도록 (현재 코드는 5개 고정)

**참고**: 현재 코드는 하드코딩되어 있어 테이블 수정만으로는 해결 불가. 하지만 base_metric_id가 올바른지 확인 필요:
```sql
-- base_metric_id가 올바른지 확인
SELECT 
    m.id,
    m.base_metric_id,
    base.source as base_source,
    base.api_list_id as base_api
FROM config_lv2_metric m
LEFT JOIN config_lv2_metric base ON base.id = m.base_metric_id
WHERE m.id IN ('apicYoY', 'revenueYoY', 'sharesYoY');
```

##### 2.2 `revenueQoQ` 실패

**문제**: `revenue`가 스칼라 값으로 반환되어 QoQ 계산 실패 가능

**현재 설정 확인**:
```sql
SELECT id, base_metric_id, aggregation_kind
FROM config_lv2_metric
WHERE id = 'revenueQoQ';
```

**해결 방안**: `revenue` 메트릭이 리스트를 반환하는지 확인
```sql
-- revenue 메트릭이 리스트를 반환하도록 확인
SELECT id, api_list_id, response_key
FROM config_lv2_metric
WHERE id = 'revenue';
```

**참고**: `revenue`는 `fmp-income-statement`에서 가져오므로 리스트여야 함. API 응답 구조 확인 필요.

##### 2.3 `consensusWithPrev` 실패 - consensusSignal 구현 방식 설명

**문제 분석**: `consensusWithPrev`가 `leadPairFromList` aggregation을 사용하려고 했지만, 이는 **불필요하게 복잡한 접근**입니다.

**consensusSignal의 실제 목표** (`1_guideline(function).ini:801-803`):
- 컨센서스(Price Target) 이벤트의 "변화 신호"를 `value_qualitative`에 정규화하여 저장
- **원천 API(raw)의 publishedDate/date 키를 직접 참조하지 않음**
- **표준화된 event_date 및 evt_consensus 2단계 계산 결과(prev/direction)를 사용**

**왜 복잡해지는가?**:

1. **잘못된 접근**: `consensus` api_field에서 리스트를 가져와서 `leadPairFromList`로 prev 값을 계산하려고 함
   - 문제: 이는 원천 API를 직접 참조하는 방식으로, 지침에서 금지함
   - 문제: `evt_consensus` 테이블의 2단계 계산 결과를 무시함

2. **올바른 접근**: `evt_consensus` 테이블에서 이미 계산된 `prev/direction` 값을 직접 사용
   - `evt_consensus` 테이블에는 이미 다음이 계산되어 있음:
     - `price_target_prev`: 직전 목표가
     - `price_when_posted_prev`: 직전 게시 시점 주가
     - `direction`: 변화 방향 ("up" | "down" | null)
   - 따라서 `consensusSignal`은 단순히 이 값들을 읽어서 구조화만 하면 됨

**해결 방안**: `consensusWithPrev` aggregation은 **제거하고**, `consensusSignal`을 expression으로 구현하거나, 더 나은 방법으로는 `evt_consensus` 테이블을 직접 조회하는 방식 사용

**현재 구현 확인** (`backend/src/services/valuation_service.py:575-677`):
- 이미 `calculate_qualitative_metrics()` 함수에서 `evt_consensus` 테이블을 직접 조회하여 `consensusSignal`을 생성하고 있음
- 하지만 **중요한 문제 발견**: `source_id`를 사용하지 않아서 같은 날짜에 여러 analyst가 있으면 잘못된 행을 선택할 수 있음

**목표 달성 여부 점검**:

사용자가 요구한 목표:
1. txn_events의 `source_id`로 evt_consensus의 정확한 행(`id = source_id`)을 찾기
2. 그 행의 `ticker`, `analyst_name`, `analyst_company`를 기준으로 같은 partition의 과거 값 찾기
3. 같은 애널리스트의 변화만 비교

**현재 구현의 문제점**:
- ❌ `calculate_qualitative_metrics()`가 `source_id` 파라미터를 받지 않음
- ❌ `select_consensus_data()`가 `ticker`와 `event_date`만으로 조회하여 `LIMIT 1`로 하나만 가져옴
- ❌ 같은 `ticker`와 `event_date`에 여러 analyst가 있으면 잘못된 행을 선택할 수 있음

**수정 필요**:
1. `select_consensus_data()`에 `source_id` 파라미터 추가
2. `evt_consensus.id = source_id`로 정확한 행 조회
3. `calculate_qualitative_metrics()`에 `source_id` 파라미터 추가 및 전달

자세한 점검 결과는 `CONSENSUS_SIGNAL_GOAL_VERIFICATION.md` 참조.

**테이블 수정**:
```sql
-- consensusWithPrev는 불필요하므로 제거하거나 사용하지 않음
-- consensusSignal은 evt_consensus 테이블을 직접 사용하므로
-- config_lv2_metric에 consensusSignal을 expression으로 추가하되,
-- 실제로는 calculate_qualitative_metrics()에서 직접 처리하므로
-- 테이블에 정의할 필요가 없을 수 있음

-- 하지만 지침에 따라 config_lv2_metric에 정의해야 한다면:
INSERT INTO config_lv2_metric (
    id, description, source, api_list_id, base_metric_id,
    aggregation_kind, aggregation_params, expression, domain
) VALUES (
    'consensusSignal',
    '컨센서스 변화 신호 (evt_consensus 2단계 결과 사용)',
    'expression',  -- 또는 'api_field'로 evt_consensus를 조회
    NULL,
    NULL,
    NULL,
    NULL,
    'buildConsensusSignal(evt_consensus)',  -- 특수 함수 호출
    'qualatative-consensusSignal'
) ON CONFLICT (id) DO UPDATE SET
    source = 'expression',
    expression = 'buildConsensusSignal(evt_consensus)',
    domain = 'qualatative-consensusSignal';
```

**참고**: 현재 코드에서는 `calculate_qualitative_metrics()`가 하드코딩되어 있지만, 지침에 따르면 `config_lv2_metric`의 `qualitative-*` 도메인을 동적으로 처리해야 합니다. 따라서 향후 `MetricCalculationEngine`이 `qualitative` 도메인도 처리하도록 확장되어야 합니다.

#### 3. expression 실패 항목 해결

##### 3.1 의존 메트릭이 None인 경우

**문제**: TTM 메트릭들(`revenueTTM`, `netIncomeTTM`, `ebitdaTTM` 등)이 None이면 이를 사용하는 expression도 실패

**해결 방안**: 의존 메트릭들이 올바르게 계산되도록 base 메트릭 확인

**확인 쿼리**:
```sql
-- TTM 메트릭들의 base_metric_id 확인
SELECT 
    m.id as ttm_metric,
    m.base_metric_id,
    base.id as base_exists,
    base.source as base_source
FROM config_lv2_metric m
LEFT JOIN config_lv2_metric base ON base.id = m.base_metric_id
WHERE m.id IN ('revenueTTM', 'netIncomeTTM', 'ebitdaTTM', 'grossProfitTTM', 'operatingIncomeTTM', 'rndTTM');
```

**수정 필요 시**:
```sql
-- base_metric_id가 잘못된 경우 수정
UPDATE config_lv2_metric
SET base_metric_id = 'revenue'  -- 올바른 base 메트릭 ID로 수정
WHERE id = 'revenueTTM' AND base_metric_id IS NULL OR base_metric_id != 'revenue';
```

##### 3.2 `avgFromQuarter` 메트릭 확인

**확인 쿼리**:
```sql
SELECT 
    m.id,
    m.base_metric_id,
    base.id as base_exists,
    base.source as base_source
FROM config_lv2_metric m
LEFT JOIN config_lv2_metric base ON base.id = m.base_metric_id
WHERE m.aggregation_kind = 'avgFromQuarter';
```

**수정 필요 시**:
```sql
-- base_metric_id가 올바른지 확인 및 수정
UPDATE config_lv2_metric
SET base_metric_id = 'totalDebt'  -- 예시
WHERE id = 'avgTotalDebt' AND (base_metric_id IS NULL OR base_metric_id != 'totalDebt');
```

##### 3.3 `price` expression 실패

**현재 설정**:
```sql
SELECT id, expression
FROM config_lv2_metric
WHERE id = 'price';
```

**문제**: `priceAfter`가 None이면 expression 실패

**해결 방안**: `priceAfter`가 None일 때를 대비한 expression 수정
```sql
-- priceAfter가 None일 때 priceRegular만 사용하도록 수정
UPDATE config_lv2_metric
SET expression = 'priceRegular'  -- 또는 'if priceAfter is not None then priceAfter else priceRegular'
WHERE id = 'price';
```

**참고**: 현재 코드는 `if-then-else`를 지원하지만, `is not None` 체크는 지원하지 않을 수 있음. 단순화:
```sql
UPDATE config_lv2_metric
SET expression = 'priceRegular'  -- priceAfter가 없으면 priceRegular만 사용
WHERE id = 'price';
```

#### 4. 누락된 메트릭 추가

**확인 필요**: 일부 메트릭이 테이블에 없을 수 있음

**확인 쿼리**:
```sql
-- 실패한 메트릭들이 테이블에 존재하는지 확인
SELECT id, source, domain
FROM config_lv2_metric
WHERE id IN (
    'consensus', 'priceAfter', 'priceEodOHLC',
    'apicYoY', 'consensusWithPrev', 'revenueQoQ', 'revenueYoY', 'sharesYoY',
    'price', 'PER', 'runwayYears', 'grossMarginTTM', 'operatingMarginTTM',
    'rndIntensityTTM', 'cashToRevenueTTM', 'PSR', 'debtToEquityAvg',
    'othernclToEquityAvg', 'ROE', 'netdebtToEquityAvg', 'evEBITDA'
);
```

**누락된 메트릭 추가 예시**:
```sql
-- 예: revenueTTM이 없으면 추가
INSERT INTO config_lv2_metric (
    id, description, source, api_list_id, base_metric_id,
    aggregation_kind, aggregation_params, expression, domain
) VALUES (
    'revenueTTM',
    '매출 TTM',
    'aggregation',
    NULL,
    'revenue',
    'ttmFromQuarterSumOrScaled',
    '{"mode": "sum_or_scaled", "order": "desc", "window": 4, "scale_to": 4, "min_points": 1}',
    NULL,
    'internal'
);
```

### 테이블 수정 체크리스트

#### Phase 1: api_field 메트릭 수정 및 세분화
- [ ] `consensus`를 세분화된 항목들로 분리 (consensusPriceTarget, consensusAnalystName, consensusAnalystCompany 등)
- [ ] `targetMedian` 메트릭 추가 (fmp-price-target-consensus)
- [ ] `consensusSummary` 관련 메트릭 추가 (targetLow, targetHigh, targetMedian, targetConsensus)
- [ ] `priceAfter`의 `api_list_id` 및 `response_key` 확인 및 수정
- [ ] `priceEodOHLC`의 `api_list_id` 및 `response_key` 확인 및 수정

#### Phase 2: aggregation 메트릭 확인
- [ ] `apicYoY`, `revenueYoY`, `sharesYoY`의 `base_metric_id` 확인
- [ ] `revenueQoQ`의 `base_metric_id` 확인
- [ ] `consensusWithPrev`의 aggregation_kind 변경 또는 제거

#### Phase 3: expression 메트릭 확인
- [ ] TTM 메트릭들의 `base_metric_id` 확인 및 수정
- [ ] `avgFromQuarter` 메트릭들의 `base_metric_id` 확인 및 수정
- [ ] `price` expression 수정 (priceAfter 없을 때 처리)
- [ ] 의존 메트릭들이 모두 존재하는지 확인

#### Phase 4: 누락된 메트릭 추가
- [ ] 누락된 base 메트릭 추가
- [ ] 누락된 aggregation 메트릭 추가
- [ ] 누락된 expression 메트릭 추가

#### Phase 5: value_qualitative 전체 구조 구현
- [ ] `targetMedian` 메트릭 추가 및 계산 확인
- [ ] `consensusSummary` expression 메트릭 추가 및 계산 확인
- [ ] `consensusSignal` expression 메트릭 추가 (또는 evt_consensus 직접 조회 방식 유지)
- [ ] `value_qualitative` 출력 예시 검증 (`1_guideline(function).ini:851-890`):
  - [ ] `targetMedian` 포함 확인
  - [ ] `consensusSummary` 구조 확인 (`{targetLow, targetHigh, targetMedian, targetConsensus}`)
  - [ ] `consensusSignal` 구조 확인 (`{source, source_id, event_date, direction, last, prev, delta, deltaPct, meta}`)

### 검증 쿼리

**의존성 체크**:
```sql
-- base_metric_id가 존재하는지 확인
SELECT 
    m.id,
    m.base_metric_id,
    CASE WHEN base.id IS NULL THEN 'MISSING' ELSE 'OK' END as base_status
FROM config_lv2_metric m
LEFT JOIN config_lv2_metric base ON base.id = m.base_metric_id
WHERE m.base_metric_id IS NOT NULL;
```

**expression 의존성 체크**:
```sql
-- expression에서 참조하는 메트릭이 존재하는지 확인
-- (수동으로 expression을 파싱하여 확인 필요)
SELECT id, expression
FROM config_lv2_metric
WHERE source = 'expression' AND expression IS NOT NULL;
```

**API 호출 확인**:
```sql
-- api_field 메트릭의 api_list_id가 config_lv1_api_list에 존재하는지 확인
SELECT 
    m.id,
    m.api_list_id,
    CASE WHEN api.id IS NULL THEN 'MISSING' ELSE 'OK' END as api_status
FROM config_lv2_metric m
LEFT JOIN config_lv1_api_list api ON api.id = m.api_list_id
WHERE m.source = 'api_field' AND m.api_list_id IS NOT NULL;
```

