import React, { useState, useRef, useCallback, useEffect } from 'react';
import { useLog } from '../contexts/LogContext';

import { API_BASE_URL, getAuthHeaders } from '../services/api';

/**
 * Default timeout settings per endpoint (in milliseconds)
 * Set to 0 to disable timeout for an endpoint
 * Can be overridden via 'timeout' query parameter
 */
const ENDPOINT_TIMEOUTS = {
  '/sourceData': 3600000,              // 60 minutes
  '/setEventsTable': 3600000,          // 60 minutes
  '/backfillEventsTable': 0,           // No timeout (can run for hours)
  '/getQuantitatives': 0,              // No timeout (can run for hours)
};

/**
 * Common timeout field definition for all endpoints
 * Can be added to any endpoint's queryFields array
 */
const TIMEOUT_FIELD = {
  key: 'timeout',
  label: 'Timeout (ms)',
  type: 'number',
  control: 'input',
  placeholder: '0 = no timeout, 3600000 = 60min',
  min: 0,
  required: false,
  description: 'Request timeout in milliseconds. Set to 0 to disable timeout (run indefinitely). Default: endpoint-specific (see ENDPOINT_TIMEOUTS).',
};

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


const TRADE_CSV_HEADERS = {
  tradedate: 'trade_date',
  ticker: 'ticker',
  position: 'position',
  model: 'model',
  notes: 'notes',
  source: 'source',
  entryprice: 'entry_price',
  exitprice: 'exit_price',
  quantity: 'quantity',
};

const UNDELIMITED_TRADE_HEADERS = ['trade_date', 'ticker', 'position', 'model', 'notes'];

function normalizeHeader(header) {
  return header.trim().toLowerCase().replace(/[^a-z0-9]/g, '');
}

function splitDelimitedLine(line, delimiter) {
  if (delimiter) {
    return line.split(delimiter).map((value) => value.trim());
  }
  return line.trim().split(/\s+/);
}

function normalizeTradeDate(value) {
  if (!value) return value;
  const match = value.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/);
  if (!match) return value;
  const [, year, month, day] = match;
  return `${year}-${month.padStart(2, '0')}-${day.padStart(2, '0')}`;
}

function parseUndelimitedTradeLine(line, headers) {
  if (headers.join(',') !== UNDELIMITED_TRADE_HEADERS.join(',')) {
    throw new Error('Undelimited format supports headers: trade_date,ticker,position,model,notes');
  }

  const dateMatch = line.match(/^(\d{4}-\d{1,2}-\d{1,2})/);
  if (!dateMatch) {
    throw new Error(`Invalid trade_date: ${line}`);
  }

  const trade_date = normalizeTradeDate(dateMatch[1]);
  const rest = line.slice(trade_date.length);
  if (!rest) {
    throw new Error(`Missing fields after trade_date: ${line}`);
  }

  const restLower = rest.toLowerCase();
  const positions = ['long', 'short', 'neutral'];
  let positionIndex = -1;
  let positionValue = '';

  positions.forEach((pos) => {
    const idx = restLower.indexOf(pos);
    if (idx !== -1 && (positionIndex === -1 || idx < positionIndex)) {
      positionIndex = idx;
      positionValue = pos;
    }
  });

  if (positionIndex === -1) {
    throw new Error(`Missing position (long/short/neutral): ${line}`);
  }

  const ticker = rest.slice(0, positionIndex).trim();
  const modelNotes = rest.slice(positionIndex + positionValue.length).trim();

  if (!ticker) {
    throw new Error(`Missing ticker: ${line}`);
  }
  if (!modelNotes) {
    throw new Error(`Missing model/notes: ${line}`);
  }

  let model = modelNotes;
  let notes;
  const urlIndex = modelNotes.search(/https?:\/\//i);
  if (urlIndex !== -1) {
    model = modelNotes.slice(0, urlIndex).trim();
    notes = modelNotes.slice(urlIndex).trim();
  }

  if (!model) {
    throw new Error(`Missing model: ${line}`);
  }

  return {
    trade_date,
    ticker,
    position: positionValue,
    model,
    notes,
  };
}

function parseDelimitedTrades(rawText) {
  const lines = rawText
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);

  if (lines.length < 2) {
    throw new Error('CSV/TSV must include a header and at least one data row');
  }

  const headerLine = lines[0];
  let delimiter = null;
  let undelimited = false;
  let rawHeaders = [];
  if (headerLine.includes('	')) {
    delimiter = '	';
  } else if (headerLine.includes(',')) {
    delimiter = ',';
  }

  if (delimiter) {
    rawHeaders = splitDelimitedLine(headerLine, delimiter);
  } else {
    const normalizedHeaderLine = normalizeHeader(headerLine);
    const expectedConcatenated = UNDELIMITED_TRADE_HEADERS.map((header) => header.replace('_', '')).join('');
    if (normalizedHeaderLine === expectedConcatenated) {
      undelimited = true;
      rawHeaders = UNDELIMITED_TRADE_HEADERS;
    } else {
      rawHeaders = splitDelimitedLine(headerLine, delimiter);
    }
  }

  if (!undelimited && rawHeaders.length < 2) {
    throw new Error('Invalid CSV/TSV header');
  }

  const headers = undelimited ? rawHeaders : rawHeaders.map((header) => {
    const normalized = normalizeHeader(header);
    const key = TRADE_CSV_HEADERS[normalized];
    if (!key) {
      throw new Error(`Unsupported header: ${header}`);
    }
    return key;
  });

  const trades = [];
  for (const line of lines.slice(1)) {
    if (undelimited) {
      trades.push(parseUndelimitedTradeLine(line, headers));
      continue;
    }

    let parts = splitDelimitedLine(line, delimiter);
    if (parts.length < headers.length) {
      throw new Error(`Row has fewer columns than header: ${line}`);
    }

    if (parts.length > headers.length) {
      const joiner = delimiter || ' ';
      parts = parts
        .slice(0, headers.length - 1)
        .concat(parts.slice(headers.length - 1).join(joiner));
    }

    const trade = {};
    headers.forEach((key, index) => {
      const value = parts[index];
      if (value === undefined || value === '') {
        return;
      }
      trade[key] = value;
    });

    if (!trade.trade_date || !trade.ticker) {
      throw new Error('trade_date and ticker are required');
    }

    trade.trade_date = normalizeTradeDate(trade.trade_date);

    if (trade.position) {
      trade.position = trade.position.toLowerCase();
    }
    if (trade.source) {
      trade.source = trade.source.toLowerCase();
    }
    if (trade.entry_price) {
      const parsed = parseFloat(trade.entry_price);
      if (Number.isNaN(parsed)) {
        throw new Error(`Invalid entry_price: ${trade.entry_price}`);
      }
      trade.entry_price = parsed;
    }
    if (trade.exit_price) {
      const parsed = parseFloat(trade.exit_price);
      if (Number.isNaN(parsed)) {
        throw new Error(`Invalid exit_price: ${trade.exit_price}`);
      }
      trade.exit_price = parsed;
    }
    if (trade.quantity) {
      const parsed = parseInt(trade.quantity, 10);
      if (Number.isNaN(parsed)) {
        throw new Error(`Invalid quantity: ${trade.quantity}`);
      }
      trade.quantity = parsed;
    }

    trades.push(trade);
  }

  return { trades };
}

/**
 * RequestForm - Generic request form component.
 */
function RequestForm({ title, method, path, queryFields, bodyFields, bodyExample, bodyExampleCsv, onRequestStart, onRequestComplete, onLog }) {
  const [queryParams, setQueryParams] = useState({});
  const [bodyData, setBodyData] = useState(bodyFields?.[0]?.default ?? '{}');
  const [loading, setLoading] = useState(false);
  const [response, setResponse] = useState(null);
  const [error, setError] = useState(null);
  const [copyStatus, setCopyStatus] = useState({});

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

  const handleCopyExample = async (key, text) => {
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      setCopyStatus((prev) => ({ ...prev, [key]: 'copied' }));
      setTimeout(() => {
        setCopyStatus((prev) => {
          const next = { ...prev };
          delete next[key];
          return next;
        });
      }, 2000);
    } catch (err) {
      setCopyStatus((prev) => ({ ...prev, [key]: 'failed' }));
      setTimeout(() => {
        setCopyStatus((prev) => {
          const next = { ...prev };
          delete next[key];
          return next;
        });
      }, 2000);
    }
  };

  const renderExampleBox = (label, example, key) => {
    if (!example) return null;
    const status = copyStatus[key];
    const buttonLabel = status === 'copied' ? 'Copied' : status === 'failed' ? 'Copy failed' : 'Copy';

    return (
      <div
        key={key}
        style={{
          border: '1px solid var(--border)',
          borderRadius: 'var(--rounded-md)',
          backgroundColor: 'var(--surface)',
          padding: 'var(--space-2)',
          marginBottom: 'var(--space-2)',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}>
            {label}
          </div>
          <button
            type="button"
            onClick={() => handleCopyExample(key, example)}
            className="btn btn-xs btn-secondary"
          >
            {buttonLabel}
          </button>
        </div>
        <pre
          style={{
            margin: 'var(--space-1) 0 0 0',
            fontFamily: 'monospace',
            fontSize: 'var(--text-xs)',
            whiteSpace: 'pre-wrap',
          }}
        >
          {example}
        </pre>
      </div>
    );
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
      (path === '/backfillEventsTable' && method === 'POST') ||
      (path === '/getQuantitatives' && method === 'POST');

    if (isStreaming) {
      // Use SSE for real-time streaming
      let streamUrl;
      if (path === '/sourceData' && method === 'GET') {
        streamUrl = `${API_BASE_URL}/sourceData/stream${queryString ? '?' + queryString : ''}`;
      } else if (path === '/setEventsTable' && method === 'POST') {
        streamUrl = `${API_BASE_URL}/setEventsTable/stream${queryString ? '?' + queryString : ''}`;
      } else if (path === '/backfillEventsTable' && method === 'POST') {
        streamUrl = `${API_BASE_URL}/backfillEventsTable/stream${queryString ? '?' + queryString : ''}`;
      } else if (path === '/getQuantitatives' && method === 'POST') {
        streamUrl = `${API_BASE_URL}/getQuantitatives/stream${queryString ? '?' + queryString : ''}`;
      }
      const eventSource = new EventSource(streamUrl);
      let requestId = null;
      const detailedLogs = [];

      // Determine timeout for this endpoint
      // Priority: 1) timeout query param, 2) endpoint default, 3) no timeout
      let timeoutMs = ENDPOINT_TIMEOUTS[path] !== undefined ? ENDPOINT_TIMEOUTS[path] : 0;

      // Check if user specified timeout in query params
      if (queryParams.timeout !== undefined && queryParams.timeout !== '') {
        timeoutMs = parseInt(queryParams.timeout, 10);
        if (isNaN(timeoutMs)) {
          timeoutMs = 0; // Invalid value = no timeout
        }
      }

      // Setup safety timeout if configured (0 = no timeout)
      let safetyTimeout = null;
      if (timeoutMs > 0) {
        const timeoutMinutes = Math.round(timeoutMs / 60000);
        console.log(`Setting ${timeoutMinutes}min timeout for ${path}`);

        safetyTimeout = setTimeout(() => {
          if (eventSource.readyState !== EventSource.CLOSED) {
            console.error(`EventSource timeout after ${timeoutMinutes}min - closing connection`);
            eventSource.close();
            setError(`Request timeout - no response after ${timeoutMinutes} minutes`);
            setLoading(false);
            onLog?.('error', `${method} ${path} - Timeout (${timeoutMinutes}min)`, requestId || 'unknown');
            onRequestComplete?.({
              id: requestId || Date.now().toString(),
              status: 'error',
              statusCode: 408,
              duration: timeoutMs,
              error: `Request timeout (${timeoutMinutes}min)`,
              detailedLogs: [...detailedLogs],
            });
          }
        }, timeoutMs);
      } else {
        console.log(`No timeout set for ${path} (will run indefinitely)`);
      }

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
        if (safetyTimeout) clearTimeout(safetyTimeout);
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
        if (safetyTimeout) clearTimeout(safetyTimeout);
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

        if (safetyTimeout) clearTimeout(safetyTimeout);
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
          let parsedBody;

          try {
            parsedBody = JSON.parse(bodyData);
          } catch (err) {
            if (path === '/trades') {
              parsedBody = parseDelimitedTrades(bodyData);
            } else {
              throw new Error('Invalid JSON in request body');
            }
          }

          options.body = JSON.stringify(parsedBody);
        }

        options.headers = await getAuthHeaders(options.headers);

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
                  ) : field.type === 'number' ? (
                    <input
                      type="number"
                      value={queryParams[field.key] || ''}
                      onChange={(e) => handleQueryChange(field.key, e.target.value)}
                      placeholder={field.placeholder}
                      min={field.min}
                      max={field.max}
                      style={{
                        borderColor: required && !queryParams[field.key] ? 'var(--accent-warning)' : undefined,
                        width: '150px',
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
            {path === '/trades' && (
              <div
                style={{
                  fontSize: 'var(--text-xs)',
                  color: 'var(--text-secondary)',
                  marginBottom: 'var(--space-2)',
                }}
              >
                CSV/TSV input supported (headers: trade_date, ticker, position, model, notes; optional source, entry_price, exit_price, quantity). Undelimited header/data supported for trade_date,ticker,position,model,notes.
              </div>
            )}
            {renderExampleBox('JSON Example', bodyExample, 'json')}
            {renderExampleBox('CSV/TSV Example', bodyExampleCsv, 'csv')}
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
    { id: 'getQuantitatives', title: 'POST /getQuantitatives' },
    { id: 'setEventsTable', title: 'POST /setEventsTable' },
    { id: 'backfillEventsTable', title: 'POST /backfillEventsTable' },
    { id: 'trades', title: 'POST /trades' },
    { id: 'fillAnalyst', title: 'POST /fillAnalyst' }
  ];

  const tradesBodyExampleCsv = [
    'trade_date,ticker,position,model,notes',
    '2026-01-13,PRGS,long,MODEL-0,https://chatgpt.com/g/g-68cb99af63a081918e0f7d0c3e38a3e3-tuja-model-0/c/6965f399-15d8-8328-b27b-1b6f848e4251',
    '2026-01-13,FAST,long,MODEL-0,https://chatgpt.com/g/g-68cb99af63a081918e0f7d0c3e38a3e3-tuja-model-0/c/6965f399-15d8-8328-b27b-1b6f848e4251',
  ].join('\n');

  const tradesBodyExample = JSON.stringify({
    trades: [
      {
        ticker: 'AAPL',
        trade_date: '2024-01-15',
        model: 'default',
        source: 'consensus',
        position: 'long',
        entry_price: 185.5,
        exit_price: null,
        quantity: 100,
        notes: 'Entry based on consensus signal',
      },
    ],
  }, null, 2);

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
            Execute backend API requests (backfill batch_size groups unique tickers)
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
            {
              key: 'max_workers',
              type: 'number',
              control: 'input',
              placeholder: '20',
              min: 1,
              max: 100,
              required: false,
              description: '동시 실행 worker 수 (1-100). DB CPU 모니터링하며 조정. 낮음=안전/느림, 높음=빠름/부하',
            },
            { ...TIMEOUT_FIELD },
          ]}
          onRequestStart={handleRequestStart}
          onRequestComplete={handleRequestComplete}
          onLog={handleLog}
        />}

        {/* POST /getQuantitatives */}
        {selectedEndpoint === 'getQuantitatives' && <RequestForm
          title="POST /getQuantitatives"
          method="POST"
          path="/getQuantitatives"
          queryFields={[
            {
              key: 'overwrite',
              type: 'boolean',
              control: 'checkbox',
              required: false,
              description: 'If checked, refetch all selected APIs even if data already exists. If unchecked, skip APIs with existing data.',
            },
            {
              key: 'apis',
              type: 'string',
              control: 'input',
              placeholder: 'ratios,key-metrics,cash-flow,balance-sheet,market-cap,price,income,quote',
              required: false,
              description: 'Comma-separated list of APIs to fetch. Available: ratios, key-metrics, cash-flow, balance-sheet, market-cap, price, income, quote. Leave empty to fetch all APIs.',
            },
            {
              key: 'tickers',
              type: 'string',
              control: 'input',
              placeholder: 'AAPL,MSFT,NVDA',
              required: false,
              description: 'Comma-separated list of tickers to process. Only tickers that exist in config_lv3_targets (ticker or peer column) will be processed. Leave empty to process all targets and their peers.',
            },
            {
              key: 'max_workers',
              type: 'number',
              control: 'input',
              placeholder: '20',
              min: 1,
              max: 100,
              required: false,
              description: '동시 실행 ticker worker 수 (1-100). DB CPU에 따라 조정. 기본값: 20',
            },
            { ...TIMEOUT_FIELD },
          ]}
          bodyFields={[]}
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
            {
              key: 'max_workers',
              type: 'number',
              control: 'input',
              placeholder: '20',
              min: 1,
              max: 100,
              required: false,
              description: '동시 실행 worker 수 (1-100). DB CPU 모니터링하며 조정. 낮음=안전/느림, 높음=빠름/부하',
            },
            {
              key: 'cleanup_mode',
              type: 'string',
              control: 'select',
              required: false,
              options: ['preview', 'archive', 'delete'],
              placeholder: '(선택 안 함)',
              dynamicDescription: (params) => {
                if (params.cleanup_mode === 'preview') {
                  return '🔍 Preview: config_lv3_targets에 없는 invalid ticker 조회만 (DB 변경 없음, 권장: 먼저 실행)';
                } else if (params.cleanup_mode === 'archive') {
                  return '📦 Archive: Invalid ticker를 txn_events_archived로 이동 후 삭제 (복구 가능, 권장)';
                } else if (params.cleanup_mode === 'delete') {
                  return '⚠️ Delete: Invalid ticker 영구 삭제 (복구 불가, 주의!)';
                }
                return 'Invalid ticker 정리 모드. preview로 먼저 확인 후 archive 권장';
              },
            },
            { ...TIMEOUT_FIELD },
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
              key: 'startPoint',
              label: 'Start Point (ticker)',
              type: 'text',
              control: 'input',
              required: false,
              placeholder: 'MSFT',
              description: '알파벳 순 티커 진행 재개 지점 (inclusive). 예: MSFT부터 처리',
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
            {
              key: 'batch_size',
              label: 'Batch Size (1-2,000)',
              type: 'number',
              control: 'input',
              required: false,
              placeholder: '500',
              min: 1,
              max: 2000,
              description: 'BATCH PROCESSING: Processes unique tickers in chunks. Example: 500 = process 500 tickers per batch (equivalent to calling with grouped tickers). Maximum: 2,000 (Supabase free tier: 1GB RAM). Use 200-1000 to prevent memory exhaustion.',
            },
            {
              key: 'max_workers',
              type: 'number',
              control: 'input',
              placeholder: '20',
              min: 1,
              max: 100,
              required: false,
              description: '동시 실행 worker 수 (1-100). DB CPU 모니터링하며 조정. 낮음=안전/느림, 높음=빠름/부하',
            },
            { ...TIMEOUT_FIELD },
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
          queryFields={[{ ...TIMEOUT_FIELD }]}
          bodyExample={tradesBodyExample}
          bodyExampleCsv={tradesBodyExampleCsv}
          bodyFields={[
            {
              key: '__body__',
              label: 'Request Body (JSON)',
              type: 'json',
              default: '',
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
            {
              key: 'max_workers',
              type: 'number',
              control: 'input',
              placeholder: '20',
              min: 1,
              max: 100,
              required: false,
              description: '동시 실행 worker 수 (1-100). DB CPU 모니터링하며 조정. 낮음=안전/느림, 높음=빠름/부하',
            },
            { ...TIMEOUT_FIELD },
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
