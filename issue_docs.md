# Config 수정 이슈 문서

## 항목 1: consensusSignal config 정리

### 현상

config_lv2_metric 테이블의 consensusSignal 메트릭이 실제 구현과 불일치합니다.

**현재 config_lv2_metric 설정**:
```
id: consensusSignal
source: expression
expression: buildConsensusSignal(consensusWithPrev)
domain: qualatative-consensusSignal
```

**실제 구현** (`valuation_service.py:578-684`):
- `calculate_qualitative_metrics()` 함수에서 하드코딩으로 처리
- evt_consensus 테이블을 직접 조회하여 consensusSignal 생성
- `buildConsensusSignal()` 함수는 구현되어 있지 않음
- `consensusWithPrev` 메트릭도 존재하지 않음

### 현상의 문제 원인

1. **설정과 구현의 불일치**: config에는 expression 방식으로 정의되어 있으나 실제로는 하드코딩
2. **존재하지 않는 의존성**: `consensusWithPrev` 메트릭이 존재하지 않음
3. **미구현 함수**: `buildConsensusSignal()` 함수가 MetricCalculationEngine에 구현되지 않음
4. **혼란 야기**: 새로운 개발자가 config를 보고 expression 방식으로 동작한다고 오해할 수 있음

### LLM 제공 선택지

**옵션 A**: expression을 NULL로 설정하고 하드코딩 방식 명시
```sql
UPDATE config_lv2_metric
SET
  expression = NULL,
  description = 'Consensus signal from evt_consensus Phase 2 data. Calculated in calculate_qualitative_metrics() using source_id to find exact analyst row. Includes direction, last, prev, delta, deltaPct.'
WHERE id = 'consensusSignal';
```

**옵션 B**: config_lv2_metric에서 삭제
```sql
DELETE FROM config_lv2_metric WHERE id = 'consensusSignal';
```

**차이점**:
- 옵션 A: 메트릭을 config에 유지하되 하드코딩임을 명시
- 옵션 B: config에서 완전히 제거하여 하드코딩만 사용

### 사용자가 선택한 답

**옵션 B 선택**: consensusSignal을 config_lv2_metric에서 삭제

**이유 (추정)**:
- consensusSignal은 완전히 하드코딩으로 관리
- config_lv2_metric은 동적 계산 가능한 메트릭만 관리
- 혼란을 줄이기 위해 config에서 제거

### LLM이 적용할 diff

**SQL diff**:
```sql
-- consensusSignal 메트릭 삭제
DELETE FROM config_lv2_metric WHERE id = 'consensusSignal';
```

**영향**:
- ✅ config_lv2_metric에서 제거됨
- ✅ `calculate_qualitative_metrics()`는 영향 없음 (하드코딩이므로)
- ✅ MetricCalculationEngine은 consensusSignal을 처리하지 않음 (현재도 처리하지 않음)

**검증**:
```sql
-- 삭제 확인
SELECT id FROM config_lv2_metric WHERE id = 'consensusSignal';
-- 결과: (empty)
```

---

## 항목 2: priceEodOHLC - API 호출 방식 명확화

### 현상

priceEodOHLC_dict_response_key.md에서 API 응답 구조를 `{symbol, historical}` 형태로 잘못 가정했습니다.

**잘못된 가정** (문서에서):
```
API: GET https://financialmodelingprep.com/api/v3/historical-price-full/{ticker}?apikey=...
응답: {symbol: "AAPL", historical: [{...}]}
```

**실제 API** (config_lv1_api_list):
```
api: https://financialmodelingprep.com/stable/historical-price-eod/full?symbol={ticker}&from={fromDate}&to={toDate}&apikey={apiKey}
```

**실제 응답 구조**:
```json
[
  {
    "symbol": "AAPL",
    "date": "2025-12-08",
    "open": 225.5,
    "high": 228.75,
    "low": 224.0,
    "close": 227.5,
    ...
  }
]
```
→ 직접 배열을 반환하므로 `{symbol, historical}` 구조가 아님

### 현상의 문제 원인

1. **하드코딩된 API URL 사용**: 문서 작성 시 config_lv1_api_list를 확인하지 않고 하드코딩된 URL 사용
2. **outdated API 참조**: FMP의 `/api/v3/historical-price-full`은 구버전 API로 `{symbol, historical}` 구조 반환
3. **설정 무시**: config_lv1_api_list 테이블의 api 컬럼을 확인하지 않음

### LLM 제공 선택지

**옵션 A**: response_path 설정 추가 (잘못된 접근)
```sql
-- config_lv1_api_list에 response_path 추가
UPDATE config_lv1_api_list
SET response_path = '$.historical'
WHERE id = 'fmp-historical-price-eod-full';
```

**옵션 B**: priceEodOHLC를 4개 메트릭으로 분리 (잘못된 접근)

**옵션 C**: close만 사용 (잘못된 접근)

**실제 상황**: **조치 불필요**
- API 응답 구조가 `{symbol, historical}` 형태가 아님
- dict response_key가 이미 정상 작동 중
- FMPAPIClient가 config_lv1_api_list의 api 컬럼을 사용 중

### 사용자가 선택한 답

**조치 불필요**: API 응답 구조가 `{symbol, historical}` 형태가 아니므로 response_path 설정 불필요

**사용자 지적 사항**:
- LLM이 하드코딩된 API URL을 사용하여 분석함
- 올바른 방법: `SELECT api FROM config_lv1_api_list WHERE id = 'fmp-historical-price-eod-full'`
- 실제 API는 `/stable/historical-price-eod/full`이며 배열을 직접 반환

### LLM이 적용할 diff

**diff**: 없음 (조치 불필요)

**교훈**:
- ✅ 항상 config_lv1_api_list 테이블의 api 컬럼 확인
- ✅ 하드코딩된 API URL 사용 금지
- ✅ 실제 API 응답 구조 확인 후 분석

**검증** (현재 정상 작동 확인):
```sql
SELECT id, api, schema
FROM config_lv1_api_list
WHERE id = 'fmp-historical-price-eod-full';

-- schema에 이미 priceEodOpen, priceEodHigh, priceEodLow, priceEodClose 정의됨
```

---

## 항목 3: targetMedian & consensusSummary 구현

### 현상

지침(1_guideline(function).ini:851-890)에서 value_qualitative에 다음을 요구:
```json
{
  "targetMedian": 0,
  "consensusSummary": {
    "targetLow": "...",
    "targetHigh": "...",
    "targetMedian": "...",
    "targetConsensus": "..."
  },
  "consensusSignal": {...}
}
```

**현재 상태**:
- ❌ `calculate_qualitative_metrics()`에 targetMedian과 consensusSummary 미구현
- ✅ config_lv2_metric에 `consensusSummary` 메트릭은 존재
  ```
  id: consensusSummary
  source: api_field
  api_list_id: fmp-price-target-consensus
  response_key: {"ticker": "symbol", "targetLow": "targetLow", "targetHigh": "targetHigh", "targetMedian": "targetMedian", "targetConsensus": "targetConsensus"}
  domain: qualatative-consensusSummary
  ```
- ❌ targetMedian 단독 메트릭은 없음

### 현상의 문제 원인

1. **지침 미충족**: value_qualitative에 targetMedian과 consensusSummary가 포함되어 있지 않음
2. **하드코딩 미구현**: calculate_qualitative_metrics()에서 처리하지 않음
3. **개별 필드 메트릭 부재**: targetMedian, consensusSummaryTargetLow 등 개별 메트릭 없음

### LLM 제공 선택지

**옵션 A**: 하드코딩으로 구현
```python
async def calculate_qualitative_metrics(...):
    # fmp-price-target-consensus API 호출
    async with FMPAPIClient() as fmp_client:
        consensus_summary_data = await fmp_client.call_api(
            'fmp-price-target-consensus',
            {'ticker': ticker}
        )

    # consensusSummary 생성
    if consensus_summary_data and len(consensus_summary_data) > 0:
        summary = consensus_summary_data[0]
        consensus_summary = {
            'targetLow': summary.get('targetLow'),
            'targetHigh': summary.get('targetHigh'),
            'targetMedian': summary.get('targetMedian'),
            'targetConsensus': summary.get('targetConsensus')
        }
        target_median = summary.get('targetMedian', 0)
    else:
        consensus_summary = None
        target_median = 0

    value_qualitative = {
        'targetMedian': target_median,
        'consensusSummary': consensus_summary,
        'consensusSignal': consensus_signal
    }
```

**옵션 B**: config_lv2_metric에 추가하여 동적 처리
```sql
-- 개별 필드 메트릭 추가
INSERT INTO config_lv2_metric (id, source, api_list_id, response_key, domain, description)
VALUES
  ('targetMedian', 'api_field', 'fmp-price-target-consensus', '"targetMedian"', 'qualatative-targetMedian', 'Target price median'),
  ('consensusSummaryTargetLow', 'api_field', 'fmp-price-target-consensus', '"targetLow"', 'internal', 'Target price low'),
  ('consensusSummaryTargetHigh', 'api_field', 'fmp-price-target-consensus', '"targetHigh"', 'internal', 'Target price high'),
  ('consensusSummaryTargetMedian', 'api_field', 'fmp-price-target-consensus', '"targetMedian"', 'internal', 'Target price median'),
  ('consensusSummaryTargetConsensus', 'api_field', 'fmp-price-target-consensus', '"targetConsensus"', 'internal', 'Target price consensus');

-- consensusSummary를 expression으로 변경
UPDATE config_lv2_metric
SET
  source = 'expression',
  api_list_id = NULL,
  response_key = NULL,
  expression = 'buildConsensusSummary(consensusSummaryTargetLow, consensusSummaryTargetHigh, consensusSummaryTargetMedian, consensusSummaryTargetConsensus)'
WHERE id = 'consensusSummary';
```

### 사용자가 선택한 답

**옵션 B 선택 (수정)**:
- config_lv2_metric에 추가하여 동적 처리
- **단, 이미 있는 값을 최대한 활용**
- **최소한의 API 호출로 값을 채우기** (절대 준수)

**사용자 지적 사항**:
1. targetMedian 등은 이미 config_lv1_api_list의 schema에 정의되어 있음
   ```json
   {
     "targetLow": "targetLow",
     "targetHigh": "targetHigh",
     "targetMedian": "targetMedian",
     "targetConsensus": "targetConsensus"
   }
   ```
2. consensusSummary가 이미 api_field로 존재하며 fmp-price-target-consensus를 사용 중
3. 개별 필드 메트릭을 추가하되, **같은 API를 여러 번 호출하지 않도록** 해야 함

### LLM이 적용할 diff

#### 방안 A: consensusSummary를 그대로 사용 (권장)

**핵심 아이디어**:
- consensusSummary가 이미 dict response_key로 전체 필드를 가져옴
- MetricCalculationEngine이 dict를 지원하므로 정상 작동
- targetMedian은 consensusSummary에서 추출 (expression 또는 하드코딩)

**SQL diff**:
```sql
-- 1. targetMedian을 expression으로 추가 (consensusSummary에서 추출)
INSERT INTO config_lv2_metric (id, source, expression, domain, description)
VALUES (
  'targetMedian',
  'expression',
  'consensusSummary.targetMedian',  -- consensusSummary dict에서 targetMedian 추출
  'qualatative-targetMedian',
  'Target price median extracted from consensusSummary'
)
ON CONFLICT (id) DO UPDATE SET
  source = 'expression',
  expression = 'consensusSummary.targetMedian',
  domain = 'qualatative-targetMedian';

-- consensusSummary는 이미 존재하므로 수정 불필요
-- 현재 설정:
--   source: api_field
--   api_list_id: fmp-price-target-consensus
--   response_key: {"ticker": "symbol", "targetLow": "targetLow", ...}
--   domain: qualatative-consensusSummary
```

**Python diff** (calculate_qualitative_metrics):
```python
# Before:
value_qualitative = {
    'consensusSignal': consensus_signal
}

# After:
value_qualitative = {
    'targetMedian': calculated_values.get('targetMedian', 0),  # MetricCalculationEngine에서 계산됨
    'consensusSummary': calculated_values.get('consensusSummary'),  # MetricCalculationEngine에서 계산됨
    'consensusSignal': consensus_signal
}
```

**문제**: MetricCalculationEngine이 `consensusSummary.targetMedian` 같은 dict 필드 접근을 지원하지 않을 수 있음

#### 방안 B: 개별 필드 메트릭 추가 (API 중복 호출 방지)

**핵심 아이디어**:
- 개별 필드를 api_field로 추가하되 같은 api_list_id 사용
- MetricCalculationEngine이 같은 API는 한 번만 호출하도록 이미 구현되어 있음 (api_data 캐싱)
- consensusSummary는 expression으로 변경하여 개별 필드 조합

**SQL diff**:
```sql
-- 1. 개별 필드 메트릭 추가 (모두 같은 API 사용)
INSERT INTO config_lv2_metric (id, source, api_list_id, response_key, domain, description)
VALUES
  ('consensusSummaryTargetLow', 'api_field', 'fmp-price-target-consensus', '"targetLow"', 'internal', 'Target price low from consensus'),
  ('consensusSummaryTargetHigh', 'api_field', 'fmp-price-target-consensus', '"targetHigh"', 'internal', 'Target price high from consensus'),
  ('consensusSummaryTargetMedian', 'api_field', 'fmp-price-target-consensus', '"targetMedian"', 'internal', 'Target price median from consensus'),
  ('consensusSummaryTargetConsensus', 'api_field', 'fmp-price-target-consensus', '"targetConsensus"', 'internal', 'Target price consensus from consensus')
ON CONFLICT (id) DO NOTHING;

-- 2. targetMedian 추가 (consensusSummaryTargetMedian과 같은 값)
INSERT INTO config_lv2_metric (id, source, api_list_id, response_key, domain, description)
VALUES (
  'targetMedian',
  'api_field',
  'fmp-price-target-consensus',
  '"targetMedian"',
  'qualatative-targetMedian',
  'Target price median (same as consensusSummaryTargetMedian but in qualatative-targetMedian domain)'
)
ON CONFLICT (id) DO UPDATE SET
  source = 'api_field',
  api_list_id = 'fmp-price-target-consensus',
  response_key = '"targetMedian"',
  domain = 'qualatative-targetMedian';

-- 3. consensusSummary를 expression으로 변경
UPDATE config_lv2_metric
SET
  source = 'expression',
  api_list_id = NULL,
  response_key = NULL,
  expression = 'buildDict(targetLow=consensusSummaryTargetLow, targetHigh=consensusSummaryTargetHigh, targetMedian=consensusSummaryTargetMedian, targetConsensus=consensusSummaryTargetConsensus)',
  description = 'Consensus summary built from individual fields'
WHERE id = 'consensusSummary';
```

**Python diff** (MetricCalculationEngine에 buildDict 함수 추가):
```python
# metric_engine.py

def _calculate_expression(self, metric, calculated_values):
    expression = metric.get('expression')

    # Handle buildDict function
    if expression and expression.startswith('buildDict('):
        # Parse: buildDict(key1=metric1, key2=metric2, ...)
        return self._build_dict(expression, calculated_values)

    # ... existing code ...

def _build_dict(self, expression: str, calculated_values: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build a dict from expression like: buildDict(key1=metric1, key2=metric2)

    Example:
      buildDict(targetLow=consensusSummaryTargetLow, targetHigh=consensusSummaryTargetHigh)
      → {'targetLow': <value of consensusSummaryTargetLow>, 'targetHigh': <value of consensusSummaryTargetHigh>}
    """
    # Extract arguments from buildDict(...)
    import re
    match = re.match(r'buildDict\((.*)\)', expression)
    if not match:
        return None

    args_str = match.group(1)

    # Parse key=value pairs
    result = {}
    for pair in args_str.split(','):
        pair = pair.strip()
        if '=' not in pair:
            continue

        key, metric_name = pair.split('=', 1)
        key = key.strip()
        metric_name = metric_name.strip()

        # Get value from calculated_values
        value = calculated_values.get(metric_name)
        if value is not None:
            result[key] = value

    return result if result else None
```

**장점**:
- ✅ 같은 API는 한 번만 호출됨 (MetricCalculationEngine의 api_data 캐싱)
- ✅ 개별 필드를 다른 메트릭에서도 재사용 가능
- ✅ consensusSummary를 동적으로 생성

**단점**:
- ❌ buildDict() 함수 구현 필요
- ❌ SQL이 복잡함

#### 방안 C: consensusSummary 유지 + 하드코딩 보완 (절충안)

**핵심 아이디어**:
- consensusSummary는 config에 그대로 유지 (api_field, dict response_key)
- calculate_qualitative_metrics()에서 MetricCalculationEngine을 호출하여 consensusSummary 가져오기
- targetMedian은 consensusSummary dict에서 추출

**SQL diff**:
```sql
-- consensusSummary는 수정하지 않음 (이미 올바르게 설정됨)
-- targetMedian 추가하지 않음 (하드코딩으로 처리)
```

**Python diff** (calculate_qualitative_metrics):
```python
async def calculate_qualitative_metrics(
    pool, ticker, event_date, source, source_id
):
    # ... 기존 consensusSignal 계산 ...

    # MetricCalculationEngine으로 consensusSummary 계산
    from .metric_engine import MetricCalculationEngine

    # qualatative 도메인 메트릭 가져오기
    qualitative_metrics_by_domain = await metrics.select_metrics_by_domain(pool, 'qualatative-')

    # Engine 초기화
    engine = MetricCalculationEngine(qualitative_metrics_by_domain, {})
    required_apis = engine.get_required_apis()  # ['fmp-price-target-consensus']

    # API 호출
    api_data = {}
    async with FMPAPIClient() as fmp_client:
        for api_id in required_apis:
            result = await fmp_client.call_api(api_id, {'ticker': ticker})
            api_data[api_id] = result

    # consensusSummary 계산
    target_domains = ['consensusSummary']
    calculated = engine.calculate_all(api_data, target_domains)

    # consensusSummary dict 추출
    consensus_summary = calculated.get('consensusSummary', {}).get('consensusSummary')
    target_median = consensus_summary.get('targetMedian', 0) if consensus_summary else 0

    # value_qualitative 생성
    value_qualitative = {
        'targetMedian': target_median,
        'consensusSummary': consensus_summary,
        'consensusSignal': consensus_signal
    }

    return {
        'status': 'success',
        'value': value_qualitative,
        'currentPrice': float(price_when_posted) if price_when_posted else None,
        'message': 'Qualitative metrics calculated'
    }
```

**장점**:
- ✅ config_lv2_metric 수정 최소화
- ✅ MetricCalculationEngine 재사용
- ✅ API 한 번만 호출

**단점**:
- ❌ 여전히 일부 하드코딩

### 최종 권장: 방안 B (개별 필드 메트릭 추가)

**이유**:
1. ✅ 완전한 동적 처리
2. ✅ 지침 준수 (targetMedian과 consensusSummary 모두 포함)
3. ✅ API 중복 호출 없음 (MetricCalculationEngine 캐싱)
4. ✅ 재사용성 높음

**검증**:
```python
# MetricCalculationEngine의 API 호출 확인
# fmp-price-target-consensus는 한 번만 호출되어야 함
# targetMedian, consensusSummaryTargetLow 등이 모두 같은 API 응답에서 추출됨
```

---

## 항목 4: 짧은 이름 메트릭 사용하지 않음

### 현상

일부 메트릭이 긴 이름으로 정의되어 있습니다:
- `researchAndDevelopmentExpenses` (rnd 대신)
- `totalStockholdersEquity` (totalEquity 대신)
- `otherNonCurrentLiabilities` (otherNCL 대신)

### 현상의 문제 원인

API 응답 필드명을 그대로 사용하여 메트릭 이름이 길어졌습니다.

### LLM 제공 선택지

**옵션 A**: 짧은 이름 메트릭 추가
```sql
INSERT INTO config_lv2_metric ...
```

**옵션 B**: 현재 상태 유지

### 사용자가 선택한 답

**옵션 B 선택**: 테이블에 정의된 명명으로 통일하여 사용

**이유**:
- 일관성 유지
- API 필드명과 직접 매핑되어 명확함
- 짧은 이름 추가는 불필요한 중복

### LLM이 적용할 diff

**diff**: 없음 (현재 상태 유지)

---

## 항목 5: consensus 관련 메트릭

### 현상

다음 8개 메트릭이 config_lv2_metric에 존재하지 않음:
- consensus
- consensusPriceTarget
- consensusAnalystName
- consensusAnalystCompany
- consensusPriceWhenPosted
- consensusNewsURL
- consensusNewsTitle
- consensusNewsPublisher
- consensusPublishedDate

**현재 상태**:
- evt_consensus 테이블에 모두 저장됨
- calculate_qualitative_metrics()에서 직접 조회하여 사용

### 현상의 문제 원인

1. evt_consensus 테이블을 직접 사용하므로 config_lv2_metric에 정의하지 않음
2. consensusSignal 생성 시 하드코딩으로 처리

### LLM 제공 선택지

**옵션 A**: 8개 메트릭 모두 추가
**옵션 B**: 추가하지 않음

### 사용자가 선택한 답

**항목 3과 동일하게 처리**:
- 기존 테이블 스키마 확인
- 기존 값의 expression 업데이트 방식 활용
- **최소한의 API 호출로 값을 채우기** (절대 준수)

**확인 결과**:
- config_lv1_api_list의 fmp-price-target schema에 이미 모든 필드 정의됨:
  ```json
  {
    "ticker": "symbol",
    "newsURL": "newsURL",
    "newsTitle": "newsTitle",
    "analystName": "analystName",
    "analystCompany": "analystCompany",
    "priceTarget": "priceTarget",
    "priceWhenPosted": "priceWhenPosted",
    ...
  }
  ```

### LLM이 적용할 diff

**결론**: **추가하지 않음**

**이유**:
1. ✅ consensusSignal은 evt_consensus 테이블을 직접 조회하는 방식이 올바름
2. ✅ evt_consensus에 Phase 2 계산 결과(prev, direction)가 저장되어 있음
3. ✅ config_lv2_metric에 추가해도 실제로 사용되지 않음 (중복)
4. ✅ API 호출을 늘리지 않으려면 evt_consensus 직접 조회가 효율적

**diff**: 없음

**참고**:
- evt_consensus는 POST /backfillSourceData에서 fmp-price-target API를 호출하여 채워짐
- consensusSignal 계산 시 추가 API 호출 없이 evt_consensus만 조회
- 최소한의 API 호출 원칙 준수

---

## 항목 6: consensusWithPrev

### 현상

consensusWithPrev 메트릭이 config_lv2_metric에 존재하지 않습니다.

**consensusSignal의 expression**:
```
expression: buildConsensusSignal(consensusWithPrev)
```

**문제**:
- consensusWithPrev가 없어서 expression이 실패함
- 실제로는 calculate_qualitative_metrics()에서 하드코딩으로 처리하므로 expression이 사용되지 않음

### 현상의 문제 원인

1. leadPairFromList aggregation이 구현되지 않음
2. consensusSignal이 expression 방식이 아닌 하드코딩 방식으로 처리됨
3. 항목 1에서 consensusSignal을 삭제하기로 결정

### LLM 제공 선택지

**옵션 A**: consensusWithPrev 추가
**옵션 B**: 추가하지 않음

### 사용자가 선택한 답

**항목 1의 진행에 따라 결정**:
- 항목 1에서 consensusSignal을 config_lv2_metric에서 삭제
- consensusSignal이 없으므로 consensusWithPrev도 불필요
- **추가하지 않음** 또는 **다른 방식으로 입력될 수 있음**

### LLM이 적용할 diff

**diff**: 없음 (추가하지 않음)

**이유**:
- ✅ consensusSignal이 config에서 삭제됨
- ✅ evt_consensus Phase 2 방식이 올바름
- ✅ leadPairFromList 구현은 불필요한 복잡도

---

## 요약 및 실행 계획

### 적용할 변경사항

| 항목 | 변경 내용 | 우선순위 |
|------|-----------|----------|
| 항목 1 | consensusSignal 삭제 | 🔴 필수 |
| 항목 2 | 조치 없음 (정상) | - |
| 항목 3 | targetMedian & consensusSummary 구현 (방안 B) | 🔴 필수 |
| 항목 4 | 조치 없음 (현재 상태 유지) | - |
| 항목 5 | 조치 없음 (evt_consensus 직접 조회) | - |
| 항목 6 | 조치 없음 (추가 불필요) | - |

### 실행 순서

1. **항목 1**: consensusSignal 삭제 (SQL 1줄)
2. **항목 3**: targetMedian & consensusSummary 구현 (SQL 다수 + Python 수정)
   - SQL: 개별 필드 메트릭 추가
   - SQL: targetMedian 추가
   - SQL: consensusSummary expression 변경
   - Python: buildDict() 함수 구현

### 다음 단계

사용자 확인 후:
1. SQL 스크립트 작성
2. Python 코드 수정
3. 테스트
4. 적용
