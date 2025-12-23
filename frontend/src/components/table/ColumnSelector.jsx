/**
 * ColumnSelector Component
 *
 * Popover panel with checkboxes for selecting visible table columns.
 * Changes apply immediately and persist to localStorage.
 * Based on alsign/prompt/2_designSystem.ini
 */

import React, { useState, useRef, useEffect } from 'react';

/**
 * Column/Menu icon SVG
 */
function ColumnsIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <path
        d="M2 4H14M2 8H14M2 12H14"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </svg>
  );
}

/**
 * ColumnSelector component for selecting visible table columns.
 *
 * @param {Object} props - Component props
 * @param {Array} props.allColumns - All available columns [{ key, label }, ...]
 * @param {Array} props.selectedColumns - Currently selected column keys
 * @param {Function} props.onChange - Callback when selection changes (selectedKeys) => void
 * @returns {JSX.Element} Column selector button with popover
 */
export default function ColumnSelector({ allColumns, selectedColumns, onChange }) {
  const [isOpen, setIsOpen] = useState(false);
  const popoverRef = useRef(null);
  const buttonRef = useRef(null);

  // Close popover on ESC key
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && isOpen) {
        setIsOpen(false);
      }
    };

    if (isOpen) {
      document.addEventListener('keydown', handleKeyDown);
      return () => document.removeEventListener('keydown', handleKeyDown);
    }
  }, [isOpen]);

  // Close popover when clicking outside
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (
        isOpen &&
        popoverRef.current &&
        !popoverRef.current.contains(e.target) &&
        !buttonRef.current.contains(e.target)
      ) {
        setIsOpen(false);
      }
    };

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [isOpen]);

  const handleToggle = (columnKey) => {
    const newSelected = selectedColumns.includes(columnKey)
      ? selectedColumns.filter((key) => key !== columnKey)
      : [...selectedColumns, columnKey];

    // Apply immediately
    onChange(newSelected);
  };

  const handleSelectAll = () => {
    onChange(allColumns.map((col) => col.key));
  };

  const handleDeselectAll = () => {
    onChange([]);
  };

  return (
    <div style={{ position: 'relative', display: 'inline-block' }}>
      <button
        ref={buttonRef}
        type="button"
        className="btn btn-sm btn-outline"
        onClick={() => setIsOpen(!isOpen)}
        aria-label="Select columns"
      >
        <ColumnsIcon />
        <span>Columns</span>
      </button>

      {isOpen && (
        <div
          ref={popoverRef}
          className="panel column-selector-panel open"
          style={{
            top: '100%',
            left: 0,
            marginTop: 'var(--space-1)',
          }}
        >
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: 'var(--space-2)',
              paddingBottom: 'var(--space-2)',
              borderBottom: '1px solid var(--border)',
            }}
          >
            <div
              style={{
                fontSize: 'var(--text-sm)',
                fontWeight: 'var(--font-semibold)',
                color: 'var(--ink)',
              }}
            >
              Select Columns
            </div>
            <div style={{ display: 'flex', gap: 'var(--space-1)' }}>
              <button
                type="button"
                onClick={handleSelectAll}
                style={{
                  background: 'none',
                  border: 'none',
                  padding: '2px var(--space-1)',
                  cursor: 'pointer',
                  fontSize: 'var(--text-xs)',
                  color: 'var(--accent-primary)',
                }}
              >
                All
              </button>
              <button
                type="button"
                onClick={handleDeselectAll}
                style={{
                  background: 'none',
                  border: 'none',
                  padding: '2px var(--space-1)',
                  cursor: 'pointer',
                  fontSize: 'var(--text-xs)',
                  color: 'var(--accent-primary)',
                }}
              >
                None
              </button>
            </div>
          </div>

          <div
            style={{
              maxHeight: '300px',
              overflowY: 'auto',
            }}
          >
            {allColumns.map((column) => {
              const isChecked = selectedColumns.includes(column.key);

              return (
                <label
                  key={column.key}
                  className="checkbox-label"
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 'var(--space-1)',
                    padding: 'var(--space-1) 0',
                    cursor: 'pointer',
                  }}
                >
                  <input
                    type="checkbox"
                    checked={isChecked}
                    onChange={() => handleToggle(column.key)}
                  />
                  <span>{column.label}</span>
                </label>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
