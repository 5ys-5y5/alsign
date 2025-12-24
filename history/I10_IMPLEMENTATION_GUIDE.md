# 🎯 I-10 구현 가이드: priceEodOHLC_dateRange 정책

**이슈**: I-10 - priceEodOHLC_dateRange 정책 미사용
**상태**: Python 코드는 이미 구현됨 ✅ / DB 정책만 추가 필요 ❌

---

## 📊 현재 상황

### ✅ 이미 구현된 Python 코드

#### 1. `policies.py` (라인 96-123)
```python
async def get_ohlc_date_range_policy(pool: asyncpg.Pool) -> Dict[str, int]:
    """
    Get OHLC API fetch date range policy (countStart, countEnd).
    Uses priceEodOHLC_dateRange policy, separate from fillPriceTrend_dateRange.
    """
    policy = await select_policy(pool, 'priceEodOHLC_dateRange')
    
    if not policy:
        raise ValueError("Policy 'priceEodOHLC_dateRange' not found in config_lv0_policy")
    
    policy_config = policy['policy']
    
    if 'countStart' not in policy_config or 'countEnd' not in policy_config:
        raise ValueError("Policy 'priceEodOHLC_dateRange' missing countStart or countEnd")
    
    return {
        'countStart': int(policy_config['countStart']),
        'countEnd': int(policy_config['countEnd'])
    }
```

#### 2. `valuation_service.py` (라인 840-843)
```python
# Load priceEodOHLC_dateRange policy (separate policy for OHLC API fetch date range)
ohlc_policy = await policies.get_ohlc_date_range_policy(pool)
ohlc_count_start = ohlc_policy['countStart']
ohlc_count_end = ohlc_policy['countEnd']
```

#### 3. OHLC 날짜 범위 계산 (라인 892-896)
```python
# Apply priceEodOHLC_dateRange policy (countStart/countEnd are calendar day offsets)
fetch_start = min_date + timedelta(days=ohlc_count_start)
fetch_end = max_date + timedelta(days=ohlc_count_end)

ohlc_ranges[ticker] = (fetch_start, fetch_end)
```

**결론**: 코드는 완벽하게 구현되어 있습니다! DB 정책만 추가하면 즉시 동작합니다.

---

## ❌ 필요한 작업: DB에 정책 추가

### 단계 1: Supabase SQL Editor 접속

1. https://supabase.com/dashboard 접속
2. 프로젝트 선택 (fgypclaqxonwxlmqdphx)
3. 왼쪽 메뉴에서 **SQL Editor** 클릭
4. **New query** 클릭

### 단계 2: SQL 스크립트 실행

다음 파일의 내용을 복사하여 실행:
```
backend/scripts/add_ohlc_policy.sql
```

또는 직접 복사:

```sql
-- Insert priceEodOHLC_dateRange policy
INSERT INTO config_lv0_policy (
    endpoint,
    function,
    description,
    policy
)
VALUES (
    'POST /backfillEventsTable',
    'priceEodOHLC_dateRange',
    'Date range policy for OHLC API fetch. Defines countStart/countEnd offsets (calendar days) from min/max event dates to determine OHLC API fetch range.',
    '{
        "countStart": -30,
        "countEnd": 7
    }'::jsonb
)
ON CONFLICT (function) DO UPDATE SET
    endpoint = EXCLUDED.endpoint,
    description = EXCLUDED.description,
    policy = EXCLUDED.policy;

-- Verify the insert
SELECT function, policy, description
FROM config_lv0_policy
WHERE function = 'priceEodOHLC_dateRange';
```

### 단계 3: 검증

SQL 실행 후 다음 명령어로 확인:

```bash
cd c:\dev\alsign\backend
python scripts\verify_checklist_items.py
```

**예상 결과**:
```
✅ config_lv0_policy 테이블 존재 (3개 정책)
   - fillPriceTrend_dateRange
   - sourceData_dateRange
   - priceEodOHLC_dateRange  <-- ✅ 새로 추가됨!

   ✅ priceEodOHLC_dateRange 정책 존재 (I-10 관련)
```

---

## 📝 정책 값 설명

### countStart: -30
- **의미**: 이벤트 최소 날짜에서 30일 **이전**부터 OHLC 데이터 가져오기
- **이유**: 과거 트렌드 분석을 위해 충분한 과거 데이터 확보

### countEnd: 7
- **의미**: 이벤트 최대 날짜에서 7일 **이후**까지 OHLC 데이터 가져오기
- **이유**: 이벤트 이후 단기 가격 변동 추적

### 예시
```
이벤트 날짜: 2024-01-15 ~ 2024-01-20

OHLC API 호출 범위:
- fromDate: 2024-01-15 + (-30일) = 2023-12-16
- toDate:   2024-01-20 + (7일)   = 2024-01-27
```

---

## ✅ 완료 후 상태

### DB
- ✅ config_lv0_policy에 priceEodOHLC_dateRange 추가됨

### Python
- ✅ policies.py: get_ohlc_date_range_policy() (이미 구현됨)
- ✅ valuation_service.py: 정책 호출 (이미 구현됨)
- ✅ valuation_service.py: OHLC 날짜 범위 계산 (이미 구현됨)

### 체크리스트
- 🔄 I-10: priceEodOHLC_dateRange 정책 → ✅ 완료

---

## 🎉 예상 소요 시간

- **SQL 실행**: 1분
- **검증**: 1분
- **총 소요 시간**: **2분** 🚀

---

*작성일: 2025-12-24*

