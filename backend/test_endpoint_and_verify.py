"""Call endpoint and verify position/disparity qualitative columns"""
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
            response = await client.post(url, params=params)
            print(f"Response Status: {response.status_code}")

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
    print("STEP 2: Verify database columns")
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

    # Check consensus event
    consensus_row = await conn.fetchrow('''
        SELECT id::text, ticker, event_date::date, source,
               position_quantitative,
               position_qualitative,
               disparity_quantitative,
               disparity_qualitative
        FROM txn_events
        WHERE id = $1
    ''', '1120c650-71fd-41f4-aa3d-2ea986214ed8')

    print(f"\nConsensus Event (ID: 1120c650...):")
    print(f"  Source: {consensus_row['source']}")
    print(f"  Date: {consensus_row['event_date']}")
    print(f"  position_quantitative:  {consensus_row['position_quantitative']}")
    print(f"  position_qualitative:   {consensus_row['position_qualitative']}")
    print(f"  disparity_quantitative: {consensus_row['disparity_quantitative']}")
    print(f"  disparity_qualitative:  {consensus_row['disparity_qualitative']}")

    # Check statistics
    stats = await conn.fetchrow('''
        SELECT COUNT(*) as total,
               COUNT(position_qualitative) as pos_qual_filled,
               COUNT(disparity_qualitative) as disp_qual_filled
        FROM txn_events
        WHERE ticker = 'RGTI'
          AND source = 'consensus'
    ''')

    print("\n" + "="*80)
    print("VERIFICATION RESULT")
    print("="*80)

    total = stats['total']
    pos_qual_pct = (stats['pos_qual_filled'] / total * 100) if total > 0 else 0
    disp_qual_pct = (stats['disp_qual_filled'] / total * 100) if total > 0 else 0

    print(f"\nConsensus Events Statistics:")
    print(f"  Total: {total}")
    print(f"  position_qualitative:  {stats['pos_qual_filled']}/{total} ({pos_qual_pct:.1f}%)")
    print(f"  disparity_qualitative: {stats['disp_qual_filled']}/{total} ({disp_qual_pct:.1f}%)")

    if stats['pos_qual_filled'] == total and stats['disp_qual_filled'] == total:
        print("\n[PASS] All consensus events have position_qualitative and disparity_qualitative!")
    else:
        print("\n[FAIL] Some consensus events are missing qualitative data!")

    print("="*80 + "\n")

    await conn.close()

if __name__ == '__main__':
    asyncio.run(test())
