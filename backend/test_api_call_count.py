"""Test actual API call count for RGTI backfill"""
import asyncio
import logging
from collections import defaultdict
from src.database.connection import db_pool
from src.services import valuation_service

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    force=True
)

# Track API calls
api_call_counter = defaultdict(int)
api_calls_by_ticker = defaultdict(list)

# Monkey patch to count API calls
original_logger_info = logging.Logger.info

def counting_logger_info(self, msg, *args, **kwargs):
    if '[API Call]' in str(msg):
        # Extract ticker from URL
        msg_str = str(msg)
        if 'symbol=' in msg_str:
            ticker_start = msg_str.find('symbol=') + 7
            ticker_end = msg_str.find('&', ticker_start)
            if ticker_end == -1:
                ticker_end = msg_str.find(' ', ticker_start)
            ticker = msg_str[ticker_start:ticker_end]

            # Extract API name
            api_name = 'unknown'
            if '| [API Call]' in msg_str:
                parts = msg_str.split('| [API Call]')
                if len(parts) > 1:
                    api_part = parts[1].strip().split(' ')[0]
                    api_name = api_part

            api_call_counter[ticker] += 1
            api_calls_by_ticker[ticker].append(api_name)

    return original_logger_info(self, msg, *args, **kwargs)

logging.Logger.info = counting_logger_info

async def test():
    pool = await db_pool.get_pool()

    print("\n" + "="*80)
    print("Testing API Call Count for RGTI Backfill")
    print("="*80)
    print("Counting actual API calls made to FMP...\n")

    # Run backfill
    result = await valuation_service.calculate_valuations(
        overwrite=True,
        tickers=['RGTI'],
        calc_fair_value=True
    )

    print("\n" + "="*80)
    print("API CALL STATISTICS")
    print("="*80)

    total_calls = sum(api_call_counter.values())
    print(f"\nTotal API calls made: {total_calls}")
    print(f"\nBreakdown by ticker:")
    print("-" * 80)

    for ticker in sorted(api_call_counter.keys()):
        count = api_call_counter[ticker]
        apis = set(api_calls_by_ticker[ticker])
        print(f"  {ticker:10s}: {count:3d} calls ({len(apis)} unique APIs)")
        if ticker == 'RGTI':
            print(f"    APIs: {', '.join(sorted(apis))}")

    print("\n" + "="*80)
    print("BACKFILL RESULT")
    print("="*80)
    print(f"Events processed: {result['summary']['totalEventsProcessed']}")
    print(f"Quantitative success: {result['summary']['quantitativeSuccess']}")
    print(f"Qualitative success: {result['summary']['qualitativeSuccess']}")

    print("\n" + "="*80)
    print("ANALYSIS")
    print("="*80)

    rgti_calls = api_call_counter.get('RGTI', 0)
    events_count = result['summary']['totalEventsProcessed']

    if rgti_calls > len(api_calls_by_ticker['RGTI']):
        print(f"⚠️  WARNING: RGTI API called {rgti_calls} times for {events_count} events")
        print(f"    Expected: {len(set(api_calls_by_ticker['RGTI']))} calls (once per API type)")
        print(f"    This suggests API caching is NOT working properly!")
    else:
        print(f"✓  GOOD: RGTI API called {rgti_calls} times (ticker-level caching working)")
        print(f"    Events processed: {events_count}")

    print("="*80 + "\n")

    await db_pool.close()

if __name__ == '__main__':
    asyncio.run(test())
