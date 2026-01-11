"""
Price Trends Router

Handles price trend generation for events in txn_price_trend table.
Separated from backfillEventsTable for independent execution.
"""
from fastapi import APIRouter, Depends, Request, Response
from typing import Optional, List
from datetime import date
import uuid

from ..services.valuation_service import generate_price_trends
from ..models.request_models import BackfillEventsTableQueryParams


router = APIRouter(tags=["Price Trends"])


@router.post("/generatePriceTrends")
async def generate_price_trends_endpoint(
    request: Request,
    response: Response,
    params: BackfillEventsTableQueryParams = Depends()
):
    """
    Generate price trends for events in txn_price_trend table.

    Fetches OHLC data and calculates dayOffset price trends (-14 to +14 trading days)
    for all events in txn_events, storing results in txn_price_trend table.

    Performance optimized for 140k+ events:
    - Pre-caches trading days for entire date range
    - Batch OHLC fetching per ticker
    - Single batch UPSERT using PostgreSQL UNNEST

    Args:
        params: Query parameters (overwrite, from, to, tickers)

    Returns:
        Dict with success/fail counts

    Raises:
        HTTPException: 500 for processing errors
    """
    # Get request ID from middleware
    req_id = request.state.reqId if hasattr(request.state, 'reqId') else str(uuid.uuid4())

    # Parse ticker list
    ticker_list = params.get_ticker_list()

    try:
        result = await generate_price_trends(
            from_date=params.from_date,
            to_date=params.to_date,
            tickers=ticker_list,
            max_workers=params.max_workers,
            verbose=params.verbose
        )

        return {
            "reqId": req_id,
            "endpoint": "POST /generatePriceTrends",
            "summary": {
                "success": result.get('success', 0),
                "fail": result.get('fail', 0)
            }
        }

    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=f"Price trend generation failed: {str(e)}")
