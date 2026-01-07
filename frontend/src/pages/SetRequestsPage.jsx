/**
 * SetRequestsPage Component
 *
 * Visual endpoint flow documentation with inline API configuration.
 * - Interactive flow diagrams for each endpoint
 * - Click on API nodes to change config_lv1_api_list ID
 * - Schema-based validation (no API calls needed)
 */

import React, { useState, useEffect, useCallback } from 'react';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

/**
 * Endpoint Flow Definitions
 * Based on /history/0_endpointFlow documentation
 */
const ENDPOINT_FLOWS = {
  sourceData: {
    id: 'sourceData',
    title: 'GET /sourceData',
    description: '외부 FMP API에서 금융 데이터를 수집하여 DB에 저장 (target 모드는 peer 컬럼 업데이트 포함)',
    parameters: [
      {
        name: 'mode',
        type: 'string',
        required: false,
        options: ['holiday', 'target', 'consensus', 'earning'],
        description: '실행할 모드 (쉼표 구분 가능, 예: "target,consensus"). 미지정 시 전체 모드 순차 실행 (holiday → target → consensus → earning)'
      },
      {
        name: 'overwrite',
        type: 'boolean',
        required: false,
        default: 'false',
        description: 'NULL만 채우기(false) vs 기존 데이터 덮어쓰기(true)'
      },
      {
        name: 'past',
        type: 'boolean',
        required: false,
        default: 'false',
        description: 'earning 모드 전용: true면 과거 5년 + 미래 28일, false면 미래 28일만'
      },
      {
        name: 'calc_mode',
        type: 'string',
        required: false,
        options: ['maintenance', 'calculation'],
        description: 'consensus 모드 전용: maintenance(Phase 1+2 with scope), calculation(Phase 2만, API 호출 없음). 미지정 시 Phase 1+2 실행'
      },
      {
        name: 'calc_scope',
        type: 'string',
        required: false,
        options: ['all', 'ticker', 'event_date_range', 'partition_keys'],
        description: 'calc_mode와 함께 사용: 재계산 범위 지정 (all, ticker, event_date_range, partition_keys)'
      },
      {
        name: 'tickers',
        type: 'string',
        required: false,
        description: 'calc_scope=ticker일 때 필수: 쉼표로 구분된 티커 목록 (예: "AAPL,MSFT")'
      },
      {
        name: 'from',
        type: 'date',
        required: false,
        description: 'calc_scope=event_date_range일 때 필수: 시작 날짜 (YYYY-MM-DD)'
      },
      {
        name: 'to',
        type: 'date',
        required: false,
        description: 'calc_scope=event_date_range일 때 필수: 종료 날짜 (YYYY-MM-DD)'
      },
    ],
    usageExamples: [
      {
        title: '기본: 전체 모드 순차 실행',
        url: 'GET /sourceData',
        description: 'holiday → target → consensus → earning 순서로 모두 실행'
      },
      {
        title: '특정 모드만 실행',
        url: 'GET /sourceData?mode=consensus',
        description: 'consensus 모드만 실행 (Phase 1+2+3)'
      },
      {
        title: '여러 모드 선택 실행',
        url: 'GET /sourceData?mode=target,consensus',
        description: 'target과 consensus만 실행'
      },
      {
        title: 'consensus 재계산 (전체)',
        url: 'GET /sourceData?mode=consensus&calc_mode=maintenance&calc_scope=all',
        description: 'API 호출 + 모든 파티션 재계산'
      },
      {
        title: 'consensus 재계산 (특정 티커만)',
        url: 'GET /sourceData?mode=consensus&calc_mode=calculation&calc_scope=ticker&tickers=AAPL,MSFT',
        description: 'AAPL, MSFT만 재계산 (API 호출 없음)'
      },
      {
        title: 'earning 과거 데이터 수집',
        url: 'GET /sourceData?mode=earning&past=true',
        description: '과거 5년 + 미래 28일 실적 발표일 수집'
      },
    ],
    modes: {
      holiday: {
        description: '시장 휴장일 수집',
        outputTable: 'config_lv3_market_holidays',
        phases: [
          {
            id: 'fetch',
            title: 'API 호출',
            description: 'FMP API에서 휴장일 데이터 수집',
            apiId: 'fmp-market-holidays',
            requiredKeys: ['year', 'date', 'exchange'],
            configKey: 'sourceData.holiday.fetch'
          },
          {
            id: 'save',
            title: 'DB 저장',
            description: 'config_lv3_market_holidays에 UPSERT',
            apiId: null
          }
        ]
      },
      consensus: {
        description: '애널리스트 컨센서스 수집 (3-Phase)',
        outputTable: 'evt_consensus',
        phases: [
          {
            id: 'phase1',
            title: 'Phase 1: API 호출',
            description: 'FMP price-target API에서 raw 데이터 수집',
            apiId: 'fmp-price-target',
            requiredKeys: ['symbol', 'publishedDate', 'priceTarget', 'priceWhenPosted', 'analystName', 'analystCompany'],
            configKey: 'sourceData.consensus.phase1',
            skipCondition: 'calc_mode=calculation이면 스킵'
          },
          {
            id: 'phase2',
            title: 'Phase 2: prev 계산',
            description: 'price_target_prev, price_when_posted_prev, direction 계산',
            apiId: null,
            note: '같은 ticker+analyst_name+analyst_company 기준 이전 레코드 조회'
          },
          {
            id: 'phase3',
            title: 'Phase 3: targetSummary',
            description: '과거 데이터 기반 통계 계산 (I-31)',
            apiId: null,
            note: 'lastMonth/lastQuarter/lastYear/allTime 집계'
          }
        ]
      },
      earning: {
        description: '실적 발표 수집',
        outputTable: 'evt_earning',
        phases: [
          {
            id: 'fetch',
            title: 'API 호출',
            description: 'FMP earning calendar API 호출',
            apiId: 'fmp-earning-calendar',
            requiredKeys: ['symbol', 'date', 'eps', 'revenue'],
            configKey: 'sourceData.earning.fetch'
          },
          {
            id: 'save',
            title: 'DB 저장',
            description: 'evt_earning에 UPSERT',
            apiId: null
          }
        ]
      },
      target: {
        description: '분석 대상 종목 수집 및 peer 데이터 채움',
        outputTable: 'config_lv3_targets',
        phases: [
          {
            id: 'fetch',
            title: 'API 호출',
            description: 'FMP stock screener API 호출',
            apiId: 'fmp-stock-screener',
            requiredKeys: ['symbol', 'sector', 'industry'],
            configKey: 'sourceData.target.fetch'
          },
          {
            id: 'save',
            title: 'DB 저장',
            description: 'config_lv3_targets에 UPSERT',
            apiId: null
          },
          {
            id: 'peer',
            title: 'Peer 업데이트',
            description: 'FMP stock peers API 호출 후 peer 컬럼 업데이트',
            apiId: 'fmp-stock-peers'
          }
        ]
      }
    }
  },
  backfillEventsTable: {
    id: 'backfillEventsTable',
    title: 'POST /backfillEventsTable',
    description: 'txn_events 테이블의 이벤트에 valuation metrics 계산 (Price Trend 제외)',
    performanceNote: '100개 이벤트 (10개 티커) 처리 시: ~480 API calls, ~4분 소요. Peer 데이터 수집이 85% 시간 차지 (400 API calls)',
    parameters: [
      {
        name: 'overwrite',
        type: 'boolean',
        required: false,
        default: 'false',
        description: 'NULL만 채우기(false) vs 덮어쓰기(true). metrics 지정 시 해당 메트릭에만 적용, 미지정 시 전체 필드에 적용 (I-41 Part 3)'
      },
      {
        name: 'from',
        type: 'date',
        required: false,
        description: '이벤트 시작 날짜 필터 (YYYY-MM-DD). 미지정 시 전체 기간'
      },
      {
        name: 'to',
        type: 'date',
        required: false,
        description: '이벤트 종료 날짜 필터 (YYYY-MM-DD). 미지정 시 전체 기간'
      },
      {
        name: 'tickers',
        type: 'string',
        required: false,
        description: '티커 필터 (쉼표 구분, 예: "AAPL,MSFT"). 미지정 시 전체 티커'
      },
      {
        name: 'metrics',
        type: 'string',
        required: false,
        description: '업데이트할 메트릭 ID 리스트 (쉼표 구분, 예: "priceQuantitative,PER,PBR"). 미지정 시 전체 메트릭 계산 (I-41)'
      },
    ],
    behaviorMatrix: [
      { metrics: 'None', overwrite: 'false', behavior: '전체 필드 NULL만 채우기 (기본 동작)' },
      { metrics: 'None', overwrite: 'true', behavior: '전체 필드 강제 덮어쓰기' },
      { metrics: '"priceQuantitative"', overwrite: 'false', behavior: 'priceQuantitative만 NULL 채우기' },
      { metrics: '"priceQuantitative"', overwrite: 'true', behavior: 'priceQuantitative만 강제 덮어쓰기' },
      { metrics: '"PER,PBR"', overwrite: 'false', behavior: 'PER,PBR만 NULL 채우기 (동시)' },
      { metrics: '"PER,PBR"', overwrite: 'true', behavior: 'PER,PBR만 강제 덮어쓰기 (동시)' },
    ],
    usageExamples: [
      {
        title: '기본: 모든 메트릭 계산 (NULL만)',
        url: 'POST /backfillEventsTable',
        description: 'NULL 값만 채우기, 전체 메트릭'
      },
      {
        title: '특정 메트릭만 NULL 채우기',
        url: 'POST /backfillEventsTable?metrics=priceQuantitative',
        description: 'priceQuantitative 메트릭만 계산 (NULL 값만)'
      },
      {
        title: '특정 메트릭 강제 재계산',
        url: 'POST /backfillEventsTable?metrics=priceQuantitative&overwrite=true',
        description: 'priceQuantitative 강제 덮어쓰기'
      },
      {
        title: '여러 메트릭 동시 업데이트',
        url: 'POST /backfillEventsTable?metrics=PER,PBR,PSR&overwrite=false',
        description: 'PER, PBR, PSR 메트릭만 NULL 채우기'
      },
      {
        title: '날짜 + 티커 + 메트릭 필터링',
        url: 'POST /backfillEventsTable?from=2024-01-01&to=2024-12-31&tickers=AAPL,MSFT&metrics=priceQuantitative&overwrite=true',
        description: '2024년, AAPL/MSFT만, priceQuantitative 강제 재계산'
      },
      {
        title: '배치 처리 (점진적 피드백)',
        url: 'POST /backfillEventsTable?batch_size=5000',
        description: '5,000개씩 배치 처리하여 빠른 진행 피드백 제공 (I-44)'
      },
    ],
    phases: [
      {
        id: 'load_metrics',
        title: '1. 메트릭 정의 로드',
        description: 'config_lv2_metric에서 정의 로드',
        apiId: null,
        note: 'DB 쿼리 (API 아님)'
      },
      {
        id: 'load_events',
        title: '2. 이벤트 로드',
        description: 'txn_events에서 대상 이벤트 조회',
        apiId: null,
        note: 'DB 쿼리 (API 아님)'
      },
      {
        id: 'group_tickers',
        title: '3. 티커 그룹화',
        description: '이벤트를 티커별로 그룹화 (10개 티커 병렬 처리)',
        apiId: null,
        note: '메모리 작업 (semaphore limit=10)'
      },
      {
        id: 'ticker_cache',
        title: '4. 티커별 API 캐싱 (CRITICAL)',
        description: '티커당 1회만 API 호출 → 모든 이벤트가 캐시 재사용',
        note: '이 단계가 90% API 절감의 핵심! 티커당 ~6개 API 호출, 이벤트당 0개',
        subPhases: [
          {
            id: 'base_financials',
            title: '기본 재무 데이터',
            apiId: 'fmp-income-statement',
            note: 'income/balance/cash/historical-price/market-cap (5 APIs, period=quarter, limit=100)',
            requiredKeys: ['date', 'revenue', 'grossProfit', 'operatingIncome', 'netIncome'],
            configKey: 'backfill.income'
          },
          {
            id: 'consensus',
            title: '컨센서스 데이터',
            apiId: 'fmp-price-target-consensus',
            note: '1 API per ticker',
            requiredKeys: ['targetHigh', 'targetLow', 'targetConsensus', 'targetMedian'],
            configKey: 'backfill.consensus'
          },
          {
            id: 'peer_list',
            title: 'Peer 티커 목록',
            apiId: 'fmp-stock-peers',
            note: '1 API per ticker → 최대 10개 peer 반환',
            requiredKeys: ['symbol', 'peersList'],
            configKey: 'backfill.peers'
          },
          {
            id: 'peer_financials',
            title: 'Peer 재무 데이터 (BOTTLENECK)',
            apiId: 'fmp-income-statement',
            note: '⚠️ 40 APIs per ticker (4 APIs × 10 peers) → 전체의 85% 시간 소요! 티커 10개 = 400 API calls',
            requiredKeys: ['date', 'revenue', 'netIncome', 'totalAssets', 'totalEquity', 'marketCap'],
            configKey: 'backfill.peer_financials'
          }
        ]
      },
      {
        id: 'event_processing',
        title: '5. 이벤트 처리 (캐시 사용)',
        description: '각 이벤트: 캐시된 데이터 필터링 → 메트릭 계산 (API 호출 없음!)',
        apiId: null,
        note: '100개 이벤트 처리해도 추가 API 호출 0개 (날짜 필터링만 수행)'
      },
      {
        id: 'calc_quantitative',
        title: '6. Quantitative 메트릭',
        description: 'PER, PBR, PSR, ROE 등 계산',
        apiId: null,
        note: 'MetricCalculationEngine 사용 (캐시된 재무 데이터 기반)'
      },
      {
        id: 'calc_qualitative',
        title: '7. Qualitative 메트릭',
        description: 'consensusSignal, targetSummary 계산',
        apiId: null,
        note: 'evt_consensus 테이블 + 캐시된 컨센서스 데이터 사용'
      },
      {
        id: 'calc_price_quantitative',
        title: '8. priceQuantitative 계산',
        description: 'Peer 평균 PER × 회사 EPS = 적정가',
        apiId: null,
        note: '캐시된 sector_averages 사용 (단계 4에서 계산됨)'
      },
      {
        id: 'batch_update',
        title: '9. 배치 업데이트',
        description: 'txn_events 테이블 일괄 UPDATE (티커당 1회)',
        apiId: null,
        note: 'UNNEST 패턴으로 100개 이벤트를 단일 쿼리로 업데이트'
      }
    ],
    outputs: [
      'value_quantitative (PER, PBR, PSR, evEBITDA, ROE, ...)',
      'value_qualitative (targetMedian, targetSummary, consensusSignal)',
      'position_quantitative, position_qualitative',
      'disparity_quantitative, disparity_qualitative'
    ]
  },
  generatePriceTrends: {
    id: 'generatePriceTrends',
    title: 'POST /generatePriceTrends',
    description: 'txn_price_trend 테이블에 ±14 trading days OHLC 가격 추세 데이터 생성 (backfillEventsTable과 독립 실행). txn_events 이벤트 + txn_trades 거래 모두 처리',
    performanceNote: '100개 레코드 (10개 티커) 처리 시: ~10 API calls (OHLC만), ~5초 소요. Trading days는 전역 캐싱으로 DB 쿼리 1회만. txn_trades에서 txn_events에 없는 거래도 자동 처리',
    parameters: [
      {
        name: 'overwrite',
        type: 'boolean',
        required: false,
        default: 'false',
        description: 'NULL만 채우기(false) vs 덮어쓰기(true)'
      },
      {
        name: 'from',
        type: 'date',
        required: false,
        description: '이벤트 시작 날짜 필터 (YYYY-MM-DD). 미지정 시 전체 기간'
      },
      {
        name: 'to',
        type: 'date',
        required: false,
        description: '이벤트 종료 날짜 필터 (YYYY-MM-DD). 미지정 시 전체 기간'
      },
      {
        name: 'tickers',
        type: 'string',
        required: false,
        description: '티커 필터 (쉼표 구분, 예: "AAPL,MSFT"). 미지정 시 전체 티커'
      },
    ],
    usageExamples: [
      {
        title: '기본: 전체 이벤트 price trend 생성',
        url: 'POST /generatePriceTrends',
        description: 'txn_events의 모든 이벤트에 대해 price trend 계산 (NULL만)'
      },
      {
        title: '특정 티커만 생성',
        url: 'POST /generatePriceTrends?tickers=RGTI',
        description: 'RGTI 티커만 price trend 계산'
      },
      {
        title: '날짜 범위 + 강제 재계산',
        url: 'POST /generatePriceTrends?from=2024-01-01&to=2024-12-31&overwrite=true',
        description: '2024년 이벤트만 price trend 강제 재계산'
      },
      {
        title: '여러 티커 + 날짜 필터링',
        url: 'POST /generatePriceTrends?tickers=AAPL,MSFT&from=2024-01-01',
        description: '2024년 이후 AAPL/MSFT 이벤트만 계산'
      },
    ],
    phases: [
      {
        id: 'load_policies',
        title: '1. 정책 로드',
        description: 'fillPriceTrend_dateRange (-14~+14 trading days) 정책',
        apiId: null,
        note: 'DB 쿼리 (API 아님)'
      },
      {
        id: 'load_events',
        title: '2. 이벤트 & 거래 로드 & 그룹화',
        description: 'txn_events에서 이벤트 + txn_trades에서 txn_events에 없는 거래 조회 → 티커별 그룹화',
        apiId: null,
        note: 'DB 쿼리 2개 (API 아님). 거래와 이벤트 모두 price trend 계산 대상'
      },
      {
        id: 'cache_trading_days',
        title: '3. Trading Days 전역 캐싱 (CRITICAL)',
        description: '전체 기간의 모든 거래일을 1회 DB 쿼리로 로드',
        apiId: null,
        note: '⚡ 핵심 최적화: 100개 이벤트 처리 시 100회 쿼리 → 1회 쿼리로 단축! config_lv3_market_holidays 테이블 사용'
      },
      {
        id: 'calc_ohlc_ranges',
        title: '4. OHLC 페치 범위 계산',
        description: '티커별 min/max event_date 기준으로 필요한 날짜 범위 계산',
        apiId: null,
        note: '±14 trading days = 약 ±25 calendar days (주말/휴일 포함) + 15일 버퍼'
      },
      {
        id: 'fetch_ohlc',
        title: '5. OHLC 데이터 티커별 캐싱',
        description: '티커당 1회 API 호출 → 모든 이벤트가 캐시 재사용',
        apiId: 'fmp-historical-price-eod-full',
        requiredKeys: ['date', 'open', 'high', 'low', 'close'],
        configKey: 'generatePriceTrends.ohlc',
        note: '티커당 1 API call × 10 티커 = 10 API calls total (100개 이벤트에 대해)'
      },
      {
        id: 'event_processing',
        title: '6. 이벤트별 처리 (캐시 사용)',
        description: '각 이벤트: dayOffset 날짜 계산 → OHLC 매핑 → 성과 계산',
        apiId: null,
        note: '100개 이벤트 처리해도 추가 API 호출 0개 (모두 캐시 사용)'
      },
      {
        id: 'calc_dayoffset_dates',
        title: '7. dayOffset 날짜 계산',
        description: 'event_date 기준 -14~+14 trading days 계산',
        apiId: null,
        note: '캐시된 trading_days_set 사용 (O(1) lookup)'
      },
      {
        id: 'map_ohlc',
        title: '8. OHLC 데이터 매핑',
        description: '각 dayOffset 날짜에 대응하는 OHLC 데이터 조회',
        apiId: null,
        note: '캐시된 ohlc_cache 사용 (API 호출 없음)'
      },
      {
        id: 'forward_backward_fill',
        title: '9. Forward/Backward Fill',
        description: '휴일로 OHLC 누락 시 인접 거래일 데이터로 채우기',
        apiId: null,
        note: 'neg offset: backward fill (이전 거래일), pos offset: forward fill (다음 거래일)'
      },
      {
        id: 'calc_performance',
        title: '10. 성과(Performance) 계산',
        description: 'D0(event_date) close 대비 각 dayOffset의 수익률',
        apiId: null,
        note: 'performance = (close - d0_close) / d0_close'
      },
      {
        id: 'build_jsonb',
        title: '11. JSONB 컬럼 생성',
        description: '29개 컬럼 생성 (d_neg_14 ~ d_pos_14)',
        apiId: null,
        note: '각 컬럼: {targetDate, price_trend{ohlc}, dayOffset0{close}, performance{close}}'
      },
      {
        id: 'batch_upsert',
        title: '12. 배치 UPSERT',
        description: 'txn_price_trend 테이블 일괄 UPSERT (티커당 1회)',
        apiId: null,
        note: 'PostgreSQL UNNEST 패턴 사용: 100개 이벤트를 단일 쿼리로 처리'
      }
    ],
    outputs: [
      'd_neg_14 ~ d_neg_1 (14 JSONB columns)',
      'd_0 (JSONB column)',
      'd_pos_1 ~ d_pos_14 (14 JSONB columns)',
      '각 JSONB: {targetDate, price_trend{low,high,open,close}, dayOffset0{close}, performance{close}}'
    ]
  },
  trades: {
    id: 'trades',
    title: 'POST /trades',
    description: 'txn_trades 테이블에 실제 거래 기록 벌크 삽입 (성과 추적용)',
    performanceNote: 'Unique key: (ticker, trade_date, model). 중복 시 UPSERT로 기존 레코드 업데이트',
    bodyStructure: {
      description: 'JSON 배열로 여러 거래 기록을 한번에 삽입',
      example: {
        trades: [
          {
            ticker: 'AAPL',
            trade_date: '2024-01-15',
            model: 'default',
            source: 'consensus',
            position: 'long',
            entry_price: 185.50,
            exit_price: null,
            quantity: 100,
            notes: 'Entry based on consensus signal'
          }
        ]
      },
      fields: [
        { name: 'ticker', type: 'string', required: true, description: '종목 심볼 (예: AAPL, MSFT)' },
        { name: 'trade_date', type: 'date', required: true, description: '거래 실행 날짜 (YYYY-MM-DD)' },
        { name: 'model', type: 'string', required: false, default: 'default', description: '거래 모델/전략 식별자' },
        { name: 'source', type: 'string', required: false, description: '이벤트 소스: consensus 또는 earning' },
        { name: 'position', type: 'string', required: false, description: '포지션: long, short, 또는 neutral' },
        { name: 'entry_price', type: 'number', required: false, description: '진입 가격 (선택)' },
        { name: 'exit_price', type: 'number', required: false, description: '청산 가격 (선택)' },
        { name: 'quantity', type: 'integer', required: false, description: '거래 수량 (선택)' },
        { name: 'notes', type: 'string', required: false, description: '추가 메모 (선택)' }
      ]
    },
    phases: [
      {
        id: 'validate',
        title: '1. 요청 검증',
        description: 'Pydantic 모델로 거래 데이터 검증 (source: consensus/earning, position: long/short/neutral)'
      },
      {
        id: 'bulk_upsert',
        title: '2. 벌크 UPSERT',
        description: 'PostgreSQL UNNEST 패턴 사용, ON CONFLICT (ticker, trade_date, model) DO UPDATE',
        note: '중복 키 발생 시 source, position, prices, quantity, notes 업데이트'
      }
    ],
    integration: [
      {
        endpoint: 'POST /generatePriceTrends',
        description: 'txn_events에 없고 txn_trades에만 존재하는 ticker, trade_date 조합에 대해 가격 추세 데이터 생성',
        note: '거래 기록도 이벤트처럼 가격 추세 분석 가능'
      }
    ],
    outputs: [
      'txn_trades 테이블에 레코드 삽입/업데이트',
      'Primary key: (ticker, trade_date, model)',
      'Indexes: ticker, trade_date, model, (ticker, trade_date)'
    ]
  },
  setEventsTable: {
    id: 'setEventsTable',
    title: 'POST /setEventsTable',
    description: 'evt_* 테이블의 데이터를 txn_events 테이블로 통합',
    parameters: [
      {
        name: 'schema',
        type: 'string',
        required: false,
        default: 'public',
        description: '검색할 스키마 이름. evt_* 테이블을 자동 탐색'
      },
      {
        name: 'table',
        type: 'string',
        required: false,
        description: '특정 evt_* 테이블만 처리 (쉼표 구분 가능, 예: "evt_consensus,evt_earning"). 미지정 시 스키마 내 모든 evt_* 테이블 처리'
      },
      {
        name: 'overwrite',
        type: 'boolean',
        required: false,
        default: 'false',
        description: 'sector/industry 업데이트 모드: false=NULL만 채우기, true=불일치도 수정'
      },
      {
        name: 'dryRun',
        type: 'boolean',
        required: false,
        default: 'false',
        description: 'true면 변경사항만 표시하고 실제 DB 수정 없음 (테스트용)'
      },
    ],
    usageExamples: [
      {
        title: '기본: 모든 evt_* 테이블 통합',
        url: 'POST /setEventsTable',
        description: 'public 스키마의 모든 evt_* 테이블을 txn_events로 통합'
      },
      {
        title: '특정 테이블만 통합',
        url: 'POST /setEventsTable?table=evt_consensus',
        description: 'evt_consensus 테이블만 처리'
      },
      {
        title: '여러 테이블 통합',
        url: 'POST /setEventsTable?table=evt_consensus,evt_earning',
        description: 'evt_consensus, evt_earning 테이블 처리'
      },
      {
        title: 'Dry Run (테스트)',
        url: 'POST /setEventsTable?dryRun=true',
        description: '변경사항만 확인, 실제 수정 없음'
      },
      {
        title: 'sector/industry 강제 수정',
        url: 'POST /setEventsTable?overwrite=true',
        description: 'NULL뿐만 아니라 불일치하는 sector/industry도 수정'
      },
    ],
    phases: [
      {
        id: 'query_source',
        title: '1. 소스 조회',
        description: 'evt_consensus 또는 evt_earning에서 이벤트 조회',
        apiId: null
      },
      {
        id: 'enrich',
        title: '2. 데이터 보강',
        description: 'sector, industry 정보 추가 (config_lv3_targets)',
        apiId: null
      },
      {
        id: 'upsert',
        title: '3. UPSERT',
        description: 'txn_events 테이블에 INSERT/UPDATE',
        apiId: null
      }
    ]
  }
};

/**
 * PhaseNode - 단일 Phase 노드
 */
function PhaseNode({ phase, onApiClick, isLast }) {
  const hasApi = phase.apiId !== null;
  
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
      {/* Phase 박스 */}
      <div
        style={{
          padding: 'var(--space-3)',
          backgroundColor: hasApi ? '#dbeafe' : 'var(--bg-secondary)',
          border: `2px solid ${hasApi ? '#3b82f6' : 'var(--border)'}`,
          borderRadius: 'var(--rounded-lg)',
          minWidth: '200px',
          maxWidth: '280px',
          textAlign: 'center',
          position: 'relative',
        }}
      >
        <div style={{ fontWeight: 'var(--font-semibold)', fontSize: 'var(--text-sm)', marginBottom: '4px' }}>
          {phase.title}
        </div>
        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)', marginBottom: hasApi ? '8px' : '0' }}>
          {phase.description}
        </div>
        
        {/* API 버튼 (있는 경우) */}
        {hasApi && (
          <button
            onClick={() => onApiClick(phase)}
            style={{
              marginTop: '8px',
              padding: '6px 12px',
              backgroundColor: '#1e40af',
              color: 'white',
              border: 'none',
              borderRadius: 'var(--rounded)',
              fontSize: 'var(--text-xs)',
              fontFamily: 'monospace',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '6px',
              width: '100%',
            }}
            title="클릭하여 API 변경"
          >
            <span>🔌</span>
            <span>{phase.apiId}</span>
            <span style={{ opacity: 0.7 }}>✏️</span>
          </button>
        )}
        
        {/* 스킵 조건 (있는 경우) */}
        {phase.skipCondition && (
          <div style={{ 
            marginTop: '8px', 
            padding: '4px 8px', 
            backgroundColor: '#fef3c7', 
            borderRadius: 'var(--rounded)',
            fontSize: 'var(--text-xs)',
            color: '#92400e'
          }}>
            ⚡ {phase.skipCondition}
          </div>
        )}
        
        {/* 노트 (있는 경우) */}
        {phase.note && (
          <div style={{ 
            marginTop: '8px', 
            fontSize: 'var(--text-xs)', 
            color: 'var(--text-dim)',
            fontStyle: 'italic'
          }}>
            💡 {phase.note}
          </div>
        )}
      </div>
      
      {/* 화살표 (마지막 아님) */}
      {!isLast && (
        <div style={{ 
          height: '30px', 
          display: 'flex', 
          flexDirection: 'column', 
          alignItems: 'center',
          justifyContent: 'center',
          color: 'var(--text-dim)'
        }}>
          <div style={{ width: '2px', height: '15px', backgroundColor: 'var(--border)' }} />
          <div>▼</div>
        </div>
      )}
    </div>
  );
}

/**
 * SubPhaseGroup - 병렬 실행되는 하위 Phase들
 */
function SubPhaseGroup({ subPhases, onApiClick }) {
  return (
    <div style={{ 
      display: 'flex', 
      gap: 'var(--space-2)', 
      justifyContent: 'center',
      flexWrap: 'wrap',
      padding: 'var(--space-2)',
      backgroundColor: 'rgba(59, 130, 246, 0.05)',
      borderRadius: 'var(--rounded-lg)',
      border: '1px dashed var(--border)'
    }}>
      {subPhases.map((subPhase) => (
        <div
          key={subPhase.id}
          style={{
            padding: 'var(--space-2)',
            backgroundColor: '#dbeafe',
            border: '1px solid #93c5fd',
            borderRadius: 'var(--rounded)',
            minWidth: '140px',
            textAlign: 'center',
          }}
        >
          <div style={{ fontSize: 'var(--text-xs)', fontWeight: 'var(--font-semibold)', marginBottom: '4px' }}>
            {subPhase.title}
          </div>
          <button
            onClick={() => onApiClick(subPhase)}
            style={{
              padding: '4px 8px',
              backgroundColor: '#1e40af',
              color: 'white',
              border: 'none',
              borderRadius: 'var(--rounded)',
              fontSize: '10px',
              fontFamily: 'monospace',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '4px',
              width: '100%',
            }}
            title="클릭하여 API 변경"
          >
            <span>{subPhase.apiId}</span>
            <span style={{ opacity: 0.7 }}>✏️</span>
          </button>
        </div>
      ))}
    </div>
  );
}

/**
 * EndpointFlowDiagram - 엔드포인트 흐름도
 */
function EndpointFlowDiagram({ endpoint, onApiClick }) {
  const [selectedMode, setSelectedMode] = useState(
    endpoint.modes ? Object.keys(endpoint.modes)[0] : null
  );
  
  const currentFlow = endpoint.modes 
    ? endpoint.modes[selectedMode]
    : { phases: endpoint.phases };

  return (
    <div style={{
      backgroundColor: 'var(--bg-secondary)',
      border: '1px solid var(--border)',
      borderRadius: 'var(--rounded-lg)',
      padding: 'var(--space-4)',
      marginBottom: 'var(--space-4)',
    }}>
      {/* 헤더 */}
      <div style={{ marginBottom: 'var(--space-4)' }}>
        <h3 style={{ margin: 0, fontSize: 'var(--text-xl)', color: 'var(--accent-primary)' }}>
          {endpoint.title}
        </h3>
        <p style={{ margin: 'var(--space-1) 0 0 0', fontSize: 'var(--text-sm)', color: 'var(--text-secondary)' }}>
          {endpoint.description}
        </p>
      </div>

      {/* 파라미터 상세 */}
      <div style={{ marginBottom: 'var(--space-4)' }}>
        <div style={{ fontSize: 'var(--text-sm)', fontWeight: 'var(--font-semibold)', color: 'var(--ink)', marginBottom: '8px' }}>
          📋 Parameters
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {endpoint.parameters.map((param) => (
            <div
              key={param.name}
              style={{
                padding: 'var(--space-2)',
                backgroundColor: param.deprecated ? '#fef3c7' : param.required ? '#fee2e2' : '#f9fafb',
                border: `1px solid ${param.deprecated ? '#fcd34d' : param.required ? '#fca5a5' : '#e5e7eb'}`,
                borderRadius: 'var(--rounded)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                <code style={{
                  fontSize: 'var(--text-sm)',
                  fontWeight: 'var(--font-semibold)',
                  color: param.deprecated ? '#92400e' : param.required ? '#991b1b' : 'var(--ink)'
                }}>
                  {param.name}
                </code>
                <span style={{
                  fontSize: 'var(--text-xs)',
                  color: 'var(--text-dim)',
                  fontFamily: 'monospace'
                }}>
                  {param.type}
                </span>
                {param.required && (
                  <span style={{ fontSize: 'var(--text-xs)', color: '#991b1b', fontWeight: 'var(--font-semibold)' }}>
                    REQUIRED
                  </span>
                )}
                {param.deprecated && (
                  <span style={{ fontSize: 'var(--text-xs)', color: '#92400e', fontWeight: 'var(--font-semibold)' }}>
                    DEPRECATED
                  </span>
                )}
                {param.default && (
                  <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)' }}>
                    default: {param.default}
                  </span>
                )}
              </div>
              {param.options && (
                <div style={{ marginBottom: '4px' }}>
                  <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)' }}>
                    Options: {param.options.map((opt, idx) => (
                      <code key={idx} style={{
                        backgroundColor: 'white',
                        padding: '2px 4px',
                        margin: '0 2px',
                        borderRadius: '2px',
                        fontSize: 'var(--text-xs)'
                      }}>
                        {opt}
                      </code>
                    ))}
                  </span>
                </div>
              )}
              {param.description && (
                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}>
                  {param.description}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* 동작 매트릭스 (있는 경우) */}
      {endpoint.behaviorMatrix && (
        <div style={{ marginBottom: 'var(--space-4)' }}>
          <div style={{ fontSize: 'var(--text-sm)', fontWeight: 'var(--font-semibold)', color: 'var(--ink)', marginBottom: '8px' }}>
            🎯 Parameter Behavior Matrix
          </div>
          <div style={{
            overflowX: 'auto',
            backgroundColor: 'var(--bg-primary)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--rounded)'
          }}>
            <table style={{
              width: '100%',
              fontSize: 'var(--text-xs)',
              borderCollapse: 'collapse'
            }}>
              <thead>
                <tr style={{ backgroundColor: '#f3f4f6' }}>
                  <th style={{ padding: '8px', textAlign: 'left', borderBottom: '2px solid var(--border)', fontWeight: 'var(--font-semibold)' }}>
                    metrics
                  </th>
                  <th style={{ padding: '8px', textAlign: 'left', borderBottom: '2px solid var(--border)', fontWeight: 'var(--font-semibold)' }}>
                    overwrite
                  </th>
                  <th style={{ padding: '8px', textAlign: 'left', borderBottom: '2px solid var(--border)', fontWeight: 'var(--font-semibold)' }}>
                    동작
                  </th>
                </tr>
              </thead>
              <tbody>
                {endpoint.behaviorMatrix.map((row, idx) => (
                  <tr key={idx} style={{ backgroundColor: idx % 2 === 0 ? 'white' : '#f9fafb' }}>
                    <td style={{ padding: '8px', borderBottom: '1px solid #e5e7eb', fontFamily: 'monospace' }}>
                      {row.metrics}
                    </td>
                    <td style={{ padding: '8px', borderBottom: '1px solid #e5e7eb', fontFamily: 'monospace' }}>
                      {row.overwrite}
                    </td>
                    <td style={{ padding: '8px', borderBottom: '1px solid #e5e7eb' }}>
                      {row.behavior}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* 사용 예시 (있는 경우) */}
      {endpoint.usageExamples && (
        <div style={{ marginBottom: 'var(--space-4)' }}>
          <div style={{ fontSize: 'var(--text-sm)', fontWeight: 'var(--font-semibold)', color: 'var(--ink)', marginBottom: '8px' }}>
            💡 Usage Examples
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {endpoint.usageExamples.map((example, idx) => (
              <div
                key={idx}
                style={{
                  padding: 'var(--space-2)',
                  backgroundColor: '#eff6ff',
                  border: '1px solid #bfdbfe',
                  borderRadius: 'var(--rounded)',
                }}
              >
                <div style={{ fontSize: 'var(--text-sm)', fontWeight: 'var(--font-semibold)', color: '#1e40af', marginBottom: '4px' }}>
                  {idx + 1}. {example.title}
                </div>
                <code style={{
                  display: 'block',
                  padding: '6px 8px',
                  backgroundColor: 'white',
                  borderRadius: 'var(--rounded)',
                  fontSize: 'var(--text-xs)',
                  fontFamily: 'monospace',
                  color: '#1e3a8a',
                  marginBottom: '4px',
                  overflowX: 'auto',
                  whiteSpace: 'nowrap'
                }}>
                  {example.url}
                </code>
                <div style={{ fontSize: 'var(--text-xs)', color: '#1e40af' }}>
                  → {example.description}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 모드 선택 (있는 경우) */}
      {endpoint.modes && (
        <div style={{ marginBottom: 'var(--space-4)' }}>
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)', marginBottom: '8px' }}>
            mode 선택:
          </div>
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            {Object.entries(endpoint.modes).map(([modeKey, mode]) => (
              <button
                key={modeKey}
                onClick={() => setSelectedMode(modeKey)}
                style={{
                  padding: '8px 16px',
                  backgroundColor: selectedMode === modeKey ? '#1e40af' : 'white',
                  color: selectedMode === modeKey ? 'white' : 'var(--ink)',
                  border: `2px solid ${selectedMode === modeKey ? '#1e40af' : 'var(--border)'}`,
                  borderRadius: 'var(--rounded)',
                  cursor: 'pointer',
                  fontSize: 'var(--text-sm)',
                }}
              >
                <div style={{ fontWeight: 'var(--font-semibold)' }}>{modeKey}</div>
                <div style={{ fontSize: 'var(--text-xs)', opacity: 0.8 }}>{mode.description}</div>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* 흐름도 */}
      <div style={{ 
        padding: 'var(--space-4)', 
        backgroundColor: 'var(--bg-primary)', 
        borderRadius: 'var(--rounded-lg)',
        border: '1px solid var(--border)',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
      }}>
        <div style={{ 
          fontSize: 'var(--text-xs)', 
          color: 'var(--text-dim)', 
          marginBottom: 'var(--space-3)',
          textAlign: 'center',
          width: '100%',
          borderBottom: '1px solid var(--border)',
          paddingBottom: 'var(--space-2)',
        }}>
          {selectedMode && (
            <>
              <strong>mode={selectedMode}</strong>
              {endpoint.modes[selectedMode].outputTable && (
                <span> → {endpoint.modes[selectedMode].outputTable}</span>
              )}
            </>
          )}
        </div>

        {currentFlow.phases.map((phase, idx) => (
          <React.Fragment key={phase.id}>
            {phase.subPhases ? (
              <>
                <div style={{ 
                  padding: 'var(--space-2)', 
                  backgroundColor: 'var(--bg-secondary)',
                  borderRadius: 'var(--rounded-lg)',
                  textAlign: 'center',
                  marginBottom: '8px',
                  minWidth: '200px',
                }}>
                  <div style={{ fontWeight: 'var(--font-semibold)', fontSize: 'var(--text-sm)' }}>
                    {phase.title}
                  </div>
                  <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}>
                    {phase.description}
                  </div>
                </div>
                <SubPhaseGroup subPhases={phase.subPhases} onApiClick={onApiClick} />
                {idx < currentFlow.phases.length - 1 && (
                  <div style={{ height: '30px', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', color: 'var(--text-dim)' }}>
                    <div style={{ width: '2px', height: '15px', backgroundColor: 'var(--border)' }} />
                    <div>▼</div>
                  </div>
                )}
              </>
            ) : (
              <PhaseNode 
                phase={phase} 
                onApiClick={onApiClick}
                isLast={idx === currentFlow.phases.length - 1}
              />
            )}
          </React.Fragment>
        ))}
      </div>

      {/* 출력 (있는 경우) */}
      {endpoint.outputs && (
        <div style={{ marginTop: 'var(--space-3)' }}>
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)', marginBottom: '8px' }}>
            출력 컬럼:
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
            {endpoint.outputs.map((output) => (
              <span
                key={output}
                style={{
                  padding: '4px 8px',
                  backgroundColor: '#d1fae5',
                  borderRadius: 'var(--rounded)',
                  fontSize: 'var(--text-xs)',
                  fontFamily: 'monospace',
                  color: '#065f46',
                }}
              >
                {output}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * APIChangeModal - API 변경 모달
 */
function APIChangeModal({ phase, apiList, onClose, onSave }) {
  const [selectedApiId, setSelectedApiId] = useState(phase.apiId);
  const [validationResult, setValidationResult] = useState(null);

  const validateSchemaKeys = (apiId) => {
    const api = apiList.find(a => a.id === apiId);
    if (!api) {
      return { valid: false, error: `API '${apiId}' not found` };
    }

    let schemaKeys = [];
    if (api.schema) {
      if (typeof api.schema === 'object') {
        schemaKeys = Object.keys(api.schema);
      } else if (typeof api.schema === 'string') {
        try {
          const parsed = JSON.parse(api.schema);
          schemaKeys = Object.keys(parsed);
        } catch {
          return { valid: false, error: 'Invalid schema format' };
        }
      }
    }

    const missingKeys = phase.requiredKeys.filter(key => !schemaKeys.includes(key));
    
    return {
      valid: missingKeys.length === 0,
      schemaKeys,
      requiredKeys: phase.requiredKeys,
      missingKeys,
      api
    };
  };

  const handleValidate = () => {
    const result = validateSchemaKeys(selectedApiId);
    setValidationResult(result);
  };

  const handleSave = () => {
    if (validationResult?.valid) {
      onSave(phase.configKey, selectedApiId);
      onClose();
    }
  };

  return (
    <div
      style={{
        position: 'fixed',
        top: 0, left: 0, right: 0, bottom: 0,
        backgroundColor: 'rgba(0,0,0,0.5)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000
      }}
      onClick={onClose}
    >
      <div
        style={{
          backgroundColor: 'white',
          borderRadius: 'var(--rounded-lg)',
          padding: 'var(--space-4)',
          minWidth: '550px',
          maxWidth: '90%',
          maxHeight: '80vh',
          overflow: 'auto'
        }}
        onClick={e => e.stopPropagation()}
      >
        <h3 style={{ marginTop: 0, color: 'var(--ink)' }}>
          🔌 API 변경: {phase.title}
        </h3>
        <p style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)' }}>
          {phase.description}
        </p>
        
        {/* 현재 API */}
        <div style={{ marginBottom: 'var(--space-3)' }}>
          <label style={{ display: 'block', marginBottom: '4px', fontSize: 'var(--text-sm)', fontWeight: 'var(--font-semibold)', color: 'var(--ink)' }}>
            현재 API
          </label>
          <div style={{ 
            padding: 'var(--space-2)', 
            backgroundColor: '#f3f4f6', 
            borderRadius: 'var(--rounded)',
            fontFamily: 'monospace',
            fontSize: 'var(--text-sm)',
            color: 'var(--ink)'
          }}>
            {phase.apiId}
          </div>
        </div>

        {/* 필수 키 */}
        <div style={{ marginBottom: 'var(--space-3)' }}>
          <label style={{ display: 'block', marginBottom: '4px', fontSize: 'var(--text-sm)', fontWeight: 'var(--font-semibold)', color: 'var(--ink)' }}>
            필수 응답 키 (Schema에 존재해야 함)
          </label>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
            {phase.requiredKeys.map(key => (
              <span 
                key={key}
                style={{
                  padding: '4px 8px',
                  backgroundColor: '#fef3c7',
                  borderRadius: 'var(--rounded)',
                  fontSize: 'var(--text-xs)',
                  fontFamily: 'monospace',
                  color: '#92400e'
                }}
              >
                {key}
              </span>
            ))}
          </div>
        </div>

        {/* 새 API 선택 */}
        <div style={{ marginBottom: 'var(--space-3)' }}>
          <label style={{ display: 'block', marginBottom: '4px', fontSize: 'var(--text-sm)', fontWeight: 'var(--font-semibold)', color: 'var(--ink)' }}>
            새 API 선택
          </label>
          <select
            value={selectedApiId}
            onChange={(e) => {
              setSelectedApiId(e.target.value);
              setValidationResult(null);
            }}
            style={{
              width: '100%',
              padding: 'var(--space-2)',
              borderRadius: 'var(--rounded)',
              border: '1px solid #d1d5db',
              fontSize: 'var(--text-sm)',
              backgroundColor: 'white',
              color: 'var(--ink)'
            }}
          >
            {apiList.map(api => (
              <option key={api.id} value={api.id}>
                [{api.api_service}] {api.id}
              </option>
            ))}
          </select>
        </div>

        {/* 검증 결과 */}
        {validationResult && (
          <div
            style={{
              padding: 'var(--space-3)',
              borderRadius: 'var(--rounded)',
              backgroundColor: validationResult.valid ? '#d1fae5' : '#fee2e2',
              marginBottom: 'var(--space-3)'
            }}
          >
            <div style={{ fontWeight: 'var(--font-semibold)', marginBottom: '8px', color: validationResult.valid ? '#065f46' : '#991b1b' }}>
              {validationResult.valid ? '✅ 검증 성공' : '❌ 검증 실패'}
            </div>
            
            {validationResult.schemaKeys && (
              <div style={{ fontSize: 'var(--text-sm)' }}>
                <div style={{ color: '#374151', marginBottom: '4px' }}>Schema 키 ({validationResult.schemaKeys.length}개):</div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px', maxHeight: '100px', overflow: 'auto' }}>
                  {validationResult.schemaKeys.map(key => {
                    const isRequired = validationResult.requiredKeys.includes(key);
                    return (
                      <span 
                        key={key}
                        style={{
                          padding: '2px 6px',
                          backgroundColor: isRequired ? '#d1fae5' : '#f3f4f6',
                          borderRadius: 'var(--rounded)',
                          fontSize: 'var(--text-xs)',
                          fontFamily: 'monospace',
                          color: isRequired ? '#065f46' : '#6b7280'
                        }}
                      >
                        {key}
                      </span>
                    );
                  })}
                </div>
              </div>
            )}
            
            {validationResult.missingKeys?.length > 0 && (
              <div style={{ color: '#991b1b', marginTop: '8px', fontSize: 'var(--text-sm)' }}>
                <strong>누락된 필수 키:</strong> {validationResult.missingKeys.join(', ')}
              </div>
            )}
            
            {validationResult.error && (
              <div style={{ color: '#991b1b', fontSize: 'var(--text-sm)' }}>
                {validationResult.error}
              </div>
            )}
          </div>
        )}

        {/* 버튼 */}
        <div style={{ display: 'flex', gap: 'var(--space-2)', justifyContent: 'flex-end' }}>
          <button onClick={onClose} className="btn btn-outline">
            취소
          </button>
          <button 
            onClick={handleValidate} 
            className="btn btn-outline"
            disabled={!selectedApiId || selectedApiId === phase.apiId}
          >
            🔍 Schema 검증
          </button>
          <button 
            onClick={handleSave} 
            className="btn btn-primary"
            disabled={!validationResult?.valid}
          >
            💾 저장
          </button>
        </div>
      </div>
    </div>
  );
}

/**
 * SetRequestsPage component.
 */
export default function SetRequestsPage() {
  const [apiList, setApiList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedPhase, setSelectedPhase] = useState(null);
  const [savedConfig, setSavedConfig] = useState({});
  const [selectedEndpoint, setSelectedEndpoint] = useState(Object.keys(ENDPOINT_FLOWS)[0]); // Default to first endpoint
  const [headerHeight, setHeaderHeight] = useState(52); // State for header height

  const fetchApiList = useCallback(async () => {
    try {
      setLoading(true);
      const response = await fetch(`${API_BASE_URL}/control/apiList`);
      if (!response.ok) throw new Error('Failed to fetch API list');
      const data = await response.json();
      setApiList(data);
    } catch (err) {
      console.error('Failed to fetch API list:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchApiList();
    // Load saved config
    const saved = localStorage.getItem('endpointApiConfig');
    if (saved) {
      setSavedConfig(JSON.parse(saved));
    }
  }, [fetchApiList]);

  // Dynamically measure navigation height
  useEffect(() => {
    const measureNavHeight = () => {
      const nav = document.querySelector('nav');
      if (nav) {
        setHeaderHeight(nav.offsetHeight);
      }
    };

    measureNavHeight();
    window.addEventListener('resize', measureNavHeight);
    return () => window.removeEventListener('resize', measureNavHeight);
  }, []);

  const handleApiClick = (phase) => {
    if (phase.apiId && phase.requiredKeys) {
      setSelectedPhase(phase);
    }
  };

  const handleSaveConfig = (configKey, newApiId) => {
    const newConfig = { ...savedConfig, [configKey]: newApiId };
    setSavedConfig(newConfig);
    localStorage.setItem('endpointApiConfig', JSON.stringify(newConfig));
  };

  if (loading) {
    return (
      <div style={{ textAlign: 'center' }}>
        Loading...
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', minHeight: '100vh', position: 'relative' }}>
      {/* Left Sidebar */}
      <div style={{
        width: '250px',
        position: 'fixed',
        top: `${headerHeight}px`,
        left: 0,
        height: `calc(100vh - ${headerHeight}px)`,
        backgroundColor: '#f8fafc',
        borderRight: '1px solid #e2e8f0',
        overflowY: 'auto',
        padding: 'var(--space-4)',
        zIndex: 100
      }}>
        <h2 style={{
          fontSize: 'var(--text-lg)',
          fontWeight: 'var(--font-semibold)',
          marginBottom: 'var(--space-4)',
          color: '#1e293b'
        }}>
          Endpoints
        </h2>
        <nav style={{ marginTop: '20px' }}>
          {Object.values(ENDPOINT_FLOWS).map((endpoint) => (
            <button
              key={endpoint.id}
              onClick={() => setSelectedEndpoint(endpoint.id)}
              style={{
                display: 'block',
                width: '100%',
                textAlign: 'left',
                padding: 'var(--space-2) var(--space-3)',
                marginBottom: 'var(--space-1)',
                backgroundColor: selectedEndpoint === endpoint.id ? '#3b82f6' : 'transparent',
                color: selectedEndpoint === endpoint.id ? 'white' : '#475569',
                border: 'none',
                borderRadius: '10px',
                cursor: 'pointer',
                fontSize: 'var(--text-sm)',
                fontWeight: selectedEndpoint === endpoint.id ? 'var(--font-semibold)' : 'normal',
                transition: 'all 0.2s'
              }}
              onMouseEnter={(e) => {
                if (selectedEndpoint !== endpoint.id) {
                  e.target.style.backgroundColor = '#e2e8f0';
                }
              }}
              onMouseLeave={(e) => {
                if (selectedEndpoint !== endpoint.id) {
                  e.target.style.backgroundColor = 'transparent';
                }
              }}
            >
              {endpoint.title}
            </button>
          ))}
        </nav>
      </div>

      {/* Main Content */}
      <div style={{ marginLeft: '250px', flex: 1, padding: 'var(--space-4)' }}>
        <header style={{ marginBottom: 'var(--space-4)' }}>
          <h1>Request Settings</h1>
          <p style={{ color: 'var(--text-dim)', fontSize: 'var(--text-sm)' }}>
            엔드포인트 흐름도 - 각 단계의 🔌 API 버튼을 클릭하여 변경할 수 있습니다
          </p>
        </header>

        {/* 안내 */}
        <div style={{
          padding: 'var(--space-3)',
          backgroundColor: '#eff6ff',
          borderRadius: 'var(--rounded)',
          border: '1px solid #bfdbfe',
          marginBottom: 'var(--space-4)'
        }}>
          <div style={{ fontWeight: 'var(--font-semibold)', color: '#1e40af', marginBottom: '4px' }}>
            💡 사용 방법
          </div>
          <ol style={{ margin: 0, paddingLeft: '20px', fontSize: 'var(--text-sm)', color: '#1e3a8a' }}>
            <li>좌측 메뉴에서 엔드포인트 선택</li>
            <li>파란색 <strong>🔌 API 버튼</strong>을 클릭하여 변경 모달 열기</li>
            <li>새 API 선택 → <strong>Schema 검증</strong> → 필수 키 존재 확인</li>
            <li>검증 성공 시 <strong>저장</strong> (API 호출 없이 즉시 검증)</li>
          </ol>
        </div>

        {/* Selected Endpoint Flow Diagram */}
        {ENDPOINT_FLOWS[selectedEndpoint] && (
          <EndpointFlowDiagram
            key={selectedEndpoint}
            endpoint={ENDPOINT_FLOWS[selectedEndpoint]}
            onApiClick={handleApiClick}
          />
        )}

        {/* API 변경 모달 */}
        {selectedPhase && (
          <APIChangeModal
            phase={selectedPhase}
            apiList={apiList}
            onClose={() => setSelectedPhase(null)}
            onSave={handleSaveConfig}
          />
        )}
      </div>
    </div>
  );
}
