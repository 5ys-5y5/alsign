"""Global error handling middleware."""

import logging
import traceback
from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("alsign")


async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """
    Handle HTTP exceptions with consistent error response format.

    Logs the error and returns a JSON response with error details.
    """
    logger.error(
        f"action=http_exception status=error path={request.url.path} "
        f"method={request.method} status_code={exc.status_code} detail={exc.detail}"
    )

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "type": "HTTPException",
                "status_code": exc.status_code,
                "message": exc.detail,
                "path": str(request.url.path),
            }
        },
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Handle request validation errors with detailed error messages.

    Returns validation errors in a user-friendly format.
    """
    errors = []
    for error in exc.errors():
        field = ".".join(str(loc) for loc in error["loc"])
        errors.append({
            "field": field,
            "message": error["msg"],
            "type": error["type"],
        })

    logger.error(
        f"action=validation_error status=error path={request.url.path} "
        f"method={request.method} errors={errors}"
    )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": {
                "type": "ValidationError",
                "status_code": 422,
                "message": "Request validation failed",
                "path": str(request.url.path),
                "validation_errors": errors,
            }
        },
    )


async def generic_exception_handler(request: Request, exc: Exception):
    """
    Handle all other unhandled exceptions.

    Logs full traceback and returns generic error response to avoid leaking
    implementation details.
    """
    # Log full traceback for debugging
    tb = traceback.format_exc()
    logger.error(
        f"action=unhandled_exception status=error path={request.url.path} "
        f"method={request.method} error={str(exc)} traceback={tb}"
    )

    # Return generic error to client (don't leak internal details)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "type": "InternalServerError",
                "status_code": 500,
                "message": "An internal server error occurred",
                "path": str(request.url.path),
            }
        },
    )
