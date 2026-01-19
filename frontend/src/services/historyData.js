import { API_BASE_URL, getAuthHeaders } from './api';
import {
  getHistoryCacheToken,
  setHistoryCacheToken,
  getHistorySettings,
  getItem,
  setItem,
} from './localStorage';

const HISTORY_PAGE_SIZE = 1000;
const HISTORY_TICKER_BATCH = 100;
const HISTORY_CACHE_VERSION = 3;
const HISTORY_CACHE_VERSION_KEY = 'ui.history_cache_version';
const HISTORY_DEBUG_KEY = 'ui.history_debug';
const HISTORY_DEBUG_VERBOSE_KEY = 'ui.history_debug_verbose';

let cachedPayload = null;
let cachedToken = null;
let cachedSettings = null;
let inFlightPromise = null;
const updateListeners = new Set();

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

async function fetchAllTrades() {
  let page = 1;
  let total = 0;
  const rows = [];
  const debugVerbose = getItem(HISTORY_DEBUG_VERBOSE_KEY, false);

  while (page === 1 || rows.length < total) {
    const params = new URLSearchParams({
      page: String(page),
      pageSize: String(HISTORY_PAGE_SIZE),
    });
    const response = await fetch(
      `${API_BASE_URL}/history/trades?${params.toString()}`,
      { headers: await getAuthHeaders() }
    );
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      const errorMessage = errorData.detail || errorData.error?.message || `HTTP ${response.status}`;
      throw new Error(errorMessage);
    }
    const result = await response.json();
    total = result.total || 0;
    rows.push(...(result.data || []));
    if (debugVerbose) {
      // eslint-disable-next-line no-console
      console.log('[history-debug] fetched trades page', { page, total, rows: rows.length });
    }
    page += 1;
    if (result.data?.length === 0) {
      break;
    }
  }

  if (debugVerbose) {
    // eslint-disable-next-line no-console
    console.log('[history-debug] fetched trades complete', { total: rows.length });
  }
  return rows;
}

async function fetchHistoricalPrices(tickers) {
  const results = {};
  const debugVerbose = getItem(HISTORY_DEBUG_VERBOSE_KEY, false);
  for (let i = 0; i < tickers.length; i += HISTORY_TICKER_BATCH) {
    const batch = tickers.slice(i, i + HISTORY_TICKER_BATCH);
    const response = await fetch(`${API_BASE_URL}/history/historical-prices`, {
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
    if (debugVerbose) {
      // eslint-disable-next-line no-console
      console.log('[history-debug] fetched historical batch', { batchSize: batch.length, total: Object.keys(results).length });
    }
  }
  if (debugVerbose) {
    // eslint-disable-next-line no-console
    console.log('[history-debug] fetched historical complete', { total: Object.keys(results).length });
  }
  return results;
}

function buildDayKey(offset) {
  if (offset === 0) return 'd_0';
  return `d_pos${offset}`;
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

function computeHistoryRows(trades, tickerCache, settings) {
  const baseOffset = Number.isFinite(Number(settings.baseOffset)) ? Number(settings.baseOffset) : 0;
  const baseField = settings.baseField || 'open';
  const minThreshold = parseThreshold(settings.minThreshold);
  const maxThreshold = parseThreshold(settings.maxThreshold);
  const debugEnabled = getItem(HISTORY_DEBUG_KEY, false);

  return trades.map((trade) => {
    const ticker = trade.ticker;
    const tradeDate = trade.trade_date;
    const cache = tickerCache.get(ticker);
    const datesAsc = cache?.datesAsc || [];
    const indexByDate = cache?.indexByDate || new Map();
    const ohlcByDate = cache?.ohlcByDate || {};
    let tradeIndex = tradeDate && indexByDate.has(tradeDate) ? indexByDate.get(tradeDate) : -1;
    if (tradeIndex < 0) {
      tradeIndex = findNearestFutureIndex(datesAsc, tradeDate);
    }

    const dayOffsetTargetDates = {};
    const dayOffsetPriceTrend = {};
    const dayOffsetOpen = {};
    const dayOffsetHigh = {};
    const dayOffsetLow = {};
    const dayOffsetClose = {};
    const dayOffsetPerformance = {};

    let basePrice = null;
    if (tradeIndex >= 0 && datesAsc[tradeIndex + baseOffset]) {
      const baseDate = datesAsc[tradeIndex + baseOffset];
      const baseOhlc = ohlcByDate[baseDate];
      const baseValue = baseOhlc ? baseOhlc[baseField] : null;
      if (Number.isFinite(baseValue) && baseValue !== 0) {
        basePrice = baseValue;
      }
    }

    const positionMultiplier = getPositionMultiplier(trade.position);
    let stopOffset = null;
    let stopValueRaw = null;

    for (let offset = 0; offset <= 14; offset += 1) {
      const dayKey = buildDayKey(offset);
      const dateKey = tradeIndex >= 0 ? datesAsc[tradeIndex + offset] : null;
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

      const baseForOffset = offset === 0
        ? (Number.isFinite(open) && open !== 0 ? open : null)
        : basePrice;
      if (!baseForOffset) {
        dayOffsetPerformance[dayKey] = null;
        continue;
      }

      const perfCloseRaw = Number.isFinite(close)
        ? (close - baseForOffset) / baseForOffset
        : null;
      const perfOpenRaw = Number.isFinite(open)
        ? (open - baseForOffset) / baseForOffset
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
      const perfOpenDisplay = Number.isFinite(perfOpenRaw)
        ? perfOpenRaw * positionMultiplier
        : null;
      const perfHighDisplay = Number.isFinite(perfHighRaw)
        ? perfHighRaw * positionMultiplier
        : null;
      const perfLowDisplay = Number.isFinite(perfLowRaw)
        ? perfLowRaw * positionMultiplier
        : null;

      if (stopOffset === null) {
        const minProbe = positionMultiplier === -1 ? perfHighDisplay : perfLowDisplay;
        const maxProbe = positionMultiplier === -1 ? perfLowDisplay : perfHighDisplay;
        const closeProbe = perfCloseDisplay;
        const minCandidates = [minProbe, closeProbe].filter((value) => Number.isFinite(value));
        const maxCandidates = [maxProbe, closeProbe].filter((value) => Number.isFinite(value));
        const minCheck = minCandidates.length ? Math.min(...minCandidates) : null;
        const maxCheck = maxCandidates.length ? Math.max(...maxCandidates) : null;

        // Check MIN% (stop loss) FIRST per FR-007 clarification
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
        // Check MIN% (stop loss) FIRST per FR-007 clarification
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
      ...trade,
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

    for (let offset = 0; offset <= 14; offset += 1) {
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

    if (debugEnabled) {
      const sample = {
        ticker: row.ticker,
        trade_date: row.trade_date,
        position: row.position,
        baseOffset,
        baseField,
        minThreshold,
        maxThreshold,
        stopOffset: thresholdStop?.offset ?? null,
        stopThreshold: thresholdStop?.threshold ?? null,
        d0: row.d_0,
        d1: row.d_pos1,
        d2: row.d_pos2,
      };
      // eslint-disable-next-line no-console
      console.log('[history-debug]', sample);
    }

    return row;
  });
}

export function requestHistoryCacheRefresh() {
  const token = Date.now();
  setHistoryCacheToken(token);
  cachedPayload = null;
  cachedToken = null;
  cachedSettings = null;
  inFlightPromise = null;
  updateListeners.forEach((listener) => listener(token));
  return token;
}

export function subscribeHistoryCacheRefresh(listener) {
  updateListeners.add(listener);
  return () => updateListeners.delete(listener);
}

export function getCachedHistorySettings() {
  return cachedSettings;
}

export async function loadHistoryDataset() {
  const storedVersion = getItem(HISTORY_CACHE_VERSION_KEY, 0);
  if (storedVersion !== HISTORY_CACHE_VERSION) {
    setItem(HISTORY_CACHE_VERSION_KEY, HISTORY_CACHE_VERSION);
    requestHistoryCacheRefresh();
  }

  const token = getHistoryCacheToken();
  if (cachedPayload && cachedToken === token) {
    return cachedPayload;
  }
  if (inFlightPromise && cachedToken === token) {
    return inFlightPromise;
  }

  const settings = getHistorySettings();
  cachedToken = token;
  cachedSettings = settings;
  const tokenAtStart = token;
  const debugVerbose = getItem(HISTORY_DEBUG_VERBOSE_KEY, false);
  if (debugVerbose) {
    // eslint-disable-next-line no-console
    console.log('[history-debug] load start', { token: tokenAtStart, settings });
  }

  inFlightPromise = (async () => {
    const trades = await fetchAllTrades();
    const tickers = Array.from(new Set(trades.map((trade) => trade.ticker).filter(Boolean)));
    const historicalMap = await fetchHistoricalPrices(tickers);

    const tickerCache = new Map();
    tickers.forEach((ticker) => {
      const normalized = normalizeHistoricalPrice(historicalMap[ticker]);
      tickerCache.set(ticker, buildTickerCache(normalized));
    });

    const rows = computeHistoryRows(trades, tickerCache, settings);
    const payload = {
      rows,
      total: rows.length,
      settings,
      token: tokenAtStart,
    };
    if (getHistoryCacheToken() === tokenAtStart) {
      cachedPayload = payload;
    }
    if (debugVerbose) {
      // eslint-disable-next-line no-console
      console.log('[history-debug] load complete', { token: tokenAtStart, total: rows.length });
    }
    return payload;
  })();

  try {
    return await inFlightPromise;
  } finally {
    inFlightPromise = null;
  }
}
