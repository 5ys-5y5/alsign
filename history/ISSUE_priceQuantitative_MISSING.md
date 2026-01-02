# ⚠️ 중대 이슈: priceQuantitative 메트릭 미구현

**발견**: 2026-01-02
**우선순위**: HIGH
**상태**: 설계 불일치

---

## 📋 문제 요약

원본 설계(1_guideline(function).ini)와 실제 구현이 다릅니다:

- **원본 설계**: `priceQuantitative` 메트릭 사용
- **실제 구현**: `calcFairValue` 파라미터 + peer tickers 기반 적정가 계산

---

## 🔍 상세 분석

### 1. 원본 설계 요구사항

**파일**: `prompt/1_guideline(function).ini`
**라인**: 892-897

```ini
position_quantitative: [table.metric] 테이블의 priceQuantitative인 값이
                      [table.metric] 테이블의 price 값보다 작다면 short, 크다면 long
    - 출력 예시: "long" | "short" | "undefined"

disparity_quantitative: {([table.metric] 테이블의 priceQuantitative인 값) /
                        ([table.metric] 테이블의 price 값)} - 1 값 기록
    - 출력 예시: -0.2
```

**설계 의도**:
- config_lv2_metric 테이블에 `priceQuantitative` 메트릭 정의 필요
- quantitative 지표에서 직접 적정가 도출
- 모든 ticker에 대해 일관되게 계산 가능해야 함

### 2. 실제 구현 (I-36 해결안)

**발견**: 2025-12-31
**구현**: `calcFairValue` 파라미터 추가

#### 현재 동작

```python
# backend/src/services/valuation_service.py:191-209
if calc_fair_value:
    # 업종 평균 기반 적정가 계산
    fair_value_result = await calculate_fair_value_for_ticker(...)
    position_quant = fair_value_result.get('position')
    disparity_quant = fair_value_result.get('disparity')
else:
    # NULL 유지
    position_quant, disparity_quant = None, None
```

#### 계산 방식

1. `fmp-stock-peers` API로 peer tickers 조회
2. Peer tickers의 평균 PER/PBR 계산
3. 평균 PER × EPS = 적정가
4. 적정가와 현재가 비교 → position/disparity 산출

#### 문제점

- **priceQuantitative 메트릭이 config_lv2_metric에 없음**
- Peer tickers 없는 경우 NULL (소형주, 특수 섹터)
- 설계 문서와 불일치

---

## 🔬 DB 검증

### config_lv2_metric 테이블 확인

```sql
SELECT id, domain, source, expression
FROM config_lv2_metric
WHERE id LIKE '%priceQuantitative%';
```

**결과**: `NOT FOUND`

**현재 quantitative 메트릭**:
- PER, PBR, PSR, PEG (valuation)
- ROE, ROA, ROIC (profitability)
- revenueGrowth, epsGrowth (momentum)
- debtToEquity, currentRatio (risk)
- sharesOutstanding, sharesDilution (dilution)

→ **priceQuantitative 메트릭이 존재하지 않음**

---

## 🎯 현재 동작 (calcFairValue 방식)

### 성공 사례: 대형주 (AAPL, MSFT)

```json
{
  "value_quantitative": {
    "valuation": {
      "PER": 28.5,
      "PBR": 7.2,
      "_fairValue": {
        "value": 185.0,
        "sectorAverages": {"PER": 25.0, "PBR": 6.5},
        "peerCount": 12
      }
    }
  },
  "position_quantitative": "short",
  "disparity_quantitative": -0.12
}
```

### 실패 사례: 소형주/특수 섹터 (RGTI)

```json
{
  "value_quantitative": {
    "valuation": {"PER": -19.09, "PBR": 18.02}
    // ← _fairValue 없음 (peer tickers 없음)
  },
  "position_quantitative": null,  // ← NULL
  "disparity_quantitative": null  // ← NULL
}
```

**로그**: `[I-36] No peer tickers found for RGTI, skipping fair value calculation`

---

## ⚖️ 설계 vs 구현 비교

| 항목 | 원본 설계 | 실제 구현 |
|------|-----------|-----------|
| **메트릭 정의** | priceQuantitative 메트릭 | ❌ 미존재 |
| **계산 방법** | 메트릭 기반 적정가 | Peer 평균 기반 적정가 |
| **적용 범위** | 모든 ticker | Peer 있는 ticker만 |
| **실패 시** | 설계상 명시 없음 | NULL 유지 |
| **추가 API** | 없음 | fmp-stock-peers 필요 |

---

## 💡 해결 방안 제안

### Option A: priceQuantitative 메트릭 구현 (원본 설계 준수)

**장점**:
- 원본 설계 문서와 일치
- 모든 ticker에 일관되게 적용 가능
- Peer tickers 의존성 제거

**단점**:
- priceQuantitative 계산 로직 정의 필요
- 기존 calcFairValue 방식과 병행/대체 결정 필요

**구현 방안**:
1. config_lv2_metric에 priceQuantitative 메트릭 추가
2. 계산 공식 정의 (예: 업종 평균 PER × EPS)
3. 메트릭 엔진에서 자동 계산

### Option B: 설계 문서 업데이트 (현행 유지)

**장점**:
- 이미 구현되어 작동 중
- I-36, I-38, I-40 이슈로 문서화됨

**단점**:
- 원본 설계와 영구적 불일치
- Peer 없는 ticker는 NULL

**필요 작업**:
1. 1_guideline(function).ini 업데이트
2. priceQuantitative → calcFairValue 방식으로 명시
3. NULL 발생 조건 문서화

### Option C: 하이브리드 (권장)

**구현**:
1. priceQuantitative 메트릭 추가 (fallback용)
2. calcFairValue=true 시 peer 기반 계산 우선
3. Peer 없으면 priceQuantitative 메트릭 사용

**장점**:
- 원본 설계 준수
- Peer 없는 ticker도 계산 가능
- 유연성 확보

---

## 📊 영향 분석

### 현재 NULL 발생률

```bash
# 전체 이벤트: 136,954개
# position_quantitative NULL: 136,954개 (100%)
# disparity_quantitative NULL: 136,954개 (100%)
```

**원인**:
- calcFairValue=true가 기본값 (I-38)
- 그러나 대부분 ticker가 peer tickers 없음
- 결과적으로 여전히 100% NULL

### 영향받는 ticker 비율

```sql
-- Peer tickers 보유 ticker 수
SELECT COUNT(DISTINCT ticker) FROM config_lv3_targets;
-- 결과: 예상 10-20% (대형주 중심)
```

---

## 🎯 권장 조치

### 즉시 (단기)

1. **설계 결정 필요**: Option A/B/C 중 선택
2. **문서화**: 현재 동작 방식 명확히 기록
3. **알려진 제한사항**: README 업데이트

### 중기

1. **priceQuantitative 메트릭 구현** (Option A 또는 C 선택 시)
2. **Fallback 로직**: Peer 없을 때 대체 방법
3. **테스트 케이스**: 다양한 ticker 유형 검증

### 장기

1. **대체 valuation 방법**: P/S ratio, DCF 등
2. **Manual peer 설정**: 특수 섹터 대응
3. **Machine Learning**: 적정가 예측 모델

---

## 📝 관련 이슈

- **I-36**: Quantitative Position/Disparity 항상 None (calcFairValue 구현)
- **I-38**: calcFairValue 기본값 False → True
- **I-40**: Peer tickers 미존재 시 NULL (설계상 예상 동작으로 분류됨)

---

## 🔗 관련 파일

- `prompt/1_guideline(function).ini` (원본 설계)
- `backend/src/services/valuation_service.py` (구현)
- `history/1_CHECKLIST.md`, `history/3_DETAIL.md` (문서화)

---

*작성일: 2026-01-02*
*우선순위: HIGH - 설계 불일치*
*결정 필요: priceQuantitative 메트릭 구현 여부*
