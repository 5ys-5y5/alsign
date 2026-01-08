"""Service for POST /getQuantitatives endpoint - collects quantitative data for tickers."""

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from ..database.connection import db_pool
from ..database.queries import quantitatives
from .external_api import FMPAPIClient
from .utils.datetime_utils import parse_to_utc
from .utils.batch_utils import calculate_eta, format_progress, format_eta_ms
from .utils.freshness_utils import should_fetch_api

logger = logging.getLogger("alsign")

API_COLUMN_MAP = {
    "fmp-ratios": "financial_ratios",
    "fmp-key-metrics": "key_metrics",
    "fmp-cash-flow-statement": "cash_flow_statement",
    "fmp-balance-sheet-statement": "balance_sheet_statement",
    "fmp-historical-market-capitalization": "historical_market_cap",
    "fmp-historical-price-eod-full": "historical_price",
    "fmp-income-statement": "income_statement",
    "fmp-quote": "quote",
}

# API aliases for user-friendly parameter names
API_ALIASES = {
    "ratios": "fmp-ratios",
    "key-metrics": "fmp-key-metrics",
    "cash-flow": "fmp-cash-flow-statement",
    "balance-sheet": "fmp-balance-sheet-statement",
    "market-cap": "fmp-historical-market-capitalization",
    "price": "fmp-historical-price-eod-full",
    "income": "fmp-income-statement",
    "quote": "fmp-quote",
}

# API_CONCURRENCY will be calculated dynamically based on usagePerMin from database


def _parse_peer_value(peer_value: Any) -> List[str]:
    if not peer_value:
        return []
    if isinstance(peer_value, list):
        return [str(item).strip().upper() for item in peer_value if str(item).strip()]
    if isinstance(peer_value, dict):
        peers = peer_value.get("peers") or peer_value.get("tickers") or peer_value.get("symbols")
        if isinstance(peers, list):
            return [str(item).strip().upper() for item in peers if str(item).strip()]
        if isinstance(peers, str):
            return [item.strip().upper() for item in peers.split(",") if item.strip()]
        return []
    if isinstance(peer_value, str):
        stripped = peer_value.strip()
        if not stripped:
            return []
        if stripped.startswith("[") or stripped.startswith("{"):
            try:
                import json

                parsed = json.loads(stripped)
                return _parse_peer_value(parsed)
            except Exception:
                return [item.strip().upper() for item in stripped.split(",") if item.strip()]
        return [item.strip().upper() for item in stripped.split(",") if item.strip()]
    return []


def _extract_records(data: Any) -> List[Dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        historical = data.get("historical")
        if isinstance(historical, list):
            return [item for item in historical if isinstance(item, dict)]
        return [data]
    return []


def _find_date_candidates(record: Dict[str, Any]) -> List[str]:
    candidates = []
    for key, value in record.items():
        if value is None:
            continue
        if key == "calendarYear" and isinstance(value, str):
            candidates.append(f"{value}-01-01")
        elif key == "date" and isinstance(value, str):
            candidates.append(value)
        elif isinstance(value, str) and (key.lower().endswith("date") or "date" in key.lower()):
            candidates.append(value)
    return candidates


def _extract_min_max_dates(data: Any) -> Tuple[Optional[str], Optional[str]]:
    records = _extract_records(data)
    parsed_dates: List[datetime] = []
    for record in records:
        candidates = _find_date_candidates(record)
        for candidate in candidates:
            try:
                parsed_dates.append(parse_to_utc(candidate))
                break
            except Exception:
                continue
    if not parsed_dates:
        return None, None
    min_date = min(parsed_dates).isoformat()
    max_date = max(parsed_dates).isoformat()
    return min_date, max_date


def _should_update_status(existing_status: Dict[str, Any], api_id: str, new_max_date: Optional[str]) -> bool:
    if not new_max_date:
        return False
    entry = existing_status.get(api_id)
    if not entry or not isinstance(entry, dict):
        return True
    existing_max = entry.get("maxDate")
    if not existing_max:
        return True
    try:
        return parse_to_utc(new_max_date) > parse_to_utc(existing_max)
    except Exception:
        return True


async def _process_ticker(
    fmp_client: FMPAPIClient,
    ticker: str,
    pool,
    overwrite: bool = False,
    selected_apis: Optional[List[str]] = None,
) -> Dict[str, Any]:
    existing_row = await quantitatives.get_quantitatives_by_ticker(pool, ticker)
    existing_status = existing_row.get("status") if existing_row else None

    # Parse status if it's a JSON string
    if isinstance(existing_status, str):
        try:
            import json
            existing_status = json.loads(existing_status)
        except Exception as e:
            logger.warning(f"[{ticker}] Failed to parse status JSON: {e}")
            existing_status = {}
    elif not isinstance(existing_status, dict):
        existing_status = {}

    updated_columns: List[str] = []
    skipped_columns: List[str] = []
    status_updates = dict(existing_status)
    column_values: Dict[str, Any] = {}

    # Process APIs SEQUENTIALLY for this ticker to minimize DB connections
    for api_id, column in API_COLUMN_MAP.items():
        # Skip if not in selected APIs (when specified)
        if selected_apis is not None and api_id not in selected_apis:
            # Keep existing data
            if existing_row and existing_row.get(column) is not None:
                column_values[column] = existing_row.get(column)
            continue

        # Check data freshness before making API call
        has_data = existing_row and existing_row.get(column) is not None
        should_fetch, reason = await should_fetch_api(
            api_id,
            existing_status,
            has_data,
            overwrite,
            pool
        )

        if not should_fetch:
            # Skip API call - data is fresh
            logger.info(
                f"[{ticker}] Skipping {api_id}: {reason}",
                extra={
                    'endpoint': 'POST /getQuantitatives',
                    'phase': 'freshness-check',
                    'counters': {'skipped': 1}
                }
            )
            column_values[column] = existing_row.get(column) if existing_row else None
            skipped_columns.append(column)
            continue

        # Fetch data from API
        logger.info(
            f"[{ticker}] Fetching {api_id}: {reason}",
            extra={
                'endpoint': 'POST /getQuantitatives',
                'phase': 'fetch-api',
                'counters': {'fetch': 1}
            }
        )
        api_data = await fmp_client.call_api(api_id, {"ticker": ticker})
        min_date, max_date = _extract_min_max_dates(api_data)

        column_values[column] = api_data
        updated_columns.append(column)

        # Always update status when API is called, even if dates can't be extracted
        if min_date or max_date:
            status_updates[api_id] = {"minDate": min_date, "maxDate": max_date}
        else:
            # If no dates found, use current timestamp to mark data as fetched
            from datetime import datetime, timezone
            current_time = datetime.now(timezone.utc).isoformat()
            status_updates[api_id] = {"minDate": current_time, "maxDate": current_time}

    record = {
        "ticker": ticker,
        "status": status_updates,
        "income_statement": column_values.get("income_statement") or (existing_row or {}).get("income_statement"),
        "balance_sheet_statement": column_values.get("balance_sheet_statement") or (existing_row or {}).get("balance_sheet_statement"),
        "cash_flow_statement": column_values.get("cash_flow_statement") or (existing_row or {}).get("cash_flow_statement"),
        "key_metrics": column_values.get("key_metrics") or (existing_row or {}).get("key_metrics"),
        "financial_ratios": column_values.get("financial_ratios") or (existing_row or {}).get("financial_ratios"),
        "quote": column_values.get("quote") or (existing_row or {}).get("quote"),
        "historical_price": column_values.get("historical_price") or (existing_row or {}).get("historical_price"),
        "historical_market_cap": column_values.get("historical_market_cap") or (existing_row or {}).get("historical_market_cap"),
    }

    await quantitatives.upsert_quantitatives(pool, record)

    # Determine status: if all APIs were skipped (no updates), mark as skipped
    result_status = "skipped" if not updated_columns and skipped_columns else "success"

    return {
        "ticker": ticker,
        "status": result_status,
        "updatedColumns": updated_columns,
        "skippedColumns": skipped_columns,
    }


async def _analyze_all_tickers_freshness_batch(
    tickers: List[str],
    pool,
    overwrite: bool,
    selected_apis: Optional[List[str]]
) -> List[Dict[str, Any]]:
    """
    Analyze freshness for ALL tickers in a single batch operation.

    This is MUCH faster than individual ticker analysis:
    - 1 DB query instead of N queries (N can be 6000+)
    - Date calculations done once, not N times
    - All processing in memory

    Returns:
        List of analysis results, one per ticker
    """
    from datetime import date, timedelta, datetime
    from .utils.datetime_utils import parse_to_utc
    import calendar
    import json
    import time

    step_start = time.time()

    # ===== Step 1: Fetch metadata only (status + NULL checks) =====
    logger.info(
        f"[Batch Freshness] Step 1: Fetching metadata for {len(tickers)} tickers from DB...",
        extra={
            'endpoint': 'POST /getQuantitatives',
            'phase': 'batch-fetch-start',
            'counters': {'tickers': len(tickers)}
        }
    )

    logger.info(
        f"[Batch Freshness] Step 1a: Acquiring connection and preparing query...",
        extra={
            'endpoint': 'POST /getQuantitatives',
            'phase': 'batch-fetch-connection'
        }
    )

    async with pool.acquire() as conn:
        # Only fetch status and check if JSONB columns are NULL (not the actual data!)
        # This is MUCH faster than fetching all JSONB data
        query = """
            SELECT ticker,
                   status,
                   (income_statement IS NOT NULL) as has_income_statement,
                   (balance_sheet_statement IS NOT NULL) as has_balance_sheet,
                   (cash_flow_statement IS NOT NULL) as has_cash_flow,
                   (key_metrics IS NOT NULL) as has_key_metrics,
                   (financial_ratios IS NOT NULL) as has_financial_ratios,
                   (quote IS NOT NULL) as has_quote,
                   (historical_price IS NOT NULL) as has_historical_price,
                   (historical_market_cap IS NOT NULL) as has_historical_market_cap
            FROM config_lv3_quantitatives
            WHERE ticker = ANY($1::text[])
        """

        logger.info(
            f"[Batch Freshness] Step 1b: Executing query for {len(tickers)} tickers...",
            extra={
                'endpoint': 'POST /getQuantitatives',
                'phase': 'batch-fetch-executing'
            }
        )

        rows = await conn.fetch(query, tickers)

        logger.info(
            f"[Batch Freshness] Step 1c: Query returned {len(rows)} rows, building lookup dict...",
            extra={
                'endpoint': 'POST /getQuantitatives',
                'phase': 'batch-fetch-returned',
                'counters': {'rows': len(rows)}
            }
        )

    step1_elapsed = int((time.time() - step_start) * 1000)
    logger.info(
        f"[Batch Freshness] Step 1 complete: Fetched {len(rows)} existing rows ({step1_elapsed}ms)",
        extra={
            'endpoint': 'POST /getQuantitatives',
            'phase': 'batch-fetch-complete',
            'elapsed_ms': step1_elapsed,
            'counters': {'existing_rows': len(rows)}
        }
    )

    # Build lookup dict: O(1) access per ticker
    existing_data = {row['ticker']: dict(row) for row in rows}

    # ===== Step 2: Pre-calculate dates ONCE (not N times) =====
    step2_start = time.time()
    logger.info(
        "[Batch Freshness] Step 2: Pre-calculating date boundaries...",
        extra={
            'endpoint': 'POST /getQuantitatives',
            'phase': 'batch-date-calc-start'
        }
    )

    today = date.today()

    # Current quarter end date
    current_quarter = (today.month - 1) // 3 + 1
    quarter_end_month = current_quarter * 3
    _, last_day = calendar.monthrange(today.year, quarter_end_month)
    current_quarter_end = date(today.year, quarter_end_month, last_day)

    # 2 quarters ago end date (more lenient than "current quarter")
    two_quarters_ago_month = quarter_end_month - 6
    two_quarters_ago_year = today.year
    if two_quarters_ago_month <= 0:
        two_quarters_ago_month += 12
        two_quarters_ago_year -= 1
    _, last_day_2q = calendar.monthrange(two_quarters_ago_year, two_quarters_ago_month)
    two_quarters_ago_end = date(two_quarters_ago_year, two_quarters_ago_month, last_day_2q)

    # Last 2 trading days (for daily API freshness check)
    # Pre-fetch holidays to determine trading days
    logger.info(
        "[Batch Freshness] Step 2a: Fetching NASDAQ holidays for trading day calculation...",
        extra={
            'endpoint': 'POST /getQuantitatives',
            'phase': 'batch-holidays-fetch-start'
        }
    )

    async with pool.acquire() as conn:
        holidays_query = """
            SELECT DISTINCT date::date as holiday_date
            FROM config_lv3_market_holidays
            WHERE exchange = 'NASDAQ'
              AND is_fully_closed = true
              AND date::date <= $1
              AND date::date >= $2
        """
        holiday_rows = await conn.fetch(
            holidays_query,
            today,
            today - timedelta(days=10)
        )

    holidays = {row['holiday_date'] for row in holiday_rows}

    logger.info(
        f"[Batch Freshness] Step 2a complete: Loaded {len(holidays)} NASDAQ holidays",
        extra={
            'endpoint': 'POST /getQuantitatives',
            'phase': 'batch-holidays-fetch-complete',
            'counters': {'holidays': len(holidays)}
        }
    )

    # Find last 2 trading days
    last_2_trading_days = []
    check_date = today
    days_back = 0
    while len(last_2_trading_days) < 2 and days_back < 10:
        # Weekend check
        is_weekend = check_date.weekday() >= 5  # Saturday=5, Sunday=6
        if not is_weekend and check_date not in holidays:
            last_2_trading_days.append(check_date)
        check_date -= timedelta(days=1)
        days_back += 1

    second_last_trading_day = last_2_trading_days[1] if len(last_2_trading_days) >= 2 else today - timedelta(days=3)

    step2_elapsed = int((time.time() - step2_start) * 1000)
    logger.info(
        f"[Batch Freshness] Step 2 complete: Date boundaries calculated ({step2_elapsed}ms): "
        f"currentQuarterEnd={current_quarter_end}, "
        f"twoQuartersAgoEnd={two_quarters_ago_end}, "
        f"secondLastTradingDay={second_last_trading_day}",
        extra={
            'endpoint': 'POST /getQuantitatives',
            'phase': 'batch-date-calc-complete',
            'elapsed_ms': step2_elapsed
        }
    )

    # ===== Step 3: Process all tickers in memory (NO DB queries) =====
    step3_start = time.time()
    logger.info(
        f"[Batch Freshness] Step 3: Processing {len(tickers)} tickers in memory (no DB calls)...",
        extra={
            'endpoint': 'POST /getQuantitatives',
            'phase': 'batch-process-start',
            'counters': {'total_tickers': len(tickers)}
        }
    )

    results = []
    progress_interval = 1000  # Log every 1000 tickers

    # Column name to has_* field mapping (define once, use for all tickers)
    column_to_has_field = {
        'income_statement': 'has_income_statement',
        'balance_sheet_statement': 'has_balance_sheet',
        'cash_flow_statement': 'has_cash_flow',
        'key_metrics': 'has_key_metrics',
        'financial_ratios': 'has_financial_ratios',
        'quote': 'has_quote',
        'historical_price': 'has_historical_price',
        'historical_market_cap': 'has_historical_market_cap'
    }

    for idx, ticker in enumerate(tickers, start=1):
        existing_row = existing_data.get(ticker)

        # New ticker - no data in DB
        if not existing_row:
            apis_to_fetch = list(API_COLUMN_MAP.keys()) if selected_apis is None else selected_apis
            results.append({
                'ticker': ticker,
                'status': 'new',
                'apis_to_fetch': apis_to_fetch,
                'apis_to_skip': [],
                'existing_row': None,
                'reason': f"New ticker: {len(apis_to_fetch)} APIs to fetch"
            })
            continue

        # Parse status JSON
        existing_status = existing_row.get('status')
        if isinstance(existing_status, str):
            try:
                existing_status = json.loads(existing_status)
            except:
                existing_status = {}
        elif not isinstance(existing_status, dict):
            existing_status = {}

        # Check each API's freshness (in-memory calculation)
        apis_to_fetch = []
        apis_to_skip = []

        for api_id, column in API_COLUMN_MAP.items():
            if selected_apis is not None and api_id not in selected_apis:
                continue

            # Use has_* boolean field instead of checking JSONB data
            has_field = column_to_has_field.get(column, f'has_{column}')
            has_data = existing_row.get(has_field, False)

            # Inline freshness check (no DB calls, no async)
            should_fetch = False
            fetch_reason = ""

            if overwrite:
                should_fetch = True
                fetch_reason = "overwrite=True"
            elif not has_data:
                should_fetch = True
                fetch_reason = "no_data"
            else:
                status_entry = existing_status.get(api_id, {})
                max_date_str = status_entry.get("maxDate") if isinstance(status_entry, dict) else None

                if not max_date_str:
                    should_fetch = True
                    fetch_reason = "no_status_metadata"
                else:
                    try:
                        max_date = parse_to_utc(max_date_str).date()

                        # Quarterly APIs: fresh if maxDate >= 2 quarters ago
                        if api_id in {
                            "fmp-income-statement",
                            "fmp-balance-sheet-statement",
                            "fmp-cash-flow-statement",
                            "fmp-key-metrics",
                            "fmp-ratios"
                        }:
                            is_fresh = max_date >= two_quarters_ago_end
                            should_fetch = not is_fresh
                            if should_fetch:
                                fetch_reason = f"quarterly_stale (maxDate={max_date}, need>={two_quarters_ago_end})"
                            else:
                                fetch_reason = f"quarterly_fresh (maxDate={max_date})"

                        # Daily APIs: fresh if maxDate >= 2nd last trading day
                        elif api_id in {
                            "fmp-historical-price-eod-full",
                            "fmp-historical-market-capitalization"
                        }:
                            is_fresh = max_date >= second_last_trading_day
                            should_fetch = not is_fresh
                            if should_fetch:
                                fetch_reason = f"daily_stale (maxDate={max_date}, need>={second_last_trading_day})"
                            else:
                                fetch_reason = f"daily_fresh (maxDate={max_date})"

                        # Realtime APIs: fresh if updated today
                        elif api_id == "fmp-quote":
                            is_fresh = max_date >= today
                            should_fetch = not is_fresh
                            if should_fetch:
                                fetch_reason = f"realtime_stale (maxDate={max_date}, today={today})"
                            else:
                                fetch_reason = f"realtime_fresh (maxDate={max_date})"

                        else:
                            should_fetch = True  # Unknown API type, fetch to be safe
                            fetch_reason = "unknown_api_type"
                    except Exception as e:
                        should_fetch = True  # Parse error, fetch to be safe
                        fetch_reason = f"parse_error: {str(e)}"

            if should_fetch:
                apis_to_fetch.append(api_id)
            else:
                apis_to_skip.append(api_id)

        # Determine ticker status
        if not apis_to_fetch:
            status = 'skip'
            reason = f"All {len(apis_to_skip)} APIs are fresh"
        else:
            status = 'update'
            reason = f"{len(apis_to_fetch)} APIs to fetch, {len(apis_to_skip)} APIs fresh"

        results.append({
            'ticker': ticker,
            'status': status,
            'apis_to_fetch': apis_to_fetch,
            'apis_to_skip': apis_to_skip,
            'existing_row': existing_row,
            'reason': reason
        })

        # Debug log for first 10 tickers to verify freshness logic
        if idx <= 10:
            logger.info(
                f"[Batch Freshness DEBUG] Ticker {idx}/{len(tickers)} - {ticker}: "
                f"status={status}, fetch={len(apis_to_fetch)}, skip={len(apis_to_skip)}, reason={reason}"
            )

        # Log progress every 1000 tickers
        if idx % progress_interval == 0 or idx == len(tickers):
            elapsed = int((time.time() - step3_start) * 1000)
            tickers_per_sec = idx / (elapsed / 1000) if elapsed > 0 else 0
            eta_ms = int((len(tickers) - idx) / tickers_per_sec * 1000) if tickers_per_sec > 0 else 0

            logger.info(
                f"[Batch Freshness] Step 3 progress: {idx}/{len(tickers)} tickers "
                f"({idx*100//len(tickers)}%) - {tickers_per_sec:.1f} tickers/sec - ETA: {eta_ms}ms",
                extra={
                    'endpoint': 'POST /getQuantitatives',
                    'phase': 'batch-process-progress',
                    'elapsed_ms': elapsed,
                    'progress': {'current': idx, 'total': len(tickers), 'percent': idx*100//len(tickers)},
                    'rate': {'tickers_per_sec': tickers_per_sec},
                    'eta': eta_ms
                }
            )

    step3_elapsed = int((time.time() - step3_start) * 1000)
    logger.info(
        f"[Batch Freshness] Step 3 complete: Processed {len(tickers)} tickers in {step3_elapsed}ms",
        extra={
            'endpoint': 'POST /getQuantitatives',
            'phase': 'batch-process-complete',
            'elapsed_ms': step3_elapsed,
            'counters': {'processed': len(tickers)}
        }
    )

    return results


async def get_quantitatives(
    overwrite: bool = False,
    apis: Optional[List[str]] = None,
    tickers: Optional[List[str]] = None,
    max_workers: int = 20
) -> Dict[str, Any]:
    """
    Collect quantitative financial data for tickers.

    Args:
        overwrite: If True, refetch all APIs even if data exists. If False, skip existing data.
        apis: List of API aliases to fetch (e.g., ['ratios', 'key-metrics']). If None, fetch all.
        tickers: List of tickers to process (e.g., ['AAPL', 'MSFT']). Only tickers that exist in
                 config_lv3_targets (ticker or peer column) will be processed. If None, process all.
        max_workers: Maximum number of concurrent ticker workers. Lower values reduce DB CPU load.
                     Default: 20. Recommended: 10-30 depending on DB capacity.

    Returns:
        Dict with summary and results
    """
    logger.info(
        f"[get_quantitatives] Starting: overwrite={overwrite}, apis={apis}, tickers={tickers}",
        extra={
            'endpoint': 'POST /getQuantitatives',
            'phase': 'start',
            'elapsed_ms': 0
        }
    )
    pool = await db_pool.get_pool()

    # ===== Phase 1: Load target tickers =====
    phase1_start = time.time()
    logger.info(
        "[Phase 1] Loading target tickers from config_lv3_targets...",
        extra={
            'endpoint': 'POST /getQuantitatives',
            'phase': 'load-targets',
            'elapsed_ms': 0
        }
    )
    target_rows = await quantitatives.fetch_target_tickers_with_peers(pool)
    logger.info(
        f"[Phase 1] Loaded {len(target_rows)} target rows",
        extra={
            'endpoint': 'POST /getQuantitatives',
            'phase': 'load-targets-complete',
            'elapsed_ms': int((time.time() - phase1_start) * 1000),
            'counters': {'target_rows': len(target_rows)}
        }
    )

    # Convert API aliases to full API IDs
    selected_apis = None
    if apis:
        selected_apis = []
        for api_alias in apis:
            # Try to find the full API ID
            full_api_id = API_ALIASES.get(api_alias, api_alias)
            if full_api_id in API_COLUMN_MAP:
                selected_apis.append(full_api_id)
            else:
                logger.warning(f"Unknown API alias or ID: {api_alias}")
        logger.info(f"[Phase 1] Selected APIs: {selected_apis}")

    # ===== Phase 2: Expand peers to unique tickers =====
    phase2_start = time.time()
    logger.info(
        "[Phase 2] Expanding peer tickers...",
        extra={
            'endpoint': 'POST /getQuantitatives',
            'phase': 'expand-peers',
            'elapsed_ms': 0
        }
    )
    all_valid_tickers = set()
    for row in target_rows:
        ticker = row.get("ticker")
        if ticker:
            all_valid_tickers.add(str(ticker).upper())
        for peer in _parse_peer_value(row.get("peer")):
            all_valid_tickers.add(peer)

    phase2_elapsed = int((time.time() - phase2_start) * 1000)
    logger.info(
        f"[Phase 2] Expanded to {len(all_valid_tickers)} unique tickers ({phase2_elapsed}ms)",
        extra={
            'endpoint': 'POST /getQuantitatives',
            'phase': 'expand-peers-complete',
            'elapsed_ms': phase2_elapsed,
            'counters': {'unique_tickers': len(all_valid_tickers)}
        }
    )

    # Filter tickers based on user input
    if tickers:
        # User specified tickers - filter and validate
        requested_tickers = set(ticker.upper() for ticker in tickers)
        valid_tickers = requested_tickers & all_valid_tickers
        invalid_tickers = requested_tickers - all_valid_tickers

        if invalid_tickers:
            logger.warning(
                f"[get_quantitatives] Skipping {len(invalid_tickers)} invalid tickers (not in config_lv3_targets): {sorted(invalid_tickers)}"
            )

        if not valid_tickers:
            logger.warning("[get_quantitatives] No valid tickers to process after filtering")
            return {
                "summary": {
                    "totalTickers": 0,
                    "success": 0,
                    "fail": 0,
                    "skipped": 0,
                    "invalidTickers": len(invalid_tickers),
                },
                "results": [],
                "invalidTickers": sorted(invalid_tickers),
            }

        tickers_to_process = valid_tickers
        logger.info(f"[get_quantitatives] Processing {len(tickers_to_process)} valid tickers from user input")
    else:
        # No tickers specified - process all
        tickers_to_process = all_valid_tickers
        logger.info(f"[get_quantitatives] Processing all {len(tickers_to_process)} tickers from config_lv3_targets")

    if not tickers_to_process:
        return {
            "summary": {
                "totalTickers": 0,
                "success": 0,
                "fail": 0,
                "skipped": 0,
            },
            "results": [],
        }

    # ===== Phase 3: Pre-analyze freshness for all tickers =====
    phase3_start = time.time()
    logger.info(
        f"[Phase 3] Analyzing freshness for {len(tickers_to_process)} tickers in batch mode...",
        extra={
            'endpoint': 'POST /getQuantitatives',
            'phase': 'freshness-analysis-start',
            'elapsed_ms': 0,
            'counters': {'total_tickers': len(tickers_to_process)}
        }
    )

    # Batch analyze all tickers in a single DB operation (1 query instead of N queries)
    analysis_results = await _analyze_all_tickers_freshness_batch(
        list(tickers_to_process), pool, overwrite, selected_apis
    )

    # Categorize tickers by status
    new_tickers = [r for r in analysis_results if r['status'] == 'new']
    update_tickers = [r for r in analysis_results if r['status'] == 'update']
    skip_tickers = [r for r in analysis_results if r['status'] == 'skip']

    phase3_elapsed = int((time.time() - phase3_start) * 1000)
    logger.info(
        f"[Phase 3] Analysis complete ({phase3_elapsed}ms): "
        f"new={len(new_tickers)}, update={len(update_tickers)}, skip={len(skip_tickers)}",
        extra={
            'endpoint': 'POST /getQuantitatives',
            'phase': 'freshness-analysis',
            'elapsed_ms': phase3_elapsed,
            'counters': {
                'new': len(new_tickers),
                'update': len(update_tickers),
                'skip': len(skip_tickers)
            }
        }
    )

    # Log skipped tickers
    for skip_info in skip_tickers:
        logger.info(
            f"[{skip_info['ticker']}] Skipping: {skip_info['reason']}",
            extra={
                'endpoint': 'POST /getQuantitatives',
                'phase': 'skip-fresh-ticker',
                'counters': {'skipped': 1}
            }
        )

    # ===== Phase 4: Process work targets (new + update) =====
    work_targets = new_tickers + update_tickers
    logger.info(
        f"[Phase 4] Processing {len(work_targets)} tickers "
        f"(new: {len(new_tickers)}, update: {len(update_tickers)})",
        extra={
            'endpoint': 'POST /getQuantitatives',
            'phase': 'api-processing-start',
            'elapsed_ms': 0,
            'counters': {
                'work_targets': len(work_targets),
                'new': len(new_tickers),
                'update': len(update_tickers)
            }
        }
    )

    results: List[Dict[str, Any]] = []
    success_count = 0
    fail_count = 0
    skipped_count = len(skip_tickers)  # Pre-count skipped tickers

    # Add skip results
    for skip_info in skip_tickers:
        results.append({
            "ticker": skip_info['ticker'],
            "status": "skipped",
            "updatedColumns": [],
            "skippedColumns": list(API_COLUMN_MAP.values()) if selected_apis is None else [
                API_COLUMN_MAP[api_id] for api_id in selected_apis if api_id in API_COLUMN_MAP
            ],
            "reason": skip_info['reason']
        })

    # Progress tracking
    completed_tickers = 0
    start_time = time.time()

    if not work_targets:
        # All tickers skipped - return early
        logger.info("[Phase 4] All tickers have fresh data, no API calls needed")
        return {
            "summary": {
                "totalTickers": len(tickers_to_process),
                "success": 0,
                "fail": 0,
                "skipped": skipped_count,
            },
            "results": results,
        }

    async with FMPAPIClient() as fmp_client:
        # CRITICAL: Balance between API rate limit and DB capacity
        # - API: RateLimiter controls 700/min (no problem)
        # - DB: JSONB upserts are CPU-intensive → limit concurrent workers
        #
        # max_workers parameter allows runtime tuning based on DB CPU monitoring
        # - Lower values (10-15): Reduce DB CPU load when DB is struggling
        # - Higher values (25-30): Increase throughput when DB has spare capacity
        max_concurrent = max_workers

        usage_per_min = fmp_client._usage_per_min_cache or 300
        logger.info(
            f"[get_quantitatives] Max concurrent ticker workers: {max_concurrent} (user-configured). "
            f"API rate limit: {usage_per_min}/min (RateLimiter controlled)."
        )

        semaphore = asyncio.Semaphore(max_concurrent)
        async def worker(ticker: str):
            nonlocal success_count, fail_count, completed_tickers
            async with semaphore:
                try:
                    result = await _process_ticker(
                        fmp_client,
                        ticker,
                        pool,
                        overwrite=overwrite,
                        selected_apis=selected_apis
                    )
                    results.append(result)
                    if result["status"] == "success":
                        success_count += 1
                    elif result["status"] == "skipped":
                        # Note: Individual API skips within a ticker are not counted as ticker-level skip
                        # Ticker-level skips (all APIs fresh) were already counted in Phase 3
                        success_count += 1
                    else:
                        fail_count += 1
                except Exception as exc:
                    logger.error(f"[get_quantitatives] Failed for {ticker}: {exc}", exc_info=True)
                    results.append(
                        {
                            "ticker": ticker,
                            "status": "failed",
                            "updatedColumns": [],
                            "error": str(exc),
                        }
                    )
                    fail_count += 1
                finally:
                    completed_tickers += 1

                    # Log progress every 10 tickers or at completion
                    if completed_tickers % 10 == 0 or completed_tickers == len(work_targets):
                        elapsed_ms = int((time.time() - start_time) * 1000)
                        eta_ms = calculate_eta(len(work_targets), completed_tickers, elapsed_ms)
                        eta = format_eta_ms(eta_ms)

                        logger.info(
                            f"Processed {completed_tickers}/{len(work_targets)} work tickers "
                            f"({skipped_count} pre-skipped)",
                            extra={
                                'endpoint': 'POST /getQuantitatives',
                                'phase': 'ticker-processing',
                                'elapsed_ms': elapsed_ms,
                                'progress': format_progress(completed_tickers, len(work_targets)),
                                'eta': eta,
                                'counters': {
                                    'success': success_count,
                                    'fail': fail_count,
                                    'skipped': skipped_count
                                }
                            }
                        )

        # Process only work targets (new + update tickers)
        await asyncio.gather(*[worker(target_info['ticker']) for target_info in work_targets])

    return {
        "summary": {
            "totalTickers": len(tickers_to_process),
            "success": success_count,
            "fail": fail_count,
            "skipped": skipped_count,
        },
        "results": results,
    }
