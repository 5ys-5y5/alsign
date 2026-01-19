/**
 * EventsHistoryPage Component
 *
 * Events-only page with cached, front-end computed performance metrics.
 */

import React, { useEffect, useRef, useState } from 'react';
import KPICard from '../components/dashboard/KPICard';
import EventsHistoryTable from '../components/dashboard/EventsHistoryTable';
import {
  getEventsHistoryState,
  setEventsHistoryState,
  getEventsSettings,
} from '../services/localStorage';
import {
  loadEventsHistoryDataset,
  requestEventsHistoryCacheRefresh,
  subscribeEventsHistoryCacheRefresh,
  getCachedEventsHistorySettings,
  subscribeEventsHistoryProgress,
} from '../services/eventsHistoryData';
import EventsSettingsPanel from '../components/dashboard/EventsSettingsPanel';
import { API_BASE_URL, getAuthHeaders } from '../services/api';

function formatDate(dateString) {
  if (!dateString) return 'N/A';
  try {
    const date = new Date(dateString);
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
  } catch (e) {
    return dateString;
  }
}

function getPositionMultiplier(position) {
  if (!position) return 1;
  const normalized = String(position).toLowerCase();
  return normalized === 'short' ? -1 : 1;
}

export default function EventsHistoryPage() {
  const [eventsData, setEventsData] = useState([]);
  const [eventsTotal, setEventsTotal] = useState(0);
  const [eventsPage, setEventsPage] = useState(1);
  const [eventsPageSize, setEventsPageSize] = useState(100);
  const [eventsLoading, setEventsLoading] = useState(false);
  const [eventsError, setEventsError] = useState(null);
  const [eventsSortConfig, setEventsSortConfig] = useState(() => getEventsHistoryState().sort);
  const [eventsFilters, setEventsFilters] = useState(() => getEventsHistoryState().filters);
  const [lastSettings, setLastSettings] = useState(() => getEventsSettings());
  const [kpis, setKpis] = useState({
    coverage: 0,
    targetsFreshness: null,
    quantitativesFreshness: null,
    eventsFreshness: null,
  });
  const [kpisLoading, setKpisLoading] = useState(true);
  const [kpisError, setKpisError] = useState(null);
  const [refreshCounter, setRefreshCounter] = useState(0);
  const [progress, setProgress] = useState(null);
  const [progressLogs, setProgressLogs] = useState([]);
  const [showProgressLogs, setShowProgressLogs] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [filterDraft, setFilterDraft] = useState({
    eventDateFrom: '',
    eventDateTo: '',
    sector: '',
    industry: '',
    source: '',
    positionQuantitative: 'all',
    positionQualitative: 'all',
    sectorAll: true,
    industryAll: true,
    sourceAll: true,
  });
  const [appliedFilters, setAppliedFilters] = useState(null);
  const computeStartRef = useRef(null);
  const partialRowsRef = useRef(null);
  const loadStartRef = useRef(null);
  const logIdRef = useRef(1);

  useEffect(() => {
    setEventsHistoryState({ sort: eventsSortConfig });
  }, [eventsSortConfig]);

  useEffect(() => {
    setEventsHistoryState({ filters: eventsFilters });
  }, [eventsFilters]);

  useEffect(() => {
    let mounted = true;
    async function fetchKPIs() {
      try {
        setKpisLoading(true);
        setKpisError(null);
        const response = await fetch(`${API_BASE_URL}/dashboard/events/kpis`, {
          headers: await getAuthHeaders(),
        });
        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}));
          const errorMessage = errorData.detail || errorData.error?.message || `HTTP ${response.status}`;
          throw new Error(errorMessage);
        }
        const data = await response.json();
        if (mounted) {
          setKpis(data);
        }
      } catch (error) {
        console.error('Failed to fetch events KPIs:', error);
        if (mounted) {
          setKpisError(error.message || 'Failed to connect to backend. Please ensure the backend server is running on port 8000.');
        }
      } finally {
        if (mounted) {
          setKpisLoading(false);
        }
      }
    }

    fetchKPIs();
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    const unsubscribe = subscribeEventsHistoryCacheRefresh(() => {
      setEventsPage(1);
      setRefreshCounter((prev) => prev + 1);
    });
    return () => unsubscribe();
  }, []);

  useEffect(() => {
    const unsubscribe = subscribeEventsHistoryProgress((payload) => {
      const logId = logIdRef.current;
      logIdRef.current += 1;
      const logEntry = {
        id: logId,
        time: new Date().toISOString(),
        stage: payload?.stage || 'unknown',
        payload,
      };
      setProgressLogs((prev) => {
        const next = [...prev, logEntry];
        if (next.length > 200) {
          return next.slice(next.length - 200);
        }
        return next;
      });

      if (payload.stage === 'compute' && !computeStartRef.current) {
        computeStartRef.current = Date.now();
      }
      if (payload.stage !== 'compute') {
        computeStartRef.current = null;
      }
      if (!loadStartRef.current) {
        loadStartRef.current = Date.now();
      }
      if (payload.stage === 'compute' && Array.isArray(payload.rows)) {
        partialRowsRef.current = payload.rows;
        if (Number.isFinite(payload.processed)) {
          const slice = payload.rows.slice(0, payload.processed).filter(Boolean);
          setEventsData(slice);
          setEventsTotal(payload.total || slice.length);
        }
      }
      setProgress(payload);
    });
    return () => unsubscribe();
  }, []);

  useEffect(() => {
    if (!eventsLoading) {
      setElapsedSeconds(0);
      loadStartRef.current = null;
      return undefined;
    }
    if (!loadStartRef.current) {
      loadStartRef.current = Date.now();
    }
    const timer = setInterval(() => {
      if (!loadStartRef.current) return;
      const elapsed = Math.floor((Date.now() - loadStartRef.current) / 1000);
      setElapsedSeconds(elapsed);
    }, 1000);
    return () => clearInterval(timer);
  }, [eventsLoading]);

  useEffect(() => {
    const handleStorage = (event) => {
      if (event.key === 'ui.events_history_cache_token') {
        setEventsPage(1);
        setRefreshCounter((prev) => prev + 1);
      }
    };
    window.addEventListener('storage', handleStorage);
    return () => window.removeEventListener('storage', handleStorage);
  }, []);

  const buildAppliedFilters = (draft) => {
    const filters = {
      eventDateFrom: draft.eventDateFrom || '',
      eventDateTo: draft.eventDateTo || '',
      sector: draft.sectorAll ? '' : (draft.sector || ''),
      industry: draft.industryAll ? '' : (draft.industry || ''),
      source: draft.sourceAll ? '' : (draft.source || ''),
      positionQuantitative: draft.positionQuantitative === 'all' ? '' : draft.positionQuantitative,
      positionQualitative: draft.positionQualitative === 'all' ? '' : draft.positionQualitative,
    };
    return filters;
  };

  const hasActiveFilters = (filters) => {
    return Boolean(
      filters.eventDateFrom
      || filters.eventDateTo
      || filters.sector
      || filters.industry
      || filters.source
      || filters.positionQuantitative
      || filters.positionQualitative
    );
  };

  useEffect(() => {
    let mounted = true;
    async function fetchEventsHistory() {
      if (!appliedFilters || !hasActiveFilters(appliedFilters)) {
        setEventsData([]);
        setEventsTotal(0);
        setEventsLoading(false);
        setProgress(null);
        return;
      }
      try {
        setEventsLoading(true);
        setEventsError(null);
        const payload = await loadEventsHistoryDataset(appliedFilters);
        if (!mounted) return;
        setEventsData(payload.rows || []);
        setEventsTotal(payload.total || 0);
        setLastSettings(payload.settings || getCachedEventsHistorySettings() || getEventsSettings());
      } catch (error) {
        if (!mounted) return;
        console.error('Failed to fetch events history data:', error);
        setEventsError(error.message || 'Failed to load events history data.');
      } finally {
        if (mounted) {
          setEventsLoading(false);
        }
      }
    }

    fetchEventsHistory();
    return () => {
      mounted = false;
    };
  }, [refreshCounter, appliedFilters]);

  const handleRefresh = async () => {
    if (!appliedFilters || !hasActiveFilters(appliedFilters)) {
      setEventsData([]);
      setEventsTotal(0);
      setEventsLoading(false);
      return;
    }
    requestEventsHistoryCacheRefresh();
    try {
      setEventsLoading(true);
      setEventsError(null);
      const payload = await loadEventsHistoryDataset(appliedFilters);
      setEventsData(payload.rows || []);
      setEventsTotal(payload.total || 0);
      setLastSettings(payload.settings || getEventsSettings());
      setEventsPage(1);
    } catch (error) {
      console.error('Failed to refresh events history data:', error);
      setEventsError(error.message || 'Failed to refresh events history data.');
    } finally {
      setEventsLoading(false);
    }
  };

  const handleApplyFilters = () => {
    const nextFilters = buildAppliedFilters(filterDraft);
    setAppliedFilters(nextFilters);
    setEventsPage(1);
    setRefreshCounter((prev) => prev + 1);
    setProgress(null);
  };

  const handleResetFilters = () => {
    const reset = {
      eventDateFrom: '',
      eventDateTo: '',
      sector: '',
      industry: '',
      source: '',
      positionQuantitative: 'all',
      positionQualitative: 'all',
      sectorAll: true,
      industryAll: true,
      sourceAll: true,
    };
    setFilterDraft(reset);
    setAppliedFilters(null);
    setEventsData([]);
    setEventsTotal(0);
    setEventsError(null);
    setEventsLoading(false);
    setProgress(null);
  };

  const baseFieldLabel = lastSettings?.baseField ? lastSettings.baseField.toUpperCase() : '-';
  const settingsLabel = lastSettings
    ? `Base D${lastSettings.baseOffset} - ${baseFieldLabel} - MIN ${lastSettings.minThreshold || '-'}% - MAX ${lastSettings.maxThreshold || '-'}%`
    : '';

  const progressLabel = (() => {
    if (!progress) return null;
    const percent = Number.isFinite(progress.percent) ? progress.percent.toFixed(1) : null;
    if (progress.stage === 'start') {
      const mins = Math.floor(elapsedSeconds / 60);
      const secs = elapsedSeconds % 60;
      return `Waiting for server response (${mins}m ${secs}s elapsed)`;
    }
    if (progress.stage === 'events') {
      const totalLabel = progress.totalKnown ? `/${progress.total || 0}` : '';
      return `Loading events (filtered): ${progress.loaded || 0}${totalLabel}${percent ? ` (${percent}%)` : ''}`;
    }
    if (progress.stage === 'historical') {
      return `Loading prices: ${progress.batch || 0}/${progress.batches || 0}${percent ? ` (${percent}%)` : ''}`;
    }
    if (progress.stage === 'compute') {
      let eta = '';
      if (computeStartRef.current && progress.processed && progress.total) {
        const elapsed = (Date.now() - computeStartRef.current) / 1000;
        const rate = elapsed / progress.processed;
        const remaining = Math.max(0, rate * (progress.total - progress.processed));
        if (Number.isFinite(remaining)) {
          const mins = Math.floor(remaining / 60);
          const secs = Math.floor(remaining % 60);
          eta = ` - ETA ${mins}m ${secs}s`;
        }
      }
      const totalLabel = progress.totalKnown ? `/${progress.total || 0}` : '';
      const etaLabel = progress.totalKnown ? eta : ' - scanning filters';
      return `Computing (filtered): ${progress.processed || 0}${totalLabel}${percent ? ` (${percent}%)` : ''}${etaLabel}`;
    }
    if (progress.stage === 'complete') {
      const totalLabel = Number.isFinite(progress.total) ? ` (${progress.total} rows)` : '';
      return `Complete${totalLabel}`;
    }
    return null;
  })();

  const progressPercent = (() => {
    if (!progress || !Number.isFinite(progress.percent)) {
      return 0;
    }
    return Math.min(100, Math.max(0, progress.percent));
  })();

  const progressStageLabel = (() => {
    if (!progress) return null;
    if (progress.stage === 'start') return 'Waiting';
    if (progress.stage === 'events') return 'Loading events';
    if (progress.stage === 'historical') return 'Loading prices';
    if (progress.stage === 'compute') return 'Computing';
    if (progress.stage === 'complete') return 'Complete';
    return 'Working';
  })();

  const progressVisible = Boolean(progressLabel) || eventsLoading;
  const displayStageLabel = progressStageLabel || 'Loading';
  const displayPercent = progress?.stage === 'complete'
    ? 100
    : (progressLabel && progress?.totalKnown ? progressPercent : 0);
  const displayPercentLabel = progress?.stage === 'complete'
    ? '100.0%'
    : (progress?.totalKnown ? `${displayPercent.toFixed(1)}%` : '...');
  const displayLabel = progressLabel
    || `Waiting for server response (${Math.floor(elapsedSeconds / 60)}m ${elapsedSeconds % 60}s elapsed)`;

  const tableLoading = eventsLoading && eventsData.length === 0;
  const activeFilters = appliedFilters ? hasActiveFilters(appliedFilters) : false;

  const bestWindow = React.useMemo(() => {
    if (!eventsData || eventsData.length === 0) {
      return null;
    }
    const candidates = [];
    for (let offset = -14; offset <= 14; offset += 1) {
      if (offset === 0) continue;
      const key = offset < 0 ? `d_neg${Math.abs(offset)}` : `d_pos${offset}`;
      let sum = 0;
      let count = 0;
      for (const row of eventsData) {
        const raw = Number(row[key]);
        if (!Number.isFinite(raw)) {
          continue;
        }
        const position = row.position || row.position_quantitative || row.position_qualitative;
        const multiplier = getPositionMultiplier(position);
        sum += raw * multiplier;
        count += 1;
      }
      if (count > 0) {
        candidates.push({ offset, avg: sum / count, count });
      }
    }
    if (candidates.length === 0) {
      return null;
    }
    return candidates.reduce((best, current) => (current.avg > best.avg ? current : best));
  }, [eventsData]);

  const baseOffset = lastSettings?.baseOffset ?? 0;
  const buyLabel = baseOffset === 0 ? 'D0' : `D${baseOffset > 0 ? `+${baseOffset}` : baseOffset}`;
  const sellLabel = bestWindow
    ? `D${bestWindow.offset > 0 ? `+${bestWindow.offset}` : bestWindow.offset}`
    : '-';
  const bestReturnLabel = bestWindow
    ? `${(bestWindow.avg * 100).toFixed(2)}%`
    : 'N/A';

  const formatLogMessage = (entry) => {
    const stage = entry.stage || 'unknown';
    const payload = entry.payload || {};
    if (stage === 'start') {
      return 'Request started';
    }
    if (stage === 'events') {
      const loaded = payload.loaded ?? 0;
      const total = payload.totalKnown ? `/${payload.total || 0}` : '';
      return `Loaded events ${loaded}${total}`;
    }
    if (stage === 'historical') {
      const batch = payload.batch ?? 0;
      const batches = payload.batches ?? 0;
      return `Historical prices batch ${batch}/${batches}`;
    }
    if (stage === 'compute') {
      const processed = payload.processed ?? 0;
      const total = payload.totalKnown ? `/${payload.total || 0}` : '';
      return `Computing rows ${processed}${total}`;
    }
    if (stage === 'complete') {
      const total = payload.total ?? 0;
      return `Complete (${total} rows)`;
    }
    return 'Working';
  };

  return (
    <>
      <header style={{ marginBottom: 'var(--space-4)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 style={{ marginBottom: 'var(--space-1)' }}>Events</h1>
          <p style={{ color: 'var(--text-dim)', fontSize: 'var(--text-sm)', margin: 0 }}>
            Cached calculations - {settingsLabel}
          </p>
        </div>
      </header>

      <section style={{ marginBottom: 'var(--space-4)' }}>
        <h2 style={{ marginBottom: 'var(--space-2)' }}>Dashboard</h2>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
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
                title="Targets Freshness"
                value={formatDate(kpis.targetsFreshness)}
                subtitle="config_lv3_targets updated_at"
              />
              <KPICard
                title="Quantitatives Freshness"
                value={formatDate(kpis.quantitativesFreshness)}
                subtitle="config_lv3_quantitatives updated_at"
              />
              <KPICard
                title="Events Freshness"
                value={formatDate(kpis.eventsFreshness)}
                subtitle="txn_events updated_at"
              />
              <KPICard
                title="Best Window"
                value={bestReturnLabel}
                subtitle={`Buy ${buyLabel} / Sell ${sellLabel}`}
              />
            </>
          )}
        </div>
      </section>

      <section
        className="table-toolbar"
        style={{
          marginBottom: 'var(--space-4)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--rounded-lg)',
          flexWrap: 'wrap',
          gap: 'var(--space-2)',
        }}
      >
        <div style={{ flexBasis: '100%' }}>
          <EventsSettingsPanel />
        </div>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
            gap: 'var(--space-2)',
            alignItems: 'end',
            width: '100%',
          }}
        >
          <div>
            <label style={{ display: 'block', fontSize: 'var(--text-xs)', fontWeight: 600, marginBottom: '4px' }}>
              Event date from
            </label>
            <input
              type="date"
              value={filterDraft.eventDateFrom}
              onChange={(e) => setFilterDraft((prev) => ({ ...prev, eventDateFrom: e.target.value }))}
            />
          </div>
          <div>
            <label style={{ display: 'block', fontSize: 'var(--text-xs)', fontWeight: 600, marginBottom: '4px' }}>
              Event date to
            </label>
            <input
              type="date"
              value={filterDraft.eventDateTo}
              onChange={(e) => setFilterDraft((prev) => ({ ...prev, eventDateTo: e.target.value }))}
            />
          </div>
          <div>
            <label style={{ display: 'block', fontSize: 'var(--text-xs)', fontWeight: 600, marginBottom: '4px' }}>
              Sector
            </label>
            <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
              <input
                type="text"
                placeholder="e.g. Technology"
                value={filterDraft.sector}
                onChange={(e) => setFilterDraft((prev) => ({ ...prev, sector: e.target.value, sectorAll: false }))}
                disabled={filterDraft.sectorAll}
              />
              <label style={{ fontSize: 'var(--text-xs)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                <input
                  type="checkbox"
                  checked={filterDraft.sectorAll}
                  onChange={(e) => setFilterDraft((prev) => ({ ...prev, sectorAll: e.target.checked }))}
                />
                All
              </label>
            </div>
          </div>
          <div>
            <label style={{ display: 'block', fontSize: 'var(--text-xs)', fontWeight: 600, marginBottom: '4px' }}>
              Industry
            </label>
            <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
              <input
                type="text"
                placeholder="e.g. Semiconductors"
                value={filterDraft.industry}
                onChange={(e) => setFilterDraft((prev) => ({ ...prev, industry: e.target.value, industryAll: false }))}
                disabled={filterDraft.industryAll}
              />
              <label style={{ fontSize: 'var(--text-xs)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                <input
                  type="checkbox"
                  checked={filterDraft.industryAll}
                  onChange={(e) => setFilterDraft((prev) => ({ ...prev, industryAll: e.target.checked }))}
                />
                All
              </label>
            </div>
          </div>
          <div>
            <label style={{ display: 'block', fontSize: 'var(--text-xs)', fontWeight: 600, marginBottom: '4px' }}>
              Source
            </label>
            <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
              <input
                type="text"
                placeholder="e.g. Bloomberg"
                value={filterDraft.source}
                onChange={(e) => setFilterDraft((prev) => ({ ...prev, source: e.target.value, sourceAll: false }))}
                disabled={filterDraft.sourceAll}
              />
              <label style={{ fontSize: 'var(--text-xs)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                <input
                  type="checkbox"
                  checked={filterDraft.sourceAll}
                  onChange={(e) => setFilterDraft((prev) => ({ ...prev, sourceAll: e.target.checked }))}
                />
                All
              </label>
            </div>
          </div>
          <div>
            <label style={{ display: 'block', fontSize: 'var(--text-xs)', fontWeight: 600, marginBottom: '4px' }}>
              Position (Quantitative)
            </label>
            <select
              value={filterDraft.positionQuantitative}
              onChange={(e) => setFilterDraft((prev) => ({ ...prev, positionQuantitative: e.target.value }))}
            >
              <option value="all">All</option>
              <option value="long">long</option>
              <option value="short">short</option>
              <option value="undefined">undefined</option>
            </select>
          </div>
          <div>
            <label style={{ display: 'block', fontSize: 'var(--text-xs)', fontWeight: 600, marginBottom: '4px' }}>
              Position (Qualitative)
            </label>
            <select
              value={filterDraft.positionQualitative}
              onChange={(e) => setFilterDraft((prev) => ({ ...prev, positionQualitative: e.target.value }))}
            >
              <option value="all">All</option>
              <option value="long">long</option>
              <option value="short">short</option>
              <option value="undefined">undefined</option>
            </select>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', justifyContent: 'flex-end' }}>
            <button type="button" className="btn btn-sm btn-primary" onClick={handleApplyFilters}>
              Apply
            </button>
            <button type="button" className="btn btn-sm btn-outline" onClick={handleResetFilters}>
              Reset
            </button>
          </div>
        </div>
      </section>

      {!activeFilters ? (
        <div className="alert alert-warning" style={{ marginBottom: 'var(--space-3)' }}>
          Enter filters and click Apply to load events.
        </div>
      ) : null}

      {progressVisible ? (
        <div
          style={{
            marginBottom: 'var(--space-4)',
            padding: 'var(--space-3)',
            borderRadius: 'var(--rounded-lg)',
            background: progress?.stage === 'complete'
              ? 'linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%)'
              : 'linear-gradient(135deg, #fff7ed 0%, #ffedd5 100%)',
            border: progress?.stage === 'complete' ? '1px solid #6ee7b7' : '1px solid #fdba74',
            boxShadow: progress?.stage === 'complete'
              ? '0 10px 30px rgba(16, 185, 129, 0.12)'
              : '0 10px 30px rgba(251, 146, 60, 0.15)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 'var(--space-2)' }}>
            <div
              style={{
                fontSize: 'var(--text-base)',
                fontWeight: 700,
                color: progress?.stage === 'complete' ? '#065f46' : '#9a3412',
              }}
            >
              {displayStageLabel}
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <div
                style={{
                  fontSize: 'var(--text-sm)',
                  fontWeight: 600,
                  color: progress?.stage === 'complete' ? '#065f46' : '#9a3412',
                }}
              >
                {displayPercentLabel}
              </div>
              <button
                type="button"
                className="btn btn-sm btn-outline"
                onClick={() => setShowProgressLogs((prev) => !prev)}
                style={{ height: '28px', padding: '0 8px' }}
                aria-label="Toggle loading logs"
              >
                ...
              </button>
            </div>
          </div>
          <div
            style={{
              height: '10px',
              borderRadius: '999px',
              backgroundColor: progress?.stage === 'complete' ? '#a7f3d0' : '#fed7aa',
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                width: `${progress?.stage === 'complete' ? 100 : (progress?.totalKnown ? displayPercent : 15)}%`,
                height: '100%',
                borderRadius: '999px',
                background: progress?.stage === 'complete'
                  ? 'linear-gradient(90deg, #10b981 0%, #34d399 100%)'
                  : 'linear-gradient(90deg, #ea580c 0%, #fb923c 100%)',
                transition: 'width 0.2s ease',
              }}
            />
          </div>
          <div
            style={{
              marginTop: 'var(--space-2)',
              fontSize: 'var(--text-sm)',
              color: progress?.stage === 'complete' ? '#065f46' : '#9a3412',
            }}
          >
            {displayLabel}
          </div>
          {showProgressLogs && (
            <div
              style={{
                marginTop: 'var(--space-3)',
                padding: 'var(--space-2)',
                borderRadius: 'var(--rounded-lg)',
                border: '1px solid var(--border)',
                backgroundColor: 'white',
                maxHeight: '240px',
                overflowY: 'auto',
                fontSize: 'var(--text-xs)',
              }}
            >
              {progressLogs.length === 0 ? (
                <div>No logs yet.</div>
              ) : (
                progressLogs.map((entry) => (
                  <div
                    key={entry.id}
                    style={{
                      display: 'flex',
                      gap: '8px',
                      padding: '4px 0',
                      borderBottom: '1px solid var(--border)',
                    }}
                  >
                    <div style={{ minWidth: '48px', color: 'var(--text-dim)' }}>
                      #{entry.id}
                    </div>
                    <div style={{ minWidth: '80px', color: 'var(--text-dim)' }}>
                      {new Date(entry.time).toLocaleTimeString()}
                    </div>
                    <div style={{ minWidth: '72px', fontWeight: 600 }}>
                      {entry.stage}
                    </div>
                    <div style={{ flex: 1 }}>{formatLogMessage(entry)}</div>
                  </div>
                ))
              )}
            </div>
          )}
        </div>
      ) : null}

      {eventsError ? (
        <div className={`alert ${eventsData.length ? 'alert-warning' : 'alert-error'}`}>
          Error loading events: {eventsError}
        </div>
      ) : (
        <EventsHistoryTable
          data={eventsData}
          loading={tableLoading}
          total={eventsTotal}
          page={eventsPage}
          pageSize={eventsPageSize}
          onPageChange={setEventsPage}
          onPageSizeChange={(newSize) => {
            setEventsPageSize(newSize);
            setEventsPage(1);
          }}
          sortConfig={eventsSortConfig}
          onSortChange={(newSortConfig) => {
            setEventsSortConfig(newSortConfig);
            setEventsPage(1);
          }}
          filters={eventsFilters}
          onFiltersChange={(newFilters) => {
            setEventsFilters(newFilters);
            setEventsPage(1);
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
