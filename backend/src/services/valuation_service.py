"""Service for POST /backfillEventsTable endpoint - calculates valuation metrics."""

import logging
import time
import json
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime, date, timedelta
from collections import defaultdict

from ..database.connection import db_pool
from ..database.queries import metrics, policies, targets, consensus
from .external_api import FMPAPIClient
from .utils.datetime_utils import calculate_dayOffset_dates, calculate_dayOffset_dates_cached, get_trading_days_in_range
# I-42: Removed formatter imports - formatting should only be done in API responses, not database storage
# from .utils.response_formatter import format_value_quantitative, format_value_qualitative
from ..models.response_models import EventProcessingResult
from .metric_engine import MetricCalculationEngine
from ..utils.logging_utils import (
    log_error, log_warning, log_event_update, log_batch_start, log_batch_complete, log_db_update
)
from .utils.batch_utils import calculate_eta, format_eta_ms
from .utils.quantitative_cache import (
    get_peer_tickers_from_db,
    get_batch_peer_tickers_from_db,
    get_quantitative_data_from_db,
    get_batch_quantitative_data_from_db,
    calculate_sector_average_from_cache,
    calculate_sector_average_metrics_from_db,
    calculate_fair_value_from_sector
)

logger = logging.getLogger("alsign")

# Configuration: Maximum concurrent OpenAI API calls
MAX_CONCURRENT_QUALITATIVE = 10  # Adjust based on OpenAI rate limits

# Configuration: Maximum concurrent event processing (quantitative + position/disparity)
MAX_CONCURRENT_EVENTS = 20  # Adjust based on system resources


def remove_meta_from_value_quantitative(value_quantitative: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Remove _meta data from value_quantitative JSONB field.

    _meta was used for validation purposes during development, but is no longer needed
    in production outputs.

    Args:
        value_quantitative: Value quantitative data (e.g., {"valuation": {...}, "profitability": {...}})

    Returns:
        Value quantitative data without _meta fields
    """
    if not value_quantitative or not isinstance(value_quantitative, dict):
        return value_quantitative

    cleaned = {}
    for domain_key, domain_value in value_quantitative.items():
        if isinstance(domain_value, dict):
            # Remove _meta from this domain
            cleaned[domain_key] = {k: v for k, v in domain_value.items() if k != '_meta'}
        else:
            cleaned[domain_key] = domain_value

    return cleaned


async def process_single_event_parallel(
    event: Dict[str, Any],
    idx: int,
    total_events: int,
    ticker: str,
    ticker_api_cache: Dict[str, Any],
    engine: Any,
    target_domains: List[str],
    qual_result: Dict[str, Any],
    sector_averages: Dict[str, float],
    peer_count: int,
    overwrite: bool,
    metrics_list: Optional[List[str]]
) -> Dict[str, Any]:
    """
    Process a single event: calculate quantitative, position, disparity.

    This function is designed to be called in parallel for multiple events.
    All async operations (quantitative calculation) are awaited here.

    Args:
        event: Event dictionary
        idx: Event index (1-based)
        total_events: Total event count
        ticker: Ticker symbol
        ticker_api_cache: Cached API data
        engine: MetricCalculationEngine
        target_domains: Domains to calculate
        qual_result: Pre-calculated qualitative result
        sector_averages: Sector average metrics
        peer_count: Number of peers
        overwrite: Update mode
        metrics_list: Metrics to update

    Returns:
        Dictionary ready for DB update
    """
    event_id = event.get('id')
    event_date = event['event_date']
    source = event['source']
    source_id = event['source_id']

    event_id_str = str(event_id) if event_id else "unknown"
    row_context = f"[table: txn_events | id: {event_id_str}]"

    # Define key metrics to track for summary logging
    track_metrics = ['PER', 'PBR', 'PSR', 'priceQuantitative', 'ROE', 'ROA']

    try:
        # I-41: Prepare custom_values for priceQuantitative metric
        base_custom_values = {
            '_row_context': row_context,
            '_suppress_calc_fail_logs': True
        }
        custom_values = dict(base_custom_values)
        current_price_for_position = None

        if sector_averages:
            # First, calculate basic quantitative metrics (PER, PBR, etc.)
            temp_quant_result = await calculate_quantitative_metrics_fast(
                ticker, event_date, ticker_api_cache, engine, target_domains,
                custom_values=base_custom_values
            )

            # Get current price for priceQuantitative calculation
            current_price = None
            if source == 'consensus':
                # Use PRE-CALCULATED qualitative result
                current_price = qual_result.get('currentPrice')
            else:
                # For earning events: get historical price from cache
                if 'fmp-historical-price-eod-full' in ticker_api_cache:
                    historical_prices = ticker_api_cache['fmp-historical-price-eod-full']
                    if isinstance(historical_prices, list):
                        if isinstance(event_date, str):
                            target_date = datetime.fromisoformat(event_date.replace('Z', '+00:00')).date()
                        elif hasattr(event_date, 'date'):
                            target_date = event_date.date()
                        else:
                            target_date = event_date

                        for price_record in historical_prices:
                            record_date_str = price_record.get('date')
                            if record_date_str:
                                try:
                                    record_date = datetime.fromisoformat(record_date_str.replace('Z', '+00:00')).date()
                                    if record_date == target_date:
                                        current_price = price_record.get('close')
                                        break
                                except:
                                    continue

            current_price_for_position = current_price

            if current_price and temp_quant_result.get('value'):
                # calculate_fair_value_from_sector is imported at top of file
                fair_value, fair_value_method = calculate_fair_value_from_sector_with_method(
                    temp_quant_result.get('value'),
                    sector_averages,
                    current_price
                )
                if fair_value is not None:
                    custom_values['priceQuantitative'] = fair_value

        # Calculate quantitative metrics with custom values and track key metrics
        quant_result = await calculate_quantitative_metrics_fast(
            ticker, event_date, ticker_api_cache, engine, target_domains,
            custom_values=custom_values, track_metrics=track_metrics
        )

        # Calculate positions and disparities
        value_quant = quant_result.get('value', {})
        current_price = qual_result.get('currentPrice')
        if not current_price and current_price_for_position:
            current_price = current_price_for_position

        # Extract priceQuantitative
        price_quant_value = None
        if value_quant and 'valuation' in value_quant:
            price_quant_value = value_quant['valuation'].get('priceQuantitative')
            if price_quant_value is not None and fair_value_method:
                # Record method only for priceQuantitative
                value_quant['valuation']['priceQuantitative_meta'] = {
                    'method': fair_value_method
                }

        # ============================================================
        # I-45 Phase 4: Position & Disparity Calculation
        # ============================================================
        # NOT registered in config_lv2_metric
        # Reason: Simple comparison logic, no need for separate metric registration
        # Kept in Python for simplicity and direct integration
        #
        # These calculations are derived from priceQuantitative (fair value):
        # - position_quant: Investment recommendation (long/short/neutral)
        # - disparity_quant: Percentage deviation from fair value
        # ============================================================
        if price_quant_value is not None and current_price:
            # Position calculation: Compare fair value vs current price
            if price_quant_value > current_price:
                # LONG: Stock is undervalued
                # Fair value > Current price → Buy signal
                # Example: fair_value=$150, current_price=$100 → LONG (50% undervalued)
                position_quant = 'long'
            elif price_quant_value < current_price:
                # SHORT: Stock is overvalued
                # Fair value < Current price → Sell signal
                # Example: fair_value=$80, current_price=$100 → SHORT (25% overvalued)
                position_quant = 'short'
            else:
                # NEUTRAL: Fair value = Current price
                # Stock is fairly valued
                position_quant = 'neutral'

            # ============================================================
            # Disparity calculation: (fair_value / current_price) - 1
            # ============================================================
            # Positive value = undervalued (fair_value > current_price)
            # Negative value = overvalued (fair_value < current_price)
            # Zero = fairly valued
            #
            # Example calculations:
            #   fair_value=$150, current_price=$100
            #   disparity = (150 / 100) - 1 = 0.5 (50% undervalued)
            #
            #   fair_value=$80, current_price=$100
            #   disparity = (80 / 100) - 1 = -0.2 (20% overvalued)
            # ============================================================
            disparity_quant = round((price_quant_value / current_price) - 1, 4) if current_price != 0 else None
        else:
            # Fallback: calculate_position_disparity is defined later in this file
            # Python will find it at runtime
            position_quant, disparity_quant = calculate_position_disparity(
                quant_result.get('value'),
                qual_result.get('currentPrice')
            )

        # Calculate qualitative position/disparity
        position_qual, disparity_qual = calculate_position_disparity(
            qual_result.get('value'),
            qual_result.get('currentPrice')
        )

        # Store raw values
        value_qual = qual_result.get('value')

        # Extract priceQuantitative for dedicated column
        price_quant_col = None
        if value_quant and 'valuation' in value_quant:
            price_quant_col = value_quant['valuation'].get('priceQuantitative')

        # Build peer_quantitative JSONB
        peer_quant_col = None
        fair_value_method = None
        if sector_averages:
            peer_quant_col = {
                'peerCount': peer_count,
                'sectorAverages': sector_averages,
                'fairValueMethod': fair_value_method
            }

        # Log at debug level only (remove per-event logs to prevent excessive output)
        if quant_result['status'] != 'success':
            logger.debug(f"Failed: txn_events.id={event_id_str}, reason={quant_result.get('message', 'Unknown')}")

        # Remove _meta from value_quantitative before storing
        value_quant_cleaned = remove_meta_from_value_quantitative(value_quant)

        # Return update dictionary
        result = {
            'ticker': ticker,
            'event_date': event_date,
            'source': source,
            'source_id': source_id,
            'value_quantitative': value_quant_cleaned,
            'value_qualitative': value_qual,
            'position_quantitative': position_quant,
            'position_qualitative': position_qual,
            'disparity_quantitative': disparity_quant,
            'disparity_qualitative': disparity_qual,
            'price_quantitative': price_quant_col,
            'peer_quantitative': peer_quant_col,
            'quant_status': quant_result['status'],
            'qual_status': qual_result['status'],
            'event_id': event_id
        }

        # Add metric_status for summary logging
        if 'metric_status' in quant_result:
            result['metric_status'] = quant_result['metric_status']
        if qual_result.get('warnings'):
            result['qual_warnings'] = qual_result['warnings']

        return result

    except Exception as e:
        logger.error(f"Failed: txn_events.id={event_id_str}, reason={str(e)}")
        return {
            'ticker': ticker,
            'event_date': event_date,
            'source': source,
            'source_id': source_id,
            'quant_status': 'failed',
            'qual_status': qual_result.get('status', 'failed'),
            'error': str(e),
            'event_id': event_id
        }


async def batch_process_events_parallel(
    ticker: str,
    events: List[Dict[str, Any]],
    ticker_api_cache: Dict[str, Any],
    engine: Any,
    target_domains: List[str],
    qual_cache: Dict[str, Dict],
    sector_averages: Dict[str, float],
    peer_count: int,
    overwrite: bool,
    metrics_list: Optional[List[str]],
    max_concurrent: int = MAX_CONCURRENT_EVENTS
) -> List[Dict[str, Any]]:
    """
    Process all events in parallel with concurrency control.

    This function uses asyncio.Semaphore to limit concurrent event processing,
    preventing resource exhaustion while maximizing throughput.

    Args:
        ticker: Ticker symbol
        events: List of events to process
        ticker_api_cache: Cached API data
        engine: MetricCalculationEngine
        target_domains: Domains to calculate
        qual_cache: Pre-calculated qualitative results
        sector_averages: Sector average metrics
        peer_count: Number of peers
        overwrite: Update mode
        metrics_list: Metrics to update
        max_concurrent: Maximum concurrent processing (default: 20)

    Returns:
        List of update dictionaries ready for DB
    """
    semaphore = asyncio.Semaphore(max_concurrent)
    total_events = len(events)

    async def process_with_limit(event, idx):
        """Helper function to process event with semaphore control."""
        async with semaphore:
            event_key = f"{event['event_date']}_{event['source']}_{event['source_id']}"
            qual_result = qual_cache.get(event_key, {
                'status': 'failed',
                'message': 'Not found in qualitative cache',
                'currentPrice': None,
                'value': None
            })

            return await process_single_event_parallel(
                event, idx, total_events, ticker, ticker_api_cache, engine,
                target_domains, qual_result, sector_averages, peer_count,
                overwrite, metrics_list
            )

    # Create tasks for all events
    tasks = [process_with_limit(event, idx) for idx, event in enumerate(events, 1)]

    # Execute all tasks in parallel (with semaphore limiting concurrency)
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Filter out exceptions and return valid results
    valid_results = []
    for result in results:
        if isinstance(result, dict):
            valid_results.append(result)
        else:
            logger.error(f"Failed: Unexpected exception during parallel event processing: {result}")

    return valid_results


async def batch_calculate_qualitative_parallel(
    pool,
    ticker: str,
    events: List[Dict[str, Any]],
    engine: MetricCalculationEngine,
    max_concurrent: int = MAX_CONCURRENT_QUALITATIVE
) -> Dict[str, Dict]:
    """
    Batch calculate qualitative metrics for multiple events (DB-driven).

    Uses calculate_qualitative_metrics_fast which:
    - Fetches priceTarget data from evt_consensus (DB)
    - Delegates calculation to MetricCalculationEngine (DB calculation code)

    Args:
        pool: Database connection pool
        ticker: Ticker symbol
        events: List of events for this ticker
        engine: Pre-initialized MetricCalculationEngine
        max_concurrent: Max concurrent calculations

    Returns:
        Dict mapping event_key to qualitative result
        Example: {"2024-01-15_consensus_uuid": {"status": "success", ...}, ...}
    """
    semaphore = asyncio.Semaphore(max_concurrent)

    async def calculate_with_limit(event):
        """Helper function to calculate qualitative with semaphore control."""
        async with semaphore:
            event_date = event['event_date']
            source = event['source']
            source_id = event['source_id']

            # Create unique key for this event
            event_key = f"{event_date}_{source}_{source_id}"

            # Call DB-driven calculation
            qual_result = await calculate_qualitative_metrics_fast(
                pool, ticker, event_date, source, source_id, engine, suppress_logs=True
            )

            return event_key, qual_result

    # Create tasks for all events
    tasks = [calculate_with_limit(event) for event in events]

    # Execute all tasks in parallel
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Convert results to dict
    qual_cache = {}
    for result in results:
        if isinstance(result, tuple):
            event_key, qual_result = result
            qual_cache[event_key] = qual_result
        else:
            logger.error(f"Failed: Unexpected exception during qualitative calculation: {result}")

    return qual_cache


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
    completed_events_count: Dict[str, int] = None,
    metrics_list: Optional[List[str]] = None,
    global_peer_cache: Dict[str, Dict[str, Any]] = None,
    ticker_to_peers: Dict[str, List[str]] = None,
    verbose: bool = False
) -> Dict[str, Any]:
    """
    Process all events for a single ticker (with REAL API caching + GLOBAL PEER CACHE).

    This function:
    1. Fetches ALL required API data ONCE for the ticker
    2. Uses GLOBAL PEER CACHE for sector averages (no per-ticker peer fetching)
    3. Processes all events for this ticker using the SAME cached API data
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

    if verbose:
        log_batch_start(logger, ticker, len(ticker_events))
    
    # ========================================
    # CRITICAL: Fetch API data ONCE for ticker
    # ========================================
    try:
        # Load transform definitions
        transforms = await metrics.select_metric_transforms(pool)
        engine = MetricCalculationEngine(metrics_by_domain, transforms)
        required_apis = engine.get_required_apis()
        
        # Use special event_id format for ticker-level API calls
        ticker_context_id = f"ticker-cache:{ticker}"

    
        # ========================================
        # NEW: DB에서 quantitative 데이터 조회 (API 호출 제거!)
        # ========================================
        ticker_api_cache = await get_quantitative_data_from_db(pool, ticker, required_apis)

        if not ticker_api_cache:
            log_warning(
                logger,
                f"No quantitative data for {ticker}. Run POST /getQuantitatives first.",
                ticker=ticker
            )
            # 빈 결과 반환 - 이 ticker는 실패로 처리됨
            logger.info(f"[table: txn_events | id: {ticker_context_id}] | ========== TICKER-LEVEL DB CACHING FAILED ==========")
            return {
                'updates': [],
                'results': [],
                'success_counts': {'quant': 0, 'qual': 0},
                'fail_counts': {'quant': len(ticker_events), 'qual': len(ticker_events)}
            }

        # OPTIMIZATION: Load transforms and engine ONCE per ticker (not per event!)
        transforms = await metrics.select_metric_transforms(pool)
        engine = MetricCalculationEngine(metrics_by_domain, transforms)
        target_domains = ['valuation', 'profitability', 'momentum', 'risk', 'dilution']
        

        # ========================================
        # CRITICAL: Use GLOBAL PEER CACHE (PERFORMANCE OPTIMIZATION)
        # ========================================
        # IMPORTANT: Always calculate priceQuantitative for ALL events (source-agnostic)
        # per user requirement: "quantitative columns must be filled regardless of source value"
        peer_tickers = []
        sector_averages = {}
        peer_count = 0

        try:
            # USE GLOBAL PEER CACHE if available (PERFORMANCE OPTIMIZATION)
            if global_peer_cache and ticker_to_peers:
                # Get pre-collected peer list for this ticker
                peer_tickers = ticker_to_peers.get(ticker, [])
                peer_count = len(peer_tickers)

                if peer_tickers:

                    # Calculate sector averages from GLOBAL CACHE (no API calls!)
                    # Uses quantitative_cache.calculate_sector_average_from_cache (DB mode)
                    sector_averages = await calculate_sector_average_from_cache(
                        peer_tickers, global_peer_cache
                    )
                    if not sector_averages and ticker_events:
                        reference_date = ticker_events[0]['event_date']
                        logger.warning(
                            f"[PERF-OPT] Empty sector averages from global cache for {ticker}. "
                            "Falling back to DB-based peer metrics."
                        )
                        sector_averages = await calculate_sector_average_metrics_from_db(
                            pool, peer_tickers, reference_date, metrics_by_domain
                        )

            else:
                # FALLBACK: DB에서 peer 데이터 조회 (API 호출 대신!)
                peer_tickers = await get_peer_tickers_from_db(pool, ticker)
                peer_count = len(peer_tickers)

                if peer_tickers and ticker_events:
                    # Use first event's date as reference for sector averages
                    reference_date = ticker_events[0]['event_date']
                    # DB 기반 sector average 계산 (API 호출 없음!)
                    sector_averages = await calculate_sector_average_metrics_from_db(
                        pool, peer_tickers, reference_date, metrics_by_domain
                    )

        except Exception as e:
            logger.error(f"Failed: ticker={ticker}, reason=Failed to process peer data: {e}")
            sector_averages = {}

    except Exception as e:
        log_error(logger, f"Failed to build API cache for {ticker}", exception=e, ticker=ticker)
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


    qual_cache = await batch_calculate_qualitative_parallel(
        pool, ticker, ticker_events, engine, max_concurrent=MAX_CONCURRENT_QUALITATIVE
    )

    batch_updates = await batch_process_events_parallel(
        ticker, ticker_events, ticker_api_cache, engine, target_domains,
        qual_cache, sector_averages, peer_count, overwrite, metrics_list,
        max_concurrent=MAX_CONCURRENT_EVENTS
    )

    # Count success/fail from parallel results
    quant_success = sum(1 for r in batch_updates if r.get('quant_status') == 'success')
    quant_fail = sum(1 for r in batch_updates if r.get('quant_status') != 'success')
    qual_success = sum(1 for r in batch_updates if r.get('qual_status') == 'success')
    qual_fail = sum(1 for r in batch_updates if r.get('qual_status') != 'success')

    # Build results list for compatibility
    results = []
    for update in batch_updates:
        results.append(EventProcessingResult(
            ticker=update['ticker'],
            event_date=update['event_date'].isoformat() if hasattr(update['event_date'], 'isoformat') else str(update['event_date']),
            source=update['source'],
            source_id=str(update['source_id']),
            status='success' if update.get('quant_status') == 'success' and update.get('qual_status') == 'success' else 'partial',
            quantitative={
                'status': update.get('quant_status', 'unknown'),
                'message': update.get('error') if update.get('quant_status') != 'success' else None
            },
            qualitative={
                'status': update.get('qual_status', 'unknown'),
                'message': update.get('error') if update.get('qual_status') != 'success' else None
            }
        ))

    # ========================================
    # EVENT PROCESSING COMPLETED - Ready for DB update
    # ========================================

    # Skip deprecated sequential processing code (replaced by parallel processing above)
    # Old code removed for clarity - git history available if needed

    # Batch update DB
    try:
        if batch_updates:
            # I-41: Pass selective metric update parameters
            updated_count = await metrics.batch_update_event_valuations(
                pool, batch_updates, overwrite=overwrite,
                metrics=metrics_list
            )
            log_db_update(logger, "txn_events", updated_count, len(batch_updates))
    except Exception as e:
        log_error(logger, f"DB batch update failed for {ticker}", exception=e, ticker=ticker)

    # Update global completed events count
    if completed_events_count is not None:
        completed_events_count['count'] = completed_events_count.get('count', 0) + len(ticker_events)

    # Log ticker completion (verbose only)
    if verbose:
        log_batch_complete(logger, ticker, len(ticker_events), quant_success + qual_success, quant_fail + qual_fail)

    # ========================================
    # TICKER SUMMARY: Aggregate metric status
    # ========================================
    # Collect metric status from all events and create summary
    if batch_updates:
        # Track metrics across all events
        metric_totals = {}
        for update in batch_updates:
            if 'metric_status' in update:
                for metric_name, success in update['metric_status'].items():
                    if metric_name not in metric_totals:
                        metric_totals[metric_name] = {'success': 0, 'fail': 0}
                    if success:
                        metric_totals[metric_name]['success'] += 1
                    else:
                        metric_totals[metric_name]['fail'] += 1

        # Build summary string: metric1=o/x, metric2=o/x, ...
        if metric_totals and verbose:
            summary_parts = []
            for metric_name in sorted(metric_totals.keys()):
                success_count = metric_totals[metric_name]['success']
                fail_count = metric_totals[metric_name]['fail']
                total_count = success_count + fail_count

                # Use unicode symbols: ✓ for success, ✗ for fail
                summary_parts.append(f"{metric_name}={success_count}✓/{fail_count}✗")

            # Log ticker-level summary (verbose mode only)
            logger.info(f"[TICKER] {ticker}: {quant_success}✓/{quant_fail}✗ | {', '.join(summary_parts)}")

    return {
        'ticker': ticker,
        'updates': batch_updates,
        'results': results,
        'quant_success': quant_success,
        'quant_fail': quant_fail,
        'qual_success': qual_success,
        'qual_fail': qual_fail
    }


# OLD SEQUENTIAL CODE REMOVED
# The sequential event processing loop has been replaced by parallel processing above
# Git history contains the original implementation if needed for reference

async def process_single_batch(
    pool,
    batch_size: Optional[int],
    from_date: Optional[date],
    to_date: Optional[date],
    tickers: Optional[List[str]],
    overwrite: bool,
    metrics_list: Optional[List[str]],
    metrics_by_domain: Dict[str, List[Dict[str, Any]]],
    max_workers: int,
    start_time: float,
    batch_number: int,
    cancel_event: Optional[asyncio.Event] = None
) -> Optional[Dict[str, Any]]:
    """
    Process a single batch of events (Phase 2-4).

    Args:
        pool: Database connection pool
        batch_size: Number of tickers to process in this batch
        from_date, to_date, tickers, overwrite, metrics_list: Filter parameters
        metrics_by_domain: Pre-loaded metric definitions
        max_workers: Concurrency limit
        start_time: Overall start time for elapsed calculation
        batch_number: Current batch number (for logging)

    Returns:
        Dict with batch results or None if no events to process
    """
    if not tickers:
        return None

    # Phase 2: Prepare ticker batch
    phase2_start = time.time()
    if batch_size:
        logger.info(f"[Batch {batch_number}] Phase 2: Prepared {len(tickers):,} tickers (overwrite={overwrite})")
    else:
        logger.info(f"[Phase 2] Prepared {len(tickers):,} tickers (overwrite={overwrite})")

    # Phase 3.5: Global Peer Collection (INDEPENDENT PER BATCH!)
    global_peer_cache = {}
    ticker_to_peers = {}

    try:
        # Step 1: Load peer mappings
        peer_collect_start = time.time()
        ticker_to_peers = await get_batch_peer_tickers_from_db(pool, list(tickers))

        # Limit to 10 peers per ticker
        unique_peers = set()
        for ticker, peer_list in ticker_to_peers.items():
            if peer_list:
                ticker_to_peers[ticker] = peer_list[:10]
                unique_peers.update(peer_list[:10])

        peer_collect_elapsed = time.time() - peer_collect_start

        # Step 2: Load peer financials
        if unique_peers:
            peer_fetch_start = time.time()

            transforms = await metrics.select_metric_transforms(pool)
            engine = MetricCalculationEngine(metrics_by_domain, transforms)
            required_apis = engine.get_required_apis()
            required_apis_with_ratios = set(required_apis)
            required_apis_with_ratios.add('fmp-ratios')

            global_peer_cache = await get_batch_quantitative_data_from_db(
                pool,
                list(unique_peers),
                list(required_apis_with_ratios)
            )

            peer_fetch_elapsed = time.time() - peer_fetch_start
            logger.info(f"[Batch {batch_number}] Phase 3.5: Loaded {len(global_peer_cache):,} peers in {peer_fetch_elapsed:.2f}s")
        else:
            logger.warning(f"[Batch {batch_number}] Phase 3.5: No peer tickers found")
            global_peer_cache = {}

    except Exception as e:
        logger.error(f"[Batch {batch_number}] Phase 3.5 Failed to build peer cache: {e}")
        global_peer_cache = {}
        ticker_to_peers = {}

    # Phase 4: Process tickers in parallel
    semaphore = asyncio.Semaphore(max_workers)

    # Progress tracking
    completed_tickers = 0
    total_tickers = len(tickers)
    total_events_count = 0
    completed_events_count = {'count': 0}

    async def process_ticker_with_semaphore(ticker: str):
        nonlocal completed_tickers

        if cancel_event and cancel_event.is_set():
            logger.warning(f"[Batch {batch_number}] Cancelled - skipping ticker {ticker}")
            return {
                'ticker': ticker,
                'results': [],
                'quant_success': 0,
                'quant_fail': 0,
                'qual_success': 0,
                'qual_fail': 0,
                'events_count': 0
            }

        async with semaphore:
            try:
                ticker_events = await metrics.select_events_for_valuation(
                    pool,
                    from_date=from_date,
                    to_date=to_date,
                    tickers=[ticker],
                    overwrite=overwrite,
                    metrics_list=metrics_list
                )
            except Exception as e:
                logger.error(f"[Batch {batch_number}] Phase 2 FAILED for ticker {ticker}: {e}")
                return {
                    'ticker': ticker,
                    'results': [],
                    'quant_success': 0,
                    'quant_fail': 0,
                    'qual_success': 0,
                    'qual_fail': 0,
                    'events_count': 0
                }

            if not ticker_events:
                logger.info(f"[Batch {batch_number}] No events for ticker {ticker}")
                completed_tickers += 1
                return {
                    'ticker': ticker,
                    'results': [],
                    'quant_success': 0,
                    'quant_fail': 0,
                    'qual_success': 0,
                    'qual_fail': 0,
                    'events_count': 0
                }

            result = await process_ticker_batch(
                pool, ticker, ticker_events, metrics_by_domain, overwrite,
                total_events_count, completed_events_count,
                metrics_list,
                global_peer_cache,
                ticker_to_peers
            )

            completed_tickers += 1
            result['events_count'] = len(ticker_events)
            return result

    logger.info(f"[Batch {batch_number}] Phase 4: Processing {total_tickers:,} tickers with concurrency={max_workers}")

    # Create and execute tasks
    tasks = [process_ticker_with_semaphore(ticker) for ticker in tickers]

    ticker_results = await asyncio.gather(*tasks, return_exceptions=True)

    # Aggregate results
    results = []
    quantitative_success = 0
    quantitative_fail = 0
    qualitative_success = 0
    qualitative_fail = 0
    events_count = 0
    tickers_with_events = 0

    summary_updates = []
    for ticker_result in ticker_results:
        if isinstance(ticker_result, Exception):
            logger.error(f"[Batch {batch_number}] Ticker batch failed: {ticker_result}")
            continue

        results.extend(ticker_result['results'])
        summary_updates.extend(ticker_result.get('updates', []))
        quantitative_success += ticker_result['quant_success']
        quantitative_fail += ticker_result['quant_fail']
        qualitative_success += ticker_result['qual_success']
        qualitative_fail += ticker_result['qual_fail']
        events_count += ticker_result.get('events_count', 0)
        if ticker_result.get('events_count', 0) > 0:
            tickers_with_events += 1

    calc_fail_tickers = set()
    qual_fail_tickers = set()
    summary_source = summary_updates if summary_updates else results
    for result in summary_source:
        if isinstance(result, dict):
            ticker = result.get('ticker')
            metric_status = result.get('metric_status', {})
            qual_warnings = result.get('qual_warnings')
            qual_status = result.get('qual_status')
        else:
            ticker = getattr(result, 'ticker', None)
            metric_status = getattr(result, 'metric_status', None) or {}
            qual_warnings = getattr(result, 'qual_warnings', None)
            qual_status = getattr(result, 'qual_status', None)

        if not ticker:
            continue
        if metric_status.get('priceQuantitative') is False:
            calc_fail_tickers.add(ticker)
        if qual_warnings or qual_status != 'success':
            qual_fail_tickers.add(ticker)

    batch_elapsed = time.time() - phase2_start
    logger.info(f"[Batch {batch_number}] Complete: {len(results):,} events, {tickers_with_events:,} tickers, {len(global_peer_cache):,} peers in {batch_elapsed:.1f}s")
    if calc_fail_tickers:
        logger.warning(f"[BATCH {batch_number} SUMMARY] [CALC FAIL] {', '.join(sorted(calc_fail_tickers))}")
    if qual_fail_tickers:
        logger.warning(f"[BATCH {batch_number} SUMMARY] [QUALITATIVE FAIL] {', '.join(sorted(qual_fail_tickers))}")

    return {
        'results': results,
        'events_count': events_count,
        'tickers_count': tickers_with_events,
        'unique_peer_count': len(global_peer_cache),
        'quantitative_success': quantitative_success,
        'quantitative_fail': quantitative_fail,
        'qualitative_success': qualitative_success,
        'qualitative_fail': qualitative_fail
    }


async def calculate_valuations(
    overwrite: bool = False,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    tickers: Optional[List[str]] = None,
    start_point: Optional[str] = None,
    cancel_event: Optional[asyncio.Event] = None,
    metrics_list: Optional[List[str]] = None,
    batch_size: Optional[int] = None,
    max_workers: int = 20,
    verbose: bool = False
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
        overwrite: If False, update only NULL values. If True, overwrite existing values.
                   When used with metrics_list: applies to specified metrics only.
                   When used without metrics_list: applies to all value_* JSONB fields.
        from_date: Optional start date for filtering events by event_date.
        to_date: Optional end date for filtering events by event_date.
        tickers: Optional list of ticker symbols to filter events. If None, processes all tickers.
        cancel_event: Optional asyncio.Event for cancellation.
        metrics_list: Optional list of metric IDs to recalculate (I-41). If specified, only these metrics are updated.
        batch_size: Optional batch size for processing tickers. If None, processes all tickers in one batch.
        max_workers: Maximum number of concurrent workers (1-100). Lower values reduce DB CPU load.
                     Default: 20. Recommended: 10-30 depending on DB capacity.
        verbose: Enable verbose logging. If True, outputs detailed per-event and per-ticker logs.
                 If False (default), outputs only summary logs for efficient problem identification.

    Returns:
        Dict with summary and per-event results

    Example:
        # Update only priceQuantitative metric for NULL values
        >>> await calculate_valuations(metrics_list=['priceQuantitative'], overwrite=False)

        # Recalculate PER and PBR for all events (overwrite existing values)
        >>> await calculate_valuations(metrics_list=['PER', 'PBR'], overwrite=True)
    """
    start_time = time.time()
    
    from .utils.logging_utils import create_log_context

    logger.info(
        "[backfillEventsTable] START - "
        f"overwrite={overwrite}, from={from_date}, to={to_date}, "
        f"tickers={tickers}, start_point={start_point}, batch={batch_size}"
    )

    pool = await db_pool.get_pool()

    # Phase 1: Load metric definitions
    try:
        metrics_by_domain = await metrics.select_metric_definitions(pool)
        logger.info(f"[Phase 1] Loaded {len(metrics_by_domain)} metric domains")
    except Exception as e:
        logger.error(f"[Phase 1] FAILED to load metrics: {e}")
        raise

    if not metrics_by_domain:
        logger.warning("[Phase 1] No metrics found in config_lv2_metric")

    # Phase 2: Build ticker list
    try:
        tickers_to_process = await metrics.select_unique_tickers_for_valuation(
            pool,
            from_date=from_date,
            to_date=to_date,
            tickers=tickers,
            start_point=start_point,
            overwrite=overwrite,
            metrics_list=metrics_list
        )
        logger.info(f"[Phase 2] Loaded {len(tickers_to_process):,} unique tickers for processing")
    except Exception as e:
        logger.error(f"[Phase 2] FAILED to load tickers: {e}")
        raise

    if not tickers_to_process:
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
        return {
            'summary': summary,
            'results': []
        }

    # Phase 3-4: Batch processing loop
    batch_number = 0
    all_results = []
    total_events_processed = 0
    total_tickers_processed = 0
    total_unique_peers = 0
    all_quantitative_success = 0
    all_quantitative_fail = 0
    all_qualitative_success = 0
    all_qualitative_fail = 0

    if batch_size:
        ticker_batches = [
            tickers_to_process[i:i + batch_size]
            for i in range(0, len(tickers_to_process), batch_size)
        ]
    else:
        ticker_batches = [tickers_to_process]

    for ticker_batch in ticker_batches:
        batch_number += 1

        tickers_preview = ", ".join(ticker_batch[:10])
        if len(ticker_batch) > 10:
            tickers_preview = f"{tickers_preview}, ..."
        logger.info(f"[Batch {batch_number}] Ticker batch: {len(ticker_batch)} tickers ({tickers_preview})")

        # Process one batch
        batch_result = await process_single_batch(
            pool=pool,
            batch_size=batch_size,
            from_date=from_date,
            to_date=to_date,
            tickers=ticker_batch,
            overwrite=overwrite,
            metrics_list=metrics_list,
            metrics_by_domain=metrics_by_domain,
            max_workers=max_workers,
            start_time=start_time,
            batch_number=batch_number,
            cancel_event=cancel_event
        )

        # Skip empty batch
        if batch_result is None:
            logger.info(f"[backfillEventsTable] Batch {batch_number} had no events to process")
            continue

        # Accumulate results
        all_results.extend(batch_result['results'])
        total_events_processed += batch_result['events_count']
        total_tickers_processed += batch_result['tickers_count']
        total_unique_peers = max(total_unique_peers, batch_result['unique_peer_count'])  # Track max peers used in any batch
        all_quantitative_success += batch_result['quantitative_success']
        all_quantitative_fail += batch_result['quantitative_fail']
        all_qualitative_success += batch_result['qualitative_success']
        all_qualitative_fail += batch_result['qualitative_fail']

    # Early return if no events processed
    if len(all_results) == 0:
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
        return {
            'summary': summary,
            'results': []
        }

    # Use aggregated results for final summary
    events = all_results  # For compatibility with Phase 5
    results = all_results
    quantitative_success = all_quantitative_success
    quantitative_fail = all_quantitative_fail
    qualitative_success = all_qualitative_success
    qualitative_fail = all_qualitative_fail

    # Log final batch summary
    total_elapsed = time.time() - start_time
    logger.info(
        f"\n{'='*90}\n"
        f"[BATCH PROCESSING COMPLETE] {batch_number} batches | "
        f"{len(results):,} events | "
        f"{total_tickers_processed:,} tickers | "
        f"{total_unique_peers:,} max peers\n"
        f"Time: {int(total_elapsed/60)}min {int(total_elapsed%60)}s | "
        f"Success: {quantitative_success:,}✓ / {quantitative_fail:,}✗\n"
        f"{'='*90}"
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

    total_elapsed_ms = int((time.time() - start_time) * 1000)

    # Build summary with comprehensive stats
    summary = {
        'totalBatches': batch_number,
        'totalEventsProcessed': len(results),
        'totalTickersProcessed': total_tickers_processed,
        'totalUniquePeersUsed': total_unique_peers,
        'batchSize': batch_size if batch_size else None,
        'quantitativeSuccess': quantitative_success,
        'quantitativeFail': quantitative_fail,
        'qualitativeSuccess': qualitative_success,
        'qualitativeFail': qualitative_fail,
        'totalDbUpdates': quantitative_success + qualitative_success,
        'elapsedMs': total_elapsed_ms,
        'averagePerEventMs': int(total_elapsed_ms / max(1, len(results))),
        'eventsPerSecond': int(len(results) / max(1, total_elapsed_ms / 1000))
    }

    logger.info(f"[backfillEventsTable] ✅ COMPLETE - Events: {len(results):,}, Tickers: {total_tickers_processed:,}, Peers: {total_unique_peers:,}, Success: {quantitative_success:,}✓/{quantitative_fail:,}✗")

    return {
        'summary': summary,
        'results': results
    }


async def calculate_quantitative_metrics_fast(
    ticker: str,
    event_date,
    api_cache: Dict[str, List[Dict[str, Any]]],
    engine: MetricCalculationEngine,
    target_domains: List[str],
    custom_values: Optional[Dict[str, Any]] = None,
    track_metrics: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    ULTRA-FAST quantitative metrics calculation.

    Uses pre-initialized engine and pre-fetched API cache.
    Only performs date filtering per event - NO DB queries, NO engine init!

    Performance: ~50x faster than calculate_quantitative_metrics_cached

    Args:
        ticker: Ticker symbol
        event_date: Event date
        api_cache: Cached API data
        engine: Pre-initialized MetricCalculationEngine
        target_domains: Domains to calculate
        custom_values: Pre-calculated custom metrics
        track_metrics: Optional list of metric names to track (for summary logging)

    Returns:
        Dict with status, value, message, and optionally metric_status
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
        # I-41: Pass custom_values for priceQuantitative metric
        # calculate_all now returns (quantitative, qualitative, metric_status) tuple
        value_quantitative, value_qualitative, metric_status = engine.calculate_all(
            api_data_filtered, target_domains, custom_values, track_metrics
        )

        result = {
            'status': 'success',
            'value': value_quantitative,  # Return only quantitative for this function
            'message': 'Quantitative metrics calculated (fast)'
        }

        # Add metric_status if tracking was requested
        if track_metrics:
            result['metric_status'] = metric_status

        return result

    except Exception as e:
        logger.error(f"[calculate_quantitative_metrics_fast] Failed for {ticker}: {e}")
        result = {
            'status': 'failed',
            'value': None,
            'message': str(e)
        }

        # Add empty metric_status if tracking was requested
        if track_metrics:
            result['metric_status'] = {m: False for m in track_metrics}

        return result


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
        # calculate_all now returns (quantitative, qualitative, metric_status) tuple
        value_quantitative, value_qualitative, _ = engine.calculate_all(api_data_filtered, target_domains)

        return {
            'status': 'success',
            'value': value_quantitative,  # Return only quantitative for this function
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
                    # I-25: fmp-historical-market-capitalization도 from/to 파라미터 필요
                    if 'historical-price' in api_id or 'eod' in api_id or 'historical-market-cap' in api_id:
                        # Historical price/market-cap APIs need date range
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

        # calculate_all now returns (quantitative, qualitative, metric_status) tuple
        value_quantitative, value_qualitative, _ = engine.calculate_all(api_data, target_domains)

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
    engine: MetricCalculationEngine,
    suppress_logs: bool = False
) -> Dict[str, Any]:
    """
    ULTRA-FAST qualitative metrics calculation (DB-driven).

    Hybrid approach:
    1. Fetch priceTarget data from evt_consensus (async DB query in Python)
    2. Pass to MetricCalculationEngine for calculation (dynamic calculation from DB)

    This combines:
    - DB data source (evt_consensus) - no duplication in txn_quantitatives
    - DB calculation logic (config_lv2_metric.calculation) - no hardcoded business logic

    Args:
        pool: Database connection pool
        ticker: Ticker symbol
        event_date: Event date
        source: Source table name (e.g., 'consensus')
        source_id: evt_consensus.id (UUID string)
        engine: Pre-initialized MetricCalculationEngine

    Returns:
        Dict with status, value (qualitative metrics), currentPrice, message
    """
    qual_warnings = []
    try:
        # Convert event_date to date object
        if isinstance(event_date, str):
            event_date_obj = datetime.fromisoformat(event_date.replace('Z', '+00:00')).date()
        elif hasattr(event_date, 'date'):
            event_date_obj = event_date.date()
        else:
            event_date_obj = event_date

        # Fetch ALL priceTarget data for this ticker from evt_consensus
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT
                    price_target as "priceTarget",
                    price_when_posted as "priceWhenPosted",
                    event_date as "publishedDate",
                    analyst_company as "analystCompany"
                FROM evt_consensus
                WHERE ticker = $1
                ORDER BY event_date DESC
            """, ticker)

        # Convert to list of dicts (mimics fmp-price-target API format)
        price_target_data = [dict(row) for row in rows]

        # Only log if NO data found (error case)
        if len(price_target_data) == 0:
            if suppress_logs:
                qual_warnings.append('no_consensus_data')
            else:
                logger.warning(f"[QUALITATIVE FAIL] {ticker}: No consensus data. Run GET /sourceData?mode=consensus")

        # Pass priceTarget data and event_date to calculation code
        custom_values = {
            'priceTarget': price_target_data,  # Raw data for consensus calculation
            'event_date': event_date_obj,  # Used by consensus calculation to filter
            '_suppress_calc_fail_logs': True
        }

        # Calculate metrics using PRE-INITIALIZED engine (DB-driven)
        _, value_qualitative, _ = engine.calculate_all(
            {},  # No API data needed
            target_domains=['valuation'],
            custom_values=custom_values
        )

        # Extract consensus data (flatten structure to match original format)
        consensus_data = {}
        current_price = None

        if value_qualitative and 'valuation' in value_qualitative:
            consensus = value_qualitative['valuation'].get('consensus')

            if consensus and isinstance(consensus, dict):
                consensus_data = consensus

                # Extract currentPrice from consensusSignal
                consensus_signal = consensus.get('consensusSignal')
                if consensus_signal and isinstance(consensus_signal, dict):
                    last_data = consensus_signal.get('last', {})
                    current_price = last_data.get('price_when_posted')
            else:
                if suppress_logs:
                    qual_warnings.append('invalid_consensus_data')
                else:
                    logger.warning(f"[QUALITATIVE FAIL] event_id={source_id}: consensus calculation returned invalid data")
        else:
            if suppress_logs:
                qual_warnings.append('missing_valuation_domain')
            else:
                logger.warning(f"[QUALITATIVE FAIL] event_id={source_id}: valuation domain missing in engine result")

        return {
            'status': 'success',
            'value': consensus_data,  # Flat structure matching original format
            'currentPrice': current_price,
            'warnings': qual_warnings,
            'message': 'Qualitative metrics calculated (DB-driven from evt_consensus)'
        }

    except Exception as e:
        logger.error(f"[calculate_qualitative_metrics_fast] Failed for {ticker}: {e}", exc_info=True)
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
    tickers: Optional[List[str]] = None,
    tables: Optional[List[str]] = None,
    start_point: Optional[str] = None,
    batch_size: Optional[int] = None,
    max_workers: int = 20
) -> Dict[str, Any]:
    """
    Generate price_trend arrays for events in txn_events and trades in txn_trades.

    Fetches policy configuration, generates dayOffset scaffolds,
    fetches OHLC data from FMP, and populates txn_price_trend table for:
    1. All events from txn_events (existing behavior)
    2. Trades from txn_trades that don't exist in txn_events (new behavior)

    Args:
        from_date: Optional start date for filtering by event_date/trade_date
        to_date: Optional end date for filtering by event_date/trade_date
        tickers: Optional list of ticker symbols to filter. If None, processes all tickers.
        tables: Optional list of source tables to process ("txn_events", "txn_trades").
        start_point: Optional start ticker (alphabetical) to resume processing from this point.
        batch_size: Optional batch size for processing tickers. If None, processes all tickers in one batch.
        max_workers: Maximum number of concurrent workers (1-100). Lower values reduce DB CPU load.
                     Default: 20. Recommended: 10-30 depending on DB capacity.

    Returns:
        Dict with summary and statistics including events and trades counts
    """
    start_time = time.time()

    pool = await db_pool.get_pool()

    # Load policy configurations
    logger.info(
        "Loading price trend policies",
        extra={
            'endpoint': 'POST /generatePriceTrends',
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

    tables_set = {"txn_events", "txn_trades"}
    if tables:
        tables_set = {table.lower() for table in tables}

    # Load events to process
    events = []
    if "txn_events" in tables_set:
        events = await metrics.select_events_for_price_trends(
            pool,
            from_date=from_date,
            to_date=to_date,
            tickers=tickers
        )
        for event in events:
            event['record_type'] = 'event'

    # Load trades from txn_trades that are NOT in txn_events
    trades = []
    if "txn_trades" in tables_set:
        trades = await metrics.select_trades_for_price_trends(
            pool,
            from_date=from_date,
            to_date=to_date,
            tickers=tickers
        )
        for trade in trades:
            trade['record_type'] = 'trade'

    # Merge events and trades for processing
    all_records = events + trades

    logger.info(
        f"Processing price trends for {len(events)} events and {len(trades)} trades (total: {len(all_records)})",
        extra={
            'endpoint': 'POST /generatePriceTrends',
            'phase': 'process_price_trends',
            'elapsed_ms': int((time.time() - start_time) * 1000),
            'counters': {'events': len(events), 'trades': len(trades), 'total': len(all_records)},
            'progress': {},
            'rate': {},
            'batch': {},
            'warn': []
        }
    )

    # Group all records (events + trades) by ticker for efficient OHLC fetching
    events_by_ticker = {}
    for record in all_records:
        ticker = record['ticker']
        if ticker not in events_by_ticker:
            events_by_ticker[ticker] = []
        events_by_ticker[ticker].append(record)

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
    # I-43: Group events by (ticker, event_date) for txn_price_trend
    # ========================================
    # Deduplicate events by (ticker, event_date) since txn_price_trend is indexed by this combination
    unique_ticker_dates = {}
    for record in all_records:
        ticker = record['ticker']
        event_date = record['event_date'].date() if hasattr(record['event_date'], 'date') else record['event_date']
        if ticker not in unique_ticker_dates:
            unique_ticker_dates[ticker] = {}
        if event_date not in unique_ticker_dates[ticker]:
            unique_ticker_dates[ticker][event_date] = record

    logger.info(
        f"Deduplicated {len(all_records)} records into {sum(len(dates) for dates in unique_ticker_dates.values())} unique (ticker, event_date) pairs",
        extra={
            'endpoint': 'POST /generatePriceTrends',
            'phase': 'deduplicate_events',
            'elapsed_ms': int((time.time() - start_time) * 1000),
            'counters': {
                'records': len(all_records),
                'events': len(events),
                'trades': len(trades),
                'unique_pairs': sum(len(dates) for dates in unique_ticker_dates.values())
            },
            'progress': {},
            'rate': {},
            'batch': {},
            'warn': []
        }
    )

    tickers_to_process = sorted(unique_ticker_dates.keys())
    if start_point:
        tickers_to_process = [ticker for ticker in tickers_to_process if ticker >= start_point]

    if not tickers_to_process:
        logger.info(
            "No tickers to process after applying startPoint",
            extra={
                'endpoint': 'POST /generatePriceTrends',
                'phase': 'no_tickers',
                'elapsed_ms': int((time.time() - start_time) * 1000),
                'counters': {},
                'progress': {},
                'rate': {},
                'batch': {},
                'warn': []
            }
        )
        return {
            'success': 0,
            'fail': 0
        }

    # ========================================
    # Helper function for individual price trend upserts
    # ========================================
    async def _upsert_single_price_trend(
        ticker: str,
        event_date: date,
        record_type: str,
        jsonb_columns: dict,
        wts_long: int,
        wts_short: int
    ):
        """
        Upsert a single price trend record to txn_price_trend table.

        Args:
            ticker: Stock ticker symbol
            event_date: Event date
            record_type: Source record type ("event" or "trade")
            jsonb_columns: Dict with d_neg14 through d_pos14 JSONB data
            wts_long: Long position winning time shift
            wts_short: Short position winning time shift
        """
        import json

        # Helper to convert dict to JSON string for JSONB columns
        def jsonb_or_null(val):
            if val is None:
                return None
            if isinstance(val, dict):
                return json.dumps(val)
            return val

        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO txn_price_trend (
                    ticker, event_date, type,
                    d_neg14, d_neg13, d_neg12, d_neg11, d_neg10,
                    d_neg9, d_neg8, d_neg7, d_neg6, d_neg5,
                    d_neg4, d_neg3, d_neg2, d_neg1,
                    d_0,
                    d_pos1, d_pos2, d_pos3, d_pos4, d_pos5,
                    d_pos6, d_pos7, d_pos8, d_pos9, d_pos10,
                    d_pos11, d_pos12, d_pos13, d_pos14,
                    wts_long, wts_short
                ) VALUES (
                    $1, $2, $3,
                    $4::jsonb, $5::jsonb, $6::jsonb, $7::jsonb, $8::jsonb,
                    $9::jsonb, $10::jsonb, $11::jsonb, $12::jsonb, $13::jsonb,
                    $14::jsonb, $15::jsonb, $16::jsonb, $17::jsonb,
                    $18::jsonb,
                    $19::jsonb, $20::jsonb, $21::jsonb, $22::jsonb, $23::jsonb,
                    $24::jsonb, $25::jsonb, $26::jsonb, $27::jsonb, $28::jsonb,
                    $29::jsonb, $30::jsonb, $31::jsonb, $32::jsonb,
                    $33, $34
                )
                ON CONFLICT (ticker, event_date) DO UPDATE
                SET
                    type = EXCLUDED.type,
                    d_neg14 = EXCLUDED.d_neg14,
                    d_neg13 = EXCLUDED.d_neg13,
                    d_neg12 = EXCLUDED.d_neg12,
                    d_neg11 = EXCLUDED.d_neg11,
                    d_neg10 = EXCLUDED.d_neg10,
                    d_neg9 = EXCLUDED.d_neg9,
                    d_neg8 = EXCLUDED.d_neg8,
                    d_neg7 = EXCLUDED.d_neg7,
                    d_neg6 = EXCLUDED.d_neg6,
                    d_neg5 = EXCLUDED.d_neg5,
                    d_neg4 = EXCLUDED.d_neg4,
                    d_neg3 = EXCLUDED.d_neg3,
                    d_neg2 = EXCLUDED.d_neg2,
                    d_neg1 = EXCLUDED.d_neg1,
                    d_0 = EXCLUDED.d_0,
                    d_pos1 = EXCLUDED.d_pos1,
                    d_pos2 = EXCLUDED.d_pos2,
                    d_pos3 = EXCLUDED.d_pos3,
                    d_pos4 = EXCLUDED.d_pos4,
                    d_pos5 = EXCLUDED.d_pos5,
                    d_pos6 = EXCLUDED.d_pos6,
                    d_pos7 = EXCLUDED.d_pos7,
                    d_pos8 = EXCLUDED.d_pos8,
                    d_pos9 = EXCLUDED.d_pos9,
                    d_pos10 = EXCLUDED.d_pos10,
                    d_pos11 = EXCLUDED.d_pos11,
                    d_pos12 = EXCLUDED.d_pos12,
                    d_pos13 = EXCLUDED.d_pos13,
                    d_pos14 = EXCLUDED.d_pos14,
                    wts_long = EXCLUDED.wts_long,
                    wts_short = EXCLUDED.wts_short,
                    updated_at = CURRENT_TIMESTAMP
                """,
                ticker,
                event_date,
                record_type,
                # 29 day offset JSONB columns
                jsonb_or_null(jsonb_columns.get('d_neg14')),
                jsonb_or_null(jsonb_columns.get('d_neg13')),
                jsonb_or_null(jsonb_columns.get('d_neg12')),
                jsonb_or_null(jsonb_columns.get('d_neg11')),
                jsonb_or_null(jsonb_columns.get('d_neg10')),
                jsonb_or_null(jsonb_columns.get('d_neg9')),
                jsonb_or_null(jsonb_columns.get('d_neg8')),
                jsonb_or_null(jsonb_columns.get('d_neg7')),
                jsonb_or_null(jsonb_columns.get('d_neg6')),
                jsonb_or_null(jsonb_columns.get('d_neg5')),
                jsonb_or_null(jsonb_columns.get('d_neg4')),
                jsonb_or_null(jsonb_columns.get('d_neg3')),
                jsonb_or_null(jsonb_columns.get('d_neg2')),
                jsonb_or_null(jsonb_columns.get('d_neg1')),
                jsonb_or_null(jsonb_columns.get('d_0')),
                jsonb_or_null(jsonb_columns.get('d_pos1')),
                jsonb_or_null(jsonb_columns.get('d_pos2')),
                jsonb_or_null(jsonb_columns.get('d_pos3')),
                jsonb_or_null(jsonb_columns.get('d_pos4')),
                jsonb_or_null(jsonb_columns.get('d_pos5')),
                jsonb_or_null(jsonb_columns.get('d_pos6')),
                jsonb_or_null(jsonb_columns.get('d_pos7')),
                jsonb_or_null(jsonb_columns.get('d_pos8')),
                jsonb_or_null(jsonb_columns.get('d_pos9')),
                jsonb_or_null(jsonb_columns.get('d_pos10')),
                jsonb_or_null(jsonb_columns.get('d_pos11')),
                jsonb_or_null(jsonb_columns.get('d_pos12')),
                jsonb_or_null(jsonb_columns.get('d_pos13')),
                jsonb_or_null(jsonb_columns.get('d_pos14')),
                # wts_long and wts_short (integers)
                wts_long,
                wts_short
            )

    # ========================================
    # I-43: Process unique pairs and save incrementally
    # ========================================
    success_count = 0
    fail_count = 0
    processed_pairs = 0
    progress_lock = asyncio.Lock()

    total_unique_pairs = sum(len(dates) for dates in unique_ticker_dates.values() if dates)
    if total_unique_pairs == 0:
        logger.info(
            "No unique (ticker, event_date) pairs to process",
            extra={
                'endpoint': 'POST /generatePriceTrends',
                'phase': 'no_pairs',
                'elapsed_ms': int((time.time() - start_time) * 1000),
                'counters': {},
                'progress': {},
                'rate': {},
                'batch': {},
                'warn': []
            }
        )
        return {
            'success': 0,
            'fail': 0
        }

    def _normalize_historical_prices(raw_prices: Any) -> List[Dict[str, Any]]:
        if raw_prices is None:
            return []
        if isinstance(raw_prices, list):
            return raw_prices
        if isinstance(raw_prices, dict):
            historical = raw_prices.get('historical')
            if isinstance(historical, list):
                return historical
        return []

    def _build_ohlc_cache_for_ticker(
        historical_prices: List[Dict[str, Any]],
        fetch_start: date,
        fetch_end: date
    ) -> Dict[str, Dict[str, Any]]:
        ohlc_by_date = {}
        for record in historical_prices:
            record_date = record.get('date')
            if not record_date:
                continue
            try:
                record_date_obj = datetime.fromisoformat(record_date.replace('Z', '+00:00')).date()
            except ValueError:
                continue
            if fetch_start <= record_date_obj <= fetch_end:
                ohlc_by_date[record_date_obj.isoformat()] = record
        return ohlc_by_date

    async def _process_ticker(ticker: str, ohlc_by_date: Dict[str, Dict[str, Any]]):
        nonlocal success_count, fail_count, processed_pairs

        ticker_dates = unique_ticker_dates.get(ticker, {})
        for event_date, record in ticker_dates.items():
            record_type = record.get('record_type', 'event')
            try:
                # OPTIMIZED: Use cached trading days (NO DB CALL per event!)
                dayoffset_dates = calculate_dayOffset_dates_cached(
                    event_date,
                    count_start,
                    count_end,
                    trading_days_set
                )

                # Build dayOffset OHLC map with target_date
                dayoffset_ohlc = {}
                dayoffset_target_dates = {}

                for dayoffset, target_date in dayoffset_dates:
                    date_str = target_date.isoformat()
                    dayoffset_target_dates[dayoffset] = date_str
                    ohlc = ohlc_by_date.get(date_str)

                    if ohlc:
                        dayoffset_ohlc[dayoffset] = {
                            'open': float(ohlc.get('open')) if ohlc.get('open') else None,
                            'high': float(ohlc.get('high')) if ohlc.get('high') else None,
                            'low': float(ohlc.get('low')) if ohlc.get('low') else None,
                            'close': float(ohlc.get('close')) if ohlc.get('close') else None
                        }
                    else:
                        dayoffset_ohlc[dayoffset] = None

                # Fill missing data with forward/backward fill
                for offset in range(-14, 15):
                    if dayoffset_ohlc.get(offset) is None:
                        if offset < 0:
                            for prev_offset in range(offset - 1, -15, -1):
                                if dayoffset_ohlc.get(prev_offset) is not None:
                                    dayoffset_ohlc[offset] = dayoffset_ohlc[prev_offset].copy()
                                    break
                        else:
                            for next_offset in range(offset + 1, 15):
                                if dayoffset_ohlc.get(next_offset) is not None:
                                    dayoffset_ohlc[offset] = dayoffset_ohlc[next_offset].copy()
                                    break

                d0_data = dayoffset_ohlc.get(0)
                base_close = d0_data['close'] if d0_data and d0_data.get('close') is not None else None

                if base_close is None:
                    logger.warning(f"No D0 close for {ticker} on {event_date}, recording with null values")

                jsonb_columns = {}
                day_performances = {}

                for offset in range(-14, 15):
                    ohlc = dayoffset_ohlc.get(offset)
                    target_date = dayoffset_target_dates.get(offset)

                    if ohlc and ohlc.get('close') is not None and base_close is not None:
                        close_price = ohlc['close']
                        performance = (close_price - base_close) / base_close if base_close != 0 else 0
                        day_performances[offset] = performance

                        jsonb_data = {
                            'targetDate': target_date,
                            'price_trend': {
                                'low': ohlc['low'],
                                'high': ohlc['high'],
                                'open': ohlc['open'],
                                'close': ohlc['close']
                            },
                            'dayOffset0': {
                                'close': base_close
                            },
                            'performance': {
                                'close': performance
                            }
                        }
                    elif ohlc and ohlc.get('close') is not None and base_close is None:
                        day_performances[offset] = None
                        jsonb_data = {
                            'targetDate': target_date,
                            'price_trend': {
                                'low': ohlc['low'],
                                'high': ohlc['high'],
                                'open': ohlc['open'],
                                'close': ohlc['close']
                            },
                            'dayOffset0': {
                                'close': None
                            },
                            'performance': {
                                'close': None
                            }
                        }
                    else:
                        jsonb_data = {
                            'targetDate': target_date,
                            'price_trend': None,
                            'dayOffset0': {
                                'close': base_close
                            },
                            'performance': {
                                'close': None
                            }
                        } if target_date else None
                        day_performances[offset] = None

                    if offset < 0:
                        col_name = f'd_neg{abs(offset)}'
                    elif offset == 0:
                        col_name = 'd_0'
                    else:
                        col_name = f'd_pos{offset}'

                    jsonb_columns[col_name] = json.dumps(jsonb_data) if jsonb_data else None

                wts_long = None
                wts_short = None
                max_performance = None
                min_performance = None

                for offset, perf in day_performances.items():
                    if perf is not None:
                        if max_performance is None or perf > max_performance:
                            max_performance = perf
                            wts_long = offset
                        if min_performance is None or perf < min_performance:
                            min_performance = perf
                            wts_short = offset

                await _upsert_single_price_trend(
                    ticker,
                    event_date,
                    record_type,
                    jsonb_columns,
                    wts_long,
                    wts_short
                )
                ticker_success = True
            except Exception as e:
                ticker_success = False
                logger.error(f"Failed to generate price trend for {ticker} {event_date}: {e}", exc_info=True)

            async with progress_lock:
                processed_pairs += 1
                if ticker_success:
                    success_count += 1
                else:
                    fail_count += 1

                if processed_pairs % 50 == 0 or processed_pairs == total_unique_pairs:
                    elapsed_ms = int((time.time() - start_time) * 1000)
                    eta_ms = calculate_eta(total_unique_pairs, processed_pairs, elapsed_ms)
                    eta = format_eta_ms(eta_ms)

                    logger.info(
                        f"Processed {processed_pairs}/{total_unique_pairs} unique pairs",
                        extra={
                            'endpoint': 'POST /generatePriceTrends',
                            'phase': 'process_price_trends',
                            'elapsed_ms': elapsed_ms,
                            'counters': {
                                'processed': processed_pairs,
                                'total': total_unique_pairs,
                                'success': success_count,
                                'fail': fail_count
                            },
                            'progress': {
                                'done': processed_pairs,
                                'total': total_unique_pairs,
                                'pct': round((processed_pairs / total_unique_pairs) * 100, 1)
                            },
                            'eta': eta,
                            'rate': {},
                            'batch': {},
                            'warn': []
                        }
                    )

    if batch_size:
        ticker_batches = [
            tickers_to_process[i:i + batch_size]
            for i in range(0, len(tickers_to_process), batch_size)
        ]
    else:
        ticker_batches = [tickers_to_process]

    batch_number = 0
    for ticker_batch in ticker_batches:
        batch_number += 1
        tickers_preview = ", ".join(ticker_batch[:10])
        if len(ticker_batch) > 10:
            tickers_preview = f"{tickers_preview}, ..."

        logger.info(
            f"[Batch {batch_number}] Ticker batch: {len(ticker_batch)} tickers ({tickers_preview})",
            extra={
                'endpoint': 'POST /generatePriceTrends',
                'phase': 'batch_start',
                'elapsed_ms': int((time.time() - start_time) * 1000),
                'counters': {},
                'progress': {},
                'rate': {},
                'batch': {'size': len(ticker_batch), 'mode': 'ticker'},
                'warn': []
            }
        )

        batch_cache = await get_batch_quantitative_data_from_db(
            pool,
            ticker_batch,
            ['fmp-historical-price-eod-full']
        )

        ticker_ohlc_cache = {}
        for ticker in ticker_batch:
            ticker_events = unique_ticker_dates.get(ticker, {})
            event_dates = list(ticker_events.keys())
            if not event_dates:
                ticker_ohlc_cache[ticker] = {}
                continue

            min_date = min(event_dates)
            max_date = max(event_dates)

            extra_buffer_days = 15
            fetch_start = min_date + timedelta(days=ohlc_count_start - extra_buffer_days)
            fetch_end = max_date + timedelta(days=ohlc_count_end + extra_buffer_days)

            raw_prices = batch_cache.get(ticker, {}).get('fmp-historical-price-eod-full')
            historical_prices = _normalize_historical_prices(raw_prices)

            if not historical_prices:
                logger.warning(f"[DB-Cache] Missing historical_price for {ticker} in config_lv3_quantitatives")
                ticker_ohlc_cache[ticker] = {}
                continue

            ticker_ohlc_cache[ticker] = _build_ohlc_cache_for_ticker(
                historical_prices,
                fetch_start,
                fetch_end
            )

        semaphore = asyncio.Semaphore(max_workers)

        async def _semaphore_wrapper(ticker: str):
            async with semaphore:
                await _process_ticker(ticker, ticker_ohlc_cache.get(ticker, {}))

        tasks = [_semaphore_wrapper(ticker) for ticker in ticker_batch]
        await asyncio.gather(*tasks)

    # All records saved incrementally - no batch operation needed
    total_elapsed_ms = int((time.time() - start_time) * 1000)

    logger.info(
        f"Price trend generation completed",
        extra={
            'endpoint': 'POST /generatePriceTrends',
            'phase': 'complete_price_trends',
            'elapsed_ms': total_elapsed_ms,
            'counters': {'success': success_count, 'fail': fail_count, 'events': len(events), 'trades': len(trades)},
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


# =============================================================================
# I-36: 업종 평균 기반 적정가(Fair Value) 계산 함수들
# =============================================================================

async def get_peer_tickers(ticker: str, event_id: Optional[str] = None) -> List[str]:
    """
    fmp-stock-peers API를 사용하여 동종 업종 티커 목록을 조회합니다.

    주의: fmp-stock-peers API는 현재 날짜 기준 데이터만 반환하므로,
    symbol(ticker) 값만 사용하고 다른 값(price, mktCap 등)은 사용하지 않습니다. (I-36)

    Args:
        ticker: 기준 티커
        event_id: Optional event context for API call logging

    Returns:
        동종 업종 티커 목록 (기준 티커 제외)
    """
    try:
        async with FMPAPIClient() as fmp_client:
            response = await fmp_client.call_api('fmp-stock-peers', {'ticker': ticker}, event_id=event_id)

            if not response or len(response) == 0:
                logger.warning(f"[I-36] No peer tickers found for {ticker}")
                return []

            # I-36: FMP API returns flat list of peer ticker objects
            # After schema mapping: 'symbol' -> 'ticker'
            peer_tickers = []
            for item in response:
                if isinstance(item, dict):
                    # Get ticker from mapped field name
                    peer_ticker = item.get('ticker') or item.get('symbol')
                    if peer_ticker and peer_ticker != ticker:  # Exclude base ticker
                        peer_tickers.append(peer_ticker)

            logger.info(f"[I-36] Found {len(peer_tickers)} peer tickers for {ticker}: {peer_tickers[:5]}...")
            return peer_tickers

    except Exception as e:
        logger.error(f"[I-36] Failed to get peer tickers for {ticker}: {e}", exc_info=True)
        return []


async def collect_all_peer_tickers(
    ticker_groups: Dict[str, List[Dict[str, Any]]]
) -> Dict[str, List[str]]:
    """
    모든 ticker의 peer를 병렬로 수집하고, unique peer set을 반환합니다. (OPTIMIZED)

    Args:
        ticker_groups: {ticker: [event1, event2, ...]} 형태의 딕셔너리

    Returns:
        {ticker: [peer1, peer2, ...]} 형태의 딕셔너리 (각 ticker의 peer 목록)
    """
    tickers = list(ticker_groups.keys())
    total_count = len(tickers)

    logger.info("=" * 80)
    logger.info(f"[PERF-OPT] PARALLEL peer collection starting for {total_count} tickers")
    logger.info("=" * 80)

    ticker_to_peers = {}

    # OPTIMIZATION: Parallel fetching with semaphore for rate limiting
    # Set to high value (700 = usagePerMin), RateLimiter will dynamically control actual rate
    MAX_CONCURRENT_PEER_REQUESTS = 700  # Increased from 20, RateLimiter controls actual rate
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_PEER_REQUESTS)

    async def fetch_ticker_peers_with_semaphore(ticker: str, idx: int):
        """Fetch peers for a single ticker with rate limiting."""
        async with semaphore:
            # Log progress every 50 tickers
            if idx == 0 or (idx + 1) % 50 == 0 or idx == total_count - 1:
                logger.info(f"[PERF-OPT] Progress: {idx + 1}/{total_count} tickers ({(idx + 1)/total_count*100:.1f}%)")

            try:
                peer_tickers = await get_peer_tickers(ticker)
                if peer_tickers:
                    return ticker, peer_tickers[:10]  # Limit to 10 peers per ticker
                return ticker, []
            except Exception as e:
                logger.warning(f"[PERF-OPT] Failed to get peers for {ticker}: {e}")
                return ticker, []

    # Create all tasks for parallel execution
    tasks = [fetch_ticker_peers_with_semaphore(ticker, idx) for idx, ticker in enumerate(tickers)]

    # Execute all tasks in parallel
    start_time = time.time()
    logger.info(f"[PERF-OPT] Starting parallel execution with max_concurrent={MAX_CONCURRENT_PEER_REQUESTS}")

    results = await asyncio.gather(*tasks, return_exceptions=True)

    parallel_elapsed = time.time() - start_time

    # Process results
    for result in results:
        if isinstance(result, Exception):
            logger.error(f"[PERF-OPT] Task failed with exception: {result}")
            continue
        ticker, peers = result
        ticker_to_peers[ticker] = peers

    # Get unique peer set for parallel fetching
    all_peers = set()
    for peers in ticker_to_peers.values():
        all_peers.update(peers)

    logger.info("=" * 80)
    logger.info(f"[PERF-OPT] ✓ PARALLEL peer collection COMPLETE in {parallel_elapsed:.2f}s")
    logger.info(f"[PERF-OPT] Total tickers processed: {len(ticker_to_peers)}/{total_count}")
    logger.info(f"[PERF-OPT] Total unique peers: {len(all_peers)}")
    logger.info(f"[PERF-OPT] Average time per ticker: {parallel_elapsed/total_count:.3f}s")
    logger.info(f"[PERF-OPT] Performance gain: ~{total_count * 0.5:.1f}s (sequential) → {parallel_elapsed:.1f}s (parallel) = {(1 - parallel_elapsed/(total_count * 0.5))*100:.0f}% faster")
    logger.info("=" * 80)

    return ticker_to_peers, list(all_peers)


async def fetch_single_peer_financials(
    peer_ticker: str,
    pool,
    metrics_by_domain: Dict[str, List[Dict[str, Any]]],
    reference_date
) -> Dict[str, Any]:
    """
    단일 peer의 financial data를 fetch합니다.

    Args:
        peer_ticker: Peer ticker symbol
        pool: Database pool
        metrics_by_domain: Metric definitions
        reference_date: Reference date for filtering

    Returns:
        {peer_ticker: {api_data, calculated_metrics}} 또는 None
    """
    try:
        # Transform 정의 로드
        transforms = await metrics.select_metric_transforms(pool)

        # 메트릭 계산 엔진 초기화
        engine = MetricCalculationEngine(metrics_by_domain, transforms)
        engine.build_dependency_graph()
        engine.topological_sort()

        # 필요한 API 목록
        required_apis = engine.get_required_apis()

        # API 데이터 조회
        peer_api_cache = {}
        async with FMPAPIClient() as fmp_client:
            for api_id in required_apis:
                params = {'ticker': peer_ticker}

                # API별 파라미터 설정
                if 'income-statement' in api_id or 'balance-sheet' in api_id or 'cash-flow' in api_id:
                    params['period'] = 'quarter'
                    params['limit'] = 20
                elif 'historical-market-cap' in api_id:
                    params['fromDate'] = '2000-01-01'
                    if isinstance(reference_date, str):
                        params['toDate'] = reference_date[:10]
                    elif hasattr(reference_date, 'strftime'):
                        params['toDate'] = reference_date.strftime('%Y-%m-%d')
                    else:
                        params['toDate'] = str(reference_date)

                api_response = await fmp_client.call_api(api_id, params, event_id=f"peer-cache-{peer_ticker}")
                if api_response:
                    peer_api_cache[api_id] = api_response

        if not peer_api_cache:
            logger.debug(f"[PERF-OPT] No API data for peer {peer_ticker}")
            return None

        # event_date 기준 필터링
        if isinstance(reference_date, str):
            event_date_obj = datetime.fromisoformat(reference_date.replace('Z', '+00:00')).date()
        elif hasattr(reference_date, 'date'):
            event_date_obj = reference_date.date()
        else:
            event_date_obj = reference_date

        # 날짜 필터링
        filtered_cache = {}
        for api_id, records in peer_api_cache.items():
            if isinstance(records, list):
                filtered_cache[api_id] = [
                    r for r in records
                    if _get_record_date(r) is None or _get_record_date(r) <= event_date_obj
                ]
            else:
                filtered_cache[api_id] = records

        # 메트릭 계산
        # calculate_all now returns (quantitative, qualitative, metric_status) tuple
        value_quantitative, value_qualitative, _ = engine.calculate_all(filtered_cache, ['valuation'])

        logger.debug(f"[PERF-OPT] Successfully fetched and calculated metrics for peer {peer_ticker}")

        return {
            'ticker': peer_ticker,
            'api_cache': peer_api_cache,
            'filtered_cache': filtered_cache,
            'calculated_metrics': value_quantitative  # Use quantitative metrics only
        }

    except Exception as e:
        logger.debug(f"[PERF-OPT] Failed to fetch financials for peer {peer_ticker}: {e}")
        return None


async def fetch_peer_financials_parallel(
    unique_peers: List[str],
    pool,
    metrics_by_domain: Dict[str, List[Dict[str, Any]]],
    reference_date,
    max_concurrent: int = 20
) -> Dict[str, Dict[str, Any]]:
    """
    여러 peer의 financial data를 병렬로 fetch합니다.

    Args:
        unique_peers: Unique peer ticker list
        pool: Database pool
        metrics_by_domain: Metric definitions
        reference_date: Reference date for filtering
        max_concurrent: Maximum concurrent API calls

    Returns:
        {peer_ticker: {api_cache, calculated_metrics}} 형태의 global cache
    """
    logger.info(f"[PERF-OPT] Fetching financial data for {len(unique_peers)} peers in parallel (max_concurrent={max_concurrent})...")

    # Use semaphore to limit concurrency
    semaphore = asyncio.Semaphore(max_concurrent)

    async def fetch_with_semaphore(peer_ticker):
        async with semaphore:
            return await fetch_single_peer_financials(peer_ticker, pool, metrics_by_domain, reference_date)

    # Fetch all peers in parallel
    start_time = time.time()
    results = await asyncio.gather(*[fetch_with_semaphore(peer) for peer in unique_peers], return_exceptions=True)
    elapsed = time.time() - start_time

    # Build global cache
    global_peer_cache = {}
    success_count = 0
    for result in results:
        if result and isinstance(result, dict) and 'ticker' in result:
            global_peer_cache[result['ticker']] = result
            success_count += 1
        elif isinstance(result, Exception):
            logger.debug(f"[PERF-OPT] Peer fetch exception: {result}")

    logger.info(f"[PERF-OPT] Parallel fetching completed: {success_count}/{len(unique_peers)} peers fetched successfully in {elapsed:.2f}s")
    logger.info(f"[PERF-OPT] Average time per peer: {elapsed/len(unique_peers):.2f}s (with parallelization)")

    return global_peer_cache


async def calculate_sector_average_from_cache_api(
    peer_tickers: List[str],
    global_peer_cache: Dict[str, Dict[str, Any]],
    target_metrics: List[str] = ['PER', 'PBR']
) -> Dict[str, float]:
    """
    캐시된 peer data로 sector average를 계산합니다 (API 모드용 - calculated_metrics 구조).

    이 함수는 API에서 fetch한 peer data (calculated_metrics 포함) 구조를 처리합니다.
    DB 모드에서는 quantitative_cache.calculate_sector_average_from_cache를 사용하세요.

    Args:
        peer_tickers: Peer ticker list for this ticker
        global_peer_cache: Global peer financial data cache (with calculated_metrics)
        target_metrics: Metrics to calculate average for

    Returns:
        {'PER': 25.5, 'PBR': 3.2, ...} 형태의 업종 평균
    """
    if not peer_tickers or not global_peer_cache:
        return {}

    # Collect metrics from cached peer data
    peer_metrics = {metric: [] for metric in target_metrics}

    for peer_ticker in peer_tickers[:10]:  # Limit to 10 peers
        peer_data = global_peer_cache.get(peer_ticker)
        if not peer_data:
            continue

        result = peer_data.get('calculated_metrics', {})
        if 'valuation' in result:
            valuation = result['valuation']
            for metric in target_metrics:
                value = valuation.get(metric)
                if value is not None and isinstance(value, (int, float)) and value > 0:
                    peer_metrics[metric].append(value)

    # Calculate averages with IQR outlier removal
    sector_averages = {}
    for metric, values in peer_metrics.items():
        if values:
            # IQR 방식 이상치 제거
            values_sorted = sorted(values)
            n = len(values_sorted)
            if n >= 4:
                q1 = values_sorted[n // 4]
                q3 = values_sorted[3 * n // 4]
                iqr = q3 - q1
                lower = q1 - 1.5 * iqr
                upper = q3 + 1.5 * iqr
                filtered_values = [v for v in values if lower <= v <= upper]
                if filtered_values:
                    sector_averages[metric] = sum(filtered_values) / len(filtered_values)
                else:
                    sector_averages[metric] = sum(values) / len(values)
            else:
                sector_averages[metric] = sum(values) / len(values)

            logger.debug(f"[PERF-OPT] Sector average {metric}: {sector_averages[metric]:.2f} (from {len(values)} cached peers)")

    return sector_averages


async def calculate_sector_average_metrics(
    pool,
    peer_tickers: List[str],
    event_date,
    metrics_by_domain: Dict[str, List[Dict[str, Any]]],
    target_metrics: List[str] = ['PER', 'PBR'],
    event_id: Optional[str] = None
) -> Dict[str, float]:
    """
    동종 업종 티커들의 평균 PER, PBR 등을 계산합니다.

    Args:
        pool: DB 연결 풀
        peer_tickers: 동종 업종 티커 목록
        event_date: 이벤트 날짜 (시간적 유효성 적용)
        metrics_by_domain: 메트릭 정의
        target_metrics: 계산할 메트릭 목록
        event_id: Optional event context for API call logging

    Returns:
        {'PER': 25.5, 'PBR': 3.2, ...} 형태의 업종 평균
    """
    if not peer_tickers:
        return {}
    
    # Transform 정의 로드
    transforms = await metrics.select_metric_transforms(pool)
    
    # 메트릭 계산 엔진 초기화
    engine = MetricCalculationEngine(metrics_by_domain, transforms)
    engine.build_dependency_graph()
    engine.topological_sort()
    
    # 필요한 API 목록
    required_apis = engine.get_required_apis()
    
    # 각 peer 티커의 메트릭 수집
    peer_metrics = {metric: [] for metric in target_metrics}
    
    async with FMPAPIClient() as fmp_client:
        for peer_ticker in peer_tickers[:10]:  # 최대 10개 peer만 사용 (성능)
            try:
                # Build peer context for logging: show that this is peer data collection
                peer_context = f"{event_id}:peer-{peer_ticker}" if event_id else f"peer-{peer_ticker}"

                # API 데이터 조회
                peer_api_cache = {}
                for api_id in required_apis:
                    params = {'ticker': peer_ticker}

                    # API별 파라미터 설정
                    if 'income-statement' in api_id or 'balance-sheet' in api_id or 'cash-flow' in api_id:
                        params['period'] = 'quarter'
                        params['limit'] = 20
                    elif 'historical-market-cap' in api_id:
                        params['fromDate'] = '2000-01-01'
                        if isinstance(event_date, str):
                            params['toDate'] = event_date[:10]
                        elif hasattr(event_date, 'strftime'):
                            params['toDate'] = event_date.strftime('%Y-%m-%d')
                        else:
                            params['toDate'] = str(event_date)

                    api_response = await fmp_client.call_api(api_id, params, event_id=peer_context)
                    if api_response:
                        peer_api_cache[api_id] = api_response
                
                if not peer_api_cache:
                    continue
                
                # event_date 기준 필터링 및 메트릭 계산
                if isinstance(event_date, str):
                    event_date_obj = datetime.fromisoformat(event_date.replace('Z', '+00:00')).date()
                elif hasattr(event_date, 'date'):
                    event_date_obj = event_date.date()
                else:
                    event_date_obj = event_date
                
                # 날짜 필터링
                filtered_cache = {}
                for api_id, records in peer_api_cache.items():
                    if isinstance(records, list):
                        filtered_cache[api_id] = [
                            r for r in records 
                            if _get_record_date(r) is None or _get_record_date(r) <= event_date_obj
                        ]
                    else:
                        filtered_cache[api_id] = records
                
                # 메트릭 계산
                # calculate_all now returns (quantitative, qualitative, metric_status) tuple
                value_quantitative, value_qualitative, _ = engine.calculate_all(filtered_cache, ['valuation'])

                # 타겟 메트릭 수집
                if 'valuation' in value_quantitative:
                    valuation = value_quantitative['valuation']
                    for metric in target_metrics:
                        value = valuation.get(metric)
                        if value is not None and isinstance(value, (int, float)) and value > 0:
                            peer_metrics[metric].append(value)
                
            except Exception as e:
                logger.debug(f"[I-36] Failed to calculate metrics for peer {peer_ticker}: {e}")
                continue
    
    # 평균 계산
    sector_averages = {}
    for metric, values in peer_metrics.items():
        if values:
            # 이상치 제거 (IQR 방식)
            values_sorted = sorted(values)
            n = len(values_sorted)
            if n >= 4:
                q1 = values_sorted[n // 4]
                q3 = values_sorted[3 * n // 4]
                iqr = q3 - q1
                lower = q1 - 1.5 * iqr
                upper = q3 + 1.5 * iqr
                filtered_values = [v for v in values if lower <= v <= upper]
                if filtered_values:
                    sector_averages[metric] = sum(filtered_values) / len(filtered_values)
                else:
                    sector_averages[metric] = sum(values) / len(values)
            else:
                sector_averages[metric] = sum(values) / len(values)
            
            logger.debug(f"[I-36] Sector average {metric}: {sector_averages[metric]:.2f} (from {len(values)} peers)")
    
    return sector_averages


def calculate_fair_value_from_sector_with_method(
    value_quantitative: Dict[str, Any],
    sector_averages: Dict[str, float],
    current_price: float
) -> tuple[Optional[float], Optional[str]]:
    """
    업종 평균 멀티플 기반 적정가를 계산합니다.

    우선순위:
      1) PER
      2) PBR
      3) PSR

    Returns:
        (fair_value, method) where method in {'PER', 'PBR', 'PSR'} or None
    """
    if not value_quantitative or not sector_averages or not current_price:
        return None, None

    try:
        qual_warnings = []
        valuation = value_quantitative.get('valuation', {})
        if isinstance(valuation, dict) and '_meta' in valuation:
            valuation = {k: v for k, v in valuation.items() if k != '_meta'}

        current_per = valuation.get('PER')
        sector_avg_per = sector_averages.get('PER')

        if current_per and sector_avg_per and current_per > 0 and sector_avg_per > 0:
            eps = current_price / current_per
            fair_value = sector_avg_per * eps
            logger.debug(
                f"[I-36] Fair value calculation: "
                f"current_price={current_price:.2f}, current_PER={current_per:.2f}, "
                f"sector_avg_PER={sector_avg_per:.2f}, EPS={eps:.4f}, fair_value={fair_value:.2f}"
            )
            return fair_value, 'PER'

        current_pbr = valuation.get('PBR')
        sector_avg_pbr = sector_averages.get('PBR')

        if current_pbr and sector_avg_pbr and current_pbr > 0 and sector_avg_pbr > 0:
            bps = current_price / current_pbr
            fair_value = sector_avg_pbr * bps
            logger.debug(
                f"[I-36] Fair value calculation (PBR): "
                f"current_price={current_price:.2f}, current_PBR={current_pbr:.2f}, "
                f"sector_avg_PBR={sector_avg_pbr:.2f}, BPS={bps:.4f}, fair_value={fair_value:.2f}"
            )
            return fair_value, 'PBR'

        current_psr = valuation.get('PSR')
        sector_avg_psr = sector_averages.get('PSR')

        if current_psr and sector_avg_psr and current_psr > 0 and sector_avg_psr > 0:
            sps = current_price / current_psr
            fair_value = sector_avg_psr * sps
            logger.debug(
                f"[I-36] Fair value calculation (PSR): "
                f"current_price={current_price:.2f}, current_PSR={current_psr:.2f}, "
                f"sector_avg_PSR={sector_avg_psr:.2f}, SPS={sps:.4f}, fair_value={fair_value:.2f}"
            )
            return fair_value, 'PSR'

        return None, None
    except Exception as e:
        logger.error(f"[I-36] Failed to calculate fair value: {e}")
        return None, None


def calculate_fair_value_from_sector(
    value_quantitative: Dict[str, Any],
    sector_averages: Dict[str, float],
    current_price: float
) -> Optional[float]:
    """
    업종 평균 멀티플 기반 적정가를 계산합니다.
    """
    fair_value, _ = calculate_fair_value_from_sector_with_method(
        value_quantitative, sector_averages, current_price
    )
    return fair_value


async def calculate_fair_value_for_ticker(
    pool,
    ticker: str,
    event_date,
    value_quantitative: Dict[str, Any],
    current_price: float,
    metrics_by_domain: Dict[str, List[Dict[str, Any]]]
) -> Dict[str, Any]:
    """
    특정 티커의 업종 평균 기반 적정가를 계산합니다.
    
    Args:
        pool: DB 연결 풀
        ticker: 티커 심볼
        event_date: 이벤트 날짜
        value_quantitative: Quantitative 메트릭 결과
        current_price: 현재 주가
        metrics_by_domain: 메트릭 정의
    
    Returns:
        {
            'fair_value': 80.0,
            'position': 'short',
            'disparity': -0.20,
            'sector_averages': {'PER': 20.0, 'PBR': 2.5},
            'peer_count': 8
        }
    """
    result = {
        'fair_value': None,
        'position': None,
        'disparity': None,
        'sector_averages': None,
        'peer_count': 0
    }
    
    try:
        # 1. 동종 업종 티커 조회
        peer_tickers = await get_peer_tickers(ticker)
        if not peer_tickers:
            logger.warning(f"[I-36] No peer tickers for {ticker}, skipping fair value calculation")
            return result
        
        result['peer_count'] = len(peer_tickers)
        
        # 2. 업종 평균 PER/PBR 계산
        sector_averages = await calculate_sector_average_metrics(
            pool, peer_tickers, event_date, metrics_by_domain
        )
        if not sector_averages:
            logger.warning(f"[I-36] Could not calculate sector averages for {ticker}")
            return result
        
        result['sector_averages'] = sector_averages
        
        # 3. 적정가 계산
        fair_value = calculate_fair_value_from_sector(
            value_quantitative, sector_averages, current_price
        )
        if fair_value is None:
            logger.warning(f"[I-36] Could not calculate fair value for {ticker}")
            return result
        
        result['fair_value'] = round(fair_value, 2)
        
        # 4. Position, Disparity 계산
        if fair_value > current_price:
            result['position'] = 'long'
        elif fair_value < current_price:
            result['position'] = 'short'
        else:
            result['position'] = 'neutral'
        
        result['disparity'] = round((fair_value / current_price) - 1, 4) if current_price != 0 else None
        
        logger.info(
            f"[I-36] Fair value for {ticker}: fair_value={result['fair_value']}, "
            f"position={result['position']}, disparity={result['disparity']:.2%}"
        )
        
        return result

    except Exception as e:
        logger.error(f"[I-36] Failed to calculate fair value for {ticker}: {e}")
        return result


# =============================================================================
# I-41: priceQuantitative 메트릭 계산 (Metric System 통합)
# =============================================================================

async def calculate_price_quantitative_metric(
    pool,
    ticker: str,
    event_date,
    value_quantitative: Dict[str, Any],
    current_price: float,
    metrics_by_domain: Dict[str, List[Dict[str, Any]]]
) -> Optional[float]:
    """
    priceQuantitative 메트릭을 계산합니다 (I-41).

    이 함수는 calculate_fair_value_for_ticker를 래핑하여
    메트릭 시스템(custom source)과 통합합니다.

    Args:
        pool: DB 연결 풀
        ticker: 티커 심볼
        event_date: 이벤트 날짜
        value_quantitative: Quantitative 메트릭 결과 (PER, PBR 포함)
        current_price: 현재 주가
        metrics_by_domain: 메트릭 정의

    Returns:
        적정가 (fair value) 또는 None

    Example:
        >>> price_quant = await calculate_price_quantitative_metric(
        ...     pool, 'AAPL', '2025-12-31',
        ...     {'valuation': {'PER': 28.5, 'PBR': 7.2}},
        ...     180.0,
        ...     metrics_by_domain
        ... )
        >>> # price_quant = 185.0

    Note:
        - Peer tickers 없으면 None 반환
        - I-36에서 구현한 로직 재사용
    """
    try:
        # I-36 함수 재사용
        result = await calculate_fair_value_for_ticker(
            pool, ticker, event_date, value_quantitative, current_price, metrics_by_domain
        )

        fair_value = result.get('fair_value')

        if fair_value is not None:
            logger.info(
                f"[I-41] priceQuantitative for {ticker}: {fair_value} "
                f"(peers: {result.get('peer_count', 0)}, "
                f"sector_avg: {result.get('sector_averages')})"
            )
        else:
            logger.debug(f"[I-41] priceQuantitative for {ticker}: NULL (no peer tickers or calculation failed)")

        return fair_value

    except Exception as e:
        logger.error(f"[I-41] Failed to calculate priceQuantitative for {ticker}: {e}")
        return None
