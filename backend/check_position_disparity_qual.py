"""Check position_qualitative and disparity_qualitative columns"""
import asyncio
import asyncpg

async def check():
    env_vars = {}
    with open('.env') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, val = line.split('=', 1)
                env_vars[key.strip()] = val.strip().strip('"')

    conn = await asyncpg.connect(env_vars['DATABASE_URL'], statement_cache_size=0)

    print("\n" + "="*80)
    print("Checking position/disparity qualitative columns")
    print("="*80)

    # Check consensus event (should have qualitative data)
    consensus_row = await conn.fetchrow('''
        SELECT id::text, ticker, event_date::date, source,
               position_quantitative,
               position_qualitative,
               disparity_quantitative,
               disparity_qualitative,
               value_qualitative->>'value' as qual_value,
               value_qualitative->>'currentPrice' as current_price
        FROM txn_events
        WHERE id = $1
    ''', '1120c650-71fd-41f4-aa3d-2ea986214ed8')

    print("\nConsensus Event (ID: 1120c650-71fd-41f4-aa3d-2ea986214ed8):")
    print("-" * 80)
    print(f"Source: {consensus_row['source']}")
    print(f"Date: {consensus_row['event_date']}")
    print(f"position_quantitative: {consensus_row['position_quantitative']}")
    print(f"position_qualitative: {consensus_row['position_qualitative']}")
    print(f"disparity_quantitative: {consensus_row['disparity_quantitative']}")
    print(f"disparity_qualitative: {consensus_row['disparity_qualitative']}")
    print(f"value_qualitative.value: {consensus_row['qual_value']}")
    print(f"value_qualitative.currentPrice: {consensus_row['current_price']}")

    # Check earning event (should NOT have qualitative data)
    earning_row = await conn.fetchrow('''
        SELECT id::text, ticker, event_date::date, source,
               position_quantitative,
               position_qualitative,
               disparity_quantitative,
               disparity_qualitative,
               value_qualitative->>'value' as qual_value,
               value_qualitative->>'currentPrice' as current_price
        FROM txn_events
        WHERE id = $1
    ''', 'c9690674-d4a1-406f-9959-540bdb2f72f0')

    print("\nEarning Event (ID: c9690674-d4a1-406f-9959-540bdb2f72f0):")
    print("-" * 80)
    print(f"Source: {earning_row['source']}")
    print(f"Date: {earning_row['event_date']}")
    print(f"position_quantitative: {earning_row['position_quantitative']}")
    print(f"position_qualitative: {earning_row['position_qualitative']}")
    print(f"disparity_quantitative: {earning_row['disparity_quantitative']}")
    print(f"disparity_qualitative: {earning_row['disparity_qualitative']}")
    print(f"value_qualitative.value: {earning_row['qual_value']}")
    print(f"value_qualitative.currentPrice: {earning_row['current_price']}")

    # Statistics
    print("\n" + "="*80)
    print("STATISTICS (all consensus events)")
    print("="*80)

    stats = await conn.fetchrow('''
        SELECT COUNT(*) as total,
               COUNT(position_quantitative) as pos_quant_filled,
               COUNT(position_qualitative) as pos_qual_filled,
               COUNT(disparity_quantitative) as disp_quant_filled,
               COUNT(disparity_qualitative) as disp_qual_filled
        FROM txn_events
        WHERE ticker = 'RGTI'
          AND source = 'consensus'
    ''')

    total = stats['total']
    print(f"\nTotal consensus events: {total}")
    print(f"position_quantitative:  {stats['pos_quant_filled']}/{total} ({stats['pos_quant_filled']/total*100 if total > 0 else 0:.1f}%)")
    print(f"position_qualitative:   {stats['pos_qual_filled']}/{total} ({stats['pos_qual_filled']/total*100 if total > 0 else 0:.1f}%)")
    print(f"disparity_quantitative: {stats['disp_quant_filled']}/{total} ({stats['disp_quant_filled']/total*100 if total > 0 else 0:.1f}%)")
    print(f"disparity_qualitative:  {stats['disp_qual_filled']}/{total} ({stats['disp_qual_filled']/total*100 if total > 0 else 0:.1f}%)")

    if stats['pos_qual_filled'] == 0 or stats['disp_qual_filled'] == 0:
        print("\n[PROBLEM] position_qualitative and/or disparity_qualitative are NULL!")

    print("="*80 + "\n")

    await conn.close()

if __name__ == '__main__':
    asyncio.run(check())
