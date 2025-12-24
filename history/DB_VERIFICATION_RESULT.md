# 📊 AlSign DB 검증 결과 보고서

**검증일시**: 2025-12-24
**검증 스크립트**: `backend/scripts/verify_checklist_items.py`
**DB**: Supabase PostgreSQL (프로젝트: fgypclaqxonwxlmqdphx)

---

## 📋 검증 요약

| 항목 | 상태 | 비고 |
|------|------|------|
| DB 연결 | ✅ 성공 | Supabase Pooler 모드 |
| config_lv2_metric 테이블 | ✅ 존재 | 81개 메트릭 정의됨 |
| I-01 SQL 변경 | ✅ 완료 | consensusSignal 설정 적용됨 |
| I-05 SQL 변경 | ✅ 완료 | consensus 메트릭 추가됨 |
| config_lv0_policy 테이블 | ✅ 존재 | 2개 정책 (I-10 정책 없음) |

---

## ✅ 1. 테이블 존재 확인

```
✅ config_lv2_metric 테이블 존재
   총 81개 메트릭 정의됨
```

**결론**: setup_supabase.sql이 성공적으로 실행됨

---

## ✅ 2. I-01: consensusSignal 설정 확인

### DB 현황
```sql
SELECT id, source, expression, aggregation_kind, base_metric_id, domain
FROM config_lv2_metric
WHERE id = 'consensusSignal';
```

### 결과
| 필드 | 현재 값 | 예상 값 | 상태 |
|------|---------|---------|------|
| source | aggregation | aggregation | ✅ |
| expression | NULL | NULL | ✅ |
| aggregation_kind | leadPairFromList | leadPairFromList | ✅ |
| base_metric_id | NULL | NULL | ✅ |
| domain | qualatative-consensusSignal | qualatative-consensusSignal | ✅ |

**결론**: ✅ **I-01 SQL 변경사항 모두 적용됨**

### 적용된 SQL (apply_issue_docs_changes.sql)
```sql
UPDATE config_lv2_metric
SET
  source = 'aggregation',
  expression = NULL,
  aggregation_kind = 'leadPairFromList',
  aggregation_params = '{...}'::jsonb
WHERE id = 'consensusSignal';
```

---

## ✅ 3. I-05: consensus 메트릭 추가 확인

### DB 현황
```sql
SELECT id, source, api_list_id, domain, response_key
FROM config_lv2_metric
WHERE id = 'consensus';
```

### 결과
| 필드 | 현재 값 | 예상 값 | 상태 |
|------|---------|---------|------|
| source | api_field | api_field | ✅ |
| api_list_id | fmp-price-target | fmp-price-target | ✅ |
| domain | qualatative-consensus | qualatative-consensus | ✅ |
| response_key | 12개 필드 매핑 | 12개 필드 | ✅ |

**response_key 필드**:
- ticker, newsURL, newsTitle, event_date, analystName
- newsBaseURL, priceTarget, newsPublisher, publishedDate
- adjPriceTarget, analystCompany, priceWhenPosted

**결론**: ✅ **I-05 SQL 변경사항 적용됨**

### 적용된 SQL (apply_issue_docs_changes.sql)
```sql
INSERT INTO config_lv2_metric (id, source, api_list_id, response_key, domain, description)
VALUES ('consensus', 'api_field', 'fmp-price-target', '{...}'::jsonb, 'qualatative-consensus', '...')
ON CONFLICT (id) DO UPDATE SET ...;
```

---

## ✅ 4. qualatative-* 도메인 메트릭 현황

### DB 현황
```sql
SELECT id, domain, source
FROM config_lv2_metric
WHERE domain LIKE 'qualatative-%'
ORDER BY domain, id;
```

### 결과 (4개 메트릭)

| 도메인 | 메트릭 ID | source |
|--------|-----------|--------|
| qualatative-consensus | consensus | api_field |
| qualatative-consensusSignal | consensusSignal | aggregation |
| qualatative-consensusSummary | consensusSummary | (확인필요) |
| qualatative-targetMedian | priceQualitative | (확인필요) |

**결론**: ✅ qualatative 도메인 메트릭들이 정상적으로 존재함

---

## ⚠️ 5. config_lv0_policy 테이블 확인

### DB 현황
```sql
SELECT function, policy
FROM config_lv0_policy
ORDER BY function;
```

### 결과 (2개 정책)

| function | 존재 여부 |
|----------|-----------|
| fillPriceTrend_dateRange | ✅ |
| sourceData_dateRange | ✅ |
| **priceEodOHLC_dateRange** | ❌ **없음** |

**결론**: ⚠️ **I-10 관련 priceEodOHLC_dateRange 정책 없음 (미반영)**

---

## 📊 최종 결론

### ✅ 성공적으로 반영된 항목 (2개)

1. **I-01: consensusSignal 설정**
   - SQL 변경사항 100% 적용
   - aggregation 방식으로 전환 완료
   - Python 코드에서 leadPairFromList 구현 필요

2. **I-05: consensus 메트릭**
   - SQL 변경사항 100% 적용
   - fmp-price-target API 연동 설정 완료
   - 12개 필드 response_key 매핑 완료

### ⚠️ 추가 구현 필요 항목 (3개)

1. **I-01: leadPairFromList aggregation** (Python 코드)
   - metric_engine.py에 _lead_pair_from_list() 메서드 구현
   - 우선순위: 중 (현재는 하드코딩으로 동작 중)

2. **I-10: priceEodOHLC_dateRange 정책** (DB + Python)
   - config_lv0_policy 테이블에 정책 추가
   - policies.py에 get_ohlc_date_range_policy() 구현
   - valuation_service.py에서 사용
   - 우선순위: 중 (현재는 fillPriceTrend_dateRange 재사용)

3. **I-11: internal(qual) 메트릭 동적 처리** (Python 코드)
   - metrics.py에 select_internal_qual_metrics() 구현
   - analyst_service.py에서 DB 정의 기반 계산
   - 우선순위: 중 (현재는 하드코딩된 통계 계산)

---

## 🎯 권장 조치 순서

### 단기 (1-2일)
1. ✅ ~~I-01, I-05 SQL 실행~~ (완료)
2. I-03 Python 코드 재확인 (targetMedian & consensusSummary)
3. I-07, I-08, I-09 Python 코드 재확인

### 중기 (1주)
1. I-10: priceEodOHLC_dateRange 정책 구현
2. I-11: internal(qual) 메트릭 동적 처리

### 장기 (2주+)
1. I-01: leadPairFromList aggregation 완전 구현
2. I-01: db_field source 타입 구현
3. I-01: consensusRaw 메트릭 추가

---

## 📝 검증 명령어

```bash
cd c:\dev\alsign\backend
python scripts\verify_checklist_items.py
```

또는 (DATABASE_URL 직접 입력):

```bash
python scripts\verify_checklist_direct.py "YOUR_DATABASE_URL"
```

---

*보고서 작성: 2025-12-24*
*검증 스크립트 버전: 1.0*

