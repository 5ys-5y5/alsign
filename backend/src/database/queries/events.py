"""Database queries for event consolidation (txn_events table)."""

import asyncpg
from typing import List, Dict, Any, Tuple


async def discover_evt_tables(
    pool: asyncpg.Pool,
    schema: str = "public",
    table_filter: List[str] = None
) -> List[str]:
    """
    Discover evt_* tables in specified schema.

    Args:
        pool: Database connection pool
        schema: Target schema name
        table_filter: Optional list of specific table names to include

    Returns:
        List of table names matching evt_* pattern
    """
    async with pool.acquire() as conn:
        if table_filter:
            # Validate all tables exist and match pattern
            tables = await conn.fetch(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = $1
                  AND table_name = ANY($2)
                  AND table_name LIKE 'evt_%'
                ORDER BY table_name
                """,
                schema,
                table_filter
            )
        else:
            # Auto-discover all evt_* tables
            tables = await conn.fetch(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = $1
                  AND table_name LIKE 'evt_%'
                ORDER BY table_name
                """,
                schema
            )

        return [row['table_name'] for row in tables]


async def validate_schema_exists(pool: asyncpg.Pool, schema: str) -> bool:
    """
    Check if schema exists.

    Args:
        pool: Database connection pool
        schema: Schema name to validate

    Returns:
        True if schema exists, False otherwise
    """
    async with pool.acquire() as conn:
        result = await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.schemata
                WHERE schema_name = $1
            )
            """,
            schema
        )
        return result


async def select_events_from_table(
    pool: asyncpg.Pool,
    table_name: str,
    schema: str = "public"
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Extract events from a specific evt_* table.

    Required columns: id, ticker, event_date
    Optional columns tracked but not required

    Args:
        pool: Database connection pool
        table_name: Name of evt_* table
        schema: Schema name

    Returns:
        Tuple of (events list, warnings list)
    """
    warnings = []

    async with pool.acquire() as conn:
        # Check required columns exist
        columns = await conn.fetch(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = $1
              AND table_name = $2
            """,
            schema,
            table_name
        )

        column_names = {row['column_name'] for row in columns}
        required_columns = {'id', 'ticker', 'event_date'}

        if not required_columns.issubset(column_names):
            missing = required_columns - column_names
            warnings.append(f"MISSING_REQUIRED_COLUMNS: {', '.join(missing)}")
            return [], warnings

        # Extract events
        events = await conn.fetch(
            f"""
            SELECT id, ticker, event_date
            FROM {schema}.{table_name}
            WHERE ticker IS NOT NULL
              AND event_date IS NOT NULL
            ORDER BY ticker, event_date
            """
        )

        # Extract source name from table name (evt_consensus -> consensus)
        source = table_name.replace('evt_', '')

        event_list = [
            {
                'ticker': row['ticker'],
                'event_date': row['event_date'],
                'source': source,
                'source_id': str(row['id'])  # Convert UUID to string for asyncpg
            }
            for row in events
        ]

        return event_list, warnings


async def upsert_txn_events(
    pool: asyncpg.Pool,
    events: List[Dict[str, Any]]
) -> Dict[str, int]:
    """
    Insert events into txn_events table using batch insert.

    Uses ON CONFLICT (ticker, event_date, source, source_id) DO NOTHING.

    Args:
        pool: Database connection pool
        events: List of event dictionaries with ticker, event_date, source, source_id

    Returns:
        Dict with insert and conflict counts

    Table columns (never write to created_at, updated_at):
    - ticker (text)
    - event_date (timestamptz)
    - source (text)
    - source_id (uuid)
    - sector (text, nullable) -- enriched separately
    - industry (text, nullable) -- enriched separately
    - created_at (timestamptz, DB-managed)
    - updated_at (timestamptz, DB-managed)
    """
    import logging
    logger = logging.getLogger("alsign")

    if not events:
        return {"insert": 0, "conflict": 0}

    logger.info(f"Inserting {len(events)} events into txn_events in batch")

    # Prepare batch data
    batch_data = [
        (event['ticker'], event['event_date'], event['source'], event['source_id'])
        for event in events
    ]

    insert_count = 0
    conflict_count = 0

    async with pool.acquire() as conn:
        # Get count before insert
        count_before = await conn.fetchval("SELECT COUNT(*) FROM txn_events")

        # Batch insert with executemany
        try:
            await conn.executemany(
                """
                INSERT INTO txn_events (ticker, event_date, source, source_id)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (ticker, event_date, source, source_id) DO NOTHING
                """,
                batch_data
            )

            # Get count after insert
            count_after = await conn.fetchval("SELECT COUNT(*) FROM txn_events")

            insert_count = count_after - count_before
            conflict_count = len(batch_data) - insert_count

            logger.info(f"Batch insert completed: {insert_count} inserted, {conflict_count} conflicts")

        except Exception as e:
            logger.error(f"Batch insert failed: {e}", exc_info=True)
            raise

    return {"insert": insert_count, "conflict": conflict_count}


async def update_sector_industry(
    pool: asyncpg.Pool,
    overwrite: bool = False
) -> Dict[str, int]:
    """
    Enrich txn_events with sector/industry from config_lv3_targets.

    Args:
        pool: Database connection pool
        overwrite: If False, update only NULL values. If True, update NULL + mismatched values.

    Returns:
        Dict with update counts:
        - updated_null: Rows where sector/industry were NULL
        - updated_mismatch: Rows where sector/industry were non-NULL but different
        - skipped_no_target: Rows with no matching ticker in targets
    """
    async with pool.acquire() as conn:
        if overwrite:
            # Update both NULL and mismatched values
            result = await conn.fetch(
                """
                WITH updates AS (
                    UPDATE txn_events e
                    SET sector = t.sector,
                        industry = t.industry
                    FROM config_lv3_targets t
                    WHERE e.ticker = t.ticker
                      AND (
                          e.sector IS NULL
                          OR e.industry IS NULL
                          OR e.sector != t.sector
                          OR e.industry != t.industry
                      )
                    RETURNING
                        CASE WHEN e.sector IS NULL OR e.industry IS NULL THEN 1 ELSE 0 END as was_null,
                        CASE WHEN e.sector IS NOT NULL AND e.industry IS NOT NULL THEN 1 ELSE 0 END as was_mismatch
                )
                SELECT
                    SUM(was_null) as updated_null,
                    SUM(was_mismatch) as updated_mismatch
                FROM updates
                """
            )
        else:
            # Update only NULL values
            result = await conn.fetch(
                """
                WITH updates AS (
                    UPDATE txn_events e
                    SET sector = t.sector,
                        industry = t.industry
                    FROM config_lv3_targets t
                    WHERE e.ticker = t.ticker
                      AND (e.sector IS NULL OR e.industry IS NULL)
                    RETURNING 1
                )
                SELECT COUNT(*) as updated_null
                FROM updates
                """
            )

        # Get count of rows with no matching target
        no_target = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM txn_events e
            WHERE NOT EXISTS (
                SELECT 1 FROM config_lv3_targets t WHERE t.ticker = e.ticker
            )
            """
        )

        if overwrite and result and result[0]:
            return {
                "updated_null": int(result[0]['updated_null'] or 0),
                "updated_mismatch": int(result[0]['updated_mismatch'] or 0),
                "skipped_no_target": int(no_target or 0)
            }
        elif result and result[0]:
            return {
                "updated_null": int(result[0]['updated_null'] or 0),
                "updated_mismatch": 0,
                "skipped_no_target": int(no_target or 0)
            }
        else:
            return {
                "updated_null": 0,
                "updated_mismatch": 0,
                "skipped_no_target": int(no_target or 0)
            }


async def select_invalid_ticker_events(
    pool: asyncpg.Pool
) -> Dict[str, Any]:
    """
    Preview invalid ticker events (tickers not in config_lv3_targets).

    Returns:
        Dict with:
        - total_count: Total number of invalid events
        - ticker_counts: List of {ticker, count} for each invalid ticker
        - sample_events: Sample of 10 events to be deleted
    """
    import logging
    logger = logging.getLogger("alsign")

    async with pool.acquire() as conn:
        # Get invalid ticker counts
        ticker_counts = await conn.fetch(
            """
            SELECT
                e.ticker,
                COUNT(*) as event_count
            FROM txn_events e
            WHERE NOT EXISTS (
                SELECT 1 FROM config_lv3_targets t WHERE t.ticker = e.ticker
            )
            GROUP BY e.ticker
            ORDER BY event_count DESC
            """
        )

        # Get sample events
        sample_events = await conn.fetch(
            """
            SELECT
                id, ticker, event_date, source, source_id
            FROM txn_events e
            WHERE NOT EXISTS (
                SELECT 1 FROM config_lv3_targets t WHERE t.ticker = e.ticker
            )
            LIMIT 10
            """
        )

        total_count = sum(row['event_count'] for row in ticker_counts)

        logger.info(f"[Preview] Found {total_count} invalid events across {len(ticker_counts)} tickers")

        return {
            'total_count': total_count,
            'ticker_counts': [
                {
                    'ticker': row['ticker'],
                    'count': int(row['event_count'])
                }
                for row in ticker_counts
            ],
            'sample_events': [
                {
                    'id': str(row['id']),
                    'ticker': row['ticker'],
                    'event_date': row['event_date'].isoformat() if row['event_date'] else None,
                    'source': row['source'],
                    'source_id': str(row['source_id'])
                }
                for row in sample_events
            ]
        }


async def create_archived_table_if_not_exists(
    pool: asyncpg.Pool
) -> bool:
    """
    Create txn_events_archived table if it doesn't exist.

    Table structure matches txn_events plus archived_at timestamp.

    Returns:
        True if table was created, False if it already existed
    """
    import logging
    logger = logging.getLogger("alsign")

    async with pool.acquire() as conn:
        # Check if table exists
        exists = await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name = 'txn_events_archived'
            )
            """
        )

        if exists:
            logger.info("[Archive] txn_events_archived table already exists")
            return False

        # Create table with same structure as txn_events plus archived_at
        await conn.execute(
            """
            CREATE TABLE txn_events_archived (
                id UUID NOT NULL,
                ticker TEXT NOT NULL,
                event_date TIMESTAMPTZ NOT NULL,
                sector TEXT,
                industry TEXT,
                source TEXT NOT NULL,
                source_id TEXT NOT NULL,
                value_quantitative JSONB,
                position_quantitative position,
                disparity_quantitative NUMERIC,
                value_qualitative JSONB,
                position_qualitative position,
                disparity_qualitative NUMERIC,
                price_trend JSONB,
                analyst_performance JSONB,
                condition TEXT,
                created_at TIMESTAMPTZ NOT NULL,
                price_quantitative NUMERIC,
                peer_quantitative JSONB,
                position position,
                archived_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                archived_reason TEXT DEFAULT 'invalid_ticker_not_in_targets',
                CONSTRAINT txn_events_archived_pkey PRIMARY KEY (id)
            )
            """
        )

        # Create indexes for performance
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_archived_ticker ON txn_events_archived(ticker)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_archived_date ON txn_events_archived(archived_at)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_archived_reason ON txn_events_archived(archived_reason)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_archived_event_date ON txn_events_archived(event_date)"
        )

        logger.info("[Archive] Created txn_events_archived table with indexes")
        return True


async def archive_invalid_ticker_events(
    pool: asyncpg.Pool
) -> Dict[str, int]:
    """
    Archive invalid ticker events to txn_events_archived and delete from txn_events.

    Uses transaction to ensure atomicity (both INSERT and DELETE succeed or both fail).

    Returns:
        Dict with archived and deleted counts
    """
    import logging
    logger = logging.getLogger("alsign")

    # Ensure archived table exists
    await create_archived_table_if_not_exists(pool)

    async with pool.acquire() as conn:
        # Use transaction for atomicity
        async with conn.transaction():
            # First, check how many invalid events exist
            invalid_count = await conn.fetchval(
                """
                SELECT COUNT(*)
                FROM txn_events e
                WHERE NOT EXISTS (
                    SELECT 1 FROM config_lv3_targets t WHERE t.ticker = e.ticker
                )
                """
            )

            logger.info(f"[Archive] Found {invalid_count} invalid ticker events to archive")

            if invalid_count == 0:
                logger.info("[Archive] No invalid ticker events found")
                return {
                    'archived': 0,
                    'deleted': 0
                }

            # Copy invalid events to archived table
            archived_rows = await conn.fetch(
                """
                WITH invalid_events AS (
                    SELECT e.*
                    FROM txn_events e
                    WHERE NOT EXISTS (
                        SELECT 1 FROM config_lv3_targets t WHERE t.ticker = e.ticker
                    )
                )
                INSERT INTO txn_events_archived (
                    id, ticker, event_date, sector, industry,
                    source, source_id,
                    value_quantitative, position_quantitative, disparity_quantitative,
                    value_qualitative, position_qualitative, disparity_qualitative,
                    price_trend, analyst_performance, condition,
                    created_at,
                    price_quantitative, peer_quantitative, position,
                    archived_at, archived_reason
                )
                SELECT
                    id, ticker, event_date, sector, industry,
                    source, source_id,
                    value_quantitative, position_quantitative, disparity_quantitative,
                    value_qualitative, position_qualitative, disparity_qualitative,
                    price_trend, analyst_performance, condition,
                    created_at,
                    price_quantitative, peer_quantitative, position,
                    NOW(), 'invalid_ticker_not_in_targets'
                FROM invalid_events
                RETURNING id, ticker
                """
            )

            archived_count = len(archived_rows)
            logger.info(f"[Archive] Inserted {archived_count} rows into txn_events_archived")

            # Delete from txn_events
            deleted_count = await conn.fetchval(
                """
                DELETE FROM txn_events e
                WHERE NOT EXISTS (
                    SELECT 1 FROM config_lv3_targets t WHERE t.ticker = e.ticker
                )
                """
            )

            deleted_count = int(deleted_count.split()[-1]) if isinstance(deleted_count, str) and "DELETE" in deleted_count else 0

            logger.info(f"[Archive] Archived {archived_count} events, deleted {deleted_count} from txn_events")

            return {
                'archived': archived_count if archived_count else 0,
                'deleted': deleted_count
            }


async def delete_invalid_ticker_events(
    pool: asyncpg.Pool
) -> int:
    """
    Permanently delete invalid ticker events from txn_events.

    WARNING: This is a destructive operation with no recovery.

    Returns:
        Number of rows deleted
    """
    import logging
    logger = logging.getLogger("alsign")

    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            DELETE FROM txn_events e
            WHERE NOT EXISTS (
                SELECT 1 FROM config_lv3_targets t WHERE t.ticker = e.ticker
            )
            """
        )

        # Parse result to get row count
        if "DELETE" in result:
            count = int(result.split()[-1])
            logger.info(f"[Delete] Permanently deleted {count} invalid ticker events")
            return count

        return 0
