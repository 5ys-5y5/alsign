/**
 * TradesTable Component
 *
 * Table component for displaying trades from txn_trades with price trend data.
 */

import React, { useEffect, useMemo, useState } from 'react';
import DataTable from '../table/DataTable';
import { getTradesState, setTradesState } from '../../services/localStorage';

const TRADES_COLUMNS = [
  { key: 'ticker', label: 'ticker', type: 'string', width: 110, isDefault: true },
  { key: 'trade_date', label: 'trade_date', type: 'daterange', width: 170, isDefault: true },
  { key: 'model', label: 'model', type: 'string', width: 140, isDefault: true },
  { key: 'source', label: 'source', type: 'string', width: 120, isDefault: true },
  { key: 'position', label: 'position', type: 'string', width: 110, isDefault: true },
  { key: 'wts', label: 'WTS', type: 'number', width: 80, isDefault: true },

  { key: 'd_neg14', label: 'D-14', type: 'dayoffset', width: 90, isDefault: true },
  { key: 'd_neg13', label: 'D-13', type: 'dayoffset', width: 90, isDefault: true },
  { key: 'd_neg12', label: 'D-12', type: 'dayoffset', width: 90, isDefault: true },
  { key: 'd_neg11', label: 'D-11', type: 'dayoffset', width: 90, isDefault: true },
  { key: 'd_neg10', label: 'D-10', type: 'dayoffset', width: 90, isDefault: true },
  { key: 'd_neg9', label: 'D-9', type: 'dayoffset', width: 90, isDefault: true },
  { key: 'd_neg8', label: 'D-8', type: 'dayoffset', width: 90, isDefault: true },
  { key: 'd_neg7', label: 'D-7', type: 'dayoffset', width: 90, isDefault: true },
  { key: 'd_neg6', label: 'D-6', type: 'dayoffset', width: 90, isDefault: true },
  { key: 'd_neg5', label: 'D-5', type: 'dayoffset', width: 90, isDefault: true },
  { key: 'd_neg4', label: 'D-4', type: 'dayoffset', width: 90, isDefault: true },
  { key: 'd_neg3', label: 'D-3', type: 'dayoffset', width: 90, isDefault: true },
  { key: 'd_neg2', label: 'D-2', type: 'dayoffset', width: 90, isDefault: true },
  { key: 'd_neg1', label: 'D-1', type: 'dayoffset', width: 90, isDefault: true },
  { key: 'd_0', label: 'D0', type: 'dayoffset', width: 90, isDefault: true },
  { key: 'd_pos1', label: 'D1', type: 'dayoffset', width: 90, isDefault: true },
  { key: 'd_pos2', label: 'D2', type: 'dayoffset', width: 90, isDefault: true },
  { key: 'd_pos3', label: 'D3', type: 'dayoffset', width: 90, isDefault: true },
  { key: 'd_pos4', label: 'D4', type: 'dayoffset', width: 90, isDefault: true },
  { key: 'd_pos5', label: 'D5', type: 'dayoffset', width: 90, isDefault: true },
  { key: 'd_pos6', label: 'D6', type: 'dayoffset', width: 90, isDefault: true },
  { key: 'd_pos7', label: 'D7', type: 'dayoffset', width: 90, isDefault: true },
  { key: 'd_pos8', label: 'D8', type: 'dayoffset', width: 90, isDefault: true },
  { key: 'd_pos9', label: 'D9', type: 'dayoffset', width: 90, isDefault: true },
  { key: 'd_pos10', label: 'D10', type: 'dayoffset', width: 90, isDefault: true },
  { key: 'd_pos11', label: 'D11', type: 'dayoffset', width: 90, isDefault: true },
  { key: 'd_pos12', label: 'D12', type: 'dayoffset', width: 90, isDefault: true },
  { key: 'd_pos13', label: 'D13', type: 'dayoffset', width: 90, isDefault: true },
  { key: 'd_pos14', label: 'D14', type: 'dayoffset', width: 90, isDefault: true },

  { key: 'notes', label: 'notes', type: 'string', width: 220, isDefault: false },
];

/**
 * TradesTable component.
 */
export default function TradesTable({
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
  onDayOffsetModeChange,
}) {
  const allowedColumns = useMemo(() => new Set(TRADES_COLUMNS.map((col) => col.key)), []);
  const [selectedColumns, setSelectedColumns] = useState(() => {
    const persisted = getTradesState();
    const defaults = TRADES_COLUMNS.filter((col) => col.isDefault).map((col) => col.key);
    if (!persisted.selectedColumns) {
      return defaults;
    }
    return persisted.selectedColumns.filter((col) => allowedColumns.has(col));
  });

  useEffect(() => {
    setTradesState({ selectedColumns });
  }, [selectedColumns]);

  const rowClassName = useMemo(() => {
    return (row) => (row?.is_blurred ? 'row-blurred' : '');
  }, []);

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-3)' }}>
        <h2 style={{ margin: 0 }}>Trades</h2>
        {onDayOffsetModeChange ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
            <label style={{ fontSize: 'var(--text-sm)', fontWeight: 'var(--font-medium)', whiteSpace: 'nowrap' }}>
              mode:
            </label>
            <select
              value={dayOffsetMode}
              onChange={(e) => onDayOffsetModeChange(e.target.value)}
              style={{ padding: 'var(--space-1)', borderRadius: 'var(--rounded-lg)', border: '1px solid var(--border)' }}
            >
              <option value="performance">%</option>
              <option value="price_trend">N</option>
            </select>
          </div>
        ) : null}
      </div>

      <DataTable
        data={data}
        columns={TRADES_COLUMNS}
        selectedColumns={selectedColumns}
        onSelectedColumnsChange={setSelectedColumns}
        filters={filters}
        onFiltersChange={onFiltersChange}
        sortConfig={sortConfig}
        onSortChange={onSortChange}
        loading={loading}
        dayOffsetMode={dayOffsetMode}
        enableRowExpand={false}
        enableCheckboxes={false}
        enableFooterStats={true}
        enableServerSideSort={true}
        enableServerSideFilter={true}
        getRowClassName={rowClassName}
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
          Showing {((page - 1) * pageSize) + 1} to {Math.min(page * pageSize, total)} of {total.toLocaleString()} trades
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
              disabled={page === 1}
              style={{ minWidth: '32px' }}
            >
              бьбь
            </button>
            <button
              className="btn btn-sm btn-outline"
              onClick={() => onPageChange(page - 1)}
              disabled={page === 1}
              style={{ minWidth: '32px' }}
            >
              ?
            </button>

            <div style={{
              padding: '0 var(--space-2)',
              display: 'flex',
              alignItems: 'center',
              fontSize: 'var(--text-sm)',
              whiteSpace: 'nowrap'
            }}>
              Page {page} / {Math.ceil(total / pageSize)}
            </div>

            <button
              className="btn btn-sm btn-outline"
              onClick={() => onPageChange(page + 1)}
              disabled={page >= Math.ceil(total / pageSize)}
              style={{ minWidth: '32px' }}
            >
              ?
            </button>
            <button
              className="btn btn-sm btn-outline"
              onClick={() => onPageChange(Math.ceil(total / pageSize))}
              disabled={page >= Math.ceil(total / pageSize)}
              style={{ minWidth: '32px' }}
            >
              бэбэ
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
