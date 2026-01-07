"""Service for POST /getQuantatatives endpoint - collects quantitative data for tickers."""

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
    existing_row = await quantitatives.get_quantatatives_by_ticker(pool, ticker)
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
                    'endpoint': 'POST /getQuantatatives',
                    'phase': 'freshness-check',
                    'counters': {'skipped': 1}
                }
            )
            column_values[column] = existing_row.get(column)
            skipped_columns.append(column)
            continue

        # Fetch data from API
        logger.info(
            f"[{ticker}] Fetching {api_id}: {reason}",
            extra={
                'endpoint': 'POST /getQuantatatives',
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

    await quantitatives.upsert_quantatatives(pool, record)

    # Determine status: if all APIs were skipped (no updates), mark as skipped
    result_status = "skipped" if not updated_columns and skipped_columns else "success"

    return {
        "ticker": ticker,
        "status": result_status,
        "updatedColumns": updated_columns,
        "skippedColumns": skipped_columns,
    }


async def get_quantatatives(
    overwrite: bool = False,
    apis: Optional[List[str]] = None,
    tickers: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Collect quantitative financial data for tickers.

    Args:
        overwrite: If True, refetch all APIs even if data exists. If False, skip existing data.
        apis: List of API aliases to fetch (e.g., ['ratios', 'key-metrics']). If None, fetch all.
        tickers: List of tickers to process (e.g., ['AAPL', 'MSFT']). Only tickers that exist in
                 config_lv3_targets (ticker or peer column) will be processed. If None, process all.

    Returns:
        Dict with summary and results
    """
    logger.info(f"[get_quantatatives] Starting: overwrite={overwrite}, apis={apis}, tickers={tickers}")
    pool = await db_pool.get_pool()
    target_rows = await quantitatives.fetch_target_tickers_with_peers(pool)

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
        logger.info(f"[get_quantatatives] Selected APIs: {selected_apis}")

    # Collect all valid tickers from config_lv3_targets
    all_valid_tickers = set()
    for row in target_rows:
        ticker = row.get("ticker")
        if ticker:
            all_valid_tickers.add(str(ticker).upper())
        for peer in _parse_peer_value(row.get("peer")):
            all_valid_tickers.add(peer)

    # Filter tickers based on user input
    if tickers:
        # User specified tickers - filter and validate
        requested_tickers = set(ticker.upper() for ticker in tickers)
        valid_tickers = requested_tickers & all_valid_tickers
        invalid_tickers = requested_tickers - all_valid_tickers

        if invalid_tickers:
            logger.warning(
                f"[get_quantatatives] Skipping {len(invalid_tickers)} invalid tickers (not in config_lv3_targets): {sorted(invalid_tickers)}"
            )

        if not valid_tickers:
            logger.warning("[get_quantatatives] No valid tickers to process after filtering")
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
        logger.info(f"[get_quantatatives] Processing {len(tickers_to_process)} valid tickers from user input")
    else:
        # No tickers specified - process all
        tickers_to_process = all_valid_tickers
        logger.info(f"[get_quantatatives] Processing all {len(tickers_to_process)} tickers from config_lv3_targets")

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

    results: List[Dict[str, Any]] = []
    success_count = 0
    fail_count = 0
    skipped_count = 0

    # Progress tracking
    completed_tickers = 0
    start_time = time.time()

    async with FMPAPIClient() as fmp_client:
        # Set semaphore to usagePerMin to allow full rate limit utilization
        # RateLimiter (sliding window) will dynamically control actual rate
        # This allows burst capacity when API calls haven't been made for a while
        usage_per_min = fmp_client._usage_per_min_cache or 300  # Default to 300 if not set

        # Allow concurrent tasks up to the rate limit
        # RateLimiter.acquire() will sleep when needed to stay within limit
        max_concurrent = usage_per_min

        logger.info(
            f"[get_quantatatives] Max concurrent workers: {max_concurrent} "
            f"(usagePerMin={usage_per_min}). RateLimiter will dynamically throttle."
        )

        semaphore = asyncio.Semaphore(max_concurrent)
        async def worker(ticker: str):
            nonlocal success_count, fail_count, skipped_count, completed_tickers
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
                        skipped_count += 1
                    else:
                        fail_count += 1
                except Exception as exc:
                    logger.error(f"[get_quantatatives] Failed for {ticker}: {exc}", exc_info=True)
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
                    if completed_tickers % 10 == 0 or completed_tickers == len(tickers_to_process):
                        elapsed_ms = int((time.time() - start_time) * 1000)
                        eta_ms = calculate_eta(len(tickers_to_process), completed_tickers, elapsed_ms)
                        eta = format_eta_ms(eta_ms)

                        logger.info(
                            f"Processed {completed_tickers}/{len(tickers_to_process)} tickers",
                            extra={
                                'endpoint': 'POST /getQuantatatives',
                                'phase': 'ticker-processing',
                                'elapsed_ms': elapsed_ms,
                                'progress': format_progress(completed_tickers, len(tickers_to_process)),
                                'eta': eta,
                                'counters': {
                                    'success': success_count,
                                    'fail': fail_count,
                                    'skipped': skipped_count
                                }
                            }
                        )

        await asyncio.gather(*[worker(ticker) for ticker in sorted(tickers_to_process)])

    return {
        "summary": {
            "totalTickers": len(tickers_to_process),
            "success": success_count,
            "fail": fail_count,
            "skipped": skipped_count,
        },
        "results": results,
    }
