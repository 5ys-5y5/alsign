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
  const [highlightedVerboseIndex, setHighlightedVerboseIndex] = useState(null);
  const [isResizing, setIsResizing] = useState(false);
  const [headerHeight, setHeaderHeight] = useState(52);
  const [logFilters, setLogFilters] = useState(() => {
    // Load filters from localStorage
    const saved = localStorage.getItem('logFilters');
    return saved ? JSON.parse(saved) : {};
  });
  const detailsEndRef = useRef(null);

  // Save filters to localStorage whenever they change
  React.useEffect(() => {
    localStorage.setItem('logFilters', JSON.stringify(logFilters));
  }, [logFilters]);

  // Extract log patterns from logs
  const extractLogPatterns = useCallback((logs) => {
    const patterns = new Set();
    logs.forEach((log) => {
      const match = log.match(/^\[([^\]]+)\]/);
      if (match) {
        patterns.add(match[1]);
      }
    });
    return Array.from(patterns).sort();
  }, []);

  // Apply filters to logs
  const applyFilters = useCallback((logs) => {
    if (Object.keys(logFilters).length === 0) return logs;
    return logs.filter((log) => {
      const match = log.match(/^\[([^\]]+)\]/);
      if (!match) return true; // No pattern, always show
      const pattern = match[1];
      return logFilters[pattern] !== false; // Show if not explicitly hidden
    });
  }, [logFilters]);

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

  const formatIndexedLog = (index, line) => {
    const paddedIndex = String(index).padStart(4, '0');
    return `${paddedIndex} | ${line}`;
  };

  const extractPhase = (line) => {
    if (typeof line !== 'string') return null;
    const headerMatch = line.match(/^\[([^\]]+)\]/);
    if (!headerMatch) return null;
    const parts = headerMatch[1].split('|').map((part) => part.trim());
    return parts[1] || null;
  };

  const buildSummaryLogs = (lines) => {
    const summaryEntries = [];
    const includedIndexes = new Set();
    const seenPhases = new Set();
    const lastProgressPctByPhase = new Map();

    lines.forEach((line, idx) => {
      if (typeof line !== 'string') return;

      const index = idx + 1;
      const phase = extractPhase(line);
      const phaseKey = phase || 'global';

      const isFirstLine = idx === 0;
      const isLastLine = idx === lines.length - 1;

      const progressMatch = line.match(/progress=(\d+)\/(\d+)\((\d+(?:\.\d+)?)%\)/);
      const progressPct = progressMatch ? parseFloat(progressMatch[3]) : null;
      const lastPct = lastProgressPctByPhase.get(phaseKey);

      const isProgressMilestone =
        progressPct !== null &&
        (progressPct === 0 || progressPct >= 100 || lastPct === undefined || progressPct - lastPct >= 10);

      if (isProgressMilestone) {
        lastProgressPctByPhase.set(phaseKey, progressPct);
      }

      const warnPresent = line.includes('warn=[') && !line.includes('warn=[]');
      const failMatch = line.match(/fail=(\d+)/);
      const failCount = failMatch ? parseInt(failMatch[1], 10) : 0;
      const isFailure = failCount > 0;
      const isError = line.toLowerCase().includes('error');

      const hasProgress = line.includes('progress=') || line.includes('ETA:') || line.includes('[PROGRESS]');

      const isStageLine =
        line.startsWith('[Phase ') ||
        line.startsWith('[DB-Cache]') ||
        line.startsWith('[select_events_for_valuation]') ||
        line.startsWith('[backfillEventsTable]') ||
        line.startsWith('[STREAM]') ||
        line.includes('| request_start]') ||
        line.includes('| request_complete]') ||
        line.includes('| complete]') ||
        line.includes(' START ') ||
        line.includes(' starting') ||
        line.includes(' completed');

      const hasRowId =
        line.includes('id:') ||
        line.includes('txn_events.id=') ||
        line.includes('[table:');

      const isNoisyLine = line.startsWith('[MetricEngine]');

      const phaseIsKey =
        phase &&
        (phase.includes('request_start') ||
          phase.includes('request_complete') ||
          phase.includes('complete') ||
          phase.includes('cancelled'));

      const isNewPhase = phase && !seenPhases.has(phase);

      if (
        isFirstLine ||
        isLastLine ||
        isProgressMilestone ||
        warnPresent ||
        isFailure ||
        isError ||
        hasProgress ||
        isStageLine ||
        hasRowId ||
        phaseIsKey ||
        isNewPhase
      ) {
        if (!includedIndexes.has(index) && !isNoisyLine) {
          includedIndexes.add(index);
          summaryEntries.push({ index, line });
        }
      }

      if (phase && !seenPhases.has(phase)) {
        seenPhases.add(phase);
      }
    });

    return summaryEntries;
  };

  const getLatestProgress = (lines) => {
    for (let i = lines.length - 1; i >= 0; i--) {
      const log = lines[i];
      if (typeof log !== 'string') continue;

      const progressMatch =
        log.match(/progress=(\d+)\/(\d+)\((\d+(?:\.\d+)?)%\)/) ||
        log.match(/\[TICKER PROGRESS\]\s*(\d+)\/(\d+)\s*\((\d+(?:\.\d+)?)%\)/) ||
        log.match(/(\d+)\/(\d+)\s*\((\d+(?:\.\d+)?)%\)/);
      const etaMatch = log.match(/ETA:\s*([^\n|]+)/i) || log.match(/eta=(\d+)ms/);

      if (progressMatch) {
        return {
          done: parseInt(progressMatch[1], 10),
          total: parseInt(progressMatch[2], 10),
          pct: parseFloat(progressMatch[3]),
          eta: etaMatch ? etaMatch[1].trim() : null,
        };
      }
    }
    return null;
  };

  const selectedRequest = selectedRequestId
    ? requests.find((req) => req.id === selectedRequestId)
    : null;
  const detailedLogs = selectedRequest?.detailedLogs || [];
  const filteredDetailedLogs = React.useMemo(
    () => applyFilters(detailedLogs),
    [detailedLogs, applyFilters]
  );
  const summaryLogs = React.useMemo(() => buildSummaryLogs(filteredDetailedLogs), [filteredDetailedLogs]);
  const progress = React.useMemo(() => getLatestProgress(filteredDetailedLogs), [filteredDetailedLogs]);
  const verboseLogs = React.useMemo(
    () => filteredDetailedLogs.map((line, index) => ({ index: index + 1, line })),
    [filteredDetailedLogs]
  );

  React.useEffect(() => {
    setHighlightedVerboseIndex(null);
  }, [selectedRequestId]);

  React.useEffect(() => {
    if (activeTab !== 'verbose' || !highlightedVerboseIndex || !selectedRequestId) return;
    const targetId = `verbose-log-${selectedRequestId}-${highlightedVerboseIndex}`;
    const target = document.getElementById(targetId);
    if (target) {
      target.scrollIntoView({ block: 'center', behavior: 'smooth' });
    }
  }, [activeTab, highlightedVerboseIndex, selectedRequestId]);

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
                Details
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
                Status & Details
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
                {requests.length} requests
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
          flexDirection: 'column',
          gap: 'var(--space-2)',
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: isRightPanel ? 'flex-start' : 'center',
            justifyContent: 'space-between',
            flexDirection: isRightPanel ? 'column' : 'row',
            gap: isRightPanel ? 'var(--space-2)' : '0',
            width: '100%',
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
            onClick={() => setActiveTab('details')}
            className={activeTab === 'details' ? 'btn btn-sm btn-primary' : 'btn btn-sm btn-outline'}
          >
            Log Details
            {selectedRequestId && (
              <span style={{ marginLeft: 'var(--space-1)', opacity: 0.7 }}>(Selected)</span>
            )}
          </button>
          <button
            onClick={() => setActiveTab('verbose')}
            className={activeTab === 'verbose' ? 'btn btn-sm btn-primary' : 'btn btn-sm btn-outline'}
          >
            Log Details Verbose
            {selectedRequestId && (
              <span style={{ marginLeft: 'var(--space-1)', opacity: 0.7 }}>(Selected)</span>
            )}
          </button>
          <button
            onClick={() => setActiveTab('filter')}
            className={activeTab === 'filter' ? 'btn btn-sm btn-primary' : 'btn btn-sm btn-outline'}
          >
            Log Filter
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
        {selectedRequest && progress && (
          <div
            style={{
              padding: 'var(--space-2)',
              backgroundColor: 'var(--surface)',
              borderRadius: 'var(--rounded-lg)',
              border: '1px solid var(--border)',
              boxShadow: '0 2px 8px rgba(0, 0, 0, 0.08)',
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
                ?? Progress: {progress.done} / {progress.total} ({progress.pct.toFixed(1)}%)
              </span>
              {progress.eta && (
                <span style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)' }}>
                  ?? ETA: {progress.eta}
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
          </div>
        )}
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
                      <tr
                        key={req.id}
                        onClick={() => {
                          setSelectedRequestId(req.id);
                          setActiveTab('details');
                        }}
                        style={{
                          cursor: 'pointer',
                          backgroundColor: selectedRequestId === req.id ? 'var(--surface)' : 'transparent',
                        }}
                      >
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

        {activeTab === 'details' && (
          <div style={{ fontFamily: 'monospace', fontSize: 'var(--text-xs)' }}>
            {!selectedRequestId ? (
              <div className="empty-state">
                No request selected. Click a request in Status to view log details.
              </div>
            ) : (
              (() => {
                if (!selectedRequest) {
                  return <div className="empty-state">Selected request not found.</div>;
                }

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

                    {/* Detailed Logs */}
                    {summaryLogs.length === 0 ? (
                      <div className="empty-state">
                        No detailed logs available for this request.
                        <br />
                        <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)' }}>
                          (Backend must include 'detailedLogs' array in response)
                        </span>
                      </div>
                    ) : (
                      summaryLogs.map((logEntry) => (
                        <div
                          key={logEntry.index}
                          style={{
                            padding: 'var(--space-1) var(--space-2)',
                            fontFamily: 'monospace',
                            fontSize: 'var(--text-xs)',
                            color: 'var(--text)',
                            cursor: 'pointer',
                          }}
                          onClick={() => {
                            setHighlightedVerboseIndex(logEntry.index);
                            setActiveTab('verbose');
                          }}
                        >
                          {formatIndexedLog(logEntry.index, logEntry.line)}
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

        {activeTab === 'verbose' && (
          <div style={{ fontFamily: 'monospace', fontSize: 'var(--text-xs)' }}>
            {!selectedRequestId ? (
              <div className="empty-state">
                No request selected. Click a request in Status to view verbose logs.
              </div>
            ) : !selectedRequest ? (
              <div className="empty-state">Selected request not found.</div>
            ) : (
              <div>
                
                {verboseLogs.length === 0 ? (
                  <div className="empty-state">No verbose logs available for this request.</div>
                ) : (
                  verboseLogs.map((logEntry) => (
                    <div
                      key={logEntry.index}
                      id={`verbose-log-${selectedRequestId}-${logEntry.index}`}
                      style={{
                        padding: 'var(--space-1) var(--space-2)',
                        fontFamily: 'monospace',
                        fontSize: 'var(--text-xs)',
                        color: 'var(--text)',
                        backgroundColor:
                          highlightedVerboseIndex === logEntry.index ? 'var(--surface)' : 'transparent',
                      }}
                    >
                      {formatIndexedLog(logEntry.index, logEntry.line)}
                    </div>
                  ))
                )}
              </div>
            )}
          </div>
        )}

        {activeTab === 'filter' && (
          <div>
            {!selectedRequestId ? (
              <div className="empty-state">
                No request selected. Click a request in Status to configure log filters.
              </div>
            ) : !selectedRequest ? (
              <div className="empty-state">Selected request not found.</div>
            ) : (
              <div>
                <div
                  style={{
                    padding: 'var(--space-2)',
                    backgroundColor: 'var(--surface)',
                    borderBottom: '2px solid var(--border)',
                    marginBottom: 'var(--space-2)',
                  }}
                >
                  <h4 style={{ marginBottom: 'var(--space-2)', fontWeight: 'var(--font-semibold)' }}>
                    Log Pattern Filters
                  </h4>
                  <p style={{ fontSize: 'var(--text-sm)', color: 'var(--text-dim)', marginBottom: 'var(--space-2)' }}>
                    Select log patterns to display in Log Details and Log Details Verbose tabs. Unchecked patterns will be hidden.
                  </p>
                  <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
                    <button
                      onClick={() => {
                        const logs = selectedRequest.detailedLogs || [];
                        const patterns = extractLogPatterns(logs);
                        const newFilters = {};
                        patterns.forEach((p) => (newFilters[p] = true));
                        setLogFilters(newFilters);
                      }}
                      className="btn btn-sm btn-outline"
                    >
                      Select All
                    </button>
                    <button
                      onClick={() => {
                        const logs = selectedRequest.detailedLogs || [];
                        const patterns = extractLogPatterns(logs);
                        const newFilters = {};
                        patterns.forEach((p) => (newFilters[p] = false));
                        setLogFilters(newFilters);
                      }}
                      className="btn btn-sm btn-outline"
                    >
                      Deselect All
                    </button>
                    <button
                      onClick={() => setLogFilters({})}
                      className="btn btn-sm btn-outline"
                    >
                      Reset Filters
                    </button>
                  </div>
                </div>

                {(() => {
                  const logs = selectedRequest.detailedLogs || [];
                  const patterns = extractLogPatterns(logs);

                  if (patterns.length === 0) {
                    return <div className="empty-state">No log patterns found in this request.</div>;
                  }

                  // Count logs per pattern
                  const patternCounts = {};
                  logs.forEach((log) => {
                    const match = log.match(/^\[([^\]]+)\]/);
                    if (match) {
                      const pattern = match[1];
                      patternCounts[pattern] = (patternCounts[pattern] || 0) + 1;
                    }
                  });

                  return (
                    <div style={{ padding: 'var(--space-2)' }}>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 'var(--space-2)' }}>
                        {patterns.map((pattern) => (
                          <label
                            key={pattern}
                            style={{
                              display: 'flex',
                              alignItems: 'center',
                              gap: 'var(--space-2)',
                              padding: 'var(--space-2)',
                              backgroundColor: 'var(--surface)',
                              borderRadius: 'var(--rounded-lg)',
                              cursor: 'pointer',
                              border: '1px solid var(--border)',
                            }}
                          >
                            <input
                              type="checkbox"
                              checked={logFilters[pattern] !== false}
                              onChange={(e) => {
                                setLogFilters((prev) => ({
                                  ...prev,
                                  [pattern]: e.target.checked,
                                }));
                              }}
                              style={{ cursor: 'pointer' }}
                            />
                            <span style={{ flex: 1, fontSize: 'var(--text-sm)', fontFamily: 'monospace' }}>
                              [{pattern}]
                            </span>
                            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)' }}>
                              ({patternCounts[pattern] || 0} logs)
                            </span>
                          </label>
                        ))}
                      </div>
                    </div>
                  );
                })()}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
