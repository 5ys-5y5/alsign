/**
 * HistoryTable Component
 *
 * Table component for displaying history calculations from cached data.
 */

import React, { useEffect, useMemo, useState } from 'react';
import DataTable from '../table/DataTable';
import { getHistoryState, setHistoryState } from '../../services/localStorage';
import { TRADES_COLUMNS } from './tradesColumns';

function applyFilters(data, filters, columns) {
  return data.filter((row) => {
    return Object.entries(filters).every(([columnKey, filterValue]) => {
      if (!filterValue) return true;

      const column = columns.find((col) => col.key === columnKey);
      if (!column) return true;

      const cellValue = row[columnKey];

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

function applySort(data, sortConfig, columns) {
  if (!sortConfig.key || !sortConfig.direction) {
    return data;
  }

  const column = columns.find((col) => col.key === sortConfig.key);
  if (!column) return data;

  return [...data].sort((a, b) => {
    const aVal = a[sortConfig.key];
    const bVal = b[sortConfig.key];

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

export default function HistoryTable({
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
  dayOffsetMode = 'performance',
  minThreshold = null,
  maxThreshold = null,
  baseOffset = 0,
  baseField = 'close',
}) {
  const allowedColumns = useMemo(() => new Set(TRADES_COLUMNS.map((col) => col.key)), []);
  const [selectedColumns, setSelectedColumns] = useState(() => {
    const persisted = getHistoryState();
    const defaults = TRADES_COLUMNS.filter((col) => col.isDefault).map((col) => col.key);
    if (!persisted.selectedColumns) {
      return defaults;
    }
    return persisted.selectedColumns.filter((col) => allowedColumns.has(col));
  });

  useEffect(() => {
    setHistoryState({ selectedColumns });
  }, [selectedColumns]);

  const processedData = useMemo(() => {
    const filtered = applyFilters(data, filters, TRADES_COLUMNS);
    return applySort(filtered, sortConfig, TRADES_COLUMNS);
  }, [data, filters, sortConfig]);

  const totalPages = Math.max(1, Math.ceil(processedData.length / pageSize));
  const safePage = Math.min(page, totalPages);
  const startIndex = (safePage - 1) * pageSize;
  const pageData = processedData.slice(startIndex, startIndex + pageSize);

  useEffect(() => {
    if (page !== safePage) {
      onPageChange(safePage);
    }
  }, [page, safePage, onPageChange]);

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-3)' }}>
        <h2 style={{ margin: 0 }}>History</h2>
      </div>

      <DataTable
        data={pageData}
        columns={TRADES_COLUMNS}
        selectedColumns={selectedColumns}
        onSelectedColumnsChange={setSelectedColumns}
        filters={filters}
        onFiltersChange={onFiltersChange}
        sortConfig={sortConfig}
        onSortChange={onSortChange}
        loading={loading}
        dayOffsetMode={dayOffsetMode}
        minThreshold={minThreshold}
        maxThreshold={maxThreshold}
        baseOffset={baseOffset}
        baseField={baseField}
        enableRowExpand={false}
        enableCheckboxes={false}
        enableFooterStats={true}
        enableServerSideSort={true}
        enableServerSideFilter={true}
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
          No history data available.
        </div>
      ) : null}
    </div>
  );
}
