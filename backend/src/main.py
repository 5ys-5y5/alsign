"""FastAPI application entry point."""

import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from contextlib import asynccontextmanager

from .config import settings
from .database.connection import db_pool
from .middleware.logging_middleware import LoggingMiddleware
from .middleware.error_handler import (
    http_exception_handler,
    validation_exception_handler,
    generic_exception_handler,
)
from .services.utils.logging_utils import setup_logging

# Setup logging
setup_logging(settings.LOG_LEVEL)
logger = logging.getLogger("alsign")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan context manager.

    Handles startup and shutdown events.
    """
    # Startup
    logger.info("Starting application...")
    await db_pool.connect()
    logger.info("Database connection pool created")

    yield

    # Shutdown
    logger.info("Shutting down application...")
    await db_pool.close()
    logger.info("Database connection pool closed")


# Create FastAPI application
app = FastAPI(
    title="AlSign Financial Data API",
    description="JSON-only Web API for financial data collection and processing",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
# Allow all origins in development for flexible dev server configuration
# TODO: Configure proper CORS origins for production deployment
logger.info("CORS: Allowing all origins for development")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add logging middleware
# TEMPORARILY DISABLED FOR DEBUGGING
# app.add_middleware(LoggingMiddleware)

# Add request logging for debugging
@app.middleware("http")
async def log_requests(request, call_next):
    """Simple request logger for debugging."""
    logger.info(f">>>>>> REQUEST: {request.method} {request.url.path}")
    try:
        response = await call_next(request)
        logger.info(f"<<<<<< RESPONSE: {request.method} {request.url.path} - {response.status_code}")
        return response
    except Exception as e:
        logger.error(f"<<<<<< ERROR: {request.method} {request.url.path} - {e}")
        raise

# Register exception handlers
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)


@app.get("/health")
async def health_check():
    """
    Enhanced health check endpoint.

    Returns:
        Health status, database connection status, version, and timestamp
    """
    from datetime import datetime, timezone

    health_status = {
        "status": "unknown",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "1.0.0",
        "checks": {
            "database": {"status": "unknown", "message": None},
        }
    }

    # Check database connection
    try:
        pool = await db_pool.get_pool()
        async with pool.acquire() as conn:
            # Test connection and get database version
            db_version = await conn.fetchval("SELECT version()")
            await conn.fetchval("SELECT 1")

        health_status["checks"]["database"] = {
            "status": "healthy",
            "message": "Connected",
            "details": {
                "pool_size": pool.get_size(),
                "pool_max_size": pool.get_max_size(),
            }
        }
    except Exception as e:
        logger.error(f"Health check database failure: {e}")
        health_status["checks"]["database"] = {
            "status": "unhealthy",
            "message": str(e)
        }

    # Overall status
    all_healthy = all(
        check["status"] == "healthy"
        for check in health_status["checks"].values()
    )
    health_status["status"] = "healthy" if all_healthy else "unhealthy"

    return health_status


# Import and include routers
from .routers import source_data, source_data_stream, events, events_stream, analyst, condition_group, dashboard, control
app.include_router(source_data.router)
app.include_router(source_data_stream.router)
app.include_router(events.router)
app.include_router(events_stream.router)
app.include_router(analyst.router)
app.include_router(condition_group.router)
app.include_router(dashboard.router)
app.include_router(control.router)
