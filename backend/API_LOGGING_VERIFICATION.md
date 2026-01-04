# API Logging Verification Report

## 요청 사항
POST /backfillEventsTable?overwrite=true&tickers=rgti 엔드포인트 호출 시:
1. 다른 ticker (BILI 등)에 대한 API 호출 발생
2. 로그 형식이 `[table: txn_events | id: ...]` 형식으로 출력되지 않음

---

## 해결 내용

### 1. ✅ 로그 형식 개선

**문제:**
사용자가 제공한 로그에서 row_context가 누락:
```
[API Response] fmp-balance-sheet-statement -> HTTP 200
[API Call] fmp-historical-market-capitalization -> https://...BILI...
```

**원인:**
서버가 최신 코드로 재시작되지 않음

**해결:**
모든 API 호출에 row_context 추가 완료:
```
[table: txn_events | id: ticker-cache:RGTI] | [API Call] fmp-balance-sheet-statement -> ...
[table: txn_events | id: ticker-cache:RGTI] | [API Response] fmp-balance-sheet-statement -> HTTP 200
```

### 2. ✅ Peer Ticker API 호출 Context 개선

**문제:**
RGTI만 요청했는데 BILI, ZBRA 등 9개 peer ticker에 대한 API 호출 발생

**원인:**
sector average PER/PBR 계산을 위해 peer ticker 재무 데이터 필요
- priceQuantitative (적정가) = sector_avg_PER × current_EPS
- sector_avg_PER 계산 위해 peer ticker들의 PER 필요

**해결:**
Peer ticker API 호출에 명확한 context 추가:
```
[table: txn_events | id: ticker-cache:RGTI:peer-BILI] | [API Call] fmp-balance-sheet-statement -> ...
[table: txn_events | id: ticker-cache:RGTI:peer-ZBRA] | [API Call] fmp-income-statement -> ...
```

이제 로그만 봐도:
- `ticker-cache:RGTI` = RGTI 자체 데이터
- `ticker-cache:RGTI:peer-BILI` = RGTI의 sector average 계산을 위한 BILI 데이터

---

## 최종 로그 구조

### API Call 통계 (tickers=rgti 요청 시)

```
   9 calls → ticker-cache:RGTI                  (RGTI 자체 데이터)
   7 calls → ticker-cache:RGTI:peer-ZBRA        (Peer 데이터)
   7 calls → ticker-cache:RGTI:peer-SNX         (Peer 데이터)
   7 calls → ticker-cache:RGTI:peer-SAIL        (Peer 데이터)
   7 calls → ticker-cache:RGTI:peer-QXO         (Peer 데이터)
   7 calls → ticker-cache:RGTI:peer-QBTS        (Peer 데이터)
   7 calls → ticker-cache:RGTI:peer-IONQ        (Peer 데이터)
   7 calls → ticker-cache:RGTI:peer-DUOL        (Peer 데이터)
   7 calls → ticker-cache:RGTI:peer-CACI        (Peer 데이터)
   7 calls → ticker-cache:RGTI:peer-BILI        (Peer 데이터)
```

**총 API 호출:**
- RGTI 자체: 9개
- Peer ticker (9개 × 7 calls): 63개
- **합계: 72개 API 호출**

### Peer Ticker 리스트 (RGTI의 동종 업종)
FMP stock-peers API가 반환한 peer tickers:
1. BILI - Bilibili Inc.
2. CACI - CACI International Inc.
3. DUOL - Duolingo Inc.
4. IONQ - IonQ Inc.
5. QBTS - D-Wave Quantum Inc.
6. QXO - QXO Inc.
7. SAIL - SailPoint Technologies Holdings Inc.
8. SNX - TD SYNNEX Corp.
9. ZBRA - Zebra Technologies Corp.

---

## 로그 예시

### RGTI 자체 데이터 호출
```
[table: txn_events | id: ticker-cache:RGTI] | [API Call] fmp-income-statement -> https://...symbol=RGTI...
[table: txn_events | id: ticker-cache:RGTI] | [API Response] fmp-income-statement -> HTTP 200
[table: txn_events | id: ticker-cache:RGTI] | [API Parse] fmp-income-statement -> Type: list, Length: 35
```

### Peer Ticker 데이터 호출 (Sector Average 계산용)
```
[table: txn_events | id: ticker-cache:RGTI:peer-BILI] | [API Call] fmp-income-statement -> https://...symbol=BILI...
[table: txn_events | id: ticker-cache:RGTI:peer-BILI] | [API Response] fmp-income-statement -> HTTP 200
[table: txn_events | id: ticker-cache:RGTI:peer-BILI] | [API Parse] fmp-income-statement -> Type: list, Length: 28
```

### Peer 데이터 캐싱 로그
```
[I-36] Found 9 peer tickers for RGTI: ['BILI', 'CACI', 'DUOL', 'IONQ', 'QBTS', 'QXO', 'SAIL', 'SNX', 'ZBRA']
[PERF] RGTI: Peer data cached ONCE (peers=9, sector_avg_keys=['PER', 'PBR'])
```

---

## 변경 사항

### backend/src/services/valuation_service.py
**Line 2124:** Peer ticker context 생성
```python
peer_context = f"{event_id}:peer-{peer_ticker}" if event_id else f"peer-{peer_ticker}"
```

**Line 2144:** Peer ticker API 호출 시 context 전달
```python
api_response = await fmp_client.call_api(api_id, params, event_id=peer_context)
```

---

## 검증 방법

```bash
cd backend
python test_rgti_backfill_logs.py 2>&1 | grep "\[API Call\]"
```

**예상 결과:**
- 모든 API 호출에 `[table: txn_events | id: ...]` prefix 존재
- Peer ticker 호출에 `:peer-{ticker}` suffix 존재
- RGTI 자체 데이터와 peer 데이터 구분 명확

---

## 주의사항

**서버 재시작 필수**

변경 사항을 적용하려면 백엔드 서버를 재시작해야 합니다:

```bash
# 1. 기존 프로세스 종료
taskkill /F /IM uvicorn.exe

# 2. 서버 재시작
cd backend
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## 요약

✅ **로그 형식:** 모든 API 호출에 row_context 추가 완료
✅ **Peer ticker context:** peer ticker 호출에 명확한 표시 추가
✅ **추적 가능성:** 각 API 호출이 어떤 목적(자체 데이터 vs peer 데이터)인지 명확히 구분 가능

priceQuantitative (적정가) 계산을 위해서는 sector average가 필수이므로, peer ticker API 호출은 정상적이고 필요한 동작입니다.
