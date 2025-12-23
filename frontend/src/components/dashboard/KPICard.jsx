/**
 * KPICard Component
 *
 * Displays a single KPI (Key Performance Indicator) card with title, value, and subtitle.
 * Follows the design system specifications from alsign/prompt/2_designSystem.ini
 */

import React from 'react';

/**
 * KPICard component for displaying a key metric.
 *
 * @param {Object} props - Component props
 * @param {string} props.title - The KPI title (e.g., "Coverage", "Data Freshness")
 * @param {string|number} props.value - The KPI value to display
 * @param {string} [props.subtitle] - Optional subtitle or description
 * @param {string} [props.className] - Additional CSS classes
 * @returns {JSX.Element} KPI card component
 */
export default function KPICard({ title, value, subtitle, className = '' }) {
  return (
    <div className={`kpi-card ${className}`}>
      <div className="kpi-card-title">{title}</div>
      <div className="kpi-card-value">{value}</div>
      {subtitle && <div className="kpi-card-subtitle">{subtitle}</div>}
    </div>
  );
}
