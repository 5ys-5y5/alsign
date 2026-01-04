"""Test backfill for RGTI consensus events to verify position/disparity columns"""
import asyncio
from src.database.connection import db_pool
from src.services import valuation_service

async def test():
    pool = await db_pool.get_pool()

    print("\n" + "="*80)
    print("BEFORE BACKFILL - Checking current state")
    print("="*80)

    # Check current state
    rows = await pool.fetch('''
        SELECT COUNT(*) as total,
               COUNT(price_quantitative) as price_filled,
               COUNT(position_quantitative) as pos_filled,
               COUNT(disparity_quantitative) as disp_filled
        FROM txn_events
        WHERE ticker = $1
          AND source = 'consensus'
    ''', 'RGTI')

    if rows:
        row = rows[0]
        print(f"Total consensus events: {row['total']}")
        print(f"price_quantitative: {row['price_filled']}/{row['total']} ({row['price_filled']/row['total']*100 if row['total'] > 0 else 0:.1f}%)")
        print(f"position_quantitative: {row['pos_filled']}/{row['total']} ({row['pos_filled']/row['total']*100 if row['total'] > 0 else 0:.1f}%)")
        print(f"disparity_quantitative: {row['disp_filled']}/{row['total']} ({row['disp_filled']/row['total']*100 if row['total'] > 0 else 0:.1f}%)")

    print("\n" + "="*80)
    print("RUNNING BACKFILL with overwrite=True")
    print("="*80)

    # Run backfill
    result = await valuation_service.calculate_valuations(
        overwrite=True,
        tickers=['RGTI'],
        calc_fair_value=True
    )

    print("\n" + "="*80)
    print("BACKFILL SUMMARY")
    print("="*80)
    print(f"Total events: {result['summary']['totalEventsProcessed']}")
    print(f"Quant success: {result['summary']['quantitativeSuccess']}")
    print(f"Qual success: {result['summary']['qualitativeSuccess']}")

    print("\n" + "="*80)
    print("AFTER BACKFILL - Verifying columns")
    print("="*80)

    # Check after backfill
    rows = await pool.fetch('''
        SELECT COUNT(*) as total,
               COUNT(price_quantitative) as price_filled,
               COUNT(position_quantitative) as pos_filled,
               COUNT(disparity_quantitative) as disp_filled
        FROM txn_events
        WHERE ticker = $1
          AND source = 'consensus'
    ''', 'RGTI')

    if rows:
        row = rows[0]
        print(f"Total consensus events: {row['total']}")
        print(f"price_quantitative: {row['price_filled']}/{row['total']} ({row['price_filled']/row['total']*100 if row['total'] > 0 else 0:.1f}%)")
        print(f"position_quantitative: {row['pos_filled']}/{row['total']} ({row['pos_filled']/row['total']*100 if row['total'] > 0 else 0:.1f}%)")
        print(f"disparity_quantitative: {row['disp_filled']}/{row['total']} ({row['disp_filled']/row['total']*100 if row['total'] > 0 else 0:.1f}%)")

    # Show sample data
    print("\n" + "="*80)
    print("SAMPLE DATA")
    print("="*80)

    sample = await pool.fetch('''
        SELECT id::text as event_id,
               ticker,
               event_date::date,
               price_quantitative,
               position_quantitative,
               disparity_quantitative
        FROM txn_events
        WHERE ticker = $1
          AND source = 'consensus'
        ORDER BY event_date DESC
        LIMIT 5
    ''', 'RGTI')

    print(f"\n{'DATE':<12} {'PRICE':<10} {'POSITION':<10} {'DISPARITY':<10} {'EVENT_ID':<40}")
    print("-" * 90)
    for row in sample:
        price_val = f"{row['price_quantitative']:.2f}" if row['price_quantitative'] is not None else "NULL"
        pos_val = str(row['position_quantitative']) if row['position_quantitative'] is not None else "NULL"
        disp_val = f"{row['disparity_quantitative']:.2f}" if row['disparity_quantitative'] is not None else "NULL"
        event_id_short = row['event_id'][:8] + "..."
        print(f"{str(row['event_date']):<12} {price_val:<10} {pos_val:<10} {disp_val:<10} {event_id_short:<40}")

    print()

    await db_pool.close()

if __name__ == '__main__':
    asyncio.run(test())
