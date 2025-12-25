"""Datetime utilities for UTC parsing, timezone enforcement, and trading day calculations."""

from datetime import datetime, date, timedelta, timezone
from dateutil import parser
from typing import List, Tuple
import asyncpg


def parse_to_utc(date_string: str) -> datetime:
    """
    Parse date string to UTC datetime.

    Supports ISO8601 and various formats. Always returns timezone-aware UTC datetime.
    Raises ValueError if parsing fails.

    Args:
        date_string: Date string in ISO8601 or other common formats

    Returns:
        Timezone-aware datetime in UTC

    Raises:
        ValueError: If date string cannot be parsed
    """
    try:
        # Try strict ISO8601 first
        dt = datetime.fromisoformat(date_string.replace('Z', '+00:00'))
    except ValueError:
        # Fall back to flexible parsing
        dt = parser.parse(date_string)

    # Ensure timezone-aware
    if dt.tzinfo is None:
        # Treat naive datetime as UTC
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        # Convert to UTC
        dt = dt.astimezone(timezone.utc)

    return dt


def parse_date_only_to_utc(date_string: str) -> datetime:
    """
    Parse YYYY-MM-DD date string to UTC datetime at midnight.

    Args:
        date_string: Date string in YYYY-MM-DD format

    Returns:
        Timezone-aware datetime at 00:00:00 UTC

    Raises:
        ValueError: If date string is invalid
    """
    try:
        dt = datetime.fromisoformat(date_string)
    except ValueError:
        raise ValueError(f"Invalid date format: {date_string}. Expected YYYY-MM-DD")

    # Set time to midnight UTC
    return datetime(dt.year, dt.month, dt.day, 0, 0, 0, tzinfo=timezone.utc)


def to_utc_iso8601(dt: datetime) -> str:
    """
    Convert datetime to UTC ISO8601 string with +00:00 timezone suffix.

    Args:
        dt: Datetime object (timezone-aware or naive)

    Returns:
        ISO8601 string with +00:00 suffix
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)

    return dt.isoformat().replace('+00:00', '+00:00')


async def is_trading_day(target_date: date, exchange: str, pool: asyncpg.Pool) -> bool:
    """
    Check if given date is a trading day for the exchange.

    A trading day is a day that is:
    - Not Saturday or Sunday
    - Not a fully closed market holiday

    Args:
        target_date: Date to check
        exchange: Exchange identifier (e.g., "NASDAQ", "NYSE")
        pool: Database connection pool

    Returns:
        True if trading day, False otherwise
    """
    # Check if weekend
    if target_date.weekday() >= 5:  # Saturday=5, Sunday=6
        return False

    # Check if market holiday
    result = await pool.fetchval(
        "SELECT is_fully_closed FROM config_lv3_market_holidays WHERE exchange=$1 AND date=$2",
        exchange,
        target_date
    )

    # If no record, assume trading day; if record exists and is_fully_closed=True, not trading day
    return result is not True


async def next_trading_day(start_date: date, exchange: str, pool: asyncpg.Pool) -> date:
    """
    Find next trading day on or after given date.

    Args:
        start_date: Starting date
        exchange: Exchange identifier
        pool: Database connection pool

    Returns:
        Next trading day (could be start_date if it's a trading day)
    """
    current = start_date
    max_iterations = 30  # Prevent infinite loop (max ~4 weeks)

    for _ in range(max_iterations):
        if await is_trading_day(current, exchange, pool):
            return current
        current += timedelta(days=1)

    raise RuntimeError(f"Could not find trading day within 30 days of {start_date}")


async def previous_trading_day(start_date: date, exchange: str, pool: asyncpg.Pool) -> date:
    """
    Find previous trading day on or before given date.

    Args:
        start_date: Starting date
        exchange: Exchange identifier
        pool: Database connection pool

    Returns:
        Previous trading day (could be start_date if it's a trading day)
    """
    current = start_date
    max_iterations = 30

    for _ in range(max_iterations):
        if await is_trading_day(current, exchange, pool):
            return current
        current -= timedelta(days=1)

    raise RuntimeError(f"Could not find trading day within 30 days before {start_date}")


async def get_trading_days_in_range(
    start_date: date,
    end_date: date,
    exchange: str,
    pool: asyncpg.Pool
) -> set:
    """
    Get all trading days within a date range (inclusive) as a set.
    
    This is optimized to fetch all holidays in one query for fast lookup.
    
    Args:
        start_date: Start of range
        end_date: End of range
        exchange: Exchange identifier
        pool: Database connection pool
    
    Returns:
        Set of trading days (date objects)
    """
    # Fetch all holidays in range in ONE query
    holidays = await pool.fetch(
        """
        SELECT date FROM config_lv3_market_holidays 
        WHERE exchange = $1 
          AND date >= $2 
          AND date <= $3 
          AND is_fully_closed = true
        """,
        exchange,
        start_date,
        end_date
    )
    holiday_set = {h['date'] for h in holidays}
    
    # Generate all trading days (weekdays that are not holidays)
    trading_days = set()
    current = start_date
    while current <= end_date:
        if current.weekday() < 5 and current not in holiday_set:  # weekday and not holiday
            trading_days.add(current)
        current += timedelta(days=1)
    
    return trading_days


def calculate_dayOffset_dates_cached(
    event_date: date,
    count_start: int,
    count_end: int,
    trading_days_set: set
) -> List[Tuple[int, date]]:
    """
    Generate (dayOffset, targetDate) pairs using pre-cached trading days.
    
    NO DB CALLS - uses pre-fetched trading_days_set for fast calculation.
    
    Args:
        event_date: Event date (may be non-trading day)
        count_start: Starting dayOffset (typically negative, e.g., -14)
        count_end: Ending dayOffset (typically positive, e.g., +14)
        trading_days_set: Pre-fetched set of trading days
    
    Returns:
        List of (dayOffset, targetDate) tuples sorted by dayOffset
    """
    # Convert set to sorted list for binary search-like operations
    trading_days_sorted = sorted(trading_days_set)
    
    # Find base_date (first trading day on or after event_date)
    base_date = None
    for td in trading_days_sorted:
        if td >= event_date:
            base_date = td
            break
    
    if base_date is None:
        # Fallback: use event_date itself
        base_date = event_date
    
    # Find index of base_date in sorted trading days
    try:
        base_idx = trading_days_sorted.index(base_date)
    except ValueError:
        # base_date not in trading days (shouldn't happen, but handle gracefully)
        return [(0, event_date)]
    
    results = []
    
    # Generate all offsets from count_start to count_end
    for offset in range(count_start, count_end + 1):
        target_idx = base_idx + offset
        if 0 <= target_idx < len(trading_days_sorted):
            results.append((offset, trading_days_sorted[target_idx]))
        # else: out of range, skip this offset
    
    return results


async def calculate_dayOffset_dates(
    event_date: date,
    count_start: int,
    count_end: int,
    exchange: str,
    pool: asyncpg.Pool
) -> List[Tuple[int, date]]:
    """
    Generate (dayOffset, targetDate) pairs for price trend.

    dayOffset=0 maps to the next trading day on or after event_date.
    Negative offsets go backward, positive offsets go forward, counting only trading days.

    Args:
        event_date: Event date (may be non-trading day)
        count_start: Starting dayOffset (typically negative, e.g., -14)
        count_end: Ending dayOffset (typically positive, e.g., +14)
        exchange: Exchange identifier
        pool: Database connection pool

    Returns:
        List of (dayOffset, targetDate) tuples sorted by dayOffset

    Example:
        If event_date=2025-12-15 (Monday), count_start=-2, count_end=2:
        Returns: [(-2, 2025-12-11), (-1, 2025-12-12), (0, 2025-12-15), (1, 2025-12-16), (2, 2025-12-17)]
    """
    # Map dayOffset=0 to next trading day
    base_date = await next_trading_day(event_date, exchange, pool)

    results = []

    # Generate negative offsets (backward from base_date)
    if count_start < 0:
        current = base_date
        for offset in range(0, count_start, -1):
            if offset < 0:
                current = await previous_trading_day(current - timedelta(days=1), exchange, pool)
            results.append((offset, current))

    # Add dayOffset=0
    results.append((0, base_date))

    # Generate positive offsets (forward from base_date)
    if count_end > 0:
        current = base_date
        for offset in range(1, count_end + 1):
            current = await next_trading_day(current + timedelta(days=1), exchange, pool)
            results.append((offset, current))

    # Sort by dayOffset
    results.sort(key=lambda x: x[0])

    return results
