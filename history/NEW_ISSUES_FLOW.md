# 📊 가이드라인 검증 후 발견된 이슈 흐름도

> 이 문서는 가이드라인 검증 후 발견된 이슈들의 흐름을 기록합니다.

---

## I-NEW-01: consensusSignal 하드코딩 문제

### 현상
	`valuation_service.py`의 `calculate_qualitative_metrics()` 함수에서 consensusSignal을 하드코딩된 로직으로 생성함.
	
	- **현재 구현**: 하드코딩된 Python 로직으로 consensusSignal 계산 (라인 638-667)
	- **DB 설정**: consensusSignal 메트릭이 aggregation 타입, leadPairFromList로 설정됨
	- **불일치**: DB 설정과 Python 코드가 일치하지 않음

### 원인
	1. I-01 작업에서 leadPairFromList aggregation을 구현했으나, 실제로 사용하지 않음
	2. `calculate_qualitative_metrics()` 함수가 여전히 기존 하드코딩 로직 사용
	3. MetricCalculationEngine을 호출하지 않음

### 가이드라인 요구사항
	**가이드라인** (`1_guideline(function).ini` 라인 800-891):
	```
	- consensusSignal (qualitative-consensusSignal)
		- 입력 소스(권위): public.evt_consensus (2단계 계산 완료본)
		- 사용 컬럼: ticker, event_date, analyst_name, analyst_company,
		             price_target, price_when_posted, price_target_prev,
		             price_when_posted_prev, direction, response_key.last/prev
		- 생성 규칙(강제):
			- direction: evt_consensus.direction 값 사용
			- last: price_target, price_when_posted
			- prev: price_target_prev, price_when_posted_prev
			- delta, deltaPct 계산
			- meta: analyst_name, analyst_company, 뉴스 정보
	```
	
	**권장 방식**: MetricCalculationEngine + leadPairFromList aggregation 사용

### LLM 제공 선택지
	직접 수정 제안 (선택지 없음)

### 사용자 채택
	**수정 필요** (미반영)

### 반영 내용
	- **상태**: ❌ 미반영
	- **필요 작업**: → [상세: I-NEW-01]
		- `calculate_qualitative_metrics()` 함수 수정
		- MetricCalculationEngine 초기화
		- consensusSignal 메트릭 정의 로드
		- leadPairFromList aggregation으로 동적 계산
		- 하드코딩된 로직 제거
	- **참조**: `backend/src/services/valuation_service.py` 라인 638-667

---

## I-NEW-02: consensusSignal 출력 스키마 불일치

### 현상
	현재 출력되는 consensusSignal 스키마가 가이드라인의 요구사항과 부분적으로 일치하지 않음.
	
	- **존재하는 필드**: direction, last, prev, delta, deltaPct
	- **누락된 필드**: source, source_id, event_date
	- **부분 누락**: meta.news_url, meta.news_title, meta.news_publisher, meta.source_api

### 원인
	1. `calculate_qualitative_metrics()` 함수에서 간소화된 스키마 사용
	2. 메타 정보 중 일부만 포함

### 가이드라인 요구사항
	**가이드라인** (`1_guideline(function).ini` 라인 851-891):
	```json
	{
	  "consensusSignal": {
	    "source": "evt_consensus",
	    "source_id": "7f5b7a2a-9e1f-4d7b-9d52-6b3f5f5a0d0a",
	    "event_date": "2025-12-08T00:00:00Z",
	    "direction": "up",
	    "last": {
	      "price_target": 210.0,
	      "price_when_posted": 198.5
	    },
	    "prev": {
	      "price_target": 190.0,
	      "price_when_posted": 185.2
	    },
	    "delta": {
	      "price_target": 20.0,
	      "price_when_posted": 13.3
	    },
	    "deltaPct": {
	      "price_target": 0.1052631579
	    },
	    "meta": {
	      "analyst_name": "John Doe",
	      "analyst_company": "ABC Securities",
	      "news_url": "https://...",
	      "news_title": "....",
	      "news_publisher": "....",
	      "source_api": "fmp-price-target"
	    }
	  }
	}
	```

### LLM 제공 선택지
	직접 수정 제안 (선택지 없음)

### 사용자 채택
	**보완 권장** (부분반영)

### 반영 내용
	- **상태**: ⚠️ 부분반영
	- **필요 작업**: → [상세: I-NEW-02]
		- source, source_id, event_date 필드 추가
		- meta.news_url, news_title, news_publisher, source_api 추가
		- evt_consensus.response_key.last에서 뉴스 정보 추출
	- **참조**: `backend/src/services/valuation_service.py` 라인 724-727

---

## I-NEW-03: Upsert 전략 검증 필요

### 현상
	가이드라인에 명시된 Upsert 전략이 코드에서 정확히 구현되었는지 미확인

### 가이드라인 요구사항
	**가이드라인** (`1_guideline(function).ini` 라인 37-39):
	```
	적재 전략 명시(Upsert vs Insert-only)
	- Insert-only(기존 레코드 변경 금지): evt_earning (중복 시 DO NOTHING)
	- Upsert(갱신 허용): config_lv3_market_holidays, config_lv3_targets,
	                     evt_consensus, config_lv3_analyst, [table.events]
	```

### LLM 제공 선택지
	검증 작업 수행

### 사용자 채택
	**검증 필요** (미확인)

### 반영 내용
	- **상태**: ⚪ 미확인
	- **필요 작업**:
		- evt_earning INSERT 로직에서 DO NOTHING 확인
		- 각 테이블의 upsert 충돌 키 확인
		- ON CONFLICT 동작 검증

---

## I-NEW-04: dayOffset 처리 검증 필요

### 현상
	event_date가 비거래일일 때 dayOffset=0의 처리 로직 미확인

### 가이드라인 요구사항
	**가이드라인** (`1_guideline(function).ini` 라인 947-949):
	```
	dayOffset 정의
	- dayOffset는 countStart부터 countEnd까지 0 포함하여 생성한다.
	- event_date가 비거래일인 경우 dayOffset=0의 targetDate는 직후 첫 거래일로 매핑한다.
	```

### LLM 제공 선택지
	검증 작업 수행

### 사용자 채택
	**검증 필요** (미확인)

### 반영 내용
	- **상태**: ⚪ 미확인
	- **필요 작업**:
		- `events_service.py`의 `fill_price_trend()` 함수 검증
		- 비거래일 → 첫 거래일 매핑 로직 확인
		- dayOffset=0 처리 검증

---

## 요약 테이블

| ID | 이슈 | 상태 | 사용자 선택 | 상세도 |
|----|------|------|------------|--------|
| I-NEW-01 | consensusSignal 하드코딩 | ❌ | 수정 필요 | I-NEW-01 |
| I-NEW-02 | consensusSignal 스키마 | ⚠️ | 보완 권장 | I-NEW-02 |
| I-NEW-03 | Upsert 전략 검증 | ⚪ | 검증 필요 | - |
| I-NEW-04 | dayOffset 처리 검증 | ⚪ | 검증 필요 | - |

---

*마지막 업데이트: 2025-12-24*

