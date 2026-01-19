/**
 * LocalStorage Service
 *
 * Handles persistence of UI state to localStorage following the design system contract.
 * Based on alsign/prompt/2_designSystem.ini persistence specifications.
 */

/**
 * Get an item from localStorage and parse it as JSON.
 *
 * @param {string} key - The localStorage key
 * @param {*} defaultValue - The default value if key doesn't exist or parsing fails
 * @returns {*} The parsed value or defaultValue
 */
export function getItem(key, defaultValue = null) {
  try {
    const item = localStorage.getItem(key);
    if (item === null) {
      return defaultValue;
    }
    return JSON.parse(item);
  } catch (error) {
    console.warn(`Failed to parse localStorage item "${key}":`, error);
    return defaultValue;
  }
}

/**
 * Set an item in localStorage by stringifying it as JSON.
 *
 * @param {string} key - The localStorage key
 * @param {*} value - The value to store (will be JSON stringified)
 */
export function setItem(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch (error) {
    console.error(`Failed to set localStorage item "${key}":`, error);
  }
}

/**
 * Remove an item from localStorage.
 *
 * @param {string} key - The localStorage key to remove
 */
export function removeItem(key) {
  try {
    localStorage.removeItem(key);
  } catch (error) {
    console.error(`Failed to remove localStorage item "${key}":`, error);
  }
}

/**
 * Clear all items from localStorage.
 */
export function clear() {
  try {
    localStorage.clear();
  } catch (error) {
    console.error('Failed to clear localStorage:', error);
  }
}

// ===== TABLE PERSISTENCE HELPERS =====

/**
 * Get selected columns for a table.
 *
 * @param {string} key - The persistence key (e.g., "ui.selected_columns")
 * @param {Array} defaultColumns - Default column keys to use if none persisted
 * @returns {Array} Array of selected column keys
 */
export function getSelectedColumns(key, defaultColumns = []) {
  return getItem(key, defaultColumns);
}

/**
 * Set selected columns for a table.
 *
 * @param {string} key - The persistence key (e.g., "ui.selected_columns")
 * @param {Array} columns - Array of selected column keys
 */
export function setSelectedColumns(key, columns) {
  setItem(key, columns);
}

/**
 * Get filters for a table.
 *
 * @param {string} key - The persistence key (e.g., "ui.events_filters")
 * @param {Object} defaultFilters - Default filters object
 * @returns {Object} Filters object where keys are column names and values are filter values
 */
export function getFilters(key, defaultFilters = {}) {
  return getItem(key, defaultFilters);
}

/**
 * Set filters for a table.
 *
 * @param {string} key - The persistence key (e.g., "ui.events_filters")
 * @param {Object} filters - Filters object
 */
export function setFilters(key, filters) {
  setItem(key, filters);
}

/**
 * Get sort configuration for a table.
 *
 * @param {string} key - The persistence key (e.g., "ui.events_sort")
 * @param {Object} defaultSort - Default sort config { key: null, direction: null }
 * @returns {Object} Sort config { key: string|null, direction: 'asc'|'desc'|null }
 */
export function getSort(key, defaultSort = { key: null, direction: null }) {
  return getItem(key, defaultSort);
}

/**
 * Set sort configuration for a table.
 *
 * @param {string} key - The persistence key (e.g., "ui.events_sort")
 * @param {Object} sort - Sort config { key: string|null, direction: 'asc'|'desc'|null }
 */
export function setSort(key, sort) {
  setItem(key, sort);
}

// ===== DATASET-SPECIFIC HELPERS =====

/**
 * Get persisted state for txn_events table.
 *
 * @returns {Object} { selectedColumns, filters, sort }
 */
export function getTxnEventsState() {
  return {
    selectedColumns: getSelectedColumns('ui.selected_columns', null),
    filters: getFilters('ui.events_filters', {}),
    sort: getSort('ui.events_sort', { key: null, direction: null }),
  };
}

/**
 * Set persisted state for txn_events table.
 *
 * @param {Object} state - { selectedColumns?, filters?, sort? }
 */
export function setTxnEventsState(state) {
  if (state.selectedColumns !== undefined) {
    setSelectedColumns('ui.selected_columns', state.selectedColumns);
  }
  if (state.filters !== undefined) {
    setFilters('ui.events_filters', state.filters);
  }
  if (state.sort !== undefined) {
    setSort('ui.events_sort', state.sort);
  }
}

/**
 * Get persisted state for dayoffset metrics table.
 *
 * @returns {Object} { selectedColumns, filters, sort }
 */
export function getDayOffsetState() {
  return {
    selectedColumns: getSelectedColumns('ui.dayoffset_columns', null),
    filters: getFilters('ui.dayoffset_filters', {}),
    sort: getSort('ui.dayoffset_sort', { key: null, direction: null }),
  };
}

/**
 * Set persisted state for dayoffset metrics table.
 *
 * @param {Object} state - { selectedColumns?, filters?, sort? }
 */
export function setDayOffsetState(state) {
  if (state.selectedColumns !== undefined) {
    setSelectedColumns('ui.dayoffset_columns', state.selectedColumns);
  }
  if (state.filters !== undefined) {
    setFilters('ui.dayoffset_filters', state.filters);
  }
  if (state.sort !== undefined) {
    setSort('ui.dayoffset_sort', state.sort);
  }
}

/**
 * Get persisted state for trades table.
 *
 * @returns {Object} { selectedColumns, filters, sort }
 */
export function getTradesState() {
  return {
    selectedColumns: getSelectedColumns('ui.trades_columns', null),
    filters: getFilters('ui.trades_filters', {}),
    sort: getSort('ui.trades_sort', { key: null, direction: null }),
    dayOffsetMode: getItem('ui.trades_day_offset_mode', 'performance'),
  };
}

/**
 * Set persisted state for trades table.
 *
 * @param {Object} state - { selectedColumns?, filters?, sort? }
 */
export function setTradesState(state) {
  if (state.selectedColumns !== undefined) {
    setSelectedColumns('ui.trades_columns', state.selectedColumns);
  }
  if (state.filters !== undefined) {
    setFilters('ui.trades_filters', state.filters);
  }
  if (state.sort !== undefined) {
    setSort('ui.trades_sort', state.sort);
  }
  if (state.dayOffsetMode !== undefined) {
    setItem('ui.trades_day_offset_mode', state.dayOffsetMode);
  }
}

// ===== HISTORY PAGE HELPERS =====

/**
 * Get history calculation settings.
 *
 * @returns {Object} { baseOffset, baseField, minThreshold, maxThreshold }
 */
export function getHistorySettings() {
  return getItem('ui.history_settings', {
    baseOffset: 0,
    baseField: 'close',
    minThreshold: null,
    maxThreshold: null,
  });
}

/**
 * Set history calculation settings.
 *
 * @param {Object} settings - { baseOffset?, baseField?, minThreshold?, maxThreshold? }
 */
export function setHistorySettings(settings) {
  const current = getHistorySettings();
  const updated = { ...current, ...settings };
  setItem('ui.history_settings', updated);
}

/**
 * Get events calculation settings.
 *
 * @returns {Object} { baseOffset, baseField, minThreshold, maxThreshold }
 */
export function getEventsSettings() {
  return getItem('ui.events_settings', {
    baseOffset: 0,
    baseField: 'close',
    minThreshold: null,
    maxThreshold: null,
    bestWindowMinConf: 95,
  });
}

/**
 * Set events calculation settings.
 *
 * @param {Object} settings - { baseOffset?, baseField?, minThreshold?, maxThreshold? }
 */
export function setEventsSettings(settings) {
  const current = getEventsSettings();
  const updated = { ...current, ...settings };
  setItem('ui.events_settings', updated);
}

/**
 * Get persisted state for history table.
 *
 * @returns {Object} { selectedColumns, filters, sort, dayOffsetMode }
 */
export function getHistoryState() {
  return {
    selectedColumns: getSelectedColumns('ui.history_columns', null),
    filters: getFilters('ui.history_filters', {}),
    sort: getSort('ui.history_sort', { key: 'trade_date', direction: 'desc' }),
    dayOffsetMode: getItem('ui.history_day_offset_mode', 'performance'),
  };
}

/**
 * Set persisted state for history table.
 *
 * @param {Object} state - { selectedColumns?, filters?, sort?, dayOffsetMode? }
 */
export function setHistoryState(state) {
  if (state.selectedColumns !== undefined) {
    setSelectedColumns('ui.history_columns', state.selectedColumns);
  }
  if (state.filters !== undefined) {
    setFilters('ui.history_filters', state.filters);
  }
  if (state.sort !== undefined) {
    setSort('ui.history_sort', state.sort);
  }
  if (state.dayOffsetMode !== undefined) {
    setItem('ui.history_day_offset_mode', state.dayOffsetMode);
  }
}

/**
 * Get persisted state for events history table.
 *
 * @returns {Object} { selectedColumns, filters, sort }
 */
export function getEventsHistoryState() {
  return {
    selectedColumns: getSelectedColumns('ui.events_history_columns', null),
    filters: getFilters('ui.events_history_filters', {}),
    sort: getSort('ui.events_history_sort', { key: 'event_date', direction: 'desc' }),
    dayOffsetMode: getItem('ui.events_history_day_offset_mode', 'performance_designated'),
  };
}

/**
 * Set persisted state for events history table.
 *
 * @param {Object} state - { selectedColumns?, filters?, sort? }
 */
export function setEventsHistoryState(state) {
  if (state.selectedColumns !== undefined) {
    setSelectedColumns('ui.events_history_columns', state.selectedColumns);
  }
  if (state.filters !== undefined) {
    setFilters('ui.events_history_filters', state.filters);
  }
  if (state.sort !== undefined) {
    setSort('ui.events_history_sort', state.sort);
  }
  if (state.dayOffsetMode !== undefined) {
    setItem('ui.events_history_day_offset_mode', state.dayOffsetMode);
  }
}

/**
 * Get history cache token for invalidation tracking.
 *
 * @returns {number} Timestamp or 0 if not set
 */
export function getHistoryCacheToken() {
  return getItem('ui.history_cache_token', 0);
}

/**
 * Set history cache token to trigger cache invalidation.
 *
 * @param {number} token - Timestamp (typically Date.now())
 */
export function setHistoryCacheToken(token) {
  setItem('ui.history_cache_token', token);
}
