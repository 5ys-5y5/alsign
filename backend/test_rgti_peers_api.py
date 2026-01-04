"""Test RGTI peer tickers API call."""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.services.external_api import FMPAPIClient


async def test_peers_api():
    """Test fmp-stock-peers API for RGTI."""

    print("\n=== Testing fmp-stock-peers API for RGTI ===\n")

    try:
        async with FMPAPIClient() as client:
            print("1. Calling fmp-stock-peers API...")
            response = await client.call_api('fmp-stock-peers', {'ticker': 'RGTI'})

            print(f"\n2. API Response Type: {type(response)}")
            print(f"3. Response Length: {len(response) if response else 0}")

            if response:
                print(f"\n4. First Response Item:")
                import json
                print(json.dumps(response[0] if isinstance(response, list) else response, indent=2))

                # Extract peer tickers
                peer_tickers = []
                for item in response:
                    peer_list = item.get('peerTickers', []) if isinstance(item, dict) else []
                    if isinstance(peer_list, list):
                        for peer in peer_list:
                            if isinstance(peer, dict) and 'symbol' in peer:
                                peer_ticker = peer['symbol']
                                if peer_ticker != 'RGTI':
                                    peer_tickers.append(peer_ticker)
                            elif isinstance(peer, str):
                                if peer != 'RGTI':
                                    peer_tickers.append(peer)

                print(f"\n5. Extracted Peer Tickers ({len(peer_tickers)}):")
                print(peer_tickers[:10] if len(peer_tickers) > 10 else peer_tickers)
            else:
                print("\n4. No response from API!")

    except Exception as e:
        print(f"\nERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    asyncio.run(test_peers_api())
