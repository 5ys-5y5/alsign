"""
Trades Router

Handles trade record management for performance tracking.
"""
from fastapi import APIRouter, Request, Response, HTTPException
import uuid
import logging

from ..database.connection import db_pool
from ..models.request_models import BulkTradesRequest


router = APIRouter(tags=["Trades"])
logger = logging.getLogger("alsign")


@router.post("/trades")
async def bulk_insert_trades(
    request: Request,
    response: Response,
    body: BulkTradesRequest
):
    """
    Bulk insert trade records into txn_trades table.

    Inserts multiple trade records in a single transaction using PostgreSQL UNNEST.
    Unique constraint: (ticker, trade_date, model)
    On conflict, updates the existing record with new values.

    Args:
        body: BulkTradesRequest containing list of TradeRecord objects

    Returns:
        Dict with inserted/updated counts

    Raises:
        HTTPException: 400 for validation errors, 500 for database errors
    """
    # Get request ID from middleware
    req_id = request.state.reqId if hasattr(request.state, 'reqId') else str(uuid.uuid4())

    if not body.trades:
        raise HTTPException(status_code=400, detail="No trades provided")

    try:
        # Prepare batch data
        tickers = []
        trade_dates = []
        models = []
        sources = []
        positions = []
        entry_prices = []
        exit_prices = []
        quantities = []
        notes_list = []

        for trade in body.trades:
            tickers.append(trade.ticker.upper())
            trade_dates.append(trade.trade_date)
            models.append(trade.model)
            sources.append(trade.source)
            positions.append(trade.position)
            entry_prices.append(trade.entry_price)
            exit_prices.append(trade.exit_price)
            quantities.append(trade.quantity)
            notes_list.append(trade.notes)

        # Bulk UPSERT using PostgreSQL UNNEST
        query = """
            WITH batch_data AS (
                SELECT * FROM UNNEST(
                    $1::text[],
                    $2::date[],
                    $3::text[],
                    $4::text[],
                    $5::text[],
                    $6::numeric[],
                    $7::numeric[],
                    $8::integer[],
                    $9::text[]
                ) AS t(
                    ticker,
                    trade_date,
                    model,
                    source,
                    position,
                    entry_price,
                    exit_price,
                    quantity,
                    notes
                )
            )
            INSERT INTO public.txn_trades (
                ticker,
                trade_date,
                model,
                source,
                position,
                entry_price,
                exit_price,
                quantity,
                notes
            )
            SELECT
                ticker,
                trade_date,
                model,
                source,
                position,
                entry_price,
                exit_price,
                quantity,
                notes
            FROM batch_data
            ON CONFLICT (ticker, trade_date, model)
            DO UPDATE SET
                source = EXCLUDED.source,
                position = EXCLUDED.position,
                entry_price = EXCLUDED.entry_price,
                exit_price = EXCLUDED.exit_price,
                quantity = EXCLUDED.quantity,
                notes = EXCLUDED.notes,
                updated_at = CURRENT_TIMESTAMP
            RETURNING ticker, trade_date, model
        """

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                query,
                tickers,
                trade_dates,
                models,
                sources,
                positions,
                entry_prices,
                exit_prices,
                quantities,
                notes_list
            )

        inserted_count = len(rows)

        logger.info(f"[POST /trades] Processed {inserted_count} trade records")

        return {
            "reqId": req_id,
            "endpoint": "POST /trades",
            "summary": {
                "processed": inserted_count,
                "total": len(body.trades)
            },
            "trades": [
                {
                    "ticker": row["ticker"],
                    "trade_date": row["trade_date"].isoformat(),
                    "model": row["model"]
                }
                for row in rows
            ]
        }

    except Exception as e:
        logger.error(f"[POST /trades] Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to insert trades: {str(e)}")
