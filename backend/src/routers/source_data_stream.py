"""Router for GET /sourceData/stream endpoint with SSE."""

import uuid
import time
import logging
import asyncio
import json
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from typing import Dict, Any

from ..models.request_models import SourceDataQueryParams
from ..services import source_data_service

logger = logging.getLogger("alsign")

router = APIRouter(prefix="", tags=["Data Collection"])

# Store active streaming requests for cancellation
active_streams: Dict[str, asyncio.Event] = {}


@router.get("/sourceData/stream")
async def stream_source_data(
    request: Request,
    params: SourceDataQueryParams = Depends()
):
    """
    Stream financial data collection with real-time logs via SSE.

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
                        f"Request started: GET /sourceData",
                        extra={
                            'endpoint': 'GET /sourceData',
                            'phase': 'request_start',
                            'elapsed_ms': 0,
                            'counters': {},
                            'progress': {},
                            'rate': {},
                            'batch': {},
                            'warn': []
                        }
                    )

                    # Get mode list
                    mode_list = params.get_mode_list()

                    results = {}
                    total_success = 0
                    total_fail = 0

                    for mode in mode_list:
                        # Check for cancellation
                        if cancel_event.is_set():
                            logger.warning(
                                f"Request cancelled by user",
                                extra={
                                    'endpoint': 'GET /sourceData',
                                    'phase': 'cancelled',
                                    'elapsed_ms': int((time.time() - start_time) * 1000),
                                    'counters': {},
                                    'progress': {},
                                    'rate': {},
                                    'batch': {},
                                    'warn': ['REQUEST_CANCELLED']
                                }
                            )
                            break

                        mode_start = time.time()

                        try:
                            if mode == 'holiday':
                                logger.info(
                                    f"Executing getHolidays",
                                    extra={
                                        'endpoint': 'GET /sourceData',
                                        'phase': 'getHolidays',
                                        'elapsed_ms': int((time.time() - mode_start) * 1000),
                                        'counters': {},
                                        'progress': {},
                                        'rate': {},
                                        'batch': {},
                                        'warn': []
                                    }
                                )
                                result = await source_data_service.get_holidays(overwrite=params.overwrite)
                                results['holiday'] = result
                                total_success += result['counters'].success
                                total_fail += result['counters'].fail

                            elif mode == 'target':
                                logger.info(
                                    f"Executing getTargets",
                                    extra={
                                        'endpoint': 'GET /sourceData',
                                        'phase': 'getTargets',
                                        'elapsed_ms': int((time.time() - mode_start) * 1000),
                                        'counters': {},
                                        'progress': {},
                                        'rate': {},
                                        'batch': {},
                                        'warn': []
                                    }
                                )
                                result = await source_data_service.get_targets(overwrite=params.overwrite)
                                results['target'] = result
                                total_success += result['counters'].success
                                total_fail += result['counters'].fail

                            elif mode == 'consensus':
                                logger.info(
                                    f"Executing getConsensus",
                                    extra={
                                        'endpoint': 'GET /sourceData',
                                        'phase': 'getConsensus',
                                        'elapsed_ms': int((time.time() - mode_start) * 1000),
                                        'counters': {},
                                        'progress': {},
                                        'rate': {},
                                        'batch': {},
                                        'warn': []
                                    }
                                )
                                result = await source_data_service.get_consensus(
                                    overwrite=params.overwrite,
                                    calc_mode=params.calc_mode,
                                    calc_scope=params.calc_scope,
                                    tickers_param=params.tickers,
                                    from_date=params.from_date,
                                    to_date=params.to_date,
                                    partitions_param=params.partitions
                                )
                                results['consensus'] = result
                                total_success += result['counters'].success
                                total_fail += result['counters'].fail

                            elif mode == 'earning':
                                logger.info(
                                    f"Executing getEarning",
                                    extra={
                                        'endpoint': 'GET /sourceData',
                                        'phase': 'getEarning',
                                        'elapsed_ms': int((time.time() - mode_start) * 1000),
                                        'counters': {},
                                        'progress': {},
                                        'rate': {},
                                        'batch': {},
                                        'warn': []
                                    }
                                )
                                result = await source_data_service.get_earning(overwrite=params.overwrite, past=params.past)
                                results['earning'] = result
                                total_success += result['counters'].success
                                total_fail += result['counters'].fail

                        except Exception as e:
                            logger.error(
                                f"Mode '{mode}' failed: {str(e)}",
                                extra={
                                    'endpoint': 'GET /sourceData',
                                    'phase': mode,
                                    'elapsed_ms': int((time.time() - mode_start) * 1000),
                                    'counters': {'fail': 1},
                                    'progress': {},
                                    'rate': {},
                                    'batch': {},
                                    'warn': []
                                },
                                exc_info=True
                            )
                            results[mode] = {
                                "executed": False,
                                "elapsedMs": int((time.time() - mode_start) * 1000),
                                "counters": {"success": 0, "fail": 1},
                                "error": str(e)
                            }
                            total_fail += 1

                    total_elapsed_ms = int((time.time() - start_time) * 1000)

                    logger.info(
                        f"GET /sourceData completed",
                        extra={
                            'endpoint': 'GET /sourceData',
                            'phase': 'complete',
                            'elapsed_ms': total_elapsed_ms,
                            'counters': {'success': total_success, 'fail': total_fail},
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
                            'endpoint': 'GET /sourceData',
                            'summary': {
                                'totalElapsedMs': total_elapsed_ms,
                                'totalSuccess': total_success,
                                'totalFail': total_fail
                            },
                            'results': results
                        }
                    }))

                except Exception as e:
                    logger.error(f"Stream error: {str(e)}", exc_info=True)
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


@router.post("/sourceData/cancel/{req_id}")
async def cancel_stream(req_id: str):
    """
    Cancel an active streaming request.

    Args:
        req_id: Request ID to cancel

    Returns:
        Cancellation status
    """
    if req_id in active_streams:
        active_streams[req_id].set()
        return {"status": "cancelled", "reqId": req_id}
    else:
        raise HTTPException(status_code=404, detail="Request not found or already completed")
