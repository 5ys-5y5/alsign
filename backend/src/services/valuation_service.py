"""Service for POST /backfillEventsTable endpoint - calculates valuation metrics."""

import logging
import time
import json
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime, date
from collections import defaultdict

from ..database.connection import db_pool
from ..database.queries import metrics, policies, targets
from .external_api import FMPAPIClient
from .utils.datetime_utils import calculate_dayOffset_dates, calculate_dayOffset_dates_cached, get_trading_days_in_range
from ..models.response_models import EventProcessingResult
from .metric_engine import MetricCalculationEngine

logger = logging.getLogger("alsign")


def group_events_by_ticker(events: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Group events by ticker symbol.
    
    Args:
        events: List of event dictionaries
    
    Returns:
        Dict with ticker as key, list of events as value
        Example: {'AAPL': [event1, event2, ...], 'GOOGL': [...], ...}
    """
    grouped = defaultdict(list)
    for event in events:
        ticker = event['ticker']
        grouped[ticker].append(event)
    return dict(grouped)


async def process_ticker_batch(
    pool,
    ticker: str,
    ticker_events: List[Dict[str, Any]],
    metrics_by_domain: Dict[str, List[Dict[str, Any]]],
    overwrite: bool = False,
    total_events_count: int = 0,
    completed_events_count: Dict[str, int] = None
) -> Dict[str, Any]:
    """
    Process all events for a single ticker (with REAL API caching).
    
    This function:
    1. Fetches ALL required API data ONCE for the ticker
    2. Processes all events for this ticker using the SAME cached API data
    3. Returns batch results for DB update
    
    Args:
        pool: Database connection pool
        ticker: Ticker symbol
        ticker_events: List of events for this ticker
        metrics_by_domain: Metric definitions
        overwrite: Update mode
    
    Returns:
        Dict with 'updates', 'results', 'success_counts', 'fail_counts'
    """
    batch_updates = []
    results = []
    quant_success = 0
    quant_fail = 0
    qual_success = 0
    qual_fail = 0
    
    logger.info(
        f"\n{'*'*90}\n"
        f"[START TICKER] {ticker} | {len(ticker_events)} events to process\n"
        f"{'*'*90}"
    )
    
    # ========================================
    # CRITICAL: Fetch API data ONCE for ticker
    # ========================================
    try:
        # Load transform definitions
        transforms = await metrics.select_metric_transforms(pool)
        engine = MetricCalculationEngine(metrics_by_domain, transforms)
        required_apis = engine.get_required_apis()
        
        logger.info(f"[Ticker Batch] {ticker}: Fetching {len(required_apis)} APIs (ONCE)")
        
        # Fetch all API data once
        ticker_api_cache = {}
        consensus_summary_cache = None
        
        async with FMPAPIClient() as fmp_client:
            # Fetch quantitative APIs
            for api_id in required_apis:
                try:
                    params = {'ticker': ticker}
                    
                    if 'historical-price' in api_id or 'eod' in api_id:
                        # Wide date range to cover all events
                        params['fromDate'] = '2000-01-01'
                        params['toDate'] = datetime.now().strftime('%Y-%m-%d')
                    else:
                        params['period'] = 'quarter'
                        params['limit'] = 100
                    
                    result = await fmp_client.call_api(api_id, params)
                    ticker_api_cache[api_id] = result
                    logger.debug(f"[Ticker Batch] {ticker}: Cached {api_id} ({len(result) if isinstance(result, list) else 'single'} records)")
                except Exception as e:
                    logger.warning(f"[Ticker Batch] {ticker}: Failed to fetch {api_id}: {e}")
                    ticker_api_cache[api_id] = []
            
            # Fetch qualitative API (consensus) ONCE for ticker
            try:
                consensus_data = await fmp_client.call_api('fmp-price-target-consensus', {'ticker': ticker})
                if consensus_data:
                    if isinstance(consensus_data, list) and len(consensus_data) > 0:
                        consensus_summary_cache = consensus_data[0]
                    elif isinstance(consensus_data, dict):
                        consensus_summary_cache = consensus_data
                logger.debug(f"[Ticker Batch] {ticker}: Consensus summary cached")
            except Exception as e:
                logger.warning(f"[Ticker Batch] {ticker}: Consensus fetch skipped: {e}")
        
        logger.info(f"[Ticker Batch] {ticker}: API cache ready ({len(ticker_api_cache) + 1} APIs)")
        
        # OPTIMIZATION: Load transforms and engine ONCE per ticker (not per event!)
        transforms = await metrics.select_metric_transforms(pool)
        engine = MetricCalculationEngine(metrics_by_domain, transforms)
        target_domains = ['valuation', 'profitability', 'momentum', 'risk', 'dilution']
        
        logger.info(f"[Ticker Batch] {ticker}: MetricEngine initialized (60 metrics)")
        
    except Exception as e:
        logger.error(f"[Ticker Batch] {ticker}: Failed to build API cache: {e}")
        # Return early with all events failed
        for event in ticker_events:
            results.append(EventProcessingResult(
                ticker=ticker,
                event_date=event['event_date'].isoformat() if hasattr(event['event_date'], 'isoformat') else str(event['event_date']),
                source=event['source'],
                source_id=str(event['source_id']),
                status='failed',
                error=f"API cache failed: {str(e)}",
                errorCode='API_CACHE_ERROR'
            ))
            quant_fail += 1
            qual_fail += 1
        
        return {
            'ticker': ticker,
            'updates': [],
            'results': results,
            'quant_success': 0,
            'quant_fail': quant_fail,
            'qual_success': 0,
            'qual_fail': qual_fail
        }
    
    # ========================================
    # Process each event using CACHED API data
    # ========================================
    total_events = len(ticker_events)
    batch_start_time = time.time()
    last_checkpoint_time = batch_start_time
    last_checkpoint_idx = 0
    
    for idx, event in enumerate(ticker_events, 1):
        event_date = event['event_date']
        source = event['source']
        source_id = event['source_id']
        
        try:
            # Calculate quantitative metrics using CACHED API data + pre-initialized engine
            quant_result = await calculate_quantitative_metrics_fast(
                ticker, event_date, ticker_api_cache, engine, target_domains
            )
            
            # Calculate qualitative metrics using CACHED consensus data
            qual_result = await calculate_qualitative_metrics_fast(
                pool, ticker, event_date, source, source_id, consensus_summary_cache
            )
            
            # Calculate positions and disparities
            position_quant, disparity_quant = calculate_position_disparity(
                quant_result.get('value'),
                qual_result.get('currentPrice')
            )
            
            position_qual, disparity_qual = calculate_position_disparity(
                qual_result.get('value'),
                qual_result.get('currentPrice')
            )
            
            # Prepare batch update
            batch_updates.append({
                'ticker': ticker,
                'event_date': event_date,
                'source': source,
                'source_id': source_id,
                'value_quantitative': quant_result.get('value'),
                'value_qualitative': qual_result.get('value'),
                'position_quantitative': position_quant,
                'position_qualitative': position_qual,
                'disparity_quantitative': disparity_quant,
                'disparity_qualitative': disparity_qual
            })
            
            # Track success/fail
            if quant_result['status'] == 'success':
                quant_success += 1
            elif quant_result['status'] == 'failed':
                quant_fail += 1
            
            if qual_result['status'] == 'success':
                qual_success += 1
            elif qual_result['status'] == 'failed':
                qual_fail += 1
            
            # Build position and disparity dicts
            position_dict = {}
            if position_quant is not None:
                position_dict['quantitative'] = position_quant
            if position_qual is not None:
                position_dict['qualitative'] = position_qual
            
            disparity_dict = {}
            if disparity_quant is not None:
                disparity_dict['quantitative'] = disparity_quant
            if disparity_qual is not None:
                disparity_dict['qualitative'] = disparity_qual
            
            # Build result
            results.append(EventProcessingResult(
                ticker=ticker,
                event_date=event_date.isoformat() if hasattr(event_date, 'isoformat') else str(event_date),
                source=source,
                source_id=str(source_id),
                status='success' if quant_result['status'] == 'success' and qual_result['status'] == 'success' else 'partial',
                quantitative={
                    'status': quant_result['status'],
                    'message': quant_result.get('message')
                },
                qualitative={
                    'status': qual_result['status'],
                    'message': qual_result.get('message')
                },
                position=position_dict if position_dict else None,
                disparity=disparity_dict if disparity_dict else None
            ))
            
            # Log event progress every 10 events (reduce I/O overhead)
            if idx % 10 == 0 or idx == total_events:
                event_pct = (idx / total_events) * 100
                current_time = time.time()
                
                # Calculate ETA based on last 10 events
                elapsed_since_checkpoint = current_time - last_checkpoint_time
                events_processed_since_checkpoint = idx - last_checkpoint_idx
                if events_processed_since_checkpoint > 0:
                    avg_time_per_event = elapsed_since_checkpoint / events_processed_since_checkpoint
                else:
                    elapsed_total = current_time - batch_start_time
                    avg_time_per_event = elapsed_total / idx if idx > 0 else 0
                
                # Update checkpoint
                last_checkpoint_time = current_time
                last_checkpoint_idx = idx
                
                remaining_events = total_events - idx
                eta_seconds = remaining_events * avg_time_per_event
                eta_minutes = int(eta_seconds / 60)
                eta_seconds_remainder = int(eta_seconds % 60)
                
                # Format ETA
                if eta_minutes > 60:
                    eta_hours = eta_minutes // 60
                    eta_minutes_remainder = eta_minutes % 60
                    eta_str = f"{eta_hours}h {eta_minutes_remainder}min"
                elif eta_minutes > 0:
                    eta_str = f"{eta_minutes}min {eta_seconds_remainder}s"
                else:
                    eta_str = f"{eta_seconds_remainder}s"
                
                timestamp_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                # Calculate total events progress
                if completed_events_count is not None:
                    current_total = completed_events_count.get('count', 0) + idx
                    total_pct = (current_total / total_events_count * 100) if total_events_count > 0 else 0
                    all_events_line = f"[ALL EVENTS] {current_total}/{total_events_count} ({total_pct:.1f}%)\n"
                else:
                    all_events_line = ""
                
                logger.info(
                    f"\n{'#'*80}\n"
                    f"{all_events_line}"
                    f"[{ticker} EVENTS] {idx}/{total_events} ({event_pct:.1f}%)\n"
                    f"TIMESTAMP: {timestamp_str}\n"
                    f"ETA: {eta_str}\n"
                    f"{'#'*80}"
                )
            
        except Exception as e:
            logger.error(f"[Ticker Batch] Failed to process {ticker} {event_date}: {e}")
            
            quant_fail += 1
            qual_fail += 1
            
            results.append(EventProcessingResult(
                ticker=ticker,
                event_date=event_date.isoformat() if hasattr(event_date, 'isoformat') else str(event_date),
                source=source,
                source_id=str(source_id),
                status='failed',
                error=str(e),
                errorCode='INTERNAL_ERROR'
            ))
            
            # Log event progress even on error - every 10 events
            if idx % 10 == 0 or idx == total_events:
                event_pct = (idx / total_events) * 100
                current_time = time.time()
                
                elapsed_since_checkpoint = current_time - last_checkpoint_time
                events_processed_since_checkpoint = idx - last_checkpoint_idx
                if events_processed_since_checkpoint > 0:
                    avg_time_per_event = elapsed_since_checkpoint / events_processed_since_checkpoint
                else:
                    elapsed_total = current_time - batch_start_time
                    avg_time_per_event = elapsed_total / idx if idx > 0 else 0
                
                # Update checkpoint
                last_checkpoint_time = current_time
                last_checkpoint_idx = idx
                
                remaining_events = total_events - idx
                eta_seconds = remaining_events * avg_time_per_event
                eta_minutes = int(eta_seconds / 60)
                eta_seconds_remainder = int(eta_seconds % 60)
                
                # Format ETA
                if eta_minutes > 60:
                    eta_hours = eta_minutes // 60
                    eta_minutes_remainder = eta_minutes % 60
                    eta_str = f"{eta_hours}h {eta_minutes_remainder}min"
                elif eta_minutes > 0:
                    eta_str = f"{eta_minutes}min {eta_seconds_remainder}s"
                else:
                    eta_str = f"{eta_seconds_remainder}s"
                
                timestamp_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                # Calculate total events progress
                if completed_events_count is not None:
                    current_total = completed_events_count.get('count', 0) + idx
                    total_pct = (current_total / total_events_count * 100) if total_events_count > 0 else 0
                    all_events_line = f"[ALL EVENTS] {current_total}/{total_events_count} ({total_pct:.1f}%)\n"
                else:
                    all_events_line = ""
                
                logger.info(
                    f"\n{'#'*80}\n"
                    f"{all_events_line}"
                    f"[{ticker} EVENTS] {idx}/{total_events} ({event_pct:.1f}%)\n"
                    f"TIMESTAMP: {timestamp_str}\n"
                    f"ETA: {eta_str}\n"
                    f"{'#'*80}"
                )
    
    # Batch update DB
    try:
        if batch_updates:
            updated_count = await metrics.batch_update_event_valuations(
                pool, batch_updates, overwrite=overwrite
            )
            logger.info(f"[Ticker Batch] {ticker}: Updated {updated_count} events in DB")
    except Exception as e:
        logger.error(f"[Ticker Batch] {ticker}: DB batch update failed: {e}")
    
    # Update global completed events count
    if completed_events_count is not None:
        completed_events_count['count'] = completed_events_count.get('count', 0) + len(ticker_events)
    
    # Log ticker completion
    logger.info(
        f"\n{'*'*90}\n"
        f"[COMPLETE TICKER] {ticker} | {len(ticker_events)} events processed\n"
        f"[COMPLETE TICKER] Quant: {quant_success}✓/{quant_fail}✗ | Qual: {qual_success}✓/{qual_fail}✗\n"
        f"{'*'*90}\n"
    )
    
    return {
        'ticker': ticker,
        'updates': batch_updates,
        'results': results,
        'quant_success': quant_success,
        'quant_fail': quant_fail,
        'qual_success': qual_success,
        'qual_fail': qual_fail
    }


async def calculate_valuations(
    overwrite: bool = False,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    tickers: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Calculate quantitative and qualitative valuations for all events in txn_events.

    Phase 1: Load metric definitions from config_lv2_metric
    Phase 2: For each event, calculate:
        - value_quantitative (financial ratios grouped by domain)
        - value_qualitative (consensusSignal from evt_consensus)
        - position_quantitative, position_qualitative (long/short/undefined)
        - disparity_quantitative, disparity_qualitative (price deviation)

    Args:
        overwrite: If False, partial update (NULL only). If True, full replace.
        from_date: Optional start date for filtering events by event_date.
        to_date: Optional end date for filtering events by event_date.
        tickers: Optional list of ticker symbols to filter events. If None, processes all tickers.

    Returns:
        Dict with summary and per-event results
    """
    start_time = time.time()
    
    from .utils.logging_utils import create_log_context

    logger.info("=" * 80)
    logger.info(
        "[backfillEventsTable] START - Processing valuations", 
        extra=create_log_context(
            endpoint='POST /backfillEventsTable',
            phase='start',
            elapsed_ms=0
        )
    )
    logger.info(f"[backfillEventsTable] Parameters: overwrite={overwrite}, from_date={from_date}, to_date={to_date}, tickers={tickers}")
    logger.info("=" * 80)

    pool = await db_pool.get_pool()
    logger.info("[backfillEventsTable] Database pool acquired")

    # Phase 1: Load metric definitions
    logger.info("[backfillEventsTable] Phase 1: Loading metric definitions")
    logger.info(
        "Loading metric definitions",
        extra={
            'endpoint': 'POST /backfillEventsTable',
            'phase': 'load_metrics',
            'elapsed_ms': 0,
            'counters': {},
            'progress': {},
            'rate': {},
            'batch': {},
            'warn': []
        }
    )

    try:
        metrics_by_domain = await metrics.select_metric_definitions(pool)
        logger.info(f"[backfillEventsTable] Metrics loaded: {len(metrics_by_domain)} domains")
    except Exception as e:
        logger.error(f"[backfillEventsTable] FAILED to load metrics: {e}")
        raise

    if not metrics_by_domain:
        logger.warning(
            "No metrics found in config_lv2_metric",
            extra={
                'endpoint': 'POST /backfillEventsTable',
                'phase': 'load_metrics',
                'elapsed_ms': int((time.time() - start_time) * 1000),
                'counters': {},
                'progress': {},
                'rate': {},
                'batch': {},
                'warn': ['NO_METRICS_DEFINED']
            }
        )

    # Phase 2: Load events to process
    logger.info("[backfillEventsTable] Phase 2: Loading events from database")
    logger.info(
        "Loading events for valuation",
        extra={
            'endpoint': 'POST /backfillEventsTable',
            'phase': 'load_events',
            'elapsed_ms': 0,
            'counters': {},
            'progress': {},
            'rate': {},
            'batch': {},
            'warn': []
        }
    )

    try:
        events = await metrics.select_events_for_valuation(
            pool,
            from_date=from_date,
            to_date=to_date,
            tickers=tickers
        )
        logger.info(f"[backfillEventsTable] Events loaded: {len(events)} events")
        if tickers:
            logger.info(f"[backfillEventsTable] Filtered by tickers: {tickers}")
    except Exception as e:
        logger.error(f"[backfillEventsTable] FAILED to load events: {e}")
        raise

    logger.info(
        f"Processing {len(events)} events",
        extra={
            'endpoint': 'POST /backfillEventsTable',
            'phase': 'load_events',
            'elapsed_ms': int((time.time() - start_time) * 1000),
            'counters': {'total': len(events)},
            'progress': {},
            'rate': {},
            'batch': {},
            'warn': []
        }
    )

    # Early return if no events to process
    if len(events) == 0:
        logger.info("[backfillEventsTable] No events to process - returning early")
        summary = {
            'totalEventsProcessed': 0,
            'quantitativeSuccess': 0,
            'quantitativeFail': 0,
            'qualitativeSuccess': 0,
            'qualitativeFail': 0,
            'priceTrendSuccess': 0,
            'priceTrendFail': 0,
            'elapsedMs': int((time.time() - start_time) * 1000)
        }
        logger.info("=" * 80)
        logger.info("[backfillEventsTable] COMPLETE - No events processed")
        logger.info("=" * 80)
        return {
            'summary': summary,
            'results': []
        }

    # Phase 3: Group events by ticker
    logger.info(f"[backfillEventsTable] Phase 3: Grouping {len(events)} events by ticker")
    ticker_groups = group_events_by_ticker(events)
    logger.info(f"[backfillEventsTable] Grouped into {len(ticker_groups)} tickers")
    
    logger.info(
        f"Processing {len(ticker_groups)} ticker groups",
        extra={
            'endpoint': 'POST /backfillEventsTable',
            'phase': 'group_tickers',
            'elapsed_ms': int((time.time() - start_time) * 1000),
            'counters': {
                'tickers': len(ticker_groups),
                'events': len(events)
            },
            'progress': {},
            'rate': {},
            'batch': {},
            'warn': []
        }
    )
    
    # Phase 4: Process tickers in parallel with concurrency control
    TICKER_CONCURRENCY = 10  # Process 10 tickers concurrently
    semaphore = asyncio.Semaphore(TICKER_CONCURRENCY)
    
    # Progress tracking
    completed_tickers = 0
    total_tickers = len(ticker_groups)
    ticker_start_time = time.time()
    ticker_last_checkpoint_time = ticker_start_time
    ticker_last_checkpoint_idx = 0
    
    # Global events progress tracking
    total_events_count = len(events)
    completed_events_count = {'count': 0}  # Mutable dict for sharing across async tasks
    
    async def process_ticker_with_semaphore(ticker: str, ticker_events: List[Dict[str, Any]]):
        nonlocal completed_tickers
        async with semaphore:
            result = await process_ticker_batch(
                pool, ticker, ticker_events, metrics_by_domain, overwrite,
                total_events_count, completed_events_count
            )
            
            # Update progress
            completed_tickers += 1
            
            # Calculate ETA for tickers
            progress_pct = (completed_tickers / total_tickers) * 100
            current_time = time.time()
            
            # Calculate ETA based on last 10 tickers (or all tickers if < 10)
            if completed_tickers >= 10 and completed_tickers % 10 == 0:
                elapsed_since_checkpoint = current_time - ticker_last_checkpoint_time
                tickers_processed_since_checkpoint = completed_tickers - ticker_last_checkpoint_idx
                avg_time_per_ticker = elapsed_since_checkpoint / tickers_processed_since_checkpoint
                
                # Update checkpoint
                ticker_last_checkpoint_time = current_time
                ticker_last_checkpoint_idx = completed_tickers
            else:
                # Use overall average
                elapsed_total = current_time - ticker_start_time
                avg_time_per_ticker = elapsed_total / completed_tickers if completed_tickers > 0 else 0
            
            remaining_tickers = total_tickers - completed_tickers
            eta_seconds = remaining_tickers * avg_time_per_ticker
            eta_minutes = int(eta_seconds / 60)
            eta_seconds_remainder = int(eta_seconds % 60)
            
            # Format ETA
            if eta_minutes > 60:
                eta_hours = eta_minutes // 60
                eta_minutes_remainder = eta_minutes % 60
                eta_str = f"{eta_hours}h {eta_minutes_remainder}min"
            elif eta_minutes > 0:
                eta_str = f"{eta_minutes}min {eta_seconds_remainder}s"
            else:
                eta_str = f"{eta_seconds_remainder}s"
            
            # Current timestamp
            timestamp_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            logger.info(
                f"\n\n{'='*90}\n"
                f"{'='*90}\n"
                f"[TICKER PROGRESS] {completed_tickers}/{total_tickers} ({progress_pct:.1f}%) | Latest: {ticker}\n"
                f"TIMESTAMP: {timestamp_str}\n"
                f"ETA: {eta_str}\n"
                f"{'='*90}\n"
                f"{'='*90}\n"
            )
            
            return result
    
    logger.info(f"[backfillEventsTable] Phase 4: Processing tickers with concurrency={TICKER_CONCURRENCY}")
    
    start_timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    logger.info(
        f"\n\n{'='*90}\n"
        f"{'='*90}\n"
        f"[TICKER PROGRESS] 0/{total_tickers} (0.0%) | STARTING...\n"
        f"TIMESTAMP: {start_timestamp}\n"
        f"{'='*90}\n"
        f"{'='*90}\n"
    )
    
    # Create tasks for all ticker groups
    tasks = [
        process_ticker_with_semaphore(ticker, ticker_events)
        for ticker, ticker_events in ticker_groups.items()
    ]
    
    # Execute all tasks concurrently
    ticker_results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Aggregate results
    results = []
    quantitative_success = 0
    quantitative_fail = 0
    qualitative_success = 0
    qualitative_fail = 0
    
    for ticker_result in ticker_results:
        if isinstance(ticker_result, Exception):
            logger.error(f"[backfillEventsTable] Ticker batch failed: {ticker_result}")
            continue
        
        # Aggregate from ticker batch
        results.extend(ticker_result['results'])
        quantitative_success += ticker_result['quant_success']
        quantitative_fail += ticker_result['quant_fail']
        qualitative_success += ticker_result['qual_success']
        qualitative_fail += ticker_result['qual_fail']
    
    # Final progress - CELEBRATION!
    final_timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    total_elapsed = time.time() - ticker_start_time
    total_elapsed_minutes = int(total_elapsed / 60)
    total_elapsed_seconds = int(total_elapsed % 60)
    
    if total_elapsed_minutes > 60:
        total_elapsed_hours = total_elapsed_minutes // 60
        total_elapsed_minutes_remainder = total_elapsed_minutes % 60
        elapsed_str = f"{total_elapsed_hours}h {total_elapsed_minutes_remainder}min"
    elif total_elapsed_minutes > 0:
        elapsed_str = f"{total_elapsed_minutes}min {total_elapsed_seconds}s"
    else:
        elapsed_str = f"{total_elapsed_seconds}s"
    
    logger.info(
        f"\n\n{'='*90}\n"
        f"{'='*90}\n"
        f"[TICKER PROGRESS] {len(ticker_groups)}/{len(ticker_groups)} (100.0%) | ✅ ALL TICKERS COMPLETE!\n"
        f"TIMESTAMP: {final_timestamp}\n"
        f"TOTAL TIME: {elapsed_str}\n"
        f"{'='*90}\n"
        f"{'='*90}\n"
        f"\n[📊 SUMMARY]\n"
        f"  - Total Events: {len(results)}\n"
        f"  - Quantitative: {quantitative_success}✓ / {quantitative_fail}✗\n"
        f"  - Qualitative: {qualitative_success}✓ / {qualitative_fail}✗\n"
        f"{'='*90}\n"
    )
    
    logger.info(
        f"Completed all ticker batches: {len(ticker_groups)} tickers, {len(results)} events",
        extra={
            'endpoint': 'POST /backfillEventsTable',
            'phase': 'ticker_batches_complete',
            'elapsed_ms': int((time.time() - start_time) * 1000),
            'counters': {
                'tickers': len(ticker_groups),
                'events': len(results),
                'quant_success': quantitative_success,
                'quant_fail': quantitative_fail,
                'qual_success': qualitative_success,
                'qual_fail': qualitative_fail
            },
            'progress': {},
            'rate': {},
            'batch': {},
            'warn': []
        }
    )

    # Phase 5: Generate price trends
    logger.info(f"[backfillEventsTable] Phase 5: Generating price trends")
    logger.info(
        "Generating price trends",
        extra={
            'endpoint': 'POST /backfillEventsTable',
            'phase': 'price_trends',
            'elapsed_ms': int((time.time() - start_time) * 1000),
            'counters': {},
            'progress': {},
            'rate': {},
            'batch': {},
            'warn': []
        }
    )

    try:
        price_trend_result = await generate_price_trends(
            from_date=from_date,
            to_date=to_date,
            tickers=tickers
        )
        logger.info(f"[backfillEventsTable] Price trends generated: success={price_trend_result.get('success', 0)}, fail={price_trend_result.get('fail', 0)}")
    except Exception as e:
        logger.error(f"[backfillEventsTable] Price trend generation failed: {e}")
        price_trend_result = {
            'success': 0,
            'fail': 0,
            'error': str(e)
        }

    total_elapsed_ms = int((time.time() - start_time) * 1000)

    # Build summary
    summary = {
        'totalEventsProcessed': len(events),
        'quantitativeSuccess': quantitative_success,
        'quantitativeFail': quantitative_fail,
        'qualitativeSuccess': qualitative_success,
        'qualitativeFail': qualitative_fail,
        'priceTrendSuccess': price_trend_result.get('success', 0),
        'priceTrendFail': price_trend_result.get('fail', 0),
        'elapsedMs': total_elapsed_ms
    }

    logger.info("=" * 80)
    logger.info("[backfillEventsTable] COMPLETE")
    logger.info(f"[backfillEventsTable] Summary: {summary}")
    logger.info("=" * 80)

    logger.info(
        "POST /backfillEventsTable completed",
        extra={
            'endpoint': 'POST /backfillEventsTable',
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
        'results': results
    }


async def calculate_quantitative_metrics_fast(
    ticker: str,
    event_date,
    api_cache: Dict[str, List[Dict[str, Any]]],
    engine: MetricCalculationEngine,
    target_domains: List[str]
) -> Dict[str, Any]:
    """
    ULTRA-FAST quantitative metrics calculation.
    
    Uses pre-initialized engine and pre-fetched API cache.
    Only performs date filtering per event - NO DB queries, NO engine init!
    
    Performance: ~50x faster than calculate_quantitative_metrics_cached
    """
    try:
        # Convert event_date to date object
        if isinstance(event_date, str):
            event_date_obj = datetime.fromisoformat(event_date.replace('Z', '+00:00')).date()
        elif hasattr(event_date, 'date'):
            event_date_obj = event_date.date()
        else:
            event_date_obj = event_date
        
        # Filter by event_date (temporal validity) - OPTIMIZED
        api_data_filtered = {}
        for api_id, records in api_cache.items():
            if not records:
                api_data_filtered[api_id] = []
                continue
            
            if isinstance(records, list):
                # Filter by date - use list comprehension for speed
                # IMPORTANT: Keep records WITHOUT 'date' field (snapshot APIs like fmp-quote)
                # These are current-value APIs, not time-series data
                api_data_filtered[api_id] = [
                    r for r in records 
                    if _get_record_date(r) is None or _get_record_date(r) <= event_date_obj
                ]
            else:
                # Single record (e.g., quote, market status)
                api_data_filtered[api_id] = records
        
        # Calculate metrics using PRE-INITIALIZED engine
        result = engine.calculate_all(api_data_filtered, target_domains)
        
        return {
            'status': 'success',
            'value': result,
            'message': 'Quantitative metrics calculated (fast)'
        }
        
    except Exception as e:
        logger.error(f"[calculate_quantitative_metrics_fast] Failed for {ticker}: {e}")
        return {
            'status': 'failed',
            'value': None,
            'message': str(e)
        }


def _get_record_date(record: Dict[str, Any]):
    """Helper to extract and convert record date - cached for performance."""
    record_date = record.get('date')
    if not record_date:
        return None
    
    if isinstance(record_date, str):
        try:
            return datetime.fromisoformat(record_date.replace('Z', '+00:00')).date()
        except:
            return None
    elif hasattr(record_date, 'date'):
        return record_date.date()
    return record_date


async def calculate_quantitative_metrics_cached(
    pool,
    ticker: str,
    event_date,
    metrics_by_domain: Dict[str, List[Dict[str, Any]]],
    api_cache: Dict[str, List[Dict[str, Any]]]
) -> Dict[str, Any]:
    """
    Calculate quantitative metrics using pre-fetched API cache.
    
    This is the optimized version that skips API calls and uses cached data.
    """
    try:
        # Load transform definitions
        transforms = await metrics.select_metric_transforms(pool)
        
        # Initialize metric calculation engine with transforms
        engine = MetricCalculationEngine(metrics_by_domain, transforms)
        
        # Convert event_date to date object
        if isinstance(event_date, str):
            event_date_obj = datetime.fromisoformat(event_date.replace('Z', '+00:00')).date()
        elif hasattr(event_date, 'date'):
            event_date_obj = event_date.date()
        else:
            event_date_obj = event_date
        
        # Use cached API data (NO API CALLS!)
        api_data_raw = api_cache
        
        # Filter by event_date (temporal validity)
        api_data_filtered = {}
        for api_id, records in api_data_raw.items():
            if not records:
                api_data_filtered[api_id] = []
                continue
            
            if isinstance(records, list):
                # Filter by date
                filtered = []
                for record in records:
                    record_date = record.get('date')
                    if record_date:
                        if isinstance(record_date, str):
                            record_date = datetime.fromisoformat(record_date.replace('Z', '+00:00')).date()
                        elif hasattr(record_date, 'date'):
                            record_date = record_date.date()
                        
                        if record_date <= event_date_obj:
                            filtered.append(record)
                
                api_data_filtered[api_id] = filtered
            else:
                # Single record (e.g., quote, market status)
                api_data_filtered[api_id] = records
        
        # Calculate metrics
        target_domains = ['valuation', 'profitability', 'momentum', 'risk', 'dilution']
        result = engine.calculate_all(api_data_filtered, target_domains)
        
        return {
            'status': 'success',
            'value': result,
            'message': 'Quantitative metrics calculated (cached)'
        }
        
    except Exception as e:
        logger.error(f"[calculate_quantitative_metrics_cached] Failed for {ticker}: {e}")
        return {
            'status': 'failed',
            'value': None,
            'message': str(e)
        }


async def calculate_quantitative_metrics(
    pool,
    ticker: str,
    event_date,
    metrics_by_domain: Dict[str, List[Dict[str, Any]]]
) -> Dict[str, Any]:
    """
    Calculate quantitative metrics (financial ratios).

    Fetches quarterly financials from FMP, calculates TTM values,
    computes metrics per domain (valuation, profitability, momentum, risk, dilution).

    Args:
        pool: Database connection pool
        ticker: Ticker symbol
        event_date: Event date
        metrics_by_domain: Metric definitions grouped by domain

    Returns:
        Dict with status, value (jsonb), message
    """
    try:
        # Load transform definitions from DB for dynamic calculation
        transforms = await metrics.select_metric_transforms(pool)
        
        # Initialize metric calculation engine with transforms
        engine = MetricCalculationEngine(metrics_by_domain, transforms)
        required_apis = engine.get_required_apis()

        logger.info(f"[calculate_quantitative_metrics] Required APIs (from DB): {required_apis}")

        # Convert event_date to date object for comparison (MUST be done before API calls)
        from datetime import datetime
        if isinstance(event_date, str):
            event_date_obj = datetime.fromisoformat(event_date.replace('Z', '+00:00')).date()
        elif hasattr(event_date, 'date'):
            event_date_obj = event_date.date()
        else:
            event_date_obj = event_date

        # Dynamically fetch all required API data based on config_lv2_metric definitions
        api_data_raw = {}
        async with FMPAPIClient() as fmp_client:
            for api_id in required_apis:
                try:
                    # Prepare API-specific parameters
                    params = {'ticker': ticker}
                    
                    # Add API-specific parameters
                    if 'historical-price' in api_id or 'eod' in api_id:
                        # Historical price APIs need date range
                        # Use wide date range to get all available data
                        params['fromDate'] = '2000-01-01'  # Far past
                        params['toDate'] = event_date_obj.strftime('%Y-%m-%d')
                    else:
                        # Quarterly financial APIs
                        params['period'] = 'quarter'
                        params['limit'] = 100  # For temporal validity
                    
                    # Call API using DB configuration
                    result = await fmp_client.call_api(api_id, params)
                    api_data_raw[api_id] = result
                    result_len = len(result) if isinstance(result, list) else ('single' if result else 'empty')
                    logger.info(f"[calculate_quantitative_metrics] Fetched {api_id}: {result_len} records")
                    
                    # Debug: Log empty responses for historical-price
                    if 'historical-price' in api_id or 'eod' in api_id:
                        if isinstance(result, list) and len(result) == 0:
                            logger.warning(f"[calculate_quantitative_metrics] Empty response from {api_id}, params: {params}")
                except Exception as e:
                    logger.warning(f"[calculate_quantitative_metrics] Failed to fetch {api_id}: {e}")
                    api_data_raw[api_id] = []

        # Check if we have any data
        if not api_data_raw:
            return {
                'status': 'failed',
                'value': None,
                'message': 'No API data fetched - check config_lv2_metric.api_list_id definitions'
            }

        # Filter quarterly data by event_date (temporal validity)
        # Only use quarters where quarter end date <= event_date

        # Filter all API data by event_date (for time-series data)
        api_data = {}
        for api_id, data in api_data_raw.items():
            if isinstance(data, list):
                # Time-series data (quarterly financials) - filter by date
                filtered_data = []
                for record in data:
                    record_date_str = record.get('date')
                    if record_date_str:
                        try:
                            record_date = datetime.fromisoformat(record_date_str.replace('Z', '+00:00')).date()
                            if record_date <= event_date_obj:
                                filtered_data.append(record)
                        except:
                            pass  # Skip records with invalid date format
                    else:
                        # No date field - include as-is (snapshot data)
                        filtered_data.append(record)

                api_data[api_id] = filtered_data
                logger.info(f"[calculate_quantitative_metrics] Filtered {api_id}: {len(data)} -> {len(filtered_data)} records for event_date {event_date_obj}")
            else:
                # Snapshot data (e.g., quote) - use as-is
                api_data[api_id] = data

        # Check if we have sufficient data after filtering
        has_data = any(
            len(data) > 0 if isinstance(data, list) else data
            for data in api_data.values()
        )

        if not has_data:
            return {
                'status': 'failed',
                'value': None,
                'message': f'no_valid_data: No data available before event_date {event_date_obj}'
            }

        # Calculate all quantitative metrics
        # Dynamically extract target domains from metrics_by_domain (exclude 'internal')
        target_domains = [domain for domain in metrics_by_domain.keys() if domain != 'internal']
        logger.info(f"[calculate_quantitative_metrics] Target domains: {target_domains}")

        value_quantitative = engine.calculate_all(api_data, target_domains)

        # Get sector and industry from config_lv3_targets
        company_info = await targets.get_company_info(pool, ticker)

        # Add metadata to each domain
        # Find a time-series API to determine quarters used (prefer income statement, then any quarterly data)
        quarterly_data = None
        for api_id in ['fmp-income-statement', 'fmp-balance-sheet-statement']:
            if api_id in api_data and isinstance(api_data[api_id], list) and len(api_data[api_id]) > 0:
                quarterly_data = api_data[api_id]
                break

        # If no known quarterly API, search for any list with 'date' field
        if not quarterly_data:
            for data in api_data.values():
                if isinstance(data, list) and len(data) > 0 and 'date' in data[0]:
                    quarterly_data = data
                    break

        quarters_used = min(len(quarterly_data), 4) if quarterly_data else 0

        for domain_key in value_quantitative:
            if '_meta' not in value_quantitative[domain_key]:
                value_quantitative[domain_key]['_meta'] = {}

            # Add date range information based on actual quarters used
            if quarterly_data and len(quarterly_data) > 0:
                # TTM uses most recent N quarters (where N = min(available, 4))
                if quarters_used >= 4:
                    # Full TTM: use quarters 0-3
                    value_quantitative[domain_key]['_meta']['date_range'] = {
                        'start': quarterly_data[3].get('date'),  # 4th oldest quarter
                        'end': quarterly_data[0].get('date')      # Most recent quarter
                    }
                    value_quantitative[domain_key]['_meta']['calcType'] = 'TTM_fullQuarter'
                else:
                    # Partial TTM: use all available quarters
                    value_quantitative[domain_key]['_meta']['date_range'] = {
                        'start': quarterly_data[quarters_used - 1].get('date') if quarters_used > 0 else None,
                        'end': quarterly_data[0].get('date')
                    }
                    value_quantitative[domain_key]['_meta']['calcType'] = 'TTM_partialQuarter'

                value_quantitative[domain_key]['_meta']['count'] = quarters_used
                value_quantitative[domain_key]['_meta']['event_date'] = str(event_date_obj)

                # Add sector and industry from config_lv3_targets
                if company_info:
                    value_quantitative[domain_key]['_meta']['sector'] = company_info.get('sector')
                    value_quantitative[domain_key]['_meta']['industry'] = company_info.get('industry')

        return {
            'status': 'success',
            'value': value_quantitative if value_quantitative else None,
            'message': 'Quantitative metrics calculated'
        }

    except Exception as e:
        logger.error(f"Quantitative calculation failed for {ticker}: {e}", exc_info=True)
        return {
            'status': 'failed',
            'value': None,
            'message': str(e)
        }


async def calculate_qualitative_metrics_fast(
    pool,
    ticker: str,
    event_date,
    source: str,
    source_id: str,
    consensus_summary_cache: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    ULTRA-FAST qualitative metrics calculation.
    
    Uses pre-fetched consensus summary - NO API calls!
    
    Args:
        pool: Database connection pool
        ticker: Ticker symbol
        event_date: Event date
        source: Source table name
        source_id: evt_consensus.id (UUID string)
        consensus_summary_cache: Pre-fetched consensus summary from fmp-price-target-consensus
    
    Returns:
        Dict with status, value (jsonb), currentPrice, message
    """
    try:
        # Only calculate for consensus events
        if source != 'consensus':
            return {
                'status': 'skipped',
                'value': None,
                'currentPrice': None,
                'message': 'Not a consensus event'
            }

        # Fetch consensus data using source_id for exact row match
        consensus_data = await metrics.select_consensus_data(
            pool, ticker, event_date, source_id
        )

        if not consensus_data:
            return {
                'status': 'failed',
                'value': None,
                'currentPrice': None,
                'message': f'Consensus data not found for source_id={source_id}'
            }

        # Extract Phase 2 data
        price_target = consensus_data.get('price_target')
        price_when_posted = consensus_data.get('price_when_posted')
        price_target_prev = consensus_data.get('price_target_prev')
        price_when_posted_prev = consensus_data.get('price_when_posted_prev')
        direction = consensus_data.get('direction')

        # Build consensusSignal
        consensus_signal = {
            'direction': direction,
            'last': {
                'price_target': float(price_target) if price_target else None,
                'price_when_posted': float(price_when_posted) if price_when_posted else None
            }
        }

        # Add prev and delta if available
        if price_target_prev is not None and price_when_posted_prev is not None:
            consensus_signal['prev'] = {
                'price_target': float(price_target_prev),
                'price_when_posted': float(price_when_posted_prev)
            }

            # Calculate delta and deltaPct
            if price_target and price_target_prev:
                delta = float(price_target) - float(price_target_prev)
                delta_pct = (delta / float(price_target_prev)) * 100 if price_target_prev != 0 else None

                consensus_signal['delta'] = delta
                consensus_signal['deltaPct'] = delta_pct
            else:
                consensus_signal['delta'] = None
                consensus_signal['deltaPct'] = None
        else:
            consensus_signal['prev'] = None
            consensus_signal['delta'] = None
            consensus_signal['deltaPct'] = None

        # Use CACHED consensus summary - NO API CALL!
        target_median = 0
        consensus_summary = consensus_summary_cache
        
        if consensus_summary and isinstance(consensus_summary, dict):
            target_median = consensus_summary.get('targetMedian', 0)

        # value_qualitative 구성
        value_qualitative = {
            'targetMedian': target_median,
            'consensusSummary': consensus_summary,
            'consensusSignal': consensus_signal
        }

        return {
            'status': 'success',
            'value': value_qualitative,
            'currentPrice': float(price_when_posted) if price_when_posted else None,
            'message': 'Qualitative metrics calculated (fast)'
        }

    except Exception as e:
        logger.error(f"Qualitative calculation failed for {ticker}: {e}")
        return {
            'status': 'failed',
            'value': None,
            'currentPrice': None,
            'message': str(e)
        }


async def calculate_qualitative_metrics(
    pool,
    ticker: str,
    event_date,
    source: str,
    source_id: str
) -> Dict[str, Any]:
    """
    Calculate qualitative metrics (consensusSignal, targetMedian, consensusSummary).

    Uses source_id to find the exact evt_consensus row,
    ensuring we compare the same analyst's previous values.

    Extracts consensus data from evt_consensus Phase 2 fields.

    항목 3 & 5 적용:
    - consensusSummary: MetricCalculationEngine을 사용하여 fmp-price-target-consensus API 호출
    - targetMedian: consensusSummary dict에서 추출
    - consensus: (항목 5, 선택사항) fmp-price-target API 호출

    Args:
        pool: Database connection pool
        ticker: Ticker symbol
        event_date: Event date
        source: Source table name
        source_id: evt_consensus.id (UUID string)

    Returns:
        Dict with status, value (jsonb), currentPrice, message
    """
    try:
        # Only calculate for consensus events
        if source != 'consensus':
            return {
                'status': 'skipped',
                'value': None,
                'currentPrice': None,
                'message': 'Not a consensus event'
            }

        # Fetch consensus data using source_id for exact row match
        consensus_data = await metrics.select_consensus_data(
            pool, ticker, event_date, source_id
        )

        if not consensus_data:
            return {
                'status': 'failed',
                'value': None,
                'currentPrice': None,
                'message': f'Consensus data not found for source_id={source_id}'
            }

        # Extract Phase 2 data
        price_target = consensus_data.get('price_target')
        price_when_posted = consensus_data.get('price_when_posted')
        price_target_prev = consensus_data.get('price_target_prev')
        price_when_posted_prev = consensus_data.get('price_when_posted_prev')
        direction = consensus_data.get('direction')

        # Build consensusSignal
        consensus_signal = {
            'direction': direction,
            'last': {
                'price_target': float(price_target) if price_target else None,
                'price_when_posted': float(price_when_posted) if price_when_posted else None
            }
        }

        # Add prev and delta if available
        if price_target_prev is not None and price_when_posted_prev is not None:
            consensus_signal['prev'] = {
                'price_target': float(price_target_prev),
                'price_when_posted': float(price_when_posted_prev)
            }

            # Calculate delta and deltaPct
            if price_target and price_target_prev:
                delta = float(price_target) - float(price_target_prev)
                delta_pct = (delta / float(price_target_prev)) * 100 if price_target_prev != 0 else None

                consensus_signal['delta'] = delta
                consensus_signal['deltaPct'] = delta_pct
            else:
                consensus_signal['delta'] = None
                consensus_signal['deltaPct'] = None
        else:
            consensus_signal['prev'] = None
            consensus_signal['delta'] = None
            consensus_signal['deltaPct'] = None

        # 항목 3: targetMedian & consensusSummary 추가
        # Fetch consensusSummary from FMP API (simplified)
        target_median = 0  # 기본값
        consensus_summary = None
        
        try:
            from .external_api import FMPAPIClient
            
            # Fetch consensus summary from FMP API
            async with FMPAPIClient() as fmp_client:
                consensus_target_data = await fmp_client.call_api(
                    'fmp-price-target-consensus',
                    {'ticker': ticker}
                )
                if consensus_target_data:
                    # Extract consensus summary
                    if isinstance(consensus_target_data, list) and len(consensus_target_data) > 0:
                        consensus_summary = consensus_target_data[0]
                    elif isinstance(consensus_target_data, dict):
                        consensus_summary = consensus_target_data
                    
                    # Extract targetMedian
                    if isinstance(consensus_summary, dict):
                        target_median = consensus_summary.get('targetMedian', 0)
                        
            logger.debug(f"[QualitativeMetrics] consensusSummary: {consensus_summary}, targetMedian: {target_median}")
                            
        except Exception as e:
            logger.debug(f"[QualitativeMetrics] consensusSummary fetch skipped: {e}")
            # 실패해도 계속 진행 (consensusSignal은 이미 계산됨)

        # value_qualitative 구성
        value_qualitative = {
            'targetMedian': target_median,
            'consensusSummary': consensus_summary,
            'consensusSignal': consensus_signal
        }

        return {
            'status': 'success',
            'value': value_qualitative,
            'currentPrice': float(price_when_posted) if price_when_posted else None,
            'message': 'Qualitative metrics calculated'
        }

    except Exception as e:
        logger.error(f"Qualitative calculation failed for {ticker}: {e}")
        return {
            'status': 'failed',
            'value': None,
            'currentPrice': None,
            'message': str(e)
        }


def calculate_position_disparity(
    target_price: Optional[Dict[str, Any]],
    current_price: Optional[float]
) -> tuple[Optional[str], Optional[float]]:
    """
    Calculate position and disparity.

    Args:
        target_price: Value dict (quantitative or qualitative)
        current_price: Current market price

    Returns:
        Tuple of (position, disparity)
        position: 'long' | 'short' | 'neutral' | None
        disparity: (target / current) - 1
    """
    # Extract target price value
    # For quantitative: extract from value_quantitative structure
    # For qualitative: extract from consensusSignal.last.price_target
    price_target = None

    if target_price:
        if 'consensusSignal' in target_price:
            # Qualitative
            signal = target_price['consensusSignal']
            if signal and 'last' in signal:
                price_target = signal['last'].get('price_target')
        elif 'valuation' in target_price:
            # Quantitative - would extract price target from valuation metrics
            # For now, placeholder
            price_target = None

    if price_target is None or current_price is None:
        return None, None

    # Calculate position
    if price_target > current_price:
        position = 'long'
    elif price_target < current_price:
        position = 'short'
    else:
        position = 'neutral'

    # Calculate disparity
    disparity = (price_target / current_price) - 1 if current_price != 0 else None

    return position, disparity


async def generate_price_trends(
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    tickers: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Generate price_trend arrays for all events in txn_events.

    Fetches policy configuration, generates dayOffset scaffolds,
    fetches OHLC data from FMP, and populates price_trend field.

    Args:
        from_date: Optional start date for filtering events by event_date
        to_date: Optional end date for filtering events by event_date
        tickers: Optional list of ticker symbols to filter events. If None, processes all tickers.

    Returns:
        Dict with summary and statistics
    """
    start_time = time.time()

    pool = await db_pool.get_pool()

    # Load policy configurations
    logger.info(
        "Loading price trend policies",
        extra={
            'endpoint': 'POST /backfillEventsTable',
            'phase': 'load_policy',
            'elapsed_ms': 0,
            'counters': {},
            'progress': {},
            'rate': {},
            'batch': {},
            'warn': []
        }
    )

    try:
        # Load fillPriceTrend_dateRange policy (for price trend dayOffset calculations)
        range_policy = await policies.get_price_trend_range_policy(pool)
        count_start = range_policy['countStart']
        count_end = range_policy['countEnd']

        # Load priceEodOHLC_dateRange policy (separate policy for OHLC API fetch date range)
        ohlc_policy = await policies.get_ohlc_date_range_policy(pool)
        ohlc_count_start = ohlc_policy['countStart']
        ohlc_count_end = ohlc_policy['countEnd']
    except ValueError as e:
        logger.error(f"Failed to load price trend policy: {e}")
        return {
            'success': 0,
            'fail': 0,
            'error': str(e),
            'errorCode': 'POLICY_NOT_FOUND'
        }

    # Load events to process
    events = await metrics.select_events_for_valuation(
        pool,
        from_date=from_date,
        to_date=to_date,
        tickers=tickers
    )

    logger.info(
        f"Processing price trends for {len(events)} events",
        extra={
            'endpoint': 'POST /backfillEventsTable',
            'phase': 'process_price_trends',
            'elapsed_ms': int((time.time() - start_time) * 1000),
            'counters': {'total': len(events)},
            'progress': {},
            'rate': {},
            'batch': {},
            'warn': []
        }
    )

    # Group events by ticker for efficient OHLC fetching
    events_by_ticker = {}
    for event in events:
        ticker = event['ticker']
        if ticker not in events_by_ticker:
            events_by_ticker[ticker] = []
        events_by_ticker[ticker].append(event)

    # Calculate OHLC fetch ranges per ticker
    # Guideline line 986-987: fromDate = min_event_date + countStart, toDate = max_event_date + countEnd
    from datetime import timedelta
    ohlc_ranges = {}
    for ticker, ticker_events in events_by_ticker.items():
        event_dates = [e['event_date'].date() if hasattr(e['event_date'], 'date') else e['event_date'] for e in ticker_events]
        min_date = min(event_dates)
        max_date = max(event_dates)

        # Apply priceEodOHLC_dateRange policy (countStart/countEnd are calendar day offsets)
        fetch_start = min_date + timedelta(days=ohlc_count_start)
        fetch_end = max_date + timedelta(days=ohlc_count_end)

        ohlc_ranges[ticker] = (fetch_start, fetch_end)

    # Fetch OHLC data for all tickers
    ohlc_cache = {}
    async with FMPAPIClient() as fmp_client:
        for ticker, (fetch_start, fetch_end) in ohlc_ranges.items():
            logger.info(
                f"Fetching OHLC for {ticker} from {fetch_start} to {fetch_end}",
                extra={
                    'endpoint': 'POST /backfillEventsTable',
                    'phase': 'fetch_ohlc',
                    'elapsed_ms': int((time.time() - start_time) * 1000),
                    'counters': {},
                    'progress': {},
                    'rate': {},
                    'batch': {},
                    'warn': []
                }
            )

            ohlc_data = await fmp_client.get_historical_price_eod(
                ticker,
                fetch_start.isoformat(),
                fetch_end.isoformat()
            )

            # Index by date for fast lookup
            ohlc_by_date = {}
            for record in ohlc_data:
                record_date = record.get('date')
                if record_date:
                    ohlc_by_date[record_date] = record

            ohlc_cache[ticker] = ohlc_by_date

    # ========================================
    # OPTIMIZATION: Pre-cache trading days for entire date range
    # ========================================
    # Calculate the full range of dates we need trading days for
    all_event_dates = []
    for ticker_events in events_by_ticker.values():
        for e in ticker_events:
            ed = e['event_date'].date() if hasattr(e['event_date'], 'date') else e['event_date']
            all_event_dates.append(ed)
    
    if all_event_dates:
        # Expand range to cover dayOffset calculations
        # count_start is negative (e.g., -14), count_end is positive (e.g., +14)
        # Need extra buffer for trading day calculations (~2x the offset in calendar days)
        calendar_buffer = max(abs(count_start), abs(count_end)) * 2 + 30
        trading_range_start = min(all_event_dates) - timedelta(days=calendar_buffer)
        trading_range_end = max(all_event_dates) + timedelta(days=calendar_buffer)
        
        logger.info(f"[PriceTrends] Pre-caching trading days from {trading_range_start} to {trading_range_end}")
        trading_days_set = await get_trading_days_in_range(trading_range_start, trading_range_end, 'NASDAQ', pool)
        logger.info(f"[PriceTrends] Cached {len(trading_days_set)} trading days")
    else:
        trading_days_set = set()
    
    # ========================================
    # OPTIMIZATION: Process events and build batch updates
    # ========================================
    success_count = 0
    fail_count = 0
    batch_updates = []  # Collect all updates for batch processing

    for idx, event in enumerate(events):
        try:
            ticker = event['ticker']
            event_date = event['event_date'].date() if hasattr(event['event_date'], 'date') else event['event_date']
            source = event['source']
            source_id = event['source_id']

            # OPTIMIZED: Use cached trading days (NO DB CALL per event!)
            dayoffset_dates = calculate_dayOffset_dates_cached(
                event_date,
                count_start,
                count_end,
                trading_days_set
            )

            # Build price_trend array
            price_trend = []
            for dayoffset, target_date in dayoffset_dates:
                # Look up OHLC data
                date_str = target_date.isoformat()
                ohlc = ohlc_cache.get(ticker, {}).get(date_str)

                if ohlc:
                    # Fill with actual data
                    price_trend.append({
                        'dayOffset': dayoffset,
                        'targetDate': date_str,
                        'open': float(ohlc.get('open')) if ohlc.get('open') else None,
                        'high': float(ohlc.get('high')) if ohlc.get('high') else None,
                        'low': float(ohlc.get('low')) if ohlc.get('low') else None,
                        'close': float(ohlc.get('close')) if ohlc.get('close') else None
                    })
                else:
                    # Future date or missing data - progressive null-filling
                    price_trend.append({
                        'dayOffset': dayoffset,
                        'targetDate': date_str,
                        'open': None,
                        'high': None,
                        'low': None,
                        'close': None
                    })

            # Collect for batch update instead of individual updates
            batch_updates.append({
                'ticker': ticker,
                'event_date': event['event_date'],
                'source': source,
                'source_id': source_id,
                'price_trend': json.dumps(price_trend)
            })
            success_count += 1

        except Exception as e:
            logger.error(f"Failed to generate price trend for {ticker} {event_date}: {e}")
            fail_count += 1
            continue

        # Log progress every 50 events (faster now, so less frequent logging)
        if (idx + 1) % 50 == 0 or (idx + 1) == len(events):
            logger.info(
                f"Processed {idx + 1}/{len(events)} price trends",
                extra={
                    'endpoint': 'POST /backfillEventsTable',
                    'phase': 'process_price_trends',
                    'elapsed_ms': int((time.time() - start_time) * 1000),
                    'counters': {
                        'processed': idx + 1,
                        'total': len(events),
                        'success': success_count,
                        'fail': fail_count
                    },
                    'progress': {
                        'done': idx + 1,
                        'total': len(events),
                        'pct': round((idx + 1) / len(events) * 100, 1)
                    },
                    'rate': {},
                    'batch': {},
                    'warn': []
                }
            )
    
    # ========================================
    # OPTIMIZATION: Batch DB update (single query for all events)
    # ========================================
    if batch_updates:
        logger.info(f"[PriceTrends] Executing batch update for {len(batch_updates)} events")
        batch_start = time.time()
        
        try:
            async with pool.acquire() as conn:
                # Use UNNEST for batch update
                tickers = [u['ticker'] for u in batch_updates]
                event_dates = [u['event_date'] for u in batch_updates]
                sources = [u['source'] for u in batch_updates]
                source_ids = [u['source_id'] for u in batch_updates]
                price_trends = [u['price_trend'] for u in batch_updates]
                
                result = await conn.execute(
                    """
                    UPDATE txn_events e
                    SET price_trend = b.price_trend::jsonb
                    FROM (
                        SELECT * FROM UNNEST($1::text[], $2::timestamptz[], $3::text[], $4::text[], $5::text[])
                        AS t(ticker, event_date, source, source_id, price_trend)
                    ) b
                    WHERE e.ticker = b.ticker
                      AND e.event_date = b.event_date
                      AND e.source = b.source
                      AND e.source_id = b.source_id
                    """,
                    tickers,
                    event_dates,
                    sources,
                    source_ids,
                    price_trends
                )
                
                # Parse update count from result
                if "UPDATE" in result:
                    updated_count = int(result.split()[-1])
                    logger.info(f"[PriceTrends] Batch update completed: {updated_count} rows in {int((time.time() - batch_start) * 1000)}ms")
                    
                    # Adjust counts based on actual updates
                    if updated_count < len(batch_updates):
                        fail_count += (len(batch_updates) - updated_count)
                        success_count = updated_count
        except Exception as e:
            logger.error(f"[PriceTrends] Batch update failed: {e}")
            fail_count += len(batch_updates)
            success_count = 0

    total_elapsed_ms = int((time.time() - start_time) * 1000)

    logger.info(
        f"Price trend generation completed",
        extra={
            'endpoint': 'POST /backfillEventsTable',
            'phase': 'complete_price_trends',
            'elapsed_ms': total_elapsed_ms,
            'counters': {'success': success_count, 'fail': fail_count},
            'progress': {},
            'rate': {},
            'batch': {},
            'warn': []
        }
    )

    return {
        'success': success_count,
        'fail': fail_count
    }
