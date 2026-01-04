"""Test POST /backfillEventsTable endpoint directly"""
import asyncio
import httpx
import logging

# Set up logging to see all API logs
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)

async def test():
    print("\n" + "="*80)
    print("Testing POST /backfillEventsTable?overwrite=true&tickers=rgti")
    print("="*80)
    print("Looking for:")
    print("  1. Only RGTI API calls (no other tickers)")
    print("  2. Log format: [table: txn_events | id: ...] | [API Call] ...")
    print("="*80 + "\n")

    url = "http://localhost:8000/backfillEventsTable"
    params = {
        "overwrite": "true",
        "tickers": "rgti"
    }

    async with httpx.AsyncClient(timeout=300.0) as client:
        try:
            response = await client.post(url, params=params)
            print(f"\nResponse Status: {response.status_code}")
            if response.status_code == 200:
                result = response.json()
                print(f"\nResult Summary:")
                print(f"  Total events: {result.get('summary', {}).get('totalEventsProcessed', 0)}")
                print(f"  Quantitative success: {result.get('summary', {}).get('quantitativeSuccess', 0)}")
                print(f"  Qualitative success: {result.get('summary', {}).get('qualitativeSuccess', 0)}")
            else:
                print(f"Error: {response.text}")
        except Exception as e:
            print(f"Error calling endpoint: {e}")

    print("\n" + "="*80)
    print("Check the logs above for:")
    print("  - Any API calls to tickers other than RGTI")
    print("  - Missing [table: txn_events | id: ...] prefixes")
    print("="*80 + "\n")

if __name__ == '__main__':
    asyncio.run(test())
