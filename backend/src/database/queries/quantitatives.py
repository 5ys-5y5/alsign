"""Database queries for quantitatives data (config_lv3_quantitatives table)."""

import asyncpg
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("alsign")


async def fetch_target_tickers_with_peers(pool: asyncpg.Pool) -> List[Dict[str, Any]]:
    """
    Fetch tickers and peers from config_lv3_targets.

    Returns:
        List of rows with ticker and peer columns.
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT ticker, peer FROM config_lv3_targets")
        return [dict(row) for row in rows]


async def get_quantitatives_by_ticker(
    pool: asyncpg.Pool,
    ticker: str
) -> Optional[Dict[str, Any]]:
    """
    Fetch config_lv3_quantitatives row for a ticker.

    Args:
        pool: Database connection pool.
        ticker: Ticker symbol.

    Returns:
        Dict of row values, or None if not found.
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                ticker,
                status,
                income_statement,
                balance_sheet_statement,
                cash_flow_statement,
                key_metrics,
                financial_ratios,
                quote,
                historical_price,
                historical_market_cap
            FROM config_lv3_quantitatives
            WHERE ticker = $1
            """,
            ticker,
        )
        return dict(row) if row else None


async def upsert_quantitatives(
    pool: asyncpg.Pool,
    record: Dict[str, Any]
) -> None:
    """
    Upsert a config_lv3_quantitatives row.

    Args:
        pool: Database connection pool.
        record: Dictionary of column values.
    """
    import json

    # Helper to convert dict/list to JSON string for JSONB columns
    def to_jsonb(value):
        if value is None:
            return None
        if isinstance(value, (dict, list)):
            return json.dumps(value)
        return value

    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO config_lv3_quantitatives (
                ticker,
                status,
                income_statement,
                balance_sheet_statement,
                cash_flow_statement,
                key_metrics,
                financial_ratios,
                quote,
                historical_price,
                historical_market_cap
            )
            VALUES ($1, $2::jsonb, $3::jsonb, $4::jsonb, $5::jsonb, $6::jsonb, $7::jsonb, $8::jsonb, $9::jsonb, $10::jsonb)
            ON CONFLICT (ticker)
            DO UPDATE SET
                status = EXCLUDED.status,
                income_statement = EXCLUDED.income_statement,
                balance_sheet_statement = EXCLUDED.balance_sheet_statement,
                cash_flow_statement = EXCLUDED.cash_flow_statement,
                key_metrics = EXCLUDED.key_metrics,
                financial_ratios = EXCLUDED.financial_ratios,
                quote = EXCLUDED.quote,
                historical_price = EXCLUDED.historical_price,
                historical_market_cap = EXCLUDED.historical_market_cap
            """,
            record.get("ticker"),
            to_jsonb(record.get("status")),
            to_jsonb(record.get("income_statement")),
            to_jsonb(record.get("balance_sheet_statement")),
            to_jsonb(record.get("cash_flow_statement")),
            to_jsonb(record.get("key_metrics")),
            to_jsonb(record.get("financial_ratios")),
            to_jsonb(record.get("quote")),
            to_jsonb(record.get("historical_price")),
            to_jsonb(record.get("historical_market_cap")),
        )
