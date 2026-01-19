"""Database queries for market holidays (config_lv3_market_holidays table)."""

import asyncpg
from typing import List, Dict, Any
from datetime import date


async def upsert_market_holidays(
    pool: asyncpg.Pool,
    holidays: List[Dict[str, Any]]
) -> Dict[str, int]:
    """
    Upsert market holidays to config_lv3_market_holidays table.

    Uses ON CONFLICT (exchange, date) DO UPDATE strategy.

    Args:
        pool: Database connection pool
        holidays: List of holiday dictionaries with keys: exchange, date, name, is_closed, etc.

    Returns:
        Dict with insert and update counts

    Table columns (never write to updated_at):
    - exchange (text, PK)
    - date (date, PK)
    - name (text)
    - is_closed (boolean)
    - adj_open_time (time, nullable)
    - adj_close_time (time, nullable)
    - is_fully_closed (boolean)
    - updated_at (timestamptz, DB-managed)
    """
    insert_count = 0
    update_count = 0

    async with pool.acquire() as conn:
        for holiday in holidays:
            # Map FMP API camelCase to snake_case
            is_closed = holiday.get('isClosed')
            if is_closed is None:
                is_closed = holiday.get('is_closed', True)

            is_fully_closed = holiday.get('isFullyClosed')
            if is_fully_closed is None:
                is_fully_closed = holiday.get('is_fully_closed', is_closed)

            # Upsert holiday
            result = await conn.execute(
                """
                INSERT INTO config_lv3_market_holidays (exchange, date, name, is_closed, adj_open_time, adj_close_time, is_fully_closed)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (exchange, date)
                DO UPDATE SET
                    name = EXCLUDED.name,
                    is_closed = EXCLUDED.is_closed,
                    adj_open_time = EXCLUDED.adj_open_time,
                    adj_close_time = EXCLUDED.adj_close_time,
                    is_fully_closed = EXCLUDED.is_fully_closed,
                    updated_at = NOW()
                """,
                holiday.get('exchange', 'NASDAQ'),
                holiday['date'] if isinstance(holiday['date'], date) else date.fromisoformat(holiday['date']),
                holiday.get('name', ''),
                is_closed,
                holiday.get('adjOpenTime') or holiday.get('adj_open_time'),
                holiday.get('adjCloseTime') or holiday.get('adj_close_time'),
                is_fully_closed
            )

            # Count inserts vs updates (asyncpg returns "INSERT 0 1" or "UPDATE 0 1")
            if "INSERT" in result:
                insert_count += 1
            elif "UPDATE" in result:
                update_count += 1

    return {"insert": insert_count, "update": update_count}
