# config_lv2_metric 테이블 변경 제안서

## 현재 상태 요약

- **총 확인 메트릭**: 63개
- **존재하는 메트릭**: 45개
- **누락된 메트릭**: 18개
- **깨진 의존성**: 0개

## 발견된 문제 및 제안 변경 사항

### 📋 항목 1: priceEodOHLC - dict response_key 문제

**현재 상태**:
```
- source: api_field
- api_list_id: fmp-historical-price-eod-full
- response_key: {"low": "low", "high": "high", "open": "open", "close": "close"}
```

**문제**:
- response_key가 dict 형태인데 현재 MetricCalculationEngine은 dict 형태를 지원하지 않음
- metric_engine.py:370-373에서 dict response_key를 만나면 None 반환

**제안 옵션**:

**옵션 A**: response_key를 단일 필드로 변경 (close 가격만 사용)
```sql
UPDATE config_lv2_metric
SET response_key = '"close"'
WHERE id = 'priceEodOHLC';
```

**옵션 B**: 여러 메트릭으로 분리
```sql
-- priceEodOHLC를 4개로 분리
INSERT INTO config_lv2_metric (id, source, api_list_id, response_key, domain, description)
VALUES
  ('priceEodLow', 'api_field', 'fmp-historical-price-eod-full', '"low"', 'internal', 'EOD Low Price'),
  ('priceEodHigh', 'api_field', 'fmp-historical-price-eod-full', '"high"', 'internal', 'EOD High Price'),
  ('priceEodOpen', 'api_field', 'fmp-historical-price-eod-full', '"open"', 'internal', 'EOD Open Price'),
  ('priceEodClose', 'api_field', 'fmp-historical-price-eod-full', '"close"', 'internal', 'EOD Close Price');

-- priceEodOHLC를 expression으로 변경하여 조합
UPDATE config_lv2_metric
SET
  source = 'expression',
  api_list_id = NULL,
  response_key = NULL,
  expression = 'buildOHLC(priceEodOpen, priceEodHigh, priceEodLow, priceEodClose)'
WHERE id = 'priceEodOHLC';
```

**옵션 C**: 삭제하고 사용하지 않음 (현재 실제로 사용되지 않는다면)
```sql
DELETE FROM config_lv2_metric WHERE id = 'priceEodOHLC';
```

**권장**: 옵션 A (단순함, 대부분의 경우 close 가격만 사용)

---

### 📋 항목 2: consensusSignal - 누락된 의존성

**현재 상태**:
```
- source: expression
- expression: buildConsensusSignal(consensusWithPrev)
- domain: qualatative-consensusSignal
```

**문제**:
- `consensusWithPrev` 메트릭이 존재하지 않음
- 실제로는 `calculate_qualitative_metrics()` 함수에서 하드코딩되어 evt_consensus 테이블을 직접 조회하므로 이 설정은 사용되지 않음

**제안 옵션**:

**옵션 A**: expression을 제거하고 설명만 남김 (현재 하드코딩된 방식 유지)
```sql
UPDATE config_lv2_metric
SET
  expression = NULL,
  description = 'Consensus signal (calculated from evt_consensus table in calculate_qualitative_metrics)'
WHERE id = 'consensusSignal';
```

**옵션 B**: 아예 삭제 (config에서 관리하지 않고 완전히 하드코딩)
```sql
DELETE FROM config_lv2_metric WHERE id = 'consensusSignal';
```

**권장**: 옵션 A (설정 유지, 향후 동적 계산으로 전환 가능하도록)

---

### 📋 항목 3: 누락된 consensus 관련 메트릭 (8개)

**누락된 메트릭**:
- consensusPriceTarget
- consensusAnalystName
- consensusAnalystCompany
- consensusPriceWhenPosted
- consensusNewsURL
- consensusNewsTitle
- consensusNewsPublisher
- consensusPublishedDate

**문제**:
- BACKFILL_EVENTS_TABLE_ISSUES_AND_SOLUTIONS.md에서 제안했지만 추가되지 않음
- `consensus` 메트릭 자체도 존재하지 않음

**제안 옵션**:

**옵션 A**: 모두 추가하여 consensus 데이터를 세분화
```sql
-- 실행 스크립트는 별도 파일로 제공
```

**옵션 B**: 필요한 것만 선별적으로 추가
- consensusPriceTarget: 필수 (목표가)
- consensusAnalystName: 필수 (애널리스트 이름)
- consensusAnalystCompany: 필수 (회사)
- 나머지는 선택적

**옵션 C**: 추가하지 않음 (evt_consensus 테이블에서 직접 조회하므로 불필요)

**권장**: 옵션 C (현재 evt_consensus를 직접 조회하므로 중복)
**단**, 향후 MetricCalculationEngine으로 통합할 계획이 있다면 옵션 B

---

### 📋 항목 4: 누락된 targetMedian & consensusSummary 관련 메트릭 (5개)

**누락된 메트릭**:
- targetMedian
- consensusSummaryTargetLow
- consensusSummaryTargetHigh
- consensusSummaryTargetMedian
- consensusSummaryTargetConsensus

**문제**:
- 지침(1_guideline(function).ini:851-890)에서 value_qualitative에 포함되어야 한다고 명시
- 현재 존재하는 것은 `consensusSummary`뿐

**제안 옵션**:

**옵션 A**: 모두 추가 (지침 완벽 준수)
```sql
-- API: fmp-price-target-consensus 사용
INSERT INTO config_lv2_metric ...
```

**옵션 B**: 현재처럼 하드코딩으로 처리 (calculate_qualitative_metrics에서 직접 처리)

**옵션 C**: consensusSummary만 유지하고 내부적으로 처리

**권장**: 옵션 B (현재 하드코딩 방식이 효율적)
**단**, 지침 준수가 중요하다면 옵션 A

---

### 📋 항목 5: 누락된 base 메트릭 (3개)

**누락된 메트릭과 영향**:

#### 5-1. rnd (R&D Expenses)
**영향받는 메트릭**:
- rndTTM (현재 base_metric_id = researchAndDevelopmentExpenses)
- rndIntensityTTM (expression: rndTTM / revenueTTM)

**현재 상태**:
- `researchAndDevelopmentExpenses` 메트릭이 존재함
- `rndTTM`은 이를 base로 사용 중

**제안 옵션**:

**옵션 A**: rnd 메트릭을 추가하고 rndTTM의 base를 rnd로 변경
```sql
-- rnd 추가
INSERT INTO config_lv2_metric (id, source, api_list_id, response_key, domain, description)
VALUES ('rnd', 'api_field', 'fmp-income-statement', '"researchAndDevelopmentExpenses"', 'internal', 'R&D Expenses');

-- rndTTM의 base 변경
UPDATE config_lv2_metric
SET base_metric_id = 'rnd'
WHERE id = 'rndTTM';
```

**옵션 B**: 현재 상태 유지 (researchAndDevelopmentExpenses 사용)
- 문제 없음, 단지 naming이 길 뿐

**권장**: 옵션 B (동작에 문제 없음)

#### 5-2. totalEquity
**영향받는 메트릭**:
- avgTotalEquity (현재 base_metric_id = totalStockholdersEquity)
- debtToEquityAvg, othernclToEquityAvg, ROE, netdebtToEquityAvg (모두 avgTotalEquity 사용)

**현재 상태**:
- `totalStockholdersEquity` 메트릭이 존재함
- `avgTotalEquity`는 이를 base로 사용 중

**제안 옵션**:

**옵션 A**: totalEquity 추가하고 avgTotalEquity의 base를 totalEquity로 변경
```sql
INSERT INTO config_lv2_metric (id, source, api_list_id, response_key, domain, description)
VALUES ('totalEquity', 'api_field', 'fmp-balance-sheet-statement', '"totalStockholdersEquity"', 'internal', 'Total Equity');

UPDATE config_lv2_metric
SET base_metric_id = 'totalEquity'
WHERE id = 'avgTotalEquity';
```

**옵션 B**: 현재 상태 유지 (totalStockholdersEquity 사용)

**권장**: 옵션 B (동작에 문제 없음)

#### 5-3. otherNCL (Other Non-Current Liabilities)
**영향받는 메트릭**:
- avgOtherNCL (현재 base_metric_id = otherNonCurrentLiabilities)
- othernclToEquityAvg (expression: avgOtherNCL / avgTotalEquity)

**현재 상태**:
- `otherNonCurrentLiabilities` 메트릭이 존재함
- `avgOtherNCL`은 이를 base로 사용 중

**제안 옵션**:

**옵션 A**: otherNCL 추가하고 avgOtherNCL의 base를 otherNCL로 변경
```sql
INSERT INTO config_lv2_metric (id, source, api_list_id, response_key, domain, description)
VALUES ('otherNCL', 'api_field', 'fmp-balance-sheet-statement', '"otherNonCurrentLiabilities"', 'internal', 'Other Non-Current Liabilities');

UPDATE config_lv2_metric
SET base_metric_id = 'otherNCL'
WHERE id = 'avgOtherNCL';
```

**옵션 B**: 현재 상태 유지 (otherNonCurrentLiabilities 사용)

**권장**: 옵션 B (동작에 문제 없음)

---

### 📋 항목 6: consensusWithPrev - 구현되지 않은 aggregation

**현재 상태**:
- 메트릭이 존재하지 않음
- consensusSignal이 이를 참조하려고 하지만 실제로는 사용되지 않음

**제안 옵션**:

**옵션 A**: 추가하지 않음 (현재 방식이 올바름)
- evt_consensus 테이블에서 이미 prev 값이 계산되어 있음
- leadPairFromList aggregation을 구현하는 것은 불필요하게 복잡함

**권장**: 옵션 A (추가하지 않음)

---

## 권장 최종 변경 사항

### 필수 변경 (1개)
1. **priceEodOHLC**: response_key를 단일 값으로 변경

### 선택적 변경 (1개)
2. **consensusSignal**: expression 제거 (하드코딩 방식 명시)

### 추가하지 않음 (13개)
- consensus 관련 메트릭 8개: evt_consensus 직접 조회로 충분
- targetMedian & consensusSummary 관련 5개: 하드코딩 처리로 충분
- consensusWithPrev: 불필요

### 현재 상태 유지 (3개)
- rnd → researchAndDevelopmentExpenses 사용 중 (문제 없음)
- totalEquity → totalStockholdersEquity 사용 중 (문제 없음)
- otherNCL → otherNonCurrentLiabilities 사용 중 (문제 없음)

---

## 실행 스크립트

각 항목별로 SQL 스크립트를 준비했습니다. 사용자의 결정에 따라 실행하시면 됩니다.
