"""Router for event processing streaming endpoints with SSE."""

import uuid
import time
import logging
import asyncio
import json
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from typing import Dict

from ..models.request_models import SetEventsTableQueryParams, BackfillEventsTableQueryParams
from ..services import events_service, valuation_service
from ..utils.logging_utils import log_error, log_warning

logger = logging.getLogger("alsign")

router = APIRouter(prefix="", tags=["Event Processing"])

# Store active streaming requests for cancellation
active_streams: Dict[str, asyncio.Event] = {}


@router.api_route("/setEventsTable/stream", methods=["GET", "POST"])
async def stream_set_events_table(
    request: Request,
    params: SetEventsTableQueryParams = Depends()
):
    """
    Stream event consolidation with real-time logs via SSE.

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
                        f"Request started: POST /setEventsTable",
                        extra={
                            'endpoint': 'POST /setEventsTable',
                            'phase': 'request_start',
                            'elapsed_ms': 0,
                            'counters': {},
                            'progress': {},
                            'rate': {},
                            'batch': {},
                            'warn': []
                        }
                    )

                    # Parse table filter if provided
                    table_filter = None
                    if params.table:
                        table_filter = [t.strip() for t in params.table.split(',')]

                    # Check for cancellation
                    if cancel_event.is_set():
                        logger.warning(
                            f"Request cancelled by user",
                            extra={
                                'endpoint': 'POST /setEventsTable',
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

                    # Execute consolidation
                    result = await events_service.consolidate_events(
                        overwrite=params.overwrite,
                        dry_run=params.dryRun,
                        schema=params.schema,
                        table_filter=table_filter
                    )

                    total_elapsed_ms = int((time.time() - start_time) * 1000)

                    logger.info(
                        f"POST /setEventsTable completed",
                        extra={
                            'endpoint': 'POST /setEventsTable',
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
                            'endpoint': 'POST /setEventsTable',
                            'dryRun': params.dryRun,
                            'summary': result['summary'],
                            'tables': result['tables']
                        }
                    }))

                except ValueError as e:
                    # Schema not found or invalid table name
                    log_error(logger, "Validation error in POST /setEventsTable", exception=e)
                    await log_queue.put(json.dumps({
                        'type': 'error',
                        'error': str(e)
                    }))

                except Exception as e:
                    logger.error(
                        f"POST /setEventsTable failed: {str(e)}",
                        extra={
                            'endpoint': 'POST /setEventsTable',
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
                        # JSON result
                        yield f"event: result\ndata: {log_line}\n\n"
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


@router.api_route("/backfillEventsTable/stream", methods=["GET", "POST"])
async def stream_backfill_events_table(
    request: Request,
    params: BackfillEventsTableQueryParams = Depends()
):
    """
    Stream valuation calculation with real-time logs via SSE.

    Supports both GET (for EventSource) and POST methods.

    Returns:
        SSE stream with log events and final result
    """
    req_id = str(uuid.uuid4())

    # Parse ticker list
    ticker_list = params.get_ticker_list()

    # Create cancellation event
    cancel_event = asyncio.Event()
    active_streams[req_id] = cancel_event

    logger.info("=" * 80)
    logger.info(f"[STREAM] POST /backfillEventsTable/stream RECEIVED - reqId={req_id}")
    logger.info(f"[STREAM] Parameters: overwrite={params.overwrite}, from_date={params.from_date}, to_date={params.to_date}, tickers={ticker_list}")
    logger.info("=" * 80)

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
                        f"Request started: POST /backfillEventsTable/stream",
                        extra={
                            'endpoint': 'POST /backfillEventsTable',
                            'phase': 'request_start',
                            'elapsed_ms': 0,
                            'counters': {},
                            'progress': {},
                            'rate': {},
                            'batch': {},
                            'warn': []
                        }
                    )

                    # Check for cancellation
                    if cancel_event.is_set():
                        logger.warning(
                            f"Request cancelled by user",
                            extra={
                                'endpoint': 'POST /backfillEventsTable',
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

                    # Parse metrics list (I-41)
                    metrics_list = params.get_metrics_list()

                    logger.info(f"[STREAM] Calling valuation_service.calculate_valuations")
                    logger.info(f"[STREAM] Parameters: metrics={metrics_list}, batch_size={params.batch_size}")

                    # Execute valuation calculation with cancel event
                    result = await valuation_service.calculate_valuations(
                        overwrite=params.overwrite,
                        from_date=params.from_date,
                        to_date=params.to_date,
                        tickers=ticker_list,
                        cancel_event=cancel_event,
                        metrics_list=metrics_list,
                        batch_size=params.batch_size
                    )

                    logger.info(f"[STREAM] valuation_service.calculate_valuations completed")

                    total_elapsed_ms = int((time.time() - start_time) * 1000)

                    # Determine status code based on failures
                    summary = result['summary']
                    status_code = 207 if (summary['quantitativeFail'] > 0 or summary['qualitativeFail'] > 0) else 200

                    logger.info(
                        f"POST /backfillEventsTable completed",
                        extra={
                            'endpoint': 'POST /backfillEventsTable',
                            'phase': 'complete',
                            'elapsed_ms': total_elapsed_ms,
                            'counters': summary,
                            'progress': {},
                            'rate': {},
                            'batch': {},
                            'warn': [] if status_code == 200 else ['PARTIAL_FAILURES']
                        }
                    )

                    # Send final result
                    # Convert EventProcessingResult objects to dicts for JSON serialization
                    results_serializable = [
                        r.model_dump() if hasattr(r, 'model_dump') else (r.dict() if hasattr(r, 'dict') else r)
                        for r in result['results']
                    ]
                    await log_queue.put(json.dumps({
                        'type': 'result',
                        'data': {
                            'reqId': req_id,
                            'endpoint': 'POST /backfillEventsTable',
                            'overwrite': params.overwrite,
                            'summary': result['summary'],
                            'results': results_serializable,
                            'statusCode': status_code
                        }
                    }))

                except Exception as e:
                    logger.error(
                        f"POST /backfillEventsTable failed: {str(e)}",
                        extra={
                            'endpoint': 'POST /backfillEventsTable',
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


@router.post("/setEventsTable/cancel/{req_id}")
async def cancel_set_events_stream(req_id: str):
    """
    Cancel an active setEventsTable streaming request.

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


@router.post("/backfillEventsTable/cancel/{req_id}")
async def cancel_backfill_events_stream(req_id: str):
    """
    Cancel an active backfillEventsTable streaming request.

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
