"""Database queries for metric definitions and event valuations."""

import asyncpg
import json
import logging
from typing import List, Dict, Any, Optional

from ...utils.logging_utils import log_db_update, log_row_update

logger = logging.getLogger("alsign")


async def select_metric_definitions(
    pool: asyncpg.Pool
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Load metric definitions from config_lv2_metric table.

    Groups metrics by domain suffix (valuation, profitability, momentum, risk, dilution).

    Returns:
        Dict with domain as key, list of metric definitions as value
        Example: {
            'valuation': [{'name': 'PER', 'formula': '...', ...}],
            'profitability': [{'name': 'ROE', ...}],
            ...
        }
    Note: 'name' maps to 'id' column and 'formula' maps to 'expression' column in the database.
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, domain, expression, description,
                   source, api_list_id, base_metric_id,
                   aggregation_kind, aggregation_params, response_key
            FROM config_lv2_metric
            WHERE domain LIKE 'quantitative-%'
               OR domain LIKE 'qualitative-%'
               OR domain = 'internal'
            ORDER BY domain, id
            """
        )

        # Group by domain suffix
        metrics_by_domain = {}
        for row in rows:
            # Parse JSONB fields if they come as strings
            agg_params = row['aggregation_params']
            if isinstance(agg_params, str):
                agg_params = json.loads(agg_params) if agg_params else {}

            resp_key = row['response_key']
            if isinstance(resp_key, str):
                resp_key = json.loads(resp_key) if resp_key else None

            domain_full = row['domain']

            # Extract suffix (quantitative-valuation -> valuation)
            if '-' in domain_full:
                domain_suffix = domain_full.split('-', 1)[1]
            else:
                domain_suffix = domain_full

            if domain_suffix not in metrics_by_domain:
                metrics_by_domain[domain_suffix] = []

            metrics_by_domain[domain_suffix].append({
                'name': row['id'],
                'domain': row['domain'],
                'formula': row['expression'],
                'description': row['description'],
                'source': row['source'],
                'api_list_id': row['api_list_id'],
                'base_metric_id': row['base_metric_id'],
                'aggregation_kind': row['aggregation_kind'],
                'aggregation_params': agg_params,
                'response_key': resp_key
            })

        return metrics_by_domain


async def select_events_for_valuation(
    pool: asyncpg.Pool,
    limit: int = None,
    from_date = None,
    to_date = None,
    tickers: List[str] = None
) -> List[Dict[str, Any]]:
    """
    Select events from txn_events that need valuation processing.

    Args:
        pool: Database connection pool
        limit: Optional limit on number of events to process
        from_date: Optional start date for filtering events by event_date
        to_date: Optional end date for filtering events by event_date
        tickers: Optional list of ticker symbols to filter. If None, processes all tickers.

    Returns:
        List of event dictionaries with ticker, event_date, source, source_id
    """
    async with pool.acquire() as conn:
        query = """
            SELECT id, ticker, event_date, source, source_id,
                   sector, industry,
                   value_quantitative, value_qualitative,
                   position_quantitative, position_qualitative,
                   disparity_quantitative, disparity_qualitative
            FROM txn_events
            WHERE 1=1
        """
        params = []
        param_idx = 1

        if from_date is not None:
            query += f" AND (event_date AT TIME ZONE 'UTC')::date >= ${param_idx}"
            params.append(from_date)
            param_idx += 1

        if to_date is not None:
            query += f" AND (event_date AT TIME ZONE 'UTC')::date <= ${param_idx}"
            params.append(to_date)
            param_idx += 1

        if tickers is not None and len(tickers) > 0:
            query += f" AND ticker = ANY(${param_idx})"
            params.append(tickers)
            param_idx += 1

        query += " ORDER BY ticker, event_date"

        if limit:
            query += f" LIMIT {limit}"

        rows = await conn.fetch(query, *params)
        return [dict(row) for row in rows]


async def select_trades_for_price_trends(
    pool: asyncpg.Pool,
    from_date = None,
    to_date = None,
    tickers: List[str] = None
) -> List[Dict[str, Any]]:
    """
    Select trades from txn_trades that are NOT in txn_events.

    Used by generatePriceTrends to process trades that don't have corresponding events.

    Args:
        pool: Database connection pool
        from_date: Optional start date for filtering by trade_date
        to_date: Optional end date for filtering by trade_date
        tickers: Optional list of ticker symbols to filter

    Returns:
        List of trade dictionaries with ticker and trade_date (aliased as event_date for compatibility)
    """
    async with pool.acquire() as conn:
        query = """
            SELECT
                t.ticker,
                t.trade_date AS event_date,
                t.model,
                t.source,
                t.position
            FROM txn_trades t
            WHERE NOT EXISTS (
                SELECT 1
                FROM txn_events e
                WHERE e.ticker = t.ticker
                  AND (e.event_date AT TIME ZONE 'UTC')::date = t.trade_date
            )
        """
        params = []
        param_idx = 1

        if from_date is not None:
            query += f" AND t.trade_date >= ${param_idx}"
            params.append(from_date)
            param_idx += 1

        if to_date is not None:
            query += f" AND t.trade_date <= ${param_idx}"
            params.append(to_date)
            param_idx += 1

        if tickers is not None and len(tickers) > 0:
            query += f" AND t.ticker = ANY(${param_idx})"
            params.append(tickers)
            param_idx += 1

        query += " ORDER BY t.ticker, t.trade_date"

        rows = await conn.fetch(query, *params)
        return [dict(row) for row in rows]


async def select_event_by_id(
    pool: asyncpg.Pool,
    ticker: str,
    event_date,
    source: str,
    source_id
) -> Dict[str, Any]:
    """
    Select a single event by composite key.

    Args:
        pool: Database connection pool
        ticker: Ticker symbol
        event_date: Event date
        source: Source table name
        source_id: Source record ID

    Returns:
        Event dictionary or None
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT ticker, event_date, source, source_id,
                   sector, industry,
                   value_quantitative, value_qualitative,
                   position_quantitative, position_qualitative,
                   disparity_quantitative, disparity_qualitative
            FROM txn_events
            WHERE ticker = $1
              AND event_date = $2
              AND source = $3
              AND source_id = $4
            """,
            ticker,
            event_date,
            source,
            source_id
        )

        return dict(row) if row else None


async def select_consensus_data(
    pool: asyncpg.Pool,
    ticker: str,
    event_date,
    source_id: str
) -> Dict[str, Any]:
    """
    Select consensus data for qualitative calculation.

    Uses source_id to find the exact row in evt_consensus table.
    This ensures we get the correct analyst's data when multiple
    analysts have events on the same date.

    Fetches Phase 2 data (price_target, price_when_posted, direction, prev values).

    Args:
        pool: Database connection pool
        ticker: Ticker symbol
        event_date: Event date
        source_id: evt_consensus.id (UUID string)

    Returns:
        Consensus data dictionary or None
    """
    import json

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, ticker, event_date, analyst_name, analyst_company,
                   price_target, price_when_posted,
                   price_target_prev, price_when_posted_prev,
                   direction, response_key, target_summary
            FROM evt_consensus
            WHERE id = $1
              AND ticker = $2
              AND event_date = $3
            """,
            source_id,
            ticker,
            event_date
        )

        if not row:
            return None

        # Convert row to dict
        result = dict(row)

        # I-39: Parse target_summary from JSON string to dict
        # asyncpg returns jsonb as string, need to parse it
        if result.get('target_summary') and isinstance(result['target_summary'], str):
            try:
                result['target_summary'] = json.loads(result['target_summary'])
            except (json.JSONDecodeError, TypeError):
                # Keep as string if parsing fails
                pass

        return result


async def batch_update_event_valuations(
    pool: asyncpg.Pool,
    updates: List[Dict[str, Any]],
    overwrite: bool = False,
    metrics: Optional[List[str]] = None
) -> int:
    """
    Batch update event valuations in txn_events.

    Args:
        pool: Database connection pool
        updates: List of update dictionaries, each containing:
            - ticker: Ticker symbol
            - event_date: Event date
            - source: Source table name
            - source_id: Source record ID
            - value_quantitative: Quantitative metrics jsonb
            - value_qualitative: Qualitative metrics jsonb
            - position_quantitative: Position signal
            - position_qualitative: Position signal
            - disparity_quantitative: Quantitative disparity
            - disparity_qualitative: Qualitative disparity
        overwrite: If False, update only NULL values. If True, overwrite existing values.
                   When used with metrics: applies to specified metrics only.
                   When used without metrics: applies to all value_* JSONB fields.
        metrics: Optional list of metric IDs to update (I-41). If specified, only these metrics
                 are updated within value_quantitative JSONB. Works in combination with 'overwrite'.

    Returns:
        Number of rows updated
    """
    if not updates:
        return 0
    
    async with pool.acquire() as conn:
        # I-42 DEBUG: Log what we're storing
        if updates and len(updates) > 0:
            first_upd = updates[0]
            val_quant = first_upd.get('value_quantitative')
            if val_quant and isinstance(val_quant, dict) and 'valuation' in val_quant:
                logger.info(f"[I-42 DB DEBUG] Storing valuation keys: {list(val_quant['valuation'].keys())[:6]}")

        # Prepare batch data
        records = [
            (
                upd['ticker'],
                upd['event_date'],
                upd['source'],
                upd['source_id'],
                json.dumps(upd.get('value_quantitative')) if upd.get('value_quantitative') else None,
                json.dumps(upd.get('value_qualitative')) if upd.get('value_qualitative') else None,
                upd.get('position_quantitative'),
                upd.get('position_qualitative'),
                upd.get('disparity_quantitative'),
                upd.get('disparity_qualitative'),
                # I-42: Dedicated columns for performance
                upd.get('price_quantitative'),
                json.dumps(upd.get('peer_quantitative')) if upd.get('peer_quantitative') else None
            )
            for upd in updates
        ]
        
        # I-41: Selective metric update support
        if metrics is not None:
            # Selective metric update mode (I-41)
            # Deep merge specific metrics into value_quantitative JSONB
            # The 'overwrite' parameter controls whether to replace existing values or only fill NULLs
            query = """
                WITH batch_data AS (
                    SELECT * FROM UNNEST($1::text[], $2::timestamptz[], $3::text[], $4::text[],
                                       $5::jsonb[], $6::jsonb[], $7::text[], $8::text[],
                                       $9::numeric[], $10::numeric[], $11::numeric[], $12::jsonb[])
                    AS t(ticker, event_date, source, source_id,
                         value_quantitative, value_qualitative,
                         position_quantitative, position_qualitative,
                         disparity_quantitative, disparity_qualitative,
                         price_quantitative, peer_quantitative)
                )
                UPDATE txn_events e
                SET value_quantitative = COALESCE(e.value_quantitative, '{}'::jsonb) || b.value_quantitative,
                    value_qualitative = COALESCE(e.value_qualitative, b.value_qualitative),
                    position_quantitative = COALESCE(e.position_quantitative, b.position_quantitative::"position"),
                    position_qualitative = COALESCE(e.position_qualitative, b.position_qualitative::"position"),
                    disparity_quantitative = COALESCE(e.disparity_quantitative, b.disparity_quantitative),
                    disparity_qualitative = COALESCE(e.disparity_qualitative, b.disparity_qualitative),
                    price_quantitative = COALESCE(e.price_quantitative, b.price_quantitative),
                    peer_quantitative = COALESCE(e.peer_quantitative, b.peer_quantitative)
                FROM batch_data b
                WHERE e.ticker = b.ticker
                  AND e.event_date = b.event_date
                  AND e.source = b.source
                  AND e.source_id = b.source_id
                RETURNING e.id, e.ticker, e.event_date, e.source, e.source_id
            """
        elif overwrite:
            # Full replace mode using temp table
            query = """
                WITH batch_data AS (
                    SELECT * FROM UNNEST($1::text[], $2::timestamptz[], $3::text[], $4::text[],
                                       $5::jsonb[], $6::jsonb[], $7::text[], $8::text[],
                                       $9::numeric[], $10::numeric[], $11::numeric[], $12::jsonb[])
                    AS t(ticker, event_date, source, source_id,
                         value_quantitative, value_qualitative,
                         position_quantitative, position_qualitative,
                         disparity_quantitative, disparity_qualitative,
                         price_quantitative, peer_quantitative)
                )
                UPDATE txn_events e
                SET value_quantitative = b.value_quantitative,
                    value_qualitative = b.value_qualitative,
                    position_quantitative = b.position_quantitative::"position",
                    position_qualitative = b.position_qualitative::"position",
                    disparity_quantitative = b.disparity_quantitative,
                    disparity_qualitative = b.disparity_qualitative,
                    price_quantitative = b.price_quantitative,
                    peer_quantitative = b.peer_quantitative
                FROM batch_data b
                WHERE e.ticker = b.ticker
                  AND e.event_date = b.event_date
                  AND e.source = b.source
                  AND e.source_id = b.source_id
                RETURNING e.id, e.ticker, e.event_date, e.source, e.source_id
            """
        else:
            # Partial update mode - only update NULL values
            query = """
                WITH batch_data AS (
                    SELECT * FROM UNNEST($1::text[], $2::timestamptz[], $3::text[], $4::text[],
                                       $5::jsonb[], $6::jsonb[], $7::text[], $8::text[],
                                       $9::numeric[], $10::numeric[], $11::numeric[], $12::jsonb[])
                    AS t(ticker, event_date, source, source_id,
                         value_quantitative, value_qualitative,
                         position_quantitative, position_qualitative,
                         disparity_quantitative, disparity_qualitative,
                         price_quantitative, peer_quantitative)
                )
                UPDATE txn_events e
                SET value_quantitative = CASE
                        WHEN e.value_quantitative IS NULL THEN b.value_quantitative
                        ELSE e.value_quantitative
                    END,
                    value_qualitative = CASE
                        WHEN e.value_qualitative IS NULL THEN b.value_qualitative
                        ELSE e.value_qualitative
                    END,
                    position_quantitative = COALESCE(e.position_quantitative, b.position_quantitative::"position"),
                    position_qualitative = COALESCE(e.position_qualitative, b.position_qualitative::"position"),
                    disparity_quantitative = COALESCE(e.disparity_quantitative, b.disparity_quantitative),
                    disparity_qualitative = COALESCE(e.disparity_qualitative, b.disparity_qualitative),
                    price_quantitative = COALESCE(e.price_quantitative, b.price_quantitative),
                    peer_quantitative = COALESCE(e.peer_quantitative, b.peer_quantitative)
                FROM batch_data b
                WHERE e.ticker = b.ticker
                  AND e.event_date = b.event_date
                  AND e.source = b.source
                  AND e.source_id = b.source_id
                RETURNING e.id, e.ticker, e.event_date, e.source, e.source_id
            """
        
        # Unzip records into column arrays
        tickers, event_dates, sources, source_ids = [], [], [], []
        val_quants, val_quals, pos_quants, pos_quals = [], [], [], []
        disp_quants, disp_quals = [], []
        price_quants, peer_quants = [], []  # I-42: New columns

        for rec in records:
            tickers.append(rec[0])
            event_dates.append(rec[1])
            sources.append(rec[2])
            source_ids.append(rec[3])
            val_quants.append(rec[4])
            val_quals.append(rec[5])
            pos_quants.append(rec[6])
            pos_quals.append(rec[7])
            disp_quants.append(rec[8])
            disp_quals.append(rec[9])
            price_quants.append(rec[10])  # I-42
            peer_quants.append(rec[11])   # I-42

        updated_rows = await conn.fetch(
            query,
            tickers, event_dates, sources, source_ids,
            val_quants, val_quals, pos_quants, pos_quals,
            disp_quants, disp_quals, price_quants, peer_quants  # I-42
        )

        # Log updated row IDs
        if updated_rows:
            log_db_update(logger, "txn_events", len(updated_rows))
            for row in updated_rows:
                log_row_update(
                    logger, "txn_events", str(row['id'])[:8],
                    f"ticker={row['ticker']}, date={row['event_date'].date() if row['event_date'] else None}, source={row['source']}",
                    level="debug"
                )

        return len(updated_rows)


async def update_event_valuations(
    pool: asyncpg.Pool,
    ticker: str,
    event_date,
    source: str,
    source_id,
    value_quantitative: Dict[str, Any] = None,
    value_qualitative: Dict[str, Any] = None,
    position_quantitative: str = None,
    position_qualitative: str = None,
    disparity_quantitative: float = None,
    disparity_qualitative: float = None,
    overwrite: bool = False
) -> int:
    """
    Update event valuations in txn_events.

    Args:
        pool: Database connection pool
        ticker: Ticker symbol
        event_date: Event date
        source: Source table name
        source_id: Source record ID
        value_quantitative: Quantitative metrics jsonb
        value_qualitative: Qualitative metrics jsonb
        position_quantitative: Position signal (long/short/undefined)
        position_qualitative: Position signal (long/short/undefined)
        disparity_quantitative: Quantitative disparity
        disparity_qualitative: Qualitative disparity
        overwrite: If False, partial update (NULL values only). If True, full replace.

    Returns:
        Number of rows updated (should be 1)

    Table columns (never write to created_at, updated_at):
    - value_quantitative (jsonb)
    - value_qualitative (jsonb)
    - position_quantitative (text)
    - position_qualitative (text)
    - disparity_quantitative (numeric)
    - disparity_qualitative (numeric)
    """
    async with pool.acquire() as conn:
        if overwrite:
            # Full replace mode
            result = await conn.execute(
                """
                UPDATE txn_events
                SET value_quantitative = $5,
                    value_qualitative = $6,
                    position_quantitative = $7,
                    position_qualitative = $8,
                    disparity_quantitative = $9,
                    disparity_qualitative = $10
                WHERE ticker = $1
                  AND event_date = $2
                  AND source = $3
                  AND source_id = $4
                """,
                ticker,
                event_date,
                source,
                source_id,
                json.dumps(value_quantitative) if value_quantitative else None,
                json.dumps(value_qualitative) if value_qualitative else None,
                position_quantitative,
                position_qualitative,
                disparity_quantitative,
                disparity_qualitative
            )
        else:
            # Partial update mode - only update NULL values
            result = await conn.execute(
                """
                UPDATE txn_events
                SET value_quantitative = CASE
                        WHEN value_quantitative IS NULL THEN $5::jsonb
                        ELSE value_quantitative
                    END,
                    value_qualitative = CASE
                        WHEN value_qualitative IS NULL THEN $6::jsonb
                        ELSE value_qualitative
                    END,
                    position_quantitative = COALESCE(position_quantitative, $7),
                    position_qualitative = COALESCE(position_qualitative, $8),
                    disparity_quantitative = COALESCE(disparity_quantitative, $9),
                    disparity_qualitative = COALESCE(disparity_qualitative, $10)
                WHERE ticker = $1
                  AND event_date = $2
                  AND source = $3
                  AND source_id = $4
                """,
                ticker,
                event_date,
                source,
                source_id,
                json.dumps(value_quantitative) if value_quantitative else None,
                json.dumps(value_qualitative) if value_qualitative else None,
                position_quantitative,
                position_qualitative,
                disparity_quantitative,
                disparity_qualitative
            )

        # Parse result to get row count
        if "UPDATE" in result:
            count = int(result.split()[-1])
            return count

        return 0


async def select_internal_qual_metrics(pool: asyncpg.Pool) -> List[Dict[str, Any]]:
    """
    Select internal(qual) metrics for analyst performance calculation.

    These metrics define which statistics to calculate from the return distribution.

    Returns:
        List of metric definitions with domain='internal(qual)' and base_metric_id='priceTrendReturnSeries'
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, domain, expression, description,
                   source, base_metric_id, aggregation_kind,
                   aggregation_params, response_key
            FROM config_lv2_metric
            WHERE domain = 'internal(qual)'
              AND base_metric_id = 'priceTrendReturnSeries'
            ORDER BY id
            """
        )
        result = []
        for row in rows:
            # Parse JSONB fields if they come as strings
            agg_params = row['aggregation_params']
            if isinstance(agg_params, str):
                agg_params = json.loads(agg_params) if agg_params else {}

            resp_key = row['response_key']
            if isinstance(resp_key, str):
                resp_key = json.loads(resp_key) if resp_key else None

            result.append({
                'id': row['id'],
                'domain': row['domain'],
                'expression': row['expression'],
                'description': row['description'],
                'source': row['source'],
                'base_metric_id': row['base_metric_id'],
                'aggregation_kind': row['aggregation_kind'],
                'aggregation_params': agg_params,
                'response_key': resp_key
            })
        return result


async def select_metric_transforms(
    pool: asyncpg.Pool
) -> Dict[str, Dict[str, Any]]:
    """
    Load metric transform definitions from config_lv2_metric_transform table.
    
    Returns:
        Dict with transform id as key, transform definition as value
        Example: {
            'avgFromQuarter': {
                'id': 'avgFromQuarter',
                'calculation': 'if not quarterly_values: ...',
                'input_kind': 'quarter_series',
                'output_kind': 'scalar',
                ...
            },
            ...
        }
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, transform_type, description, input_kind, output_kind,
                   params_schema, example_params, calculation, version, is_active
            FROM config_lv2_metric_transform
            WHERE is_active = true
            ORDER BY id
            """
        )
        
        transforms = {}
        for row in rows:
            # Parse JSONB fields if they come as strings
            params_schema = row['params_schema']
            if isinstance(params_schema, str):
                params_schema = json.loads(params_schema) if params_schema else {}
            
            example_params = row['example_params']
            if isinstance(example_params, str):
                example_params = json.loads(example_params) if example_params else {}
            
            transforms[row['id']] = {
                'id': row['id'],
                'transform_type': row['transform_type'],
                'description': row['description'],
                'input_kind': row['input_kind'],
                'output_kind': row['output_kind'],
                'params_schema': params_schema,
                'example_params': example_params,
                'calculation': row['calculation'],  # Python code string
                'version': row['version'],
                'is_active': row['is_active']
            }
        
        return transforms
