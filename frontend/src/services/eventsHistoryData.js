import { API_BASE_URL, getAuthHeaders } from './api';
import { supabase } from './supabaseClient';
import {
  getItem,
  setItem,
  getEventsSettings,
} from './localStorage';

const EVENTS_HISTORY_PAGE_SIZE = 1000;
const EVENTS_HISTORY_TICKER_BATCH = 100;
const EVENTS_HISTORY_CACHE_VERSION = 1;
const EVENTS_HISTORY_CACHE_VERSION_KEY = 'ui.events_history_cache_version';
const EVENTS_HISTORY_CACHE_TOKEN_KEY = 'ui.events_history_cache_token';
const EVENTS_HISTORY_MAX_ROWS = 100000;

let cachedPayload = null;
let cachedToken = null;
let cachedSettings = null;
let cachedFiltersKey = null;
let cachedSettingsKey = null;
let cachedEvents = null;
let cachedEventsRaw = null;
let cachedTickerCache = null;
let cachedDataFiltersKey = null;
let inFlightPromise = null;
const updateListeners = new Set();
const progressListeners = new Set();

function emitProgress(payload) {
  progressListeners.forEach((listener) => listener(payload));
}

export function subscribeEventsHistoryProgress(listener) {
  progressListeners.add(listener);
  return () => progressListeners.delete(listener);
}

async function fetchWithAuthRetry(url, options, allowRetry = true) {
  const response = await fetch(url, options);
  if (!response.ok && allowRetry && (response.status === 401 || response.status === 403)) {
    try {
      await supabase.auth.refreshSession();
    } catch (error) {
      return response;
    }
    const headers = await getAuthHeaders(options.headers);
    const retryOptions = { ...options, headers };
    return fetchWithAuthRetry(url, retryOptions, false);
  }
  return response;
}

function normalizeDateString(value) {
  if (!value) return null;
  if (typeof value === 'string') {
    return value.slice(0, 10);
  }
  if (value instanceof Date) {
    return value.toISOString().slice(0, 10);
  }
  return null;
}

function normalizeHistoricalPrice(raw) {
  if (!raw) return [];
  if (typeof raw === 'string') {
    try {
      const parsed = JSON.parse(raw);
      return normalizeHistoricalPrice(parsed);
    } catch (error) {
      return [];
    }
  }
  if (Array.isArray(raw)) return raw;
  if (typeof raw === 'object' && Array.isArray(raw.historical)) {
    return raw.historical;
  }
  return [];
}

function toFiniteOrNull(value) {
  if (value === '' || value === null || value === undefined) {
    return null;
  }
  const numValue = Number(value);
  return Number.isFinite(numValue) ? numValue : null;
}

function matchesFilters(event, filters) {
  if (!filters) return true;
  const eventDate = event?.event_date ? String(event.event_date) : '';
  if ((filters.eventDateFrom || filters.eventDateTo) && !eventDate) {
    return false;
  }
  if (filters.eventDateFrom && eventDate && eventDate < filters.eventDateFrom) {
    return false;
  }
  if (filters.eventDateTo && eventDate && eventDate > filters.eventDateTo) {
    return false;
  }
  if (filters.sector) {
    const sector = String(event?.sector || '').toLowerCase();
    if (!sector.includes(String(filters.sector).toLowerCase())) {
      return false;
    }
  }
  if (filters.industry) {
    const industry = String(event?.industry || '').toLowerCase();
    if (!industry.includes(String(filters.industry).toLowerCase())) {
      return false;
    }
  }
  if (filters.source) {
    const source = String(event?.source || '').toLowerCase();
    if (!source.includes(String(filters.source).toLowerCase())) {
      return false;
    }
  }
  if (filters.positionQuantitative) {
    const positionQ = String(event?.position_quantitative || '').toLowerCase();
    if (positionQ !== String(filters.positionQuantitative).toLowerCase()) {
      return false;
    }
  }
  if (filters.positionQualitative) {
    const positionQL = String(event?.position_qualitative || '').toLowerCase();
    if (positionQL !== String(filters.positionQualitative).toLowerCase()) {
      return false;
    }
  }
  return true;
}

function buildTickerCache(historicalPrices) {
  const ohlcByDate = {};
  const dates = [];
  historicalPrices.forEach((record) => {
    const dateKey = normalizeDateString(record?.date);
    if (!dateKey) {
      return;
    }
    const open = toFiniteOrNull(record.open);
    const high = toFiniteOrNull(record.high);
    const low = toFiniteOrNull(record.low);
    const close = toFiniteOrNull(record.close);
    ohlcByDate[dateKey] = {
      open,
      high,
      low,
      close,
    };
    dates.push(dateKey);
  });
  dates.sort();
  const indexByDate = new Map();
  dates.forEach((dateKey, idx) => {
    indexByDate.set(dateKey, idx);
  });
  return {
    ohlcByDate,
    datesAsc: dates,
    indexByDate,
  };
}

function buildEventsParams(page, pageSize, filters) {
  const params = new URLSearchParams({
    page: String(page),
    pageSize: String(pageSize),
    skipCount: '1',
  });
  if (filters?.eventDateFrom) {
    params.append('eventDateFrom', filters.eventDateFrom);
  }
  if (filters?.eventDateTo) {
    params.append('eventDateTo', filters.eventDateTo);
  }
  if (filters?.sector) {
    params.append('sector', filters.sector);
  }
  if (filters?.industry) {
    params.append('industry', filters.industry);
  }
  if (filters?.source) {
    params.append('source', filters.source);
  }
  if (filters?.positionQuantitative) {
    params.append('position_quantitative', filters.positionQuantitative);
  }
  if (filters?.positionQualitative) {
    params.append('position_qualitative', filters.positionQualitative);
  }
  return params;
}

async function fetchEventsPage(page, pageSize, filters) {
  const params = buildEventsParams(page, pageSize, filters);
  const response = await fetchWithAuthRetry(
    `${API_BASE_URL}/dashboard/events?${params.toString()}`,
    { headers: await getAuthHeaders() }
  );
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    const errorMessage = errorData.detail || errorData.error?.message || `HTTP ${response.status}`;
    throw new Error(errorMessage);
  }
  return response.json();
}

async function fetchHistoricalPrices(tickers) {
  const results = {};
  const totalBatches = Math.ceil(tickers.length / EVENTS_HISTORY_TICKER_BATCH) || 0;
  let batchIndex = 0;
  for (let i = 0; i < tickers.length; i += EVENTS_HISTORY_TICKER_BATCH) {
    const batch = tickers.slice(i, i + EVENTS_HISTORY_TICKER_BATCH);
    const response = await fetchWithAuthRetry(`${API_BASE_URL}/history/historical-prices`, {
      method: 'POST',
      headers: await getAuthHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ tickers: batch }),
    });
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      const errorMessage = errorData.detail || errorData.error?.message || `HTTP ${response.status}`;
      throw new Error(errorMessage);
    }
    const payload = await response.json();
    Object.assign(results, payload.data || {});
    batchIndex += 1;
    emitProgress({
      stage: 'historical',
      batch: batchIndex,
      batches: totalBatches,
      percent: totalBatches ? Math.min(100, (batchIndex / totalBatches) * 100) : 0,
    });
  }
  return results;
}

function buildDayKey(offset) {
  if (offset === 0) return 'd_0';
  if (offset > 0) return `d_pos${offset}`;
  return `d_neg${Math.abs(offset)}`;
}

function parseThreshold(value) {
  if (value === '' || value === null || value === undefined) {
    return null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed / 100 : null;
}

function getPositionMultiplier(position) {
  if (!position) return 1;
  const normalized = String(position).toLowerCase();
  if (normalized === 'short') return -1;
  return 1;
}

function findNearestFutureIndex(datesAsc, targetDate) {
  if (!targetDate || datesAsc.length === 0) return -1;
  for (let i = 0; i < datesAsc.length; i += 1) {
    if (datesAsc[i] >= targetDate) {
      return i;
    }
  }
  return -1;
}

function computeEventRows(events, tickerCache, settings, progressMeta = null) {
  const baseOffset = Number.isFinite(Number(settings.baseOffset)) ? Number(settings.baseOffset) : 0;
  const baseField = settings.baseField || 'close';
  const minThreshold = parseThreshold(settings.minThreshold);
  const maxThreshold = parseThreshold(settings.maxThreshold);

  const rows = new Array(events.length);
  const progressStep = 200;
  const emit = progressMeta?.emitProgress;
  const baseProcessed = progressMeta?.baseProcessed || 0;
  const totalCount = progressMeta?.total || events.length;

  for (let idx = 0; idx < events.length; idx += 1) {
    const event = events[idx];
    const ticker = event.ticker;
    const eventDate = event.event_date;
    const cache = tickerCache.get(ticker);
    const datesAsc = cache?.datesAsc || [];
    const indexByDate = cache?.indexByDate || new Map();
    const ohlcByDate = cache?.ohlcByDate || {};
    let eventIndex = eventDate && indexByDate.has(eventDate) ? indexByDate.get(eventDate) : -1;
    if (eventIndex < 0) {
      eventIndex = findNearestFutureIndex(datesAsc, eventDate);
    }

    const dayOffsetTargetDates = {};
    const dayOffsetPriceTrend = {};
    const dayOffsetOpen = {};
    const dayOffsetHigh = {};
    const dayOffsetLow = {};
    const dayOffsetClose = {};
    const dayOffsetPerformance = {};

    let basePrice = null;
    if (eventIndex >= 0 && datesAsc[eventIndex + baseOffset]) {
      const baseDate = datesAsc[eventIndex + baseOffset];
      const baseOhlc = ohlcByDate[baseDate];
      const baseValue = baseOhlc ? baseOhlc[baseField] : null;
      if (Number.isFinite(baseValue) && baseValue !== 0) {
        basePrice = baseValue;
      }
    }

    const positionSource = event.position_quantitative || event.position_qualitative || event.position;
    const positionMultiplier = getPositionMultiplier(positionSource);
    let stopOffset = null;
    let stopValueRaw = null;

    const thresholdStart = baseOffset < 0 ? baseOffset : 0;

    for (let offset = -14; offset <= 14; offset += 1) {
      const dayKey = buildDayKey(offset);
      const dateKey = eventIndex >= 0 ? datesAsc[eventIndex + offset] : null;
      dayOffsetTargetDates[dayKey] = dateKey || null;

      const ohlc = dateKey ? ohlcByDate[dateKey] : null;
      const open = ohlc?.open ?? null;
      const high = ohlc?.high ?? null;
      const low = ohlc?.low ?? null;
      const close = ohlc?.close ?? null;

      dayOffsetOpen[dayKey] = Number.isFinite(open) ? open : null;
      dayOffsetHigh[dayKey] = Number.isFinite(high) ? high : null;
      dayOffsetLow[dayKey] = Number.isFinite(low) ? low : null;
      dayOffsetClose[dayKey] = Number.isFinite(close) ? close : null;

      if (offset === 0) {
        dayOffsetPriceTrend[dayKey] = dayOffsetOpen[dayKey];
      } else {
        dayOffsetPriceTrend[dayKey] = dayOffsetClose[dayKey];
      }

      if (stopOffset !== null && offset > stopOffset) {
        dayOffsetPerformance[dayKey] = null;
        continue;
      }

      const baseForOffset = (offset === 0 && baseOffset === 0)
        ? (Number.isFinite(open) && open !== 0 ? open : null)
        : basePrice;
      if (!baseForOffset) {
        dayOffsetPerformance[dayKey] = null;
        continue;
      }

      const perfCloseRaw = Number.isFinite(close)
        ? (close - baseForOffset) / baseForOffset
        : null;
      const perfHighRaw = Number.isFinite(high)
        ? (high - baseForOffset) / baseForOffset
        : null;
      const perfLowRaw = Number.isFinite(low)
        ? (low - baseForOffset) / baseForOffset
        : null;
      const perfCloseDisplay = Number.isFinite(perfCloseRaw)
        ? perfCloseRaw * positionMultiplier
        : null;
      const perfHighDisplay = Number.isFinite(perfHighRaw)
        ? perfHighRaw * positionMultiplier
        : null;
      const perfLowDisplay = Number.isFinite(perfLowRaw)
        ? perfLowRaw * positionMultiplier
        : null;

      if (offset >= thresholdStart && stopOffset === null) {
        const minProbe = positionMultiplier === -1 ? perfHighDisplay : perfLowDisplay;
        const maxProbe = positionMultiplier === -1 ? perfLowDisplay : perfHighDisplay;
        const closeProbe = perfCloseDisplay;
        const minCandidates = [minProbe, closeProbe].filter((value) => Number.isFinite(value));
        const maxCandidates = [maxProbe, closeProbe].filter((value) => Number.isFinite(value));
        const minCheck = minCandidates.length ? Math.min(...minCandidates) : null;
        const maxCheck = maxCandidates.length ? Math.max(...maxCandidates) : null;

        if (minThreshold !== null && Number.isFinite(minCheck) && minCheck <= minThreshold) {
          stopOffset = offset;
          stopValueRaw = positionMultiplier !== 0
            ? minThreshold / positionMultiplier
            : null;
        } else if (maxThreshold !== null && Number.isFinite(maxCheck) && maxCheck >= maxThreshold) {
          stopOffset = offset;
          stopValueRaw = positionMultiplier !== 0
            ? maxThreshold / positionMultiplier
            : null;
        }
      }

      if (stopOffset !== null && offset === stopOffset) {
        dayOffsetPerformance[dayKey] = stopValueRaw;
      } else {
        dayOffsetPerformance[dayKey] = Number.isFinite(perfCloseRaw) ? perfCloseRaw : null;
      }
    }

    const findThresholdStop = () => {
      if (minThreshold === null && maxThreshold === null) {
        return null;
      }
      for (let offset = 0; offset <= 14; offset += 1) {
        const dayKey = buildDayKey(offset);
        const valueRaw = dayOffsetPerformance[dayKey];
        if (!Number.isFinite(valueRaw)) {
          continue;
        }
        const displayValue = valueRaw * positionMultiplier;
        if (minThreshold !== null && displayValue <= minThreshold) {
          return { offset, threshold: minThreshold };
        }
        if (maxThreshold !== null && displayValue >= maxThreshold) {
          return { offset, threshold: maxThreshold };
        }
      }
      return null;
    };

    let wts = null;
    let bestValue = null;
    for (let offset = 1; offset <= 14; offset += 1) {
      const dayKey = buildDayKey(offset);
      const valueRaw = dayOffsetPerformance[dayKey];
      const valueDisplay = Number.isFinite(valueRaw)
        ? valueRaw * positionMultiplier
        : null;
      if (Number.isFinite(valueDisplay)) {
        if (bestValue === null || valueDisplay > bestValue) {
          bestValue = valueDisplay;
          wts = offset;
        }
      }
    }

    const row = {
      ...event,
      position: positionSource,
      wts,
      day_offset_performance: dayOffsetPerformance,
      day_offset_price_trend: dayOffsetPriceTrend,
      day_offset_price_trend_close: dayOffsetClose,
      day_offset_price_trend_open: dayOffsetOpen,
      day_offset_price_trend_low: dayOffsetLow,
      day_offset_price_trend_high: dayOffsetHigh,
      day_offset_target_dates: dayOffsetTargetDates,
      is_blurred: false,
    };

    for (let offset = -14; offset <= 14; offset += 1) {
      const dayKey = buildDayKey(offset);
      row[dayKey] = dayOffsetPerformance[dayKey];
    }

    const thresholdStop = stopOffset !== null
      ? { offset: stopOffset, threshold: positionMultiplier !== 0 ? stopValueRaw * positionMultiplier : null }
      : findThresholdStop();
    if (thresholdStop) {
      const rawThresholdValue = positionMultiplier !== 0
        ? thresholdStop.threshold / positionMultiplier
        : null;
      const stopKey = buildDayKey(thresholdStop.offset);
      dayOffsetPerformance[stopKey] = rawThresholdValue;
      row[stopKey] = rawThresholdValue;

      for (let offset = thresholdStop.offset + 1; offset <= 14; offset += 1) {
        const dayKey = buildDayKey(offset);
        dayOffsetPerformance[dayKey] = null;
        row[dayKey] = null;
      }
    }

    rows[idx] = row;

    if ((idx + 1) % progressStep === 0 || idx === events.length - 1) {
      if (emit) {
        const processed = baseProcessed + idx + 1;
        emit({
          stage: 'compute',
          processed,
          total: totalCount,
          percent: totalCount ? Math.min(100, (processed / totalCount) * 100) : 0,
        });
      }
    }
  }

  return rows;
}

export function requestEventsHistoryCacheRefresh({ preserveData = false } = {}) {
  const token = Date.now();
  setItem(EVENTS_HISTORY_CACHE_TOKEN_KEY, token);
  cachedPayload = null;
  cachedToken = null;
  cachedSettings = null;
  cachedFiltersKey = null;
  cachedSettingsKey = null;
  cachedEvents = null;
  if (!preserveData) {
    cachedEventsRaw = null;
    cachedTickerCache = null;
    cachedDataFiltersKey = null;
  }
  inFlightPromise = null;
  updateListeners.forEach((listener) => listener(token));
  return token;
}

export function subscribeEventsHistoryCacheRefresh(listener) {
  updateListeners.add(listener);
  return () => updateListeners.delete(listener);
}

export function getCachedEventsHistorySettings() {
  return cachedSettings;
}

export async function loadEventsHistoryDataset(filters = null) {
  const filtersKey = JSON.stringify(filters || {});
  const settingsKey = JSON.stringify(getEventsSettings() || {});
  const storedVersion = getItem(EVENTS_HISTORY_CACHE_VERSION_KEY, 0);
  if (storedVersion !== EVENTS_HISTORY_CACHE_VERSION) {
    setItem(EVENTS_HISTORY_CACHE_VERSION_KEY, EVENTS_HISTORY_CACHE_VERSION);
    requestEventsHistoryCacheRefresh();
  }

  const token = getItem(EVENTS_HISTORY_CACHE_TOKEN_KEY, 0);
  if (cachedPayload && cachedToken === token && cachedFiltersKey === filtersKey && cachedSettingsKey === settingsKey) {
    return cachedPayload;
  }
  if (inFlightPromise && cachedToken === token && cachedFiltersKey === filtersKey && cachedSettingsKey === settingsKey) {
    return inFlightPromise;
  }

  const settings = getEventsSettings();
  cachedToken = token;
  cachedSettings = settings;
  cachedFiltersKey = filtersKey;
  cachedSettingsKey = settingsKey;
  const tokenAtStart = token;

  inFlightPromise = (async () => {
    emitProgress({ stage: 'start', percent: 0 });
    if (
      cachedEventsRaw
      && cachedTickerCache
      && cachedDataFiltersKey === filtersKey
      && cachedSettingsKey !== settingsKey
    ) {
      const rows = computeEventRows(cachedEventsRaw, cachedTickerCache, settings, {
        emitProgress,
        baseProcessed: 0,
        total: cachedEventsRaw.length,
      });
      const payload = {
        rows,
        total: rows.length,
        settings,
        token: tokenAtStart,
      };
      cachedPayload = payload;
      cachedSettings = settings;
      cachedSettingsKey = settingsKey;
      emitProgress({
        stage: 'complete',
        processed: rows.length,
        total: rows.length,
        totalKnown: true,
        percent: 100,
      });
      return payload;
    }
    const tickerCache = new Map();
    const rows = [];
    const rawEvents = [];
    let page = 1;
    let total = 0;
    let processed = 0;
    let filteredTotal = 0;
    let totalKnown = false;

    while (true) {
      const result = await fetchEventsPage(page, EVENTS_HISTORY_PAGE_SIZE, filters);
      total = result.total || 0;
      const rawRows = result.data || [];
      const pageRows = rawRows.filter((event) => matchesFilters(event, filters));
      filteredTotal += pageRows.length;
      emitProgress({
        stage: 'events',
        loaded: filteredTotal,
        total: filteredTotal,
        totalKnown,
        percent: totalKnown ? 100 : null,
      });
      if (rawRows.length === 0) {
        break;
      }

      const pageTickers = Array.from(new Set(pageRows.map((event) => event.ticker).filter(Boolean)));
      const missingTickers = pageTickers.filter((ticker) => !tickerCache.has(ticker));
      if (missingTickers.length > 0) {
        const historicalMap = await fetchHistoricalPrices(missingTickers);
        missingTickers.forEach((ticker) => {
          const normalized = normalizeHistoricalPrice(historicalMap[ticker]);
          tickerCache.set(ticker, buildTickerCache(normalized));
        });
      }

      const computedRows = computeEventRows(pageRows, tickerCache, settings, {
        emitProgress,
        baseProcessed: processed,
        total,
      });
      const remainingSlots = EVENTS_HISTORY_MAX_ROWS - rows.length;
      if (remainingSlots <= 0) {
        totalKnown = true;
        break;
      }
      const limitedComputed = computedRows.slice(0, remainingSlots);
      const limitedRaw = pageRows.slice(0, remainingSlots);
      rows.push(...limitedComputed);
      rawEvents.push(...limitedRaw);
      processed += limitedComputed.length;
      if (rows.length >= EVENTS_HISTORY_MAX_ROWS) {
        filteredTotal = rows.length;
        totalKnown = true;
      }
      cachedEvents = rows.map((row) => row);
      cachedEventsRaw = rawEvents.map((row) => row);
      cachedTickerCache = tickerCache;
      cachedDataFiltersKey = filtersKey;
      emitProgress({
        stage: 'compute',
        processed,
        total: filteredTotal,
        totalKnown,
        percent: totalKnown && filteredTotal
          ? Math.min(100, (processed / filteredTotal) * 100)
          : null,
        rows,
      });

      page += 1;
      if (rawRows.length < EVENTS_HISTORY_PAGE_SIZE || rows.length >= EVENTS_HISTORY_MAX_ROWS) {
        totalKnown = true;
        break;
      }
    }

    const payload = {
      rows,
      total: rows.length,
      settings,
      token: tokenAtStart,
    };
    if (getItem(EVENTS_HISTORY_CACHE_TOKEN_KEY, 0) === tokenAtStart) {
      cachedPayload = payload;
    }
    emitProgress({
      stage: 'complete',
      processed,
      total: filteredTotal,
      totalKnown: true,
      percent: 100,
    });
    return payload;
  })();

  try {
    return await inFlightPromise;
  } finally {
    inFlightPromise = null;
  }
}
