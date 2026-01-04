"""Final verification of all three issues"""
import asyncio
import asyncpg
import os

async def verify():
    env_vars = {}
    with open('.env') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, val = line.split('=', 1)
                env_vars[key.strip()] = val.strip().strip('"')

    conn = await asyncpg.connect(env_vars['DATABASE_URL'], statement_cache_size=0)

    print("\n" + "="*80)
    print("ISSUE 1: Abnormal values check")
    print("="*80)

    # Check for abnormal values
    rows = await conn.fetch('''
        SELECT ticker, source, COUNT(*) as total,
               AVG(price_quantitative) as avg_price,
               MIN(price_quantitative) as min_price,
               MAX(price_quantitative) as max_price
        FROM txn_events
        WHERE ticker = $1
          AND price_quantitative IS NOT NULL
        GROUP BY ticker, source
        ORDER BY source
    ''', 'RGTI')

    for row in rows:
        print(f"\n{row['source'].upper()} events:")
        print(f"  Total: {row['total']}")
        print(f"  Avg: {row['avg_price']:.2f}")
        print(f"  Range: {row['min_price']:.2f} ~ {row['max_price']:.2f}")
        if row['min_price'] < 0 or row['max_price'] > 1000:
            print(f"  WARNING: Abnormal values detected!")
        else:
            print(f"  OK: Values look normal")

    print("\n" + "="*80)
    print("ISSUE 2: Source-agnostic quantitative columns")
    print("="*80)

    # Check all sources
    rows = await conn.fetch('''
        SELECT source,
               COUNT(*) as total,
               COUNT(price_quantitative) as price_filled,
               COUNT(peer_quantitative) as peer_filled
        FROM txn_events
        WHERE ticker = $1
        GROUP BY source
        ORDER BY source
    ''', 'RGTI')

    for row in rows:
        price_pct = row['price_filled'] / row['total'] * 100 if row['total'] > 0 else 0
        peer_pct = row['peer_filled'] / row['total'] * 100 if row['total'] > 0 else 0
        print(f"\n{row['source'].upper()}: {row['total']} events")
        print(f"  price_quantitative: {row['price_filled']}/{row['total']} ({price_pct:.1f}%)")
        print(f"  peer_quantitative: {row['peer_filled']}/{row['total']} ({peer_pct:.1f}%)")
        if price_pct >= 90 and peer_pct >= 90:
            print(f"  PASS")
        else:
            print(f"  FAIL")

    print("\n" + "="*80)
    print("ISSUE 3: Sample earning event (with txn_events.id in log)")
    print("="*80)

    rows = await conn.fetch('''
        SELECT id, ticker, event_date::date, source,
               price_quantitative,
               peer_quantitative->>'peerCount' as peer_count
        FROM txn_events
        WHERE ticker = $1
          AND source = 'earning'
          AND price_quantitative IS NOT NULL
        LIMIT 5
    ''', 'RGTI')

    print(f"\nSample earning events with price_quantitative:")
    for row in rows:
        print(f"  [table: txn_events | id: {row['id']}]")
        print(f"    Date: {row['event_date']}, Price: {row['price_quantitative']:.2f}, Peers: {row['peer_count']}")

    print("\n" + "="*80)
    print("ALL CHECKS COMPLETED!")
    print("="*80 + "\n")

    await conn.close()

if __name__ == '__main__':
    asyncio.run(verify())
