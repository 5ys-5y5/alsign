"""Test RGTI backfill and capture all logs to check for issues"""
import asyncio
import logging
from src.database.connection import db_pool
from src.services import valuation_service

# Configure logging to capture everything
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    force=True
)

# Also set the alsign logger explicitly
alsign_logger = logging.getLogger("alsign")
alsign_logger.setLevel(logging.INFO)

async def test():
    pool = await db_pool.get_pool()

    print("\n" + "="*80)
    print("Testing: POST /backfillEventsTable?overwrite=true&tickers=rgti")
    print("="*80)
    print("Expected:")
    print("  1. Only RGTI ticker in API calls")
    print("  2. Log format: [table: txn_events | id: ...] | [API Call] ...")
    print("="*80 + "\n")

    # Run the same operation as the endpoint
    result = await valuation_service.calculate_valuations(
        overwrite=True,
        tickers=['RGTI'],
        calc_fair_value=True
    )

    print("\n" + "="*80)
    print("RESULT SUMMARY")
    print("="*80)
    print(f"Total events: {result['summary']['totalEventsProcessed']}")
    print(f"Quantitative success: {result['summary']['quantitativeSuccess']}")
    print(f"Qualitative success: {result['summary']['qualitativeSuccess']}")
    print("="*80 + "\n")

    await db_pool.close()

if __name__ == '__main__':
    asyncio.run(test())
