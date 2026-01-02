"""Test script to verify target_summary calculation for RGTI ticker."""

import asyncio
import asyncpg
import json
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.config import settings

async def main():
    # Connect to database using settings
    conn = await asyncpg.connect(
        dsn=settings.DATABASE_URL,
        statement_cache_size=0  # Required for Supabase connection pooler
    )
    
    print("=" * 80)
    print("Testing target_summary calculation for RGTI")
    print("=" * 80)
    
    # 1. Check RGTI events in evt_consensus
    print("\n1. RGTI events in evt_consensus:")
    rows = await conn.fetch(
        """
        SELECT id, ticker, event_date, analyst_name, analyst_company, 
               price_target, price_when_posted, target_summary
        FROM evt_consensus 
        WHERE ticker = 'RGTI'
        ORDER BY event_date DESC
        """
    )
    
    print(f"   Found {len(rows)} RGTI events")
    for row in rows:
        print(f"   - {row['event_date']}: price_target={row['price_target']}, target_summary={'SET' if row['target_summary'] else 'NULL'}")
    
    # 2. Test calculate_target_summary query for one event
    print("\n2. Testing calculate_target_summary query for first RGTI event:")
    if rows:
        test_event = rows[0]
        ticker = test_event['ticker']
        event_date = test_event['event_date']
        
        print(f"   Testing for ticker={ticker}, event_date={event_date}")
        
        result = await conn.fetchrow(
            """
            WITH base_data AS (
                SELECT 
                    price_target,
                    analyst_company,
                    event_date,
                    $2::timestamptz AS ref_date
                FROM evt_consensus
                WHERE ticker = $1
                  AND event_date <= $2::timestamptz
                  AND price_target IS NOT NULL
            )
            SELECT
                -- Last Month (30 days)
                COUNT(*) FILTER (WHERE event_date > ref_date - INTERVAL '30 days') AS last_month_count,
                AVG(price_target) FILTER (WHERE event_date > ref_date - INTERVAL '30 days') AS last_month_avg,
                
                -- Last Quarter (90 days)
                COUNT(*) FILTER (WHERE event_date > ref_date - INTERVAL '90 days') AS last_quarter_count,
                AVG(price_target) FILTER (WHERE event_date > ref_date - INTERVAL '90 days') AS last_quarter_avg,
                
                -- Last Year (365 days)
                COUNT(*) FILTER (WHERE event_date > ref_date - INTERVAL '365 days') AS last_year_count,
                AVG(price_target) FILTER (WHERE event_date > ref_date - INTERVAL '365 days') AS last_year_avg,
                
                -- All Time
                COUNT(*) AS all_time_count,
                AVG(price_target) AS all_time_avg,
                
                -- Publishers (unique analyst companies)
                ARRAY_AGG(DISTINCT analyst_company) FILTER (WHERE analyst_company IS NOT NULL) AS publishers
            FROM base_data
            """,
            ticker,
            event_date
        )
        
        print(f"   Query result:")
        print(f"   - all_time_count: {result['all_time_count']}")
        print(f"   - all_time_avg: {result['all_time_avg']}")
        print(f"   - last_year_count: {result['last_year_count']}")
        print(f"   - last_quarter_count: {result['last_quarter_count']}")
        print(f"   - last_month_count: {result['last_month_count']}")
        print(f"   - publishers: {result['publishers']}")
        
        if result['all_time_count'] > 0:
            # Build target_summary
            target_summary = {
                'lastMonthCount': result['last_month_count'] or 0,
                'lastMonthAvgPriceTarget': round(float(result['last_month_avg']), 2) if result['last_month_avg'] else None,
                'lastQuarterCount': result['last_quarter_count'] or 0,
                'lastQuarterAvgPriceTarget': round(float(result['last_quarter_avg']), 2) if result['last_quarter_avg'] else None,
                'lastYearCount': result['last_year_count'] or 0,
                'lastYearAvgPriceTarget': round(float(result['last_year_avg']), 2) if result['last_year_avg'] else None,
                'allTimeCount': result['all_time_count'] or 0,
                'allTimeAvgPriceTarget': round(float(result['all_time_avg']), 2) if result['all_time_avg'] else None,
                'publishers': result['publishers'] or []
            }
            
            print(f"\n   Calculated target_summary:")
            print(f"   {json.dumps(target_summary, indent=2)}")
            
            # 3. Update target_summary for this event
            print(f"\n3. Updating target_summary for event {test_event['id']}...")
            await conn.execute(
                """
                UPDATE evt_consensus
                SET target_summary = $2::jsonb
                WHERE id = $1
                """,
                test_event['id'],
                json.dumps(target_summary)
            )
            print("   Updated successfully!")
            
            # 4. Verify update
            print("\n4. Verifying update:")
            updated = await conn.fetchrow(
                "SELECT target_summary FROM evt_consensus WHERE id = $1",
                test_event['id']
            )
            if updated['target_summary']:
                print(f"   target_summary is now SET:")
                print(f"   {json.dumps(updated['target_summary'], indent=2)}")
            else:
                print("   ERROR: target_summary is still NULL!")
        else:
            print("   ERROR: all_time_count is 0, target_summary would be NULL")
    
    # 5. Update all RGTI events
    print("\n5. Updating target_summary for ALL RGTI events...")
    update_count = 0
    for row in rows:
        ticker = row['ticker']
        event_date = row['event_date']
        
        result = await conn.fetchrow(
            """
            WITH base_data AS (
                SELECT 
                    price_target,
                    analyst_company,
                    event_date,
                    $2::timestamptz AS ref_date
                FROM evt_consensus
                WHERE ticker = $1
                  AND event_date <= $2::timestamptz
                  AND price_target IS NOT NULL
            )
            SELECT
                COUNT(*) FILTER (WHERE event_date > ref_date - INTERVAL '30 days') AS last_month_count,
                AVG(price_target) FILTER (WHERE event_date > ref_date - INTERVAL '30 days') AS last_month_avg,
                COUNT(*) FILTER (WHERE event_date > ref_date - INTERVAL '90 days') AS last_quarter_count,
                AVG(price_target) FILTER (WHERE event_date > ref_date - INTERVAL '90 days') AS last_quarter_avg,
                COUNT(*) FILTER (WHERE event_date > ref_date - INTERVAL '365 days') AS last_year_count,
                AVG(price_target) FILTER (WHERE event_date > ref_date - INTERVAL '365 days') AS last_year_avg,
                COUNT(*) AS all_time_count,
                AVG(price_target) AS all_time_avg,
                ARRAY_AGG(DISTINCT analyst_company) FILTER (WHERE analyst_company IS NOT NULL) AS publishers
            FROM base_data
            """,
            ticker,
            event_date
        )
        
        if result['all_time_count'] > 0:
            target_summary = {
                'lastMonthCount': result['last_month_count'] or 0,
                'lastMonthAvgPriceTarget': round(float(result['last_month_avg']), 2) if result['last_month_avg'] else None,
                'lastQuarterCount': result['last_quarter_count'] or 0,
                'lastQuarterAvgPriceTarget': round(float(result['last_quarter_avg']), 2) if result['last_quarter_avg'] else None,
                'lastYearCount': result['last_year_count'] or 0,
                'lastYearAvgPriceTarget': round(float(result['last_year_avg']), 2) if result['last_year_avg'] else None,
                'allTimeCount': result['all_time_count'] or 0,
                'allTimeAvgPriceTarget': round(float(result['all_time_avg']), 2) if result['all_time_avg'] else None,
                'publishers': result['publishers'] or []
            }
            
            await conn.execute(
                """
                UPDATE evt_consensus
                SET target_summary = $2::jsonb
                WHERE id = $1
                """,
                row['id'],
                json.dumps(target_summary)
            )
            update_count += 1
    
    print(f"   Updated {update_count} RGTI events")
    
    # 6. Final verification
    print("\n6. Final verification - RGTI events with target_summary:")
    final_rows = await conn.fetch(
        """
        SELECT id, event_date, target_summary
        FROM evt_consensus 
        WHERE ticker = 'RGTI'
        ORDER BY event_date DESC
        """
    )
    
    for row in final_rows:
        ts = row['target_summary']
        if ts:
            print(f"   - {row['event_date']}: allTimeCount={ts.get('allTimeCount')}, allTimeAvg={ts.get('allTimeAvgPriceTarget')}")
        else:
            print(f"   - {row['event_date']}: target_summary=NULL")
    
    await conn.close()
    print("\n" + "=" * 80)
    print("Test completed!")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())
