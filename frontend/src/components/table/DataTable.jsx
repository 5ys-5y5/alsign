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

function getDayOffsetTooltipContent(row, column, dayOffsetMode) {
  if (!row || row.is_blurred) {
    return null;
  }

  const targetDates = row.day_offset_target_dates;
  const targetDate = targetDates ? targetDates[column.key] : null;
  const targetLine = targetDate ? `기준일: ${targetDate}` : null;

  if (dayOffsetMode === 'performance') {
    const priceTrendMap = row.day_offset_price_trend;
    if (!priceTrendMap) {
      return null;
    }
    const baseValue = Number(priceTrendMap.d_neg14);
    const currentValue = Number(priceTrendMap[column.key]);
    const baseLabel = 'D-14';
    const currentLabel = column.label || column.key;
    const lines = [];
    if (targetLine) {
      lines.push(targetLine);
      lines.push('');
    }
    if (column.key !== 'd_neg14') {
      lines.push(`${currentLabel} N: ${formatNumber(currentValue)}`);
    }
    lines.push(`${baseLabel} N: ${formatNumber(baseValue)}`);
    return lines.join('\n');
  }

  const performanceMap = row.day_offset_performance;
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
  if (targetLine) {
    lines.push(targetLine);
    lines.push('');
  }
  lines.push(`${label} %: ${(displayValue * 100).toFixed(2)}%`);
  return lines.join('\n');
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
 * @param {boolean} [props.enableRowExpand] - Enable row expand on click
 * @param {boolean} [props.enableCheckboxes] - Enable row selection with checkboxes
 * @param {boolean} [props.enableFooterStats] - Enable footer statistics row
 * @param {boolean} [props.enableServerSideSort] - If true, skip client-side sorting (data is already sorted by server)
 * @param {boolean} [props.enableServerSideFilter] - If true, skip client-side filtering (data is already filtered by server)
 * @param {Function} [props.onSelectionChange] - Callback when row selection changes (receives Set of row IDs)
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
}) {
  // Track expanded rows
  const [expandedRows, setExpandedRows] = useState(new Set());

  // Track selected rows (for checkboxes)
  const [selectedRows, setSelectedRows] = useState(new Set());
  const [hoverTooltip, setHoverTooltip] = useState({ visible: false, x: 0, y: 0, content: '' });

  // Notify parent when selection changes
  useEffect(() => {
    if (onSelectionChange) {
      onSelectionChange(selectedRows);
    }
  }, [selectedRows, onSelectionChange]);
  // Determine visible columns
  const visibleColumns = useMemo(() => {
    return columns.filter((col) => selectedColumns.includes(col.key));
  }, [columns, selectedColumns]);

  // Apply filters and sorting
  const processedData = useMemo(() => {
    let result = data;
    // Only apply client-side filtering if server-side filtering is not enabled
    if (!enableServerSideFilter) {
      result = applyFilters(result, filters, columns);
    }
    // Only apply client-side sorting if server-side sorting is not enabled
    if (!enableServerSideSort) {
      result = applySort(result, sortConfig, columns);
    }
    return result;
  }, [data, filters, sortConfig, columns, enableServerSideSort, enableServerSideFilter]);

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
    const content = getDayOffsetTooltipContent(row, column, dayOffsetMode);
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
            .map((row) => row[key])
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
          if (dayOffsetMode !== 'performance') {
            return '-';
          }
          const adjustedValues = processedData
            .map((row) => {
              const rawValue = Number(row[columnKey]);
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

  return (
    <div className="table-shell">
      {/* Toolbar - Always visible at top */}
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
                        {visibleColumns.map((column) => (
                          <td
                            key={column.key}
                            style={{
                              width: column.width ? `${column.width}px` : 'auto',
                            }}
                          >
                            {column.type === 'dayoffset' ? (
                              <span
                                onMouseMove={(event) => handleDayOffsetMove(event, row, column)}
                                onMouseLeave={handleDayOffsetLeave}
                              >
                                {renderCellValue(row[column.key], column, row, dayOffsetMode)}
                              </span>
                            ) : (
                              renderCellValue(row[column.key], column, row, dayOffsetMode)
                            )}
                          </td>
                        ))}
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
                                    <strong>{column.label}:</strong> {renderCellValue(row[column.key], column, row, dayOffsetMode)}
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
            whiteSpace: 'pre',
            zIndex: 1000,
          }}
        >
          {hoverTooltip.content}
        </div>
      )}
    </div>
  );
}
