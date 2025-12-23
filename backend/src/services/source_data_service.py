"""Service for GET /sourceData endpoint - collects financial data from FMP APIs."""

import logging
import time
import json
from typing import Dict, Any, List, Tuple
from datetime import datetime, date, timedelta

from ..database.connection import db_pool
from ..database.queries import holidays, targets, consensus, earning
from .external_api import FMPAPIClient
from .utils.batch_utils import calculate_eta, format_progress, chunk_list
from .utils.datetime_utils import parse_to_utc, parse_date_only_to_utc
from ..models.response_models import Counters, PhaseCounters

logger = logging.getLogger("alsign")


async def get_targets() -> Dict[str, Any]:
    """
    Fetch and upsert company targets from FMP screener.

    Returns:
        Dict with elapsedMs, counters, warn, dbWrites
    """
    logger.info("=" * 80)
    logger.info("[get_targets] FUNCTION START")
    logger.info("=" * 80)

    start_time = time.time()
    warn_codes = []

    logger.info("[get_targets] Step 1: Initializing FMP API client")

    try:
        logger.info("[get_targets] Step 2: Creating async context manager for FMPAPIClient")
        async with FMPAPIClient() as fmp_client:
            logger.info(f"[get_targets] FMPAPIClient created successfully, type: {type(fmp_client)}")

            # Fetch company screener
            logger.info("[get_targets] Step 3: Calling fmp_client.get_company_screener(limit=10000)")
            fetch_start = time.time()

            companies = await fmp_client.get_company_screener(limit=10000)

            fetch_elapsed = int((time.time() - fetch_start) * 1000)
            logger.info(f"[get_targets] Step 4: API call returned - Type: {type(companies)}, Length: {len(companies) if companies else 0}, Elapsed: {fetch_elapsed}ms")

            if not companies:
                logger.error("[get_targets] CRITICAL ERROR: companies is empty or None")
                logger.error(f"[get_targets] companies type: {type(companies)}")
                logger.error(f"[get_targets] companies value: {companies}")
                warn_codes.append("NO_COMPANIES_DATA")
            elif not isinstance(companies, list):
                logger.error(f"[get_targets] CRITICAL ERROR: companies is not a list, got {type(companies)}")
                logger.error(f"[get_targets] companies value: {str(companies)[:500]}")
                warn_codes.append("NO_COMPANIES_DATA")
            else:
                logger.info(f"[get_targets] SUCCESS: Received {len(companies)} companies from API")
                logger.info(f"[get_targets] First company keys: {list(companies[0].keys())}")
                logger.info(f"[get_targets] First company sample:")
                logger.info(f"[get_targets]   - ticker: {companies[0].get('ticker')}")
                logger.info(f"[get_targets]   - companyName: {companies[0].get('companyName')}")
                logger.info(f"[get_targets]   - sector: {companies[0].get('sector')}")
                logger.info(f"[get_targets]   - industry: {companies[0].get('industry')}")

            # Upsert to database
            logger.info(f"[get_targets] Step 5: Preparing to save {len(companies) if companies else 0} companies to database")
            logger.info("[get_targets] Step 6: Getting database connection pool")
            db_start = time.time()

            pool = await db_pool.get_pool()
            logger.info(f"[get_targets] Database pool acquired, type: {type(pool)}")

            logger.info("[get_targets] Step 7: Calling targets.upsert_company_targets()")
            result = await targets.upsert_company_targets(pool, companies)

            db_elapsed = int((time.time() - db_start) * 1000)
            logger.info(f"[get_targets] Step 8: Database operation completed in {db_elapsed}ms")
            logger.info(f"[get_targets] DB result type: {type(result)}")
            logger.info(f"[get_targets] DB result value: {result}")
            logger.info(f"[get_targets] DB result - Insert: {result.get('insert', 0)}, Update: {result.get('update', 0)}")

    except Exception as e:
        logger.error("=" * 80)
        logger.error(f"[get_targets] EXCEPTION CAUGHT: {type(e).__name__}")
        logger.error(f"[get_targets] Exception message: {str(e)}")
        logger.error("="  * 80)
        logger.error(f"[get_targets] Full stack trace:", exc_info=True)
        logger.error("=" * 80)
        warn_codes.append("EXCEPTION_IN_GET_TARGETS")
        result = {"insert": 0, "update": 0}

    elapsed_ms = int((time.time() - start_time) * 1000)

    logger.info("=" * 80)
    logger.info(f"[get_targets] FUNCTION END - Total elapsed: {elapsed_ms}ms")
    logger.info(f"[get_targets] Final counters: Insert={result.get('insert', 0)}, Update={result.get('update', 0)}")
    logger.info(f"[get_targets] Warnings: {warn_codes}")
    logger.info("=" * 80)

    return {
        "executed": True,
        "elapsedMs": elapsed_ms,
        "counters": Counters(
            success=result.get("insert", 0) + result.get("update", 0),
            fail=0,
            skip=0,
            update=result.get("update", 0),
            insert=result.get("insert", 0),
            conflict=0
        ),
        "warn": warn_codes,
        "dbWrites": [
            {
                "table": "config_lv3_targets",
                "insert": result.get("insert", 0),
                "update": result.get("update", 0),
                "total": result.get("insert", 0) + result.get("update", 0)
            }
        ]
    }


async def get_holidays() -> Dict[str, Any]:
    """
    Fetch and upsert market holidays from FMP API.

    Returns:
        Dict with elapsedMs, counters, warn, dbWrites
    """
    start_time = time.time()
    warn_codes = []

    async with FMPAPIClient() as fmp_client:
        # Fetch holidays for NASDAQ
        holidays_data = await fmp_client.get_market_holidays("NASDAQ")

        if not holidays_data:
            warn_codes.append("NO_HOLIDAYS_DATA")

        # Upsert to database
        pool = await db_pool.get_pool()
        result = await holidays.upsert_market_holidays(pool, holidays_data)

    elapsed_ms = int((time.time() - start_time) * 1000)

    return {
        "executed": True,
        "elapsedMs": elapsed_ms,
        "counters": Counters(
            success=result.get("insert", 0) + result.get("update", 0),
            fail=0,
            skip=0,
            update=result.get("update", 0),
            insert=result.get("insert", 0),
            conflict=0
        ),
        "warn": warn_codes,
        "dbWrites": [
            {
                "table": "config_lv3_market_holidays",
                "insert": result.get("insert", 0),
                "update": result.get("update", 0),
                "total": result.get("insert", 0) + result.get("update", 0)
            }
        ]
    }


async def get_consensus(
    calc_mode: str = None,
    calc_scope: str = None,
    tickers_param: str = None,
    from_date: date = None,
    to_date: date = None,
    partitions_param: str = None
) -> Dict[str, Any]:
    """
    Fetch and process consensus data with two-phase processing.

    Phase 1: Raw upsert of consensus data
    Phase 2: Calculate prev values and direction for target partitions

    Args:
        calc_mode: 'maintenance' or None (default: affected partitions only)
        calc_scope: 'all', 'ticker', 'event_date_range', 'partition_keys' (required if calc_mode=maintenance)
        tickers_param: Comma-separated tickers (required if calc_scope=ticker)
        from_date: Start date (required if calc_scope=event_date_range)
        to_date: End date (required if calc_scope=event_date_range)
        partitions_param: JSON array of partitions (required if calc_scope=partition_keys)

    Returns:
        Dict with elapsedMs, counters, phase1, phase2, warn
    """
    start_time = time.time()
    warn_codes = []

    pool = await db_pool.get_pool()

    # Phase 1: Raw Upsert
    phase1_start = time.time()

    # Get all tickers from targets
    ticker_list = await targets.get_all_tickers(pool)

    if not ticker_list:
        warn_codes.append("NO_TICKERS_IN_TARGETS")
        return {
            "executed": True,
            "elapsedMs": 0,
            "counters": Counters(),
            "phase1": PhaseCounters(elapsedMs=0, counters=Counters()),
            "phase2": {"partitionsProcessed": 0, "partitionsFailed": 0, "counters": Counters()},
            "warn": warn_codes
        }

    # Fetch consensus for each ticker
    all_consensus = []
    async with FMPAPIClient() as fmp_client:
        for ticker in ticker_list:
            consensus_list = await fmp_client.get_price_target_consensus(ticker)
            if consensus_list:
                all_consensus.extend(consensus_list)

    # Upsert Phase 1
    phase1_result, affected_partitions = await consensus.upsert_consensus_phase1(pool, all_consensus)

    phase1_elapsed = int((time.time() - phase1_start) * 1000)
    phase1_counters = Counters(
        success=phase1_result.get("insert", 0) + phase1_result.get("update", 0),
        fail=0,
        skip=0,
        update=phase1_result.get("update", 0),
        insert=phase1_result.get("insert", 0),
        conflict=0
    )

    # Phase 2: Change Detection
    phase2_start = time.time()

    # Determine target partitions
    if calc_mode == 'maintenance':
        target_partitions = await determine_phase2_partitions(
            pool, calc_scope, tickers_param, from_date, to_date, partitions_param
        )
    else:
        # Default mode: only affected partitions
        target_partitions = affected_partitions

    # Process each partition
    phase2_updates = []
    partitions_processed = 0
    partitions_failed = 0

    for partition in target_partitions:
        ticker, analyst_name, analyst_company = partition

        try:
            # Get all events in partition sorted by event_date DESC
            events = await consensus.select_partition_events(pool, ticker, analyst_name, analyst_company)

            # Calculate prev values and direction
            for i, event in enumerate(events):
                if i < len(events) - 1:
                    # There is a previous event
                    prev_event = events[i + 1]

                    price_target_prev = prev_event['price_target']
                    price_when_posted_prev = prev_event['price_when_posted']

                    # Calculate direction
                    if event['price_target'] > price_target_prev:
                        direction = 'up'
                    elif event['price_target'] < price_target_prev:
                        direction = 'down'
                    else:
                        direction = None

                    response_key_prev = {
                        'price_target': price_target_prev,
                        'price_when_posted': price_when_posted_prev,
                        'event_date': prev_event['event_date'].isoformat()
                    }
                else:
                    # No previous event
                    price_target_prev = None
                    price_when_posted_prev = None
                    direction = None
                    response_key_prev = None

                phase2_updates.append({
                    'id': event['id'],
                    'price_target_prev': price_target_prev,
                    'price_when_posted_prev': price_when_posted_prev,
                    'direction': direction,
                    'response_key_prev': response_key_prev
                })

            partitions_processed += 1

        except Exception as e:
            logger.error(f"Phase 2 failed for partition ({ticker}, {analyst_name}, {analyst_company}): {e}")
            partitions_failed += 1
            continue

    # Apply Phase 2 updates
    phase2_update_count = await consensus.update_consensus_phase2(pool, phase2_updates)

    phase2_elapsed = int((time.time() - phase2_start) * 1000)

    total_elapsed = int((time.time() - start_time) * 1000)

    return {
        "executed": True,
        "elapsedMs": total_elapsed,
        "counters": Counters(
            success=phase1_counters.success + phase2_update_count,
            fail=partitions_failed,
            skip=0,
            update=phase1_counters.update + phase2_update_count,
            insert=phase1_counters.insert,
            conflict=0
        ),
        "phase1": PhaseCounters(elapsedMs=phase1_elapsed, counters=phase1_counters),
        "phase2": {
            "partitionsProcessed": partitions_processed,
            "partitionsFailed": partitions_failed,
            "counters": Counters(update=phase2_update_count, success=phase2_update_count, fail=partitions_failed)
        },
        "warn": warn_codes,
        "dbWrites": [
            {
                "table": "evt_consensus (Phase 1 - Raw Upsert)",
                "insert": phase1_counters.insert,
                "update": phase1_counters.update,
                "total": phase1_counters.success
            },
            {
                "table": "evt_consensus (Phase 2 - Change Detection)",
                "insert": 0,
                "update": phase2_update_count,
                "total": phase2_update_count
            }
        ]
    }


async def determine_phase2_partitions(
    pool,
    calc_scope: str,
    tickers_param: str,
    from_date: date,
    to_date: date,
    partitions_param: str
) -> List[Tuple[str, str, str]]:
    """
    Determine which partitions to process in Phase 2 based on calc_scope.

    Returns:
        List of (ticker, analyst_name, analyst_company) tuples
    """
    if calc_scope == 'all':
        # Get all partitions
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT DISTINCT ticker, analyst_name, analyst_company FROM evt_consensus"
            )
            return [(row['ticker'], row['analyst_name'], row['analyst_company']) for row in rows]

    elif calc_scope == 'ticker':
        # Get partitions for specific tickers
        ticker_list = [t.strip().upper() for t in tickers_param.split(',')]
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT DISTINCT ticker, analyst_name, analyst_company FROM evt_consensus WHERE ticker = ANY($1)",
                ticker_list
            )
            return [(row['ticker'], row['analyst_name'], row['analyst_company']) for row in rows]

    elif calc_scope == 'event_date_range':
        # Get partitions with events in date range
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT DISTINCT ticker, analyst_name, analyst_company
                FROM evt_consensus
                WHERE event_date::date BETWEEN $1 AND $2
                """,
                from_date,
                to_date
            )
            return [(row['ticker'], row['analyst_name'], row['analyst_company']) for row in rows]

    elif calc_scope == 'partition_keys':
        # Use explicitly provided partitions
        partitions_list = json.loads(partitions_param)
        return [(p['ticker'], p.get('analyst_name'), p.get('analyst_company')) for p in partitions_list]

    return []


async def get_earning(past: bool = False) -> Dict[str, Any]:
    """
    Fetch and insert earning calendar data.

    Per 1_guideline(function).ini specifications:
    - Future query (default): 4 windows of 7 days each
      - Window 1: today ~ today+7
      - Window 2: today+8 ~ today+14
      - Window 3: today+15 ~ today+21
      - Window 4: today+22 ~ today+28
    - Past query (when past=True): 5 years back in 7-day batches
      - From: today - 5 years
      - To: today
      - Batch: 7-day chunks

    Args:
        past: If True, also fetch past 5 years (backfill mode). Default: future only.

    Returns:
        Dict with elapsedMs, counters, warn, dbWrites
    """
    start_time = time.time()
    warn_codes = []

    # Calculate date ranges
    today = date.today()
    date_ranges = []

    # Future 28 days in 4 windows (per guideline specification)
    # Window 1: today ~ today+7
    # Window 2: today+8 ~ today+14
    # Window 3: today+15 ~ today+21
    # Window 4: today+22 ~ today+28
    future_windows = [
        (today, today + timedelta(days=7)),
        (today + timedelta(days=8), today + timedelta(days=14)),
        (today + timedelta(days=15), today + timedelta(days=21)),
        (today + timedelta(days=22), today + timedelta(days=28)),
    ]
    date_ranges.extend(future_windows)

    # Past 5 years in 7-day batches (only when past=True)
    # Per guideline: batch i: fromDate=D, toDate=min(D+6, today)
    if past:
        five_years_ago = today - timedelta(days=5 * 365)
        current = five_years_ago
        while current < today:
            from_date = current
            to_date = min(current + timedelta(days=6), today)
            date_ranges.append((from_date, to_date))
            current = to_date + timedelta(days=1)

    # Get valid tickers from config_lv3_targets first
    pool = await db_pool.get_pool()
    valid_tickers = await targets.get_all_tickers(pool)
    valid_tickers_set = set(t.upper() for t in valid_tickers)

    if not valid_tickers_set:
        warn_codes.append("NO_TICKERS_IN_TARGETS")
        logger.warning("[get_earning] No tickers found in config_lv3_targets. Skipping earning fetch.")
        return {
            "executed": True,
            "elapsedMs": int((time.time() - start_time) * 1000),
            "counters": Counters(),
            "warn": warn_codes,
            "dbWrites": []
        }

    logger.info(f"[get_earning] Found {len(valid_tickers_set)} valid tickers in config_lv3_targets")

    # Fetch earnings for each range
    all_earnings = []
    async with FMPAPIClient() as fmp_client:
        for from_date, to_date in date_ranges:
            earnings_data = await fmp_client.get_earnings_calendar(
                from_date.isoformat(),
                to_date.isoformat()
            )
            all_earnings.extend(earnings_data)

    # Filter earnings to only include tickers that exist in config_lv3_targets
    total_before_filter = len(all_earnings)
    filtered_earnings = [
        e for e in all_earnings
        if (e.get('symbol') or e.get('ticker', '')).upper() in valid_tickers_set
    ]
    skipped_count = total_before_filter - len(filtered_earnings)

    logger.info(f"[get_earning] Filtered earnings: {len(filtered_earnings)} kept, {skipped_count} skipped (not in targets)")

    # Insert to database
    result = await earning.insert_earning_events(pool, filtered_earnings)

    elapsed_ms = int((time.time() - start_time) * 1000)

    return {
        "executed": True,
        "elapsedMs": elapsed_ms,
        "counters": Counters(
            success=result.get("insert", 0),
            fail=0,
            skip=skipped_count,
            update=0,
            insert=result.get("insert", 0),
            conflict=result.get("conflict", 0)
        ),
        "warn": warn_codes,
        "dbWrites": [
            {
                "table": "evt_earning",
                "insert": result.get("insert", 0),
                "update": 0,
                "total": result.get("insert", 0),
                "conflict": result.get("conflict", 0),
                "skipped": skipped_count
            }
        ]
    }
