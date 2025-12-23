"""Database queries for earning events (evt_earning table)."""

import asyncpg
import json
from typing import List, Dict, Any
from ...services.utils.datetime_utils import parse_to_utc


async def insert_earning_events(
    pool: asyncpg.Pool,
    earning_events: List[Dict[str, Any]]
) -> Dict[str, int]:
    """
    Insert earning events to evt_earning table (insert-only strategy).

    Uses batch insert with ON CONFLICT (ticker, event_date) DO NOTHING.
    Never updates existing records.

    Args:
        pool: Database connection pool
        earning_events: List of earning event dictionaries from FMP calendar

    Returns:
        Dict with insert and conflict counts

    Table columns (never write to id or created_at):
    - id (uuid, PK, DB-generated)
    - ticker (text)
    - event_date (timestamptz)
    - response_key (jsonb)
    - created_at (timestamptz, DB-managed)
    """
    import logging
    logger = logging.getLogger("alsign")

    if not earning_events:
        return {"insert": 0, "conflict": 0}

    # Prepare batch data
    batch_data = []
    skipped_count = 0

    for event in earning_events:
        ticker = event.get('symbol') or event.get('ticker')
        event_date_str = event.get('date')

        if not ticker or not event_date_str:
            skipped_count += 1
            continue

        # Parse event_date to UTC datetime
        try:
            event_date = parse_to_utc(event_date_str)
        except (ValueError, TypeError) as e:
            # Skip events with invalid dates
            logger.warning(f"Skipping earning event for {ticker}: invalid date '{event_date_str}'")
            skipped_count += 1
            continue

        # Build response_key with all event data
        response_key = {
            'epsActual': event.get('epsActual'),
            'epsEstimated': event.get('epsEstimated'),
            'revenueActual': event.get('revenueActual'),
            'revenueEstimated': event.get('revenueEstimated'),
            'time': event.get('time'),
            'updatedFromDate': event.get('updatedFromDate'),
            'fiscalDateEnding': event.get('fiscalDateEnding')
        }

        batch_data.append((
            ticker.upper(),
            event_date,
            json.dumps(response_key)
        ))

    if not batch_data:
        logger.warning(f"No valid earning events to insert ({skipped_count} skipped)")
        return {"insert": 0, "conflict": 0}

    logger.info(f"Inserting {len(batch_data)} earning events in batch ({skipped_count} skipped)")

    # Execute batch insert
    insert_count = 0
    conflict_count = 0

    async with pool.acquire() as conn:
        # Get count before insert
        count_before = await conn.fetchval("SELECT COUNT(*) FROM evt_earning")

        # Batch insert with executemany
        try:
            await conn.executemany(
                """
                INSERT INTO evt_earning (ticker, event_date, response_key)
                VALUES ($1, $2, $3)
                ON CONFLICT (ticker, event_date) DO NOTHING
                """,
                batch_data
            )

            # Get count after insert
            count_after = await conn.fetchval("SELECT COUNT(*) FROM evt_earning")

            insert_count = count_after - count_before
            conflict_count = len(batch_data) - insert_count

            logger.info(f"Batch insert completed: {insert_count} inserted, {conflict_count} conflicts")

        except Exception as e:
            logger.error(f"Batch insert failed: {e}", exc_info=True)
            raise

    return {"insert": insert_count, "conflict": conflict_count}
