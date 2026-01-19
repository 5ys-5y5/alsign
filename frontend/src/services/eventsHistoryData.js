import { API_BASE_URL, getAuthHeaders } from './api';
import { supabase } from './supabaseClient';
import {
  getItem,
  setItem,
  getEventsSettings,
} from './localStorage';

const EVENTS_HISTORY_PAGE_SIZE = 100000;
const EVENTS_HISTORY_CACHE_VERSION = 1;
const EVENTS_HISTORY_CACHE_VERSION_KEY = 'ui.events_history_cache_version';
const EVENTS_HISTORY_CACHE_TOKEN_KEY = 'ui.events_history_cache_token';

let cachedPayload = null;
let cachedToken = null;
let cachedSettings = null;
let cachedFiltersKey = null;
let cachedSettingsKey = null;
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

function buildEventsParams(page, pageSize, filters, settings) {
  const params = new URLSearchParams({
    page: String(page),
    pageSize: String(pageSize),
    baseOffset: String(settings?.baseOffset ?? 0),
    baseField: String(settings?.baseField ?? 'close'),
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
  if (settings?.minThreshold !== null && settings?.minThreshold !== undefined) {
    params.append('minThreshold', String(settings.minThreshold));
  }
  if (settings?.maxThreshold !== null && settings?.maxThreshold !== undefined) {
    params.append('maxThreshold', String(settings.maxThreshold));
  }
  return params;
}

async function fetchEventsPage(page, pageSize, filters) {
  const params = buildEventsParams(page, pageSize, filters, getEventsSettings());
  const response = await fetchWithAuthRetry(
    `${API_BASE_URL}/dashboard/eventsHistory?${params.toString()}`,
    { headers: await getAuthHeaders() }
  );
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    const errorMessage = errorData.detail || errorData.error?.message || `HTTP ${response.status}`;
    throw new Error(errorMessage);
  }
  return response.json();
}

export function requestEventsHistoryCacheRefresh({ preserveData = false } = {}) {
  const token = Date.now();
  setItem(EVENTS_HISTORY_CACHE_TOKEN_KEY, token);
  cachedPayload = null;
  cachedToken = null;
  cachedSettings = null;
  cachedFiltersKey = null;
  cachedSettingsKey = null;
  cachedDataFiltersKey = null;
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

export async function loadEventsHistoryBestWindow(filters = null, feePercent = 0) {
  const settings = getEventsSettings();
  const params = buildEventsParams(1, 1, filters, settings);
  params.append('feePercent', String(feePercent || 0));
  const response = await fetchWithAuthRetry(
    `${API_BASE_URL}/dashboard/eventsHistory/bestWindow?${params.toString()}`,
    { headers: await getAuthHeaders() }
  );
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    const errorMessage = errorData.detail || errorData.error?.message || `HTTP ${response.status}`;
    throw new Error(errorMessage);
  }
  return response.json();
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
    const result = await fetchEventsPage(1, EVENTS_HISTORY_PAGE_SIZE, filters);
    const rows = result.data || [];
    const payload = {
      rows,
      total: result.total || rows.length,
      settings,
      token: tokenAtStart,
    };
    cachedPayload = payload;
    cachedDataFiltersKey = filtersKey;
    emitProgress({
      stage: 'complete',
      processed: rows.length,
      total: rows.length,
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
