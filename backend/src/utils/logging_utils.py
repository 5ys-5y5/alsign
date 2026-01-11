"""
Logging utilities for consistent log formatting across the application.

Usage:
    from src.utils.logging_utils import log_row_update, log_error

    log_row_update(logger, "txn_events", event_id, "Calculating metrics")
    log_error(logger, "Failed to fetch API data", exception=e)
"""
import logging
from typing import Optional, Any


def format_row_id(table: str, row_id: Any) -> str:
    """
    Format table and row ID for logging.

    Args:
        table: Table name (e.g., "txn_events", "evt_consensus")
        row_id: Row identifier (UUID, int, or composite key)

    Returns:
        Formatted string like "[txn_events:cb5d488a]" or "[evt_consensus:12345]"
    """
    if isinstance(row_id, str):
        # For UUIDs, show first 8 chars
        short_id = row_id[:8] if len(row_id) > 8 else row_id
    else:
        short_id = str(row_id)

    return f"[{table}:{short_id}]"


def format_event_id(ticker: str, event_date: Any, source: str = None) -> str:
    """
    Format event identifier for logging.

    Args:
        ticker: Stock ticker symbol
        event_date: Event date (datetime or string)
        source: Optional source table

    Returns:
        Formatted string like "[RGTI@2025-12-17]" or "[RGTI@2025-12-17/consensus]"
    """
    date_str = str(event_date)[:10] if event_date else "unknown"
    if source:
        return f"[{ticker}@{date_str}/{source}]"
    return f"[{ticker}@{date_str}]"


def log_row_update(logger: logging.Logger, table: str, row_id: Any, message: str, level: str = "info"):
    """
    Log a row update with consistent formatting.

    Args:
        logger: Logger instance
        table: Table name
        row_id: Row identifier
        message: Log message
        level: Log level (info, debug, warning, error)
    """
    prefix = format_row_id(table, row_id)
    log_func = getattr(logger, level.lower())
    log_func(f"{prefix} {message}")


def log_event_update(logger: logging.Logger, ticker: str, event_date: Any, source: str, message: str, level: str = "info"):
    """
    Log an event update with consistent formatting.

    Args:
        logger: Logger instance
        ticker: Stock ticker
        event_date: Event date
        source: Source table
        message: Log message
        level: Log level
    """
    prefix = format_event_id(ticker, event_date, source)
    log_func = getattr(logger, level.lower())
    log_func(f"{prefix} {message}")


def log_error(logger: logging.Logger, message: str, exception: Optional[Exception] = None, **kwargs):
    """
    Log an error with [ERR] prefix for easy searching.

    Args:
        logger: Logger instance
        message: Error message
        exception: Optional exception object
        **kwargs: Additional context (ticker, row_id, etc.)
    """
    # Build context string
    context_parts = []
    if 'ticker' in kwargs:
        context_parts.append(f"ticker={kwargs['ticker']}")
    if 'row_id' in kwargs:
        context_parts.append(f"row_id={kwargs['row_id']}")
    if 'table' in kwargs:
        context_parts.append(f"table={kwargs['table']}")

    context = f" ({', '.join(context_parts)})" if context_parts else ""

    if exception:
        logger.error(f"[ERR] {message}{context}: {type(exception).__name__}: {str(exception)}")
    else:
        logger.error(f"[ERR] {message}{context}")


def log_warning(logger: logging.Logger, message: str, **kwargs):
    """
    Log a warning with [WARN] prefix.

    Args:
        logger: Logger instance
        message: Warning message
        **kwargs: Additional context
    """
    context_parts = []
    if 'ticker' in kwargs:
        context_parts.append(f"ticker={kwargs['ticker']}")
    if 'row_id' in kwargs:
        context_parts.append(f"row_id={kwargs['row_id']}")

    context = f" ({', '.join(context_parts)})" if context_parts else ""
    logger.warning(f"[WARN] {message}{context}")


def log_db_update(logger: logging.Logger, table: str, updated_count: int, total_count: int = None):
    """
    Log database batch update results.

    Args:
        logger: Logger instance
        table: Table name
        updated_count: Number of rows updated
        total_count: Total rows attempted (optional)
    """
    if total_count:
        logger.info(f"[DB UPDATE] {table}: Updated {updated_count}/{total_count} rows")
    else:
        logger.info(f"[DB UPDATE] {table}: Updated {updated_count} rows")


def log_batch_start(logger: logging.Logger, ticker: str, event_count: int):
    """
    Log the start of a ticker batch processing.

    Args:
        logger: Logger instance
        ticker: Stock ticker
        event_count: Number of events to process
    """
    # Reduced to debug level to minimize console output
    logger.debug(f"[BATCH] {ticker} - Processing {event_count} events")


def log_batch_complete(logger: logging.Logger, ticker: str, event_count: int, success_count: int, fail_count: int):
    """
    Log the completion of a ticker batch processing.

    Args:
        logger: Logger instance
        ticker: Stock ticker
        event_count: Total events processed
        success_count: Successful events
        fail_count: Failed events
    """
    # Reduced to debug level to minimize console output
    logger.debug(f"[BATCH] {ticker} - Done: {success_count}/{event_count} success, {fail_count} failed")
