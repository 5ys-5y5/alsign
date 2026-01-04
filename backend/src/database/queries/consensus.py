"""Database queries for consensus events (evt_consensus table)."""

import asyncpg
import json
import logging
from typing import List, Dict, Any, Tuple
from datetime import datetime
from ...services.utils.datetime_utils import parse_to_utc

logger = logging.getLogger("alsign")


async def upsert_consensus_phase1(
    pool: asyncpg.Pool,
    consensus_events: List[Dict[str, Any]]
) -> Tuple[Dict[str, int], List[Tuple[str, str, str]]]:
    """
    Phase 1: Upsert raw consensus data to evt_consensus table.

    Uses ON CONFLICT (ticker, event_date, analyst_name, analyst_company) DO UPDATE.
    Does NOT touch Phase 2 fields (price_target_prev, price_when_posted_prev, direction).

    Args:
        pool: Database connection pool
        consensus_events: List of consensus event dictionaries from FMP

    Returns:
        Tuple of (counters dict, affected_partitions list)
        affected_partitions is list of (ticker, analyst_name, analyst_company) tuples

    Table columns (never write to Phase 2 fields or created_at):
    - ticker (text)
    - event_date (timestamptz)
    - analyst_name (text, nullable)
    - analyst_company (text, nullable)
    - price_target (numeric)
    - price_when_posted (numeric)
    - price_target_prev (numeric, nullable) -- Phase 2 only
    - price_when_posted_prev (numeric, nullable) -- Phase 2 only
    - direction (text, nullable) -- Phase 2 only
    - response_key (jsonb)
    - created_at (timestamptz, DB-managed)
    """
    insert_count = 0
    update_count = 0
    affected_partitions = set()

    async with pool.acquire() as conn:
        for event in consensus_events:
            ticker = event.get('symbol') or event.get('ticker')
            if not ticker:
                continue

            analyst_name = event.get('analystName')
            analyst_company = event.get('analystCompany')

            # At least one of (analyst_name, analyst_company) must be non-null
            if analyst_name is None and analyst_company is None:
                continue

            # Track affected partition
            affected_partitions.add((ticker, analyst_name, analyst_company))

            # Parse event_date (publishedDate or eventDate) to UTC datetime
            event_date_str = event.get('publishedDate') or event.get('eventDate')
            if not event_date_str:
                continue

            try:
                event_date = parse_to_utc(event_date_str)
            except (ValueError, TypeError) as e:
                # Skip events with invalid dates
                continue

            # Prepare response_key.last
            response_key_last = {
                'price_target': event.get('priceTarget'),
                'price_when_posted': event.get('priceWhenPosted'),
                'timestamp': event_date_str
            }

            result = await conn.execute(
                """
                INSERT INTO evt_consensus (
                    ticker, event_date, analyst_name, analyst_company,
                    price_target, price_when_posted, response_key
                )
                VALUES ($1, $2, $3, $4, $5, $6, jsonb_build_object('last', $7::jsonb))
                ON CONFLICT (ticker, event_date, analyst_name, analyst_company)
                DO UPDATE SET
                    price_target = EXCLUDED.price_target,
                    price_when_posted = EXCLUDED.price_when_posted,
                    response_key = jsonb_set(
                        COALESCE(evt_consensus.response_key, '{}'::jsonb),
                        '{last}',
                        $7::jsonb
                    )
                """,
                ticker.upper(),
                event_date,
                analyst_name,
                analyst_company,
                event.get('priceTarget'),
                event.get('priceWhenPosted'),
                json.dumps(response_key_last)
            )

            if "INSERT" in result:
                insert_count += 1
            elif "UPDATE" in result:
                update_count += 1

    return (
        {"insert": insert_count, "update": update_count},
        list(affected_partitions)
    )


async def select_partition_events(
    pool: asyncpg.Pool,
    ticker: str,
    analyst_name: str,
    analyst_company: str
) -> List[Dict[str, Any]]:
    """
    Select all events in a partition sorted by event_date DESC.

    Args:
        pool: Database connection pool
        ticker: Ticker symbol
        analyst_name: Analyst name (can be None)
        analyst_company: Analyst company (can be None)

    Returns:
        List of event dictionaries sorted newest first
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, ticker, event_date, analyst_name, analyst_company,
                   price_target, price_when_posted, response_key
            FROM evt_consensus
            WHERE ticker = $1
              AND (analyst_name IS NOT DISTINCT FROM $2)
              AND (analyst_company IS NOT DISTINCT FROM $3)
            ORDER BY event_date DESC
            """,
            ticker,
            analyst_name,
            analyst_company
        )

        return [dict(row) for row in rows]


async def update_consensus_phase2(
    pool: asyncpg.Pool,
    updates: List[Dict[str, Any]]
) -> int:
    """
    Phase 2: Update consensus events with prev values and direction.

    Args:
        pool: Database connection pool
        updates: List of update dictionaries with keys:
                 id, price_target_prev, price_when_posted_prev, direction, response_key_prev

    Returns:
        Number of rows updated
    """
    update_count = 0

    async with pool.acquire() as conn:
        for upd in updates:
            # Build response_key.prev
            response_key_prev = upd.get('response_key_prev')

            result_row = await conn.fetchrow(
                """
                UPDATE evt_consensus
                SET
                    price_target_prev = $2,
                    price_when_posted_prev = $3,
                    direction = $4,
                    response_key = jsonb_set(
                        COALESCE(response_key, '{}'::jsonb),
                        '{prev}',
                        $5::jsonb
                    )
                WHERE id = $1
                RETURNING id, ticker, published_date, analyst_name, analyst_company
                """,
                upd['id'],
                upd.get('price_target_prev'),
                upd.get('price_when_posted_prev'),
                upd.get('direction'),
                json.dumps(response_key_prev) if response_key_prev else None
            )

            if result_row:
                update_count += 1
                logger.info(
                    f"[DB UPDATE] evt_consensus ID={result_row['id']}, "
                    f"ticker={result_row['ticker']}, "
                    f"published_date={result_row['published_date'].date() if result_row['published_date'] else None}, "
                    f"analyst={result_row['analyst_name']} ({result_row['analyst_company']})"
                )

    return update_count


async def calculate_target_summary(
    pool: asyncpg.Pool,
    ticker: str,
    event_date: Any
) -> Dict[str, Any]:
    """
    Calculate target summary from evt_consensus based on event_date.
    
    Aggregates price targets from all analysts for the given ticker
    for periods ending at event_date:
    - lastMonth: within 30 days before event_date
    - lastQuarter: within 90 days before event_date
    - lastYear: within 365 days before event_date
    - allTime: all records before or on event_date
    
    Args:
        pool: Database connection pool
        ticker: Ticker symbol
        event_date: Reference date for calculation
        
    Returns:
        Dict with summary statistics:
        {
            'lastMonthCount': int,
            'lastMonthAvgPriceTarget': float,
            'lastQuarterCount': int,
            'lastQuarterAvgPriceTarget': float,
            'lastYearCount': int,
            'lastYearAvgPriceTarget': float,
            'allTimeCount': int,
            'allTimeAvgPriceTarget': float,
            'publishers': list of analyst companies
        }
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            WITH base_data AS (
                SELECT 
                    price_target,
                    analyst_company,
                    event_date,
                    $2::timestamptz AS ref_date
                FROM evt_consensus
                WHERE ticker = $1
                  AND event_date <= $2::timestamptz
                  AND price_target IS NOT NULL
            )
            SELECT
                -- Last Month (30 days) - Count, Median, Avg
                COUNT(*) FILTER (WHERE event_date > ref_date - INTERVAL '30 days') AS last_month_count,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price_target) 
                    FILTER (WHERE event_date > ref_date - INTERVAL '30 days') AS last_month_median,
                AVG(price_target) FILTER (WHERE event_date > ref_date - INTERVAL '30 days') AS last_month_avg,
                
                -- Last Quarter (90 days) - Count, Median, Avg
                COUNT(*) FILTER (WHERE event_date > ref_date - INTERVAL '90 days') AS last_quarter_count,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price_target) 
                    FILTER (WHERE event_date > ref_date - INTERVAL '90 days') AS last_quarter_median,
                AVG(price_target) FILTER (WHERE event_date > ref_date - INTERVAL '90 days') AS last_quarter_avg,
                
                -- Last Year (365 days) - Count, Median, Avg
                COUNT(*) FILTER (WHERE event_date > ref_date - INTERVAL '365 days') AS last_year_count,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price_target) 
                    FILTER (WHERE event_date > ref_date - INTERVAL '365 days') AS last_year_median,
                AVG(price_target) FILTER (WHERE event_date > ref_date - INTERVAL '365 days') AS last_year_avg,
                
                -- All Time - Count, Median, Avg, Min, Max
                COUNT(*) AS all_time_count,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price_target) AS all_time_median,
                AVG(price_target) AS all_time_avg,
                MIN(price_target) AS all_time_min,
                MAX(price_target) AS all_time_max,
                
                -- Publishers (unique analyst companies)
                ARRAY_AGG(DISTINCT analyst_company) FILTER (WHERE analyst_company IS NOT NULL) AS publishers
            FROM base_data
            """,
            ticker,
            event_date
        )
        
        if not row or row['all_time_count'] == 0:
            logger.debug(f"[calculate_target_summary] No data for ticker={ticker}, event_date={event_date}")
            return None
        
        return {
            # Last Month
            'lastMonthCount': row['last_month_count'] or 0,
            'lastMonthMedianPriceTarget': round(float(row['last_month_median']), 2) if row['last_month_median'] else None,
            'lastMonthAvgPriceTarget': round(float(row['last_month_avg']), 2) if row['last_month_avg'] else None,
            # Last Quarter
            'lastQuarterCount': row['last_quarter_count'] or 0,
            'lastQuarterMedianPriceTarget': round(float(row['last_quarter_median']), 2) if row['last_quarter_median'] else None,
            'lastQuarterAvgPriceTarget': round(float(row['last_quarter_avg']), 2) if row['last_quarter_avg'] else None,
            # Last Year
            'lastYearCount': row['last_year_count'] or 0,
            'lastYearMedianPriceTarget': round(float(row['last_year_median']), 2) if row['last_year_median'] else None,
            'lastYearAvgPriceTarget': round(float(row['last_year_avg']), 2) if row['last_year_avg'] else None,
            # All Time (with Min/Max)
            'allTimeCount': row['all_time_count'] or 0,
            'allTimeMedianPriceTarget': round(float(row['all_time_median']), 2) if row['all_time_median'] else None,
            'allTimeAvgPriceTarget': round(float(row['all_time_avg']), 2) if row['all_time_avg'] else None,
            'allTimeMinPriceTarget': round(float(row['all_time_min']), 2) if row['all_time_min'] else None,
            'allTimeMaxPriceTarget': round(float(row['all_time_max']), 2) if row['all_time_max'] else None,
            # Publishers
            'publishers': row['publishers'] or []
        }


async def get_events_for_target_summary(
    pool: asyncpg.Pool,
    overwrite: bool,
    calc_scope: str = None,
    tickers_param: str = None,
    from_date: Any = None,
    to_date: Any = None
) -> List[Dict[str, Any]]:
    """
    Get evt_consensus events that need target_summary calculation.
    
    Args:
        pool: Database connection pool
        overwrite: If True, return all matching events. If False, only NULL target_summary.
        calc_scope: 'all', 'ticker', 'event_date_range'
        tickers_param: Comma-separated tickers (for calc_scope=ticker)
        from_date: Start date (for calc_scope=event_date_range)
        to_date: End date (for calc_scope=event_date_range)
    
    Returns:
        List of events needing target_summary calculation
    """
    async with pool.acquire() as conn:
        # Build WHERE clause
        conditions = []
        params = []
        param_idx = 1
        
        if not overwrite:
            conditions.append("target_summary IS NULL")
        
        if calc_scope == 'ticker' and tickers_param:
            ticker_list = [t.strip().upper() for t in tickers_param.split(',')]
            conditions.append(f"ticker = ANY(${param_idx})")
            params.append(ticker_list)
            param_idx += 1
        elif calc_scope == 'event_date_range' and from_date and to_date:
            conditions.append(f"event_date::date BETWEEN ${param_idx} AND ${param_idx + 1}")
            params.extend([from_date, to_date])
            param_idx += 2
        
        where_clause = " AND ".join(conditions) if conditions else "TRUE"
        
        query = f"""
            SELECT id, ticker, event_date
            FROM evt_consensus
            WHERE {where_clause}
            ORDER BY ticker, event_date
        """
        
        rows = await conn.fetch(query, *params)
        return [dict(row) for row in rows]


async def update_target_summary_batch(
    pool: asyncpg.Pool,
    updates: List[Dict[str, Any]]
) -> int:
    """
    Batch update target_summary for multiple evt_consensus rows.
    
    Args:
        pool: Database connection pool
        updates: List of {id, target_summary} dicts
    
    Returns:
        Number of rows updated
    """
    if not updates:
        return 0
    
    async with pool.acquire() as conn:
        # Use UNNEST for batch update
        ids = [u['id'] for u in updates]
        summaries = [json.dumps(u['target_summary']) if u['target_summary'] else None for u in updates]
        
        updated_rows = await conn.fetch(
            """
            UPDATE evt_consensus AS e
            SET target_summary = u.summary::jsonb
            FROM UNNEST($1::uuid[], $2::text[]) AS u(id, summary)
            WHERE e.id = u.id
            RETURNING e.id, e.ticker, e.published_date, e.analyst_name, e.analyst_company
            """,
            ids,
            summaries
        )

        # Log updated rows
        if updated_rows:
            logger.info(f"[DB UPDATE] Updated {len(updated_rows)} evt_consensus target_summary rows:")
            for row in updated_rows:
                logger.info(
                    f"  - ID={row['id']}, ticker={row['ticker']}, "
                    f"published_date={row['published_date'].date() if row['published_date'] else None}, "
                    f"analyst={row['analyst_name']} ({row['analyst_company']})"
                )

        return len(updated_rows)