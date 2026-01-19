/**
 * DataTable Component
 *
 * Reusable data table with column selection, filtering, sorting, and persistence.
 * Implements the complete table system from alsign/prompt/2_designSystem.ini
 */

import React, { useState, useEffect, useMemo } from 'react';
import ColumnSelector from './ColumnSelector';
import FilterPopover from './FilterPopover';
import SortHeader from './SortHeader';

/**
 * Render a cell value based on its type and column configuration.
 *
 * @param {*} value - The cell value
 * @param {Object} column - Column configuration
 * @returns {JSX.Element|string} Rendered cell content
 */
function renderCellValue(value, column, row, dayOffsetMode) {
  if (row?.is_blurred) {
    return <span className="cell-locked">Locked</span>;
  }

  // Handle null/undefined
  if (value === null || value === undefined || value === '') {
    return <span className="cell-null">-</span>;
  }

  // Handle position enum (long/short/undefined)
  if (column.key.startsWith('position_')) {
    const positionValue = value.toLowerCase();
    if (positionValue === 'long') {
      return <span className="badge badge-long">long</span>;
    } else if (positionValue === 'short') {
      return <span className="badge badge-short">short</span>;
    } else {
      return <span className="badge badge-undefined">{value}</span>;
    }
  }

  // Handle dates
  if (column.type === 'date') {
    return value; // Already formatted as YYYY-MM-DD from backend
  }

  // Handle numbers (including disparities as percentages)
  if (column.type === 'number') {
    if (column.key.includes('disparity')) {
      // Render as percentage
      const percentage = (value * 100).toFixed(2);
      return `${percentage}%`;
    }
    return value.toLocaleString();
  }

  // Handle day offset columns (D-14 to D14)
  if (column.type === 'dayoffset') {
    const arrowUp = '▲';
    const arrowDown = '▼';
    const numValue = Number(value);
    if (!Number.isFinite(numValue)) {
      return <span className="cell-null">-</span>;
    }

    if (dayOffsetMode === 'price_trend') {
      const displayValue = numValue;
      const baseValueRaw = Number(row?.d_neg14);
      const baseValue = Number.isFinite(baseValueRaw) ? baseValueRaw : null;
      const hasBase = Number.isFinite(baseValue);
      const isBaseColumn = column.key === 'd_neg14';

      let arrow = '';
      let colorClass = '';
      if (hasBase && !isBaseColumn) {
        if (displayValue > baseValue) {
          arrow = arrowUp;
          colorClass = 'text-red';
        } else if (displayValue < baseValue) {
          arrow = arrowDown;
          colorClass = 'text-blue';
        }
      }

      return (
        <span className={colorClass}>
          {arrow} {displayValue.toLocaleString(undefined, { maximumFractionDigits: 2 })}
        </span>
      );
    }
    const position = row?.position ? String(row.position).toLowerCase() : '';
    const positionMultiplier = position === 'short' ? -1 : 1;
    const displayValue = numValue * positionMultiplier;
    const percentage = (displayValue * 100).toFixed(2);
    const arrow = displayValue > 0 ? arrowUp : displayValue < 0 ? arrowDown : '';
    const colorClass = displayValue > 0 ? 'text-red' : displayValue < 0 ? 'text-blue' : '';
    return (
      <span className={colorClass}>
        {arrow} {percentage}%
      </span>
    );
  }

  // Handle JSON fields - DO NOT EXPAND
  if (
    column.key === 'value_quantitative' ||
    column.key === 'value_qualitative' ||
    column.key === 'price_trend' ||
    column.key === 'analyst_performance' ||
    column.key === 'response_key'
  ) {
    return <span className="text-xs text-dim">json</span>;
  }

  // Handle long text with truncation
  if (typeof value === 'string' && value.length > 50) {
    return (
      <span className="cell-truncate" title={value}>
        {value}
      </span>
    );
  }

  // Default: render as string
  return String(value);
}

function formatNumber(value) {
  if (!Number.isFinite(value)) {
    return '-';
  }
  return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function parseDayOffsetKey(key) {
  if (key === 'd_0') return 0;
  if (key.startsWith('d_neg')) {
    const raw = Number(key.replace('d_neg', ''));
    return Number.isFinite(raw) ? -raw : null;
  }
  if (key.startsWith('d_pos')) {
    const raw = Number(key.replace('d_pos', ''));
    return Number.isFinite(raw) ? raw : null;
  }
  return null;
}

function buildDayOffsetKey(offset) {
  if (offset === 0) return 'd_0';
  if (offset > 0) return `d_pos${offset}`;
  return `d_neg${Math.abs(offset)}`;
}

function isPerformanceMode(dayOffsetMode) {
  return Boolean(dayOffsetMode) && String(dayOffsetMode).startsWith('performance');
}

function getPerformanceMap(row, dayOffsetMode) {
  if (!row) return null;
  if (dayOffsetMode === 'performance_previous') {
    return row.day_offset_performance_previous || row.day_offset_performance || null;
  }
  return row.day_offset_performance || null;
}

function getDayOffsetValue(row, columnKey, dayOffsetMode) {
  if (isPerformanceMode(dayOffsetMode)) {
    const performanceMap = getPerformanceMap(row, dayOffsetMode);
    if (performanceMap && Object.prototype.hasOwnProperty.call(performanceMap, columnKey)) {
      return performanceMap[columnKey];
    }
  }
  return row ? row[columnKey] : null;
}

function getDayOffsetTooltipContent(
  row,
  column,
  dayOffsetMode,
  baseOffset = 0,
  baseField = 'close',
  minThreshold = null,
  maxThreshold = null
) {
  if (!row || row.is_blurred) {
    return null;
  }

  const targetDates = row.day_offset_target_dates;

  // Build base day key from settings
  const baseDayKey = baseOffset === 0
    ? 'd_0'
    : (baseOffset > 0 ? `d_pos${baseOffset}` : `d_neg${Math.abs(baseOffset)}`);
  const baseLabel = (() => {
    if (baseOffset === 0) return `D0 ${baseField}`;
    const signed = baseOffset > 0 ? `+${baseOffset}` : `${baseOffset}`;
    return `D${signed} ${baseField}`;
  })();

  // Get the correct OHLC map based on baseField setting
  const ohlcMapKey = `day_offset_price_trend_${baseField}`;
  const ohlcMap = row[ohlcMapKey];

  if (dayOffsetMode !== 'performance_previous' && isPerformanceMode(dayOffsetMode)) {
    // Get base price from the configured baseOffset and baseField
    const baseValue = ohlcMap ? Number(ohlcMap[baseDayKey]) : null;
    const baseDate = targetDates ? targetDates[baseDayKey] : null;

    const openMap = row.day_offset_price_trend_open;
    const highMap = row.day_offset_price_trend_high;
    const lowMap = row.day_offset_price_trend_low;
    const closeMap = row.day_offset_price_trend_close;

    const currentLabel = column.label || column.key;
    const currentOpen = openMap ? Number(openMap[column.key]) : null;
    const currentHigh = highMap ? Number(highMap[column.key]) : null;
    const currentLow = lowMap ? Number(lowMap[column.key]) : null;
    const currentClose = closeMap ? Number(closeMap[column.key]) : null;

    const performanceMap = getPerformanceMap(row, dayOffsetMode);
    const rawValue = performanceMap ? Number(performanceMap[column.key]) : null;
    const position = row?.position ? String(row.position).toLowerCase() : '';
    const positionMultiplier = position === 'short' ? -1 : 1;
    const displayValue = Number.isFinite(rawValue) ? rawValue * positionMultiplier : null;
    const minNorm = minThreshold !== null ? minThreshold / 100 : null;
    const maxNorm = maxThreshold !== null ? maxThreshold / 100 : null;
    const tolerance = 0.0001;

    let usedField = 'close';
    if (Number.isFinite(displayValue)) {
      if (minNorm !== null && Math.abs(displayValue - minNorm) < tolerance) {
        usedField = positionMultiplier === -1 ? 'high' : 'low';
      } else if (maxNorm !== null && Math.abs(displayValue - maxNorm) < tolerance) {
        usedField = positionMultiplier === -1 ? 'low' : 'high';
      }
    }

    const dimStyle = { color: '#d1d5db' };
    const activeStyle = { color: '#111827' };

    return (
      <div>
        {baseDate ? <div>기준일: {baseDate}</div> : null}
        <div style={{ marginTop: '6px' }}>
          <div>
            <span style={usedField === 'open' ? activeStyle : dimStyle}>
              {currentLabel} open: {formatNumber(currentOpen)}
            </span>
          </div>
          <div>
            <span style={usedField === 'high' ? activeStyle : dimStyle}>
              {currentLabel} high: {formatNumber(currentHigh)}
            </span>
          </div>
          <div>
            <span style={usedField === 'low' ? activeStyle : dimStyle}>
              {currentLabel} low: {formatNumber(currentLow)}
            </span>
          </div>
          <div>
            <span style={usedField === 'close' ? activeStyle : dimStyle}>
              {currentLabel} close: {formatNumber(currentClose)}
            </span>
          </div>
        </div>
        <div style={{ borderTop: '1px solid #e5e7eb', margin: '8px 0' }} />
        <div>
          <span style={activeStyle}>{baseLabel}: {formatNumber(baseValue)}</span>
        </div>
      </div>
    );
  }

  if (dayOffsetMode === 'performance_previous') {
    const performanceMap = getPerformanceMap(row, dayOffsetMode);
    if (!performanceMap) {
      return null;
    }
    const offset = parseDayOffsetKey(column.key);
    const prevOffset = Number.isFinite(offset) ? offset - 1 : null;
    const prevKey = Number.isFinite(prevOffset) ? buildDayOffsetKey(prevOffset) : null;
    const prevClose = prevKey && row.day_offset_price_trend_close
      ? Number(row.day_offset_price_trend_close[prevKey])
      : null;
    const fallbackBase = row.day_offset_price_trend_open
      ? Number(row.day_offset_price_trend_open[column.key])
      : null;
    const previousBase = Number.isFinite(prevClose) ? prevClose : fallbackBase;
    const currentLabel = column.label || column.key;
    const currentOpen = row.day_offset_price_trend_open ? Number(row.day_offset_price_trend_open[column.key]) : null;
    const currentHigh = row.day_offset_price_trend_high ? Number(row.day_offset_price_trend_high[column.key]) : null;
    const currentLow = row.day_offset_price_trend_low ? Number(row.day_offset_price_trend_low[column.key]) : null;
    const currentClose = row.day_offset_price_trend_close ? Number(row.day_offset_price_trend_close[column.key]) : null;
    const rawValue = Number(performanceMap[column.key]);
    const position = row?.position ? String(row.position).toLowerCase() : '';
    const positionMultiplier = position === 'short' ? -1 : 1;
    const displayValue = Number.isFinite(rawValue) ? rawValue * positionMultiplier : null;
    const dimStyle = { color: '#d1d5db' };
    const activeStyle = { color: '#111827' };

    return (
      <div>
        {targetDates && targetDates[column.key] ? <div>기준일: {targetDates[column.key]}</div> : null}
        <div style={{ marginTop: '6px' }}>
          <div>
            <span style={baseField === 'open' ? activeStyle : dimStyle}>
              {currentLabel} open: {formatNumber(currentOpen)}
            </span>
          </div>
          <div>
            <span style={baseField === 'high' ? activeStyle : dimStyle}>
              {currentLabel} high: {formatNumber(currentHigh)}
            </span>
          </div>
          <div>
            <span style={baseField === 'low' ? activeStyle : dimStyle}>
              {currentLabel} low: {formatNumber(currentLow)}
            </span>
          </div>
          <div>
            <span style={baseField === 'close' ? activeStyle : dimStyle}>
              {currentLabel} close: {formatNumber(currentClose)}
            </span>
          </div>
        </div>
        <div style={{ borderTop: '1px solid #e5e7eb', margin: '8px 0' }} />
        <div>
          <span style={activeStyle}>Prev close: {formatNumber(previousBase)}</span>
        </div>
        <div>
          <span style={activeStyle}>Current close: {formatNumber(currentClose)}</span>
        </div>
        <div>
          <span style={activeStyle}>
            Return: {Number.isFinite(displayValue) ? `${(displayValue * 100).toFixed(2)}%` : '-'}
          </span>
        </div>
      </div>
    );
  }

  const performanceMap = getPerformanceMap(row, dayOffsetMode);
  if (!performanceMap) {
    return null;
  }
  const rawValue = Number(performanceMap[column.key]);
  if (!Number.isFinite(rawValue)) {
    return null;
  }
  const position = row?.position ? String(row.position).toLowerCase() : '';
  const positionMultiplier = position === 'short' ? -1 : 1;
  const displayValue = rawValue * positionMultiplier;
  const label = column.label || column.key;
  const lines = [];
  lines.push(`${label} %: ${(displayValue * 100).toFixed(2)}%`);
  return lines.join('\n');
}

function applyFilters(data, filters, columns, dayOffsetMode) {
  return data.filter((row) => {
    return Object.entries(filters).every(([columnKey, filterValue]) => {
      if (!filterValue) return true;

      const column = columns.find((col) => col.key === columnKey);
      if (!column) return true;

      const cellValue = column.type === 'dayoffset'
        ? getDayOffsetValue(row, columnKey, dayOffsetMode)
        : row[columnKey];

      // Handle null values
      if (cellValue === null || cellValue === undefined) {
        return false;
      }

      // String filter: case-insensitive contains
      if (column.type === 'string') {
        return String(cellValue).toLowerCase().includes(filterValue.toLowerCase());
      }

      // Date filter: contains (for yyyy-MM-dd format)
      if (column.type === 'date') {
        return String(cellValue).includes(filterValue);
      }

      // Number filter: min-max, >min, <max, or exact value
      if (column.type === 'number' || column.type === 'dayoffset') {
        const numValue = Number(cellValue);
        const filterStr = filterValue.trim();

        // Range: min-max
        if (filterStr.includes('-')) {
          const [min, max] = filterStr.split('-').map((v) => parseFloat(v.trim()));
          return numValue >= (min || -Infinity) && numValue <= (max || Infinity);
        }

        // Greater than: >min
        if (filterStr.startsWith('>')) {
          const min = parseFloat(filterStr.substring(1));
          return numValue > min;
        }

        // Less than: <max
        if (filterStr.startsWith('<')) {
          const max = parseFloat(filterStr.substring(1));
          return numValue < max;
        }

        // Exact value
        const exactValue = parseFloat(filterStr);
        return !isNaN(exactValue) && numValue === exactValue;
      }

      // Enum filter: exact match
      if (column.type === 'enum') {
        return cellValue === filterValue;
      }

      return true;
    });
  });
}

/**
 * Apply sorting to data rows.
 *
 * @param {Array} data - Array of data rows
 * @param {Object} sortConfig - Sort config { key: string|null, direction: 'asc'|'desc'|null }
 * @param {Array} columns - Column configurations
 * @returns {Array} Sorted data rows
 */
function applySort(data, sortConfig, columns, dayOffsetMode) {
  if (!sortConfig.key || !sortConfig.direction) {
    return data;
  }

  const column = columns.find((col) => col.key === sortConfig.key);
  if (!column) return data;

  return [...data].sort((a, b) => {
    const aVal = column.type === 'dayoffset'
      ? getDayOffsetValue(a, sortConfig.key, dayOffsetMode)
      : a[sortConfig.key];
    const bVal = column.type === 'dayoffset'
      ? getDayOffsetValue(b, sortConfig.key, dayOffsetMode)
      : b[sortConfig.key];

    // Handle null/undefined: always last (asc), always first (desc)
    if (aVal === null || aVal === undefined) {
      return sortConfig.direction === 'asc' ? 1 : -1;
    }
    if (bVal === null || bVal === undefined) {
      return sortConfig.direction === 'asc' ? -1 : 1;
    }

    // Date comparison
    if (column.type === 'date') {
      const aDate = new Date(aVal);
      const bDate = new Date(bVal);
      return sortConfig.direction === 'asc' ? aDate - bDate : bDate - aDate;
    }

    // Number comparison
    if (column.type === 'number' || column.type === 'dayoffset') {
      return sortConfig.direction === 'asc' ? aVal - bVal : bVal - aVal;
    }

    // String comparison
    const comparison = String(aVal).localeCompare(String(bVal));
    return sortConfig.direction === 'asc' ? comparison : -comparison;
  });
}

/**
 * DataTable component with full table system features.
 *
 * @param {Object} props - Component props
 * @param {Array} props.data - Data rows to display
 * @param {Array} props.columns - Column definitions [{ key, label, type, width, isDefault }]
 * @param {Array} props.selectedColumns - Currently selected column keys
 * @param {Function} props.onSelectedColumnsChange - Callback when selected columns change
 * @param {Object} props.filters - Active filters { columnKey: filterValue }
 * @param {Function} props.onFiltersChange - Callback when filters change
 * @param {Object} props.sortConfig - Sort configuration { key, direction }
 * @param {Function} props.onSortChange - Callback when sort changes
 * @param {boolean} [props.loading] - Loading state
 * @param {boolean} [props.enableRowExpand] - Enable row expand on click
 * @param {boolean} [props.enableCheckboxes] - Enable row selection with checkboxes
 * @param {boolean} [props.enableFooterStats] - Enable footer statistics row
 * @param {boolean} [props.enableServerSideSort] - If true, skip client-side sorting (data is already sorted by server)
 * @param {boolean} [props.enableServerSideFilter] - If true, skip client-side filtering (data is already filtered by server)
 * @param {Function} [props.onSelectionChange] - Callback when row selection changes (receives Set of row IDs)
 * @param {React.ReactNode} [props.toolbarContent] - Optional toolbar content rendered below the default toolbar row
 * @returns {JSX.Element} Data table component
 */
export default function DataTable({
  data,
  columns,
  selectedColumns,
  onSelectedColumnsChange,
  filters,
  onFiltersChange,
  sortConfig,
  onSortChange,
  loading = false,
  enableRowExpand = false,
  enableCheckboxes = false,
  enableFooterStats = false,
  enableServerSideSort = false,
  enableServerSideFilter = false,
  onSelectionChange,
  getRowClassName,
  dayOffsetMode = 'performance',
  minThreshold = null,
  maxThreshold = null,
  baseOffset = 0,
  baseField = 'close',
  toolbarContent = null,
  toolbarActions = null,
  toolbarRightActions = null,
  hideColumnSelector = false,
  enableToolbarToggle = false,
  toolbarToggleLabel = 'Filters',
  defaultToolbarOpen = false,
}) {
  // Track expanded rows
  const [expandedRows, setExpandedRows] = useState(new Set());

  // Track selected rows (for checkboxes)
  const [selectedRows, setSelectedRows] = useState(new Set());
  const [hoverTooltip, setHoverTooltip] = useState({ visible: false, x: 0, y: 0, content: '' });
  const [toolbarOpen, setToolbarOpen] = useState(defaultToolbarOpen);

  // Notify parent when selection changes
  useEffect(() => {
    if (onSelectionChange) {
      onSelectionChange(selectedRows);
    }
  }, [selectedRows, onSelectionChange]);
  // Determine visible columns
  const visibleColumns = useMemo(() => {
    const columnMap = new Map(columns.map((col) => [col.key, col]));
    return selectedColumns.map((key) => columnMap.get(key)).filter(Boolean);
  }, [columns, selectedColumns]);

  // Apply filters and sorting
  const processedData = useMemo(() => {
    let result = data;
    // Only apply client-side filtering if server-side filtering is not enabled
    if (!enableServerSideFilter) {
      result = applyFilters(result, filters, columns, dayOffsetMode);
    }
    // Only apply client-side sorting if server-side sorting is not enabled
    if (!enableServerSideSort) {
      result = applySort(result, sortConfig, columns, dayOffsetMode);
    }
    return result;
  }, [data, filters, sortConfig, columns, enableServerSideSort, enableServerSideFilter, dayOffsetMode]);

  // Handle sort click: null → asc → desc → null
  const handleSort = (columnKey) => {
    if (sortConfig.key !== columnKey) {
      // Start new sort: asc
      onSortChange({ key: columnKey, direction: 'asc' });
    } else if (sortConfig.direction === 'asc') {
      // Change to desc
      onSortChange({ key: columnKey, direction: 'desc' });
    } else {
      // Clear sort
      onSortChange({ key: null, direction: null });
    }
  };

  // Handle filter change for a column
  const handleFilterChange = (columnKey, value) => {
    onFiltersChange({
      ...filters,
      [columnKey]: value,
    });
  };

  // Handle filter reset for a column
  const handleFilterReset = (columnKey) => {
    const newFilters = { ...filters };
    delete newFilters[columnKey];
    onFiltersChange(newFilters);
  };

  // Handle row expand toggle
  const toggleRowExpand = (rowId) => {
    const newExpanded = new Set(expandedRows);
    if (newExpanded.has(rowId)) {
      newExpanded.delete(rowId);
    } else {
      newExpanded.add(rowId);
    }
    setExpandedRows(newExpanded);
  };

  // Handle checkbox toggle
  const toggleRowSelect = (rowId) => {
    const newSelected = new Set(selectedRows);
    if (newSelected.has(rowId)) {
      newSelected.delete(rowId);
    } else {
      newSelected.add(rowId);
    }
    setSelectedRows(newSelected);
  };

  // Handle select all toggle
  const toggleSelectAll = () => {
    if (selectedRows.size === processedData.length) {
      // Deselect all
      setSelectedRows(new Set());
    } else {
      // Select all
      const allIds = processedData.map((row) => row.id);
      setSelectedRows(new Set(allIds));
    }
  };

  const handleDayOffsetMove = (event, row, column) => {
    const content = getDayOffsetTooltipContent(
      row,
      column,
      dayOffsetMode,
      baseOffset,
      baseField,
      minThreshold,
      maxThreshold
    );
    if (!content) {
      if (hoverTooltip.visible) {
        setHoverTooltip((prev) => ({ ...prev, visible: false }));
      }
      return;
    }
    setHoverTooltip({
      visible: true,
      x: event.clientX + 12,
      y: event.clientY + 12,
      content,
    });
  };

  const handleDayOffsetLeave = () => {
    if (hoverTooltip.visible) {
      setHoverTooltip((prev) => ({ ...prev, visible: false }));
    }
  };

  // Calculate footer statistics
  const calculateFooterStats = (columnKey, column) => {
    if (!enableFooterStats) return null;

    const values = processedData.map((row) => row[columnKey]).filter((v) => v !== null && v !== undefined);

    if (values.length === 0) return '-';

    switch (columnKey) {
      case 'ticker':
        // Row count
        return `${processedData.length} rows`;

      case 'event_date':
        // Min ~ Max
        const dates = values.map((d) => new Date(d));
        const minDate = new Date(Math.min(...dates)).toISOString().split('T')[0];
        const maxDate = new Date(Math.max(...dates)).toISOString().split('T')[0];
        return `${minDate} ~ ${maxDate}`;

      case 'source':
      case 'sector':
      case 'industry':
      case 'condition':
        // Distinct count
        return `${new Set(values).size} distinct`;

      case 'disparity_quantitative':
      case 'disparity_qualitative':
        // Average
        const avg = values.reduce((sum, v) => sum + Number(v), 0) / values.length;
        return `avg: ${(avg * 100).toFixed(2)}%`;

      case 'wts':
        // Average of each Dk, then find k with max average
        // This requires access to all D-14~D14 columns
        const dayOffsets = {};
        for (let offset = -14; offset <= 14; offset++) {
          if (offset === 0) continue;
          const key = offset < 0 ? `d_neg${Math.abs(offset)}` : `d_pos${offset}`;
          const dayValues = processedData
            .map((row) => getDayOffsetValue(row, key, dayOffsetMode))
            .filter((v) => v !== null && v !== undefined)
            .map((v) => Number(v));
          if (dayValues.length > 0) {
            dayOffsets[offset] = dayValues.reduce((sum, v) => sum + v, 0) / dayValues.length;
          }
        }
        let maxAvg = -Infinity;
        let maxOffset = null;
        for (const [offset, avg] of Object.entries(dayOffsets)) {
          if (avg > maxAvg) {
            maxAvg = avg;
            maxOffset = Number(offset);
          }
        }
        return maxOffset !== null ? `D${maxOffset > 0 ? '+' : ''}${maxOffset}` : '-';

      default:
        // For day offset columns (d_neg14 ~ d_pos14), show average
        if (column.type === 'dayoffset') {
          if (!isPerformanceMode(dayOffsetMode)) {
            return '-';
          }
          const adjustedValues = processedData
            .map((row) => {
              const raw = getDayOffsetValue(row, columnKey, dayOffsetMode);
              if (raw === null || raw === undefined) {
                return null;
              }
              const rawValue = Number(raw);
              if (!Number.isFinite(rawValue)) {
                return null;
              }
              const position = row?.position ? String(row.position).toLowerCase() : '';
              const positionMultiplier = position === 'short' ? -1 : 1;
              return rawValue * positionMultiplier;
            })
            .filter((v) => v !== null);
          if (adjustedValues.length === 0) {
            return '-';
          }
          const avg = adjustedValues.reduce((sum, v) => sum + v, 0) / adjustedValues.length;
          return `avg: ${(avg * 100).toFixed(2)}%`;
        }
        return '-';
    }
  };

  const hasToolbarContent = Boolean(toolbarContent);
  const showToolbarToggle = enableToolbarToggle && hasToolbarContent;
  const toolbarLabel = toolbarToggleLabel || 'Filters';

  return (
    <div className="table-shell">
      {/* Toolbar - Always visible at top */}
      <div className={`table-toolbar${hasToolbarContent ? ' table-toolbar--stacked' : ''}`}>
        <div className="table-toolbar__row">
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            {!hideColumnSelector ? (
              <ColumnSelector
                allColumns={columns}
                selectedColumns={selectedColumns}
                onChange={onSelectedColumnsChange}
              />
            ) : null}
            {showToolbarToggle ? (
              <button
                type="button"
                className="btn btn-sm btn-outline"
                onClick={() => setToolbarOpen((prev) => !prev)}
                aria-expanded={toolbarOpen}
              >
                <svg
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                >
                  <circle cx="12" cy="12" r="3" />
                  <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33h0a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51h0a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82v0a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
                </svg>
                {toolbarLabel}
              </button>
            ) : null}
            {toolbarActions}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-dim)' }}>
              {processedData.length} {processedData.length === 1 ? 'row' : 'rows'}
              {data.length !== processedData.length && ` (filtered from ${data.length})`}
            </div>
            {toolbarRightActions}
          </div>
        </div>
        {hasToolbarContent && (!showToolbarToggle || toolbarOpen) ? (
          <div className="table-toolbar__row table-toolbar__row--extras">
            {toolbarContent}
          </div>
        ) : null}
      </div>

      {/* Scrollable Table Container with sticky header */}
      <div className="table-scroll-container">
        {loading ? (
          <div className="loading">Loading...</div>
        ) : (
          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  {enableCheckboxes && (
                    <th style={{ width: '50px' }}>
                      <input
                        type="checkbox"
                        checked={selectedRows.size === processedData.length && processedData.length > 0}
                        onChange={toggleSelectAll}
                      />
                    </th>
                  )}
                  {visibleColumns.map((column) => (
                    <SortHeader
                      key={column.key}
                      columnKey={column.key}
                      label={column.label}
                      sortConfig={sortConfig}
                      onSort={handleSort}
                    >
                      <FilterPopover
                        columnKey={column.key}
                        columnLabel={column.label}
                        filterType={column.type}
                        enumOptions={column.enumOptions || []}
                        value={filters[column.key] || ''}
                        onChange={(value) => handleFilterChange(column.key, value)}
                        onReset={() => handleFilterReset(column.key)}
                      />
                    </SortHeader>
                  ))}
                </tr>
              </thead>
              <tbody>
                {processedData.length === 0 ? (
                  <tr>
                    <td
                      colSpan={visibleColumns.length + (enableCheckboxes ? 1 : 0)}
                      style={{
                        textAlign: 'center',
                        padding: 'var(--space-4)',
                        color: 'var(--text-dim)'
                      }}
                    >
                      No data to display
                    </td>
                  </tr>
                ) : (
                  processedData.map((row, rowIndex) => {
                  const isExpanded = expandedRows.has(row.id);
                  const isSelected = selectedRows.has(row.id);
                  const rowClassName = getRowClassName ? getRowClassName(row) : '';

                  return (
                    <React.Fragment key={row.id || rowIndex}>
                      <tr
                        onClick={() => enableRowExpand && toggleRowExpand(row.id)}
                        className={rowClassName}
                        style={{ cursor: enableRowExpand ? 'pointer' : 'default' }}
                      >
                        {enableCheckboxes && (
                          <td onClick={(e) => e.stopPropagation()}>
                            <input
                              type="checkbox"
                              checked={isSelected}
                              onChange={() => toggleRowSelect(row.id)}
                            />
                          </td>
                        )}
                        {visibleColumns.map((column) => {
                          const cellValue = column.type === 'dayoffset'
                            ? getDayOffsetValue(row, column.key, dayOffsetMode)
                            : row[column.key];
                          // Check for threshold breach on dayoffset columns
                          let thresholdStyle = null;
                          if (column.type === 'dayoffset' && dayOffsetMode !== 'performance_previous' && isPerformanceMode(dayOffsetMode)) {
                            const rawValue = Number(cellValue);
                            if (Number.isFinite(rawValue)) {
                              const position = row?.position ? String(row.position).toLowerCase() : '';
                              const positionMultiplier = position === 'short' ? -1 : 1;
                              const displayValue = rawValue * positionMultiplier;
                              const minNorm = minThreshold !== null ? minThreshold / 100 : null;
                              const maxNorm = maxThreshold !== null ? maxThreshold / 100 : null;
                              const tolerance = 0.0001;
                              if (minNorm !== null && Math.abs(displayValue - minNorm) < tolerance) {
                                thresholdStyle = { backgroundColor: 'rgba(59, 130, 246, 0.15)', fontWeight: 600 };
                              } else if (maxNorm !== null && Math.abs(displayValue - maxNorm) < tolerance) {
                                thresholdStyle = { backgroundColor: 'rgba(239, 68, 68, 0.15)', fontWeight: 600 };
                              }
                            }
                          }
                          return (
                            <td
                              key={column.key}
                              style={{
                                width: column.width ? `${column.width}px` : 'auto',
                                ...thresholdStyle,
                              }}
                            >
                              {column.render ? (
                                column.render({
                                  value: cellValue,
                                  row,
                                  column,
                                })
                              ) : column.type === 'dayoffset' ? (
                                <span
                                  onMouseMove={(event) => handleDayOffsetMove(event, row, column)}
                                  onMouseLeave={handleDayOffsetLeave}
                                >
                                  {renderCellValue(cellValue, column, row, dayOffsetMode)}
                                </span>
                              ) : (
                                renderCellValue(cellValue, column, row, dayOffsetMode)
                              )}
                            </td>
                          );
                        })}
                      </tr>
                      {isExpanded && (
                        <tr className={`expanded-row ${rowClassName}`}>
                          <td colSpan={visibleColumns.length + (enableCheckboxes ? 1 : 0)}>
                            <div style={{ padding: 'var(--space-3)', backgroundColor: 'var(--surface)' }}>
                              <h4 style={{ marginBottom: 'var(--space-2)', fontWeight: 'var(--font-semibold)' }}>
                                Full Details
                              </h4>
                              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 'var(--space-2)' }}>
                                {columns.map((column) => (
                                  <div key={column.key} style={{ fontSize: 'var(--text-sm)' }}>
                                    <strong>{column.label}:</strong>{' '}
                                    {column.render
                                      ? column.render({
                                        value: column.type === 'dayoffset'
                                          ? getDayOffsetValue(row, column.key, dayOffsetMode)
                                          : row[column.key],
                                        row,
                                        column,
                                      })
                                      : renderCellValue(
                                        column.type === 'dayoffset'
                                          ? getDayOffsetValue(row, column.key, dayOffsetMode)
                                          : row[column.key],
                                        column,
                                        row,
                                        dayOffsetMode
                                      )}
                                  </div>
                                ))}
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })
                )}
              </tbody>
              {enableFooterStats && !loading && (
                <tfoot>
                  <tr>
                    {enableCheckboxes && <td style={{ width: '50px' }}></td>}
                    {visibleColumns.map((column) => (
                      <td
                        key={column.key}
                        style={{
                          width: column.width ? `${column.width}px` : 'auto',
                        }}
                        title={calculateFooterStats(column.key, column)}
                      >
                        {calculateFooterStats(column.key, column)}
                      </td>
                    ))}
                  </tr>
                </tfoot>
              )}
            </table>
          </div>
        )}
      </div>
      {hoverTooltip.visible && (
        <div
          style={{
            position: 'fixed',
            left: hoverTooltip.x,
            top: hoverTooltip.y,
            backgroundColor: 'white',
            border: '1px solid var(--border)',
            borderRadius: 'var(--rounded-lg)',
            padding: 'var(--space-2)',
            fontSize: 'var(--text-sm)',
            color: 'var(--text)',
            boxShadow: 'var(--shadow-md)',
            pointerEvents: 'none',
            whiteSpace: typeof hoverTooltip.content === 'string' ? 'pre' : 'normal',
            zIndex: 1000,
          }}
        >
          {hoverTooltip.content}
        </div>
      )}
    </div>
  );
}

