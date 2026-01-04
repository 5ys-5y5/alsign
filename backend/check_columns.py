"""Check if price_quantitative and peer_quantitative columns are populated"""
import asyncio
import asyncpg
import os

async def check_data():
    # Load .env
    env_vars = {}
    with open('.env') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, val = line.split('=', 1)
                env_vars[key.strip()] = val.strip().strip('"')

    conn = await asyncpg.connect(env_vars['DATABASE_URL'], statement_cache_size=0)

    # Check data
    rows = await conn.fetch('''
        SELECT
            ticker,
            event_date::date,
            source,
            SUBSTRING(source_id::text, 1, 8) as source_id_short,
            price_quantitative,
            peer_quantitative->>'peerCount' as peer_count,
            (value_quantitative->'valuation'->>'priceQuantitative')::numeric as jsonb_price
        FROM txn_events
        WHERE ticker = $1
          AND source = $2
        ORDER BY event_date DESC
        LIMIT 10
    ''', 'RGTI', 'consensus')

    print(f'\n{"="*70}')
    print(f'Found {len(rows)} consensus events for RGTI')
    print(f'{"="*70}\n')
    print(f'{"DATE":<12} {"SRC_ID":<10} {"PRICE_COL":<12} {"JSONB":<12} {"PEERS":<8} {"OK":<4}')
    print('-' * 70)

    for row in rows:
        price_col = row['price_quantitative']
        jsonb_price = row['jsonb_price']
        peer_count = row['peer_count'] if row['peer_count'] else '0'
        match = 'YES' if price_col == jsonb_price else ('NO' if price_col and jsonb_price else '-')

        print(f'{str(row["event_date"]):<12} {row["source_id_short"]:<10} {str(price_col)[:12]:<12} {str(jsonb_price)[:12]:<12} {peer_count:<8} {match:<4}')

    print('\n')

    # Check earning events too
    earning_rows = await conn.fetch('''
        SELECT
            COUNT(*) as total,
            COUNT(price_quantitative) as price_filled,
            COUNT(peer_quantitative) as peer_filled
        FROM txn_events
        WHERE ticker = $1
          AND source = $2
    ''', 'RGTI', 'earning')

    if earning_rows:
        row = earning_rows[0]
        print(f'{"="*70}')
        print(f'EARNING events for RGTI')
        print(f'{"="*70}')
        print(f'Total events: {row["total"]}')
        print(f'price_quantitative filled: {row["price_filled"]} ({row["price_filled"]/row["total"]*100 if row["total"] > 0 else 0:.1f}%)')
        print(f'peer_quantitative filled: {row["peer_filled"]} ({row["peer_filled"]/row["total"]*100 if row["total"] > 0 else 0:.1f}%)')
        print()

    await conn.close()

if __name__ == '__main__':
    asyncio.run(check_data())
