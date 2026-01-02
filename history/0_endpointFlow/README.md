# 📂 AlSign 엔드포인트 흐름 문서

> **목적**: 각 엔드포인트 호출 시 어떤 파일의 어떤 함수가 실행되어 데이터가 어떻게 흐르는지 상세 기록
> 
> **최종 업데이트**: 2025-12-31

---

## 엔드포인트 목록

| 엔드포인트 | 설명 | 문서 |
|------------|------|------|
| **POST /backfillEventsTable** | txn_events에 valuation 메트릭 계산 | [POST_backfillEventsTable.md](./POST_backfillEventsTable.md) |
| **POST /setEventsTable** | evt_* 테이블을 txn_events로 통합 | [POST_setEventsTable.md](./POST_setEventsTable.md) |
| **GET /sourceData** | 외부 FMP API에서 데이터 수집 | [GET_sourceData.md](./GET_sourceData.md) |

---

## 파이프라인 흐름

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           AlSign Data Pipeline                              │
└─────────────────────────────────────────────────────────────────────────────┘

[1단계: 데이터 수집]
    │
    ▼
┌──────────────────────────┐
│ GET /sourceData          │
│   mode=holiday,target,   │
│        consensus,earning │
└──────────────────────────┘
    │
    ├─► config_lv3_market_holidays (휴장일)
    ├─► config_lv3_targets (분석 대상 종목)
    ├─► evt_consensus (애널리스트 컨센서스)
    └─► evt_earning (실적 발표)

[2단계: 이벤트 통합]
    │
    ▼
┌──────────────────────────┐
│ POST /setEventsTable     │
│   table=consensus,earning│
└──────────────────────────┘
    │
    └─► txn_events (통합 이벤트 테이블)
          ├─► ticker, event_date
          ├─► source, source_id
          └─► sector, industry (enrichment)

[3단계: Valuation 계산]
    │
    ▼
┌──────────────────────────┐
│ POST /backfillEventsTable│
│   tickers=AAPL,GOOGL     │
│   from=2024-01-01        │
└──────────────────────────┘
    │
    └─► txn_events UPDATE
          ├─► value_quantitative (PER, PBR, PSR...)
          ├─► value_qualitative (targetMedian, consensusSignal...)
          ├─► position_quantitative/qualitative
          ├─► disparity_quantitative/qualitative
          └─► price_trend (OHLC 시계열)
```

---

## 디렉토리 구조

```
backend/src/
├── routers/               # 엔드포인트 정의
│   ├── events.py          # POST /setEventsTable, POST /backfillEventsTable
│   ├── source_data.py     # GET /sourceData
│   └── analyst.py         # POST /fillAnalyst (추가 예정)
│
├── services/              # 비즈니스 로직
│   ├── events_service.py  # setEventsTable 로직
│   ├── valuation_service.py  # backfillEventsTable 로직
│   ├── source_data_service.py  # sourceData 로직
│   ├── metric_engine.py   # 메트릭 계산 엔진
│   └── external_api.py    # FMP API 클라이언트
│
└── database/queries/      # DB 쿼리
    ├── metrics.py         # 메트릭 관련 쿼리
    ├── events.py          # 이벤트 관련 쿼리
    ├── consensus.py       # 컨센서스 관련 쿼리
    ├── policies.py        # 정책 관련 쿼리
    └── targets.py         # 분석 대상 관련 쿼리
```

---

## 주요 데이터 테이블

| 테이블 | 용도 | 주요 컬럼 |
|--------|------|-----------|
| `config_lv1_api_list` | FMP API 설정 | api, endpoint, schema |
| `config_lv1_policy` | 시스템 정책 | id, policy (JSONB) |
| `config_lv2_metric` | 메트릭 정의 | id, formula, source, domain |
| `config_lv2_metric_transform` | aggregation 함수 | id, calculation |
| `config_lv3_targets` | 분석 대상 종목 | ticker, sector, industry |
| `config_lv3_market_holidays` | 시장 휴장일 | exchange, date |
| `evt_consensus` | 애널리스트 컨센서스 | ticker, price_target, direction |
| `evt_earning` | 실적 발표 | ticker, eps, revenue |
| `txn_events` | 통합 이벤트 | ticker, value_quantitative, price_trend |

---

## 알려진 이슈

해당 엔드포인트 문서 또는 [../1_CHECKLIST.md](../1_CHECKLIST.md) 참조.

### 최신 이슈 (2025-12-31 - 해결됨)

| ID | 이슈 | 상태 | 설명 |
|----|------|------|------|
| I-36 | Quantitative Position/Disparity | ✅ 해결됨 | 업종 평균 PER × EPS로 적정가 계산 (`calcFairValue` 파라미터) |
| I-37 | targetMedian | ✅ 해결됨 | PERCENTILE_CONT(0.5)로 실제 Median 계산 |

**참조**: [../3_DETAIL.md#I-36](../3_DETAIL.md#I-36), [../3_DETAIL.md#I-37](../3_DETAIL.md#I-37)

---

## Frontend 라우터

| 라우터 | 설명 | 주요 기능 |
|--------|------|-----------|
| `/#/requests` | API 요청 실행 | 엔드포인트 실행, Log 패널 (리사이즈 가능) |
| `/#/setRequests` | API 설정 관리 | 모드별 API ID 변경, Schema 기반 검증 |
| `/#/control` | 시스템 관리 | API 키 관리, 런타임 정보 |
| `/#/conditionGroup` | 조건 그룹 관리 | 분석 조건 설정 |
| `/#/dashboard` | 대시보드 | 시스템 상태 모니터링 |

### Frontend UI 특징 (I-32, I-33, I-34)

1. **Log 패널 리사이즈** (I-32)
   - 하단/우측 패널 위치 전환 가능
   - 마우스 드래그로 패널 크기 조정
   - 하단: 200~600px, 우측: 300~800px

2. **본문 80% 너비** (I-33)
   - 모든 라우터에서 본문이 출력 영역의 80% 너비
   - 가운데 정렬, 최대 너비 1400px

3. **/setRequests API 변경** (I-34)
   - 엔드포인트별 API ID 변경 UI
   - Schema 기반 검증 (API 호출 없이)
   - 필수 키 누락 시 저장 불가

---

*최종 업데이트: 2025-12-31 KST*

