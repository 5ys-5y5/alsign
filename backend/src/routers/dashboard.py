"""Router for dashboard endpoints providing KPIs and performance metrics."""

import logging
import json
from fastapi import APIRouter, HTTPException, Query, Body, Depends
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from datetime import datetime, date, timedelta, timezone
from uuid import UUID

from ..database.connection import db_pool
from ..services.utils.datetime_utils import is_trading_day
from ..services.utils.freshness_utils import get_previous_quarter_end
from ..auth import get_current_user, require_admin, UserContext

logger = logging.getLogger("alsign")

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


class KPIResponse(BaseModel):
    """Response model for KPI data."""

    coverage: int
    quantitativesFreshness: Optional[str]
    holidaysFreshness: Optional[str]
    tradesFreshness: Optional[str]


class EventsKPIResponse(BaseModel):
    """Response model for events page KPI data."""

    coverage: int
    targetsFreshness: Optional[str]
    quantitativesFreshness: Optional[str]
    eventsFreshness: Optional[str]


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
    # Day offset returns D-14 to D14 (including D0)
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
    d_0: Optional[float]
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
async def get_kpis(user: UserContext = Depends(require_admin)):
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

            quantitatives_freshness = await conn.fetchval(
                "SELECT MAX(updated_at) FROM config_lv3_quantitatives"
            )
            holidays_freshness = await conn.fetchval(
                "SELECT MAX(updated_at) FROM config_lv3_market_holidays"
            )
            trades_freshness = await conn.fetchval(
                "SELECT MAX(updated_at) FROM txn_trades"
            )
            logger.debug(
                "action=get_kpis phase=freshness_fetched "
                f"quantitatives={quantitatives_freshness} holidays={holidays_freshness} trades={trades_freshness}"
            )

            def to_iso(value):
                return value.isoformat() if value else None

            # Check if database is empty and provide helpful message
            if coverage_result == 0:
                logger.warning("action=get_kpis status=empty_database message='No data in config_lv3_targets'")

            logger.info(
                "action=get_kpis status=success "
                f"coverage={coverage_result} quantitativesFreshness={quantitatives_freshness} "
                f"holidaysFreshness={holidays_freshness} tradesFreshness={trades_freshness}"
            )

            return KPIResponse(
                coverage=coverage_result or 0,
                quantitativesFreshness=to_iso(quantitatives_freshness),
                holidaysFreshness=to_iso(holidays_freshness),
                tradesFreshness=to_iso(trades_freshness),
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


@router.get("/events/kpis", response_model=EventsKPIResponse)
async def get_events_kpis(user: UserContext = Depends(require_admin)):
    """
    Get KPI data for the events page.

    Returns:
        - coverage: Count of tickers in config_lv3_targets
        - targetsFreshness: Latest update timestamp from config_lv3_targets
        - quantitativesFreshness: Latest update timestamp from config_lv3_quantitatives
        - eventsFreshness: Latest update timestamp from txn_events
    """
    logger.info("action=get_events_kpis phase=request_received")
    try:
        pool = await db_pool.get_pool()
        async with pool.acquire() as conn:
            coverage_result = await conn.fetchval(
                "SELECT COUNT(*) FROM config_lv3_targets"
            )
            targets_freshness = await conn.fetchval(
                "SELECT MAX(updated_at) FROM config_lv3_targets"
            )
            quantitatives_freshness = await conn.fetchval(
                "SELECT MAX(updated_at) FROM config_lv3_quantitatives"
            )
            events_freshness = await conn.fetchval(
                "SELECT MAX(updated_at) FROM txn_events"
            )

            def to_iso(value):
                return value.isoformat() if value else None

            logger.info(
                "action=get_events_kpis status=success "
                f"coverage={coverage_result} targetsFreshness={targets_freshness} "
                f"quantitativesFreshness={quantitatives_freshness} eventsFreshness={events_freshness}"
            )

            return EventsKPIResponse(
                coverage=coverage_result or 0,
                targetsFreshness=to_iso(targets_freshness),
                quantitativesFreshness=to_iso(quantitatives_freshness),
                eventsFreshness=to_iso(events_freshness),
            )

    except Exception as e:
        logger.error(f"action=get_events_kpis status=error error={str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch events KPIs: {str(e)}")


@router.get("/events", response_model=EventsResponse)
async def get_events(
    user: UserContext = Depends(require_admin),
    page: int = Query(1, ge=1, description="Page number starting from 1"),
    pageSize: int = Query(50, ge=1, le=1000, description="Number of rows per page"),
    skip_count: bool = Query(False, alias="skipCount", description="Skip exact count query for faster responses"),
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
            # Get total count (or fast estimate when skipCount enabled)
            if skip_count:
                total = await conn.fetchval("SELECT reltuples::bigint FROM pg_class WHERE oid = 'txn_events'::regclass")
                total = int(total or 0)
            else:
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
                    pt.d_neg4, pt.d_neg3, pt.d_neg2, pt.d_neg1, pt.d_0,
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
                        if day_offset == 0:
                            col_name = "d_0"
                        elif day_offset < 0:
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

                    # Extract all day offsets (D-14 to D14, including D0)
                    day_values = {}
                    for offset in range(-14, 15):
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
                            if offset == 0:
                                continue
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
                        # Day offset values (D-14 to D14, including D0)
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
                        d_0=day_values.get(0),
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
    user: UserContext = Depends(require_admin),
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

    ticker: Optional[str]
    trade_date: Optional[str]
    model: Optional[str]
    source: Optional[str]
    position: Optional[str]
    entry_price: Optional[float]
    exit_price: Optional[float]
    quantity: Optional[int]
    notes: Optional[str]
    # WTS - which day offset (D+N) has the maximum return
    wts: Optional[int]
    # Day offset returns D-14 to D14 (including D0)
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
    d_0: Optional[float]
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
    day_offset_performance: Optional[Dict[str, Optional[float]]] = None
    day_offset_price_trend: Optional[Dict[str, Optional[float]]] = None
    day_offset_target_dates: Optional[Dict[str, Optional[str]]] = None
    is_blurred: Optional[bool] = None


class TradesResponse(BaseModel):
    """Response model for trades with pagination."""

    data: List[TradeRow]
    total: int
    page: int
    pageSize: int


@router.get("/trades", response_model=TradesResponse)
async def get_trades(
    user: UserContext = Depends(get_current_user),
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
    day_offset_mode: str = Query(
        "performance",
        alias="dayOffsetMode",
        regex="^(performance|price_trend)$",
        description="Day offset display mode: performance or price_trend",
    ),
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
        f"ticker={ticker} model={model} source={source} position={position} "
        f"day_offset_mode={day_offset_mode}"
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
            "trade_date",
            "position",
            "ticker",
        ]

        order_clause = "t.trade_date DESC, t.position DESC, t.ticker DESC"
        order_clause_outer = "trade_date_date DESC, position DESC, ticker DESC"
        if sortBy and sortOrder:
            if sortBy not in allowed_sort_columns:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid sort column. Allowed: {', '.join(allowed_sort_columns)}",
                )
            order_clause = f"t.{sortBy} {sortOrder.upper()}"
            order_column_outer = "trade_date_date" if sortBy == "trade_date" else sortBy
            order_clause_outer = f"{order_column_outer} {sortOrder.upper()}"

        # Calculate offset
        offset = (page - 1) * pageSize

        pool = await db_pool.get_pool()
        async with pool.acquire() as conn:
            is_paying = user.is_subscriber
            if user.is_authenticated and user.user_id:
                profile = await conn.fetchrow(
                    """
                    SELECT is_paying, subscription_expires_at
                    FROM public.user_profiles
                    WHERE user_id = $1
                    """,
                    user.user_id,
                )
                if profile:
                    expires_at = profile["subscription_expires_at"]
                    if expires_at is None:
                        is_paying = bool(profile["is_paying"])
                    else:
                        is_paying = bool(profile["is_paying"]) and expires_at > datetime.now(timezone.utc)

            cutoff_date = date.today() - timedelta(days=30)

            if is_paying:
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
                        pt.d_neg4, pt.d_neg3, pt.d_neg2, pt.d_neg1, pt.d_0,
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
            else:
                cutoff_param_index = len(params) + 1
                params_with_cutoff = [*params, cutoff_date]

                count_query = f"""
                    WITH base AS (
                        SELECT
                            t.trade_date AS trade_date_date,
                            ROW_NUMBER() OVER (ORDER BY {order_clause}) AS rn
                        FROM txn_trades t
                        WHERE {where_clause}
                    )
                    SELECT COUNT(*)
                    FROM base
                    WHERE (trade_date_date > ${cutoff_param_index} AND rn <= 5)
                       OR trade_date_date <= ${cutoff_param_index}
                """
                total = await conn.fetchval(count_query, *params_with_cutoff)

                data_query = f"""
                    WITH base AS (
                        SELECT
                            t.ticker,
                            t.trade_date AS trade_date_date,
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
                            pt.d_neg4, pt.d_neg3, pt.d_neg2, pt.d_neg1, pt.d_0,
                            pt.d_pos1, pt.d_pos2, pt.d_pos3, pt.d_pos4, pt.d_pos5,
                            pt.d_pos6, pt.d_pos7, pt.d_pos8, pt.d_pos9, pt.d_pos10,
                            pt.d_pos11, pt.d_pos12, pt.d_pos13, pt.d_pos14,
                            ROW_NUMBER() OVER (ORDER BY {order_clause}) AS rn
                        FROM txn_trades t
                        LEFT JOIN txn_price_trend pt ON (
                            t.ticker = pt.ticker
                            AND t.trade_date = pt.event_date
                        )
                        WHERE {where_clause}
                    )
                    SELECT *
                    FROM base
                    WHERE (trade_date_date > ${cutoff_param_index} AND rn <= 5)
                       OR trade_date_date <= ${cutoff_param_index}
                    ORDER BY {order_clause_outer}
                    LIMIT {pageSize}
                    OFFSET {offset}
                """

                rows = await conn.fetch(data_query, *params_with_cutoff)

            logger.debug(
                f"action=get_trades phase=query_complete "
                f"rows_fetched={len(rows)} page={page} pageSize={pageSize}"
            )

            # Process rows and extract price_trend data from txn_price_trend
            data = []
            for row in rows:
                try:
                    trade_date_str = row["trade_date"]
                    is_blurred = False
                    if not is_paying and trade_date_str:
                        try:
                            trade_date_obj = date.fromisoformat(trade_date_str)
                            if trade_date_obj > cutoff_date:
                                is_blurred = True
                        except ValueError:
                            pass

                    if is_blurred:
                        data.append(TradeRow(
                            ticker=None,
                            trade_date=None,
                            model=None,
                            source=None,
                            position=None,
                            entry_price=None,
                            exit_price=None,
                            quantity=None,
                            notes=None,
                            wts=None,
                            d_neg14=None,
                            d_neg13=None,
                            d_neg12=None,
                            d_neg11=None,
                            d_neg10=None,
                            d_neg9=None,
                            d_neg8=None,
                            d_neg7=None,
                            d_neg6=None,
                            d_neg5=None,
                            d_neg4=None,
                            d_neg3=None,
                            d_neg2=None,
                            d_neg1=None,
                            d_0=None,
                            d_pos1=None,
                            d_pos2=None,
                            d_pos3=None,
                            d_pos4=None,
                            d_pos5=None,
                            d_pos6=None,
                            d_pos7=None,
                            d_pos8=None,
                            d_pos9=None,
                            d_pos10=None,
                            d_pos11=None,
                            d_pos12=None,
                            d_pos13=None,
                            d_pos14=None,
                            day_offset_performance=None,
                            day_offset_price_trend=None,
                            day_offset_target_dates=None,
                            is_blurred=True,
                        ))
                        continue

                    # Helper function to extract day offset values from txn_price_trend JSONB
                    def get_day_value(day_offset: int, value_mode: str) -> Optional[float]:
                        """Extract performance.close or price_trend.close for day offset from txn_price_trend JSONB."""
                        # Map offset to column name
                        if day_offset == 0:
                            col_name = "d_0"
                        elif day_offset < 0:
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

                            if not isinstance(data_obj, dict):
                                return None

                            if value_mode == "price_trend":
                                price_trend = data_obj.get('price_trend')
                                if not isinstance(price_trend, dict):
                                    return None
                                close_value = price_trend.get('close')
                            else:
                                performance = data_obj.get('performance')
                                if not isinstance(performance, dict):
                                    return None
                                close_value = performance.get('close')
                            if close_value is not None:
                                return float(close_value)
                        except (json.JSONDecodeError, TypeError, ValueError):
                            pass

                        return None

                    # Extract all day offsets (D-14 to D14, excluding D0)
                    performance_day_values = {}
                    price_trend_day_values = {}
                    display_day_values = {}
                    for offset in range(-14, 15):
                        performance_day_values[offset] = get_day_value(offset, "performance")
                        price_trend_day_values[offset] = get_day_value(offset, "price_trend")
                        if day_offset_mode == "price_trend":
                            display_day_values[offset] = price_trend_day_values[offset]
                        else:
                            display_day_values[offset] = performance_day_values[offset]

                    def build_day_offset_map(day_values: Dict[int, Optional[float]]) -> Dict[str, Optional[float]]:
                        result = {}
                        for offset in range(-14, 15):
                            if offset == 0:
                                key = "d_0"
                            else:
                                key = f"d_neg{abs(offset)}" if offset < 0 else f"d_pos{offset}"
                            result[key] = day_values.get(offset)
                        return result

                    def get_day_target_date(day_offset: int) -> Optional[str]:
                        if day_offset < 0:
                            col_name = f"d_neg{abs(day_offset)}"
                        else:
                            col_name = f"d_pos{day_offset}"

                        raw_data = row.get(col_name)
                        if not raw_data:
                            return None

                        try:
                            if isinstance(raw_data, str):
                                data_obj = json.loads(raw_data)
                            elif isinstance(raw_data, dict):
                                data_obj = raw_data
                            else:
                                return None

                            if not isinstance(data_obj, dict):
                                return None

                            target_date = data_obj.get('targetDate')
                            if isinstance(target_date, str) and target_date:
                                return target_date
                        except (json.JSONDecodeError, TypeError, ValueError):
                            pass

                        return None

                    target_dates = {}
                    for offset in range(-14, 15):
                        if offset == 0:
                            key = "d_0"
                        else:
                            key = f"d_neg{abs(offset)}" if offset < 0 else f"d_pos{offset}"
                        target_dates[key] = get_day_target_date(offset)

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
                        for offset, value in performance_day_values.items():
                            if offset == 0:
                                continue
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
                        d_neg14=display_day_values.get(-14),
                        d_neg13=display_day_values.get(-13),
                        d_neg12=display_day_values.get(-12),
                        d_neg11=display_day_values.get(-11),
                        d_neg10=display_day_values.get(-10),
                        d_neg9=display_day_values.get(-9),
                        d_neg8=display_day_values.get(-8),
                        d_neg7=display_day_values.get(-7),
                        d_neg6=display_day_values.get(-6),
                        d_neg5=display_day_values.get(-5),
                        d_neg4=display_day_values.get(-4),
                        d_neg3=display_day_values.get(-3),
                        d_neg2=display_day_values.get(-2),
                        d_neg1=display_day_values.get(-1),
                        d_0=display_day_values.get(0),
                        d_pos1=display_day_values.get(1),
                        d_pos2=display_day_values.get(2),
                        d_pos3=display_day_values.get(3),
                        d_pos4=display_day_values.get(4),
                        d_pos5=display_day_values.get(5),
                        d_pos6=display_day_values.get(6),
                        d_pos7=display_day_values.get(7),
                        d_pos8=display_day_values.get(8),
                        d_pos9=display_day_values.get(9),
                        d_pos10=display_day_values.get(10),
                        d_pos11=display_day_values.get(11),
                        d_pos12=display_day_values.get(12),
                        d_pos13=display_day_values.get(13),
                        d_pos14=display_day_values.get(14),
                        day_offset_performance=build_day_offset_map(performance_day_values),
                        day_offset_price_trend=build_day_offset_map(price_trend_day_values),
                        day_offset_target_dates=target_dates,
                        is_blurred=False,
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
async def bulk_update_events(
    request: BulkUpdateRequest = Body(...),
    user: UserContext = Depends(require_admin),
):
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
