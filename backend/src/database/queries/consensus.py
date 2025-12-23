"""Database queries for consensus events (evt_consensus table)."""

import asyncpg
import json
from typing import List, Dict, Any, Tuple
from datetime import datetime
from ...services.utils.datetime_utils import parse_to_utc


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

            result = await conn.execute(
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
                """,
                upd['id'],
                upd.get('price_target_prev'),
                upd.get('price_when_posted_prev'),
                upd.get('direction'),
                json.dumps(response_key_prev) if response_key_prev else None
            )

            if "UPDATE" in result:
                update_count += 1

    return update_count
