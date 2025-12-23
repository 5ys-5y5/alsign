"""Router for condition group management endpoints."""

import uuid
import logging
from fastapi import APIRouter, HTTPException, Request, Query
from typing import List, Optional
from pydantic import BaseModel, Field, validator

from ..database.connection import db_pool

logger = logging.getLogger("alsign")

router = APIRouter(prefix="/conditionGroups", tags=["Condition Groups"])


class ConditionGroupCreate(BaseModel):
    """Request model for creating a condition group."""

    column: str = Field(description="Column name (source, sector, or industry)")
    value: str = Field(description="Column value to filter by")
    name: str = Field(description="Condition group name")
    confirm: bool = Field(default=False, description="Confirmation flag for bulk update")

    @validator('column')
    def validate_column(cls, v):
        """Validate column is one of allowed values."""
        allowed = ['source', 'sector', 'industry']
        if v not in allowed:
            raise ValueError(f"Column must be one of: {', '.join(allowed)}")
        return v

    @validator('name')
    def validate_name(cls, v):
        """Validate name is non-empty after trim."""
        trimmed = v.strip()
        if not trimmed:
            raise ValueError("Condition name cannot be empty")
        return trimmed


class ConditionGroup(BaseModel):
    """Response model for a condition group."""

    name: str
    column: str
    value: str
    rowCount: int


@router.get("/columns", response_model=List[str])
async def get_allowed_columns():
    """
    Get list of allowed columns for condition groups.

    Returns:
        List of column names that can be used for filtering
    """
    return ["source", "sector", "industry"]


@router.get("/values", response_model=List[str])
async def get_column_values(
    column: str = Query(..., description="Column name to get distinct values for")
):
    """
    Get distinct values for a specific column.

    Args:
        column: Column name (source, sector, or industry)

    Returns:
        List of distinct non-NULL values from the column

    Raises:
        HTTPException: 400 if column is not allowed
    """
    # Validate column
    allowed_columns = ['source', 'sector', 'industry']
    if column not in allowed_columns:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid column. Allowed: {', '.join(allowed_columns)}"
        )

    try:
        pool = await db_pool.get_pool()

        async with pool.acquire() as conn:
            # Use parameterized query to prevent SQL injection
            # Since column name can't be parameterized, we validate it above
            query = f"""
                SELECT DISTINCT {column}
                FROM txn_events
                WHERE {column} IS NOT NULL
                ORDER BY {column}
            """

            rows = await conn.fetch(query)
            values = [row[column] for row in rows]

            return values

    except Exception as e:
        logger.error(f"Failed to get column values: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=List[ConditionGroup])
async def get_condition_groups():
    """
    Get all existing condition groups.

    Returns:
        List of condition groups with their associated column/value combinations
    """
    try:
        pool = await db_pool.get_pool()

        async with pool.acquire() as conn:
            # Query to get distinct condition groups with their characteristics
            # We need to infer column/value by checking which column matches
            query = """
                WITH condition_stats AS (
                    SELECT
                        condition,
                        source,
                        sector,
                        industry,
                        COUNT(*) as row_count
                    FROM txn_events
                    WHERE condition IS NOT NULL
                    GROUP BY condition, source, sector, industry
                )
                SELECT
                    condition as name,
                    CASE
                        WHEN COUNT(DISTINCT source) = 1 AND MAX(source) IS NOT NULL THEN 'source'
                        WHEN COUNT(DISTINCT sector) = 1 AND MAX(sector) IS NOT NULL THEN 'sector'
                        WHEN COUNT(DISTINCT industry) = 1 AND MAX(industry) IS NOT NULL THEN 'industry'
                        ELSE 'mixed'
                    END as column,
                    CASE
                        WHEN COUNT(DISTINCT source) = 1 AND MAX(source) IS NOT NULL THEN MAX(source)
                        WHEN COUNT(DISTINCT sector) = 1 AND MAX(sector) IS NOT NULL THEN MAX(sector)
                        WHEN COUNT(DISTINCT industry) = 1 AND MAX(industry) IS NOT NULL THEN MAX(industry)
                        ELSE 'multiple'
                    END as value,
                    SUM(row_count)::int as row_count
                FROM condition_stats
                GROUP BY condition
                ORDER BY condition
            """

            rows = await conn.fetch(query)

            groups = [
                ConditionGroup(
                    name=row['name'],
                    column=row['column'],
                    value=row['value'],
                    rowCount=row['row_count']
                )
                for row in rows
            ]

            return groups

    except Exception as e:
        logger.error(f"Failed to get condition groups: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("", status_code=201)
async def create_condition_group(
    request: Request,
    body: ConditionGroupCreate
):
    """
    Create a new condition group by bulk updating txn_events.

    Args:
        body: Condition group creation parameters

    Returns:
        Summary with affected row count

    Raises:
        HTTPException: 400 if confirmation not provided or invalid parameters
    """
    req_id = request.state.reqId if hasattr(request.state, 'reqId') else str(uuid.uuid4())

    if not body.confirm:
        raise HTTPException(
            status_code=400,
            detail="Confirmation required. Set 'confirm' to true to proceed with bulk update."
        )

    try:
        pool = await db_pool.get_pool()

        async with pool.acquire() as conn:
            # First, get count of rows that will be affected
            count_query = f"""
                SELECT COUNT(*) as count
                FROM txn_events
                WHERE {body.column} = $1
            """

            count_result = await conn.fetchrow(count_query, body.value)
            affected_count = count_result['count']

            if affected_count == 0:
                raise HTTPException(
                    status_code=404,
                    detail=f"No rows found with {body.column}='{body.value}'"
                )

            # Perform the bulk update
            update_query = f"""
                UPDATE txn_events
                SET condition = $1
                WHERE {body.column} = $2
            """

            result = await conn.execute(update_query, body.name, body.value)

            logger.info(
                f"Created condition group '{body.name}'",
                extra={
                    'endpoint': 'POST /conditionGroups',
                    'phase': 'create',
                    'elapsed_ms': 0,
                    'counters': {'affected_rows': affected_count},
                    'progress': {},
                    'rate': {},
                    'batch': {},
                    'warn': []
                }
            )

            return {
                'reqId': req_id,
                'message': f"Condition group '{body.name}' created",
                'affectedRows': affected_count,
                'column': body.column,
                'value': body.value
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create condition group: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{name}", status_code=200)
async def delete_condition_group(
    request: Request,
    name: str
):
    """
    Delete a condition group by setting condition to NULL.

    Args:
        name: Condition group name to delete

    Returns:
        Summary with affected row count

    Raises:
        HTTPException: 404 if condition group not found
    """
    req_id = request.state.reqId if hasattr(request.state, 'reqId') else str(uuid.uuid4())

    try:
        pool = await db_pool.get_pool()

        async with pool.acquire() as conn:
            # Update rows to set condition to NULL
            result = await conn.execute(
                """
                UPDATE txn_events
                SET condition = NULL
                WHERE condition = $1
                """,
                name
            )

            # Parse affected row count from result
            affected_count = 0
            if "UPDATE" in result:
                parts = result.split()
                if len(parts) >= 2:
                    affected_count = int(parts[-1])

            if affected_count == 0:
                raise HTTPException(
                    status_code=404,
                    detail=f"Condition group '{name}' not found"
                )

            logger.info(
                f"Deleted condition group '{name}'",
                extra={
                    'endpoint': f'DELETE /conditionGroups/{name}',
                    'phase': 'delete',
                    'elapsed_ms': 0,
                    'counters': {'affected_rows': affected_count},
                    'progress': {},
                    'rate': {},
                    'batch': {},
                    'warn': []
                }
            )

            return {
                'reqId': req_id,
                'message': f"Condition group '{name}' deleted",
                'affectedRows': affected_count
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete condition group: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
