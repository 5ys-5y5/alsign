/**
 * EventsHistoryTable Component
 *
 * Table component for displaying events history calculations.
 */

import React, { useEffect, useMemo, useState } from 'react';
import DataTable from '../table/DataTable';
import { getEventsHistoryState, setEventsHistoryState } from '../../services/localStorage';

const EVENTS_HISTORY_COLUMNS = [
  { key: 'ticker', label: 'ticker', type: 'string', width: 110, isDefault: true },
  { key: 'event_date', label: 'event_date', type: 'daterange', width: 170, isDefault: true },
  { key: 'source', label: 'source', type: 'string', width: 140, isDefault: true },
  { key: 'sector', label: 'sector', type: 'string', width: 180, isDefault: false },
  { key: 'industry', label: 'industry', type: 'string', width: 200, isDefault: false },
  {
    key: 'position_quantitative',
    label: 'pos(Q)',
    type: 'enum',
    width: 110,
    isDefault: true,
    enumOptions: ['long', 'short', 'undefined'],
  },
  {
    key: 'position_qualitative',
    label: 'pos(QL)',
    type: 'enum',
    width: 110,
    isDefault: false,
    enumOptions: ['long', 'short', 'undefined'],
  },
  { key: 'condition', label: 'condition', type: 'string', width: 140, isDefault: false },
  { key: 'wts', label: 'WTS', type: 'number', width: 80, isDefault: true },

  { key: 'd_neg14', label: 'D-14', type: 'dayoffset', width: 90, isDefault: false },
  { key: 'd_neg13', label: 'D-13', type: 'dayoffset', width: 90, isDefault: false },
  { key: 'd_neg12', label: 'D-12', type: 'dayoffset', width: 90, isDefault: false },
  { key: 'd_neg11', label: 'D-11', type: 'dayoffset', width: 90, isDefault: false },
  { key: 'd_neg10', label: 'D-10', type: 'dayoffset', width: 90, isDefault: false },
  { key: 'd_neg9', label: 'D-9', type: 'dayoffset', width: 90, isDefault: false },
  { key: 'd_neg8', label: 'D-8', type: 'dayoffset', width: 90, isDefault: false },
  { key: 'd_neg7', label: 'D-7', type: 'dayoffset', width: 90, isDefault: false },
  { key: 'd_neg6', label: 'D-6', type: 'dayoffset', width: 90, isDefault: false },
  { key: 'd_neg5', label: 'D-5', type: 'dayoffset', width: 90, isDefault: false },
  { key: 'd_neg4', label: 'D-4', type: 'dayoffset', width: 90, isDefault: false },
  { key: 'd_neg3', label: 'D-3', type: 'dayoffset', width: 90, isDefault: false },
  { key: 'd_neg2', label: 'D-2', type: 'dayoffset', width: 90, isDefault: false },
  { key: 'd_neg1', label: 'D-1', type: 'dayoffset', width: 90, isDefault: false },
  { key: 'd_0', label: 'D0', type: 'dayoffset', width: 90, isDefault: true },
  { key: 'd_pos1', label: 'D1', type: 'dayoffset', width: 90, isDefault: false },
  { key: 'd_pos2', label: 'D2', type: 'dayoffset', width: 90, isDefault: false },
  { key: 'd_pos3', label: 'D3', type: 'dayoffset', width: 90, isDefault: false },
  { key: 'd_pos4', label: 'D4', type: 'dayoffset', width: 90, isDefault: false },
  { key: 'd_pos5', label: 'D5', type: 'dayoffset', width: 90, isDefault: false },
  { key: 'd_pos6', label: 'D6', type: 'dayoffset', width: 90, isDefault: false },
  { key: 'd_pos7', label: 'D7', type: 'dayoffset', width: 90, isDefault: false },
  { key: 'd_pos8', label: 'D8', type: 'dayoffset', width: 90, isDefault: false },
  { key: 'd_pos9', label: 'D9', type: 'dayoffset', width: 90, isDefault: false },
  { key: 'd_pos10', label: 'D10', type: 'dayoffset', width: 90, isDefault: false },
  { key: 'd_pos11', label: 'D11', type: 'dayoffset', width: 90, isDefault: false },
  { key: 'd_pos12', label: 'D12', type: 'dayoffset', width: 90, isDefault: false },
  { key: 'd_pos13', label: 'D13', type: 'dayoffset', width: 90, isDefault: false },
  { key: 'd_pos14', label: 'D14', type: 'dayoffset', width: 90, isDefault: false },
];

const COMPACT_COLUMNS = [
  'ticker',
  'event_date',
  'source',
  'position_quantitative',
  'wts',
  'd_0',
];

function getDayOffsetValue(row, columnKey, dayOffsetMode) {
  if (dayOffsetMode === 'performance_previous') {
    return row.day_offset_performance_previous?.[columnKey] ?? null;
  }
  if (String(dayOffsetMode).startsWith('performance')) {
    return row.day_offset_performance?.[columnKey] ?? null;
  }
  return row[columnKey];
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

      if (column.type === 'daterange') {
        const from = filterValue?.from;
        const to = filterValue?.to;
        if (!from && !to) {
          return true;
        }
        if (!cellValue) {
          return false;
        }
        if (from && String(cellValue) < String(from)) {
          return false;
        }
        if (to && String(cellValue) > String(to)) {
          return false;
        }
        return true;
      }

      if (cellValue === null || cellValue === undefined) {
        return false;
      }

      if (column.type === 'string') {
        const rawValue = String(filterValue).trim();
        if (rawValue.startsWith('=')) {
          return String(cellValue).toLowerCase() === rawValue.slice(1).toLowerCase();
        }
        return String(cellValue).toLowerCase().includes(rawValue.toLowerCase());
      }

      if (column.type === 'date') {
        return String(cellValue).includes(filterValue);
      }

      if (column.type === 'number' || column.type === 'dayoffset') {
        const numValue = Number(cellValue);
        const filterStr = String(filterValue).trim();

        if (filterStr.includes('-')) {
          const [min, max] = filterStr.split('-').map((v) => parseFloat(v.trim()));
          return numValue >= (min || -Infinity) && numValue <= (max || Infinity);
        }
        if (filterStr.startsWith('>')) {
          const min = parseFloat(filterStr.substring(1));
          return numValue > min;
        }
        if (filterStr.startsWith('<')) {
          const max = parseFloat(filterStr.substring(1));
          return numValue < max;
        }
        const exactValue = parseFloat(filterStr);
        return !Number.isNaN(exactValue) && numValue === exactValue;
      }

      if (column.type === 'enum') {
        return cellValue === filterValue;
      }

      return true;
    });
  });
}

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

    if (aVal === null || aVal === undefined) {
      return sortConfig.direction === 'asc' ? 1 : -1;
    }
    if (bVal === null || bVal === undefined) {
      return sortConfig.direction === 'asc' ? -1 : 1;
    }

    if (column.type === 'date' || column.type === 'daterange') {
      const aDate = new Date(aVal);
      const bDate = new Date(bVal);
      return sortConfig.direction === 'asc' ? aDate - bDate : bDate - aDate;
    }

    if (column.type === 'number' || column.type === 'dayoffset') {
      return sortConfig.direction === 'asc' ? aVal - bVal : bVal - aVal;
    }

    const comparison = String(aVal).localeCompare(String(bVal));
    return sortConfig.direction === 'asc' ? comparison : -comparison;
  });
}

export default function EventsHistoryTable({
  data,
  loading = false,
  total = 0,
  page = 1,
  pageSize = 100,
  onPageChange,
  onPageSizeChange,
  sortConfig,
  onSortChange,
  filters,
  onFiltersChange,
  dayOffsetMode = 'performance_designated',
  onDayOffsetModeChange,
  onReload,
  minThreshold = null,
  maxThreshold = null,
  baseOffset = 0,
  baseField = 'close',
  toolbarContent = null,
}) {
  const allowedColumns = useMemo(() => new Set(EVENTS_HISTORY_COLUMNS.map((col) => col.key)), []);
  const [selectedColumns, setSelectedColumns] = useState(() => {
    const persisted = getEventsHistoryState();
    const defaults = EVENTS_HISTORY_COLUMNS.filter((col) => col.isDefault).map((col) => col.key);
    if (!persisted.selectedColumns) {
      return defaults;
    }
    return persisted.selectedColumns.filter((col) => allowedColumns.has(col));
  });
  const [isCompact, setIsCompact] = useState(() => {
    if (typeof window === 'undefined') return false;
    return window.matchMedia('(max-width: 900px)').matches;
  });

  useEffect(() => {
    if (typeof window === 'undefined') return undefined;
    const mediaQuery = window.matchMedia('(max-width: 900px)');
    const handleChange = (event) => setIsCompact(event.matches);
    if (mediaQuery.addEventListener) {
      mediaQuery.addEventListener('change', handleChange);
    } else {
      mediaQuery.addListener(handleChange);
    }
    return () => {
      if (mediaQuery.removeEventListener) {
        mediaQuery.removeEventListener('change', handleChange);
      } else {
        mediaQuery.removeListener(handleChange);
      }
    };
  }, []);

  useEffect(() => {
    setEventsHistoryState({ selectedColumns });
  }, [selectedColumns]);

  const processedData = useMemo(() => {
    const filtered = applyFilters(data, filters, EVENTS_HISTORY_COLUMNS, dayOffsetMode);
    return applySort(filtered, sortConfig, EVENTS_HISTORY_COLUMNS, dayOffsetMode);
  }, [data, filters, sortConfig, dayOffsetMode]);

  const totalPages = Math.max(1, Math.ceil(processedData.length / pageSize));
  const safePage = Math.min(page, totalPages);
  const startIndex = (safePage - 1) * pageSize;
  const pageData = processedData.slice(startIndex, startIndex + pageSize);

  useEffect(() => {
    if (page !== safePage) {
      onPageChange(safePage);
    }
  }, [page, safePage, onPageChange]);

  const compactColumns = useMemo(
    () => COMPACT_COLUMNS.filter((key) => allowedColumns.has(key)),
    [allowedColumns]
  );
  const displayColumns = isCompact ? compactColumns : selectedColumns;
  const modeLabel = dayOffsetMode === 'performance_previous' ? 'Previous day' : 'Designated date';
  const nextMode = dayOffsetMode === 'performance_previous' ? 'performance_designated' : 'performance_previous';
  const reloadButton = onReload ? (
    <button
      type="button"
      className="btn btn-sm btn-outline"
      onClick={onReload}
      disabled={loading}
      aria-label="Reload"
      title="Reload"
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
        <path d="M3 12a9 9 0 0 1 15.54-6.36" />
        <polyline points="18 3 18 9 12 9" />
        <path d="M21 12a9 9 0 0 1-15.54 6.36" />
        <polyline points="6 21 6 15 12 15" />
      </svg>
    </button>
  ) : null;

  return (
    <div>
      <DataTable
        data={pageData}
        columns={EVENTS_HISTORY_COLUMNS}
        selectedColumns={displayColumns}
        onSelectedColumnsChange={setSelectedColumns}
        filters={filters}
        onFiltersChange={onFiltersChange}
        sortConfig={sortConfig}
        onSortChange={onSortChange}
        loading={loading}
        toolbarContent={toolbarContent}
        toolbarActions={onDayOffsetModeChange ? (
          <button
            type="button"
            className="btn btn-sm btn-outline"
            onClick={() => onDayOffsetModeChange(nextMode)}
            title={`Mode: ${modeLabel}`}
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
              <path d="M3 12a9 9 0 0 1 15.54-6.36" />
              <polyline points="18 3 18 9 12 9" />
              <path d="M21 12a9 9 0 0 1-15.54 6.36" />
              <polyline points="6 21 6 15 12 15" />
            </svg>
            Mode: {modeLabel}
          </button>
        ) : null}
        toolbarRightActions={reloadButton}
        dayOffsetMode={dayOffsetMode}
        minThreshold={minThreshold}
        maxThreshold={maxThreshold}
        baseOffset={baseOffset}
        baseField={baseField}
        enableRowExpand={isCompact}
        enableCheckboxes={false}
        enableFooterStats={true}
        enableServerSideSort={true}
        enableServerSideFilter={true}
        hideColumnSelector={isCompact}
        enableToolbarToggle={true}
        toolbarToggleLabel="Settings"
        defaultToolbarOpen={false}
      />

      <div style={{
        marginTop: 'var(--space-3)',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: 'var(--space-2)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--rounded-lg)',
        backgroundColor: 'white',
        flexWrap: 'wrap',
        gap: 'var(--space-2)'
      }}>
        <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-dim)', whiteSpace: 'nowrap' }}>
          Showing {startIndex + 1} to {Math.min(startIndex + pageSize, processedData.length)} of {processedData.length.toLocaleString()} rows
        </div>

        <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center', flexWrap: 'nowrap' }}>
          <label style={{ fontSize: 'var(--text-sm)', fontWeight: 'var(--font-medium)', whiteSpace: 'nowrap' }}>
            Rows:
          </label>
          <select
            value={pageSize}
            onChange={(e) => onPageSizeChange(Number(e.target.value))}
            style={{ padding: 'var(--space-1)', borderRadius: 'var(--rounded-lg)', border: '1px solid var(--border)' }}
          >
            <option value={50}>50</option>
            <option value={100}>100</option>
            <option value={200}>200</option>
            <option value={500}>500</option>
            <option value={1000}>1000</option>
            <option value={5000}>5000</option>
            <option value={10000}>10000</option>
            <option value={50000}>50000</option>
            <option value={100000}>100000</option>
          </select>

          <div style={{ display: 'flex', gap: 'var(--space-1)' }}>
            <button
              className="btn btn-sm btn-outline"
              onClick={() => onPageChange(1)}
              disabled={safePage === 1}
              style={{ minWidth: '32px' }}
            >
              {'<<'}
            </button>
            <button
              className="btn btn-sm btn-outline"
              onClick={() => onPageChange(safePage - 1)}
              disabled={safePage === 1}
              style={{ minWidth: '32px' }}
            >
              {'<'}
            </button>

            <div style={{
              padding: '0 var(--space-2)',
              display: 'flex',
              alignItems: 'center',
              fontSize: 'var(--text-sm)',
              whiteSpace: 'nowrap'
            }}>
              Page {safePage} / {totalPages}
            </div>

            <button
              className="btn btn-sm btn-outline"
              onClick={() => onPageChange(safePage + 1)}
              disabled={safePage >= totalPages}
              style={{ minWidth: '32px' }}
            >
              {'>'}
            </button>
            <button
              className="btn btn-sm btn-outline"
              onClick={() => onPageChange(totalPages)}
              disabled={safePage >= totalPages}
              style={{ minWidth: '32px' }}
            >
              {'>>'}
            </button>
          </div>
        </div>
      </div>

      {!loading && total === 0 ? (
        <div className="alert alert-warning" style={{ marginTop: 'var(--space-3)' }}>
          No events data available.
        </div>
      ) : null}
    </div>
  );
}
