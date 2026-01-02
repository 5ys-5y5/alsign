/**
 * LogContext - Global state management for request logs
 *
 * Provides persistent log state across route changes.
 * Logs are preserved when navigating between pages.
 */

import React, { createContext, useContext, useState, useCallback } from 'react';

const LogContext = createContext(null);

/**
 * LogProvider component - Wraps the app to provide log state
 */
export function LogProvider({ children }) {
  const [requests, setRequests] = useState([]);
  const [logs, setLogs] = useState([]);
  const [panelOpen, setPanelOpen] = useState(true);
  const [panelPosition, setPanelPosition] = useState('bottom'); // 'bottom' | 'right'
  const [panelSize, setPanelSize] = useState(400);

  const handlePositionChange = useCallback((newPosition) => {
    setPanelPosition(newPosition);
    setPanelSize(newPosition === 'right' ? 480 : 400);
  }, []);

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
    const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
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
        await fetch(cancelEndpoint, { method: 'POST' });
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

  const value = {
    // State
    requests,
    logs,
    panelOpen,
    panelPosition,
    panelSize,
    // Actions
    setPanelOpen,
    setPanelSize,
    handlePositionChange,
    handleRequestStart,
    handleRequestComplete,
    handleLog,
    handleClearAll,
    handleCancelRequest,
  };

  return <LogContext.Provider value={value}>{children}</LogContext.Provider>;
}

/**
 * useLog hook - Access log context from any component
 */
export function useLog() {
  const context = useContext(LogContext);
  if (!context) {
    throw new Error('useLog must be used within a LogProvider');
  }
  return context;
}

export default LogContext;
