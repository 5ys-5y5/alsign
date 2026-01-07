"""Data freshness checking utilities for quantitatives APIs."""

import calendar
import logging
from datetime import date, datetime, timedelta
from typing import Optional, Tuple
import asyncpg

from .datetime_utils import parse_to_utc, is_trading_day

logger = logging.getLogger("alsign")


def get_quarter_end_for_date(d: date) -> date:
    """Get the quarter end date for a given date."""
    quarter = (d.month - 1) // 3 + 1
    quarter_end_month = quarter * 3
    _, last_day = calendar.monthrange(d.year, quarter_end_month)
    return date(d.year, quarter_end_month, last_day)


def get_previous_quarter_end(quarters_back: int = 1) -> date:
    """
    Get the end date of a quarter N quarters before today.

    Args:
        quarters_back: Number of quarters to go back (1 = previous quarter)

    Returns:
        End date of that quarter
    """
    today = date.today()
    current_quarter = (today.month - 1) // 3 + 1

    # Calculate target quarter
    target_quarter = current_quarter - quarters_back
    target_year = today.year

    while target_quarter <= 0:
        target_quarter += 4
        target_year -= 1

    quarter_end_month = target_quarter * 3
    _, last_day = calendar.monthrange(target_year, quarter_end_month)
    return date(target_year, quarter_end_month, last_day)


def is_quarterly_data_fresh(max_date_str: Optional[str]) -> bool:
    """
    Check if quarterly data is fresh (within last 2 quarters).

    Since quarterly financial statements are published 45-60 days after quarter end,
    we consider data fresh if it's from 2 quarters ago or later.

    Example (current date: 2026-01-07):
    - Current quarter: Q1 2026
    - 2 quarters ago: Q3 2025 (ends 2025-09-30)
    - If maxDate is in Q3 2025 or later → fresh
    - If maxDate is in Q2 2025 or earlier → stale

    Args:
        max_date_str: ISO format date string from status.maxDate

    Returns:
        True if data is within last 2 quarters, False otherwise
    """
    if not max_date_str:
        return False

    try:
        max_date = parse_to_utc(max_date_str).date()

        # Get the quarter end of the max_date
        max_date_quarter_end = get_quarter_end_for_date(max_date)

        # Get quarter end from 2 quarters ago
        two_quarters_ago_end = get_previous_quarter_end(2)

        # Data is fresh if the quarter of max_date is >= 2 quarters ago
        is_fresh = max_date_quarter_end >= two_quarters_ago_end

        logger.info(
            f"Quarterly freshness check: maxDate={max_date}, "
            f"maxDateQuarterEnd={max_date_quarter_end}, "
            f"twoQuartersAgoEnd={two_quarters_ago_end}, isFresh={is_fresh}"
        )

        return is_fresh
    except Exception as e:
        logger.warning(f"Failed to parse quarterly date: {e}")
        return False


async def is_daily_data_fresh(max_date_str: Optional[str], pool: asyncpg.Pool) -> bool:
    """
    Check if daily data is fresh (within last 2 trading days).

    Args:
        max_date_str: ISO format date string from status.maxDate
        pool: Database connection pool for trading day lookup

    Returns:
        True if data is within last 2 trading days, False otherwise
    """
    if not max_date_str:
        return False

    try:
        max_date = parse_to_utc(max_date_str).date()
        today = date.today()

        # Find last 2 trading days
        days_back = 0
        trading_days_found = 0

        while trading_days_found < 2 and days_back < 10:
            check_date = today - timedelta(days=days_back)

            if await is_trading_day(check_date, "NASDAQ", pool):
                if max_date >= check_date:
                    logger.debug(
                        f"Daily freshness check: maxDate={max_date} is within "
                        f"last 2 trading days (checked up to {check_date})"
                    )
                    return True
                trading_days_found += 1

            days_back += 1

        logger.debug(
            f"Daily freshness check: maxDate={max_date} is older than "
            f"last 2 trading days"
        )
        return False

    except Exception as e:
        logger.warning(f"Failed to check daily data freshness: {e}")
        return False


def get_api_period_type(api_id: str) -> str:
    """
    Determine the update frequency of an API.

    Returns:
        'daily' or 'quarterly'
    """
    QUARTERLY_APIS = {
        "fmp-income-statement",
        "fmp-balance-sheet-statement",
        "fmp-cash-flow-statement",
        "fmp-key-metrics",
        "fmp-ratios"
    }

    DAILY_APIS = {
        "fmp-historical-price-eod-full",
        "fmp-historical-market-capitalization",
        "fmp-quote"  # Quote is updated daily (end-of-day price)
    }

    if api_id in DAILY_APIS:
        return 'daily'
    elif api_id in QUARTERLY_APIS:
        return 'quarterly'
    else:
        logger.warning(f"Unknown API period type for {api_id}, defaulting to 'quarterly'")
        return 'quarterly'


async def should_fetch_api(
    api_id: str,
    existing_status: dict,
    has_data: bool,
    overwrite: bool,
    pool: asyncpg.Pool
) -> Tuple[bool, str]:
    """
    Determine if an API should be fetched based on freshness.

    Args:
        api_id: API identifier (e.g., "fmp-ratios")
        existing_status: Status JSONB object from database
        has_data: Whether data column has content
        overwrite: If True, always fetch regardless of freshness
        pool: Database connection pool

    Returns:
        Tuple of (should_fetch: bool, reason: str)
    """
    # Always fetch if overwrite=True
    if overwrite:
        return True, "overwrite=True"

    # Always fetch if no data exists
    if not has_data:
        return True, "no_data_exists"

    # Check status metadata
    status_entry = existing_status.get(api_id, {}) if existing_status else {}
    max_date = status_entry.get("maxDate") if isinstance(status_entry, dict) else None

    if not max_date:
        return True, "no_status_metadata"

    # Check freshness based on API type
    period_type = get_api_period_type(api_id)

    if period_type == 'quarterly':
        is_fresh = is_quarterly_data_fresh(max_date)
        if is_fresh:
            return False, f"quarterly_data_fresh (maxDate: {max_date[:10]})"
        else:
            return True, f"quarterly_data_stale (maxDate: {max_date[:10]})"

    elif period_type == 'daily':
        is_fresh = await is_daily_data_fresh(max_date, pool)
        if is_fresh:
            return False, f"daily_data_fresh (maxDate: {max_date[:10]})"
        else:
            return True, f"daily_data_stale (maxDate: {max_date[:10]})"

    else:
        # Unknown API type (should not happen due to get_api_period_type default)
        logger.warning(f"Unknown period type for {api_id}: {period_type}")
        return True, "unknown_period_type"
