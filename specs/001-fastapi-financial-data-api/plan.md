# Implementation Plan: FastAPI Financial Data API Backend System

**Branch**: `001-fastapi-financial-data-api` | **Date**: 2025-12-18 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-fastapi-financial-data-api/spec.md`

## Summary

This implementation plan delivers a production-ready FastAPI backend system that collects financial data from external APIs (FMP), processes and enriches it through multiple transformation stages, and provides both API endpoints and a dashboard UI for financial analysts. The system handles market holidays, company targets, analyst consensus, earnings data, quantitative/qualitative valuations, price trend time series, and analyst performance aggregation. All data is stored in Supabase Postgres via direct SQL connections (no PostgREST), with strict adherence to database responsibilities (never writing to generated columns like created_at, updated_at, analyst_name_key, analyst_company_key).

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**:
- FastAPI 0.104+ (ASGI web framework)
- asyncpg 0.29+ OR psycopg3 3.1+ (direct Postgres async driver)
- Pydantic 2.5+ (data validation)
- httpx 0.25+ (async HTTP client for external APIs)
- Python-dateutil 2.8+ (timezone-aware date parsing)

**Storage**: Supabase Postgres (direct SQL only; PostgREST/Supabase client forbidden)
**Testing**: pytest 7.4+, pytest-asyncio 0.21+, pytest-cov for coverage
**Target Platform**: Render.com (Linux container, Python runtime)
**Project Type**: Web (FastAPI backend + frontend UI)
**Performance Goals**:
- GET /sourceData: 500 tickers in <10 min
- POST /setEventsTable: 10,000 events in <2 min
- POST /backfillEventsTable: 5,000 events in <5 min
- Price trend filling: 1,000 events × 29 dayOffsets in <8 min
- POST /fillAnalyst: 100 analysts × 5,000 events in <3 min
- Dashboard table interactions: <200ms response time

**Constraints**:
- No supabase-js, PostgREST, or Supabase Python client
- All DB I/O via raw SQL
- Never write to: created_at, updated_at, analyst_name_key, analyst_company_key
- Respect FMP API rate limits (dynamic batch sizing)
- UTC-only timezone handling
- HTTP 207 Multi-Status for batch operations

**Scale/Scope**:
- 10+ evt_* source tables
- 500+ tickers
- 100,000+ events (txn_events)
- 100+ analysts
- 4 routes (control, requests, conditionGroup, dashboard)
- 4 major endpoints + UI

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Since no project-specific constitution file exists, we apply default software engineering principles:

### Simplicity Principle
✅ **PASS**: System uses straightforward FastAPI patterns, direct SQL (no ORM complexity), and minimal abstraction layers. UI uses plain HTML/CSS/JS or React without component libraries.

### Testability Principle
✅ **PASS**: Each endpoint and phase (getConsensus Phase 1/2, valuation, priceTrend, fillAnalyst) is independently testable. Pytest with async support enables unit, integration, and contract testing.

### Single Responsibility Principle
✅ **PASS**: Clear separation between data collection (GET /sourceData), consolidation (POST /setEventsTable), valuation (POST /backfillEventsTable), and aggregation (POST /fillAnalyst). Each endpoint has a single purpose.

### Database Responsibility Boundary
✅ **PASS**: Application explicitly forbidden from writing to DB-managed columns. Upsert vs insert-only strategies clearly defined per table. This prevents logic duplication between app and database.

### Performance & Observability
✅ **PASS**: Structured logging with fixed format, ETA calculations, rate limit tracking, and per-phase counters (success/fail/skip/update/insert/conflict) enable bottleneck identification without additional debugging.

**No violations requiring complexity justification.**

## Project Structure

### Documentation (this feature)

```text
specs/001-fastapi-financial-data-api/
├── plan.md              # This file (/speckit.plan output)
├── research.md          # Phase 0 output (decisions on asyncpg vs psycopg3, etc.)
├── data-model.md        # Phase 1 output (entity relationships, validation rules)
├── quickstart.md        # Phase 1 output (local dev setup, deployment)
├── contracts/           # Phase 1 output (OpenAPI specs per endpoint)
│   ├── sourceData.yaml
│   ├── setEventsTable.yaml
│   ├── backfillEventsTable.yaml
│   └── fillAnalyst.yaml
└── tasks.md             # Phase 2 output (/speckit.tasks - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
# Web application structure (backend API + frontend UI)

backend/
├── src/
│   ├── main.py                    # FastAPI app entry point
│   ├── config.py                  # Environment variables, DB config
│   ├── database/
│   │   ├── connection.py          # Async Postgres connection pool
│   │   └── queries/               # SQL query modules per domain
│   │       ├── holidays.py
│   │       ├── targets.py
│   │       ├── consensus.py
│   │       ├── earning.py
│   │       ├── events.py
│   │       ├── analyst.py
│   │       └── metrics.py
│   ├── models/
│   │   ├── request_models.py      # Pydantic request schemas
│   │   ├── response_models.py     # Pydantic response schemas
│   │   └── domain_models.py       # Domain entities (optional thin layer)
│   ├── services/
│   │   ├── external_api.py        # FMP API client with rate limiting
│   │   ├── source_data_service.py # GET /sourceData orchestration
│   │   ├── events_service.py      # POST /setEventsTable logic
│   │   ├── valuation_service.py   # POST /backfillEventsTable logic
│   │   ├── analyst_service.py     # POST /fillAnalyst logic
│   │   └── utils/
│   │       ├── datetime_utils.py  # UTC parsing, trading day calculation
│   │       ├── batch_utils.py     # Dynamic batch sizing
│   │       └── logging_utils.py   # Structured log formatter
│   ├── routers/
│   │   ├── source_data.py         # GET /sourceData endpoint
│   │   ├── events.py              # POST /setEventsTable, POST /backfillEventsTable
│   │   └── analyst.py             # POST /fillAnalyst endpoint
│   └── middleware/
│       └── logging_middleware.py  # Request logging, reqId injection
├── tests/
│   ├── contract/                  # OpenAPI schema validation tests
│   ├── integration/               # DB + external API integration tests
│   │   ├── test_source_data_flow.py
│   │   ├── test_events_consolidation.py
│   │   ├── test_valuation_pipeline.py
│   │   └── test_analyst_aggregation.py
│   └── unit/                      # Service/utility unit tests
│       ├── test_datetime_utils.py
│       ├── test_batch_utils.py
│       └── test_consensus_phase2.py
├── requirements.txt
├── pyproject.toml                 # Poetry/setuptools config
└── README.md

frontend/
├── src/
│   ├── index.html                 # Entry point
│   ├── main.js                    # App initialization
│   ├── router.js                  # Route handling (control/requests/conditionGroup/dashboard)
│   ├── styles/
│   │   ├── design-tokens.css      # Colors, spacing, typography from 2_designSystem.ini
│   │   ├── global.css             # Reset, base styles
│   │   └── components.css         # Reusable UI patterns
│   ├── components/
│   │   ├── table/                 # Table system (thead sticky, filters, sorts)
│   │   │   ├── DataTable.js
│   │   │   ├── ColumnSelector.js
│   │   │   ├── FilterPopover.js
│   │   │   └── SortHeader.js
│   │   ├── forms/
│   │   │   ├── RequestForm.js     # Request route form builder
│   │   │   └── ConditionGroupForm.js
│   │   └── dashboard/
│   │       ├── KPICard.js
│   │       ├── PerformanceTable.js
│   │       └── DayOffsetTable.js
│   ├── pages/
│   │   ├── ControlPage.js         # control route
│   │   ├── RequestsPage.js        # requests route
│   │   ├── ConditionGroupPage.js  # conditionGroup route
│   │   └── DashboardPage.js       # dashboard route
│   ├── services/
│   │   ├── api.js                 # Fetch wrapper for backend endpoints
│   │   └── localStorage.js        # Persistence for filters/columns/sort
│   └── assets/
│       └── icons/                 # SVG icon assets (no Unicode glyphs)
├── tests/
│   └── ui/                        # UI validation tests (design system compliance)
└── package.json (if using build tools)
```

**Structure Decision**: Web application structure chosen because the feature includes both API endpoints (backend) and a dashboard UI (frontend). The backend follows service-oriented architecture with clear separation between routers (HTTP layer), services (business logic), and database (data access). The frontend follows component-based architecture aligned with 2_designSystem.ini constraints (no UI libraries, SVG icons only).

## Complexity Tracking

> **No complexity violations - this section is empty**

Since all Constitution Check gates passed, there are no violations requiring justification.
