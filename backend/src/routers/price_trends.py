"""
Price Trends Router

Handles price trend generation for events in txn_price_trend table.
Separated from backfillEventsTable for independent execution.
"""
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import StreamingResponse
from typing import Optional, List
from datetime import date
import uuid
import time
import logging
import json
import asyncio

from ..services.valuation_service import generate_price_trends
from ..models.request_models import BackfillEventsTableQueryParams


router = APIRouter(tags=["Price Trends"])

logger = logging.getLogger("alsign")


def normalize_date_range(from_date, to_date):
    if from_date is None and to_date is not None:
        return date(2000, 1, 1), to_date
    return from_date, to_date


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
    table_list = params.get_table_list()

    normalized_from, normalized_to = normalize_date_range(params.from_date, params.to_date)

    try:
        result = await generate_price_trends(
            from_date=normalized_from,
            to_date=normalized_to,
            tickers=ticker_list,
            tables=table_list,
            start_point=params.get_start_point(),
            batch_size=params.batch_size,
            max_workers=params.max_workers
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

@router.api_route("/generatePriceTrends/stream", methods=["GET", "POST"])
async def stream_generate_price_trends(
    request: Request,
    params: BackfillEventsTableQueryParams = Depends()
):
    """
    Stream price trend generation with real-time logs via SSE.

    Supports both GET (for EventSource) and POST methods.

    Returns:
        SSE stream with log events and final result
    """
    req_id = str(uuid.uuid4())

    async def event_generator():
        """Generate SSE events for logs and results."""
        queue_handler = None
        try:
            # Send initial event with request ID
            yield f"event: init\ndata: {json.dumps({'reqId': req_id})}\n\n"

            # Create log queue
            log_queue = asyncio.Queue()

            # Custom log handler that sends to queue
            class QueueHandler(logging.Handler):
                def emit(self, record):
                    try:
                        formatted = self.format(record)
                        asyncio.create_task(log_queue.put(formatted))
                    except Exception:
                        pass

            # Add queue handler to logger
            queue_handler = QueueHandler()
            queue_handler.setFormatter(logger.handlers[0].formatter if logger.handlers else None)
            logger.addHandler(queue_handler)

            # Start data collection in background task
            async def collect_data():
                try:
                    start_time = time.time()

                    logger.info(
                        "Request started: POST /generatePriceTrends/stream",
                        extra={
                            'endpoint': 'POST /generatePriceTrends',
                            'phase': 'request_start',
                            'elapsed_ms': 0,
                            'counters': {},
                            'progress': {},
                            'rate': {},
                            'batch': {},
                            'warn': []
                        }
                    )

                    ticker_list = params.get_ticker_list()
                    table_list = params.get_table_list()
                    normalized_from, normalized_to = normalize_date_range(params.from_date, params.to_date)

                    result = await generate_price_trends(
                        from_date=normalized_from,
                        to_date=normalized_to,
                        tickers=ticker_list,
                        tables=table_list,
                        start_point=params.get_start_point(),
                        batch_size=params.batch_size,
                        max_workers=params.max_workers
                    )

                    total_elapsed_ms = int((time.time() - start_time) * 1000)

                    logger.info(
                        "POST /generatePriceTrends completed",
                        extra={
                            'endpoint': 'POST /generatePriceTrends',
                            'phase': 'complete',
                            'elapsed_ms': total_elapsed_ms,
                            'counters': {
                                'success': result.get('success', 0),
                                'fail': result.get('fail', 0)
                            },
                            'progress': {},
                            'rate': {},
                            'batch': {},
                            'warn': []
                        }
                    )

                    await log_queue.put(json.dumps({
                        'type': 'result',
                        'data': {
                            'reqId': req_id,
                            'endpoint': 'POST /generatePriceTrends',
                            'summary': {
                                'success': result.get('success', 0),
                                'fail': result.get('fail', 0)
                            }
                        }
                    }))

                except Exception as e:
                    logger.error(
                        f"POST /generatePriceTrends failed: {str(e)}",
                        extra={
                            'endpoint': 'POST /generatePriceTrends',
                            'phase': 'error',
                            'elapsed_ms': int((time.time() - start_time) * 1000) if 'start_time' in locals() else 0,
                            'counters': {},
                            'progress': {},
                            'rate': {},
                            'batch': {},
                            'warn': []
                        },
                        exc_info=True
                    )
                    await log_queue.put(json.dumps({
                        'type': 'error',
                        'error': str(e)
                    }))
                finally:
                    await log_queue.put(None)

            collection_task = asyncio.create_task(collect_data())

            while True:
                try:
                    log_line = await asyncio.wait_for(log_queue.get(), timeout=0.1)

                    if log_line is None:
                        break

                    if log_line.startswith('{') and '"type"' in log_line:
                        data = json.loads(log_line)
                        if data.get('type') == 'result':
                            yield f"event: result\ndata: {log_line}\n\n"
                        elif data.get('type') == 'error':
                            yield f"event: error\ndata: {log_line}\n\n"
                    else:
                        yield f"event: log\ndata: {json.dumps({'log': log_line})}\n\n"

                except asyncio.TimeoutError:
                    if collection_task.done():
                        break
                    continue

        except Exception as e:
            logger.error(f"Stream generator error: {str(e)}", exc_info=True)
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
        finally:
            if queue_handler is not None:
                logger.removeHandler(queue_handler)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Request-ID": req_id
        }
    )
