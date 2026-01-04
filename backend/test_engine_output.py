"""Test what the metric engine actually returns."""
import asyncio
import json
from src.database.connection import db_pool
from src.database.queries import metrics as metrics_queries
from src.services.metric_engine import MetricCalculationEngine
from src.services.external_api import FMPAPIClient
from datetime import datetime

async def test():
    pool = await db_pool.get_pool()

    # Load metrics
    metrics_by_domain = await metrics_queries.select_metric_definitions(pool)
    transforms = await metrics_queries.select_metric_transforms(pool)

    # Initialize engine
    engine = MetricCalculationEngine(metrics_by_domain, transforms)
    engine.build_dependency_graph()
    engine.topological_sort()

    # Get required APIs
    required_apis = engine.get_required_apis()

    # Fetch API data for RGTI
    ticker = 'RGTI'
    event_date = datetime(2025, 12, 17)
    api_cache = {}

    async with FMPAPIClient() as fmp_client:
        for api_id in required_apis:
            params = {'ticker': ticker}
            if 'income-statement' in api_id or 'balance-sheet' in api_id or 'cash-flow' in api_id:
                params['period'] = 'quarter'
                params['limit'] = 20
            elif 'historical-market-cap' in api_id:
                params['fromDate'] = '2000-01-01'
                params['toDate'] = event_date.strftime('%Y-%m-%d')

            response = await fmp_client.call_api(api_id, params)
            if response:
                api_cache[api_id] = response

    # Calculate with custom values
    custom_values = {'priceQuantitative': 123.45}  # Test value

    result = engine.calculate_all(api_cache, ['valuation'], custom_values)

    print("=== ENGINE OUTPUT ===")
    print(json.dumps(result, indent=2))

    if 'valuation' in result:
        print("\n=== VALUATION KEYS ===")
        print(list(result['valuation'].keys()))

        if 'values' in result['valuation']:
            print("\n**ERROR**: Result has nested 'values' key! This shouldn't happen!")
        else:
            print("\n**OK**: Result has flat structure")

        if 'priceQuantitative' in result['valuation']:
            print(f"\npriceQuantitative: {result['valuation']['priceQuantitative']}")
        else:
            print("\n**ERROR**: priceQuantitative NOT in result!")

    await pool.close()

if __name__ == '__main__':
    asyncio.run(test())
