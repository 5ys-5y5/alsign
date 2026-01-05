/**
 * BottomPanel - Global Status and LOG monitoring panel.
 *
 * Supports bottom and right panel positions (Cursor-style layout switching).
 * Supports mouse-drag resizing.
 * Uses LogContext for global state management.
 */

import React, { useState, useRef, useCallback } from 'react';
import { useLog } from '../contexts/LogContext';

/**
 * BottomPanel component.
 */
export default function BottomPanel() {
  const {
    requests,
    logs,
    panelOpen,
    panelPosition,
    panelSize,
    setPanelOpen,
    setPanelSize,
    handlePositionChange,
    handleClearAll,
    handleCancelRequest,
  } = useLog();

  const [activeTab, setActiveTab] = useState('status');
  const [selectedRequestId, setSelectedRequestId] = useState(null);
  const [isResizing, setIsResizing] = useState(false);
  const [headerHeight, setHeaderHeight] = useState(52);
  const logEndRef = useRef(null);
  const detailsEndRef = useRef(null);

  // Dynamically measure navigation height
  React.useEffect(() => {
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

  // Panel position styles
  const isRightPanel = panelPosition === 'right';
  const headerHeightPx = `${headerHeight}px`;

  // Handle resize mouse events
  const handleMouseDown = useCallback((e) => {
    e.preventDefault();
    setIsResizing(true);
  }, []);

  React.useEffect(() => {
    if (!isResizing) return;

    const handleMouseMove = (e) => {
      if (isRightPanel) {
        const newWidth = Math.max(300, Math.min(800, window.innerWidth - e.clientX));
        setPanelSize(newWidth);
      } else {
        const newHeight = Math.max(200, Math.min(600, window.innerHeight - e.clientY));
        setPanelSize(newHeight);
      }
    };

    const handleMouseUp = () => {
      setIsResizing(false);
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isResizing, isRightPanel, setPanelSize]);

  // Resize handle styles
  const resizeHandleStyles = isRightPanel
    ? {
        position: 'absolute',
        top: 0,
        left: 0,
        width: '6px',
        height: '100%',
        cursor: 'ew-resize',
        backgroundColor: isResizing ? 'var(--accent-primary)' : 'transparent',
        transition: isResizing ? 'none' : 'background-color 0.2s',
        zIndex: 10,
      }
    : {
        position: 'absolute',
        top: 0,
        left: 0,
        right: 0,
        height: '6px',
        cursor: 'ns-resize',
        backgroundColor: isResizing ? 'var(--accent-primary)' : 'transparent',
        transition: isResizing ? 'none' : 'background-color 0.2s',
        zIndex: 10,
      };

  const panelStyles = isRightPanel
    ? {
        position: 'fixed',
        top: 0,
        right: 0,
        bottom: 0,
        width: `${panelSize}px`,
        backgroundColor: 'var(--bg-secondary)',
        borderLeft: '2px solid var(--border)',
        zIndex: 1000,
        display: 'flex',
        flexDirection: 'column',
        transition: isResizing ? 'none' : 'width 0.1s ease-out',
      }
    : {
        position: 'fixed',
        bottom: 0,
        left: 0,
        right: 0,
        height: `${panelSize}px`,
        backgroundColor: 'var(--bg-secondary)',
        borderTop: '2px solid var(--border)',
        zIndex: 1000,
        display: 'flex',
        flexDirection: 'column',
        transition: isResizing ? 'none' : 'height 0.1s ease-out',
      };

  const collapsedStyles = isRightPanel
    ? {
        position: 'fixed',
        top: 0,
        right: 0,
        bottom: 0,
        width: '48px',
        backgroundColor: 'var(--bg-secondary)',
        borderLeft: '2px solid var(--border)',
        zIndex: 1000,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'flex-start',
        paddingTop: 'var(--space-4)',
        transition: 'all 0.2s ease-in-out',
      }
    : {
        position: 'fixed',
        bottom: 0,
        left: 0,
        right: 0,
        backgroundColor: 'var(--bg-secondary)',
        borderTop: '2px solid var(--border)',
        zIndex: 1000,
        transition: 'all 0.2s ease-in-out',
      };

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

  const onToggle = () => setPanelOpen(!panelOpen);

  if (!panelOpen) {
    return (
      <div style={collapsedStyles}>
        {isRightPanel ? (
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: 'var(--space-3)',
              paddingTop: 'var(--space-2)',
              width: '100%',
            }}
          >
            <button
              onClick={onToggle}
              style={{
                background: 'var(--accent-primary)',
                border: 'none',
                borderRadius: 'var(--rounded-lg)',
                cursor: 'pointer',
                padding: '8px',
                color: 'white',
                fontSize: '14px',
                width: '36px',
                height: '36px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
              title="Expand panel"
            >
              ◀
            </button>

            <button
              onClick={() => handlePositionChange('bottom')}
              style={{
                background: 'none',
                border: '1px solid var(--border)',
                borderRadius: 'var(--rounded-lg)',
                cursor: 'pointer',
                padding: '8px',
                color: 'var(--text-secondary)',
                fontSize: '12px',
                width: '36px',
                height: '36px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
              title="Move to bottom"
            >
              ⬇
            </button>

            <div
              style={{
                writingMode: 'vertical-rl',
                textOrientation: 'mixed',
                display: 'flex',
                alignItems: 'center',
                gap: 'var(--space-1)',
                padding: 'var(--space-2) 0',
              }}
            >
              <span
                style={{
                  backgroundColor: requests.length > 0 ? 'var(--accent-primary)' : 'var(--border)',
                  color: requests.length > 0 ? 'white' : 'var(--text-dim)',
                  padding: '4px 6px',
                  borderRadius: 'var(--rounded-lg)',
                  fontSize: 'var(--text-xs)',
                  fontWeight: 'var(--font-semibold)',
                }}
              >
                {requests.length}
              </span>
              <span
                style={{
                  fontSize: 'var(--text-xs)',
                  color: 'var(--text-secondary)',
                  fontWeight: 'var(--font-medium)',
                }}
              >
                Logs
              </span>
            </div>
          </div>
        ) : (
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
            <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  handlePositionChange(isRightPanel ? 'bottom' : 'right');
                }}
                style={{
                  background: 'none',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--rounded-lg)',
                  cursor: 'pointer',
                  padding: '2px 6px',
                  fontSize: 'var(--text-xs)',
                  color: 'var(--text-dim)',
                }}
                title={isRightPanel ? 'Move to bottom' : 'Move to right'}
              >
                {isRightPanel ? '⬇' : '➡'}
              </button>
              <span style={{ fontSize: 'var(--text-sm)', color: 'var(--text-dim)' }}>▲ Expand</span>
            </div>
          </div>
        )}
      </div>
    );
  }

  return (
    <div style={panelStyles}>
      {/* Resize Handle */}
      <div
        style={resizeHandleStyles}
        onMouseDown={handleMouseDown}
        onMouseEnter={(e) => {
          e.currentTarget.style.backgroundColor = 'var(--accent-primary)';
          e.currentTarget.style.opacity = '0.5';
        }}
        onMouseLeave={(e) => {
          if (!isResizing) {
            e.currentTarget.style.backgroundColor = 'transparent';
            e.currentTarget.style.opacity = '1';
          }
        }}
      />

      {/* Header */}
      <div
        style={{
          padding: 'var(--space-2) var(--space-3)',
          borderBottom: '1px solid var(--border)',
          display: 'flex',
          alignItems: isRightPanel ? 'flex-start' : 'center',
          justifyContent: 'space-between',
          flexDirection: isRightPanel ? 'column' : 'row',
          gap: isRightPanel ? 'var(--space-2)' : '0',
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 'var(--space-2)',
            flexWrap: isRightPanel ? 'wrap' : 'nowrap',
          }}
        >
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
              <span style={{ marginLeft: 'var(--space-1)', opacity: 0.7 }}>(Selected)</span>
            )}
          </button>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
          <button onClick={handleClearAll} className="btn btn-sm btn-outline">
            Clear All
          </button>
          <button
            onClick={() => handlePositionChange(isRightPanel ? 'bottom' : 'right')}
            className="btn btn-sm btn-outline"
            title={isRightPanel ? 'Move panel to bottom' : 'Move panel to right'}
            style={{ padding: '4px 8px', minWidth: 'auto' }}
          >
            {isRightPanel ? '⬇' : '➡'}
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
            {isRightPanel ? '▶ Collapse' : '▼ Collapse'}
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
                          {req.query && <span style={{ color: 'var(--text-dim)' }}>?{req.query}</span>}
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
              <div className="empty-state">No logs yet. Execute an API request to see logs here.</div>
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
                    backgroundColor:
                      selectedRequestId === log.requestId ? 'var(--surface)' : 'transparent',
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
            ) : (
              (() => {
                const selectedRequest = requests.find((req) => req.id === selectedRequestId);
                if (!selectedRequest) {
                  return <div className="empty-state">Selected request not found.</div>;
                }

                const detailedLogs = selectedRequest.detailedLogs || [];

                const getLatestProgress = () => {
                  for (let i = detailedLogs.length - 1; i >= 0; i--) {
                    const log = detailedLogs[i];
                    if (typeof log !== 'string') continue;

                    const progressMatch =
                      log.match(/progress=(\d+)\/(\d+)\((\d+(?:\.\d+)?)%\)/) ||
                      log.match(/\[TICKER PROGRESS\]\s*(\d+)\/(\d+)\s*\((\d+(?:\.\d+)?)%\)/) ||
                      log.match(/(\d+)\/(\d+)\s*\((\d+(?:\.\d+)?)%\)/);
                    const etaMatch = log.match(/ETA:\s*([^\n|]+)/i) || log.match(/eta=(\d+)ms/);

                    if (progressMatch) {
                      return {
                        done: parseInt(progressMatch[1]),
                        total: parseInt(progressMatch[2]),
                        pct: parseFloat(progressMatch[3]),
                        eta: etaMatch ? etaMatch[1].trim() : null,
                      };
                    }
                  }
                  return null;
                };

                const progress = getLatestProgress();

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
                      <div
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          marginBottom: 'var(--space-1)',
                        }}
                      >
                        <div style={{ fontWeight: 'var(--font-semibold)' }}>
                          {selectedRequest.method} {selectedRequest.path}
                          {selectedRequest.query && `?${selectedRequest.query}`}
                        </div>
                        {selectedRequest.status === 'pending' && selectedRequest.eventSource && (
                          <button
                            onClick={() => handleCancelRequest?.(selectedRequest.id)}
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
                        <span>
                          Duration: {selectedRequest.duration ? formatDuration(selectedRequest.duration) : '-'}
                        </span>
                        <span>Time: {formatTime(selectedRequest.startTime)}</span>
                      </div>
                    </div>

                    {/* Progress Bar */}
                    {progress && (
                      <div
                        style={{
                          padding: 'var(--space-2)',
                          backgroundColor: 'var(--surface)',
                          borderRadius: 'var(--rounded-lg)',
                          border: '1px solid var(--border)',
                          marginBottom: 'var(--space-2)',
                        }}
                      >
                        <div
                          style={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'center',
                            marginBottom: 'var(--space-1)',
                          }}
                        >
                          <span style={{ fontSize: 'var(--text-sm)', fontWeight: 'var(--font-semibold)' }}>
                            📊 Progress: {progress.done} / {progress.total} ({progress.pct.toFixed(1)}%)
                          </span>
                          {progress.eta && (
                            <span style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)' }}>
                              ⏱️ ETA: {progress.eta}
                            </span>
                          )}
                        </div>
                        <div
                          style={{
                            width: '100%',
                            height: '8px',
                            backgroundColor: 'var(--border)',
                            borderRadius: 'var(--rounded-lg)',
                            overflow: 'hidden',
                          }}
                        >
                          <div
                            style={{
                              width: `${Math.min(progress.pct, 100)}%`,
                              height: '100%',
                              backgroundColor: progress.pct >= 100 ? '#10b981' : '#3b82f6',
                              borderRadius: 'var(--rounded-lg)',
                              transition: 'width 0.3s ease-in-out',
                            }}
                          />
                        </div>
                        {selectedRequest.status === 'pending' && (
                          <div
                            style={{
                              fontSize: 'var(--text-xs)',
                              color: 'var(--text-secondary)',
                              marginTop: 'var(--space-1)',
                              textAlign: 'center',
                            }}
                          >
                            🔄 Processing...
                          </div>
                        )}
                        {selectedRequest.status === 'success' && progress.pct >= 100 && (
                          <div
                            style={{
                              fontSize: 'var(--text-xs)',
                              color: '#10b981',
                              marginTop: 'var(--space-1)',
                              textAlign: 'center',
                            }}
                          >
                            ✅ Completed!
                          </div>
                        )}
                      </div>
                    )}

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
              })()
            )}
          </div>
        )}
      </div>
    </div>
  );
}
