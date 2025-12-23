/**
 * DayOffsetTable Component
 *
 * Table for displaying day-offset performance metrics.
 * Uses DataTable with specific column configuration and persistence for dashboard_dayoffset_metrics dataset.
 */

import React, { useState, useEffect } from 'react';
import DataTable from '../table/DataTable';
import { getDayOffsetState, setDayOffsetState } from '../../services/localStorage';

/**
 * Column catalog for dashboard_dayoffset_metrics
 * Based on design system mapping: dataset.dashboard_dayoffset_metrics.column_catalog
 */
const DAYOFFSET_COLUMNS = [
  { key: 'group_by', label: 'group_by', type: 'string', width: 140, isDefault: true },
  { key: 'group_value', label: 'group_value', type: 'string', width: 220, isDefault: true },
  { key: 'dayOffset', label: 'D+N', type: 'number', width: 90, isDefault: true },
  { key: 'sample_count', label: 'count', type: 'number', width: 90, isDefault: true },
  { key: 'return_mean', label: 'mean', type: 'number', width: 110, isDefault: true },
  { key: 'return_median', label: 'median', type: 'number', width: 110, isDefault: true },
  // Additional columns
  { key: 'row_id', label: 'row_id', type: 'string', width: 200, isDefault: false },
];

/**
 * DayOffsetTable component for displaying day-offset metrics.
 *
 * @param {Object} props - Component props
 * @param {Array} props.data - Day-offset metrics data rows
 * @param {boolean} [props.loading] - Loading state
 * @returns {JSX.Element} Day-offset table component
 */
export default function DayOffsetTable({ data, loading = false }) {
  // Initialize state from localStorage or defaults
  const [selectedColumns, setSelectedColumns] = useState(() => {
    const persisted = getDayOffsetState();
    return (
      persisted.selectedColumns ||
      DAYOFFSET_COLUMNS.filter((col) => col.isDefault).map((col) => col.key)
    );
  });

  const [filters, setFilters] = useState(() => {
    const persisted = getDayOffsetState();
    return persisted.filters || {};
  });

  const [sortConfig, setSortConfig] = useState(() => {
    const persisted = getDayOffsetState();
    return persisted.sort || { key: null, direction: null };
  });

  // Persist state changes to localStorage
  useEffect(() => {
    setDayOffsetState({ selectedColumns });
  }, [selectedColumns]);

  useEffect(() => {
    setDayOffsetState({ filters });
  }, [filters]);

  useEffect(() => {
    setDayOffsetState({ sort: sortConfig });
  }, [sortConfig]);

  return (
    <div>
      <h2 style={{ marginBottom: 'var(--space-3)' }}>Day-Offset Metrics</h2>
      <div style={{ marginBottom: 'var(--space-2)', fontSize: 'var(--text-sm)', color: 'var(--text-dim)' }}>
        Performance metrics aggregated by day offset from event date
      </div>
      <DataTable
        data={data}
        columns={DAYOFFSET_COLUMNS}
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
