# Research: FastAPI Financial Data API Backend System

**Date**: 2025-12-18
**Branch**: `001-fastapi-financial-data-api`

## Overview

This document captures research decisions for technical unknowns, dependency choices, and implementation patterns for the FastAPI Financial Data API system.

## Technology Decisions

### 1. Async Postgres Driver: asyncpg vs psycopg3

**Decision**: Use **asyncpg** 0.29+

**Rationale**:
- **Performance**: asyncpg is a pure Python async driver optimized for performance, typically 2-3x faster than psycopg3 in async mode for bulk operations
- **Maturity**: asyncpg has been the de facto standard for async Postgres in Python since 2016, with extensive production usage
- **API Design**: asyncpg's API is designed from the ground up for async, whereas psycopg3 maintains compatibility with psycopg2's sync API
- **Connection Pooling**: asyncpg has built-in connection pooling optimized for async workloads
- **Type Mapping**: Excellent support for PostgreSQL's jsonb type which is heavily used in this project

**Alternatives Considered**:
- **psycopg3**: More feature-complete for advanced PostgreSQL features (LISTEN/NOTIFY, COPY streams), but marginally slower for basic CRUD
- **SQLAlchemy AsyncEngine**: Rejected due to requirement for "direct SQL only" - ORM abstraction prohibited

**Implementation Notes**:
- Use `asyncpg.create_pool()` for connection pooling
- Prefer `$1, $2` positional parameters over named parameters for consistency
- Use `fetch()` for multiple rows, `fetchrow()` for single row, `fetchval()` for scalar
- Handle jsonb encoding/decoding explicitly using `json.dumps()` / `json.loads()`

---

### 2. HTTP Client for External APIs: httpx vs aiohttp

**Decision**: Use **httpx** 0.25+

**Rationale**:
- **API Consistency**: httpx provides a requests-like API (familiar to Python developers) with full async support
- **HTTP/2 Support**: httpx supports HTTP/2 which can improve performance for repeated calls to same host (FMP API)
- **Timeout Control**: Better timeout configuration (connect timeout vs read timeout vs total timeout)
- **Type Hints**: httpx has excellent type hint coverage for better IDE support and type checking

**Alternatives Considered**:
- **aiohttp**: Mature and widely used, but API is less intuitive than requests-like interface
- **urllib3**: Sync only, not suitable for async FastAPI context

**Implementation Notes**:
- Use `httpx.AsyncClient()` with connection pooling for all FMP API calls
- Configure timeouts: `timeout=httpx.Timeout(10.0, connect=5.0)`
- Implement retry logic with exponential backoff for transient failures (429, 503)
- Track rate limits using response headers if provided by FMP

---

### 3. Date/Time Handling: python-dateutil vs arrow vs pendulum

**Decision**: Use **python-dateutil** 2.8+ with stdlib `datetime`

**Rationale**:
- **Stdlib Integration**: python-dateutil extends stdlib `datetime` without replacing it
- **Parsing Flexibility**: `dateutil.parser.parse()` handles wide variety of date formats including ISO8601
- **Timezone Support**: Works seamlessly with `pytz` or `zoneinfo` (Python 3.9+) for UTC enforcement
- **No Dependencies**: python-dateutil is widely used and has minimal dependencies

**Alternatives Considered**:
- **arrow**: More opinionated API, but adds overhead and not as widely adopted
- **pendulum**: Good API but heavyweight for our needs (we only need parsing + UTC enforcement)
- **stdlib datetime only**: Insufficient - need robust parsing for ISO8601 variants

**Implementation Notes**:
- Use `datetime.fromisoformat()` for strict ISO8601 (preferred when format is known)
- Use `dateutil.parser.parse()` for flexible parsing (when format varies)
- Always convert to UTC immediately: `dt.astimezone(timezone.utc)`
- Store in DB as timestamptz, extract from DB as timezone-aware datetime
- For jsonb dates: store as ISO8601 string with +00:00 suffix

---

### 4. Testing Strategy: pytest fixtures vs factory patterns

**Decision**: Use **pytest fixtures** with factory patterns for complex data

**Rationale**:
- **Pytest Standard**: Fixtures are the idiomatic way to manage test dependencies in pytest
- **Reusability**: Fixtures can be shared across test files via `conftest.py`
- **Cleanup**: Fixtures support automatic cleanup with yield syntax
- **Combination**: Factory patterns within fixtures provide flexibility for parameterized data

**Implementation Pattern**:
```python
# conftest.py
@pytest.fixture
async def db_pool():
    pool = await asyncpg.create_pool(dsn=TEST_DATABASE_URL)
    yield pool
    await pool.close()

@pytest.fixture
def ticker_factory():
    def _create_ticker(symbol="AAPL", sector="Technology", industry="Consumer Electronics"):
        return {"ticker": symbol, "sector": sector, "industry": industry}
    return _create_ticker

@pytest.fixture
async def populated_evt_consensus(db_pool, ticker_factory):
    # Insert test data and return IDs
    pass
```

**Test Coverage Goals**:
- Unit tests: 80%+ coverage for services/utils
- Integration tests: All endpoint flows (P1 user stories)
- Contract tests: OpenAPI schema compliance for all endpoints

---

### 5. Trading Day Calculation: Business Days vs Market Holidays

**Decision**: Implement **custom trading day calculator** using `config_lv3_market_holidays`

**Rationale**:
- **Accuracy**: Standard business day calculators (e.g., numpy.busday_count) don't account for market-specific holidays (Thanksgiving, Good Friday, etc.)
- **Database as Source of Truth**: `config_lv3_market_holidays` is maintained and updated via GET /sourceData?mode=holiday
- **Timezone Consistency**: Market holidays are timezone-specific; custom calculator enforces UTC consistency

**Implementation Approach**:
```python
async def is_trading_day(date: datetime.date, exchange: str, db_pool) -> bool:
    """Check if given date is a trading day for exchange."""
    # Check if weekend
    if date.weekday() >= 5:  # Saturday=5, Sunday=6
        return False

    # Check if market holiday
    result = await db_pool.fetchval(
        "SELECT is_fully_closed FROM config_lv3_market_holidays WHERE exchange=$1 AND date=$2",
        exchange, date
    )
    return result is not True  # None (no record) means trading day

async def next_trading_day(date: datetime.date, exchange: str, db_pool) -> datetime.date:
    """Find next trading day after given date."""
    current = date
    while not await is_trading_day(current, exchange, db_pool):
        current += timedelta(days=1)
    return current

async def calculate_dayOffset_dates(event_date: datetime.date, count_start: int, count_end: int, exchange: str, db_pool) -> List[Tuple[int, datetime.date]]:
    """Generate (dayOffset, targetDate) pairs for price trend."""
    # Map dayOffset=0 to next trading day if event_date is non-trading
    base_date = await next_trading_day(event_date, exchange, db_pool) if not await is_trading_day(event_date, exchange, db_pool) else event_date

    results = []
    # ... iterate trading days forward and backward from base_date
    return results
```

**Alternatives Considered**:
- **numpy.busday_count**: Doesn't handle market-specific holidays
- **pandas.tseries.offsets.BusinessDay**: Requires full pandas dependency (too heavy)
- **Hardcoded holiday list**: Not maintainable; database approach allows updates without code changes

---

### 6. Rate Limiting Strategy: Token Bucket vs Sliding Window

**Decision**: Use **sliding window** with dynamic batch sizing

**Rationale**:
- **FMP API Constraints**: FMP rate limits are typically defined as "X calls per minute"
- **Burst Tolerance**: Sliding window allows bursts within window while maintaining average rate
- **Dynamic Adjustment**: Based on `config_lv1_api_service.usagePerMin`, batch size adjusts to avoid rate limit violations

**Implementation Approach**:
```python
class RateLimiter:
    def __init__(self, calls_per_minute: int):
        self.calls_per_minute = calls_per_minute
        self.window_size = 60.0  # seconds
        self.call_timestamps = deque()

    async def acquire(self):
        """Wait if necessary to stay within rate limit."""
        now = time.time()

        # Remove timestamps outside window
        while self.call_timestamps and self.call_timestamps[0] < now - self.window_size:
            self.call_timestamps.popleft()

        # If at capacity, wait until oldest call ages out
        if len(self.call_timestamps) >= self.calls_per_minute:
            sleep_time = self.call_timestamps[0] + self.window_size - now + 0.1  # +0.1 buffer
            await asyncio.sleep(sleep_time)

        self.call_timestamps.append(now)

    def get_current_rate(self) -> float:
        """Calculate calls per minute in current window."""
        now = time.time()
        recent_calls = [ts for ts in self.call_timestamps if ts > now - self.window_size]
        return len(recent_calls)

    def adjust_batch_size(self, current_batch_size: int) -> int:
        """Dynamically adjust batch size based on usage."""
        usage_pct = self.get_current_rate() / self.calls_per_minute
        if usage_pct < 0.3:
            return int(current_batch_size * 1.5)  # Aggressive mode
        elif usage_pct > 0.7:
            return max(1, int(current_batch_size * 0.7))  # Conservative mode
        return current_batch_size  # Maintain
```

**Alternatives Considered**:
- **Token Bucket**: More complex to implement; sliding window sufficient for our use case
- **Simple sleep between calls**: Too naive; wastes time when under rate limit

---

### 7. Error Code Standardization: String vs Enum

**Decision**: Use **Python Enum** for error codes

**Rationale**:
- **Type Safety**: Enum prevents typos in error code strings
- **Discoverability**: IDEs can autocomplete error codes
- **Documentation**: Enum docstrings provide inline documentation

**Implementation**:
```python
from enum import Enum

class ErrorCode(str, Enum):
    """Standardized error codes for API responses."""
    POLICY_NOT_FOUND = "POLICY_NOT_FOUND"
    INVALID_POLICY = "INVALID_POLICY"
    INVALID_CONSENSUS_DATA = "INVALID_CONSENSUS_DATA"
    INVALID_PRICE_TREND_RANGE = "INVALID_PRICE_TREND_RANGE"
    METRIC_NOT_FOUND = "METRIC_NOT_FOUND"
    EVENT_ROW_NOT_FOUND = "EVENT_ROW_NOT_FOUND"
    AMBIGUOUS_EVENT_DATE = "AMBIGUOUS_EVENT_DATE"
    INTERNAL_ERROR = "INTERNAL_ERROR"
```

---

### 8. Logging Format: Structured Logging Library vs Manual

**Decision**: **Manual structured logging** using Python logging with custom formatter

**Rationale**:
- **Simplicity**: Fixed 1-line format specified in requirements is straightforward to implement
- **No Dependencies**: Avoid adding structlog or python-json-logger dependencies
- **Performance**: Manual formatting is faster than full structured logging libraries

**Implementation**:
```python
import logging

class StructuredFormatter(logging.Formatter):
    def format(self, record):
        # Extract from record.extra
        endpoint = getattr(record, 'endpoint', 'N/A')
        phase = getattr(record, 'phase', 'N/A')
        elapsed_ms = getattr(record, 'elapsed_ms', 0)
        progress = getattr(record, 'progress', {})
        # ... format according to spec
        return f"[{endpoint} | {phase}] elapsed={elapsed_ms}ms | progress={progress['done']}/{progress['total']}({progress['pct']}%) | ..."
```

**Alternatives Considered**:
- **structlog**: Feature-rich but overkill for fixed format
- **python-json-logger**: JSON format not required (spec defines key=value format)

---

## Best Practices

### Async/Await Patterns

1. **Connection Pooling**: Always use connection pools, never single connections
2. **Concurrency Control**: Use `asyncio.Semaphore` to limit concurrent operations
3. **Error Handling**: Wrap async operations in try/except to prevent task cancellation
4. **Timeouts**: Always set timeouts for external API calls and DB queries

### Database Access Patterns

1. **Transactions**: Use `async with conn.transaction()` for multi-statement operations
2. **Parameterized Queries**: Always use `$1, $2` parameters (never string interpolation)
3. **Batch Inserts**: Use `COPY` or `INSERT ... VALUES ($1), ($2), ...` for bulk data
4. **JSONB Handling**: Use `jsonb_set()` for partial updates within jsonb fields

### Testing Patterns

1. **Test Database**: Use separate test database, reset schema before each test suite
2. **Mocking External APIs**: Use `respx` library to mock httpx requests in tests
3. **Async Test Fixtures**: Use `@pytest.fixture(scope="function")` for async fixtures
4. **Coverage**: Run `pytest --cov=src --cov-report=html` to generate coverage reports

---

## Open Questions (None)

All technical decisions have been made. No NEEDS CLARIFICATION items remain from Technical Context.
