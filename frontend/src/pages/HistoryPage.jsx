/**
 * HistoryPage Component
 *
 * History-only page with cached, front-end computed performance metrics.
 */

import React, { useEffect, useState } from 'react';
import HistoryTable from '../components/dashboard/HistoryTable';
import {
  getHistoryState,
  setHistoryState,
  getHistorySettings,
} from '../services/localStorage';
import {
  loadHistoryDataset,
  requestHistoryCacheRefresh,
  subscribeHistoryCacheRefresh,
  getCachedHistorySettings,
} from '../services/historyData';

export default function HistoryPage() {
  const [historyData, setHistoryData] = useState([]);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [historyPage, setHistoryPage] = useState(1);
  const [historyPageSize, setHistoryPageSize] = useState(100);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyError, setHistoryError] = useState(null);
  const [historySortConfig, setHistorySortConfig] = useState(() => getHistoryState().sort);
  const [historyFilters, setHistoryFilters] = useState(() => getHistoryState().filters);
  const [lastSettings, setLastSettings] = useState(() => getHistorySettings());
  const [refreshCounter, setRefreshCounter] = useState(0);

  useEffect(() => {
    setHistoryState({ sort: historySortConfig });
  }, [historySortConfig]);

  useEffect(() => {
    setHistoryState({ filters: historyFilters });
  }, [historyFilters]);

  useEffect(() => {
    const unsubscribe = subscribeHistoryCacheRefresh(() => {
      setHistoryPage(1);
      setRefreshCounter((prev) => prev + 1);
    });
    return () => unsubscribe();
  }, []);

  useEffect(() => {
    const handleStorage = (event) => {
      if (event.key === 'ui.history_cache_token') {
        setHistoryPage(1);
        setRefreshCounter((prev) => prev + 1);
      }
    };
    window.addEventListener('storage', handleStorage);
    return () => window.removeEventListener('storage', handleStorage);
  }, []);

  useEffect(() => {
    let mounted = true;
    async function fetchHistory() {
      try {
        setHistoryLoading(true);
        setHistoryError(null);
        const payload = await loadHistoryDataset();
        if (!mounted) return;
        setHistoryData(payload.rows || []);
        setHistoryTotal(payload.total || 0);
        setLastSettings(payload.settings || getCachedHistorySettings() || getHistorySettings());
      } catch (error) {
        if (!mounted) return;
        console.error('Failed to fetch history data:', error);
        setHistoryError(error.message || 'Failed to load history data.');
      } finally {
        if (mounted) {
          setHistoryLoading(false);
        }
      }
    }

    fetchHistory();
    return () => {
      mounted = false;
    };
  }, [refreshCounter]);

  const handleRefresh = async () => {
    requestHistoryCacheRefresh();
    try {
      setHistoryLoading(true);
      setHistoryError(null);
      const payload = await loadHistoryDataset();
      setHistoryData(payload.rows || []);
      setHistoryTotal(payload.total || 0);
      setLastSettings(payload.settings || getHistorySettings());
      setHistoryPage(1);
    } catch (error) {
      console.error('Failed to refresh history data:', error);
      setHistoryError(error.message || 'Failed to refresh history data.');
    } finally {
      setHistoryLoading(false);
    }
  };

  const baseFieldLabel = lastSettings?.baseField ? lastSettings.baseField.toUpperCase() : '-';
  const settingsLabel = lastSettings
    ? `Base D${lastSettings.baseOffset} • ${baseFieldLabel} • MIN ${lastSettings.minThreshold || '-'}% • MAX ${lastSettings.maxThreshold || '-'}%`
    : '';

  return (
    <>
      <header style={{ marginBottom: 'var(--space-4)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 style={{ marginBottom: 'var(--space-1)' }}>History</h1>
          <p style={{ color: 'var(--text-dim)', fontSize: 'var(--text-sm)', margin: 0 }}>
            Cached calculations • {settingsLabel}
          </p>
        </div>
        <button
          type="button"
          className="btn btn-sm btn-primary"
          onClick={handleRefresh}
          disabled={historyLoading}
        >
          Update
        </button>
      </header>

      {historyError ? (
        <div className="alert alert-error">Error loading history: {historyError}</div>
      ) : (
        <HistoryTable
          data={historyData}
          loading={historyLoading}
          total={historyTotal}
          page={historyPage}
          pageSize={historyPageSize}
          onPageChange={setHistoryPage}
          onPageSizeChange={(newSize) => {
            setHistoryPageSize(newSize);
            setHistoryPage(1);
          }}
          sortConfig={historySortConfig}
          onSortChange={(newSortConfig) => {
            setHistorySortConfig(newSortConfig);
            setHistoryPage(1);
          }}
          filters={historyFilters}
          onFiltersChange={(newFilters) => {
            setHistoryFilters(newFilters);
            setHistoryPage(1);
          }}
          dayOffsetMode="performance"
          minThreshold={lastSettings?.minThreshold}
          maxThreshold={lastSettings?.maxThreshold}
          baseOffset={lastSettings?.baseOffset}
          baseField={lastSettings?.baseField}
        />
      )}
    </>
  );
}
