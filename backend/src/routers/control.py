"""Router for control panel and data management endpoints."""

import logging
import json
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Request
from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field

from ..database.connection import db_pool
from ..config import settings
from ..utils.logging_utils import log_error, log_warning

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
        log_error(logger, "Failed to fetch API services", exception=e)
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
        log_error(logger, "Failed to update API service", exception=e)
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
        log_error(logger, "Failed to fetch runtime info", exception=e)
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
        log_error(logger, "Failed to fetch API list", exception=e)
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch API list: {str(e)}"
        )


class APIListUpdate(BaseModel):
    """API list item update."""
    api_service: Optional[str] = None
    api: Optional[str] = None
    schema: Optional[Union[Dict[str, Any], str]] = None
    endpoint: Optional[str] = None
    function2: Optional[str] = None


class APITestResult(BaseModel):
    """API test result."""
    success: bool
    status_code: Optional[int] = None
    response_sample: Optional[Any] = None
    response_keys: Optional[List[str]] = None
    error: Optional[str] = None
    elapsed_ms: Optional[int] = None


@router.put("/apiList/{api_id}")
async def update_api_list_item(api_id: str, update: APIListUpdate):
    """
    Update API list item configuration.
    Only updates provided fields (partial update).
    """
    try:
        pool = await db_pool.get_pool()
        async with pool.acquire() as conn:
            # Build update query dynamically
            updates = []
            params = []
            param_count = 1

            if update.api_service is not None:
                updates.append(f'api_service = ${param_count}')
                params.append(update.api_service)
                param_count += 1

            if update.api is not None:
                updates.append(f'api = ${param_count}')
                params.append(update.api)
                param_count += 1

            if update.schema is not None:
                updates.append(f'schema = ${param_count}::jsonb')
                schema_val = json.dumps(update.schema) if isinstance(update.schema, dict) else update.schema
                params.append(schema_val)
                param_count += 1

            if update.endpoint is not None:
                updates.append(f'endpoint = ${param_count}')
                params.append(update.endpoint)
                param_count += 1

            if update.function2 is not None:
                updates.append(f'function2 = ${param_count}')
                params.append(update.function2)
                param_count += 1

            if not updates:
                raise HTTPException(status_code=400, detail="No fields to update")

            params.append(api_id)

            query = f"""
                UPDATE config_lv1_api_list
                SET {', '.join(updates)}
                WHERE id = ${param_count}
                RETURNING id
            """

            result = await conn.fetchval(query, *params)

            if not result:
                raise HTTPException(status_code=404, detail=f"API '{api_id}' not found")

            logger.info(f"action=update_api_list status=success id={api_id}")
            return {"status": "updated", "id": api_id}

    except HTTPException:
        raise
    except Exception as e:
        log_error(logger, "Failed to update API list", exception=e)
        raise HTTPException(status_code=500, detail=f"Failed to update API: {str(e)}")


@router.post("/apiList/{api_id}/test", response_model=APITestResult)
async def test_api_endpoint(api_id: str, test_params: Optional[Dict[str, Any]] = None):
    """
    Test an API endpoint and validate response keys.
    
    Args:
        api_id: The API ID from config_lv1_api_list
        test_params: Optional parameters to send with the API call (e.g., {"ticker": "AAPL"})
    
    Returns:
        Test result with response sample and available keys.
    """
    import time
    from ..services.external_api import FMPAPIClient
    
    try:
        pool = await db_pool.get_pool()
        
        # Get API configuration
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM config_lv1_api_list WHERE id = $1",
                api_id
            )
            
            if not row:
                raise HTTPException(status_code=404, detail=f"API '{api_id}' not found")
        
        # Prepare test parameters
        params = test_params or {}
        if 'ticker' not in params:
            params['ticker'] = 'AAPL'  # Default test ticker
        
        # Call the API
        start_time = time.time()
        try:
            api_client = FMPAPIClient()
            response = await api_client.call_api(api_id, params)
            elapsed_ms = int((time.time() - start_time) * 1000)
            
            # Extract response keys
            response_keys = []
            response_sample = None
            
            if isinstance(response, list) and len(response) > 0:
                response_sample = response[0] if len(response) == 1 else response[:2]
                if isinstance(response[0], dict):
                    response_keys = list(response[0].keys())
            elif isinstance(response, dict):
                response_sample = response
                response_keys = list(response.keys())
            
            logger.info(f"action=test_api status=success id={api_id} elapsed_ms={elapsed_ms}")
            
            return APITestResult(
                success=True,
                status_code=200,
                response_sample=response_sample,
                response_keys=response_keys,
                elapsed_ms=elapsed_ms
            )
            
        except Exception as api_error:
            elapsed_ms = int((time.time() - start_time) * 1000)
            error_msg = str(api_error)

            log_warning(logger, f"API test failed for {api_id}: {error_msg}")

            return APITestResult(
                success=False,
                error=error_msg,
                elapsed_ms=elapsed_ms
            )
    
    except HTTPException:
        raise
    except Exception as e:
        log_error(logger, f"Failed to test API {api_id}", exception=e)
        raise HTTPException(status_code=500, detail=f"Failed to test API: {str(e)}")


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
        log_error(logger, "Failed to fetch metrics", exception=e)
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch metrics: {str(e)}"
        )


class MetricApiUpdate(BaseModel):
    """Update api_list_id for a metric."""
    api_list_id: str
    required_keys: Optional[List[str]] = None  # Keys that must exist in API response


class MetricApiUpdateResult(BaseModel):
    """Result of metric API update."""
    success: bool
    metric_id: str
    old_api_list_id: Optional[str]
    new_api_list_id: str
    validation_result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


@router.put("/metrics/{metric_id}/apiListId", response_model=MetricApiUpdateResult)
async def update_metric_api_list_id(metric_id: str, update: MetricApiUpdate):
    """
    Update the api_list_id for a metric with validation.
    
    1. Tests the new API to ensure it returns valid data
    2. Validates that required_keys exist in the API response
    3. Updates config_lv2_metric if validation passes
    
    Args:
        metric_id: The metric ID to update
        update: Contains new api_list_id and optional required_keys for validation
    
    Returns:
        Update result with validation details
    """
    import time
    from ..services.external_api import FMPAPIClient
    
    try:
        pool = await db_pool.get_pool()
        
        # Get current metric configuration
        async with pool.acquire() as conn:
            metric_row = await conn.fetchrow(
                """SELECT id, api_list_id, response_key, response_path 
                   FROM config_lv2_metric WHERE id = $1""",
                metric_id
            )
            
            if not metric_row:
                raise HTTPException(status_code=404, detail=f"Metric '{metric_id}' not found")
            
            old_api_list_id = metric_row["api_list_id"]
            
            # Check if new API exists
            api_row = await conn.fetchrow(
                "SELECT id, schema FROM config_lv1_api_list WHERE id = $1",
                update.api_list_id
            )
            
            if not api_row:
                raise HTTPException(
                    status_code=404, 
                    detail=f"API '{update.api_list_id}' not found in config_lv1_api_list"
                )
        
        # Test the new API
        start_time = time.time()
        try:
            api_client = FMPAPIClient()
            response = await api_client.call_api(update.api_list_id, {'ticker': 'AAPL'})
            elapsed_ms = int((time.time() - start_time) * 1000)
            
            # Extract response keys
            response_keys = []
            if isinstance(response, list) and len(response) > 0:
                if isinstance(response[0], dict):
                    response_keys = list(response[0].keys())
            elif isinstance(response, dict):
                response_keys = list(response.keys())
            
            # Validate required keys
            required_keys = update.required_keys or []
            missing_keys = [k for k in required_keys if k not in response_keys]
            
            validation_result = {
                'api_tested': True,
                'elapsed_ms': elapsed_ms,
                'available_keys': response_keys,
                'required_keys': required_keys,
                'missing_keys': missing_keys,
                'valid': len(missing_keys) == 0
            }
            
            if missing_keys:
                log_warning(
                    logger,
                    f"Metric API validation failed: missing required keys {missing_keys}",
                    metric_id=metric_id
                )
                return MetricApiUpdateResult(
                    success=False,
                    metric_id=metric_id,
                    old_api_list_id=old_api_list_id,
                    new_api_list_id=update.api_list_id,
                    validation_result=validation_result,
                    error=f"Missing required keys: {missing_keys}"
                )
            
            # Update metric with new api_list_id
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE config_lv2_metric SET api_list_id = $1 WHERE id = $2",
                    update.api_list_id,
                    metric_id
                )
            
            logger.info(
                f"action=update_metric_api status=success "
                f"metric={metric_id} old_api={old_api_list_id} new_api={update.api_list_id}"
            )
            
            return MetricApiUpdateResult(
                success=True,
                metric_id=metric_id,
                old_api_list_id=old_api_list_id,
                new_api_list_id=update.api_list_id,
                validation_result=validation_result
            )
            
        except Exception as api_error:
            elapsed_ms = int((time.time() - start_time) * 1000)
            error_msg = str(api_error)

            log_warning(
                logger,
                f"API test failed for metric {metric_id}: {error_msg}"
            )

            return MetricApiUpdateResult(
                success=False,
                metric_id=metric_id,
                old_api_list_id=old_api_list_id,
                new_api_list_id=update.api_list_id,
                validation_result={
                    'api_tested': True,
                    'elapsed_ms': elapsed_ms,
                    'error': error_msg
                },
                error=f"API test failed: {error_msg}"
            )
    
    except HTTPException:
        raise
    except Exception as e:
        log_error(logger, "Failed to update metric API", exception=e)
        raise HTTPException(status_code=500, detail=f"Failed to update metric: {str(e)}")


@router.get("/endpointApiConfig")
async def get_endpoint_api_config():
    """
    Get endpoint-to-API mapping configuration.
    
    Returns a structured view of which APIs are used by each endpoint/mode.
    """
    try:
        pool = await db_pool.get_pool()
        async with pool.acquire() as conn:
            # Get all metrics with their api_list_id
            metrics = await conn.fetch("""
                SELECT id, api_list_id, domain, response_key, description
                FROM config_lv2_metric
                WHERE api_list_id IS NOT NULL
                ORDER BY domain, id
            """)
            
            # Get all available APIs
            apis = await conn.fetch("""
                SELECT id, api_service, api, endpoint
                FROM config_lv1_api_list
                ORDER BY api_service, id
            """)
        
        # Build endpoint configuration
        endpoint_config = {
            'sourceData': {
                'description': 'GET /sourceData - 외부 API 데이터 수집',
                'modes': {
                    'holiday': {
                        'description': '시장 휴장일 수집',
                        'apis': [{'id': 'fmp-market-holidays', 'required_keys': ['year', 'date', 'exchange']}]
                    },
                    'consensus': {
                        'description': '애널리스트 컨센서스 수집',
                        'apis': [{'id': 'fmp-price-target', 'required_keys': ['symbol', 'priceTarget', 'priceWhenPosted', 'analystName', 'analystCompany']}]
                    },
                    'earning': {
                        'description': '실적 발표 수집',
                        'apis': [{'id': 'fmp-earning-call-transcript', 'required_keys': ['symbol', 'date', 'content']}]
                    }
                }
            },
            'backfillEventsTable': {
                'description': 'POST /backfillEventsTable - Valuation 메트릭 계산',
                'phases': {
                    'financial': {
                        'description': '재무제표 메트릭 계산',
                        'metrics': [],
                        'apis': []
                    },
                    'market': {
                        'description': '시장 데이터 메트릭 계산',
                        'metrics': [],
                        'apis': []
                    },
                    'price': {
                        'description': '가격 추세 계산',
                        'apis': [{'id': 'fmp-historical-price-eod-full', 'required_keys': ['date', 'open', 'high', 'low', 'close']}]
                    }
                }
            }
        }
        
        # Group metrics by their API
        for metric in metrics:
            api_id = metric['api_list_id']
            domain = metric['domain'] or 'unknown'
            
            # Determine which phase this belongs to
            if 'income' in api_id.lower() or 'balance' in api_id.lower() or 'cash' in api_id.lower():
                phase_key = 'financial'
            elif 'market' in api_id.lower() or 'quote' in api_id.lower():
                phase_key = 'market'
            else:
                phase_key = 'financial'
            
            if phase_key in endpoint_config['backfillEventsTable']['phases']:
                phase = endpoint_config['backfillEventsTable']['phases'][phase_key]
                if api_id not in [a['id'] for a in phase['apis']]:
                    phase['apis'].append({'id': api_id, 'required_keys': []})
                phase['metrics'].append({
                    'id': metric['id'],
                    'api_list_id': api_id,
                    'domain': domain
                })
        
        # Add available APIs list
        available_apis = [
            {'id': api['id'], 'service': api['api_service'], 'name': api['api'], 'endpoint': api['endpoint']}
            for api in apis
        ]
        
        return {
            'endpoints': endpoint_config,
            'availableApis': available_apis,
            'metricsWithApi': [dict(m) for m in metrics]
        }
    
    except Exception as e:
        log_error(logger, "Failed to get endpoint API config", exception=e)
        raise HTTPException(status_code=500, detail=str(e))


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
        log_error(logger, "Failed to fetch metric transforms", exception=e)
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch metric transforms: {str(e)}"
        )
