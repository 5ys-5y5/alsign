# Price Trend 기준 재설계 (2026-01-15)

이 문서는 day-offset 성과 계산을 사용자 선택 기준(offset/ohlc)으로 변경하는 설계안을 정리한 것입니다.

## 목표
- 기준일을 사용자가 선택한 offset(D-14..D+14)으로 지정.
- 기준가(매수 기준)는 기준일의 OHLC 중 선택한 값(open/high/low/close).
- 각 컬럼의 매도 기준도 OHLC 중 선택한 값으로 계산.
- 조회 속도를 위해 `txn_price_trend`에 사전 계산된 값을 저장.
- 각 `d_*` JSONB에는 `targetDate`, `price_target`만 유지.

## 모드별 계산
### % 모드
- 기준일 = event_date + base_offset (거래일 기준)
- 기준값 = 기준일의 base_ohlc
- 각 Dn 값 = (sell_ohlc_at_offset / base_value) - 1

### N 모드
- 기준일 = event_date + base_offset
- 기준값 = 기준일의 base_ohlc
- 각 Dn 값 = sell_ohlc_at_offset
- UI는 기준값과 비교하여 +/−를 화살표/색상으로 표시

## 데이터 모델 옵션
### 옵션 A (권장): txn_price_trend에 기준 설정 저장
추가 컬럼:
- base_offset SMALLINT
- base_ohlc TEXT  -- 'open'|'high'|'low'|'close'
- sell_ohlc TEXT  -- 'open'|'high'|'low'|'close'
- base_price NUMERIC

장점: 조인 없이 빠른 조회. 단점: 스키마 변경 필요.

### 옵션 B: 별도 테이블 저장
예: txn_price_trend_base(ticker, event_date, base_offset, base_ohlc, sell_ohlc, base_price)

장점: 설정 분리. 단점: 조회 시 조인 필요.

## d_* JSON 정리 형태
각 `d_*` JSONB는 아래만 유지:
```
{
  "targetDate": "2025-10-10",
  "price_target": 45.58
}
```
- price_target = 해당 offset의 sell_ohlc 값
- targetDate = 해당 offset의 실제 거래일

## JSON 정리 SQL 예시 (단일 컬럼)
```sql
UPDATE txn_price_trend
SET d_neg14 = jsonb_build_object(
      'targetDate', d_neg14->>'targetDate',
      'price_target', (d_neg14->'price_trend'->>'close')::numeric
    )
WHERE d_neg14 IS NOT NULL;
```
`price_target`에 사용할 OHLC는 sell_ohlc 선택값과 일치해야 함.

## 계산/저장 파이프라인 변경
1) 사용자 입력 수집: base_offset, base_ohlc, sell_ohlc
2) generatePriceTrends 수정:
   - 기준일 계산(거래일 캘린더)
   - 기준일 base_ohlc 조회 → base_price 저장
   - 각 offset에 대해 price_target 계산(sell_ohlc) → {targetDate, price_target} 저장
   - % 모드는 필요 시 성과를 저장하거나, 조회 시 (price_target / base_price - 1) 계산

## 캐싱/성능 전략
- 계산은 하루 1회만 수행(예: 배치/스케줄러).
- 화면 최초 로드 시에는 이미 계산된 결과를 읽기만 함.
- 테이블 전환/화면 전환과 관계없이 즉시 로드되도록, 계산 결과는 DB에 영구 저장.
- API는 실시간 계산 대신 저장된 값을 그대로 반환하여 응답 시간을 최소화.

## 결정 필요 사항
1) 입력 UI 위치: Trades 테이블 상단? Events 테이블 상단? 별도 설정 페이지?
2) sell_ohlc는 모든 컬럼에 공통 하나인가?
3) % 값은 DB에 저장할지, 조회 시 계산할지?

