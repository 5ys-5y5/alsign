# Tasks: History Page with Trade Performance Calculations

**Input**: Design documents from `/specs/001-history-performance-page/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Not requested in specification - using manual testing (existing pattern).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Web app**: `backend/src/`, `frontend/src/`
- Backend already complete - no changes required
- Frontend modifications only

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Add missing localStorage functions required by all user stories

- [x] T001 Add getHistorySettings() function to frontend/src/services/localStorage.js - returns {baseOffset, baseField, minThreshold, maxThreshold} with defaults {0, 'close', null, null}
- [x] T002 Add setHistorySettings(settings) function to frontend/src/services/localStorage.js - persists to 'ui.history_settings' key and triggers cache refresh
- [x] T003 [P] Add getHistoryState() function to frontend/src/services/localStorage.js - returns {selectedColumns, filters, sort, dayOffsetMode}
- [x] T004 [P] Add setHistoryState(state) function to frontend/src/services/localStorage.js - persists to 'ui.history_state' key
- [x] T005 [P] Add getHistoryCacheToken() function to frontend/src/services/localStorage.js - returns timestamp from 'ui.history_cache_token'
- [x] T006 [P] Add setHistoryCacheToken(token) function to frontend/src/services/localStorage.js - stores timestamp

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Add route and fix calculation logic - MUST complete before user stories can be verified

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T007 Add HistoryPage import to frontend/src/components/AppRouter.jsx
- [x] T008 Add history route to ROUTES array in frontend/src/components/AppRouter.jsx - { id: 'history', label: 'history', path: '#/history', component: HistoryPage, adminOnly: true }
- [x] T009 Fix threshold evaluation order in frontend/src/services/historyData.js - change to check MIN% (stop loss) BEFORE MAX% (profit target) per FR-007 clarification

**Checkpoint**: Foundation ready - route accessible and calculations correct

---

## Phase 3: User Story 1 - View Trade Performance History (Priority: P1) 🎯 MVP

**Goal**: Users can navigate to #/history and view trades with D0-D14 performance calculations

**Independent Test**: Navigate to #/history as admin, verify table displays trades with performance percentages for each day offset

### Implementation for User Story 1

- [x] T010 [US1] Verify HistoryPage.jsx correctly imports getHistoryState, setHistoryState, getHistorySettings from localStorage.js - fix import paths if needed in frontend/src/pages/HistoryPage.jsx
- [x] T011 [US1] Verify HistoryTable.jsx correctly imports getHistoryState, setHistoryState from localStorage.js - fix import paths if needed in frontend/src/components/dashboard/HistoryTable.jsx
- [x] T012 [US1] Verify historyData.js correctly imports getHistoryCacheToken, setHistoryCacheToken, getHistorySettings from localStorage.js - fix import paths if needed in frontend/src/services/historyData.js
- [x] T013 [US1] Test History page loads and displays trades with calculated D0-D14 values

**Checkpoint**: User Story 1 complete - basic History page functional with performance calculations

---

## Phase 4: User Story 2 - Configure Performance Calculation Settings (Priority: P2)

**Goal**: Users can configure baseOffset, baseField, MIN%, MAX% settings from Dashboard that control calculations

**Independent Test**: Change settings in Dashboard, verify History page recalculates using new settings

### Implementation for User Story 2

- [x] T014 [US2] Create HistorySettingsPanel.jsx component in frontend/src/components/dashboard/HistorySettingsPanel.jsx with:
  - Base Day Offset dropdown (D0-D14, default D0)
  - Base OHLC Field dropdown (open/high/low/close, default close)
  - MIN% threshold input (numeric, empty for disabled)
  - MAX% threshold input (numeric, empty for disabled)
- [x] T015 [US2] Add settings persistence to HistorySettingsPanel - use setHistorySettings() on change, trigger requestHistoryCacheRefresh() for auto-recalculation
- [x] T016 [US2] Import and add HistorySettingsPanel to DashboardPage.jsx in frontend/src/pages/DashboardPage.jsx - add below KPI cards section
- [x] T017 [US2] Style HistorySettingsPanel following design system - 8px grid spacing, btn-sm (32px height), font-weight 400/500/600 only
- [x] T018 [US2] Test settings changes trigger auto-recalculation on History page

**Checkpoint**: User Story 2 complete - settings configurable from Dashboard with auto-recalculation

---

## Phase 5: User Story 3 - Position-Aware Performance Calculation (Priority: P2)

**Goal**: Performance calculations correctly apply position multiplier (+1 long, -1 short)

**Independent Test**: Create long and short trades for same ticker/date, verify inverse performance values

### Implementation for User Story 3

- [x] T019 [US3] Verify getPositionMultiplier() function in frontend/src/services/historyData.js returns -1 for 'short', +1 otherwise
- [x] T020 [US3] Verify computeHistoryRows() applies positionMultiplier to perfClose, perfHigh, perfLow calculations in frontend/src/services/historyData.js
- [x] T021 [US3] Test with sample long and short trades - verify long shows +% for price increase, short shows -% for same price increase

**Checkpoint**: User Story 3 complete - position direction correctly reflected in calculations

---

## Phase 6: User Story 4 - Refresh Calculations On Demand (Priority: P3)

**Goal**: Users can manually refresh calculations via Update button when new price data available

**Independent Test**: Click Update button, verify fresh data fetched and calculations refreshed

### Implementation for User Story 4

- [x] T022 [US4] Verify Update button in HistoryPage.jsx header calls requestHistoryCacheRefresh() and triggers loadHistoryDataset() in frontend/src/pages/HistoryPage.jsx
- [x] T023 [US4] Verify cache is preserved during page navigation (no recalculation on navigate away/back)
- [x] T024 [US4] Test Update button fetches fresh trades and historical prices, recalculates all rows

**Checkpoint**: User Story 4 complete - manual refresh available for fetching new data

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Visual improvements and validation

- [x] T025 [P] Add visual indication for threshold breach in HistoryTable.jsx - style cells where MIN/MAX was hit in frontend/src/components/dashboard/HistoryTable.jsx
- [x] T026 [P] Update HistoryPage header to display current settings (Base D{n} • {OHLC} • MIN {x}% • MAX {y}%) in frontend/src/pages/HistoryPage.jsx
- [x] T027 Run quickstart.md validation - verify all scenarios in specs/001-history-performance-page/quickstart.md

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3-6)**: All depend on Foundational phase completion
  - US1 (P1) → Core viewing capability (MVP)
  - US2 (P2) → Settings configuration
  - US3 (P2) → Position awareness (can parallel with US2)
  - US4 (P3) → Manual refresh
- **Polish (Phase 7)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories - **MVP**
- **User Story 2 (P2)**: Can start after Foundational (Phase 2) - Enhances US1 but US1 works without it
- **User Story 3 (P2)**: Can start after Foundational (Phase 2) - Already implemented in historyData.js, just needs verification
- **User Story 4 (P3)**: Can start after Foundational (Phase 2) - Already implemented, just needs verification

### Within Each User Story

- Verify existing code works before modifications
- Test after each significant change
- Story complete before moving to next priority

### Parallel Opportunities

- T003, T004, T005, T006 (localStorage functions) can run in parallel
- US2 and US3 can run in parallel after US1 is verified
- T025, T026 (polish tasks) can run in parallel

---

## Parallel Example: Phase 1 Setup

```bash
# Launch parallel localStorage tasks:
Task: "T003 Add getHistoryState() function"
Task: "T004 Add setHistoryState(state) function"
Task: "T005 Add getHistoryCacheToken() function"
Task: "T006 Add setHistoryCacheToken(token) function"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (localStorage functions)
2. Complete Phase 2: Foundational (route + threshold fix)
3. Complete Phase 3: User Story 1 (verify page works)
4. **STOP and VALIDATE**: Navigate to #/history, verify calculations display
5. Deploy/demo if ready

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. Add User Story 1 → Test independently → Deploy/Demo (MVP!)
3. Add User Story 2 → Settings panel → Deploy/Demo
4. Add User Story 3 → Position verification → Deploy/Demo
5. Add User Story 4 → Update button → Deploy/Demo
6. Polish → Visual improvements → Final Deploy

### Notes

- Most functionality already exists - tasks focus on wiring and verification
- Backend is complete - no backend tasks needed
- Key risk: localStorage functions missing - must add in Setup phase
- historyData.js has complete calculation logic - verify and fix threshold order

---

## Task Summary

| Phase | Tasks | Parallel Tasks |
|-------|-------|----------------|
| Phase 1: Setup | 6 | 4 |
| Phase 2: Foundational | 3 | 0 |
| Phase 3: US1 (P1) | 4 | 0 |
| Phase 4: US2 (P2) | 5 | 0 |
| Phase 5: US3 (P2) | 3 | 0 |
| Phase 6: US4 (P3) | 3 | 0 |
| Phase 7: Polish | 3 | 2 |
| **Total** | **27** | **6** |

**MVP Scope**: Phases 1-3 (13 tasks) for basic History page with calculations
