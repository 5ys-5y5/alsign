# Tasks: FastAPI Financial Data API Backend System

**Input**: Design documents from `/specs/001-fastapi-financial-data-api/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Tests are OPTIONAL - only included if explicitly requested. This specification does not explicitly request TDD, so test tasks are minimal.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

Based on plan.md, this is a **web application** structure:
- Backend: `backend/src/`, `backend/tests/`
- Frontend: `frontend/src/`, `frontend/tests/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [ ] T001 Create backend project structure with directories: backend/src/{database,models,services,routers,middleware,utils}, backend/tests/{contract,integration,unit}
- [ ] T002 Initialize Python project with requirements.txt including: fastapi==0.104.1, uvicorn[standard]==0.24.0, asyncpg==0.29.0, pydantic==2.5.0, httpx==0.25.0, python-dateutil==2.8.2, pytest==7.4.3, pytest-asyncio==0.21.1
- [ ] T003 [P] Create frontend project structure with directories: frontend/src/{components,pages,services,styles,assets}, frontend/tests/ui
- [ ] T004 [P] Configure .gitignore for Python (venv/, __pycache__/, *.pyc, .env), frontend (node_modules/, dist/, .env.local)
- [ ] T005 [P] Create .env.example with DATABASE_URL, FMP_API_KEY, FMP_BASE_URL, LOG_LEVEL, ENVIRONMENT placeholders
- [ ] T006 [P] Configure code quality tools: create pyproject.toml with black and ruff configurations

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [ ] T007 Implement database connection pool in backend/src/database/connection.py using asyncpg.create_pool()
- [ ] T008 [P] Create configuration loader in backend/src/config.py using pydantic-settings for environment variables
- [ ] T009 [P] Implement structured logging formatter in backend/src/services/utils/logging_utils.py with fixed 1-line format: `[endpoint | phase] elapsed=Xms | progress=done/total(pct%) | ...`
- [ ] T010 [P] Create datetime utilities in backend/src/services/utils/datetime_utils.py with UTC parsing, timezone enforcement, trading day calculation functions
- [ ] T011 [P] Create batch utilities in backend/src/services/utils/batch_utils.py with dynamic batch sizing and rate limit calculation
- [ ] T012 [P] Implement ErrorCode enum in backend/src/models/domain_models.py with: POLICY_NOT_FOUND, INVALID_POLICY, INVALID_CONSENSUS_DATA, INVALID_PRICE_TREND_RANGE, METRIC_NOT_FOUND, EVENT_ROW_NOT_FOUND, AMBIGUOUS_EVENT_DATE, INTERNAL_ERROR
- [ ] T013 [P] Create base response models in backend/src/models/response_models.py: ErrorResponse, Summary, Counters schemas
- [ ] T014 [P] Implement request logging middleware in backend/src/middleware/logging_middleware.py to inject reqId and log request/response
- [ ] T015 Create FastAPI application in backend/src/main.py with CORS, middleware registration, health check endpoint
- [ ] T016 [P] Implement external API client with rate limiting in backend/src/services/external_api.py using httpx.AsyncClient and sliding window rate limiter
- [ ] T017 [P] Create trading day calculator in backend/src/services/utils/datetime_utils.py: is_trading_day(), next_trading_day(), calculate_dayOffset_dates() using config_lv3_market_holidays

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Collect Market Foundation Data (Priority: P1) 🎯 MVP

**Goal**: Fetch and store market holidays, company targets, analyst consensus, and earnings data from FMP APIs with two-phase consensus processing

**Independent Test**: Call `GET /sourceData` with mode=holiday,target,consensus,earning and verify data is upserted to config_lv3_market_holidays, config_lv3_targets, evt_consensus (with Phase 2 prev/direction fields populated), evt_earning

### Implementation for User Story 1

- [ ] T018 [P] [US1] Create database query module for holidays in backend/src/database/queries/holidays.py with upsert_market_holidays() SQL function
- [ ] T019 [P] [US1] Create database query module for targets in backend/src/database/queries/targets.py with upsert_company_targets() SQL function
- [ ] T020 [P] [US1] Create database query module for consensus in backend/src/database/queries/consensus.py with upsert_consensus_phase1(), select_partition(), update_consensus_phase2() SQL functions
- [ ] T021 [P] [US1] Create database query module for earnings in backend/src/database/queries/earning.py with insert_earning_events() SQL function (insert-only with ON CONFLICT DO NOTHING)
- [ ] T022 [P] [US1] Create request models in backend/src/models/request_models.py: SourceDataQueryParams with mode, past, calc_mode, calc_scope, tickers, from, to, partitions validation
- [ ] T023 [P] [US1] Create response models in backend/src/models/response_models.py: SourceDataResponse, ModeResult, ConsensusResult, PhaseCounters schemas
- [ ] T024 [US1] Implement getHolidays function in backend/src/services/source_data_service.py: fetch FMP holidays API, parse, call holidays.py upsert
- [ ] T025 [US1] Implement getTargets function in backend/src/services/source_data_service.py: fetch FMP company screener, filter isActivelyTrading=true, call targets.py upsert
- [ ] T026 [US1] Implement getConsensus Phase 1 in backend/src/services/source_data_service.py: fetch FMP consensus API for tickers in config_lv3_targets, call consensus.py upsert_phase1, track affected partitions
- [ ] T027 [US1] Implement getConsensus Phase 2 in backend/src/services/source_data_service.py: determine target partitions based on calc_mode/calc_scope, for each partition: select rows sorted by event_date DESC, calculate prev values/direction, call consensus.py update_phase2
- [ ] T028 [US1] Implement getEarning function in backend/src/services/source_data_service.py: fetch future 28 days (4×7-day windows), optionally fetch past 5 years in 7-day chunks when past=true, call earning.py insert with ON CONFLICT DO NOTHING
- [ ] T029 [US1] Implement GET /sourceData router in backend/src/routers/source_data.py: validate mode/calc_mode/calc_scope parameters, execute modes in default order (holiday→target→consensus→earning), aggregate results, return 200 with SourceDataResponse
- [ ] T030 [US1] Add validation in backend/src/routers/source_data.py: return 400 for invalid mode values, missing calc_scope when calc_mode=maintenance, missing required parameters for each calc_scope
- [ ] T031 [US1] Implement ETA calculation and progress logging in backend/src/services/source_data_service.py for each mode using structured log format with elapsed, progress, eta, rate, batch, counters

**Checkpoint**: At this point, User Story 1 should be fully functional - can collect all foundation data from FMP APIs and store with proper consensus change tracking

---

## Phase 4: User Story 2 - Consolidate Events from Multiple Sources (Priority: P2)

**Goal**: Auto-discover evt_* tables, consolidate into txn_events, enrich with sector/industry from config_lv3_targets

**Independent Test**: Populate evt_consensus and evt_earning, call `POST /setEventsTable`, verify txn_events has all events with source/source_id and enriched sector/industry

### Implementation for User Story 2

- [ ] T032 [P] [US2] Create database query module for events in backend/src/database/queries/events.py with discover_evt_tables(), select_events_from_table(), upsert_txn_events(), update_sector_industry() SQL functions
- [ ] T033 [P] [US2] Create request models in backend/src/models/request_models.py: SetEventsTableQueryParams with overwrite, dryRun, schema, table validation (table must match evt_* pattern)
- [ ] T034 [P] [US2] Create response models in backend/src/models/response_models.py: SetEventsTableResponse, TableProcessingResult schemas
- [ ] T035 [US2] Implement table discovery in backend/src/services/events_service.py: query information_schema for tables matching evt_% pattern in specified schema, filter by table parameter if provided
- [ ] T036 [US2] Implement event extraction in backend/src/services/events_service.py: for each discovered table, SELECT id as source_id, ticker, event_date, extract source from table name, batch by DB_UPSERT_BATCH_SIZE=1000
- [ ] T037 [US2] Implement event consolidation in backend/src/services/events_service.py: INSERT INTO txn_events (ticker, event_date, source, source_id) ON CONFLICT (ticker, event_date, source, source_id) DO NOTHING, track inserts/conflicts
- [ ] T038 [US2] Implement sector/industry enrichment in backend/src/services/events_service.py: LEFT JOIN config_lv3_targets on ticker, UPDATE txn_events SET sector=targets.sector, industry=targets.industry based on overwrite flag (false=NULL only, true=NULL+mismatched)
- [ ] T039 [US2] Implement POST /setEventsTable router in backend/src/routers/events.py: validate parameters, call events_service, handle dryRun mode (return projected changes without DB modification), return 200 with SetEventsTableResponse
- [ ] T040 [US2] Add validation in backend/src/routers/events.py: return 400 if specified table doesn't match evt_* pattern or schema doesn't exist

**Checkpoint**: At this point, User Story 2 should be fully functional - can consolidate multiple evt_* tables into unified txn_events with enrichment

---

## Phase 5: User Story 3 - Calculate Quantitative and Qualitative Value Metrics (Priority: P2)

**Goal**: Calculate value_quantitative (financial ratios grouped by domain), value_qualitative (consensusSignal), position_*, disparity_* for events in txn_events

**Independent Test**: Ensure txn_events has events with ticker/event_date/source, call `POST /backfillEventsTable`, verify value_quantitative contains PER/PBR/ROE grouped by domain, value_qualitative contains consensusSignal with direction/last/prev/delta, position_* and disparity_* are calculated

### Implementation for User Story 3

- [ ] T041 [P] [US3] Create database query module for metrics in backend/src/database/queries/metrics.py with select_metric_definitions(), select_events_for_valuation(), update_event_valuations() SQL functions
- [ ] T042 [P] [US3] Create request models in backend/src/models/request_models.py: BackfillEventsTableQueryParams with overwrite validation
- [ ] T043 [P] [US3] Create response models in backend/src/models/response_models.py: BackfillEventsTableResponse, EventProcessingResult schemas with quantitative/qualitative status
- [ ] T044 [US3] Implement metric loading in backend/src/services/valuation_service.py: query config_lv2_metric WHERE domain LIKE 'quantitative-%' OR domain LIKE 'qualitative-%', group by domain suffix
- [ ] T045 [US3] Implement quantitative calculation in backend/src/services/valuation_service.py: fetch quarterly financials from FMP, calculate TTM (4 quarters or partial avg×4), calculate metrics per domain (valuation, profitability, momentum, risk, dilution), generate value_quantitative jsonb with _meta (date_range, calcType=TTM_fullQuarter/TTM_partialQuarter, count)
- [ ] T046 [US3] Implement qualitative calculation in backend/src/services/valuation_service.py: extract consensusSignal from evt_consensus Phase 2 data (direction, last={price_target, price_when_posted}, prev={price_target_prev, price_when_posted_prev}, delta=last-prev, deltaPct=(delta/prev)×100), set delta/deltaPct=null when prev doesn't exist
- [ ] T047 [US3] Implement position calculation in backend/src/services/valuation_service.py: extract priceQuantitative from value_quantitative, extract priceQualitative from value_qualitative, compare with current price: position_quantitative="long" if priceQuantitative>price else "short" if <price else "undefined", same for position_qualitative
- [ ] T048 [US3] Implement disparity calculation in backend/src/services/valuation_service.py: disparity_quantitative = (priceQuantitative / price) - 1, disparity_qualitative = (priceQualitative / price) - 1
- [ ] T049 [US3] Implement partial vs full update logic in backend/src/services/valuation_service.py: when overwrite=false, use jsonb_set to update only NULL keys within value_* fields; when overwrite=true, fully replace value_* fields
- [ ] T050 [US3] Implement POST /backfillEventsTable router in backend/src/routers/events.py: validate overwrite parameter, call valuation_service for all events in txn_events, return HTTP 207 Multi-Status with per-record results and summary
- [ ] T051 [US3] Add error handling in backend/src/services/valuation_service.py: skip events with missing required data (log as skip), return error codes (INVALID_CONSENSUS_DATA, METRIC_NOT_FOUND, INTERNAL_ERROR)

**Checkpoint**: At this point, User Story 3 should be fully functional - can calculate comprehensive valuation metrics for all events

---

## Phase 6: User Story 4 - Generate Price Trend Time Series (Priority: P2)

**Goal**: Generate price_trend arrays with dayOffset-indexed OHLC data from countStart to countEnd trading days, with progressive null-filling for future dates

**Independent Test**: Ensure txn_events has populated records, verify price_trend field contains arrays from dayOffset countStart to countEnd with OHLC data (past filled, future nulls)

### Implementation for User Story 4

- [ ] T052 [P] [US4] Create database query module for policies in backend/src/database/queries/policies.py with select_policy(), parse_policy_json() functions
- [ ] T053 [US4] Implement policy loading in backend/src/services/valuation_service.py (or create price_trend_service.py): query config_lv0_policy WHERE function='fillPriceTrend_dateRange', extract countStart/countEnd, return error POLICY_NOT_FOUND if missing
- [ ] T054 [US4] Implement dayOffset scaffold generation in backend/src/services/valuation_service.py: for each event, call calculate_dayOffset_dates(event_date, countStart, countEnd, 'NASDAQ', db_pool) from datetime_utils, generate array of {dayOffset, targetDate, open:null, high:null, low:null, close:null}
- [ ] T055 [US4] Implement OHLC fetch range calculation in backend/src/services/valuation_service.py: query config_lv0_policy WHERE function='priceEodOHLC_dateRange', group events by ticker, calculate per-ticker range as (min_event_date + countStart) to (max_event_date + countEnd)
- [ ] T056 [US4] Implement OHLC API batching in backend/src/services/valuation_service.py: for each ticker, call FMP historical OHLC API once with full date range, respect rate limits using external_api rate limiter
- [ ] T057 [US4] Implement OHLC matching in backend/src/services/valuation_service.py: for each event's price_trend array, match targetDate with OHLC response by date, fill open/high/low/close values, keep future dates as null (progressive null-filling)
- [ ] T058 [US4] Implement price_trend update in backend/src/services/valuation_service.py: UPDATE txn_events SET price_trend=$1 WHERE (ticker, source, source_id, event_day_utc_date) matches, return error EVENT_ROW_NOT_FOUND if 0 rows, AMBIGUOUS_EVENT_DATE if 2+ rows
- [ ] T059 [US4] Add validation in backend/src/services/valuation_service.py: ensure event_date maps to dayOffset=0 (next trading day if event_date is non-trading), verify weekends and NASDAQ holidays are skipped using is_trading_day()

**Checkpoint**: At this point, User Story 4 should be fully functional - price trends are filled with trading-day-adjusted OHLC data

---

## Phase 7: User Story 5 - Aggregate Analyst Performance Metrics (Priority: P3)

**Goal**: Group consensus events by (analyst_name, analyst_company), calculate return distributions per dayOffset, upsert to config_lv3_analyst

**Independent Test**: Ensure txn_events has consensusSignal with analyst metadata and price_trend, call `POST /fillAnalyst`, verify config_lv3_analyst is populated with performance statistics (mean, median, quartiles, stddev, count per dayOffset)

### Implementation for User Story 5

- [ ] T060 [P] [US5] Create database query module for analysts in backend/src/database/queries/analyst.py with select_consensus_events(), upsert_analyst_performance() using generated keys (analyst_name_key, analyst_company_key) SQL functions
- [ ] T061 [P] [US5] Create response models in backend/src/models/response_models.py: FillAnalystResponse, AnalystGroupResult schemas
- [ ] T062 [US5] Implement policy validation in backend/src/services/analyst_service.py: query config_lv0_policy WHERE function='fillPriceTrend_dateRange', return error POLICY_NOT_FOUND if missing, extract countStart/countEnd
- [ ] T063 [US5] Implement event loading in backend/src/services/analyst_service.py: SELECT FROM txn_events WHERE source='evt_consensus' AND (analyst_name IS NOT NULL OR analyst_company IS NOT NULL), skip events where both are NULL, count as events_skipped_both_null_analyst
- [ ] T064 [US5] Implement analyst grouping in backend/src/services/analyst_service.py: GROUP BY (analyst_name, analyst_company), prepare generated keys for upsert: analyst_name_key=COALESCE(analyst_name,'__NULL__'), analyst_company_key=COALESCE(analyst_company,'__NULL__')
- [ ] T065 [US5] Implement priceTrend validation in backend/src/services/analyst_service.py: for each event, verify price_trend array has all dayOffsets from countStart to countEnd, return error INVALID_PRICE_TREND_RANGE if mismatch
- [ ] T066 [US5] Implement return calculation in backend/src/services/analyst_service.py: for each dayOffset, extract basePrice=consensusSignal.last.price_when_posted, extract close=price_trend[dayOffset].close, calculate return=(close/basePrice)-1, exclude samples where close=null or basePrice=null/0
- [ ] T067 [US5] Implement statistics calculation in backend/src/services/analyst_service.py: query config_lv2_metric WHERE domain='internal(qual)' AND base_metric_id='priceTrendReturnSeries', for each dayOffset return distribution: calculate mean, median, 1stQuartile (p25), 3rdQuartile (p75), InterquartileRange (p75-p25), standardDeviation, count, optionally ConfidenceInterval and ProficiencyRate if metric definitions exist
- [ ] T068 [US5] Implement analyst upsert in backend/src/services/analyst_service.py: INSERT INTO config_lv3_analyst (analyst_name, analyst_company, performance) VALUES ... ON CONFLICT (analyst_name_key, analyst_company_key) DO UPDATE SET performance=$1, never write to analyst_name_key/analyst_company_key (DB-generated)
- [ ] T069 [US5] Implement POST /fillAnalyst router in backend/src/routers/analyst.py: call analyst_service, return HTTP 207 Multi-Status with per-group results and summary (total_events_loaded, events_skipped_both_null_analyst, total_groups, groups_success, groups_failed)
- [ ] T070 [US5] Add error handling in backend/src/services/analyst_service.py: log POLICY_CONFLICT_DB_SCHEMA warning if guideline conflicts with DB constraints

**Checkpoint**: At this point, User Story 5 should be fully functional - analyst performance metrics are aggregated and stored

---

## Phase 8: User Story 6 - Manage Condition Groups for Event Filtering (Priority: P3)

**Goal**: Create UI for selecting column (source/sector/industry) and value, entering condition name, bulk updating txn_events.condition field

**Independent Test**: Use UI to select column="source", value="evt_consensus", name="conAll", verify all txn_events rows with source=evt_consensus have condition="conAll"

### Implementation for User Story 6

- [ ] T071 [P] [US6] Create API endpoint GET /conditionGroups/columns in backend/src/routers/conditionGroup.py: return list of allowed columns ["source", "sector", "industry"]
- [ ] T072 [P] [US6] Create API endpoint GET /conditionGroups/values in backend/src/routers/conditionGroup.py: accept column parameter, return SELECT DISTINCT {column} FROM txn_events WHERE {column} IS NOT NULL
- [ ] T073 [P] [US6] Create API endpoint GET /conditionGroups in backend/src/routers/conditionGroup.py: return existing condition groups (query txn_events for distinct condition values with associated column/value combinations)
- [ ] T074 [P] [US6] Create API endpoint POST /conditionGroups in backend/src/routers/conditionGroup.py: accept {column, value, name}, validate name is non-empty after trim, UPDATE txn_events SET condition=$name WHERE {column}=$value, require explicit confirmation parameter
- [ ] T075 [P] [US6] Create API endpoint DELETE /conditionGroups/{name} in backend/src/routers/conditionGroup.py: UPDATE txn_events SET condition=NULL WHERE condition=$name
- [ ] T076 [US6] Create ConditionGroupForm component in frontend/src/components/forms/ConditionGroupForm.js: dropdown for column selection, dropdown for value selection (populated via API), text input for condition name, submit button with confirmation
- [ ] T077 [US6] Create ConditionGroupPage in frontend/src/pages/ConditionGroupPage.js: render ConditionGroupForm, display existing condition groups in table with edit/delete buttons, handle API calls to backend
- [ ] T078 [US6] Add validation in frontend/src/components/forms/ConditionGroupForm.js: prevent empty condition names, show confirmation dialog before bulk update with row count estimate

**Checkpoint**: At this point, User Story 6 should be fully functional - can create/update/delete condition groups via UI

---

## Phase 9: User Story 7 - View Dashboards with Performance Metrics (Priority: P3)

**Goal**: Display KPI cards, performance summary table (txn_events), day-offset metrics table with filters/sorts/column selection persisted to localStorage

**Independent Test**: Navigate to /dashboard route, verify KPI cards show coverage/data freshness, performance table displays txn_events with working filters/sorts, day-offset table shows aggregated returns

### Implementation for User Story 7

- [ ] T079 [P] [US7] Create API endpoint GET /dashboard/kpis in backend/src/routers/dashboard.py: return {coverage: COUNT(*) FROM config_lv3_targets, dataFreshness: MAX(updated_at) FROM config_lv3_market_holidays}
- [ ] T080 [P] [US7] Create API endpoint GET /dashboard/performanceSummary in backend/src/routers/dashboard.py: SELECT * FROM txn_events with pagination, filtering (support column filters), sorting (support multi-column sort)
- [ ] T081 [P] [US7] Create API endpoint GET /dashboard/dayOffsetMetrics in backend/src/routers/dashboard.py: aggregate txn_events grouped by analyst/sector/other dimensions, calculate return statistics per dayOffset, return {group_by, group_value, dayOffset, sample_count, return_mean, return_median}
- [ ] T082 [P] [US7] Create design tokens CSS in frontend/src/styles/design-tokens.css: extract colors, spacing, typography, dimensions from alsign/prompt/2_designSystem.ini
- [ ] T083 [P] [US7] Create global styles in frontend/src/styles/global.css: CSS reset, base styles
- [ ] T084 [P] [US7] Create component styles in frontend/src/styles/components.css: table styles (thead sticky), badge styles (long=blue, short=red, undefined=gray), button styles
- [ ] T085 [P] [US7] Create DataTable component in frontend/src/components/table/DataTable.js: render table with thead sticky, support column selection, filtering, sorting, handle null rendering as "-" with dim text, never expand JSON fields (value_*, response_key, price_trend, analyst_performance)
- [ ] T086 [P] [US7] Create ColumnSelector component in frontend/src/components/table/ColumnSelector.js: checkbox list for column selection, persist to localStorage
- [ ] T087 [P] [US7] Create FilterPopover component in frontend/src/components/table/FilterPopover.js: render appropriate filter widget based on column type (string/date/number/enum), AND-combine active filters
- [ ] T088 [P] [US7] Create SortHeader component in frontend/src/components/table/SortHeader.js: implement sort state machine (null → asc → desc → null), support multi-column sorting
- [ ] T089 [P] [US7] Create KPICard component in frontend/src/components/dashboard/KPICard.js: display metric label and value with styling
- [ ] T090 [P] [US7] Create PerformanceTable component in frontend/src/components/dashboard/PerformanceTable.js: wrap DataTable with performanceSummary data binding
- [ ] T091 [P] [US7] Create DayOffsetTable component in frontend/src/components/dashboard/DayOffsetTable.js: wrap DataTable with dayOffsetMetrics data binding
- [ ] T092 [US7] Create DashboardPage in frontend/src/pages/DashboardPage.js: render KPI cards, PerformanceTable, DayOffsetTable, fetch data from API endpoints
- [ ] T093 [US7] Create localStorage service in frontend/src/services/localStorage.js: persist/retrieve column selection, filter state, sort state
- [ ] T094 [US7] Implement position_* badge rendering in frontend/src/components/table/DataTable.js: render "long" as blue badge, "short" as red badge, "undefined" as gray badge
- [ ] T095 [US7] Add validation in backend/src/routers/dashboard.py: return error if dayoffset_metrics dataset is missing (MUST_CONTAIN rule from specification)

**Checkpoint**: At this point, User Story 7 should be fully functional - dashboard displays KPIs and interactive tables

---

## Phase 10: Additional Routes (Priority: P3 continuation)

**Purpose**: Implement control and requests routes (lower priority than dashboard)

- [ ] T096 [P] Create ControlPage in frontend/src/pages/ControlPage.js: display environment variable management UI (view encrypted values, add/modify/delete), API call optimization settings, base time configuration, scheduler settings (cron expressions), batch processing configuration
- [ ] T097 [P] Create RequestsPage in frontend/src/pages/RequestsPage.js: file upload support (CSV/TSV/JSON/TXT), direct input textarea, preview table, API Status component (fixed 20% bottom area with progress bars, ETA, real-time logs)
- [ ] T098 [P] Create API Status component in frontend/src/components/requests/APIStatus.js: display current operation state (elapsed, progress, timeLeft, rate, mode, batchSize), progress bar, ETA calculation, streaming logs, cancel button
- [ ] T099 [P] Create router configuration in frontend/src/router.js: map routes (control, requests, conditionGroup, dashboard) to pages, ensure routes render in declared order without content relocation
- [ ] T100 [P] Create main.js in frontend/src/main.js: initialize router, mount app

---

## Phase 11: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [ ] T101 [P] Add comprehensive error handling across all routers in backend/src/routers/: wrap endpoint logic in try/except, return appropriate HTTP status codes (400/500), use ErrorCode enum for error responses
- [ ] T102 [P] Add input validation to all Pydantic models in backend/src/models/request_models.py: ticker must be uppercase alphanumeric, dates must be ISO8601 UTC, mode values must be in allowed list
- [ ] T103 [P] Create seed scripts in backend/scripts/: seed_policies.py (insert fillPriceTrend_dateRange and priceEodOHLC_dateRange policies), seed_api_config.py (insert FMP API rate limits), seed_metrics.py (insert metric definitions)
- [ ] T104 [P] Create render.yaml in repository root for Render.com deployment with web service configuration, environment variables, health check path
- [ ] T105 [P] Create README.md in backend/ with project overview, setup instructions, API documentation links
- [ ] T106 [P] Add SVG icon assets in frontend/src/assets/icons/ (filter icon, sort icon, column selector icon, cancel icon) - no Unicode glyphs, no icon libraries
- [ ] T107 [P] Implement health check endpoint GET /health in backend/src/main.py: return {status: "healthy", database: "connected"} after verifying DB pool is active
- [ ] T108 Add end-to-end validation by running quickstart.md steps: verify local dev setup works, test all API endpoints with curl examples, verify dashboard UI displays correctly
  - **Acceptance Criteria**:
    - All commands in quickstart.md execute without errors
    - All 6 core endpoints (GET /sourceData, POST /setEventsTable, POST /backfillEventsTable, POST /fillAnalyst, GET /dashboard/kpis, GET /dashboard/performanceSummary) return 200 status with valid JSON
    - Dashboard page loads in browser, displays KPI cards, and renders performance table with at least 1 row of sample data
- [ ] T109 Performance optimization: add database indexes on (ticker, event_date, analyst_name, analyst_company) for evt_consensus, (ticker, source) for txn_events, (exchange, date) for config_lv3_market_holidays
  - **Acceptance Criteria**:
    - CREATE INDEX statements added to backend/src/database/schema.sql for all specified columns
    - Database migration script created or documented in migration notes
    - Query performance improvement verified: SELECT from evt_consensus WHERE ticker = 'AAPL' executes in <10ms, txn_events filtered by ticker returns in <20ms
- [ ] T110 Security hardening: ensure .env file is gitignored, verify no secrets in code, add CORS configuration validation, sanitize user inputs in condition group names
  - **Acceptance Criteria**:
    - .env file appears in .gitignore and is not committed to repository
    - Code audit complete: zero hardcoded API keys or database credentials found (confirmed via grep -r "apiKey\|password\|secret")
    - CORS_ORIGINS environment variable is validated at startup, rejects invalid URLs
    - Condition group name input sanitized with regex validation (only alphanumeric, underscores, hyphens allowed; max 64 chars)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3-10)**: All depend on Foundational phase completion
  - User stories CAN proceed in parallel if staffed
  - Or sequentially in priority order: US1(P1) → US2,US3,US4(P2) → US5,US6,US7(P3)
- **Polish (Phase 11)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 2 (P2)**: Can start after Foundational (Phase 2) - Depends on US1 for evt_* tables to exist (but independently testable by seeding test data)
- **User Story 3 (P2)**: Can start after Foundational (Phase 2) - Depends on US2 for txn_events to exist (but independently testable by seeding test data)
- **User Story 4 (P2)**: Can start after Foundational (Phase 2) - Depends on US3 for txn_events with event_date (but independently testable by seeding test data)
- **User Story 5 (P3)**: Can start after Foundational (Phase 2) - Depends on US1 for consensus data and US4 for price_trend (but independently testable by seeding test data)
- **User Story 6 (P3)**: Can start after Foundational (Phase 2) - Depends on US2 for txn_events (but independently testable by seeding test data)
- **User Story 7 (P3)**: Can start after Foundational (Phase 2) - Depends on US2/US3/US4 for populated txn_events (but independently testable by seeding test data)

**Key Insight**: While stories have logical data dependencies, each is independently testable with seed data, enabling parallel development.

### Within Each User Story

- Models before services
- Services before routers
- Core implementation before integration
- Backend endpoints before frontend UI (for UI-dependent stories)
- Story complete before moving to next priority

### Parallel Opportunities

- All Setup tasks marked [P] can run in parallel
- All Foundational tasks marked [P] can run in parallel (within Phase 2)
- Once Foundational phase completes, all user stories can start in parallel (if team capacity allows)
- Within each story, all tasks marked [P] can run in parallel
- Different user stories can be worked on in parallel by different team members

---

## Parallel Example: User Story 1

```bash
# Launch all database query modules together (different files):
Task T018: "Create database query module for holidays in backend/src/database/queries/holidays.py"
Task T019: "Create database query module for targets in backend/src/database/queries/targets.py"
Task T020: "Create database query module for consensus in backend/src/database/queries/consensus.py"
Task T021: "Create database query module for earnings in backend/src/database/queries/earning.py"

# Launch all model files together:
Task T022: "Create request models in backend/src/models/request_models.py"
Task T023: "Create response models in backend/src/models/response_models.py"

# After query modules complete, implement all getXXX functions in parallel:
Task T024: "Implement getHolidays function in backend/src/services/source_data_service.py"
Task T025: "Implement getTargets function in backend/src/services/source_data_service.py"
# Note: T026/T027 (getConsensus Phase 1/2) are sequential within consensus, but parallel to T024/T025/T028
Task T028: "Implement getEarning function in backend/src/services/source_data_service.py"
```

---

## Parallel Example: User Story 7

```bash
# Launch all API endpoints together (different routes):
Task T079: "Create API endpoint GET /dashboard/kpis"
Task T080: "Create API endpoint GET /dashboard/performanceSummary"
Task T081: "Create API endpoint GET /dashboard/dayOffsetMetrics"

# Launch all CSS files together:
Task T082: "Create design tokens CSS in frontend/src/styles/design-tokens.css"
Task T083: "Create global styles in frontend/src/styles/global.css"
Task T084: "Create component styles in frontend/src/styles/components.css"

# Launch all table components together:
Task T085: "Create DataTable component in frontend/src/components/table/DataTable.js"
Task T086: "Create ColumnSelector component in frontend/src/components/table/ColumnSelector.js"
Task T087: "Create FilterPopover component in frontend/src/components/table/FilterPopover.js"
Task T088: "Create SortHeader component in frontend/src/components/table/SortHeader.js"

# Launch all dashboard components together:
Task T089: "Create KPICard component in frontend/src/components/dashboard/KPICard.js"
Task T090: "Create PerformanceTable component in frontend/src/components/dashboard/PerformanceTable.js"
Task T091: "Create DayOffsetTable component in frontend/src/components/dashboard/DayOffsetTable.js"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 1 (Data Collection)
4. **STOP and VALIDATE**: Test GET /sourceData independently with all modes
5. Deploy/demo if ready - this is a functional MVP that can collect all foundation data

**Deliverable**: Working data collection pipeline from FMP APIs to Supabase Postgres

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Test independently → Deploy/Demo (MVP!)
3. Add User Story 2 → Test independently → Deploy/Demo (MVP + Event Consolidation)
4. Add User Story 3 → Test independently → Deploy/Demo (MVP + Valuation)
5. Add User Story 4 → Test independently → Deploy/Demo (MVP + Price Trends)
6. Add User Story 5 → Test independently → Deploy/Demo (MVP + Analyst Performance)
7. Add User Stories 6 & 7 → Test independently → Deploy/Demo (Full System with UI)
8. Each story adds value without breaking previous stories

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together (critical path)
2. Once Foundational is done:
   - Developer A: User Story 1 (P1) - HIGHEST PRIORITY
   - Developer B: User Story 2 (P2) - Prepare consolidation with seed data
   - Developer C: User Story 3 (P2) - Prepare valuation with seed data
3. Stories complete and integrate independently
4. After US1-US4 complete:
   - Developer A: User Story 5 (P3)
   - Developer B: User Story 6 (P3)
   - Developer C: User Story 7 (P3)

---

## Notes

- [P] tasks = different files, no dependencies - can run in parallel
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Never write to DB-generated columns: created_at, updated_at, analyst_name_key, analyst_company_key
- All dates must be parsed to UTC and stored as timestamptz
- Use upsert for: config_lv3_market_holidays, config_lv3_targets, evt_consensus, config_lv3_analyst, txn_events
- Use insert-only for: evt_earning
- Consensus processing is two-phase: Phase 1 (raw upsert) → Phase 2 (change detection)
- Trading day calculations must use config_lv3_market_holidays (no hardcoded holidays)
- Rate limiting must use sliding window with dynamic batch sizing
- Structured logging must use fixed 1-line format from spec
- Frontend must use plain HTML/CSS/JS or React WITHOUT component libraries, icon libraries, or Unicode glyphs
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
