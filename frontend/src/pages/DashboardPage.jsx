/**
 * DashboardPage Component
 *
 * Main dashboard page displaying KPI cards and events.
 * Based on alsign/prompt/2_designSystem.ini route contract for dashboard route.
 */

import React, { useState, useEffect } from 'react';
import KPICard from '../components/dashboard/KPICard';
import EventsTable from '../components/dashboard/EventsTable';
import TradesTable from '../components/dashboard/TradesTable';

// API base URL
const API_BASE_URL = '/api';

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
  const [eventsSortConfig, setEventsSortConfig] = useState({ key: null, direction: null });
  const [eventsFilters, setEventsFilters] = useState({});
  const [eventsRefreshTrigger, setEventsRefreshTrigger] = useState(0);

  // Trades state
  const [tradesData, setTradesData] = useState([]);
  const [tradesTotal, setTradesTotal] = useState(0);
  const [tradesPage, setTradesPage] = useState(1);
  const [tradesPageSize, setTradesPageSize] = useState(50);
  const [tradesLoading, setTradesLoading] = useState(true);
  const [tradesError, setTradesError] = useState(null);
  const [tradesSortConfig, setTradesSortConfig] = useState({ key: null, direction: null });
  const [tradesFilters, setTradesFilters] = useState({});
  const [tradesRefreshTrigger, setTradesRefreshTrigger] = useState(0);

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

        // Build query parameters
        const params = new URLSearchParams({
          page: eventsPage.toString(),
          pageSize: eventsPageSize.toString(),
        });

        // Add sort parameters if sorting is active
        if (eventsSortConfig.key && eventsSortConfig.direction) {
          params.append('sortBy', eventsSortConfig.key);
          params.append('sortOrder', eventsSortConfig.direction);
        }

        // Map column filters to backend API parameters
        if (eventsFilters.ticker) {
          params.append('ticker', eventsFilters.ticker);
        }
        if (eventsFilters.sector) {
          params.append('sector', eventsFilters.sector);
        }
        if (eventsFilters.industry) {
          params.append('industry', eventsFilters.industry);
        }
        if (eventsFilters.source) {
          params.append('source', eventsFilters.source);
        }
        if (eventsFilters.condition) {
          params.append('condition', eventsFilters.condition);
        }
        if (eventsFilters.position_quantitative) {
          params.append('position_quantitative', eventsFilters.position_quantitative);
        }
        if (eventsFilters.position_qualitative) {
          params.append('position_qualitative', eventsFilters.position_qualitative);
        }

        // Parse disparity_quantitative number filter (e.g., "0.1-0.5", ">0.2", "<0.8")
        if (eventsFilters.disparity_quantitative) {
          const val = eventsFilters.disparity_quantitative.trim();
          if (val.includes('-')) {
            const [min, max] = val.split('-').map(v => v.trim());
            if (min) params.append('disparity_quantitative_min', min);
            if (max) params.append('disparity_quantitative_max', max);
          } else if (val.startsWith('>')) {
            params.append('disparity_quantitative_min', val.substring(1));
          } else if (val.startsWith('<')) {
            params.append('disparity_quantitative_max', val.substring(1));
          } else {
            // Exact value - use min=max
            params.append('disparity_quantitative_min', val);
            params.append('disparity_quantitative_max', val);
          }
        }

        // Parse disparity_qualitative number filter
        if (eventsFilters.disparity_qualitative) {
          const val = eventsFilters.disparity_qualitative.trim();
          if (val.includes('-')) {
            const [min, max] = val.split('-').map(v => v.trim());
            if (min) params.append('disparity_qualitative_min', min);
            if (max) params.append('disparity_qualitative_max', max);
          } else if (val.startsWith('>')) {
            params.append('disparity_qualitative_min', val.substring(1));
          } else if (val.startsWith('<')) {
            params.append('disparity_qualitative_max', val.substring(1));
          } else {
            params.append('disparity_qualitative_min', val);
            params.append('disparity_qualitative_max', val);
          }
        }

        // Handle event_date daterange filter
        if (eventsFilters.event_date) {
          if (typeof eventsFilters.event_date === 'object') {
            if (eventsFilters.event_date.from) {
              params.append('eventDateFrom', eventsFilters.event_date.from);
            }
            if (eventsFilters.event_date.to) {
              params.append('eventDateTo', eventsFilters.event_date.to);
            }
          }
        }

        const response = await fetch(
          `${API_BASE_URL}/dashboard/events?${params.toString()}`
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
  }, [eventsPage, eventsPageSize, eventsSortConfig, eventsFilters, eventsRefreshTrigger]);

  // Fetch trades
  useEffect(() => {
    async function fetchTrades() {
      try {
        setTradesLoading(true);
        setTradesError(null);

        // Build query parameters
        const params = new URLSearchParams({
          page: tradesPage.toString(),
          pageSize: tradesPageSize.toString(),
        });

        // Add sort parameters if sorting is active
        if (tradesSortConfig.key && tradesSortConfig.direction) {
          params.append('sortBy', tradesSortConfig.key);
          params.append('sortOrder', tradesSortConfig.direction);
        }

        // Add filter parameters
        if (tradesFilters.ticker) {
          params.append('ticker', tradesFilters.ticker);
        }
        if (tradesFilters.model) {
          params.append('model', tradesFilters.model);
        }
        if (tradesFilters.source) {
          params.append('source', tradesFilters.source);
        }
        if (tradesFilters.position) {
          params.append('position', tradesFilters.position);
        }
        if (tradesFilters.tradeDateFrom) {
          params.append('tradeDateFrom', tradesFilters.tradeDateFrom);
        }
        if (tradesFilters.tradeDateTo) {
          params.append('tradeDateTo', tradesFilters.tradeDateTo);
        }

        const response = await fetch(
          `${API_BASE_URL}/dashboard/trades?${params.toString()}`
        );
        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}));
          const errorMessage = errorData.detail || errorData.error?.message || `HTTP ${response.status}`;
          throw new Error(errorMessage);
        }
        const result = await response.json();
        setTradesData(result.data);
        setTradesTotal(result.total);

        // Warn if no data found
        if (result.data.length === 0 || result.total === 0) {
          setTradesError('No trades in database. To populate data: use POST /trades to insert trade records.');
        }
      } catch (error) {
        console.error('Failed to fetch trades:', error);
        setTradesError(error.message || 'Failed to connect to backend. Please ensure the backend server is running on port 8000.');
      } finally {
        setTradesLoading(false);
      }
    }

    fetchTrades();
  }, [tradesPage, tradesPageSize, tradesSortConfig, tradesFilters, tradesRefreshTrigger]);


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
            sortConfig={eventsSortConfig}
            onSortChange={(newSortConfig) => {
              setEventsSortConfig(newSortConfig);
              setEventsPage(1); // Reset to first page when sorting changes
            }}
            filters={eventsFilters}
            onFiltersChange={(newFilters) => {
              setEventsFilters(newFilters);
              setEventsPage(1); // Reset to first page when filters change
            }}
            onRefresh={() => setEventsRefreshTrigger(prev => prev + 1)}
          />
        )}
      </section>

      {/* Trades Section */}
      <section style={{ marginBottom: 'var(--space-5)' }}>
        {tradesError ? (
          <div className="alert alert-error">
            Error loading trades: {tradesError}
          </div>
        ) : (
          <TradesTable
            data={tradesData}
            loading={tradesLoading}
            total={tradesTotal}
            page={tradesPage}
            pageSize={tradesPageSize}
            onPageChange={setTradesPage}
            onPageSizeChange={(newSize) => {
              setTradesPageSize(newSize);
              setTradesPage(1); // Reset to first page
            }}
            sortConfig={tradesSortConfig}
            onSortChange={(newSortConfig) => {
              setTradesSortConfig(newSortConfig);
              setTradesPage(1); // Reset to first page when sorting changes
            }}
            filters={tradesFilters}
            onFiltersChange={(newFilters) => {
              setTradesFilters(newFilters);
              setTradesPage(1); // Reset to first page when filters change
            }}
            onRefresh={() => setTradesRefreshTrigger(prev => prev + 1)}
          />
        )}
      </section>
    </>
  );
}