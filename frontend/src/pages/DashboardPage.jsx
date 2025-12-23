/**
 * DashboardPage Component
 *
 * Main dashboard page displaying KPI cards, performance summary, and day-offset metrics.
 * Based on alsign/prompt/2_designSystem.ini route contract for dashboard route.
 */

import React, { useState, useEffect } from 'react';
import KPICard from '../components/dashboard/KPICard';
import PerformanceTable from '../components/dashboard/PerformanceTable';
import DayOffsetTable from '../components/dashboard/DayOffsetTable';

// API base URL from environment or default to localhost
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

/**
 * Format date string for display.
 *
 * @param {string} dateString - ISO date string
 * @returns {string} Formatted date string
 */
function formatDate(dateString) {
  if (!dateString) return 'N/A';
  try {
    const date = new Date(dateString);
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
  } catch (e) {
    return dateString;
  }
}

/**
 * DashboardPage component.
 *
 * @returns {JSX.Element} Dashboard page
 */
export default function DashboardPage() {
  // KPIs state
  const [kpis, setKpis] = useState({ coverage: 0, dataFreshness: null });
  const [kpisLoading, setKpisLoading] = useState(true);
  const [kpisError, setKpisError] = useState(null);

  // Performance summary state
  const [performanceData, setPerformanceData] = useState([]);
  const [performanceLoading, setPerformanceLoading] = useState(true);
  const [performanceError, setPerformanceError] = useState(null);

  // Day-offset metrics state
  const [dayOffsetData, setDayOffsetData] = useState([]);
  const [dayOffsetLoading, setDayOffsetLoading] = useState(true);
  const [dayOffsetError, setDayOffsetError] = useState(null);

  // Day-offset groupBy selector
  const [groupBy, setGroupBy] = useState('sector');

  // Fetch KPIs
  useEffect(() => {
    async function fetchKPIs() {
      try {
        setKpisLoading(true);
        setKpisError(null);
        const response = await fetch(`${API_BASE_URL}/dashboard/kpis`);
        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}));
          const errorMessage = errorData.detail || errorData.error?.message || `HTTP ${response.status}`;
          throw new Error(errorMessage);
        }
        const data = await response.json();
        setKpis(data);

        // Warn if database is empty
        if (data.coverage === 0) {
          setKpisError('Database is empty. Please populate data first: 1) Run GET /sourceData to collect foundation data, 2) POST /setEventsTable to consolidate events, 3) POST /backfillEventsTable to calculate metrics.');
        }
      } catch (error) {
        console.error('Failed to fetch KPIs:', error);
        setKpisError(error.message || 'Failed to connect to backend. Please ensure the backend server is running on port 8000.');
      } finally {
        setKpisLoading(false);
      }
    }

    fetchKPIs();
  }, []);

  // Fetch performance summary
  useEffect(() => {
    async function fetchPerformanceSummary() {
      try {
        setPerformanceLoading(true);
        setPerformanceError(null);
        // Fetch first page with reasonable page size
        const response = await fetch(
          `${API_BASE_URL}/dashboard/performanceSummary?page=1&pageSize=100`
        );
        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}));
          const errorMessage = errorData.detail || errorData.error?.message || `HTTP ${response.status}`;
          throw new Error(errorMessage);
        }
        const result = await response.json();
        setPerformanceData(result.data);

        // Warn if no data found
        if (result.data.length === 0 || result.total === 0) {
          setPerformanceError('No events in database. To populate data: 1) Run GET /sourceData to collect foundation data, 2) POST /setEventsTable to consolidate events, 3) POST /backfillEventsTable to calculate metrics.');
        }
      } catch (error) {
        console.error('Failed to fetch performance summary:', error);
        setPerformanceError(error.message || 'Failed to connect to backend. Please ensure the backend server is running on port 8000.');
      } finally {
        setPerformanceLoading(false);
      }
    }

    fetchPerformanceSummary();
  }, []);

  // Fetch day-offset metrics
  useEffect(() => {
    async function fetchDayOffsetMetrics() {
      try {
        setDayOffsetLoading(true);
        setDayOffsetError(null);
        const response = await fetch(
          `${API_BASE_URL}/dashboard/dayOffsetMetrics?groupBy=${groupBy}`
        );
        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}));
          const errorMessage = errorData.detail || errorData.error?.message || `HTTP ${response.status}`;
          throw new Error(errorMessage);
        }
        const result = await response.json();
        setDayOffsetData(result.data);

        // Warn if no data found
        if (result.data.length === 0 || result.total === 0) {
          setDayOffsetError('No metrics available. Database needs to be populated with market data first. Please run API endpoints in this order: 1) GET /sourceData (collect foundation data), 2) POST /setEventsTable (consolidate events), 3) POST /backfillEventsTable (calculate metrics).');
        }
      } catch (error) {
        console.error('Failed to fetch day-offset metrics:', error);
        setDayOffsetError(error.message || 'Failed to connect to backend. Please ensure the backend server is running on port 8000.');
      } finally {
        setDayOffsetLoading(false);
      }
    }

    fetchDayOffsetMetrics();
  }, [groupBy]);

  return (
    <div
      style={{
        padding: 'var(--space-4)',
        maxWidth: '1400px',
        margin: '0 auto',
      }}
    >
      {/* Page Header */}
      <header style={{ marginBottom: 'var(--space-4)' }}>
        <h1>Dashboard</h1>
        <p style={{ color: 'var(--text-dim)', fontSize: 'var(--text-sm)' }}>
          Performance metrics and KPIs for financial data
        </p>
      </header>

      {/* KPI Cards Section */}
      <section style={{ marginBottom: 'var(--space-5)' }}>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))',
            gap: 'var(--space-3)',
          }}
        >
          {kpisLoading ? (
            <div className="loading">Loading KPIs...</div>
          ) : kpisError ? (
            <div className="alert alert-error">Error loading KPIs: {kpisError}</div>
          ) : (
            <>
              <KPICard
                title="Coverage"
                value={kpis.coverage.toLocaleString()}
                subtitle="Active tickers"
              />
              <KPICard
                title="Data Freshness"
                value={formatDate(kpis.dataFreshness)}
                subtitle="Last market holiday update"
              />
            </>
          )}
        </div>
      </section>

      {/* Performance Summary Section */}
      <section style={{ marginBottom: 'var(--space-5)' }}>
        {performanceError ? (
          <div className="alert alert-error">
            Error loading performance summary: {performanceError}
          </div>
        ) : (
          <PerformanceTable data={performanceData} loading={performanceLoading} />
        )}
      </section>

      {/* Day-Offset Metrics Section */}
      <section>
        {/* GroupBy Selector */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 'var(--space-2)',
            marginBottom: 'var(--space-3)',
          }}
        >
          <label
            htmlFor="groupBy"
            style={{
              fontSize: 'var(--text-sm)',
              fontWeight: 'var(--font-medium)',
              color: 'var(--text)',
            }}
          >
            Group by:
          </label>
          <select
            id="groupBy"
            value={groupBy}
            onChange={(e) => setGroupBy(e.target.value)}
            style={{
              padding: 'var(--space-1) var(--space-2)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--rounded-lg)',
              fontSize: 'var(--text-sm)',
              backgroundColor: 'white',
            }}
          >
            <option value="sector">Sector</option>
            <option value="industry">Industry</option>
            <option value="source">Source</option>
            <option value="analyst">Analyst</option>
          </select>
        </div>

        {dayOffsetError ? (
          <div className="alert alert-error">
            Error loading day-offset metrics: {dayOffsetError}
          </div>
        ) : (
          <DayOffsetTable data={dayOffsetData} loading={dayOffsetLoading} />
        )}
      </section>
    </div>
  );
}
