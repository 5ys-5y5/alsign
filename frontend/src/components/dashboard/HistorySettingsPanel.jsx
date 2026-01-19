/**
 * HistorySettingsPanel Component
 *
 * Settings panel for configuring history performance calculation parameters.
 * Displays on Dashboard page and controls History page calculations.
 */

import React, { useState, useEffect } from 'react';
import {
  getHistorySettings,
  setHistorySettings,
} from '../../services/localStorage';
import { requestHistoryCacheRefresh } from '../../services/historyData';

const DAY_OFFSET_OPTIONS = Array.from({ length: 15 }, (_, i) => ({
  value: i,
  label: `D${i}`,
}));

const OHLC_OPTIONS = [
  { value: 'open', label: 'Open' },
  { value: 'high', label: 'High' },
  { value: 'low', label: 'Low' },
  { value: 'close', label: 'Close' },
];

export default function HistorySettingsPanel() {
  const [settings, setSettings] = useState(() => getHistorySettings());
  const [isExpanded, setIsExpanded] = useState(true);

  // Save and trigger recalculation when settings change
  const handleSettingChange = (key, value) => {
    const newSettings = { ...settings, [key]: value };
    setSettings(newSettings);
    setHistorySettings(newSettings);
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

  const handleUpdateClick = () => {
    requestHistoryCacheRefresh();
  };

  return (
    <div
      style={{
        backgroundColor: 'white',
        borderRadius: '8px',
        border: '1px solid var(--border)',
        marginBottom: 'var(--space-4)',
      }}
    >
      {/* Header with toggle */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: 'var(--space-3) var(--space-4)',
          borderBottom: isExpanded ? '1px solid var(--border)' : 'none',
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
            History Settings
          </span>
          <span style={{ color: 'var(--text-dim)', fontSize: 'var(--text-sm)' }}>
            {isExpanded ? 'v' : '>'}
          </span>
        </button>
        <button
          type="button"
          className="btn btn-sm btn-primary"
          onClick={handleUpdateClick}
        >
          Update
        </button>
      </div>

      {/* Settings content */}
      {isExpanded && (
        <div
          style={{
            padding: 'var(--space-4)',
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
            gap: 'var(--space-4)',
          }}
        >
          {/* Base Day Offset */}
          <div>
            <label
              htmlFor="baseOffset"
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
              id="baseOffset"
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
              htmlFor="baseField"
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
              id="baseField"
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
              htmlFor="minThreshold"
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
              id="minThreshold"
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
              htmlFor="maxThreshold"
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
              id="maxThreshold"
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
