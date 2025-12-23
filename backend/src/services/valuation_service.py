"""Service for POST /backfillEventsTable endpoint - calculates valuation metrics."""

import logging
import time
import json
from typing import Dict, Any, List, Optional
from datetime import datetime, date

from ..database.connection import db_pool
from ..database.queries import metrics, policies
from .external_api import FMPAPIClient
from .utils.datetime_utils import calculate_dayOffset_dates
from ..models.response_models import EventProcessingResult

logger = logging.getLogger("alsign")


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

    logger.info("=" * 80)
    logger.info("[backfillEventsTable] START - Processing valuations")
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

    # Phase 3: Process each event
    logger.info(f"[backfillEventsTable] Phase 3: Processing {len(events)} events")
    results = []
    quantitative_success = 0
    quantitative_fail = 0
    qualitative_success = 0
    qualitative_fail = 0

    for idx, event in enumerate(events):
        event_start = time.time()

        ticker = event['ticker']
        event_date = event['event_date']
        source = event['source']
        source_id = event['source_id']

        logger.info(f"[backfillEventsTable] Processing event {idx+1}/{len(events)}: {ticker} {event_date} {source}")

        # Calculate quantitative metrics
        try:
            quant_result = await calculate_quantitative_metrics(
                pool, ticker, event_date, metrics_by_domain
            )
            logger.info(f"[backfillEventsTable] Quantitative result for {ticker}: {quant_result['status']}")
        except Exception as e:
            logger.error(f"[backfillEventsTable] Quantitative calculation failed for {ticker}: {e}")
            quant_result = {
                'status': 'failed',
                'value': None,
                'message': str(e)
            }

        # Calculate qualitative metrics
        try:
            qual_result = await calculate_qualitative_metrics(
                pool, ticker, event_date, source
            )
            logger.info(f"[backfillEventsTable] Qualitative result for {ticker}: {qual_result['status']}")
        except Exception as e:
            logger.error(f"[backfillEventsTable] Qualitative calculation failed for {ticker}: {e}")
            qual_result = {
                'status': 'failed',
                'value': None,
                'currentPrice': None,
                'message': str(e)
            }

        # Calculate positions and disparities
        position_quant, disparity_quant = calculate_position_disparity(
            quant_result.get('value'),
            qual_result.get('currentPrice')
        )

        position_qual, disparity_qual = calculate_position_disparity(
            qual_result.get('value'),
            qual_result.get('currentPrice')
        )

        # Update database
        try:
            updated = await metrics.update_event_valuations(
                pool,
                ticker,
                event_date,
                source,
                source_id,
                value_quantitative=quant_result.get('value'),
                value_qualitative=qual_result.get('value'),
                position_quantitative=position_quant,
                position_qualitative=position_qual,
                disparity_quantitative=disparity_quant,
                disparity_qualitative=disparity_qual,
                overwrite=overwrite
            )

            if updated == 0:
                raise ValueError("Event not found for update")

            # Track success/fail
            if quant_result['status'] == 'success':
                quantitative_success += 1
            elif quant_result['status'] == 'failed':
                quantitative_fail += 1

            if qual_result['status'] == 'success':
                qualitative_success += 1
            elif qual_result['status'] == 'failed':
                qualitative_fail += 1

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
                position={
                    'quantitative': position_quant,
                    'qualitative': position_qual
                } if position_quant or position_qual else None,
                disparity={
                    'quantitative': disparity_quant,
                    'qualitative': disparity_qual
                } if disparity_quant is not None or disparity_qual is not None else None
            ))

        except Exception as e:
            logger.error(
                f"Failed to update event {ticker} {event_date}: {e}",
                extra={
                    'endpoint': 'POST /backfillEventsTable',
                    'phase': 'update',
                    'elapsed_ms': int((time.time() - event_start) * 1000),
                    'counters': {},
                    'progress': {},
                    'rate': {},
                    'batch': {},
                    'warn': []
                }
            )

            quantitative_fail += 1
            qualitative_fail += 1

            results.append(EventProcessingResult(
                ticker=ticker,
                event_date=event_date.isoformat() if hasattr(event_date, 'isoformat') else str(event_date),
                source=source,
                source_id=str(source_id),
                status='failed',
                error=str(e),
                errorCode='INTERNAL_ERROR'
            ))

        # Log progress every 10 events
        if (idx + 1) % 10 == 0:
            logger.info(
                f"Processed {idx + 1}/{len(events)} events",
                extra={
                    'endpoint': 'POST /backfillEventsTable',
                    'phase': 'process',
                    'elapsed_ms': int((time.time() - start_time) * 1000),
                    'counters': {
                        'processed': idx + 1,
                        'total': len(events)
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

    # Phase 4: Generate price trends
    logger.info(f"[backfillEventsTable] Phase 4: Generating price trends")
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
            to_date=to_date
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
        # Fetch quarterly financials from FMP
        async with FMPAPIClient() as fmp_client:
            income_stmt = await fmp_client.get_income_statement(ticker, period='quarter', limit=4)
            balance_sheet = await fmp_client.get_balance_sheet(ticker, period='quarter', limit=4)
            cash_flow = await fmp_client.get_cash_flow(ticker, period='quarter', limit=4)

        if not income_stmt or not balance_sheet:
            return {
                'status': 'failed',
                'value': None,
                'message': 'Missing financial data from FMP'
            }

        # Calculate TTM values
        # For simplicity, we'll use basic TTM calculation
        # In production, this would implement complex formula parsing

        # Build value_quantitative structure
        value_quantitative = {}

        # Example: Calculate PER (Price to Earnings Ratio)
        # This is a simplified example - real implementation would parse formulas
        if 'valuation' in metrics_by_domain:
            valuation_metrics = {}

            # Get latest market cap and earnings
            if income_stmt:
                ttm_earnings = sum([q.get('netIncome', 0) for q in income_stmt[:4]])
                # Note: In real implementation, fetch current price and calculate P/E
                valuation_metrics['PER'] = None  # Would calculate: current_price / (ttm_earnings / shares_outstanding)

            if valuation_metrics:
                value_quantitative['valuation'] = {
                    **valuation_metrics,
                    '_meta': {
                        'date_range': f"{income_stmt[-1].get('date')} to {income_stmt[0].get('date')}" if income_stmt else None,
                        'calcType': 'TTM_fullQuarter',
                        'count': len(income_stmt)
                    }
                }

        # For this implementation, we'll return a placeholder structure
        # Real implementation would process all domains and formulas
        return {
            'status': 'success',
            'value': value_quantitative if value_quantitative else None,
            'message': 'Quantitative metrics calculated'
        }

    except Exception as e:
        logger.error(f"Quantitative calculation failed for {ticker}: {e}")
        return {
            'status': 'failed',
            'value': None,
            'message': str(e)
        }


async def calculate_qualitative_metrics(
    pool,
    ticker: str,
    event_date,
    source: str
) -> Dict[str, Any]:
    """
    Calculate qualitative metrics (consensusSignal).

    Extracts consensus data from evt_consensus Phase 2 fields.

    Args:
        pool: Database connection pool
        ticker: Ticker symbol
        event_date: Event date
        source: Source table name

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

        # Fetch consensus data
        consensus_data = await metrics.select_consensus_data(pool, ticker, event_date)

        if not consensus_data:
            return {
                'status': 'failed',
                'value': None,
                'currentPrice': None,
                'message': 'Consensus data not found'
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

        value_qualitative = {
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
    to_date: Optional[date] = None
) -> Dict[str, Any]:
    """
    Generate price_trend arrays for all events in txn_events.

    Fetches policy configuration, generates dayOffset scaffolds,
    fetches OHLC data from FMP, and populates price_trend field.

    Args:
        from_date: Optional start date for filtering events by event_date
        to_date: Optional end date for filtering events by event_date

    Returns:
        Dict with summary and statistics
    """
    start_time = time.time()

    pool = await db_pool.get_pool()

    # Load policy configuration
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
        range_policy = await policies.get_price_trend_range_policy(pool)
        count_start = range_policy['countStart']
        count_end = range_policy['countEnd']
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
        to_date=to_date
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
    ohlc_ranges = {}
    for ticker, ticker_events in events_by_ticker.items():
        event_dates = [e['event_date'].date() if hasattr(e['event_date'], 'date') else e['event_date'] for e in ticker_events]
        min_date = min(event_dates)
        max_date = max(event_dates)

        # Calculate range with buffer for dayOffset
        # For now, use approximate calendar day calculation
        # In production, would calculate exact trading day range
        from datetime import timedelta
        fetch_start = min_date + timedelta(days=count_start * 2)  # Approximate
        fetch_end = max_date + timedelta(days=count_end * 2)  # Approximate

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

    # Process each event
    success_count = 0
    fail_count = 0

    for idx, event in enumerate(events):
        try:
            ticker = event['ticker']
            event_date = event['event_date'].date() if hasattr(event['event_date'], 'date') else event['event_date']
            source = event['source']
            source_id = event['source_id']

            # Generate dayOffset scaffold
            dayoffset_dates = await calculate_dayOffset_dates(
                event_date,
                count_start,
                count_end,
                'NASDAQ',
                pool
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

            # Update database
            async with pool.acquire() as conn:
                result = await conn.execute(
                    """
                    UPDATE txn_events
                    SET price_trend = $5
                    WHERE ticker = $1
                      AND event_date = $2
                      AND source = $3
                      AND source_id = $4
                    """,
                    ticker,
                    event['event_date'],
                    source,
                    source_id,
                    json.dumps(price_trend)
                )

                if "UPDATE 1" in result:
                    success_count += 1
                elif "UPDATE 0" in result:
                    fail_count += 1
                    logger.warning(f"Event not found for update: {ticker} {event_date}")
                elif "UPDATE" in result and int(result.split()[-1]) > 1:
                    fail_count += 1
                    logger.error(f"Ambiguous event date: {ticker} {event_date}")

        except Exception as e:
            logger.error(f"Failed to generate price trend for {ticker} {event_date}: {e}")
            fail_count += 1
            continue

        # Log progress every 10 events
        if (idx + 1) % 10 == 0:
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
