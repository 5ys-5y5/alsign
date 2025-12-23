"""Service for POST /fillAnalyst endpoint - aggregates analyst performance metrics."""

import logging
import time
import json
from typing import Dict, Any, List, Optional

from ..database.connection import db_pool
from ..database.queries import analyst, policies
from ..models.response_models import AnalystGroupResult

logger = logging.getLogger("alsign")


async def aggregate_analyst_performance() -> Dict[str, Any]:
    """
    Aggregate analyst performance metrics from consensus events.

    Groups events by (analyst_name, analyst_company), calculates return
    distributions per dayOffset, and upserts to config_lv3_analyst.

    Returns:
        Dict with summary and per-group results
    """
    start_time = time.time()

    pool = await db_pool.get_pool()

    # Phase 1: Load policy configuration
    logger.info(
        "Loading price trend policy",
        extra={
            'endpoint': 'POST /fillAnalyst',
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
            'summary': {
                'totalEventsLoaded': 0,
                'eventsSkippedBothNullAnalyst': 0,
                'totalGroups': 0,
                'groupsSuccess': 0,
                'groupsFailed': 1,
                'elapsedMs': int((time.time() - start_time) * 1000)
            },
            'groups': [],
            'error': str(e),
            'errorCode': 'POLICY_NOT_FOUND'
        }

    # Phase 2: Load consensus events
    logger.info(
        "Loading consensus events",
        extra={
            'endpoint': 'POST /fillAnalyst',
            'phase': 'load_events',
            'elapsed_ms': int((time.time() - start_time) * 1000),
            'counters': {},
            'progress': {},
            'rate': {},
            'batch': {},
            'warn': []
        }
    )

    events = await analyst.select_consensus_events(pool)

    # Count skipped events (both analyst_name and analyst_company are NULL)
    # This should be 0 based on our query filter, but keeping for completeness
    events_skipped_both_null = 0

    logger.info(
        f"Loaded {len(events)} consensus events",
        extra={
            'endpoint': 'POST /fillAnalyst',
            'phase': 'load_events',
            'elapsed_ms': int((time.time() - start_time) * 1000),
            'counters': {'total': len(events), 'skipped': events_skipped_both_null},
            'progress': {},
            'rate': {},
            'batch': {},
            'warn': []
        }
    )

    # Phase 3: Group by analyst
    logger.info(
        "Grouping events by analyst",
        extra={
            'endpoint': 'POST /fillAnalyst',
            'phase': 'group_analysts',
            'elapsed_ms': int((time.time() - start_time) * 1000),
            'counters': {},
            'progress': {},
            'rate': {},
            'batch': {},
            'warn': []
        }
    )

    groups_dict = await analyst.get_analyst_groups(events)

    logger.info(
        f"Created {len(groups_dict)} analyst groups",
        extra={
            'endpoint': 'POST /fillAnalyst',
            'phase': 'group_analysts',
            'elapsed_ms': int((time.time() - start_time) * 1000),
            'counters': {'groups': len(groups_dict)},
            'progress': {},
            'rate': {},
            'batch': {},
            'warn': []
        }
    )

    # Phase 4: Process each analyst group
    group_results = []
    groups_success = 0
    groups_failed = 0
    groups_skipped = 0

    for idx, ((analyst_name, analyst_company), group_events) in enumerate(groups_dict.items()):
        group_start = time.time()

        logger.info(
            f"Processing analyst group: {analyst_name or 'NULL'} / {analyst_company or 'NULL'}",
            extra={
                'endpoint': 'POST /fillAnalyst',
                'phase': 'process_group',
                'elapsed_ms': int((time.time() - group_start) * 1000),
                'counters': {'events': len(group_events)},
                'progress': {},
                'rate': {},
                'batch': {},
                'warn': []
            }
        )

        try:
            # Validate price_trend for all events
            valid_events = []
            for event in group_events:
                if validate_price_trend(event, count_start, count_end):
                    valid_events.append(event)
                else:
                    logger.warning(
                        f"Invalid price_trend range for event {event['ticker']} {event['event_date']}"
                    )

            if not valid_events:
                logger.warning(
                    f"No valid events for analyst {analyst_name or 'NULL'} / {analyst_company or 'NULL'}"
                )
                groups_skipped += 1
                group_results.append(AnalystGroupResult(
                    analyst_name=analyst_name,
                    analyst_company=analyst_company,
                    status='skipped',
                    eventsCount=0,
                    error='No events with valid price_trend',
                    errorCode='INVALID_PRICE_TREND_RANGE'
                ))
                continue

            # Calculate returns per dayOffset
            returns_by_offset = calculate_returns_by_offset(
                valid_events,
                count_start,
                count_end
            )

            # Calculate statistics per dayOffset
            performance = {}
            for dayoffset in range(count_start, count_end + 1):
                returns = returns_by_offset.get(dayoffset, [])
                stats = analyst.calculate_statistics(returns)
                performance[str(dayoffset)] = stats

            # Upsert to database
            upserted = await analyst.upsert_analyst_performance(
                pool,
                analyst_name,
                analyst_company,
                performance
            )

            if upserted > 0:
                groups_success += 1

                # Build performance summary for response
                performance_summary = {
                    'dayOffsets': list(range(count_start, count_end + 1)),
                    'meanReturns': {str(k): v['mean'] for k, v in performance.items() if v['mean'] is not None},
                    'medianReturns': {str(k): v['median'] for k, v in performance.items() if v['median'] is not None},
                    'sampleCounts': {str(k): v['count'] for k, v in performance.items()}
                }

                group_results.append(AnalystGroupResult(
                    analyst_name=analyst_name,
                    analyst_company=analyst_company,
                    status='success',
                    eventsCount=len(valid_events),
                    performanceSummary=performance_summary
                ))

                logger.info(
                    f"Successfully processed analyst {analyst_name or 'NULL'} / {analyst_company or 'NULL'}",
                    extra={
                        'endpoint': 'POST /fillAnalyst',
                        'phase': 'process_group',
                        'elapsed_ms': int((time.time() - group_start) * 1000),
                        'counters': {
                            'events': len(valid_events),
                            'upserted': upserted
                        },
                        'progress': {},
                        'rate': {},
                        'batch': {},
                        'warn': []
                    }
                )
            else:
                groups_failed += 1
                group_results.append(AnalystGroupResult(
                    analyst_name=analyst_name,
                    analyst_company=analyst_company,
                    status='failed',
                    eventsCount=len(valid_events),
                    error='Database upsert failed',
                    errorCode='INTERNAL_ERROR'
                ))

        except Exception as e:
            logger.error(
                f"Failed to process analyst {analyst_name or 'NULL'} / {analyst_company or 'NULL'}: {e}",
                extra={
                    'endpoint': 'POST /fillAnalyst',
                    'phase': 'process_group',
                    'elapsed_ms': int((time.time() - group_start) * 1000),
                    'counters': {},
                    'progress': {},
                    'rate': {},
                    'batch': {},
                    'warn': []
                },
                exc_info=True
            )

            groups_failed += 1
            group_results.append(AnalystGroupResult(
                analyst_name=analyst_name,
                analyst_company=analyst_company,
                status='failed',
                eventsCount=len(group_events),
                error=str(e),
                errorCode='INTERNAL_ERROR'
            ))

        # Log progress every 10 groups
        if (idx + 1) % 10 == 0:
            logger.info(
                f"Processed {idx + 1}/{len(groups_dict)} analyst groups",
                extra={
                    'endpoint': 'POST /fillAnalyst',
                    'phase': 'process_groups',
                    'elapsed_ms': int((time.time() - start_time) * 1000),
                    'counters': {
                        'processed': idx + 1,
                        'total': len(groups_dict),
                        'success': groups_success,
                        'failed': groups_failed
                    },
                    'progress': {
                        'done': idx + 1,
                        'total': len(groups_dict),
                        'pct': round((idx + 1) / len(groups_dict) * 100, 1)
                    },
                    'rate': {},
                    'batch': {},
                    'warn': []
                }
            )

    total_elapsed_ms = int((time.time() - start_time) * 1000)

    # Build summary
    summary = {
        'totalEventsLoaded': len(events),
        'eventsSkippedBothNullAnalyst': events_skipped_both_null,
        'totalGroups': len(groups_dict),
        'groupsSuccess': groups_success,
        'groupsFailed': groups_failed,
        'groupsSkipped': groups_skipped,
        'elapsedMs': total_elapsed_ms
    }

    logger.info(
        "POST /fillAnalyst completed",
        extra={
            'endpoint': 'POST /fillAnalyst',
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
        'groups': group_results
    }


def validate_price_trend(
    event: Dict[str, Any],
    count_start: int,
    count_end: int
) -> bool:
    """
    Validate that price_trend array has all required dayOffsets.

    Args:
        event: Event dictionary with price_trend field
        count_start: Expected starting dayOffset
        count_end: Expected ending dayOffset

    Returns:
        True if valid, False otherwise
    """
    price_trend = event.get('price_trend')

    if not price_trend:
        return False

    # Parse price_trend if it's a string
    if isinstance(price_trend, str):
        try:
            price_trend = json.loads(price_trend)
        except json.JSONDecodeError:
            return False

    if not isinstance(price_trend, list):
        return False

    # Extract dayOffsets from price_trend
    dayoffsets = set()
    for entry in price_trend:
        if isinstance(entry, dict) and 'dayOffset' in entry:
            dayoffsets.add(entry['dayOffset'])

    # Check if all required dayOffsets are present
    expected_offsets = set(range(count_start, count_end + 1))

    return expected_offsets.issubset(dayoffsets)


def calculate_returns_by_offset(
    events: List[Dict[str, Any]],
    count_start: int,
    count_end: int
) -> Dict[int, List[float]]:
    """
    Calculate returns per dayOffset for a group of events.

    For each event:
    - basePrice = consensusSignal.last.price_when_posted (from value_qualitative)
    - For each dayOffset: close = price_trend[dayOffset].close
    - return = (close / basePrice) - 1

    Excludes samples where close=null or basePrice=null/0.

    Args:
        events: List of events with value_qualitative and price_trend
        count_start: Starting dayOffset
        count_end: Ending dayOffset

    Returns:
        Dict with dayOffset as key, list of returns as value
    """
    returns_by_offset = {}

    for dayoffset in range(count_start, count_end + 1):
        returns_by_offset[dayoffset] = []

    for event in events:
        # Extract base price from value_qualitative
        value_qualitative = event.get('value_qualitative')
        base_price = None

        if value_qualitative:
            # Parse if string
            if isinstance(value_qualitative, str):
                try:
                    value_qualitative = json.loads(value_qualitative)
                except json.JSONDecodeError:
                    value_qualitative = None

            if value_qualitative and isinstance(value_qualitative, dict):
                consensus_signal = value_qualitative.get('consensusSignal', {})
                last = consensus_signal.get('last', {})
                base_price = last.get('price_when_posted')

        # Fallback: try to get from direct column
        if base_price is None:
            base_price = event.get('price_when_posted')

        if base_price is None or base_price == 0:
            continue

        # Extract price_trend
        price_trend = event.get('price_trend')

        if isinstance(price_trend, str):
            try:
                price_trend = json.loads(price_trend)
            except json.JSONDecodeError:
                continue

        if not isinstance(price_trend, list):
            continue

        # Index price_trend by dayOffset
        price_by_offset = {}
        for entry in price_trend:
            if isinstance(entry, dict):
                offset = entry.get('dayOffset')
                close = entry.get('close')
                if offset is not None:
                    price_by_offset[offset] = close

        # Calculate returns for each dayOffset
        for dayoffset in range(count_start, count_end + 1):
            close_price = price_by_offset.get(dayoffset)

            if close_price is not None and close_price > 0:
                ret = (float(close_price) / float(base_price)) - 1
                returns_by_offset[dayoffset].append(ret)

    return returns_by_offset
