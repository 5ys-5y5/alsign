"""Test sector average calculation for RGTI peers."""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.database.connection import db_pool
from src.database.queries import metrics as metrics_queries
from src.services.valuation_service import (
    get_peer_tickers,
    calculate_sector_average_metrics
)
from datetime import datetime


async def test():
    print("\n=== Testing Sector Average Calculation for RGTI ===\n")

    pool = await db_pool.get_pool()

    try:
        # 1. Get peer tickers
        print("1. Getting peer tickers...")
        peer_tickers = await get_peer_tickers('RGTI')
        print(f"   Found {len(peer_tickers)} peers: {peer_tickers}\n")

        if not peer_tickers:
            print("ERROR: No peer tickers found!")
            return

        # 2. Load metrics definitions
        print("2. Loading metrics definitions...")
        metrics_by_domain = await metrics_queries.select_metric_definitions(pool)
        print(f"   Loaded {sum(len(v) for v in metrics_by_domain.values())} metrics\n")

        # 3. Calculate sector averages
        print("3. Calculating sector averages...")
        event_date = datetime(2025, 12, 17)  # Latest RGTI consensus event date

        sector_averages = await calculate_sector_average_metrics(
            pool, peer_tickers, event_date, metrics_by_domain
        )

        print(f"   Sector averages: {sector_averages}\n")

        if not sector_averages:
            print("ERROR: Sector averages calculation returned empty dict!")
            print("This means no valid PER/PBR values were collected from peer tickers.")
        else:
            print(f"SUCCESS: Calculated sector averages for {len(sector_averages)} metrics")
            for metric, avg_value in sector_averages.items():
                print(f"  - {metric}: {avg_value:.2f}")

    finally:
        await pool.close()


if __name__ == '__main__':
    asyncio.run(test())
