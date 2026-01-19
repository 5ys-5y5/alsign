/**
 * EventsSettingsPanel Component
 *
 * Settings panel for configuring events performance calculation parameters.
 * Displays on Dashboard page and controls Events page calculations.
 */

import React, { useState } from 'react';

const DAY_OFFSET_OPTIONS = Array.from({ length: 29 }, (_, i) => {
  const offset = i - 14;
  const label = offset === 0 ? 'D0' : `D${offset > 0 ? `+${offset}` : offset}`;
  return {
    value: offset,
    label,
  };
});

const OHLC_OPTIONS = [
  { value: 'open', label: 'Open' },
  { value: 'high', label: 'High' },
  { value: 'low', label: 'Low' },
  { value: 'close', label: 'Close' },
];

const DEFAULT_SETTINGS = {
  baseOffset: 0,
  baseField: 'close',
  minThreshold: null,
  maxThreshold: null,
};

export default function EventsSettingsPanel({ settings = DEFAULT_SETTINGS, onChange }) {
  const [isExpanded, setIsExpanded] = useState(true);

  const handleSettingChange = (key, value) => {
    const newSettings = { ...settings, [key]: value };
    if (onChange) {
      onChange(newSettings);
    }
  };

  const handleBaseOffsetChange = (e) => {
    handleSettingChange('baseOffset', parseInt(e.target.value, 10));
  };

  const handleBaseFieldChange = (e) => {
    handleSettingChange('baseField', e.target.value);
  };

  const handleMinThresholdChange = (e) => {
    const value = e.target.value.trim();
    handleSettingChange('minThreshold', value === '' ? null : parseFloat(value));
  };

  const handleMaxThresholdChange = (e) => {
    const value = e.target.value.trim();
    handleSettingChange('maxThreshold', value === '' ? null : parseFloat(value));
  };

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--space-2)',
        width: '100%',
      }}
    >
      {/* Header with toggle */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 'var(--space-2)',
        }}
      >
        <button
          type="button"
          onClick={() => setIsExpanded(!isExpanded)}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 'var(--space-2)',
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            padding: 0,
          }}
        >
          <span style={{ fontWeight: 500, fontSize: 'var(--text-base)' }}>
            Events Settings
          </span>
          <span style={{ color: 'var(--text-dim)', fontSize: 'var(--text-sm)' }}>
            {isExpanded ? 'v' : '>'}
          </span>
        </button>
      </div>

      {/* Settings content */}
      {isExpanded && (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
            gap: 'var(--space-2)',
          }}
        >
          {/* Base Day Offset */}
          <div>
            <label
              htmlFor="eventsBaseOffset"
              style={{
                display: 'block',
                fontSize: 'var(--text-sm)',
                fontWeight: 500,
                marginBottom: 'var(--space-1)',
                color: 'var(--text)',
              }}
            >
              Base Day Offset
            </label>
            <select
              id="eventsBaseOffset"
              value={settings.baseOffset}
              onChange={handleBaseOffsetChange}
              style={{
                width: '100%',
                height: '32px',
                padding: '0 var(--space-2)',
                fontSize: 'var(--text-sm)',
                border: '1px solid var(--border)',
                borderRadius: '8px',
                backgroundColor: 'white',
              }}
            >
              {DAY_OFFSET_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>

          {/* Base OHLC Field */}
          <div>
            <label
              htmlFor="eventsBaseField"
              style={{
                display: 'block',
                fontSize: 'var(--text-sm)',
                fontWeight: 500,
                marginBottom: 'var(--space-1)',
                color: 'var(--text)',
              }}
            >
              Base OHLC Field
            </label>
            <select
              id="eventsBaseField"
              value={settings.baseField}
              onChange={handleBaseFieldChange}
              style={{
                width: '100%',
                height: '32px',
                padding: '0 var(--space-2)',
                fontSize: 'var(--text-sm)',
                border: '1px solid var(--border)',
                borderRadius: '8px',
                backgroundColor: 'white',
              }}
            >
              {OHLC_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>

          {/* MIN% Threshold */}
          <div>
            <label
              htmlFor="eventsMinThreshold"
              style={{
                display: 'block',
                fontSize: 'var(--text-sm)',
                fontWeight: 500,
                marginBottom: 'var(--space-1)',
                color: 'var(--text)',
              }}
            >
              MIN% (Stop Loss)
            </label>
            <input
              id="eventsMinThreshold"
              type="number"
              placeholder="e.g. -10"
              value={settings.minThreshold ?? ''}
              onChange={handleMinThresholdChange}
              style={{
                width: '100%',
                height: '32px',
                padding: '0 var(--space-2)',
                fontSize: 'var(--text-sm)',
                border: '1px solid var(--border)',
                borderRadius: '8px',
              }}
            />
            <span
              style={{
                fontSize: 'var(--text-xs)',
                color: 'var(--text-dim)',
              }}
            >
              Empty = disabled
            </span>
          </div>

          {/* MAX% Threshold */}
          <div>
            <label
              htmlFor="eventsMaxThreshold"
              style={{
                display: 'block',
                fontSize: 'var(--text-sm)',
                fontWeight: 500,
                marginBottom: 'var(--space-1)',
                color: 'var(--text)',
              }}
            >
              MAX% (Profit Target)
            </label>
            <input
              id="eventsMaxThreshold"
              type="number"
              placeholder="e.g. 20"
              value={settings.maxThreshold ?? ''}
              onChange={handleMaxThresholdChange}
              style={{
                width: '100%',
                height: '32px',
                padding: '0 var(--space-2)',
                fontSize: 'var(--text-sm)',
                border: '1px solid var(--border)',
                borderRadius: '8px',
              }}
            />
            <span
              style={{
                fontSize: 'var(--text-xs)',
                color: 'var(--text-dim)',
              }}
            >
              Empty = disabled
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
