"""Database queries for API configuration (config_lv1_api_list, config_lv1_api_service)."""

import logging
import json
from typing import Dict, Any, Optional
from asyncpg import Pool

logger = logging.getLogger("alsign")


async def get_api_config_by_id(pool: Pool, api_id: str) -> Optional[Dict[str, Any]]:
    """
    Get API configuration from config_lv1_api_list by ID.

    Args:
        pool: Database connection pool
        api_id: API identifier (e.g., 'fmp-company-screener')

    Returns:
        Dict with api, schema, api_service or None if not found
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, api_service, api, schema, endpoint, function2
            FROM config_lv1_api_list
            WHERE id = $1
            """,
            api_id
        )

        if not row:
            logger.warning(f"API config not found: {api_id}")
            return None

        result = dict(row)

        # Parse JSONB schema field if it's a string
        if result.get('schema') and isinstance(result['schema'], str):
            result['schema'] = json.loads(result['schema'])

        return result


async def get_api_service_config(pool: Pool, service_name: str) -> Optional[Dict[str, Any]]:
    """
    Get API service configuration from config_lv1_api_service.

    Args:
        pool: Database connection pool
        service_name: Service name (e.g., 'financialmodelingprep')

    Returns:
        Dict with apiKey, usagePerMin or None if not found
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT api_service, "apiKey", "usagePerMin"
            FROM config_lv1_api_service
            WHERE api_service = $1
            """,
            service_name
        )

        if not row:
            logger.warning(f"API service config not found: {service_name}")
            return None

        return dict(row)
