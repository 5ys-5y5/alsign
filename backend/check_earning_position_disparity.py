"""Check earning events position/disparity columns"""
import asyncio
import httpx
import asyncpg

async def test():
    print("\n" + "="*80)
    print("STEP 1: Call POST /backfillEventsTable endpoint")
    print("="*80)

    url = "http://localhost:8000/backfillEventsTable"
    params = {
        "overwrite": "true",
        "tickers": "rgti"
    }

    async with httpx.AsyncClient(timeout=300.0) as client:
        try:
            print(f"\nCalling: {url}?overwrite=true&tickers=rgti")
            print("Waiting for completion...")
            response = await client.post(url, params=params)
            print(f"\nResponse Status: {response.status_code}")

            if response.status_code == 200:
                result = response.json()
                print(f"\nEndpoint Result:")
                print(f"  Total events: {result['summary']['totalEventsProcessed']}")
                print(f"  Quant success: {result['summary']['quantitativeSuccess']}")
                print(f"  Qual success: {result['summary']['qualitativeSuccess']}")
            else:
                print(f"Error: {response.text}")
                return
        except Exception as e:
            print(f"Error calling endpoint: {e}")
            return

    print("\n" + "="*80)
    print("STEP 2: Check earning events in database")
    print("="*80)

    # Connect to database
    env_vars = {}
    with open('.env') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, val = line.split('=', 1)
                env_vars[key.strip()] = val.strip().strip('"')

    conn = await asyncpg.connect(env_vars['DATABASE_URL'], statement_cache_size=0)

    # Check the specific earning event from log
    earning_row = await conn.fetchrow('''
        SELECT id::text, ticker, event_date::date, source,
               value_quantitative IS NOT NULL as has_value_quant,
               price_quantitative,
               peer_quantitative IS NOT NULL as has_peer_quant,
               position_quantitative,
               disparity_quantitative,
               position_qualitative,
               disparity_qualitative
        FROM txn_events
        WHERE id = $1
    ''', 'c9690674-d4a1-406f-9959-540bdb2f72f0')

    print(f"\nEarning Event (ID: c9690674-d4a1-406f-9959-540bdb2f72f0):")
    print("-" * 80)
    print(f"Source: {earning_row['source']}")
    print(f"Date: {earning_row['event_date']}")
    print(f"\nQuantitative columns:")
    print(f"  value_quantitative:     {'SET' if earning_row['has_value_quant'] else 'NULL'}")
    print(f"  price_quantitative:     {earning_row['price_quantitative']}")
    print(f"  peer_quantitative:      {'SET' if earning_row['has_peer_quant'] else 'NULL'}")
    print(f"  position_quantitative:  {earning_row['position_quantitative']}")
    print(f"  disparity_quantitative: {earning_row['disparity_quantitative']}")
    print(f"\nQualitative columns:")
    print(f"  position_qualitative:   {earning_row['position_qualitative']}")
    print(f"  disparity_qualitative:  {earning_row['disparity_qualitative']}")

    # Check all earning events statistics
    stats = await conn.fetchrow('''
        SELECT COUNT(*) as total,
               COUNT(value_quantitative) as value_quant_filled,
               COUNT(price_quantitative) as price_quant_filled,
               COUNT(peer_quantitative) as peer_quant_filled,
               COUNT(position_quantitative) as pos_quant_filled,
               COUNT(disparity_quantitative) as disp_quant_filled,
               COUNT(position_qualitative) as pos_qual_filled,
               COUNT(disparity_qualitative) as disp_qual_filled
        FROM txn_events
        WHERE ticker = 'RGTI'
          AND source = 'earning'
    ''')

    print("\n" + "="*80)
    print("STATISTICS (all earning events)")
    print("="*80)

    total = stats['total']
    print(f"\nTotal earning events: {total}")
    print(f"\nQuantitative columns:")
    print(f"  value_quantitative:     {stats['value_quant_filled']}/{total} ({stats['value_quant_filled']/total*100 if total > 0 else 0:.1f}%)")
    print(f"  price_quantitative:     {stats['price_quant_filled']}/{total} ({stats['price_quant_filled']/total*100 if total > 0 else 0:.1f}%)")
    print(f"  peer_quantitative:      {stats['peer_quant_filled']}/{total} ({stats['peer_quant_filled']/total*100 if total > 0 else 0:.1f}%)")
    print(f"  position_quantitative:  {stats['pos_quant_filled']}/{total} ({stats['pos_quant_filled']/total*100 if total > 0 else 0:.1f}%)")
    print(f"  disparity_quantitative: {stats['disp_quant_filled']}/{total} ({stats['disp_quant_filled']/total*100 if total > 0 else 0:.1f}%)")
    print(f"\nQualitative columns:")
    print(f"  position_qualitative:   {stats['pos_qual_filled']}/{total} ({stats['pos_qual_filled']/total*100 if total > 0 else 0:.1f}%)")
    print(f"  disparity_qualitative:  {stats['disp_qual_filled']}/{total} ({stats['disp_qual_filled']/total*100 if total > 0 else 0:.1f}%)")

    print("\n" + "="*80)
    print("PROBLEM IDENTIFICATION")
    print("="*80)

    if stats['pos_quant_filled'] == 0:
        print("\n[CRITICAL] position_quantitative is NULL for ALL earning events!")
        print("Expected: Should be calculated using priceQuantitative and currentPrice")

    if stats['disp_quant_filled'] == 0:
        print("\n[CRITICAL] disparity_quantitative is NULL for ALL earning events!")
        print("Expected: Should be calculated using priceQuantitative and currentPrice")

    if stats['price_quant_filled'] == total:
        print(f"\n[INFO] price_quantitative is properly filled ({total}/{total})")
        print("This confirms the issue is NOT in priceQuantitative calculation")
        print("The issue is in position/disparity calculation logic")

    # Sample a few earning events to see the pattern
    print("\n" + "="*80)
    print("SAMPLE EARNING EVENTS")
    print("="*80)

    samples = await conn.fetch('''
        SELECT id::text as event_id,
               event_date::date,
               price_quantitative,
               position_quantitative,
               disparity_quantitative
        FROM txn_events
        WHERE ticker = 'RGTI'
          AND source = 'earning'
        ORDER BY event_date DESC
        LIMIT 5
    ''')

    print(f"\n{'EVENT_ID':<40} {'DATE':<12} {'PRICE_Q':<10} {'POS_Q':<10} {'DISP_Q':<10}")
    print("-" * 90)
    for row in samples:
        event_id = row['event_id'][:8] + "..."
        price_q = f"{row['price_quantitative']:.2f}" if row['price_quantitative'] else "NULL"
        pos_q = str(row['position_quantitative']) if row['position_quantitative'] else "NULL"
        disp_q = f"{row['disparity_quantitative']:.2f}" if row['disparity_quantitative'] else "NULL"
        print(f"{event_id:<40} {str(row['event_date']):<12} {price_q:<10} {pos_q:<10} {disp_q:<10}")

    print("\n" + "="*80 + "\n")

    await conn.close()

if __name__ == '__main__':
    asyncio.run(test())
