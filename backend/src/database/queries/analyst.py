"""Database queries for analyst performance aggregation (config_lv3_analyst table)."""

import asyncpg
import json
from typing import List, Dict, Any, Tuple, Optional


async def select_consensus_events(
    pool: asyncpg.Pool
) -> List[Dict[str, Any]]:
    """
    Select consensus events from txn_events for analyst performance calculation.

    Filters for events where source='consensus' and at least one of
    (analyst_name, analyst_company) is NOT NULL.

    Returns:
        List of event dictionaries with analyst metadata and price_trend
    """
    async with pool.acquire() as conn:
        # Join with evt_consensus to get analyst metadata
        rows = await conn.fetch(
            """
            SELECT
                t.ticker,
                t.event_date,
                t.source,
                t.source_id,
                t.value_qualitative,
                t.price_trend,
                c.analyst_name,
                c.analyst_company,
                c.price_target,
                c.price_when_posted
            FROM txn_events t
            INNER JOIN evt_consensus c ON (
                t.ticker = c.ticker
                AND t.event_date = c.event_date
                AND t.source = 'consensus'
            )
            WHERE (c.analyst_name IS NOT NULL OR c.analyst_company IS NOT NULL)
              AND t.price_trend IS NOT NULL
            ORDER BY c.analyst_name, c.analyst_company, t.event_date
            """
        )

        return [dict(row) for row in rows]


async def upsert_analyst_performance(
    pool: asyncpg.Pool,
    analyst_name: Optional[str],
    analyst_company: Optional[str],
    performance: Dict[str, Any]
) -> int:
    """
    Upsert analyst performance statistics to config_lv3_analyst table.

    Uses generated keys (analyst_name_key, analyst_company_key) for NULL handling.
    Never writes to generated key columns - they are DB-managed.

    Args:
        pool: Database connection pool
        analyst_name: Analyst name (can be None)
        analyst_company: Analyst company (can be None)
        performance: Performance statistics jsonb

    Returns:
        Number of rows upserted (should be 1)

    Table columns (never write to generated keys or timestamps):
    - analyst_name (text, nullable)
    - analyst_company (text, nullable)
    - analyst_name_key (text, GENERATED) -- DB manages: COALESCE(analyst_name, '__NULL__')
    - analyst_company_key (text, GENERATED) -- DB manages: COALESCE(analyst_company, '__NULL__')
    - performance (jsonb)
    - created_at (timestamptz, DB-managed)
    - updated_at (timestamptz, DB-managed)
    """
    async with pool.acquire() as conn:
        # PostgreSQL GENERATED columns are computed automatically
        # We only insert/update the source columns
        result = await conn.execute(
            """
            INSERT INTO config_lv3_analyst (analyst_name, analyst_company, performance)
            VALUES ($1, $2, $3)
            ON CONFLICT (analyst_name_key, analyst_company_key)
            DO UPDATE SET
                performance = EXCLUDED.performance
            """,
            analyst_name,
            analyst_company,
            json.dumps(performance)
        )

        # Parse result to get row count
        if "INSERT" in result or "UPDATE" in result:
            # Extract count from result string (e.g., "INSERT 0 1" or "UPDATE 1")
            parts = result.split()
            if len(parts) >= 2:
                return int(parts[-1])

        return 0


async def get_analyst_groups(
    events: List[Dict[str, Any]]
) -> Dict[Tuple[Optional[str], Optional[str]], List[Dict[str, Any]]]:
    """
    Group events by (analyst_name, analyst_company).

    Args:
        events: List of consensus events

    Returns:
        Dict with (analyst_name, analyst_company) tuple as key, events list as value
    """
    groups = {}

    for event in events:
        analyst_name = event.get('analyst_name')
        analyst_company = event.get('analyst_company')

        key = (analyst_name, analyst_company)

        if key not in groups:
            groups[key] = []

        groups[key].append(event)

    return groups


def calculate_statistics(values: List[float]) -> Dict[str, Any]:
    """
    Calculate statistical metrics for a list of values.

    Args:
        values: List of numeric values

    Returns:
        Dict with mean, median, p25, p75, iqr, stddev, count
    """
    if not values:
        return {
            'mean': None,
            'median': None,
            'p25': None,
            'p75': None,
            'iqr': None,
            'stddev': None,
            'count': 0
        }

    import statistics

    sorted_values = sorted(values)
    count = len(values)

    mean = statistics.mean(values)
    median = statistics.median(values)
    stddev = statistics.stdev(values) if count > 1 else 0

    # Calculate quartiles
    def percentile(data, p):
        """Calculate percentile using linear interpolation."""
        if not data:
            return None
        k = (len(data) - 1) * p
        f = int(k)
        c = f + 1
        if c >= len(data):
            return data[f]
        d0 = data[f]
        d1 = data[c]
        return d0 + (d1 - d0) * (k - f)

    p25 = percentile(sorted_values, 0.25)
    p75 = percentile(sorted_values, 0.75)
    iqr = p75 - p25 if p25 is not None and p75 is not None else None

    return {
        'mean': mean,
        'median': median,
        'p25': p25,
        'p75': p75,
        'iqr': iqr,
        'stddev': stddev,
        'count': count
    }
