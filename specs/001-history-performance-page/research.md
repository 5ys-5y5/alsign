# Research: History Page with Trade Performance Calculations

**Date**: 2026-01-16
**Feature**: 001-history-performance-page

## Summary

Research on existing implementation patterns and technical decisions for the History page feature.

## Findings

### 1. Existing Implementation Analysis

**Decision**: Extend existing HistoryPage and historyData.js rather than creating new files.

**Rationale**:
- HistoryPage.jsx already exists with caching, loading states, and refresh logic
- historyData.js already implements the complete calculation engine (D0-D14, OHLC caching, threshold logic)
- Backend endpoints (GET /history/trades, POST /history/historical-prices) already exist

**Alternatives considered**:
- Create new HistoryV2Page - rejected (duplicates existing logic)
- Server-side calculations - rejected (spec requires client-side only, no pre-computed values)

### 2. Missing localStorage Functions

**Decision**: Add missing functions to localStorage.js that historyData.js expects.

**Rationale**:
- historyData.js imports `getHistoryCacheToken`, `setHistoryCacheToken`, `getHistorySettings` but these don't exist in localStorage.js
- These functions are essential for settings persistence and cache management

**Functions to add**:
```javascript
// History settings (baseOffset, baseField, minThreshold, maxThreshold)
export function getHistorySettings()
export function setHistorySettings(settings)

// History UI state (selectedColumns, filters, sort, dayOffsetMode)
export function getHistoryState()
export function setHistoryState(state)

// Cache token for invalidation
export function getHistoryCacheToken()
export function setHistoryCacheToken(token)
```

### 3. Routing Pattern

**Decision**: Add `#/history` route as admin-only page.

**Rationale**:
- Matches existing Dashboard pattern (admin-only access)
- History calculations reveal trade performance data
- Consistent with existing route structure

**Alternatives considered**:
- Public route like Trades - rejected (performance data is sensitive)
- Combined with Dashboard - rejected (too much content on one page)

### 4. Settings Panel Location

**Decision**: Add settings panel to DashboardPage, not HistoryPage.

**Rationale**:
- Spec states "settings controllable from Dashboard"
- Dashboard is the admin control center
- Settings changes auto-trigger recalculation on HistoryPage

**Alternatives considered**:
- Settings inline on HistoryPage - rejected (spec requires Dashboard controls)
- Separate settings route - rejected (over-engineering)

### 5. Threshold Evaluation Order

**Decision**: Check MIN% (stop loss) first, then MAX% (profit target).

**Rationale**:
- Clarified with user: MIN% takes priority
- Risk management perspective: protect against losses first

**Implementation**:
```javascript
// In computeHistoryRows, when both thresholds could trigger:
if (minThreshold !== null && minCheck <= minThreshold) {
  stopOffset = offset;  // MIN checked first
} else if (maxThreshold !== null && maxCheck >= maxThreshold) {
  stopOffset = offset;
}
```

### 6. Auto-Recalculation Pattern

**Decision**: Settings changes invalidate cache and trigger auto-recalculation.

**Rationale**:
- Clarified with user: auto-recalculate on settings change
- Manual "Update" button only for fetching new price data

**Implementation**:
- setHistorySettings() calls requestHistoryCacheRefresh()
- HistoryPage subscribes to cache refresh events
- Auto-reload triggered when settings change

## Technical Patterns to Reuse

### From Existing Code

| Pattern | Source | Reuse For |
|---------|--------|-----------|
| localStorage state management | getTradesState/setTradesState | History settings persistence |
| Client-side filtering/sorting | HistoryTable applyFilters/applySort | Already implemented |
| Cache invalidation | requestHistoryCacheRefresh | Settings change trigger |
| OHLC caching | buildTickerCache | Already implemented |
| Performance calculation | computeHistoryRows | Already implemented |
| Day offset columns | TRADES_COLUMNS | Already shared |

### Design System Compliance

| Element | Specification | Source |
|---------|---------------|--------|
| Button height | 32px (btn-sm), 40px (btn-md) | 2_designSystem.ini |
| Spacing | 8px grid (8/12/16/24/32) | 2_designSystem.ini |
| Font weights | 400/500/600 only | 2_designSystem.ini |
| Form inputs | Standard border, 8px radius | Existing forms |

## Conclusions

The feature is largely implemented - the main work is:
1. Adding missing localStorage functions
2. Adding #/history route to AppRouter
3. Creating HistorySettingsPanel for Dashboard
4. Wiring up auto-recalculation on settings change
5. Minor fix to threshold evaluation order (MIN first)
