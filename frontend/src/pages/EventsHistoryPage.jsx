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
  setEventsSettings,
} from '../services/localStorage';
import {
  loadEventsHistoryDataset,
  loadEventsHistoryBestWindow,
  requestEventsHistoryCacheRefresh,
  subscribeEventsHistoryCacheRefresh,
  getCachedEventsHistorySettings,
  subscribeEventsHistoryProgress,
} from '../services/eventsHistoryData';
import { API_BASE_URL, getAuthHeaders } from '../services/api';

function formatDate(dateString, { dateOnly = false } = {}) {
  if (!dateString) return 'N/A';
  try {
    const date = new Date(dateString);
    if (dateOnly) {
      return date.toLocaleDateString();
    }
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
  const [eventsDayOffsetMode, setEventsDayOffsetMode] = useState(
    () => getEventsHistoryState().dayOffsetMode || 'performance_designated'
  );
  const [lastSettings, setLastSettings] = useState(() => getEventsSettings());
  const [settingsDraft, setSettingsDraft] = useState(() => getEventsSettings());
  const [appliedSettings, setAppliedSettings] = useState(() => getEventsSettings());
  const [feeDraft, setFeeDraft] = useState(0.1);
  const [appliedFee, setAppliedFee] = useState(0);
  const [bestWindowSummary, setBestWindowSummary] = useState(null);
  const [bestWindowLoading, setBestWindowLoading] = useState(false);
  const [bestWindowError, setBestWindowError] = useState(null);
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
  const [showOptionalSettings, setShowOptionalSettings] = useState(false);
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
    setEventsHistoryState({ dayOffsetMode: eventsDayOffsetMode });
  }, [eventsDayOffsetMode]);

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

  const draftFilters = React.useMemo(() => buildAppliedFilters(filterDraft), [filterDraft]);

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

  const appliedFilterSummary = React.useMemo(() => {
    if (!appliedFilters) return [];
    const summary = [];
    if (appliedFilters.eventDateFrom || appliedFilters.eventDateTo) {
      const fromLabel = appliedFilters.eventDateFrom || '...';
      const toLabel = appliedFilters.eventDateTo || '...';
      summary.push(`Date: ${fromLabel} to ${toLabel}`);
    }
    if (appliedFilters.sector) summary.push(`Sector: ${appliedFilters.sector}`);
    if (appliedFilters.industry) summary.push(`Industry: ${appliedFilters.industry}`);
    if (appliedFilters.source) summary.push(`Source: ${appliedFilters.source}`);
    if (appliedFilters.positionQuantitative) summary.push(`Pos(Q): ${appliedFilters.positionQuantitative}`);
    if (appliedFilters.positionQualitative) summary.push(`Pos(QL): ${appliedFilters.positionQualitative}`);
    return summary;
  }, [appliedFilters]);

  const appliedSettingsSummary = React.useMemo(() => {
    if (!appliedSettings) return [];
    const summary = [];
    const baseOffset = appliedSettings.baseOffset ?? 0;
    const baseField = appliedSettings.baseField ? String(appliedSettings.baseField).toUpperCase() : 'CLOSE';
    summary.push(`Base D${baseOffset} ${baseField}`);
    if (appliedSettings.minThreshold !== null && appliedSettings.minThreshold !== undefined) {
      summary.push(`MIN ${appliedSettings.minThreshold}%`);
    }
    if (appliedSettings.maxThreshold !== null && appliedSettings.maxThreshold !== undefined) {
      summary.push(`MAX ${appliedSettings.maxThreshold}%`);
    }
    if (Number.isFinite(appliedFee) && appliedFee > 0) {
      summary.push(`Fee ${appliedFee}%`);
    }
    if (Number.isFinite(appliedSettings?.bestWindowMinConf)) {
      summary.push(`Conf >= ${appliedSettings.bestWindowMinConf}%`);
    }
    return summary;
  }, [appliedSettings, appliedFee]);

  const hasDraftChanges = React.useMemo(() => {
    const draftKey = JSON.stringify(draftFilters);
    const appliedKey = appliedFilters ? JSON.stringify(appliedFilters) : '';
    return draftKey !== appliedKey;
  }, [draftFilters, appliedFilters]);

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
        const resolvedSettings = payload.settings || getCachedEventsHistorySettings() || getEventsSettings();
        setLastSettings(resolvedSettings);
        setAppliedSettings(resolvedSettings);
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

  useEffect(() => {
    let mounted = true;
    async function fetchBestWindow() {
      if (!appliedFilters || !hasActiveFilters(appliedFilters)) {
        setBestWindowSummary(null);
        return;
      }
      try {
        setBestWindowLoading(true);
        setBestWindowError(null);
        const payload = await loadEventsHistoryBestWindow(appliedFilters, appliedFee);
        if (mounted) {
          setBestWindowSummary(payload);
        }
      } catch (error) {
        if (mounted) {
          setBestWindowError(error.message || 'Failed to load best window.');
        }
      } finally {
        if (mounted) {
          setBestWindowLoading(false);
        }
      }
    }

    fetchBestWindow();
    return () => {
      mounted = false;
    };
  }, [appliedFilters, appliedFee, appliedSettings]);

  const handleApplyFilters = () => {
    const nextFilters = draftFilters;
    const settingsChanged = JSON.stringify(settingsDraft) !== JSON.stringify(appliedSettings);
    const feeChanged = feeDraft !== appliedFee;
    if (settingsChanged) {
      setEventsSettings(settingsDraft);
      setAppliedSettings(settingsDraft);
      requestEventsHistoryCacheRefresh({ preserveData: true });
    }
    if (feeChanged) {
      setAppliedFee(feeDraft);
    }
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
    setSettingsDraft(appliedSettings);
    setFeeDraft(appliedFee);
    setShowOptionalSettings(false);
    setAppliedFilters(null);
    setEventsData([]);
    setEventsTotal(0);
    setEventsError(null);
    setEventsLoading(false);
    setProgress(null);
  };

  const handleReload = () => {
    requestEventsHistoryCacheRefresh({ preserveData: true });
    setProgress(null);
  };

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
  const settingsChanged = JSON.stringify(settingsDraft) !== JSON.stringify(appliedSettings);
  const feeChanged = feeDraft !== appliedFee;
  const canApplyFilters = (hasActiveFilters(draftFilters) && (hasDraftChanges || !activeFilters)) || settingsChanged || feeChanged;
  const canResetFilters = activeFilters || hasDraftChanges || settingsChanged || feeChanged;

  const toolbarContent = (
    <div className="events-toolbar">
      <div className="events-toolbar__summary">
        <span className="events-toolbar__summary-label">Applied:</span>
        {[...appliedSettingsSummary, ...appliedFilterSummary].length === 0 ? (
          <span className="events-toolbar__chip events-toolbar__chip--muted">None</span>
        ) : (
          [...appliedSettingsSummary, ...appliedFilterSummary].map((item) => (
            <span key={item} className="events-toolbar__chip">
              {item}
            </span>
          ))
        )}
      </div>
      <div className="events-toolbar__form">
        <div>
          <label className="events-toolbar__label">Fee (%)</label>
          <input
            type="number"
            step="0.01"
            min="0"
            placeholder="e.g. 0.1"
            value={feeDraft}
            onChange={(e) => {
              const value = e.target.value.trim();
              setFeeDraft(value === '' ? 0 : parseFloat(value));
            }}
          />
        </div>
        <div>
          <label className="events-toolbar__label">
            Base Day Offset <span className="required-asterisk">*</span>
          </label>
          <select
            value={settingsDraft.baseOffset}
            onChange={(e) => setSettingsDraft((prev) => ({ ...prev, baseOffset: parseInt(e.target.value, 10) }))}
          >
            {Array.from({ length: 29 }, (_, i) => {
              const offset = i - 14;
              const label = offset === 0 ? 'D0' : `D${offset > 0 ? `+${offset}` : offset}`;
              return (
                <option key={offset} value={offset}>
                  {label}
                </option>
              );
            })}
          </select>
        </div>
        <div>
          <label className="events-toolbar__label">
            Base OHLC Field <span className="required-asterisk">*</span>
          </label>
          <select
            value={settingsDraft.baseField}
            onChange={(e) => setSettingsDraft((prev) => ({ ...prev, baseField: e.target.value }))}
          >
            <option value="open">Open</option>
            <option value="high">High</option>
            <option value="low">Low</option>
            <option value="close">Close</option>
          </select>
        </div>
        <div>
          <label className="events-toolbar__label">
            Event date from <span className="required-asterisk">*</span>
          </label>
          <input
            type="date"
            value={filterDraft.eventDateFrom}
            onChange={(e) => setFilterDraft((prev) => ({ ...prev, eventDateFrom: e.target.value }))}
          />
        </div>
        <div>
          <label className="events-toolbar__label">
            Event date to <span className="required-asterisk">*</span>
          </label>
          <input
            type="date"
            value={filterDraft.eventDateTo}
            onChange={(e) => setFilterDraft((prev) => ({ ...prev, eventDateTo: e.target.value }))}
          />
        </div>
        <div>
          <label className="events-toolbar__label">
            Position (Quantitative) <span className="required-asterisk">*</span>
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
      </div>
      <div className="events-toolbar__optional">
        <button
          type="button"
          className="btn btn-sm btn-outline"
          onClick={() => setShowOptionalSettings((prev) => !prev)}
        >
          {showOptionalSettings ? '선택 항목 숨기기' : '선택 항목 보기'}
        </button>
        {showOptionalSettings ? (
          <div className="events-toolbar__optional-grid">
            <div>
              <label className="events-toolbar__label">MIN% (Stop Loss)</label>
              <input
                type="number"
                placeholder="e.g. -10"
                value={settingsDraft.minThreshold ?? ''}
                onChange={(e) => {
                  const value = e.target.value.trim();
                  setSettingsDraft((prev) => ({
                    ...prev,
                    minThreshold: value === '' ? null : parseFloat(value),
                  }));
                }}
              />
            </div>
            <div>
              <label className="events-toolbar__label">MAX% (Profit Target)</label>
              <input
                type="number"
                placeholder="e.g. 20"
                value={settingsDraft.maxThreshold ?? ''}
                onChange={(e) => {
                  const value = e.target.value.trim();
                  setSettingsDraft((prev) => ({
                    ...prev,
                    maxThreshold: value === '' ? null : parseFloat(value),
                  }));
                }}
              />
            </div>
            <div>
              <label className="events-toolbar__label">Best Window Conf (%)</label>
              <input
                type="number"
                min="0"
                max="100"
                step="0.1"
                placeholder="e.g. 95"
                value={settingsDraft.bestWindowMinConf ?? ''}
                onChange={(e) => {
                  const value = e.target.value.trim();
                  setSettingsDraft((prev) => ({
                    ...prev,
                    bestWindowMinConf: value === '' ? null : parseFloat(value),
                  }));
                }}
              />
            </div>
            <div>
              <label className="events-toolbar__label">Sector</label>
              <div className="events-toolbar__inline">
                <input
                  type="text"
                  placeholder="e.g. Technology"
                  value={filterDraft.sector}
                  onChange={(e) => setFilterDraft((prev) => ({ ...prev, sector: e.target.value, sectorAll: false }))}
                  disabled={filterDraft.sectorAll}
                />
                <label className="events-toolbar__check">
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
              <label className="events-toolbar__label">Industry</label>
              <div className="events-toolbar__inline">
                <input
                  type="text"
                  placeholder="e.g. Semiconductors"
                  value={filterDraft.industry}
                  onChange={(e) => setFilterDraft((prev) => ({ ...prev, industry: e.target.value, industryAll: false }))}
                  disabled={filterDraft.industryAll}
                />
                <label className="events-toolbar__check">
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
              <label className="events-toolbar__label">Source</label>
              <div className="events-toolbar__inline">
                <input
                  type="text"
                  placeholder="e.g. Bloomberg"
                  value={filterDraft.source}
                  onChange={(e) => setFilterDraft((prev) => ({ ...prev, source: e.target.value, sourceAll: false }))}
                  disabled={filterDraft.sourceAll}
                />
                <label className="events-toolbar__check">
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
              <label className="events-toolbar__label">Position (Qualitative)</label>
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
          </div>
        ) : null}
      </div>
      <div className="events-toolbar__actions">
        <button
          type="button"
          className="btn btn-sm btn-primary"
          onClick={handleApplyFilters}
          disabled={!canApplyFilters || eventsLoading}
        >
          Apply
        </button>
        <button
          type="button"
          className="btn btn-sm btn-outline"
          onClick={handleResetFilters}
          disabled={!canResetFilters || eventsLoading}
        >
          Reset
        </button>
      </div>
    </div>
  );

  const bestWindowMeta = React.useMemo(() => {
    if (!bestWindowSummary) return null;
    const modeKey = eventsDayOffsetMode === 'performance_previous' ? 'previous' : 'designated';
    return bestWindowSummary[modeKey] || null;
  }, [bestWindowSummary, eventsDayOffsetMode]);

  const formatOffsetLabel = (offset) => (offset === 0 ? 'D0' : `D${offset}`);
  const parseOffsetKey = (key) => {
    if (key === 'd_0') return 0;
    const match = key.match(/^d_(pos|neg)(\d+)$/);
    if (!match) return null;
    const value = parseInt(match[2], 10);
    return match[1] === 'neg' ? -value : value;
  };
  const bestWindowMinConf = Number.isFinite(appliedSettings?.bestWindowMinConf)
    ? appliedSettings.bestWindowMinConf
    : null;
  const bestWindowDetailItems = React.useMemo(() => {
    if (!bestWindowMeta?.offsetAverages) return [];
    const minConf = bestWindowMinConf;
    const items = Object.entries(bestWindowMeta.offsetAverages)
      .map(([key, avg]) => {
        if (!Number.isFinite(avg)) return null;
        const confValue = Number.isFinite(bestWindowMeta?.offsetPValues?.[key])
          ? (1 - bestWindowMeta.offsetPValues[key]) * 100
          : null;
        if (!Number.isFinite(confValue)) return null;
        const avgPct = avg * 100;
        const score = avgPct * confValue;
        const offsetValue = parseOffsetKey(key);
        const offsetLabel = offsetValue !== null ? formatOffsetLabel(offsetValue) : key;
        return {
          offsetKey: key,
          offsetLabel,
          avg: avgPct.toFixed(2),
          conf: confValue.toFixed(1),
          score: score.toFixed(2),
          scoreValue: score,
          count: bestWindowMeta?.offsetCounts?.[key] ?? 0,
        };
      })
      .filter(Boolean);
    const filtered = Number.isFinite(minConf)
      ? items.filter((item) => Number(item.conf) >= minConf)
      : items;
    return filtered
      .sort((a, b) => b.scoreValue - a.scoreValue)
      .slice(0, 2)
      .map((item, index) => ({
        ...item,
        label: `${index + 1}${index === 0 ? 'st' : 'nd'}`,
      }));
  }, [bestWindowMeta, bestWindowMinConf]);
  const bestReturnLabel = bestWindowDetailItems.length
    ? `${bestWindowDetailItems[0].avg}%`
    : bestWindowLoading ? 'Loading...' : 'N/A';
  const [backtestMode, setBacktestMode] = React.useState('percent');
  const backtestModes = bestWindowMeta?.backtestModes || null;
  const selectedBacktest = backtestModes?.[backtestMode] || bestWindowMeta?.backtest || null;
  const backtestDetailLines = selectedBacktest
    ? [
      `Backtest(${selectedBacktest.exitMode || backtestMode}): hold=${selectedBacktest.holdDays ?? '-'}d | trades=${selectedBacktest.trades ?? 0}`,
      `Avg Daily Log=${((selectedBacktest.avgDailyLogReturn ?? 0) * 100).toFixed(2)}% | Score=${((selectedBacktest.avgScore ?? 0) * 100).toFixed(2)}%`,
      `Sharpe=${(selectedBacktest.strategy?.sharpe ?? 0).toFixed(2)} | Sortino=${(selectedBacktest.strategy?.sortino ?? 0).toFixed(2)} | Calmar=${(selectedBacktest.strategy?.calmar ?? 0).toFixed(2)}`,
    ]
    : [];

  React.useEffect(() => {
    if (bestWindowMeta?.backtest?.exitMode) {
      setBacktestMode(bestWindowMeta.backtest.exitMode);
    }
  }, [bestWindowMeta?.backtest?.exitMode]);
  const backtestDefaultLabel = bestWindowMeta?.backtest?.exitMode
    ? `Default mode: ${bestWindowMeta.backtest.exitMode}`
    : null;
  const backtestModeNote = eventsDayOffsetMode === 'performance_previous'
    ? 'Previous day 모드는 전일 대비 변화로 계산합니다. Hold=1일 때 일부 지표가 불안정할 수 있습니다.'
    : 'Designated date 모드는 기준일(Base Offset) 가격을 진입 기준으로 계산합니다.';
  const backtestModeTitle = eventsDayOffsetMode === 'performance_previous'
    ? 'Previous day 모드 설명'
    : 'Designated date 모드 설명';
  const backtestTableRows = selectedBacktest
    ? [
      ['Avg Log Return', (selectedBacktest.avgLogReturn ?? 0).toFixed(6), '전체 거래의 로그 수익 평균입니다. 클수록 좋아요.'],
      ['Avg Daily Log', (selectedBacktest.avgDailyLogReturn ?? 0).toFixed(6), '하루 평균 수익입니다. 클수록 좋아요.'],
      ['Avg CAGR Daily', (selectedBacktest.avgCagrDaily ?? 0).toFixed(6), '하루 복리 수익입니다. 클수록 좋아요.'],
      ['Avg MDD', (selectedBacktest.avgMdd ?? 0).toFixed(6), '거래 중 가장 크게 떨어진 비율의 평균입니다. 작을수록 좋아요.'],
      ['Avg ATR', (selectedBacktest.avgAtr ?? 0).toFixed(6), '평균 변동성입니다. 수치가 크면 가격이 많이 흔들린다는 뜻입니다.'],
      ['Avg Risk Penalty', (selectedBacktest.avgRiskPenalty ?? 0).toFixed(6), '위험 벌점입니다. 작을수록 좋아요.'],
      ['Avg Score', (selectedBacktest.avgScore ?? 0).toFixed(6), '수익에서 위험을 뺀 점수입니다. 클수록 좋아요.'],
      ['Sharpe', (selectedBacktest.strategy?.sharpe ?? 0).toFixed(6), '수익을 흔들림으로 나눈 값입니다. 클수록 좋아요.'],
      ['Sortino', (selectedBacktest.strategy?.sortino ?? 0).toFixed(6), '나쁜 흔들림만 고려한 점수입니다. 클수록 좋아요.'],
      ['Calmar', (selectedBacktest.strategy?.calmar ?? 0).toFixed(6), '연복리 수익을 최대 낙폭으로 나눈 값입니다. 클수록 좋아요.'],
      ['CAGR', (selectedBacktest.strategy?.cagr ?? 0).toFixed(6), '연 복리 수익률입니다. 클수록 좋아요.'],
      ['Max Drawdown', (selectedBacktest.strategy?.maxDrawdown ?? 0).toFixed(6), '전체 기간 중 가장 크게 떨어진 비율입니다. 작을수록 좋아요.'],
      ['Total Return', (selectedBacktest.strategy?.totalReturn ?? 0).toFixed(6), '전체 기간의 누적 수익률입니다. 클수록 좋아요.'],
      ['Trades', String(selectedBacktest.trades ?? 0), '계산에 사용된 거래 수입니다. 너무 적으면 참고용입니다.'],
    ]
    : [];
  const offsetAverageRows = bestWindowMeta?.offsetAverages
    ? Object.entries(bestWindowMeta.offsetAverages)
      .filter(([, value]) => Number.isFinite(value))
      .map(([key, value]) => {
        const count = bestWindowMeta.offsetCounts?.[key] ?? 0;
        const pValueRaw = bestWindowMeta.offsetPValues?.[key];
        const confidence = Number.isFinite(pValueRaw) ? ((1 - pValueRaw) * 100).toFixed(1) : null;
        const stdevRaw = bestWindowMeta.offsetStdDevs?.[key];
        const stdev = Number.isFinite(stdevRaw) ? (stdevRaw * 100).toFixed(4) : null;
        return [key, ((value || 0) * 100).toFixed(4), count, stdev, confidence];
      })
    : [];

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
        </div>
      </header>

      <section style={{ marginBottom: 'var(--space-4)' }}>
        <h2 style={{ marginBottom: 'var(--space-2)' }}>Dashboard</h2>
        {kpisLoading ? (
          <div className="loading">Loading KPIs...</div>
        ) : kpisError ? (
          <div className="alert alert-error">Error loading KPIs: {kpisError}</div>
        ) : (
          <>
            <div className="events-kpi-row">
              <KPICard
                title="Coverage"
                value={kpis.coverage.toLocaleString()}
                subtitle="Active tickers"
              />
              <KPICard
                title="Best Window"
                value={bestReturnLabel}
                subtitle={(
                  <div>
                    {bestWindowDetailItems.length === 0 ? (
                      <div>
                        {bestWindowLoading
                          ? 'Loading...'
                          : bestWindowError
                            || (bestWindowMeta?.topWindows?.length
                              ? (Number.isFinite(bestWindowMinConf)
                                ? `No windows with Conf >= ${bestWindowMinConf}%`
                                : 'Complete to compute')
                              : 'Complete to compute')}
                      </div>
                    ) : (
                      <>
                        <details style={{ marginBottom: 'var(--space-1)' }}>
                          <summary style={{ cursor: 'pointer', fontSize: 'var(--text-xs)' }}>
                            Best Window Details
                          </summary>
                          {bestWindowDetailItems.map((item) => (
                            <div
                              key={`${item.label}-${item.buy}-${item.sell}`}
                              style={{
                                marginTop: '4px',
                                padding: '6px 8px',
                                borderRadius: 'var(--rounded-sm)',
                                backgroundColor: 'var(--surface)',
                              }}
                            >
                              <table
                                style={{
                                  width: '100%',
                                  borderCollapse: 'collapse',
                                  fontSize: 'var(--text-xs)',
                                  tableLayout: 'fixed',
                                }}
                              >
                                <tbody>
                                  <tr>
                                    <td style={{ padding: '2px 6px', color: 'var(--text-dim)' }}>Rank</td>
                                    <td style={{ padding: '2px 6px' }}>{item.label}</td>
                                    <td style={{ padding: '2px 6px', color: 'var(--text-dim)' }}>Offset</td>
                                    <td style={{ padding: '2px 6px' }}>{item.offsetLabel}</td>
                                  </tr>
                                  <tr>
                                    <td style={{ padding: '2px 6px', color: 'var(--text-dim)' }}>Avg (%)</td>
                                    <td style={{ padding: '2px 6px' }}>{item.avg}</td>
                                    <td style={{ padding: '2px 6px', color: 'var(--text-dim)' }}>Conf (%)</td>
                                    <td style={{ padding: '2px 6px' }}>{item.conf}</td>
                                  </tr>
                                  <tr>
                                    <td style={{ padding: '2px 6px', color: 'var(--text-dim)' }}>Score</td>
                                    <td style={{ padding: '2px 6px' }}>{item.score}</td>
                                    <td style={{ padding: '2px 6px', color: 'var(--text-dim)' }}>N</td>
                                    <td style={{ padding: '2px 6px' }}>{item.count}</td>
                                  </tr>
                                </tbody>
                              </table>
                            </div>
                          ))}
                        </details>
                        {backtestTableRows.length > 0 ? (
                          <details style={{ marginTop: 'var(--space-1)' }}>
                            <summary style={{ cursor: 'pointer', fontSize: 'var(--text-xs)' }}>
                              Backtest Details
                            </summary>
                            <div style={{ marginTop: '6px', marginBottom: '6px' }}>
                              {backtestDefaultLabel ? (
                                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)' }}>
                                  현재 기본값: {backtestDefaultLabel.replace('Default mode: ', '')}
                                </div>
                              ) : null}
                              <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)', display: 'flex', alignItems: 'center', gap: '6px', marginTop: '4px' }}>
                                <span>{backtestModeTitle}</span>
                                <span
                                  title={`${backtestModeNote} percent는 퍼센트 기준, ATR은 변동성 기준으로 손절/익절을 계산합니다.`}
                                  style={{
                                    display: 'inline-flex',
                                    justifyContent: 'center',
                                    alignItems: 'center',
                                    width: '16px',
                                    height: '16px',
                                    borderRadius: '999px',
                                    backgroundColor: 'var(--surface)',
                                    border: '1px solid var(--border)',
                                    fontSize: '10px',
                                    color: 'var(--text-dim)',
                                    cursor: 'help',
                                  }}
                                >
                                  ?
                                </span>
                              </div>
                              <div style={{ display: 'flex', gap: '6px', marginTop: '6px' }}>
                                <button
                                  type="button"
                                  className={`btn btn-sm ${backtestMode === 'percent' ? 'btn-primary' : 'btn-outline'}`}
                                  onClick={() => setBacktestMode('percent')}
                                  style={{ flex: 1 }}
                                >
                                  %
                                </button>
                                <button
                                  type="button"
                                  className={`btn btn-sm ${backtestMode === 'atr' ? 'btn-primary' : 'btn-outline'}`}
                                  onClick={() => setBacktestMode('atr')}
                                  style={{ flex: 1 }}
                                >
                                  ATR
                                </button>
                              </div>
                            </div>
                            <table
                              style={{
                                width: '100%',
                                marginTop: 'var(--space-1)',
                                borderCollapse: 'collapse',
                                fontSize: 'var(--text-xs)',
                              }}
                            >
                              <tbody>
                                {backtestTableRows.map(([label, value, help]) => (
                                  <tr key={label}>
                                    <td style={{ padding: '2px 6px', color: 'var(--text-dim)' }}>
                                      <span>{label}</span>
                                      <span
                                        title={help}
                                        style={{
                                          display: 'inline-flex',
                                          justifyContent: 'center',
                                          alignItems: 'center',
                                          marginLeft: '6px',
                                          width: '16px',
                                          height: '16px',
                                          borderRadius: '999px',
                                          backgroundColor: 'var(--surface)',
                                          border: '1px solid var(--border)',
                                          fontSize: '10px',
                                          color: 'var(--text-dim)',
                                          cursor: 'help',
                                        }}
                                      >
                                        ?
                                      </span>
                                    </td>
                                    <td style={{ padding: '2px 6px', textAlign: 'right' }}>{value}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </details>
                        ) : null}
                        {offsetAverageRows.length > 0 ? (
                          <details style={{ marginTop: 'var(--space-1)' }}>
                            <summary style={{ cursor: 'pointer', fontSize: 'var(--text-xs)' }}>
                              Raw Offset Averages (Backend)
                            </summary>
                            <table
                              style={{
                                width: '100%',
                                marginTop: 'var(--space-1)',
                                borderCollapse: 'collapse',
                                fontSize: 'var(--text-xs)',
                              }}
                            >
                              <thead>
                                <tr>
                                  <th style={{ textAlign: 'left', padding: '2px 6px', color: 'var(--text-dim)' }}>Offset</th>
                                  <th style={{ textAlign: 'right', padding: '2px 6px', color: 'var(--text-dim)' }}>Avg (%)</th>
                                  <th style={{ textAlign: 'right', padding: '2px 6px', color: 'var(--text-dim)' }}>N</th>
                                  <th style={{ textAlign: 'right', padding: '2px 6px', color: 'var(--text-dim)' }}>
                                    Std (%)
                                    <span
                                      title="평균값이 얼마나 흔들리는지 보여줍니다. 숫자가 클수록 들쑥날쑥합니다."
                                      style={{
                                        display: 'inline-flex',
                                        justifyContent: 'center',
                                        alignItems: 'center',
                                        marginLeft: '6px',
                                        width: '14px',
                                        height: '14px',
                                        borderRadius: '999px',
                                        backgroundColor: 'var(--surface)',
                                        border: '1px solid var(--border)',
                                        fontSize: '9px',
                                        color: 'var(--text-dim)',
                                        cursor: 'help',
                                      }}
                                    >
                                      ?
                                    </span>
                                  </th>
                                  <th style={{ textAlign: 'right', padding: '2px 6px', color: 'var(--text-dim)' }}>
                                    Conf (%)
                                    <span
                                      title="평균이 우연일 가능성이 낮다는 뜻입니다. 표본이 작거나 변동이 크면 낮아질 수 있습니다."
                                      style={{
                                        display: 'inline-flex',
                                        justifyContent: 'center',
                                        alignItems: 'center',
                                        marginLeft: '6px',
                                        width: '14px',
                                        height: '14px',
                                        borderRadius: '999px',
                                        backgroundColor: 'var(--surface)',
                                        border: '1px solid var(--border)',
                                        fontSize: '9px',
                                        color: 'var(--text-dim)',
                                        cursor: 'help',
                                      }}
                                    >
                                      ?
                                    </span>
                                  </th>
                                </tr>
                              </thead>
                              <tbody>
                                {offsetAverageRows.map(([key, value, count, stdev, confidence]) => (
                                  <tr key={key}>
                                    <td style={{ padding: '2px 6px' }}>{key}</td>
                                    <td style={{ padding: '2px 6px', textAlign: 'right' }}>{value}</td>
                                    <td style={{ padding: '2px 6px', textAlign: 'right' }}>{count}</td>
                                    <td style={{ padding: '2px 6px', textAlign: 'right' }}>{stdev ?? '-'}</td>
                                    <td style={{ padding: '2px 6px', textAlign: 'right' }}>{confidence ?? '-'}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </details>
                        ) : null}
                      </>
                    )}
                  </div>
                )}
              />
            </div>
            <div className="events-kpi-row events-kpi-row--freshness">
              <KPICard
                title="Targets Freshness"
                value={formatDate(kpis.targetsFreshness, { dateOnly: true })}
                subtitle="config_lv3_targets updated_at"
                className="kpi-card--compact"
              />
              <KPICard
                title="Quantitatives Freshness"
                value={formatDate(kpis.quantitativesFreshness, { dateOnly: true })}
                subtitle="config_lv3_quantitatives updated_at"
                className="kpi-card--compact"
              />
              <KPICard
                title="Events Freshness"
                value={formatDate(kpis.eventsFreshness, { dateOnly: true })}
                subtitle="txn_events updated_at"
                className="kpi-card--compact"
              />
            </div>
          </>
        )}
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
          dayOffsetMode={eventsDayOffsetMode}
          onDayOffsetModeChange={setEventsDayOffsetMode}
          minThreshold={lastSettings?.minThreshold}
          maxThreshold={lastSettings?.maxThreshold}
          baseOffset={lastSettings?.baseOffset}
          baseField={lastSettings?.baseField}
          toolbarContent={toolbarContent}
          onReload={handleReload}
        />
      )}
    </>
  );
}
