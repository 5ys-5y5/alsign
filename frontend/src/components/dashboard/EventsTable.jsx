/**
 * EventsTable Component
 *
 * Table for displaying txn_events.
 * Uses DataTable with specific column configuration and persistence for txn_events dataset.
 */

import React, { useState, useEffect } from 'react';
import DataTable from '../table/DataTable';
import { getTxnEventsState, setTxnEventsState } from '../../services/localStorage';

/**
 * Column catalog for txn_events (Events)
 * Based on design system mapping: dataset.txn_events.column_catalog
 */
const EVENTS_COLUMNS = [
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
  { key: 'id', label: 'id', type: 'string', width: 280, isDefault: true },

  // WTS column
  { key: 'wts', label: 'WTS', type: 'number', width: 80, isDefault: true },

  // Day offset columns (D-14 to D14, excluding D0)
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

  // Additional columns (not default)
  { key: 'source_id', label: 'source_id', type: 'string', width: 120, isDefault: false },
];

// API base URL from environment or default to localhost
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

/**
 * EventsTable component for displaying txn_events.
 *
 * @param {Object} props - Component props
 * @param {Array} props.data - Events data rows from txn_events
 * @param {boolean} [props.loading] - Loading state
 * @param {number} props.total - Total number of events
 * @param {number} props.page - Current page number
 * @param {number} props.pageSize - Page size
 * @param {Function} props.onPageChange - Page change callback
 * @param {Function} props.onPageSizeChange - Page size change callback
 * @returns {JSX.Element} Events table component
 */
export default function EventsTable({
  data,
  loading = false,
  total = 0,
  page = 1,
  pageSize = 100,
  onPageChange,
  onPageSizeChange,
}) {
  // Initialize state from localStorage or defaults
  const [selectedColumns, setSelectedColumns] = useState(() => {
    const persisted = getTxnEventsState();
    return (
      persisted.selectedColumns ||
      EVENTS_COLUMNS.filter((col) => col.isDefault).map((col) => col.key)
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

  // Track selected rows for bulk operations
  const [selectedRowIds, setSelectedRowIds] = useState(new Set());

  // Bulk edit state
  const [showBulkEdit, setShowBulkEdit] = useState(false);
  const [bulkEditField, setBulkEditField] = useState('condition');
  const [bulkEditOperation, setBulkEditOperation] = useState('append');
  const [bulkEditValue, setBulkEditValue] = useState('');
  const [bulkEditLoading, setBulkEditLoading] = useState(false);
  const [bulkEditMessage, setBulkEditMessage] = useState('');

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

  // Handle bulk edit submission
  const handleBulkEdit = async () => {
    if (selectedRowIds.size === 0) {
      setBulkEditMessage('No rows selected');
      return;
    }

    if (!bulkEditValue && bulkEditOperation !== 'remove') {
      setBulkEditMessage('Please enter a value');
      return;
    }

    setBulkEditLoading(true);
    setBulkEditMessage('');

    try {
      const response = await fetch(`${API_BASE_URL}/dashboard/bulkUpdate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          event_ids: Array.from(selectedRowIds),
          field: bulkEditField,
          operation: bulkEditOperation,
          value: bulkEditValue,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `HTTP ${response.status}`);
      }

      const result = await response.json();
      setBulkEditMessage(`Success: ${result.message}`);

      // Reset form
      setBulkEditValue('');
      setSelectedRowIds(new Set());

      // Optionally reload data here
      setTimeout(() => {
        window.location.reload();
      }, 1500);
    } catch (error) {
      console.error('Bulk edit failed:', error);
      setBulkEditMessage(`Error: ${error.message}`);
    } finally {
      setBulkEditLoading(false);
    }
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-3)' }}>
        <h2 style={{ margin: 0 }}>Events</h2>
        <button
          className="btn btn-sm btn-primary"
          onClick={() => setShowBulkEdit(!showBulkEdit)}
          disabled={selectedRowIds.size === 0}
        >
          Bulk Edit ({selectedRowIds.size} selected)
        </button>
      </div>

      {showBulkEdit && selectedRowIds.size > 0 && (
        <div style={{
          padding: 'var(--space-3)',
          backgroundColor: 'var(--surface)',
          borderRadius: 'var(--rounded-lg)',
          marginBottom: 'var(--space-3)',
          border: '1px solid var(--border)'
        }}>
          <h3 style={{ marginBottom: 'var(--space-2)', fontSize: 'var(--text-base)' }}>
            Bulk Edit {selectedRowIds.size} Events
          </h3>

          <div style={{ display: 'flex', gap: 'var(--space-2)', marginBottom: 'var(--space-2)', flexWrap: 'wrap' }}>
            <div>
              <label style={{ fontSize: 'var(--text-sm)', fontWeight: 'var(--font-medium)' }}>Field:</label>
              <select
                value={bulkEditField}
                onChange={(e) => {
                  setBulkEditField(e.target.value);
                  // Reset operation based on field
                  if (e.target.value === 'condition') {
                    setBulkEditOperation('append');
                  } else {
                    setBulkEditOperation('set');
                  }
                }}
                style={{ marginLeft: 'var(--space-1)' }}
              >
                <option value="condition">Condition</option>
                <option value="position_quantitative">Position (Q)</option>
                <option value="position_qualitative">Position (QL)</option>
              </select>
            </div>

            {bulkEditField === 'condition' && (
              <div>
                <label style={{ fontSize: 'var(--text-sm)', fontWeight: 'var(--font-medium)' }}>Operation:</label>
                <select
                  value={bulkEditOperation}
                  onChange={(e) => setBulkEditOperation(e.target.value)}
                  style={{ marginLeft: 'var(--space-1)' }}
                >
                  <option value="append">Append (add with comma)</option>
                  <option value="replace">Replace</option>
                  <option value="remove">Remove</option>
                </select>
              </div>
            )}

            <div style={{ flexGrow: 1 }}>
              <label style={{ fontSize: 'var(--text-sm)', fontWeight: 'var(--font-medium)' }}>Value:</label>
              {bulkEditField.startsWith('position') ? (
                <select
                  value={bulkEditValue}
                  onChange={(e) => setBulkEditValue(e.target.value)}
                  style={{ marginLeft: 'var(--space-1)' }}
                >
                  <option value="">Select...</option>
                  <option value="long">long</option>
                  <option value="short">short</option>
                  <option value="neutral">neutral</option>
                  <option value="null">null</option>
                </select>
              ) : (
                <input
                  type="text"
                  value={bulkEditValue}
                  onChange={(e) => setBulkEditValue(e.target.value)}
                  placeholder="Enter value"
                  style={{ marginLeft: 'var(--space-1)', width: '200px' }}
                />
              )}
            </div>

            <div style={{ display: 'flex', alignItems: 'flex-end', gap: 'var(--space-1)' }}>
              <button
                className="btn btn-sm btn-success"
                onClick={handleBulkEdit}
                disabled={bulkEditLoading}
              >
                {bulkEditLoading ? 'Updating...' : 'Apply'}
              </button>
              <button
                className="btn btn-sm btn-outline"
                onClick={() => {
                  setShowBulkEdit(false);
                  setBulkEditMessage('');
                }}
              >
                Cancel
              </button>
            </div>
          </div>

          {bulkEditMessage && (
            <div style={{
              marginTop: 'var(--space-2)',
              padding: 'var(--space-2)',
              borderRadius: 'var(--rounded-lg)',
              backgroundColor: bulkEditMessage.startsWith('Error') ? 'rgb(254 226 226)' : 'rgb(220 252 231)',
              color: bulkEditMessage.startsWith('Error') ? 'rgb(127 29 29)' : 'rgb(22 101 52)',
              fontSize: 'var(--text-sm)'
            }}>
              {bulkEditMessage}
            </div>
          )}
        </div>
      )}

      <DataTable
        data={data}
        columns={EVENTS_COLUMNS}
        selectedColumns={selectedColumns}
        onSelectedColumnsChange={setSelectedColumns}
        filters={filters}
        onFiltersChange={setFilters}
        sortConfig={sortConfig}
        onSortChange={setSortConfig}
        loading={loading}
        enableRowExpand={true}
        enableCheckboxes={true}
        enableFooterStats={true}
        onSelectionChange={setSelectedRowIds}
      />

      {/* Pagination Controls */}
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
          Showing {((page - 1) * pageSize) + 1} to {Math.min(page * pageSize, total)} of {total.toLocaleString()} events
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
              ««
            </button>
            <button
              className="btn btn-sm btn-outline"
              onClick={() => onPageChange(page - 1)}
              disabled={page === 1}
              style={{ minWidth: '32px' }}
            >
              ‹
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
              ›
            </button>
            <button
              className="btn btn-sm btn-outline"
              onClick={() => onPageChange(Math.ceil(total / pageSize))}
              disabled={page >= Math.ceil(total / pageSize)}
              style={{ minWidth: '32px' }}
            >
              »»
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
