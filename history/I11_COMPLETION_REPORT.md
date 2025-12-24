# I-11: internal(qual) 메트릭 동적 처리 - 완료 보고서

## 📋 작업 요약

**이슈**: POST /fillAnalyst 엔드포인트에서 하드코딩된 통계 계산 로직 사용  
**목표**: DB의 internal(qual) 메트릭 정의를 기반으로 동적 통계 계산 구현  
**상태**: ✅ **완료** (2025-12-24)

---

## ✅ 완료된 작업

### 1. Python 코드 구현 (이미 완료됨)

#### 📁 `backend/src/database/queries/metrics.py`
**함수**: `select_internal_qual_metrics()` (라인 334-378)

```python
async def select_internal_qual_metrics(pool: asyncpg.Pool) -> List[Dict[str, Any]]:
    """
    Select internal(qual) metrics for analyst performance calculation.
    
    These metrics define which statistics to calculate from the return distribution.
    
    Returns:
        List of metric definitions with domain='internal(qual)' and base_metric_id='priceTrendReturnSeries'
    """
```

**기능**:
- `config_lv2_metric` 테이블에서 `domain='internal(qual)'` 메트릭 조회
- `base_metric_id='priceTrendReturnSeries'` 필터링
- JSONB 필드 파싱 (`aggregation_params`, `response_key`)

---

#### 📁 `backend/src/services/analyst_service.py`
**함수**: `calculate_statistics_from_db_metrics()` (라인 15-114)

```python
def calculate_statistics_from_db_metrics(
    values: List[float],
    internal_metrics: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Calculate statistics based on internal(qual) metric definitions from config_lv2_metric.
    
    Field mapping (guideline line 1171-1178):
    - returnMeanByDayOffset → mean
    - returnMedianByDayOffset → median
    - returnFirstQuartileByDayOffset → p25
    - returnThirdQuartileByDayOffset → p75
    - returnIQRByDayOffset → iqr
    - returnStdDevByDayOffset → stddev
    - returnCountByDayOffset → count
    """
```

**기능**:
- DB 메트릭 정의를 기반으로 통계 계산
- 메트릭 ID를 필드명으로 매핑 (mean, median, p25, p75, iqr, stddev, count)
- 빈 데이터 처리 (None 반환)

**호출 위치**:
- 라인 181: `internal_metrics = await metrics.select_internal_qual_metrics(pool)`
- 라인 339: `stats = calculate_statistics_from_db_metrics(returns, internal_metrics)`

---

### 2. DB 메트릭 설정 (완료)

#### 📊 config_lv2_metric 테이블

**확인된 메트릭** (7개):

| ID | Domain | Source | Aggregation Kind | Expression |
|----|--------|--------|------------------|------------|
| returnCountByDayOffset | internal(qual) | aggregation | statsByDayOffset | NULL |
| returnFirstQuartileByDayOffset | internal(qual) | aggregation | statsByDayOffset | NULL |
| returnIQRByDayOffset | internal(qual) | expression | NULL | returnThirdQuartileByDayOffset - returnFirstQuartileByDayOffset |
| returnMeanByDayOffset | internal(qual) | aggregation | statsByDayOffset | NULL |
| returnMedianByDayOffset | internal(qual) | aggregation | statsByDayOffset | NULL |
| returnStdDevByDayOffset | internal(qual) | aggregation | statsByDayOffset | NULL |
| returnThirdQuartileByDayOffset | internal(qual) | aggregation | statsByDayOffset | NULL |

**추가 작업**:
- `returnIQRByDayOffset` 메트릭 추가 (SQL 스크립트: `backend/scripts/add_internal_iqr_metric.sql`)
- 실행 완료: 2025-12-24

---

## 🔍 검증 결과

### 검증 스크립트
**파일**: `backend/scripts/check_internal_metrics.py`

**실행 결과**:
```
✅ Found 7 internal(qual) metrics:
  📊 returnCountByDayOffset
  📊 returnFirstQuartileByDayOffset
  📊 returnIQRByDayOffset
  📊 returnMeanByDayOffset
  📊 returnMedianByDayOffset
  📊 returnStdDevByDayOffset
  📊 returnThirdQuartileByDayOffset
```

---

## 📊 구현 흐름

```
POST /fillAnalyst
    ↓
1. Load internal(qual) metrics from DB
   → select_internal_qual_metrics(pool)
    ↓
2. Load consensus events
   → analyst.select_consensus_events_with_price_trend(pool)
    ↓
3. Group by (analyst_name, analyst_company)
    ↓
4. For each group, calculate return distribution per dayOffset
    ↓
5. Calculate statistics using DB metric definitions
   → calculate_statistics_from_db_metrics(returns, internal_metrics)
    ↓
6. Map metric IDs to field names
   - returnMeanByDayOffset → mean
   - returnMedianByDayOffset → median
   - returnFirstQuartileByDayOffset → p25
   - returnThirdQuartileByDayOffset → p75
   - returnIQRByDayOffset → iqr
   - returnStdDevByDayOffset → stddev
   - returnCountByDayOffset → count
    ↓
7. Upsert to config_lv3_analyst
```

---

## ✅ 완료 확인 항목

- [x] `select_internal_qual_metrics()` 함수 구현
- [x] `calculate_statistics_from_db_metrics()` 함수 구현
- [x] DB 메트릭 로드 로직 (analyst_service.py:181)
- [x] DB 기반 통계 계산 호출 (analyst_service.py:339)
- [x] DB에 7개 internal(qual) 메트릭 존재
- [x] returnIQRByDayOffset 메트릭 추가
- [x] 검증 스크립트 실행 및 확인
- [x] 하드코딩된 calculate_statistics() 함수 없음 (확인 완료)

---

## 📝 주요 발견 사항

### 1. 이미 구현되어 있었음
코드 분석 결과, **I-11은 이미 대부분 구현되어 있었습니다!**
- `select_internal_qual_metrics()` 함수: 이미 존재
- `calculate_statistics_from_db_metrics()` 함수: 이미 존재
- DB 메트릭 로드 및 호출: 이미 구현됨

### 2. 누락된 메트릭 추가
- `returnIQRByDayOffset` 메트릭만 DB에 없었음
- SQL 스크립트 작성 및 실행으로 추가 완료

### 3. 하드코딩 없음
- 하드코딩된 `calculate_statistics()` 함수는 존재하지 않음
- 모든 통계 계산이 DB 메트릭 정의 기반으로 동작

---

## 📂 관련 파일

### Python 코드
- `backend/src/database/queries/metrics.py` (라인 334-378)
- `backend/src/services/analyst_service.py` (라인 15-114, 181, 339)

### SQL 스크립트
- `backend/scripts/add_internal_iqr_metric.sql`
- `backend/scripts/setup_supabase.sql` (라인 390-398, 414-420)

### 검증 스크립트
- `backend/scripts/check_internal_metrics.py`

### 문서
- `history/1_CHECKLIST.md` (I-11 섹션)
- `history/2_FLOW.md` (I-11 섹션)
- `history/3_DETAIL.md` (I-11 섹션 - 예정)

---

## 🎯 결론

**I-11: internal(qual) 메트릭 동적 처리**는 **✅ 완료**되었습니다!

- Python 코드: 이미 구현되어 있었음 ✅
- DB 메트릭: 7개 모두 존재 (returnIQRByDayOffset 추가) ✅
- 검증: 스크립트 실행으로 확인 완료 ✅
- 하드코딩: 없음 (DB 기반 동적 처리) ✅

---

*작성일: 2025-12-24*  
*작성자: AI Assistant*  
*검증 완료: ✅*

