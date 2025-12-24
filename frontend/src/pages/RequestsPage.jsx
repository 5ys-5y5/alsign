/**
 * RequestsPage Component
 *
 * Request forms for backend API endpoints with Status/LOG monitoring panel.
 * Based on alsign/prompt/2_designSystem.ini request_contract.
 */

import React, { useState, useRef, useCallback } from 'react';

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

      eventSource.onerror = () => {
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
            {queryFields.map((field) => (
              <div key={field.key} style={{ marginBottom: 'var(--space-2)' }}>
                <label
                  style={{
                    display: 'block',
                    fontSize: 'var(--text-sm)',
                    marginBottom: 'var(--space-1)',
                  }}
                >
                  {field.label || field.key}
                  {field.required && <span style={{ color: 'var(--accent-danger)' }}>*</span>}
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
                  />
                ) : (
                  <input
                    type="text"
                    value={queryParams[field.key] || ''}
                    onChange={(e) => handleQueryChange(field.key, e.target.value)}
                    placeholder={field.placeholder}
                  />
                )}
              </div>
            ))}
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
 * BottomPanel - Status and LOG monitoring panel.
 */
function BottomPanel({ requests, logs, isOpen, onToggle, onClear, onCancelRequest }) {
  const [activeTab, setActiveTab] = useState('status');
  const [selectedRequestId, setSelectedRequestId] = useState(null);
  const logEndRef = useRef(null);
  const detailsEndRef = useRef(null);

  const scrollToBottom = useCallback(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  React.useEffect(() => {
    if (activeTab === 'logs') {
      scrollToBottom();
    }
  }, [logs, activeTab, scrollToBottom]);

  const formatTime = (timestamp) => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString('en-US', { hour12: false });
  };

  const formatDuration = (ms) => {
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(2)}s`;
  };

  const getStatusBadge = (status) => {
    const styles = {
      pending: { backgroundColor: '#fef3c7', color: '#92400e' },
      success: { backgroundColor: '#d1fae5', color: '#065f46' },
      error: { backgroundColor: '#fee2e2', color: '#991b1b' },
    };

    return (
      <span
        style={{
          ...styles[status],
          padding: '2px var(--space-1)',
          borderRadius: 'var(--rounded-lg)',
          fontSize: 'var(--text-xs)',
          fontWeight: 'var(--font-medium)',
          textTransform: 'uppercase',
        }}
      >
        {status}
      </span>
    );
  };

  const getLogLevelBadge = (level) => {
    const styles = {
      info: { backgroundColor: '#dbeafe', color: '#1e40af' },
      success: { backgroundColor: '#d1fae5', color: '#065f46' },
      error: { backgroundColor: '#fee2e2', color: '#991b1b' },
    };

    return (
      <span
        style={{
          ...styles[level],
          padding: '2px var(--space-1)',
          borderRadius: 'var(--rounded-lg)',
          fontSize: 'var(--text-xs)',
          fontWeight: 'var(--font-medium)',
          textTransform: 'uppercase',
          minWidth: '60px',
          display: 'inline-block',
          textAlign: 'center',
        }}
      >
        {level}
      </span>
    );
  };

  if (!isOpen) {
    return (
      <div
        style={{
          position: 'fixed',
          bottom: 0,
          left: 0,
          right: 0,
          backgroundColor: 'white',
          borderTop: '2px solid var(--border)',
          zIndex: 'var(--z-toolbar)',
        }}
      >
        <div
          style={{
            padding: 'var(--space-2) var(--space-3)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            cursor: 'pointer',
          }}
          onClick={onToggle}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
            <span style={{ fontSize: 'var(--text-sm)', fontWeight: 'var(--font-semibold)' }}>
              Status & Logs
            </span>
            <span
              style={{
                backgroundColor: 'var(--accent-primary)',
                color: 'white',
                padding: '2px var(--space-1)',
                borderRadius: 'var(--rounded-lg)',
                fontSize: 'var(--text-xs)',
                fontWeight: 'var(--font-medium)',
              }}
            >
              {requests.length} requests, {logs.length} logs
            </span>
          </div>
          <span style={{ fontSize: 'var(--text-sm)', color: 'var(--text-dim)' }}>▲ Expand</span>
        </div>
      </div>
    );
  }

  return (
    <div
      style={{
        position: 'fixed',
        bottom: 0,
        left: 0,
        right: 0,
        height: '400px',
        backgroundColor: 'white',
        borderTop: '2px solid var(--border)',
        zIndex: 'var(--z-toolbar)',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {/* Header */}
      <div
        style={{
          padding: 'var(--space-2) var(--space-3)',
          borderBottom: '1px solid var(--border)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
          <button
            onClick={() => setActiveTab('status')}
            className={activeTab === 'status' ? 'btn btn-sm btn-primary' : 'btn btn-sm btn-outline'}
          >
            Status ({requests.length})
          </button>
          <button
            onClick={() => setActiveTab('logs')}
            className={activeTab === 'logs' ? 'btn btn-sm btn-primary' : 'btn btn-sm btn-outline'}
          >
            Logs ({logs.length})
          </button>
          <button
            onClick={() => setActiveTab('details')}
            className={activeTab === 'details' ? 'btn btn-sm btn-primary' : 'btn btn-sm btn-outline'}
          >
            Log Details
            {selectedRequestId && (
              <span style={{ marginLeft: 'var(--space-1)', opacity: 0.7 }}>
                (Selected)
              </span>
            )}
          </button>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
          <button onClick={onClear} className="btn btn-sm btn-outline">
            Clear All
          </button>
          <button
            onClick={onToggle}
            style={{
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              fontSize: 'var(--text-sm)',
              color: 'var(--text-dim)',
            }}
          >
            ▼ Collapse
          </button>
        </div>
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflowY: 'auto', padding: 'var(--space-2)' }}>
        {activeTab === 'status' && (
          <div className="table-shell" style={{ height: '100%' }}>
            <div className="scroll-y" style={{ maxHeight: '100%' }}>
              <table>
                <thead>
                  <tr>
                    <th style={{ width: '80px' }}>Time</th>
                    <th style={{ width: '80px' }}>Method</th>
                    <th>Path</th>
                    <th style={{ width: '100px' }}>Status</th>
                    <th style={{ width: '80px' }}>Code</th>
                    <th style={{ width: '100px' }}>Duration</th>
                  </tr>
                </thead>
                <tbody>
                  {requests.length === 0 ? (
                    <tr>
                      <td colSpan="6" className="empty-state">
                        No requests yet. Execute an API request to see status here.
                      </td>
                    </tr>
                  ) : (
                    requests.map((req) => (
                      <tr key={req.id}>
                        <td style={{ fontSize: 'var(--text-xs)', fontFamily: 'monospace' }}>
                          {formatTime(req.startTime)}
                        </td>
                        <td>
                          <span
                            style={{
                              fontSize: 'var(--text-xs)',
                              fontWeight: 'var(--font-semibold)',
                              fontFamily: 'monospace',
                            }}
                          >
                            {req.method}
                          </span>
                        </td>
                        <td style={{ fontFamily: 'monospace', fontSize: 'var(--text-sm)' }}>
                          {req.path}
                          {req.query && (
                            <span style={{ color: 'var(--text-dim)' }}>?{req.query}</span>
                          )}
                        </td>
                        <td>{getStatusBadge(req.status)}</td>
                        <td style={{ fontFamily: 'monospace', fontSize: 'var(--text-sm)' }}>
                          {req.statusCode || '-'}
                        </td>
                        <td style={{ fontFamily: 'monospace', fontSize: 'var(--text-sm)' }}>
                          {req.duration ? formatDuration(req.duration) : '-'}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {activeTab === 'logs' && (
          <div style={{ fontFamily: 'monospace', fontSize: 'var(--text-xs)' }}>
            {logs.length === 0 ? (
              <div className="empty-state">
                No logs yet. Execute an API request to see logs here.
              </div>
            ) : (
              logs.map((log, index) => (
                <div
                  key={index}
                  style={{
                    padding: 'var(--space-1)',
                    borderBottom: '1px solid var(--border)',
                    display: 'flex',
                    gap: 'var(--space-2)',
                    alignItems: 'flex-start',
                    cursor: log.requestId ? 'pointer' : 'default',
                    backgroundColor: selectedRequestId === log.requestId ? 'var(--surface)' : 'transparent',
                  }}
                  onClick={() => {
                    if (log.requestId) {
                      setSelectedRequestId(log.requestId);
                      setActiveTab('details');
                    }
                  }}
                >
                  <span style={{ color: 'var(--text-dim)', minWidth: '80px' }}>
                    {formatTime(log.timestamp)}
                  </span>
                  {getLogLevelBadge(log.level)}
                  <span style={{ flex: 1, color: 'var(--text)' }}>{log.message}</span>
                  {log.requestId && (
                    <span
                      style={{
                        color: 'var(--text-dim)',
                        fontSize: '0.75em',
                        padding: '2px 4px',
                        backgroundColor: 'var(--surface)',
                        borderRadius: 'var(--rounded-sm)',
                      }}
                    >
                      Click for details →
                    </span>
                  )}
                </div>
              ))
            )}
            <div ref={logEndRef} />
          </div>
        )}

        {activeTab === 'details' && (
          <div style={{ fontFamily: 'monospace', fontSize: 'var(--text-xs)' }}>
            {!selectedRequestId ? (
              <div className="empty-state">
                No request selected. Click on a log entry in the Logs tab to view detailed logs.
              </div>
            ) : (() => {
              const selectedRequest = requests.find((req) => req.id === selectedRequestId);
              if (!selectedRequest) {
                return (
                  <div className="empty-state">
                    Selected request not found.
                  </div>
                );
              }

              const detailedLogs = selectedRequest.detailedLogs || [];

              return (
                <div>
                  {/* Request Header */}
                  <div
                    style={{
                      padding: 'var(--space-2)',
                      backgroundColor: 'var(--surface)',
                      borderBottom: '2px solid var(--border)',
                      marginBottom: 'var(--space-2)',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-1)' }}>
                      <div style={{ fontWeight: 'var(--font-semibold)' }}>
                        {selectedRequest.method} {selectedRequest.path}
                        {selectedRequest.query && `?${selectedRequest.query}`}
                      </div>
                      {selectedRequest.status === 'pending' && selectedRequest.eventSource && (
                        <button
                          onClick={() => onCancelRequest?.(selectedRequest.id)}
                          className="btn btn-sm btn-outline"
                          style={{ color: 'var(--accent-danger)', borderColor: 'var(--accent-danger)' }}
                        >
                          Cancel
                        </button>
                      )}
                    </div>
                    <div style={{ display: 'flex', gap: 'var(--space-2)', fontSize: 'var(--text-xs)' }}>
                      <span>Status: {getStatusBadge(selectedRequest.status)}</span>
                      <span>Code: {selectedRequest.statusCode || '-'}</span>
                      <span>Duration: {selectedRequest.duration ? formatDuration(selectedRequest.duration) : '-'}</span>
                      <span>Time: {formatTime(selectedRequest.startTime)}</span>
                    </div>
                  </div>

                  {/* Detailed Logs */}
                  {detailedLogs.length === 0 ? (
                    <div className="empty-state">
                      No detailed logs available for this request.
                      <br />
                      <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)' }}>
                        (Backend must include 'detailedLogs' array in response)
                      </span>
                    </div>
                  ) : (
                    detailedLogs.map((logLine, index) => (
                      <div
                        key={index}
                        style={{
                          padding: 'var(--space-1) var(--space-2)',
                          fontFamily: 'monospace',
                          fontSize: 'var(--text-xs)',
                          color: 'var(--text)',
                        }}
                      >
                        {logLine}
                      </div>
                    ))
                  )}
                  <div ref={detailsEndRef} />
                </div>
              );
            })()}
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * RequestsPage component.
 */
export default function RequestsPage() {
  const [requests, setRequests] = useState([]);
  const [logs, setLogs] = useState([]);
  const [panelOpen, setPanelOpen] = useState(true);

  const handleRequestStart = useCallback((request) => {
    setRequests((prev) => [...prev, request]);
  }, []);

  const handleRequestComplete = useCallback((update) => {
    setRequests((prev) =>
      prev.map((req) => (req.id === update.id ? { ...req, ...update } : req))
    );
  }, []);

  const handleLog = useCallback((level, message, requestId) => {
    setLogs((prev) => [...prev, { timestamp: Date.now(), level, message, requestId }]);
  }, []);

  const handleClearAll = useCallback(() => {
    setRequests([]);
    setLogs([]);
  }, []);

  const handleCancelRequest = useCallback(async (requestId) => {
    const request = requests.find((req) => req.id === requestId);
    if (!request) return;

    // Close EventSource if it exists
    if (request.eventSource) {
      request.eventSource.close();
    }

    // Determine cancel endpoint based on request path
    let cancelEndpoint;
    if (request.path === '/sourceData') {
      cancelEndpoint = `${API_BASE_URL}/sourceData/cancel/${requestId}`;
    } else if (request.path === '/setEventsTable') {
      cancelEndpoint = `${API_BASE_URL}/setEventsTable/cancel/${requestId}`;
    } else if (request.path === '/backfillEventsTable') {
      cancelEndpoint = `${API_BASE_URL}/backfillEventsTable/cancel/${requestId}`;
    }

    // Call backend cancel endpoint
    if (cancelEndpoint) {
      try {
        await fetch(cancelEndpoint, {
          method: 'POST',
        });
      } catch (err) {
        console.error('Failed to cancel request:', err);
      }
    }

    // Update request status
    setRequests((prev) =>
      prev.map((req) =>
        req.id === requestId
          ? { ...req, status: 'error', error: 'Cancelled by user', eventSource: null }
          : req
      )
    );

    handleLog('error', 'Request cancelled by user', requestId);
  }, [requests, handleLog]);

  return (
    <>
      <div style={{ padding: 'var(--space-4)', maxWidth: '1200px', margin: '0 auto', paddingBottom: panelOpen ? '420px' : '80px' }}>
        <header style={{ marginBottom: 'var(--space-4)' }}>
          <h1>Requests</h1>
          <p style={{ color: 'var(--text-dim)', fontSize: 'var(--text-sm)' }}>
            Execute backend API requests
          </p>
        </header>

        {/* GET /sourceData */}
        <RequestForm
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
              options: ['maintenance'],
              required: false,
            },
          ]}
          onRequestStart={handleRequestStart}
          onRequestComplete={handleRequestComplete}
          onLog={handleLog}
        />

        {/* POST /setEventsTable */}
        <RequestForm
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
        />

        {/* POST /backfillEventsTable */}
        <RequestForm
          title="POST /backfillEventsTable"
          method="POST"
          path="/backfillEventsTable"
          queryFields={[
            {
              key: 'overwrite',
              type: 'boolean',
              control: 'checkbox',
              required: false,
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
        />

        {/* POST /fillAnalyst */}
        <RequestForm
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
        />
      </div>

      <BottomPanel
        requests={requests}
        logs={logs}
        isOpen={panelOpen}
        onToggle={() => setPanelOpen(!panelOpen)}
        onClear={handleClearAll}
        onCancelRequest={handleCancelRequest}
      />
    </>
  );
}
