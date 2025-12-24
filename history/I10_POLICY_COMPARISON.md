# 📊 fillPriceTrend_dateRange vs priceEodOHLC_dateRange 비교

**질문**: 왜 두 정책이 필요한가? fillPriceTrend_dateRange를 재사용하면 안 되나?

**답변**: **용도가 완전히 다릅니다!**

---

## 🎯 1. fillPriceTrend_dateRange

### 용도
**price_trend 배열의 dayOffset 범위** (거래일 기준)

### 예시 설정
```json
{
  "countStart": -5,
  "countEnd": 5
}
```

### 의미
- 이벤트 날짜 기준 **거래일** -5일 ~ +5일
- price_trend 배열에 11개 항목 생성 (dayOffset: -5, -4, -3, -2, -1, 0, +1, +2, +3, +4, +5)

### 사용 위치 (valuation_service.py)
```python
# 라인 835-838: 정책 로드
range_policy = await policies.get_price_trend_range_policy(pool)
count_start = range_policy['countStart']  # -5
count_end = range_policy['countEnd']      # +5

# 라인 943-948: dayOffset 스캐폴드 생성 (거래일 계산!)
dayoffset_dates = await calculate_dayOffset_dates(
    event_date,
    count_start,    # -5
    count_end,      # +5
    'NASDAQ',
    pool
)
# 결과: [(−5, 2024-01-08), (−4, 2024-01-09), ..., (0, 2024-01-15), ..., (+5, 2024-01-22)]
```

### 실제 결과
```json
// price_trend 배열
[
  {"dayOffset": -5, "targetDate": "2024-01-08", "open": 100, ...},
  {"dayOffset": -4, "targetDate": "2024-01-09", "open": 101, ...},
  ...
  {"dayOffset": 0,  "targetDate": "2024-01-15", "open": 105, ...},
  ...
  {"dayOffset": +5, "targetDate": "2024-01-22", "open": 110, ...}
]
```

---

## 📅 2. priceEodOHLC_dateRange

### 용도
**OHLC API 호출 시 fromDate/toDate 범위** (달력일 기준)

### 예시 설정
```json
{
  "countStart": -30,
  "countEnd": 7
}
```

### 의미
- 이벤트 날짜 기준 **달력일** -30일 ~ +7일
- OHLC API를 충분히 넓은 범위로 호출하여 모든 거래일 데이터 확보

### 사용 위치 (valuation_service.py)
```python
# 라인 840-843: 정책 로드
ohlc_policy = await policies.get_ohlc_date_range_policy(pool)
ohlc_count_start = ohlc_policy['countStart']  # -30
ohlc_count_end = ohlc_policy['countEnd']      # +7

# 라인 887-896: OHLC API 호출 범위 계산 (달력일!)
min_date = min(event_dates)  # 2024-01-15
max_date = max(event_dates)  # 2024-01-20

fetch_start = min_date + timedelta(days=ohlc_count_start)  # 2024-01-15 + (-30) = 2023-12-16
fetch_end = max_date + timedelta(days=ohlc_count_end)      # 2024-01-20 + (7)   = 2024-01-27

# 라인 916-920: OHLC API 호출
ohlc_data = await fmp_client.get_historical_price_eod(
    ticker,
    fetch_start.isoformat(),  # "2023-12-16"
    fetch_end.isoformat()     # "2024-01-27"
)
```

### 왜 넓은 범위가 필요한가?

#### 문제 상황
- fillPriceTrend_dateRange: countStart=-5, countEnd=+5 (거래일 기준)
- 이벤트 날짜: 2024-01-15 (월요일)
- 필요한 거래일: 2024-01-08 (월) ~ 2024-01-22 (월)

**문제**: 주말 + 공휴일이 있으면 달력일로 -5일 ~ +5일이 **부족합니다!**

```
1월 6일(토) - 주말
1월 7일(일) - 주말
1월 8일(월) ← 거래일 -5
...
1월 13일(토) - 주말
1월 14일(일) - 주말
1월 15일(월) ← 이벤트 날짜 (거래일 0)
...
1월 20일(토) - 주말
1월 21일(일) - 주말
1월 22일(월) ← 거래일 +5
```

**해결**: priceEodOHLC_dateRange로 **넉넉하게** (-30 ~ +7) 데이터를 가져온 후, 
필요한 거래일만 추출

---

## 🔍 실제 코드 흐름 (valuation_service.py)

### 1단계: 정책 로드 (라인 835-843)
```python
# 정책 1: price_trend 배열 범위 (거래일 기준)
range_policy = get_price_trend_range_policy(pool)
count_start = -5   # 거래일 -5
count_end = +5     # 거래일 +5

# 정책 2: OHLC API 호출 범위 (달력일 기준)
ohlc_policy = get_ohlc_date_range_policy(pool)
ohlc_count_start = -30  # 달력일 -30
ohlc_count_end = +7     # 달력일 +7
```

### 2단계: OHLC 데이터 대량 수집 (라인 883-929)
```python
# 모든 이벤트를 ticker별로 그룹핑
# 각 ticker의 min/max 이벤트 날짜 계산
# priceEodOHLC_dateRange 정책 적용 (달력일 -30 ~ +7)
fetch_start = min_date + timedelta(days=-30)
fetch_end = max_date + timedelta(days=+7)

# 한 번의 API 호출로 충분한 데이터 확보
ohlc_data = fmp_client.get_historical_price_eod(ticker, fetch_start, fetch_end)
```

### 3단계: 이벤트별 price_trend 생성 (라인 943-976)
```python
# fillPriceTrend_dateRange 정책 적용 (거래일 -5 ~ +5)
dayoffset_dates = calculate_dayOffset_dates(
    event_date,
    count_start=-5,    # 거래일 -5
    count_end=+5       # 거래일 +5
)
# 결과: 실제 거래일 11개의 (dayOffset, date) 리스트

# 2단계에서 받은 OHLC 데이터에서 필요한 날짜만 추출
for dayoffset, target_date in dayoffset_dates:
    ohlc = ohlc_cache[ticker][target_date]  # 2단계 데이터에서 찾기
    price_trend.append({
        'dayOffset': dayoffset,
        'targetDate': target_date,
        'open': ohlc['open'],
        ...
    })
```

---

## 📌 결론

### ❌ fillPriceTrend_dateRange를 재사용하면 안 되는 이유

1. **목적이 다름**
   - fillPriceTrend: price_trend 배열의 범위 (출력 데이터 구조)
   - priceEodOHLC: API 호출 범위 (입력 데이터 수집)

2. **기준이 다름**
   - fillPriceTrend: 거래일 기준 (-5 거래일 ~ +5 거래일)
   - priceEodOHLC: 달력일 기준 (-30 달력일 ~ +7 달력일)

3. **범위가 다름**
   - fillPriceTrend: 좁은 범위 (예: -5 ~ +5 = 11개 항목)
   - priceEodOHLC: 넓은 범위 (예: -30 ~ +7 = 37일치 데이터)

4. **사용 시점이 다름**
   - fillPriceTrend: 각 이벤트마다 사용 (거래일 계산)
   - priceEodOHLC: ticker별 1회 사용 (API 호출 최소화)

### ✅ 올바른 구현 (현재 코드)

코드는 **이미 완벽하게 구현**되어 있습니다!
- 두 정책을 별도로 로드 ✅
- 각각의 용도에 맞게 사용 ✅
- 단지 DB에 priceEodOHLC_dateRange 정책이 없어서 에러 발생 중 ❌

### 🎯 필요한 작업

**DB에 priceEodOHLC_dateRange 정책만 추가하면 완료!**

---

*작성일: 2025-12-24*

