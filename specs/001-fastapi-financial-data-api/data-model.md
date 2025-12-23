# Data Model: FastAPI Financial Data API Backend System

**Date**: 2025-12-18
**Branch**: `001-fastapi-financial-data-api`

## Overview

This document defines the data entities, relationships, validation rules, and state transitions for the FastAPI Financial Data API system. All entities map to Supabase Postgres tables defined in `alsign/prompt/1_guideline(tableSetting).ini`.

## Entity Catalog

### Configuration Entities (Config Layer)

#### 1. MarketHoliday (`config_lv3_market_holidays`)

**Purpose**: Represents exchange-specific trading holidays and adjusted trading hours.

**Key Fields**:
- `exchange` (text, PK): Exchange identifier (e.g., "NASDAQ", "NYSE")
- `date` (date, PK): Holiday date
- `name` (text): Holiday name (e.g., "Thanksgiving")
- `is_closed` (boolean): Whether market is fully closed
- `adj_open_time` (time, nullable): Adjusted opening time if partially closed
- `adj_close_time` (time, nullable): Adjusted closing time if partially closed
- `is_fully_closed` (boolean): Derived field indicating complete closure
- `updated_at` (timestamptz): Last update timestamp (DB-managed)

**Composite Primary Key**: `(exchange, date)`

**Validation Rules**:
- `exchange` must not be empty
- `date` must be valid calendar date
- If `is_closed=false`, `adj_open_time` and `adj_close_time` should be provided

**Update Strategy**: **Upsert** (ON CONFLICT (exchange, date) DO UPDATE)

**Application Responsibilities**:
- Fetch from FMP holidays API
- Parse and normalize date to UTC
- Never write to `updated_at` (DB trigger manages this)

**Relationships**:
- Used by: Trading day calculator for price trend generation

---

#### 2. CompanyTarget (`config_lv3_targets`)

**Purpose**: Represents tradable securities (stocks, ETFs) with sector/industry classification.

**Key Fields**:
- `ticker` (text, PK): Stock ticker symbol (e.g., "AAPL")
- `sector` (text, nullable): Business sector (e.g., "Technology")
- `industry` (text, nullable): Business industry (e.g., "Consumer Electronics")
- `response_key` (jsonb): Full API response from FMP company screener
- `updated_at` (timestamptz): Last update timestamp (DB-managed)

**Primary Key**: `ticker`

**Validation Rules**:
- `ticker` must be uppercase, alphanumeric
- `response_key` must contain valid JSON

**Update Strategy**: **Upsert** (ON CONFLICT (ticker) DO UPDATE)

**Application Responsibilities**:
- Fetch from FMP company screener API
- Filter out non-actively trading companies (response_key.isActivelyTrading=true)
- Never write to `updated_at`

**Relationships**:
- Referenced by: `evt_consensus`, `evt_earning`, `txn_events` (for sector/industry enrichment)
- Used by: Filtering logic in getConsensus (only fetch consensus for tickers in this table)

---

#### 3. MetricDefinition (`config_lv2_metric`)

**Purpose**: Defines calculation rules for quantitative and qualitative financial metrics.

**Key Fields**:
- `id` (uuid, PK): Unique metric identifier
- `description` (text): Human-readable metric description
- `source` (text): Data source indicator
- `api_list_id` (uuid, FK, nullable): Reference to `config_lv1_api_list` if API-sourced
- `base_metric_id` (text, nullable): Base metric for derived calculations
- `aggregation_kind` (text, nullable): Aggregation type (e.g., "sum", "mean", "median")
- `aggregation_params` (jsonb, nullable): Parameters for aggregation
- `expression` (text, nullable): Calculation expression
- `domain` (text): Metric domain category (e.g., "quantitative-valuation", "qualitative-consensusSignal", "internal(qual)")
- `response_path` (text, nullable): JSON path to extract value from API response
- `response_key` (text, nullable): JSON key to extract value
- `created_at` (timestamptz): Creation timestamp (DB-managed)

**Primary Key**: `id`

**Validation Rules**:
- `domain` must start with "quantitative-", "qualitative-", or "internal("
- If `domain` starts with "internal(", must have `base_metric_id` defined

**Update Strategy**: Manual (not updated by application; configured by admins)

**Application Responsibilities**:
- Read-only access
- Query by `domain` prefix to determine which metrics to calculate for valuation

**Relationships**:
- Used by: `valuation_service` (backfillEventsTable) and `analyst_service` (fillAnalyst)

---

#### 4. Policy (`config_lv0_policy`)

**Purpose**: System-wide configuration rules controlling date ranges, batch sizes, and calculation scopes.

**Key Fields**:
- `id` (uuid, PK): Policy identifier
- `function` (text): Policy function name (e.g., "fillPriceTrend_dateRange", "priceEodOHLC_dateRange")
- `policy` (jsonb): Policy configuration parameters
- `created_at` (timestamptz): Creation timestamp (DB-managed)

**Primary Key**: `id`

**Validation Rules**:
- `function` must match expected function names
- `policy` must contain required keys based on function type

**Update Strategy**: Manual (configured by admins; rarely updated)

**Application Responsibilities**:
- Read-only access
- Parse `policy` jsonb to extract countStart/countEnd for date range calculations

**Relationships**:
- Referenced by: Price trend generation, OHLC fetching, analyst performance aggregation

---

### Event Source Entities (evt_* tables)

#### 5. ConsensusEvent (`evt_consensus`)

**Purpose**: Analyst price target publications with historical change tracking.

**Key Fields**:
- `id` (uuid, PK): Event identifier
- `ticker` (text, composite key): Stock ticker
- `event_date` (timestamptz, composite key): Publication date (UTC)
- `analyst_name` (text, composite key, nullable): Analyst name
- `analyst_company` (text, composite key, nullable): Analyst firm
- `price_target` (numeric): Target price
- `price_when_posted` (numeric): Stock price at publication
- `price_target_prev` (numeric, nullable): Previous target price (Phase 2 calculated)
- `price_when_posted_prev` (numeric, nullable): Previous posted price (Phase 2 calculated)
- `direction` (text, nullable): Change direction ("up"/"down"/null) (Phase 2 calculated)
- `response_key` (jsonb): Full API response + prev data
- `created_at` (timestamptz): Creation timestamp (DB-managed)

**Composite Unique Key**: `(ticker, event_date, analyst_name, analyst_company)`

**Validation Rules**:
- `ticker` must exist in `config_lv3_targets`
- `event_date` must be valid timestamptz in UTC
- `price_target` and `price_when_posted` must be positive
- At least one of (`analyst_name`, `analyst_company`) must be non-null

**Update Strategy**: **Upsert** in Phase 1 (raw data), **Update-by-key** in Phase 2 (prev/direction)

**State Transitions**:
1. **Phase 1 (Raw Upsert)**: Insert/update ticker, event_date, analyst_name, analyst_company, price_target, price_when_posted, response_key.last
2. **Phase 2 (Change Detection)**: Calculate and update price_target_prev, price_when_posted_prev, direction, response_key.prev for affected partitions

**Application Responsibilities**:
- **Phase 1**: Upsert raw data; never write to price_target_prev, price_when_posted_prev, direction
- **Phase 2**: Query partition (ticker, analyst_name, analyst_company), sort by event_date DESC, calculate prev values, update using `ON CONFLICT DO UPDATE`
- Never write to `id` (if DB-generated) or `created_at`

**Relationships**:
- References: `config_lv3_targets` (ticker)
- Used by: `txn_events` (consolidated view), `config_lv3_analyst` (performance aggregation)

---

#### 6. EarningEvent (`evt_earning`)

**Purpose**: Earnings calendar entries with actual vs estimated financials.

**Key Fields**:
- `id` (uuid, PK): Event identifier
- `ticker` (text, composite key): Stock ticker
- `event_date` (timestamptz, composite key): Earnings date (UTC)
- `response_key` (jsonb): Full API response (epsActual, epsEstimated, revenueActual, revenueEstimated)
- `created_at` (timestamptz): Creation timestamp (DB-managed)

**Composite Unique Key**: `(ticker, event_date)`

**Validation Rules**:
- `ticker` must not be empty
- `event_date` must be valid timestamptz in UTC

**Update Strategy**: **Insert-only** (ON CONFLICT (ticker, event_date) DO NOTHING)

**Application Responsibilities**:
- Insert only; never update existing records
- Never write to `id` or `created_at`

**Relationships**:
- Used by: `txn_events` (consolidated view)

---

### Consolidated Event Entity

#### 7. UnifiedEvent (`txn_events` / `[table.events]`)

**Purpose**: Consolidates all financial events from evt_* tables with enriched sector/industry, valuations, and price trends.

**Key Fields**:
- `id` (uuid, PK): Event identifier
- `ticker` (text, composite key): Stock ticker
- `event_date` (timestamptz, composite key): Event timestamp (UTC)
- `source` (text, composite key): Source table name (e.g., "evt_consensus", "evt_earning")
- `source_id` (uuid, composite key): Original event ID from source table
- `sector` (text, nullable): Business sector (enriched from config_lv3_targets)
- `industry` (text, nullable): Business industry (enriched from config_lv3_targets)
- `value_quantitative` (jsonb, nullable): Quantitative metrics grouped by domain (valuation, momentum, profitability, risk, dilution)
- `value_qualitative` (jsonb, nullable): Qualitative signals (consensusSignal)
- `position_quantitative` (text, nullable): Long/short/undefined based on priceQuantitative vs price
- `position_qualitative` (text, nullable): Long/short/undefined based on priceQualitative vs price
- `disparity_quantitative` (numeric, nullable): (priceQuantitative / price) - 1
- `disparity_qualitative` (numeric, nullable): (priceQualitative / price) - 1
- `price_trend` (jsonb, nullable): Array of {dayOffset, targetDate, open, high, low, close}
- `analyst_performance` (jsonb, nullable): Performance metrics (not directly populated; calculated separately)
- `condition` (text, nullable): User-defined condition group tag
- `created_at` (timestamptz): Creation timestamp (DB-managed)
- `updated_at` (timestamptz): Last update timestamp (DB-managed)

**Composite Unique Key**: `(ticker, event_date, source, source_id)`

**Validation Rules**:
- `ticker`, `event_date`, `source`, `source_id` must all be non-null
- `source` must match pattern "evt_%"
- `position_quantitative` and `position_qualitative` must be one of: "long", "short", "undefined", null

**Update Strategy**: **Upsert** during consolidation (POST /setEventsTable), **Update** for valuation/price_trend filling

**State Transitions**:
1. **Consolidation (setEventsTable)**: Insert (ticker, event_date, source, source_id) from evt_* tables
2. **Sector/Industry Enrichment**: Update sector/industry from config_lv3_targets
3. **Valuation (backfillEventsTable)**: Calculate and update value_quantitative, value_qualitative, position_*, disparity_*
4. **Price Trend Filling**: Calculate and update price_trend array

**Application Responsibilities**:
- During consolidation: Insert with source attribution; never modify existing source/source_id
- During enrichment: Update sector/industry based on overwrite flag
- During valuation: Partially update jsonb fields (overwrite=false) or fully replace (overwrite=true)
- During price trend filling: Update price_trend; fail if row doesn't exist (EVENT_ROW_NOT_FOUND)
- Never write to `id`, `created_at`, `updated_at`

**Relationships**:
- References: `config_lv3_targets` (ticker → sector/industry)
- Aggregated by: `config_lv3_analyst` (performance metrics)
- Used by: Dashboard UI (performance summary table, day-offset metrics)

---

### Analyst Performance Entity

#### 8. AnalystProfile (`config_lv3_analyst`)

**Purpose**: Aggregates performance metrics per (analyst_name, analyst_company) with dayOffset-indexed return distributions.

**Key Fields**:
- `id` (uuid, PK): Profile identifier
- `analyst_name` (text, nullable): Analyst name
- `analyst_company` (text, nullable): Analyst firm
- `analyst_name_key` (text, GENERATED ALWAYS STORED): COALESCE(analyst_name,'__NULL__')
- `analyst_company_key` (text, GENERATED ALWAYS STORED): COALESCE(analyst_company,'__NULL__')
- `performance` (jsonb): Array of {dayOffset, Mean, Median, 1stQuartile, 3rdQuartile, InterquartileRange, standardDeviation, ConfidenceInterval, ProficiencyRate, count}
- `updated_at` (timestamptz): Last update timestamp (DB-managed)

**Composite Unique Key**: `(analyst_name_key, analyst_company_key)` (generated keys, not raw fields)

**Validation Rules**:
- At least one of (analyst_name, analyst_company) must be non-null
- `performance` must be array of objects with required dayOffset field

**Update Strategy**: **Upsert** using generated keys (ON CONFLICT (analyst_name_key, analyst_company_key) DO UPDATE)

**Application Responsibilities**:
- Read `txn_events` where source='evt_consensus' and (analyst_name IS NOT NULL OR analyst_company IS NOT NULL)
- Group by (analyst_name, analyst_company), calculate return distributions per dayOffset
- Upsert using conflict keys (analyst_name_key, analyst_company_key)
- **Never write to `analyst_name_key` or `analyst_company_key`** (DB generates these)
- Never write to `id` or `updated_at`

**Relationships**:
- Aggregates from: `txn_events` (where source='evt_consensus')
- Used by: Dashboard UI (analyst performance views)

---

## Data Flow Diagrams

### Flow 1: Data Collection (GET /sourceData)

```
External APIs (FMP)
     ↓ (fetch)
source_data_service
     ↓ (parse, validate)
     ├─→ config_lv3_market_holidays (upsert)
     ├─→ config_lv3_targets (upsert)
     ├─→ evt_consensus Phase 1 (upsert) → Phase 2 (calculate prev/direction, update)
     └─→ evt_earning (insert-only)
```

### Flow 2: Event Consolidation (POST /setEventsTable)

```
DB Schema Introspection (find evt_* tables)
     ↓
events_service (auto-discover)
     ↓ (iterate tables)
evt_consensus, evt_earning, etc.
     ↓ (extract ticker, event_date, source, source_id)
txn_events (insert with ON CONFLICT DO NOTHING)
     ↓ (enrich)
config_lv3_targets (LEFT JOIN on ticker)
     ↓ (update sector/industry)
txn_events (UPDATE based on overwrite flag)
```

### Flow 3: Valuation (POST /backfillEventsTable)

```
txn_events (read rows with ticker, event_date, source)
     ↓
config_lv2_metric (read quantitative-*, qualitative-* definitions)
     ↓
External APIs (FMP) - fetch quarterly financials, consensus data
     ↓ (calculate)
valuation_service
     ├─→ value_quantitative (PER, PBR, ROE, etc. grouped by domain)
     ├─→ value_qualitative (consensusSignal with direction, last/prev, delta)
     ├─→ position_quantitative / position_qualitative (long/short/undefined)
     └─→ disparity_quantitative / disparity_qualitative (ratio - 1)
     ↓ (update)
txn_events (UPDATE value_*, position_*, disparity_* fields)
```

### Flow 4: Price Trend Filling

```
txn_events (read ticker, event_date, source, source_id)
     ↓
config_lv0_policy (read fillPriceTrend_dateRange policy: countStart, countEnd)
     ↓
config_lv3_market_holidays (identify trading days)
     ↓ (calculate dayOffset dates)
Trading Day Calculator
     ↓ (generate dayOffset array scaffold)
txn_events.price_trend ← [{dayOffset: -14, targetDate: "2025-11-19", open:null, high:null, low:null, close:null}, ...]
     ↓
config_lv0_policy (read priceEodOHLC_dateRange policy)
     ↓ (batch OHLC fetch per ticker, consolidated date range)
External API (FMP historical OHLC)
     ↓ (fill OHLC values, keep future nulls)
txn_events (UPDATE price_trend with filled data)
```

### Flow 5: Analyst Performance Aggregation (POST /fillAnalyst)

```
config_lv0_policy (read fillPriceTrend_dateRange policy)
     ↓
txn_events (read where source='evt_consensus' AND (analyst_name IS NOT NULL OR analyst_company IS NOT NULL))
     ↓ (group by (analyst_name, analyst_company))
analyst_service
     ↓ (for each group)
     ├─→ Extract price_trend arrays
     ├─→ Calculate return = (close / basePrice) - 1 per dayOffset
     ├─→ Exclude samples where close=null or basePrice=null/0
     ├─→ Query config_lv2_metric (domain="internal(qual)")
     └─→ Calculate mean, median, quartiles, IQR, stddev, count per dayOffset
     ↓ (upsert using generated keys)
config_lv3_analyst (INSERT ... ON CONFLICT (analyst_name_key, analyst_company_key) DO UPDATE)
```

---

## Validation Rules Summary

### Timezone Handling
- **All incoming dates**: Parse to UTC immediately
- **Date-only strings (YYYY-MM-DD)**: Treat as YYYY-MM-DD 00:00:00+00:00 UTC
- **Storage**: Use timestamptz for all timestamp fields
- **JSONB dates**: Store as ISO8601 strings with +00:00 suffix
- **Parsing failures**: Return 400 Bad Request

### Database Write Prohibitions
- **Never write to**: created_at, updated_at, analyst_name_key, analyst_company_key
- **Never modify**: Existing source/source_id in txn_events after initial insert
- **evt_earning**: Insert-only (never update existing records)

### Upsert vs Insert-Only Strategies
- **Upsert**: config_lv3_market_holidays, config_lv3_targets, evt_consensus, config_lv3_analyst, txn_events
- **Insert-only**: evt_earning

### JSONB Partial Update Rules
- **overwrite=false**: Update only NULL values within jsonb fields (use jsonb_set for selective key updates)
- **overwrite=true**: Fully replace jsonb field (entire object replaced)

---

## State Machine: getConsensus Two-Phase Processing

### Phase 1: Raw Upsert
- **Input**: Ticker list from config_lv3_targets
- **Action**: Fetch consensus data from FMP API, filter by ticker, upsert to evt_consensus
- **Fields Written**: ticker, event_date, analyst_name, analyst_company, price_target, price_when_posted, response_key.last
- **Fields NOT Written**: price_target_prev, price_when_posted_prev, direction, response_key.prev

### Phase 2: Change Detection
- **Trigger**: After Phase 1 completes for all tickers
- **Target Partitions**:
  - **Default mode**: Affected partitions only (those included in Phase 1 input payload)
  - **Maintenance mode**: Scope-based (all, ticker, event_date_range, partition_keys)
- **Action**: For each target partition:
  1. Query all rows in partition: `SELECT * FROM evt_consensus WHERE ticker=$1 AND analyst_name=$2 AND analyst_company=$3 ORDER BY event_date DESC`
  2. Calculate prev values by iterating pairs (current, previous)
  3. Calculate direction: "up" if price_target > price_target_prev, "down" if less, null if equal/no prev
  4. Update using row key: `UPDATE evt_consensus SET price_target_prev=$1, price_when_posted_prev=$2, direction=$3, response_key=jsonb_set(response_key, '{prev}', $4) WHERE ticker=$5 AND event_date=$6 AND analyst_name=$7 AND analyst_company=$8`
- **Concurrency**: Single execution flow per partition (no concurrent updates to same partition)

---

## Performance Considerations

### Indexing Requirements
- **evt_consensus**: Index on (ticker, event_date, analyst_name, analyst_company) for Phase 2 queries
- **txn_events**: Index on (ticker, source) for analyst aggregation queries
- **config_lv3_market_holidays**: Index on (exchange, date) for trading day lookups

### Batch Operations
- **Upsert batching**: Group inserts into batches of 1000 (DB_UPSERT_BATCH_SIZE)
- **OHLC fetching**: Consolidate per ticker (one API call per ticker covering full date range)
- **Consensus Phase 2**: Process partitions in parallel (different (ticker, analyst_name, analyst_company) combinations)

### JSONB Query Optimization
- Use `jsonb_set()` for partial updates within JSONB fields
- Use `->` and `->>` operators for JSONB path extraction
- Create GIN indexes on frequently queried JSONB fields if needed

---

## Open Questions (None)

All data model decisions have been finalized based on feature specification and guideline documents.
