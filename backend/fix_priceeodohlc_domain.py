"""Fix priceEodOHLC domain to quantitative-momentum."""
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
    print("FIXING priceEodOHLC DOMAIN")
    print("=" * 80)

    # Check current state
    row = await conn.fetchrow('''
        SELECT id, domain, source, api_list_id, response_key
        FROM config_lv2_metric
        WHERE id = 'priceEodOHLC'
    ''')

    print("\n[BEFORE]")
    print(f"  domain: {row['domain']}")
    print(f"  source: {row['source']}")
    print(f"  api_list_id: {row['api_list_id']}")
    print(f"  response_key: {row['response_key']}")

    # Update domain to quantitative-momentum (since it's price trend data)
    await conn.execute('''
        UPDATE config_lv2_metric
        SET domain = 'quantitative-momentum'
        WHERE id = 'priceEodOHLC'
    ''')

    # Verify update
    row = await conn.fetchrow('''
        SELECT id, domain, source, api_list_id, response_key
        FROM config_lv2_metric
        WHERE id = 'priceEodOHLC'
    ''')

    print("\n[AFTER]")
    print(f"  domain: {row['domain']}")
    print(f"  source: {row['source']}")
    print(f"  api_list_id: {row['api_list_id']}")
    print(f"  response_key: {row['response_key']}")

    print("\n✓ priceEodOHLC domain updated to 'quantitative-momentum'")
    print("  This ensures it's included in normal metric calculation flow")

    await conn.close()


if __name__ == '__main__':
    asyncio.run(main())
