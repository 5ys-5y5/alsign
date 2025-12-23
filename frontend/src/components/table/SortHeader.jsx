/**
 * SortHeader Component
 *
 * Table header cell with sort functionality.
 * Implements the sort state machine: null → asc → desc → null
 * Based on alsign/prompt/2_designSystem.ini
 */

import React from 'react';

/**
 * SVG icons for sort states (inline SVG to avoid icon library dependency)
 */
const SortIcons = {
  none: () => (
    <svg
      className="sort-icon sort-icon-none"
      viewBox="0 0 14 14"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <path
        d="M7 2L7 12M7 2L4 5M7 2L10 5M7 12L4 9M7 12L10 9"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  ),
  asc: () => (
    <svg
      className="sort-icon sort-icon-asc"
      viewBox="0 0 14 14"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <path
        d="M7 2L7 12M7 2L4 5M7 2L10 5"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  ),
  desc: () => (
    <svg
      className="sort-icon sort-icon-desc"
      viewBox="0 0 14 14"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <path
        d="M7 12L7 2M7 12L4 9M7 12L10 9"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  ),
};

/**
 * SortHeader component for table column headers with sort functionality.
 *
 * @param {Object} props - Component props
 * @param {string} props.columnKey - The column key for sorting
 * @param {string} props.label - The column label to display
 * @param {Object} props.sortConfig - Current sort config { key: string|null, direction: 'asc'|'desc'|null }
 * @param {Function} props.onSort - Callback when sort is clicked (columnKey) => void
 * @param {React.ReactNode} [props.children] - Additional content (e.g., filter button)
 * @returns {JSX.Element} Table header cell with sort functionality
 */
export default function SortHeader({ columnKey, label, sortConfig, onSort, children }) {
  const isActive = sortConfig.key === columnKey;
  const direction = isActive ? sortConfig.direction : null;

  // Determine which icon to show
  let SortIcon;
  if (!isActive || direction === null) {
    SortIcon = SortIcons.none;
  } else if (direction === 'asc') {
    SortIcon = SortIcons.asc;
  } else {
    SortIcon = SortIcons.desc;
  }

  const handleClick = () => {
    onSort(columnKey);
  };

  // Aria label for accessibility
  const ariaLabel = !isActive || direction === null
    ? `Sort by ${label}`
    : `Sorted by ${label} ${direction === 'asc' ? 'ascending' : 'descending'}. Click to ${
        direction === 'asc' ? 'sort descending' : 'clear sort'
      }.`;

  return (
    <th>
      <div className="th-content">
        <span>{label}</span>
        <button
          type="button"
          onClick={handleClick}
          aria-label={ariaLabel}
          className="sort-button"
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
          <SortIcon />
        </button>
        {children}
      </div>
    </th>
  );
}
