# AlSign Financial Data API Constitution

## Core Principles

### I. Simplicity
Every component must have a clear, singular purpose. Avoid unnecessary abstraction layers. Use straightforward FastAPI patterns and direct SQL queries. The UI must use plain HTML/CSS/React without component libraries.

**MUST**:
- Use direct SQL connections (no ORM, no PostgREST)
- Keep service layer thin (business logic only)
- Avoid premature optimization

**MUST NOT**:
- Use supabase-js, PostgREST, or Supabase Python client for CRUD
- Add abstraction layers without clear justification
- Use UI component libraries (shadcn/ui, MUI, Ant, Chakra, Mantine)

### II. Testability
Each endpoint and business logic phase must be independently testable. Unit tests, integration tests, and contract tests must be possible without complex setup.

**MUST**:
- Each user story must be independently testable
- Each endpoint must have clear input/output contracts
- Use pytest with async support for all backend tests

**SHOULD**:
- Provide seed data scripts for independent testing
- Mock external API calls in unit tests
- Use contract testing for API schemas

### III. Single Responsibility
Clear separation between data collection, consolidation, valuation, and aggregation. Each router handles one concern. Each service implements one business capability.

**MUST**:
- One router per major domain (source_data, events, analyst, dashboard, control, condition_group)
- One service per business operation
- One database query module per entity type

**MUST NOT**:
- Mix concerns across layers (e.g., router doing database queries directly)
- Duplicate business logic across services

### IV. Database Responsibility Boundary (NON-NEGOTIABLE)
The application must never write to database-managed columns. This prevents logic duplication and maintains clear boundaries.

**MUST NEVER** write to:
- `created_at` (DB manages via DEFAULT NOW())
- `updated_at` (DB manages via trigger)
- `analyst_name_key` (DB manages via GENERATED ALWAYS AS)
- `analyst_company_key` (DB manages via GENERATED ALWAYS AS)

**MUST**:
- Use upsert for: config_lv3_market_holidays, config_lv3_targets, evt_consensus, config_lv3_analyst, txn_events
- Use insert-only for: evt_earning
- Log 'POLICY_CONFLICT_DB_SCHEMA' warning if guideline conflicts with DB constraints

**Violation of this principle is CRITICAL and will cause database errors.**

### V. Performance & Observability
All operations must be observable through structured logging. Performance bottlenecks must be identifiable from logs alone without additional debugging.

**MUST**:
- Use fixed 1-line log format: `[endpoint | phase] elapsed=Xms | progress=done/total(pct%) | eta=Yms | rate=perMin/limitPerMin(usagePct%) | batch=size(mode) | ok=X fail=Y skip=Z upd=A ins=B cf=C | warn=[codes] | message`
- Calculate and log ETA for long-running operations
- Track success/fail/skip/update/insert/conflict counts per operation
- Log all rate limit adjustments with current usage percentage

**MUST**:
- Respect external API rate limits (dynamic batch sizing)
- Meet performance targets: GET /sourceData <10min for 500 tickers, POST /setEventsTable <2min for 10K events
- Dashboard interactions <200ms response time

### VI. Data Integrity & Timezone Handling
All date/time operations must use UTC. No local timezone conversions. All dates must be traceable and consistent.

**MUST**:
- Parse all incoming dates to UTC
- Store all timestamps as timestamptz (PostgreSQL)
- Store dates in jsonb as UTC ISO8601 strings with +00:00 timezone
- Return 400 Bad Request on date parsing failures

**MUST NOT**:
- Use local timezones
- Store timezone-naive datetime objects
- Assume any date is in a specific timezone without validation

### VII. Security & Secrets Management
No secrets in code. All sensitive data via environment variables. Input validation on all user-provided data.

**MUST**:
- Load API keys from environment variables only
- Validate all user inputs (ticker format, date ranges, column names)
- Use SQL parameter binding (never string interpolation)
- Whitelist column names for dynamic queries (prevent SQL injection)

**MUST NOT**:
- Commit .env files to git
- Log API keys or sensitive credentials
- Trust user input without validation
- Use string concatenation for SQL queries

## Design System Compliance (UI)

### VIII. Design System Lock (NON-NEGOTIABLE)
The frontend must exactly replicate the design system specification. No creative interpretation.

**MUST**:
- Use exact dimensions: btn-sm (32px height), btn-md (40px height)
- Use 8px spacing grid: only 8/12/16/24/32px values
- Use exact font weights: only 400/500/600
- Use exact z-index values: 0/10/20/21/30/100/200
- Use SVG icons only (no Unicode glyphs, no icon libraries)

**MUST NOT**:
- Deviate from button/table dimensions in 2_designSystem.ini
- Use arbitrary spacing (e.g., 6px, 10px, 14px)
- Use font weights other than 400/500/600
- Use UI component libraries or icon libraries
- Use Unicode glyphs for functional icons (arrows, filters, etc.)

**Source of Truth**: `alsign/prompt/2_designSystem.ini`

## Error Handling Standards

### IX. Structured Error Responses
All errors must use standardized codes and formats. HTTP status codes must match error semantics.

**MUST**:
- Use ErrorCode enum: POLICY_NOT_FOUND, INVALID_POLICY, INVALID_CONSENSUS_DATA, INVALID_PRICE_TREND_RANGE, METRIC_NOT_FOUND, EVENT_ROW_NOT_FOUND, AMBIGUOUS_EVENT_DATE, INTERNAL_ERROR
- Return HTTP 207 Multi-Status for batch operations with per-record status
- Return summary with counts: success/fail/skip/update/insert/conflict
- Return 400 Bad Request for client errors (invalid input)
- Return 500 Internal Server Error for server errors

**MUST NOT**:
- Return generic "error occurred" messages without error codes
- Mix successful and failed batch items in HTTP 200 response
- Expose internal stack traces to API clients

## Governance

This constitution supersedes all other development practices. All implementation decisions must align with these principles.

**Amendments**:
- Require documentation of rationale
- Require approval from project stakeholders
- Require migration plan if existing code conflicts

**Enforcement**:
- All code reviews must verify constitution compliance
- Complexity must be justified against these principles
- Violations of NON-NEGOTIABLE principles are blocking issues

**Version**: 1.0.0 | **Ratified**: 2025-12-18 | **Last Amended**: 2025-12-18
