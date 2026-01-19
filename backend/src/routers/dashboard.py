"""Router for dashboard endpoints providing KPIs and performance metrics."""

import logging
import json
import math
import time
import asyncio
from fastapi import APIRouter, HTTPException, Query, Body, Depends
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from datetime import datetime, date, timedelta, timezone
from uuid import UUID

from ..database.connection import db_pool
from ..services.utils.datetime_utils import is_trading_day
from ..services.utils.freshness_utils import get_previous_quarter_end
from ..services.best_window_policy import (
    evaluate_best_window_formula,
    get_best_window_offsets,
    load_best_window_policy,
)
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


class EventsHistoryRow(BaseModel):
    """Response model for a single events history row with precomputed maps."""

    id: str
    ticker: str
    event_date: str
    sector: Optional[str]
    industry: Optional[str]
    source: Optional[str]
    source_id: Optional[str]
    position_quantitative: Optional[str]
    disparity_quantitative: Optional[float]
    position_qualitative: Optional[str]
    disparity_qualitative: Optional[float]
    condition: Optional[str]
    position: Optional[str]
    wts: Optional[int]
    day_offset_performance: Optional[Dict[str, Optional[float]]]
    day_offset_performance_previous: Optional[Dict[str, Optional[float]]]
    day_offset_price_trend: Optional[Dict[str, Optional[float]]]
    day_offset_price_trend_open: Optional[Dict[str, Optional[float]]]
    day_offset_price_trend_high: Optional[Dict[str, Optional[float]]]
    day_offset_price_trend_low: Optional[Dict[str, Optional[float]]]
    day_offset_price_trend_close: Optional[Dict[str, Optional[float]]]
    day_offset_target_dates: Optional[Dict[str, Optional[str]]]
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


class EventsHistoryResponse(BaseModel):
    """Response model for events history rows."""

    data: List[EventsHistoryRow]
    total: int


class BestWindowEntry(BaseModel):
    """Best window entry for a specific mode."""

    startOffset: int
    endOffset: int
    avg: float
    avgAfterFee: float
    totalReturn: float
    totalAfterFee: float
    length: int
    avgRows: Optional[float]


class StrategyMetrics(BaseModel):
    sharpe: Optional[float]
    sortino: Optional[float]
    calmar: Optional[float]
    cagr: Optional[float]
    maxDrawdown: Optional[float]
    meanDaily: Optional[float]
    stdevDaily: Optional[float]
    downsideStdevDaily: Optional[float]
    days: int
    totalReturn: Optional[float]


class BestWindowBacktestSummary(BaseModel):
    entryOffset: Optional[int]
    entryField: Optional[str]
    holdDays: Optional[int]
    exitOffset: Optional[int]
    exitMode: Optional[str]
    trades: int
    avgLogReturn: Optional[float]
    avgDailyLogReturn: Optional[float]
    avgCagrDaily: Optional[float]
    avgMdd: Optional[float]
    avgAtr: Optional[float]
    avgRiskPenalty: Optional[float]
    avgScore: Optional[float]
    exitReasonCounts: Dict[str, int]
    strategy: Optional[StrategyMetrics]


class BestWindowMode(BaseModel):
    """Best window summary for a mode."""

    best: Optional[BestWindowEntry]
    topWindows: List[BestWindowEntry]
    windowsCount: int
    dataOffsetsCount: int
    totalOffsets: int
    backtest: Optional[BestWindowBacktestSummary] = None
    backtestModes: Optional[Dict[str, Optional[BestWindowBacktestSummary]]] = None
    offsetAverages: Optional[Dict[str, Optional[float]]] = None
    offsetCounts: Optional[Dict[str, int]] = None
    offsetStdDevs: Optional[Dict[str, Optional[float]]] = None
    offsetPValues: Optional[Dict[str, Optional[float]]] = None


class EventsHistoryBestWindowResponse(BaseModel):
    """Response model for events history best window summary."""

    designated: BestWindowMode
    previous: BestWindowMode


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

            # Get data without txn_price_trend (use historical_price from config_lv3_quantitatives)
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
                    e.position_qualitative as pos_ql_enum
                FROM txn_events e
                WHERE {where_clause}
                ORDER BY {order_clause}
                LIMIT {pageSize}
                OFFSET {offset}
            """

            rows = await conn.fetch(data_query, *params)
            tickers = sorted({row["ticker"] for row in rows if row["ticker"]})
            ticker_cache: Dict[str, Dict[str, Any]] = {}
            if tickers:
                historical_rows = await conn.fetch(
                    """
                    SELECT ticker, historical_price
                    FROM config_lv3_quantitatives
                    WHERE ticker = ANY($1)
                    """,
                    tickers,
                )
                for historical_row in historical_rows:
                    historical_price = normalize_historical_price(historical_row["historical_price"])
                    ticker_cache[historical_row["ticker"]] = build_ticker_cache(historical_price)

            logger.debug(
                f"action=get_performance_summary phase=query_complete "
                f"rows_fetched={len(rows)} page={page} pageSize={pageSize}"
            )

            # Process rows and compute performance using historical_price (D-14 close baseline)
            data = []
            for row in rows:
                row_id = str(row["id"])
                logger.debug(f"Processing row: id={row_id}, type={type(row_id)}, ticker={row['ticker']}")

                try:
                    day_values: Dict[int, Optional[float]] = {}
                    cache = ticker_cache.get(row["ticker"])
                    if cache:
                        maps = build_event_day_offset_maps(cache, row["event_date"])
                        close_map = maps["day_offset_close"]
                        base_close = close_map.get("d_neg14")
                        if base_close is None or base_close == 0:
                            base_close = None
                        for offset in range(-14, 15):
                            day_key = build_day_key(offset)
                            close_value = close_map.get(day_key)
                            if base_close is None or close_value is None:
                                day_values[offset] = None
                            else:
                                day_values[offset] = (close_value - base_close) / base_close
                    else:
                        for offset in range(-14, 15):
                            day_values[offset] = None

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


def build_day_key(offset: int) -> str:
    if offset == 0:
        return "d_0"
    if offset < 0:
        return f"d_neg{abs(offset)}"
    return f"d_pos{offset}"


def parse_jsonb(raw_data: Any) -> Optional[dict]:
    if raw_data is None:
        return None
    if isinstance(raw_data, dict):
        return raw_data
    if isinstance(raw_data, str):
        try:
            return json.loads(raw_data)
        except json.JSONDecodeError:
            return None
    return None


def normalize_historical_price(raw_data: Any) -> List[dict]:
    if raw_data is None:
        return []
    if isinstance(raw_data, str):
        try:
            parsed = json.loads(raw_data)
        except json.JSONDecodeError:
            return []
        return normalize_historical_price(parsed)
    if isinstance(raw_data, dict) and isinstance(raw_data.get("historical"), list):
        return raw_data.get("historical") or []
    if isinstance(raw_data, list):
        return raw_data
    return []


def build_ticker_cache(historical_rows: List[dict]) -> Dict[str, Any]:
    ohlc_by_date: Dict[str, Dict[str, Optional[float]]] = {}
    dates = []
    for record in historical_rows:
        date_key = record.get("date")
        if not date_key:
            continue
        open_value = to_finite_or_none(record.get("open"))
        high_value = to_finite_or_none(record.get("high"))
        low_value = to_finite_or_none(record.get("low"))
        close_value = to_finite_or_none(record.get("close"))
        ohlc_by_date[date_key] = {
            "open": open_value,
            "high": high_value,
            "low": low_value,
            "close": close_value,
        }
        dates.append(date_key)
    dates.sort()
    index_by_date = {date_key: idx for idx, date_key in enumerate(dates)}
    return {
        "ohlc_by_date": ohlc_by_date,
        "dates_asc": dates,
        "index_by_date": index_by_date,
    }


def find_nearest_future_index(dates_asc: List[str], target_date: Optional[str]) -> int:
    if not target_date:
        return -1
    for idx, date_key in enumerate(dates_asc):
        if date_key >= target_date:
            return idx
    return -1


def build_event_day_offset_maps(
    cache: Dict[str, Any],
    event_date: Optional[str],
) -> Dict[str, Dict[str, Optional[float]]]:
    dates_asc = cache.get("dates_asc", [])
    index_by_date = cache.get("index_by_date", {})
    ohlc_by_date = cache.get("ohlc_by_date", {})

    event_index = index_by_date.get(event_date, -1)
    if event_index < 0:
        event_index = find_nearest_future_index(dates_asc, event_date)

    day_offset_target_dates: Dict[str, Optional[str]] = {}
    day_offset_open: Dict[str, Optional[float]] = {}
    day_offset_high: Dict[str, Optional[float]] = {}
    day_offset_low: Dict[str, Optional[float]] = {}
    day_offset_close: Dict[str, Optional[float]] = {}
    day_offset_price_trend: Dict[str, Optional[float]] = {}

    for offset in range(-14, 15):
        day_key = build_day_key(offset)
        target_index = event_index + offset if event_index >= 0 else None
        date_key = dates_asc[target_index] if target_index is not None and 0 <= target_index < len(dates_asc) else None
        ohlc = ohlc_by_date.get(date_key) if date_key else None
        open_value = ohlc.get("open") if ohlc else None
        high_value = ohlc.get("high") if ohlc else None
        low_value = ohlc.get("low") if ohlc else None
        close_value = ohlc.get("close") if ohlc else None

        day_offset_target_dates[day_key] = date_key
        day_offset_open[day_key] = open_value
        day_offset_high[day_key] = high_value
        day_offset_low[day_key] = low_value
        day_offset_close[day_key] = close_value
        day_offset_price_trend[day_key] = open_value if offset == 0 else close_value

    return {
        "day_offset_target_dates": day_offset_target_dates,
        "day_offset_open": day_offset_open,
        "day_offset_high": day_offset_high,
        "day_offset_low": day_offset_low,
        "day_offset_close": day_offset_close,
        "day_offset_price_trend": day_offset_price_trend,
    }


def get_position_multiplier(position_value: Optional[str]) -> int:
    if not position_value:
        return 1
    normalized = str(position_value).lower()
    return -1 if normalized == "short" else 1


def to_finite_or_none(value: Any) -> Optional[float]:
    try:
        num_value = float(value)
        if num_value != num_value:
            return None
        return num_value
    except (TypeError, ValueError):
        return None


def compute_designated_performance(
    open_map: Dict[str, Optional[float]],
    high_map: Dict[str, Optional[float]],
    low_map: Dict[str, Optional[float]],
    close_map: Dict[str, Optional[float]],
    base_offset: int,
    base_field: str,
    min_threshold: Optional[float],
    max_threshold: Optional[float],
    position_multiplier: int,
) -> Dict[str, Optional[float]]:
    base_day_key = build_day_key(base_offset)
    base_map = {
        "open": open_map,
        "high": high_map,
        "low": low_map,
        "close": close_map,
    }.get(base_field, close_map)
    base_price = base_map.get(base_day_key)
    if base_price is None or base_price == 0:
        base_price = None

    performance_map: Dict[str, Optional[float]] = {}
    stop_offset: Optional[int] = None
    stop_value_raw: Optional[float] = None
    threshold_start = max(-14, min(14, base_offset))

    for offset in range(-14, 15):
        day_key = build_day_key(offset)
        open_value = open_map.get(day_key)
        high_value = high_map.get(day_key)
        low_value = low_map.get(day_key)
        close_value = close_map.get(day_key)

        if stop_offset is not None and offset > stop_offset:
            performance_map[day_key] = None
            continue

        base_for_offset = None
        if offset == 0 and base_offset == 0 and open_value is not None and open_value != 0:
            base_for_offset = open_value
        else:
            base_for_offset = base_price

        if base_for_offset is None or base_for_offset == 0:
            performance_map[day_key] = None
            continue

        perf_close_raw = (close_value - base_for_offset) / base_for_offset if close_value is not None else None
        perf_high_raw = (high_value - base_for_offset) / base_for_offset if high_value is not None else None
        perf_low_raw = (low_value - base_for_offset) / base_for_offset if low_value is not None else None

        perf_close_display = perf_close_raw * position_multiplier if perf_close_raw is not None else None
        perf_high_display = perf_high_raw * position_multiplier if perf_high_raw is not None else None
        perf_low_display = perf_low_raw * position_multiplier if perf_low_raw is not None else None

        if offset >= threshold_start and stop_offset is None:
            min_probe = perf_high_display if position_multiplier == -1 else perf_low_display
            max_probe = perf_low_display if position_multiplier == -1 else perf_high_display
            close_probe = perf_close_display
            min_candidates = [value for value in (min_probe, close_probe) if value is not None]
            max_candidates = [value for value in (max_probe, close_probe) if value is not None]
            min_check = min(min_candidates) if min_candidates else None
            max_check = max(max_candidates) if max_candidates else None

            if min_threshold is not None and min_check is not None and min_check <= min_threshold:
                stop_offset = offset
                stop_value_raw = min_threshold / position_multiplier if position_multiplier != 0 else None
            elif max_threshold is not None and max_check is not None and max_check >= max_threshold:
                stop_offset = offset
                stop_value_raw = max_threshold / position_multiplier if position_multiplier != 0 else None

        if stop_offset is not None and offset == stop_offset:
            performance_map[day_key] = stop_value_raw
        else:
            performance_map[day_key] = perf_close_raw

    return performance_map


def compute_previous_performance(
    open_map: Dict[str, Optional[float]],
    close_map: Dict[str, Optional[float]],
) -> Dict[str, Optional[float]]:
    performance_map: Dict[str, Optional[float]] = {}
    for offset in range(-14, 15):
        day_key = build_day_key(offset)
        prev_key = build_day_key(offset - 1) if offset > -14 else None
        prev_close = close_map.get(prev_key) if prev_key else None
        current_close = close_map.get(day_key)
        fallback_open = open_map.get(day_key)
        previous_base = prev_close if prev_close is not None else fallback_open
        if previous_base is None or previous_base == 0 or current_close is None:
            performance_map[day_key] = None
            continue
        performance_map[day_key] = (current_close - previous_base) / previous_base
    return performance_map


def compute_atr(
    cache: Dict[str, Any],
    entry_date: Optional[str],
    period: int,
    method: str,
) -> Optional[float]:
    if not entry_date or period <= 0:
        return None
    dates_asc = cache.get("dates_asc", [])
    index_by_date = cache.get("index_by_date", {})
    ohlc_by_date = cache.get("ohlc_by_date", {})

    entry_index = index_by_date.get(entry_date, -1)
    if entry_index < 1:
        return None

    start_index = entry_index - period + 1
    if start_index < 1:
        return None

    trs: List[float] = []
    for idx in range(start_index, entry_index + 1):
        date_key = dates_asc[idx]
        prev_date_key = dates_asc[idx - 1]
        ohlc = ohlc_by_date.get(date_key) or {}
        prev_ohlc = ohlc_by_date.get(prev_date_key) or {}
        high_value = to_finite_or_none(ohlc.get("high"))
        low_value = to_finite_or_none(ohlc.get("low"))
        prev_close = to_finite_or_none(prev_ohlc.get("close"))
        if high_value is None or low_value is None or prev_close is None:
            return None
        tr = max(
            high_value - low_value,
            abs(high_value - prev_close),
            abs(low_value - prev_close),
        )
        trs.append(tr)

    if not trs:
        return None

    method_norm = str(method or "wilder").lower()
    if method_norm == "sma":
        return sum(trs) / len(trs)

    atr_value = trs[0]
    for tr in trs[1:]:
        atr_value = ((atr_value * (period - 1)) + tr) / period
    return atr_value


def compute_trade_mdd(
    close_map: Dict[str, Optional[float]],
    entry_price: float,
    entry_offset: int,
    exit_offset: int,
    position_multiplier: int,
) -> Optional[float]:
    if entry_price <= 0:
        return None
    equity_series: List[float] = []
    for offset in range(entry_offset, exit_offset + 1):
        close_value = close_map.get(build_day_key(offset))
        if close_value is None or close_value <= 0:
            continue
        if position_multiplier == -1:
            equity = entry_price / close_value
        else:
            equity = close_value / entry_price
        equity_series.append(equity)

    if not equity_series:
        return None

    peak = equity_series[0]
    max_drawdown = 0.0
    for value in equity_series:
        if value > peak:
            peak = value
        drawdown = (peak - value) / peak if peak > 0 else 0.0
        if drawdown > max_drawdown:
            max_drawdown = drawdown
    return max_drawdown


def compute_strategy_metrics(
    daily_returns: List[float],
    annualization_days: int,
) -> StrategyMetrics:
    days = len(daily_returns)
    mean_daily = sum(daily_returns) / days if days > 0 else None
    variance = None
    if days > 1 and mean_daily is not None:
        variance = sum((value - mean_daily) ** 2 for value in daily_returns) / (days - 1)
    stdev = math.sqrt(variance) if variance is not None and variance >= 0 else None
    downside_values = [value for value in daily_returns if value < 0]
    downside_variance = None
    if len(downside_values) > 1:
        downside_mean = sum(downside_values) / len(downside_values)
        downside_variance = sum((value - downside_mean) ** 2 for value in downside_values) / (len(downside_values) - 1)
    downside_stdev = math.sqrt(downside_variance) if downside_variance is not None and downside_variance >= 0 else None

    sharpe = (mean_daily / stdev) if stdev and mean_daily is not None else None
    sortino = (mean_daily / downside_stdev) if downside_stdev and mean_daily is not None else None

    cumulative_log = 0.0
    equity = 1.0
    max_equity = 1.0
    max_drawdown = 0.0
    for value in daily_returns:
        cumulative_log += value
        equity = math.exp(cumulative_log)
        if equity > max_equity:
            max_equity = equity
        drawdown = (max_equity - equity) / max_equity if max_equity > 0 else 0.0
        if drawdown > max_drawdown:
            max_drawdown = drawdown

    cagr = None
    if days > 0 and annualization_days > 0:
        cagr = (equity ** (annualization_days / days)) - 1
    calmar = (cagr / max_drawdown) if cagr is not None and max_drawdown > 0 else None

    return StrategyMetrics(
        sharpe=sharpe,
        sortino=sortino,
        calmar=calmar,
        cagr=cagr,
        maxDrawdown=max_drawdown if days > 0 else None,
        meanDaily=mean_daily,
        stdevDaily=stdev,
        downsideStdevDaily=downside_stdev,
        days=days,
        totalReturn=equity - 1 if days > 0 else None,
    )


def normal_cdf(value: float) -> float:
    return 0.5 * (1 + math.erf(value / math.sqrt(2)))


def compute_best_window_summaries(
    rows: List[Dict[str, Any]],
    base_offset: int,
    base_field_norm: str,
    min_threshold_norm: Optional[float],
    max_threshold_norm: Optional[float],
    fee_rate: float,
    best_window_policy: Dict[str, Any],
    request_start: Optional[float] = None,
) -> Dict[str, BestWindowMode]:
    offset_meta = get_best_window_offsets(best_window_policy)
    offsets = offset_meta["offsets"]

    sums_designated = {offset: 0.0 for offset in offsets}
    counts_designated = {offset: 0 for offset in offsets}
    sums_previous = {offset: 0.0 for offset in offsets}
    counts_previous = {offset: 0 for offset in offsets}
    sumsq_designated = {offset: 0.0 for offset in offsets}
    sumsq_previous = {offset: 0.0 for offset in offsets}

    ticker_cache: Dict[str, Dict[str, Any]] = {}
    event_snapshots: List[Dict[str, Any]] = []
    for row in rows:
        ticker = row["ticker"]
        cache = ticker_cache.get(ticker)
        if cache is None:
            historical_rows = normalize_historical_price(row.get("historical_price"))
            cache = build_ticker_cache(historical_rows)
            ticker_cache[ticker] = cache

        maps = build_event_day_offset_maps(cache, row["event_date"])
        day_offset_price_trend_open = maps["day_offset_open"]
        day_offset_price_trend_high = maps["day_offset_high"]
        day_offset_price_trend_low = maps["day_offset_low"]
        day_offset_price_trend_close = maps["day_offset_close"]

        position_source = row["position_quantitative"] or row["position_qualitative"]
        position_multiplier = get_position_multiplier(position_source)
        event_snapshots.append({
            "cache": cache,
            "maps": maps,
            "position_multiplier": position_multiplier,
        })

        designated_performance = compute_designated_performance(
            day_offset_price_trend_open,
            day_offset_price_trend_high,
            day_offset_price_trend_low,
            day_offset_price_trend_close,
            base_offset,
            base_field_norm,
            min_threshold_norm,
            max_threshold_norm,
            position_multiplier,
        )
        previous_performance = compute_previous_performance(
            day_offset_price_trend_open,
            day_offset_price_trend_close,
        )

        for offset_value in offsets:
            day_key = build_day_key(offset_value)
            designated_value = designated_performance.get(day_key)
            if designated_value is not None:
                adjusted_value = designated_value * position_multiplier
                sums_designated[offset_value] += adjusted_value
                counts_designated[offset_value] += 1
                sumsq_designated[offset_value] += adjusted_value * adjusted_value
            previous_value = previous_performance.get(day_key)
            if previous_value is not None:
                adjusted_prev = previous_value * position_multiplier
                sums_previous[offset_value] += adjusted_prev
                counts_previous[offset_value] += 1
                sumsq_previous[offset_value] += adjusted_prev * adjusted_prev

    if request_start is not None:
        build_elapsed = time.perf_counter() - request_start
        logger.info(
            "action=get_events_history_best_window phase=maps_built "
            f"events={len(event_snapshots)} elapsed_ms={int(build_elapsed * 1000)}"
        )

    mean_designated = {
        offset: (sums_designated[offset] / counts_designated[offset]) if counts_designated[offset] > 0 else None
        for offset in offsets
    }
    mean_previous = {
        offset: (sums_previous[offset] / counts_previous[offset]) if counts_previous[offset] > 0 else None
        for offset in offsets
    }

    def compute_stddevs(
        sums: Dict[int, float],
        sumsquares: Dict[int, float],
        counts: Dict[int, int],
    ) -> Dict[int, Optional[float]]:
        result: Dict[int, Optional[float]] = {}
        for offset in offsets:
            count = counts[offset]
            if count < 2:
                result[offset] = None
                continue
            mean = sums[offset] / count
            variance = (sumsquares[offset] - (count * mean * mean)) / (count - 1)
            if variance < 0:
                variance = 0
            result[offset] = math.sqrt(variance)
        return result

    def compute_pvalues(
        means: Dict[int, Optional[float]],
        stddevs: Dict[int, Optional[float]],
        counts: Dict[int, int],
    ) -> Dict[int, Optional[float]]:
        result: Dict[int, Optional[float]] = {}
        for offset in offsets:
            mean = means.get(offset)
            stdev = stddevs.get(offset)
            count = counts.get(offset, 0)
            if mean is None or stdev is None or stdev == 0 or count < 2:
                result[offset] = None
                continue
            t_value = mean / (stdev / math.sqrt(count))
            p_value = 2 * (1 - normal_cdf(abs(t_value)))
            result[offset] = min(max(p_value, 0.0), 1.0)
        return result

    std_designated = compute_stddevs(sums_designated, sumsq_designated, counts_designated)
    std_previous = compute_stddevs(sums_previous, sumsq_previous, counts_previous)
    p_designated = compute_pvalues(mean_designated, std_designated, counts_designated)
    p_previous = compute_pvalues(mean_previous, std_previous, counts_previous)

    def build_offset_map(values: Dict[int, Optional[float]]) -> Dict[str, Optional[float]]:
        result: Dict[str, Optional[float]] = {}
        for offset, value in values.items():
            result[build_day_key(offset)] = value
        return result

    def build_count_map(values: Dict[int, int]) -> Dict[str, int]:
        result: Dict[str, int] = {}
        for offset, value in values.items():
            result[build_day_key(offset)] = value
        return result

    designated_summary = build_best_window(
        mean_designated,
        counts_designated,
        fee_rate,
        base_offset,
        mode="designated",
        policy=best_window_policy,
    )
    designated_summary.offsetAverages = build_offset_map(mean_designated)
    designated_summary.offsetCounts = build_count_map(counts_designated)
    designated_summary.offsetStdDevs = build_offset_map(std_designated)
    designated_summary.offsetPValues = build_offset_map(p_designated)
    previous_summary = build_best_window(
        mean_previous,
        counts_previous,
        fee_rate,
        base_offset=None,
        mode="previous",
        policy=best_window_policy,
    )
    previous_summary.offsetAverages = build_offset_map(mean_previous)
    previous_summary.offsetCounts = build_count_map(counts_previous)
    previous_summary.offsetStdDevs = build_offset_map(std_previous)
    previous_summary.offsetPValues = build_offset_map(p_previous)

    designated_percent = compute_best_window_backtest(
        event_snapshots,
        designated_summary.best,
        "designated",
        base_field_norm,
        min_threshold_norm,
        max_threshold_norm,
        best_window_policy,
        exit_mode_override="percent",
    )
    designated_atr = compute_best_window_backtest(
        event_snapshots,
        designated_summary.best,
        "designated",
        base_field_norm,
        min_threshold_norm,
        max_threshold_norm,
        best_window_policy,
        exit_mode_override="atr",
    )
    designated_summary.backtestModes = {
        "percent": designated_percent,
        "atr": designated_atr,
    }
    designated_summary.backtestModes = {
        key: value for key, value in designated_summary.backtestModes.items() if value is not None
    }

    previous_percent = compute_best_window_backtest(
        event_snapshots,
        previous_summary.best,
        "previous",
        base_field_norm,
        min_threshold_norm,
        max_threshold_norm,
        best_window_policy,
        exit_mode_override="percent",
    )
    previous_atr = compute_best_window_backtest(
        event_snapshots,
        previous_summary.best,
        "previous",
        base_field_norm,
        min_threshold_norm,
        max_threshold_norm,
        best_window_policy,
        exit_mode_override="atr",
    )
    previous_summary.backtestModes = {
        "percent": previous_percent,
        "atr": previous_atr,
    }
    previous_summary.backtestModes = {
        key: value for key, value in previous_summary.backtestModes.items() if value is not None
    }

    default_exit_mode = str(best_window_policy.get("backtest", {}).get("exit", {}).get("mode", "percent")).lower()
    designated_summary.backtest = designated_summary.backtestModes.get(default_exit_mode) or designated_percent
    previous_summary.backtest = previous_summary.backtestModes.get(default_exit_mode) or previous_percent

    return {
        "designated": designated_summary,
        "previous": previous_summary,
    }


def build_best_window(
    mean_by_offset: Dict[int, Optional[float]],
    count_by_offset: Dict[int, int],
    fee_rate: float,
    base_offset: Optional[int],
    mode: str,
    policy: Dict[str, Any],
) -> BestWindowMode:
    offset_meta = get_best_window_offsets(policy)
    offsets = offset_meta["offsets"]
    data_offsets_count = sum(1 for offset in offsets if mean_by_offset.get(offset) is not None)
    windows: List[BestWindowEntry] = []
    best_entry: Optional[BestWindowEntry] = None
    windows_count = 0
    mode_policy = policy.get(mode, {})
    total_return_formula = mode_policy.get("totalReturnFormula")
    avg_formula = mode_policy.get("avgFormula")
    avg_after_fee_formula = mode_policy.get("avgAfterFeeFormula")
    top_k = int(mode_policy.get("topK", 2) or 2)

    def resolve_value(value: Optional[float], fallback: float) -> float:
        checked = to_finite_or_none(value)
        return checked if checked is not None else fallback

    def score_value(value: Optional[float]) -> float:
        return value if value is not None else float("-inf")

    if mode == "previous":
        for start_idx, start_offset in enumerate(offsets):
            running_sum = 0.0
            running_count = 0
            length = 0
            running_compound = 1.0
            for end_offset in offsets[start_idx:]:
                mean_value = mean_by_offset.get(end_offset)
                count_value = count_by_offset.get(end_offset, 0)
                if mean_value is None:
                    break
                running_sum += mean_value
                running_count += count_value
                length += 1
                running_compound *= (1 + mean_value)
                windows_count += 1
                compound_return = running_compound - 1.0
                base_context = {
                    "mean_value": mean_value,
                    "running_sum": running_sum,
                    "running_compound": running_compound,
                    "compound_return": compound_return,
                    "running_count": running_count,
                    "length": length,
                    "hold": length,
                    "fee_rate": fee_rate,
                    "start_offset": start_offset,
                    "end_offset": end_offset,
                }
                total_return = resolve_value(
                    evaluate_best_window_formula(total_return_formula, base_context),
                    running_sum,
                )
                total_after_fee = total_return - fee_rate
                avg = resolve_value(
                    evaluate_best_window_formula(avg_formula, {**base_context, "total_return": total_return}),
                    running_sum / length,
                )
                avg_after_fee = resolve_value(
                    evaluate_best_window_formula(
                        avg_after_fee_formula,
                        {**base_context, "avg": avg, "total_return": total_return, "total_after_fee": total_after_fee},
                    ),
                    total_after_fee / length,
                )
                entry = BestWindowEntry(
                    startOffset=start_offset,
                    endOffset=end_offset,
                    avg=avg,
                    avgAfterFee=avg_after_fee,
                    totalReturn=total_return,
                    totalAfterFee=total_after_fee,
                    length=length,
                    avgRows=(running_count / length) if length else None,
                )
                windows.append(entry)
                if best_entry is None or score_value(entry.avgAfterFee) > score_value(best_entry.avgAfterFee):
                    best_entry = entry
    else:
        if base_offset is None or base_offset not in offsets:
            return BestWindowMode(
                best=None,
                topWindows=[],
                windowsCount=0,
                dataOffsetsCount=data_offsets_count,
                totalOffsets=len(offsets),
            )
        base_index = offsets.index(base_offset)
        for end_offset in offsets[base_index + 1:]:
            mean_value = mean_by_offset.get(end_offset)
            if mean_value is None:
                break
            hold = end_offset - base_offset
            if hold <= 0:
                continue
            windows_count += 1
            base_context = {
                "mean_value": mean_value,
                "hold": hold,
                "fee_rate": fee_rate,
                "start_offset": base_offset,
                "end_offset": end_offset,
                "count_value": count_by_offset.get(end_offset, 0),
            }
            total_return = resolve_value(
                evaluate_best_window_formula(total_return_formula, base_context),
                mean_value,
            )
            total_after_fee = total_return - fee_rate
            avg = resolve_value(
                evaluate_best_window_formula(avg_formula, {**base_context, "total_return": total_return}),
                mean_value / hold,
            )
            avg_after_fee = resolve_value(
                evaluate_best_window_formula(
                    avg_after_fee_formula,
                    {**base_context, "avg": avg, "total_return": total_return, "total_after_fee": total_after_fee},
                ),
                total_after_fee / hold,
            )
            entry = BestWindowEntry(
                startOffset=base_offset,
                endOffset=end_offset,
                avg=avg,
                avgAfterFee=avg_after_fee,
                totalReturn=total_return,
                totalAfterFee=total_after_fee,
                length=hold,
                avgRows=float(count_by_offset.get(end_offset, 0)),
            )
            windows.append(entry)
            if best_entry is None or score_value(entry.avgAfterFee) > score_value(best_entry.avgAfterFee):
                best_entry = entry

    top_windows = sorted(windows, key=lambda entry: score_value(entry.avgAfterFee), reverse=True)[:top_k]
    return BestWindowMode(
        best=best_entry,
        topWindows=top_windows,
        windowsCount=windows_count,
        dataOffsetsCount=data_offsets_count,
        totalOffsets=len(offsets),
    )


def compute_best_window_backtest(
    events: List[Dict[str, Any]],
    best_entry: Optional[BestWindowEntry],
    mode: str,
    base_field: str,
    min_threshold: Optional[float],
    max_threshold: Optional[float],
    policy: Dict[str, Any],
    exit_mode_override: Optional[str] = None,
) -> Optional[BestWindowBacktestSummary]:
    if not best_entry:
        return None

    entry_offset = best_entry.startOffset
    exit_offset = best_entry.endOffset
    hold_days = best_entry.length
    if hold_days <= 0:
        return None
    mode_norm = str(mode or "designated").lower()

    backtest_policy = policy.get("backtest", {}) if isinstance(policy, dict) else {}
    atr_policy = backtest_policy.get("atr", {})
    exit_policy = backtest_policy.get("exit", {})
    risk_policy = backtest_policy.get("risk", {})
    strategy_policy = backtest_policy.get("strategy", {})
    atr_period = int(atr_policy.get("period", 14))
    atr_method = atr_policy.get("method", "wilder")
    exit_mode = str(exit_policy.get("mode", "percent")).lower()
    if exit_mode_override:
        exit_mode = str(exit_mode_override).lower()
    stop_loss_atr = float(exit_policy.get("stopLossAtr", 1.0))
    take_profit_atr = float(exit_policy.get("takeProfitAtr", 2.0))
    risk_lambda = float(risk_policy.get("lambda", 1.0))
    daily_return_mode = str(strategy_policy.get("dailyReturnMode", "spread")).lower()
    annualization_days = int(strategy_policy.get("annualizationDays", 252))

    total_log_returns = []
    total_daily_log_returns = []
    total_cagr_daily = []
    total_mdd = []
    total_atr = []
    total_risk_penalty = []
    total_scores = []
    exit_reason_counts: Dict[str, int] = {"stop": 0, "take": 0, "hold": 0, "unknown": 0}
    daily_return_by_date: Dict[str, float] = {}

    for event in events:
        cache = event.get("cache")
        maps = event.get("maps", {})
        close_map = maps.get("day_offset_close", {})
        high_map = maps.get("day_offset_high", {})
        low_map = maps.get("day_offset_low", {})
        target_dates = maps.get("day_offset_target_dates", {})
        position_multiplier = event.get("position_multiplier", 1)

        if mode_norm == "previous":
            entry_offset_effective = entry_offset - 1
            entry_map = close_map
            if entry_offset_effective < -14:
                continue
        else:
            entry_offset_effective = entry_offset
            entry_map = maps.get(f"day_offset_{base_field}", {}) or close_map

        entry_key = build_day_key(entry_offset_effective)
        entry_price = entry_map.get(entry_key)
        entry_date = target_dates.get(entry_key)
        if entry_price is None or entry_price == 0 or entry_date is None:
            continue

        exit_reason = "hold"
        actual_exit_offset = exit_offset
        atr_value = compute_atr(cache, entry_date, atr_period, atr_method) if cache else None
        loop_start = entry_offset_effective + 1 if mode_norm == "previous" else entry_offset_effective
        for offset in range(loop_start, exit_offset + 1):
            day_key = build_day_key(offset)
            high_value = high_map.get(day_key)
            low_value = low_map.get(day_key)
            close_value = close_map.get(day_key)
            if close_value is None:
                continue

            high_return = ((high_value - entry_price) / entry_price) if high_value is not None else None
            low_return = ((low_value - entry_price) / entry_price) if low_value is not None else None
            close_return = (close_value - entry_price) / entry_price

            high_display = high_return * position_multiplier if high_return is not None else None
            low_display = low_return * position_multiplier if low_return is not None else None
            close_display = close_return * position_multiplier

            min_probe = high_display if position_multiplier == -1 else low_display
            max_probe = low_display if position_multiplier == -1 else high_display
            min_candidates = [value for value in (min_probe, close_display) if value is not None]
            max_candidates = [value for value in (max_probe, close_display) if value is not None]
            min_check = min(min_candidates) if min_candidates else None
            max_check = max(max_candidates) if max_candidates else None

            if exit_mode == "atr" and atr_value is not None:
                stop_threshold = -stop_loss_atr * (atr_value / entry_price)
                take_threshold = take_profit_atr * (atr_value / entry_price)
                if min_check is not None and min_check <= stop_threshold:
                    exit_reason = "stop"
                    actual_exit_offset = offset
                    break
                if max_check is not None and max_check >= take_threshold:
                    exit_reason = "take"
                    actual_exit_offset = offset
                    break
            else:
                if min_threshold is not None and min_check is not None and min_check <= min_threshold:
                    exit_reason = "stop"
                    actual_exit_offset = offset
                    break
                if max_threshold is not None and max_check is not None and max_check >= max_threshold:
                    exit_reason = "take"
                    actual_exit_offset = offset
                    break

        exit_key = build_day_key(actual_exit_offset)
        exit_price = close_map.get(exit_key)
        exit_date = target_dates.get(exit_key)
        if exit_price is None or exit_price == 0 or exit_date is None:
            exit_reason = "unknown"
            continue

        actual_hold_days = actual_exit_offset - entry_offset_effective
        if actual_hold_days <= 0:
            exit_reason_counts["unknown"] += 1
            continue

        adj_ratio = exit_price / entry_price
        if position_multiplier == -1:
            adj_ratio = entry_price / exit_price
        log_return = math.log(adj_ratio) if adj_ratio > 0 else None
        if log_return is None:
            exit_reason_counts["unknown"] += 1
            continue

        daily_log_return = log_return / actual_hold_days
        cagr_daily = (adj_ratio ** (1 / actual_hold_days)) - 1

        mdd_value = compute_trade_mdd(
            close_map,
            entry_price,
            entry_offset,
            actual_exit_offset,
            position_multiplier,
        )
        risk_penalty = (mdd_value / atr_value) if mdd_value is not None and atr_value else None
        score_value = (
            daily_log_return - (risk_lambda * risk_penalty)
            if risk_penalty is not None
            else daily_log_return
        )

        total_log_returns.append(log_return)
        total_daily_log_returns.append(daily_log_return)
        total_cagr_daily.append(cagr_daily)
        if mdd_value is not None:
            total_mdd.append(mdd_value)
        if atr_value is not None:
            total_atr.append(atr_value)
        if risk_penalty is not None:
            total_risk_penalty.append(risk_penalty)
        if score_value is not None:
            total_scores.append(score_value)

        exit_reason_counts[exit_reason] = exit_reason_counts.get(exit_reason, 0) + 1

        if daily_return_mode == "lump":
            daily_return_by_date[exit_date] = daily_return_by_date.get(exit_date, 0.0) + log_return
        else:
            for offset in range(entry_offset + 1, actual_exit_offset + 1):
                current_key = build_day_key(offset)
                prev_key = build_day_key(offset - 1)
                current_close = close_map.get(current_key)
                prev_close = close_map.get(prev_key)
                current_date = target_dates.get(current_key)
                if not current_date or current_close is None or prev_close is None or prev_close <= 0:
                    continue
                daily_ratio = current_close / prev_close
                if position_multiplier == -1:
                    daily_ratio = prev_close / current_close
                daily_log = math.log(daily_ratio) if daily_ratio > 0 else None
                if daily_log is None:
                    continue
                daily_return_by_date[current_date] = daily_return_by_date.get(current_date, 0.0) + daily_log

    daily_series = [value for _, value in sorted(daily_return_by_date.items())]
    strategy = compute_strategy_metrics(daily_series, annualization_days) if daily_series else None

    def safe_avg(values: List[float]) -> Optional[float]:
        return sum(values) / len(values) if values else None

    return BestWindowBacktestSummary(
        entryOffset=entry_offset,
        entryField=base_field,
        holdDays=hold_days,
        exitOffset=exit_offset,
        exitMode=exit_mode,
        trades=len(total_log_returns),
        avgLogReturn=safe_avg(total_log_returns),
        avgDailyLogReturn=safe_avg(total_daily_log_returns),
        avgCagrDaily=safe_avg(total_cagr_daily),
        avgMdd=safe_avg(total_mdd),
        avgAtr=safe_avg(total_atr),
        avgRiskPenalty=safe_avg(total_risk_penalty),
        avgScore=safe_avg(total_scores),
        exitReasonCounts=exit_reason_counts,
        strategy=strategy,
    )


@router.get("/eventsHistory", response_model=EventsHistoryResponse)
async def get_events_history(
    user: UserContext = Depends(require_admin),
    page: int = Query(1, ge=1, description="Page number starting from 1"),
    pageSize: int = Query(100000, ge=1, le=100000, description="Number of rows per page"),
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
    base_offset: int = Query(0, alias="baseOffset", description="Base day offset for performance"),
    base_field: str = Query("close", alias="baseField", description="Base OHLC field"),
    min_threshold: Optional[float] = Query(None, alias="minThreshold", description="Stop loss threshold (%)"),
    max_threshold: Optional[float] = Query(None, alias="maxThreshold", description="Profit target threshold (%)"),
):
    logger.info(
        "action=get_events_history phase=request_received "
        f"page={page} pageSize={pageSize} sortBy={sortBy} sortOrder={sortOrder} "
        f"ticker={ticker} sector={sector} industry={industry} source={source} condition={condition} "
        f"event_date_from={event_date_from} event_date_to={event_date_to}"
    )
    try:
        where_conditions = []
        params = []
        param_count = 1

        if ticker:
            if ticker.startswith('='):
                where_conditions.append(f"e.ticker = ${param_count}")
                params.append(ticker[1:])
            else:
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

        order_clause = "e.id ASC"
        if sortBy and sortOrder:
            if sortBy not in allowed_sort_columns:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid sort column. Allowed: {', '.join(allowed_sort_columns)}",
                )
            order_clause = f"e.{sortBy} {sortOrder.upper()}"

        offset = (page - 1) * pageSize
        pool = await db_pool.get_pool()
        async with pool.acquire() as conn:
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
                    q.historical_price
                FROM txn_events e
                LEFT JOIN config_lv3_quantitatives q ON (
                    e.ticker = q.ticker
                )
                WHERE {where_clause}
                ORDER BY {order_clause}
                LIMIT {pageSize}
                OFFSET {offset}
            """
            rows = await conn.fetch(data_query, *params)

        min_threshold_norm = min_threshold / 100 if min_threshold is not None else None
        max_threshold_norm = max_threshold / 100 if max_threshold is not None else None

        ticker_cache: Dict[str, Dict[str, Any]] = {}
        data: List[EventsHistoryRow] = []
        for row in rows:
            ticker = row["ticker"]
            cache = ticker_cache.get(ticker)
            if cache is None:
                historical_rows = normalize_historical_price(row.get("historical_price"))
                cache = build_ticker_cache(historical_rows)
                ticker_cache[ticker] = cache

            maps = build_event_day_offset_maps(cache, row["event_date"])
            day_offset_target_dates = maps["day_offset_target_dates"]
            day_offset_price_trend_open = maps["day_offset_open"]
            day_offset_price_trend_high = maps["day_offset_high"]
            day_offset_price_trend_low = maps["day_offset_low"]
            day_offset_price_trend_close = maps["day_offset_close"]
            day_offset_price_trend = maps["day_offset_price_trend"]

            position_source = row["position_quantitative"] or row["position_qualitative"]
            position_multiplier = get_position_multiplier(position_source)

            designated_performance = compute_designated_performance(
                day_offset_price_trend_open,
                day_offset_price_trend_high,
                day_offset_price_trend_low,
                day_offset_price_trend_close,
                base_offset,
                base_field,
                min_threshold_norm,
                max_threshold_norm,
                position_multiplier,
            )
            previous_performance = compute_previous_performance(
                day_offset_price_trend_open,
                day_offset_price_trend_close,
            )

            wts = None
            best_value = None
            for offset_value in range(1, 15):
                key = build_day_key(offset_value)
                raw_value = designated_performance.get(key)
                if raw_value is None:
                    continue
                display_value = raw_value * position_multiplier
                if best_value is None or display_value > best_value:
                    best_value = display_value
                    wts = offset_value

            row_payload = EventsHistoryRow(
                id=row["id"],
                ticker=row["ticker"],
                event_date=row["event_date"],
                sector=row["sector"],
                industry=row["industry"],
                source=row["source"],
                source_id=row["source_id"],
                position_quantitative=row["position_quantitative"],
                disparity_quantitative=row["disparity_quantitative"],
                position_qualitative=row["position_qualitative"],
                disparity_qualitative=row["disparity_qualitative"],
                condition=row["condition"],
                position=position_source,
                wts=wts,
                day_offset_performance=designated_performance,
                day_offset_performance_previous=previous_performance,
                day_offset_price_trend=day_offset_price_trend,
                day_offset_price_trend_open=day_offset_price_trend_open,
                day_offset_price_trend_high=day_offset_price_trend_high,
                day_offset_price_trend_low=day_offset_price_trend_low,
                day_offset_price_trend_close=day_offset_price_trend_close,
                day_offset_target_dates=day_offset_target_dates,
                d_neg14=designated_performance.get("d_neg14"),
                d_neg13=designated_performance.get("d_neg13"),
                d_neg12=designated_performance.get("d_neg12"),
                d_neg11=designated_performance.get("d_neg11"),
                d_neg10=designated_performance.get("d_neg10"),
                d_neg9=designated_performance.get("d_neg9"),
                d_neg8=designated_performance.get("d_neg8"),
                d_neg7=designated_performance.get("d_neg7"),
                d_neg6=designated_performance.get("d_neg6"),
                d_neg5=designated_performance.get("d_neg5"),
                d_neg4=designated_performance.get("d_neg4"),
                d_neg3=designated_performance.get("d_neg3"),
                d_neg2=designated_performance.get("d_neg2"),
                d_neg1=designated_performance.get("d_neg1"),
                d_0=designated_performance.get("d_0"),
                d_pos1=designated_performance.get("d_pos1"),
                d_pos2=designated_performance.get("d_pos2"),
                d_pos3=designated_performance.get("d_pos3"),
                d_pos4=designated_performance.get("d_pos4"),
                d_pos5=designated_performance.get("d_pos5"),
                d_pos6=designated_performance.get("d_pos6"),
                d_pos7=designated_performance.get("d_pos7"),
                d_pos8=designated_performance.get("d_pos8"),
                d_pos9=designated_performance.get("d_pos9"),
                d_pos10=designated_performance.get("d_pos10"),
                d_pos11=designated_performance.get("d_pos11"),
                d_pos12=designated_performance.get("d_pos12"),
                d_pos13=designated_performance.get("d_pos13"),
                d_pos14=designated_performance.get("d_pos14"),
            )
            data.append(row_payload)

        return EventsHistoryResponse(
            data=data,
            total=len(data),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"action=get_events_history status=error error={str(e)}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=f"Failed to fetch events history: {str(e)}")


@router.get("/eventsHistory/bestWindow", response_model=EventsHistoryBestWindowResponse)
async def get_events_history_best_window(
    user: UserContext = Depends(require_admin),
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
    base_offset: int = Query(0, alias="baseOffset", description="Base day offset for performance"),
    base_field: str = Query("close", alias="baseField", description="Base OHLC field"),
    min_threshold: Optional[float] = Query(None, alias="minThreshold", description="Stop loss threshold (%)"),
    max_threshold: Optional[float] = Query(None, alias="maxThreshold", description="Profit target threshold (%)"),
    fee_percent: Optional[float] = Query(0, alias="feePercent", description="Fee percent to subtract"),
):
    logger.info(
        "action=get_events_history_best_window phase=request_received "
        f"ticker={ticker} sector={sector} industry={industry} source={source} condition={condition} "
        f"event_date_from={event_date_from} event_date_to={event_date_to}"
    )
    try:
        request_start = time.perf_counter()
        where_conditions = []
        params = []
        param_count = 1

        if ticker:
            if ticker.startswith('='):
                where_conditions.append(f"e.ticker = ${param_count}")
                params.append(ticker[1:])
            else:
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
        pool = await db_pool.get_pool()
        async with pool.acquire() as conn:
            query_start = time.perf_counter()
            data_query = f"""
                SELECT
                    e.ticker,
                    TO_CHAR(e.event_date, 'YYYY-MM-DD') as event_date,
                    e.position_quantitative::text as position_quantitative,
                    e.position_qualitative::text as position_qualitative,
                    q.historical_price
                FROM txn_events e
                LEFT JOIN config_lv3_quantitatives q ON (
                    e.ticker = q.ticker
                )
                WHERE {where_clause}
            """
            rows = await conn.fetch(data_query, *params)
            query_elapsed = time.perf_counter() - query_start
            logger.info(
                "action=get_events_history_best_window phase=db_fetch_complete "
                f"rows={len(rows)} elapsed_ms={int(query_elapsed * 1000)}"
            )
        fetch_elapsed = time.perf_counter() - request_start
        logger.info(
            "action=get_events_history_best_window phase=post_fetch "
            f"elapsed_ms={int(fetch_elapsed * 1000)}"
        )

        min_threshold_norm = min_threshold / 100 if min_threshold is not None else None
        max_threshold_norm = max_threshold / 100 if max_threshold is not None else None
        fee_rate = (fee_percent or 0) / 100
        base_field_norm = (base_field or "close").lower()
        best_window_policy = await load_best_window_policy(pool)
        summaries = await asyncio.to_thread(
            compute_best_window_summaries,
            rows,
            base_offset,
            base_field_norm,
            min_threshold_norm,
            max_threshold_norm,
            fee_rate,
            best_window_policy,
            request_start,
        )
        designated_summary = summaries["designated"]
        previous_summary = summaries["previous"]

        total_elapsed = time.perf_counter() - request_start
        logger.info(
            "action=get_events_history_best_window status=success "
            f"elapsed_ms={int(total_elapsed * 1000)}"
        )

        return EventsHistoryBestWindowResponse(
            designated=designated_summary,
            previous=previous_summary,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"action=get_events_history_best_window status=error error={str(e)}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=f"Failed to fetch events history best window: {str(e)}")


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
    - Day offset values computed from config_lv3_quantitatives.historical_price
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

                # Get data without txn_price_trend (use historical_price from config_lv3_quantitatives)
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
                        t.notes
                    FROM txn_trades t
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
                        ROW_NUMBER() OVER (ORDER BY {order_clause}) AS rn
                    FROM txn_trades t
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

            tickers = sorted({row["ticker"] for row in rows if row["ticker"]})
            ticker_cache: Dict[str, Dict[str, Any]] = {}
            if tickers:
                historical_rows = await conn.fetch(
                    """
                    SELECT ticker, historical_price
                    FROM config_lv3_quantitatives
                    WHERE ticker = ANY($1)
                    """,
                    tickers,
                )
                for historical_row in historical_rows:
                    historical_price = normalize_historical_price(historical_row["historical_price"])
                    ticker_cache[historical_row["ticker"]] = build_ticker_cache(historical_price)

            logger.debug(
                f"action=get_trades phase=query_complete "
                f"rows_fetched={len(rows)} page={page} pageSize={pageSize}"
            )

            # Process rows and compute day offsets using historical_price
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

                    performance_day_values: Dict[int, Optional[float]] = {}
                    price_trend_day_values: Dict[int, Optional[float]] = {}
                    display_day_values: Dict[int, Optional[float]] = {}
                    cache = ticker_cache.get(row["ticker"])
                    if cache:
                        maps = build_event_day_offset_maps(cache, trade_date_str)
                        close_map = maps["day_offset_close"]
                        price_trend_map = maps["day_offset_price_trend"]
                        target_dates = maps["day_offset_target_dates"]

                        base_close = close_map.get("d_neg14")
                        if base_close is None or base_close == 0:
                            base_close = None

                        for offset in range(-14, 15):
                            day_key = build_day_key(offset)
                            close_value = close_map.get(day_key)
                            if base_close is None or close_value is None:
                                performance_day_values[offset] = None
                            else:
                                performance_day_values[offset] = (close_value - base_close) / base_close
                            price_trend_day_values[offset] = price_trend_map.get(day_key)
                            if day_offset_mode == "price_trend":
                                display_day_values[offset] = price_trend_day_values[offset]
                            else:
                                display_day_values[offset] = performance_day_values[offset]
                    else:
                        target_dates = {build_day_key(offset): None for offset in range(-14, 15)}
                        for offset in range(-14, 15):
                            performance_day_values[offset] = None
                            price_trend_day_values[offset] = None
                            display_day_values[offset] = None

                    def build_day_offset_map(day_values: Dict[int, Optional[float]]) -> Dict[str, Optional[float]]:
                        result = {}
                        for offset in range(-14, 15):
                            if offset == 0:
                                key = "d_0"
                            else:
                                key = f"d_neg{abs(offset)}" if offset < 0 else f"d_pos{offset}"
                            result[key] = day_values.get(offset)
                        return result

                    target_dates = target_dates or {build_day_key(offset): None for offset in range(-14, 15)}

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
