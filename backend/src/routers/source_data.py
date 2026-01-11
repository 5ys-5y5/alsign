"""Router for GET /sourceData endpoint."""

import uuid
import time
import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from typing import Dict, Any

from ..models.request_models import SourceDataQueryParams
from ..models.response_models import SourceDataResponse, Summary
from ..services import source_data_service

logger = logging.getLogger("alsign")

router = APIRouter(prefix="", tags=["Data Collection"])


@router.get("/sourceData", response_model=SourceDataResponse)
async def get_source_data(
    request: Request,
    params: SourceDataQueryParams = Depends()
):
    """
    Collect financial data from external FMP APIs.

    Supports selective execution via mode parameter.
    Executes two-phase consensus processing.

    Args:
        params: Query parameters

    Returns:
        SourceDataResponse with results per mode and summary

    Raises:
        HTTPException: 400 for invalid parameters
    """
    # Get request ID from middleware
    req_id = request.state.reqId if hasattr(request.state, 'reqId') else str(uuid.uuid4())

    start_time = time.time()

    # Get mode list in default order
    mode_list = params.get_mode_list()

    # Execute each mode
    results = {}
    total_success = 0
    total_fail = 0

    for mode in mode_list:
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
                result = await source_data_service.get_holidays(
                    overwrite=params.overwrite,
                    max_workers=params.max_workers,
                    verbose=params.verbose
                )
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
                result = await source_data_service.get_targets(
                    overwrite=params.overwrite,
                    max_workers=params.max_workers,
                    verbose=params.verbose
                )
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
                    partitions_param=params.partitions,
                    max_workers=params.max_workers,
                    verbose=params.verbose
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
                result = await source_data_service.get_earning(
                    overwrite=params.overwrite,
                    past=params.past,
                    max_workers=params.max_workers,
                    verbose=params.verbose
                )
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
            # Continue with other modes even if one fails
            results[mode] = {
                "executed": False,
                "elapsedMs": int((time.time() - mode_start) * 1000),
                "counters": {"success": 0, "fail": 1},
                "error": str(e)
            }
            total_fail += 1

    total_elapsed_ms = int((time.time() - start_time) * 1000)

    # Build response
    response = SourceDataResponse(
        reqId=req_id,
        endpoint="GET /sourceData",
        summary=Summary(
            totalElapsedMs=total_elapsed_ms,
            totalSuccess=total_success,
            totalFail=total_fail
        ),
        results=results
    )

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

    return response
