# 🎯 미반영 항목 우선순위 분석

**분석일**: 2025-12-24

---

## 📊 항목별 분석

### 1. I-10: priceEodOHLC_dateRange 정책 분리 ⭐⭐⭐

#### 현재 상태
```python
# valuation_service.py - generate_price_trends()
# ❌ 잘못됨: fillPriceTrend_dateRange 재사용
policy = await policies.get_price_trend_date_range(pool)
fetch_start = min_date + timedelta(days=count_start * 2)  # fillPriceTrend 정책 사용
```

#### 문제점
- **지침 위반**: `1_guideline(function).ini`에서 별도 정책 요구
- **잘못된 날짜 범위**: OHLC API 호출에 price trend 정책 사용
- **DB 정책 무시**: `priceEodOHLC_dateRange` 정책 미존재

#### 영향도
- 🔴 **높음**: API 호출 시 잘못된 날짜 범위 사용 가능
- 지침 준수 실패
- 유지보수성 저하

#### 구현 복잡도
- ⭐ **낮음** (30분~1시간)
- DB에 정책 1개 추가
- Python 함수 1개 추가 (10줄)
- 기존 코드 5줄 수정

#### 필요 작업
1. DB: `config_lv0_policy`에 정책 추가
2. Python: `policies.py`에 `get_ohlc_date_range_policy()` 함수 추가
3. Python: `valuation_service.py`에서 호출

---

### 2. I-11: internal(qual) 메트릭 동적 처리 ⭐⭐

#### 현재 상태
```python
# analyst_service.py
# ❌ 하드코딩: calculate_statistics()
stats = {
    'Mean': np.mean(returns),
    'Median': np.median(returns),
    'StdDev': np.std(returns),
    # ... 하드코딩된 통계
}
```

#### 문제점
- **DB 설정 무시**: `config_lv2_metric`의 `internal(qual)` 메트릭 미사용
- **확장성 부족**: 새 통계 지표 추가 시 코드 수정 필요
- **일관성 부족**: 다른 메트릭은 DB 기반인데 이것만 하드코딩

#### 영향도
- 🟡 **중간**: POST /fillAnalyst 엔드포인트 동작은 정상
- 지침 준수 실패
- 향후 확장성 제약

#### 구현 복잡도
- ⭐⭐ **중간** (2~3시간)
- Python: `metrics.py`에 `select_internal_qual_metrics()` 추가
- Python: `analyst_service.py`에서 DB 기반 계산 로직 구현
- 기존 하드코딩 로직 교체

#### 필요 작업
1. Python: `metrics.py`에 쿼리 함수 추가
2. Python: `analyst_service.py`에서 DB 메트릭 정의 읽기
3. Python: 메트릭 ID → 통계 함수 매핑 로직 구현

---

### 3. I-01: leadPairFromList aggregation 구현 ⭐

#### 현재 상태
```python
# valuation_service.py - calculate_qualitative_metrics()
# ✅ 작동 중: 하드코딩으로 consensusSignal 생성
consensus_signal = {
    'direction': consensus_data.get('direction'),
    'last': {...},
    'prev': {...},
    # ... 하드코딩
}
```

#### 문제점
- **부분 동적화**: DB 설정은 되어 있으나 Python 로직 미구현
- **완전성 부족**: aggregation_kind='leadPairFromList' 미지원

#### 영향도
- 🟢 **낮음**: 현재 consensusSignal은 정상 작동 중
- 완전한 동적 처리 미달성
- 기능적 문제 없음

#### 구현 복잡도
- ⭐⭐⭐ **높음** (4~6시간)
- Python: `metric_engine.py`에 `_lead_pair_from_list()` 메서드 구현
- 복잡한 로직: partition, sort, lead 계산
- 기존 하드코딩 제거 및 동적 호출로 교체
- 테스트 필요

#### 필요 작업
1. Python: `metric_engine.py`에 leadPairFromList 구현
2. Python: `valuation_service.py`의 하드코딩 제거
3. 테스트: consensusSignal 정상 동작 확인

---

## 🎯 추천 순서

### 1순위: I-10 (즉시 실행 권장) ⭐⭐⭐

**이유:**
- ✅ **가장 간단** (30분~1시간)
- ✅ **지침 준수** 필수
- ✅ **실질적 문제 해결** (잘못된 날짜 범위)
- ✅ **빠른 성과** 확인 가능

**즉시 시작 가능:**
- DB 정책 추가 SQL 작성
- Python 코드 10줄 추가
- 검증 완료

---

### 2순위: I-11 (단기 실행 권장) ⭐⭐

**이유:**
- ✅ **동적 설정 완성도** 향상
- ✅ **확장성 개선**
- ✅ **일관성 확보** (다른 메트릭과 동일한 방식)
- ⚠️ 중간 복잡도 (2~3시간)

**실행 조건:**
- I-10 완료 후
- DB 메트릭 정의 확인 필요

---

### 3순위: I-01 (장기 실행) ⭐

**이유:**
- ⚠️ **현재 작동 중** (긴급하지 않음)
- ⚠️ **복잡도 높음** (4~6시간)
- ⚠️ **리스크 존재** (기존 로직 교체)
- ✅ **완전성** 향상

**실행 조건:**
- I-10, I-11 완료 후
- 충분한 테스트 시간 확보
- 기능 테스트 환경 준비

---

## 📋 실행 계획

### Phase 1: 즉시 (오늘)
```
✅ I-10: priceEodOHLC_dateRange 정책
   - 예상 시간: 30분~1시간
   - 파일: 2개 (SQL 1개, Python 2개)
```

### Phase 2: 단기 (1주 내)
```
⏸️ I-11: internal(qual) 메트릭
   - 예상 시간: 2~3시간
   - 파일: Python 2개
```

### Phase 3: 장기 (2주 내)
```
⏸️ I-01: leadPairFromList
   - 예상 시간: 4~6시간
   - 파일: Python 2개 + 테스트
```

---

## 💡 결론

**I-10 → I-11 → I-01** 순서로 진행하는 것을 강력히 권장합니다.

### 즉시 시작: I-10
- 간단하고 빠름
- 실질적 문제 해결
- 지침 준수

지금 바로 I-10부터 시작하시겠습니까?

---

*분석 작성: 2025-12-24*

