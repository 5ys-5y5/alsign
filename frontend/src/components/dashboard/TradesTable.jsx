/**
 * TradesTable Component
 *
 * Table component for displaying trades from txn_trades with price trend data.
 */

import React, { useState, useMemo } from 'react';
import DataTable from '../table/DataTable';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

/**
 * Format percentage for display.
 */
function formatPercent(value) {
  if (value === null || value === undefined) return 'N/A';
  const percent = value * 100;
  const sign = percent >= 0 ? '+' : '';
  return `${sign}${percent.toFixed(2)}%`;
}

/**
 * Format number with 2 decimal places.
 */
function formatNumber(value) {
  if (value === null || value === undefined) return 'N/A';
  return Number(value).toFixed(2);
}

/**
 * TradesTable component.
 */
export default function TradesTable({
  data,
  loading,
  total,
  page,
  pageSize,
  onPageChange,
  onPageSizeChange,
  sortConfig,
  onSortChange,
  filters,
  onFiltersChange,
  onRefresh,
}) {
  // Define columns once using useMemo
  const columns = useMemo(() => {
    const cols = [
      {
        key: 'ticker',
        label: 'Ticker',
        type: 'string',
        width: 100,
        isDefault: true,
      },
      {
        key: 'trade_date',
        label: 'Trade Date',
        type: 'date',
        width: 120,
        isDefault: true,
      },
      {
        key: 'model',
        label: 'Model',
        type: 'string',
        width: 120,
        isDefault: true,
      },
      {
        key: 'source',
        label: 'Source',
        type: 'string',
        width: 100,
        isDefault: true,
      },
      {
        key: 'position',
        label: 'Position',
        type: 'string',
        width: 100,
        isDefault: true,
      },
      {
        key: 'entry_price',
        label: 'Entry Price',
        type: 'number',
        width: 110,
        isDefault: true,
      },
      {
        key: 'exit_price',
        label: 'Exit Price',
        type: 'number',
        width: 110,
        isDefault: true,
      },
      {
        key: 'quantity',
        label: 'Qty',
        type: 'number',
        width: 80,
        isDefault: true,
      },
      {
        key: 'wts',
        label: 'WTS',
        type: 'number',
        width: 70,
        isDefault: true,
      },
    ];

    // Add day offset columns (D-14 to D14, excluding D0)
    for (let offset = -14; offset <= 14; offset++) {
      if (offset === 0) continue;
      const key = offset < 0 ? `d_neg${Math.abs(offset)}` : `d_pos${offset}`;
      const label = `D${offset > 0 ? '+' : ''}${offset}`;
      cols.push({
        key,
        label,
        type: 'dayoffset',
        width: 80,
        isDefault: true,
      });
    }

    // Add notes column at the end
    cols.push({
      key: 'notes',
      label: 'Notes',
      type: 'string',
      width: 200,
      isDefault: false,
    });

    return cols;
  }, []);

  // Initialize selected columns state - all columns by default
  const [selectedColumns, setSelectedColumns] = useState(() => {
    return columns.filter((col) => col.isDefault).map((col) => col.key);
  });

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-3)' }}>
        <h2 style={{ margin: 0 }}>Trades</h2>
      </div>

      <DataTable
        data={data}
        columns={columns}
        selectedColumns={selectedColumns}
        onSelectedColumnsChange={setSelectedColumns}
        filters={filters}
        onFiltersChange={onFiltersChange}
        sortConfig={sortConfig}
        onSortChange={onSortChange}
        loading={loading}
        enableRowExpand={false}
        enableCheckboxes={false}
        enableFooterStats={false}
        enableServerSideSort={false}
        enableServerSideFilter={false}
      />
    </div>
  );
}
