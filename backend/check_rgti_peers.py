"""Check RGTI peer tickers."""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.database.connection import db_pool


async def check_peers():
    """Check if RGTI has peer tickers."""

    pool = await db_pool.get_pool()
    conn = await pool.acquire()

    try:
        # Check RGTI sector and industry
        row = await conn.fetchrow("""
            SELECT ticker, sector, industry
            FROM config_lv3_targets
            WHERE ticker = 'RGTI'
        """)

        if row:
            print(f"\n=== RGTI Info ===")
            print(f"Ticker: {row['ticker']}")
            print(f"Sector: {row['sector']}")
            print(f"Industry: {row['industry']}")
        else:
            print("\nRGTI not found in config_lv3_targets!")
            return

        # Check peer count (same sector)
        peer_count = await conn.fetchval("""
            SELECT COUNT(*)
            FROM config_lv3_targets
            WHERE sector = $1 AND ticker != 'RGTI'
        """, row['sector'])

        print(f"\n=== Peer Tickers (Same Sector) ===")
        print(f"Total peers in sector '{row['sector']}': {peer_count}")

        # Show some example peers
        peers = await conn.fetch("""
            SELECT ticker, sector, industry
            FROM config_lv3_targets
            WHERE sector = $1 AND ticker != 'RGTI'
            LIMIT 10
        """, row['sector'])

        print(f"\nExample peers:")
        for peer in peers:
            print(f"  - {peer['ticker']}: {peer['industry']}")

        # Check if API endpoint exists for peers
        api_check = await conn.fetchrow("""
            SELECT id, api_service, endpoint, description
            FROM config_lv1_api_list
            WHERE id = 'fmp-stock-peers'
        """)

        print(f"\n=== FMP Stock Peers API ===")
        if api_check:
            print(f"API ID: {api_check['id']}")
            print(f"Service: {api_check['api_service']}")
            print(f"Endpoint: {api_check['endpoint']}")
            print(f"Description: {api_check['description']}")
        else:
            print("fmp-stock-peers API not configured!")

    finally:
        await pool.release(conn)
        await pool.close()


if __name__ == '__main__':
    asyncio.run(check_peers())
