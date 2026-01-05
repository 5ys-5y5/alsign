/**
 * RequestsPage Component
 *
 * Request forms for backend API endpoints with Status/LOG monitoring panel.
 * Based on alsign/prompt/2_designSystem.ini request_contract.
 */

import React, { useState, useRef, useCallback, useEffect } from 'react';
import { useLog } from '../contexts/LogContext';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

/**
 * Parse log line in key=value format.
 * Format: [endpoint | phase] key1=value1 | key2=value2 | ... | msg
 */
function parseLogLine(logLine) {
  if (!logLine || typeof logLine !== 'string') return null;

  try {
    const parsed = {};

    // Extract endpoint and phase from [endpoint | phase]
    const headerMatch = logLine.match(/^\[([^\]]+)\]/);
    if (headerMatch) {
      const parts = headerMatch[1].split('|').map((s) => s.trim());
      if (parts[0]) parsed.endpoint = parts[0];
      if (parts[1]) parsed.phase = parts[1];
    }

    // Extract key=value pairs (split by |, then by =)
    const segments = logLine.split('|');
    for (const segment of segments) {
      const trimmed = segment.trim();

      // Skip header segment
      if (trimmed.startsWith('[') && trimmed.endsWith(']')) continue;

      // Parse key=value
      const eqIndex = trimmed.indexOf('=');
      if (eqIndex > 0) {
        const key = trimmed.substring(0, eqIndex).trim();
        const value = trimmed.substring(eqIndex + 1).trim();
        parsed[key] = value;
      } else if (trimmed.length > 0) {
        // Last segment is usually the message
        parsed.msg = trimmed;
      }
    }

    return Object.keys(parsed).length > 0 ? parsed : null;
  } catch (err) {
    return null;
  }
}

/**
 * RequestForm - Generic request form component.
 */
function RequestForm({ title, method, path, queryFields, bodyFields, onRequestStart, onRequestComplete, onLog }) {
  const [queryParams, setQueryParams] = useState({});
  const [bodyData, setBodyData] = useState('{}');
  const [loading, setLoading] = useState(false);
  const [response, setResponse] = useState(null);
  const [error, setError] = useState(null);

  const handleQueryChange = (key, value) => {
    setQueryParams((prev) => ({ ...prev, [key]: value }));
  };

  /**
   * Check if a field should be visible based on showWhen condition
   */
  const isFieldVisible = (field) => {
    if (!field.showWhen) return true;
    const { field: depField, values } = field.showWhen;
    const currentValue = queryParams[depField];
    return values.includes(currentValue);
  };

  /**
   * Check if a field is required based on requiredWhen condition
   */
  const isFieldRequired = (field) => {
    if (field.required) return true;
    if (!field.requiredWhen) return false;
    const { field: depField, values } = field.requiredWhen;
    const currentValue = queryParams[depField];
    return values.includes(currentValue);
  };

  /**
   * Get dynamic description based on current selections
   */
  const getFieldDescription = (field) => {
    if (field.dynamicDescription) {
      const desc = field.dynamicDescription(queryParams);
      if (desc) return desc;
    }
    return field.description || '';
  };

  const handleBodyChange = (value) => {
    setBodyData(value);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setResponse(null);

    const startTime = Date.now();

    // Build query string
    const queryString = Object.entries(queryParams)
      .filter(([_, value]) => value !== '' && value !== undefined)
      .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(value)}`)
      .join('&');

    // Check if this is a streaming endpoint
    const isStreaming =
      (path === '/sourceData' && method === 'GET') ||
      (path === '/setEventsTable' && method === 'POST') ||
      (path === '/backfillEventsTable' && method === 'POST');

    if (isStreaming) {
      // Use SSE for real-time streaming
      let streamUrl;
      if (path === '/sourceData' && method === 'GET') {
        streamUrl = `${API_BASE_URL}/sourceData/stream${queryString ? '?' + queryString : ''}`;
      } else if (path === '/setEventsTable' && method === 'POST') {
        streamUrl = `${API_BASE_URL}/setEventsTable/stream${queryString ? '?' + queryString : ''}`;
      } else if (path === '/backfillEventsTable' && method === 'POST') {
        streamUrl = `${API_BASE_URL}/backfillEventsTable/stream${queryString ? '?' + queryString : ''}`;
      }
      const eventSource = new EventSource(streamUrl);
      let requestId = null;
      const detailedLogs = [];

      eventSource.addEventListener('init', (e) => {
        const data = JSON.parse(e.data);
        requestId = data.reqId;

        onLog?.('info', `${method} ${path} - Request started (streaming)`, requestId);
        onRequestStart?.({
          id: requestId,
          method,
          path,
          query: queryString,
          startTime,
          status: 'pending',
          detailedLogs: [],
          eventSource, // Store for cancellation
        });
      });

      eventSource.addEventListener('log', (e) => {
        const data = JSON.parse(e.data);
        detailedLogs.push(data.log);

        // Update request with new log
        if (requestId) {
          onRequestComplete?.({
            id: requestId,
            status: 'pending',
            statusCode: null,
            duration: null,
            detailedLogs: [...detailedLogs],
          });
        }
      });

      eventSource.addEventListener('result', (e) => {
        const result = JSON.parse(e.data);
        const duration = Date.now() - startTime;

        setResponse(result.data);
        onLog?.('success', `${method} ${path} - Completed in ${duration}ms`, requestId);
        onRequestComplete?.({
          id: requestId,
          status: 'success',
          statusCode: 200,
          duration,
          response: result.data,
          detailedLogs: [...detailedLogs],
        });

        eventSource.close();
        setLoading(false);
      });

      eventSource.addEventListener('error', (e) => {
        const duration = Date.now() - startTime;
        let errorMsg = 'Stream error';

        try {
          const data = JSON.parse(e.data);
          errorMsg = data.error || errorMsg;
        } catch {}

        setError(errorMsg);
        onLog?.('error', `${method} ${path} - Error: ${errorMsg}`, requestId);
        onRequestComplete?.({
          id: requestId,
          status: 'error',
          statusCode: 0,
          duration,
          error: errorMsg,
          detailedLogs: [...detailedLogs],
        });

        eventSource.close();
        setLoading(false);
      });

      eventSource.onerror = (e) => {
        // Only handle if not already closed by result/error event
        if (eventSource.readyState === EventSource.CLOSED) {
          return;
        }
        
        const duration = Date.now() - startTime;
        const errorMsg = 'Connection error';

        setError(errorMsg);
        onLog?.('error', `${method} ${path} - ${errorMsg}`, requestId);
        onRequestComplete?.({
          id: requestId || Date.now().toString(),
          status: 'error',
          statusCode: 0,
          duration,
          error: errorMsg,
          detailedLogs: [...detailedLogs],
        });

        eventSource.close();
        setLoading(false);
      };
      
      // Safety net: ensure loading is reset when stream ends
      eventSource.onopen = () => {
        // Stream opened successfully
      };

    } else {
      // Regular non-streaming request
      const requestId = Date.now().toString();

      try {
        const url = `${API_BASE_URL}${path}${queryString ? '?' + queryString : ''}`;

        // Build request options
        const options = {
          method,
          headers: {},
        };

        if (method !== 'GET' && bodyFields) {
          options.headers['Content-Type'] = 'application/json';
          // Parse body or use empty object
          try {
            const parsedBody = JSON.parse(bodyData);
            options.body = JSON.stringify(parsedBody);
          } catch (err) {
            throw new Error('Invalid JSON in request body');
          }
        }

        // Log request start
        onLog?.('info', `${method} ${path} - Request started`, requestId);
        onRequestStart?.({
          id: requestId,
          method,
          path,
          query: queryString,
          startTime,
          status: 'pending',
          detailedLogs: [],
        });

        const res = await fetch(url, options);
        const text = await res.text();

        let data;
        try {
          data = JSON.parse(text);
        } catch {
          data = text;
        }

        const duration = Date.now() - startTime;

        if (!res.ok) {
          const errorMsg = `HTTP ${res.status}: ${typeof data === 'string' ? data : JSON.stringify(data)}`;
          setError(errorMsg);
          onLog?.('error', `${method} ${path} - Failed: ${res.status}`, requestId);
          onRequestComplete?.({
            id: requestId,
            status: 'error',
            statusCode: res.status,
            duration,
            error: errorMsg,
            detailedLogs: data?.detailedLogs || [],
          });
          throw new Error(errorMsg);
        }

        setResponse(data);
        onLog?.('success', `${method} ${path} - Completed in ${duration}ms`, requestId);
        onRequestComplete?.({
          id: requestId,
          status: 'success',
          statusCode: res.status,
          duration,
          response: data,
          detailedLogs: data?.detailedLogs || [],
        });
      } catch (err) {
        const duration = Date.now() - startTime;
        setError(err.message);
        onLog?.('error', `${method} ${path} - Error: ${err.message}`, requestId);
        onRequestComplete?.({
          id: requestId,
          status: 'error',
          statusCode: 0,
          duration,
          error: err.message,
          detailedLogs: [],
        });
      } finally {
        setLoading(false);
      }
    }
  };

  return (
    <div
      style={{
        border: '1px solid var(--border)',
        borderRadius: 'var(--rounded-lg)',
        padding: 'var(--space-3)',
        backgroundColor: 'white',
        marginBottom: 'var(--space-4)',
      }}
    >
      <h3 style={{ marginBottom: 'var(--space-3)' }}>{title}</h3>

      <form onSubmit={handleSubmit}>
        {/* Query Parameters */}
        {queryFields && queryFields.length > 0 && (
          <div style={{ marginBottom: 'var(--space-3)' }}>
            <h4
              style={{
                fontSize: 'var(--text-sm)',
                fontWeight: 'var(--font-semibold)',
                marginBottom: 'var(--space-2)',
              }}
            >
              Query Parameters
            </h4>
            {queryFields.filter(isFieldVisible).map((field) => {
              const required = isFieldRequired(field);
              const description = getFieldDescription(field);
              
              return (
                <div key={field.key} style={{ marginBottom: 'var(--space-2)' }}>
                  <label
                    style={{
                      display: 'block',
                      fontSize: 'var(--text-sm)',
                      marginBottom: 'var(--space-1)',
                      fontWeight: required ? 'var(--font-semibold)' : 'normal',
                    }}
                  >
                    {field.label || field.key}
                    {required && <span style={{ color: 'var(--accent-danger)', marginLeft: '2px' }}>*</span>}
                  </label>
                  {field.control === 'checkbox' ? (
                    <input
                      type="checkbox"
                      checked={queryParams[field.key] || false}
                      onChange={(e) => handleQueryChange(field.key, e.target.checked)}
                    />
                  ) : field.control === 'select' ? (
                    <select
                      value={queryParams[field.key] || ''}
                      onChange={(e) => handleQueryChange(field.key, e.target.value)}
                      style={{
                        borderColor: required && !queryParams[field.key] ? 'var(--accent-warning)' : undefined,
                      }}
                    >
                      <option value="">(unset)</option>
                      {field.options?.map((opt) => (
                        <option key={opt} value={opt}>
                          {opt}
                        </option>
                      ))}
                    </select>
                  ) : field.type === 'date' ? (
                    <input
                      type="date"
                      value={queryParams[field.key] || ''}
                      onChange={(e) => handleQueryChange(field.key, e.target.value)}
                      placeholder={field.placeholder}
                      style={{
                        borderColor: required && !queryParams[field.key] ? 'var(--accent-warning)' : undefined,
                      }}
                    />
                  ) : (
                    <input
                      type="text"
                      value={queryParams[field.key] || ''}
                      onChange={(e) => handleQueryChange(field.key, e.target.value)}
                      placeholder={field.placeholder}
                      style={{
                        borderColor: required && !queryParams[field.key] ? 'var(--accent-warning)' : undefined,
                      }}
                    />
                  )}
                  {description && (
                    <div
                      style={{
                        fontSize: 'var(--text-xs)',
                        color: 'var(--text-secondary)',
                        marginTop: '2px',
                        fontStyle: 'italic',
                      }}
                    >
                      {description}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {/* Request Body */}
        {bodyFields && bodyFields.length > 0 && (
          <div style={{ marginBottom: 'var(--space-3)' }}>
            <h4
              style={{
                fontSize: 'var(--text-sm)',
                fontWeight: 'var(--font-semibold)',
                marginBottom: 'var(--space-2)',
              }}
            >
              Request Body (JSON)
            </h4>
            <textarea
              value={bodyData}
              onChange={(e) => handleBodyChange(e.target.value)}
              rows={8}
              style={{
                fontFamily: 'monospace',
                fontSize: 'var(--text-xs)',
              }}
              placeholder={bodyFields[0]?.default || '{}'}
            />
          </div>
        )}

        {/* Submit Button */}
        <button type="submit" className="btn btn-md btn-primary" disabled={loading}>
          {loading ? 'Executing...' : 'Execute'}
        </button>
      </form>

      {/* Response Panel */}
      {(response || error) && (
        <div style={{ marginTop: 'var(--space-3)' }}>
          <h4
            style={{
              fontSize: 'var(--text-sm)',
              fontWeight: 'var(--font-semibold)',
              marginBottom: 'var(--space-2)',
            }}
          >
            Response
          </h4>
          <div
            style={{
              border: '1px solid var(--border)',
              borderRadius: 'var(--rounded-lg)',
              padding: 'var(--space-2)',
              backgroundColor: error ? '#fef2f2' : 'var(--surface)',
              maxHeight: '70vh',
              overflowY: 'auto',
            }}
          >
            <pre
              style={{
                fontSize: 'var(--text-xs)',
                color: error ? 'var(--accent-danger)' : 'var(--text)',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                margin: 0,
                fontFamily: 'monospace',
              }}
            >
              {error || JSON.stringify(response, null, 2)}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * RequestsPage component.
 */
export default function RequestsPage() {
  // Use global log context
  const { handleRequestStart, handleRequestComplete, handleLog } = useLog();

  // State for selected endpoint
  const [selectedEndpoint, setSelectedEndpoint] = useState('sourceData');

  // State for header height to adjust sidebar position
  const [headerHeight, setHeaderHeight] = useState(52);

  // Endpoint list for navigation
  const endpoints = [
    { id: 'sourceData', title: 'GET /sourceData' },
    { id: 'setEventsTable', title: 'POST /setEventsTable' },
    { id: 'backfillEventsTable', title: 'POST /backfillEventsTable' },
    { id: 'generatePriceTrends', title: 'POST /generatePriceTrends' },
    { id: 'trades', title: 'POST /trades' },
    { id: 'fillAnalyst', title: 'POST /fillAnalyst' }
  ];

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
          {endpoints.map((endpoint) => (
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
          <h1>Requests</h1>
          <p style={{ color: 'var(--text-dim)', fontSize: 'var(--text-sm)' }}>
            Execute backend API requests
          </p>
        </header>

        {/* GET /sourceData */}
        {selectedEndpoint === 'sourceData' && <RequestForm
          title="GET /sourceData"
          method="GET"
          path="/sourceData"
          queryFields={[
            {
              key: 'overwrite',
              type: 'boolean',
              control: 'checkbox',
              required: false,
            },
            {
              key: 'mode',
              type: 'string',
              control: 'input',
              placeholder: 'holiday,target,consensus,earning',
              required: false,
            },
            {
              key: 'past',
              type: 'boolean',
              control: 'checkbox',
              required: false,
            },
            {
              key: 'calc_mode',
              type: 'string',
              control: 'select',
              options: ['maintenance', 'calculation'],
              required: false,
              dynamicDescription: (params) => {
                if (params.calc_mode === 'maintenance') {
                  return '✅ Phase 1 (API 호출) + Phase 2 (prev/direction 계산) - 사용자 지정 scope로 실행';
                } else if (params.calc_mode === 'calculation') {
                  return '✅ Phase 2만 실행 (API 호출 없음) - 기존 데이터로 prev/direction 계산';
                }
                return 'maintenance: Phase1+2 with scope, calculation: Phase2 only (no API calls)';
              },
            },
            {
              key: 'calc_scope',
              type: 'string',
              control: 'select',
              options: ['all', 'ticker', 'event_date_range', 'partition_keys'],
              required: false,
              showWhen: { field: 'calc_mode', values: ['maintenance', 'calculation'] },
              requiredWhen: { field: 'calc_mode', values: ['maintenance', 'calculation'] },
              dynamicDescription: (params) => {
                if (!params.calc_mode) return '';
                if (params.calc_scope === 'all') {
                  return '📊 전체 파티션 대상으로 계산 수행';
                } else if (params.calc_scope === 'ticker') {
                  return '🎯 특정 티커만 대상으로 계산 수행 → tickers 필드 입력 필요';
                } else if (params.calc_scope === 'event_date_range') {
                  return '📅 날짜 범위 내 이벤트 대상으로 계산 수행 → from/to 필드 입력 필요';
                } else if (params.calc_scope === 'partition_keys') {
                  return '🔑 지정된 파티션(ticker+analyst)만 대상으로 계산 수행 → partitions 필드 입력 필요';
                }
                return '⚠️ calc_mode가 설정되면 필수입니다';
              },
            },
            {
              key: 'tickers',
              type: 'string',
              control: 'input',
              placeholder: 'RGTI,AAPL,MSFT',
              required: false,
              showWhen: { field: 'calc_scope', values: ['ticker'] },
              requiredWhen: { field: 'calc_scope', values: ['ticker'] },
              description: '쉼표로 구분된 티커 목록 (예: RGTI,AAPL,MSFT)',
            },
            {
              key: 'from',
              type: 'string',
              control: 'input',
              placeholder: '2023-01-01',
              required: false,
              showWhen: { field: 'calc_scope', values: ['event_date_range'] },
              requiredWhen: { field: 'calc_scope', values: ['event_date_range'] },
              description: '시작 날짜 (YYYY-MM-DD 형식)',
            },
            {
              key: 'to',
              type: 'string',
              control: 'input',
              placeholder: '2025-12-31',
              required: false,
              showWhen: { field: 'calc_scope', values: ['event_date_range'] },
              requiredWhen: { field: 'calc_scope', values: ['event_date_range'] },
              description: '종료 날짜 (YYYY-MM-DD 형식)',
            },
            {
              key: 'partitions',
              type: 'string',
              control: 'input',
              placeholder: '[{"ticker":"RGTI","analyst_name":"David Williams","analyst_company":"Williams Trading"}]',
              required: false,
              showWhen: { field: 'calc_scope', values: ['partition_keys'] },
              requiredWhen: { field: 'calc_scope', values: ['partition_keys'] },
              description: 'JSON 배열 형식의 파티션 목록',
            },
          ]}
          onRequestStart={handleRequestStart}
          onRequestComplete={handleRequestComplete}
          onLog={handleLog}
        />}

        {/* POST /setEventsTable */}
        {selectedEndpoint === 'setEventsTable' && <RequestForm
          title="POST /setEventsTable"
          method="POST"
          path="/setEventsTable"
          queryFields={[
            {
              key: 'overwrite',
              type: 'boolean',
              control: 'checkbox',
              required: false,
            },
            {
              key: 'dryRun',
              type: 'boolean',
              control: 'checkbox',
              required: false,
            },
            {
              key: 'schema',
              type: 'string',
              control: 'input',
              placeholder: 'public',
              required: false,
            },
            {
              key: 'table',
              type: 'string',
              control: 'input',
              placeholder: 'evt_consensus,evt_earning',
              required: false,
            },
          ]}
          bodyFields={[{ key: '__body__', type: 'json', default: '{}' }]}
          onRequestStart={handleRequestStart}
          onRequestComplete={handleRequestComplete}
          onLog={handleLog}
        />}

        {/* POST /backfillEventsTable */}
        {selectedEndpoint === 'backfillEventsTable' && <RequestForm
          title="POST /backfillEventsTable"
          method="POST"
          path="/backfillEventsTable"
          queryFields={[
            {
              key: 'overwrite',
              type: 'boolean',
              control: 'checkbox',
              required: false,
              description: 'If false, update only NULL values. If true, overwrite existing values. When used with metrics: applies to specified metrics only.',
            },
            {
              key: 'from',
              label: 'From Date',
              type: 'date',
              control: 'input',
              required: false,
              placeholder: 'YYYY-MM-DD',
            },
            {
              key: 'to',
              label: 'To Date',
              type: 'date',
              control: 'input',
              required: false,
              placeholder: 'YYYY-MM-DD',
            },
            {
              key: 'tickers',
              label: 'Tickers (comma-separated)',
              type: 'text',
              control: 'input',
              required: false,
              placeholder: 'AAPL,MSFT,GOOGL or [AAPL,MSFT,GOOGL]',
            },
            {
              key: 'metrics',
              label: 'Metrics (comma-separated)',
              type: 'text',
              control: 'input',
              required: false,
              placeholder: 'priceQuantitative,PER,PBR',
              description: 'Selective metric update: specify metric IDs to recalculate (I-41)',
            },
          ]}
          bodyFields={[
            {
              key: '__body__',
              label: 'Request Body (JSON)',
              type: 'json',
              default: '{}',
            }
          ]}
          onRequestStart={handleRequestStart}
          onRequestComplete={handleRequestComplete}
          onLog={handleLog}
        />}

        {/* POST /generatePriceTrends */}
        {selectedEndpoint === 'generatePriceTrends' && <RequestForm
          title="POST /generatePriceTrends"
          method="POST"
          path="/generatePriceTrends"
          queryFields={[
            {
              key: 'overwrite',
              type: 'boolean',
              control: 'checkbox',
              required: false,
              description: 'If false, update only NULL values. If true, overwrite existing values.',
            },
            {
              key: 'from',
              label: 'From Date',
              type: 'date',
              control: 'input',
              required: false,
              placeholder: 'YYYY-MM-DD',
            },
            {
              key: 'to',
              label: 'To Date',
              type: 'date',
              control: 'input',
              required: false,
              placeholder: 'YYYY-MM-DD',
            },
            {
              key: 'tickers',
              label: 'Tickers (comma-separated)',
              type: 'text',
              control: 'input',
              required: false,
              placeholder: 'AAPL,MSFT,GOOGL or [AAPL,MSFT,GOOGL]',
            },
          ]}
          bodyFields={[
            {
              key: '__body__',
              label: 'Request Body (JSON)',
              type: 'json',
              default: '{}',
            }
          ]}
          onRequestStart={handleRequestStart}
          onRequestComplete={handleRequestComplete}
          onLog={handleLog}
        />}

        {/* POST /trades */}
        {selectedEndpoint === 'trades' && <RequestForm
          title="POST /trades"
          method="POST"
          path="/trades"
          queryFields={[]}
          bodyFields={[
            {
              key: '__body__',
              label: 'Request Body (JSON)',
              type: 'json',
              default: JSON.stringify({
                "trades": [
                  {
                    "ticker": "AAPL",
                    "trade_date": "2024-01-15",
                    "model": "default",
                    "source": "consensus",
                    "position": "long",
                    "entry_price": 185.50,
                    "exit_price": null,
                    "quantity": 100,
                    "notes": "Entry based on consensus signal"
                  }
                ]
              }, null, 2),
            }
          ]}
          onRequestStart={handleRequestStart}
          onRequestComplete={handleRequestComplete}
          onLog={handleLog}
        />}

        {/* POST /fillAnalyst */}
        {selectedEndpoint === 'fillAnalyst' && <RequestForm
          title="POST /fillAnalyst"
          method="POST"
          path="/fillAnalyst"
          queryFields={[
            {
              key: 'overwrite',
              type: 'boolean',
              control: 'checkbox',
              required: false,
            },
          ]}
          bodyFields={[
            {
              key: '__body__',
              type: 'json',
              default: JSON.stringify(
                {
                  calc_mode: 'maintenance',
                  calc_scope: 'event_date_range',
                  from: '2024-01-01',
                  to: '2024-12-31',
                },
                null,
                2
              ),
            },
          ]}
          onRequestStart={handleRequestStart}
          onRequestComplete={handleRequestComplete}
          onLog={handleLog}
        />}
      </div>
    </div>
  );
}
