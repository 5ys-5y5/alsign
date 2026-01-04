"""Check position_quantitative and disparity_quantitative for consensus events"""
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
    print("CONSENSUS EVENTS - Position/Disparity Check")
    print("="*80)

    # Check consensus events
    rows = await conn.fetch('''
        SELECT id, ticker, event_date::date,
               price_quantitative,
               position_quantitative,
               disparity_quantitative,
               value_quantitative->'valuation'->>'positionQuantitative' as jsonb_position,
               value_quantitative->'valuation'->>'disparityQuantitative' as jsonb_disparity
        FROM txn_events
        WHERE ticker = $1
          AND source = 'consensus'
        ORDER BY event_date DESC
        LIMIT 10
    ''', 'RGTI')

    print(f"\nFound {len(rows)} consensus events:\n")
    print(f"{'DATE':<12} {'PRICE_Q':<10} {'POS_COL':<10} {'POS_JSONB':<10} {'DISP_COL':<10} {'DISP_JSONB':<10}")
    print("-" * 80)

    for row in rows:
        price_q = f"{float(row['price_quantitative']):.2f}" if row['price_quantitative'] is not None else "NULL"

        # Handle both numeric and string types
        try:
            pos_col = f"{float(row['position_quantitative']):.2f}" if row['position_quantitative'] is not None else "NULL"
        except (ValueError, TypeError):
            pos_col = str(row['position_quantitative']) if row['position_quantitative'] is not None else "NULL"

        pos_jsonb = row['jsonb_position'] if row['jsonb_position'] else "NULL"

        try:
            disp_col = f"{float(row['disparity_quantitative']):.2f}" if row['disparity_quantitative'] is not None else "NULL"
        except (ValueError, TypeError):
            disp_col = str(row['disparity_quantitative']) if row['disparity_quantitative'] is not None else "NULL"

        disp_jsonb = row['jsonb_disparity'] if row['jsonb_disparity'] else "NULL"

        print(f"{str(row['event_date']):<12} {price_q:<10} {pos_col:<10} {pos_jsonb:<10} {disp_col:<10} {disp_jsonb:<10}")

    # Summary stats
    stats = await conn.fetchrow('''
        SELECT COUNT(*) as total,
               COUNT(price_quantitative) as price_filled,
               COUNT(position_quantitative) as pos_filled,
               COUNT(disparity_quantitative) as disp_filled
        FROM txn_events
        WHERE ticker = $1
          AND source = 'consensus'
    ''', 'RGTI')

    print("\n" + "="*80)
    print("SUMMARY:")
    print("="*80)
    print(f"Total consensus events: {stats['total']}")
    print(f"price_quantitative filled: {stats['price_filled']}/{stats['total']} ({stats['price_filled']/stats['total']*100 if stats['total'] > 0 else 0:.1f}%)")
    print(f"position_quantitative filled: {stats['pos_filled']}/{stats['total']} ({stats['pos_filled']/stats['total']*100 if stats['total'] > 0 else 0:.1f}%)")
    print(f"disparity_quantitative filled: {stats['disp_filled']}/{stats['total']} ({stats['disp_filled']/stats['total']*100 if stats['total'] > 0 else 0:.1f}%)")
    print()

    await conn.close()

if __name__ == '__main__':
    asyncio.run(check())
