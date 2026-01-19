"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

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
    if settings.DATABASE_URL:
        await db_pool.connect()
        logger.info("Database connection pool created")
    else:
        logger.warning("DATABASE_URL not set; skipping database connection pool creation")

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

project_root = Path(__file__).resolve().parents[2]
frontend_dist = project_root / "frontend" / "dist"
index_file = frontend_dist / "index.html"

if index_file.exists():
    assets_dir = frontend_dist / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/", include_in_schema=False)
    async def serve_frontend_index():
        return FileResponse(str(index_file))

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

# Add logging middleware (injects detailedLogs into JSON responses)
app.add_middleware(LoggingMiddleware)

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
    if not settings.DATABASE_URL:
        health_status["checks"]["database"] = {
            "status": "unhealthy",
            "message": "DATABASE_URL not configured",
        }
    else:
        try:
            pool = await db_pool.get_pool()
            async with pool.acquire() as conn:
                # Test connection and get database version
                await conn.fetchval("SELECT version()")
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
from .routers import source_data, source_data_stream, events, events_stream, analyst, condition_group, dashboard, control, price_trends, trades, quantitatives, auth, history
app.include_router(source_data.router)
app.include_router(source_data_stream.router)
app.include_router(events.router)
app.include_router(events_stream.router)
app.include_router(analyst.router)
app.include_router(condition_group.router)
app.include_router(dashboard.router)
app.include_router(control.router)
app.include_router(price_trends.router)
app.include_router(trades.router)
app.include_router(quantitatives.router)
app.include_router(auth.router)
app.include_router(history.router)
