"""Backfill target_summary for all evt_consensus events that have NULL target_summary."""

import asyncio
import asyncpg
import json
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.config import settings

BATCH_SIZE = 100

async def calculate_target_summary(conn, ticker: str, event_date) -> dict:
    """Calculate target summary for a single event."""
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
    
    if not result or result['all_time_count'] == 0:
        return None
    
    return {
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


async def main():
    print("=" * 80)
    print("Backfilling target_summary for all evt_consensus events")
    print("=" * 80)
    
    conn = await asyncpg.connect(dsn=settings.DATABASE_URL, statement_cache_size=0)
    
    # Get count of events with NULL target_summary
    null_count = await conn.fetchval(
        "SELECT COUNT(*) FROM evt_consensus WHERE target_summary IS NULL"
    )
    total_count = await conn.fetchval(
        "SELECT COUNT(*) FROM evt_consensus"
    )
    
    print(f"\nTotal events: {total_count}")
    print(f"Events with NULL target_summary: {null_count}")
    print(f"Events already processed: {total_count - null_count}")
    
    if null_count == 0:
        print("\nAll events already have target_summary!")
        await conn.close()
        return
    
    print(f"\nProcessing {null_count} events...")
    
    # Get all events with NULL target_summary
    rows = await conn.fetch(
        """
        SELECT id, ticker, event_date
        FROM evt_consensus 
        WHERE target_summary IS NULL
        ORDER BY ticker, event_date
        """
    )
    
    start_time = time.time()
    success_count = 0
    skip_count = 0
    fail_count = 0
    updates = []
    
    for idx, row in enumerate(rows):
        try:
            target_summary = await calculate_target_summary(conn, row['ticker'], row['event_date'])
            
            if target_summary:
                updates.append({
                    'id': row['id'],
                    'target_summary': target_summary
                })
                success_count += 1
            else:
                skip_count += 1
            
            # Batch update every BATCH_SIZE events
            if len(updates) >= BATCH_SIZE:
                await batch_update(conn, updates)
                updates = []
            
            # Log progress every 500 events
            if (idx + 1) % 500 == 0 or (idx + 1) == len(rows):
                elapsed = time.time() - start_time
                rate = (idx + 1) / elapsed if elapsed > 0 else 0
                remaining = len(rows) - (idx + 1)
                eta_seconds = remaining / rate if rate > 0 else 0
                eta_str = f"{int(eta_seconds)}s" if eta_seconds < 60 else f"{int(eta_seconds/60)}m {int(eta_seconds%60)}s"
                
                pct = ((idx + 1) / len(rows)) * 100
                print(f"  Progress: {idx + 1}/{len(rows)} ({pct:.1f}%) | rate={rate:.1f}/s | ETA: {eta_str} | success={success_count}, skip={skip_count}, fail={fail_count}")
        
        except Exception as e:
            print(f"  Error for {row['ticker']} {row['event_date']}: {e}")
            fail_count += 1
    
    # Final batch update
    if updates:
        await batch_update(conn, updates)
    
    elapsed = time.time() - start_time
    
    print(f"\n" + "=" * 80)
    print(f"Backfill completed in {elapsed:.1f}s")
    print(f"  Success: {success_count}")
    print(f"  Skipped: {skip_count}")
    print(f"  Failed: {fail_count}")
    print("=" * 80)
    
    # Verify
    remaining_null = await conn.fetchval(
        "SELECT COUNT(*) FROM evt_consensus WHERE target_summary IS NULL"
    )
    print(f"\nRemaining events with NULL target_summary: {remaining_null}")
    
    await conn.close()


async def batch_update(conn, updates):
    """Batch update target_summary for multiple events."""
    if not updates:
        return
    
    for update in updates:
        await conn.execute(
            """
            UPDATE evt_consensus
            SET target_summary = $2::jsonb
            WHERE id = $1
            """,
            update['id'],
            json.dumps(update['target_summary'])
        )


if __name__ == "__main__":
    asyncio.run(main())
