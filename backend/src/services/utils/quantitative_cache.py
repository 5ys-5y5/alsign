"""
DB 기반 quantitative 데이터 캐시 유틸리티

POST /backfillEventsTable에서 FMP API 호출 없이 DB만 사용하도록 지원.
config_lv3_quantitatives와 config_lv3_targets 테이블에서 데이터를 조회합니다.
"""
import logging
import json
import time
from typing import Dict, Any, List, Optional

logger = logging.getLogger("alsign")

# API ID → 테이블 컬럼 매핑 (quantitatives_service.py:18-27 참조)
API_COLUMN_MAP = {
    "fmp-income-statement": "income_statement",
    "fmp-balance-sheet-statement": "balance_sheet_statement",
    "fmp-cash-flow-statement": "cash_flow_statement",
    "fmp-key-metrics": "key_metrics",
    "fmp-ratios": "financial_ratios",
    "fmp-historical-price-eod-full": "historical_price",
    "fmp-historical-market-capitalization": "historical_market_cap",
    "fmp-quote": "quote",
}


async def get_peer_tickers_from_db(pool, ticker: str) -> List[str]:
    """
    config_lv3_targets.peer 컬럼에서 peer 목록 조회 (API 호출 없음!)

    Args:
        pool: Database connection pool
        ticker: Target ticker

    Returns:
        Peer ticker 목록 (JSON array에서 파싱, 자기 자신 제외)

    Example:
        >>> peers = await get_peer_tickers_from_db(pool, "AAPL")
        >>> # Returns: ["MSFT", "GOOGL", "META", ...]
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT peer FROM config_lv3_targets WHERE ticker = $1",
            ticker.upper()
        )

        if not row or not row['peer']:
            logger.warning(f"[DB-Cache] No peer data in config_lv3_targets for {ticker}")
            return []

        # JSONB array 파싱
        peers = row['peer']
        if isinstance(peers, list):
            # PostgreSQL JSONB는 자동으로 list로 반환됨
            peer_list = [p for p in peers if p != ticker.upper()]
        elif isinstance(peers, str):
            # 문자열인 경우 JSON 파싱 시도
            try:
                peers_list = json.loads(peers)
                peer_list = [p for p in peers_list if p != ticker.upper()]
            except Exception as e:
                logger.error(f"[DB-Cache] Failed to parse peer JSON for {ticker}: {e}")
                return []
        else:
            logger.warning(f"[DB-Cache] Unexpected peer format for {ticker}: {type(peers)}")
            return []

        logger.debug(f"[DB-Cache] Found {len(peer_list)} peers for {ticker} from DB")
        return peer_list


async def get_batch_peer_tickers_from_db(pool, tickers: List[str]) -> Dict[str, List[str]]:
    """
    config_lv3_targets.peer 컬럼에서 여러 ticker의 peer 목록을 일괄 조회 (최적화)

    단일 배치 쿼리로 여러 ticker의 peer 데이터를 한 번에 조회하여 성능 향상.
    DB CPU 부하 최소화: Query planning 1회, Index scan 1회 (batch)

    Args:
        pool: Database connection pool
        tickers: Ticker 목록 (e.g., ["AAPL", "MSFT", "GOOGL"])

    Returns:
        {ticker: [peer1, peer2, ...], ...} 형태의 dict (자기 자신 제외)

    Example:
        >>> result = await get_batch_peer_tickers_from_db(pool, ["AAPL", "MSFT"])
        >>> # Returns: {
        ...     "AAPL": ["MSFT", "GOOGL", "META", ...],
        ...     "MSFT": ["AAPL", "GOOGL", "META", ...]
        ... }
    """
    if not tickers:
        return {}

    # 배치 쿼리로 모든 ticker의 peer 데이터 한 번에 조회
    tickers_upper = [t.upper() for t in tickers]
    logger.info(f"[DB-Cache] Batch query from config_lv3_targets: {len(tickers_upper)} tickers (Peer mappings)")

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT ticker, peer
            FROM config_lv3_targets
            WHERE ticker = ANY($1::text[])
            """,
            tickers_upper
        )

    # 결과 변환: DB row → {ticker: [peers]} 형식
    result = {}
    success_tickers = []
    failed_tickers = []

    for row in rows:
        ticker = row['ticker']
        peers = row['peer']

        if not peers:
            result[ticker] = []
            failed_tickers.append(ticker)
            continue

        # JSONB array 파싱
        if isinstance(peers, list):
            # PostgreSQL JSONB는 자동으로 list로 반환됨
            peer_list = [p for p in peers if p != ticker]
        elif isinstance(peers, str):
            # 문자열인 경우 JSON 파싱 시도
            try:
                peers_list = json.loads(peers)
                peer_list = [p for p in peers_list if p != ticker]
            except Exception as e:
                logger.error(f"[DB-Cache] Failed to parse peer JSON for {ticker}: {e}")
                peer_list = []
                failed_tickers.append(ticker)
                result[ticker] = peer_list
                continue
        else:
            logger.warning(f"[DB-Cache] Unexpected peer format for {ticker}: {type(peers)}")
            peer_list = []
            failed_tickers.append(ticker)
            result[ticker] = peer_list
            continue

        result[ticker] = peer_list
        if peer_list:
            success_tickers.append(f"{ticker}({len(peer_list)})")

    # 누락된 ticker 체크
    missing_tickers = set(tickers_upper) - set(result.keys())
    if missing_tickers:
        # 누락된 ticker는 빈 리스트로 초기화
        for ticker in missing_tickers:
            result[ticker] = []
            failed_tickers.append(ticker)

    # 요약 로그 출력
    logger.info(
        f"[DB-Cache] ✓ config_lv3_targets query complete: "
        f"Success={len(success_tickers)}, Failed={len(failed_tickers)} | "
        f"Samples: {', '.join(success_tickers[:5])}{', ...' if len(success_tickers) > 5 else ''}"
    )

    if failed_tickers:
        logger.warning(
            f"[DB-Cache] Tickers without peers ({len(failed_tickers)}): "
            f"{', '.join(failed_tickers[:10])}{', ...' if len(failed_tickers) > 10 else ''}"
        )

    return result


async def get_quantitative_data_from_db(
    pool,
    ticker: str,
    required_apis: List[str]
) -> Dict[str, Any]:
    """
    config_lv3_quantitatives에서 단일 ticker의 재무 데이터 조회 (API 호출 없음!)

    Args:
        pool: Database connection pool
        ticker: Ticker to fetch
        required_apis: List of API IDs to retrieve (e.g., ["fmp-income-statement", ...])

    Returns:
        {api_id: data, ...} 형태의 딕셔너리 (API cache 형식과 동일)

    Example:
        >>> cache = await get_quantitative_data_from_db(
        ...     pool,
        ...     "AAPL",
        ...     ["fmp-income-statement", "fmp-ratios"]
        ... )
        >>> # Returns: {
        ...     "fmp-income-statement": [...],  # JSONB data
        ...     "fmp-ratios": [...]
        ... }
    """
    from ...database.queries import quantitatives

    ticker_row = await quantitatives.get_quantitatives_by_ticker(pool, ticker)

    if not ticker_row:
        logger.warning(f"[DB-Cache] No quantitative data for {ticker} in config_lv3_quantitatives")
        return {}

    # DB 컬럼 → API cache 형식 변환
    api_cache = {}
    missing_apis = []

    for api_id in required_apis:
        column_name = API_COLUMN_MAP.get(api_id)
        if not column_name:
            logger.debug(f"[DB-Cache] Unknown API ID: {api_id}")
            continue

        column_data = ticker_row.get(column_name)
        if column_data is not None:
            # CRITICAL FIX: Parse JSONB string to list/dict
            if isinstance(column_data, str):
                try:
                    column_data = json.loads(column_data)
                    logger.debug(f"[DB-Cache] Parsed JSON string for {ticker}.{column_name} (API: {api_id})")
                except Exception as e:
                    logger.error(f"[DB-Cache] Failed to parse JSON for {ticker}.{column_name}: {e}")
                    column_data = []
                    missing_apis.append(api_id)
            api_cache[api_id] = column_data
        else:
            logger.debug(f"[DB-Cache] Missing data for {ticker}.{column_name} (API: {api_id})")
            api_cache[api_id] = []  # 빈 데이터로 초기화 (계산 엔진에서 처리)
            missing_apis.append(api_id)

    if missing_apis:
        logger.warning(
            f"[DB-Cache] {ticker}: Missing {len(missing_apis)} APIs: {missing_apis[:3]}... "
            f"Run POST /getQuantitatives to fetch missing data."
        )

    logger.debug(f"[DB-Cache] Loaded {len(api_cache) - len(missing_apis)}/{len(required_apis)} APIs for {ticker} from DB")
    return api_cache


async def get_batch_quantitative_data_from_db(
    pool,
    tickers: List[str],
    required_apis: List[str]
) -> Dict[str, Dict[str, Any]]:
    """
    config_lv3_quantitatives에서 여러 ticker의 재무 데이터 일괄 조회 (최적화)

    단일 배치 쿼리로 여러 ticker의 데이터를 한 번에 조회하여 성능 향상.

    Args:
        pool: Database connection pool
        tickers: Ticker 목록 (e.g., ["AAPL", "MSFT", "GOOGL"])
        required_apis: List of API IDs to retrieve

    Returns:
        {ticker: {api_id: data, ...}, ...} 형태의 nested dict

    Example:
        >>> cache = await get_batch_quantitative_data_from_db(
        ...     pool,
        ...     ["AAPL", "MSFT"],
        ...     ["fmp-income-statement", "fmp-ratios"]
        ... )
        >>> # Returns: {
        ...     "AAPL": {"fmp-income-statement": [...], "fmp-ratios": [...]},
        ...     "MSFT": {"fmp-income-statement": [...], "fmp-ratios": [...]}
        ... }
    """
    if not tickers:
        return {}

    # 필요한 컬럼 목록 추출
    columns_to_fetch = set(['ticker'])  # ticker 컬럼은 항상 필요
    api_to_column = {}  # API ID → 컬럼명 매핑 (역조회용)

    for api_id in required_apis:
        column_name = API_COLUMN_MAP.get(api_id)
        if column_name:
            columns_to_fetch.add(column_name)
            api_to_column[api_id] = column_name

    columns_str = ", ".join(columns_to_fetch)

    # 배치 쿼리로 모든 ticker 데이터 한 번에 조회
    logger.info(
        f"[DB-Cache] Batch query from config_lv3_quantitatives: "
        f"{len(tickers)} tickers × {len(required_apis)} APIs (No API calls)"
    )
    query_start = time.time()
    logger.info(
        f"[temp.debug] quant cache query start: tickers={len(tickers)} apis={len(required_apis)}"
    )

    async with pool.acquire() as conn:
        try:
            await conn.execute("SET statement_timeout = '300s'")
            rows = await conn.fetch(
                f"""
            SELECT {columns_str}
            FROM config_lv3_quantitatives
            WHERE ticker = ANY($1::text[])
            """,
                tickers
            )
        except Exception as e:
            elapsed_ms = int((time.time() - query_start) * 1000)
            logger.error(
                f"[temp.debug] quant cache query failed: {type(e).__name__}: {e!r} elapsed_ms={elapsed_ms}",
                exc_info=True
            )
            raise
    query_elapsed_ms = int((time.time() - query_start) * 1000)
    logger.info(
        f"[temp.debug] quant cache query done: rows={len(rows)} elapsed_ms={query_elapsed_ms}"
    )

    # 결과 변환: DB row → API cache 형식
    result = {}
    success_tickers = []
    parse_errors = []

    for row in rows:
        ticker = row['ticker']
        api_cache = {}
        ticker_has_error = False

        for api_id in required_apis:
            column_name = API_COLUMN_MAP.get(api_id)
            if column_name:
                column_data = row.get(column_name)

                # CRITICAL FIX: Parse JSONB string to list/dict
                if column_data is not None:
                    if isinstance(column_data, str):
                        try:
                            column_data = json.loads(column_data)
                        except Exception as e:
                            logger.error(f"[DB-Cache] Failed to parse JSON for {ticker}.{column_name}: {e}")
                            column_data = []
                            ticker_has_error = True
                    api_cache[api_id] = column_data
                else:
                    api_cache[api_id] = []

        result[ticker] = api_cache
        if not ticker_has_error:
            success_tickers.append(ticker)
        else:
            parse_errors.append(ticker)

    # 누락된 ticker 체크
    missing_tickers = set(tickers) - set(result.keys())

    # 요약 로그 출력
    logger.info(
        f"[DB-Cache] ✓ config_lv3_quantitatives query complete: "
        f"Success={len(success_tickers)}, ParseError={len(parse_errors)}, Missing={len(missing_tickers)} | "
        f"APIs={len(required_apis)} | "
        f"Samples: {', '.join(success_tickers[:5])}{', ...' if len(success_tickers) > 5 else ''}"
    )

    if parse_errors:
        logger.warning(
            f"[DB-Cache] Tickers with parse errors ({len(parse_errors)}): "
            f"{', '.join(parse_errors[:10])}{', ...' if len(parse_errors) > 10 else ''}"
        )

    if missing_tickers:
        logger.warning(
            f"[DB-Cache] Missing tickers ({len(missing_tickers)}): "
            f"{', '.join(list(missing_tickers)[:10])}{', ...' if len(missing_tickers) > 10 else ''} | "
            f"Run POST /getQuantitatives to fetch missing data."
        )

    return result


async def calculate_sector_average_from_cache(
    peer_tickers: List[str],
    global_peer_cache: Dict[str, Dict[str, Any]]
) -> Dict[str, float]:
    """
    글로벌 peer 캐시에서 sector average 계산 (API 호출 없음!)

    Args:
        peer_tickers: Peer ticker 목록
        global_peer_cache: {ticker: {api_id: data}} 형태의 글로벌 캐시

    Returns:
        {metric_name: average_value} 형태의 sector averages

    Example:
        >>> sector_avg = await calculate_sector_average_from_cache(
        ...     ["MSFT", "GOOGL"],
        ...     global_peer_cache
        ... )
        >>> # Returns: {"PER": 25.5, "PBR": 7.2, ...}
    """
    from ..metric_engine import MetricCalculationEngine

    sector_averages = {}
    metric_values = {}  # {metric_name: [value1, value2, ...]}
    peers_with_data_count = 0
    peers_without_ratios = []
    peers_not_in_cache = []

    for peer_ticker in peer_tickers:
        peer_data = global_peer_cache.get(peer_ticker)
        if not peer_data:
            peers_not_in_cache.append(peer_ticker)
            continue

        # 각 peer의 financial ratios에서 메트릭 추출
        ratios = peer_data.get('fmp-ratios')

        if ratios and isinstance(ratios, list) and len(ratios) > 0:
            latest_ratio = ratios[0]  # 가장 최근 데이터
            peers_with_data_count += 1

            # PER, PBR, PSR 등 주요 메트릭 추출
            for metric_name in ['priceEarningsRatio', 'priceToBookRatio', 'priceToSalesRatio',
                                'debtEquityRatio', 'returnOnEquity', 'currentRatio']:
                value = latest_ratio.get(metric_name)
                if value is not None and value != 0:
                    if metric_name not in metric_values:
                        metric_values[metric_name] = []
                    metric_values[metric_name].append(float(value))
        else:
            peers_without_ratios.append(peer_ticker)

    # Calculate averages and convert to short names (PER, PBR, PSR)
    metric_name_map = {
        'priceEarningsRatio': 'PER',
        'priceToBookRatio': 'PBR',
        'priceToSalesRatio': 'PSR',
        'debtEquityRatio': 'debtEquityRatio',
        'returnOnEquity': 'ROE',
        'currentRatio': 'currentRatio'
    }

    for metric_name, values in metric_values.items():
        if values:
            avg_value = sum(values) / len(values)
            short_name = metric_name_map.get(metric_name, metric_name)
            sector_averages[short_name] = avg_value

    # 요약 로그 출력
    metrics_str = ', '.join([f"{k}={v:.2f}" for k, v in sector_averages.items()])
    logger.info(
        f"[DB-Cache] ✓ Sector average calculation complete (from global_peer_cache via config_lv3_quantitatives): "
        f"ValidPeers={peers_with_data_count}/{len(peer_tickers)}, Metrics={len(sector_averages)} | "
        f"{metrics_str}"
    )

    if peers_not_in_cache:
        logger.warning(
            f"[DB-Cache] Peers not in cache ({len(peers_not_in_cache)}): "
            f"{', '.join(peers_not_in_cache[:10])}{', ...' if len(peers_not_in_cache) > 10 else ''}"
        )

    if peers_without_ratios:
        logger.warning(
            f"[DB-Cache] Peers without ratios ({len(peers_without_ratios)}): "
            f"{', '.join(peers_without_ratios[:10])}{', ...' if len(peers_without_ratios) > 10 else ''}"
        )

    if not sector_averages:
        logger.error(
            f"[DB-Cache] CRITICAL: Empty sector_averages! "
            f"ValidPeers={peers_with_data_count}, NotInCache={len(peers_not_in_cache)}, "
            f"WithoutRatios={len(peers_without_ratios)}"
        )

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

        # PBR이 음수이거나 없으면 PSR로 시도
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
            return fair_value

        return None

    except Exception as e:
        logger.error(f"[I-36] Failed to calculate fair value: {e}")
        return None


async def calculate_sector_average_metrics_from_db(
    pool,
    peer_tickers: List[str],
    reference_date,
    metrics_by_domain: Dict[str, List[Dict[str, Any]]]
) -> Dict[str, float]:
    """
    DB에서 peer 데이터를 조회하여 sector average 계산 (fallback)

    Args:
        pool: Database connection pool
        peer_tickers: Peer ticker 목록
        reference_date: 기준 날짜
        metrics_by_domain: Metric definitions

    Returns:
        {metric_name: average_value} 형태의 sector averages
    """
    from ...database.queries import quantitatives

    sector_averages = {}
    metric_values = {}

    for peer_ticker in peer_tickers:
        peer_row = await quantitatives.get_quantitatives_by_ticker(pool, peer_ticker)
        if not peer_row:
            continue

        # Extract financial ratios
        ratios = peer_row.get('financial_ratios')
        if ratios and isinstance(ratios, list) and len(ratios) > 0:
            latest_ratio = ratios[0]

            for metric_name in ['priceEarningsRatio', 'priceToBookRatio', 'priceToSalesRatio',
                                'debtEquityRatio', 'returnOnEquity', 'currentRatio']:
                value = latest_ratio.get(metric_name)
                if value is not None and value != 0:
                    if metric_name not in metric_values:
                        metric_values[metric_name] = []
                    metric_values[metric_name].append(float(value))

    # Calculate averages and convert to short names (PER, PBR, PSR)
    metric_name_map = {
        'priceEarningsRatio': 'PER',
        'priceToBookRatio': 'PBR',
        'priceToSalesRatio': 'PSR',
        'debtEquityRatio': 'debtEquityRatio',
        'returnOnEquity': 'ROE',
        'currentRatio': 'currentRatio'
    }

    for metric_name, values in metric_values.items():
        if values:
            avg_value = sum(values) / len(values)
            short_name = metric_name_map.get(metric_name, metric_name)
            sector_averages[short_name] = avg_value

    logger.debug(f"[DB-Cache] Calculated sector averages from {len(peer_tickers)} peers from DB: {list(sector_averages.keys())}")
    return sector_averages
