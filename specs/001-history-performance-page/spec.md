# Feature Specification: History Page with Trade Performance Calculations

**Feature Branch**: `001-history-performance-page`
**Created**: 2026-01-16
**Status**: Draft
**Input**: User description: "History page design draft for trade performance tracking"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - View Trade Performance History (Priority: P1)

As a trader, I want to view my historical trades with calculated performance metrics (D0 through D14) so that I can analyze how my trades performed over time after entry.

**Why this priority**: This is the core functionality - without being able to view performance data, the feature provides no value.

**Independent Test**: Can be fully tested by navigating to the History page and verifying that trades display with calculated performance values for each day offset.

**Acceptance Scenarios**:

1. **Given** I have trades recorded in the system with corresponding historical price data, **When** I navigate to the History page, **Then** I see a table displaying my trades with performance percentages calculated for D0 through D14.
2. **Given** I have a trade with ticker "AAPL" dated 2024-01-15, **When** I view it on the History page, **Then** I see the performance calculated using actual trading day dates (not calendar days) for each offset.
3. **Given** a trade has no corresponding historical price data for its ticker, **When** I view it on the History page, **Then** all Dn columns show null/empty values gracefully.

---

### User Story 2 - Configure Performance Calculation Settings (Priority: P2)

As a trader, I want to configure the base day offset (D0..D14), base OHLC field (open/high/low/close), and MIN%/MAX% thresholds from the Dashboard so that I can customize how performance is calculated according to my trading strategy.

**Why this priority**: Customization allows traders to analyze performance against their actual entry points and risk parameters, making the data actionable.

**Independent Test**: Can be tested by adjusting settings on Dashboard and verifying that History page recalculates performance accordingly.

**Acceptance Scenarios**:

1. **Given** I am on the Dashboard, **When** I select "D1" as the base day offset and "open" as the base OHLC field, **Then** the settings are saved and used for all performance calculations on the History page.
2. **Given** I set MIN% to -10% and MAX% to +20%, **When** a trade's performance reaches the MAX% threshold on D5, **Then** D5 displays the stop value and D6-D14 columns show null.
3. **Given** I change settings on the Dashboard, **When** I navigate to the History page, **Then** the performance values reflect the new settings.

---

### User Story 3 - Position-Aware Performance Calculation (Priority: P2)

As a trader, I want performance calculations to account for my position direction (long vs short) so that gains and losses are correctly reflected regardless of trade direction.

**Why this priority**: Accurate performance attribution is essential for portfolio analysis; incorrect calculations would render the feature misleading.

**Independent Test**: Can be tested by creating long and short trades on the same ticker/date and verifying inverse performance values.

**Acceptance Scenarios**:

1. **Given** I have a long position trade, **When** the price increases from base, **Then** performance shows a positive percentage.
2. **Given** I have a short position trade, **When** the price increases from base, **Then** performance shows a negative percentage (reflecting a loss on the short).
3. **Given** I have both long and short trades for the same ticker on the same date, **When** I view them on History page, **Then** they show opposite performance values.

---

### User Story 4 - Refresh Calculations On Demand (Priority: P3)

As a trader, I want to manually trigger a recalculation of performance data so that I can see updated results after changing settings or when new data is available.

**Why this priority**: Provides user control over when expensive calculations occur, improving perceived performance and user experience.

**Independent Test**: Can be tested by clicking the update button and observing that calculations are refreshed.

**Acceptance Scenarios**:

1. **Given** I change any calculation setting on the Dashboard, **When** the setting is saved, **Then** performance calculations are automatically refreshed using the new settings.
2. **Given** calculations have been cached, **When** I navigate between pages without changing settings, **Then** the cached values are displayed without recalculation.
3. **Given** I am on the History page or Dashboard, **When** I click the "Update" button, **Then** performance calculations are refreshed to pick up any new price data.

---

### Edge Cases

- What happens when a trade_date does not exist in the historical price data? All Dn values display as null.
- What happens when basePrice is zero or missing? Performance shows as null (division by zero is handled).
- What happens when historical_price data has fewer than 15 trading days after trade_date? Available Dn values are calculated; missing days show null.
- What happens when historical_price is nested inside a "historical" wrapper object? The system normalizes the data structure before processing.
- How does the system handle a ticker with no historical_price record at all? All Dn columns show null for that trade.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a History page accessible via the `#/history` route that displays trades in a table format identical to the Trades page.
- **FR-002**: System MUST calculate performance using only `txn_trades` and `config_lv3_quantitatives.historical_price` data sources (no pre-computed values like `txn_price_trend`).
- **FR-003**: System MUST calculate day offsets (D0-D14) using actual trading days from historical price data, not calendar days.
- **FR-004**: System MUST apply position multiplier (+1 for long, -1 for short) to all performance calculations.
- **FR-005**: System MUST provide Dashboard controls for: base day offset (D0-D14), base OHLC field (open/high/low/close), MIN% threshold, MAX% threshold.
- **FR-006**: System MUST persist user settings across page navigations and browser sessions.
- **FR-007**: System MUST stop performance calculation at a day offset when MIN% or MAX% threshold is breached, showing null for subsequent days. When both thresholds could be breached on the same day, MIN% (stop loss) is evaluated first and takes priority.
- **FR-008**: System MUST cache calculated performance data and reuse it during page navigation; cache is invalidated automatically when settings change.
- **FR-009**: System MUST auto-recalculate performance when any setting changes; an "Update" button is provided for manual refresh when new price data may be available.
- **FR-010**: System MUST handle missing or malformed historical price data gracefully by displaying null values.
- **FR-011**: System MUST display performance values in percentage format.
- **FR-012**: System MUST calculate three performance metrics per day offset: perfClose, perfHigh, and perfLow.
- **FR-013**: System MUST default to displaying perfClose as the primary performance value.

### Key Entities

- **Trade**: Represents a trading transaction with attributes: ticker (stock symbol), trade_date (entry date), position (long/short), model, source, notes.
- **Historical Price**: Daily OHLC price data for a ticker with attributes: date, open, high, low, close. Used to calculate performance after trade entry.
- **Performance Settings**: User-configurable calculation parameters: baseOffset (0-14), baseField (open/high/low/close), minThreshold (percentage), maxThreshold (percentage).
- **Calculated Performance**: Computed result for each trade containing: day_offset_performance (array of 15 values), day_offset_target_dates (actual dates for each offset), stop indicators.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can view performance calculations for all their trades within 3 seconds of page load (for up to 500 trades).
- **SC-002**: 100% of trades with valid historical price data display calculated performance values.
- **SC-003**: Users can change calculation settings and see updated results within 5 seconds of triggering recalculation.
- **SC-004**: Performance calculations correctly reflect position direction (verified by long vs short showing inverse values for same market movement).
- **SC-005**: Page navigation between History and other pages completes instantly using cached data (under 500ms).
- **SC-006**: Users can identify which trades hit MIN/MAX thresholds by visual indication in the table.

## Clarifications

### Session 2026-01-16

- Q: What are the default MIN%/MAX% threshold values? → A: Thresholds disabled by default; only perfClose is calculated when thresholds not set.
- Q: When both MIN% and MAX% could be breached on the same day, which takes priority? → A: MIN% (stop loss) is checked first and takes priority.
- Q: When settings change on Dashboard, should History auto-recalculate or require manual Update? → A: Auto-recalculate immediately when any setting changes.

## Assumptions

- MIN% and MAX% thresholds are disabled by default; threshold-based stop logic only activates when user explicitly sets values.
- Historical price data is already populated in `config_lv3_quantitatives.historical_price` for relevant tickers.
- Historical price data represents actual trading days only (no weekends/holidays).
- The existing Trades page UI components can be reused without modification.
- LocalStorage or equivalent browser storage is available for persisting user settings.
- Stop point display will show the actual perfHigh or perfLow value at the threshold breach point (not the threshold value itself).
- D-negative (days before trade_date) display is not included in initial scope; only D0-D14 (forward-looking) is displayed.

## Out of Scope

- Backend batch API for historical price retrieval (frontend will query data source directly).
- Pre-computing or caching performance on the server side.
- Historical price data ingestion or management.
- D-negative (pre-trade date) performance display.
- Export functionality for performance data.
