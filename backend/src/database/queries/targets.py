"""Database queries for company targets (config_lv3_targets table)."""

import asyncpg
import json
import logging
from typing import List, Dict, Any

logger = logging.getLogger("alsign")


async def truncate_and_insert_company_targets(
    pool: asyncpg.Pool,
    companies: List[Dict[str, Any]]
) -> Dict[str, int]:
    """
    Truncate config_lv3_targets table and insert fresh company targets.

    IMPORTANT: Deletes all existing data before inserting new data.
    Filters out non-actively trading companies.

    Args:
        pool: Database connection pool
        companies: List of company dictionaries from FMP screener

    Returns:
        Dict with insert count

    Table columns (never write to updated_at):
    - ticker (text, PK)
    - sector (text, nullable)
    - industry (text, nullable)
    - response_key (jsonb)
    - updated_at (timestamptz, DB-managed)
    """
    logger.info("=" * 80)
    logger.info("[truncate_and_insert_company_targets] FUNCTION START")
    logger.info(f"[truncate_and_insert_company_targets] Parameters:")
    logger.info(f"[truncate_and_insert_company_targets]   - pool type: {type(pool)}")
    logger.info(f"[truncate_and_insert_company_targets]   - companies type: {type(companies)}")
    logger.info(f"[truncate_and_insert_company_targets]   - companies length: {len(companies) if companies else 0}")
    logger.info("=" * 80)

    insert_count = 0

    if not companies:
        logger.error("[truncate_and_insert_company_targets] CRITICAL: companies is empty!")
        logger.error(f"[truncate_and_insert_company_targets] companies value: {companies}")
        logger.info("=" * 80)
        logger.info("[truncate_and_insert_company_targets] FUNCTION END - No companies to insert")
        logger.info("=" * 80)
        return {"insert": 0, "update": 0}

    logger.info(f"[truncate_and_insert_company_targets] First company in list:")
    logger.info(f"[truncate_and_insert_company_targets]   Type: {type(companies[0])}")
    logger.info(f"[truncate_and_insert_company_targets]   Keys: {list(companies[0].keys()) if isinstance(companies[0], dict) else 'N/A'}")
    logger.info(f"[truncate_and_insert_company_targets]   Sample: {str(companies[0])[:300]}")

    async with pool.acquire() as conn:
        logger.info(f"[truncate_and_insert_company_targets] Step 1: Acquired DB connection, type: {type(conn)}")

        async with conn.transaction():
            logger.info("[truncate_and_insert_company_targets] Step 2: Started transaction")

            # TRUNCATE table (delete all existing data)
            logger.info("[truncate_and_insert_company_targets] Step 3: Executing TRUNCATE TABLE config_lv3_targets")
            await conn.execute("TRUNCATE TABLE config_lv3_targets")
            logger.info("[truncate_and_insert_company_targets] Step 4: TRUNCATE completed successfully")

            # Insert new data
            logger.info(f"[truncate_and_insert_company_targets] Step 5: Starting to insert {len(companies)} companies")

            for idx, company in enumerate(companies):
                # Log every 500 companies
                if idx % 500 == 0:
                    logger.info(f"[truncate_and_insert_company_targets] Progress: {idx}/{len(companies)} companies processed")

                # Filter out non-actively trading companies
                is_active = company.get('isActivelyTrading', True)
                if not is_active:
                    logger.debug(f"[truncate_and_insert_company_targets] Skipping inactive company: {company.get('ticker')}")
                    continue

                # Schema mapping converts 'symbol' -> 'ticker'
                ticker = company.get('ticker')
                if not ticker:
                    logger.warning(f"[truncate_and_insert_company_targets] Skipping company with no ticker: {str(company)[:100]}")
                    continue

                # Insert company
                try:
                    await conn.execute(
                        """
                        INSERT INTO config_lv3_targets (ticker, sector, industry, response_key)
                        VALUES ($1, $2, $3, $4)
                        """,
                        ticker.upper(),
                        company.get('sector'),
                        company.get('industry'),
                        json.dumps(company)
                    )
                    insert_count += 1
                except Exception as e:
                    logger.error(f"[truncate_and_insert_company_targets] Failed to insert {ticker}: {type(e).__name__}: {str(e)}")

            logger.info(f"[truncate_and_insert_company_targets] Step 6: Insertion loop completed")
            logger.info(f"[truncate_and_insert_company_targets] Total inserted: {insert_count}")
            logger.info(f"[truncate_and_insert_company_targets] Step 7: Committing transaction")

    logger.info("=" * 80)
    logger.info(f"[truncate_and_insert_company_targets] FUNCTION END")
    logger.info(f"[truncate_and_insert_company_targets] Result: Insert={insert_count}, Update=0")
    logger.info("=" * 80)

    return {"insert": insert_count, "update": 0}


async def upsert_company_targets(
    pool: asyncpg.Pool,
    companies: List[Dict[str, Any]]
) -> Dict[str, int]:
    """
    DEPRECATED: Use truncate_and_insert_company_targets instead.

    This function is kept for backward compatibility but should not be used.
    The requirement is to truncate and insert fresh data on each call.
    """
    logger.info("[upsert_company_targets] Called - Redirecting to truncate_and_insert_company_targets")
    return await truncate_and_insert_company_targets(pool, companies)


async def get_all_tickers(pool: asyncpg.Pool) -> List[str]:
    """
    Get all ticker symbols from config_lv3_targets.

    Args:
        pool: Database connection pool

    Returns:
        List of ticker symbols
    """
    logger.info("[get_all_tickers] Fetching all tickers from config_lv3_targets")
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT ticker FROM config_lv3_targets")
        ticker_list = [row['ticker'] for row in rows]
        logger.info(f"[get_all_tickers] Fetched {len(ticker_list)} tickers")
        return ticker_list


async def get_company_info(pool: asyncpg.Pool, ticker: str) -> Dict[str, Any]:
    """
    Get sector and industry for a ticker from config_lv3_targets.

    Args:
        pool: Database connection pool
        ticker: Ticker symbol

    Returns:
        Dict with 'sector' and 'industry' keys, or empty dict if not found
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT sector, industry FROM config_lv3_targets WHERE ticker = $1",
            ticker.upper()
        )
        if row:
            return {
                'sector': row['sector'],
                'industry': row['industry']
            }
        return {}
