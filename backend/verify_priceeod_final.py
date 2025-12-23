"""Verify priceEodOHLC is correctly configured and will be loaded."""
import asyncio
import asyncpg


async def main():
    conn = await asyncpg.connect(
        user='postgres.fgypclaqxonwxlmqdphx',
        password='qycKXqvs@!Q_Pt3',
        host='aws-1-ap-south-1.pooler.supabase.com',
        port=6543,
        database='postgres',
        statement_cache_size=0
    )

    print("=" * 80)
    print("VERIFICATION: priceEodOHLC Configuration")
    print("=" * 80)

    # Check priceEodOHLC
    row = await conn.fetchrow('''
        SELECT id, domain, source, api_list_id, response_key
        FROM config_lv2_metric
        WHERE id = 'priceEodOHLC'
    ''')

    if not row:
        print("\n[CRITICAL ERROR] priceEodOHLC NOT FOUND")
        await conn.close()
        return

    print("\n[priceEodOHLC Current State]")
    print(f"  id: {row['id']}")
    print(f"  domain: {row['domain']}")
    print(f"  source: {row['source']}")
    print(f"  api_list_id: {row['api_list_id']}")
    print(f"  response_key: {row['response_key']}")

    # Check if it matches the query
    print("\n[Checking against SELECT query]")
    match_count = await conn.fetchval('''
        SELECT COUNT(*)
        FROM config_lv2_metric
        WHERE id = 'priceEodOHLC'
          AND (domain LIKE 'quantitative-%'
               OR domain LIKE 'qualitative-%'
               OR domain = 'internal')
    ''')

    if match_count > 0:
        print(f"  OK: priceEodOHLC matches query (count: {match_count})")
    else:
        print(f"  ERROR: priceEodOHLC does NOT match query!")
        print(f"    Current domain: {row['domain']}")
        print(f"    Expected: domain LIKE 'quantitative-%' OR 'qualitative-%' OR = 'internal'")

    # Get all quantitative-momentum metrics
    print("\n[All quantitative-momentum metrics]")
    momentum_metrics = await conn.fetch('''
        SELECT id, source, api_list_id
        FROM config_lv2_metric
        WHERE domain = 'quantitative-momentum'
        ORDER BY id
    ''')

    print(f"  Found {len(momentum_metrics)} metrics:")
    for m in momentum_metrics:
        print(f"    - {m['id']} (source: {m['source']}, api: {m['api_list_id']})")

    # Count all metrics that should be loaded
    print("\n[Total metrics that will be loaded]")
    total = await conn.fetchval('''
        SELECT COUNT(*)
        FROM config_lv2_metric
        WHERE domain LIKE 'quantitative-%'
           OR domain LIKE 'qualitative-%'
           OR domain = 'internal'
    ''')

    print(f"  Total metrics: {total}")
    print(f"  Expected in logs: {total}")

    await conn.close()


if __name__ == '__main__':
    asyncio.run(main())
