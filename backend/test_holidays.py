"""Test script for holidays API."""
import asyncio
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.services.external_api import FMPAPIClient
from src.database.queries import holidays
from src.database.connection import db_pool

async def test_holidays():
    print('Testing FMP holidays API...')

    async with FMPAPIClient() as fmp_client:
        holidays_data = await fmp_client.get_market_holidays('NASDAQ')
        print(f'\nFetched {len(holidays_data) if holidays_data else 0} holidays from FMP API')

        if holidays_data:
            print(f'\nFirst 3 holidays:')
            for h in holidays_data[:3]:
                print(f'  - {h.get("date")}: {h.get("name")} (exchange: {h.get("exchange")})')

            # Test DB insert
            print('\nInserting into database...')
            pool = await db_pool.get_pool()
            result = await holidays.upsert_market_holidays(pool, holidays_data)
            print(f'DB upsert result: {result}')

            # Verify
            async with pool.acquire() as conn:
                count = await conn.fetchval('SELECT COUNT(*) FROM config_lv3_market_holidays')
                print(f'\nTotal records in DB: {count}')
        else:
            print('NO DATA RECEIVED!')

if __name__ == '__main__':
    asyncio.run(test_holidays())
