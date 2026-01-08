"""
Quantitatives Router

Handles collection of quantitative financial data for tickers and their peers.
"""
from fastapi import APIRouter, Request, Response, Query
from fastapi.responses import StreamingResponse
from typing import Optional, List, Dict
import uuid
import asyncio
import json
import logging
import time

from ..services.quantitatives_service import get_quantitatives

logger = logging.getLogger("alsign")

router = APIRouter(tags=["Quantitatives"])

# Store active streaming requests for cancellation
active_streams: Dict[str, asyncio.Event] = {}


@router.post("/getQuantitatives")
async def get_quantitatives_endpoint(
    request: Request,
    response: Response,
    overwrite: bool = Query(
        default=False,
        description="If True, refetch all APIs even if data exists. If False, skip APIs with existing data."
    ),
    apis: Optional[str] = Query(
        default=None,
        description="Comma-separated list of APIs to fetch. Available: ratios,key-metrics,cash-flow,balance-sheet,market-cap,price,income,quote. If not specified, fetches all APIs."
    ),
    tickers: Optional[str] = Query(
        default=None,
        description="Comma-separated list of tickers to process. Only tickers that exist in config_lv3_targets (ticker or peer column) will be processed. If not specified, processes all targets and their peers."
    ),
    max_workers: Optional[int] = Query(
        default=20,
        ge=1,
        le=100,
        description="Maximum number of concurrent ticker workers (1-100). Lower values reduce DB CPU load. Default: 20. Recommended: 10-30 depending on DB capacity."
    ),
):
    """
    Collect quantitative financial data for all target tickers and their peers.

    Fetches data from 8 FMP API endpoints per ticker:
    - Financial ratios
    - Key metrics
    - Cash flow statement
    - Balance sheet statement
    - Historical market capitalization
    - Historical price (EOD full)
    - Income statement
    - Quote (realtime)

    Performance characteristics:
    - Parallel processing with Semaphore(5) for concurrent API calls
    - Skips columns that already have data (with freshness checks)
    - Updates status field with min/max dates for each API
    - Expected time: 3-6 minutes for 100 tickers (8 APIs × ticker count)

    Returns:
        Dict with summary (totalTickers, success, fail, skipped) and results array

    Raises:
        HTTPException: 500 for processing errors
    """
    # Get request ID from middleware
    req_id = request.state.reqId if hasattr(request.state, 'reqId') else str(uuid.uuid4())

    # Parse API list
    api_list = None
    if apis:
        api_list = [api.strip() for api in apis.split(',') if api.strip()]

    # Parse ticker list
    ticker_list = None
    if tickers:
        ticker_list = [ticker.strip().upper() for ticker in tickers.split(',') if ticker.strip()]

    try:
        result = await get_quantitatives(
            overwrite=overwrite,
            apis=api_list,
            tickers=ticker_list,
            max_workers=max_workers
        )

        return {
            "reqId": req_id,
            "endpoint": "POST /getQuantitatives",
            "summary": result.get('summary', {}),
            "results": result.get('results', [])
        }

    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=f"Quantatatives collection failed: {str(e)}")


@router.api_route("/getQuantitatives/stream", methods=["GET", "POST"])
async def stream_get_quantitatives(
    request: Request,
    overwrite: bool = Query(
        default=False,
        description="If True, refetch all APIs even if data exists. If False, skip APIs with existing data."
    ),
    apis: Optional[str] = Query(
        default=None,
        description="Comma-separated list of APIs to fetch. Available: ratios,key-metrics,cash-flow,balance-sheet,market-cap,price,income,quote. If not specified, fetches all APIs."
    ),
    tickers: Optional[str] = Query(
        default=None,
        description="Comma-separated list of tickers to process. Only tickers that exist in config_lv3_targets (ticker or peer column) will be processed. If not specified, processes all targets and their peers."
    ),
    max_workers: Optional[int] = Query(
        default=20,
        ge=1,
        le=100,
        description="Maximum number of concurrent ticker workers (1-100). Lower values reduce DB CPU load. Default: 20. Recommended: 10-30 depending on DB capacity."
    ),
):
    """
    Stream quantitatives collection with real-time logs via SSE.

    Supports both GET (for EventSource) and POST methods.

    Returns:
        SSE stream with log events and final result
    """
    req_id = str(uuid.uuid4())

    # Create cancellation event
    cancel_event = asyncio.Event()
    active_streams[req_id] = cancel_event

    async def event_generator():
        """Generate SSE events for logs and results."""
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

                    # Log request start
                    logger.info(
                        f"Request started: POST /getQuantitatives",
                        extra={
                            'endpoint': 'POST /getQuantitatives',
                            'phase': 'request_start',
                            'elapsed_ms': 0,
                            'counters': {},
                            'progress': {},
                            'rate': {},
                            'batch': {},
                            'warn': []
                        }
                    )

                    # Parse API list
                    api_list = None
                    if apis:
                        api_list = [api.strip() for api in apis.split(',') if api.strip()]

                    # Parse ticker list
                    ticker_list = None
                    if tickers:
                        ticker_list = [ticker.strip().upper() for ticker in tickers.split(',') if ticker.strip()]

                    # Check for cancellation
                    if cancel_event.is_set():
                        logger.warning(
                            f"Request cancelled by user",
                            extra={
                                'endpoint': 'POST /getQuantitatives',
                                'phase': 'cancelled',
                                'elapsed_ms': int((time.time() - start_time) * 1000),
                                'counters': {},
                                'progress': {},
                                'rate': {},
                                'batch': {},
                                'warn': ['REQUEST_CANCELLED']
                            }
                        )
                        await log_queue.put(json.dumps({
                            'type': 'error',
                            'error': 'Request cancelled by user'
                        }))
                        return

                    # Execute quantitatives collection
                    result = await get_quantitatives(
                        overwrite=overwrite,
                        apis=api_list,
                        tickers=ticker_list,
                        max_workers=max_workers
                    )

                    total_elapsed_ms = int((time.time() - start_time) * 1000)

                    logger.info(
                        f"POST /getQuantitatives completed",
                        extra={
                            'endpoint': 'POST /getQuantitatives',
                            'phase': 'complete',
                            'elapsed_ms': total_elapsed_ms,
                            'counters': result['summary'],
                            'progress': {},
                            'rate': {},
                            'batch': {},
                            'warn': []
                        }
                    )

                    # Send final result
                    await log_queue.put(json.dumps({
                        'type': 'result',
                        'data': {
                            'reqId': req_id,
                            'endpoint': 'POST /getQuantitatives',
                            'summary': result['summary'],
                            'results': result.get('results', []),
                            'invalidTickers': result.get('invalidTickers', [])
                        }
                    }))

                except Exception as e:
                    logger.error(
                        f"POST /getQuantitatives failed: {str(e)}",
                        extra={
                            'endpoint': 'POST /getQuantitatives',
                            'phase': 'error',
                            'elapsed_ms': int((time.time() - start_time) * 1000),
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
                    # Signal completion
                    await log_queue.put(None)

            # Start collection task
            collection_task = asyncio.create_task(collect_data())

            # Stream logs from queue
            while True:
                try:
                    # Wait for log with timeout to check cancellation
                    log_line = await asyncio.wait_for(log_queue.get(), timeout=0.1)

                    if log_line is None:
                        # Collection complete
                        break

                    # Check if it's a result or log
                    if log_line.startswith('{') and '"type"' in log_line:
                        # JSON result or error
                        data = json.loads(log_line)
                        if data.get('type') == 'result':
                            yield f"event: result\ndata: {log_line}\n\n"
                        elif data.get('type') == 'error':
                            yield f"event: error\ndata: {log_line}\n\n"
                    else:
                        # Regular log line
                        yield f"event: log\ndata: {json.dumps({'log': log_line})}\n\n"

                except asyncio.TimeoutError:
                    # Check if cancelled
                    if cancel_event.is_set():
                        collection_task.cancel()
                        break
                    continue

        except Exception as e:
            logger.error(f"Stream generator error: {str(e)}", exc_info=True)
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
        finally:
            # Remove queue handler
            logger.removeHandler(queue_handler)

            # Cleanup
            if req_id in active_streams:
                del active_streams[req_id]

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Request-ID": req_id
        }
    )


@router.post("/getQuantitatives/cancel/{req_id}")
async def cancel_get_quantitatives_stream(req_id: str):
    """
    Cancel an active getQuantitatives streaming request.

    Args:
        req_id: Request ID to cancel

    Returns:
        Cancellation status
    """
    if req_id in active_streams:
        active_streams[req_id].set()
        return {"status": "cancelled", "reqId": req_id}
    else:
        return {"status": "not_found", "reqId": req_id}
