"""Service for GET /sourceData endpoint - collects financial data from FMP APIs."""

import logging
import time
import json
import asyncio
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime, date, timedelta

from ..database.connection import db_pool
from ..database.queries import holidays, targets, consensus, earning
from .external_api import FMPAPIClient
from .utils.batch_utils import calculate_eta, format_progress, chunk_list, format_eta_ms
from .utils.datetime_utils import parse_to_utc, parse_date_only_to_utc
from ..models.response_models import Counters, PhaseCounters

logger = logging.getLogger("alsign")

# Concurrency settings for API calls (considering FMP rate limits)
# API_CONCURRENCY is now calculated dynamically from usagePerMin
PEER_MAX_CONCURRENCY = 50
API_BATCH_SIZE = 20   # Batch size for progress logging
API_RETRY_COUNT = 2   # Number of retries for failed API calls

def _extract_peer_tickers(base_ticker: str, response: Any) -> List[str]:
    """
    Extract peer ticker list from fmp-stock-peers response.
    """
    peer_candidates: List[Any] = []
    if isinstance(response, dict):
        peer_candidates = (
            response.get('peersList')
            or response.get('peers')
            or response.get('peerList')
            or response.get('data')
            or []
        )
    elif isinstance(response, list):
        peer_candidates = response

    peers: List[str] = []
    for item in peer_candidates:
        if isinstance(item, str):
            peer = item
        elif isinstance(item, dict):
            peer = item.get('ticker') or item.get('symbol')
        else:
            peer = None

        if peer:
            peer_upper = peer.upper()
            if peer_upper != base_ticker:
                peers.append(peer_upper)

    return list(dict.fromkeys(peers))


async def _fetch_peer_tickers(
    fmp_client: FMPAPIClient,
    ticker: str,
    semaphore: asyncio.Semaphore
) -> Tuple[str, List[str], bool]:
    async with semaphore:
        try:
            response = await fmp_client.call_api('fmp-stock-peers', {'ticker': ticker})
            peers = _extract_peer_tickers(ticker.upper(), response)
            return ticker, peers, True
        except Exception as exc:
            logger.warning(f"[get_targets] Failed to fetch peers for {ticker}: {exc}")
            return ticker, [], False


async def collect_target_peers(
    fmp_client: FMPAPIClient,
    tickers: List[str]
) -> Tuple[Dict[str, List[str]], int]:
    """
    Collect peer tickers for all targets using fmp-stock-peers API.

    Returns:
        Tuple of (peer_updates dict, failed_count)
    """
    if not tickers:
        return {}, 0

    peer_updates: Dict[str, List[str]] = {}
    failed_count = 0
    total = len(tickers)
    index = 0
    completed = 0
    start_time = time.time()

    logger.info(f"[collect_target_peers] Starting peer collection for {total} tickers")

    while index < total:
        remaining = total - index
        batch_size, mode = fmp_client.rate_limiter.calculate_dynamic_batch_size(remaining)
        batch_size = min(batch_size, remaining)
        batch = tickers[index:index + batch_size]

        rate_limit = fmp_client.get_rate_limit()
        max_concurrent = min(rate_limit, PEER_MAX_CONCURRENCY, batch_size)
        semaphore = asyncio.Semaphore(max_concurrent)
        logger.info(
            f"[get_targets] Peer batch: size={batch_size}, mode={mode}, "
            f"rate_limit={rate_limit}, max_concurrent={max_concurrent}"
        )
        tasks = [_fetch_peer_tickers(fmp_client, ticker, semaphore) for ticker in batch]
        results = await asyncio.gather(*tasks)
        for ticker, peers, ok in results:
            if ok:
                peer_updates[ticker] = peers
            else:
                failed_count += 1

        index += batch_size
        completed = index

        # Log progress every 20 tickers or at completion
        if completed % 20 == 0 or completed == total:
            elapsed_ms = int((time.time() - start_time) * 1000)
            eta_ms = calculate_eta(total, completed, elapsed_ms)
            eta = format_eta_ms(eta_ms)

            logger.info(
                f"Peer collection: {completed}/{total} tickers",
                extra={
                    'endpoint': 'GET /sourceData',
                    'phase': 'target-peer-collection',
                    'elapsed_ms': elapsed_ms,
                    'progress': format_progress(completed, total),
                    'eta': eta,
                    'counters': {
                        'success': len(peer_updates),
                        'fail': failed_count
                    },
                    'batch': {
                        'size': batch_size,
                        'mode': mode
                    }
                }
            )

    return peer_updates, failed_count

async def get_targets(overwrite: bool = False) -> Dict[str, Any]:
    """
    Fetch and upsert company targets from FMP screener.

    Args:
        overwrite: If False, update only NULL values. If True, truncate and insert all data.

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

            logger.info("[get_targets] Step 9: Fetching peer tickers via fmp-stock-peers")
            peer_update_result = {"update": 0}
            if companies:
                target_tickers = await targets.get_all_tickers(pool)
                logger.info(f"[get_targets] Found {len(target_tickers)} tickers for peer collection")
                peer_updates, failed_count = await collect_target_peers(fmp_client, target_tickers)
                if failed_count:
                    warn_codes.append("PEER_FETCH_FAILED")
                peer_update_result = await targets.update_target_peers(pool, peer_updates)
                logger.info(
                    f"[get_targets] Peer updates complete: updated={peer_update_result.get('update', 0)}, failed={failed_count}"
                )
            else:
                logger.warning("[get_targets] No companies available for peer collection")

    except Exception as e:
        logger.error("=" * 80)
        logger.error(f"[get_targets] EXCEPTION CAUGHT: {type(e).__name__}")
        logger.error(f"[get_targets] Exception message: {str(e)}")
        logger.error("="  * 80)
        logger.error(f"[get_targets] Full stack trace:", exc_info=True)
        logger.error("=" * 80)
        warn_codes.append("EXCEPTION_IN_GET_TARGETS")
        result = {"insert": 0, "update": 0}
        peer_update_result = {"update": 0}

    elapsed_ms = int((time.time() - start_time) * 1000)

    logger.info("=" * 80)
    logger.info(f"[get_targets] FUNCTION END - Total elapsed: {elapsed_ms}ms")
    logger.info(f"[get_targets] Final counters: Insert={result.get('insert', 0)}, Update={result.get('update', 0)}")
    logger.info(f"[get_targets] Warnings: {warn_codes}")
    logger.info("=" * 80)

    counters_obj = Counters(
        success=result.get("insert", 0) + result.get("update", 0),
        fail=0,
        skip=0,
        update=result.get("update", 0),
        insert=result.get("insert", 0),
        conflict=0
    )

    return {
        "executed": True,
        "elapsedMs": elapsed_ms,
        "counters": counters_obj.model_dump(),
        "warn": warn_codes,
        "dbWrites": [
            {
                "table": "config_lv3_targets",
                "insert": result.get("insert", 0),
                "update": result.get("update", 0),
                "total": result.get("insert", 0) + result.get("update", 0)
            },
            {
                "table": "config_lv3_targets",
                "insert": 0,
                "update": peer_update_result.get("update", 0),
                "total": peer_update_result.get("update", 0)
            }
        ]
    }


async def get_holidays(overwrite: bool = False) -> Dict[str, Any]:
    """
    Fetch and upsert market holidays from FMP API.

    Args:
        overwrite: If False, update only NULL values. If True, overwrite existing data.

    Returns:
        Dict with elapsedMs, counters, warn, dbWrites
    """
    start_time = time.time()
    warn_codes = []

    logger.info(
        "Starting holiday data collection",
        extra={
            'endpoint': 'GET /sourceData',
            'phase': 'holiday-start',
            'elapsed_ms': 0
        }
    )

    async with FMPAPIClient() as fmp_client:
        # Fetch holidays for NASDAQ
        holidays_data = await fmp_client.get_market_holidays("NASDAQ")

        if not holidays_data:
            warn_codes.append("NO_HOLIDAYS_DATA")

        # Upsert to database
        pool = await db_pool.get_pool()
        result = await holidays.upsert_market_holidays(pool, holidays_data)

    elapsed_ms = int((time.time() - start_time) * 1000)

    counters_obj = Counters(
        success=result.get("insert", 0) + result.get("update", 0),
        fail=0,
        skip=0,
        update=result.get("update", 0),
        insert=result.get("insert", 0),
        conflict=0
    )

    logger.info(
        f"Holiday data collection completed: {counters_obj.success} records",
        extra={
            'endpoint': 'GET /sourceData',
            'phase': 'holiday-complete',
            'elapsed_ms': elapsed_ms,
            'counters': {
                'success': counters_obj.success,
                'insert': counters_obj.insert,
                'update': counters_obj.update
            }
        }
    )

    return {
        "executed": True,
        "elapsedMs": elapsed_ms,
        "counters": counters_obj.model_dump(),
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
    overwrite: bool = False,
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
        calc_mode: 
            - None (default): Phase 1 + Phase 2 for affected partitions only
            - 'maintenance': Phase 1 + Phase 2 with custom scope
            - 'calculation': Phase 2 only (skip API calls, use existing data)
        calc_scope: 'all', 'ticker', 'event_date_range', 'partition_keys' (required if calc_mode=maintenance or calculation)
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

    # calc_mode=calculation: Skip Phase 1 (API calls), only run Phase 2
    if calc_mode == 'calculation':
        logger.info(
            f"[get_consensus] calc_mode=calculation: Skipping Phase 1, running Phase 2 only",
            extra={
                'endpoint': 'GET /sourceData',
                'phase': 'consensus-phase1-skip',
                'elapsed_ms': 0,
                'counters': {},
                'progress': {'done': 0, 'total': 0, 'pct': 0},
                'rate': {},
                'batch': {},
                'warn': []
            }
        )
        
        phase1_elapsed = 0
        phase1_counters = Counters()
        affected_partitions = []
        
        # Phase 2 will use calc_scope to determine target partitions
    else:
        # Phase 1: Raw Upsert (Parallel API calls)
        phase1_start = time.time()

        # Get all tickers from targets
        ticker_list = await targets.get_all_tickers(pool)

        if not ticker_list:
            warn_codes.append("NO_TICKERS_IN_TARGETS")
            return {
                "executed": True,
                "elapsedMs": 0,
                "counters": Counters().model_dump(),
                "phase1": PhaseCounters(elapsedMs=0, counters=Counters()).model_dump(),
                "phase2": {"partitionsProcessed": 0, "partitionsFailed": 0, "counters": Counters().model_dump()},
                "warn": warn_codes
            }

        total_tickers = len(ticker_list)
        logger.info(
            f"[get_consensus] Phase 1: Fetching consensus for {total_tickers} tickers (parallel, concurrency={API_CONCURRENCY})",
            extra={
                'endpoint': 'GET /sourceData',
                'phase': 'consensus-phase1-start',
                'elapsed_ms': 0,
                'counters': {},
                'progress': {'done': 0, 'total': total_tickers, 'pct': 0},
                'rate': {},
                'batch': {},
                'warn': []
            }
        )

        # Parallel API calls with semaphore
        all_consensus = []
        completed_tickers = 0
        failed_tickers = 0

        # Dynamic concurrency based on usagePerMin
        max_concurrent = fmp_client.get_rate_limit()
        semaphore = asyncio.Semaphore(max_concurrent)
        results_lock = asyncio.Lock()

        logger.info(f"[fill_consensus] Using dynamic concurrency: {max_concurrent}")

        async def fetch_ticker_consensus(fmp_client: FMPAPIClient, ticker: str):
            nonlocal completed_tickers, failed_tickers
            async with semaphore:
                consensus_list = None
                last_error = None
                
                # Retry logic
                for attempt in range(API_RETRY_COUNT + 1):
                    try:
                        consensus_list = await fmp_client.get_price_target_consensus(ticker)
                        break  # Success
                    except Exception as e:
                        last_error = e
                        if attempt < API_RETRY_COUNT:
                            await asyncio.sleep(1 * (attempt + 1))  # Backoff
                        continue
                
                async with results_lock:
                    if consensus_list is not None:
                        if consensus_list:
                            all_consensus.extend(consensus_list)
                    elif last_error:
                        failed_tickers += 1
                        logger.warning(f"[Phase 1] Failed to fetch consensus for {ticker} after {API_RETRY_COUNT+1} attempts: {last_error}")
                    
                    completed_tickers += 1
                    
                    # Log progress every batch
                    if completed_tickers % API_BATCH_SIZE == 0 or completed_tickers == total_tickers:
                        progress_pct = (completed_tickers / total_tickers) * 100
                        elapsed = time.time() - phase1_start
                        rate = completed_tickers / elapsed if elapsed > 0 else 0
                        remaining = total_tickers - completed_tickers
                        eta_seconds = remaining / rate if rate > 0 else 0
                        eta_str = f"{int(eta_seconds)}s" if eta_seconds < 60 else f"{int(eta_seconds/60)}m {int(eta_seconds%60)}s"
                        
                        logger.info(
                            f"[Phase 1] progress={completed_tickers}/{total_tickers}({progress_pct:.1f}%) | rate={rate:.1f}/s | ETA: {eta_str}",
                            extra={
                                'endpoint': 'GET /sourceData',
                                'phase': 'consensus-phase1',
                                'elapsed_ms': int(elapsed * 1000),
                                'counters': {'success': completed_tickers - failed_tickers, 'fail': failed_tickers},
                                'progress': {'done': completed_tickers, 'total': total_tickers, 'pct': int(progress_pct)},
                                'rate': {'per_second': rate},
                                'batch': {},
                                'warn': []
                            }
                        )

        async with FMPAPIClient() as fmp_client:
            tasks = [fetch_ticker_consensus(fmp_client, ticker) for ticker in ticker_list]
            await asyncio.gather(*tasks)

        # Upsert Phase 1
        phase1_result, affected_partitions = await consensus.upsert_consensus_phase1(pool, all_consensus)

        phase1_elapsed = int((time.time() - phase1_start) * 1000)
        phase1_counters = Counters(
            success=phase1_result.get("insert", 0) + phase1_result.get("update", 0),
            fail=failed_tickers,
            skip=0,
            update=phase1_result.get("update", 0),
            insert=phase1_result.get("insert", 0),
            conflict=0
        )
        
        logger.info(
            f"[Phase 1] Complete: {len(all_consensus)} records from {completed_tickers} tickers in {phase1_elapsed}ms",
            extra={
                'endpoint': 'GET /sourceData',
                'phase': 'consensus-phase1-complete',
                'elapsed_ms': phase1_elapsed,
                'counters': {'success': completed_tickers - failed_tickers, 'fail': failed_tickers},
                'progress': {'done': total_tickers, 'total': total_tickers, 'pct': 100},
                'rate': {},
                'batch': {},
                'warn': []
            }
        )

    # Phase 2: Change Detection
    phase2_start = time.time()

    # Determine target partitions
    if calc_mode in ('maintenance', 'calculation'):
        # maintenance/calculation mode: use calc_scope to determine partitions
        target_partitions = await determine_phase2_partitions(
            pool, calc_scope, tickers_param, from_date, to_date, partitions_param
        )
        logger.info(
            f"[get_consensus] Phase 2 starting: {len(target_partitions)} partitions (calc_mode={calc_mode}, calc_scope={calc_scope})",
            extra={
                'endpoint': 'GET /sourceData',
                'phase': 'consensus-phase2-start',
                'elapsed_ms': 0,
                'counters': {},
                'progress': {'done': 0, 'total': len(target_partitions), 'pct': 0},
                'rate': {},
                'batch': {},
                'warn': []
            }
        )
    else:
        # Default mode: only affected partitions from Phase 1
        target_partitions = affected_partitions
        logger.info(
            f"[get_consensus] Phase 2 starting: {len(target_partitions)} partitions from Phase 1 affected partitions",
            extra={
                'endpoint': 'GET /sourceData',
                'phase': 'consensus-phase2-start',
                'elapsed_ms': 0,
                'counters': {},
                'progress': {'done': 0, 'total': len(target_partitions), 'pct': 0},
                'rate': {},
                'batch': {},
                'warn': []
            }
        )

    # Process each partition
    phase2_updates = []
    partitions_processed = 0
    partitions_failed = 0
    total_partitions = len(target_partitions)
    partition_start_times = []

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

                    # Convert Decimal to float for JSON serialization
                    price_target_prev = float(prev_event['price_target']) if prev_event['price_target'] is not None else None
                    price_when_posted_prev = float(prev_event['price_when_posted']) if prev_event['price_when_posted'] is not None else None
                    current_price_target = float(event['price_target']) if event['price_target'] is not None else None

                    # Calculate direction
                    if current_price_target is not None and price_target_prev is not None:
                        if current_price_target > price_target_prev:
                            direction = 'up'
                        elif current_price_target < price_target_prev:
                            direction = 'down'
                        else:
                            direction = None
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
            partition_start_times.append(time.time())

            # Log progress every 5 partitions or on last partition
            if partitions_processed % 5 == 0 or partitions_processed == total_partitions:
                progress_pct = (partitions_processed / total_partitions) * 100 if total_partitions > 0 else 0
                
                # Calculate ETA
                if len(partition_start_times) >= 2:
                    recent_times = partition_start_times[-min(10, len(partition_start_times)):]
                    if len(recent_times) >= 2:
                        avg_time_per_partition = (recent_times[-1] - recent_times[0]) / (len(recent_times) - 1)
                        remaining_partitions = total_partitions - partitions_processed
                        eta_seconds = remaining_partitions * avg_time_per_partition
                        
                        if eta_seconds > 60:
                            eta_str = f"{int(eta_seconds / 60)}min {int(eta_seconds % 60)}s"
                        else:
                            eta_str = f"{int(eta_seconds)}s"
                    else:
                        eta_str = "calculating..."
                else:
                    eta_str = "calculating..."
                
                elapsed = time.time() - phase2_start
                rate = partitions_processed / elapsed if elapsed > 0 else 0
                
                logger.info(
                    f"[Phase 2] progress={partitions_processed}/{total_partitions}({progress_pct:.1f}%) | rate={rate:.1f}/s | ETA: {eta_str}",
                    extra={
                        'endpoint': 'GET /sourceData',
                        'phase': 'consensus-phase2',
                        'elapsed_ms': int(elapsed * 1000),
                        'counters': {'success': partitions_processed, 'fail': partitions_failed},
                        'progress': {'done': partitions_processed, 'total': total_partitions, 'pct': int(progress_pct)},
                        'rate': {'per_second': rate},
                        'batch': {},
                        'warn': []
                    }
                )

        except Exception as e:
            logger.error(f"Phase 2 failed for partition ({ticker}, {analyst_name}, {analyst_company}): {e}")
            partitions_failed += 1
            partition_start_times.append(time.time())
            continue

    # Apply Phase 2 updates
    phase2_update_count = await consensus.update_consensus_phase2(pool, phase2_updates)

    phase2_elapsed = int((time.time() - phase2_start) * 1000)
    
    # Phase 2 complete log
    logger.info(
        f"[Phase 2] Complete: {partitions_processed} partitions, {phase2_update_count} events updated in {phase2_elapsed}ms",
        extra={
            'endpoint': 'GET /sourceData',
            'phase': 'consensus-phase2-complete',
            'elapsed_ms': phase2_elapsed,
            'counters': {'success': partitions_processed, 'fail': partitions_failed, 'update': phase2_update_count},
            'progress': {'done': total_partitions, 'total': total_partitions, 'pct': 100},
            'rate': {},
            'batch': {},
            'warn': []
        }
    )

    # Phase 3: Calculate targetSummary for each event
    phase3_start = time.time()
    phase3_success = 0
    phase3_fail = 0
    phase3_skip = 0
    
    logger.info(
        f"[get_consensus] Phase 3 starting: targetSummary calculation (overwrite={overwrite})",
        extra={
            'endpoint': 'GET /sourceData',
            'phase': 'consensus-phase3-start',
            'elapsed_ms': 0,
            'counters': {},
            'progress': {'done': 0, 'total': 0, 'pct': 0},
            'rate': {},
            'batch': {},
            'warn': []
        }
    )
    
    # Get events needing targetSummary calculation
    events_for_summary = await consensus.get_events_for_target_summary(
        pool, overwrite, calc_scope, tickers_param, from_date, to_date
    )
    
    total_events_phase3 = len(events_for_summary)
    logger.info(f"[Phase 3] Found {total_events_phase3} events for targetSummary calculation")
    
    # Batch processing
    BATCH_SIZE = 100
    phase3_updates = []
    
    for idx, event in enumerate(events_for_summary):
        try:
            # Calculate targetSummary for this event
            target_summary = await consensus.calculate_target_summary(
                pool, event['ticker'], event['event_date']
            )
            
            if target_summary:
                phase3_updates.append({
                    'id': event['id'],
                    'target_summary': target_summary
                })
                phase3_success += 1
            else:
                phase3_skip += 1
                # Log first few skips for debugging
                if phase3_skip <= 5:
                    logger.debug(
                        f"[Phase 3] Skip: no target_summary for ticker={event['ticker']}, event_date={event['event_date']}, id={event['id']}"
                    )
            
            # Log progress every 100 events
            if (idx + 1) % 100 == 0 or (idx + 1) == total_events_phase3:
                progress_pct = ((idx + 1) / total_events_phase3) * 100 if total_events_phase3 > 0 else 0
                elapsed = time.time() - phase3_start
                rate = (idx + 1) / elapsed if elapsed > 0 else 0
                remaining = total_events_phase3 - (idx + 1)
                eta_seconds = remaining / rate if rate > 0 else 0
                eta_str = f"{int(eta_seconds)}s" if eta_seconds < 60 else f"{int(eta_seconds/60)}m {int(eta_seconds%60)}s"
                
                logger.info(
                    f"[Phase 3] progress={idx + 1}/{total_events_phase3}({progress_pct:.1f}%) | rate={rate:.1f}/s | ETA: {eta_str}",
                    extra={
                        'endpoint': 'GET /sourceData',
                        'phase': 'consensus-phase3',
                        'elapsed_ms': int(elapsed * 1000),
                        'counters': {'success': phase3_success, 'fail': phase3_fail, 'skip': phase3_skip},
                        'progress': {'done': idx + 1, 'total': total_events_phase3, 'pct': int(progress_pct)},
                        'rate': {'per_second': rate},
                        'batch': {},
                        'warn': []
                    }
                )
            
            # Batch update every BATCH_SIZE events
            if len(phase3_updates) >= BATCH_SIZE:
                await consensus.update_target_summary_batch(pool, phase3_updates)
                phase3_updates = []
                
        except Exception as e:
            logger.error(f"Phase 3 failed for event {event['id']}: {e}")
            phase3_fail += 1
    
    # Final batch update
    if phase3_updates:
        await consensus.update_target_summary_batch(pool, phase3_updates)
    
    phase3_elapsed = int((time.time() - phase3_start) * 1000)
    
    # Phase 3 complete log
    logger.info(
        f"[Phase 3] Complete: {phase3_success} events updated, {phase3_skip} skipped, {phase3_fail} failed in {phase3_elapsed}ms",
        extra={
            'endpoint': 'GET /sourceData',
            'phase': 'consensus-phase3-complete',
            'elapsed_ms': phase3_elapsed,
            'counters': {'success': phase3_success, 'fail': phase3_fail, 'skip': phase3_skip},
            'progress': {'done': total_events_phase3, 'total': total_events_phase3, 'pct': 100},
            'rate': {},
            'batch': {},
            'warn': []
        }
    )

    total_elapsed = int((time.time() - start_time) * 1000)

    total_counters = Counters(
        success=phase1_counters.success + phase2_update_count + phase3_success,
        fail=partitions_failed + phase3_fail,
        skip=phase3_skip,
        update=phase1_counters.update + phase2_update_count + phase3_success,
        insert=phase1_counters.insert,
        conflict=0
    )
    phase1_obj = PhaseCounters(elapsedMs=phase1_elapsed, counters=phase1_counters)
    phase2_counters = Counters(update=phase2_update_count, success=phase2_update_count, fail=partitions_failed)
    phase3_counters = Counters(success=phase3_success, fail=phase3_fail, skip=phase3_skip, update=phase3_success)

    return {
        "executed": True,
        "elapsedMs": total_elapsed,
        "counters": total_counters.model_dump(),
        "phase1": phase1_obj.model_dump(),
        "phase2": {
            "partitionsProcessed": partitions_processed,
            "partitionsFailed": partitions_failed,
            "counters": phase2_counters.model_dump()
        },
        "phase3": {
            "eventsProcessed": total_events_phase3,
            "elapsedMs": phase3_elapsed,
            "counters": phase3_counters.model_dump()
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
            },
            {
                "table": "evt_consensus (Phase 3 - Target Summary)",
                "insert": 0,
                "update": phase3_success,
                "total": phase3_success
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


async def get_earning(overwrite: bool = False, past: bool = False) -> Dict[str, Any]:
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
        overwrite: If False, update only NULL values. If True, overwrite existing data.
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
            "counters": Counters().model_dump(),
            "warn": warn_codes,
            "dbWrites": []
        }

    logger.info(f"[get_earning] Found {len(valid_tickers_set)} valid tickers in config_lv3_targets")

    # Fetch earnings for each range (Parallel API calls)
    total_ranges = len(date_ranges)
    logger.info(
        f"[get_earning] Fetching earnings for {total_ranges} date ranges (parallel, concurrency={API_CONCURRENCY})",
        extra={
            'endpoint': 'GET /sourceData',
            'phase': 'earning-fetch-start',
            'elapsed_ms': 0,
            'counters': {},
            'progress': {'done': 0, 'total': total_ranges, 'pct': 0},
            'rate': {},
            'batch': {},
            'warn': []
        }
    )

    all_earnings = []
    completed_ranges = 0
    failed_ranges = 0
    fetch_start = time.time()

    # Dynamic concurrency based on usagePerMin
    max_concurrent = fmp_client.get_rate_limit()
    semaphore = asyncio.Semaphore(max_concurrent)
    results_lock = asyncio.Lock()

    logger.info(f"[fill_earnings] Using dynamic concurrency: {max_concurrent}")

    async def fetch_range_earnings(fmp_client: FMPAPIClient, from_dt: date, to_dt: date):
        nonlocal completed_ranges, failed_ranges
        async with semaphore:
            earnings_data = None
            last_error = None
            
            # Retry logic
            for attempt in range(API_RETRY_COUNT + 1):
                try:
                    earnings_data = await fmp_client.get_earnings_calendar(
                        from_dt.isoformat(),
                        to_dt.isoformat()
                    )
                    break  # Success
                except Exception as e:
                    last_error = e
                    if attempt < API_RETRY_COUNT:
                        await asyncio.sleep(1 * (attempt + 1))  # Backoff
                    continue
            
            async with results_lock:
                if earnings_data is not None:
                    if earnings_data:
                        all_earnings.extend(earnings_data)
                elif last_error:
                    failed_ranges += 1
                    logger.warning(f"[get_earning] Failed to fetch earnings for {from_dt} ~ {to_dt} after {API_RETRY_COUNT+1} attempts: {last_error}")
                
                completed_ranges += 1
                
                # Log progress every batch
                if completed_ranges % API_BATCH_SIZE == 0 or completed_ranges == total_ranges:
                    progress_pct = (completed_ranges / total_ranges) * 100
                    elapsed = time.time() - fetch_start
                    rate = completed_ranges / elapsed if elapsed > 0 else 0
                    remaining = total_ranges - completed_ranges
                    eta_seconds = remaining / rate if rate > 0 else 0
                    eta_str = f"{int(eta_seconds)}s" if eta_seconds < 60 else f"{int(eta_seconds/60)}m {int(eta_seconds%60)}s"
                    
                    logger.info(
                        f"[get_earning] progress={completed_ranges}/{total_ranges}({progress_pct:.1f}%) | records={len(all_earnings)} | ETA: {eta_str}",
                        extra={
                            'endpoint': 'GET /sourceData',
                            'phase': 'earning-fetch',
                            'elapsed_ms': int(elapsed * 1000),
                            'counters': {'success': completed_ranges - failed_ranges, 'fail': failed_ranges},
                            'progress': {'done': completed_ranges, 'total': total_ranges, 'pct': int(progress_pct)},
                            'rate': {'per_second': rate},
                            'batch': {},
                            'warn': []
                        }
                    )

    async with FMPAPIClient() as fmp_client:
        tasks = [fetch_range_earnings(fmp_client, fr, to) for fr, to in date_ranges]
        await asyncio.gather(*tasks)
    
    fetch_elapsed = int((time.time() - fetch_start) * 1000)
    logger.info(f"[get_earning] Fetch complete: {len(all_earnings)} records from {completed_ranges} ranges in {fetch_elapsed}ms")

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

    counters_obj = Counters(
        success=result.get("insert", 0),
        fail=0,
        skip=skipped_count,
        update=0,
        insert=result.get("insert", 0),
        conflict=result.get("conflict", 0)
    )

    return {
        "executed": True,
        "elapsedMs": elapsed_ms,
        "counters": counters_obj.model_dump(),
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
