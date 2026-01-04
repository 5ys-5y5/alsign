"""
Performance test for POST /backfillEventsTable optimization.

Tests the performance improvement from caching peer data at ticker level.
"""
import asyncio
import time
from src.database.connection import db_pool
from src.services.valuation_service import calculate_valuations

async def test_performance():
    """Test backfill performance with a small dataset."""
    print("=" * 80)
    print("PERFORMANCE TEST: POST /backfillEventsTable")
    print("=" * 80)

    # Test with RGTI ticker (known to have multiple events)
    test_params = {
        'overwrite': True,
        'from_date': '2025-12-17',
        'to_date': '2025-12-17',
        'tickers': ['RGTI'],
        'calc_fair_value': True,  # This triggers priceQuantitative calculation
        'metrics_list': None
    }

    print(f"\nTest Parameters:")
    print(f"  Ticker: {test_params['tickers']}")
    print(f"  Date Range: {test_params['from_date']} to {test_params['to_date']}")
    print(f"  calc_fair_value: {test_params['calc_fair_value']}")
    print()

    start_time = time.time()

    try:
        result = await calculate_valuations(**test_params)

        elapsed = time.time() - start_time

        print(f"\n{'='*80}")
        print(f"RESULTS:")
        print(f"{'='*80}")
        print(f"  Total Time: {elapsed:.2f}s")
        print(f"  Events Processed: {result['summary']['quantitativeSuccess'] + result['summary']['quantitativeFail']}")
        print(f"  Success: {result['summary']['quantitativeSuccess']}")
        print(f"  Failed: {result['summary']['quantitativeFail']}")
        print(f"  Avg Time/Event: {elapsed / max(1, result['summary']['quantitativeSuccess'] + result['summary']['quantitativeFail']):.3f}s")
        print()

        # Check if priceQuantitative was calculated
        if result['results']:
            first_result = result['results'][0]
            print(f"Sample Event:")
            print(f"  Ticker: {first_result.ticker}")
            print(f"  Date: {first_result.event_date}")
            print(f"  Status: {first_result.status}")

        print(f"\n{'='*80}")
        print("PERFORMANCE NOTES:")
        print("  - Peer data fetched ONCE per ticker (not per event)")
        print("  - Expected: ~10-50x faster than before optimization")
        print("  - Check logs for '[PERF]' tags to verify caching")
        print(f"{'='*80}\n")

    except Exception as e:
        elapsed = time.time() - start_time
        print(f"\n{'='*80}")
        print(f"ERROR after {elapsed:.2f}s:")
        print(f"  {type(e).__name__}: {str(e)}")
        print(f"{'='*80}\n")
        raise

    await db_pool.close()

if __name__ == '__main__':
    asyncio.run(test_performance())
