# 📊 AlSign 이슈 흐름도 (I-18, I-19 추가분)

> 이 문서는 2_FLOW.md의 I-18, I-19 항목입니다.

---

## I-18: priceEodOHLC Schema Array Type 문제

### 현상
`POST /backfillEventsTable` 실행 시 에러 발생:
```
[MetricEngine] Failed to calculate priceEodOHLC: unhashable type: 'list'
```

**에러 위치**: `metric_engine.py:74` - `api_ids.add(api_list_id)`

### 원인
1. **DB 타입 오류**: `config_lv1_api_list.schema`가 array `[{}]`로 저장됨
2. **Python 타입 제약**: `set()`에 list를 추가할 수 없음 (unhashable)
3. **일관성 문제**: 19개 API 중 1개만 array type

**기술적 원인**:
```python
# metric_engine.py:74
api_ids.add(api_list_id)  # list는 set에 추가 불가!

# external_api.py 
schema.items()  # list에는 .items() 메서드 없음!
```

### LLM 제공 선택지
| 옵션 | 설명 | 장점 | 단점 |
|------|------|------|------|
| A | 단일 API만 수정 | 빠른 수정 | 다른 API 미검증 |
| B | 전체 API 검증 + 수정 | 시스템 안정성 | 시간 소요 |

### 사용자 채택
**옵션 B** - 전체 API 검증 후 일괄 수정

**이유**:
- 동일 문제가 다른 API에도 존재할 가능성
- 한 번에 모든 array type 문제 해결
- 향후 유사 문제 방지

### 반영 내용
- **상태**: ✅ 반영 완료
- **진단 스크립트**: `backend/scripts/diagnose_priceEodOHLC_issue.sql`
- **검증 스크립트**: `backend/scripts/verify_all_api_schemas.sql`
- **수정 스크립트**: `backend/scripts/fix_priceEodOHLC_array_types.sql`
- **통합 실행**: `backend/scripts/EXECUTE_FIX_SEQUENCE.sql`

**검증 결과**:
- ❌ 1개 API (array): `fmp-historical-price-eod-full`
- ✅ 18개 API (object): 정상

**수정 내용**:
```sql
-- schema: array → object
UPDATE config_lv1_api_list
SET schema = '{"symbol": "ticker", "date": "date", ...}'::jsonb
WHERE jsonb_typeof(schema) = 'array';
```

### 교훈
- **JSONB 타입**: `[{}]` ≠ `{}`
- **전체 검증**: 하나의 문제는 다른 곳에도 존재
- **타입 일관성**: 모든 API schema는 object 타입

---

## I-19: 메트릭 로그 Truncation 문제

### 현상
메트릭 로그가 50자로 잘려서 중요한 정보 누락:
```
[MetricEngine] ✓ priceEodOHLC = [{'low': 15.48, 'high': 16.37, 'open': 15.65, 'clo
                                                                              ^^^^ 잘림!
```

**문제점**:
1. `close` 필드 값이 표시 안됨
2. 리스트 총 개수 알 수 없음
3. 과도한 디버그 로그 (priceEodOHLC 전용 6줄)

### 원인
1. **하드코딩된 길이**: `str(value)[:50]` → 50자로 자름
2. **단순 문자열 변환**: 리스트/스칼라 구분 없이 동일 처리
3. **과도한 디버깅**: priceEodOHLC 전용 warning 로그 5개

**코드 위치**: `metric_engine.py:261, 431-473`

### LLM 제공 선택지
| 옵션 | 설명 | 장점 | 단점 |
|------|------|------|------|
| A | 길이 증가 (50→100자) | 간단 | 여전히 잘림 가능 |
| B | 스마트 포맷팅 | 정보 최적화 | 로직 복잡 |
| C | 로그 레벨 분리 | 환경별 제어 | 디버깅 어려움 |

### 사용자 채택
**옵션 B** - 스마트 포맷팅

**이유**:
- 리스트: 첫 항목 + 개수
- 스칼라: 전체 값
- 가독성 + 정보량 최적화

### 반영 내용
- **상태**: ✅ 반영 완료
- **파일**: `backend/src/services/metric_engine.py`
- **라인**: 258-271 (포맷팅), 431-473 (로그 정리)

**Before (6줄)**:
```
[priceEodOHLC] Dict response_key processing: ...
[priceEodOHLC] First record keys: ...
[priceEodOHLC] First record sample: ...
[priceEodOHLC] Extracted 1082 dicts from 1082 records
[priceEodOHLC] First result: {'low': 15.48, ...}
[MetricEngine] ✓ priceEodOHLC = [{'low': 15.48, ..., 'clo (잘림!)
```

**After (1줄)**:
```
[MetricEngine] ✓ priceEodOHLC = [{'low': 15.48, 'high': 16.37, 'open': 15.65, 'close': 16.2}, ...] (1082 items) (source: api_field)
```

**개선 효과**:
- ✅ 로그 노이즈 83% 감소 (6줄 → 1줄)
- ✅ `close` 값 완전 표시
- ✅ 총 개수 표시
- ✅ 가독성 향상

### 교훈
- **스마트 포맷팅**: 데이터 타입별 최적 표시
- **로그 정리**: 필수 정보만 남기기
- **안전장치**: 150자 제한으로 극단적 케이스 방어

---

*추가일: 2025-12-25*
*이 내용은 `2_FLOW.md`의 끝에 추가되어야 합니다.*

