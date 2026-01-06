"""Router for dashboard endpoints providing KPIs and performance metrics."""

import logging
import json
from fastapi import APIRouter, HTTPException, Query, Body
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from datetime import datetime, date
from uuid import UUID

from ..database.connection import db_pool

logger = logging.getLogger("alsign")

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


class KPIResponse(BaseModel):
    """Response model for KPI data."""

    coverage: int
    dataFreshness: Optional[str]


class EventRow(BaseModel):
    """Response model for a single event row."""

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
    # WTS - which day offset (D+N) has the maximum return
    wts: Optional[int]
    # Day offset returns D-14 to D14 (excluding D0)
    d_neg14: Optional[float]
    d_neg13: Optional[float]
    d_neg12: Optional[float]
    d_neg11: Optional[float]
    d_neg10: Optional[float]
    d_neg9: Optional[float]
    d_neg8: Optional[float]
    d_neg7: Optional[float]
    d_neg6: Optional[float]
    d_neg5: Optional[float]
    d_neg4: Optional[float]
    d_neg3: Optional[float]
    d_neg2: Optional[float]
    d_neg1: Optional[float]
    d_pos1: Optional[float]
    d_pos2: Optional[float]
    d_pos3: Optional[float]
    d_pos4: Optional[float]
    d_pos5: Optional[float]
    d_pos6: Optional[float]
    d_pos7: Optional[float]
    d_pos8: Optional[float]
    d_pos9: Optional[float]
    d_pos10: Optional[float]
    d_pos11: Optional[float]
    d_pos12: Optional[float]
    d_pos13: Optional[float]
    d_pos14: Optional[float]


class EventsResponse(BaseModel):
    """Response model for events with pagination."""

    data: List[EventRow]
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


@router.get("/events", response_model=EventsResponse)
async def get_events(
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
    position_quantitative: Optional[str] = Query(None, description="Filter by position_quantitative (exact match)"),
    position_qualitative: Optional[str] = Query(None, description="Filter by position_qualitative (exact match)"),
    disparity_quantitative_min: Optional[float] = Query(None, description="Filter by disparity_quantitative >= value"),
    disparity_quantitative_max: Optional[float] = Query(None, description="Filter by disparity_quantitative <= value"),
    disparity_qualitative_min: Optional[float] = Query(None, description="Filter by disparity_qualitative >= value"),
    disparity_qualitative_max: Optional[float] = Query(None, description="Filter by disparity_qualitative <= value"),
    event_date_from: Optional[str] = Query(None, alias="eventDateFrom", description="Filter by event_date >= (YYYY-MM-DD)"),
    event_date_to: Optional[str] = Query(None, alias="eventDateTo", description="Filter by event_date <= (YYYY-MM-DD)"),
):
    """
    Get events from txn_events table with pagination, filtering, and sorting.

    Supports:
    - Pagination via page and pageSize
    - Filtering by ticker, sector, industry, source, condition (case-insensitive contains)
    - Date range filtering with eventDateFrom and eventDateTo
    - Sorting by any column (asc/desc)
    """
    logger.info(
        f"action=get_events phase=request_received "
        f"page={page} pageSize={pageSize} sortBy={sortBy} sortOrder={sortOrder} "
        f"ticker={ticker} sector={sector} industry={industry} source={source} condition={condition} "
        f"event_date_from={event_date_from} event_date_to={event_date_to}"
    )
    try:
        # Build WHERE clause
        where_conditions = []
        params = []
        param_count = 1

        if ticker:
            if ticker.startswith('='):
                # Exact match: =AAPL
                where_conditions.append(f"e.ticker = ${param_count}")
                params.append(ticker[1:])
            else:
                # Partial match: AAPL or dit (matches EDIT)
                where_conditions.append(f"e.ticker ILIKE ${param_count}")
                params.append(f"%{ticker}%")
            param_count += 1

        if sector:
            if sector.startswith('='):
                where_conditions.append(f"e.sector = ${param_count}")
                params.append(sector[1:])
            else:
                where_conditions.append(f"e.sector ILIKE ${param_count}")
                params.append(f"%{sector}%")
            param_count += 1

        if industry:
            if industry.startswith('='):
                where_conditions.append(f"e.industry = ${param_count}")
                params.append(industry[1:])
            else:
                where_conditions.append(f"e.industry ILIKE ${param_count}")
                params.append(f"%{industry}%")
            param_count += 1

        if source:
            if source.startswith('='):
                where_conditions.append(f"e.source = ${param_count}")
                params.append(source[1:])
            else:
                where_conditions.append(f"e.source ILIKE ${param_count}")
                params.append(f"%{source}%")
            param_count += 1

        if condition:
            if condition.startswith('='):
                where_conditions.append(f"e.condition = ${param_count}")
                params.append(condition[1:])
            else:
                where_conditions.append(f"e.condition ILIKE ${param_count}")
                params.append(f"%{condition}%")
            param_count += 1

        if position_quantitative:
            where_conditions.append(f"e.position_quantitative::text = ${param_count}")
            params.append(position_quantitative)
            param_count += 1

        if position_qualitative:
            where_conditions.append(f"e.position_qualitative::text = ${param_count}")
            params.append(position_qualitative)
            param_count += 1

        if disparity_quantitative_min is not None:
            where_conditions.append(f"e.disparity_quantitative >= ${param_count}")
            params.append(disparity_quantitative_min)
            param_count += 1

        if disparity_quantitative_max is not None:
            where_conditions.append(f"e.disparity_quantitative <= ${param_count}")
            params.append(disparity_quantitative_max)
            param_count += 1

        if disparity_qualitative_min is not None:
            where_conditions.append(f"e.disparity_qualitative >= ${param_count}")
            params.append(disparity_qualitative_min)
            param_count += 1

        if disparity_qualitative_max is not None:
            where_conditions.append(f"e.disparity_qualitative <= ${param_count}")
            params.append(disparity_qualitative_max)
            param_count += 1

        if event_date_from:
            where_conditions.append(f"e.event_date >= ${param_count}")
            params.append(date.fromisoformat(event_date_from))
            param_count += 1

        if event_date_to:
            where_conditions.append(f"e.event_date <= ${param_count}")
            params.append(date.fromisoformat(event_date_to))
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

        order_clause = "e.id ASC"  # Default sort
        if sortBy and sortOrder:
            if sortBy not in allowed_sort_columns:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid sort column. Allowed: {', '.join(allowed_sort_columns)}",
                )
            order_clause = f"e.{sortBy} {sortOrder.upper()}"

        # Calculate offset
        offset = (page - 1) * pageSize

        pool = await db_pool.get_pool()
        async with pool.acquire() as conn:
            # Get total count
            count_query = f"SELECT COUNT(*) FROM txn_events e WHERE {where_clause}"
            logger.debug(f"Executing count_query: {count_query} with params: {params} (types: {[type(p) for p in params]})")
            total = await conn.fetchval(count_query, *params)

            # Get data with txn_price_trend JOIN (price_trend JSONB is deprecated)
            data_query = f"""
                SELECT
                    e.id::text,
                    e.ticker,
                    TO_CHAR(e.event_date, 'YYYY-MM-DD') as event_date,
                    e.sector,
                    e.industry,
                    e.source,
                    e.source_id,
                    e.position_quantitative::text,
                    e.disparity_quantitative,
                    e.position_qualitative::text,
                    e.disparity_qualitative,
                    e.condition,
                    e.position_quantitative as pos_q_enum,
                    e.position_qualitative as pos_ql_enum,
                    -- Price trend data from txn_price_trend table
                    pt.d_neg14, pt.d_neg13, pt.d_neg12, pt.d_neg11, pt.d_neg10,
                    pt.d_neg9, pt.d_neg8, pt.d_neg7, pt.d_neg6, pt.d_neg5,
                    pt.d_neg4, pt.d_neg3, pt.d_neg2, pt.d_neg1,
                    pt.d_pos1, pt.d_pos2, pt.d_pos3, pt.d_pos4, pt.d_pos5,
                    pt.d_pos6, pt.d_pos7, pt.d_pos8, pt.d_pos9, pt.d_pos10,
                    pt.d_pos11, pt.d_pos12, pt.d_pos13, pt.d_pos14
                FROM txn_events e
                LEFT JOIN txn_price_trend pt ON (
                    e.ticker = pt.ticker
                    AND e.event_date::date = pt.event_date
                )
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

            # Process rows and extract price_trend data from txn_price_trend
            data = []
            for row in rows:
                row_id = str(row["id"])
                logger.debug(f"Processing row: id={row_id}, type={type(row_id)}, ticker={row['ticker']}")

                try:
                    # Helper function to extract performance.close from JSONB
                    def get_day_value(day_offset: int) -> Optional[float]:
                        """Extract performance.close value for day offset from txn_price_trend JSONB."""
                        # Map offset to column name
                        if day_offset < 0:
                            col_name = f"d_neg{abs(day_offset)}"
                        else:
                            col_name = f"d_pos{day_offset}"

                        raw_data = row.get(col_name)
                        if not raw_data:
                            return None

                        # Parse JSONB
                        try:
                            if isinstance(raw_data, str):
                                data_obj = json.loads(raw_data)
                            elif isinstance(raw_data, dict):
                                data_obj = raw_data
                            else:
                                return None

                            # Extract performance.close
                            performance = data_obj.get('performance', {})
                            close_value = performance.get('close')
                            if close_value is not None:
                                return float(close_value)
                        except (json.JSONDecodeError, TypeError, ValueError):
                            pass

                        return None

                    # Extract all day offsets (D-14 to D14, excluding D0)
                    day_values = {}
                    for offset in range(-14, 15):
                        if offset == 0:
                            continue
                        day_values[offset] = get_day_value(offset)

                    # Calculate WTS: day offset with maximum absolute return
                    # Apply position multiplier: long = +1, short = -1
                    position_multiplier = 1
                    pos_q = row["pos_q_enum"]
                    if pos_q:
                        pos_q_str = str(pos_q).lower()
                        if pos_q_str == "short":
                            position_multiplier = -1
                        elif pos_q_str not in ["long", "undefined"]:
                            position_multiplier = 0  # null position

                    wts = None
                    if position_multiplier != 0:
                        max_return = None
                        max_offset = None
                        for offset, value in day_values.items():
                            if value is not None:
                                adjusted_return = value * position_multiplier
                                if max_return is None or adjusted_return > max_return:
                                    max_return = adjusted_return
                                    max_offset = offset
                        wts = max_offset

                    row_data = EventRow(
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
                        wts=wts,
                        # Day offset values (D-14 to D14, excluding D0)
                        d_neg14=day_values.get(-14),
                        d_neg13=day_values.get(-13),
                        d_neg12=day_values.get(-12),
                        d_neg11=day_values.get(-11),
                        d_neg10=day_values.get(-10),
                        d_neg9=day_values.get(-9),
                        d_neg8=day_values.get(-8),
                        d_neg7=day_values.get(-7),
                        d_neg6=day_values.get(-6),
                        d_neg5=day_values.get(-5),
                        d_neg4=day_values.get(-4),
                        d_neg3=day_values.get(-3),
                        d_neg2=day_values.get(-2),
                        d_neg1=day_values.get(-1),
                        d_pos1=day_values.get(1),
                        d_pos2=day_values.get(2),
                        d_pos3=day_values.get(3),
                        d_pos4=day_values.get(4),
                        d_pos5=day_values.get(5),
                        d_pos6=day_values.get(6),
                        d_pos7=day_values.get(7),
                        d_pos8=day_values.get(8),
                        d_pos9=day_values.get(9),
                        d_pos10=day_values.get(10),
                        d_pos11=day_values.get(11),
                        d_pos12=day_values.get(12),
                        d_pos13=day_values.get(13),
                        d_pos14=day_values.get(14),
                    )
                    data.append(row_data)
                    logger.debug(f"Successfully created EventRow with id={row_data.id}, wts={wts}")
                except Exception as e:
                    logger.error(f"Failed to create EventRow: {e}, row_id={row_id}, type={type(row_id)}")
                    raise

            # Log warning if no data found
            if total == 0:
                logger.warning(
                    "action=get_events status=empty_result message='No events in txn_events table. "
                    "Please run: 1) GET /sourceData to collect foundation data, "
                    "2) POST /setEventsTable to consolidate events, "
                    "3) POST /backfillEventsTable to calculate metrics'"
                )

            logger.info(
                f"action=get_events status=success page={page} "
                f"pageSize={pageSize} total={total} returned={len(data)}"
            )

            return EventsResponse(
                data=data, total=total, page=page, pageSize=pageSize
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"action=get_events status=error error={str(e)} "
            f"error_type={type(e).__name__} page={page} pageSize={pageSize}",
            exc_info=True
        )
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch events: {str(e)}"
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


class BulkUpdateRequest(BaseModel):
    """Request model for bulk update events."""

    event_ids: List[str]
    field: str  # "condition" or "position"
    operation: str  # For condition: "append", "modify", "remove". For position: "set"
    value: Optional[str]  # The value to set/append/remove


class BulkUpdateResponse(BaseModel):
    """Response model for bulk update."""

    updated_count: int
    message: str


class TradeRow(BaseModel):
    """Response model for a single trade row."""

    ticker: str
    trade_date: str
    model: str
    source: Optional[str]
    position: Optional[str]
    entry_price: Optional[float]
    exit_price: Optional[float]
    quantity: Optional[int]
    notes: Optional[str]
    # WTS - which day offset (D+N) has the maximum return
    wts: Optional[int]
    # Day offset returns D-14 to D14 (excluding D0)
    d_neg14: Optional[float]
    d_neg13: Optional[float]
    d_neg12: Optional[float]
    d_neg11: Optional[float]
    d_neg10: Optional[float]
    d_neg9: Optional[float]
    d_neg8: Optional[float]
    d_neg7: Optional[float]
    d_neg6: Optional[float]
    d_neg5: Optional[float]
    d_neg4: Optional[float]
    d_neg3: Optional[float]
    d_neg2: Optional[float]
    d_neg1: Optional[float]
    d_pos1: Optional[float]
    d_pos2: Optional[float]
    d_pos3: Optional[float]
    d_pos4: Optional[float]
    d_pos5: Optional[float]
    d_pos6: Optional[float]
    d_pos7: Optional[float]
    d_pos8: Optional[float]
    d_pos9: Optional[float]
    d_pos10: Optional[float]
    d_pos11: Optional[float]
    d_pos12: Optional[float]
    d_pos13: Optional[float]
    d_pos14: Optional[float]


class TradesResponse(BaseModel):
    """Response model for trades with pagination."""

    data: List[TradeRow]
    total: int
    page: int
    pageSize: int


@router.get("/trades", response_model=TradesResponse)
async def get_trades(
    page: int = Query(1, ge=1, description="Page number starting from 1"),
    pageSize: int = Query(50, ge=1, le=1000, description="Number of rows per page"),
    sortBy: Optional[str] = Query(None, description="Column to sort by"),
    sortOrder: Optional[str] = Query(
        None, regex="^(asc|desc)$", description="Sort order: asc or desc"
    ),
    ticker: Optional[str] = Query(None, description="Filter by ticker (contains)"),
    model: Optional[str] = Query(None, description="Filter by model (contains)"),
    source: Optional[str] = Query(None, description="Filter by source (contains)"),
    position: Optional[str] = Query(None, description="Filter by position (contains)"),
    trade_date_from: Optional[str] = Query(None, alias="tradeDateFrom", description="Filter by trade_date >= (YYYY-MM-DD)"),
    trade_date_to: Optional[str] = Query(None, alias="tradeDateTo", description="Filter by trade_date <= (YYYY-MM-DD)"),
):
    """
    Get trades from txn_trades table with pagination, filtering, and sorting.

    Supports:
    - Pagination via page and pageSize
    - Filtering by ticker, model, source, position (case-insensitive contains)
    - Sorting by any column (asc/desc)
    - LEFT JOIN with txn_price_trend for day offset returns
    """
    logger.info(
        f"action=get_trades phase=request_received "
        f"page={page} pageSize={pageSize} sortBy={sortBy} sortOrder={sortOrder} "
        f"ticker={ticker} model={model} source={source} position={position}"
    )
    try:
        # Build WHERE clause
        where_conditions = []
        params = []
        param_count = 1

        if ticker:
            where_conditions.append(f"t.ticker ILIKE ${param_count}")
            params.append(f"%{ticker}%")
            param_count += 1

        if model:
            where_conditions.append(f"t.model ILIKE ${param_count}")
            params.append(f"%{model}%")
            param_count += 1

        if source:
            where_conditions.append(f"t.source ILIKE ${param_count}")
            params.append(f"%{source}%")
            param_count += 1

        if position:
            where_conditions.append(f"t.position ILIKE ${param_count}")
            params.append(f"%{position}%")
            param_count += 1

        if trade_date_from:
            where_conditions.append(f"t.trade_date >= ${param_count}")
            params.append(date.fromisoformat(trade_date_from))
            param_count += 1

        if trade_date_to:
            where_conditions.append(f"t.trade_date <= ${param_count}")
            params.append(date.fromisoformat(trade_date_to))
            param_count += 1

        where_clause = " AND ".join(where_conditions) if where_conditions else "TRUE"

        # Build ORDER BY clause
        allowed_sort_columns = [
            "ticker",
            "trade_date",
            "model",
            "source",
            "position",
            "entry_price",
            "exit_price",
            "quantity",
        ]

        order_clause = "t.ticker ASC, t.trade_date ASC"  # Default sort
        if sortBy and sortOrder:
            if sortBy not in allowed_sort_columns:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid sort column. Allowed: {', '.join(allowed_sort_columns)}",
                )
            order_clause = f"t.{sortBy} {sortOrder.upper()}"

        # Calculate offset
        offset = (page - 1) * pageSize

        pool = await db_pool.get_pool()
        async with pool.acquire() as conn:
            # Get total count
            count_query = f"SELECT COUNT(*) FROM txn_trades t WHERE {where_clause}"
            total = await conn.fetchval(count_query, *params)

            # Get data with txn_price_trend JOIN
            data_query = f"""
                SELECT
                    t.ticker,
                    TO_CHAR(t.trade_date, 'YYYY-MM-DD') as trade_date,
                    t.model,
                    t.source,
                    t.position,
                    t.entry_price,
                    t.exit_price,
                    t.quantity,
                    t.notes,
                    -- Price trend data from txn_price_trend table (JOIN on trade_date = event_date)
                    pt.d_neg14, pt.d_neg13, pt.d_neg12, pt.d_neg11, pt.d_neg10,
                    pt.d_neg9, pt.d_neg8, pt.d_neg7, pt.d_neg6, pt.d_neg5,
                    pt.d_neg4, pt.d_neg3, pt.d_neg2, pt.d_neg1,
                    pt.d_pos1, pt.d_pos2, pt.d_pos3, pt.d_pos4, pt.d_pos5,
                    pt.d_pos6, pt.d_pos7, pt.d_pos8, pt.d_pos9, pt.d_pos10,
                    pt.d_pos11, pt.d_pos12, pt.d_pos13, pt.d_pos14
                FROM txn_trades t
                LEFT JOIN txn_price_trend pt ON (
                    t.ticker = pt.ticker
                    AND t.trade_date = pt.event_date
                )
                WHERE {where_clause}
                ORDER BY {order_clause}
                LIMIT {pageSize}
                OFFSET {offset}
            """

            rows = await conn.fetch(data_query, *params)

            logger.debug(
                f"action=get_trades phase=query_complete "
                f"rows_fetched={len(rows)} page={page} pageSize={pageSize}"
            )

            # Process rows and extract price_trend data from txn_price_trend
            data = []
            for row in rows:
                try:
                    # Helper function to extract performance.close from JSONB
                    def get_day_value(day_offset: int) -> Optional[float]:
                        """Extract performance.close value for day offset from txn_price_trend JSONB."""
                        # Map offset to column name
                        if day_offset < 0:
                            col_name = f"d_neg{abs(day_offset)}"
                        else:
                            col_name = f"d_pos{day_offset}"

                        raw_data = row.get(col_name)
                        if not raw_data:
                            return None

                        # Parse JSONB
                        try:
                            if isinstance(raw_data, str):
                                data_obj = json.loads(raw_data)
                            elif isinstance(raw_data, dict):
                                data_obj = raw_data
                            else:
                                return None

                            # Extract performance.close
                            performance = data_obj.get('performance', {})
                            close_value = performance.get('close')
                            if close_value is not None:
                                return float(close_value)
                        except (json.JSONDecodeError, TypeError, ValueError):
                            pass

                        return None

                    # Extract all day offsets (D-14 to D14, excluding D0)
                    day_values = {}
                    for offset in range(-14, 15):
                        if offset == 0:
                            continue
                        day_values[offset] = get_day_value(offset)

                    # Calculate WTS: day offset with maximum return
                    # For trades, use position to determine multiplier
                    position_multiplier = 1
                    pos = row["position"]
                    if pos:
                        pos_str = str(pos).lower()
                        if pos_str == "short":
                            position_multiplier = -1
                        elif pos_str == "neutral" or pos_str == "null":
                            position_multiplier = 0

                    wts = None
                    if position_multiplier != 0:
                        max_return = None
                        max_offset = None
                        for offset, value in day_values.items():
                            if value is not None:
                                adjusted_return = value * position_multiplier
                                if max_return is None or adjusted_return > max_return:
                                    max_return = adjusted_return
                                    max_offset = offset
                        wts = max_offset

                    row_data = TradeRow(
                        ticker=row["ticker"],
                        trade_date=row["trade_date"],
                        model=row["model"],
                        source=row["source"],
                        position=row["position"],
                        entry_price=row["entry_price"],
                        exit_price=row["exit_price"],
                        quantity=row["quantity"],
                        notes=row["notes"],
                        wts=wts,
                        # Day offset values
                        d_neg14=day_values.get(-14),
                        d_neg13=day_values.get(-13),
                        d_neg12=day_values.get(-12),
                        d_neg11=day_values.get(-11),
                        d_neg10=day_values.get(-10),
                        d_neg9=day_values.get(-9),
                        d_neg8=day_values.get(-8),
                        d_neg7=day_values.get(-7),
                        d_neg6=day_values.get(-6),
                        d_neg5=day_values.get(-5),
                        d_neg4=day_values.get(-4),
                        d_neg3=day_values.get(-3),
                        d_neg2=day_values.get(-2),
                        d_neg1=day_values.get(-1),
                        d_pos1=day_values.get(1),
                        d_pos2=day_values.get(2),
                        d_pos3=day_values.get(3),
                        d_pos4=day_values.get(4),
                        d_pos5=day_values.get(5),
                        d_pos6=day_values.get(6),
                        d_pos7=day_values.get(7),
                        d_pos8=day_values.get(8),
                        d_pos9=day_values.get(9),
                        d_pos10=day_values.get(10),
                        d_pos11=day_values.get(11),
                        d_pos12=day_values.get(12),
                        d_pos13=day_values.get(13),
                        d_pos14=day_values.get(14),
                    )
                    data.append(row_data)
                except Exception as e:
                    logger.error(f"Failed to create TradeRow: {e}, ticker={row['ticker']}, trade_date={row['trade_date']}")
                    raise

            # Log warning if no data found
            if total == 0:
                logger.warning(
                    "action=get_trades status=empty_result message='No trades in txn_trades table. "
                    "Please insert trades using POST /trades endpoint.'"
                )

            logger.info(
                f"action=get_trades status=success page={page} "
                f"pageSize={pageSize} total={total} returned={len(data)}"
            )

            return TradesResponse(
                data=data, total=total, page=page, pageSize=pageSize
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"action=get_trades status=error error={str(e)} "
            f"error_type={type(e).__name__} page={page} pageSize={pageSize}",
            exc_info=True
        )
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch trades: {str(e)}"
        )


@router.post("/bulkUpdate", response_model=BulkUpdateResponse)
async def bulk_update_events(request: BulkUpdateRequest = Body(...)):
    """
    Bulk update events.

    Supports:
    - condition field: append (adds value with comma), modify (replaces entire value), remove (removes value from comma-separated list)
    - position: set (sets to specified value: long/short/null/neutral)
    """
    logger.info(
        f"action=bulk_update_events phase=request_received "
        f"event_ids={len(request.event_ids)} field={request.field} operation={request.operation} value={request.value}"
    )

    try:
        # Validate field
        allowed_fields = ["condition", "position"]
        if request.field not in allowed_fields:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid field. Allowed: {', '.join(allowed_fields)}",
            )

        # Validate operation
        if request.field == "condition":
            allowed_operations = ["append", "modify", "remove"]
            if request.operation not in allowed_operations:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid operation for condition. Allowed: {', '.join(allowed_operations)}",
                )
        elif request.field == "position":
            allowed_operations = ["set"]
            if request.operation not in allowed_operations:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid operation for position. Allowed: {', '.join(allowed_operations)}",
                )
            # Validate value for position
            allowed_positions = ["long", "short", "null", "neutral"]
            if request.value and request.value.lower() not in allowed_positions:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid position value. Allowed: {', '.join(allowed_positions)}",
                )

        pool = await db_pool.get_pool()
        async with pool.acquire() as conn:
            updated_count = 0

            if request.field == "condition":
                if request.operation == "append":
                    # Append value to existing condition (comma-separated)
                    update_query = """
                        UPDATE txn_events
                        SET condition = CASE
                            WHEN condition IS NULL OR condition = '' THEN $1
                            ELSE condition || ',' || $1
                        END
                        WHERE id = ANY($2::uuid[])
                    """
                    result = await conn.execute(update_query, request.value, request.event_ids)
                elif request.operation == "modify":
                    # Modify (replace) entire condition value
                    update_query = """
                        UPDATE txn_events
                        SET condition = $1
                        WHERE id = ANY($2::uuid[])
                    """
                    result = await conn.execute(update_query, request.value, request.event_ids)
                elif request.operation == "remove":
                    # Remove value from comma-separated list
                    # This is complex, use Python to parse and update
                    for event_id in request.event_ids:
                        row = await conn.fetchrow("SELECT condition FROM txn_events WHERE id = $1::uuid", event_id)
                        if row and row["condition"]:
                            conditions = [c.strip() for c in row["condition"].split(",")]
                            conditions = [c for c in conditions if c != request.value]
                            new_condition = ",".join(conditions) if conditions else None
                            await conn.execute(
                                "UPDATE txn_events SET condition = $1 WHERE id = $2::uuid",
                                new_condition,
                                event_id,
                            )
                            updated_count += 1
                    logger.info(
                        f"action=bulk_update_events status=success field={request.field} "
                        f"operation={request.operation} updated={updated_count}"
                    )
                    return BulkUpdateResponse(
                        updated_count=updated_count,
                        message=f"Successfully updated {updated_count} events",
                    )

                # Extract count from result
                updated_count = int(result.split()[-1])

            elif request.field == "position":
                if request.operation == "set":
                    # Set position value (long/short/null/neutral)
                    position_value = None if request.value.lower() == "null" else request.value.lower()
                    update_query = """
                        UPDATE txn_events
                        SET position = $1::position
                        WHERE id = ANY($2::uuid[])
                    """
                    result = await conn.execute(update_query, position_value, request.event_ids)
                    updated_count = int(result.split()[-1])

            logger.info(
                f"action=bulk_update_events status=success field={request.field} "
                f"operation={request.operation} updated={updated_count}"
            )

            return BulkUpdateResponse(
                updated_count=updated_count,
                message=f"Successfully updated {updated_count} events",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"action=bulk_update_events status=error error={str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to bulk update events: {str(e)}"
        )
