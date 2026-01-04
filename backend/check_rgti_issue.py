"""Check RGTI position/disparity issue."""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.database.connection import db_pool
import json
from datetime import datetime


async def check_rgti():
    """Check RGTI txn_events for priceQuantitative and position/disparity values."""

    # Get DB pool from app
    pool = await db_pool.get_pool()
    conn = await pool.acquire()

    try:
        # Query RGTI consensus events
        rows = await conn.fetch("""
            SELECT
                ticker,
                event_date,
                source,
                source_id,
                value_quantitative->'valuation'->'priceQuantitative' as price_quant,
                position_quantitative,
                disparity_quantitative,
                position_qualitative,
                disparity_qualitative
            FROM txn_events
            WHERE ticker = 'RGTI' AND source = 'consensus'
            ORDER BY event_date DESC
            LIMIT 10
        """)

        print(f"\n=== RGTI Consensus Events (Latest 10) ===\n")

        for row in rows:
            print(f"Date: {row['event_date'].date()}")
            print(f"  priceQuantitative: {row['price_quant']}")
            print(f"  position_quantitative: {row['position_quantitative']}")
            print(f"  disparity_quantitative: {row['disparity_quantitative']}")
            print(f"  position_qualitative: {row['position_qualitative']}")
            print(f"  disparity_qualitative: {row['disparity_qualitative']}")
            print()

        # Check if priceQuantitative exists in value_quantitative
        rows2 = await conn.fetch("""
            SELECT
                event_date,
                value_quantitative::text
            FROM txn_events
            WHERE ticker = 'RGTI' AND source = 'consensus'
            ORDER BY event_date DESC
            LIMIT 3
        """)

        print(f"\n=== RGTI value_quantitative Structure (Latest 3) ===\n")
        for row in rows2:
            print(f"Date: {row['event_date'].date()}")
            try:
                vq = json.loads(row['value_quantitative']) if row['value_quantitative'] else {}
                if 'valuation' in vq:
                    print(f"  valuation keys: {list(vq['valuation'].keys())}")
                    print(f"  priceQuantitative in valuation: {'priceQuantitative' in vq['valuation']}")
                else:
                    print(f"  No 'valuation' domain found")
                print(f"  All domains: {list(vq.keys())}")
            except Exception as e:
                print(f"  Error parsing: {e}")
            print()

    finally:
        await pool.release(conn)
        await pool.close()


if __name__ == '__main__':
    asyncio.run(check_rgti())
