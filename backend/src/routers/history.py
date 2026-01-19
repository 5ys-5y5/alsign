"""Router for history endpoints to fetch raw trades and historical prices."""

import logging
from typing import List, Optional, Dict, Any
from datetime import date

from fastapi import APIRouter, HTTPException, Query, Body, Depends
from pydantic import BaseModel, Field

from ..database.connection import db_pool
from ..auth import get_current_user, UserContext

logger = logging.getLogger("alsign")

router = APIRouter(prefix="/history", tags=["History"])


class HistoryTradeRow(BaseModel):
    """Response model for a raw trade row without precomputed metrics."""

    ticker: Optional[str]
    trade_date: Optional[str]
    model: Optional[str]
    source: Optional[str]
    position: Optional[str]
    entry_price: Optional[float]
    exit_price: Optional[float]
    quantity: Optional[int]
    notes: Optional[str]


class HistoryTradesResponse(BaseModel):
    """Response model for history trades with pagination."""

    data: List[HistoryTradeRow]
    total: int
    page: int
    pageSize: int


class HistoricalPriceRequest(BaseModel):
    """Request payload for historical price fetch."""

    tickers: List[str] = Field(default_factory=list)


class HistoricalPriceResponse(BaseModel):
    """Response model for historical prices by ticker."""

    data: Dict[str, Any]
    missing: List[str]


@router.get("/trades", response_model=HistoryTradesResponse)
async def get_history_trades(
    user: UserContext = Depends(get_current_user),
    page: int = Query(1, ge=1, description="Page number starting from 1"),
    pageSize: int = Query(1000, ge=1, le=2000, description="Number of rows per page"),
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
    Get trades from txn_trades without precomputed price trend data.
    """
    logger.info(
        "action=get_history_trades phase=request_received "
        f"page={page} pageSize={pageSize} sortBy={sortBy} sortOrder={sortOrder} "
        f"ticker={ticker} model={model} source={source} position={position}"
    )
    try:
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

        allowed_sort_columns = [
            "ticker",
            "trade_date",
            "model",
            "source",
            "position",
            "entry_price",
            "exit_price",
            "quantity",
            "notes",
        ]
        order_clause = "t.trade_date DESC"
        if sortBy and sortOrder:
            if sortBy not in allowed_sort_columns:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid sort column. Allowed: {', '.join(allowed_sort_columns)}",
                )
            order_clause = f"t.{sortBy} {sortOrder.upper()}"

        offset = (page - 1) * pageSize

        pool = await db_pool.get_pool()
        async with pool.acquire() as conn:
            count_query = f"SELECT COUNT(*) FROM txn_trades t WHERE {where_clause}"
            total = await conn.fetchval(count_query, *params)

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

        data = [
            HistoryTradeRow(
                ticker=row["ticker"],
                trade_date=row["trade_date"],
                model=row["model"],
                source=row["source"],
                position=row["position"],
                entry_price=row["entry_price"],
                exit_price=row["exit_price"],
                quantity=row["quantity"],
                notes=row["notes"],
            )
            for row in rows
        ]

        return HistoryTradesResponse(
            data=data,
            total=total or 0,
            page=page,
            pageSize=pageSize,
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            f"action=get_history_trades status=error error={str(exc)}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=f"Failed to fetch history trades: {str(exc)}")


@router.post("/historical-prices", response_model=HistoricalPriceResponse)
async def get_historical_prices(
    payload: HistoricalPriceRequest = Body(...),
    user: UserContext = Depends(get_current_user),
):
    """
    Fetch historical_price from config_lv3_quantitatives for a list of tickers.
    """
    tickers = [ticker for ticker in payload.tickers if ticker]
    unique_tickers = sorted(set(tickers))
    if not unique_tickers:
        return HistoricalPriceResponse(data={}, missing=[])

    try:
        pool = await db_pool.get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT ticker, historical_price
                FROM config_lv3_quantitatives
                WHERE ticker = ANY($1)
                """,
                unique_tickers,
            )

        data = {}
        for row in rows:
            data[row["ticker"]] = row["historical_price"]

        missing = [ticker for ticker in unique_tickers if ticker not in data]
        return HistoricalPriceResponse(data=data, missing=missing)

    except Exception as exc:
        logger.error(
            f"action=get_historical_prices status=error error={str(exc)}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=f"Failed to fetch historical prices: {str(exc)}")
