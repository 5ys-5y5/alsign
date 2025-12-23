/**
 * PerformanceTable Component
 *
 * Table for displaying txn_events performance summary.
 * Uses DataTable with specific column configuration and persistence for txn_events dataset.
 */

import React, { useState, useEffect } from 'react';
import DataTable from '../table/DataTable';
import { getTxnEventsState, setTxnEventsState } from '../../services/localStorage';

/**
 * Column catalog for txn_events (performance summary)
 * Based on design system mapping: dataset.txn_events.column_catalog
 */
const PERFORMANCE_COLUMNS = [
  { key: 'ticker', label: 'ticker', type: 'string', width: 110, isDefault: true },
  { key: 'event_date', label: 'event_date', type: 'date', width: 160, isDefault: true },
  { key: 'source', label: 'source', type: 'string', width: 140, isDefault: true },
  { key: 'sector', label: 'sector', type: 'string', width: 180, isDefault: true },
  { key: 'industry', label: 'industry', type: 'string', width: 200, isDefault: true },
  {
    key: 'position_quantitative',
    label: 'pos(Q)',
    type: 'enum',
    width: 110,
    isDefault: true,
    enumOptions: ['long', 'short', 'undefined'],
  },
  {
    key: 'disparity_quantitative',
    label: 'disp(Q)',
    type: 'number',
    width: 110,
    isDefault: true,
  },
  {
    key: 'position_qualitative',
    label: 'pos(QL)',
    type: 'enum',
    width: 110,
    isDefault: true,
    enumOptions: ['long', 'short', 'undefined'],
  },
  {
    key: 'disparity_qualitative',
    label: 'disp(QL)',
    type: 'number',
    width: 110,
    isDefault: true,
  },
  { key: 'condition', label: 'condition', type: 'string', width: 140, isDefault: true },
  // Additional columns (not default)
  { key: 'id', label: 'id', type: 'number', width: 80, isDefault: false },
  { key: 'source_id', label: 'source_id', type: 'string', width: 120, isDefault: false },
];

/**
 * PerformanceTable component for displaying txn_events.
 *
 * @param {Object} props - Component props
 * @param {Array} props.data - Performance data rows from txn_events
 * @param {boolean} [props.loading] - Loading state
 * @returns {JSX.Element} Performance table component
 */
export default function PerformanceTable({ data, loading = false }) {
  // Initialize state from localStorage or defaults
  const [selectedColumns, setSelectedColumns] = useState(() => {
    const persisted = getTxnEventsState();
    return (
      persisted.selectedColumns ||
      PERFORMANCE_COLUMNS.filter((col) => col.isDefault).map((col) => col.key)
    );
  });

  const [filters, setFilters] = useState(() => {
    const persisted = getTxnEventsState();
    return persisted.filters || {};
  });

  const [sortConfig, setSortConfig] = useState(() => {
    const persisted = getTxnEventsState();
    return persisted.sort || { key: null, direction: null };
  });

  // Persist state changes to localStorage
  useEffect(() => {
    setTxnEventsState({ selectedColumns });
  }, [selectedColumns]);

  useEffect(() => {
    setTxnEventsState({ filters });
  }, [filters]);

  useEffect(() => {
    setTxnEventsState({ sort: sortConfig });
  }, [sortConfig]);

  return (
    <div>
      <h2 style={{ marginBottom: 'var(--space-3)' }}>Performance Summary</h2>
      <DataTable
        data={data}
        columns={PERFORMANCE_COLUMNS}
        selectedColumns={selectedColumns}
        onSelectedColumnsChange={setSelectedColumns}
        filters={filters}
        onFiltersChange={setFilters}
        sortConfig={sortConfig}
        onSortChange={setSortConfig}
        loading={loading}
      />
    </div>
  );
}
