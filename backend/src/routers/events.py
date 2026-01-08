"""Router for event processing endpoints."""

import uuid
import logging
from fastapi import APIRouter, Depends, HTTPException, Request, Response

from ..models.request_models import SetEventsTableQueryParams, BackfillEventsTableQueryParams
from ..models.response_models import SetEventsTableResponse, BackfillEventsTableResponse
from ..services import events_service, valuation_service
from ..utils.logging_utils import log_error

logger = logging.getLogger("alsign")

router = APIRouter(prefix="", tags=["Event Processing"])


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

    Args:
        params: Query parameters

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

    # Parse metrics list (I-41)
    metrics_list = params.get_metrics_list()

    logger.info("=" * 80)
    logger.info(f"[ROUTER] POST /backfillEventsTable RECEIVED - reqId={req_id}")
    logger.info(f"[ROUTER] Parameters: overwrite={params.overwrite}, from_date={params.from_date}, to_date={params.to_date}, tickers={ticker_list}, metrics={metrics_list}, batch_size={params.batch_size}")
    logger.info("=" * 80)

    try:
        logger.info(f"[ROUTER] Calling valuation_service.calculate_valuations")
        result = await valuation_service.calculate_valuations(
            overwrite=params.overwrite,
            from_date=params.from_date,
            to_date=params.to_date,
            tickers=ticker_list,
            metrics_list=metrics_list,
            batch_size=params.batch_size,
            max_workers=params.max_workers
        )
        logger.info(f"[ROUTER] valuation_service.calculate_valuations completed successfully")

        # Determine HTTP status code
        # 207 Multi-Status if some events failed, otherwise 200
        summary = result['summary']
        if summary['quantitativeFail'] > 0 or summary['qualitativeFail'] > 0:
            response.status_code = 207
            logger.info(f"[ROUTER] Setting status code to 207 (Multi-Status) due to failures")

        # Build response
        api_response = BackfillEventsTableResponse(
            reqId=req_id,
            endpoint="POST /backfillEventsTable",
            overwrite=params.overwrite,
            summary=result['summary'],
            results=result['results']
        )

        logger.info("=" * 80)
        logger.info(f"[ROUTER] POST /backfillEventsTable COMPLETE - Returning response")
        logger.info("=" * 80)

        return api_response

    except Exception as e:
        logger.error("=" * 80)
        logger.error(f"[ROUTER] POST /backfillEventsTable FAILED")
        logger.error("=" * 80)

        log_error(logger, "POST /backfillEventsTable failed", exception=e)
        raise HTTPException(status_code=500, detail=str(e))
