"""Service for POST /setEventsTable endpoint - consolidates events from evt_* tables."""

import logging
import time
from typing import Dict, Any, List

from ..database.connection import db_pool
from ..database.queries import events
from ..models.response_models import TableProcessingResult

logger = logging.getLogger("alsign")


async def consolidate_events(
    overwrite: bool = False,
    dry_run: bool = False,
    schema: str = "public",
    table_filter: List[str] = None
) -> Dict[str, Any]:
    """
    Consolidate events from evt_* tables into txn_events.

    Phase 1: Auto-discover evt_* tables (or use provided filter)
    Phase 2: Extract events from each table
    Phase 3: Insert into txn_events with ON CONFLICT DO NOTHING
    Phase 4: Enrich with sector/industry from config_lv3_targets

    Args:
        overwrite: If False, update only NULL sector/industry. If True, update NULL + mismatched.
        dry_run: If True, return projected changes without modifying database
        schema: Target schema to search for evt_* tables
        table_filter: Optional list of specific table names to process

    Returns:
        Dict with summary and per-table results
    """
    start_time = time.time()

    pool = await db_pool.get_pool()

    # Validate schema exists
    schema_exists = await events.validate_schema_exists(pool, schema)
    if not schema_exists:
        raise ValueError(f"Schema '{schema}' does not exist")

    # Phase 1: Discover tables
    logger.info(
        f"Discovering evt_* tables in schema '{schema}'",
        extra={
            'endpoint': 'POST /setEventsTable',
            'phase': 'discover',
            'elapsed_ms': 0,
            'counters': {},
            'progress': {},
            'rate': {},
            'batch': {},
            'warn': []
        }
    )

    discovered_tables = await events.discover_evt_tables(pool, schema, table_filter)

    if not discovered_tables:
        logger.warning(
            f"No evt_* tables found in schema '{schema}'",
            extra={
                'endpoint': 'POST /setEventsTable',
                'phase': 'discover',
                'elapsed_ms': int((time.time() - start_time) * 1000),
                'counters': {},
                'progress': {},
                'rate': {},
                'batch': {},
                'warn': ['NO_EVT_TABLES_FOUND']
            }
        )

    # Phase 2-3: Extract and consolidate events from each table
    table_results = []
    total_rows_scanned = 0
    total_inserted = 0
    total_conflicts = 0

    for table_name in discovered_tables:
        table_start = time.time()

        logger.info(
            f"Processing table {table_name}",
            extra={
                'endpoint': 'POST /setEventsTable',
                'phase': f'process_{table_name}',
                'elapsed_ms': 0,
                'counters': {},
                'progress': {},
                'rate': {},
                'batch': {},
                'warn': []
            }
        )

        # Extract events
        event_list, warnings = await events.select_events_from_table(pool, table_name, schema)

        rows_scanned = len(event_list)
        total_rows_scanned += rows_scanned

        # Check if table was skipped
        if warnings and any('MISSING_REQUIRED_COLUMNS' in w for w in warnings):
            table_results.append(TableProcessingResult(
                tableName=table_name,
                rowsScanned=0,
                inserted=0,
                conflicts=0,
                skipped=0,
                skipReason=warnings[0],
                warn=warnings
            ))
            continue

        # Dry run: don't insert
        if dry_run:
            table_results.append(TableProcessingResult(
                tableName=table_name,
                rowsScanned=rows_scanned,
                inserted=rows_scanned,  # Projected inserts
                conflicts=0,
                skipped=0,
                warn=warnings
            ))
        else:
            # Insert into txn_events
            insert_result = await events.upsert_txn_events(pool, event_list)

            total_inserted += insert_result.get('insert', 0)
            total_conflicts += insert_result.get('conflict', 0)

            table_results.append(TableProcessingResult(
                tableName=table_name,
                rowsScanned=rows_scanned,
                inserted=insert_result.get('insert', 0),
                conflicts=insert_result.get('conflict', 0),
                skipped=0,
                warn=warnings
            ))

        logger.info(
            f"Completed table {table_name}",
            extra={
                'endpoint': 'POST /setEventsTable',
                'phase': f'process_{table_name}',
                'elapsed_ms': int((time.time() - table_start) * 1000),
                'counters': {
                    'scanned': rows_scanned,
                    'inserted': insert_result.get('insert', 0) if not dry_run else rows_scanned,
                    'conflicts': insert_result.get('conflict', 0) if not dry_run else 0
                },
                'progress': {},
                'rate': {},
                'batch': {},
                'warn': warnings
            }
        )

    # Phase 4: Enrich sector/industry (skip in dry run)
    enrichment_result = {
        'updated_null': 0,
        'updated_mismatch': 0,
        'skipped_no_target': 0
    }

    if not dry_run:
        logger.info(
            f"Enriching sector/industry (overwrite={overwrite})",
            extra={
                'endpoint': 'POST /setEventsTable',
                'phase': 'enrich',
                'elapsed_ms': 0,
                'counters': {},
                'progress': {},
                'rate': {},
                'batch': {},
                'warn': []
            }
        )

        enrichment_result = await events.update_sector_industry(pool, overwrite)

        logger.info(
            f"Enrichment completed",
            extra={
                'endpoint': 'POST /setEventsTable',
                'phase': 'enrich',
                'elapsed_ms': int((time.time() - start_time) * 1000),
                'counters': enrichment_result,
                'progress': {},
                'rate': {},
                'batch': {},
                'warn': []
            }
        )

    total_elapsed_ms = int((time.time() - start_time) * 1000)

    # Build summary
    summary = {
        'tablesDiscovered': len(discovered_tables),
        'tablesProcessed': len([r for r in table_results if r.skipReason is None]),
        'totalRowsScanned': total_rows_scanned,
        'totalInserted': total_inserted if not dry_run else total_rows_scanned,
        'totalConflicts': total_conflicts,
        'sectorIndustryUpdated': enrichment_result['updated_null'] + enrichment_result['updated_mismatch'],
        'sectorIndustryUpdatedNull': enrichment_result['updated_null'],
        'sectorIndustryUpdatedMismatch': enrichment_result['updated_mismatch'],
        'sectorIndustrySkippedNoTarget': enrichment_result['skipped_no_target'],
        'elapsedMs': total_elapsed_ms
    }

    logger.info(
        f"POST /setEventsTable completed",
        extra={
            'endpoint': 'POST /setEventsTable',
            'phase': 'complete',
            'elapsed_ms': total_elapsed_ms,
            'counters': summary,
            'progress': {},
            'rate': {},
            'batch': {},
            'warn': []
        }
    )

    return {
        'summary': summary,
        'tables': table_results
    }
