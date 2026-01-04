"""Complete end-to-end test for RGTI priceQuantitative calculation."""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.database.connection import db_pool
from src.database.queries import metrics as metrics_queries
from src.services.valuation_service import (
    get_peer_tickers,
    calculate_sector_average_metrics,
    calculate_fair_value_for_ticker
)
from src.services.external_api import FMPAPIClient
from src.services.metric_engine import MetricCalculationEngine
from datetime import datetime


async def test_full_flow():
    print("\n" + "=" * 80)
    print("TESTING FULL RGTI priceQuantitative CALCULATION FLOW")
    print("=" * 80 + "\n")

    pool = await db_pool.get_pool()
    ticker = 'RGTI'
    event_date = datetime(2025, 12, 17)

    try:
        # Step 1: Get peer tickers
        print("STEP 1: Getting peer tickers...")
        peer_tickers = await get_peer_tickers(ticker)
        print(f"[OK] Found {len(peer_tickers)} peers: {peer_tickers}\n")

        # Step 2: Load metrics
        print("STEP 2: Loading metrics definitions...")
        metrics_by_domain = await metrics_queries.select_metric_definitions(pool)
        print(f"[OK] Loaded {sum(len(v) for v in metrics_by_domain.values())} metrics\n")

        # Step 3: Calculate sector averages
        print("STEP 3: Calculating sector averages...")
        sector_averages = await calculate_sector_average_metrics(
            pool, peer_tickers, event_date, metrics_by_domain
        )
        print(f"[OK] Sector averages: {sector_averages}\n")

        # Step 4: Get RGTI's own metrics (PER, PBR, EPS, BPS)
        print("STEP 4: Calculating RGTI's own quantitative metrics...")
        transforms = await metrics_queries.select_metric_transforms(pool)
        engine = MetricCalculationEngine(metrics_by_domain, transforms)
        engine.build_dependency_graph()
        engine.topological_sort()

        # Fetch RGTI API data
        required_apis = engine.get_required_apis()
        api_cache = {}

        async with FMPAPIClient() as fmp_client:
            for api_id in required_apis:
                params = {'ticker': ticker}
                if 'income-statement' in api_id or 'balance-sheet' in api_id or 'cash-flow' in api_id:
                    params['period'] = 'quarter'
                    params['limit'] = 20
                elif 'historical-market-cap' in api_id:
                    params['fromDate'] = '2000-01-01'
                    params['toDate'] = event_date.strftime('%Y-%m-%d')

                response = await fmp_client.call_api(api_id, params)
                if response:
                    api_cache[api_id] = response

        # Calculate RGTI metrics
        result = engine.calculate_all(api_cache, ['valuation'])
        value_quantitative = result
        print(f"[OK] RGTI valuation metrics: {value_quantitative.get('valuation', {})}\n")

        # Step 5: Get current price
        print("STEP 5: Getting current price...")
        current_price_row = await pool.fetchrow('''
            SELECT value_qualitative->'currentPrice' as price
            FROM txn_events
            WHERE ticker = $1 AND event_date = $2 AND source = 'consensus'
        ''', ticker, event_date)

        if current_price_row and current_price_row['price']:
            current_price = float(current_price_row['price'])
            print(f"[OK] Current price: ${current_price}\n")
        else:
            print("[ERROR] Current price not found!\n")
            return

        # Step 6: Calculate fair value
        print("STEP 6: Calculating fair value...")
        result = await calculate_fair_value_for_ticker(
            pool, ticker, event_date, value_quantitative, current_price, metrics_by_domain
        )

        fair_value = result.get('fair_value')
        print(f"[OK] Fair value result:")
        print(f"  - fair_value: {fair_value}")
        print(f"  - position: {result.get('position')}")
        print(f"  - disparity: {result.get('disparity')}")
        print(f"  - peer_count: {result.get('peer_count')}")
        print(f"  - sector_averages: {result.get('sector_averages')}\n")

        # Step 7: Check database
        print("STEP 7: Checking database for priceQuantitative...")
        db_row = await pool.fetchrow('''
            SELECT value_quantitative->'valuation'->>'priceQuantitative' as price_quant
            FROM txn_events
            WHERE ticker = $1 AND event_date = $2 AND source = 'consensus'
        ''', ticker, event_date)

        if db_row:
            db_value = db_row['price_quant']
            print(f"Database value: {db_value}\n")

            if db_value is None:
                print("[WARNING] priceQuantitative is NULL in database even though calculation succeeded!")
            else:
                print(f"[OK] SUCCESS: priceQuantitative saved to database: {db_value}")
        else:
            print("[ERROR] No database record found!")

        print("\n" + "=" * 80)
        print("TEST COMPLETE")
        print("=" * 80)

    finally:
        await pool.close()


if __name__ == '__main__':
    asyncio.run(test_full_flow())
