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
function renderCellValue(value, column) {
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

/**
 * Apply filters to data rows.
 *
 * @param {Array} data - Array of data rows
 * @param {Object} filters - Filters object { columnKey: filterValue }
 * @param {Array} columns - Column configurations
 * @returns {Array} Filtered data rows
 */
function applyFilters(data, filters, columns) {
  return data.filter((row) => {
    return Object.entries(filters).every(([columnKey, filterValue]) => {
      if (!filterValue) return true;

      const column = columns.find((col) => col.key === columnKey);
      if (!column) return true;

      const cellValue = row[columnKey];

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
      if (column.type === 'number') {
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
function applySort(data, sortConfig, columns) {
  if (!sortConfig.key || !sortConfig.direction) {
    return data;
  }

  const column = columns.find((col) => col.key === sortConfig.key);
  if (!column) return data;

  return [...data].sort((a, b) => {
    const aVal = a[sortConfig.key];
    const bVal = b[sortConfig.key];

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
    if (column.type === 'number') {
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
}) {
  // Determine visible columns
  const visibleColumns = useMemo(() => {
    return columns.filter((col) => selectedColumns.includes(col.key));
  }, [columns, selectedColumns]);

  // Apply filters and sorting
  const processedData = useMemo(() => {
    let result = data;
    result = applyFilters(result, filters, columns);
    result = applySort(result, sortConfig, columns);
    return result;
  }, [data, filters, sortConfig, columns]);

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

  return (
    <div className="table-shell">
      {/* Toolbar */}
      <div className="table-toolbar">
        <ColumnSelector
          allColumns={columns}
          selectedColumns={selectedColumns}
          onChange={onSelectedColumnsChange}
        />
        <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-dim)' }}>
          {processedData.length} {processedData.length === 1 ? 'row' : 'rows'}
          {data.length !== processedData.length && ` (filtered from ${data.length})`}
        </div>
      </div>

      {/* Scrollable Table Container */}
      <div className="scroll-y">
        <div className="scroll-x">
          {loading ? (
            <div className="loading">Loading...</div>
          ) : processedData.length === 0 ? (
            <div className="empty-state">No data to display</div>
          ) : (
            <table>
              <thead>
                <tr>
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
                {processedData.map((row, rowIndex) => (
                  <tr key={row.id || rowIndex}>
                    {visibleColumns.map((column) => (
                      <td
                        key={column.key}
                        style={{
                          width: column.width ? `${column.width}px` : 'auto',
                        }}
                      >
                        {renderCellValue(row[column.key], column)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
