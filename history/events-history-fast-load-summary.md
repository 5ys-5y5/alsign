# Events History 빠른 로딩 변경 요약 (현재 상태)

## 현재 빠른 로딩 흐름

1) 프론트 계산 제거
- 브라우저에서 historical 가격 배치를 가져와 계산하던 로직 제거.
- 이벤트 데이터는 서버에서 계산된 결과를 그대로 받음.

2) 서버 계산 방식 (Option B)
- `/dashboard/eventsHistory`
  - `txn_events` + `config_lv3_quantitatives.historical_price`를 조인해 계산.
  - historical_price(JSON 배열)를 파싱해 이벤트 날짜 기준 D-14~D14 매핑.
  - Designated/Previous 수익률 및 OHLC/타겟 날짜 맵을 서버에서 생성.
- `/dashboard/eventsHistory/bestWindow`
  - 동일한 소스를 사용해 Best Window를 서버에서 계산.
  - 프론트는 요약 결과만 수신.

3) 단일 요청 흐름
- 이벤트 1회 요청 + Best Window 1회 요청으로 완료.
- 브라우저의 대량 네트워크/CPU 병목 제거.

## 성능 특성
- `historical_price`는 요청마다 JSON 파싱 + 날짜 인덱싱 + 29일 계산이 필요.
- `txn_price_trend` 대비 느릴 가능성이 높음(실측 필요).

## txn_price_trend 사용 여부 (현재 서비스 기준)
다음 기능들은 여전히 `txn_price_trend`를 사용합니다.

- `/dashboard/events` (events 테이블, 기존 성능 컬럼)
  - `txn_price_trend` 조인 후 `performance.close`를 추출
- `/dashboard/trades` (trades 테이블 day offset)
  - `txn_price_trend` 조인 후 day-offset 값 사용
- `/dashboard/dayOffsetMetrics` 관련 로직
  - `txn_price_trend` 기반 (주석/로직 포함)
- `backend/src/services/valuation_service.py`
  - `txn_price_trend` 생성/업서트 로직
- `backend/src/routers/price_trends.py`
  - `txn_price_trend` 생성 엔드포인트
- `frontend/src/pages/SetRequestsPage.jsx`
  - `txn_price_trend` 생성/업서트 작업 안내 및 UI

따라서 `txn_price_trend`를 완전히 삭제하려면
위 기능들의 대체 소스 변경이 필요합니다.

## 변경된 파일 (빠른 로딩 관련)
- `backend/src/routers/dashboard.py`
  - `/dashboard/eventsHistory` 및 `/dashboard/eventsHistory/bestWindow` (Option B)
- `frontend/src/services/eventsHistoryData.js`
  - 서버 엔드포인트 사용으로 전환
- `frontend/src/pages/EventsHistoryPage.jsx`
  - Best Window 서버 결과 사용
