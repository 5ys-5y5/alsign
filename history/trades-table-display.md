# Trades Table Rendering (Dashboard + Trades pages)

This note summarizes how the Trades table is rendered and populated on:
- http://localhost:3000/#/dashboard
- http://localhost:3000/#/trades

Source files:
- `frontend/src/pages/DashboardPage.jsx`
- `frontend/src/pages/TradesPage.jsx`
- `frontend/src/components/dashboard/TradesTable.jsx`
- `frontend/src/components/table/DataTable.jsx`
- `frontend/src/components/table/ColumnSelector.jsx`
- `frontend/src/components/table/FilterPopover.jsx`
- `frontend/src/components/table/SortHeader.jsx`
- `frontend/src/styles/components.css`

---

## 1) Data source and query behavior

### Dashboard page
- Fetches trades from `GET /dashboard/trades`.
- Query params:
  - `page`, `pageSize`
  - `sortBy`, `sortOrder` (only when sort is active)
  - Filters mapped from UI:
    - `ticker`
    - `model`
    - `source`
    - `position`
    - `tradeDateFrom`, `tradeDateTo` (from daterange filter)
- Default sort: `trade_date` descending.
- No default date cap; the backend receives whatever filter the user applied.
- If API returns zero records, the page shows an error alert:
  - "No trades in database. To populate data: use POST /trades to insert trade records."
- Includes a `tradesRefreshTrigger` (manual refresh callback) but there is no explicit UI button in `TradesTable` for it.

### Trades page
- Fetches trades from `GET /dashboard/trades` with the same base params:
  - `page`, `pageSize`, `sortBy`, `sortOrder`, `ticker`, `model`, `source`, `position`, `tradeDateFrom`, `tradeDateTo`.
- Adds a date guard:
  - If `tradeDateTo` is not supplied, it defaults to today (local date, `en-CA` format).
  - If a user picks a future date, it clamps `tradeDateTo` to today.
- If the API returns zero records (after loading), it shows a warning alert that there are no trades for today.
- Also renders a subscription warning when the user is not paying:
  - "recent trades (last 30 days) are blurred."
  - The table uses the `is_blurred` flag per-row to enforce blur in the UI.

---

## 2) Columns and defaults

The Trades table uses a fixed column definition list:

- `ticker` (string, 110px, default visible)
- `trade_date` (daterange, 170px, default visible)
- `model` (string, 140px, default visible)
- `source` (string, 120px, default visible)
- `position` (string, 110px, default visible)
- `wts` (number, 80px, default visible)
- `d_neg14` ... `d_neg1` (dayoffset, 90px each, default visible)
- `d_pos1` ... `d_pos14` (dayoffset, 90px each, default visible)
- `notes` (string, 220px, NOT default visible)

Column visibility is persisted to local storage (via `getTradesState` / `setTradesState`).

---

## 3) Table layout and structure

`TradesTable` is a thin wrapper around `DataTable` plus the bottom pager.

### 3.1 Table shell + toolbar
- The table is wrapped in `.table-shell` with a border and rounded corners.
- Toolbar row (always visible):
  - Column selector button on the left.
  - Live row count on the right: `X rows` (and `(filtered from Y)` if client-side filtering is active).

### 3.2 Scroll container + sticky header/footer
- The table sits inside `.table-scroll-container`:
  - `max-height: 70vh`
  - `overflow: auto`
- The header (`thead`) is sticky at the top of the scroll container.
- The footer (`tfoot`) is sticky at the bottom when enabled.

### 3.3 Rows and cells
- Each cell uses a fixed width when the column defines `width`.
- Default table styles:
  - `white-space: nowrap`, `text-overflow: ellipsis`, `max-width: 0` (enables clipping).
- `row.is_blurred`:
  - Applies `.row-blurred` (blur + opacity).
  - Each cell shows the literal text "Locked".

---

## 4) Cell rendering rules

`DataTable` renders cell values by type:

- Null/empty value -> `-` (via `.cell-null`).
- `position_*` enum columns -> badge (long/short/undefined).
  - Note: the Trades table uses `position` (string), so it renders as plain text.
- `number` -> `toLocaleString()`.
- `dayoffset` -> percentage with sign:
  - Percent = `value * 100`, fixed to 2 decimals.
  - Adds an up/down arrow glyph for positive/negative values.
  - Positive values use `.text-red`, negative use `.text-blue`.
- JSON-ish columns (not used in Trades table) render as `json`.
- Long strings (> 50 chars) get a truncated span with `title` tooltip.

---

## 5) Sorting

Sorting UI:
- Each header cell uses `SortHeader`.
- Click cycle: none -> ascending -> descending -> none.
- Sort icon reflects state.

Behavior:
- Trades tables run in **server-side sort** mode:
  - `DataTable` does not sort the data client-side.
  - Sort state is passed to the backend (`sortBy`, `sortOrder`).

Default sort:
- `trade_date` descending on both pages.

---

## 6) Filtering

Filtering UI:
- Each header has a filter popover (funnel icon).
- Filter panels are rendered in a portal with fixed positioning.
- Types:
  - `string`: text input (contains match)
  - `daterange`: from/to date inputs
  - `number` / `dayoffset`: text input with range formats

Behavior:
- Trades tables run in **server-side filter** mode:
  - `DataTable` does not filter locally.
  - Filter values are mapped to API query params in the page components.

Trades filters mapping:
- `ticker`, `model`, `source`, `position` -> direct string params.
- `trade_date` -> `tradeDateFrom`, `tradeDateTo`.
- Trades page additionally clamps `tradeDateTo` to today.

---

## 7) Footer statistics

`TradesTable` enables `enableFooterStats`:
- Footer row is sticky at the bottom of the scroll container.
- Stats are computed from the visible data in the table:
  - `ticker`: shows row count.
  - `wts`: finds the day offset (D-14..D14) with the highest average.
  - Each `dayoffset` column: average percentage (value * 100, 2 decimals).
  - Other columns: `-` (placeholder).

---

## 8) Pagination and paging controls

Below the table:
- Summary: "Showing X to Y of Z trades".
- Page size dropdown: 50 / 100 / 200 / 500 / 1000.
- Pager buttons: first, previous, next, last.
  - Disabled when at the start/end.
- Page indicator: "Page N / M".

Paging triggers a server-side refetch (both pages).

