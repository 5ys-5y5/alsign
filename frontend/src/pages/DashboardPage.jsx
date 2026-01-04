/**
 * DashboardPage Component
 *
 * Main dashboard page displaying KPI cards and events.
 * Based on alsign/prompt/2_designSystem.ini route contract for dashboard route.
 */

import React, { useState, useEffect } from 'react';
import KPICard from '../components/dashboard/KPICard';
import EventsTable from '../components/dashboard/EventsTable';

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

  // Events state
  const [eventsData, setEventsData] = useState([]);
  const [eventsTotal, setEventsTotal] = useState(0);
  const [eventsPage, setEventsPage] = useState(1);
  const [eventsPageSize, setEventsPageSize] = useState(100);
  const [eventsLoading, setEventsLoading] = useState(true);
  const [eventsError, setEventsError] = useState(null);

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

  // Fetch events
  useEffect(() => {
    async function fetchEvents() {
      try {
        setEventsLoading(true);
        setEventsError(null);
        const response = await fetch(
          `${API_BASE_URL}/dashboard/events?page=${eventsPage}&pageSize=${eventsPageSize}`
        );
        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}));
          const errorMessage = errorData.detail || errorData.error?.message || `HTTP ${response.status}`;
          throw new Error(errorMessage);
        }
        const result = await response.json();
        setEventsData(result.data);
        setEventsTotal(result.total);

        // Warn if no data found
        if (result.data.length === 0 || result.total === 0) {
          setEventsError('No events in database. To populate data: 1) Run GET /sourceData to collect foundation data, 2) POST /setEventsTable to consolidate events, 3) POST /backfillEventsTable to calculate metrics.');
        }
      } catch (error) {
        console.error('Failed to fetch events:', error);
        setEventsError(error.message || 'Failed to connect to backend. Please ensure the backend server is running on port 8000.');
      } finally {
        setEventsLoading(false);
      }
    }

    fetchEvents();
  }, [eventsPage, eventsPageSize]);


  return (
    <>
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

      {/* Events Section */}
      <section style={{ marginBottom: 'var(--space-5)' }}>
        {eventsError ? (
          <div className="alert alert-error">
            Error loading events: {eventsError}
          </div>
        ) : (
          <EventsTable
            data={eventsData}
            loading={eventsLoading}
            total={eventsTotal}
            page={eventsPage}
            pageSize={eventsPageSize}
            onPageChange={setEventsPage}
            onPageSizeChange={(newSize) => {
              setEventsPageSize(newSize);
              setEventsPage(1); // Reset to first page
            }}
          />
        )}
      </section>
    </>
  );
}
