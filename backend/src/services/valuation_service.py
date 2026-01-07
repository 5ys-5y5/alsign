"""Service for POST /backfillEventsTable endpoint - calculates valuation metrics."""

import logging
import time
import json
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime, date
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
    completed_events_count: Dict[str, int] = None,
    metrics_list: Optional[List[str]] = None,
    global_peer_cache: Dict[str, Dict[str, Any]] = None,
    ticker_to_peers: Dict[str, List[str]] = None
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

        logger.info(f"[table: txn_events | id: {ticker_context_id}] | ========== TICKER-LEVEL API CACHING START ==========")
        logger.info(f"[table: txn_events | id: {ticker_context_id}] | Fetching {len(required_apis)} APIs for {ticker} (ONCE for all {len(ticker_events)} events)")

        # Fetch all API data once
        ticker_api_cache = {}
        consensus_summary_cache = None

        async with FMPAPIClient() as fmp_client:
            # Fetch quantitative APIs
            for api_id in required_apis:
                try:
                    params = {'ticker': ticker}

                    if 'historical-price' in api_id or 'eod' in api_id or 'historical-market-cap' in api_id:
                        # Wide date range to cover all events
                        # I-25: fmp-historical-market-capitalization도 from/to 파라미터 필요
                        params['fromDate'] = '2000-01-01'
                        params['toDate'] = datetime.now().strftime('%Y-%m-%d')
                    else:
                        params['period'] = 'quarter'
                        params['limit'] = 100

                    result = await fmp_client.call_api(api_id, params, event_id=ticker_context_id)
                    ticker_api_cache[api_id] = result
                    logger.debug(f"[Ticker Batch] {ticker}: Cached {api_id} ({len(result) if isinstance(result, list) else 'single'} records)")
                except Exception as e:
                    log_warning(logger, f"Failed to fetch API {api_id}", ticker=ticker)
                    ticker_api_cache[api_id] = []

            # Fetch qualitative API (consensus) ONCE for ticker
            try:
                consensus_data = await fmp_client.call_api('fmp-price-target-consensus', {'ticker': ticker}, event_id=ticker_context_id)
                if consensus_data:
                    if isinstance(consensus_data, list) and len(consensus_data) > 0:
                        consensus_summary_cache = consensus_data[0]
                    elif isinstance(consensus_data, dict):
                        consensus_summary_cache = consensus_data
                logger.debug(f"[Ticker Batch] {ticker}: Consensus summary cached")
            except Exception as e:
                logger.warning(f"[Ticker Batch] {ticker}: Consensus fetch skipped: {e}")

        logger.info(f"[table: txn_events | id: {ticker_context_id}] | API cache ready: {len(ticker_api_cache) + 1} APIs cached")
        logger.info(f"[table: txn_events | id: {ticker_context_id}] | ========== TICKER-LEVEL API CACHING END ==========")
        
        # OPTIMIZATION: Load transforms and engine ONCE per ticker (not per event!)
        transforms = await metrics.select_metric_transforms(pool)
        engine = MetricCalculationEngine(metrics_by_domain, transforms)
        target_domains = ['valuation', 'profitability', 'momentum', 'risk', 'dilution']
        
        logger.info(f"[Ticker Batch] {ticker}: MetricEngine initialized (60 metrics)")

        # ========================================
        # CRITICAL: Use GLOBAL PEER CACHE (PERFORMANCE OPTIMIZATION)
        # ========================================
        # IMPORTANT: Always calculate priceQuantitative for ALL events (source-agnostic)
        # per user requirement: "quantitative columns must be filled regardless of source value"
        peer_tickers = []
        sector_averages = {}
        peer_count = 0

        try:
            logger.info(f"[table: txn_events | id: {ticker_context_id}] | ========== PEER DATA PROCESSING START ==========")

            # USE GLOBAL PEER CACHE if available (PERFORMANCE OPTIMIZATION)
            if global_peer_cache and ticker_to_peers:
                # Get pre-collected peer list for this ticker
                peer_tickers = ticker_to_peers.get(ticker, [])
                peer_count = len(peer_tickers)

                if peer_tickers:
                    logger.info(f"[PERF-OPT] {ticker}: Using global peer cache ({peer_count} peers)")

                    # Calculate sector averages from GLOBAL CACHE (no API calls!)
                    sector_averages = await calculate_sector_average_from_cache(
                        peer_tickers, global_peer_cache
                    )

                    logger.info(
                        f"[PERF-OPT] {ticker}: Sector averages calculated from cache: {list(sector_averages.keys())}"
                    )
                else:
                    logger.warning(f"[PERF-OPT] {ticker}: No peers in global cache")

            else:
                # FALLBACK: Use per-ticker peer fetching (old method)
                logger.info(f"[FALLBACK] {ticker}: Global cache not available, fetching peers individually")

                # Get peer tickers ONCE for this ticker
                peer_tickers = await get_peer_tickers(ticker, event_id=ticker_context_id)
                peer_count = len(peer_tickers)

                if peer_tickers and ticker_events:
                    logger.info(f"[FALLBACK] {ticker}: Found {peer_count} peer tickers: {peer_tickers}")

                    # Use first event's date as reference for sector averages
                    reference_date = ticker_events[0]['event_date']
                    sector_averages = await calculate_sector_average_metrics(
                        pool, peer_tickers, reference_date, metrics_by_domain, event_id=ticker_context_id
                    )
                    logger.info(f"[FALLBACK] {ticker}: Sector averages calculated: {list(sector_averages.keys())}")
                else:
                    logger.warning(f"[FALLBACK] {ticker}: No peer tickers found")

            logger.info(f"[table: txn_events | id: {ticker_context_id}] | ========== PEER DATA PROCESSING END ==========")

            if not sector_averages:
                logger.warning(f"[PERF] {ticker}: No sector averages available, priceQuantitative will be NULL")

        except Exception as e:
            logger.warning(f"[PERF] {ticker}: Failed to process peer data: {e}")
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

    logger.info(f"[table: txn_events | id: ticker-cache:{ticker}] | ========== EVENT PROCESSING START ==========")
    logger.info(f"[table: txn_events | id: ticker-cache:{ticker}] | Processing {total_events} events using CACHED API data (no new API calls)")

    for idx, event in enumerate(ticker_events, 1):
        event_id = event.get('id')
        event_date = event['event_date']
        source = event['source']
        source_id = event['source_id']

        # Row ID logging for user visibility - use txn_events.id
        event_id_str = str(event_id) if event_id else "unknown"
        row_context = f"[table: txn_events | id: {event_id_str}]"

        logger.info(f"{row_context} | ---------- Event {idx}/{total_events} | source={source} ----------")

        try:
            # I-41: Prepare custom_values for priceQuantitative metric
            custom_values = {}

            # ALWAYS calculate priceQuantitative for ALL events (source-agnostic)
            # per user requirement: "quantitative columns must be filled regardless of source value"
            # IMPORTANT: Store current_price for later use in position/disparity calculation
            current_price_for_position = None

            if sector_averages:
                # First, calculate basic quantitative metrics (PER, PBR, etc.) to get current values
                temp_quant_result = await calculate_quantitative_metrics_fast(
                    ticker, event_date, ticker_api_cache, engine, target_domains
                )

                # Get current price for priceQuantitative calculation
                # For consensus events: get from qualitative metrics (recent data)
                # For earning events: get historical price at event_date
                current_price = None
                if source == 'consensus':
                    temp_qual_result = await calculate_qualitative_metrics_fast(
                        pool, ticker, event_date, source, source_id, consensus_summary_cache
                    )
                    current_price = temp_qual_result.get('currentPrice')
                else:
                    # For earning events: get historical price at event_date
                    # Use fmp-historical-price-eod-full API cache
                    if 'fmp-historical-price-eod-full' in ticker_api_cache:
                        historical_prices = ticker_api_cache['fmp-historical-price-eod-full']
                        if isinstance(historical_prices, list):
                            # Convert event_date to date object for comparison
                            if isinstance(event_date, str):
                                target_date = datetime.fromisoformat(event_date.replace('Z', '+00:00')).date()
                            elif hasattr(event_date, 'date'):
                                target_date = event_date.date()
                            else:
                                target_date = event_date

                            # Find the closest price on or before event_date
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

                # CRITICAL: Save current_price for position/disparity calculation later
                current_price_for_position = current_price

                # DEBUG: Log price retrieval
                if idx <= 2:
                    logger.info(f"{row_context} | DEBUG | current_price={current_price}, has_temp_value={temp_quant_result.get('value') is not None}, sector_avg_keys={list(sector_averages.keys())}")

                if current_price and temp_quant_result.get('value'):
                    # PERFORMANCE FIX: Use CACHED sector_averages (NO API CALLS!)
                    # Instead of calling calculate_price_quantitative_metric which fetches peer data every time,
                    # we use the sector_averages that were cached once at ticker level
                    fair_value = calculate_fair_value_from_sector(
                        temp_quant_result.get('value'),
                        sector_averages,  # CACHED at ticker level - NO API calls!
                        current_price
                    )

                    if fair_value is not None:
                        custom_values['priceQuantitative'] = fair_value
                        if idx <= 2:
                            logger.info(f"{row_context} | DEBUG | priceQuantitative={fair_value:.2f} (CACHED sector_avg)")
                    else:
                        if idx <= 2:
                            logger.warning(f"{row_context} | DEBUG | priceQuantitative=NULL (calculation failed)")
                else:
                    if idx <= 2:
                        logger.warning(f"{row_context} | DEBUG | Skipped priceQuantitative: current_price={current_price}, has_value={temp_quant_result.get('value') is not None}")

            # Calculate quantitative metrics using CACHED API data + custom values
            quant_result = await calculate_quantitative_metrics_fast(
                ticker, event_date, ticker_api_cache, engine, target_domains,
                custom_values=custom_values  # I-41: Pass custom metrics
            )

            # Calculate qualitative metrics using CACHED consensus data
            qual_result = await calculate_qualitative_metrics_fast(
                pool, ticker, event_date, source, source_id, consensus_summary_cache
            )

            # Calculate positions and disparities
            # I-41: Use priceQuantitative from value_quantitative if available
            value_quant = quant_result.get('value', {})

            # CRITICAL: Use current_price from qualitative OR historical price for earning events
            current_price = qual_result.get('currentPrice')
            if not current_price and current_price_for_position:
                # For earning events: use historical price that was retrieved earlier
                current_price = current_price_for_position

            # Extract priceQuantitative from valuation domain
            price_quant_value = None
            if value_quant and 'valuation' in value_quant:
                price_quant_value = value_quant['valuation'].get('priceQuantitative')

            # DEBUG: Log position/disparity calculation
            if idx <= 2:
                logger.info(f"{row_context} | DEBUG | Position calc: price_quant={price_quant_value}, current_price={current_price} (from_qual={qual_result.get('currentPrice') is not None}, from_hist={current_price_for_position is not None})")

            if price_quant_value is not None and current_price:
                # I-41: Calculate position/disparity using priceQuantitative
                if price_quant_value > current_price:
                    position_quant = 'long'
                elif price_quant_value < current_price:
                    position_quant = 'short'
                else:
                    position_quant = 'neutral'

                disparity_quant = round((price_quant_value / current_price) - 1, 4) if current_price != 0 else None

                if idx <= 2:
                    logger.info(f"{row_context} | DEBUG | Calculated position={position_quant}, disparity={disparity_quant}")
            else:
                # Fallback: No priceQuantitative available
                position_quant, disparity_quant = calculate_position_disparity(
                    quant_result.get('value'),
                    qual_result.get('currentPrice')
                )
                if idx <= 2:
                    logger.warning(f"{row_context} | DEBUG | Fallback position={position_quant}, disparity={disparity_quant}")
            
            position_qual, disparity_qual = calculate_position_disparity(
                qual_result.get('value'),
                qual_result.get('currentPrice')
            )

            # I-42: DON'T format values for database storage
            # The formatter creates nested structure (values/dateInfo) which breaks database queries
            # Formatting should only be done for API responses, not database storage
            #
            # OLD CODE (BROKEN):
            # formatted_quant = format_value_quantitative(quant_result.get('value'))
            # formatted_qual = format_value_qualitative(qual_result.get('value'))
            #
            # NEW CODE: Store raw values directly
            value_quant = quant_result.get('value')
            value_qual = qual_result.get('value')

            # I-42 DEBUG: Log what we're about to store
            if value_quant and 'valuation' in value_quant:
                val_keys = list(value_quant['valuation'].keys())[:5]
                logger.info(f"[I-42 DEBUG] value_quant valuation keys: {val_keys}")
                if 'priceQuantitative' in value_quant['valuation']:
                    logger.info(f"[I-42 DEBUG] priceQuantitative value: {value_quant['valuation']['priceQuantitative']}")

            # Extract priceQuantitative for dedicated column
            price_quant_col = None
            if value_quant and 'valuation' in value_quant:
                price_quant_col = value_quant['valuation'].get('priceQuantitative')

            # Build peer_quantitative JSONB (if priceQuantitative exists)
            peer_quant_col = None
            if price_quant_col is not None and sector_averages:
                peer_quant_col = {
                    'peerCount': peer_count,
                    'sectorAverages': sector_averages
                }

            # DEBUG: Log column values for first few events
            if idx <= 3:
                logger.info(f"{row_context} | DEBUG | price_quantitative={price_quant_col}, peer_quantitative={'set' if peer_quant_col else 'NULL'}")

            # Prepare batch update
            batch_updates.append({
                'ticker': ticker,
                'event_date': event_date,
                'source': source,
                'source_id': source_id,
                'value_quantitative': value_quant,
                'value_qualitative': value_qual,
                'position_quantitative': position_quant,
                'position_qualitative': position_qual,
                'disparity_quantitative': disparity_quant,
                'disparity_qualitative': disparity_qual,
                # NEW: Dedicated columns for performance (I-42)
                'price_quantitative': price_quant_col,
                'peer_quantitative': peer_quant_col
            })

            # INCREMENTAL DB UPDATE: Save progress every N events (PERFORMANCE OPTIMIZATION)
            INCREMENTAL_UPDATE_BATCH_SIZE = 20
            if len(batch_updates) >= INCREMENTAL_UPDATE_BATCH_SIZE:
                try:
                    logger.info(f"[INCR-UPDATE] {ticker}: Saving {len(batch_updates)} events to DB (checkpoint at {idx}/{total_events})")
                    incr_updated_count = await metrics.batch_update_event_valuations(
                        pool, batch_updates, overwrite=overwrite, metrics=metrics_list
                    )
                    logger.info(f"[INCR-UPDATE] {ticker}: ✓ {incr_updated_count} events saved successfully")

                    # Clear batch after successful update
                    batch_updates.clear()

                except Exception as e:
                    logger.warning(f"[INCR-UPDATE] {ticker}: Incremental DB update failed: {e}")
                    # Don't clear batch_updates on failure - will retry at end

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

            # Log each event completion
            logger.info(f"{row_context} | Event {idx}/{total_events} completed | quant={'OK' if quant_result['status']=='success' else 'FAIL'}, qual={'OK' if qual_result['status']=='success' else 'FAIL'}")

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
            log_error(logger, f"{row_context} | Event processing failed", exception=e, ticker=ticker)

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

    logger.info(f"[table: txn_events | id: ticker-cache:{ticker}] | ========== EVENT PROCESSING END ==========")
    logger.info(f"[table: txn_events | id: ticker-cache:{ticker}] | Processed {total_events} events | quant_success={quant_success}, qual_success={qual_success}")

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
    
    # Log ticker completion
    log_batch_complete(logger, ticker, len(ticker_events), quant_success + qual_success, quant_fail + qual_fail)
    
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
    tickers: Optional[List[str]] = None,
    cancel_event: Optional[asyncio.Event] = None,
    metrics_list: Optional[List[str]] = None,
    batch_size: Optional[int] = None
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
        batch_size: Optional batch size for processing events. If None, processes all events in one batch.

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

    logger.info("=" * 80)
    logger.info(
        "[backfillEventsTable] START - Processing valuations",
        extra=create_log_context(
            endpoint='POST /backfillEventsTable',
            phase='start',
            elapsed_ms=0
        )
    )
    logger.info(f"[backfillEventsTable] Parameters: overwrite={overwrite}, from_date={from_date}, to_date={to_date}, tickers={tickers}, batch_size={batch_size}")
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

    phase2_start = time.time()
    try:
        logger.info(f"[backfillEventsTable] Calling metrics.select_events_for_valuation...")
        events = await metrics.select_events_for_valuation(
            pool,
            from_date=from_date,
            to_date=to_date,
            tickers=tickers
        )
        phase2_elapsed = time.time() - phase2_start
        logger.info("=" * 80)
        logger.info(f"[backfillEventsTable] ✓ Phase 2 completed in {phase2_elapsed:.2f}s")
        logger.info(f"[backfillEventsTable] Events loaded: {len(events)} events")
        if tickers:
            logger.info(f"[backfillEventsTable] Filtered by tickers: {tickers}")
        logger.info("=" * 80)
    except Exception as e:
        logger.error("=" * 80)
        logger.error(f"[backfillEventsTable] ✗ FAILED to load events: {e}")
        logger.error("=" * 80)
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

    # BATCH PROCESSING: Log batch info (actual batching happens at query level via LIMIT)
    if batch_size and len(events) > batch_size:
        logger.info("=" * 80)
        logger.warning(f"[BATCH] Note: Loaded {len(events)} events (more than batch_size={batch_size})")
        logger.warning(f"[BATCH] Tip: For true batch processing, use date filters to limit events at query time")
        logger.warning(f"[BATCH] Example: ?from_date=2024-01-01&to_date=2024-03-31&batch_size=5000")
        logger.info("=" * 80)
    elif batch_size:
        logger.info(f"[BATCH] Batch size set to {batch_size}, but only {len(events)} events loaded (within limit)")

    # Process all loaded events
    logger.info("[backfillEventsTable] Processing all loaded events")

    # Phase 3: Group events by ticker
    phase3_start = time.time()
    logger.info("=" * 80)
    logger.info(f"[backfillEventsTable] Phase 3: Grouping {len(events)} events by ticker")
    ticker_groups = group_events_by_ticker(events)
    phase3_elapsed = time.time() - phase3_start
    logger.info(f"[backfillEventsTable] ✓ Phase 3 completed in {phase3_elapsed:.2f}s - grouped into {len(ticker_groups)} tickers")
    logger.info("=" * 80)

    # Phase 3.5: Global Peer Collection & Parallel Fetching (PERFORMANCE OPTIMIZATION)
    logger.info("=" * 80)
    logger.info(f"[backfillEventsTable] Phase 3.5: GLOBAL PEER COLLECTION & PARALLEL FETCHING")
    logger.info("=" * 80)

    global_peer_cache = {}
    ticker_to_peers = {}

    try:
        # Step 1: Collect all peer tickers
        peer_collect_start = time.time()
        logger.info(f"[PERF-OPT] Step 1/2: Starting peer ticker collection for {len(ticker_groups)} tickers...")
        ticker_to_peers, unique_peers = await collect_all_peer_tickers(ticker_groups)
        peer_collect_elapsed = time.time() - peer_collect_start

        logger.info(f"[PERF-OPT] ✓ Step 1/2: Peer collection completed in {peer_collect_elapsed:.2f}s")
        logger.info(f"[PERF-OPT] Found {len(ticker_to_peers)} tickers with peers, {len(unique_peers)} unique peers total")

        # Step 2: Fetch peer financials in parallel
        if unique_peers:
            # Use first event date as reference for all peers (reasonable approximation)
            reference_date = events[0]['event_date']

            peer_fetch_start = time.time()
            logger.info(f"[PERF-OPT] Step 2/2: Starting parallel fetch of {len(unique_peers)} peer financials (max_concurrent=20)...")
            global_peer_cache = await fetch_peer_financials_parallel(
                unique_peers,
                pool,
                metrics_by_domain,
                reference_date,
                max_concurrent=20  # Parallel fetching limit
            )
            peer_fetch_elapsed = time.time() - peer_fetch_start

            logger.info("=" * 80)
            logger.info(f"[PERF-OPT] ✓ Step 2/2: Global peer cache ready: {len(global_peer_cache)} peers cached")
            logger.info(f"[PERF-OPT] ✓ Total peer fetching time: {peer_fetch_elapsed:.2f}s (parallelized)")
            logger.info(f"[PERF-OPT] ✓ Estimated time saved vs sequential: {peer_fetch_elapsed * 10:.2f}s → {peer_fetch_elapsed:.2f}s (~{(1 - peer_fetch_elapsed/(peer_fetch_elapsed*10))*100:.0f}% faster)")
            logger.info("=" * 80)
        else:
            logger.warning("[PERF-OPT] No peer tickers found for any ticker - skipping Step 2/2")

    except Exception as e:
        logger.error("=" * 80)
        logger.error(f"[PERF-OPT] ✗ Failed to build global peer cache: {e}", exc_info=True)
        logger.warning("[PERF-OPT] Falling back to per-ticker peer fetching")
        logger.error("=" * 80)
        global_peer_cache = {}
        ticker_to_peers = {}
    
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
    # This is DB/calculation work (not API calls), so use higher concurrency
    TICKER_CONCURRENCY = 50  # Process 50 tickers concurrently (increased from 10)
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
        
        # Check for cancellation
        if cancel_event and cancel_event.is_set():
            logger.warning(f"[backfillEventsTable] Cancelled - skipping ticker {ticker}")
            return {
                'ticker': ticker,
                'quantitative': {'success': 0, 'fail': 0, 'skip': len(ticker_events)},
                'qualitative': {'success': 0, 'fail': 0, 'skip': len(ticker_events)},
                'priceTrend': {'success': 0, 'fail': 0, 'skip': len(ticker_events)},
                'dbUpdate': {'success': 0, 'fail': 0}
            }
        
        async with semaphore:
            result = await process_ticker_batch(
                pool, ticker, ticker_events, metrics_by_domain, overwrite,
                total_events_count, completed_events_count,
                metrics_list,  # I-41: Pass selective update parameters
                global_peer_cache,  # PERF-OPT: Global peer cache
                ticker_to_peers  # PERF-OPT: Ticker to peers mapping
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

    total_elapsed_ms = int((time.time() - start_time) * 1000)

    # Build summary
    summary = {
        'totalEventsProcessed': len(events),
        'quantitativeSuccess': quantitative_success,
        'quantitativeFail': quantitative_fail,
        'qualitativeSuccess': qualitative_success,
        'qualitativeFail': qualitative_fail,
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
    target_domains: List[str],
    custom_values: Optional[Dict[str, Any]] = None
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
        # I-41: Pass custom_values for priceQuantitative metric
        result = engine.calculate_all(api_data_filtered, target_domains, custom_values)
        
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

        # I-26: Check if event_date is historical (more than 7 days ago)
        # FMP price-target-consensus API only provides current consensus, not historical
        from datetime import timedelta
        today = datetime.now().date()
        
        # Convert event_date to date object
        if isinstance(event_date, str):
            event_date_obj = datetime.fromisoformat(event_date.replace('Z', '+00:00')).date()
        elif hasattr(event_date, 'date'):
            event_date_obj = event_date.date()
        else:
            event_date_obj = event_date
        
        is_historical_event = event_date_obj < (today - timedelta(days=7))
        
        # Use CACHED consensus summary - NO API CALL!
        # But only for recent events (within 7 days)
        # Read targetSummary from evt_consensus.target_summary (pre-calculated by GET /sourceData Phase 3)
        target_summary = consensus_data.get('target_summary')
        
        if target_summary:
            # Extract targetMedian from the pre-calculated summary (I-37: use actual Median, not Avg)
            target_median = target_summary.get('allTimeMedianPriceTarget')
            target_average = target_summary.get('allTimeAvgPriceTarget')
            consensus_meta = {
                'dataAvailable': True,
                'source': 'evt_consensus.target_summary',
                'event_date': event_date_obj.isoformat()
            }
            logger.debug(f"[QualitativeMetrics] targetSummary read from evt_consensus for {ticker} at {event_date_obj}")
        else:
            # targetSummary not calculated yet - run GET /sourceData?mode=consensus first
            target_median = None
            consensus_meta = {
                'dataAvailable': False,
                'reason': 'targetSummary not calculated. Run GET /sourceData?mode=consensus first.',
                'event_date': event_date_obj.isoformat()
            }
            logger.debug(f"[QualitativeMetrics] targetSummary not available for {ticker} at {event_date_obj} - run GET /sourceData first")

        # value_qualitative 구성
        # targetSummary: 측정 당시(event_date 기준)의 price target 요약 (evt_consensus에서 계산)
        value_qualitative = {
            'targetMedian': target_median,
            'targetSummary': target_summary,  # 측정 당시의 요약 (replaced consensusSummary)
            'consensusSignal': consensus_signal,
            '_meta': consensus_meta
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
    Generate price_trend arrays for events in txn_events and trades in txn_trades.

    Fetches policy configuration, generates dayOffset scaffolds,
    fetches OHLC data from FMP, and populates txn_price_trend table for:
    1. All events from txn_events (existing behavior)
    2. Trades from txn_trades that don't exist in txn_events (new behavior)

    Args:
        from_date: Optional start date for filtering by event_date/trade_date
        to_date: Optional end date for filtering by event_date/trade_date
        tickers: Optional list of ticker symbols to filter. If None, processes all tickers.

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

    # Load events to process
    events = await metrics.select_events_for_valuation(
        pool,
        from_date=from_date,
        to_date=to_date,
        tickers=tickers
    )

    # Load trades from txn_trades that are NOT in txn_events
    trades = await metrics.select_trades_for_price_trends(
        pool,
        from_date=from_date,
        to_date=to_date,
        tickers=tickers
    )

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

    # Calculate OHLC fetch ranges per ticker
    # Guideline line 986-987: fromDate = min_event_date + countStart, toDate = max_event_date + countEnd
    from datetime import timedelta
    ohlc_ranges = {}
    for ticker, ticker_events in events_by_ticker.items():
        event_dates = [e['event_date'].date() if hasattr(e['event_date'], 'date') else e['event_date'] for e in ticker_events]
        min_date = min(event_dates)
        max_date = max(event_dates)

        # Apply priceEodOHLC_dateRange policy (countStart/countEnd are calendar day offsets)
        # I-43: Add extra buffer to ensure we have data for all dayOffset values (-14 to +14 trading days)
        # Trading days -14/+14 require approximately -25/+25 calendar days (accounting for weekends + holidays)
        extra_buffer_days = 15  # Additional buffer on each side
        fetch_start = min_date + timedelta(days=ohlc_count_start - extra_buffer_days)
        fetch_end = max_date + timedelta(days=ohlc_count_end + extra_buffer_days)

        ohlc_ranges[ticker] = (fetch_start, fetch_end)

    # Fetch OHLC data for all tickers
    ohlc_cache = {}
    async with FMPAPIClient() as fmp_client:
        for ticker, (fetch_start, fetch_end) in ohlc_ranges.items():
            logger.info(
                f"Fetching OHLC for {ticker} from {fetch_start} to {fetch_end}",
                extra={
                    'endpoint': 'POST /generatePriceTrends',
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
    # I-43: Group events by (ticker, event_date) for txn_price_trend
    # ========================================
    # Deduplicate events by (ticker, event_date) since txn_price_trend is indexed by this combination
    unique_ticker_dates = {}
    for event in events:
        ticker = event['ticker']
        event_date = event['event_date'].date() if hasattr(event['event_date'], 'date') else event['event_date']
        key = (ticker, event_date)
        if key not in unique_ticker_dates:
            unique_ticker_dates[key] = event

    logger.info(
        f"Deduplicated {len(all_records)} records into {len(unique_ticker_dates)} unique (ticker, event_date) pairs",
        extra={
            'endpoint': 'POST /generatePriceTrends',
            'phase': 'deduplicate_events',
            'elapsed_ms': int((time.time() - start_time) * 1000),
            'counters': {'records': len(all_records), 'events': len(events), 'trades': len(trades), 'unique_pairs': len(unique_ticker_dates)},
            'progress': {},
            'rate': {},
            'batch': {},
            'warn': []
        }
    )

    # ========================================
    # Helper function for individual price trend upserts
    # ========================================
    async def _upsert_single_price_trend(ticker: str, event_date: date, jsonb_columns: dict, wts_long: int, wts_short: int):
        """
        Upsert a single price trend record to txn_price_trend table.

        Args:
            ticker: Stock ticker symbol
            event_date: Event date
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
                    ticker, event_date,
                    d_neg14, d_neg13, d_neg12, d_neg11, d_neg10,
                    d_neg9, d_neg8, d_neg7, d_neg6, d_neg5,
                    d_neg4, d_neg3, d_neg2, d_neg1,
                    d_0,
                    d_pos1, d_pos2, d_pos3, d_pos4, d_pos5,
                    d_pos6, d_pos7, d_pos8, d_pos9, d_pos10,
                    d_pos11, d_pos12, d_pos13, d_pos14,
                    wts_long, wts_short
                ) VALUES (
                    $1, $2,
                    $3::jsonb, $4::jsonb, $5::jsonb, $6::jsonb, $7::jsonb,
                    $8::jsonb, $9::jsonb, $10::jsonb, $11::jsonb, $12::jsonb,
                    $13::jsonb, $14::jsonb, $15::jsonb, $16::jsonb,
                    $17::jsonb,
                    $18::jsonb, $19::jsonb, $20::jsonb, $21::jsonb, $22::jsonb,
                    $23::jsonb, $24::jsonb, $25::jsonb, $26::jsonb, $27::jsonb,
                    $28::jsonb, $29::jsonb, $30::jsonb, $31::jsonb,
                    $32, $33
                )
                ON CONFLICT (ticker, event_date) DO UPDATE
                SET
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

    for idx, ((ticker, event_date), event) in enumerate(unique_ticker_dates.items()):
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
            dayoffset_target_dates = {}  # Store target dates separately

            for dayoffset, target_date in dayoffset_dates:
                date_str = target_date.isoformat()
                dayoffset_target_dates[dayoffset] = date_str
                ohlc = ohlc_cache.get(ticker, {}).get(date_str)

                if ohlc:
                    dayoffset_ohlc[dayoffset] = {
                        'open': float(ohlc.get('open')) if ohlc.get('open') else None,
                        'high': float(ohlc.get('high')) if ohlc.get('high') else None,
                        'low': float(ohlc.get('low')) if ohlc.get('low') else None,
                        'close': float(ohlc.get('close')) if ohlc.get('close') else None
                    }
                else:
                    # Missing data - will fill later
                    dayoffset_ohlc[dayoffset] = None

            # Fill missing data with forward/backward fill
            # For negative offsets: use previous trading day (backward fill)
            # For positive offsets: use next trading day (forward fill)
            for offset in range(-14, 15):
                if dayoffset_ohlc.get(offset) is None:
                    if offset < 0:
                        # Backward fill: use earlier trading day
                        for prev_offset in range(offset - 1, -15, -1):
                            if dayoffset_ohlc.get(prev_offset) is not None:
                                dayoffset_ohlc[offset] = dayoffset_ohlc[prev_offset].copy()
                                break
                    else:
                        # Forward fill: use later trading day
                        for next_offset in range(offset + 1, 15):
                            if dayoffset_ohlc.get(next_offset) is not None:
                                dayoffset_ohlc[offset] = dayoffset_ohlc[next_offset].copy()
                                break

            # Get D0 close as base_close for performance calculation
            # If D0 close is None, set base_close to None but continue (record with null values)
            d0_data = dayoffset_ohlc.get(0)
            base_close = d0_data['close'] if d0_data and d0_data.get('close') is not None else None


            if base_close is None:
                logger.warning(f"No D0 close for {ticker} on {event_date}, recording with null values")
                # Continue processing but all will be null

            # Build JSONB columns for each dayOffset (-14 to 14)
            jsonb_columns = {}
            day_performances = {}  # For WTS calculation

            for offset in range(-14, 15):  # -14 to 14 inclusive
                ohlc = dayoffset_ohlc.get(offset)
                target_date = dayoffset_target_dates.get(offset)

                if ohlc and ohlc.get('close') is not None and base_close is not None:
                    # Has data and base_close available
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
                    # Has data but no base_close - record price without performance
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
                    # No data - record with targetDate only
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

                # Map offset to column name
                if offset < 0:
                    col_name = f'd_neg{abs(offset)}'
                elif offset == 0:
                    col_name = 'd_0'
                else:
                    col_name = f'd_pos{offset}'

                # Convert to JSON string for UNNEST (asyncpg requires str for array parameters)
                jsonb_columns[col_name] = json.dumps(jsonb_data) if jsonb_data else None

            # Calculate WTS (Which Trading day to Sell)
            # wts_long: best dayOffset for long position (max performance)
            # wts_short: best dayOffset for short position (max negative performance = min performance)
            wts_long = None
            wts_short = None
            max_performance = None
            min_performance = None

            for offset, perf in day_performances.items():
                if perf is not None:
                    # Long position: maximize performance
                    if max_performance is None or perf > max_performance:
                        max_performance = perf
                        wts_long = offset

                    # Short position: maximize negative performance (minimize performance)
                    if min_performance is None or perf < min_performance:
                        min_performance = perf
                        wts_short = offset


            # Immediately save to database (incremental save)
            try:
                await _upsert_single_price_trend(ticker, event_date, jsonb_columns, wts_long, wts_short)
                success_count += 1
                logger.debug(
                    f"Saved price trend: {ticker} @ {event_date}",
                    extra={
                        'endpoint': 'POST /generatePriceTrends',
                        'phase': 'save_price_trend',
                        'counters': {'success': 1}
                    }
                )
            except Exception as db_error:
                fail_count += 1
                logger.error(
                    f"Failed to save price trend: {ticker} @ {event_date}: {db_error}",
                    exc_info=True
                )
                # Continue processing other records

        except Exception as e:
            logger.error(f"Failed to generate price trend for {ticker} {event_date}: {e}")
            fail_count += 1
            continue

        # Log progress every 50 pairs
        if (idx + 1) % 50 == 0 or (idx + 1) == len(unique_ticker_dates):
            elapsed_ms = int((time.time() - start_time) * 1000)
            eta_ms = calculate_eta(len(unique_ticker_dates), idx + 1, elapsed_ms)
            eta = format_eta_ms(eta_ms)

            logger.info(
                f"Processed {idx + 1}/{len(unique_ticker_dates)} unique pairs",
                extra={
                    'endpoint': 'POST /generatePriceTrends',
                    'phase': 'process_price_trends',
                    'elapsed_ms': elapsed_ms,
                    'counters': {
                        'processed': idx + 1,
                        'total': len(unique_ticker_dates),
                        'success': success_count,
                        'fail': fail_count
                    },
                    'progress': {
                        'done': idx + 1,
                        'total': len(unique_ticker_dates),
                        'pct': round((idx + 1) / len(unique_ticker_dates) * 100, 1)
                    },
                    'eta': eta,
                    'rate': {},
                    'batch': {},
                    'warn': []
                }
            )

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
        result = engine.calculate_all(filtered_cache, ['valuation'])

        logger.debug(f"[PERF-OPT] Successfully fetched and calculated metrics for peer {peer_ticker}")

        return {
            'ticker': peer_ticker,
            'api_cache': peer_api_cache,
            'filtered_cache': filtered_cache,
            'calculated_metrics': result
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


async def calculate_sector_average_from_cache(
    peer_tickers: List[str],
    global_peer_cache: Dict[str, Dict[str, Any]],
    target_metrics: List[str] = ['PER', 'PBR']
) -> Dict[str, float]:
    """
    캐시된 peer data로 sector average를 계산합니다.

    Args:
        peer_tickers: Peer ticker list for this ticker
        global_peer_cache: Global peer financial data cache
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
                result = engine.calculate_all(filtered_cache, ['valuation'])
                
                # 타겟 메트릭 수집
                if 'valuation' in result:
                    valuation = result['valuation']
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


def calculate_fair_value_from_sector(
    value_quantitative: Dict[str, Any],
    sector_averages: Dict[str, float],
    current_price: float
) -> Optional[float]:
    """
    업종 평균 PER을 기반으로 적정가를 계산합니다.
    
    적정가 = (업종 평균 PER) × EPS
    EPS = 현재 주가 / 현재 PER
    
    Args:
        value_quantitative: Quantitative 메트릭 결과
        sector_averages: 업종 평균 {'PER': 25.5, 'PBR': 3.2}
        current_price: 현재 주가 (price_when_posted)
    
    Returns:
        적정가 또는 None
    """
    if not value_quantitative or not sector_averages or not current_price:
        return None
    
    try:
        valuation = value_quantitative.get('valuation', {})
        if isinstance(valuation, dict) and '_meta' in valuation:
            # _meta 제외한 실제 값 추출
            valuation = {k: v for k, v in valuation.items() if k != '_meta'}
        
        current_per = valuation.get('PER')
        sector_avg_per = sector_averages.get('PER')

        # CRITICAL: Only use positive PER values (negative PER = loss-making company)
        if current_per and sector_avg_per and current_per > 0 and sector_avg_per > 0:
            # EPS = 현재 주가 / 현재 PER
            eps = current_price / current_per
            # 적정가 = 업종 평균 PER × EPS
            fair_value = sector_avg_per * eps

            logger.debug(
                f"[I-36] Fair value calculation: "
                f"current_price={current_price:.2f}, current_PER={current_per:.2f}, "
                f"sector_avg_PER={sector_avg_per:.2f}, EPS={eps:.4f}, fair_value={fair_value:.2f}"
            )
            return fair_value

        # PER이 음수이거나 없으면 PBR로 시도
        current_pbr = valuation.get('PBR')
        sector_avg_pbr = sector_averages.get('PBR')

        # CRITICAL: Only use positive PBR values
        if current_pbr and sector_avg_pbr and current_pbr > 0 and sector_avg_pbr > 0:
            # BPS = 현재 주가 / 현재 PBR
            bps = current_price / current_pbr
            # 적정가 = 업종 평균 PBR × BPS
            fair_value = sector_avg_pbr * bps

            logger.debug(
                f"[I-36] Fair value calculation (PBR): "
                f"current_price={current_price:.2f}, current_PBR={current_pbr:.2f}, "
                f"sector_avg_PBR={sector_avg_pbr:.2f}, BPS={bps:.4f}, fair_value={fair_value:.2f}"
            )
            return fair_value
        
        return None
        
    except Exception as e:
        logger.error(f"[I-36] Failed to calculate fair value: {e}")
        return None


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
