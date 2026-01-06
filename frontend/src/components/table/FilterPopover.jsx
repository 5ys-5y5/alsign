/**
 * FilterPopover Component
 *
 * Popover panel for filtering table columns.
 * Supports different filter types: string (contains), date, number (min-max), enum (select).
 * Based on alsign/prompt/2_designSystem.ini
 */

import React, { useState, useRef, useEffect } from 'react';
import { createPortal } from 'react-dom';

/**
 * Filter icon SVG (funnel shape)
 */
function FilterIcon({ active }) {
  return (
    <svg
      className={`filter-icon ${active ? 'active' : ''}`}
      viewBox="0 0 14 14"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <path
        d="M2 3H12L8 8V11L6 12V8L2 3Z"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/**
 * FilterPopover component for column filtering.
 *
 * @param {Object} props - Component props
 * @param {string} props.columnKey - The column key being filtered
 * @param {string} props.columnLabel - The column label for display
 * @param {string} props.filterType - Filter type: 'string' | 'date' | 'daterange' | 'number' | 'enum' | 'dayoffset'
 * @param {Array} [props.enumOptions] - Options for enum filter type
 * @param {*} props.value - Current filter value (for daterange: { from: '2024-01-01', to: '2024-12-31' })
 * @param {Function} props.onChange - Callback when filter changes (value) => void
 * @param {Function} props.onReset - Callback to reset this filter () => void
 * @returns {JSX.Element} Filter button with popover
 */
export default function FilterPopover({
  columnKey,
  columnLabel,
  filterType,
  enumOptions = [],
  value,
  onChange,
  onReset,
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [localValue, setLocalValue] = useState(value || '');
  // For daterange filter
  const [localDateFrom, setLocalDateFrom] = useState(value?.from || '');
  const [localDateTo, setLocalDateTo] = useState(value?.to || '');
  const [popoverPosition, setPopoverPosition] = useState({ top: 0, left: 0 });
  const popoverRef = useRef(null);
  const buttonRef = useRef(null);

  const hasActiveFilter = filterType === 'daterange'
    ? (value?.from || value?.to)
    : (value !== null && value !== undefined && value !== '');

  // Update local value when prop changes
  useEffect(() => {
    if (filterType === 'daterange') {
      setLocalDateFrom(value?.from || '');
      setLocalDateTo(value?.to || '');
    } else {
      setLocalValue(value || '');
    }
  }, [value, filterType]);

  // Calculate popover position when opened
  useEffect(() => {
    if (isOpen && buttonRef.current) {
      const buttonRect = buttonRef.current.getBoundingClientRect();
      setPopoverPosition({
        top: buttonRect.bottom + 4, // 4px margin
        left: buttonRect.right - 256, // 256px = filter panel width, align right edge
      });
    }
  }, [isOpen]);

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
        buttonRef.current &&
        !buttonRef.current.contains(e.target)
      ) {
        setIsOpen(false);
      }
    };

    if (isOpen) {
      // Delay adding the listener to prevent immediate closure
      const timeoutId = setTimeout(() => {
        document.addEventListener('mousedown', handleClickOutside);
      }, 100);

      return () => {
        clearTimeout(timeoutId);
        document.removeEventListener('mousedown', handleClickOutside);
      };
    }
  }, [isOpen]);

  const handleApply = () => {
    if (filterType === 'daterange') {
      onChange({ from: localDateFrom, to: localDateTo });
    } else {
      onChange(localValue);
    }
    setIsOpen(false);
  };

  const handleReset = () => {
    if (filterType === 'daterange') {
      setLocalDateFrom('');
      setLocalDateTo('');
    } else {
      setLocalValue('');
    }
    onReset();
    setIsOpen(false);
  };

  const handleInputChange = (e) => {
    setLocalValue(e.target.value);
  };

  const renderFilterInput = () => {
    switch (filterType) {
      case 'string':
        return (
          <div>
            <input
              type="text"
              value={localValue}
              onChange={handleInputChange}
              placeholder={`Filter ${columnLabel}...`}
              autoFocus
            />
            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)', marginTop: 'var(--space-1)' }}>
              Tip: Use = prefix for exact match (e.g., =AAPL)
            </div>
          </div>
        );

      case 'date':
        return (
          <input
            type="date"
            value={localValue}
            onChange={handleInputChange}
            autoFocus
          />
        );

      case 'daterange':
        return (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
            <div>
              <label style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)', display: 'block', marginBottom: 'var(--space-1)' }}>
                From:
              </label>
              <input
                type="date"
                value={localDateFrom}
                onChange={(e) => setLocalDateFrom(e.target.value)}
                autoFocus
              />
            </div>
            <div>
              <label style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)', display: 'block', marginBottom: 'var(--space-1)' }}>
                To:
              </label>
              <input
                type="date"
                value={localDateTo}
                onChange={(e) => setLocalDateTo(e.target.value)}
              />
            </div>
          </div>
        );

      case 'number':
      case 'dayoffset':
        return (
          <div>
            <input
              type="text"
              value={localValue}
              onChange={handleInputChange}
              placeholder="e.g., 10-20, >5, <100"
              autoFocus
            />
            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)', marginTop: 'var(--space-1)' }}>
              Format: min-max, &gt;min, &lt;max, or value
            </div>
          </div>
        );

      case 'enum':
        return (
          <select value={localValue} onChange={handleInputChange} autoFocus>
            <option value="">All</option>
            {enumOptions.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        );

      default:
        return <div>Unknown filter type</div>;
    }
  };

  const ariaLabel = hasActiveFilter
    ? `Filter ${columnLabel} (active)`
    : `Filter ${columnLabel}`;

  const popoverContent = isOpen ? (
    <div
      ref={popoverRef}
      className="panel filter-panel open"
      style={{
        position: 'fixed',
        top: `${popoverPosition.top}px`,
        left: `${popoverPosition.left}px`,
        zIndex: 1000,
      }}
    >
      <div className="filter-panel-header">
        <div className="filter-panel-title">Filter {columnLabel}</div>
      </div>

      <div className="filter-panel-body">
        {renderFilterInput()}
      </div>

      <div
        style={{
          display: 'flex',
          gap: 'var(--space-1)',
          marginTop: 'var(--space-2)',
          paddingTop: 'var(--space-2)',
          borderTop: '1px solid var(--border)',
        }}
      >
        <button
          type="button"
          className="btn btn-sm btn-primary"
          onClick={handleApply}
        >
          Apply
        </button>
        <button
          type="button"
          className="btn btn-sm btn-outline"
          onClick={handleReset}
        >
          Reset
        </button>
      </div>
    </div>
  ) : null;

  return (
    <div style={{ position: 'relative', display: 'inline-block' }}>
      <button
        ref={buttonRef}
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          setIsOpen(!isOpen);
        }}
        aria-label={ariaLabel}
        style={{
          background: 'none',
          border: 'none',
          padding: 0,
          cursor: 'pointer',
          display: 'inline-flex',
          alignItems: 'center',
          color: 'inherit',
        }}
      >
        <FilterIcon active={hasActiveFilter} />
      </button>

      {popoverContent && createPortal(popoverContent, document.body)}
    </div>
  );
}
