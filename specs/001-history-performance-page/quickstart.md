# Quickstart: History Page with Trade Performance Calculations

**Date**: 2026-01-16
**Feature**: 001-history-performance-page

## Prerequisites

- Backend running on port 8000
- Frontend running on port 5173 (or deployed)
- Admin user authenticated
- Trades exist in `txn_trades` table
- Historical prices exist in `config_lv3_quantitatives.historical_price`

## Usage Scenarios

### Scenario 1: View Trade Performance (P1)

1. Login as admin
2. Navigate to `#/history`
3. View table with trades and D0-D14 performance columns
4. Toggle between "PERFORM" and "HISTORY" modes using the mode switch
5. Use column selector to show/hide specific day offsets
6. Filter by ticker, date range, or position
7. Sort by any column

**Expected**: Each trade shows calculated performance percentages for D0-D14 based on trading days.

### Scenario 2: Configure Calculation Settings (P2)

1. Login as admin
2. Navigate to `#/dashboard`
3. Locate "History Settings" panel
4. Change settings:
   - Base Day Offset: Select D0-D14 (default: D0)
   - Base OHLC: Select open/high/low/close (default: close)
   - MIN%: Enter stop loss threshold (e.g., -10) or leave empty to disable
   - MAX%: Enter profit target threshold (e.g., 20) or leave empty to disable
5. Settings auto-save to localStorage

**Expected**: Settings persist and apply to History page calculations.

### Scenario 3: Auto-Recalculate on Settings Change

1. Have History page open in another tab
2. In Dashboard, change a setting (e.g., Base OHLC from "close" to "open")
3. Switch to History tab

**Expected**: Performance values automatically recalculate using new settings. No manual refresh needed.

### Scenario 4: Threshold Stop Logic

1. Configure MIN% = -10, MAX% = 20 in Dashboard
2. Navigate to History page
3. Find a trade with significant price movement

**Expected**:
- If perfLow drops below -10% on any day, that day shows the stop value and subsequent days show null
- If perfHigh rises above +20% on any day (and MIN not hit first), that day shows the stop value
- MIN% (stop loss) is always evaluated before MAX% (profit target)

### Scenario 5: Position-Aware Calculations

1. Find trades with both long and short positions for the same ticker
2. Compare performance values

**Expected**:
- Long position: price increase = positive %, price decrease = negative %
- Short position: price increase = negative %, price decrease = positive %

### Scenario 6: Manual Refresh for New Data

1. Navigate to History page
2. Click "Update" button in header

**Expected**: Fresh data fetched from backend, calculations redone with current settings.

## Verification Checklist

| Check | Command/Action | Expected Result |
|-------|----------------|-----------------|
| Route exists | Navigate to `#/history` | Page loads without error |
| Data displays | View History table | Trades with D0-D14 columns |
| Settings panel | Go to Dashboard | History Settings section visible |
| Settings persist | Change setting, refresh page | Setting retained |
| Auto-recalc | Change setting in Dashboard | History page updates |
| Threshold stop | Set MIN%, find trade | Subsequent days show null after stop |
| Position multiplier | Compare long vs short | Inverse performance values |
| Cache works | Navigate away and back | Instant load (no recalculation) |
| Update button | Click Update | Fresh data loaded |

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| "No history data" | No trades in txn_trades | Add trades via POST /trades |
| All Dn columns null | Missing historical_price | Verify ticker exists in config_lv3_quantitatives |
| Settings not saving | localStorage disabled | Check browser settings |
| Calculations not updating | Cache not invalidating | Click Update or refresh page |
| 401 Unauthorized | Not logged in as admin | Login with admin credentials |
