"""Test direct API call to verify logging"""
import asyncio
import logging
from src.services.external_api import FMPAPIClient

# Set up logging to see INFO level
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

async def test():
    print("\n" + "="*80)
    print("Testing direct API call with event_id")
    print("="*80 + "\n")

    async with FMPAPIClient() as client:
        # Test with event_id
        print("1. Calling API with event_id='test-event-123'")
        try:
            result = await client.call_api(
                'fmp-quote',
                {'ticker': 'AAPL'},
                event_id='test-event-123'
            )
            print(f"Result type: {type(result)}")
        except Exception as e:
            print(f"Error: {e}")

        print("\n2. Calling API with ticker-cache event_id")
        try:
            result = await client.call_api(
                'fmp-quote',
                {'ticker': 'MSFT'},
                event_id='ticker-cache:MSFT'
            )
            print(f"Result type: {type(result)}")
        except Exception as e:
            print(f"Error: {e}")

        print("\n3. Calling API without event_id")
        try:
            result = await client.call_api(
                'fmp-quote',
                {'ticker': 'GOOGL'}
            )
            print(f"Result type: {type(result)}")
        except Exception as e:
            print(f"Error: {e}")

    print("\n" + "="*80)
    print("Test completed - check logs above for [API Call] messages")
    print("="*80 + "\n")

if __name__ == '__main__':
    asyncio.run(test())
