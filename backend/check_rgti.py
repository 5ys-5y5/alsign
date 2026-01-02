"""Check RGTI target_summary status."""

import asyncio
import asyncpg
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.config import settings

async def main():
    conn = await asyncpg.connect(dsn=settings.DATABASE_URL, statement_cache_size=0)
    rows = await conn.fetch('''
        SELECT ticker, event_date, 
               CASE WHEN target_summary IS NULL THEN 'NULL' ELSE 'SET' END as summary_status,
               target_summary
        FROM evt_consensus 
        WHERE ticker = 'RGTI'
        ORDER BY event_date DESC
    ''')
    print('RGTI target_summary status:')
    for row in rows:
        ts = row['target_summary']
        if ts:
            print(f"  {row['event_date']}: SET - allTimeCount={ts.get('allTimeCount') if isinstance(ts, dict) else 'N/A'}")
        else:
            print(f"  {row['event_date']}: NULL")
    await conn.close()

asyncio.run(main())
