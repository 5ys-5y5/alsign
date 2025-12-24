# 누락된 메트릭 상세 분석

## 개요

현재 config_lv2_metric 테이블에 누락된 메트릭 18개에 대한 상세 분석입니다.

**누락된 메트릭 목록**:
1. consensus (1개)
2. consensus 관련 세분화 메트릭 (8개)
3. targetMedian & consensusSummary 관련 (5개)
4. consensusWithPrev (1개)
5. 기타 base 메트릭 (3개): rnd, totalEquity, otherNCL

각 메트릭에 대해:
- **무엇인가?**: 메트릭의 정의와 역할
- **왜 필요/불필요한가?**: 사용 목적과 필요성
- **현재 상태**: 어떻게 처리되고 있는가
- **권장 조치**: 추가 vs 유지 vs 대체

---

## 그룹 1: consensus 메트릭

### 1-1. consensus

**정의**: FMP Price Target API의 전체 응답 데이터

**원천 API**: `fmp-price-target`

**API 응답 구조**:
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

**현재 상태**:
- ❌ config_lv2_metric에 존재하지 않음
- ✅ evt_consensus 테이블에 저장됨 (Phase 1)
- ✅ calculate_qualitative_metrics()에서 직접 조회하여 사용

**필요성 분석**:

**추가해야 하는 경우**:
- MetricCalculationEngine으로 모든 메트릭을 통합 관리하고 싶을 때
- config_lv2_metric 테이블에서 모든 메트릭을 추적하고 싶을 때

**추가하지 않아도 되는 경우** (현재 방식):
- evt_consensus 테이블에서 직접 조회하는 것이 더 효율적
- consensusSignal 생성 시 이미 하드코딩으로 처리 중
- 중복 저장이 불필요

**권장 조치**: ⚪ **추가하지 않음**

**이유**:
1. evt_consensus 테이블이 이미 전체 데이터를 저장
2. consensusSignal 생성 시 직접 조회하는 것이 효율적
3. config_lv2_metric에 추가해도 실제로 사용되지 않을 가능성
4. 중복 관리의 복잡도 증가

---

## 그룹 2: consensus 세분화 메트릭 (8개)

### 2-1. consensusPriceTarget

**정의**: 애널리스트의 목표가 (Price Target)

**원천 필드**: `priceTarget`

**사용 목적**: consensusSignal의 last.price_target 값

**현재 상태**:
- ❌ config_lv2_metric에 존재하지 않음
- ✅ evt_consensus.price_target 컬럼에 저장됨
- ✅ calculate_qualitative_metrics()에서 직접 추출

**권장 조치**: ⚪ **추가하지 않음**

**이유**: evt_consensus에서 직접 조회하므로 중복

---

### 2-2. consensusAnalystName

**정의**: 애널리스트 이름

**원천 필드**: `analystName`

**사용 목적**: consensusSignal의 meta.analyst_name

**현재 상태**:
- ❌ config_lv2_metric에 존재하지 않음
- ✅ evt_consensus.analyst_name 컬럼에 저장됨

**권장 조치**: ⚪ **추가하지 않음**

**이유**: evt_consensus에서 직접 조회하므로 중복

---

### 2-3. consensusAnalystCompany

**정의**: 애널리스트 회사 (증권사)

**원천 필드**: `analystCompany`

**사용 목적**: consensusSignal의 meta.analyst_company

**현재 상태**:
- ❌ config_lv2_metric에 존재하지 않음
- ✅ evt_consensus.analyst_company 컬럼에 저장됨

**권장 조치**: ⚪ **추가하지 않음**

**이유**: evt_consensus에서 직접 조회하므로 중복

---

### 2-4. consensusPriceWhenPosted

**정의**: 목표가 발표 시점의 주가

**원천 필드**: `priceWhenPosted`

**사용 목적**: consensusSignal의 last.price_when_posted

**현재 상태**:
- ❌ config_lv2_metric에 존재하지 않음
- ✅ evt_consensus.price_when_posted 컬럼에 저장됨

**권장 조치**: ⚪ **추가하지 않음**

**이유**: evt_consensus에서 직접 조회하므로 중복

---

### 2-5 ~ 2-8. consensusNewsURL, consensusNewsTitle, consensusNewsPublisher, consensusPublishedDate

**정의**: 뉴스 관련 메타데이터

**사용 목적**: consensusSignal에 포함되지 않음 (현재 사용되지 않음)

**현재 상태**:
- ❌ config_lv2_metric에 존재하지 않음
- ✅ evt_consensus.news_url, news_title, news_publisher 컬럼에 저장됨
- ❌ consensusSignal에서 사용되지 않음

**권장 조치**: ⚪ **추가하지 않음**

**이유**:
1. 현재 consensusSignal에 포함되지 않음
2. 필요하면 evt_consensus에서 직접 조회 가능
3. 지침에서 요구하지 않음

---

## 그룹 3: targetMedian & consensusSummary 관련 (5개)

### 배경: 지침 요구사항

**지침** (1_guideline(function).ini:851-890):
```
value_qualitative = {
  "targetMedian": 0,  // 단일 값
  "consensusSummary": {
    "targetLow": ...,
    "targetHigh": ...,
    "targetMedian": ...,
    "targetConsensus": ...
  },
  "consensusSignal": {...}
}
```

**요구사항**:
1. `targetMedian`: 여러 애널리스트 목표가의 중간값 (단일 값)
2. `consensusSummary`: 목표가 통계 요약 (low, high, median, consensus)

**원천 API**: `fmp-price-target-consensus`

**API 응답 예시**:
```json
[
  {
    "symbol": "AAPL",
    "targetHigh": 260,
    "targetLow": 200,
    "targetConsensus": 235,
    "targetMedian": 240
  }
]
```

---

### 3-1. targetMedian

**정의**: 여러 애널리스트 목표가의 중간값

**원천 API**: `fmp-price-target-consensus`

**원천 필드**: `targetMedian`

**사용 목적**: value_qualitative.targetMedian (지침 요구사항)

**현재 상태**:
- ❌ config_lv2_metric에 존재하지 않음
- ❓ calculate_qualitative_metrics()에서 하드코딩 여부 확인 필요
- ❓ fmp-price-target-consensus API 호출 여부 확인 필요

**권장 조치**: ⚠️ **확인 후 결정**

**옵션 A**: 하드코딩으로 처리 (calculate_qualitative_metrics에 추가)
```python
async def calculate_qualitative_metrics(...):
    # ...
    # Fetch consensus summary from fmp-price-target-consensus
    consensus_summary = await fmp_client.get_price_target_consensus(ticker)

    value_qualitative = {
        'targetMedian': consensus_summary.get('targetMedian', 0),
        'consensusSummary': {
            'targetLow': consensus_summary.get('targetLow'),
            'targetHigh': consensus_summary.get('targetHigh'),
            'targetMedian': consensus_summary.get('targetMedian'),
            'targetConsensus': consensus_summary.get('targetConsensus')
        },
        'consensusSignal': {...}
    }
```

**옵션 B**: config_lv2_metric에 추가하여 동적 처리
```sql
INSERT INTO config_lv2_metric (id, source, api_list_id, response_key, domain, description)
VALUES
  ('targetMedian', 'api_field', 'fmp-price-target-consensus', '"targetMedian"', 'qualatative-targetMedian', 'Target price median from analyst consensus');
```

**결정 기준**:
- **지침 준수가 중요**하다면: 옵션 A 또는 B 중 선택
- **현재 구현 상태**를 먼저 확인해야 함

---

### 3-2 ~ 3-5. consensusSummaryTargetLow, TargetHigh, TargetMedian, TargetConsensus

**정의**: consensusSummary를 구성하는 개별 필드

**사용 목적**: value_qualitative.consensusSummary (지침 요구사항)

**현재 상태**:
- ❌ config_lv2_metric에 존재하지 않음
- ❓ calculate_qualitative_metrics()에서 하드코딩 여부 확인 필요

**권장 조치**: ⚠️ **targetMedian과 동일하게 처리**

**옵션 A**: 하드코딩 (위 참조)

**옵션 B**: config_lv2_metric에 추가
```sql
INSERT INTO config_lv2_metric (id, source, api_list_id, response_key, domain, description)
VALUES
  ('consensusSummaryTargetLow', 'api_field', 'fmp-price-target-consensus', '"targetLow"', 'internal', '...'),
  ('consensusSummaryTargetHigh', 'api_field', 'fmp-price-target-consensus', '"targetHigh"', 'internal', '...'),
  ('consensusSummaryTargetMedian', 'api_field', 'fmp-price-target-consensus', '"targetMedian"', 'internal', '...'),
  ('consensusSummaryTargetConsensus', 'api_field', 'fmp-price-target-consensus', '"targetConsensus"', 'internal', '...');

-- consensusSummary를 expression으로 조합
INSERT INTO config_lv2_metric (id, source, expression, domain, description)
VALUES
  ('consensusSummary', 'expression', 'buildConsensusSummary(consensusSummaryTargetLow, consensusSummaryTargetHigh, consensusSummaryTargetMedian, consensusSummaryTargetConsensus)', 'qualatative-consensusSummary', '...');
```

**참고**: `buildConsensusSummary()` 특수 함수 구현 필요

---

## 그룹 4: consensusWithPrev

### 4-1. consensusWithPrev

**정의**: consensus 데이터에 이전 값을 붙인 것 (lead pair)

**원래 의도**:
- `leadPairFromList` aggregation을 사용하여 consensus 리스트에서 prev 값 생성
- consensusSignal 생성 시 사용

**문제점**:
1. `leadPairFromList` aggregation이 구현되지 않음
2. 불필요하게 복잡함
3. evt_consensus Phase 2에서 이미 prev 값을 계산함

**현재 상태**:
- ❌ config_lv2_metric에 존재하지 않음
- ✅ evt_consensus.price_target_prev, direction이 Phase 2에서 계산됨
- ✅ consensusSignal이 evt_consensus를 직접 조회하여 prev 사용

**권장 조치**: ⚪ **추가하지 않음**

**이유**:
1. evt_consensus Phase 2 방식이 올바르고 효율적
2. leadPairFromList 구현은 불필요한 복잡도 증가
3. 지침에서 원천 API 직접 참조를 금지 (evt_consensus의 표준화된 데이터 사용)

**참고**: consensusSignal_flow.md에서 자세히 설명

---

## 그룹 5: 기타 base 메트릭 (3개)

### 5-1. rnd (R&D Expenses)

**정의**: 연구개발비 (Research & Development Expenses)

**원천 API**: `fmp-income-statement`

**원천 필드**: `researchAndDevelopmentExpenses`

**사용 메트릭**:
- `rndTTM`: TTM 연구개발비
- `rndIntensityTTM`: 연구개발비 집약도 (rndTTM / revenueTTM)

**현재 상태**:
- ❌ `rnd` 메트릭은 존재하지 않음
- ✅ `researchAndDevelopmentExpenses` 메트릭이 존재함
- ✅ `rndTTM.base_metric_id = researchAndDevelopmentExpenses` (정상 작동)

**권장 조치**: ⚪ **추가하지 않음 (현재 상태 유지)**

**이유**:
1. `researchAndDevelopmentExpenses`가 이미 같은 역할 수행
2. `rndTTM`이 정상 작동 중
3. 메트릭 이름이 길어도 기능에는 문제 없음

**대안** (선택적):
- `rnd`를 추가하고 `rndTTM.base_metric_id`를 `rnd`로 변경
- 이름이 짧아지지만 본질적 차이는 없음

```sql
-- 선택적 추가
INSERT INTO config_lv2_metric (id, source, api_list_id, response_key, domain, description)
VALUES ('rnd', 'api_field', 'fmp-income-statement', '"researchAndDevelopmentExpenses"', 'internal', 'R&D Expenses');

-- rndTTM의 base 변경
UPDATE config_lv2_metric
SET base_metric_id = 'rnd'
WHERE id = 'rndTTM';
```

---

### 5-2. totalEquity

**정의**: 총 자본 (Total Stockholders' Equity)

**원천 API**: `fmp-balance-sheet-statement`

**원천 필드**: `totalStockholdersEquity`

**사용 메트릭**:
- `avgTotalEquity`: 평균 자본 (최근 4분기 평균)
- `debtToEquityAvg`, `ROE`, `othernclToEquityAvg`, `netdebtToEquityAvg`: 비율 계산

**현재 상태**:
- ❌ `totalEquity` 메트릭은 존재하지 않음
- ✅ `totalStockholdersEquity` 메트릭이 존재함
- ✅ `avgTotalEquity.base_metric_id = totalStockholdersEquity` (정상 작동)

**권장 조치**: ⚪ **추가하지 않음 (현재 상태 유지)**

**이유**: `researchAndDevelopmentExpenses`와 동일한 상황

**대안** (선택적):
```sql
INSERT INTO config_lv2_metric (id, source, api_list_id, response_key, domain, description)
VALUES ('totalEquity', 'api_field', 'fmp-balance-sheet-statement', '"totalStockholdersEquity"', 'internal', 'Total Equity');

UPDATE config_lv2_metric
SET base_metric_id = 'totalEquity'
WHERE id = 'avgTotalEquity';
```

---

### 5-3. otherNCL (Other Non-Current Liabilities)

**정의**: 기타 비유동부채

**원천 API**: `fmp-balance-sheet-statement`

**원천 필드**: `otherNonCurrentLiabilities`

**사용 메트릭**:
- `avgOtherNCL`: 평균 기타 비유동부채
- `othernclToEquityAvg`: 기타 비유동부채 대 자본 비율

**현재 상태**:
- ❌ `otherNCL` 메트릭은 존재하지 않음
- ✅ `otherNonCurrentLiabilities` 메트릭이 존재함
- ✅ `avgOtherNCL.base_metric_id = otherNonCurrentLiabilities` (정상 작동)

**권장 조치**: ⚪ **추가하지 않음 (현재 상태 유지)**

**이유**: 위와 동일

**대안** (선택적):
```sql
INSERT INTO config_lv2_metric (id, source, api_list_id, response_key, domain, description)
VALUES ('otherNCL', 'api_field', 'fmp-balance-sheet-statement', '"otherNonCurrentLiabilities"', 'internal', 'Other Non-Current Liabilities');

UPDATE config_lv2_metric
SET base_metric_id = 'otherNCL'
WHERE id = 'avgOtherNCL';
```

---

## 종합 권장 사항

### 필수 조치 없음

모든 누락된 메트릭은 다음 중 하나:
1. **중복**: evt_consensus에 이미 저장되어 있음
2. **대체됨**: 다른 이름의 메트릭이 같은 역할 수행
3. **불필요**: 구현하지 않아도 정상 작동

### 확인 필요 (지침 준수)

**targetMedian & consensusSummary**:
- 지침(1_guideline(function).ini)에서 요구하는지 확인 필요
- 현재 calculate_qualitative_metrics()에 구현되어 있는지 확인

**확인 방법**:
```python
# valuation_service.py의 calculate_qualitative_metrics() 확인
# value_qualitative에 targetMedian과 consensusSummary가 포함되어 있는지 확인
```

**확인 후 조치**:
- ✅ 이미 구현됨: 아무 조치 불필요
- ❌ 구현 안됨: 하드코딩 추가 (옵션 A) 또는 config_lv2_metric 추가 (옵션 B)

### 선택적 조치 (이름 통일)

**rnd, totalEquity, otherNCL**:
- 현재 긴 이름으로 정상 작동 중
- 짧은 이름을 선호한다면 추가 가능
- 본질적 차이는 없음

**판단 기준**:
- **현재 상태 유지**: 동작에 문제 없으므로 변경 불필요
- **이름 통일**: 일관성을 위해 짧은 이름 추가 가능

---

## 다음 단계

### 1. 지침 확인

**확인 사항**:
- value_qualitative에 targetMedian과 consensusSummary가 필수인지 확인
- 지침서(1_guideline(function).ini:851-890) 재확인

### 2. 현재 구현 확인

**확인 코드**:
```python
# backend/src/services/valuation_service.py
async def calculate_qualitative_metrics(...):
    # ...
    value_qualitative = {
        'targetMedian': ???,  # 있는지 확인
        'consensusSummary': ???,  # 있는지 확인
        'consensusSignal': {...}
    }
```

### 3. 결정

**시나리오 A**: targetMedian/consensusSummary가 이미 구현됨
- **조치**: 없음

**시나리오 B**: 구현 안되어 있고 지침에서 요구함
- **조치**: calculate_qualitative_metrics()에 하드코딩 추가

**시나리오 C**: 구현 안되어 있지만 지침에서 요구하지 않음
- **조치**: 없음

---

## 결론

### 현재 상태: ✅ 대부분 정상

- **18개 누락 메트릭** 중 대부분이 실제로는 불필요하거나 대체됨
- **기능적 문제 없음**: 모든 의존 메트릭이 정상 작동 중
- **확인 필요**: targetMedian & consensusSummary만 확인

### 권장 조치 요약

| 메트릭 | 개수 | 권장 조치 | 이유 |
|--------|------|-----------|------|
| consensus | 1 | ⚪ 추가 안함 | evt_consensus 테이블 사용 |
| consensus 세분화 | 8 | ⚪ 추가 안함 | evt_consensus에 저장됨 |
| targetMedian 관련 | 5 | ⚠️ 확인 후 결정 | 지침 요구사항 확인 필요 |
| consensusWithPrev | 1 | ⚪ 추가 안함 | Phase 2 방식이 올바름 |
| rnd/totalEquity/otherNCL | 3 | ⚪ 현재 상태 유지 | 다른 이름으로 정상 작동 |

**전체**: 15개 추가 불필요, 3개 선택적, 5개 확인 필요
