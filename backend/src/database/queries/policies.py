"""Database queries for policy configuration (config_lv0_policy table)."""

import asyncpg
import json
from typing import Dict, Any, Optional


async def select_policy(
    pool: asyncpg.Pool,
    function_name: str
) -> Optional[Dict[str, Any]]:
    """
    Select policy configuration by function name.

    Args:
        pool: Database connection pool
        function_name: Policy function name (e.g., 'fillPriceTrend_dateRange')

    Returns:
        Policy dictionary or None if not found
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT function, policy, description
            FROM config_lv0_policy
            WHERE function = $1
            """,
            function_name
        )

        if not row:
            return None

        return {
            'function': row['function'],
            'policy': parse_policy_json(row['policy']),
            'description': row['description']
        }


def parse_policy_json(policy_value: Any) -> Dict[str, Any]:
    """
    Parse policy value to dictionary.

    Args:
        policy_value: Policy value (jsonb, json string, or dict)

    Returns:
        Parsed policy dictionary
    """
    if policy_value is None:
        return {}

    if isinstance(policy_value, dict):
        return policy_value

    if isinstance(policy_value, str):
        try:
            return json.loads(policy_value)
        except json.JSONDecodeError:
            return {}

    return {}


async def get_price_trend_range_policy(pool: asyncpg.Pool) -> Dict[str, int]:
    """
    Get price trend date range policy (countStart, countEnd).

    Args:
        pool: Database connection pool

    Returns:
        Dict with countStart and countEnd

    Raises:
        ValueError: If policy not found or invalid
    """
    policy = await select_policy(pool, 'fillPriceTrend_dateRange')

    if not policy:
        raise ValueError("Policy 'fillPriceTrend_dateRange' not found in config_lv0_policy")

    policy_config = policy['policy']

    if 'countStart' not in policy_config or 'countEnd' not in policy_config:
        raise ValueError("Policy 'fillPriceTrend_dateRange' missing countStart or countEnd")

    return {
        'countStart': int(policy_config['countStart']),
        'countEnd': int(policy_config['countEnd'])
    }


async def get_ohlc_fetch_policy(pool: asyncpg.Pool) -> Dict[str, Any]:
    """
    Get OHLC fetch policy configuration.

    Args:
        pool: Database connection pool

    Returns:
        Dict with OHLC fetch policy settings

    Raises:
        ValueError: If policy not found
    """
    policy = await select_policy(pool, 'priceEodOHLC_dateRange')

    if not policy:
        # Use default policy if not found
        return {
            'batchByTicker': True,
            'cacheDuration': 3600
        }

    return policy['policy']
