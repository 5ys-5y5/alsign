# priceEodOHLC Dict Response Key 분석

## 1. 개요

`priceEodOHLC`는 일별 OHLC(Open, High, Low, Close) 가격 데이터를 제공하는 메트릭입니다.

**현재 response_key**:
```json
{
  "low": "low",
  "high": "high",
  "open": "open",
  "close": "close"
}
```

**사용 목적**:
- **Open**: 장 시작 가격
- **High**: 하루 최고가
- **Low**: 하루 최저가
- **Close**: 장 마감 가격

**중요성**: 4개 필드 모두 필요하며, close만으로는 불충분합니다.

---

## 2. 현재 상태 분석

### config_lv2_metric 테이블 설정

```sql
SELECT id, source, api_list_id, response_key, domain
FROM config_lv2_metric
WHERE id = 'priceEodOHLC';
```

**결과**:
```
id: priceEodOHLC
source: api_field
api_list_id: fmp-historical-price-eod-full
response_key: {"low": "low", "high": "high", "open": "open", "close": "close"}
domain: (확인 필요)
```

### API 응답 예시

**API**: `GET https://financialmodelingprep.com/api/v3/historical-price-full/{ticker}?apikey=...`

**응답**:
```json
{
  "symbol": "AAPL",
  "historical": [
    {
      "date": "2025-12-08",
      "open": 225.50,
      "high": 228.75,
      "low": 224.00,
      "close": 227.50,
      "adjClose": 227.50,
      "volume": 50000000,
      "unadjustedVolume": 50000000,
      "change": 2.00,
      "changePercent": 0.89,
      "vwap": 226.50,
      "label": "December 08, 25",
      "changeOverTime": 0.0089
    },
    ...
  ]
}
```

**참고**: API 응답이 `{symbol: "...", historical: [...]}` 구조일 수 있음.
실제 데이터는 `historical` 배열 안에 있습니다.

---

## 3. MetricCalculationEngine의 Dict Response Key 지원 여부

### 코드 분석: `metric_engine.py:343-422`

**함수**: `_calculate_api_field()`

**Dict 처리 로직** (385-422줄):
```python
# Handle dict response_key (complex schema mapping)
if isinstance(field_key, dict):
    # Extract multiple fields from API response
    if isinstance(api_response, list):
        # For time-series data, extract dict for each record
        result_list = []
        for record in api_response:
            record_dict = {}
            for output_key, api_key in field_key.items():
                value = record.get(api_key)
                if value is not None:
                    record_dict[output_key] = self._convert_value(value)
            if record_dict:  # Only add if at least one field was found
                result_list.append(record_dict)

        # Return scalar dict if single record, else list of dicts
        if len(result_list) == 1:
            return result_list[0]
        elif len(result_list) > 1:
            return result_list
        else:
            return None
    elif isinstance(api_response, dict):
        # For snapshot data, extract dict from single record
        result_dict = {}
        for output_key, api_key in field_key.items():
            value = api_response.get(api_key)
            if value is not None:
                result_dict[output_key] = self._convert_value(value)
        return result_dict if result_dict else None
```

**결론**: ✅ **Dict response_key 지원이 이미 구현되어 있음!**

### 예상 동작

**입력**:
- `field_key = {"low": "low", "high": "high", "open": "open", "close": "close"}`
- `api_response = [{"date": "2025-12-08", "open": 225.5, "high": 228.75, "low": 224.0, "close": 227.5, ...}, ...]`

**처리**:
```python
result_list = [
    {"low": 224.0, "high": 228.75, "open": 225.5, "close": 227.5},
    {"low": 223.0, "high": 227.0, "open": 224.0, "close": 226.0},
    ...
]
```

**반환**:
- 1개 레코드: `{"low": ..., "high": ..., "open": ..., "close": ...}` (단일 dict)
- 여러 레코드: `[{...}, {...}, ...]` (dict 리스트)

---

## 4. 잠재적 문제점

### 문제 1: API 응답 구조가 `{symbol, historical}` 형태일 수 있음

**현재 가정**:
- `api_response`가 직접 리스트: `[{date, open, high, low, close, ...}, ...]`

**실제 API**:
- FMP historical-price-full API는 `{symbol: "AAPL", historical: [...]}`를 반환
- `historical` 배열을 추출해야 함

**해결 필요 여부**:
- FMPAPIClient의 `call_api()` 함수가 `historical` 배열을 자동으로 추출하는지 확인 필요
- 추출하지 않는다면, API 설정 또는 코드 수정 필요

### 문제 2: config_lv1_api_list에 response_path 설정 필요

**만약 API가 `{symbol, historical}` 구조를 반환한다면**:

`config_lv1_api_list`에 `response_path` 설정:
```sql
UPDATE config_lv1_api_list
SET response_path = '$.historical'
WHERE id = 'fmp-historical-price-eod-full';
```

이렇게 하면 FMPAPIClient가 `historical` 배열만 추출하여 반환합니다.

### 문제 3: 시간적 유효성 필터링 후 데이터가 없을 수 있음

**시나리오**:
- `event_date = '2021-01-31'`인 이벤트 처리
- API에서 최근 100개 레코드를 가져옴 (2023-2025년 데이터)
- `event_date` 이전 필터링 후 데이터가 없음 → `priceEodOHLC = None`

**해결**:
- 이미 `calculate_quantitative_metrics()`에서 필터링 구현됨
- 데이터가 없으면 정상적으로 None 반환
- 문제 없음

---

## 5. 검증 필요 사항

### 5-1. FMPAPIClient가 response_path를 지원하는지 확인

**확인 방법**:
```python
# external_api.py 또는 FMPAPIClient 코드 확인
# response_path 파라미터를 사용하여 nested 응답에서 값을 추출하는지 확인
```

**예상 코드**:
```python
async def call_api(self, api_id, params):
    # config_lv1_api_list에서 API 설정 가져오기
    api_config = await get_api_config(api_id)

    # API 호출
    response = await self.client.get(api_config['url'], params=params)

    # response_path가 있으면 해당 경로에서 데이터 추출
    if api_config.get('response_path'):
        # JSONPath 또는 dot notation으로 추출
        data = extract_path(response, api_config['response_path'])
    else:
        data = response

    return data
```

### 5-2. config_lv1_api_list의 fmp-historical-price-eod-full 설정 확인

**SQL**:
```sql
SELECT id, endpoint, response_path, params_template
FROM config_lv1_api_list
WHERE id = 'fmp-historical-price-eod-full';
```

**확인 사항**:
- `response_path`가 `'$.historical'` 또는 유사한 값으로 설정되어 있는지
- 설정되어 있지 않다면 추가 필요

### 5-3. 실제 API 호출 테스트

**테스트 코드**:
```python
async def test_price_eod_ohlc():
    async with FMPAPIClient() as client:
        result = await client.call_api('fmp-historical-price-eod-full', {
            'ticker': 'AAPL',
            'period': 'quarter',
            'limit': 10
        })

        print(f"Type: {type(result)}")
        print(f"Length: {len(result) if isinstance(result, list) else 'N/A'}")
        if isinstance(result, list) and len(result) > 0:
            print(f"First record: {result[0]}")
        elif isinstance(result, dict):
            print(f"Dict keys: {result.keys()}")
```

---

## 6. 해결 방안

### 현재 상태 확인 후 결정

#### 시나리오 A: FMPAPIClient가 이미 response_path를 지원하고 올바르게 설정됨
- **조치**: 없음 (이미 정상 작동)
- **검증**: 실제 API 호출 테스트로 확인

#### 시나리오 B: response_path는 지원하지만 config_lv1_api_list에 미설정
- **조치**: config_lv1_api_list 업데이트
```sql
UPDATE config_lv1_api_list
SET response_path = '$.historical'
WHERE id = 'fmp-historical-price-eod-full';
```

#### 시나리오 C: response_path를 지원하지 않음
- **조치**: FMPAPIClient 코드 수정하여 response_path 지원 추가
- **또는**: fmp-historical-price-eod-full API 전용 처리 로직 추가

---

## 7. 왜 이전 분석이 잘못되었는가?

### 잘못된 가정

**제안했던 옵션들**:
- **옵션 A (close만 사용)**: ❌ open, high, low를 사용하는 케이스에 대응 못함
- **옵션 B (4개로 분리)**: ❌ API 호출량 4배 증가, 비용 문제
- **옵션 C (삭제)**: ❌ 필요한 항목을 삭제하는 것은 절대 안됨

**실제 문제**:
- Dict response_key 지원이 이미 구현되어 있음
- 문제는 config나 API 호출 부분에 있을 가능성
- 코드 수정이 아닌 설정 확인이 우선

### 올바른 접근

1. **현재 구현 확인**
   - MetricCalculationEngine은 dict를 지원함
   - FMPAPIClient의 response_path 지원 여부 확인

2. **설정 확인**
   - config_lv1_api_list의 response_path 설정
   - API 응답 구조 확인

3. **테스트**
   - 실제 API 호출하여 데이터 확인
   - priceEodOHLC 메트릭 계산 결과 확인

---

## 8. 다음 단계

### 즉시 수행

1. **FMPAPIClient 코드 확인**
   - `backend/src/services/external_api.py` 확인
   - `call_api()` 함수의 response_path 처리 로직 확인

2. **config_lv1_api_list 확인**
   ```sql
   SELECT * FROM config_lv1_api_list WHERE id = 'fmp-historical-price-eod-full';
   ```

3. **실제 API 호출 테스트**
   - 스크립트 작성하여 실제 응답 확인

### 확인 후 결정

- **정상 작동 중**: 아무 조치 불필요
- **설정 문제**: config_lv1_api_list 업데이트
- **코드 문제**: FMPAPIClient 수정

---

## 9. 결론

### 현재 판단

- ✅ MetricCalculationEngine은 dict response_key를 지원함
- ❓ FMPAPIClient의 response_path 지원 여부 확인 필요
- ❓ config_lv1_api_list 설정 확인 필요
- ❓ 실제 API 호출 테스트 필요

### 권장 조치

**먼저 확인**:
1. FMPAPIClient 코드 리뷰
2. config_lv1_api_list 설정 확인
3. 실제 API 테스트

**그 후 결정**:
- 문제가 없으면: 아무 조치 불필요
- 설정 문제면: SQL 업데이트
- 코드 문제면: FMPAPIClient 수정

### 중요한 교훈

- **삭제는 절대 안됨**: 필요한 데이터를 삭제하는 것은 잘못된 접근
- **간단한 해결책의 함정**: close만 사용하거나 4개로 분리하는 것은 부작용이 큼
- **근본 원인 파악 우선**: 코드가 이미 dict를 지원하므로 설정이나 API 문제일 가능성
