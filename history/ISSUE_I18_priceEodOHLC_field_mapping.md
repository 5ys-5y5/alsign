# I-18: priceEodOHLC 필드 매핑 불일치

> **발견 일시**: 2025-12-25
> **심각도**: 🔴 높음 (OHLC 데이터 전체 실패)

---

## 🔍 문제 발견

### 로그 증거
```
[priceEodOHLC] First record keys: ['ticker', 'date', 'priceEodOpen', 'priceEodHigh', 'priceEodLow', 'priceEodClose', ...]
[priceEodOHLC] Field 'low' not found in record, available keys: ['ticker', 'date', 'priceEodOpen', ...]
[priceEodOHLC] Extracted 0 dicts from 768 records
```

### 현상
- API 응답: 768개 레코드 수신 성공
- 필드 추출: 0개 추출 (100% 실패)
- 이유: 필드명 불일치

---

## 🚨 추가 발견: Schema 타입 오류!

### 실제 에러 로그
```
[Schema Mapping Error] fmp-historical-price-eod-full -> AttributeError: 'list' object has no attribute 'items'
[Schema Mapping Error] Schema type: <class 'list'>, Schema: [{'low': 'low', 'date': 'date', ...}]
```

### 근본 원인
**DB에 저장된 schema가 잘못된 타입!**

```json
❌ 현재 DB 상태: [{'low': 'low', 'date': 'date', ...}]  // list 타입
✅ 올바른 형태:  {'low': 'low', 'date': 'date', ...}    // dict 타입
```

**`external_api.py`의 `_apply_schema_mapping()` 함수**:
```python
def _apply_schema_mapping(self, data: Any, schema: Dict[str, str]) -> Any:
    if isinstance(data, dict):
        return {schema.get(k, k): v for k, v in data.items()}  # ✅ dict.items() 작동
    elif isinstance(data, list):
        return [self._apply_schema_mapping(item, schema) for item in data]

# 문제: schema가 list이면
schema.items()  # ❌ AttributeError: 'list' object has no attribute 'items'
```

### 데이터 흐름 (수정 후)
```
1. FMP API 원본 응답
   └─> {symbol: "RGTI", open: 24.19, high: 25.22, low: 22.41, close: 22.47, ...}

2. config_lv1_api_list.schema 매핑 적용 (external_api.py)
   └─> schema = {'symbol': 'ticker', 'open': 'open', 'low': 'low', ...}  ✅ dict
   └─> {ticker: "RGTI", open: 24.19, high: 25.22, low: 22.41, close: 22.47, ...}

3. config_lv2_metric.response_key로 추출 (metric_engine.py)
   └─> response_key = {'low': 'low', 'high': 'high', 'open': 'open', 'close': 'close'}
   └─> ✅ 성공: {low: 22.41, high: 25.22, open: 24.19, close: 22.47}
```

## 🚨 원인 분석

### 데이터 흐름
```
1. FMP API 원본 응답
   └─> {open: 26.3, high: 26.88, low: 25.06, close: 25.84, ...}

2. config_lv1_api_list.schema 매핑 적용 (external_api.py)
   └─> {priceEodOpen: 26.3, priceEodHigh: 26.88, priceEodLow: 25.06, priceEodClose: 25.84, ...}

3. config_lv2_metric.response_key로 추출 시도 (metric_engine.py)
   └─> 찾으려는 필드: 'low', 'high', 'open', 'close'
   └─> ❌ 실패: 필드명이 이미 변환됨
```

### 근본 원인
**이중 매핑 문제**:
- `config_lv1_api_list.schema`: FMP API 필드 → 내부 표준 필드 (1차 변환)
- `config_lv2_metric.response_key`: 내부 표준 필드 → 메트릭 필드 (2차 추출)
- **문제**: response_key가 1차 변환 전 필드명을 참조

### DB 확인
```sql
-- config_lv1_api_list의 schema (추정)
SELECT schema FROM config_lv1_api_list WHERE api = 'fmp-historical-price-eod-full';
-- 결과: {"open": "priceEodOpen", "high": "priceEodHigh", "low": "priceEodLow", "close": "priceEodClose", ...}

-- config_lv2_metric의 response_key (현재 - 잘못됨)
SELECT response_key FROM config_lv2_metric WHERE id = 'priceEodOHLC';
-- 결과: {"low": "low", "high": "high", "open": "open", "close": "close"}
-- 문제: 변환 전 필드명을 참조
```

---

## 💡 해결 방안

### 옵션 A: response_key 수정
**장점**: 
- 스키마 매핑의 의도를 유지 (priceEod 접두사로 명확화)
- 다른 메트릭에 영향 없음

**단점**: 
- FMP API 원본과 불일치 (open → priceEodOpen)
- 불필요한 필드명 변환 유지
- ❌ **FMP API는 실제로 `open`, `high`, `low`, `close`를 사용함!**

### 옵션 B: schema 수정 (✅ 권장)
**장점**: 
- FMP API 원본 필드명과 일치
- response_key는 그대로 유지 (변경 불필요)
- 직관적이고 명확
- **FMP API 실제 응답과 정확히 일치**

**단점**: 
- 다른 곳에서 `priceEodOpen` 등을 참조한다면 영향
- → 확인 결과: `priceEodOHLC` 메트릭만 사용, 영향 없음

### 옵션 C: 이중 매핑 제거 설계 개선
**장점**: 
- 근본적 해결
- 미래의 유사 문제 방지

**단점**: 
- 대규모 리팩토링 필요
- 전체 시스템 영향

---

## ✅ 채택된 해결책: 옵션 B (수정됨)

### 문제 재분석
**FMP API 원본 응답 확인**:
```json
{
  "symbol": "RGTI",
  "date": "2022-12-12",
  "open": 1,           ← 원본 필드명
  "high": 1.01,        ← 원본 필드명
  "low": 0.95,         ← 원본 필드명
  "close": 0.9638,     ← 원본 필드명
  ...
}
```
**출처**: [FMP API 실제 호출 결과](https://financialmodelingprep.com/stable/historical-price-eod/full?symbol=RGTI&from=2022-12-11&to=2022-12-12&apikey=...)

**결론**: FMP API는 `open`, `high`, `low`, `close`를 그대로 사용합니다.
→ `config_lv1_api_list.schema`가 **불필요하게** `priceEodOpen` 등으로 변환했습니다!

### 올바른 해결책: schema 수정

```sql
-- config_lv1_api_list의 schema를 수정하여 원본 필드명 유지
UPDATE config_lv1_api_list
SET schema = '{
  "symbol": "ticker",
  "date": "date",
  "open": "open",
  "high": "high",
  "low": "low",
  "close": "close",
  "volume": "volume",
  "change": "change",
  "changePercent": "changePercent",
  "vwap": "vwap"
}'::jsonb
WHERE api = 'fmp-historical-price-eod-full';
```

### 적용 파일
- `backend/scripts/fix_fmp_historical_price_schema.sql` (권장)
- ~~`backend/scripts/fix_priceEodOHLC_response_key.sql`~~ (불필요)

### 예상 결과
**Before**:
```
[priceEodOHLC] Field 'low' not found in record
[priceEodOHLC] Extracted 0 dicts from 768 records
```

**After**:
```
[priceEodOHLC] Extracted 768 dicts from 768 records
[priceEodOHLC] First result: {'low': 1.26, 'high': 1.34, 'open': 1.3, 'close': 1.28}
[MetricEngine] ✓ priceEodOHLC = [{'low': 1.26, ...}, ...] (source: api_field)
```

---

## 🔍 근본 원인 고찰

### 이중 매핑의 문제점
1. **복잡성 증가**: 2단계 매핑으로 인한 혼란
2. **유지보수 어려움**: 두 곳의 설정이 동기화되어야 함
3. **디버깅 어려움**: 어느 단계에서 문제인지 파악 곤란

### 설계 개선 제안 (장기)
```
현재: FMP API → schema 매핑 → response_key 추출
개선: FMP API → 단일 매핑 → 직접 사용

또는:
현재: 2단계 매핑 (config_lv1_api_list.schema + config_lv2_metric.response_key)
개선: 1단계 매핑 (config_lv2_metric.api_field_mapping)
```

### 향후 방지책
1. **문서화**: 스키마 매핑과 response_key의 관계 명시
2. **검증 쿼리**: 매핑 일관성 자동 체크
3. **테스트**: 신규 메트릭 추가 시 필드 추출 테스트 필수

---

## 📊 영향 분석

### 영향받는 메트릭
- `priceEodOHLC`: 직접 영향

### 연쇄 영향
- `priceEodOHLC`에 의존하는 모든 메트릭
- OHLC 데이터를 사용하는 분석 기능

### 데이터 무결성
- 기존 DB 데이터: 영향 없음 (NULL 상태였음)
- 신규 데이터: SQL 실행 후 정상 수집 예상

---

## ✅ 체크리스트

- [x] 문제 원인 규명
- [x] 디버깅 로그로 증거 확보
- [x] SQL 스크립트 작성
- [x] 문서화 (이 파일)
- [ ] SQL 실행
- [ ] 백엔드 재시작
- [ ] POST /backfillEventsTable 재실행
- [ ] 결과 검증

---

*작성: 2025-12-25*  
*해결: SQL 스크립트 작성 완료, 실행 대기 중*

