"""Router for POST /fillAnalyst endpoint."""

import uuid
import logging
from fastapi import APIRouter, HTTPException, Request, Response, Depends

from ..models.request_models import FillAnalystQueryParams
from ..models.response_models import FillAnalystResponse
from ..services import analyst_service

logger = logging.getLogger("alsign")

router = APIRouter(prefix="", tags=["Analytics"])


@router.post("/fillAnalyst", response_model=FillAnalystResponse)
async def fill_analyst(
    request: Request,
    response: Response,
    params: FillAnalystQueryParams = Depends()
):
    """
    Aggregate analyst performance metrics.

    Groups consensus events by (analyst_name, analyst_company), calculates
    return distributions per dayOffset, and upserts performance statistics
    to config_lv3_analyst table.

    Args:
        params: Query parameters including overwrite

    Returns:
        FillAnalystResponse with summary and per-group results

    Raises:
        HTTPException: 400 for validation errors, 500 for server errors
    """
    # Get request ID from middleware
    req_id = request.state.reqId if hasattr(request.state, 'reqId') else str(uuid.uuid4())

    try:
        result = await analyst_service.aggregate_analyst_performance(
            overwrite=params.overwrite,
            max_workers=params.max_workers,
            verbose=params.verbose
        )

        # Check if there was a global error
        if 'error' in result and 'errorCode' in result:
            # Policy not found or other validation error
            logger.error(
                f"Validation error: {result['error']}",
                extra={
                    'endpoint': 'POST /fillAnalyst',
                    'phase': 'validation',
                    'elapsed_ms': 0,
                    'counters': {},
                    'progress': {},
                    'rate': {},
                    'batch': {},
                    'warn': []
                }
            )
            raise HTTPException(
                status_code=400,
                detail={
                    'error': result['error'],
                    'code': result['errorCode']
                }
            )

        # Determine HTTP status code
        # 207 Multi-Status if some groups failed, otherwise 200
        summary = result['summary']
        if summary['groupsFailed'] > 0:
            response.status_code = 207

        # Build response
        api_response = FillAnalystResponse(
            reqId=req_id,
            endpoint="POST /fillAnalyst",
            summary=result['summary'],
            groups=result['groups']
        )

        return api_response

    except HTTPException:
        # Re-raise HTTP exceptions
        raise

    except Exception as e:
        logger.error(
            f"POST /fillAnalyst failed: {str(e)}",
            extra={
                'endpoint': 'POST /fillAnalyst',
                'phase': 'error',
                'elapsed_ms': 0,
                'counters': {},
                'progress': {},
                'rate': {},
                'batch': {},
                'warn': []
            },
            exc_info=True
        )
        raise HTTPException(status_code=500, detail=str(e))
