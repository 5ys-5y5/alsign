"""Test API call logging with event_id"""
import asyncio
from src.database.connection import db_pool
from src.services import valuation_service

async def test():
    pool = await db_pool.get_pool()

    print("\n" + "="*80)
    print("Testing API call logging with event_id")
    print("="*80)
    print("Look for logs with format: [table: txn_events | id: ...] | [API Call] ...")
    print("="*80 + "\n")

    # Run backfill for a single ticker to see API logs
    result = await valuation_service.calculate_valuations(
        overwrite=True,
        tickers=['RGTI'],
        calc_fair_value=True
    )

    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"Total events: {result['summary']['totalEventsProcessed']}")
    print(f"Quantitative success: {result['summary']['quantitativeSuccess']}")
    print(f"Qualitative success: {result['summary']['qualitativeSuccess']}")
    print()

    await db_pool.close()

if __name__ == '__main__':
    asyncio.run(test())
