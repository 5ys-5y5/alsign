"""Router for event processing endpoints."""

import uuid
import logging
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Request, Response

from ..models.request_models import SetEventsTableQueryParams, BackfillEventsTableQueryParams
from ..models.response_models import SetEventsTableResponse, BackfillEventsTableResponse
from ..services import events_service, valuation_service
from ..utils.logging_utils import log_error

logger = logging.getLogger("alsign")

router = APIRouter(prefix="", tags=["Event Processing"])


def normalize_date_range(from_date, to_date):
    if from_date is None and to_date is not None:
        return date(2000, 1, 1), to_date
    return from_date, to_date


@router.post("/test-post")
async def test_post():
    """Simple test endpoint to verify POST requests work."""
    logger.info("TEST POST ENDPOINT CALLED")
    return {"message": "test post works", "timestamp": "now"}


@router.post("/setEventsTable", response_model=SetEventsTableResponse)
async def set_events_table(
    request: Request,
    params: SetEventsTableQueryParams = Depends()
):
    """
    Consolidate and enrich events from source tables.

    Auto-discovers evt_* tables in specified schema, extracts events,
    inserts into txn_events, and enriches with sector/industry from config_lv3_targets.

    Optional cleanup mode:
    - preview: Show invalid tickers that would be deleted (no changes)
    - archive: Move invalid ticker events to txn_events_archived then delete
    - delete: Permanently delete invalid ticker events (WARNING: no recovery)

    Args:
        params: Query parameters including cleanup_mode

    Returns:
        SetEventsTableResponse with summary and per-table results

    Raises:
        HTTPException: 400 for invalid parameters or schema not found
    """
    # Get request ID from middleware
    req_id = request.state.reqId if hasattr(request.state, 'reqId') else str(uuid.uuid4())

    # Parse table filter if provided
    table_filter = None
    if params.table:
        table_filter = [t.strip() for t in params.table.split(',')]

    try:
        result = await events_service.consolidate_events(
            overwrite=params.overwrite,
            dry_run=params.dryRun,
            schema=params.schema,
            table_filter=table_filter,
            cleanup_mode=params.cleanup_mode,
            max_workers=params.max_workers
        )

        # Build response
        response = SetEventsTableResponse(
            reqId=req_id,
            endpoint="POST /setEventsTable",
            dryRun=params.dryRun,
            summary=result['summary'],
            tables=result['tables']
        )

        return response

    except ValueError as e:
        # Schema not found or invalid table name
        log_error(logger, "Validation error in POST /setEventsTable", exception=e)
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        log_error(logger, "POST /setEventsTable failed", exception=e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/backfillEventsTable", response_model=BackfillEventsTableResponse)
async def backfill_events_table(
    request: Request,
    response: Response,
    params: BackfillEventsTableQueryParams = Depends()
):
    """
    Calculate valuation metrics for events.

    Calculates value_quantitative, value_qualitative, position_quantitative,
    position_qualitative, disparity_quantitative, and disparity_qualitative
    for events in txn_events.

    Args:
        params: Query parameters including overwrite, from, to

    Returns:
        BackfillEventsTableResponse with summary and per-event results

    Raises:
        HTTPException: 400 for invalid parameters
    """
    # Get request ID from middleware
    req_id = request.state.reqId if hasattr(request.state, 'reqId') else str(uuid.uuid4())

    # Parse ticker list
    ticker_list = params.get_ticker_list()
    start_point = params.get_start_point()

    # Parse metrics list (I-41)
    metrics_list = params.get_metrics_list()

    normalized_from, normalized_to = normalize_date_range(params.from_date, params.to_date)

    logger.info(
        "[POST /backfillEventsTable] "
        f"reqId={req_id}, overwrite={params.overwrite}, from={normalized_from}, "
        f"to={normalized_to}, startPoint={start_point}"
    )

    try:
        result = await valuation_service.calculate_valuations(
            overwrite=params.overwrite,
            from_date=normalized_from,
            to_date=normalized_to,
            tickers=ticker_list,
            start_point=start_point,
            metrics_list=metrics_list,
            batch_size=params.batch_size,
            max_workers=params.max_workers
        )

        # Determine HTTP status code
        summary = result['summary']
        if summary['quantitativeFail'] > 0 or summary['qualitativeFail'] > 0:
            response.status_code = 207

        # Build response
        api_response = BackfillEventsTableResponse(
            reqId=req_id,
            endpoint="POST /backfillEventsTable",
            overwrite=params.overwrite,
            summary=result['summary'],
            results=result['results']
        )

        logger.info(f"[POST /backfillEventsTable] COMPLETE - reqId={req_id}, status={response.status_code}")
        return api_response

    except Exception as e:
        logger.error(f"[POST /backfillEventsTable] FAILED - reqId={req_id}")
        log_error(logger, "POST /backfillEventsTable failed", exception=e)
        raise HTTPException(status_code=500, detail=str(e))
