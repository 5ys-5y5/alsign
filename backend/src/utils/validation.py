"""Input validation utilities."""

import re
from typing import List, Optional
from datetime import datetime
from fastapi import HTTPException


def validate_date_string(date_str: str, field_name: str = "date") -> datetime:
    """
    Validate and parse a date string in YYYY-MM-DD format.

    Args:
        date_str: Date string to validate
        field_name: Field name for error messages

    Returns:
        Parsed datetime object

    Raises:
        HTTPException: If date format is invalid
    """
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {field_name} format. Expected YYYY-MM-DD, got: {date_str}",
        )


def validate_date_range(
    from_date: str, to_date: str, allow_future: bool = True
) -> tuple[datetime, datetime]:
    """
    Validate a date range.

    Args:
        from_date: Start date string (YYYY-MM-DD)
        to_date: End date string (YYYY-MM-DD)
        allow_future: Whether to allow future dates

    Returns:
        Tuple of (from_datetime, to_datetime)

    Raises:
        HTTPException: If date range is invalid
    """
    from_dt = validate_date_string(from_date, "from")
    to_dt = validate_date_string(to_date, "to")

    if from_dt > to_dt:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid date range: 'from' ({from_date}) must be before or equal to 'to' ({to_date})",
        )

    if not allow_future:
        now = datetime.now()
        if to_dt > now:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid date range: 'to' date ({to_date}) cannot be in the future",
            )

    return from_dt, to_dt


def validate_ticker(ticker: str) -> str:
    """
    Validate ticker symbol format.

    Args:
        ticker: Ticker symbol to validate

    Returns:
        Uppercase ticker symbol

    Raises:
        HTTPException: If ticker format is invalid
    """
    if not ticker:
        raise HTTPException(status_code=400, detail="Ticker cannot be empty")

    # Allow alphanumeric and common ticker characters (-, ., ^)
    if not re.match(r'^[A-Z0-9.\-^]{1,10}$', ticker.upper()):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid ticker format: {ticker}. Must be 1-10 alphanumeric characters, can include -, ., ^",
        )

    return ticker.upper()


def validate_allowed_values(
    value: str, allowed_values: List[str], field_name: str = "value"
) -> str:
    """
    Validate that a value is in the allowed list.

    Args:
        value: Value to validate
        allowed_values: List of allowed values
        field_name: Field name for error messages

    Returns:
        The validated value

    Raises:
        HTTPException: If value is not in allowed list
    """
    if value not in allowed_values:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {field_name}: '{value}'. Allowed values: {', '.join(allowed_values)}",
        )
    return value


def validate_positive_integer(
    value: Optional[int], field_name: str = "value", allow_zero: bool = False
) -> Optional[int]:
    """
    Validate that a value is a positive integer.

    Args:
        value: Value to validate
        field_name: Field name for error messages
        allow_zero: Whether to allow zero as valid

    Returns:
        The validated value

    Raises:
        HTTPException: If value is not a positive integer
    """
    if value is None:
        return None

    min_value = 0 if allow_zero else 1
    if value < min_value:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {field_name}: {value}. Must be >= {min_value}",
        )

    return value


def validate_column_name(column: str, allowed_columns: List[str]) -> str:
    """
    Validate SQL column name against whitelist to prevent SQL injection.

    Args:
        column: Column name to validate
        allowed_columns: List of allowed column names

    Returns:
        The validated column name

    Raises:
        HTTPException: If column name is not in allowed list
    """
    if column not in allowed_columns:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid column name: '{column}'. Allowed columns: {', '.join(allowed_columns)}",
        )
    return column


def validate_table_name(table: str) -> str:
    """
    Validate table name format to prevent SQL injection.

    Args:
        table: Table name to validate

    Returns:
        The validated table name

    Raises:
        HTTPException: If table name format is invalid
    """
    # Allow only alphanumeric, underscore, and period (for schema.table)
    if not re.match(r'^[a-zA-Z0-9_.]+$', table):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid table name format: {table}. Only alphanumeric, underscore, and period allowed",
        )

    # Prevent SQL keywords
    sql_keywords = ['select', 'drop', 'delete', 'insert', 'update', 'create', 'alter', 'truncate']
    if table.lower() in sql_keywords:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid table name: {table}. Cannot use SQL keywords",
        )

    return table


def validate_pagination(
    page: int = 1, page_size: int = 50, max_page_size: int = 1000
) -> tuple[int, int]:
    """
    Validate pagination parameters.

    Args:
        page: Page number (1-indexed)
        page_size: Number of items per page
        max_page_size: Maximum allowed page size

    Returns:
        Tuple of (page, page_size)

    Raises:
        HTTPException: If pagination parameters are invalid
    """
    if page < 1:
        raise HTTPException(
            status_code=400, detail=f"Invalid page: {page}. Must be >= 1"
        )

    if page_size < 1:
        raise HTTPException(
            status_code=400, detail=f"Invalid page_size: {page_size}. Must be >= 1"
        )

    if page_size > max_page_size:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid page_size: {page_size}. Must be <= {max_page_size}",
        )

    return page, page_size
