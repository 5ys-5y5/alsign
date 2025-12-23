/**
 * Condition Group Form Component
 *
 * Provides UI for creating condition groups with column/value selection
 * and confirmation dialog for bulk updates.
 */

import { useState, useEffect } from 'react';
import {
  getAllowedColumns,
  getColumnValues,
  createConditionGroup,
} from '../../services/conditionGroupService';

export default function ConditionGroupForm({ onSuccess, onError }) {
  const [columns, setColumns] = useState([]);
  const [selectedColumn, setSelectedColumn] = useState('');
  const [values, setValues] = useState([]);
  const [selectedValue, setSelectedValue] = useState('');
  const [conditionName, setConditionName] = useState('');
  const [loading, setLoading] = useState(false);
  const [loadingValues, setLoadingValues] = useState(false);
  const [showConfirmation, setShowConfirmation] = useState(false);
  const [estimatedRows, setEstimatedRows] = useState(0);

  // Load allowed columns on mount
  useEffect(() => {
    async function loadColumns() {
      try {
        const cols = await getAllowedColumns();
        setColumns(cols);
      } catch (error) {
        console.error('Failed to load columns:', error);
        onError?.(error.message);
      }
    }

    loadColumns();
  }, []);

  // Load values when column changes
  useEffect(() => {
    if (!selectedColumn) {
      setValues([]);
      setSelectedValue('');
      return;
    }

    async function loadValues() {
      setLoadingValues(true);
      try {
        const vals = await getColumnValues(selectedColumn);
        setValues(vals);
        setSelectedValue(''); // Reset selection
      } catch (error) {
        console.error('Failed to load values:', error);
        onError?.(error.message);
        setValues([]);
      } finally {
        setLoadingValues(false);
      }
    }

    loadValues();
  }, [selectedColumn]);

  const handleSubmit = async (e) => {
    e.preventDefault();

    // Validation
    const trimmedName = conditionName.trim();
    if (!trimmedName) {
      onError?.('Condition name cannot be empty');
      return;
    }

    if (!selectedColumn || !selectedValue) {
      onError?.('Please select both column and value');
      return;
    }

    // Show confirmation dialog
    setShowConfirmation(true);
  };

  const handleConfirm = async () => {
    setLoading(true);
    setShowConfirmation(false);

    try {
      const result = await createConditionGroup({
        column: selectedColumn,
        value: selectedValue,
        name: conditionName.trim(),
        confirm: true,
      });

      // Reset form
      setConditionName('');
      setSelectedColumn('');
      setSelectedValue('');
      setValues([]);

      onSuccess?.(result);
    } catch (error) {
      console.error('Failed to create condition group:', error);
      onError?.(error.message);
    } finally {
      setLoading(false);
    }
  };

  const handleCancel = () => {
    setShowConfirmation(false);
  };

  return (
    <div
      style={{
        border: '1px solid var(--border)',
        borderRadius: 'var(--rounded-lg)',
        padding: 'var(--space-3)',
        backgroundColor: 'white',
      }}
    >
      <form onSubmit={handleSubmit}>
        <div style={{ marginBottom: 'var(--space-3)' }}>
          <label
            htmlFor="column-select"
            style={{
              display: 'block',
              fontSize: 'var(--text-sm)',
              fontWeight: 'var(--font-semibold)',
              color: 'var(--ink)',
              marginBottom: 'var(--space-1)',
            }}
          >
            Column
            <span style={{ color: 'var(--accent-danger)', marginLeft: 'var(--space-1)' }}>*</span>
          </label>
          <select
            id="column-select"
            value={selectedColumn}
            onChange={(e) => setSelectedColumn(e.target.value)}
            disabled={loading}
            required
            style={{
              cursor: loading ? 'not-allowed' : 'pointer',
            }}
          >
            <option value="">Select a column...</option>
            {columns.map((col) => (
              <option key={col} value={col}>
                {col}
              </option>
            ))}
          </select>
        </div>

        <div style={{ marginBottom: 'var(--space-3)' }}>
          <label
            htmlFor="value-select"
            style={{
              display: 'block',
              fontSize: 'var(--text-sm)',
              fontWeight: 'var(--font-semibold)',
              color: 'var(--ink)',
              marginBottom: 'var(--space-1)',
            }}
          >
            Value
            <span style={{ color: 'var(--accent-danger)', marginLeft: 'var(--space-1)' }}>*</span>
          </label>
          <select
            id="value-select"
            value={selectedValue}
            onChange={(e) => setSelectedValue(e.target.value)}
            disabled={loading || !selectedColumn || loadingValues}
            required
            style={{
              cursor: loading || !selectedColumn || loadingValues ? 'not-allowed' : 'pointer',
            }}
          >
            <option value="">
              {loadingValues
                ? 'Loading values...'
                : selectedColumn
                ? 'Select a value...'
                : 'Select a column first'}
            </option>
            {values.map((val) => (
              <option key={val} value={val}>
                {val}
              </option>
            ))}
          </select>
        </div>

        <div style={{ marginBottom: 'var(--space-4)' }}>
          <label
            htmlFor="condition-name"
            style={{
              display: 'block',
              fontSize: 'var(--text-sm)',
              fontWeight: 'var(--font-semibold)',
              color: 'var(--ink)',
              marginBottom: 'var(--space-1)',
            }}
          >
            Condition Name
            <span style={{ color: 'var(--accent-danger)', marginLeft: 'var(--space-1)' }}>*</span>
          </label>
          <input
            type="text"
            id="condition-name"
            value={conditionName}
            onChange={(e) => setConditionName(e.target.value)}
            placeholder="Enter condition name..."
            disabled={loading}
            required
            style={{
              cursor: loading ? 'not-allowed' : 'text',
            }}
          />
        </div>

        <div>
          <button type="submit" disabled={loading} className="btn btn-md btn-primary">
            {loading ? 'Creating...' : 'Create Condition Group'}
          </button>
        </div>
      </form>

      {showConfirmation && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            width: '100%',
            height: '100%',
            zIndex: 'var(--z-popover)',
          }}
        >
          <div
            style={{
              position: 'absolute',
              top: 0,
              left: 0,
              width: '100%',
              height: '100%',
              backgroundColor: 'rgba(0, 0, 0, 0.5)',
            }}
            onClick={handleCancel}
          ></div>
          <div
            style={{
              position: 'absolute',
              top: '50%',
              left: '50%',
              transform: 'translate(-50%, -50%)',
              backgroundColor: 'white',
              padding: 'var(--space-4)',
              borderRadius: 'var(--rounded-xl)',
              boxShadow: 'var(--shadow-lg)',
              maxWidth: '500px',
              width: '90%',
              border: '1px solid var(--border)',
            }}
          >
            <h3 style={{ marginTop: 0, marginBottom: 'var(--space-3)' }}>Confirm Bulk Update</h3>
            <p style={{ marginBottom: 'var(--space-2)', color: 'var(--text)' }}>
              This will update all rows where <strong>{selectedColumn}</strong> ={' '}
              <strong>{selectedValue}</strong>
            </p>
            <p style={{ marginBottom: 'var(--space-2)', color: 'var(--text)' }}>
              The condition field will be set to: <strong>{conditionName.trim()}</strong>
            </p>
            <p
              style={{
                marginBottom: 'var(--space-3)',
                color: 'var(--accent-danger)',
                fontWeight: 'var(--font-semibold)',
              }}
            >
              This action cannot be undone.
            </p>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 'var(--space-2)' }}>
              <button onClick={handleCancel} className="btn btn-md btn-outline">
                Cancel
              </button>
              <button onClick={handleConfirm} className="btn btn-md btn-danger">
                Confirm Update
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
