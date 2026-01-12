# AlSign Financial Data API - Backend

FastAPI-based JSON Web API for financial data processing with direct Supabase Postgres access.

## Overview

This backend system implements a comprehensive financial data pipeline with:
- Market foundation data collection (holidays, company targets, analyst consensus, earnings)
- Event consolidation from multiple sources
- Quantitative and qualitative value metric calculation
- Price trend time series generation
- Analyst performance aggregation

## Architecture

### Core Principles (from constitution.md)

1. **Simplicity**: Direct SQL connections (asyncpg), no ORM, no PostgREST
2. **Testability**: Each user story is independently testable
3. **Single Responsibility**: Clear separation between routers, services, and database queries
4. **Database Responsibility Boundary**: Never write to DB-managed columns (created_at, updated_at, analyst_name_key, analyst_company_key)
5. **Performance & Observability**: Structured logging with fixed 1-line format
6. **UTC-Only Timezone Handling**: All dates/times in UTC (FR-114)
7. **Security**: No secrets in code, all via environment variables
8. **Structured Error Responses**: Standardized error codes and HTTP 207 Multi-Status for batch operations

### Key Requirements

#### FR-002: Direct Database Access
- System uses asyncpg for all database operations
- Raw SQL queries only (no ORM, no PostgREST, no Supabase client libraries)

#### FR-029: Dynamic Batch Sizing with Rate Limiting
Algorithm: `batch_size = max(1, min(remaining_items, floor(limit_per_min * (1 - usage_pct) / 2)))`
- `usage_pct = current_requests_per_minute / config_lv1_api_service.usagePerMin`
- When `usage_pct >= 0.80`: reduce to 1 (throttled mode)
- When `usage_pct < 0.50`: increase up to 50 (aggressive mode)

#### FR-029-A: Batch Mode Reporting
- **"dynamic"**: normal adaptive sizing (0.50 ≤ usage_pct < 0.80)
- **"throttled"**: usage_pct ≥ 0.80, batch_size = 1
- **"aggressive"**: usage_pct < 0.50, batch_size up to 50
- **"minimum"**: batch_size = 1 (forced minimum)

#### FR-027: API Call Optimization
- System makes exactly 1 API call per ticker per OHLC date range
- Consolidates requests across multiple event dates for same ticker

#### FR-114: UTC-Only Timezone Handling
1. Parse all incoming date strings to Python datetime objects in UTC
2. Treat date-only strings (YYYY-MM-DD) as YYYY-MM-DD 00:00:00+00:00 UTC
3. Store all timestamp fields as timestamptz in PostgreSQL
4. Store dates within jsonb as UTC ISO8601 strings with +00:00 timezone
5. Return 400 Bad Request when date parsing fails

#### FR-031/FR-122: Structured Logging Format
```
[endpoint | phase] elapsed=Xms | progress=done/total(pct%) | eta=Yms | rate=perMin/limitPerMin(usagePct%) | batch=size(mode) | ok=X fail=Y skip=Z upd=A ins=B cf=C | warn=[codes] | message
```
Where mode is one of: dynamic, throttled, aggressive, minimum

## Project Structure

```
backend/
├── src/
│   ├── config.py                    # Environment configuration (Pydantic)
│   ├── main.py                      # FastAPI application entry point
│   ├── database/
│   │   ├── connection.py            # asyncpg connection pool
│   │   └── queries/                 # SQL query modules
│   │       ├── holidays.py
│   │       ├── targets.py
│   │       ├── consensus.py
│   │       ├── earning.py
│   │       ├── events.py
│   │       ├── metrics.py
│   │       ├── analyst.py
│   │       └── policies.py
│   ├── models/
│   │   ├── domain_models.py         # ErrorCode enum, Position enum
│   │   ├── request_models.py        # Pydantic request schemas
│   │   └── response_models.py       # Pydantic response schemas
│   ├── routers/
│   │   ├── source_data.py           # GET /sourceData
│   │   ├── events.py                # POST /setEventsTable, /backfillEventsTable
│   │   ├── analyst.py               # POST /fillAnalyst
│   │   ├── dashboard.py             # GET /dashboard/*
│   │   └── conditionGroup.py        # Condition group management
│   ├── services/
│   │   ├── external_api.py          # FMP API client with rate limiting
│   │   ├── source_data_service.py   # Data collection logic
│   │   ├── events_service.py        # Event consolidation logic
│   │   ├── valuation_service.py     # Metric calculation logic
│   │   ├── analyst_service.py       # Analyst aggregation logic
│   │   └── utils/
│   │       ├── batch_utils.py       # RateLimiter, dynamic batch sizing
│   │       ├── datetime_utils.py    # UTC parsing, trading day calc
│   │       └── logging_utils.py     # Structured logging formatter
│   └── middleware/
│       └── logging_middleware.py    # Request/response logging
├── scripts/
│   ├── setup_supabase.sql           # Database schema setup
│   ├── test_supabase_connection.py  # Connection test script
│   └── execute_supabase_setup.py    # Automated setup script
├── tests/
│   ├── contract/                    # API contract tests
│   ├── integration/                 # Integration tests
│   └── unit/                        # Unit tests
├── requirements.txt
├── .env.example
└── README.md
```

## Setup

### Prerequisites

- Python 3.11+
- Supabase Postgres database (tables created via setup_supabase.sql)
- FMP API key (from https://financialmodelingprep.com)

### Installation

1. Clone repository and navigate to backend directory
```bash
cd backend
```

2. Create virtual environment
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies
```bash
pip install -r requirements.txt
```

4. Configure environment variables
```bash
cp .env.example .env
# Edit .env with your credentials:
# - DATABASE_URL (Supabase connection pooler URL with port 6543)
# - FMP_API_KEY
# - FMP_BASE_URL (default: https://financialmodelingprep.com/api/v3)
```

5. Test database connection
```bash
python scripts/test_supabase_connection.py
```

### Running the Server

Development server with auto-reload:
```bash
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

Production server:
```bash
uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers 4
```

## API Endpoints

### Data Collection

#### GET /sourceData
Fetch and store market foundation data from FMP APIs.

Query Parameters:
- `mode` (optional): Comma-separated list of modes (holiday, target, consensus, earning)
- `past` (optional): Boolean, only effective when mode includes "earning"
- `calc_mode` (optional): "default" or "maintenance" (for consensus Phase 2)
- `calc_scope` (optional): "all", "ticker", "event_date_range", "partition_keys"
- Additional scope parameters based on calc_scope

**Modes:**
- `holiday`: Fetch market holidays → config_lv3_market_holidays
- `target`: Fetch company targets → config_lv3_targets
- `consensus`: Fetch analyst consensus (2-phase processing) → evt_consensus
- `earning`: Fetch earnings calendar → evt_earning

### Event Processing

#### POST /setEventsTable
Consolidate events from evt_* tables into txn_events with sector/industry enrichment.

Query Parameters:
- `overwrite` (default: false): When false, only update NULL sector/industry; when true, update NULL + mismatched
- `dryRun` (default: false): Return projected changes without modification
- `schema` (default: "public"): Target schema
- `table` (optional): Comma-separated list of specific evt_* tables

#### POST /backfillEventsTable
Calculate quantitative and qualitative value metrics for events.

Query Parameters:
- `overwrite` (default: false): When false, partially update NULL values in value_* jsonb; when true, fully replace
- `from` / `to` (optional): Filter by event_date range
- `tickers` (optional): Comma-separated tickers to process
- `metrics` (optional): Comma-separated metric IDs to recalculate
- `batch_size` (optional): Number of unique tickers per batch (range: 1-2,000; equivalent to calling with grouped tickers)
- `max_workers` (optional): Concurrency for ticker processing (tickers in a batch run in parallel)

### Analyst Performance

#### POST /fillAnalyst
Aggregate analyst performance metrics from consensus signals and price trends.

Returns: HTTP 207 Multi-Status with per-group results and summary

### Dashboard

#### GET /dashboard/kpis
Returns coverage and data freshness KPIs.

#### GET /dashboard/performanceSummary
Returns txn_events data with pagination, filtering, sorting.

#### GET /dashboard/dayOffsetMetrics
Returns aggregated return statistics grouped by analyst/sector/other dimensions.

## Health Check

#### GET /health
Returns server and database status.

Response:
```json
{
  "status": "healthy",
  "checks": {
    "database": {
      "status": "healthy",
      "message": "Connected"
    }
  }
}
```

## API Documentation

- Interactive API docs: http://localhost:8000/docs (Swagger UI)
- Alternative docs: http://localhost:8000/redoc (ReDoc)

## Testing

Run all tests:
```bash
pytest
```

Run specific test suite:
```bash
pytest tests/unit/
pytest tests/integration/
pytest tests/contract/
```

## Database Notes

### Never Write to These Columns
- `created_at` (DB DEFAULT NOW())
- `updated_at` (DB trigger)
- `analyst_name_key` (DB GENERATED ALWAYS AS)
- `analyst_company_key` (DB GENERATED ALWAYS AS)

### Upsert Strategy Tables
- config_lv3_market_holidays
- config_lv3_targets
- evt_consensus
- config_lv3_analyst
- txn_events

### Insert-Only Strategy Tables
- evt_earning (ON CONFLICT DO NOTHING)

## Rate Limiting

Rate limits are configured in `config_lv1_api_service.usagePerMin` column.

The system uses sliding window rate limiting with dynamic batch sizing:
- Tracks requests in 60-second window
- Adjusts batch size based on current usage percentage
- Logs rate information in every progress log

## Logging

All operations use structured logging with fixed 1-line format (FR-031/FR-122).

Example log:
```
[GET /sourceData | getConsensus] elapsed=1234ms | progress=50/100(50%) | eta=1234ms | rate=180/250(72%) | batch=10(dynamic) | ok=45 fail=2 skip=3 upd=30 ins=15 cf=5 | warn=[] | Processing consensus data
```

## Deployment

### Render.com

1. Create Web Service in Render.com dashboard
2. Connect GitHub repository
3. Configure build command: `pip install -r requirements.txt`
4. Configure start command: `uvicorn src.main:app --host 0.0.0.0 --port $PORT`
5. Set environment variables:
   - `DATABASE_URL`
   - `FMP_API_KEY`
   - `FMP_BASE_URL`
   - `LOG_LEVEL` (default: INFO)
   - `ENVIRONMENT` (default: production)
   - `CORS_ORIGINS` (JSON array)

Health check path: `/health`

## Troubleshooting

### Database Connection Issues

If you see `statement_cache_size` errors:
- Ensure `statement_cache_size=0` is set in connection.py for Supabase pooler compatibility

### Rate Limit Warnings

If you see high usage warnings in logs:
- System automatically throttles to batch_size=1 when usage ≥ 80%
- Check `config_lv1_api_service.usagePerMin` configuration
- Consider upgrading FMP API plan if sustained high usage

### Timezone Errors

If you see 400 Bad Request on date inputs:
- Ensure all dates are ISO8601 format with timezone
- Date-only strings (YYYY-MM-DD) are treated as 00:00:00 UTC
- System enforces UTC-only handling (FR-114)

## Additional Documentation

- Feature Specification: `specs/001-fastapi-financial-data-api/spec.md`
- Implementation Plan: `specs/001-fastapi-financial-data-api/plan.md`
- Task List: `specs/001-fastapi-financial-data-api/tasks.md`
- Constitution: `.specify/memory/constitution.md`
- Quickstart Guide: `QUICKSTART.md`
- Supabase Setup: `SUPABASE_SETUP.md`

## License

[Add your license here]

## Support

For issues and questions, see:
- Feature specification documentation in `specs/` directory
- Analysis reports in `.specify/reports/` directory
