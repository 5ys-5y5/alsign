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
    On conflict, existing records are skipped and reported as failures.

    Args:
        body: BulkTradesRequest containing list of TradeRecord objects

    Returns:
        Dict with per-record success/failure and summary counts

    Raises:
        HTTPException: 400 for validation errors, 500 for database errors
    """
    # Get request ID from middleware
    req_id = request.state.reqId if hasattr(request.state, 'reqId') else str(uuid.uuid4())

    if not body.trades:
        raise HTTPException(status_code=400, detail="No trades provided")

    try:
        # Normalize request payload and detect duplicates in the same batch
        normalized_trades = []
        seen_keys = set()
        duplicate_failures = []

        for trade in body.trades:
            ticker = trade.ticker.upper()
            key = (ticker, trade.trade_date, trade.model)

            if key in seen_keys:
                duplicate_failures.append({
                    "ticker": ticker,
                    "trade_date": trade.trade_date.isoformat(),
                    "model": trade.model,
                    "reason": "중복으로 인해 추가가 불가능"
                })
                continue

            seen_keys.add(key)
            normalized_trades.append({
                "ticker": ticker,
                "trade_date": trade.trade_date,
                "model": trade.model,
                "source": trade.source,
                "position": trade.position,
                "entry_price": trade.entry_price,
                "exit_price": trade.exit_price,
                "quantity": trade.quantity,
                "notes": trade.notes,
            })

        if not normalized_trades:
            summary = {
                "total": len(body.trades),
                "success": 0,
                "failed": len(duplicate_failures),
                "already_exists": 0,
                "duplicates": len(duplicate_failures),
                "success_items": [],
                "fail_items": duplicate_failures,
            }
            logger.info(f"[POST /trades] Summary: {summary}")
            return {
                "reqId": req_id,
                "endpoint": "POST /trades",
                "summary": summary,
                "success": [],
                "fail": duplicate_failures,
            }

        # Prepare batch data for existence check
        tickers = [trade["ticker"] for trade in normalized_trades]
        trade_dates = [trade["trade_date"] for trade in normalized_trades]
        models = [trade["model"] for trade in normalized_trades]
        sources = [trade["source"] for trade in normalized_trades]
        positions = [trade["position"] for trade in normalized_trades]
        entry_prices = [trade["entry_price"] for trade in normalized_trades]
        exit_prices = [trade["exit_price"] for trade in normalized_trades]
        quantities = [trade["quantity"] for trade in normalized_trades]
        notes_list = [trade["notes"] for trade in normalized_trades]

        existing_failures = []
        existing_keys = set()

        async with db_pool.acquire() as conn:
            existing_query = '''
                WITH batch_data AS (
                    SELECT * FROM UNNEST(
                        $1::text[],
                        $2::date[],
                        $3::text[]
                    ) AS t(
                        ticker,
                        trade_date,
                        model
                    )
                )
                SELECT t.ticker, t.trade_date, t.model
                FROM batch_data t
                INNER JOIN public.txn_trades x
                  ON x.ticker = t.ticker
                 AND x.trade_date = t.trade_date
                 AND x.model = t.model
            '''
            existing_rows = await conn.fetch(existing_query, tickers, trade_dates, models)

            for row in existing_rows:
                key = (row["ticker"], row["trade_date"], row["model"])
                existing_keys.add(key)
                existing_failures.append({
                    "ticker": row["ticker"],
                    "trade_date": row["trade_date"].isoformat(),
                    "model": row["model"],
                    "reason": "이미 존재함"
                })

            to_insert = [
                trade for trade in normalized_trades
                if (trade["ticker"], trade["trade_date"], trade["model"]) not in existing_keys
            ]

            inserted_rows = []
            if to_insert:
                insert_query = '''
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
                    DO NOTHING
                    RETURNING ticker, trade_date, model
                '''

                insert_rows = [trade["ticker"] for trade in to_insert]
                insert_dates = [trade["trade_date"] for trade in to_insert]
                insert_models = [trade["model"] for trade in to_insert]
                insert_sources = [trade["source"] for trade in to_insert]
                insert_positions = [trade["position"] for trade in to_insert]
                insert_entry_prices = [trade["entry_price"] for trade in to_insert]
                insert_exit_prices = [trade["exit_price"] for trade in to_insert]
                insert_quantities = [trade["quantity"] for trade in to_insert]
                insert_notes = [trade["notes"] for trade in to_insert]

                inserted_rows = await conn.fetch(
                    insert_query,
                    insert_rows,
                    insert_dates,
                    insert_models,
                    insert_sources,
                    insert_positions,
                    insert_entry_prices,
                    insert_exit_prices,
                    insert_quantities,
                    insert_notes
                )

        success_trades = [
            {
                "ticker": row["ticker"],
                "trade_date": row["trade_date"].isoformat(),
                "model": row["model"]
            }
            for row in inserted_rows
        ]

        failures = existing_failures + duplicate_failures
        summary = {
            "total": len(body.trades),
            "success": len(success_trades),
            "failed": len(failures),
            "already_exists": len(existing_failures),
            "duplicates": len(duplicate_failures),
            "success_items": success_trades,
            "fail_items": failures,
        }

        logger.info(f"[POST /trades] Summary: {summary}")

        return {
            "reqId": req_id,
            "endpoint": "POST /trades",
            "summary": summary,
            "success": success_trades,
            "fail": failures,
        }

    except Exception as e:

        logger.error(f"[POST /trades] Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to insert trades: {str(e)}")
