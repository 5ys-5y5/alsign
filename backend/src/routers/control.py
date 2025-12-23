"""Router for control panel and data management endpoints."""

import logging
import json
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Request
from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field

from ..database.connection import db_pool
from ..config import settings

logger = logging.getLogger("alsign")

router = APIRouter(prefix="/control", tags=["Control"])


# ===== REQUEST/RESPONSE MODELS =====

class APIServiceConfig(BaseModel):
    """API service configuration."""

    api_service: str
    apiKey: Optional[str] = None
    usagePerMin: Optional[int] = None
    created_at: Optional[str] = None


class APIServiceUpdate(BaseModel):
    """API service configuration update."""

    apiKey: Optional[str] = None
    usagePerMin: Optional[int] = None


class RuntimeInfo(BaseModel):
    """Runtime information."""

    server_time_iso: str
    server_tz: str
    app_version: str


class APIListItem(BaseModel):
    """API list item from config_lv1_api_list."""

    id: str
    api_service: str
    api: str
    schema: Optional[Union[Dict[str, Any], str]]
    endpoint: str
    function2: Optional[str]
    created_at: Optional[str]


class MetricItem(BaseModel):
    """Metric item from config_lv2_metric."""

    id: str
    description: Optional[str]
    source: Optional[str]
    api_list_id: Optional[str]
    base_metric_id: Optional[str]
    aggregation_kind: Optional[str]
    aggregation_params: Optional[Union[Dict[str, Any], str]]
    expression: Optional[str]
    domain: Optional[str]
    response_path: Optional[str]
    response_key: Optional[Union[Dict[str, Any], str]]
    created_at: Optional[str]


class MetricTransformItem(BaseModel):
    """Metric transform item from config_lv2_metric_transform."""

    id: str
    transform_type: str
    description: Optional[str]
    input_kind: Optional[str]
    output_kind: Optional[str]
    params_schema: Optional[Union[Dict[str, Any], str]]
    example_params: Optional[Union[Dict[str, Any], str]]
    version: Optional[Union[str, int]]
    is_active: Optional[bool]
    created_at: Optional[str]


# ===== ENDPOINTS =====

@router.get("/apiServices", response_model=List[APIServiceConfig])
async def get_api_services():
    """
    Get all API service configurations from config_lv1_api_service.

    Returns list of API services with masked apiKey fields.
    """
    try:
        pool = await db_pool.get_pool()
        async with pool.acquire() as conn:
            query = """
                SELECT
                    api_service,
                    "apiKey" AS apikey,
                    "usagePerMin" AS usagepermin,
                    created_at
                FROM config_lv1_api_service
                ORDER BY api_service
            """
            rows = await conn.fetch(query)

            services = []
            for row in rows:
                services.append(
                    APIServiceConfig(
                        api_service=row["api_service"],
                        apiKey=row["apikey"] if row["apikey"] else None,
                        usagePerMin=row["usagepermin"],
                        created_at=row["created_at"].isoformat() if row["created_at"] else None,
                    )
                )

            logger.info(f"action=get_api_services status=success count={len(services)}")
            return services

    except Exception as e:
        logger.error(f"action=get_api_services status=error error={str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch API services: {str(e)}"
        )


@router.put("/apiServices/{service}")
async def update_api_service(service: str, update: APIServiceUpdate):
    """
    Update API service configuration (apiKey and/or usagePerMin).

    Only updates provided fields (partial update).
    """
    try:
        pool = await db_pool.get_pool()
        async with pool.acquire() as conn:
            # Build update query dynamically
            updates = []
            params = []
            param_count = 1

            if update.apiKey is not None:
                updates.append(f'"apiKey" = ${param_count}')
                params.append(update.apiKey)
                param_count += 1

            if update.usagePerMin is not None:
                updates.append(f'"usagePerMin" = ${param_count}')
                params.append(update.usagePerMin)
                param_count += 1

            if not updates:
                raise HTTPException(
                    status_code=400, detail="No fields to update"
                )

            # Add service name param
            params.append(service)

            query = f"""
                UPDATE config_lv1_api_service
                SET {', '.join(updates)}
                WHERE api_service = ${param_count}
                RETURNING api_service
            """

            result = await conn.fetchval(query, *params)

            if not result:
                raise HTTPException(
                    status_code=404, detail=f"API service '{service}' not found"
                )

            logger.info(
                f"action=update_api_service status=success service={service} "
                f"fields={list(update.dict(exclude_unset=True).keys())}"
            )

            return {"status": "updated", "service": service}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"action=update_api_service status=error error={str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to update API service: {str(e)}"
        )


@router.get("/runtime", response_model=RuntimeInfo)
async def get_runtime_info():
    """
    Get runtime information (server time, timezone, app version).
    """
    try:
        now = datetime.now(timezone.utc)

        runtime = RuntimeInfo(
            server_time_iso=now.isoformat(),
            server_tz="UTC",
            app_version="1.0.0",
        )

        logger.info(f"action=get_runtime_info status=success")
        return runtime

    except Exception as e:
        logger.error(f"action=get_runtime_info status=error error={str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch runtime info: {str(e)}"
        )


@router.get("/apiList", response_model=List[APIListItem])
async def get_api_list():
    """
    Get API catalog from config_lv1_api_list.

    Returns list of available APIs with their endpoints and metadata.
    """
    try:
        pool = await db_pool.get_pool()
        async with pool.acquire() as conn:
            query = """
                SELECT
                    id,
                    api_service,
                    api,
                    schema,
                    endpoint,
                    function2,
                    created_at
                FROM config_lv1_api_list
                ORDER BY api_service, api
            """
            rows = await conn.fetch(query)

            items = []
            for row in rows:
                # Parse JSONB fields if they come as strings
                schema_val = row["schema"]
                if isinstance(schema_val, str):
                    schema_val = json.loads(schema_val) if schema_val else None

                items.append(
                    APIListItem(
                        id=row["id"],
                        api_service=row["api_service"],
                        api=row["api"],
                        schema=schema_val,
                        endpoint=row["endpoint"],
                        function2=row["function2"],
                        created_at=row["created_at"].isoformat() if row["created_at"] else None,
                    )
                )

            logger.info(f"action=get_api_list status=success count={len(items)}")
            return items

    except Exception as e:
        logger.error(f"action=get_api_list status=error error={str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch API list: {str(e)}"
        )


@router.get("/metrics", response_model=List[MetricItem])
async def get_metrics():
    """
    Get metric catalog from config_lv2_metric.

    Returns list of available metrics with their configurations.
    """
    try:
        pool = await db_pool.get_pool()
        async with pool.acquire() as conn:
            query = """
                SELECT
                    id,
                    description,
                    source,
                    api_list_id,
                    base_metric_id,
                    aggregation_kind,
                    aggregation_params,
                    expression,
                    domain,
                    response_path,
                    response_key,
                    created_at
                FROM config_lv2_metric
                ORDER BY domain, id
            """
            rows = await conn.fetch(query)

            items = []
            for row in rows:
                # Parse JSONB fields if they come as strings
                agg_params = row["aggregation_params"]
                if isinstance(agg_params, str):
                    agg_params = json.loads(agg_params) if agg_params else None

                resp_key = row["response_key"]
                if isinstance(resp_key, str):
                    resp_key = json.loads(resp_key) if resp_key else None

                items.append(
                    MetricItem(
                        id=row["id"],
                        description=row["description"],
                        source=row["source"],
                        api_list_id=row["api_list_id"],
                        base_metric_id=row["base_metric_id"],
                        aggregation_kind=row["aggregation_kind"],
                        aggregation_params=agg_params,
                        expression=row["expression"],
                        domain=row["domain"],
                        response_path=row["response_path"],
                        response_key=resp_key,
                        created_at=row["created_at"].isoformat() if row["created_at"] else None,
                    )
                )

            logger.info(f"action=get_metrics status=success count={len(items)}")
            return items

    except Exception as e:
        logger.error(f"action=get_metrics status=error error={str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch metrics: {str(e)}"
        )


@router.get("/metricTransforms", response_model=List[MetricTransformItem])
async def get_metric_transforms():
    """
    Get metric transform catalog from config_lv2_metric_transform.

    Returns list of available metric transformations with their configurations.
    """
    try:
        pool = await db_pool.get_pool()
        async with pool.acquire() as conn:
            query = """
                SELECT
                    id,
                    transform_type,
                    description,
                    input_kind,
                    output_kind,
                    params_schema,
                    example_params,
                    version,
                    is_active,
                    created_at
                FROM config_lv2_metric_transform
                ORDER BY transform_type
            """
            rows = await conn.fetch(query)

            items = []
            for row in rows:
                # Parse JSONB fields if they come as strings
                params_schema_val = row["params_schema"]
                if isinstance(params_schema_val, str):
                    params_schema_val = json.loads(params_schema_val) if params_schema_val else None

                example_params_val = row["example_params"]
                if isinstance(example_params_val, str):
                    example_params_val = json.loads(example_params_val) if example_params_val else None

                # Convert version to string if it's an integer
                version_val = row["version"]
                if isinstance(version_val, int):
                    version_val = str(version_val)

                items.append(
                    MetricTransformItem(
                        id=row["id"],
                        transform_type=row["transform_type"],
                        description=row["description"],
                        input_kind=row["input_kind"],
                        output_kind=row["output_kind"],
                        params_schema=params_schema_val,
                        example_params=example_params_val,
                        version=version_val,
                        is_active=row["is_active"],
                        created_at=row["created_at"].isoformat() if row["created_at"] else None,
                    )
                )

            logger.info(f"action=get_metric_transforms status=success count={len(items)}")
            return items

    except Exception as e:
        logger.error(f"action=get_metric_transforms status=error error={str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch metric transforms: {str(e)}"
        )
