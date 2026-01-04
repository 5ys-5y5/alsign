# Logging Improvements

## Overview
Enhanced logging across all endpoints for better debugging and monitoring.

## Key Changes

### 1. Row-Level Logging with Table and ID Prefix
All logs related to specific row updates now include `[table:row_id]` prefix:

**Before:**
```
INFO: Updated 5 txn_events rows
INFO:   - ID=cb5d488a-68d5-4795-954b-409c2b627714, ticker=RGTI, ...
```

**After:**
```
[DB UPDATE] txn_events: Updated 5 rows
[txn_events:cb5d488a] ticker=RGTI, date=2025-12-17, source=consensus
```

### 2. Error Logs with [ERR] Prefix
All error logs now have `[ERR]` prefix for easy Ctrl+F searching:

**Before:**
```
ERROR: [Ticker Batch] RGTI: DB batch update failed: connection timeout
ERROR: Failed to fetch API data: HTTPError 500
```

**After:**
```
[ERR] DB batch update failed for RGTI (ticker=RGTI): ConnectionTimeout: connection timeout
[ERR] API call failed: fmp-income-statement: HTTPError: 500 Internal Server Error
```

### 3. Batch Processing Logs
Improved batch processing start/complete logs:

**Before:**
```
**********************************************************************************
[START TICKER] RGTI | 30 events to process
**********************************************************************************
```

**After:**
```
**********************************************************************************
[BATCH START] RGTI | 30 events to process
**********************************************************************************
```

## New Logging Utilities

### Location
`backend/src/utils/logging_utils.py`

### Functions

#### `log_row_update(logger, table, row_id, message, level="info")`
Log updates to specific database rows.

```python
log_row_update(logger, "txn_events", event_id, "Calculating metrics")
# Output: [txn_events:cb5d488a] Calculating metrics
```

#### `log_event_update(logger, ticker, event_date, source, message, level="info")`
Log updates to specific events.

```python
log_event_update(logger, "RGTI", "2025-12-17", "consensus", "Processing event")
# Output: [RGTI@2025-12-17/consensus] Processing event
```

#### `log_error(logger, message, exception=None, **kwargs)`
Log errors with [ERR] prefix and context.

```python
log_error(logger, "Failed to process event", exception=e, ticker="RGTI", row_id=event_id)
# Output: [ERR] Failed to process event (ticker=RGTI, row_id=cb5d488a): ValueError: Invalid data
```

#### `log_warning(logger, message, **kwargs)`
Log warnings with [WARN] prefix.

```python
log_warning(logger, "API rate limit approaching", ticker="RGTI")
# Output: [WARN] API rate limit approaching (ticker=RGTI)
```

#### `log_db_update(logger, table, updated_count, total_count=None)`
Log database batch update results.

```python
log_db_update(logger, "txn_events", 25, 30)
# Output: [DB UPDATE] txn_events: Updated 25/30 rows
```

#### `log_batch_start(logger, ticker, event_count)`
Log batch processing start.

```python
log_batch_start(logger, "RGTI", 30)
# Output:
# **********************************************************************************
# [BATCH START] RGTI | 30 events to process
# **********************************************************************************
```

#### `log_batch_complete(logger, ticker, event_count, success_count, fail_count)`
Log batch processing completion.

```python
log_batch_complete(logger, "RGTI", 30, 28, 2)
# Output:
# **********************************************************************************
# [BATCH COMPLETE] RGTI | Processed: 30, Success: 28, Failed: 2
# **********************************************************************************
```

## Modified Files

### Core Services
1. **`src/services/valuation_service.py`**
   - Added logging utilities import
   - Replaced manual logs with utility functions
   - All errors now have [ERR] prefix
   - Batch logs use consistent format

2. **`src/database/queries/metrics.py`**
   - Added logging utilities import
   - DB update logs show [DB UPDATE] prefix
   - Row-level logs show [txn_events:id] prefix

3. **`src/services/external_api.py`**
   - Added logging utilities import
   - API errors now have [ERR] prefix
   - Consistent error formatting

## Usage Examples

### Search for Errors
```bash
# Find all errors in logs
grep "\[ERR\]" backend.log

# Find errors for specific ticker
grep "\[ERR\]" backend.log | grep "RGTI"

# Find errors by error type
grep "\[ERR\]" backend.log | grep "ConnectionTimeout"
```

### Search for Specific Row Updates
```bash
# Find all logs for specific event
grep "\[txn_events:cb5d488a\]" backend.log

# Find all logs for specific ticker and date
grep "\[RGTI@2025-12-17\]" backend.log
```

### Monitor Batch Processing
```bash
# Watch batch processing in real-time
tail -f backend.log | grep "BATCH"

# Count successful vs failed batches
grep "\[BATCH COMPLETE\]" backend.log | grep -c "Failed: 0"
```

## Benefits

1. **Easy Error Tracking**: Use Ctrl+F to search for `[ERR]` in logs
2. **Row-Level Debugging**: Quickly find all logs related to specific row
3. **Event Tracking**: Follow processing flow for specific ticker/date
4. **Performance Monitoring**: Track batch success/fail rates
5. **Consistent Format**: All logs follow same structure

## Migration Guide

### For New Code
Use logging utilities instead of direct logger calls:

```python
# ✗ Old way
logger.error(f"Failed to process {ticker}: {e}")

# ✓ New way
log_error(logger, f"Failed to process ticker", exception=e, ticker=ticker)
```

### For Existing Code
Gradually migrate logs to new format:
1. Start with error logs (highest priority)
2. Migrate row update logs
3. Standardize batch processing logs
4. Update remaining info/debug logs

## Testing

Test the new logging:

```bash
cd backend

# Start server
uvicorn src.main:app --reload

# Run backfill
curl -X POST "http://localhost:8000/backfillEventsTable?tickers=RGTI&overwrite=true"

# Check logs for new format
grep "\[ERR\]" logs/backend.log
grep "\[DB UPDATE\]" logs/backend.log
grep "\[txn_events:" logs/backend.log
```

## Future Enhancements

1. **Structured Logging**: Add JSON log format option
2. **Log Aggregation**: Send logs to centralized system (ELK, Datadog)
3. **Alert Rules**: Trigger alerts on `[ERR]` frequency
4. **Performance Tracking**: Add `[PERF]` prefix for performance logs
5. **Audit Trail**: Add `[AUDIT]` prefix for data modification logs
