"""Debug why earning events have NULL price_quantitative"""
import asyncio
from src.database.connection import db_pool
from src.services import valuation_service

async def test():
    pool = await db_pool.get_pool()

    # Test with a small dataset - only earning events
    result = await valuation_service.calculate_valuations(
        overwrite=True,
        tickers=['RGTI'],
        calc_fair_value=True
    )

    print("\n" + "="*80)
    print("SUMMARY:")
    print("="*80)
    print(f"Total events: {result['summary']['totalEventsProcessed']}")
    print(f"Quant success: {result['summary']['quantitativeSuccess']}")
    print(f"Quant fail: {result['summary']['quantitativeFail']}")

    # Check which sources were processed
    sources = {}
    for r in result['results']:
        source = r.source
        sources[source] = sources.get(source, 0) + 1

    print(f"\nEvents by source:")
    for source, count in sources.items():
        print(f"  {source}: {count}")

    await db_pool.close()

if __name__ == '__main__':
    asyncio.run(test())
