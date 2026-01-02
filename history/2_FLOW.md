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
| **I-15** | **event_date_obj 변수 순서** | **✅** | **옵션 A (변환 로직 이동)** | **I-15** |
| **I-16** | **메트릭 실패 디버깅 로그 부재** | **✅** | **옵션 A (중앙 집중식)** | **I-16** |
| **I-17** | **로그 형식 N/A 과다** | **✅** | **옵션 A (조건부 포맷)** | **I-17** |
| **I-18** | **priceEodOHLC Schema Array** | **✅** | **옵션 B (전체 검증)** | **I-18** |
| **I-19** | **메트릭 로그 Truncation** | **✅** | **옵션 B (스마트 포맷)** | **I-19** |
| **I-20** | **backfillEventsTable 성능** | **✅** | **옵션 D (복합 전략)** | **I-20** |

---

## I-18: priceEodOHLC Schema Array Type 문제

> **발견**: 2025-12-25 10:00 | **해결**: 2025-12-25 11:30

### 현상
	POST /backfillEventsTable 실행 시 에러:
	```
	[MetricEngine] Failed to calculate priceEodOHLC: unhashable type: 'list'
	```
	
	에러 위치: metric_engine.py:74 - `api_ids.add(api_list_id)`

### 원인
	1. DB 타입 오류: config_lv1_api_list.schema가 array [{}]로 저장됨
	2. Python 타입 제약: set()에 list를 추가할 수 없음 (unhashable)
	3. 일관성 문제: 19개 API 중 1개만 array type

### LLM 제공 선택지
	| 옵션 | 설명 |
	|------|------|
	| A | 단일 API만 수정 |
	| B | 전체 API 검증 + 수정 (권장) |

### 사용자 채택
	**옵션 B** - 전체 API 검증 후 일괄 수정

### 반영 내용
	- **상태**: ✅ 반영 완료
	- **진단 스크립트**: diagnose_priceEodOHLC_issue.sql
	- **수정 스크립트**: fix_priceEodOHLC_array_types.sql
	- **검증 스크립트**: verify_all_api_schemas.sql
	- **통합 실행**: EXECUTE_FIX_SEQUENCE.sql
	- **참조**: → [상세: I-18]

---

## I-19: 메트릭 로그 Truncation 문제

> **발견**: 2025-12-25 12:00 | **해결**: 2025-12-25 13:00

### 현상
	메트릭 로그가 50자로 잘려서 중요한 정보 누락:
	```
	[MetricEngine] ✓ priceEodOHLC = [{'low': 15.48, 'high': 16.37, 'open': 15.65, 'clo
	                                                                              ^^^^ 잘림!
	```

### 원인
	1. 하드코딩된 길이: str(value)[:50]
	2. 단순 문자열 변환: 리스트/스칼라 구분 없이 동일 처리
	3. 과도한 디버깅: priceEodOHLC 전용 warning 로그 5개

### LLM 제공 선택지
	| 옵션 | 설명 |
	|------|------|
	| A | 길이 증가 (50→100자) |
	| B | 스마트 포맷팅 (권장) |
	| C | 로그 레벨 분리 |

### 사용자 채택
	**옵션 B** - 스마트 포맷팅

### 반영 내용
	- **상태**: ✅ 반영 완료
	- **파일**: metric_engine.py:258-271
	- **변경**: 리스트는 첫 항목 + 개수 표시, 150자 제한
	- **효과**: 로그 노이즈 83% 감소 (6줄 → 1줄)
	- **참조**: → [상세: I-19]

---

## I-20: POST /backfillEventsTable 성능 개선 (배치 처리)

> **발견**: 2025-12-25 14:00 | **해결**: 2025-12-25 18:00

### 현상
	POST /backfillEventsTable 엔드포인트가 136,954개 이벤트 처리 필요:
	```
	[backfillEventsTable] Processing event 40/136954: A 2025-08-28 consensus
	```
	
	- 순차 처리 (하나씩)
	- 예상 소요 시간: **76시간**
	- 운영 불가능

### 원인
	1. 순차 처리: for idx, event in enumerate(events)
	2. 중복 API 호출: 같은 ticker → 동일 API 반복 호출
	3. 개별 DB 쓰기: 136,954번의 개별 UPDATE
	4. 병렬 처리 미활용

### LLM 제공 선택지
	| 옵션 | 설명 | 성능 |
	|------|------|------|
	| A | Ticker 배치 + API 캐싱 | 76h → 4-6h |
	| B | 병렬 처리 | 76h → 1.5-2h |
	| C | DB 배치 쓰기 only | 76h → 50-60h |
	| **D** | **복합 전략 (A+B+C)** | **76h → 0.5-1h** |

### 사용자 채택
	**옵션 D** - 복합 전략 (Ticker 배치 + 병렬 + DB 배치)

### 반영 내용
	- **상태**: ✅ 반영 완료
	- **구현 항목**:
		- Ticker 그룹화 (group_events_by_ticker)
		- Ticker 배치 처리 (process_ticker_batch)
		- DB 배치 업데이트 (batch_update_event_valuations)
		- 병렬 처리 (asyncio.Semaphore, TICKER_CONCURRENCY=10)
	- **성능 개선**:
		| 항목 | Before | After | 개선율 |
		|------|--------|-------|--------|
		| API 호출 | 136,954 | ~5,000 | 96% ↓ |
		| DB 쿼리 | 136,954 | ~5,000 | 96% ↓ |
		| **소요 시간** | **76시간** | **0.5-1시간** | **99% ↓** |
	- **참조**: → [상세: I-20]

---

## I-21: priceEodOHLC domain 설정 오류

> **발견**: 2025-12-25 19:00 | **해결**: 2025-12-25 19:30

### 현상
	POST /backfillEventsTable 실행 후 value_quantitative의 momentum 객체에 priceEodOHLC가 포함됨:
	```json
	{
	  "momentum": {
	    "priceEodOHLC": {...},  // ❌ 지침서에 없는 항목
	    "grossMarginTTM": 0.54,
	    ...
	  }
	}
	```
	
	지침서(라인 788-793)에 따르면 momentum에는 grossMarginLast, grossMarginTTM, operatingMarginTTM, rndIntensityTTM만 포함되어야 함.

### 원인
	1. fix_priceeodohlc_domain.py 스크립트가 priceEodOHLC domain을 'internal' → 'quantitative-momentum'으로 잘못 변경
	2. metric_engine.py의 _group_by_domain()이 domain='internal'인 경우만 결과에서 제외

### LLM 제공 선택지
	| 옵션 | 설명 |
	|------|------|
	| A | priceEodOHLC domain을 'internal'로 복원 |
	| B | metric_engine에서 priceEodOHLC 명시적 제외 |

### 사용자 채택
	**옵션 A** - domain을 'internal'로 복원 (원래 설정으로 복구)

### 반영 내용
	- **상태**: ✅ 반영 완료
	- **SQL**: fix_priceEodOHLC_domain_to_internal.sql 생성
	- **삭제**: fix_priceeodohlc_domain.py 삭제 (잘못된 스크립트)
	- **참조**: → [상세: I-21]

---

## I-22: SQL 예약어 "position" 문제

> **발견**: 2025-12-25 19:30 | **해결**: 2025-12-25 19:45

### 현상
	DB 배치 업데이트 실패:
	```
	[Ticker Batch] A: DB batch update failed: syntax error at or near "position"
	```

### 원인
	batch_update_event_valuations() 함수에서 `::position` 타입 캐스팅 사용.
	PostgreSQL에서 `position`은 예약어이므로 따옴표로 감싸야 함.

### LLM 제공 선택지
	| 옵션 | 설명 |
	|------|------|
	| A | ::"position"으로 따옴표 추가 |
	| B | 타입 이름을 변경 (예: position_type) |

### 사용자 채택
	**옵션 A** - 따옴표 추가 (가장 간단한 해결책)

### 반영 내용
	- **상태**: ✅ 반영 완료
	- **파일**: backend/src/database/queries/metrics.py
	- **변경**: `::position` → `::"position"` (4곳)
	- **참조**: → [상세: I-22]

---

## I-23: NULL 값 디버깅 로그 개선

> **발견**: 2025-12-25 20:00 | **해결**: 2025-12-25 20:30

### 현상
	value_quantitative에 NULL 값이 많이 출력되지만 원인을 구별할 수 없음:
	```json
	{
	  "valuation": {
	    "PBR": null,
	    "PER": null,
	    "PSR": null,
	    "evEBITDA": null
	  }
	}
	```
	
	- API 데이터가 없어서 NULL인지?
	- 계산 로직 오류로 NULL인지?

### 원인
	1. 현재 로그가 DEBUG 레벨로만 출력 (기본 INFO에서 안 보임)
	2. 실패 이유가 너무 간략함

### LLM 제공 선택지
	| 옵션 | 설명 |
	|------|------|
	| A | DEBUG → INFO 레벨 변경 |
	| B | 결과에 _errors 필드 추가 |
	| C | 별도 디버그 엔드포인트 |

### 사용자 채택
	**옵션 A** - INFO 레벨로 상세 로그 출력

### 반영 내용
	- **상태**: ✅ 반영 완료
	- **파일**: backend/src/services/metric_engine.py
	- **변경**: 
		- NULL 값 발생 시 INFO 레벨로 출력
		- expression 의존성 상세 추적 (어떤 dependency가 None인지)
	- **출력 형식**: 
		```
		[MetricEngine] ✗ NULL: PER | domain=valuation | reason=Missing deps: netIncomeTTM(=None) | formula: marketCap / netIncomeTTM
		```
	- **참조**: → [상세: I-23]

---

## I-24: price trends 처리 성능 최적화

> **발견**: 2025-12-25 21:00 | **해결**: 2025-12-25 21:30

### 현상
	Phase 5 (price trends 생성)이 매우 느림:
	```
	[POST /backfillEventsTable | process_price_trends] | elapsed=117579ms | progress=10/53(18.9%)
	[POST /backfillEventsTable | process_price_trends] | elapsed=232150ms | progress=20/53(37.7%)
	```
	
	- 이벤트당 ~12초 소요
	- 53개 이벤트 처리에 약 10분 이상 예상

### 원인
	1. `calculate_dayOffset_dates()` - 각 dayOffset마다 개별 DB 조회 (is_trading_day)
	2. 각 이벤트마다 개별 DB UPDATE 실행

### LLM 제공 선택지
	| 옵션 | 설명 | 성능 |
	|------|------|------|
	| A | 거래일 캐싱 | ~50% 개선 |
	| B | 배치 DB UPDATE | ~40% 개선 |
	| **C** | **복합 전략 (A+B)** | **98% 개선** |

### 사용자 채택
	**옵션 C** - 복합 전략 (거래일 캐싱 + 배치 DB 업데이트)

### 반영 내용
	- **상태**: ✅ 반영 완료
	- **구현 항목**:
		- `get_trading_days_in_range()`: 전체 기간 거래일을 1회 DB 조회로 캐시
		- `calculate_dayOffset_dates_cached()`: DB 조회 없이 메모리에서 계산
		- 배치 DB UPDATE: UNNEST 사용하여 모든 이벤트를 1회 UPDATE로 처리
	- **성능 개선**:
		| 항목 | Before | After | 개선율 |
		|------|--------|-------|--------|
		| 거래일 DB 조회 | 이벤트×dayOffset회 | 1회 | **99% ↓** |
		| DB UPDATE | 이벤트당 1회 | 배치 1회 | **99% ↓** |
		| **53개 이벤트** | **~10분** | **~10초** | **98% ↓** |
	- **참조**: → [상세: I-24]

---

## I-25: API별 기준 날짜 불일치 (Temporal Validity Mismatch)

> **발견**: 2025-12-27 | **해결**: 2025-12-27

### 현상 (해결됨)
	POST /backfillEventsTable 실행 시 같은 이벤트에 대해 서로 다른 기준 날짜의 데이터가 혼합되는 문제:
	
	```
	event_date=2021-01-31 이벤트 처리 시 (수정 전):
	- 재무제표 데이터: 2021년 Q4 기준 (정상) ✅
	- marketCap: 2025년 현재 시가총액 (잘못됨) → ✅ historical-market-cap API로 해결
	- consensusSummary: 2025년 현재 컨센서스 (잘못됨) → ✅ I-26에서 NULL 처리로 해결
	```
	
	**해결됨**: marketCap은 historical-market-cap API, consensus는 과거 이벤트 시 NULL 처리.

### 원인
	1. **fmp-quote API**: 현재 시점 스냅샷만 제공 (과거 marketCap 조회 불가)
	2. **fmp-price-target-consensus API**: 현재 시점 컨센서스만 제공
	3. **날짜 필터링 미적용**: 위 API들은 date 필드가 없어 필터링 불가능
	4. **API 한계**: FMP에서 과거 시점의 marketCap, consensus 조회 API 미제공

### LLM 제공 선택지
	| 옵션 | 설명 | 복잡도 | 정확도 |
	|------|------|--------|--------|
	| A | 과거 OHLC 종가 × 발행주식수로 marketCap 계산 | 중간 | 높음 |
	| B | 현재 marketCap 사용하되 _meta에 경고 표시 | 낮음 | 낮음 |
	| C | event_date 기준 데이터가 없으면 NULL 처리 | 낮음 | 높음 |
	| D | 모든 API 결과에 기준 날짜 명시 | 중간 | 중간 |

### 사용자 채택
	**신규 옵션 채택**: FMP `historical-market-capitalization` API 사용
	
	**근거**: 
	- FMP에서 과거 marketCap 조회 API 제공 확인
	- API: `/stable/historical-market-capitalization?symbol={ticker}&from={fromDate}&to={toDate}`
	- **핵심 장점**: `from`/`to` 파라미터로 날짜 범위 특정 가능
	- 응답에 `date` 필드 포함 → event_date 기준 필터링 가능
	- 주말/휴장일 대응: 가장 가까운 거래일 자동 선택 로직 필요

### 반영 내용
	- **상태**: ✅ 반영 완료
	- **구현 완료 사항**:
		1. ✅ `config_lv1_api_list`에 `fmp-historical-market-capitalization` API 추가 (사용자 직접 반영)
		2. ✅ `config_lv2_metric`에서 `marketCap` 메트릭의 `api_list_id` 변경 (사용자 직접 반영)
		3. ✅ `valuation_service.py`에서 historical-market-cap API 호출 시 `from/to` 파라미터 처리
		4. ✅ `metric_engine.py`에서 시계열 marketCap 응답 중 가장 최근 값(첫 번째) 선택
	- **SQL 스크립트**: `backend/scripts/fix_I25_historical_market_cap.sql`
	- **참조**: → [상세: I-25]

---

## I-26: consensus_summary_cache가 event_date 무시

> **발견**: 2025-12-27 | **해결**: 2025-12-27

### 현상
	process_ticker_batch() 함수에서 consensus_summary_cache를 티커당 1회만 fetch:
	
	```python
	# valuation_service.py:115-125
	# Fetch qualitative API (consensus) ONCE for ticker
	try:
	    consensus_data = await fmp_client.call_api('fmp-price-target-consensus', {'ticker': ticker})
	    if consensus_data:
	        consensus_summary_cache = consensus_data[0]  # 현재 시점 데이터
	```
	
	- 같은 티커의 모든 이벤트에 동일한 현재 시점 consensus 값 사용
	- event_date가 2021-01-31이든 2025-12-27이든 동일한 값 적용

### 원인
	1. **API 제약**: fmp-price-target-consensus는 과거 시점 조회 미지원
	2. **캐싱 전략**: 티커당 1회 호출로 성능 최적화 → event_date 무시
	3. **대안 부재**: 과거 시점 컨센서스를 제공하는 API 없음

### LLM 제공 선택지
	| 옵션 | 설명 | 복잡도 | 정확도 |
	|------|------|--------|--------|
	| **A** | **과거 consensus 데이터 없으면 NULL 처리** | **낮음** | **높음** |
	| B | evt_consensus 테이블의 과거 데이터 활용 | 중간 | 높음 |
	| C | 현재 상태 유지 + _meta에 timestamp 명시 | 낮음 | 낮음 |

### 사용자 채택
	**옵션 A** - 과거 이벤트(7일 이전)에는 consensus 값을 NULL로 처리
	
	**이유**: 
	- FMP API가 과거 consensus 데이터를 제공하지 않음
	- 잘못된 데이터(현재 consensus를 과거에 적용)보다 NULL이 정확함
	- `_meta` 필드에 데이터 가용성 정보 명시로 투명성 확보

### 반영 내용
	- **상태**: ✅ 반영 완료
	- **구현 사항**:
		- `calculate_qualitative_metrics_fast()` 함수 수정
		- 과거 이벤트 판단: `event_date < today - 7days`
		- 과거 이벤트: `targetMedian=NULL`, `consensusSummary=NULL`
		- `_meta` 필드 추가: `dataAvailable`, `reason`, `fetchDate`
	- **참조**: → [상세: I-26]

---

## I-27: priceTrend 티커별 1회 호출 확인

> **발견**: 2025-12-27 | **확인 완료**

### 현상
	priceTrend가 티커별로 1회만 OHLC API를 호출하는지 점검 요청.

### 원인
	**점검 결과: 정상 작동 확인**
	
	```python
	# valuation_service.py:1570-1601
	# Fetch OHLC data for all tickers
	ohlc_cache = {}
	async with FMPAPIClient() as fmp_client:
	    for ticker, (fetch_start, fetch_end) in ohlc_ranges.items():  # 티커별 1회
	        ohlc_data = await fmp_client.get_historical_price_eod(
	            ticker, fetch_start.isoformat(), fetch_end.isoformat()
	        )
	        # Index by date for fast lookup
	        ohlc_by_date = {}
	        for record in ohlc_data:
	            ohlc_by_date[record.get('date')] = record
	        ohlc_cache[ticker] = ohlc_by_date  # 캐시 저장
	```
	
	- 티커별로 1회만 API 호출
	- 전체 날짜 범위를 한 번에 조회
	- 이벤트별로는 캐시에서 날짜 기반 조회

### LLM 제공 선택지
	| 옵션 | 설명 |
	|------|------|
	| 확인 완료 | 현재 구현이 최적화되어 있음 |

### 사용자 채택
	**확인 완료** - 추가 조치 불필요

### 반영 내용
	- **상태**: ✅ 확인 완료
	- **조치**: 없음 (정상 작동)
	- **참조**: → [상세: I-27]

---

## I-28: 재무제표 TTM 계산의 시간적 유효성 확인

> **발견**: 2025-12-27 | **확인 완료**

### 현상
	사용자 점검 요청: event_date 기준으로 재무제표 TTM 계산이 올바르게 수행되는지 확인.
	
	**예시 시나리오**:
	- event_date = 2024-12-22
	- TTM 계산에 사용해야 할 분기: 2024-09-28, 2024-06-29, 2024-03-30, 2023-12-30
	- 2024-12-28 분기는 event_date 이후이므로 **제외되어야 함**

### 원인
	**점검 결과: 정상 작동 확인** ✅
	
	**1단계: 날짜 필터링 (valuation_service.py:847-850)**
	```python
	api_data_filtered[api_id] = [
	    r for r in records 
	    if _get_record_date(r) is None or _get_record_date(r) <= event_date_obj
	]
	```
	- `fmp-income-statement` 응답에서 `date <= event_date` 조건으로 필터링
	- 2024-12-28 > 2024-12-22 이므로 **제외됨** ✅
	
	**2단계: netIncome 리스트 추출 (metric_engine.py:501-522)**
	```python
	# API 응답에서 각 레코드의 netIncome 값을 리스트로 추출
	values = []
	for record in api_response:
	    value = record.get(field_key)
	    if value is not None:
	        values.append(self._convert_value(value))
	return values  # [Q1값, Q2값, Q3값, Q4값, ...]
	```
	- 필터링된 응답은 최신순 정렬 유지
	- `netIncome = [14736000000, 21448000000, 23636000000, 33916000000, ...]`
	
	**3단계: TTM 합산 (metric_engine.py:689-722)**
	```python
	def _ttm_sum_or_scaled(self, quarterly_values, params):
	    window = params.get('window', 4)  # 4분기
	    recent_quarters = quarterly_values[:window]  # 최근 4개
	    return sum(recent_quarters)  # 합산
	```
	- 첫 4개 분기 합산: 14736 + 21448 + 23636 + 33916 = **93,736백만**
	
	**검증 예시**:
	```
	event_date = 2024-12-22
	
	fmp-income-statement 원본 (최신순):
	[2025-09-27, 2025-06-28, 2025-03-29, 2024-12-28, 2024-09-28, ...]
	
	필터링 후 (event_date ≤ 2024-12-22):
	[2024-09-28, 2024-06-29, 2024-03-30, 2023-12-30, ...]
	                                                  ↑ 2024-12-28 제외됨
	
	TTM 계산:
	= Q4(2024-09-28) + Q3(2024-06-29) + Q2(2024-03-30) + Q1(2023-12-30)
	= 14,736,000,000 + 21,448,000,000 + 23,636,000,000 + 33,916,000,000
	= 93,736,000,000 ✅
	```

### LLM 제공 선택지
	| 옵션 | 설명 |
	|------|------|
	| 확인 완료 | 현재 구현이 올바르게 작동함 |

### 사용자 채택
	**확인 완료** - 재무제표 TTM 계산은 event_date 기준으로 정확하게 필터링됨

### 반영 내용
	- **상태**: ✅ 확인 완료
	- **조치**: 없음 (정상 작동)
	- **핵심 로직**:
		- `valuation_service.py:847-850`: 날짜 필터링
		- `metric_engine.py:501-522`: 값 추출
		- `metric_engine.py:689-722`: TTM 합산
	- **참조**: → [상세: I-28]

---

## 요약 테이블 (업데이트 - 2025-12-27)

| ID | 이슈 | 상태 | 채택 방안 | 상세 |
|----|------|------|-----------|------|
| I-01 ~ I-24 | (이전 이슈들) | 대부분 ✅ | - | - |
| **I-25** | **API별 기준 날짜 불일치 (marketCap)** | **✅** | **historical-market-cap API** | **I-25** |
| **I-26** | **consensus_summary_cache event_date 무시** | **✅** | **옵션 A: 과거 이벤트 NULL 처리** | **I-26** |
| **I-27** | **priceTrend 티커별 1회 호출** | **✅** | **확인 완료** | **I-27** |
| **I-28** | **재무제표 TTM 계산 시간적 유효성** | **✅** | **확인 완료** | **I-28** |

---

## I-29: evt_consensus 2단계 계산 미실행

> **발견**: 2025-12-30 | **해결**: 미해결

### 현상
	POST /backfillEventsTable 실행 시 consensusSignal의 prev, delta, deltaPct, direction이 항상 null로 출력됨:
	
	```json
	{
	  "consensusSignal": {
	    "last": {
	      "price_target": 20.0,
	      "price_when_posted": 16.77
	    },
	    "prev": null,
	    "delta": null,
	    "deltaPct": null,
	    "direction": null
	  }
	}
	```

### 원인 (DB 데이터 확인)
	**evt_consensus 테이블 확인 결과**: 모든 레코드의 `price_target_prev`, `price_when_posted_prev`, `direction`이 NULL
	
	RGTI 티커의 David Williams / Williams Trading 파티션 예시:
	```
	event_date       | price_target | price_target_prev | direction
	-----------------|--------------|-------------------|----------
	2023-08-11       | 4            | NULL              | NULL      ← 첫 번째라 NULL 정상
	2025-08-13       | 20           | NULL (❌ 4)       | NULL (❌ up)
	2025-10-07       | 50           | NULL (❌ 20)      | NULL (❌ up)
	2025-11-11       | 40           | NULL (❌ 50)      | NULL (❌ down)
	```
	
	- **원인**: GET /sourceData?mode=consensus의 **2단계(변경 감지 및 기록)가 실행되지 않음**
	- 1단계(Raw Upsert)만 완료되어 price_target, price_when_posted만 기록됨
	- 2단계에서 파티션별(ticker, analyst_name, analyst_company)로 prev/direction 계산이 필요
	
	**(참고)** valuation_service.py의 코드는 이미 올바르게 작성되어 있음 (price_when_posted_prev 포함)

### LLM 제공 선택지
	| 옵션 | 설명 | 작업량 |
	|------|------|--------|
	| **A** | **GET /sourceData?mode=consensus 재실행** | **낮음** |
	| B | 별도 2단계 재계산 엔드포인트 추가 | 중간 |

### 사용자 채택
	**옵션 A 채택** - GET /sourceData?mode=consensus 재실행하여 2단계 계산 수행

### 반영 내용
	- **상태**: ✅ 반영됨
	- **구현 내용**:
		- `calc_mode=calculation` 모드 추가: API 호출 없이 2단계 계산만 수행
		- 기존 데이터를 기반으로 price_target_prev, price_when_posted_prev, direction 계산
	- **사용법**:
		```bash
		# 전체 파티션 재계산 (API 호출 없음)
		GET /sourceData?mode=consensus&calc_mode=calculation&calc_scope=all
		
		# 특정 티커만 재계산
		GET /sourceData?mode=consensus&calc_mode=calculation&calc_scope=ticker&tickers=RGTI,AAPL
		```
	- **수정된 파일**: `backend/src/services/source_data_service.py:177-260`

---

## I-30: 메트릭별 원천 날짜 추적 (옵션 B 채택)

> **발견**: 2025-12-30 | **해결**: 2025-12-31 ✅

### 현상
	POST /backfillEventsTable 실행 시 value_quantitative._meta.date_range가 null로 출력됨:
	
	```json
	{
	  "valuation": {
	    "_meta": {
	      "count": 4,
	      "calcType": "TTM_fullQuarter",
	      "date_range": null
	    },
	    "PER": -31.19,
	    "PBR": 9.29
	  }
	}
	```
	
	- **문제**: PER = marketCap / netIncomeTTM 계산 시, marketCap이 어떤 날짜 값인지, netIncomeTTM이 어떤 분기들의 합인지 알 수 없음
	- **필요**: 계산된 값이 올바른 시점의 데이터를 기반으로 하는지 검증 가능해야 함

### 원인
	1. **원천 날짜 미추적**: 메트릭 계산 시 사용된 원천 데이터의 날짜 정보를 수집하지 않음
	2. **API 응답 활용 부족**: fmp-historical-market-capitalization 응답의 date 필드 등을 기록하지 않음
	3. **분기 정보 미기록**: TTM 합산 시 어떤 분기들이 사용되었는지 기록하지 않음

### LLM 제공 선택지
	| 옵션 | 설명 | 작업량 |
	|------|------|--------|
	| A | 도메인별 통합 (간결) | 낮음 |
	| **B** | **메트릭별 상세 _sources** | **높음** |
	| C | 원천 메트릭별 분리 (중간) | 중간 |

### 사용자 채택
	**옵션 B 채택** - 각 메트릭별로 원천 데이터의 날짜 정보를 상세히 기록
	
	**채택된 구조**:
	```json
	{
	  "valuation": {
	    "PER": {
	      "value": -31.19,
	      "_sources": {
	        "marketCap": {
	          "api": "fmp-historical-market-capitalization",
	          "date": "2025-08-13",
	          "value": 8029534478.0
	        },
	        "netIncomeTTM": {
	          "api": "fmp-income-statement",
	          "quarters": ["2024-09-30", "2024-12-31", "2025-03-31", "2025-06-30"],
	          "values": [100000000, 120000000, 110000000, -130000000],
	          "total": -257000000
	        }
	      }
	    },
	    "PBR": {
	      "value": 9.29,
	      "_sources": {
	        "marketCap": {
	          "api": "fmp-historical-market-capitalization",
	          "date": "2025-08-13",
	          "value": 8029534478.0
	        },
	        "equityLatest": {
	          "api": "fmp-balance-sheet",
	          "date": "2025-06-30",
	          "value": 864000000
	        }
	      }
	    }
	  }
	}
	```

### 반영 내용
	- **상태**: ✅ 해결됨 (2025-12-31)
	- **구현 완료**: → [상세: I-30]
		1. **MetricCalculationEngine 수정**: `metric_sources` 딕셔너리 추가
		2. **API 응답 날짜 추출**: `_calculate_api_field_with_source()` 함수 추가
		3. **분기 정보 기록**: `_calculate_aggregation_with_source()` 함수 추가
		4. **출력 구조 변경**: `_group_by_domain()`에서 `_meta.sources`에 메트릭별 소스 정보 포함
	- **참조**: `backend/src/services/metric_engine.py`

---

## I-31: targetSummary 계산 (consensusSummary 대체)

> **발견**: 2025-12-31 | **해결**: 2025-12-31 ✅

### 현상
	POST /backfillEventsTable 실행 시 value_qualitative.consensusSummary가 항상 null 또는 현재 시점 데이터만 반환됨:
	
	```json
	{
	  "_meta": {
	    "reason": "Historical event - FMP API only provides current consensus",
	    "dataAvailable": false
	  },
	  "targetMedian": null,
	  "consensusSummary": null,
	  "consensusSignal": {...}
	}
	```
	
	- **문제**: FMP의 fmp-price-target-consensus API는 현재 시점 데이터만 제공
	- **필요**: 과거 이벤트에 대해서도 해당 시점 기준 consensus 요약 필요

### 원인
	1. **API 한계**: fmp-price-target-consensus API는 현재 시점만 반환, 과거 날짜 지원 안함
	2. **데이터 미활용**: evt_consensus 테이블에 과거 데이터가 있지만 활용하지 않음
	3. **실시간 계산 비효율**: 매 backfill 실행 시 집계 계산하면 성능 저하

### LLM 제공 선택지
	| 옵션 | 설명 | 작업량 |
	|------|------|--------|
	| A | POST /backfillEventsTable에서 실시간 집계 | 낮음 |
	| **B** | **GET /sourceData에서 사전 계산 후 저장** | **중간** |
	| C | 별도 배치 작업으로 계산 | 높음 |

### 사용자 채택
	**옵션 B 채택** - GET /sourceData?mode=consensus에서 Phase 3로 target_summary 계산 및 저장
	
	**이유**:
	- evt_consensus 테이블에 이미 과거 데이터 존재
	- 사전 계산으로 backfill 성능 유지
	- overwrite 옵션으로 재계산 가능

### 반영 내용
	- **상태**: ✅ 해결됨 (2025-12-31)
	- **DB 변경**: evt_consensus 테이블에 target_summary JSONB 컬럼 추가
	- **구현 내용**: → [상세: I-31]
		1. **Phase 3 추가**: GET /sourceData?mode=consensus에서 target_summary 계산
		2. **집계 함수**: calculate_target_summary()로 lastMonth/lastQuarter/lastYear/allTime 집계
		3. **저장**: update_consensus_phase3()로 evt_consensus.target_summary 업데이트
		4. **읽기**: POST /backfillEventsTable에서 evt_consensus.target_summary 조회
	- **overwrite 지원**:
		- overwrite=true: 지정된 scope의 모든 행 재계산
		- overwrite=false: target_summary가 NULL인 행만 계산
	- **참조**: 
		- `backend/src/services/source_data_service.py`
		- `backend/src/database/queries/consensus.py`
		- `backend/src/services/valuation_service.py`

---

---

## I-32: Log 패널 리사이즈 기능

### 현상
	/requests 라우터의 Log 패널 크기가 고정되어 있어 사용자 편의성 저하
	
	- **요구사항**: Cursor의 agent UI처럼 마우스 드래그로 패널 크기 조정
	- **현재 상태**: 하단 패널 400px, 우측 패널 480px 고정

### 원인
	1. 패널 크기가 하드코딩되어 있음
	2. 리사이즈 핸들러 미구현

### LLM 제공 선택지
	| 옵션 | 설명 |
	|------|------|
	| A | CSS resize 속성 사용 (제한적) |
	| **B** | **마우스 이벤트 기반 리사이즈 핸들러 구현** |

### 사용자 채택
	**옵션 B 채택** - 마우스 드래그 리사이즈
	
	**이유**: Cursor UI와 동일한 UX 제공

### 반영 내용
	- **상태**: ✅ 해결됨 (2025-12-31)
	- **구현 내용**: → [상세: I-32]
		1. **리사이즈 핸들**: 하단(상단 가장자리) / 우측(좌측 가장자리)
		2. **크기 제한**: 하단 200~600px, 우측 300~800px
		3. **시각적 피드백**: 호버/드래그 시 파란색 하이라이트
		4. **상태 관리**: panelSize 상태로 동적 크기 관리
	- **참조**: `frontend/src/pages/RequestsPage.jsx`

---

## I-33: 본문 80% 너비 및 가운데 정렬

### 현상
	본문 너비가 페이지마다 다르고, Log 패널 상태에 따라 일관성 없음
	
	- **요구사항**: 모든 라우터에서 본문이 출력 영역의 80% 너비로 가운데 정렬
	- **특별 요구**: /requests에서 패널 접힘/펼침 시에도 80% 유지

### 원인
	1. 각 페이지별로 maxWidth 하드코딩 (1200px, 1400px 등)
	2. 패널 영역을 고려하지 않은 레이아웃

### LLM 제공 선택지
	| 옵션 | 설명 |
	|------|------|
	| A | 전역 CSS 클래스로 통일 |
	| **B** | **각 페이지에 width: 80% 적용 + Wrapper div 패턴** |

### 사용자 채택
	**옵션 B 채택** - 페이지별 width: 80% + Wrapper
	
	**이유**: 패널 위치에 따른 동적 레이아웃 지원

### 반영 내용
	- **상태**: ✅ 해결됨 (2025-12-31)
	- **구현 내용**: → [상세: I-33]
		1. **공통 스타일**: `width: 80%`, `maxWidth: 1400px`, `margin: 0 auto`
		2. **RequestsPage**: Wrapper div로 패널 영역 제외 후 80% 적용
		3. **적용 페이지**: /requests, /setRequests, /control, /conditionGroup, /dashboard
	- **참조**: 
		- `frontend/src/pages/RequestsPage.jsx`
		- `frontend/src/pages/SetRequestsPage.jsx`
		- `frontend/src/pages/ControlPage.jsx`
		- `frontend/src/pages/ConditionGroupPage.jsx`
		- `frontend/src/pages/DashboardPage.jsx`

---

## I-34: /setRequests API 변경 기능 (Schema 기반 검증)

### 현상
	엔드포인트별 사용 API를 변경할 방법이 없고, 변경 시 유효성 검증 불가
	
	- **요구사항**: 각 mode/phase별 config_lv1_api_list ID 변경 가능
	- **검증 요구**: API 호출 없이 config_lv1_api_list.schema로 필수 키 존재 확인
	- **불필요 기능**: API List 탭의 수정/테스트 기능 제거

### 원인
	1. API 매핑이 코드에 하드코딩되어 있음
	2. 변경 시 검증 메커니즘 없음

### LLM 제공 선택지
	| 옵션 | 설명 |
	|------|------|
	| A | API 호출로 실시간 검증 (느림, API 비용) |
	| **B** | **Schema 필드 기반 오프라인 검증** |

### 사용자 채택
	**옵션 B 채택** - Schema 기반 검증
	
	**이유**: 
	- API 호출 없이 즉시 검증
	- API 비용 절감
	- 오프라인 환경에서도 작동

### 반영 내용
	- **상태**: ✅ 해결됨 (2025-12-31)
	- **구현 내용**: → [상세: I-34]
		1. **UI 구조**: 엔드포인트 → 모드/페이즈 → 현재 API + "변경" 버튼
		2. **변경 모달**: 새 API 드롭다운 선택 → Schema 검증 버튼 → 저장 버튼
		3. **검증 로직**: config_lv1_api_list.schema에서 키 추출 → 필수 키 존재 확인
		4. **검증 결과**: 성공 시 저장 가능, 실패 시 누락된 키 표시
		5. **저장**: localStorage에 설정 저장 (백엔드 연동 가능)
	- **참조**: `frontend/src/pages/SetRequestsPage.jsx`

---

## I-35: GET /sourceData 병렬 처리 성능 개선

### 현상
	mode=consensus, mode=earning 호출 시 각 요청이 순차적으로 처리됨
	
	- **mode=consensus**: 티커별로 순차 API 호출 (5000개 티커 → 5000회 순차 호출)
	- **mode=earning**: 날짜 범위별 순차 API 호출 (past=true 시 ~260개 범위)
	- **문제**: 처리 시간이 선형으로 증가, 5000 티커 시 약 83분 소요 예상

### 원인
	1. 순차 처리 방식: `for ticker in ticker_list: await fmp_client.get_...`
	2. 동시성 제어 없음
	3. Rate limit 고려 없이 단순 순차 실행

### LLM 제공 선택지
	| 옵션 | 설명 | Rate Limit 고려 |
	|------|------|-----------------|
	| A | 단순 병렬 (gather 전체) | ❌ 위험 |
	| **B** | **Semaphore 기반 병렬** | **✅ 안전** |
	| C | 배치 단위 순차 | ○ 부분적 |

### 사용자 채택
	**옵션 B 채택** - Semaphore 기반 병렬 처리
	
	**이유**: 
	- Rate limit 안전 (FMP API 분당 300-750 제한 고려)
	- 동시성 수준 조절 가능 (API_CONCURRENCY = 10)
	- POST /backfillEventsTable과 동일한 패턴 적용

### 반영 내용
	- **상태**: ✅ 해결됨 (2025-12-31)
	- **구현 내용**: → [상세: I-35]
		1. **asyncio.Semaphore**: 동시 API 호출 수 제한 (10개)
		2. **asyncio.gather**: 모든 작업 병렬 실행
		3. **진행률 로깅**: 배치별 progress, rate, ETA 출력
		4. **에러 처리**: 개별 실패 시 계속 진행, 실패 카운트 추적
	- **성능 개선**:
		| 항목 | Before | After | 개선율 |
		|------|--------|-------|--------|
		| mode=consensus (5000 티커) | ~83분 | ~8분 | 90% ↓ |
		| mode=earning (past=true) | ~4분 | ~30초 | 87% ↓ |
	- **참조**: `backend/src/services/source_data_service.py`

---

## 요약 테이블 (업데이트 - 2025-12-31)

| ID | 이슈 | 상태 | 채택 방안 | 상세 |
|----|------|------|-----------|------|
| I-01 ~ I-28 | (이전 이슈들) | 대부분 ✅ | - | - |
| **I-29** | **evt_consensus 2단계 계산 미실행** | **✅** | **calc_mode=calculation 모드 추가** | **I-29** |
| **I-30** | **_meta 필드 개선 (date_range → sources)** | **✅** | **옵션 B: 메트릭별 상세 소스 추적** | **I-30** |
| **I-31** | **targetSummary 계산 (consensusSummary 대체)** | **✅** | **Method B: 사전 계산 및 저장** | **I-31** |
| **I-32** | **Log 패널 리사이즈 기능** | **✅** | **마우스 드래그 리사이즈** | **I-32** |
| **I-33** | **본문 80% 너비 및 가운데 정렬** | **✅** | **width: 80% + Wrapper** | **I-33** |
| **I-34** | **/setRequests API 변경 기능** | **✅** | **Schema 기반 검증** | **I-34** |
| **I-35** | **GET /sourceData 병렬 처리** | **✅** | **Semaphore 기반 병렬** | **I-35** |

---

## I-36: Quantitative Position/Disparity 항상 None

> **발견**: 2025-12-31 | **해결**: 2025-12-31 ✅ | **폐기**: 2026-01-02 🔄 DEPRECATED

⚠️ **DEPRECATED**: 이 이슈는 임시 해결책이었으며, **I-41**에서 원본 설계대로 `priceQuantitative` 메트릭을 구현하여 대체되었습니다.

**폐기 이유**:
- 원본 설계는 `priceQuantitative` **메트릭** 사용을 요구했으나, 이 해결책은 `calcFairValue` **파라미터**로 우회
- 메트릭 시스템 아키텍처와 불일치
- I-41에서 근본적으로 해결

---

### 현상 (참고용)
	POST /backfillEventsTable 실행 후 txn_events 테이블의 position_quantitative, disparity_quantitative가 항상 NULL

### 원인 (참고용)
	Quantitative 지표(PER, PBR 등)에서 "적정 주가" 도출 로직 미구현

### LLM 제공 선택지 (참고용)
	| 옵션 | 설명 | 복잡도 |
	|------|------|--------|
	| **A** | **업종 평균 대비 적정가 계산** | **🔴 높음** |
	| B | 역사적 평균 대비 적정가 계산 | 🟡 중간 |
	| C | 의도적 NULL 유지 + 문서화 | 🟢 낮음 |

### 사용자 채택 (참고용)
	**옵션 A 채택** - 업종 평균 PER × EPS로 적정가 계산

	**핵심 결정**:
	- `fmp-stock-peers` API 활용하여 동종 업종 티커 조회
	- symbol(ticker) 값만 사용 (다른 값은 event_date와 무관하므로 제외)
	- `calcFairValue` 파라미터로 선택적 기능 제공

### 반영 내용 (참고용)
	- **상태**: 🔄 DEPRECATED (I-41로 대체)
	- **구현 내용** (I-41에서 재사용됨):
		1. `get_peer_tickers()`: fmp-stock-peers API로 동종 업종 티커 조회
		2. `calculate_sector_average_metrics()`: 동종 업종 평균 PER/PBR 계산
		3. `calculate_fair_value_from_sector()`: 적정가 = 업종 평균 PER × EPS
		4. `calculate_fair_value_for_ticker()`: 통합 함수
		5. ~~`calcFairValue` 파라미터 추가~~ → I-41 배포 후 제거 예정
	- **마이그레이션**: → [I-41: priceQuantitative 메트릭 구현]
	- **참조**: → [상세: I-36 (deprecated)]

---

## I-37: targetMedian 명칭/값 불일치 (평균 vs 중앙값)

> **발견**: 2025-12-31 | **해결**: 2025-12-31 ✅

### 현상
	value_qualitative의 `targetMedian` 값이 실제로는 중앙값(Median)이 아닌 평균값(Average)

### 원인
	- DB 쿼리: `AVG(price_target)` 사용
	- Python: 평균값을 `target_median` 변수에 할당

### LLM 제공 선택지
	| 옵션 | 설명 | 복잡도 |
	|------|------|--------|
	| A | 변수명을 `targetAverage`로 수정 | 🟢 낮음 |
	| **B** | **실제 Median 계산 구현** | **🟡 중간** |

### 사용자 채택
	**옵션 B 채택** - PostgreSQL `PERCENTILE_CONT(0.5)` 함수로 실제 Median 계산

### 반영 내용
	- **상태**: ✅ 해결됨
	- **구현 내용**:
		1. `calculate_target_summary()` SQL에 `PERCENTILE_CONT(0.5)` 추가
		2. 반환 구조에 Median, Avg, Min, Max 모두 포함:
			```python
			{
			    'lastMonthMedianPriceTarget': ...,
			    'lastMonthAvgPriceTarget': ...,
			    'lastQuarterMedianPriceTarget': ...,
			    'lastQuarterAvgPriceTarget': ...,
			    'lastYearMedianPriceTarget': ...,
			    'lastYearAvgPriceTarget': ...,
			    'allTimeMedianPriceTarget': ...,
			    'allTimeAvgPriceTarget': ...,
			    'allTimeMinPriceTarget': ...,
			    'allTimeMaxPriceTarget': ...,
			}
			```
		3. `valuation_service.py`에서 실제 Median 사용 (`allTimeMedianPriceTarget`)
	- **데이터 재계산**: `GET /sourceData?mode=consensus&overwrite=true`
	- **참조**: → [상세: I-37]

---

## I-41: priceQuantitative 메트릭 미구현 (설계 불일치)

> **발견**: 2026-01-02 | **해결**: 2026-01-02 ✅

### 현상
	원본 설계 문서(`prompt/1_guideline(function).ini`:892-897)는 `priceQuantitative` 메트릭 사용을 명시했으나, 실제 구현에는 해당 메트릭이 `config_lv2_metric` 테이블에 존재하지 않음

### 원인
	- 설계 문서와 구현 간 불일치
	- I-36에서 `calcFairValue` 파라미터로 임시 우회
	- 메트릭 시스템 아키텍처를 따르지 않음

### LLM 제공 선택지
	| 옵션 | 설명 | 복잡도 |
	|------|------|--------|
	| **A** | **priceQuantitative 메트릭 구현 (원본 설계 준수)** | **🔴 높음** |
	| B | 설계 문서 업데이트 (현행 유지) | 🟢 낮음 |
	| C | 하이브리드 (메트릭 + fallback) | 🟡 중간 |

### 사용자 채택
	**옵션 A 채택** - 원본 설계대로 priceQuantitative 메트릭 구현

	**핵심 결정**:
	- `config_lv2_metric` 테이블에 메트릭 정의
	- I-36의 calcFairValue 로직을 메트릭 계산에 통합
	- 메트릭 시스템 아키텍처 준수

### 반영 내용
	- **상태**: ✅ 해결됨
	- **구현 내용**:
		1. SQL 스크립트 작성: `backend/scripts/add_priceQuantitative_metric.sql`
		2. 메트릭 정의:
			```sql
			INSERT INTO config_lv2_metric (
			    id: 'priceQuantitative',
			    source: 'custom',
			    domain: 'quantitative-valuation',
			    aggregation_params: {
			        "calculation_method": "sector_average_fair_value",
			        "peer_api": "fmp-stock-peers",
			        "valuation_metrics": ["PER", "PBR"],
			        "max_peers": 10,
			        "outlier_removal": "iqr_1.5"
			    }
			)
			```
		3. 계산 로직 (I-36에서 개발한 함수 재사용):
			- `get_peer_tickers()`: fmp-stock-peers API 호출
			- `calculate_sector_average_metrics()`: 업종 평균 계산
			- `calculate_fair_value_from_sector()`: 적정가 도출
		4. position/disparity 계산:
			```
			position_quantitative = 'long' if priceQuantitative > price else 'short'
			disparity_quantitative = (priceQuantitative / price) - 1
			```
	- **폐기된 이슈**:
		- I-36: calcFairValue 파라미터 방식
		- I-38: calcFairValue 기본값
		- I-40: Peer tickers 로깅
	- **알려진 제한사항**:
		- Peer tickers 미존재 시 NULL (소형주, 특수 섹터)
		- fmp-stock-peers는 현재 peer 목록만 제공
	- **참조**:
		- → [설계 문서: backend/DESIGN_priceQuantitative_metric.md]
		- → [이슈 분석: history/ISSUE_priceQuantitative_MISSING.md]
		- → [상세: I-41]

---

## 요약 테이블 (업데이트 - 2026-01-02 최종)

| ID | 이슈 | 상태 | 채택 방안 | 상세 |
|----|------|------|-----------|------|
| I-01 ~ I-35 | (이전 이슈들) | 대부분 ✅ | - | - |
| **I-36** | **Quantitative Position/Disparity 항상 None** | **🔄 DEPRECATED** | **I-41로 대체됨** | **I-36** |
| **I-37** | **targetMedian 명칭/값 불일치** | **✅** | **옵션 B: PERCENTILE_CONT 사용** | **I-37** |
| **I-38** | **calcFairValue 기본값** | **🔄 DEPRECATED** | **I-41로 대체됨** | **-** |
| **I-39** | **target_summary JSONB 파싱 오류** | **✅** | **JSON parsing 추가** | **I-39** |
| **I-40** | **Peer tickers 로깅** | **🔄 DEPRECATED** | **I-41 제한사항으로 통합** | **-** |
| **I-41** | **priceQuantitative 메트릭 미구현** | **✅** | **옵션 A: 메트릭 구현 (원본 설계 준수)** | **I-41** |

### 폐기 이슈 (Deprecated)
- **I-36**: calcFairValue 파라미터 → I-41 priceQuantitative 메트릭으로 대체
- **I-38**: calcFairValue 기본값 → I-41 메트릭 자동 계산으로 대체
- **I-40**: Peer tickers 로깅 → I-41 제한사항으로 통합

---

*최종 업데이트: 2026-01-02 KST (I-41 구현 완료 - priceQuantitative 메트릭 추가, I-36/I-38/I-40 deprecated)*
