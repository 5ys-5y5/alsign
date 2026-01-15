/**
 * TradesPage Component
 *
 * Trades-only page with subscription-based visibility.
 */

import React, { useEffect, useState } from 'react';
import TradesTable from '../components/dashboard/TradesTable';
import { API_BASE_URL, getAuthHeaders } from '../services/api';
import { getTradesState, setTradesState } from '../services/localStorage';
import { useAuth } from '../contexts/AuthContext';

export default function TradesPage() {
  const { loading: authLoading, isPaying } = useAuth();
  const todayString = new Date().toLocaleDateString('en-CA');

  const [tradesData, setTradesData] = useState([]);
  const [tradesTotal, setTradesTotal] = useState(0);
  const [tradesPage, setTradesPage] = useState(1);
  const [tradesPageSize, setTradesPageSize] = useState(50);
  const [tradesLoading, setTradesLoading] = useState(true);
  const [tradesError, setTradesError] = useState(null);
  const [tradesSortConfig, setTradesSortConfig] = useState({ key: 'trade_date', direction: 'desc' });
  const [tradesFilters, setTradesFilters] = useState({});
  const [tradesDayOffsetMode, setTradesDayOffsetMode] = useState(() => {
    const persisted = getTradesState();
    return persisted.dayOffsetMode || 'performance';
  });

  useEffect(() => {
    setTradesState({ dayOffsetMode: tradesDayOffsetMode });
  }, [tradesDayOffsetMode]);

  useEffect(() => {
    async function fetchTrades() {
      try {
        setTradesLoading(true);
        setTradesError(null);

        const params = new URLSearchParams({
          page: tradesPage.toString(),
          pageSize: tradesPageSize.toString(),
        });

        if (tradesSortConfig.key && tradesSortConfig.direction) {
          params.append('sortBy', tradesSortConfig.key);
          params.append('sortOrder', tradesSortConfig.direction);
        }
        params.append('dayOffsetMode', tradesDayOffsetMode);

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
        if (tradesFilters.trade_date) {
          if (typeof tradesFilters.trade_date === 'object') {
            if (tradesFilters.trade_date.from) {
              params.append('tradeDateFrom', tradesFilters.trade_date.from);
            }
            if (tradesFilters.trade_date.to) {
              const toDate = tradesFilters.trade_date.to;
              params.append('tradeDateTo', toDate > todayString ? todayString : toDate);
            }
          }
        }

        if (!params.has('tradeDateTo')) {
          params.append('tradeDateTo', todayString);
        }

        const response = await fetch(
          `${API_BASE_URL}/dashboard/trades?${params.toString()}`,
          { headers: await getAuthHeaders() }
        );
        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}));
          const errorMessage = errorData.detail || errorData.error?.message || `HTTP ${response.status}`;
          throw new Error(errorMessage);
        }
        const result = await response.json();
        setTradesData(result.data);
        setTradesTotal(result.total);

        if (result.data.length === 0 || result.total === 0) {
          setTradesError(null);
        }
      } catch (error) {
        console.error('Failed to fetch trades:', error);
        setTradesError(error.message || 'Failed to connect to backend. Please ensure the backend server is running on port 8000.');
      } finally {
        setTradesLoading(false);
      }
    }

    fetchTrades();
  }, [tradesPage, tradesPageSize, tradesSortConfig, tradesFilters, tradesDayOffsetMode]);

  return (
    <>
      <header style={{ marginBottom: 'var(--space-4)' }} />

      {!authLoading && !isPaying && (
        <div className="alert alert-warning">
          Subscription inactive: recent trades (last 30 days) are blurred. Subscribe to unlock full visibility.
        </div>
      )}
      {tradesError ? (
        <div className="alert alert-error">
          Error loading trades: {tradesError}
        </div>
      ) : !tradesLoading && tradesTotal === 0 ? (
        <div className="alert alert-warning">
          오늘 날짜의 거래가 없습니다.
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
            setTradesPage(1);
          }}
          sortConfig={tradesSortConfig}
          onSortChange={(newSortConfig) => {
            setTradesSortConfig(newSortConfig);
            setTradesPage(1);
          }}
          filters={tradesFilters}
          onFiltersChange={(newFilters) => {
            const nextFilters = { ...newFilters };
            if (nextFilters.trade_date?.to && nextFilters.trade_date.to > todayString) {
              nextFilters.trade_date = {
                ...nextFilters.trade_date,
                to: todayString,
              };
            }
            setTradesFilters(nextFilters);
            setTradesPage(1);
          }}
          dayOffsetMode={tradesDayOffsetMode}
          onDayOffsetModeChange={setTradesDayOffsetMode}
        />
      )}
    </>
  );
}
