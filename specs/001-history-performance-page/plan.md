# Implementation Plan: History Page with Trade Performance Calculations

**Branch**: `001-history-performance-page` | **Date**: 2026-01-16 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-history-performance-page/spec.md`

## Summary

Implement a History page (`#/history`) that displays trades from `txn_trades` with client-side calculated performance metrics (D0-D14) using `historical_price` data from `config_lv3_quantitatives`. The page reuses the existing TradesTable UI and adds Dashboard controls for configuring calculation settings (base offset, OHLC field, MIN%/MAX% thresholds). Settings changes trigger auto-recalculation with client-side caching for navigation performance.

## Technical Context

**Language/Version**: JavaScript (ES2020+), Python 3.11+
**Primary Dependencies**: React 18, FastAPI, asyncpg
**Storage**: PostgreSQL (Supabase), localStorage (browser)
**Testing**: Manual testing (existing pattern)
**Target Platform**: Web browser (Chrome, Firefox, Safari)
**Project Type**: Web application (frontend + backend)
**Performance Goals**: Page load with calculations <3s for 500 trades, navigation <500ms
**Constraints**: No UI component libraries, direct SQL only (no ORM/PostgREST)
**Scale/Scope**: ~500 trades, ~500 unique tickers

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Simplicity | PASS | Uses existing patterns, no new abstractions |
| II. Testability | PASS | Client-side calculations can be tested independently |
| III. Single Responsibility | PASS | History service handles calculations, Dashboard handles settings |
| IV. Database Boundary | PASS | Read-only access to txn_trades and config_lv3_quantitatives |
| V. Performance & Observability | PASS | Caching strategy aligns with requirements |
| VI. Data Integrity & Timezone | PASS | Uses existing date handling patterns |
| VII. Security & Secrets | PASS | Uses existing auth patterns |
| VIII. Design System Lock | PASS | Reuses TradesTable, follows 8px grid |
| IX. Structured Error Responses | PASS | Uses existing error patterns |

## Project Structure

### Documentation (this feature)

```text
specs/001-history-performance-page/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
└── tasks.md             # Phase 2 output (not created by /speckit.plan)
```

### Source Code (repository root)

```text
backend/
├── src/
│   ├── routers/
│   │   └── history.py           # GET /history/trades, POST /history/historical-prices (EXISTS)
│   └── main.py                  # Router registration (EXISTS)

frontend/
├── src/
│   ├── components/
│   │   ├── dashboard/
│   │   │   ├── HistoryTable.jsx        # History table component (EXISTS - needs modification)
│   │   │   ├── HistorySettingsPanel.jsx # NEW: Settings controls panel
│   │   │   └── tradesColumns.js        # Column definitions (EXISTS)
│   │   └── AppRouter.jsx               # Route registration (EXISTS - needs #/history route)
│   ├── pages/
│   │   ├── HistoryPage.jsx             # History page (EXISTS - needs modification)
│   │   └── DashboardPage.jsx           # Dashboard page (EXISTS - needs settings panel)
│   └── services/
│       ├── historyData.js              # Calculation logic (EXISTS - needs modification)
│       └── localStorage.js             # Persistence (EXISTS - needs history settings)
```

**Structure Decision**: Web application (Option 2) - extends existing frontend/backend structure.

## Complexity Tracking

No constitution violations requiring justification.

## Implementation Phases

### Phase 1: Backend (Minimal - already exists)

The backend already provides:
- `GET /history/trades` - fetches raw trades without precomputed metrics
- `POST /history/historical-prices` - fetches historical_price for tickers

No backend changes required.

### Phase 2: Frontend Core

1. **Add localStorage functions** for history settings persistence:
   - `getHistorySettings()` / `setHistorySettings()`
   - `getHistoryState()` / `setHistoryState()`
   - `getHistoryCacheToken()` / `setHistoryCacheToken()`

2. **Update historyData.js** calculation logic:
   - Already implements core calculation logic
   - Fix threshold evaluation order (MIN% first per clarification)
   - Ensure auto-recalculation on settings change

3. **Add route** to AppRouter.jsx:
   - Add `#/history` route pointing to HistoryPage
   - Make it admin-only (matches Dashboard pattern)

### Phase 3: Settings Panel

1. **Create HistorySettingsPanel.jsx** component:
   - Base Day Offset dropdown (D0-D14)
   - Base OHLC Field dropdown (open/high/low/close)
   - MIN% threshold input (numeric, optional)
   - MAX% threshold input (numeric, optional)
   - Settings persist to localStorage
   - Changes trigger cache invalidation → auto-recalculation

2. **Add to DashboardPage.jsx**:
   - History Settings section below KPIs
   - Collapsible panel to reduce clutter

### Phase 4: Integration & Polish

1. **Update HistoryPage.jsx**:
   - Subscribe to settings changes
   - Auto-refresh on settings change
   - Display current settings in header

2. **Update HistoryTable.jsx**:
   - Pass threshold values for visual indication (FR-007)
   - Add threshold breach styling

## Key Implementation Details

### Calculation Formula (from spec)

```javascript
// Base price from configured offset and field
basePrice = OHLC[D{baseOffset}][baseField]

// Performance metrics per day
perfClose = (Dn.close - basePrice) / basePrice * positionMultiplier
perfHigh = (Dn.high - basePrice) / basePrice * positionMultiplier
perfLow = (Dn.low - basePrice) / basePrice * positionMultiplier

// Position multiplier
positionMultiplier = position === 'short' ? -1 : 1
```

### Threshold Logic (from clarifications)

1. Thresholds disabled by default (no stop logic)
2. When both enabled, MIN% (stop loss) evaluated first
3. Stop point shows actual perf value (not threshold value)
4. Subsequent Dn columns show null after stop

### Caching Strategy

- Cache invalidated on settings change → triggers auto-recalculation
- Cache preserved during page navigation
- Manual "Update" button for refreshing data (not settings)

### Settings Defaults

| Setting | Default | Range |
|---------|---------|-------|
| baseOffset | 0 | 0-14 |
| baseField | "close" | open/high/low/close |
| minThreshold | null (disabled) | -100 to 0 |
| maxThreshold | null (disabled) | 0 to 1000 |

## Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `frontend/src/services/localStorage.js` | MODIFY | Add history settings/state/cache functions |
| `frontend/src/services/historyData.js` | MODIFY | Fix threshold order, settings subscription |
| `frontend/src/components/AppRouter.jsx` | MODIFY | Add #/history route |
| `frontend/src/components/dashboard/HistorySettingsPanel.jsx` | CREATE | Settings control panel |
| `frontend/src/pages/DashboardPage.jsx` | MODIFY | Add settings panel section |
| `frontend/src/pages/HistoryPage.jsx` | MODIFY | Settings change subscription |
| `frontend/src/components/dashboard/HistoryTable.jsx` | MODIFY | Threshold breach styling |

## Dependencies

- Existing: React, FastAPI, asyncpg, Supabase
- No new dependencies required
