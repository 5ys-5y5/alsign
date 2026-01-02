# Feature Specification: FastAPI Financial Data API Backend System

**Feature Branch**: `001-fastapi-financial-data-api`
**Created**: 2025-12-18
**Status**: Draft
**Input**: Implementation of a JSON-only Web API backend system deployed to Render.com for financial data processing, with FastAPI (Python 3.11+) and direct Supabase Postgres access

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Collect Market Foundation Data (Priority: P1)

Financial analysts need to automatically collect and maintain up-to-date market foundation data (holidays, company targets, analyst consensus, and earnings calendars) from external financial APIs to ensure all downstream analysis is based on current market information.

**Why this priority**: This is the foundational data layer that all other features depend on. Without accurate market holidays, company targets, and financial event data, no meaningful analysis can be performed.

**Independent Test**: Can be fully tested by calling `GET /sourceData` with various mode parameters and verifying that data is correctly fetched from external APIs and stored in the appropriate database tables (config_lv3_market_holidays, config_lv3_targets, evt_consensus, evt_earning).

**Acceptance Scenarios**:

1. **Given** the API service is running, **When** calling `GET /sourceData?mode=holiday`, **Then** market holidays are fetched and upserted to config_lv3_market_holidays table
2. **Given** the API service is running, **When** calling `GET /sourceData?mode=target`, **Then** company targets are fetched and upserted to config_lv3_targets table
3. **Given** the API service is running, **When** calling `GET /sourceData?mode=consensus`, **Then** analyst consensus data is fetched, upserted to evt_consensus, and change detection is performed
4. **Given** the API service is running, **When** calling `GET /sourceData?mode=earning&past=true`, **Then** both historical (5 years) and future earnings data are fetched and inserted
5. **Given** invalid mode value, **When** calling `GET /sourceData?mode=invalid`, **Then** API returns 400 Bad Request
6. **Given** rate limits are configured, **When** fetching data, **Then** API respects rate limits and dynamically adjusts batch sizes

---

### User Story 2 - Consolidate Events from Multiple Sources (Priority: P2)

Financial analysts need all financial events from different source tables (evt_consensus, evt_earning, etc.) consolidated into a unified events table with enriched sector/industry information to enable cross-source analysis and filtering.

**Why this priority**: This unification layer enables analysts to query and analyze events regardless of their original source, and ensures consistent sector/industry classification across all events.

**Independent Test**: Can be fully tested by first populating source tables (evt_*), then calling `POST /setEventsTable` and verifying that txn_events table contains all events with correct source attribution and sector/industry enrichment.

**Acceptance Scenarios**:

1. **Given** evt_consensus and evt_earning tables have data, **When** calling `POST /setEventsTable`, **Then** all events are inserted into txn_events with source and source_id populated
2. **Given** events exist without sector/industry, **When** calling `POST /setEventsTable?overwrite=false`, **Then** only NULL sector/industry values are filled from config_lv3_targets
3. **Given** events have outdated sector/industry, **When** calling `POST /setEventsTable?overwrite=true`, **Then** all sector/industry values are synchronized with config_lv3_targets
4. **Given** dryRun=true, **When** calling `POST /setEventsTable?dryRun=true`, **Then** API returns projected changes without modifying database
5. **Given** new evt_* table is added to schema, **When** calling `POST /setEventsTable`, **Then** new table is automatically discovered and processed

---

### User Story 3 - Calculate Quantitative and Qualitative Value Metrics (Priority: P2)

Financial analysts need each event to be evaluated with quantitative financial metrics (valuation ratios, profitability, risk indicators) and qualitative signals (consensus direction, price target changes) to assess investment opportunities.

**Why this priority**: This transforms raw event data into actionable financial intelligence by calculating key metrics that analysts use to make investment decisions.

**Independent Test**: Can be fully tested by ensuring txn_events has ticker/event_date/source data, then calling `POST /backfillEventsTable` and verifying that value_quantitative, value_qualitative, position_quantitative, position_qualitative, disparity_quantitative, and disparity_qualitative fields are populated.

**Acceptance Scenarios**:

1. **Given** txn_events has events with ticker/event_date, **When** calling `POST /backfillEventsTable`, **Then** value_quantitative is populated with financial ratios (PER, PBR, ROE, etc.) grouped by domain
2. **Given** evt_consensus has price target data, **When** calculating qualitative metrics, **Then** consensusSignal includes direction, last/prev values, delta, deltaPct
3. **Given** calcFairValue=true (default), **When** calling `POST /backfillEventsTable`, **Then** position_quantitative is calculated using sector-average-based fair value and set to "long", "short", or "neutral"
4. **Given** qualitative metrics are calculated, **When** comparing priceQualitative with current price, **Then** position_qualitative is set to "long" or "short"
5. **Given** overwrite=false, **When** calling `POST /backfillEventsTable`, **Then** only NULL values within jsonb fields are updated
6. **Given** TTM calculation requires 4 quarters, **When** only 3 quarters available, **Then** system uses (Q0+Q1+Q2)/3 × 4 and records calcType as "TTM_partialQuarter"
7. **Given** calcFairValue=true (default), **When** calculating valuations, **Then** system fetches peer tickers via fmp-stock-peers API and calculates sector-average PER/PBR for fair value estimation (I-36, I-38)

---

### User Story 4 - Generate Price Trend Time Series (Priority: P2)

Financial analysts need historical and future price trends (OHLC data) for each event to analyze price performance before and after the event occurs, enabling cohort analysis and signal validation.

**Why this priority**: Price trend analysis is essential for validating the predictive power of financial events and analyst signals.

**Independent Test**: Can be fully tested by ensuring txn_events has populated records, then verifying that price_trend field contains dayOffset-indexed OHLC arrays from countStart to countEnd.

**Acceptance Scenarios**:

1. **Given** txn_events has event_date, **When** priceTrend is calculated, **Then** price_trend array contains entries from dayOffset countStart to countEnd based on config_lv0_policy
2. **Given** event_date falls on weekend, **When** calculating dayOffset=0, **Then** dayOffset=0 maps to next trading day
3. **Given** target date is in future, **When** filling priceTrend, **Then** OHLC values are set to null (progressive null-filling)
4. **Given** market holidays exist, **When** calculating trading days, **Then** weekends and NASDAQ holidays are skipped
5. **Given** multiple events for same ticker, **When** fetching OHLC data, **Then** API is called once per ticker covering full date range (economic calling)
6. **Given** priceTrend row doesn't exist in txn_events, **When** attempting update, **Then** API returns error EVENT_ROW_NOT_FOUND

---

### User Story 5 - Aggregate Analyst Performance Metrics (Priority: P3)

Financial analysts need to evaluate the historical performance of individual analysts or analyst companies by aggregating their consensus signals and measuring return distributions across different time offsets (D+0, D+1, ..., D+N).

**Why this priority**: This enables analysts to identify which analysts or firms have the best track records, informing trust and weighting decisions.

**Independent Test**: Can be fully tested by ensuring txn_events has consensusSignal data with analyst_name/analyst_company and price_trend, then calling `POST /fillAnalyst` and verifying config_lv3_analyst table is populated with performance statistics.

**Acceptance Scenarios**:

1. **Given** txn_events has consensusSignal with analyst metadata, **When** calling `POST /fillAnalyst`, **Then** config_lv3_analyst is upserted with analyst_name, analyst_company
2. **Given** analyst performance is calculated, **When** aggregating returns, **Then** performance field contains mean, median, quartiles, stddev, count for each dayOffset
3. **Given** analyst_name is NULL but analyst_company exists, **When** grouping analysts, **Then** (NULL, company) is treated as valid group using generated key
4. **Given** both analyst_name and analyst_company are NULL, **When** processing events, **Then** those events are skipped and counted in events_skipped_both_null_analyst
5. **Given** priceTrend range doesn't match policy, **When** validating events, **Then** API returns error INVALID_PRICE_TREND_RANGE
6. **Given** internal(qual) metrics are defined, **When** calculating statistics, **Then** system uses metric definitions from config_lv2_metric instead of hardcoded logic

---

### User Story 6 - Manage Condition Groups for Event Filtering (Priority: P3)

Financial analysts need to create named condition groups (e.g., "conFS" for Financial Services consensus events) by selecting column and value combinations, enabling quick filtering and cohort analysis in dashboards.

**Why this priority**: This provides a flexible tagging system that allows analysts to create custom event segments without modifying the database schema.

**Independent Test**: Can be fully tested by selecting a column (e.g., source), a value (e.g., evt_consensus), and a condition name (e.g., "techConsensus"), then verifying that all matching rows in txn_events have their condition field updated.

**Acceptance Scenarios**:

1. **Given** analyst selects column "source" and value "evt_consensus", **When** entering condition name "conAll", **Then** all rows where source=evt_consensus have condition set to "conAll"
2. **Given** condition "conFS" already exists, **When** analyst selects it, **Then** UI shows current column/value combination and allows update or delete
3. **Given** analyst creates condition with column "sector" and value "Financial Services", **When** applying condition, **Then** only rows matching (column, value) are updated
4. **Given** analyst deletes a condition, **When** delete is confirmed, **Then** all rows with that condition value have condition set to NULL

---

### User Story 7 - View Dashboards with Performance Metrics (Priority: P3)

Financial analysts need visual dashboards showing KPI cards (coverage, data freshness), performance summaries (event table with filters/sorts), and day-offset metrics (cohort performance by group) to monitor system health and identify top-performing signals.

**Why this priority**: This provides the visualization layer that makes all the processed data actionable and enables data-driven decision making.

**Independent Test**: Can be fully tested by navigating to dashboard route and verifying that KPI cards display correct counts, performance table shows txn_events data with working filters/sorts, and day-offset table shows aggregated returns grouped by analyst, sector, or other dimensions.

**Acceptance Scenarios**:

1. **Given** dashboard is loaded, **When** viewing KPI cards, **Then** coverage shows total tickers, data freshness shows last update time
2. **Given** performance summary table is rendered, **When** clicking column header, **Then** table sorts by that column (null → asc → desc → null cycle)
3. **Given** performance summary table is rendered, **When** clicking filter icon, **Then** popover opens with appropriate filter widget (string/date/number/enum)
4. **Given** day-offset metrics are calculated, **When** viewing table, **Then** rows show group_by, group_value, dayOffset, sample_count, return_mean, return_median
5. **Given** user selects different columns, **When** changes are made, **Then** selection persists to localStorage
6. **Given** dashboard route is loaded, **When** dayoffset_metrics is missing, **Then** specification validation FAILS (MUST_CONTAIN rule)

---

### Edge Cases

- **Rate Limit Handling**: What happens when external API rate limits are exceeded? System must dynamically reduce batch size per FR-029 algorithm (batch_size reduces to 1 when usage_pct >= 80%), log rate limit warnings, and continue processing at reduced rate until usage_pct drops below threshold.
- **Timezone Ambiguity**: How does system handle date inputs without timezone information? All dates must be parsed to UTC; parsing failures result in 400 Bad Request.
- **Partial Data Availability**: What happens when TTM calculation needs 4 quarters but only 2 are available? System calculates average of available quarters × 4 and marks as "TTM_partialQuarter".
- **Concurrent Update Conflicts**: How does system handle concurrent updates to same (ticker, analyst_name, analyst_company) partition in getConsensus Phase 2? System enforces single execution flow per partition.
- **Missing Company Target**: What happens when txn_events references ticker not in config_lv3_targets? Sector/industry remain NULL without auto-correction; logged as warning.
- **Future Price Data**: How does system handle requests for OHLC data for future dates? Future dates receive null values (progressive null-filling).
- **Holiday Date Calculation**: What happens when event_date falls on a weekend or market holiday for dayOffset=0? System maps to next trading day based on config_lv3_market_holidays.
- **Empty evt_* Tables**: What happens when POST /setEventsTable is called but no evt_* tables have data? API returns success with zero records processed.
- **Duplicate Event Insert**: How does system handle duplicate (ticker, event_date) in evt_earning? Uses ON CONFLICT DO NOTHING (insert-only strategy).
- **Generated Column Write Attempt**: What happens if application tries to write to analyst_name_key or analyst_company_key? Database rejects write; application must never attempt to write these columns.
- **Ambiguous Event Date Match**: What happens when (ticker, source, source_id, event_day_utc_date) matches multiple rows? API returns error AMBIGUOUS_EVENT_DATE.
- **Policy-Data Mismatch**: What happens when fillPriceTrend_dateRange policy changes but existing priceTrend data has old range? Validation fails with INVALID_PRICE_TREND_RANGE; no auto-correction.

## Requirements *(mandatory)*

### Functional Requirements

#### Core API Infrastructure

- **FR-001**: System MUST implement FastAPI (ASGI) as the web framework using Python 3.11+
- **FR-002**: System MUST connect directly to Supabase Postgres using asyncpg for all database operations; System MUST perform all database I/O operations using raw SQL queries; System MUST NOT use supabase-js, Supabase REST API, PostgREST, Supabase Python client, or ORMs
- **FR-005**: System MUST be deployable to Render.com
- **FR-006**: System MUST return JSON-only responses for all API endpoints

#### Data Collection & Source Management (GET /sourceData)

- **FR-007**: System MUST support GET /sourceData endpoint with optional "mode" query parameter accepting: holiday, target, consensus, earning
- **FR-008**: System MUST execute all modes in default order (holiday → target → consensus → earning) when mode is unspecified
- **FR-009**: System MUST allow comma-separated mode values and execute them in default order after deduplication
- **FR-010**: System MUST return 400 Bad Request when mode contains invalid values
- **FR-011**: System MUST support "past" boolean parameter that is only effective when mode includes "earning"
- **FR-012**: System MUST fetch and upsert market holidays to config_lv3_market_holidays table keyed by (exchange, date)
- **FR-013**: System MUST fetch and upsert company targets to config_lv3_targets table keyed by ticker
- **FR-014**: System MUST fetch consensus data only for tickers present in config_lv3_targets
- **FR-015**: System MUST execute getConsensus in two phases: Phase 1 (Raw Upsert) and Phase 2 (Change Detection)
- **FR-016**: System MUST upsert consensus data to evt_consensus keyed by (ticker, event_date, analyst_name, analyst_company)
- **FR-017**: System MUST calculate price_target_prev, price_when_posted_prev, direction, and response_key.prev in getConsensus Phase 2
- **FR-018**: System MUST determine Phase 2 target partitions based on calc_mode: default (affected partitions only) or maintenance (scope-based)
- **FR-019**: System MUST support calc_mode=maintenance with calc_scope: all, ticker, event_date_range, partition_keys
- **FR-020**: System MUST require appropriate parameters for each calc_scope (tickers for ticker, from/to for event_date_range, partitions for partition_keys)
- **FR-021**: System MUST return 400 Bad Request when calc_mode is invalid or calc_scope is missing in maintenance mode
- **FR-022**: System MUST enforce single execution flow per (ticker, analyst_name, analyst_company) partition in Phase 2
- **FR-023**: System MUST allow parallel processing of different partitions in Phase 2
- **FR-024**: System MUST fetch earning data for future 28 days (4 windows of 7 days) by default
- **FR-025**: System MUST fetch earning data for past 5 years in 7-day chunks when past=true
- **FR-026**: System MUST insert earning data to evt_earning using INSERT-only strategy with ON CONFLICT DO NOTHING

#### Economic API Calling

- **FR-027**: System MUST minimize API calls by consolidating requests per ticker across all event dates; System MUST make exactly 1 API call per ticker per OHLC date range (instead of 1 call per ticker per event_date)
- **FR-028**: System MUST respect rate limits defined in config_lv1_api_service.usagePerMin
- **FR-029**: System MUST dynamically adjust batch size based on current rate vs limit ratio using algorithm: `batch_size = max(1, min(remaining_items, floor(limit_per_min * (1 - usage_pct) / 2)))` where `usage_pct = (current_requests_per_minute / config_lv1_api_service.usagePerMin)`; when usage_pct >= 0.80, reduce batch_size to 1; when usage_pct < 0.50, increase batch_size up to 50
- **FR-029-A**: System MUST report batch mode in logs using values: "dynamic" (normal adaptive sizing), "throttled" (usage_pct >= 0.80), "aggressive" (usage_pct < 0.50), "minimum" (batch_size = 1)
- **FR-030**: System MUST calculate and log ETA (estimated time remaining) for long-running operations
- **FR-031**: System MUST log progress with format: `[endpoint | phase] elapsed=Xms | progress=done/total(pct%) | eta=Yms | rate=perMin/limitPerMin(usagePct%) | batch=size(mode) | ok=X fail=Y skip=Z upd=A ins=B cf=C | warn=[codes] | message` where mode is one of: dynamic, throttled, aggressive, minimum

#### Event Consolidation (POST /setEventsTable)

- **FR-032**: System MUST support POST /setEventsTable endpoint accepting empty JSON body
- **FR-033**: System MUST auto-discover all tables matching "evt_%" pattern in specified schema (default: public)
- **FR-034**: System MUST insert events from evt_* tables into txn_events with (ticker, event_date, source, source_id)
- **FR-035**: System MUST use ON CONFLICT (ticker, event_date, source, source_id) DO NOTHING to prevent duplicates
- **FR-036**: System MUST support "overwrite" boolean parameter (default: false) controlling sector/industry update strategy: when false, only update NULL sector/industry values; when true, update both NULL and mismatched sector/industry values from config_lv3_targets
- **FR-039**: System MUST support "dryRun" boolean parameter that returns projected changes without database modification
- **FR-040**: System MUST support "schema" string parameter (default: "public") to specify target schema
- **FR-041**: System MUST support "table" comma-separated string parameter to limit discovery to specific tables
- **FR-042**: System MUST return 400 Bad Request when specified table doesn't match evt_* pattern
- **FR-043**: System MUST return summary including: tables discovered, rows per table, inserts, conflicts, sector/industry updates

#### Event Valuation (POST /backfillEventsTable)

- **FR-044**: System MUST support POST /backfillEventsTable endpoint accepting empty JSON body
- **FR-045**: System MUST support "overwrite" boolean parameter (default: false) controlling value field update strategy: when false, partially update only NULL values within value_* jsonb fields; when true, fully replace value_* fields for all rows meeting preconditions
- **FR-048**: System MUST calculate value_quantitative by querying config_lv2_metric where domain starts with "quantitative-"
- **FR-049**: System MUST group quantitative metrics by domain suffix (e.g., "quantitative-valuation" → "valuation" key)
- **FR-050**: System MUST include _meta in value_quantitative with date_range, calcType, and count
- **FR-051**: System MUST calculate TTM using 4 quarters when available, or (available_avg × 4) when partial
- **FR-052**: System MUST mark calcType as "TTM_fullQuarter" or "TTM_partialQuarter" based on data availability
- **FR-053**: System MUST calculate value_qualitative by querying config_lv2_metric where domain starts with "qualitative-"
- **FR-054**: System MUST generate consensusSignal from evt_consensus Phase 2 data (not Phase 1)
- **FR-055**: System MUST include direction, last, prev, delta, deltaPct, and meta in consensusSignal
- **FR-056**: System MUST set delta and deltaPct to null when prev doesn't exist
- **FR-057**: System MUST calculate position_quantitative as "long" when priceQuantitative > price, "short" when less, "undefined" otherwise
- **FR-058**: System MUST calculate disparity_quantitative as (priceQuantitative / price) - 1
- **FR-059**: System MUST calculate position_qualitative as "long" when priceQualitative > price, "short" when less, "undefined" otherwise
- **FR-060**: System MUST calculate disparity_qualitative as (priceQualitative / price) - 1

#### Price Trend Time Series

- **FR-061**: System MUST generate price_trend arrays based on config_lv0_policy where function="fillPriceTrend_dateRange"
- **FR-062**: System MUST create dayOffset entries from countStart to countEnd (inclusive of 0)
- **FR-063**: System MUST map event_date to dayOffset=0 using next trading day if event_date is non-trading day
- **FR-064**: System MUST skip weekends and NASDAQ holidays when calculating trading days
- **FR-065**: System MUST use config_lv3_market_holidays to determine holiday dates
- **FR-066**: System MUST set OHLC values to null for future dates (progressive null-filling)
- **FR-067**: System MUST batch OHLC API calls per ticker covering full date range based on priceEodOHLC_dateRange policy
- **FR-068**: System MUST calculate OHLC fetch range as (min_event_date + countStart) to (max_event_date + countEnd)
- **FR-069**: System MUST match txn_events rows using (ticker, source, source_id, event_day_utc_date)
- **FR-070**: System MUST return error EVENT_ROW_NOT_FOUND when 0 rows match update criteria
- **FR-071**: System MUST return error AMBIGUOUS_EVENT_DATE when 2+ rows match update criteria
- **FR-072**: System MUST update existing txn_events rows only; never insert new rows during price trend filling

#### Analyst Performance Aggregation (POST /fillAnalyst)

- **FR-073**: System MUST support POST /fillAnalyst endpoint accepting empty JSON body
- **FR-074**: System MUST validate that config_lv0_policy contains function="fillPriceTrend_dateRange" policy
- **FR-075**: System MUST return error POLICY_NOT_FOUND when policy is missing
- **FR-076**: System MUST load txn_events rows where source='evt_consensus' and at least one of (analyst_name, analyst_company) is not NULL
- **FR-077**: System MUST skip events where both analyst_name and analyst_company are NULL
- **FR-078**: System MUST group events by (analyst_name, analyst_company) using generated keys for upsert
- **FR-079**: System MUST use analyst_name_key=COALESCE(analyst_name,'__NULL__') and analyst_company_key=COALESCE(analyst_company,'__NULL__')
- **FR-080**: System MUST validate that priceTrend arrays match policy countStart/countEnd range
- **FR-081**: System MUST return error INVALID_PRICE_TREND_RANGE when range validation fails
- **FR-082**: System MUST calculate return as (close / basePrice) - 1 where basePrice=consensusSignal.last.price_when_posted
- **FR-083**: System MUST exclude samples where close is null or basePrice is null/zero
- **FR-084**: System MUST calculate performance statistics using metric definitions from config_lv2_metric where domain="internal(qual)"
- **FR-085**: System MUST calculate mean, median, 1st quartile, 3rd quartile, IQR, standard deviation, and count for each dayOffset
- **FR-086**: System MUST upsert config_lv3_analyst using (analyst_name_key, analyst_company_key) as conflict keys
- **FR-087**: System MUST NOT write to generated columns (analyst_name_key, analyst_company_key)
- **FR-088**: System MUST return HTTP 207 Multi-Status with per-group results and summary
- **FR-089**: System MUST include total_events_loaded, events_skipped_both_null_analyst, total_groups, groups_success, groups_failed in summary

#### Condition Group Management

- **FR-090**: System MUST provide UI for selecting a column from predefined list (source, sector, industry)
- **FR-091**: System MUST populate value dropdown with distinct values from txn_events for selected column
- **FR-092**: System MUST allow analyst to enter condition name (minimum 1 character after trim)
- **FR-093**: System MUST update txn_events.condition field for all rows matching (column, value) combination
- **FR-094**: System MUST support reading existing conditions for update or delete
- **FR-095**: System MUST set condition to NULL when deleting a condition group
- **FR-096**: System MUST require explicit user confirmation before applying bulk updates

#### Dashboard & UI

- **FR-097**: System MUST implement four routes: control, requests, conditionGroup, dashboard
- **FR-098**: System MUST render routes in declared order without content relocation
- **FR-099**: System MUST display KPI cards in dashboard showing coverage (config_lv3_targets count) and data freshness (config_lv3_market_holidays latest update)
- **FR-100**: System MUST display performance summary table in dashboard bound to txn_events dataset
- **FR-101**: System MUST display day-offset metrics table in dashboard bound to dashboard_dayoffset_metrics dataset
- **FR-102**: System MUST support column selection (FR-103: checkbox list with localStorage persistence), filtering (FR-105: AND-combined active filters with type-appropriate widgets for string/date/number/enum), and sorting (FR-104: null→asc→desc→null state machine) for all dashboard tables
- **FR-103**: System MUST persist column selection, filter state, and sort state to localStorage
- **FR-104**: System MUST implement sort state machine: null → asc → desc → null
- **FR-105**: System MUST AND-combine all active filters
- **FR-106**: System MUST render null/undefined values as "-" with dim text
- **FR-107**: System MUST render position_* enum fields as colored badges (long=blue, short=red, undefined=gray)
- **FR-108**: System MUST NOT expand JSON fields (value_*, response_key, price_trend, analyst_performance) in tables
- **FR-109**: System MUST use exact design tokens from 2_designSystem.ini (colors, spacing, typography, dimensions) - see `alsign/prompt/2_designSystem.ini` for complete specification
- **FR-110**: System MUST use plain HTML+CSS+Vanilla JS or React with self-authored markup
- **FR-111**: System MUST NOT use UI component libraries (shadcn/ui, MUI, Ant, Chakra, Mantine)
- **FR-112**: System MUST NOT use icon libraries (lucide-react, heroicons, font-awesome)
- **FR-113**: System MUST use SVG assets for all functional icons (no Unicode glyphs)

#### Time & Date Handling

- **FR-114**: System MUST enforce UTC-only timezone handling: (1) parse all incoming date strings to Python datetime objects in UTC; (2) treat date-only strings (YYYY-MM-DD) as YYYY-MM-DD 00:00:00+00:00 UTC; (3) store all timestamp fields as timestamptz in PostgreSQL; (4) store dates within jsonb as UTC ISO8601 strings with +00:00 timezone; (5) return 400 Bad Request when date parsing fails
- **FR-119**: System MUST NOT write to created_at or updated_at columns (DB manages these)

#### Error Handling & Logging

- **FR-120**: System MUST use standardized error codes: POLICY_NOT_FOUND, INVALID_POLICY, INVALID_CONSENSUS_DATA, INVALID_PRICE_TREND_RANGE, METRIC_NOT_FOUND, EVENT_ROW_NOT_FOUND, AMBIGUOUS_EVENT_DATE, INTERNAL_ERROR
- **FR-121**: System MUST log all operations with reqId, endpoint, phase, elapsedMs, progress, etaMs, rate, batch, counters, policy, warn, msg
- **FR-122**: System MUST use fixed 1-line log format: `[endpoint | phase] elapsed=Xms | progress=done/total(pct%) | eta=Yms | rate=perMin/limitPerMin(usagePct%) | batch=size(mode) | ok=X fail=Y skip=Z upd=A ins=B cf=C | warn=[codes] | message` where mode is one of: dynamic, throttled, aggressive, minimum (as defined in FR-029-A)
- **FR-123**: System MUST return HTTP 207 Multi-Status for batch operations with per-record status
- **FR-124**: System MUST return summary with success/fail/skip/update/insert/conflict counts

## Constraints *(mandatory)*

Database and architectural constraints that the system must respect:

### Database Write Constraints

- **CONS-001**: System MUST NOT write to database-generated columns: `created_at`, `updated_at`, `analyst_name_key`, `analyst_company_key` (these are managed by database defaults, triggers, and generated column expressions)
- **CONS-002**: System MUST use upsert strategy (INSERT ... ON CONFLICT DO UPDATE) for tables: config_lv3_market_holidays, config_lv3_targets, evt_consensus, config_lv3_analyst, txn_events
- **CONS-003**: System MUST use insert-only strategy (INSERT ... ON CONFLICT DO NOTHING) for table: evt_earning
- **CONS-004**: System MUST log 'POLICY_CONFLICT_DB_SCHEMA' warning when application guideline conflicts with database schema constraints

### Key Entities

- **Market Holiday**: Represents exchange trading holidays with date, name, closure status, and adjusted trading hours; keyed by (exchange, date)
- **Company Target**: Represents tradable securities with ticker, sector, industry, and full API response; keyed by ticker
- **Consensus Event**: Represents analyst price target publications with ticker, event_date, analyst identity, price targets, and change tracking (prev values, direction); keyed by (ticker, event_date, analyst_name, analyst_company)
- **Earning Event**: Represents earnings calendar entries with ticker, event_date, actual/estimated EPS and revenue; keyed by (ticker, event_date); insert-only
- **Unified Event (txn_events)**: Consolidates all financial events with source attribution, sector/industry enrichment, quantitative/qualitative valuations, position signals, disparity ratios, and price trend time series
- **Analyst Performance**: Aggregates performance metrics per (analyst_name, analyst_company) combination with dayOffset-indexed return distributions; uses generated keys to handle NULL values; stored in config_lv3_analyst.performance jsonb field
- **Price Trend**: Array of dayOffset-indexed OHLC entries spanning countStart to countEnd trading days relative to event_date
- **Metric Definition**: Configuration entries defining how to calculate financial metrics (quantitative/qualitative domains, aggregation rules, transform functions)
- **Policy**: System-wide configuration rules stored in config_lv0_policy controlling date ranges, batch sizes, rate limits, and calculation scopes

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: System successfully fetches and stores market holidays, company targets, consensus data, and earnings data with 99.9% API call success rate (measured per endpoint execution; calculated as successful API calls / total API calls attempted)
- **SC-002**: GET /sourceData completes full execution (all 4 modes) for 500 tickers within 10 minutes while respecting rate limits
- **SC-003**: POST /setEventsTable discovers and consolidates events from 10+ evt_* tables in under 2 minutes for 10,000 total events
- **SC-004**: POST /backfillEventsTable calculates quantitative and qualitative metrics for 5,000 events in under 5 minutes
- **SC-005**: Price trend filling completes OHLC data population for 1,000 events covering 29 dayOffsets (-14 to +14) in under 8 minutes with optimized ticker-based batching
- **SC-006**: POST /fillAnalyst aggregates performance metrics for 100 analysts across 5,000 events in under 3 minutes
- **SC-007**: System logs include sufficient detail to identify bottlenecks and errors from log output alone (no additional debugging required)
- **SC-008**: Dashboard tables support sorting, filtering, and column selection with state persistence, and all interactions complete in under 200ms
- **SC-009**: 95% of API requests complete successfully on first attempt; retry logic handles transient failures for remaining 5%
- **SC-010**: System correctly handles timezone conversions with 100% accuracy (no date mismatches due to timezone ambiguity)
- **SC-011**: UI renders consistently across modern browsers without visual divergence from design system specifications
- **SC-012**: Concurrent requests to different endpoints process without blocking (parallel execution)
- **SC-013**: Database query performance maintains sub-100ms response times for table populations up to 100,000 events
- **SC-014**: System successfully deploys to Render.com with zero manual configuration steps beyond environment variables
- **SC-015**: All database operations respect DB responsibilities: never write to generated columns, honor upsert vs insert-only strategies

## Assumptions

1. **External API Availability**: FMP (Financial Modeling Prep) APIs are accessible and return data in documented formats
2. **Database Schema Pre-exists**: All tables defined in 1_guideline(tableSetting).ini are already created with correct constraints, triggers, and generated columns
3. **Environment Variables**: SUPABASE connection credentials and FMP_API_KEY are securely provided via environment
4. **Rate Limits**: config_lv1_api_service table is pre-populated with correct usagePerMin values for each API service
5. **Trading Calendar**: config_lv3_market_holidays is maintained and up-to-date (updated via GET /sourceData?mode=holiday)
6. **Metric Definitions**: config_lv2_metric table contains all necessary metric definitions for quantitative, qualitative, and internal(qual) domains
7. **Policy Configuration**: config_lv0_policy table contains required policies for fillPriceTrend_dateRange and priceEodOHLC_dateRange
8. **UTC as Standard**: All date/time operations assume UTC as the canonical timezone; no local timezone conversions are needed
9. **Single Market Focus**: System primarily targets NASDAQ/NYSE markets (US trading calendar)
10. **No Authentication Required**: API endpoints are accessible without authentication (controlled at infrastructure level)

## Out of Scope

1. **User Authentication & Authorization**: No login, user management, or role-based access control
2. **Real-time Data Streaming**: System operates on batch/scheduled execution model, not real-time WebSocket feeds
3. **Historical Data Backfill UI**: While backfill endpoints exist, no dedicated UI for managing historical data ranges
4. **Data Export Features**: No CSV/Excel export functionality from dashboard tables
5. **Custom Metric Builder**: Users cannot define new metrics via UI; metrics must be added to config_lv2_metric via database
6. **Multi-Market Support**: Only NASDAQ/NYSE holiday calendars are supported; no international exchanges
7. **Mobile Responsiveness**: Dashboard UI is optimized for desktop browsers only
8. **API Versioning**: Single API version; no /v1, /v2 endpoint versioning
9. **Rate Limit Management UI**: Rate limits are configured in database; no UI for adjusting limits
10. **Alerting & Notifications**: No email, SMS, or push notifications for data updates or errors
11. **Data Deletion**: No endpoints for deleting historical events or undoing operations
12. **Multi-tenancy**: Single-tenant system; no support for multiple isolated data spaces
13. **Caching Layer**: No Redis or external caching; relies on database and in-memory processing
14. **Audit Trail**: created_at/updated_at are logged but no comprehensive audit log of user actions
15. **Internationalization**: UI and error messages are in English and Korean only; no multi-language support
