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
    description: '외부 FMP API에서 금융 데이터를 수집하여 DB에 저장',
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
        description: '분석 대상 종목 수집',
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
          }
        ]
      }
    }
  },
  backfillEventsTable: {
    id: 'backfillEventsTable',
    title: 'POST /backfillEventsTable',
    description: 'txn_events 테이블의 이벤트에 valuation metrics 계산',
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
        name: 'calcFairValue',
        type: 'boolean',
        required: false,
        default: 'true',
        deprecated: true,
        description: '[DEPRECATED - I-41] 업종 평균 적정가 계산 → metrics=priceQuantitative 사용 권장'
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
    ],
    phases: [
      {
        id: 'load_metrics',
        title: '1. 메트릭 정의 로드',
        description: 'config_lv2_metric에서 정의 로드',
        apiId: null
      },
      {
        id: 'load_events',
        title: '2. 이벤트 로드',
        description: 'txn_events에서 대상 이벤트 조회',
        apiId: null
      },
      {
        id: 'group_tickers',
        title: '3. 티커 그룹화',
        description: '이벤트를 티커별로 그룹화 (병렬 처리 준비)',
        apiId: null
      },
      {
        id: 'calc_quantitative',
        title: '4. Quantitative 계산',
        description: '재무제표, 시가총액 기반 정량 메트릭',
        subPhases: [
          {
            id: 'income',
            title: '손익계산서',
            apiId: 'fmp-income-statement',
            requiredKeys: ['date', 'revenue', 'grossProfit', 'operatingIncome', 'netIncome', 'researchAndDevelopmentExpenses'],
            configKey: 'backfill.income'
          },
          {
            id: 'balance',
            title: '재무상태표',
            apiId: 'fmp-balance-sheet-statement',
            requiredKeys: ['date', 'totalAssets', 'totalLiabilities', 'totalEquity', 'totalCurrentAssets', 'totalCurrentLiabilities'],
            configKey: 'backfill.balance'
          },
          {
            id: 'marketcap',
            title: '시가총액',
            apiId: 'fmp-historical-market-capitalization',
            requiredKeys: ['date', 'marketCap'],
            configKey: 'backfill.marketcap'
          }
        ]
      },
      {
        id: 'calc_qualitative',
        title: '5. Qualitative 계산',
        description: 'consensusSignal, targetSummary 등 정성 메트릭',
        note: 'evt_consensus.target_summary 읽기 (I-31)',
        apiId: null
      },
      {
        id: 'calc_price_trend',
        title: '6. Price Trend 계산',
        description: '±14일 OHLC 가격 추세',
        apiId: 'fmp-historical-price-eod-full',
        requiredKeys: ['date', 'open', 'high', 'low', 'close'],
        configKey: 'backfill.priceTrend'
      },
      {
        id: 'batch_update',
        title: '7. 배치 업데이트',
        description: 'txn_events 테이블 일괄 UPDATE (UNNEST)',
        apiId: null
      }
    ],
    outputs: [
      'value_quantitative (PER, PBR, PSR, evEBITDA, ROE, ...)',
      'value_qualitative (targetMedian, targetSummary, consensusSignal)',
      'position_quantitative, position_qualitative',
      'disparity_quantitative, disparity_qualitative',
      'price_trend'
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
    <>
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
          <li>엔드포인트의 mode를 선택하여 해당 흐름도 확인</li>
          <li>파란색 <strong>🔌 API 버튼</strong>을 클릭하여 변경 모달 열기</li>
          <li>새 API 선택 → <strong>Schema 검증</strong> → 필수 키 존재 확인</li>
          <li>검증 성공 시 <strong>저장</strong> (API 호출 없이 즉시 검증)</li>
        </ol>
      </div>

      {/* 엔드포인트 흐름도들 */}
      {Object.values(ENDPOINT_FLOWS).map((endpoint) => (
        <EndpointFlowDiagram
          key={endpoint.id}
          endpoint={endpoint}
          onApiClick={handleApiClick}
        />
      ))}

      {/* API 변경 모달 */}
      {selectedPhase && (
        <APIChangeModal
          phase={selectedPhase}
          apiList={apiList}
          onClose={() => setSelectedPhase(null)}
          onSave={handleSaveConfig}
        />
      )}
    </>
  );
}
