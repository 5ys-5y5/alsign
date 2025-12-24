# 📊 AlSign 이슈 흐름도

> 이 문서는 각 이슈의 현상/원인/LLM제공 선택지/사용자 채택/반영 내용을 체계적으로 기록합니다.
> 상세한 코드는 `3_DETAIL.md#I-##`에서 확인할 수 있습니다.
>
> **ID 체계**: 모든 문서에서 동일한 `I-##` ID를 사용합니다.

---

## I-01: consensusSignal 설정 불일치

### 현상
	config_lv2_metric 테이블의 consensusSignal 메트릭이 실제 구현과 불일치함.
	
	- **config 설정**: expression = `buildConsensusSignal(consensusWithPrev)`
	- **실제 구현**: `calculate_qualitative_metrics()`에서 하드코딩으로 처리
	- **문제**: `consensusWithPrev` 메트릭 존재하지 않음, `buildConsensusSignal()` 함수 미구현

### 원인
	1. 설정과 구현의 불일치 - config는 expression 방식, 실제는 하드코딩
	2. 존재하지 않는 의존성 - consensusWithPrev 메트릭 없음
	3. 미구현 함수 - buildConsensusSignal() 없음

### LLM 제공 선택지
	| 옵션 | 설명 |
	|------|------|
	| A | expression을 NULL로 설정하고 하드코딩 방식 명시 |
	| B | config_lv2_metric에서 삭제 |
	| C | evt_consensus 필드를 개별 메트릭으로 정의 후 aggregation 조합 |

### 사용자 채택
	**옵션 C** → **aggregation 타입 사용 방식**으로 구체화
	
	**이유**: 완전한 동적 처리, 하드코딩 완전 제거, 재사용성 및 확장성

### 반영 내용
	- **상태**: ✅ 반영 완료
	- **SQL 반영**: ✅ expression=NULL, source='aggregation', aggregation_kind='leadPairFromList' → [상세: I-01-A]
	- **Python 반영**: ✅ _lead_pair_from_list() 메서드 구현 완료 → [상세: I-01-B]
	- **테스트**: ✅ test_lead_pair_from_list.py 통과
	- **참조**: `backend/src/services/metric_engine.py` 라인 520-1023

---

## I-02: priceEodOHLC dict response_key

### 현상
	priceEodOHLC_dict_response_key.md에서 API 응답 구조를 잘못 가정함.
	
	- **잘못된 가정**: 응답이 `{symbol, historical}` 구조
	- **실제 API**: `/stable/historical-price-eod/full`은 배열 직접 반환

### 원인
	1. 하드코딩된 API URL 사용 - config_lv1_api_list 미확인
	2. 구버전 API 참조 - `/api/v3/historical-price-full`

### LLM 제공 선택지
	| 옵션 | 설명 |
	|------|------|
	| A | response_path 설정 추가 (잘못된 접근) |
	| B | 4개 메트릭으로 분리 (잘못된 접근) |
	| C | close만 사용 (잘못된 접근) |
	| **실제** | **조치 불필요** - dict response_key 이미 정상 작동 |

### 사용자 채택
	**조치 불필요** - API 응답이 배열을 직접 반환하므로 response_path 설정 불필요
	
	**교훈**: 항상 config_lv1_api_list 테이블의 api 컬럼 확인

### 반영 내용
	- **상태**: ✅ 완료 (조치 불필요 확인)
	- **참조**: MetricCalculationEngine이 dict response_key 지원 확인됨 → [상세: I-02]

---

## I-03: targetMedian & consensusSummary 구현

### 현상
	지침(1_guideline(function).ini:851-890)에서 value_qualitative에 요구하는 항목 미구현:
	
	```json
	{
	  "targetMedian": 0,
	  "consensusSummary": { "targetLow", "targetHigh", "targetMedian", "targetConsensus" },
	  "consensusSignal": {...}
	}
	```

### 원인
	1. 지침 미충족 - value_qualitative에 항목 미포함
	2. 하드코딩 미구현 - calculate_qualitative_metrics()에서 처리 안함

### LLM 제공 선택지
	| 옵션 | 설명 |
	|------|------|
	| A | 하드코딩으로 구현 (fmp-price-target-consensus API 호출) |
	| B | config_lv2_metric에 개별 필드 메트릭 추가 후 동적 처리 |
	| C | consensusSummary 유지 + 하드코딩 보완 (절충안) |

### 사용자 채택
	**옵션 C (절충안)** - consensusSummary는 config에 유지, Python에서 MetricCalculationEngine 사용
	
	**핵심 요구사항**:
		- 이미 있는 값 최대한 활용
		- 최소한의 API 호출로 값 채우기 (절대 준수)

### 반영 내용
	- **상태**: ✅ 반영 완료
	- **Python 반영**: calculate_qualitative_metrics() 수정 → [상세: I-03]
		- MetricCalculationEngine으로 consensusSummary 계산
		- consensusSummary dict에서 targetMedian 추출
		- value_qualitative에 세 항목 모두 포함
	- **참조**: `backend/src/services/valuation_service.py` 라인 578-735

---

## I-04: 짧은 이름 메트릭 사용

### 현상
	일부 메트릭이 긴 이름으로 정의됨:
	
	- `researchAndDevelopmentExpenses` (rnd 대신)
	- `totalStockholdersEquity` (totalEquity 대신)
	- `otherNonCurrentLiabilities` (otherNCL 대신)

### 원인
	API 응답 필드명을 그대로 사용하여 메트릭 이름이 길어짐

### LLM 제공 선택지
	| 옵션 | 설명 |
	|------|------|
	| A | 짧은 이름 메트릭 추가 |
	| B | 현재 상태 유지 |

### 사용자 채택
	**옵션 B** - 테이블에 정의된 명명으로 통일하여 사용
	
	**이유**: 일관성 유지, API 필드명과 직접 매핑되어 명확함

### 반영 내용
	- **상태**: ⏸️ 보류 (현재 상태 유지)
	- **조치**: 없음

---

## I-05: consensus 관련 메트릭 추가

### 현상
	다음 필드들이 config_lv2_metric에 존재하지 않음:
	
	- consensusAnalystName, consensusAnalystCompany, consensusPriceTarget 등 8개

### 원인
	evt_consensus 테이블을 직접 사용하므로 별도 정의하지 않음

### LLM 제공 선택지
	| 옵션 | 설명 |
	|------|------|
	| A | 개별 필드 메트릭 추가 |
	| B | 추가하지 않음 |
	| C | fmp-price-target API 활용한 메트릭 추가 |

### 사용자 채택
	**옵션 C** - fmp-price-target API 활용한 consensus 메트릭 추가
	
	**핵심 요구사항**: 최소한의 API 호출로 값 채우기

### 반영 내용
	- **상태**: 🔄 부분 반영
	- **SQL 반영**: ✅ consensus 메트릭 추가 → [상세: I-05]
	- **실행 상태**: ❌ SQL 실행 대기
	- **참조**: `backend/scripts/apply_issue_docs_changes.sql` 라인 74-89

---

## I-06: consensusWithPrev

### 현상
	consensusWithPrev 메트릭이 config_lv2_metric에 존재하지 않음.
	consensusSignal의 expression이 이를 참조하나 실제로는 사용되지 않음.

### 원인
	I-01에서 consensusSignal이 하드코딩으로 처리되어 expression이 사용 안됨

### LLM 제공 선택지
	| 옵션 | 설명 |
	|------|------|
	| A | consensusWithPrev 추가 |
	| B | 추가하지 않음 |

### 사용자 채택
	**조치 불필요** - I-01의 개선안 적용으로 완전히 해결됨
	
	**이유**: expression=NULL 설정으로 consensusWithPrev 의존성 제거됨

### 반영 내용
	- **상태**: ✅ 완료 (I-01에서 해결)
	- **참조**: `backend/scripts/apply_issue_docs_changes.sql` 라인 93-95

---

## I-07: source_id 파라미터 누락

### 현상
	calculate_qualitative_metrics()가 source_id를 받지 않아 같은 날짜에 여러 analyst가 있으면 잘못된 행 선택 가능

### 원인
	1. source_id 파라미터 미사용
	2. select_consensus_data()가 ticker와 event_date만으로 조회

### LLM 제공 선택지
	직접 수정 제안 (선택지 없음)

### 사용자 채택
	**수정 적용**

### 반영 내용
	- **상태**: ✅ 반영 완료
	- **Python 반영**: → [상세: I-07]
		- calculate_qualitative_metrics()에 source_id 파라미터 추가
		- select_consensus_data()에 source_id 파라미터 추가
		- SQL WHERE절에 `id = $source_id` 조건 추가
	- **참조**: `backend/src/services/valuation_service.py` 라인 578-584

---

## I-08: 시간적 유효성 문제 (Temporal Validity)

### 현상
	calculate_quantitative_metrics()가 limit=4로 항상 최근 4개 분기만 가져와 과거 event_date에 잘못된 데이터 사용

### 원인
	limit=4 고정으로 과거 이벤트 처리 시 미래 데이터 사용

### LLM 제공 선택지
	직접 수정 제안 (선택지 없음)

### 사용자 채택
	**수정 적용**

### 반영 내용
	- **상태**: ✅ 반영 완료
	- **Python 반영**: → [상세: I-08]
		- limit=100으로 변경하여 충분한 과거 데이터 조회
		- event_date 기준 필터링 로직 추가
		- _meta.date_range, calcType, count, event_date 기록
		- 데이터 없을 시 'no_valid_data' 에러 반환
	- **참조**: `backend/src/services/valuation_service.py` 라인 468-504

---

## I-09: Topological Sort 순서 오류

### 현상
	메트릭 계산 엔진이 api_field 메트릭을 마지막에 계산하여 의존 메트릭들이 "not defined" 오류

### 원인
	in-degree 계산이 반대로 되어 의존 메트릭이 의존받는 메트릭보다 먼저 계산됨

### LLM 제공 선택지
	직접 수정 제안 (선택지 없음)

### 사용자 채택
	**수정 적용**

### 반영 내용
	- **상태**: ✅ 반영 완료
	- **Python 반영**: → [상세: I-09]
		- in-degree = "이 메트릭이 의존하는 메트릭 개수"로 변경
		- 역방향 그래프 구축 로직 추가
		- 의존성 없는 메트릭(api_field)부터 시작하도록 큐 초기화
	- **참조**: `backend/src/services/metric_engine.py` 라인 121-192

---

## I-10: priceEodOHLC_dateRange 정책 미사용

### 현상
	OHLC API 호출 시 fillPriceTrend_dateRange 정책을 재사용하여 별도 정책 미적용

### 원인
	priceEodOHLC_dateRange 정책을 별도로 조회하지 않음

### LLM 제공 선택지
	직접 수정 제안 (선택지 없음)

### 사용자 채택
	**수정 필요** (미반영)

### 반영 내용
	- **상태**: ❌ 미반영
	- **필요 작업**: → [상세: I-10]
		- get_ohlc_date_range_policy() 함수 구현
		- priceEodOHLC_dateRange 정책 별도 조회
		- fromDate/toDate 계산 로직 수정

---

## I-11: internal(qual) 메트릭 동적 사용 미구현

### 현상
	POST /fillAnalyst에서 하드코딩된 calculate_statistics() 함수 사용

### 원인
	DB에서 internal(qual) 메트릭 정의를 읽지 않음

### LLM 제공 선택지
	직접 수정 제안 (선택지 없음)

### 사용자 채택
	**수정 적용**

### 반영 내용
	- **상태**: ✅ 반영 완료
	- **Python 반영**: → [상세: I-11]
		- select_internal_qual_metrics() 함수 구현 (metrics.py:334-378)
		- calculate_statistics_from_db_metrics() 함수 구현 (analyst_service.py:15-114)
		- DB 메트릭 로드 로직 (analyst_service.py:181)
		- DB 기반 통계 계산 호출 (analyst_service.py:339)
	- **DB 반영**: → [상세: I-11]
		- 7개 internal(qual) 메트릭 존재 (returnIQRByDayOffset 포함)
		- domain='internal(qual)', base_metric_id='priceTrendReturnSeries'
	- **참조**: `backend/src/services/analyst_service.py`, `backend/src/database/queries/metrics.py`

---

## 요약 테이블

| ID | 이슈 | 상태 | 사용자 선택 | 상세도 |
|----|------|------|------------|--------|
| I-01 | consensusSignal 설정 불일치 | ✅ | aggregation 방식 | I-01 |
| I-02 | priceEodOHLC dict response_key | ✅ | 조치 불필요 | I-02 |
| I-03 | targetMedian & consensusSummary | ✅ | 절충안(옵션C) | I-03 |
| I-04 | 짧은 이름 메트릭 | ⏸️ | 현재 상태 유지 | - |
| I-05 | consensus 메트릭 추가 | 🔄 | fmp-price-target 활용 | I-05 |
| I-06 | consensusWithPrev | ✅ | 조치 불필요 | - |
| I-07 | source_id 파라미터 | ✅ | 수정 적용 | I-07 |
| I-08 | 시간적 유효성 | ✅ | 수정 적용 | I-08 |
| I-09 | Topological Sort | ✅ | 수정 적용 | I-09 |
| I-10 | priceEodOHLC_dateRange 정책 | ❌ | 수정 필요 | I-10 |
| I-11 | internal(qual) 메트릭 | ✅ | 수정 적용 | I-11 |

---

## I-12: 동적 계산 코드 실행 실패

### 현상
	POST /backfillEventsTable 실행 중 동적 계산 코드가 syntax 에러로 실패함.
	
	```
	[MetricEngine] Dynamic calculation execution failed: invalid syntax (<string>, line 2)
	[MetricEngine] Dynamic calculation failed for yoyFromQuarter, falling back to hardcoded
	```
	
	- **영향 범위**: yoyFromQuarter, qoqFromQuarter, lastFromQuarter, avgFromQuarter 등
	- **현재 상태**: 하드코딩 함수로 자동 폴백되어 **실제 계산은 정상 작동**

### 원인
	1. `config_lv2_metric_transform.calculation` 컬럼의 Python 코드가 `eval()` 실행 시 syntax 에러
	2. 코드 첫 줄의 공백이나 포맷 문제로 인한 파싱 실패 가능성
	3. `seed_calculation_codes.sql` 스크립트의 `$$` 구분자 내 코드 포맷 이슈

### LLM 제공 선택지
	| 옵션 | 설명 | 우선순위 |
	|------|------|----------|
	| A | calculation 컬럼 코드 재작성 및 테스트 | 낮음 |
	| B | 하드코딩 함수 유지 (현재 상태) | 높음 (권장) |
	| C | calculation 컬럼 NULL 처리 후 하드코딩만 사용 | 중간 |

### 사용자 채택
	**옵션 B 채택**: calculation 코드를 single expression으로 재작성
	
	**이유**: eval()은 single expression만 지원하므로 코드 구조 단순화 필요

### 반영 내용
	- **상태**: ✅ 반영 완료
	- **SQL 스크립트**: `backend/scripts/fix_calculation_single_expression.sql`
	- **수정 항목**: avgFromQuarter, ttmFromQuarterSumOrScaled, lastFromQuarter, qoqFromQuarter, yoyFromQuarter
	- **변경 내용**: multiple statements → single expression (lambda 활용)
	- **참조**: [상세: I-12-C]

---

## I-13: priceEodOHLC 데이터 추출 실패

### 현상
	POST /backfillEventsTable 실행 중 OHLC 데이터 추출 실패.
	
	```
	[calculate_quantitative_metrics] Filtered fmp-historical-price-eod-full: 1176 -> 0 records
	[priceEodOHLC] Extracted 0 dicts from 39 records
	[MetricEngine] ✗ priceEodOHLC = None
	```
	
	- **테스트 대상**: RGTI 티커 (2021-01-31, 2021-06-16 이벤트)
	- **API 응답**: 1176개 historical 데이터 존재
	- **추출 결과**: 0개 (필드 매핑 실패)

### 원인
	1. **파라미터 누락**: `calculate_quantitative_metrics()`에서 `fmp-historical-price-eod-full` API 호출 시 `fromDate`, `toDate` 파라미터를 전달하지 않음
	2. **URL 템플릿 미치환**: `{fromDate}`, `{toDate}` placeholder가 치환되지 않아 API가 전체 데이터를 반환하지 못함
	3. **날짜 필터링 실패**: 파라미터 없이 호출하면 API가 최근 데이터만 반환하거나 에러 발생
	4. **FMP API 검증**: 실제 API 응답 필드는 `low`, `high`, `open`, `close`로 정확함 ([참조](https://financialmodelingprep.com/stable/historical-price-eod/full?symbol=RGTI&from=2025-12-11&to=2025-12-12&apikey=...))

### LLM 제공 선택지
	| 옵션 | 설명 | 작업량 |
	|------|------|--------|
	| A | valuation_service.py에서 historical API 호출 시 fromDate/toDate 파라미터 추가 | 낮음 |
	| B | 전체 서비스에서 API 파라미터 누락 여부 점검 | 중간 |
	| C | API 파라미터 검증 로직 추가 (필수 파라미터 체크) | 높음 |

### 사용자 채택
	**옵션 A + B 채택**: 파라미터 추가 및 전체 점검
	
	**이유**: 
	- FMP API 실제 응답 확인 결과 필드명은 정확함
	- 문제는 API 호출 시 필수 파라미터(`fromDate`, `toDate`) 누락
	- 전체 서비스에서 동일한 문제가 있는지 점검 필요

### 반영 내용
	- **상태**: ✅ 반영 완료
	- **Python 수정**: `backend/src/services/valuation_service.py:431-456`
	- **변경 내용**: 
		- historical-price API 호출 시 `fromDate`, `toDate` 파라미터 추가
		- `fromDate`: '2000-01-01' (충분한 과거 데이터)
		- `toDate`: event_date (이벤트 날짜까지)
	- **전체 점검**: 모든 `call_api()` 호출 검증 완료 (11개 위치)
	- **참조**: [상세: I-13-F]

---

## I-14: fmp-aftermarket-trade API 401 오류

### 현상
	POST /backfillEventsTable 실행 중 aftermarket API 호출 실패.
	
	```
	[API Error] fmp-aftermarket-trade -> HTTPStatusError: Client error '401 Unauthorized'
	https://financialmodelingprep.com/stable/aftermarket-trade?symbol=RGTI?apikey=...
	```
	
	- **영향**: `priceAfter` 메트릭만 NULL로 처리됨
	- **URL 이슈**: `?symbol=RGTI?apikey=...` (이중 `?` 문자)

### 원인
	1. **URL 템플릿 오류**: `config_lv1_api_list.endpoint`에 이미 `?`가 포함되어 있을 가능성
	2. **API 권한 문제**: FMP 플랜이 aftermarket 데이터 접근 권한 없음
	3. **엔드포인트 변경**: FMP API가 해당 엔드포인트를 deprecated 했을 가능성

### LLM 제공 선택지
	| 옵션 | 설명 | 우선순위 |
	|------|------|----------|
	| A | DB에서 endpoint URL 수정 (이중 `?` 제거) | 높음 |
	| B | 메트릭을 optional로 처리 (실패해도 무시) | 중간 |
	| C | 해당 API 비활성화 (is_active=false) | 낮음 |
	| D | FMP 플랜 업그레이드 확인 | 낮음 |

### 사용자 채택
	**조치 불필요**: FMP 서비스의 일시적 문제로 판단
	
	**이유**: priceAfter 메트릭의 영향 범위가 제한적이며, 다른 메트릭들은 정상 작동

### 반영 내용
	- **상태**: ⏸️ 보류 (FMP 일시적 문제)
	- **조치**: 없음
	- **현황**: priceAfter 메트릭만 영향, 다른 메트릭들은 정상 작동

---

## I-15: event_date_obj 변수 순서 오류

### 현상
	POST /backfillEventsTable 실행 시 치명적 에러 발생:
	```
	[calculate_quantitative_metrics] Failed to fetch fmp-historical-price-eod-full: 
	local variable 'event_date_obj' referenced before assignment
	```

### 원인
	**변수 정의 순서 오류**:
	- 444라인: `params['toDate'] = event_date_obj.strftime('%Y-%m-%d')` 사용
	- 471라인: `event_date_obj = datetime.fromisoformat(...).date()` 정의
	- **문제**: 정의되기 전에 사용하려 함

### LLM 제공 선택지
	| 옵션 | 설명 | 작업량 |
	|------|------|--------|
	| A | event_date_obj 변환 로직을 API 호출 전으로 이동 | 낮음 |
	| B | API 호출 시점에 inline으로 변환 | 중간 |

### 사용자 채택
	**옵션 A 채택**: 변환 로직 이동
	
	**이유**: 
	- 코드 가독성 향상
	- event_date_obj를 여러 곳에서 재사용 가능
	- 디버깅 용이

### 반영 내용
	- **상태**: ✅ 반영 완료
	- **Python 수정**: `backend/src/services/valuation_service.py:425-438`
	- **변경 내용**: 
		```python
		# event_date_obj를 API 호출 전에 먼저 변환 (MUST be done before API calls)
		from datetime import datetime
		if isinstance(event_date, str):
		    event_date_obj = datetime.fromisoformat(...).date()
		# ...
		# 이제 API 호출 시 안전하게 사용 가능
		params['toDate'] = event_date_obj.strftime('%Y-%m-%d')
		```
	- **참조**: [상세: I-15-A]

---

## I-16: 메트릭 실패 디버깅 로그 부재

### 현상
	메트릭 계산 실패 시 이유를 알 수 없음:
	```
	[MetricEngine] ✗ priceEodOHLC = None (source: api_field)
	[MetricEngine] ✗ apicYoY = None (source: aggregation)
	[MetricEngine] ✗ revenueQoQ = None (source: aggregation)
	```
	
	**문제**: 왜 실패했는지 알 수 없어 디버깅 어려움

### 원인
	1. **로그 정보 부족**: 실패 이유가 로그에 포함되지 않음
	2. **디버깅 비효율**: 대량의 로그를 제공해야 문제 파악 가능
	3. **경제성 문제**: 특정 메트릭만 확인하려 해도 전체 로그 필요

### LLM 제공 선택지
	| 옵션 | 설명 | 작업량 |
	|------|------|--------|
	| A | _calculate_metric_with_reason() 메서드 추가 | 중간 |
	| B | 각 calculator 함수에서 개별적으로 이유 반환 | 높음 |
	| C | 로그 레벨을 DEBUG로 낮춰 상세 정보 출력 | 낮음 |

### 사용자 채택
	**옵션 A 채택**: 중앙 집중식 이유 추적
	
	**이유**: 
	- 모든 source 타입(api_field, aggregation, expression)에서 일관된 처리
	- 기존 코드 최소 변경
	- 실패 이유를 체계적으로 분류 가능

### 반영 내용
	- **상태**: ✅ 반영 완료
	- **Python 수정**: `backend/src/services/metric_engine.py:241-326`
	- **변경 내용**:
		- `_calculate_metric_with_reason()` 메서드 추가
		- 실패 이유 분류:
			- **api_field**: Missing api_list_id, No data from API, Field extraction failed
			- **aggregation**: Missing base_metric, Base metric is None, Transform returned None
			- **expression**: Missing dependencies, Expression evaluation returned None
		- 로그 출력 형식: `✗ metricName = None (source: ...) | reason: ...`
	- **예시 출력**:
		```
		[MetricEngine] ✗ priceEodOHLC = None (source: api_field) | reason: No data from API 'fmp-historical-price-eod-full'
		[MetricEngine] ✗ revenueQoQ = None (source: aggregation) | reason: Transform 'qoqFromQuarter' returned None
		[MetricEngine] ✗ sharesYoY = None (source: aggregation) | reason: Missing dependencies: weightedAverageShsOut
		```
	- **참조**: [상세: I-16-A]

---

## I-17: 로그 형식 N/A 과다 출력

### 현상
	로그 출력에 불필요한 N/A 값이 과다하게 표시됨:
	```
	[N/A | N/A] | elapsed=0ms | progress=N/A | eta=0ms | rate=N/A | batch=N/A | counters=N/A | warn=[] | [API Response] fmp-aftermarket-trade -> HTTP 200
	```
	
	**문제**: 
	- 가독성 저하
	- 1_guideline(function).ini의 로그 양식 미준수
	- 세부 로그에 불필요한 구조화된 포맷 적용

### 원인
	1. **로그 포맷터 설계 문제**: 모든 로그에 구조화된 포맷 강제 적용
	2. **extra 파라미터 부재**: API 호출, 메트릭 계산 등 세부 로그는 `extra` 없음
	3. **지침 미준수**: 주요 단계만 구조화된 로그 사용해야 하는데 전체 적용

### LLM 제공 선택지
	| 옵션 | 설명 | 작업량 |
	|------|------|--------|
	| A | 구조화된 데이터 없으면 단순 포맷 사용 | 낮음 |
	| B | 모든 로그에 extra 파라미터 추가 | 높음 |
	| C | 별도의 formatter 클래스 분리 | 중간 |

### 사용자 채택
	**옵션 A 채택**: 조건부 포맷 적용
	
	**이유**: 
	- 1_guideline(function).ini 지침 준수
	- 세부 로그는 단순 포맷으로 가독성 확보
	- 주요 단계만 구조화된 로그로 진행률/성능 추적
	- 최소 코드 변경

### 반영 내용
	- **상태**: ✅ 반영 완료
	- **Python 수정**: `backend/src/services/utils/logging_utils.py:15-91`
	- **변경 내용**:
		```python
		# 구조화된 데이터가 없으면 단순 포맷 사용
		has_structured_data = hasattr(record, 'endpoint') and record.endpoint != 'N/A'
		if not has_structured_data:
		    message = record.getMessage()
		    return message  # N/A 없이 깔끔하게 출력
		```
	- **출력 예시**:
		- **단순 로그** (세부 정보):
			```
			[API Call] fmp-income-statement -> https://...
			[API Response] fmp-income-statement -> HTTP 200
			[MetricEngine] ✓ marketCap = 8029534478.0 (source: api_field)
			```
		- **구조화된 로그** (주요 단계):
			```
			[POST /backfillEventsTable | process_events] elapsed=5000ms | progress=10/30(33%) | eta=10000ms | ... | Processing events
			```
	- **문서**: `backend/LOGGING_GUIDE.md` 작성
	- **참조**: [상세: I-17-A]

---

## 요약 테이블 (업데이트)

| ID | 이슈 | 상태 | 채택 방안 | 상세 |
|----|------|------|-----------|------|
| I-01 | consensusSignal 설정 불일치 | ✅ | aggregation 방식 | I-01 |
| I-02 | priceEodOHLC dict response_key | ✅ | 조치 불필요 | I-02 |
| I-03 | targetMedian & consensusSummary | ✅ | 절충안(옵션C) | I-03 |
| I-04 | 짧은 이름 메트릭 | ⏸️ | 현재 상태 유지 | - |
| I-05 | consensus 메트릭 추가 | ✅ | fmp-price-target 활용 | I-05 |
| I-06 | consensusWithPrev | ✅ | 조치 불필요 | - |
| I-07 | source_id 파라미터 | ✅ | 수정 적용 | I-07 |
| I-08 | 시간적 유효성 | ✅ | 수정 적용 | I-08 |
| I-09 | Topological Sort | ✅ | 수정 적용 | I-09 |
| I-10 | priceEodOHLC_dateRange 정책 | ✅ | 수정 적용 | I-10 |
| I-11 | internal(qual) 메트릭 | ✅ | 수정 적용 | I-11 |
| **I-12** | **동적 계산 코드 실행 실패** | **✅** | **옵션 B (single expression)** | **I-12** |
| **I-13** | **priceEodOHLC 데이터 추출** | **✅** | **옵션 A+B (파라미터 추가)** | **I-13** |
| **I-14** | **aftermarket API 401** | **⏸️** | **FMP 일시적 문제** | **I-14** |

---

*마지막 업데이트: 2025-12-24 (런타임 이슈 추가)*
