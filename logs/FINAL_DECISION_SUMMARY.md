# 최종 결정 요약서

## 분석 완료 문서

다음 3개의 상세 분석 문서를 작성했습니다:

1. **`consensusSignal_flow.md`**: consensusSignal의 전체 데이터 흐름 및 처리 방식
2. **`priceEodOHLC_dict_response_key.md`**: dict response_key 지원 현황 및 해결 방안
3. **`missing_metrics_analysis.md`**: 누락된 18개 메트릭의 상세 분석

---

## 결정이 필요한 항목

### 📌 항목 1: consensusSignal config 정리

**현재 상태**:
- config_lv2_metric에 정의되어 있음
- expression: `buildConsensusSignal(consensusWithPrev)`
- 하지만 `consensusWithPrev`는 존재하지 않음
- 실제로는 `calculate_qualitative_metrics()`에서 하드코딩으로 처리

**문제점**:
- 설정과 구현이 불일치
- `buildConsensusSignal()` 함수가 구현되지 않음

**해결 방안**:
```sql
UPDATE config_lv2_metric
SET
  expression = NULL,
  description = 'Consensus signal from evt_consensus Phase 2 data. Calculated in calculate_qualitative_metrics() using source_id to find exact analyst row. Includes direction, last, prev, delta, deltaPct.'
WHERE id = 'consensusSignal';
```

**권장**: ✅ **즉시 적용**

**이유**: 설정과 구현을 일치시켜 혼란 방지

**결정**: [ ] 적용 / [ ] 현재 상태 유지 / [ ] 다른 방안

---

### 📌 항목 2: priceEodOHLC dict response_key

**현재 상태**:
- response_key가 dict 형태: `{"low": "low", "high": "high", "open": "open", "close": "close"}`
- MetricCalculationEngine이 **이미 dict를 지원함** (metric_engine.py:385-422)

**잠재적 문제**:
1. API 응답이 `{symbol, historical: [...]}` 구조일 수 있음
2. config_lv1_api_list에 response_path 설정 필요할 수 있음

**확인 필요 사항**:
1. FMPAPIClient가 response_path를 지원하는지
2. config_lv1_api_list의 fmp-historical-price-eod-full 설정
3. 실제 API 호출 테스트

**권장**: ⚠️ **확인 후 결정**

**다음 단계**:
```python
# 1. FMPAPIClient 코드 확인 (external_api.py)
# 2. config_lv1_api_list 설정 확인
# 3. 실제 API 테스트 스크립트 실행
```

**결정**: [ ] 확인 진행 / [ ] 현재 상태 유지

---

### 📌 항목 3: targetMedian & consensusSummary 구현 (⚠️ 지침 요구사항)

**지침 요구사항** (1_guideline(function).ini:851-890):
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
- ❌ **구현되어 있지 않음**
- calculate_qualitative_metrics()에 targetMedian과 consensusSummary가 없음

**원천 API**: `fmp-price-target-consensus`

**해결 방안**:

#### 옵션 A: 하드코딩으로 구현 (권장)

**이유**:
- consensusSignal과 같은 방식으로 통일
- 간단하고 명확함
- 지침 요구사항 충족

**구현 위치**: `valuation_service.py`의 `calculate_qualitative_metrics()` 함수

**수정 코드** (대략):
```python
async def calculate_qualitative_metrics(
    pool, ticker, event_date, source, source_id
):
    # 기존 consensusSignal 계산...

    # 추가: fmp-price-target-consensus API 호출
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

**필요 작업**:
1. config_lv1_api_list에 `fmp-price-target-consensus` 추가 (이미 있는지 확인)
2. calculate_qualitative_metrics() 함수 수정
3. 테스트

#### 옵션 B: config_lv2_metric에 추가하여 동적 처리

**필요 작업**:
1. config_lv2_metric에 targetMedian, consensusSummaryTargetLow/High/Median/Consensus 추가
2. buildConsensusSummary() 특수 함수 구현
3. MetricCalculationEngine에서 qualitative 도메인 처리 로직 추가

**문제점**:
- 복잡도 증가
- 현재 consensusSignal도 하드코딩되어 있어 일관성 없음

**권장**: ✅ **옵션 A (하드코딩)**

**결정**: [ ] 옵션 A 적용 / [ ] 옵션 B 적용 / [ ] 미구현 (지침 위반)

---

### 📌 항목 4: rnd, totalEquity, otherNCL 짧은 이름 메트릭 추가

**현재 상태**:
- `researchAndDevelopmentExpenses`, `totalStockholdersEquity`, `otherNonCurrentLiabilities`가 존재
- 각각 `rndTTM`, `avgTotalEquity`, `avgOtherNCL`의 base로 사용됨
- **정상 작동 중**

**추가 시**:
```sql
-- rnd 추가
INSERT INTO config_lv2_metric (id, source, api_list_id, response_key, domain, description)
VALUES ('rnd', 'api_field', 'fmp-income-statement', '"researchAndDevelopmentExpenses"', 'internal', 'R&D Expenses');

UPDATE config_lv2_metric SET base_metric_id = 'rnd' WHERE id = 'rndTTM';

-- totalEquity 추가
INSERT INTO config_lv2_metric (id, source, api_list_id, response_key, domain, description)
VALUES ('totalEquity', 'api_field', 'fmp-balance-sheet-statement', '"totalStockholdersEquity"', 'internal', 'Total Equity');

UPDATE config_lv2_metric SET base_metric_id = 'totalEquity' WHERE id = 'avgTotalEquity';

-- otherNCL 추가
INSERT INTO config_lv2_metric (id, source, api_list_id, response_key, domain, description)
VALUES ('otherNCL', 'api_field', 'fmp-balance-sheet-statement', '"otherNonCurrentLiabilities"', 'internal', 'Other Non-Current Liabilities');

UPDATE config_lv2_metric SET base_metric_id = 'otherNCL' WHERE id = 'avgOtherNCL';
```

**효과**:
- 메트릭 이름 통일 및 간결화
- 기능적 차이 없음

**권장**: ⚪ **선택적 (필수 아님)**

**결정**: [ ] 추가 / [ ] 현재 상태 유지

---

### 📌 항목 5: consensus 관련 메트릭 (8개) 추가하지 않음

**누락 메트릭**:
- consensus
- consensusPriceTarget, consensusAnalystName, consensusAnalystCompany
- consensusPriceWhenPosted, consensusNewsURL, consensusNewsTitle
- consensusNewsPublisher, consensusPublishedDate

**현재 상태**:
- evt_consensus 테이블에 모두 저장됨
- calculate_qualitative_metrics()에서 직접 조회하여 사용

**권장**: ⚪ **추가하지 않음**

**이유**:
- evt_consensus에서 직접 조회하는 것이 효율적
- config_lv2_metric에 추가해도 중복 관리
- 실제로 사용되지 않을 가능성

**결정**: [ ] 추가 / [ ] 추가하지 않음 (권장)

---

### 📌 항목 6: consensusWithPrev 추가하지 않음

**현재 상태**:
- 존재하지 않음
- consensusSignal이 참조하려 했으나 실제로는 사용되지 않음

**권장**: ⚪ **추가하지 않음**

**이유**:
- evt_consensus Phase 2에서 이미 prev 값 계산됨
- leadPairFromList aggregation 구현은 불필요한 복잡도
- 지침에서 원천 API 직접 참조 금지

**결정**: [ ] 추가 / [ ] 추가하지 않음 (권장)

---

## 우선순위별 조치 항목

### 🔴 필수 (지침 요구사항)

1. **항목 3: targetMedian & consensusSummary 구현**
   - 지침에서 명확히 요구
   - 현재 미구현 상태
   - 옵션 A (하드코딩) 권장

### 🟡 권장 (설정 정리)

2. **항목 1: consensusSignal config 정리**
   - 설정과 구현 일치
   - 혼란 방지

### 🟡 확인 필요

3. **항목 2: priceEodOHLC 확인**
   - 실제 동작 확인
   - 문제 없으면 조치 불필요

### ⚪ 선택적 (기능적 영향 없음)

4. **항목 4: 짧은 이름 메트릭 추가**
   - 이름 통일
   - 현재 상태 유지도 가능

5. **항목 5, 6: consensus 관련 메트릭 추가하지 않음**
   - 추가 불필요

---

## 추천 실행 순서

### 1단계: 필수 구현

```
[ ] 항목 3: targetMedian & consensusSummary 구현 (옵션 A)
    - calculate_qualitative_metrics() 수정
    - fmp-price-target-consensus API 호출 추가
    - 테스트
```

### 2단계: 설정 정리

```
[ ] 항목 1: consensusSignal config 정리
    - SQL 실행: UPDATE config_lv2_metric SET expression = NULL ...
```

### 3단계: 확인

```
[ ] 항목 2: priceEodOHLC 확인
    - FMPAPIClient 코드 확인
    - config_lv1_api_list 확인
    - API 테스트 스크립트 실행
    - 문제 발견 시 해결
```

### 4단계: 선택적

```
[ ] 항목 4: 짧은 이름 메트릭 추가 (선택)
    - SQL 실행: INSERT INTO config_lv2_metric ...
```

---

## 다음 단계

사용자 결정을 기다립니다. 각 항목에 대해:
- **적용**: 즉시 구현/수정 진행
- **확인**: 상세 확인 작업 진행
- **보류**: 현재 상태 유지
- **거부**: 조치하지 않음

결정해주시면 해당 항목을 순차적으로 진행하겠습니다.
