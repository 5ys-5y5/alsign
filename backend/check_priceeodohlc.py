"""Check priceEodOHLC metric configuration in database."""
import asyncio
import asyncpg
import json


async def main():
    # Connect to database
    conn = await asyncpg.connect(
        user='postgres.fgypclaqxonwxlmqdphx',
        password='qycKXqvs@!Q_Pt3',
        host='aws-1-ap-south-1.pooler.supabase.com',
        port=6543,
        database='postgres'
    )

    print("=" * 80)
    print("CHECKING priceEodOHLC METRIC CONFIGURATION")
    print("=" * 80)

    # Check priceEodOHLC metric
    row = await conn.fetchrow('''
        SELECT id, domain, source, api_list_id, base_metric_id,
               expression, response_key, aggregation_kind, aggregation_params
        FROM config_lv2_metric
        WHERE id = 'priceEodOHLC'
    ''')

    if not row:
        print("\n[ERROR] priceEodOHLC metric NOT FOUND in config_lv2_metric")
        await conn.close()
        return

    print("\n[priceEodOHLC Metric Configuration]")
    print(f"  id: {row['id']}")
    print(f"  domain: {row['domain']}")
    print(f"  source: {row['source']}")
    print(f"  api_list_id: {row['api_list_id']}")
    print(f"  base_metric_id: {row['base_metric_id']}")
    print(f"  expression: {row['expression']}")
    print(f"  response_key: {row['response_key']}")
    print(f"  aggregation_kind: {row['aggregation_kind']}")
    print(f"  aggregation_params: {row['aggregation_params']}")

    # If api_list_id is set, check the API configuration
    if row['api_list_id']:
        print(f"\n[Checking API List: {row['api_list_id']}]")
        api_row = await conn.fetchrow('''
            SELECT id, provider_name, endpoint_path, http_method,
                   param_schema, response_schema
            FROM config_lv1_api_list
            WHERE id = $1
        ''', row['api_list_id'])

        if api_row:
            print(f"  ✓ API Found")
            print(f"    provider: {api_row['provider_name']}")
            print(f"    endpoint: {api_row['endpoint_path']}")
            print(f"    method: {api_row['http_method']}")
            print(f"    param_schema: {api_row['param_schema']}")
            print(f"    response_schema: {api_row['response_schema']}")
        else:
            print(f"  ✗ API NOT FOUND: {row['api_list_id']}")
    else:
        print(f"\n[WARNING] api_list_id is NULL")

    # Check what API is actually being used for OHLC data
    print(f"\n[Checking fmp-historical-price-eod-full API]")
    eod_api = await conn.fetchrow('''
        SELECT id, provider_name, endpoint_path
        FROM config_lv1_api_list
        WHERE id = 'fmp-historical-price-eod-full'
    ''')

    if eod_api:
        print(f"  ✓ fmp-historical-price-eod-full exists")
        print(f"    id: {eod_api['id']}")
        print(f"    provider: {eod_api['provider_name']}")
        print(f"    endpoint: {eod_api['endpoint_path']}")

        # Check if any metric uses this API
        metrics_using_eod = await conn.fetch('''
            SELECT id, domain, source
            FROM config_lv2_metric
            WHERE api_list_id = 'fmp-historical-price-eod-full'
        ''')

        print(f"\n  Metrics using fmp-historical-price-eod-full: {len(metrics_using_eod)}")
        for m in metrics_using_eod:
            print(f"    - {m['id']} (domain: {m['domain']}, source: {m['source']})")
    else:
        print(f"  ✗ fmp-historical-price-eod-full NOT FOUND")

    print("\n" + "=" * 80)
    print("DIAGNOSIS")
    print("=" * 80)

    if not row['api_list_id']:
        print("\n[ISSUE] priceEodOHLC has NULL api_list_id")
        print("  → This is why it returns None")
        print("  → Should be: 'fmp-historical-price-eod-full'")
    elif row['api_list_id'] != 'fmp-historical-price-eod-full':
        print(f"\n[ISSUE] priceEodOHLC uses wrong API: {row['api_list_id']}")
        print("  → Should be: 'fmp-historical-price-eod-full'")
    else:
        print("\n[OK] priceEodOHLC configuration looks correct")
        print("  → api_list_id is correct: fmp-historical-price-eod-full")
        print("  → response_key is dict format")
        print("  → Need to check why metric extraction is failing")

    await conn.close()


if __name__ == '__main__':
    asyncio.run(main())
