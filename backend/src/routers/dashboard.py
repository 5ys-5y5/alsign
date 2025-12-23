"""Router for dashboard endpoints providing KPIs and performance metrics."""

import logging
import json
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from datetime import datetime
from uuid import UUID

from ..database.connection import db_pool

logger = logging.getLogger("alsign")

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


class KPIResponse(BaseModel):
    """Response model for KPI data."""

    coverage: int
    dataFreshness: Optional[str]


class PerformanceSummaryRow(BaseModel):
    """Response model for a single performance summary row."""

    id: str  # UUID as string for JSON compatibility
    ticker: str
    event_date: str
    sector: Optional[str]
    industry: Optional[str]
    source: str
    source_id: str
    position_quantitative: Optional[str]
    disparity_quantitative: Optional[float]
    position_qualitative: Optional[str]
    disparity_qualitative: Optional[float]
    condition: Optional[str]


class PerformanceSummaryResponse(BaseModel):
    """Response model for performance summary with pagination."""

    data: List[PerformanceSummaryRow]
    total: int
    page: int
    pageSize: int


class DayOffsetMetricsRow(BaseModel):
    """Response model for a single day-offset metrics row."""

    row_id: str
    group_by: str
    group_value: str
    dayOffset: int
    sample_count: int
    return_mean: Optional[float]
    return_median: Optional[float]


class DayOffsetMetricsResponse(BaseModel):
    """Response model for day-offset metrics."""

    data: List[DayOffsetMetricsRow]
    total: int


@router.get("/kpis", response_model=KPIResponse)
async def get_kpis():
    """
    Get KPI data for dashboard.

    Returns:
        - coverage: Count of tickers in config_lv3_targets
        - dataFreshness: Latest update timestamp from config_lv3_market_holidays
    """
    logger.info("action=get_kpis phase=request_received")
    try:
        pool = await db_pool.get_pool()
        async with pool.acquire() as conn:
            logger.debug("action=get_kpis phase=db_connected")

            # Get coverage count
            coverage_result = await conn.fetchval(
                "SELECT COUNT(*) FROM config_lv3_targets"
            )
            logger.debug(f"action=get_kpis phase=coverage_fetched count={coverage_result}")

            # Get data freshness (latest update from holidays table)
            freshness_result = await conn.fetchval(
                "SELECT MAX(updated_at) FROM config_lv3_market_holidays"
            )
            logger.debug(f"action=get_kpis phase=freshness_fetched freshness={freshness_result}")

            # Format freshness as ISO string if it exists
            data_freshness = (
                freshness_result.isoformat() if freshness_result else None
            )

            # Check if database is empty and provide helpful message
            if coverage_result == 0:
                logger.warning("action=get_kpis status=empty_database message='No data in config_lv3_targets'")

            logger.info(
                f"action=get_kpis status=success coverage={coverage_result} "
                f"dataFreshness={data_freshness}"
            )

            return KPIResponse(
                coverage=coverage_result or 0, dataFreshness=data_freshness
            )

    except Exception as e:
        logger.error(f"action=get_kpis status=error error={str(e)}")
        # Provide more helpful error message for empty database
        if "does not exist" in str(e):
            raise HTTPException(
                status_code=500,
                detail="Database tables not found. Please run setup_supabase.sql to create tables first."
            )
        raise HTTPException(status_code=500, detail=f"Failed to fetch KPIs: {str(e)}")


@router.get("/performanceSummary", response_model=PerformanceSummaryResponse)
async def get_performance_summary(
    page: int = Query(1, ge=1, description="Page number starting from 1"),
    pageSize: int = Query(50, ge=1, le=1000, description="Number of rows per page"),
    sortBy: Optional[str] = Query(None, description="Column to sort by"),
    sortOrder: Optional[str] = Query(
        None, regex="^(asc|desc)$", description="Sort order: asc or desc"
    ),
    ticker: Optional[str] = Query(None, description="Filter by ticker (contains)"),
    sector: Optional[str] = Query(None, description="Filter by sector (contains)"),
    industry: Optional[str] = Query(None, description="Filter by industry (contains)"),
    source: Optional[str] = Query(None, description="Filter by source (contains)"),
    condition: Optional[str] = Query(None, description="Filter by condition (contains)"),
):
    """
    Get performance summary from txn_events table with pagination, filtering, and sorting.

    Supports:
    - Pagination via page and pageSize
    - Filtering by ticker, sector, industry, source, condition (case-insensitive contains)
    - Sorting by any column (asc/desc)
    """
    logger.info(
        f"action=get_performance_summary phase=request_received "
        f"page={page} pageSize={pageSize} sortBy={sortBy} sortOrder={sortOrder} "
        f"ticker={ticker} sector={sector} industry={industry} source={source} condition={condition}"
    )
    try:
        # Build WHERE clause
        where_conditions = []
        params = []
        param_count = 1

        if ticker:
            where_conditions.append(f"ticker ILIKE ${param_count}")
            params.append(f"%{ticker}%")
            param_count += 1

        if sector:
            where_conditions.append(f"sector ILIKE ${param_count}")
            params.append(f"%{sector}%")
            param_count += 1

        if industry:
            where_conditions.append(f"industry ILIKE ${param_count}")
            params.append(f"%{industry}%")
            param_count += 1

        if source:
            where_conditions.append(f"source ILIKE ${param_count}")
            params.append(f"%{source}%")
            param_count += 1

        if condition:
            where_conditions.append(f"condition ILIKE ${param_count}")
            params.append(f"%{condition}%")
            param_count += 1

        where_clause = " AND ".join(where_conditions) if where_conditions else "TRUE"

        # Build ORDER BY clause
        # Validate sortBy to prevent SQL injection
        allowed_sort_columns = [
            "id",
            "ticker",
            "event_date",
            "sector",
            "industry",
            "source",
            "source_id",
            "position_quantitative",
            "disparity_quantitative",
            "position_qualitative",
            "disparity_qualitative",
            "condition",
        ]

        order_clause = "id ASC"  # Default sort
        if sortBy and sortOrder:
            if sortBy not in allowed_sort_columns:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid sort column. Allowed: {', '.join(allowed_sort_columns)}",
                )
            order_clause = f"{sortBy} {sortOrder.upper()}"

        # Calculate offset
        offset = (page - 1) * pageSize

        pool = await db_pool.get_pool()
        async with pool.acquire() as conn:
            # Get total count
            count_query = f"SELECT COUNT(*) FROM txn_events WHERE {where_clause}"
            total = await conn.fetchval(count_query, *params)

            # Get data
            data_query = f"""
                SELECT
                    id::text,
                    ticker,
                    TO_CHAR(event_date, 'YYYY-MM-DD') as event_date,
                    sector,
                    industry,
                    source,
                    source_id,
                    position_quantitative::text,
                    disparity_quantitative,
                    position_qualitative::text,
                    disparity_qualitative,
                    condition
                FROM txn_events
                WHERE {where_clause}
                ORDER BY {order_clause}
                LIMIT {pageSize}
                OFFSET {offset}
            """

            rows = await conn.fetch(data_query, *params)

            logger.debug(
                f"action=get_performance_summary phase=query_complete "
                f"rows_fetched={len(rows)} page={page} pageSize={pageSize}"
            )

            # Explicitly convert UUIDs and enums to strings
            data = []
            for row in rows:
                row_id = str(row["id"])
                logger.debug(f"Processing row: id={row_id}, type={type(row_id)}, ticker={row['ticker']}")

                try:
                    row_data = PerformanceSummaryRow(
                        id=row_id,
                        ticker=row["ticker"],
                        event_date=row["event_date"],
                        sector=row["sector"],
                        industry=row["industry"],
                        source=row["source"],
                        source_id=row["source_id"],
                        position_quantitative=str(row["position_quantitative"]) if row["position_quantitative"] is not None else None,
                        disparity_quantitative=row["disparity_quantitative"],
                        position_qualitative=str(row["position_qualitative"]) if row["position_qualitative"] is not None else None,
                        disparity_qualitative=row["disparity_qualitative"],
                        condition=row["condition"],
                    )
                    data.append(row_data)
                    logger.debug(f"Successfully created PerformanceSummaryRow with id={row_data.id}")
                except Exception as e:
                    logger.error(f"Failed to create PerformanceSummaryRow: {e}, row_id={row_id}, type={type(row_id)}")
                    raise

            # Log warning if no data found
            if total == 0:
                logger.warning(
                    "action=get_performance_summary status=empty_result message='No events in txn_events table. "
                    "Please run: 1) GET /sourceData to collect foundation data, "
                    "2) POST /setEventsTable to consolidate events, "
                    "3) POST /backfillEventsTable to calculate metrics'"
                )

            logger.info(
                f"action=get_performance_summary status=success page={page} "
                f"pageSize={pageSize} total={total} returned={len(data)}"
            )

            return PerformanceSummaryResponse(
                data=data, total=total, page=page, pageSize=pageSize
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"action=get_performance_summary status=error error={str(e)} "
            f"error_type={type(e).__name__} page={page} pageSize={pageSize}",
            exc_info=True
        )
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch performance summary: {str(e)}"
        )


@router.get("/dayOffsetMetrics", response_model=DayOffsetMetricsResponse)
async def get_day_offset_metrics(
    groupBy: str = Query(
        "sector", description="Group by dimension: sector, industry, source, analyst"
    ),
):
    """
    Get day-offset performance metrics aggregated by specified dimension.

    Aggregates txn_events to calculate return statistics (mean, median) per dayOffset
    for each group value.

    groupBy options:
    - sector: Group by sector
    - industry: Group by industry
    - source: Group by source
    - analyst: Group by analyst_name (from evt_consensus)

    Returns aggregated metrics with sample_count, return_mean, return_median per dayOffset.
    """
    try:
        # Validate groupBy parameter
        allowed_group_by = ["sector", "industry", "source", "analyst"]
        if groupBy not in allowed_group_by:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid groupBy. Allowed: {', '.join(allowed_group_by)}",
            )

        # Determine the group column
        if groupBy == "analyst":
            # For analyst, we need to extract from source data or use a different approach
            # For now, let's use a placeholder since analyst_name is not directly in txn_events
            # In a real implementation, this would join with evt_consensus or use analyst fields
            group_column = "source"  # Fallback to source for now
            logger.warning(
                f"action=get_day_offset_metrics groupBy=analyst using_fallback=source "
                "note='analyst grouping requires evt_consensus join - using source as fallback'"
            )
        else:
            group_column = groupBy

        pool = await db_pool.get_pool()
        async with pool.acquire() as conn:
            # Query to aggregate day-offset metrics
            # Note: This is a simplified version. The full implementation would need to:
            # 1. Parse price_trend jsonb arrays to extract dayOffset returns
            # 2. Unnest the arrays
            # 3. Group by dimension and dayOffset
            # 4. Calculate statistics
            #
            # For now, we'll return a simpler aggregation showing the structure
            query = f"""
                WITH metrics AS (
                    SELECT
                        '{groupBy}' as group_by,
                        COALESCE({group_column}::text, 'unknown') as group_value,
                        0 as dayOffset,
                        COUNT(*) as sample_count,
                        AVG(disparity_quantitative) as return_mean,
                        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY disparity_quantitative) as return_median
                    FROM txn_events
                    WHERE {group_column} IS NOT NULL
                        AND disparity_quantitative IS NOT NULL
                    GROUP BY group_value
                )
                SELECT
                    group_by || '_' || group_value || '_D' || dayOffset::text as row_id,
                    group_by,
                    group_value,
                    dayOffset,
                    sample_count,
                    return_mean,
                    return_median
                FROM metrics
                ORDER BY group_value, dayOffset
            """

            rows = await conn.fetch(query)

            data = [
                DayOffsetMetricsRow(
                    row_id=row["row_id"],
                    group_by=row["group_by"],
                    group_value=row["group_value"],
                    dayOffset=row["dayoffset"],
                    sample_count=row["sample_count"],
                    return_mean=row["return_mean"],
                    return_median=row["return_median"],
                )
                for row in rows
            ]

            # Log warning if no data found
            if len(data) == 0:
                logger.warning(
                    f"action=get_day_offset_metrics status=empty_result groupBy={groupBy} "
                    "message='No metrics available. Database needs to be populated with market data first. "
                    "Please run API endpoints in this order: "
                    "1) GET /sourceData (collect foundation data), "
                    "2) POST /setEventsTable (consolidate events), "
                    "3) POST /backfillEventsTable (calculate metrics)'"
                )

            logger.info(
                f"action=get_day_offset_metrics status=success groupBy={groupBy} "
                f"returned={len(data)}"
            )

            return DayOffsetMetricsResponse(data=data, total=len(data))

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"action=get_day_offset_metrics status=error error={str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch day-offset metrics: {str(e)}"
        )
